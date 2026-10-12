
import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="NSE F&O Paper Scanner",
    page_icon="📈",
    layout="wide"
)

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_WATCHLIST = pd.DataFrame({
    "symbol": [
        "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "INFY",
        "TCS", "AXISBANK", "TATAMOTORS", "LT", "BHARTIARTL"
    ],
    "security_id": [""] * 10
})


def get_dhan_client():
    """Read Dhan credentials from Streamlit Secrets."""
    try:
        client_id = st.secrets["DHAN_CLIENT_ID"]
        access_token = st.secrets["DHAN_ACCESS_TOKEN"]

        if not client_id or not access_token:
            return None, "Dhan Client ID ya Access Token khaali hai."

        from dhanhq import DhanContext, dhanhq

        context = DhanContext(str(client_id), str(access_token))
        return dhanhq(context), None

    except Exception as exc:
        return None, (
            "Dhan connection taiyar nahi hua. Secrets aur package check karein. "
            f"Details: {exc}"
        )


def fetch_5min_candles(dhan, security_id):
    """Fetch 5-minute NSE equity candles for today's date."""
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")

    response = dhan.intraday_minute_data(
        security_id=str(security_id),
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        from_date=f"{today} 09:15:00",
        to_date=now.strftime("%Y-%m-%d %H:%M:%S"),
        interval=5
    )

    if not isinstance(response, dict):
        raise ValueError("Dhan API ka response samajh nahi aaya.")

    if response.get("status") != "success":
        raise ValueError(str(response.get("remarks", response)))

    data = response.get("data") or {}
    if not data or not data.get("timestamp"):
        return pd.DataFrame()

    df = pd.DataFrame({
        "datetime": data["timestamp"],
        "open": data["open"],
        "high": data["high"],
        "low": data["low"],
        "close": data["close"],
        "volume": data["volume"]
    })

    # Dhan timestamps are normally Unix epoch values.
    df["datetime"] = pd.to_datetime(
        df["datetime"], unit="s", utc=True
    ).dt.tz_convert("Asia/Kolkata")

    return df.sort_values("datetime").reset_index(drop=True)


