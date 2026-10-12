
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dhanhq import DhanContext, dhanhq

st.set_page_config(
    page_title="NSE F&O Paper Scanner",
    page_icon="📊",
    layout="wide"
)

IST = ZoneInfo("Asia/Kolkata")

WATCHLIST = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "INFY",
    "TCS", "AXISBANK", "TATAMOTORS", "LT", "BHARTIARTL"
]

st.title("📊 NSE F&O Paper Trading Scanner")
st.caption("5-minute candles | No demo data | Paper trading only")

if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = []

if "scan_results" not in st.session_state:
    st.session_state.scan_results = pd.DataFrame()


def get_dhan_client():
    client_id = st.secrets.get("DHAN_CLIENT_ID", "")
    access_token = st.secrets.get("DHAN_ACCESS_TOKEN", "")

    if not client_id or not access_token:
        raise ValueError(
            "Streamlit Secrets mein DHAN_CLIENT_ID aur "
            "DHAN_ACCESS_TOKEN set karein."
        )

    context = DhanContext(client_id, access_token)
    return dhanhq(context)


@st.cache_data(ttl=3600, show_spinner=False)
def load_security_master():
    # Dhan SDK ka security master
    client = get_dhan_client()
    df = client.fetch_security_list("compact")

    if isinstance(df, dict):
        df = df.get("data", df)

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def get_security_ids():
    df = load_security_master()

    required = [
        "SEM_EXM_EXCH_ID",
        "SEM_SEGMENT",
        "SEM_SMST_SECURITY_ID"
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "Security master columns missing: "
            + ", ".join(missing)
            + ". Available: "
            + ", ".join(df.columns.astype(str))
        )

    symbol_col = next(
        (
            c for c in [
                "SEM_TRADING_SYMBOL",
                "SEM_CUSTOM_SYMBOL",
                "SM_SYMBOL_NAME"
            ]
            if c in df.columns
        ),
        None
    )

    if not symbol_col:
        raise ValueError("Trading symbol column nahi mila.")

    for col in ["SEM_EXM_EXCH_ID", "SEM_SEGMENT", symbol_col]:
        df[col] = df[col].astype(str).str.strip().str.upper()

    df = df[
        (df["SEM_EXM_EXCH_ID"] == "NSE")
        & (df["SEM_SEGMENT"] == "E")
    ].copy()

    if "SEM_INSTRUMENT_NAME" in df.columns:
        instrument = (
            df["SEM_INSTRUMENT_NAME"]
            .astype(str).str.strip().str.upper()
        )
        df = df[instrument.isin(["EQUITY", "EQ"])]

    df["SEM_SMST_SECURITY_ID"] = (
        df["SEM_SMST_SECURITY_ID"].astype(str).str.strip()
    )

    return dict(
        zip(df[symbol_col], df["SEM_SMST_SECURITY_ID"])
    )


def fetch_candles(client, security_id):
    now = datetime.now(IST)

    # Recent date range allows the API to return recent candles.
    end_date = now.date()
    start_date = end_date - timedelta(days=7)

    response = client.intraday_minute_data(
        security_id=str(security_id),
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        from_date=start_date.isoformat(),
        to_date=end_date.isoformat(),
        interval=5,
    )

    if not isinstance(response, dict):
        raise ValueError(
            "Unexpected API response: " + str(response)[:500]
        )

    if response.get("status") == "failure":
        raise ValueError(
            "Dhan API failure: "
            + str(response.get("remarks", response))[:500]
        )

    data = response.get("data", response)

    if not isinstance(data, dict):
        raise ValueError("Dhan candle response format galat hai.")

    if not data or not isinstance(data.get("close"), (list, tuple)):
        raise ValueError(
            "Dhan ne candle data nahi diya. API response: "
            + str(response)[:700]
        )

    df = pd.DataFrame(data)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            "Candle columns missing: " + ", ".join(missing)
        )

    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" not in df.columns:
        df["volume"] = 0

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=required)

    return df.tail(30).reset_index(drop=True)


def candle_signal(df):
    # Signals require actual uploaded/API candles only.
    if df is None or len(df) < 3:
        return "NO SIGNAL"

    previous = df.iloc[-2]
    current = df.iloc[-1]

    if current["close"] > previous["high"]:
        return "BUY"
    if current["close"] < previous["low"]:
        return "SELL"

    return "WAIT"


# Sidebar
st.sidebar.header("Scanner Settings")

mode = st.sidebar.radio(
    "Data source",
    ["Dhan API", "Upload Candle CSV"]
)

breadth = st.sidebar.selectbox(
    "NSE Advance–Decline bias",
    [
        "Not available",
        "Advances > Declines (Buy bias)",
        "Declines > Advances (Sell bias)",
        "Advances = Declines (Neutral)"
    ]
)

st.sidebar.info(
    "Advance–Decline abhi manual setting hai; "
    "automatic NSE breadth feed connected nahi hai."
)

st.subheader("1. Watchlist")
st.write(
    "Ye starting symbols hain. Highest market activity ke basis "
    "par automatic ranking abhi enabled nahi hai."
)
st.dataframe(
    pd.DataFrame({"Symbol": WATCHLIST}),
    use_container_width=True,
    hide_index=True
)

st.subheader("2. Security IDs")

