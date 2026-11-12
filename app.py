import io
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="All NSE Stocks Auto-Scanner", layout="wide")
st.title("⚡ All NSE Stocks (2000+) Woodies & 0-Line Scanner")
st.caption(
    "यह स्कैनर NSE के सभी लिस्टेड शेयरों को लाइव स्कैन करके 0-Line ब्रेकआउट ढूंढता है।"
)


# --- 1. NSE से सारे शेयरों की लाइव लिस्ट डाउनलोड करना ---
@st.cache_data(ttl=86400)  # 24 घंटे में सिर्फ एक बार लिस्ट लोड होगी (फास्ट स्पीड के लिए)
def get_all_nse_symbols():
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        df = pd.read_csv(io.StringIO(response.text))
        # केवल एक्टिव Equity (EQ) शेयर्स लें
        df = df[df[" SERIES"].str.strip() == "EQ"]
        symbols = [f"{s.strip()}.NS" for s in df["SYMBOL"].tolist()]
        return symbols
    except Exception as e:
        # अगर NSE ब्लॉक करे तो बैकअप के लिए Nifty 500 का डायरेक्ट बैकअप
        st.warning("NSE से लिस्ट लोड करने में देरी, बैकअप लिस्ट का उपयोग हो रहा है।")
        return []


symbols_list = get_all_nse_symbols()

# साइडबार कंट्रोल्स
st.sidebar.header("📊 स्कैनिंग सेटिंग्स")
st.sidebar.info(f"कुल मिले NSE शेयर्स: **{len(symbols_list)}**")

scan_limit = st.sidebar.selectbox(
    "कितने शेयर्स स्कैन करने हैं?",
    [
        "Top 100 शेयर्स (सुपर फास्ट - 15 सेकंड)",
        "Top 500 शेयर्स (Nifty 500 - 1 से 2 मिनट)",
        "सभी NSE शेयर्स (2000+ - 4 से 5 मिनट)",
    ],
    index=1,
)

scan_type = st.sidebar.radio(
    "कंडीशन चुनें:",
    [
        "🔥 सिर्फ आज 0-Line क्रॉस करने वाले (Fresh Breakout)",
        "📈 वर्तमान में 0-Line के ऊपर चल रहे (Bullish Trend)",
    ],
)

start_scan = st.sidebar.button("🚀 शुरू करें (Start Scanning)", type="primary")

# --- 2. Woodies & CCI कैलकुलेशन फंक्शन ---
def analyze_data(ticker, df):
    try:
        sub_df = (
            df[ticker].dropna()
            if isinstance(df.columns, pd.MultiIndex)
            else df.dropna()
        )
        if len(sub_df) < 16:
            return None

        high = float(sub_df["High"].iloc[-1])
        low = float(sub_df["Low"].iloc[-1])
        close = float(sub_df["Close"].iloc[-1])

        # Woodie's Pivot
        pp = (high + low + (2 * close)) / 4
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high

        # Woodies CCI 14
        tp = (sub_df["High"] + sub_df["Low"] + sub_df["Close"]) / 3
        sma_tp = tp.rolling(window=14).mean()
        mean_dev = tp.rolling(window=14).apply(
            lambda x: np.mean(np.abs(x - x.mean()))
        )
        cci = (tp - sma_tp) / (0.015 * mean_dev)

        today_cci = float(cci.iloc[-1])
        yesterday_cci = float(cci.iloc[-2])

        return {
            "Symbol": ticker.replace(".NS", ""),
            "Close": round(close, 2),
            "Today CCI": round(today_cci, 2),
            "Yesterday CCI": round(yesterday_cci, 2),
            "Pivot (PP)": round(pp, 2),
            "R1 (Target)": round(r1, 2),
            "S1 (Support)": round(s1, 2),
            "Fresh_Cross": (yesterday_cci <= 0 and today_cci > 0),
            "Above_Zero": (today_cci > 0),
        }
    except Exception:
        return None


# --- 3. स्कैनिंग प्रोसेस ---
if start_scan:
    if not symbols_list:
        st.error("स्टॉक लिस्ट नहीं मिल पाई। कृपया दोबारा कोशिश करें।")
    else:
        # यूजर की चॉइस के हिसाब से लिमिट सेट करें
        if "100" in scan_limit:
            selected_symbols = symbols_list[:100]
        elif "500" in scan_limit:
            selected_symbols = symbols_list[:500]
        else:
            selected_symbols = symbols_list

        total = len(selected_symbols)
        batch_size = 50  # 50-50 के बैच में डाउनलोड करेंगे ताकि ऐप क्रैश न हो

        progress_bar = st.progress(0)
        status_box = st.empty()

        results = []

        for i in range(0, total, batch_size):
            batch = selected_symbols[i : i + batch_size]
            current_progress = min((i + batch_size) / total, 1.0)
            progress_bar.progress(current_progress)
            status_box.text(f"डेटा प्रोसेस हो रहा है: {i} / {total} शेयर्स...")

            try:
                # 50 शेयर्स का डेटा 1 ही बार में फ़ास्ट डाउनलोड
                batch_data = yf.download(
                    batch,
                    period="1mo",
                    interval="1d",
                    group_by="ticker",
                    progress=False,
                )

                for sym in batch:
                    res = analyze_data(sym, batch_data)
                    if res:
                        if (
                            "Fresh Breakout" in scan_type
                            and res["Fresh_Cross"]
                        ):
                            results.append(res)
                        elif (
                            "Bullish Trend" in scan_type
                            and res["Above_Zero"]
                        ):
                            results.append(res)
            except Exception:
                continue

        progress_bar.empty()
        status_box.empty()

        if results:
            df_res = pd.DataFrame(results).drop(
                columns=["Fresh_Cross", "Above_Zero"]
            )
            st.success(
                f"🎉 स्कैन पूरा हुआ! कुल **{len(df_res)}** शेयर फ़िल्टर हुए।"
            )
            st.dataframe(df_res, use_container_width=True)

            # Excel / CSV डाउनलोड
            csv_file = df_res.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 पूरी लिस्ट डाउनलोड करें (CSV)",
                csv_file,
                "all_nse_0line_stocks.csv",
                "text/csv",
            )
        else:
            st.warning("कोई भी शेयर तय कंडीशन में नहीं मिला।")
else:
    st.info("👈 साइडबार में जाकर शेयर्स की संख्या चुनें और **'Start Scanning'** दबाएं।")
