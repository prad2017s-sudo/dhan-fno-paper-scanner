import pandas as pd
import streamlit as st
import yfinance as yf
from pathlib import Path
from datetime import datetime, date, timedelta

st.set_page_config(page_title="Nifty 100 Date-Range Breakout Paper Trader", page_icon="📈", layout="wide")
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
TRADES_PATH = DATA_DIR / "paper_trades.csv"
SIGNALS_PATH = DATA_DIR / "signals.csv"

st.title("📈 Nifty 100 — Date-Range High Breakout Paper Trading")
st.caption("Paper trading only • No real orders • Data availability depends on provider")

with st.sidebar:
    st.header("Settings")
    capital = st.number_input("Virtual capital per trade (₹)", min_value=1000, value=100000, step=10000)
    green_limit = st.selectbox("Green candles after breakout", [1, 2, 3], index=2)
    st.subheader("High calculation date range")
    default_end = date.today() - timedelta(days=3)
    default_start = default_end - timedelta(days=4)
    start_date = st.date_input("High range — from", value=default_start)
    end_date = st.date_input("High range — to", value=default_end)
    st.caption("The range's High becomes the breakout level. Scanning starts only after the ending date.")
    st.warning("Yahoo Finance data may be delayed/incomplete. Use a licensed broker feed for reliable live data.")

if start_date > end_date:
    st.error("Starting date ending date se pehle honi chahiye.")
    st.stop()
if end_date >= date.today():
    st.warning("Ending date aaj ya future mein hai. Breakout scan ending date ke baad ke available completed hourly candles par hi chalega.")

@st.cache_data(ttl=86400, show_spinner=False)
def get_nifty100_symbols():
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/NIFTY_100")
        for table in tables:
            symbol_col = next((c for c in table.columns if str(c).strip().lower() in ("symbol", "company symbol")), None)
            if symbol_col is not None:
                symbols = table[symbol_col].astype(str).str.strip()
                symbols = [s.replace(".", "-") + ".NS" for s in symbols if s and s.lower() not in ("nan", "symbol")]
                symbols = sorted(set(symbols))
                if len(symbols) >= 80:
                    return symbols, "Public constituent table"
    except Exception:
        pass
    return [
        "RELIANCE.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS","TCS.NS","ITC.NS",
        "LT.NS","SBIN.NS","BHARTIARTL.NS","AXISBANK.NS","KOTAKBANK.NS","HINDUNILVR.NS",
        "BAJFINANCE.NS","MARUTI.NS","SUNPHARMA.NS","TATAMOTORS.NS","TATASTEEL.NS",
        "NTPC.NS","POWERGRID.NS","M&M.NS","ULTRACEMCO.NS","ASIANPAINT.NS","WIPRO.NS",
        "ONGC.NS","ADANIPORTS.NS","COALINDIA.NS","JSWSTEEL.NS","TECHM.NS","HCLTECH.NS",
        "GRASIM.NS","INDUSINDBK.NS","NESTLEIND.NS","TITAN.NS","DRREDDY.NS","CIPLA.NS",
        "APOLLOHOSP.NS","EICHERMOT.NS","HEROMOTOCO.NS","DIVISLAB.NS","BRITANNIA.NS",
        "BPCL.NS","IOC.NS","TATACONSUM.NS","SBILIFE.NS","HDFCLIFE.NS","BAJAJFINSV.NS",
        "SHRIRAMFIN.NS","BEL.NS","TRENT.NS","PIDILITIND.NS"
    ], "Fallback list (partial)"

def download_hourly(symbol):
    try:
        df = yf.download(symbol, period="60d", interval="1h", auto_adjust=False, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).title() for c in df.columns]
        cols = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in df.columns for c in cols):
            return pd.DataFrame()
        df = df[cols].dropna().copy()
        df.index = pd.to_datetime(df.index)
        now = pd.Timestamp.now(tz=df.index.tz) if df.index.tz is not None else pd.Timestamp.now()
        # Hourly bar start time; only completed bars.
        df = df[df.index + pd.Timedelta(hours=1) <= now]
        return df
    except Exception:
        return pd.DataFrame()

