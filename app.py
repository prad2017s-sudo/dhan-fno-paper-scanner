import streamlit as st
import pandas as pd
from datetime import datetime, time

st.set_page_config(
    page_title="NSE F&O Paper Scanner",
    page_icon="📈",
    layout="wide"
)

# ---------- HEADER ----------
st.title("📈 NSE F&O Paper Trading Scanner")
st.caption("5-Minute Scanner | Dhan API Integration Ready | Paper Trading Only")

# ---------- SIDEBAR ----------
st.sidebar.header("⚙️ Scanner Settings")

mode = st.sidebar.selectbox(
    "Data Source",
    ["Demo Mode", "Upload Candle CSV"]
)

st.sidebar.info(
    "Demo Mode ka data nakli hai. "
    "Real market data ke liye CSV ya API integration zaroori hai."
)

# ---------- WATCHLIST ----------
default_stocks = [
    "RELIANCE", "HDFCBANK", "ICICIBANK",
    "SBIN", "AXISBANK", "INFY",
    "TCS", "TATAMOTORS", "BEL", "LT"
]

st.sidebar.subheader("F&O Watchlist")
stocks_text = st.sidebar.text_area(
    "Ek line mein ek symbol",
    value="\n".join(default_stocks),
    height=220
)

stocks = [
    s.strip().upper()
    for s in stocks_text.splitlines()
    if s.strip()
]

# ---------- MARKET BREADTH ----------
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
    market_bias = "BUY BIAS"
elif declines > advances:
    market_bias = "SELL BIAS"
else:
    market_bias = "NEUTRAL"

if advances == declines == unchanged == 0:
    st.warning(
        "Market breadth enter karein. "
        "Zero values ko live market data na samjhein."
    )
else:
    st.metric("Market Bias", market_bias)

# ---------- CSV DATA ----------
uploaded_file = None

if mode == "Upload Candle CSV":
    uploaded_file = st.file_uploader(
        "5-minute candle CSV upload karein",
        type=["csv"]
    )

# CSV columns:
# symbol, datetime, open, high, low, close, volume

data = None

if mode == "Upload Candle CSV" and uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file)

        required = {
            "symbol", "datetime", "open",
            "high", "low", "close", "volume"
        }

        missing = required - set(data.columns)

        if missing:
            st.error(
                "CSV mein ye columns missing hain: "
                + ", ".join(sorted(missing))
            )
            data = None
        else:
            data["symbol"] = data["symbol"].astype(str).str.upper()
            data["datetime"] = pd.to_datetime(
                data["datetime"], errors="coerce"
            )

            for col in ["open", "high", "low", "close", "volume"]:
                data[col] = pd.to_numeric(
                    data[col], errors="coerce"
                )

            data = data.dropna(
                subset=[
                    "symbol", "datetime", "high",
                    "low", "close", "volume"
                ]
            )

    except Exception as e:
        st.error(f"CSV read error: {e}")

# ---------- SCANNER ----------
def scan_candles(df, symbols, bias):
    results = []

    for symbol in symbols:
        candles = df[df["symbol"] == symbol].sort_values("datetime")

        if len(candles) < 2:
            continue

        previous = candles.iloc[-2]
        latest = candles.iloc[-1]

        signal = "WAIT"

        # Previous candle breakout
        if latest["close"] > previous["high"]:
            signal = "BUY"
        elif latest["close"] < previous["low"]:
            signal = "SELL"

        # Market breadth filter
        if bias == "BUY BIAS" and signal == "SELL":
            signal = "WAIT"
        elif bias == "SELL BIAS" and signal == "BUY":
            signal = "WAIT"
        elif bias == "NEUTRAL":
            signal = "WAIT"

        results.append({
            "Symbol": symbol,
            "Time": str(latest["datetime"]),
            "Close": round(float(latest["close"]), 2),
            "Previous High": round(float(previous["high"]), 2),
            "Previous Low": round(float(previous["low"]), 2),
            "Volume": int(latest["volume"]),
            "Signal": signal
        })

    return pd.DataFrame(results)


# ---------- DEMO DATA ----------
if mode == "Demo Mode":
    st.warning(
        "DEMO MODE: Neeche ka data sirf example hai. "
        "Isse real trading decision na lein."
    )

    demo_rows = []

    base_time = datetime.combine(
        datetime.today().date(), time(9, 15)
    )

    for i, symbol in enumerate(stocks):
        base_price = 100 + (i * 25)

        demo_rows.extend([
            {
                "symbol": symbol,
                "datetime": base_time,
                "open": base_price,
                "high": base_price + 2,
                "low": base_price - 2,
                "close": base_price + 1,
                "volume": 10000
            },
            {
                "symbol": symbol,
                "datetime": base_time.replace(minute=20),
                "open": base_price + 1,
                "high": base_price + 4,
                "low": base_price,
                "close": base_price + 3,
                "volume": 15000
            }
        ])

    data = pd.DataFrame(demo_rows)

# ---------- RESULTS ----------
st.divider()
st.subheader("🔍 Stock Scanner")

if data is not None and not data.empty:
    results = scan_candles(data, stocks, market_bias)

    if results.empty:
        st.info(
            "Har stock ke kam se kam 2 candles honi chahiye."
        )
    else:
        st.dataframe(
            results,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "📥 Download Scanner Results",
            data=results.to_csv(index=False).encode("utf-8"),
            file_name="scanner_results.csv",
            mime="text/csv"
        )
else:
    st.info(
        "CSV upload karein ya Demo Mode mein scanner dekhein."
    )

# ---------- PAPER TRADING ----------
st.divider()
st.subheader("📝 Paper Trading")

if "trades" not in st.session_state:
    st.session_state.trades = []

with st.form("paper_trade_form"):
    col1, col2 = st.columns(2)

    with col1:
        trade_symbol = st.selectbox(
            "Stock", stocks if stocks else ["RELIANCE"]
        )

        trade_side = st.selectbox(
            "Side", ["BUY", "SELL"]
        )

    with col2:
        entry_price = st.number_input(
            "Entry Price", min_value=0.0, value=100.0
        )

        quantity = st.number_input(
            "Quantity", min_value=1, value=1, step=1
        )

    submitted = st.form_submit_button(
        "Add Paper Trade"
    )

    if submitted:
        if entry_price <= 0:
            st.error("Entry price zero se zyada hona chahiye.")
        else:
            st.session_state.trades.append({
                "Time": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "Symbol": trade_symbol,
                "Side": trade_side,
                "Entry": float(entry_price),
                "Quantity": int(quantity)
            })
            st.success("Paper trade record add ho gaya.")

if st.session_state.trades:
    trade_df = pd.DataFrame(st.session_state.trades)
    st.dataframe(
        trade_df,
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "📥 Download Paper Trades",
        data=trade_df.to_csv(index=False).encode("utf-8"),
        file_name="paper_trades.csv",
        mime="text/csv"
    )

    if st.button("Clear Paper Trades"):
        st.session_state.trades = []
        st.rerun()
else:
    st.info("Abhi koi paper trade record nahi hai.")

st.caption(
    "Educational paper-trading tool. "
    "Signals are not guaranteed to be profitable. "
    "Live Dhan API integration is not enabled in this version."
)
