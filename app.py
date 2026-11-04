
import pandas as pd
import yfinance as yf
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================
# SETTINGS
# =========================

CCI_LENGTH = 6

MIN_PRICE = 100
MAX_PRICE = 5000

MAX_WORKERS = 5

# =========================
# NIFTY 500 LIST
# =========================

def get_nifty500_symbols():

    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/"
    }

    session = requests.Session()
    session.headers.update(headers)

    try:
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
            for item in data["data"]
            if "symbol" in item
        ]

        symbols = [
            s for s in symbols
            if s not in ["NIFTY 500"]
        ]

        return sorted(set(symbols))

    except Exception as e:

        print("Nifty 500 list error:", e)

        return []


# =========================
# F&O SYMBOL LIST
# =========================

def get_fo_symbols():

    url = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"

    try:

        df = pd.read_csv(url)

        df.columns = [
            str(c).strip().upper()
            for c in df.columns
        ]

        symbol_column = next(
            (
                c for c in df.columns
                if "SYMBOL" in c
            ),
            None
        )

        if symbol_column is None:
            return set()

        return set(
            df[symbol_column]
            .dropna()
            .astype(str)
            .str.strip()
        )

    except Exception as e:

        print("F&O list error:", e)

        return set()


# =========================
# DAILY CCI FORMULA
# =========================

def calculate_cci(df, length=6):

    # Typical Price
    tp = (
        df["High"] +
        df["Low"] +
        df["Close"]
    ) / 3

    # Simple Moving Average
    sma = tp.rolling(length).mean()

    # Mean Deviation
    mean_deviation = tp.rolling(length).apply(
        lambda x: abs(x - x.mean()).mean(),
        raw=True
    )

    # CCI Formula
    cci = (
        (tp - sma) /
        (0.015 * mean_deviation)
    )

    return cci


# =========================
# SCAN STOCK
# =========================

def scan_stock(symbol):

    try:

        ticker = symbol + ".NS"

        df = yf.download(
            ticker,
            period="60d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if df.empty:
            return None

        # Handle MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):

            df.columns = df.columns.get_level_values(0)

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        if not all(
            col in df.columns
            for col in required
        ):
            return None

        df = df[required].dropna()

        if len(df) < CCI_LENGTH + 2:
            return None

        # Calculate Daily CCI Turbo 6
        df["CCI_FAST"] = calculate_cci(
            df,
            CCI_LENGTH
        )

        # Latest Daily Candle
        latest = df.iloc[-1]

        close_price = float(latest["Close"])

        fast_cci = float(latest["CCI_FAST"])

        # Price Filter
        price_condition = (
            MIN_PRICE <= close_price <= MAX_PRICE
        )

        # Fast CCI must close above Zero Line
        cci_condition = fast_cci > 0

        # Final Signal
        if price_condition and cci_condition:

            return {
                "Symbol": symbol,

                "Date": df.index[-1].strftime("%Y-%m-%d"),

                "Close": round(close_price, 2),

                "CCI Turbo 6": round(fast_cci, 2),

                "Signal": "CCI ABOVE ZERO"
            }

    except Exception as e:

        print(symbol, "Error:", e)

    return None


# =========================
# MAIN SCANNER
# =========================

def main():

    print("Getting Nifty 500 stocks...")

    nifty_symbols = get_nifty500_symbols()

    if not nifty_symbols:

        print("Nifty 500 list not available.")

        return

    print("Nifty 500 Total:", len(nifty_symbols))

    print("Getting F&O stocks...")

    fo_symbols = get_fo_symbols()

    # Remove F&O stocks
    cash_symbols = [
        symbol for symbol in nifty_symbols
        if symbol not in fo_symbols
    ]

    print("After F&O removal:", len(cash_symbols))

    results = []

    total = len(cash_symbols)

    print("Scanning Daily CCI...")

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(scan_stock, symbol): symbol
            for symbol in cash_symbols
        }

        completed = 0

        for future in as_completed(futures):

            completed += 1

            try:

                result = future.result()

                if result:

                    results.append(result)

                    print(
                        "FOUND:",
                        result["Symbol"],
                        result["Close"],
                        result["CCI Turbo 6"]
                    )

            except Exception:
                pass

            if completed % 25 == 0:

                print(
                    f"Progress: {completed}/{total}"
                )

            time.sleep(0.01)

    # Save Results
    if results:

        result_df = pd.DataFrame(results)

        result_df = result_df.sort_values(
            "Symbol"
        )

        result_df.to_csv(
            "cci_daily_results.csv",
            index=False
        )

        print("\nStocks Found:", len(results))

        print(result_df.to_string(index=False))

    else:

        print("No stocks found.")

    print("Scan completed.")


if __name__ == "__main__":

    main()
