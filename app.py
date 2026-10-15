import os
import time
import threading
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from io import BytesIO

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from dhanhq import DhanContext, MarketFeed


st.set_page_config(
    page_title="Dhan Live BUY SELL Scanner",
    page_icon="📈",
    layout="wide",
)

IST = ZoneInfo("Asia/Kolkata")

WATCHLIST = {
    "RELIANCE": "2885",
    "BHARTIARTL": "10604",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "SBIN": "3045",
    "TCS": "11536",
    "BAJFINANCE": "317",
    "LT": "11483",
    "LICI": "9480",
    "HINDUNILVR": "1394",
}

COLUMNS = [
    "Date", "Time", "Symbol", "Signal",
    "Breakout Price", "Trigger Candle", "Trigger Volume",
]


def now_ist():
    return datetime.now(IST)


def market_is_open():
    now = now_ist()
    return (
        now.weekday() < 5
        and dt_time(9, 15) <= now.time() <= dt_time(15, 15)
    )


class ScannerEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.direction = None
        self.thread_started = False
        self.status = "BUY या SELL चुनें"
        self.logs = []
        self.symbols = {}

        for symbol, sid in WATCHLIST.items():
            self.symbols[sid] = {
                "symbol": symbol,
                "last_price": None,
                "last_cum_volume": None,
                "candle": None,
                "completed": [],
                "baseline_min": None,
                "baseline_ready": False,
                "reference": None,
                "last_signal_candle": None,
                "error": None,
            }

    def choose(self, direction):
        with self.lock:
            if self.direction != direction:
                self.direction = direction
                for item in self.symbols.values():
                    item["reference"] = None
                    item["last_signal_candle"] = None

            if not self.thread_started:
                self.thread_started = True
                threading.Thread(
                    target=self.run_feed,
                    daemon=True,
                    name="dhan-market-feed",
                ).start()

            self.status = f"{direction} चुना गया — लाइव डेटा की प्रतीक्षा"

    def add_signal(self, item, direction, price, candle):
        stamp = now_ist()
        self.logs.append({
            "Date": stamp.strftime("%Y-%m-%d"),
            "Time": stamp.strftime("%H:%M:%S"),
            "Symbol": item["symbol"],
            "Signal": direction,
            "Breakout Price": round(float(price), 2),
            "Trigger Candle": candle["start"].strftime("%H:%M"),
            "Trigger Volume": int(candle["volume"]),
        })
        item["last_signal_candle"] = candle["start"]
        item["reference"] = None

    def finish_candle(self, item, candle):
        if candle is None:
            return

        item["completed"].append(candle)
        start = candle["start"]

        # Baseline केवल 9:15, 9:20 और 9:25 वाली
        # तीन शुरुआती 5-minute candles से बनेगा.
        if start.date() != now_ist().date():
            return

        first_three_times = {
            dt_time(9, 15),
            dt_time(9, 20),
            dt_time(9, 25),
        }

        first_three = [
            c for c in item["completed"]
            if c["start"].date() == start.date()
            and c["start"].time() in first_three_times
            and c["end"] is not None
        ]

        if len(first_three) == 3 and not item["baseline_ready"]:
            item["baseline_min"] = min(c["volume"] for c in first_three)
            item["baseline_ready"] = True

    def on_tick(self, data):
        if not isinstance(data, dict):
            return

        sid = str(data.get("security_id", ""))
        if sid not in self.symbols:
            return

        try:
            price = float(data.get("LTP"))
        except (TypeError, ValueError):
            return

        if price <= 0:
            return

        item = self.symbols[sid]
        stamp = now_ist()

        # Quote/Full packet में volume पूरे दिन का cumulative volume है.
        # Candle volume के लिए केवल positive volume differences जोड़ें.
        try:
            cum_volume = int(data.get("volume", 0))
        except (TypeError, ValueError):
            cum_volume = 0

        previous_cum = item["last_cum_volume"]
        delta = 0

        if previous_cum is not None and cum_volume >= previous_cum:
            delta = cum_volume - previous_cum
        elif previous_cum is not None and cum_volume < previous_cum:
            # Volume reset या data reset होने पर गलत बड़ा delta न जोड़ें.
            delta = 0

        item["last_cum_volume"] = cum_volume
        item["last_price"] = price

        # Five-minute candle boundary, IST
        minute = (stamp.minute // 5) * 5
        candle_start = stamp.replace(
            minute=minute, second=0, microsecond=0
        )

        candle = item["candle"]

        if candle is None or candle["start"] != candle_start:
            if candle is not None:
                candle["end"] = candle["start"] + pd.Timedelta(minutes=5)
                self.finish_candle(item, candle)

            candle = {
                "start": candle_start,
                "end": None,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": max(0, delta),
            }
            item["candle"] = candle
        else:
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
            candle["volume"] += max(0, delta)

        with self.lock:
            direction = self.direction

        if direction not in ("BUY", "SELL"):
            return

        if not market_is_open():
            return

        if not item["baseline_ready"]:
            return

        minimum_volume = item["baseline_min"]
        if minimum_volume is None:
            return

        # एक reference candle केवल तभी मान्य है जब उसकी
        # candle पूरी हो चुकी हो और volume शुरुआती minimum से कम हो.
        completed = item["completed"]
        if completed:
            latest = completed[-1]

            if latest["volume"] < minimum_volume:
                is_red = latest["close"] < latest["open"]
                is_green = latest["close"] > latest["open"]

                if direction == "BUY" and is_red:
                    item["reference"] = {
                        "kind": "RED",
                        "level": latest["high"],
                        "candle": latest,
                    }

                elif direction == "SELL" and is_green:
                    item["reference"] = {
                        "kind": "GREEN",
                        "level": latest["low"],
                        "candle": latest,
                    }

        ref = item["reference"]
        if not ref:
            return

        # Signal candle must be later than the reference candle.
        if candle["start"] <= ref["candle"]["start"]:
            return

        # Breakout is checked on each incoming tick, not at candle close.
        if (
            direction == "BUY"
            and ref["kind"] == "RED"
            and candle["close"] > candle["open"]
            and price > ref["level"]
        ):
            self.add_signal(item, "BUY", price, ref["candle"])

        elif (
            direction == "SELL"
            and ref["kind"] == "GREEN"
            and candle["close"] < candle["open"]
            and price < ref["level"]
        ):
            self.add_signal(item, "SELL", price, ref["candle"])

    def run_feed(self):
        token = st.secrets.get(
            "DHAN_ACCESS_TOKEN", os.getenv("DHAN_ACCESS_TOKEN", "")
        )
        client_id = st.secrets.get(
            "DHAN_CLIENT_ID", os.getenv("DHAN_CLIENT_ID", "")
        )

        if not token or not client_id:
            with self.lock:
                self.status = "Dhan credentials नहीं मिले"
            return

        instruments = [
            (MarketFeed.NSE, sid, MarketFeed.Full)
            for sid in WATCHLIST.values()
        ]

        while True:
            try:
                context = DhanContext(client_id, token)
                feed = MarketFeed(context, instruments, version="v2")
                feed.run_forever()

                with self.lock:
                    self.status = "Dhan WebSocket connected"

                while True:
                    packet = feed.get_data()
                    if isinstance(packet, dict):
                        self.on_tick(packet)

            except Exception as exc:
                with self.lock:
                    self.status = (
                        "Feed reconnect हो रहा है: "
                        + str(exc)[:180]
                    )
                time.sleep(5)


@st.cache_resource
def get_engine():
    return ScannerEngine()


engine = get_engine()

st.title("📈 Dhan Live BUY / SELL Scanner")
st.caption("Market time: 09:15–15:15 IST | Signal only — no orders placed")

token = st.secrets.get(
    "DHAN_ACCESS_TOKEN", os.getenv("DHAN_ACCESS_TOKEN", "")
)
client_id = st.secrets.get(
    "DHAN_CLIENT_ID", os.getenv("DHAN_CLIENT_ID", "")
)

if token and client_id:
    st.success("Dhan credentials मिले")
else:
    st.error(
        "Streamlit Settings → Secrets में DHAN_ACCESS_TOKEN "
        "और DHAN_CLIENT_ID भरें।"
    )

left, right = st.columns(2)

with left:
    if st.button("🟢 BUY", use_container_width=True):
        engine.choose("BUY")

with right:
    if st.button("🔴 SELL", use_container_width=True):
        engine.choose("SELL")

with engine.lock:
    selected = engine.direction
    status = engine.status
    records = list(engine.logs)

if selected:
    st.info(f"Selected direction: {selected}")

st.write("**Scanner status:**", status)

st.subheader("Watchlist")
watchlist_df = pd.DataFrame([
    {"Symbol": symbol, "Security ID": sid}
    for symbol, sid in WATCHLIST.items()
])
st.dataframe(watchlist_df, use_container_width=True, hide_index=True)

st.subheader("Live Prices")
with engine.lock:
    price_rows = [
        {
            "Symbol": data["symbol"],
            "LTP": data["last_price"],
            "Baseline Min Volume": data["baseline_min"],
            "Baseline Ready": data["baseline_ready"],
        }
        for data in engine.symbols.values()
    ]
st.dataframe(pd.DataFrame(price_rows), use_container_width=True, hide_index=True)

st.subheader("Signal Records")
records_df = pd.DataFrame(records, columns=COLUMNS)
st.dataframe(records_df, use_container_width=True, hide_index=True)

output = BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    records_df.to_excel(writer, index=False, sheet_name="Signals")
    watchlist_df.to_excel(writer, index=False, sheet_name="Watchlist")

st.download_button(
    "⬇️ Download Excel",
    data=output.getvalue(),
    file_name=f"dhan_signals_{now_ist():%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.caption(f"Current IST: {now_ist():%d-%m-%Y %H:%M:%S}")
st_autorefresh(interval=5000, key="scanner_refresh")
