import os
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Nifty 100 Breakout Paper Trader", page_icon="📈", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
TRADES_FILE = DATA_DIR / "paper_trades.csv"
SIGNALS_FILE = DATA_DIR / "signals.csv"
CAPITAL_DEFAULT = 100000.0

st.title("📈 Nifty 100 Weekly High Breakout — Paper Trading")
st.caption("Virtual trading only • No real orders are placed • Data freshness depends on the provider")

with st.sidebar:
    st.header("Settings")
    capital = st.number_input("Virtual starting capital (₹)", min_value=1000.0, value=CAPITAL_DEFAULT, step=10000.0)
    max_green = st.selectbox("Maximum green candles after breakout", [1, 2, 3], index=2)
    refresh = st.selectbox("Dashboard refresh interval", ["Manual", "30 seconds", "60 seconds", "5 minutes"], index=2)
    st.caption("Yahoo Finance data may be delayed or unavailable. For dependable real-time NSE data, connect a licensed broker/data API.")

REFRESH_SECONDS = {"Manual": None, "30 seconds": 30, "60 seconds": 60, "5 minutes": 300}[refresh]
if REFRESH_SECONDS:
    st.markdown(f"<meta http-equiv='refresh' content='{REFRESH_SECONDS}'>", unsafe_allow_html=True)

# Nifty 100 constituents are sourced from Wikipedia's public constituent table.
@st.cache_data(ttl=86400, show_spinner=False)
def get_nifty100_symbols():
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/NIFTY_100")
        for table in tables:
            cols = [str(c).strip().lower() for c in table.columns]
            symbol_col = next((c for c in table.columns if str(c).strip().lower() in ("symbol", "company symbol")), None)
            if symbol_col is not None:
                symbols = table[symbol_col].astype(str).str.strip().tolist()
                symbols = [s for s in symbols if s and s.lower() not in ("nan", "symbol")]
                if len(symbols) >= 50:
                    return sorted(set([s.replace(".", "-") + ".NS" for s in symbols]))
    except Exception:
        pass
    # Fallback list if the public constituent page is unavailable.
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
    ]

def download_hourly(symbol):
    try:
        df = yf.download(symbol, period="60d", interval="1h", auto_adjust=False, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns={c: str(c).title() for c in df.columns})
        needed = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in df.columns for c in needed):
            return pd.DataFrame()
        df = df[needed].dropna().copy()
        df.index = pd.to_datetime(df.index)
        # Avoid using the currently forming hourly candle: evaluate completed candles only.
        now = pd.Timestamp.now(tz=df.index.tz) if df.index.tz is not None else pd.Timestamp.now()
        df = df[df.index + pd.Timedelta(hours=1) <= now]
        return df
    except Exception:
        return pd.DataFrame()

def analyze_symbol(symbol, max_green):
    df = download_hourly(symbol)
    if len(df) < 10:
        return None, None

    idx = df.index
    latest = idx[-1]
    week_start = latest.normalize() - pd.Timedelta(days=latest.weekday())
    current_week = df[df.index >= week_start]
    weekly_high = float(current_week["High"].max()) if not current_week.empty else float(df["High"].max())

    # Find the latest completed setup. A breakout candle must be green and close
    # above the highest high recorded earlier in that same calendar week.
    found = None
    for i in range(1, len(df)):
        c = df.iloc[i]
        bar_time = df.index[i]
        bar_week_start = bar_time.normalize() - pd.Timedelta(days=bar_time.weekday())
        prior_same_week = df[(df.index >= bar_week_start) & (df.index < bar_time)]
        if prior_same_week.empty:
            continue
        prior_week_high = float(prior_same_week["High"].max())
        is_green_breakout = float(c["Close"]) > float(c["Open"]) and float(c["Close"]) > prior_week_high
        if not is_green_breakout:
            continue

        green_indices = [i]
        j = i + 1
        while j < len(df) and len(green_indices) < max_green and float(df.iloc[j]["Close"]) > float(df.iloc[j]["Open"]):
            # Reset the pattern if it crosses into a new calendar week.
            if df.index[j].normalize() - pd.Timedelta(days=df.index[j].weekday()) != bar_week_start:
                break
            green_indices.append(j)
            j += 1

        if j >= len(df):
            continue
        red = df.iloc[j]
        if df.index[j].normalize() - pd.Timedelta(days=df.index[j].weekday()) != bar_week_start:
            continue
        if float(red["Close"]) >= float(red["Open"]):
            continue

        latest_green_high = float(df.iloc[green_indices[-1]]["High"])
        if float(red["High"]) >= latest_green_high:
            continue

        entry_bar_i = j + 1
        base_result = {
            "symbol": symbol,
            "weekly_high": weekly_high,
            "breakout_time": str(df.index[i]),
            "green_count": len(green_indices),
            "red_time": str(df.index[j]),
            "red_high": float(red["High"]),
            "current_price": float(df["Close"].iloc[-1]),
        }
        if entry_bar_i >= len(df):
            found = {**base_result, "status": "Waiting for next candle", "entry_price": None, "entry_time": None}
            continue

        next_bar = df.iloc[entry_bar_i]
        if float(next_bar["High"]) >= float(red["High"]):
            found = {**base_result, "status": "Entry triggered", "entry_price": float(red["High"]), "entry_time": str(df.index[entry_bar_i])}
        else:
            found = {**base_result, "status": "Setup invalid (next candle did not break red high)", "entry_price": None, "entry_time": None}

    return found, float(df["Close"].iloc[-1])

