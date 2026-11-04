
import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from io import BytesIO

CCI_LENGTH = 6
MIN_PRICE = 100
MAX_PRICE = 5000
BATCH_SIZE = 50

st.set_page_config(
    page_title="Nifty 500 Daily CCI Scanner",
    layout="wide"
)

st.title("Nifty 500 Daily CCI Scanner")

st.write("""
Nifty 500 | F&O Included
Daily CCI Turbo 6 > 0
Share Price ₹100–₹5000
""")


# =========================
# NIFTY 500 LIST
# =========================

@st.cache_data(ttl=3600)
def get_symbols():

    url = (
        "https://www.niftyindices.com/"
        "IndexConstituent/ind_nifty500list.csv"
    )

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        df = pd.read_csv(
            BytesIO(response.content)
        )

        df.columns = [
            str(c).strip().upper()
            for c in df.columns
        ]

        return sorted(
            df["SYMBOL"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

    except Exception as e:
        st.error(f"Nifty 500 Error: {e}")
        return []


# =========================
# CCI FORMULA
# =========================

def calculate_cci(df, length=6):

    tp = (
        df["High"] +
        df["Low"] +
        df["Close"]
    ) / 3

    sma = tp.rolling(length).mean()

    mean_dev = tp.rolling(length).apply(
        lambda x: abs(x - x.mean()).mean(),
        raw=True
    )

    cci = (tp - sma) / (0.015 * mean_dev)

    return cci


# =========================
# BATCH SCANNER
# =========================

def scan_batch(symbols):

    tickers = [
        symbol + ".NS"
        for symbol in symbols
    ]

    try:

        data = yf.download(
            tickers=tickers,
            period="60d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False,
            timeout=30
        )

        if data.empty:
            return []

        results = []

        for symbol in symbols:

            ticker = symbol + ".NS"

            try:

                if isinstance(data.columns, pd.MultiIndex):

                    if ticker not in data.columns.get_level_values(0):
                        continue

                    df = data[ticker].copy()

                else:

                    if len(symbols) != 1:
                        continue

                    df = data.copy()

                required = [
                    "Open", "High", "Low", "Close"
                ]

                if not all(
                    c in df.columns
                    for c in required
                ):
                    continue

                df = df[required].dropna()

                if len(df) < 10:
                    continue

                df["CCI"] = calculate_cci(
                    df,
                    CCI_LENGTH
                )

                latest = df.iloc[-1]

                price = float(latest["Close"])
                cci = float(latest["CCI"])

                if (
                    MIN_PRICE <= price <= MAX_PRICE
                    and cci > 0
                ):

                    results.append({
                        "Symbol": symbol,
                        "Date": df.index[-1].strftime("%Y-%m-%d"),
                        "Price": round(price, 2),
                        "Daily CCI 6": round(cci, 2),
                        "Signal": "CCI ABOVE ZERO"
                    })

            except Exception:
                continue

        return results

    except Exception as e:

        st.warning(f"Batch download error: {e}")

        return []


# =========================
# STREAMLIT SCAN
# =========================

if st.button("SCAN START", type="primary"):

    symbols = get_symbols()

    if not symbols:

        st.error("Nifty 500 सूची नहीं मिली।")

    else:

        st.info(
            f"कुल Nifty 500 शेयर: {len(symbols)}"
        )

        batches = [
            symbols[i:i + BATCH_SIZE]
            for i in range(0, len(symbols), BATCH_SIZE)
        ]

        results = []

        progress = st.progress(0)
        status = st.empty()

        for i, batch in enumerate(batches):

            status.text(
                f"Batch {i+1}/{len(batches)} "
                f"| शेयर {len(batch)} "
                f"| Found {len(results)}"
            )

            batch_results = scan_batch(batch)

            results.extend(batch_results)

            progress.progress(
                (i + 1) / len(batches)
            )

        progress.empty()
        status.empty()

        if results:

            result_df = pd.DataFrame(results)

            result_df = result_df.sort_values(
                "Symbol"
            )

            st.success(
                f"कुल शेयर मिले: {len(result_df)}"
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
                "cci_daily_results.csv",
                "text/csv"
            )

        else:

            st.warning(
                "CCI नियम के अनुसार कोई शेयर नहीं मिला।"
            )
