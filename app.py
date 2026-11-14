import io
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="All NSE Weekly Scanner (₹100-₹2500)", layout="wide")
st.title("⚡ All NSE Stocks — Weekly Woodies & 0-Line Scanner")
st.caption(
    "यह स्कैनर NSE के सभी लिस्टेड शेयरों को Weekly Candle पर स्कैन करता है (प्राइस रेंज: ₹100 से ₹2500)।"
)

# NSE सर्वर ब्लॉक होने पर काम आने वाली बैकअप लिस्ट
BACKUP_NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "SBIN.NS", "LICI.NS", "ITC.NS", "HINDUNILVR.NS",
    "LT.NS", "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "ADANIENT.NS", "KOTAKBANK.NS", "TITAN.NS", "ONGC.NS", "TATAMOTORS.NS",
    "NTPC.NS", "AXISBANK.NS", "DMART.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "COALINDIA.NS", "JSWSTEEL.NS", "M&M.NS", "POWERGRID.NS", "BAJAJFINSV.NS",
    "ASIANPAINT.NS", "ADANIPORTS.NS", "TATASTEEL.NS", "TRENT.NS", "BEL.NS",
    "HAL.NS", "NESTLEIND.NS", "GRASIM.NS", "TECHM.NS", "HINDALCO.NS",
    "INDIGO.NS", "CIPLA.NS", "DRREDDY.NS", "BPCL.NS", "EICHERMOT.NS",
    "HEROMOTOCO.NS", "TATACONSUM.NS", "BRITANNIA.NS", "APOLLOHOSP.NS", "DIVISLAB.NS",
]


