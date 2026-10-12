
import streamlit as st
import pandas as pd
from datetime import datetime, date
from zoneinfo import ZoneInfo
from dhanhq import DhanContext, dhanhq

st.set_page_config(
    page_title="NSE F&O Paper Scanner",
    page_icon="📊",
    layout="wide"
)

IST = ZoneInfo("Asia/Kolkata")

# Watchlist: starting list only, not automatically ranked by activity.
WATCHLIST = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "INFY",
    "TCS", "AXISBANK", "TATAMOTORS", "LT", "BHARTIARTL"
]

st.title("📊 NSE F&O Paper Trading Scanner")
st.caption("5-minute candles | Dhan API | Paper trades only")

if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = []

if "scan_results" not in st.session_state:
    st.session_state.scan_results = pd.DataFrame()


def get_dhan_client():
    client_id = st.secrets.get("DHAN_CLIENT_ID", "")
    access_token = st.secrets.get("DHAN_ACCESS_TOKEN", "")

    if not client_id or not access_token:
        raise ValueError(
            "DHAN_CLIENT_ID aur DHAN_ACCESS_TOKEN "
            "Streamlit Secrets mein set karein."
        )

    context = DhanContext(client_id, access_token)
    return dhanhq(context)


def normalize_columns(df):
    df = df.copy()
    df.columns = [
        str(column).strip().upper()
        for column in df.columns
    ]
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_security_master():
    # Dhan security master: compact format
    client = get_dhan_client()
    df = client.fetch_security_list("compact")

    if isinstance(df, dict):
        if "data" in df:
            df = df["data"]
        else:
            raise ValueError(
                "Dhan security master ka response samajh nahi aaya."
            )

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    return normalize_columns(df)


def get_nse_equity_ids():
    df = load_security_master()

    exchange_col = "SEM_EXM_EXCH_ID"
    segment_col = "SEM_SEGMENT"
    security_col = "SEM_SMST_SECURITY_ID"

    required = [exchange_col, segment_col, security_col]
    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(
            "Security master columns missing: "
            + ", ".join(missing)
            + ". Available columns: "
            + ", ".join(df.columns.astype(str))
        )

    # Prefer the exact exchange trading symbol.
    symbol_candidates = [
        "SEM_TRADING_SYMBOL",
        "SEM_CUSTOM_SYMBOL",
        "SM_SYMBOL_NAME",
    ]

    symbol_col = next(
        (col for col in symbol_candidates if col in df.columns),
        None
    )

    if symbol_col is None:
        raise ValueError(
            "Trading symbol column nahi mila. Columns: "
            + ", ".join(df.columns.astype(str))
        )

    df[exchange_col] = (
        df[exchange_col].astype(str).str.strip().str.upper()
    )
    df[segment_col] = (
        df[segment_col].astype(str).str.strip().str.upper()
    )
    df[symbol_col] = (
        df[symbol_col].astype(str).str.strip().str.upper()
    )

    df = df[
        (df[exchange_col] == "NSE")
        & (df[segment_col] == "E")
    ].copy()

    # If instrument type is available, restrict to equities.
    if "SEM_INSTRUMENT_NAME" in df.columns:
        instrument = (
            df["SEM_INSTRUMENT_NAME"]
            .astype(str).str.strip().str.upper()
        )
        df = df[instrument.isin(["EQUITY", "EQ"])]

    df[security_col] = df[security_col].astype(str).str.strip()

    df = df[
        df[symbol_col].notna()
        & (df[symbol_col] != "")
        & (df[security_col] != "")
        & (df[security_col].str.lower() != "nan")
    ]

    # Prefer exact trading symbol; aliases are used only as fallbacks.
    result = {}
    for _, row in df.iterrows():
        symbol = row[symbol_col]
        security_id = row[security_col]
        if symbol not in result:
            result[symbol] = security_id

    return result


def response_to_dataframe(response):
    if isinstance(response, pd.DataFrame):
        return response.copy()

    if not isinstance(response, dict):
        raise ValueError("Dhan candle response dictionary nahi hai.")

    if response.get("status") == "failure":
        raise ValueError(
            str(response.get("remarks", "Dhan API request failed"))
        )

    data = response.get("data", response)

    if not isinstance(data, dict):
        raise ValueError("Dhan candle data ka format galat hai.")

    # Dhan returns OHLCV arrays in separate keys.
    if "close" in data and isinstance(data["close"], (list, tuple)):
        df = pd.DataFrame(data)
    else:
        df = pd.DataFrame(data)

    if df.empty:
        return df

    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def fetch_candles(client, security_id):
    today = datetime.now(IST).date().isoformat()

    response = client.intraday_minute_data(
        security_id=str(security_id),
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        from_date=today,
        to_date=today,
        interval=5,
    )

    df = response_to_dataframe(response)

    if df.empty:
        return df

    # Normalize possible timestamp field names.
    if "timestamp" not in df.columns:
        for candidate in ["start_time", "datetime", "time"]:
            if candidate in df.columns:
                df = df.rename(columns={candidate: "timestamp"})
                break

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            "Candle fields missing: " + ", ".join(missing)
        )

    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" not in df.columns:
        df["volume"] = 0

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=required)

    return df.tail(30).reset_index(drop=True)