def load_csv(path, columns):
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame(columns=columns)

signal_cols = ["symbol","weekly_high","breakout_time","green_count","red_time","red_high","status","entry_price","entry_time","current_price"]
trade_cols = ["symbol","entry_time","entry_price","quantity","current_price","pnl_rupees","pnl_percent","status"]

if st.button("🔄 Scan Nifty 100 now", type="primary"):
    st.session_state["do_scan"] = True

if "do_scan" not in st.session_state:
    st.session_state["do_scan"] = False

signals = load_csv(SIGNALS_FILE, signal_cols)
trades = load_csv(TRADES_FILE, trade_cols)

if st.session_state["do_scan"]:
    symbols = get_nifty100_symbols()
    progress = st.progress(0, text="Scanning hourly candles…")
    new_signals = []
    for n, symbol in enumerate(symbols):
        result, last_price = analyze_symbol(symbol, max_green)
        if result:
            new_signals.append(result)
        progress.progress((n + 1) / max(len(symbols), 1), text=f"Scanning {symbol} ({n+1}/{len(symbols)})")
    progress.empty()
    signals = pd.DataFrame(new_signals, columns=signal_cols) if new_signals else pd.DataFrame(columns=signal_cols)
    signals.to_csv(SIGNALS_FILE, index=False)
    # Create paper trades for newly triggered entries only once per symbol + entry time.
    existing_keys = set()
    if not trades.empty and {"symbol","entry_time"}.issubset(trades.columns):
        existing_keys = set(trades["symbol"].astype(str) + "|" + trades["entry_time"].astype(str))
    for _, row in signals.iterrows():
        if row.get("status") == "Entry triggered" and pd.notna(row.get("entry_price")):
            key = str(row["symbol"]) + "|" + str(row["entry_time"])
            if key not in existing_keys:
                qty = int(capital // float(row["entry_price"])) if float(row["entry_price"]) > 0 else 0
                trades = pd.concat([trades, pd.DataFrame([{
                    "symbol": row["symbol"], "entry_time": row["entry_time"],
                    "entry_price": float(row["entry_price"]), "quantity": qty,
                    "current_price": float(row["current_price"]), "pnl_rupees": (float(row["current_price"])-float(row["entry_price"]))*qty,
                    "pnl_percent": ((float(row["current_price"])-float(row["entry_price"]))/float(row["entry_price"]))*100,
                    "status": "OPEN"
                }])], ignore_index=True)
                existing_keys.add(key)
    trades.to_csv(TRADES_FILE, index=False)
    st.session_state["do_scan"] = False
    st.success(f"Scan complete: checked {len(symbols)} symbols.")

# Refresh prices on displayed trades when scan runs; show latest persisted values otherwise.
if not signals.empty:
    st.subheader("🔔 Breakout / Red Candle Signals")
    display = signals.copy()
    for col in ["weekly_high","red_high","entry_price","current_price"]:
        if col in display:
            display[col] = pd.to_numeric(display[col], errors="coerce").round(2)
    st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.info("Abhi saved signals nahi hain. 'Scan Nifty 100 now' dabakar pehla scan chalayen.")

if not trades.empty:
    trades["entry_price"] = pd.to_numeric(trades["entry_price"], errors="coerce")
    trades["current_price"] = pd.to_numeric(trades["current_price"], errors="coerce")
    trades["quantity"] = pd.to_numeric(trades["quantity"], errors="coerce").fillna(0)
    trades["pnl_rupees"] = (trades["current_price"] - trades["entry_price"]) * trades["quantity"]
    trades["pnl_percent"] = (trades["current_price"] - trades["entry_price"]) / trades["entry_price"] * 100
    st.subheader("📒 Paper Trading — Excel jaisi trade sheet")
    st.caption("P&L % = (Current Price − Entry Price) ÷ Entry Price × 100. Current price updates on each scan.")
    show = trades.copy()
    for col in ["entry_price","current_price","pnl_rupees","pnl_percent"]:
        show[col] = pd.to_numeric(show[col], errors="coerce").round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.metric("Open paper trades", int((trades["status"] == "OPEN").sum()))
    st.metric("Unrealized P&L (₹)", f"₹{trades['pnl_rupees'].sum():,.2f}")
    st.download_button("⬇️ Download trade sheet (CSV for Excel)", data=show.to_csv(index=False).encode("utf-8-sig"), file_name="paper_trades.csv", mime="text/csv")
else:
    st.subheader("📒 Paper Trading — Trade Sheet")
    st.write("Abhi koi entry trigger nahi hui.")

st.divider()
st.caption("Strategy implementation note: this is a starter implementation. Verify the weekly-high definition and candle sequencing with historical examples before relying on its signals. Yahoo Finance hourly data is not guaranteed real-time, and scheduled GitHub jobs are not a reliable tick-by-tick execution engine.")