def analyze_symbol(symbol, start_date, end_date, green_limit):
    df = download_hourly(symbol)
    if len(df) < 8:
        return None, "Insufficient hourly data"
    # Compare by local date labels from provider (usually Asia/Kolkata for NSE).
    bar_dates = pd.Series([x.date() for x in df.index], index=df.index)
    ref_mask = (bar_dates >= start_date) & (bar_dates <= end_date) & (pd.Series(df.index.dayofweek, index=df.index) < 5)
    ref_df = df.loc[ref_mask.values]
    if ref_df.empty:
        return None, "No reference candles in selected date range"
    range_high = float(ref_df["High"].max())
    range_high_time = str(ref_df["High"].idxmax())

    # Strictly after ending date: selected dates are used only to calculate reference high.
    scan_df = df.loc[(bar_dates > end_date).values & (pd.Series(df.index.dayofweek, index=df.index) < 5).values]
    if len(scan_df) < 2:
        return {
            "symbol": symbol, "range_from": str(start_date), "range_to": str(end_date),
            "range_high": range_high, "range_high_time": range_high_time,
            "breakout_time": "", "green_count": None, "red_time": "", "red_high": None,
            "status": "Waiting for post-range candles", "entry_price": None, "entry_time": "",
            "current_price": float(df["Close"].iloc[-1])
        }, None

    # Search post-range candles. For each green candle closing above fixed range high,
    # count consecutive green candles (the first candle is breakout candle).
    found = None
    values = scan_df
    for i in range(len(values)):
        candle = values.iloc[i]
        if float(candle["Close"]) <= float(range_high) or float(candle["Close"]) <= float(candle["Open"]):
            continue
        greens = [i]
        j = i + 1
        while j < len(values) and len(greens) < green_limit:
            next_c = values.iloc[j]
            if float(next_c["Close"]) > float(next_c["Open"]):
                greens.append(j)
                j += 1
            else:
                break
        if j >= len(values):
            found = {
                "symbol": symbol, "range_from": str(start_date), "range_to": str(end_date),
                "range_high": range_high, "range_high_time": range_high_time,
                "breakout_time": str(values.index[i]), "green_count": len(greens),
                "red_time": "", "red_high": None, "status": "Waiting for red candle",
                "entry_price": None, "entry_time": "", "current_price": float(values["Close"].iloc[-1])
            }
            continue
        red = values.iloc[j]
        if float(red["Close"]) >= float(red["Open"]):
            continue
        if float(red["High"]) >= float(values.iloc[greens[-1]]["High"]):
            continue
        next_i = j + 1
        if next_i >= len(values):
            found = {
                "symbol": symbol, "range_from": str(start_date), "range_to": str(end_date),
                "range_high": range_high, "range_high_time": range_high_time,
                "breakout_time": str(values.index[i]), "green_count": len(greens),
                "red_time": str(values.index[j]), "red_high": float(red["High"]),
                "status": "Waiting for next candle to break red High",
                "entry_price": None, "entry_time": "", "current_price": float(values["Close"].iloc[-1])
            }
            continue
        next_candle = values.iloc[next_i]
        if float(next_candle["High"]) >= float(red["High"]):
            found = {
                "symbol": symbol, "range_from": str(start_date), "range_to": str(end_date),
                "range_high": range_high, "range_high_time": range_high_time,
                "breakout_time": str(values.index[i]), "green_count": len(greens),
                "red_time": str(values.index[j]), "red_high": float(red["High"]),
                "status": "Entry triggered", "entry_price": float(red["High"]),
                "entry_time": str(values.index[next_i]), "current_price": float(values["Close"].iloc[-1])
            }
        else:
            found = {
                "symbol": symbol, "range_from": str(start_date), "range_to": str(end_date),
                "range_high": range_high, "range_high_time": range_high_time,
                "breakout_time": str(values.index[i]), "green_count": len(greens),
                "red_time": str(values.index[j]), "red_high": float(red["High"]),
                "status": "Next candle did not break red High", "entry_price": None,
                "entry_time": "", "current_price": float(values["Close"].iloc[-1])
            }
    return found, None