def demo_candles(symbol):
    # Clearly simulated values; not market data.
    import random

    rng = random.Random(
        sum(ord(ch) for ch in symbol)
        + datetime.now(IST).minute
    )

    price = rng.uniform(200, 3000)
    rows = []

    for i in range(10):
        opening = price
        change = rng.uniform(-0.012, 0.012)
        closing = max(1, opening * (1 + change))
        high = max(opening, closing) * (1 + rng.uniform(0, 0.004))
        low = min(opening, closing) * (1 - rng.uniform(0, 0.004))

        rows.append({
            "timestamp": f"Demo candle {i + 1}",
            "open": round(opening, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(closing, 2),
            "volume": rng.randint(1000, 50000),
        })

        price = closing

    return pd.DataFrame(rows)


def make_signal(df):
    if df is None or len(df) < 3:
        return "WAIT"

    previous = df.iloc[-2]
    current = df.iloc[-1]

    if current["close"] > previous["high"]:
        return "BUY"
    if current["close"] < previous["low"]:
        return "SELL"

    return "WAIT"


# Sidebar controls
st.sidebar.header("Scanner Settings")

mode = st.sidebar.radio(
    "Data source",
    ["Demo Mode", "Dhan API", "Upload Candle CSV"]
)

breadth = st.sidebar.selectbox(
    "NSE Advance–Decline bias",
    [
        "Not available",
        "Advances > Declines (Buy bias)",
        "Declines > Advances (Sell bias)",
        "Advances = Declines (Neutral)",
    ]
)

st.sidebar.info(
    "Advance–Decline value abhi manual selection hai; "
    "automatic NSE breadth feed abhi connected nahi hai."
)

st.subheader("1. Watchlist")
st.write(
    "Ye 10 starting symbols hain. Inhe highest market activity "
    "ke basis par automatically rank nahi kiya ja raha."
)

st.dataframe(
    pd.DataFrame({"Symbol": WATCHLIST}),
    use_container_width=True,
    hide_index=True
)

st.subheader("2. Security IDs")

if st.button("Find Security IDs Automatically", type="primary"):
    try:
        with st.spinner("Dhan security master load ho raha hai..."):
            ids = get_nse_equity_ids()

        rows = []
        for symbol in WATCHLIST:
            rows.append({
                "Symbol": symbol,
                "Security ID": ids.get(symbol, "NOT FOUND"),
            })

        id_df = pd.DataFrame(rows)
        st.dataframe(id_df, use_container_width=True, hide_index=True)

        found = sum(ids.get(s) is not None for s in WATCHLIST)
        st.success(f"{found}/{len(WATCHLIST)} symbols ke IDs mile.")

        if found < len(WATCHLIST):
            st.warning(
                "Jo symbols NOT FOUND hain, unke liye security master "
                "mein available trading symbols verify karne honge."
            )

    except Exception as exc:
        st.error(f"Security ID error: {exc}")


st.subheader("3. Scan 5-minute candles")

uploaded = None
if mode == "Upload Candle CSV":
    uploaded = st.file_uploader(
        "CSV upload karein (symbol, open, high, low, close; volume optional)",
        type=["csv"]
    )

if st.button("Refresh Scanner"):
    output = []
    client = None
    ids = {}

    if mode == "Dhan API":
        try:
            client = get_dhan_client()
            ids = get_nse_equity_ids()
        except Exception as exc:
            st.error(f"Dhan connection/security master error: {exc}")
            st.stop()

    if mode == "Upload Candle CSV":
        if uploaded is None:
            st.warning("Pehle candle CSV upload karein.")
            st.stop()

        try:
            csv_df = pd.read_csv(uploaded)
            csv_df.columns = [
                str(c).strip().lower() for c in csv_df.columns
            ]
            if "symbol" not in csv_df.columns:
                st.error("CSV mein 'symbol' column zaroori hai.")
                st.stop()
        except Exception as exc:
            st.error(f"CSV read error: {exc}")
            st.stop()

    progress = st.progress(0)

    for index, symbol in enumerate(WATCHLIST):
        try:
            if mode == "Demo Mode":
                candles = demo_candles(symbol)
                security_id = "DEMO"

            elif mode == "Dhan API":
                security_id = ids.get(symbol)

                if not security_id:
                    output.append({
                        "Symbol": symbol,
                        "Security ID": "NOT FOUND",
                        "Last Close": None,
                        "Signal": "NO DATA",
                        "Candles": 0,
                        "Status": "Security ID nahi mili",
                    })
                    progress.progress((index + 1) / len(WATCHLIST))
                    continue

                candles = fetch_candles(client, security_id)

            else:
                part = csv_df[
                    csv_df["symbol"].astype(str).str.upper().str.strip()
                    == symbol
                ].copy()

                for col in ["open", "high", "low", "close"]:
                    if col not in part.columns:
                        raise ValueError(f"CSV mein {col} column missing hai.")

                if "volume" not in part.columns:
                    part["volume"] = 0

                candles = part

                if "timestamp" not in candles.columns:
                    candles["timestamp"] = range(len(candles))

                security_id = "CSV"

            if candles.empty:
                output.append({
                    "Symbol": symbol,
                    "Security ID": security_id,
                    "Last Close": None,
                    "Signal": "NO DATA",
                    "Candles": 0,
                    "Status": "Koi candle nahi mili",
                })
            else:
                signal = make_signal(candles)

                # Optional manually selected breadth filter.
                if breadth.startswith("Advances >") and signal == "SELL":
                    signal = "WAIT"
                elif breadth.startswith("Declines >") and signal == "BUY":
                    signal = "WAIT"
                elif breadth.startswith("Advances =") and signal != "WAIT":
                    signal = "WAIT"

                output.append({
                    "Symbol": symbol,
                    "Security ID": security_id,
                    "Last Close": round(float(candles.iloc[-1]["close"]), 2),
                    "Signal": signal,
                    "Candles": len(candles),
                    "Status": "DEMO DATA" if mode == "Demo Mode" else "OK",
                })

        except Exception as exc:
            output.append({
                "Symbol": symbol,
                "Security ID": ids.get(symbol, "—") if mode == "Dhan API" else "—",
                "Last Close": None,
                "Signal": "ERROR",
                "Candles": 0,
                "Status": str(exc)[:180],
            })

        progress.progress((index + 1) / len(WATCHLIST))

    result_df = pd.DataFrame(output)
    st.session_state.scan_results = result_df

    st.success("Scan complete. Koi real order place nahi kiya gaya.")


if not st.session_state.scan_results.empty:
    st.subheader("Scanner Results")
    st.dataframe(
        st.session_state.scan_results,
        use_container_width=True,
        hide_index=True
    )

    csv_bytes = st.session_state.scan_results.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download scan results CSV",
        data=csv_bytes,
        file_name="paper_scanner_results.csv",
        mime="text/csv"
    )


