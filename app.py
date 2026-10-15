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
    page_title="Dhan Live Scanner",
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
    n = now_ist()
    return (
        n.weekday() < 5
        and dt_time(9, 15) <= n.time() <= dt_time(15, 15)
    )


class Scanner:
    def __init__(self):
        self.lock = threading.RLock()
        self.direction = None
        self.status = "Starting live feed..."
        self.started = False
        self.records = []
        self.items = {}

        for symbol, sid in WATCHLIST.items():
            self.items[sid] = {
                "symbol": symbol,
                "ltp": None,
                "last_cum_volume": None,
                "candle": None,
                "completed": [],
                "baseline_min": None,
                "baseline_ready": False,
                "reference": None,
                "signal_candle": None,
                "feed_time": None,
            }

    def start(self):
        with self.lock:
            if self.started:
                return
            self.started = True

        threading.Thread(
            target=self.feed_loop,
            daemon=True,
            name="dhan-live-feed",
        ).start()

    def select(self, direction):
        with self.lock:
            self.direction = direction
            self.status = (
                f"{direction} selected — waiting for valid setup"
            )

    def feed_loop(self):
        try:
            token = st.secrets.get(
                "DHAN_ACCESS_TOKEN",
                os.getenv("DHAN_ACCESS_TOKEN", ""),
            )
            client_id = st.secrets.get(
                "DHAN_CLIENT_ID",
                os.getenv("DHAN_CLIENT_ID", ""),
            )
        except Exception:
            token = os.getenv("DHAN_ACCESS_TOKEN", "")
            client_id = os.getenv("DHAN_CLIENT_ID", "")

        if not token or not client_id:
            with self.lock:
                self.status = "Dhan credentials missing"
            return

        instruments = [
            (MarketFeed.NSE, sid, MarketFeed.Full)
            for sid in WATCHLIST.values()
        ]

        while True:
            try:
                context = DhanContext(client_id, token)
                feed = MarketFeed(context, instruments, version="v2")

                with self.lock:
                    self.status = "Connecting to Dhan WebSocket..."

                feed.run_forever()

                with self.lock:
                    self.status = "WebSocket connected"

                while True:
                    packet = feed.get_data()
                    if isinstance(packet, dict):
                        self.on_tick(packet)

            except Exception as exc:
                with self.lock:
                    self.status = (
                        "Feed error/reconnecting: " + str(exc)[:160]
                    )
                time.sleep(5)

    def finish_candle(self, item, candle):
        candle["end"] = candle["start"].replace()
        item["completed"].append(candle)

        # Use only the opening three candles: 09:15, 09:20, 09:25.
        today = now_ist().date()
        opening_times = {dt_time(9, 15), dt_time(9, 20), dt_time(9, 25)}

        opening = [
            c for c in item["completed"]
            if c["start"].date() == today
            and c["start"].time() in opening_times
        ]

        if len(opening) == 3 and not item["baseline_ready"]:
            item["baseline_min"] = min(c["volume"] for c in opening)
            item["baseline_ready"] = True

    def record_signal(self, item, direction, price, reference):
        stamp = now_ist()

        with self.lock:
            self.records.append({
                "Date": stamp.strftime("%Y-%m-%d"),
                "Time": stamp.strftime("%H:%M:%S"),
                "Symbol": item["symbol"],
                "Signal": direction,
                "Breakout Price": round(float(price), 2),
                "Trigger Candle": reference["start"].strftime("%H:%M"),
                "Trigger Volume": int(reference["volume"]),
            })

        item["signal_candle"] = item["candle"]["start"]
        item["reference"] = None

    def on_tick(self, packet):
        sid = str(packet.get("security_id", ""))
        if sid not in self.items:
            return

        try:
            price = float(packet.get("LTP"))
            cum_volume = int(packet.get("volume", 0))
        except (TypeError, ValueError):
            return

        if price <= 0:
            return

        stamp = now_ist()
        item = self.items[sid]

        with self.lock:
            item["ltp"] = price
            item["feed_time"] = stamp.strftime("%H:%M:%S")
            direction = self.direction

        # Dhan Full packets provide cumulative traded volume.
        # Add only the positive difference to the active candle.
        previous_volume = item["last_cum_volume"]
        delta = 0

        if previous_volume is not None and cum_volume >= previous_volume:
            delta = cum_volume - previous_volume

        item["last_cum_volume"] = cum_volume

        candle_start = stamp.replace(
            minute=(stamp.minute // 5) * 5,
            second=0,
            microsecond=0,
        )

        candle = item["candle"]

        if candle is None or candle["start"] != candle_start:
            if candle is not None:
                self.finish_candle(item, candle)

            candle = {
                "start": candle_start,
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

        # Collect data from 09:15 even before BUY/SELL is selected.
        if not market_is_open() or direction not in ("BUY", "SELL"):
            return

        if not item["baseline_ready"]:
            return

        # Do not signal on the opening three candles.
        if stamp.time() < dt_time(9, 30):
            return

        completed = item["completed"]
        if not completed:
            return

        latest = completed[-1]
        min_volume = item["baseline_min"]

        # Low-volume RED candle is the BUY reference.
        # Low-volume GREEN candle is the SELL reference.
        if latest["volume"] < min_volume:
            red = latest["close"] < latest["open"]
            green = latest["close"] > latest["open"]

            if direction == "BUY" and red:
                item["reference"] = {
                    "start": latest["start"],
                    "high": latest["high"],
                    "low": latest["low"],
                    "open": latest["open"],
                    "close": latest["close"],
                    "volume": latest["volume"],
                    "kind": "RED",
                }

            elif direction == "SELL" and green:
                item["reference"] = {
                    "start": latest["start"],
                    "high": latest["high"],
                    "low": latest["low"],
                    "open": latest["open"],
                    "close": latest["close"],
                    "volume": latest["volume"],
                    "kind": "GREEN",
                }

        reference = item["reference"]
        if not reference:
            return

        # Only a candle after the reference candle can trigger.
        if candle["start"] <= reference["start"]:
            return

        # Check breakout on every tick, without waiting for candle close.
        if (
            direction == "BUY"
            and reference["kind"] == "RED"
            and price > reference["high"]
        ):
            self.record_signal(item, "BUY", price, reference)

        elif (
            direction == "SELL"
            and reference["kind"] == "GREEN"
            and price < reference["low"]
        ):
            self.record_signal(item, "SELL", price, reference)


@st.cache_resource
def get_scanner():
    return Scanner()


scanner = get_scanner()

# IMPORTANT: Start feed on app load, not when BUY/SELL is pressed.
scanner.start()

st.title("📈 Dhan Live BUY / SELL Scanner")
st.caption("09:15–15:15 IST | Signals only — no automatic orders")

left, right = st.columns(2)

with left:
    if st.button("🟢 BUY", use_container_width=True):
        scanner.select("BUY")

with right:
    if st.button("🔴 SELL", use_container_width=True):
        scanner.select("SELL")

with scanner.lock:
    status = scanner.status
    direction = scanner.direction
    records = list(scanner.records)
    price_rows = [
        {
            "Symbol": item["symbol"],
            "LTP": item["ltp"],
            "Last Feed Time": item["feed_time"],
            "Opening Min Volume": item["baseline_min"],
            "Opening 3 Candles Ready": item["baseline_ready"],
        }
        for item in scanner.items.values()
    ]

st.write("**Scanner status:**", status)
st.write("**Selected direction:**", direction or "Not selected")

st.subheader("Live Prices and Opening Volume")
st.dataframe(
    pd.DataFrame(price_rows),
    use_container_width=True,
    hide_index=True,
)

st.subheader("Signal Records")
records_df = pd.DataFrame(records, columns=COLUMNS)
st.dataframe(
    records_df,
    use_container_width=True,
    hide_index=True,
)

excel = BytesIO()
with pd.ExcelWriter(excel, engine="openpyxl") as writer:
    records_df.to_excel(writer, index=False, sheet_name="Signals")
    pd.DataFrame(price_rows).to_excel(
        writer, index=False, sheet_name="Live Status"
    )

st.download_button(
    "⬇️ Download Excel",
    data=excel.getvalue(),
    file_name=f"dhan_signals_{now_ist():%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.caption("Current IST: " + now_ist().strftime("%d-%m-%Y %H:%M:%S"))
st_autorefresh(interval=5000, key="refresh_scanner")