signal_cols = ["symbol","range_from","range_to","range_high","range_high_time","breakout_time","green_count","red_time","red_high","status","entry_price","entry_time","current_price"]
trade_cols = ["symbol","entry_time","entry_price","quantity","current_price","pnl_rupees","pnl_percent","status"]

def read_csv(path, cols):
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame(columns=cols)

if st.button("🔄 Scan Nifty 100", type="primary"):
    symbols, source = get_nifty100_symbols()
    progress = st.progress(0, text="Scanning stocks…")
    results = []
    for n, symbol in enumerate(symbols):
        result, err = analyze_symbol(symbol, start_date, end_date, green_limit)
        if result:
            results.append(result)
        progress.progress((n + 1) / len(symbols), text=f"{symbol} ({n+1}/{len(symbols)})")
    progress.empty()
    signals = pd.DataFrame(results, columns=signal_cols)
    signals.to_csv(SIGNALS_PATH, index=False)
    trades = read_csv(TRADES_PATH, trade_cols)
    existing = set()
    if not trades.empty:
        existing = set(trades["symbol"].astype(str) + "|" + trades["entry_time"].astype(str))
    for row in results:
        if row["status"] == "Entry triggered" and pd.notna(row["entry_price"]):
            key = str(row["symbol"]) + "|" + str(row["entry_time"])
            if key not in existing:
                entry = float(row["entry_price"])
                qty = int(capital // entry) if entry > 0 else 0
                trades = pd.concat([trades, pd.DataFrame([{
                    "symbol": row["symbol"], "entry_time": row["entry_time"],
                    "entry_price": entry, "quantity": qty, "current_price": float(row["current_price"]),
                    "pnl_rupees": (float(row["current_price"]) - entry) * qty,
                    "pnl_percent": ((float(row["current_price"]) - entry) / entry) * 100,
                    "status": "OPEN"
                }])], ignore_index=True)
                existing.add(key)
    trades.to_csv(TRADES_PATH, index=False)
    st.success(f"Scan complete: {len(symbols)} symbols checked. Source: {source}")
    if len(symbols) < 100:
        st.warning("Full Nifty 100 list load nahi hui; fallback partial list use hui.")

signals = read_csv(SIGNALS_PATH, signal_cols)
trades = read_csv(TRADES_PATH, trade_cols)
st.subheader("🔔 Breakout / Red Candle Signals")
if signals.empty:
    st.info("Date range choose karke Scan dabayein.")
else:
    for c in ["range_high","red_high","entry_price","current_price"]:
        signals[c] = pd.to_numeric(signals[c], errors="coerce").round(2)
    st.dataframe(signals, use_container_width=True, hide_index=True)

st.subheader("📒 Paper Trading — Trade Sheet")
if trades.empty:
    st.info("Abhi koi paper entry trigger nahi hui.")
else:
    for c in ["entry_price","current_price","quantity"]:
        trades[c] = pd.to_numeric(trades[c], errors="coerce")
    trades["pnl_rupees"] = ((trades["current_price"] - trades["entry_price"]) * trades["quantity"]).round(2)
    trades["pnl_percent"] = (((trades["current_price"] - trades["entry_price"]) / trades["entry_price"]) * 100).round(2)
    st.dataframe(trades, use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    c1.metric("Open paper trades", int((trades["status"] == "OPEN").sum()))
    c2.metric("Unrealized P&L (₹)", f"₹{trades['pnl_rupees'].sum():,.2f}")
    st.download_button("⬇️ Download Excel-compatible CSV", trades.to_csv(index=False).encode("utf-8-sig"), "paper_trades.csv", "text/csv")

st.caption("The selected date range is used only to calculate the reference High. Breakout scanning starts strictly after the ending date using completed hourly candles. Yahoo Finance may be delayed/incomplete. No real orders are placed.")
