import pandas as pd
import streamlit as st
import yfinance as yf
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="Nifty 100 Weekly High Breakout", page_icon="📈", layout="wide")
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
TRADES_PATH = DATA / "paper_trades.csv"
SIGNALS_PATH = DATA / "signals.csv"

st.title("📈 Nifty 100 — Current Week High Breakout Paper Trading")
st.caption("Paper trading only • No real orders • Yahoo Finance data may be delayed or incomplete")

with st.sidebar:
    st.header("Settings")
    capital = st.number_input("Virtual capital per trade (₹)", min_value=1000, value=100000, step=10000)
    green_limit = st.selectbox("Green candles after breakout", [1, 2, 3], index=2)
    st.caption("Weekly High is Monday-to-Friday of the current trading week. Holiday sessions are naturally skipped.")
    st.warning("Yahoo Finance is not a guaranteed real-time NSE data feed.")

@st.cache_data(ttl=86400, show_spinner=False)
def get_nifty100_symbols():
    # Public constituent table; fallback below is intentionally marked as partial.
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/NIFTY_100")
        for t in tables:
            col = next((c for c in t.columns if str(c).strip().lower() in ("symbol", "company symbol")), None)
            if col is not None:
                syms = t[col].astype(str).str.strip()
                syms = [s.replace(".", "-") + ".NS" for s in syms if s and s.lower() != "nan" and s.lower() != "symbol"]
                if len(set(syms)) >= 80:
                    return sorted(set(syms)), "Public constituent table"
    except Exception:
        pass
    # Fallback is partial and dashboard will clearly disclose it.
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
    ], "Fallback list (partial; not full Nifty 100)"

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
        # Keep completed candles only; yfinance timestamps may be timezone-aware.
        now = pd.Timestamp.now(tz=df.index.tz) if df.index.tz is not None else pd.Timestamp.now()
        df = df[df.index + pd.Timedelta(hours=1) <= now]
        return df
    except Exception:
        return pd.DataFrame()

def monday_start(index):
    last = index[-1]
    return last.normalize() - pd.Timedelta(days=last.weekday())

def analyze_symbol(symbol, green_limit):
    df = download_hourly(symbol)
    if len(df) < 8:
        return None
    idx = df.index
    current_week_start = monday_start(idx)
    week_df = df[(df.index >= current_week_start) & (df.index.dayofweek < 5)]
    if week_df.empty:
        return None
    # Current week's running high for display.
    current_week_high = float(week_df["High"].max())
    found = None

    # Scan for a green hourly candle that closes above the running Monday-Friday high
    # BEFORE that candle. This avoids comparing a candle to its own high.
    for i in range(1, len(df)):
        candle = df.iloc[i]
        candle_day = df.index[i].dayofweek
        if candle_day > 4:
            continue
        candle_week_start = df.index[i].normalize() - pd.Timedelta(days=candle_day)
        prior_week_rows = df[(df.index < df.index[i]) & (df.index >= candle_week_start) & (df.index.dayofweek < 5)]
        if prior_week_rows.empty:
            continue
        prior_running_high = float(prior_week_rows["High"].max())
        green_breakout = float(candle["Close"]) > float(candle["Open"]) and float(candle["Close"]) > prior_running_high
        if not green_breakout:
            continue

        greens = [i]
        j = i + 1
        while j < len(df) and len(greens) < green_limit:
            if df.index[j].dayofweek > 4:
                j += 1
                continue
            next_c = df.iloc[j]
            if float(next_c["Close"]) > float(next_c["Open"]):
                greens.append(j)
                j += 1
            else:
                break
        if j >= len(df):
            found = {
                "symbol": symbol, "current_week_high": current_week_high,
                "breakout_level_before_candle": prior_running_high, "breakout_time": str(df.index[i]),
                "green_count": len(greens), "red_time": "", "red_high": None,
                "status": "Waiting for red candle", "entry_price": None, "entry_time": "",
                "current_price": float(df["Close"].iloc[-1])
            }
            continue

        red = df.iloc[j]
        if float(red["Close"]) >= float(red["Open"]):
            continue
        # User rule: red candle high must be lower than the high of the latest green candle.
        latest_green_high = float(df.iloc[greens[-1]]["High"])
        if float(red["High"]) >= latest_green_high:
            continue

        next_i = j + 1
        if next_i >= len(df):
            found = {
                "symbol": symbol, "current_week_high": current_week_high,
                "breakout_level_before_candle": prior_running_high, "breakout_time": str(df.index[i]),
                "green_count": len(greens), "red_time": str(df.index[j]),
                "red_high": float(red["High"]), "status": "Waiting for next candle to break red High",
                "entry_price": None, "entry_time": "", "current_price": float(df["Close"].iloc[-1])
            }
            continue

        next_candle = df.iloc[next_i]
        # Entry is triggered only in the immediately next 1-hour candle.
        if float(next_candle["High"]) >= float(red["High"]):
            found = {
                "symbol": symbol, "current_week_high": current_week_high,
                "breakout_level_before_candle": prior_running_high, "breakout_time": str(df.index[i]),
                "green_count": len(greens), "red_time": str(df.index[j]),
                "red_high": float(red["High"]), "status": "Entry triggered",
                "entry_price": float(red["High"]), "entry_time": str(df.index[next_i]),
                "current_price": float(df["Close"].iloc[-1])
            }
        else:
            found = {
                "symbol": symbol, "current_week_high": current_week_high,
                "breakout_level_before_candle": prior_running_high, "breakout_time": str(df.index[i]),
                "green_count": len(greens), "red_time": str(df.index[j]),
                "red_high": float(red["High"]), "status": "Next candle did not break red High",
                "entry_price": None, "entry_time": "", "current_price": float(df["Close"].iloc[-1])
            }
    return found

