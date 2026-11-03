
import streamlit as st
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="2 Green 1 Red Screener",
    layout="wide"
)

st.title("NSE 2 Green + 1 Red Volume Screener")

st.write("""
केवल यह पैटर्न:
- लगातार 2 हरी Daily candles
- उसके बाद 1 लाल Daily candle
- लाल candle का Volume दोनों हरी candles के कुल Volume से कम
""")

@st.cache_data(ttl=3600)
def get_symbols():
    try:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]

        symbols = (
            df["SYMBOL"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        return sorted(symbols)

    except Exception:
        return [
            "RELIANCE", "TCS", "INFY", "SBIN",
            "HDFCBANK", "ICICIBANK", "ITC", "LT"
        ]


def scan_stock(symbol):
    try:
        df = yf.download(
            symbol + ".NS",
            period="45d",
            interval="1d",
            auto_adjust=False,
            progress=False
        )

        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        required = ["Open", "Close", "Volume"]

        if not all(c in df.columns for c in required):
            return None

        df = df[required].dropna()

        if len(df) < 3:
            return None

        # Latest 3 daily candles
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

        if (
            condition1
            and condition2
            and condition3
            and condition4
        ):
            return {
                "Symbol": symbol,
                "Green 1 Date": df.index[-3].strftime("%Y-%m-%d"),
                "Green 1 Volume": int(green1["Volume"]),
                "Green 2 Date": df.index[-2].strftime("%Y-%m-%d"),
                "Green 2 Volume": int(green2["Volume"]),
                "Red Date": df.index[-1].strftime("%Y-%m-%d"),
                "Red Volume": int(red["Volume"]),
                "Green Total Volume": int(green_total_volume)
            }

    except Exception:
        return None

    return None


if st.button("SCAN START", type="primary"):

    symbols = get_symbols()
    results = []

    progress = st.progress(0)
    status = st.empty()

    with ThreadPoolExecutor(max_workers=6) as executor:

        futures = {
            executor.submit(scan_stock, symbol): symbol
            for symbol in symbols
        }

        total = len(futures)
        completed = 0

        for future in as_completed(futures):

            completed += 1

            result = future.result()

            if result:
                results.append(result)

            progress.progress(completed / total)

            status.text(
                f"Scanned {completed}/{total} | "
                f"Found {len(results)}"
            )

    progress.empty()
    status.empty()

    if results:

        result_df = pd.DataFrame(results)

        result_df = result_df.sort_values("Symbol")

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
            result_df.to_csv(index=False).encode("utf-8-sig"),
            "2_green_1_red_screener.csv",
            "text/csv"
        )

    else:

        st.warning("कोई शेयर नहीं मिला।")
