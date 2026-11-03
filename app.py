
import streamlit as st
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="NSE 2 Green 1 Red Screener",
    layout="wide"
)

st.title("NSE 2 Green + 1 Red Volume Screener")

st.write("""
नियम:
1. लगातार 2 हरी Daily candles
2. उसके बाद 1 लाल Daily candle
3. Red Volume दोनों Green candles के कुल Volume से कम
4. F&O शेयर हटाएँ
5. शेयर प्राइस ₹100 से ₹5000
""")

# NSE Cash Market शेयर लिस्ट
@st.cache_data(ttl=3600)
def get_symbols():
    try:
        equity_url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        fo_url = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"

        eq = pd.read_csv(equity_url)
        fo = pd.read_csv(fo_url)

        eq.columns = [str(c).strip() for c in eq.columns]
        fo.columns = [str(c).strip() for c in fo.columns]

        symbols = (
            eq["SYMBOL"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        fo_symbols = set(
            fo["SYMBOL"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        # F&O शेयर हटाएँ
        symbols = [
            s for s in symbols
            if s not in fo_symbols
        ]

        return sorted(symbols)

    except Exception as e:
        st.error(f"NSE शेयर सूची नहीं मिली: {e}")
        return []


# शेयर पैटर्न स्कैन
def scan_stock(symbol):

    try:
        df = yf.download(
            symbol + ".NS",
            period="45d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if df.empty:
            return None

        # yfinance MultiIndex columns संभालें
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        required = ["Open", "High", "Low", "Close", "Volume"]

        if not all(c in df.columns for c in required):
            return None

        df = df[required].dropna()

        if len(df) < 3:
            return None

        # Latest 3 Daily candles
        green1 = df.iloc[-3]
        green2 = df.iloc[-2]
        red = df.iloc[-1]

        # Candle conditions
        condition1 = green1["Close"] > green1["Open"]
        condition2 = green2["Close"] > green2["Open"]
        condition3 = red["Close"] < red["Open"]

        # Volume condition
        green_total_volume = (
            green1["Volume"] + green2["Volume"]
        )

        condition4 = (
            red["Volume"] < green_total_volume
        )

        # Red candle के दिन का शेयर भाव
        share_price = float(red["Close"])

        # Price ₹100 से ₹5000
        price_condition = (
            100 <= share_price <= 5000
        )

        # सभी नियम सही होने चाहिए
        if (
            condition1
            and condition2
            and condition3
            and condition4
            and price_condition
        ):

            return {
                "Symbol": symbol,

                "Share Price": round(share_price, 2),

                "Green 1 Date":
                    df.index[-3].strftime("%Y-%m-%d"),

                "Green 1 Volume":
                    int(green1["Volume"]),

                "Green 2 Date":
                    df.index[-2].strftime("%Y-%m-%d"),

                "Green 2 Volume":
                    int(green2["Volume"]),

                "Red Date":
                    df.index[-1].strftime("%Y-%m-%d"),

                "Red Volume":
                    int(red["Volume"]),

                "Green Total Volume":
                    int(green_total_volume)
            }

    except Exception:
        return None

    return None


# Scanner Settings
workers = st.slider(
    "एक साथ कितने शेयर स्कैन करें?",
    min_value=2,
    max_value=12,
    value=6
)


# Scan Button
if st.button("SCAN START", type="primary"):

    symbols = get_symbols()

    if not symbols:
        st.error("NSE शेयर सूची नहीं मिली।")
    else:

        results = []

        progress = st.progress(0)
        status = st.empty()

        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:

            futures = {
                executor.submit(scan_stock, symbol): symbol
                for symbol in symbols
            }

            total = len(futures)
            completed = 0

            for future in as_completed(futures):

                completed += 1

                try:
                    result = future.result()

                    if result:
                        results.append(result)

                except Exception:
                    pass

                progress.progress(
                    completed / total
                )

                status.text(
                    f"Scanned {completed}/{total} | "
                    f"Found {len(results)}"
                )

        progress.empty()
        status.empty()

        if results:

            result_df = pd.DataFrame(results)

            result_df = result_df.sort_values(
                "Symbol"
            )

            st.success(
                f"Total stocks found: {len(result_df)}"
            )

            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "Download CSV",
                result_df.to_csv(
                    index=False
                ).encode("utf-8-sig"),

                "nse_2green_1red_screener.csv",

                "text/csv"
            )

        else:

            st.warning(
                "इस नियम के अनुसार कोई शेयर नहीं मिला।"
            )

st.info("""
Green Candle = Close > Open

Red Candle = Close < Open

Red Volume < दोनों Green candles का कुल Volume

Share Price = ₹100 से ₹5000

F&O शेयर स्कैन नहीं होंगे।
""")
