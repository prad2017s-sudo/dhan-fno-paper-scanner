
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

DEFAULT_SYMBOLS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "INFY",
    "TCS", "AXISBANK", "TATAMOTORS", "LT", "BHARTIARTL"
]

INSTRUMENT_URL = (
    "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
)

if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = []

if "last_scan" not in st.session_state:
    st.session_state.last_scan = pd.DataFrame()

if "last_source" not in st.session_state:
    st.session_state.last_source = ""


@st.cache_data(ttl=3600)
def load_instruments():
    df = pd.read_csv(INSTRUMENT_URL, low_memory=False)
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def find_column(df, possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None


def get_nse_equity_ids():
    df = load_instruments()

    exchange_col = find_column(df, ["EXCH_ID", "SEM_EXM_EXCH_ID"])
    segment_col = find_column(df, ["SEGMENT", "SEM_SEGMENT"])
    symbol_col = find_column(df, ["SYMBOL_NAME", "SM_SYMBOL_NAME"])
    security_col = find_column(
        df, ["SECURITY_ID", "SEM_SMST_SECURITY_ID", "SEM_SECURITY_ID"]
    )
    instrument_col = find_column(
        df, ["INSTRUMENT", "SEM_INSTRUMENT_NAME"]
    )
    series_col = find_column(df, ["SERIES", "SEM_SERIES"])

    if not all([exchange_col, segment_col, symbol_col, security_col]):
        raise ValueError(
            "Instrument list ke columns pehchane nahi gaye. "
            "Dhan ki latest instrument list ka format check karein."
        )

    df[exchange_col] = df[exchange_col].astype(str).str.upper().str.strip()
    df[segment_col] = df[segment_col].astype(str).str.upper().str.strip()
    df[symbol_col] = df[symbol_col].astype(str).str.upper().str.strip()

    # NSE equity instruments only
    df = df[
        (df[exchange_col] == "NSE") &
        (df[segment_col] == "E")
    ].copy()

    if instrument_col:
        df = df[
            df[instrument_col].astype(str).str.upper().isin(
                ["EQUITY", "EQ"]
            )
        ]

    if series_col:
        df = df[
            df[series_col].astype(str).str.upper().str.strip() == "EQ"
        ]

    df[security_col] = df[security_col].astype(str).str.strip()

    result = {}
    for _, row in df.iterrows():
        symbol = str(row[symbol_col]).strip()
        security_id = str(row[security_col]).strip()

        if symbol and security_id and security_id.lower() != "nan":
            result[symbol] = security_id

    return result


def get_dhan_client():
    try:
        from dhanhq import DhanContext, dhanhq

        client_id = st.secrets["DHAN_CLIENT_ID"]
        access_token = st.secrets["DHAN_ACCESS_TOKEN"]

        if not str(client_id).strip() or not str(access_token).strip():
            return None, "Dhan Client ID ya Access Token khaali hai."

        context = DhanContext(str(client_id), str(access_token))
        return dhanhq(context), None

    except Exception as exc:
        return None, (
            "Dhan connection setup nahi hua. Streamlit Secrets, "
            f"token aur SDK check karein. Details: {exc}"
        )


def fetch_candles(dhan, security_id):
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")

    response = dhan.intraday_minute_data(
        security_id=str(security_id),
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        from_date=today,
        to_date=today,
        interval=5
    )

    if not isinstance(response, dict):
        raise ValueError("Dhan API ka response samajh nahi aaya.")

    if response.get("status") != "success":
        raise ValueError(str(response.get("remarks", response)))

    data = response.get("data") or {}

    if not data or not data.get("timestamp"):
        return pd.DataFrame()

    timestamps = pd.to_datetime(
        data["timestamp"], unit="s", utc=True
    ).tz_convert("Asia/Kolkata")

    return pd.DataFrame({
        "datetime": timestamps,
        "open": data["open"],
        "high": data["high"],
        "low": data["low"],
        "close": data["close"],
        "volume": data["volume"]
    })


def make_demo_candles(symbol):
    random.seed(symbol + datetime.now(IST).strftime("%Y%m%d"))
    now = datetime.now(IST).replace(second=0, microsecond=0)
    now = now.replace(minute=(now.minute // 5) * 5)
    start = now.replace(hour=9, minute=15)

    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        start = now - timedelta(minutes=15)

    price = random.uniform(100, 3000)
    rows = []

    for i in range(100):
        candle_time = start + timedelta(minutes=5 * i)

        if candle_time > now:
            break

        o = price
        c = max(1, o * (1 + random.uniform(-0.008, 0.008)))

        rows.append({
            "symbol": symbol,
            "datetime": candle_time,
            "open": round(o, 2),
            "high": round(max(o, c) * 1.002, 2),
            "low": round(min(o, c) * 0.998, 2),
            "close": round(c, 2),
            "volume": random.randint(1000, 100000)
        })

        price = c

    return pd.DataFrame(rows)


st.title("📈 NSE F&O Paper Trading Scanner")
st.caption("5-Minute Candles | Dhan API | Paper Trading Only")

st.sidebar.header("⚙️ Scanner Settings")
source = st.sidebar.radio(
    "Data Source",
    ["Dhan API", "Upload Candle CSV", "Demo Mode"]
)
st.sidebar.warning("Paper trading only. Koi real order place nahi hoga.")

st.subheader("F&O Watchlist")

if st.button("🔎 Find Security IDs Automatically"):
    try:
        with st.spinner("Dhan instrument list load ho rahi hai..."):
            id_map = get_nse_equity_ids()

        st.session_state["security_id_map"] = id_map
        st.success(
            f"Instrument list se {len(id_map)} NSE equity IDs load hui."
        )
    except Exception as exc:
        st.error(f"Security ID list load nahi hui: {exc}")

try:
    id_map = st.session_state.get("security_id_map")
    if id_map is None:
        id_map = get_nse_equity_ids()
        st.session_state["security_id_map"] = id_map

    watch_rows = []
    for symbol in DEFAULT_SYMBOLS:
        watch_rows.append({
            "symbol": symbol,
            "security_id": id_map.get(symbol, "")
        })

    watchlist = pd.DataFrame(watch_rows)
    st.dataframe(watchlist, use_container_width=True, hide_index=True)

except Exception as exc:
    st.warning(
        "Dhan instrument list abhi load nahi hui. "
        "Internet ya Dhan CSV format check karein."
    )
    st.caption(str(exc))
    watchlist = pd.DataFrame({
        "symbol": DEFAULT_SYMBOLS,
        "security_id": [""] * len(DEFAULT_SYMBOLS)
    })

st.caption(
    "IDs Dhan instrument master se aati hain. "
    "Yeh NSE equity IDs hain, F&O derivative contract IDs nahi."
)

st.subheader("🌐 NSE Market Advance–Decline")
c1, c2, c3 = st.columns(3)

with c1:
    advances = st.number_input("Advances", min_value=0, value=0)
with c2:
    declines = st.number_input("Declines", min_value=0, value=0)
with c3:
    unchanged = st.number_input("Unchanged", min_value=0, value=0)

if advances > declines:
    bias = "BUY BIAS"
elif declines > advances:
    bias = "SELL BIAS"
else:
    bias = "NEUTRAL"

st.info(
    f"Entered market breadth: {bias}. "
    "Advance–Decline values abhi manual hain, live automatic nahi."
)

st.divider()
st.subheader("🔍 Stock Scanner")

uploaded_file = None
if source == "Upload Candle CSV":
    uploaded_file = st.file_uploader("Candle CSV upload karein", type=["csv"])
    st.caption(
        "Required columns: symbol, datetime, open, high, low, close, volume"
    )

if source == "Demo Mode":
    st.warning("Demo Mode ka data nakli hai.")

if st.button("🔄 Refresh Scanner", type="primary"):
    frames = []
    errors = []

    if source == "Demo Mode":
        for symbol in DEFAULT_SYMBOLS:
            df = make_demo_candles(symbol)
            if not df.empty:
                frames.append(df)
        st.session_state.last_source = "Demo Mode"

    elif source == "Upload Candle CSV":
        if uploaded_file is None:
            st.error("Pehle CSV upload karein.")
        else:
            try:
                df = pd.read_csv(uploaded_file)
                required = {
                    "symbol", "datetime", "open", "high",
                    "low", "close", "volume"
                }
                missing = required - set(df.columns)

                if missing:
                    st.error("Missing columns: " + ", ".join(sorted(missing)))
                else:
                    df["datetime"] = pd.to_datetime(
                        df["datetime"], errors="coerce"
                    )
                    for col in ["open", "high", "low", "close", "volume"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                    df = df.dropna(
                        subset=[
                            "datetime", "open", "high",
                            "low", "close", "volume"
                        ]
                    )
                    frames.append(df)
                    st.session_state.last_source = "CSV"
            except Exception as exc:
                st.error(f"CSV error: {exc}")

    else:
        dhan, error = get_dhan_client()

        if error:
            st.error(error)
        else:
            try:
                id_map = get_nse_equity_ids()
                st.session_state["security_id_map"] = id_map

                progress = st.progress(0)

                for i, symbol in enumerate(DEFAULT_SYMBOLS, start=1):
                    security_id = id_map.get(symbol)

                    if not security_id:
                        errors.append(
                            f"{symbol}: Dhan instrument list mein ID nahi mili."
                        )
                    else:
                        try:
                            df = fetch_candles(dhan, security_id)
                            if not df.empty:
                                df["symbol"] = symbol
                                frames.append(df)
                            else:
                                errors.append(
                                    f"{symbol}: candle data nahi mila."
                                )
                        except Exception as exc:
                            errors.append(f"{symbol}: {exc}")

                    progress.progress(i / len(DEFAULT_SYMBOLS))

                st.session_state.last_source = "Dhan API"

            except Exception as exc:
                st.error(f"Instrument list/API error: {exc}")

    if frames:
        st.session_state.last_scan = pd.concat(
            frames, ignore_index=True
        )
    elif source != "Dhan API":
        st.session_state.last_scan = pd.DataFrame()

    for message in errors:
        st.warning(message)

if not st.session_state.last_scan.empty:
    df = st.session_state.last_scan.copy()
    st.caption(f"Data source: {st.session_state.last_source}")

    latest = (
        df.sort_values("datetime")
        .groupby("symbol", as_index=False)
        .tail(1)
        .sort_values("symbol")
    )

    st.markdown("#### Latest Candle")
    st.dataframe(latest, use_container_width=True, hide_index=True)

    st.markdown("#### Candle History")
    st.dataframe(
        df.sort_values(["symbol", "datetime"], ascending=[True, False]),
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download Candle CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="paper_scanner_candles.csv",
        mime="text/csv"
    )
else:
    st.info("Refresh Scanner dabakar data load karein.")

st.divider()
st.subheader("📝 Paper Trading")

with st.form("paper_trade_form"):
    symbol = st.selectbox("Stock", DEFAULT_SYMBOLS)
    side = st.selectbox("Side", ["BUY", "SELL"])
    price = st.number_input("Entry Price", min_value=0.0, value=0.0)
    quantity = st.number_input("Quantity", min_value=1, value=1)
    note = st.text_input("Note (optional)")
    submitted = st.form_submit_button("Add Paper Trade")

    if submitted:
        if price <= 0:
            st.error("Entry Price zero se zyada hona chahiye.")
        else:
            st.session_state.paper_trades.append({
                "time": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "side": side,
                "entry_price": price,
                "quantity": int(quantity),
                "note": note,
                "status": "PAPER ONLY"
            })
            st.success("Paper trade record add ho gaya.")

if st.session_state.paper_trades:
    st.dataframe(
        pd.DataFrame(st.session_state.paper_trades),
        use_container_width=True,
        hide_index=True
    )
    if st.button("Clear Paper Trades"):
        st.session_state.paper_trades = []
        st.rerun()
else:
    st.info("Abhi koi paper trade record nahi hai.")

st.caption(
    "Educational tool. Yeh version real orders nahi bhejta, "
    "automatic NSE breadth ya automatic top-10 activity ranking nahi karta, "
    "aur background mein har 5 minute scan nahi karta."
)