# --- 1. NSE से शेयरों की लिस्ट डाउनलोड करना ---
@st.cache_data(ttl=86400)  # 24 घंटे कैश
def get_nse_symbols(category: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    if "Nifty 100" in category:
        url = "https://archives.nseindia.com/content/indices/ind_nifty100list.csv"
    elif "Nifty 500" in category:
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    else:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        df.columns = df.columns.str.strip()

        if "SERIES" in df.columns:
            df = df[df["SERIES"].astype(str).str.strip() == "EQ"]

        col_name = "SYMBOL" if "SYMBOL" in df.columns else "Symbol"
        symbols = [f"{str(s).strip()}.NS" for s in df[col_name].dropna().tolist()]
        return symbols
    except Exception:
        return []


# --- साइडबार कंट्रोल्स ---
st.sidebar.header("📊 स्कैनिंग सेटिंग्स (Weekly)")

scan_limit = st.sidebar.selectbox(
    "कौन-से शेयर्स स्कैन करने हैं?",
    [
        "सभी NSE शेयर्स (2000+ EQ Stocks)",
        "Nifty 500 शेयर्स",
        "Nifty 100 शेयर्स (फ़ास्ट टेस्ट)",
    ],
    index=0,  # डिफ़ॉल्ट: सभी NSE शेयर्स
)

st.sidebar.subheader("💰 प्राइस फ़िल्टर (₹)")
col1, col2 = st.sidebar.columns(2)
min_price = col1.number_input("कम से कम (Min ₹)", min_value=1.0, value=100.0, step=10.0)
max_price = col2.number_input("ज़्यादा से ज़्यादा (Max ₹)", min_value=10.0, value=2500.0, step=50.0)

symbols_list = get_nse_symbols(scan_limit)
if not symbols_list:
    st.sidebar.warning("NSE से लिस्ट लोड नहीं हो पाई, बैकअप (Nifty 50) का उपयोग हो रहा है।")
    symbols_list = BACKUP_NIFTY_50

st.sidebar.info(f"स्कैन होने वाले कुल शेयर्स: **{len(symbols_list)}**\n\nटाइमफ्रेम: **Weekly (1W)**")

scan_type = st.sidebar.radio(
    "कंडीशन चुनें (Weekly Candle):",
    [
        "🔥 इस हफ्ते 0-Line क्रॉस करने वाले (Weekly Fresh Breakout)",
        "📈 वर्तमान में Weekly 0-Line के ऊपर (Weekly Bullish)",
    ],
)

start_scan = st.sidebar.button("🚀 Weekly स्कैन शुरू करें", type="primary")


# --- 2. Weekly Woodies Pivot & CCI (14) कैलकुलेशन ---
def analyze_weekly_data(ticker: str, df: pd.DataFrame, min_p: float, max_p: float):
    try:
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            if ticker not in df.columns.get_level_values(0):
                return None
            sub_df = df[ticker][["High", "Low", "Close"]].dropna()
        else:
            sub_df = df[["High", "Low", "Close"]].dropna()

        # Weekly CCI (14) + पिछले हफ्ते से तुलना के लिए कम से कम 16 हफ्ते का डेटा चाहिए
        if len(sub_df) < 16:
            return None

        close = float(sub_df["Close"].iloc[-1])

        # प्राइस फ़िल्टर: 100 से कम नहीं, 2500 से ज़्यादा नहीं
        if not (min_p <= close <= max_p):
            return None

        high = float(sub_df["High"].iloc[-1])
        low = float(sub_df["Low"].iloc[-1])

        # Weekly Woodie's Pivot (अगले हफ्ते के लेवल्स)
        pp = (high + low + (2 * close)) / 4
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high

        # Weekly Woodies CCI (14)
        tp = (sub_df["High"] + sub_df["Low"] + sub_df["Close"]) / 3
        sma_tp = tp.rolling(window=14).mean()
        mean_dev = tp.rolling(window=14).apply(
            lambda x: np.mean(np.abs(x - x.mean())), raw=True
        )
        cci = (tp - sma_tp) / (0.015 * mean_dev.replace(0, np.nan))

        curr_week_cci = cci.iloc[-1]
        prev_week_cci = cci.iloc[-2]

        if pd.isna(curr_week_cci) or pd.isna(prev_week_cci):
            return None

        curr_week_cci = float(curr_week_cci)
        prev_week_cci = float(prev_week_cci)

        return {
            "Symbol": ticker.replace(".NS", ""),
            "Close (₹)": round(close, 2),
            "This Week CCI": round(curr_week_cci, 2),
            "Last Week CCI": round(prev_week_cci, 2),
            "Weekly Pivot (PP)": round(pp, 2),
            "Weekly R1": round(r1, 2),
            "Weekly S1": round(s1, 2),
            "Fresh_Cross": (prev_week_cci <= 0 and curr_week_cci > 0),
            "Above_Zero": (curr_week_cci > 0),
        }
    except Exception:
        return None


# --- 3. स्कैनिंग प्रोसेस ---
if start_scan:
    if min_price > max_price:
        st.error("⚠️ 'Min Price' की वैल्यू 'Max Price' से ज़्यादा नहीं हो सकती।")
    else:
        total = len(symbols_list)
        batch_size = 50

        progress_bar = st.progress(0)
        status_box = st.empty()
        results = []

        for i in range(0, total, batch_size):
            batch = symbols_list[i : i + batch_size]
            done = min(i + len(batch), total)
            progress_bar.progress(done / total)
            status_box.text(f"Weekly डेटा स्कैन हो रहा है: {done} / {total} शेयर्स... (मिले: {len(results)})")

            try:
                # Weekly कैंडल के लिए 1 साल (1y ~ 52 हफ्ते) का डेटा
                batch_data = yf.download(
                    batch,
                    period="1y",
                    interval="1wk",
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )

                for sym in batch:
                    res = analyze_weekly_data(sym, batch_data, min_price, max_price)
                    if res:
                        if "Fresh Breakout" in scan_type and res["Fresh_Cross"]:
                            results.append(res)
                        elif "Bullish" in scan_type and res["Above_Zero"]:
                            results.append(res)

                time.sleep(0.1)  # Yahoo Finance रेट-लिमिट से बचने के लिए हल्का गैप
            except Exception:
                continue

        progress_bar.empty()
        status_box.empty()

        if results:
            df_res = (
                pd.DataFrame(results)
                .drop(columns=["Fresh_Cross", "Above_Zero"])
                .sort_values(by="This Week CCI", ascending=False)
                .reset_index(drop=True)
            )
            st.success(
                f"🎉 Weekly स्कैन पूरा! ₹{min_price:.0f}–₹{max_price:.0f} रेंज में कुल **{len(df_res)}** शेयर मिले।"
            )
            st.dataframe(df_res, width="stretch")

            csv_file = df_res.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 पूरी Weekly लिस्ट डाउनलोड करें (CSV)",
                csv_file,
                "nse_weekly_100_to_2500_0line.csv",
                "text/csv",
            )
        else:
            st.warning("तय कंडीशन और ₹100–₹2500 रेंज में कोई शेयर नहीं मिला।")
else:
    st.info("👈 साइडबार में सेटिंग्स चेक करें और **'Weekly स्कैन शुरू करें'** बटन दबाएं।")
