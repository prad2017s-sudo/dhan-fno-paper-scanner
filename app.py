import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# पेज की हेडिंग और सेटिंग्स
st.set_page_config(page_title="NSE Woodies Formula Scanner", layout="wide")
st.title("📈 NSE Woodies Pivot & 0-Line Scanner")

# साइडबार में यूजर इनपुट
st.sidebar.header("सेटिंग्स")
symbol = st.sidebar.text_input(
    "NSE सिंबल डालें (उदा. RELIANCE, TCS, INFY):", "RELIANCE"
).upper()
ticker = f"{symbol}.NS"

# डेटा लोड करने का फंक्शन
st.write(f"### शेयर: **{symbol}** का Woodies फॉर्मूला डेटा")

try:
    data = yf.download(ticker, period="1mo", interval="1d", progress=False)

    if len(data) >= 2:
        # पिछले दिन का H, L, C
        high = float(data["High"].iloc[-1].values[0])
        low = float(data["Low"].iloc[-1].values[0])
        close = float(data["Close"].iloc[-1].values[0])

        # --- 1. Woodie's Pivot Points Formula ---
        pp = (high + low + (2 * close)) / 4
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)

        # स्क्रीन पर पिवट दिखाना
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Support 2 (S2)", f"{s2:.2f}")
        col2.metric("Support 1 (S1)", f"{s1:.2f}")
        col3.metric("🎯 Woodies Pivot (PP)", f"{pp:.2f}")
        col4.metric("Resistance 1 (R1)", f"{r1:.2f}")
        col5.metric("Resistance 2 (R2)", f"{r2:.2f}")

        # --- 2. Woodies CCI 0-Line Check Formula ---
        typical_price = (data["High"] + data["Low"] + data["Close"]) / 3
        sma_tp = typical_price.rolling(window=14).mean()
        mean_dev = typical_price.rolling(window=14).apply(
            lambda x: np.mean(np.abs(x - x.mean()))
        )
        cci = (typical_price - sma_tp) / (0.015 * mean_dev)

        today_cci = float(cci.iloc[-1].values[0])
        yesterday_cci = float(cci.iloc[-2].values[0])

        st.markdown("---")
        st.write("### 0-Line क्रॉस स्टेटस (Woodies CCI 14):")

        col_a, col_b = st.columns(2)
        col_a.metric("आज का CCI", f"{today_cci:.2f}")
        col_b.metric("कल का CCI", f"{yesterday_cci:.2f}")

        if yesterday_cci <= 0 and today_cci > 0:
            st.success("🚀 **बुलिश सिग्नल!** आज यह शेयर 0-Line के ऊपर क्रॉस हुआ है!")
        elif today_cci > 0:
            st.info("✅ शेयर अभी 0-Line के ऊपर (बुलिश जोन में) ट्रेड कर रहा है।")
        else:
            st.warning("⚠️ शेयर अभी 0-Line के नीचे (बेयरिश जोन में) है।")

    else:
        st.error("डेटा उपलब्ध नहीं है। कृपया सही NSE सिंबल डालें।")

except Exception as e:
    st.error(f"एरर आया: {e}")
