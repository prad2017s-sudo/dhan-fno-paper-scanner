
import streamlit as st
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================
# SETTINGS
# =========================

CCI_LENGTH = 6
MIN_PRICE = 100
MAX_PRICE = 5000
MAX_WORKERS = 5

st.set_page_config(
    page_title="Nifty 500 Daily CCI Scanner",
    layout="wide"
)

st.title("Nifty 500 Daily CCI Scanner")

st.write("""
- Nifty 500 के सभी शेयर
- F&O शेयर भी शामिल
- शेयर भाव ₹100 से ₹5000
- Daily CCI Turbo Length 6
- Daily CCI की बंद कैंडल 0 के ऊपर
""")

# =========================
# NIFTY 500 LIST
# =========================

@st.cache_data(ttl=3600)
def get_nifty500_symbols():

    url = (
        "https://www.niftyindices.com/"
        "IndexConstituent/ind_nifty500list.csv"
    )

    try:
        df = pd.read_csv(url)

        df.columns = [
            str(c).strip().upper()
            for c in df.columns
        ]

        if "SYMBOL" not in df.columns:
            st.error("Nifty 500 Symbol column नहीं मिली")
            return []

        symbols = (
            df["SYMBOL"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        return sorted(symbols)

    except Exception as e:
        st.error(f"Nifty 500 सूची Error: {e}")
        return []


# =========================
# CCI FORMULA
# =========================

def calculate_cci(df, length=6):

    typical_price = (
        df["High"] +
        df["Low"] +
        df["Close"]
    ) / 3

    sma = typical_price.rolling(length).mean()

    mean_deviation = typical_price.rolling(
        length
    ).apply(
        lambda x: abs(x - x.mean()).mean(),
        raw=True
    )

    cci = (
        (typical_price - sma)
        / (0.015 * mean_deviation)
    )

    return cci


# =========================
# SCAN STOCK
# =========================

def scan_stock(symbol):

    try:

        df = yf.download(
            symbol + ".NS",
            period="60d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        required = [
            "Open", "High", "Low", "Close", "Volume"
        ]

        if not all(c in df.columns for c in required):
            return None

        df = df[required].dropna()

        if len(df) < CCI_LENGTH + 2:
            return None

        # Daily CCI Turbo 6
        df["CCI_FAST"] = calculate_cci(
            df,
            CCI_LENGTH
        )

        latest = df.iloc[-1]

        close_price = float(latest["Close"])
        fast_cci = float(latest["CCI_FAST"])

        # Price filter
        price_condition = (
            MIN_PRICE <= close_price <= MAX_PRICE
        )

        # CCI above Zero Line
        cci_condition = fast_cci > 0

        if price_condition and cci_condition:

            return {
                "Symbol": symbol,
                "Date": df.index[-1].strftime("%Y-%m-%d"),
                "Close Price": round(close_price, 2),
                "Daily CCI Turbo 6": round(fast_cci, 2),
                "Signal": "CCI ABOVE ZERO"
            }

    except Exception:
        return None

    return None


# =========================
# STREAMLIT SCANNER
# =========================

workers = st.slider(
    "एक साथ कितने शेयर स्कैन करें?",
    min_value=2,
    max_value=10,
    value=5
)

if st.button("SCAN START", type="primary"):

    symbols = get_nifty500_symbols()

    if not symbols:

        st.error("Nifty 500 शेयर सूची डाउनलोड नहीं हुई।")

    else:

        st.info(
            f"Nifty 500 में कुल शेयर: {len(symbols)}"
        )

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

st.caption(
    "Nifty 500 | F&O Included | CCI 6 > 0 | Price ₹100–₹5000"
)
