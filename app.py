
import streamlit as st
import pandas as pd
import yfinance as yf
import requests
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
**स्कैनिंग नियम**
- केवल Nifty 500
- F&O शेयर हटाएँ
- शेयर भाव ₹100 से ₹5000
- Daily CCI Turbo Length 6
- Daily CCI की बंद कैंडल 0 के ऊपर
""")

# =========================
# NIFTY 500 LIST
# =========================

@st.cache_data(ttl=3600)
def get_nifty500_symbols():

    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/"
    }

    try:
        session = requests.Session()
        session.headers.update(headers)

        session.get(
            "https://www.nseindia.com",
            timeout=20
        )

        response = session.get(
            url,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        symbols = [
            item["symbol"]
            for item in data.get("data", [])
            if "symbol" in item
            and item["symbol"] != "NIFTY 500"
        ]

        return sorted(set(symbols))

    except Exception as e:
        st.error(f"Nifty 500 सूची नहीं मिली: {e}")
        return []


# =========================
# F&O LIST
# =========================

@st.cache_data(ttl=3600)
def get_fo_symbols():

    urls = [
        "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv",
        "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
    ]

    for url in urls:
        try:
            df = pd.read_csv(url)

            df.columns = [
                str(c).strip().upper()
                for c in df.columns
            ]

            symbol_col = next(
                (c for c in df.columns if "SYMBOL" in c),
                None
            )

            if symbol_col:
                return set(
                    df[symbol_col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                )

        except Exception:
            continue

    st.warning("F&O सूची डाउनलोड नहीं हुई।")
    return None


# =========================
# CCI FORMULA
# =========================

def calculate_cci(df, length=6):

    typical_price = (
        df["High"] + df["Low"] + df["Close"]
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

        required = ["Open", "High", "Low", "Close", "Volume"]

        if not all(col in df.columns for col in required):
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

        # Price ₹100 to ₹5000
        price_condition = (
            MIN_PRICE <= close_price <= MAX_PRICE
        )

        # Daily CCI above Zero Line
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

    with st.spinner("Nifty 500 शेयर सूची डाउनलोड हो रही है..."):

        nifty_symbols = get_nifty500_symbols()
        fo_symbols = get_fo_symbols()

    if not nifty_symbols:
        st.error("Nifty 500 शेयर सूची नहीं मिली।")

    elif fo_symbols is None:
        st.error("F&O सूची नहीं मिली। F&O हटाए बिना स्कैन नहीं किया गया।")

    else:

        # Remove F&O shares
        cash_symbols = [
            symbol for symbol in nifty_symbols
            if symbol not in fo_symbols
        ]

        st.info(
            f"Nifty 500: {len(nifty_symbols)} | "
            f"F&O हटाने के बाद: {len(cash_symbols)}"
        )

        results = []

        progress = st.progress(0)
        status = st.empty()

        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:

            futures = {
                executor.submit(scan_stock, symbol): symbol
                for symbol in cash_symbols
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
    "Daily CCI 6 > 0 | Price ₹100–₹5000 | Nifty 500 | F&O Excluded"
)
