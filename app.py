import io
import re
import time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="NSE Weekly & 112-Watchlist Scanner", layout="wide")
st.title("⚡ NSE Stocks — Weekly Scanner & 1-Day Watchlist")
st.caption(
    "ऊपर सभी NSE शेयरों को Weekly कैंडल (₹100–₹2500) पर स्कैन करें, और नीचे अपनी सेव की गई 112 शेयरों की वॉचलिस्ट को 1-Day कैंडल पर रन करें।"
)

WATCHLIST_FILE = Path("my_watchlist.txt")

# --- आपकी 112 शेयरों की पूरी सेव्ड वॉचलिस्ट (1 से 112 तक) ---
DEFAULT_112_WATCHLIST = (
    "SPARC.NS, TIPSMUSIC.NS, NESTLEIND.NS, TIMEX.NS, IGIL.NS, "
    "AUGMONT.NS, HBLENGINE.NS, KANOHAR.NS, CRIZAC.NS, DEEPA.NS, "
    "MARICO.NS, IRCTC.NS, ATLANTAELE.NS, EMMVEE.NS, NAM-INDIA.NS, "
    "HINDCOPPER.NS, TRAVELFOOD.NS, CRAMC.NS, DPABHUSHAN.NS, BUILDPRO.NS, "
    "CMPDI.NS, HDFIRE.NS, GOKULAGRO.NS, BEL.NS, OSWALPUMPS.NS, "
    "MAZDOCK.NS, INDRAMEDCO.NS, MANORAMA.NS, THYROCARE.NS, ECLERX.NS, "
    "TRITURBINE.NS, CUPID.NS, TRANSRAILL.NS, INOXINDIA.NS, CEMPRO.NS, "
    "QPOWER.NS, ACE.NS, BANCOINDIA.NS, ANTHEM.NS, RPEL.NS, "
    "GODFRYPHLP.NS, HEXT.NS, KNACK.NS, LUPIN.NS, BLS.NS, "
    "YASHHV.BO, RUBICON.NS, SUDEEPPHRM.NS, RRKABEL.NS, INDIAMART.NS, "
    "LALPATHLAB.NS, MONARCH.NS, SHRINGARMS.NS, BORORENEW.NS, KMCSHIL.NS, "
    "GOLDIAM.NS, SUPRIYA.NS, NEWGEN.NS, HAVELLS.NS, KSB.NS, "
    "MARSONS.NS, SANDUMA.NS, AJAXENGG.NS, INTERARCH.NS, SKIPPER.NS, "
    "TARIL.NS, KESAR.BO, PREMEXPLN.NS, RAILTEL.NS, ADOR.NS, "
    "REFEX.NS, BIKAJI.NS, EPACKPEB.NS, KSHINTL.NS, VESUVIUS.NS, "
    "JYOTICNC.NS, VENUSPIPES.NS, LOTUSDEV.NS, OLECTRA.NS, ANUP.NS, "
    "ELECON.NS, VENUSREM.NS, LASERPOWER.NS, SUNPHARMA.NS, VIJAYA.NS, "
    "SIRCA.NS, AGIIL.NS, RAMCOSYS.NS, VBL.NS, SEAMECLTD.NS, "
    "UNOMINDA.NS, OBSCP.NS, BETA.NS, SAMBHV.NS, ARKADE.NS, "
    "MARKSANS.NS, CNL.NS, TALBROAUTO.NS, TBOTEK.NS, CARYSIL.NS, "
    "JASH.NS, NATCOPHARM.NS, IPCALAB.NS, SARDAEN.NS, DODLA.NS, "
    "DEEPINDS.NS, VAIBHAVGBL.NS, LODHA.NS, GRAVITA.NS, CCL.NS, "
    "JSWINFRA.NS, MILKYMIST.NS"
)

# NSE सर्वर ब्लॉक होने पर काम आने वाली बैकअप लिस्ट
BACKUP_NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "SBIN.NS", "LICI.NS", "ITC.NS", "HINDUNILVR.NS",
    "LT.NS", "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "ADANIENT.NS", "KOTAKBANK.NS", "TITAN.NS", "ONGC.NS", "TATAMOTORS.NS",
    "NTPC.NS", "AXISBANK.NS", "DMART.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "COALINDIA.NS", "JSWSTEEL.NS", "M&M.NS", "POWERGRID.NS", "BAJAJFINSV.NS",
    "ASIANPAINT.NS", "ADANIPORTS.NS", "TATASTEEL.NS", "TRENT.NS", "BEL.NS",
    "HAL.NS", "NESTLEIND.NS", "GRASIM.NS", "TECHM.NS", "HINDALCO.NS",
    "INDIGO.NS", "CIPLA.NS", "DRREDDY.NS", "BPCL.NS", "EICHERMOT.NS",
    "HEROMOTOCO.NS", "TATACONSUM.NS", "BRITANNIA.NS", "APOLLOHOSP.NS", "DIVISLAB.NS",
]


def load_saved_watchlist() -> str:
    if WATCHLIST_FILE.exists():
        saved = WATCHLIST_FILE.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    return DEFAULT_112_WATCHLIST


def reset_watchlist_callback():
    st.session_state.watchlist_input = DEFAULT_112_WATCHLIST
    if WATCHLIST_FILE.exists():
        WATCHLIST_FILE.unlink()


# Session State
if "weekly_df" not in st.session_state:
    st.session_state.weekly_df = None
if "watchlist_df" not in st.session_state:
    st.session_state.watchlist_df = None
if "watchlist_failed" not in st.session_state:
    st.session_state.watchlist_failed = []
if "watchlist_input" not in st.session_state:
    st.session_state.watchlist_input = load_saved_watchlist()


# --- 1. NSE से शेयरों की लिस्ट डाउनलोड करना ---
@st.cache_data(ttl=86400)
def get_nse_symbols(category: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    if "Nifty 100" in category:
        url = "https://archives.nseindia.com/content/indices/ind_nifty100list.csv"
    elif "Nifty 500" in category:
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    else:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        df.columns = df.columns.str.strip()

        if "SERIES" in df.columns:
            df = df[df["SERIES"].astype(str).str.strip() == "EQ"]

        col_name = "SYMBOL" if "SYMBOL" in df.columns else "Symbol"
        symbols = [f"{str(s).strip()}.NS" for s in df[col_name].dropna().tolist()]
        return symbols
    except Exception:
        return []


# --- 2. Woodies Pivot & CCI (14) कैलकुलेशन (सिर्फ़ 1st Bar Breakout के साथ) ---
def analyze_woodies_cci(
    ticker: str,
    df: pd.DataFrame,
    timeframe_label: str = "Weekly",
    min_p: float = None,
    max_p: float = None,
):
    try:
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            if ticker not in df.columns.get_level_values(0):
                return None
            sub_df = df[ticker][["High", "Low", "Close"]].dropna()
        else:
            sub_df = df[["High", "Low", "Close"]].dropna()

        if len(sub_df) < 16:
            return None

        close = float(sub_df["Clos