def make_demo_data(symbol):
    """Clearly labelled synthetic data; never use as live prices."""
    random.seed(symbol + datetime.now(IST).strftime("%Y%m%d"))
    now = datetime.now(IST).replace(second=0, microsecond=0)
    now = now.replace(minute=(now.minute // 5) * 5)

    base = random.uniform(100, 3000)
    rows = []

    start = now.replace(hour=9, minute=15)
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        start = now - timedelta(minutes=15)

    for i in range(30):
        candle_time = start + timedelta(minutes=5 * i)
        if candle_time > now:
            break

        o = base
        c = max(1, o * (1 + random.uniform(-0.008, 0.008)))
        h = max(o, c) * (1 + random.uniform(0, 0.003))
        l = min(o, c) * (1 - random.uniform(0, 0.003))

        rows.append({
            "datetime": candle_time,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": random.randint(1000, 100000)
        })
        base = c

    return pd.DataFrame(rows)


if "watchlist" not in st.session_state:
    st.session_state.watchlist = DEFAULT_WATCHLIST.copy()

if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = []

st.title("📈 NSE F&O Paper Trading Scanner")
st.caption("5-Minute Candles | Dhan API | Paper Trading Only")

st.sidebar.header("⚙️ Scanner Settings")

source = st.sidebar.radio(
    "Data Source",
    ["Dhan API", "Upload Candle CSV", "Demo Mode"]
)

st.sidebar.warning(
    "Paper trading only. This app does not place real orders."
)

st.subheader("F&O Watchlist")
st.write(
    "Apne chune hue NSE F&O stocks ke Dhan Security IDs bharein. "
    "Yeh list apne-aap highest-activity stocks select nahi karti."
)

edited_watchlist = st.data_editor(
    st.session_state.watchlist,
    num_rows="fixed",
    use_container_width=True,
    key="watchlist_editor",
    column_config={
        "symbol": st.column_config.TextColumn(
            "Stock Symbol", required=True
        ),
        "security_id": st.column_config.TextColumn(
            "Dhan Security ID",
            help="NSE equity segment ke liye sahi ID bharein."
        )
    }
)

st.session_state.watchlist = edited_watchlist.copy()

st.subheader("🌐 NSE Market Advance–Decline")
c1, c2, c3 = st.columns(3)

with c1:
    advances = st.number_input(
        "Advances", min_value=0, value=0, step=1
    )
with c2:
    declines = st.number_input(
        "Declines", min_value=0, value=0, step=1
    )
with c3:
    unchanged = st.number_input(
        "Unchanged", min_value=0, value=0, step=1
    )

if advances > declines:
    breadth_bias = "BUY BIAS"
elif declines > advances:
    breadth_bias = "SELL BIAS"
else:
    breadth_bias = "NEUTRAL"

st.info(
    f"Entered market breadth: {breadth_bias}. "
    "Yeh numbers manual hain; app abhi NSE breadth automatically fetch nahi karta."
)

st.divider()
st.subheader("🔍 Stock Scanner")

uploaded_file = None
if source == "Upload Candle CSV":
    uploaded_file = st.file_uploader(
        "Candle CSV upload karein",
        type=["csv"],
        help="Columns: symbol, datetime, open, high, low, close, volume"
    )

if source == "Dhan API":
    st.caption(
        "Dhan API mode: Security IDs bhar kar refresh karein. "
        "API access, token aur market hours ke hisaab se data mil sakta hai."
    )

if source == "Demo Mode":
    st.warning("Demo Mode: neeche ka data nakli/synthetic hai.")

if st.button("🔄 Refresh Scanner", type="primary"):
    all_rows = []
    errors = []

    if source == "Dhan API":
        dhan, error = get_dhan_client()

        if error:
            st.error(error)
        else:
            valid_rows = st.session_state.watchlist.copy()
            valid_rows["security_id"] = (
                valid_rows["security_id"].fillna("").astype(str).str.strip()
            )
            valid_rows = valid_rows[
                valid_rows["security_id"] != ""
            ]

            if valid_rows.empty:
                st.error(
                    "Pehle watchlist mein valid Dhan Security IDs bharein."
                )
            else:
                progress = st.progress(0)

                for i, row in enumerate(
                    valid_rows.itertuples(index=False), start=1
                ):
                    try:
                        candles = fetch_5min_candles(
                            dhan, row.security_id
                        )
                        if not candles.empty:
                            candles["symbol"] = row.symbol
                            all_rows.append(candles)
                        else:
                            errors.append(
                                f"{row.symbol}: abhi candle data nahi mila."
                            )
                    except Exception as exc:
                        errors.append(f"{row.symbol}: {exc}")

                    progress.progress(i / len(valid_rows))

                if all_rows:
                    st.session_state["last_scan"] = pd.concat(
                        all_rows, ignore_index=True
                    )
                    st.session_state["last_source"] = "Dhan API"

                for message in errors:
                    st.warning(message)

    elif source == "Upload Candle CSV":
        if uploaded_file is None:
            st.error("Pehle CSV file upload karein.")
        else:
            try:
                csv_df = pd.read_csv(uploaded_file)
                required = {
                    "symbol", "datetime", "open", "high",
                    "low", "close", "volume"
                }
                missing = required - set(csv_df.columns)

                if missing:
                    st.error(
                        "CSV mein yeh columns missing hain: "
                        + ", ".join(sorted(missing))
                    )
                else:
                    csv_df["datetime"] = pd.to_datetime(
                        csv_df["datetime"], errors="coerce"
                    )
                    for col in ["open", "high", "low", "close", "volume"]:
                        csv_df[col] = pd.to_numeric(
                            csv_df[col], errors="coerce"
                        )

                    csv_df = csv_df.dropna(
                        subset=[
                            "datetime", "open", "high",
                            "low", "close", "volume"
                        ]
                    )
                    st.session_state["last_scan"] = csv_df
                    st.session_state["last_source"] = "CSV"
            except Exception as exc:
                st.error(f"CSV read nahi ho paayi: {exc}")

    else:
        demo_rows = []
        for symbol in st.session_state.watchlist["symbol"]:
            candles = make_demo_data(str(symbol))
            if not candles.empty:
                candles["symbol"] = symbol
                demo_rows.append(candles)

        if demo_rows:
            st.session_state["last_scan"] = pd.concat(
                demo_rows, ignore_index=True
            )
            st.session_state["last_source"] = "Demo Mode"

if "last_scan" in st.session_state:
    scan_df = st.session_state["last_scan"].copy()
    st.caption(f"Displayed source: {st.session_state.get('last_source', 'Unknown')}")

    if not scan_df.empty:
        # Latest candle for each symbol
        latest = (
            scan_df.sort_values("datetime")
            .groupby("symbol", as_index=False)
            .tail(1)
            .sort_values("symbol")
        )

        st.markdown("#### Latest candle by stock")
        st.dataframe(latest, use_container_width=True, hide_index=True)

        st.markdown("#### All available candles")
        st.dataframe(
            scan_df.sort_values(["symbol", "datetime"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Download scanned candles CSV",
            data=scan_df.to_csv(index=False).encode("utf-8"),
            file_name="paper_scanner_candles.csv",
            mime="text/csv"
        )
    else:
        st.info("Is scan mein candles nahi mili.")

st.divider()
st.subheader("📝 Paper Trading")

with st.form("paper_trade_form"):
    watch_symbols = st.session_state.watchlist["symbol"].tolist()
    trade_symbol = st.selectbox("Stock", watch_symbols)
    trade_side = st.selectbox("Side", ["BUY", "SELL"])
    trade_price = st.number_input(
        "Entry Price", min_value=0.0, value=0.0, step=0.05
    )
    trade_qty = st.number_input(
        "Quantity", min_value=1, value=1, step=1
    )
    trade_note = st.text_input("Note (optional)")
    submitted = st.form_submit_button("Add Paper Trade")

    if submitted:
        if trade_price <= 0:
            st.error("Entry Price zero se zyada hona chahiye.")
        else:
            st.session_state.paper_trades.append({
                "time": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": trade_symbol,
                "side": trade_side,
                "entry_price": trade_price,
                "quantity": int(trade_qty),
                "note": trade_note,
                "status": "PAPER ONLY"
            })
            st.success("Paper trade record add ho gaya.")

if st.session_state.paper_trades:
    trades_df = pd.DataFrame(st.session_state.paper_trades)
    st.dataframe(trades_df, use_container_width=True, hide_index=True)

    if st.button("Clear Paper Trade Records"):
        st.session_state.paper_trades = []
        st.rerun()
else:
    st.info("Abhi koi paper trade record nahi hai.")

st.caption(
    "Educational tool. Signals guaranteed nahi hain. "
    "Yeh version automatic stock ranking, automatic NSE breadth, "
    "continuous background scanning, ya real orders execute nahi karta."
)