signal_columns = ["symbol","current_week_high","breakout_level_before_candle","breakout_time","green_count","red_time","red_high","status","entry_price","entry_time","current_price"]
trade_columns = ["symbol","entry_time","entry_price","quantity","current_price","pnl_rupees","pnl_percent","status"]

def read_csv(path, cols):
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame(columns=cols)

left, right = st.columns([1, 3])
with left:
    scan = st.button("🔄 Scan Nifty 100 now", type="primary", use_container_width=True)
with right:
    st.caption(f"Last app load: {datetime.now().strftime('%d-%b-%Y %H:%M:%S')} (server time)")

if scan:
    symbols, source = get_nifty100_symbols()
    progress = st.progress(0, text="Scanning completed 1-hour candles…")
    results = []
    for n, symbol in enumerate(symbols):
        result = analyze_symbol(symbol, green_limit)
        if result:
            results.append(result)
        progress.progress((n + 1) / len(symbols), text=f"Scanning {symbol} ({n+1}/{len(symbols)})")
    progress.empty()
    signals = pd.DataFrame(results, columns=signal_columns)
    signals.to_csv(SIGNALS_PATH, index=False)

    trades = read_csv(TRADES_PATH, trade_columns)
    existing = set()
    if not trades.empty:
        existing = set(trades["symbol"].astype(str) + "|" + trades["entry_time"].astype(str))
    for row in results:
        if row["status"] == "Entry triggered" and row["entry_price"] is not None:
            key = row["symbol"] + "|" + str(row["entry_time"])
            if key not in existing:
                qty = int(capital // float(row["entry_price"]))
                trades = pd.concat([trades, pd.DataFrame([{
                    "symbol": row["symbol"], "entry_time": row["entry_time"],
                    "entry_price": row["entry_price"], "quantity": qty,
                    "current_price": row["current_price"],
                    "pnl_rupees": (row["current_price"] - row["entry_price"]) * qty,
                    "pnl_percent": ((row["current_price"] - row["entry_price"]) / row["entry_price"]) * 100,
                    "status": "OPEN"
                }])], ignore_index=True)
                existing.add(key)
    trades.to_csv(TRADES_PATH, index=False)
    st.success(f"Scan complete: checked {len(symbols)} symbols. Constituent source: {source}")
    if len(symbols) < 100:
        st.warning("Nifty 100 ki full list load nahi hui; fallback list partial hai. Full 100-stock scan ke liye constituent source/API verify karein.")

signals = read_csv(SIGNALS_PATH, signal_columns)
trades = read_csv(TRADES_PATH, trade_columns)

st.subheader("🔔 Breakout / Red Candle Signals")
if signals.empty:
    st.info("Pehla scan chalane ke liye 'Scan Nifty 100 now' dabayein.")
else:
    for col in ["current_week_high","breakout_level_before_candle","red_high","entry_price","current_price"]:
        signals[col] = pd.to_numeric(signals[col], errors="coerce").round(2)
    st.dataframe(signals, use_container_width=True, hide_index=True)

st.subheader("📒 Paper Trading — Trade Sheet")
if trades.empty:
    st.info("Abhi koi paper entry trigger nahi hui.")
else:
    for col in ["entry_price","current_price","quantity"]:
        trades[col] = pd.to_numeric(trades[col], errors="coerce")
    trades["pnl_rupees"] = (trades["current_price"] - trades["entry_price"]) * trades["quantity"]
    trades["pnl_percent"] = (trades["current_price"] - trades["entry_price"]) / trades["entry_price"] * 100
    trades["pnl_rupees"] = trades["pnl_rupees"].round(2)
    trades["pnl_percent"] = trades["pnl_percent"].round(2)
    st.dataframe(trades, use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    c1.metric("Open paper trades", int((trades["status"] == "OPEN").sum()))
    c2.metric("Unrealized P&L (₹)", f"₹{trades['pnl_rupees'].sum():,.2f}")
    st.download_button("⬇️ Download Excel-compatible trade sheet", trades.to_csv(index=False).encode("utf-8-sig"), "paper_trades.csv", "text/csv")

st.caption("Weekly High is calculated Monday-Friday. A breakout is tested against the high already formed before the breakout candle; completed 1-hour candles only. Verify historical signals before relying on this starter strategy. No live orders are placed.")
