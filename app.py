import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="NSE Auto Woodies Scanner", layout="wide")
st.title("⚡ NSE Automatic Woodies 0-Line Scanner")
st.markdown("यह स्कैनर आज मार्केट क्लोज होने पर **0-Line के ऊपर जाने वाले शेयरों** को ऑटोमैटिक फ़िल्टर करता है।")

# 1. स्टॉक बास्केट (NSE Nifty 50 & प्रमुख F&O शेयर्स)
STOCK_BASKET = {
    "Nifty 50 (Top 50 Stocks)": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
        "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
        "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS",
        "BAJFINANCE.NS", "HCLTECH.NS", "SUNPHARMA.NS", "M&M.NS", "NTPC.NS",
        "TATAMOTORS.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "ONGC.NS", "JSWSTEEL.NS",
        "TATASTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS", "BAJAJFINSV.NS",
        "GRASIM.NS", "TECHM.NS", "CIPLA.NS", "WIPRO.NS", "INDUSINDBK.NS",
        "DRREDDY.NS", "HEROMOTOCO.NS", "NESTLEIND.NS", "BPCL.NS", "APOLLOHOSP.NS",
        "TATACONSUM.NS", "EICHERMOT.NS", "DIVISLAB.NS", "SBILIFE.NS", "HDFCLIFE.NS",
        "BAJAJ-AUTO.NS", "HINDALCO.NS", "SHRIRAMFIN.NS", "TRENT.NS", "BEL.NS"
    ],
    "Nifty Next 50 (High Momentum)": [
        "HAL.NS", "ZOMATO.NS", "JIOFIN.NS", "DLF.NS", "VBL.NS",
        "CHOLAFIN.NS", "PIDILITIND.NS", "VEDL.NS", "SIEMENS.NS", "PFC.NS",
        "RECLTD.NS", "AMBUJACEM.NS", "BANKBARODA.NS", "GAIL.NS", "TVSMOTOR.NS",
        "CANBK.NS", "PNB.NS", "IRFC.NS", "IOC.NS", "ABB.NS"
    ]
}

# साइडबार ऑप्शन्स
st.sidebar.header("स्कैनर सेटिंग्स")
basket_choice = st.sidebar.selectbox("किस बास्केट को स्कैन करना है?", list(STOCK_BASKET.keys()))
scan_type = st.sidebar.radio(
    "क्या खोजना चाहते हैं?",
    ["🔥 सिर्फ आज 0-Line क्रॉस करने वाले (Fresh Breakout)", "📈 वर्तमान में 0-Line के ऊपर चल रहे (Bullish Trend)"]
)

run_button = st.sidebar.button("🚀 स्टार्ट ऑटो स्कैन", type="primary")

def calculate_woodies_and_cci(ticker, df):
    try:
        # अगर डेटा मल्टी-इंडेक्स फॉर्मेट में है
        sub_df = df[ticker].dropna() if isinstance(df.columns, pd.MultiIndex) else df.dropna()
        if len(sub_df) < 16:
            return None

        # 1. Woodie's Pivot Point
        high = float(sub_df["High"].iloc[-1])
        low = float(sub_df["Low"].iloc[-1])
        close = float(sub_df["Close"].iloc[-1])

        pp = (high + low + (2 * close)) / 4
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high

        # 2. Woodies CCI 14
        tp = (sub_df["High"] + sub_df["Low"] + sub_df["Close"]) / 3
        sma_tp = tp.rolling(window=14).mean()
        mean_dev = tp.rolling(window=14).apply(lambda x: np.mean(np.abs(x - x.mean())))
        cci = (tp - sma_tp) / (0.015 * mean_dev)

        today_cci = float(cci.iloc[-1])
        yesterday_cci = float(cci.iloc[-2])

        return {
            "Symbol": ticker.replace(".NS", ""),
            "Close Price": round(close, 2),
            "Today CCI": round(today_cci, 2),
            "Yesterday CCI": round(yesterday_cci, 2),
            "Woodies Pivot": round(pp, 2),
            "R1 (Target)": round(r1, 2),
            "S1 (Support)": round(s1, 2),
            "Fresh_Cross": (yesterday_cci <= 0 and today_cci > 0),
            "Above_Zero": (today_cci > 0)
        }
    except Exception:
        return None

if run_button:
    symbols = STOCK_BASKET[basket_choice]
    progress_bar = st.progress(0)
    status_text = st.empty()

    status_text.text("NSE से लाइव डेटा डाउनलोड हो रहा है...")
    # सभी शेयरों का डेटा 1 ही बार में फ़ास्ट डाउनलोड
    data = yf.download(symbols, period="1mo", interval="1d", group_by="ticker", progress=False)

    results = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        progress_bar.progress((i + 1) / total)
        status_text.text(f"स्कैन हो रहा है: {sym.replace('.NS', '')}")
        res = calculate_woodies_and_cci(sym, data)
        if res:
            if "Fresh Breakout" in scan_type and res["Fresh_Cross"]:
                results.append(res)
            elif "Bullish Trend" in scan_type and res["Above_Zero"]:
                results.append(res)

    progress_bar.empty()
    status_text.empty()

    if results:
        res_df = pd.DataFrame(results).drop(columns=["Fresh_Cross", "Above_Zero"])
        st.success(f"कुल {len(res_df)} शेयर्स मिले!")
        
        # टेबल दिखाना
        st.dataframe(res_df, use_container_width=True)

        # CSV डाउनलोड बटन
        csv = res_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 रिजल्ट एक्सेल/CSV में डाउनलोड करें", csv, "woodies_zero_line_stocks.csv", "text/csv")
    else:
        st.warning("आज कोई भी शेयर 0-लाइन क्रॉस करने की कंडीशन में नहीं मिला।")
else:
    st.info("👈 साइडबार में जाकर **'स्टार्ट ऑटो स्कैन'** बटन दबाएं।")