st.subheader("4. Paper Trade Entry")

with st.form("paper_trade_form"):
    symbol = st.selectbox("Symbol", WATCHLIST)
    side = st.selectbox("Side", ["BUY", "SELL"])
    quantity = st.number_input(
        "Quantity", min_value=1, max_value=100000, value=1, step=1
    )
    entry_price = st.number_input(
        "Simulated entry price (₹)",
        min_value=0.01,
        value=100.0,
        step=0.05
    )
    stop_loss = st.number_input(
        "Stop loss (₹)",
        min_value=0.0,
        value=95.0,
        step=0.05
    )
    target = st.number_input(
        "Target (₹)",
        min_value=0.0,
        value=110.0,
        step=0.05
    )

    submitted = st.form_submit_button("Record Paper Trade")

    if submitted:
        st.session_state.paper_trades.append({
            "Time": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "Symbol": symbol,
            "Side": side,
            "Quantity": int(quantity),
            "Entry": float(entry_price),
            "Stop Loss": float(stop_loss),
            "Target": float(target),
            "Mode": "PAPER ONLY",
        })
        st.success("Paper trade record save ho gaya. Real order nahi bheja.")


if st.session_state.paper_trades:
    st.subheader("Paper Trade Journal")
    trades_df = pd.DataFrame(st.session_state.paper_trades)
    st.dataframe(trades_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Download paper journal CSV",
        data=trades_df.to_csv(index=False).encode("utf-8"),
        file_name="paper_trade_journal.csv",
        mime="text/csv"
    )

    if st.button("Clear Paper Trade Journal"):
        st.session_state.paper_trades = []
        st.rerun()


st.divider()
st.caption(
    "Paper trading only. Signals are simple candle-breakout examples, "
    "not financial advice. Demo data is simulated. No automatic orders."
)