if st.button("Find Security IDs Automatically"):
    try:
        with st.spinner("Dhan security master load ho raha hai..."):
            ids = get_security_ids()

        result = pd.DataFrame([
            {
                "Symbol": symbol,
                "Security ID": ids.get(symbol, "NOT FOUND")
            }
            for symbol in WATCHLIST
        ])

        st.dataframe(result, use_container_width=True, hide_index=True)
        found = sum(ids.get(s) is not None for s in WATCHLIST)
        st.success(f"{found}/{len(WATCHLIST)} symbols ke IDs mile.")

    except Exception as exc:
        st.error(f"Security ID error: {exc}")


st.subheader("3. Scan 5-minute candles")

uploaded = None
csv_df = None

if mode == "Upload Candle CSV":
    uploaded = st.file_uploader(
        "CSV upload karein: symbol, open, high, low, close; volume optional",
        type=["csv"]
    )

    if uploaded is not None:
        try:
            csv_df = pd.read_csv(uploaded)
            csv_df.columns = [
                str(c).strip().lower() for c in csv_df.columns
            ]

            if "symbol" not in csv_df.columns:
                st.error("CSV mein symbol column zaroori hai.")
                csv_df = None

        except Exception as exc:
            st.error(f"CSV read error: {exc}")
            csv_df = None


if st.button("Refresh Scanner", type="primary"):
    client = None
    ids = {}
    results = []

    if mode == "Dhan API":
        try:
            client = get_dhan_client()
            ids = get_security_ids()
        except Exception as exc:
            st.error(f"Dhan connection error: {exc}")
            st.stop()

    if mode == "Upload Candle CSV" and csv_df is None:
        st.warning("Pehle valid Candle CSV upload karein.")
        st.stop()

    progress = st.progress(0)

    for i, symbol in enumerate(WATCHLIST):
        security_id = ids.get(symbol, "NOT FOUND")

        try:
            if mode == "Dhan API":
                if security_id == "NOT FOUND":
                    raise ValueError(
                        "Security ID nahi mili. Trading symbol verify karein."
                    )

                candles = fetch_candles(client, security_id)

            else:
                part = csv_df[
                    csv_df["symbol"].astype(str).str.strip().str.upper()
                    == symbol
                ].copy()

                for col in ["open", "high", "low", "close"]:
                    if col not in part.columns:
                        raise ValueError(
                            f"CSV mein {col} column missing hai."
                        )

                if "volume" not in part.columns:
                    part["volume"] = 0

                candles = part

            if candles.empty:
                raise ValueError("Koi candle nahi mili.")

            signal = candle_signal(candles)

            if breadth.startswith("Advances >") and signal == "SELL":
                signal = "WAIT"
            elif breadth.startswith("Declines >") and signal == "BUY":
                signal = "WAIT"
            elif breadth.startswith("Advances =") and signal in ["BUY", "SELL"]:
                signal = "WAIT"

            results.append({
                "Symbol": symbol,
                "Security ID": security_id,
                "Last Close": round(float(candles.iloc[-1]["close"]), 2),
                "Signal": signal,
                "Candles": len(candles),
                "Status": "OK"
            })

        except Exception as exc:
            results.append({
                "Symbol": symbol,
                "Security ID": security_id,
                "Last Close": None,
                "Signal": "NO SIGNAL",
                "Candles": 0,
                "Status": str(exc)[:250]
            })

        progress.progress((i + 1) / len(WATCHLIST))

    st.session_state.scan_results = pd.DataFrame(results)
    st.success("Scan complete. Koi real order place nahi hua.")


if not st.session_state.scan_results.empty:
    st.subheader("Scanner Results")
    st.dataframe(
        st.session_state.scan_results,
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download scan results CSV",
        data=st.session_state.scan_results.to_csv(index=False).encode("utf-8"),
        file_name="scanner_results.csv",
        mime="text/csv"
    )


st.subheader("4. Paper Trade Entry")

with st.form("paper_trade_form"):
    symbol = st.selectbox("Symbol", WATCHLIST)
    side = st.selectbox("Side", ["BUY", "SELL"])
    quantity = st.number_input(
        "Quantity", min_value=1, max_value=100000, value=1, step=1
    )
    entry = st.number_input(
        "Simulated entry price (₹)", min_value=0.01, value=100.0, step=0.05
    )
    stop_loss = st.number_input(
        "Stop loss (₹)", min_value=0.0, value=95.0, step=0.05
    )
    target = st.number_input(
        "Target (₹)", min_value=0.0, value=110.0, step=0.05
    )

    submitted = st.form_submit_button("Record Paper Trade")

    if submitted:
        st.session_state.paper_trades.append({
            "Time": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "Symbol": symbol,
            "Side": side,
            "Quantity": int(quantity),
            "Entry": float(entry),
            "Stop Loss": float(stop_loss),
            "Target": float(target),
            "Type": "PAPER ONLY"
        })
        st.success("Paper trade record save hua. Real order nahi bheja.")


if st.session_state.paper_trades:
    st.subheader("Paper Trade Journal")
    trades = pd.DataFrame(st.session_state.paper_trades)
    st.dataframe(trades, use_container_width=True, hide_index=True)

    st.download_button(
        "Download paper journal CSV",
        data=trades.to_csv(index=False).encode("utf-8"),
        file_name="paper_trade_journal.csv",
        mime="text/csv"
    )

    if st.button("Clear Paper Trade Journal"):
        st.session_state.paper_trades = []
        st.rerun()


st.divider()
st.caption(
    "No demo data. Signals only use API/CSV candles. "
    "Paper trading only; no automatic or real orders. "
    "Automatic breadth and activity ranking are not implemented."
)
