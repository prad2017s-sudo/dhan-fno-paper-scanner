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

        close = float(sub_df["Close"].iloc[-1])

        if min_p is not None and close < min_p:
            return None
        if max_p is not None and close > max_p:
            return None

        high = float(sub_df["High"].iloc[-1])
        low = float(sub_df["Low"].iloc[-1])

        # Woodie's Pivot
        pp = (high + low + (2 * close)) / 4
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high

        # Woodies CCI (14) - HLC3 (TradingView / Dhan Standard)
        tp = (sub_df["High"] + sub_df["Low"] + sub_df["Close"]) / 3
        sma_tp = tp.rolling(window=14).mean()
        mean_dev = tp.rolling(window=14).apply(
            lambda x: np.mean(np.abs(x - x.mean())), raw=True
        )
        cci = (tp - sma_tp) / (0.015 * mean_dev.replace(0, np.nan))

        curr_cci = cci.iloc[-1]
        prev_cci = cci.iloc[-2]

        if pd.isna(curr_cci) or pd.isna(prev_cci):
            return None

        curr_cci = float(curr_cci)
        prev_cci = float(prev_cci)

        # गिनें कि 0-लाइन के ऊपर लगातार कितने बार (bars) बने हैं
        bars_above_zero = 0
        for val in reversed(cci.dropna().tolist()):
            if val > 0:
                bars_above_zero += 1
            else:
                break

        # सिर्फ़ 1st बार पर सिग्नल (पिछला बार <= 0 और वर्तमान बार > 0)
        first_bar_cross = (bars_above_zero == 1) and (prev_cci <= 0)
        above_zero = curr_cci > 0

        if first_bar_cross:
            status = "🔥 1st Bar Breakout (0-Line Cross)"
        elif above_zero:
            status = f"📈 Bar #{bars_above_zero} Above 0-Line"
        else:
            status = "🔻 Below 0-Line (Bearish)"

        curr_col = "This Week CCI" if timeframe_label == "Weekly" else "Today CCI"
        prev_col = "Last Week CCI" if timeframe_label == "Weekly" else "Yesterday CCI"
        prefix = "Weekly" if timeframe_label == "Weekly" else "Daily"
        clean_name = re.sub(r"\.(NS|BO)$", "", ticker)

        return {
            "Symbol": clean_name,
            "Close (₹)": round(close, 2),
            "Status": status,
            "Bars Above 0": bars_above_zero,
            curr_col: round(curr_cci, 2),
            prev_col: round(prev_cci, 2),
            f"{prefix} Pivot (PP)": round(pp, 2),
            f"{prefix} R1": round(r1, 2),
            f"{prefix} S1": round(s1, 2),
            "Fresh_Cross": first_bar_cross,
            "Above_Zero": above_zero,
        }
    except Exception:
        return None


# ==============================================================================
# भाग 1: All NSE Weekly Scanner (साइडबार से कंट्रोल)
# ==============================================================================
st.sidebar.header("📊 Weekly स्कैनिंग सेटिंग्स")

scan_limit = st.sidebar.selectbox(
    "कौन-से शेयर्स स्कैन करने हैं?",
    [
        "सभी NSE शेयर्स (2000+ EQ Stocks)",
        "Nifty 500 शेयर्स",
        "Nifty 100 शेयर्स (फ़ास्ट टेस्ट)",
    ],
    index=0,
)

st.sidebar.subheader("💰 प्राइस फ़िल्टर (₹)")
col1, col2 = st.sidebar.columns(2)
min_price = col1.number_input("कम से कम (Min ₹)", min_value=1.0, value=100.0, step=10.0)
max_price = col2.number_input("ज़्यादा से ज़्यादा (Max ₹)", min_value=10.0, value=2500.0, step=50.0)

symbols_list = get_nse_symbols(scan_limit)
if not symbols_list:
    st.sidebar.warning("NSE से लिस्ट लोड नहीं हो पाई, बैकअप (Nifty 50) का उपयोग हो रहा है।")
    symbols_list = BACKUP_NIFTY_50

st.sidebar.info(f"स्कैन होने वाले कुल शेयर्स: **{len(symbols_list)}**\n\nटाइमफ्रेम: **Weekly (1W)**")

weekly_scan_type = st.sidebar.radio(
    "कंडीशन चुनें (Weekly Candle):",
    [
        "🔥 इस हफ्ते 1st Bar 0-Line क्रॉस करने वाले (Weekly Fresh Breakout)",
        "📈 वर्तमान में Weekly 0-Line के ऊपर (Weekly Bullish)",
    ],
)

start_weekly_scan = st.sidebar.button("🚀 Weekly स्कैन शुरू करें", type="primary")

st.subheader("1️⃣ All NSE Weekly Scanner (₹100 – ₹2500)")

if start_weekly_scan:
    if min_price > max_price:
        st.error("⚠️ 'Min Price' की वैल्यू 'Max Price' से ज़्यादा नहीं हो सकती।")
    else:
        total = len(symbols_list)
        batch_size = 50
        progress_bar = st.progress(0)
        status_box = st.empty()
        results = []

        for i in range(0, total, batch_size):
            batch = symbols_list[i : i + batch_size]
            done = min(i + len(batch), total)
            progress_bar.progress(done / total)
            status_box.text(
                f"Weekly डेटा स्कैन हो रहा है: {done} / {total} शेयर्स... (मिले: {len(results)})"
            )

            try:
                batch_data = yf.download(
                    batch,
                    period="1y",
                    interval="1wk",
                    group_by="ticker",
                    auto_adjust=False,
                    progress=False,
                    threads=True,
                )

                for sym in batch:
                    res = analyze_woodies_cci(
                        sym, batch_data, timeframe_label="Weekly", min_p=min_price, max_p=max_price
                    )
                    if res:
                        if "Fresh Breakout" in weekly_scan_type and res["Fresh_Cross"]:
                            results.append(res)
                        elif "Bullish" in weekly_scan_type and res["Above_Zero"]:
                            results.append(res)

                time.sleep(0.1)
            except Exception:
                continue

        progress_bar.empty()
        status_box.empty()

        if results:
            st.session_state.weekly_df = (
                pd.DataFrame(results)
                .drop(columns=["Fresh_Cross", "Above_Zero", "Status"])
                .sort_values(by="This Week CCI", ascending=False)
                .reset_index(drop=True)
            )
        else:
            st.session_state.weekly_df = pd.DataFrame()

if st.session_state.weekly_df is not None:
    if not st.session_state.weekly_df.empty:
        df_w = st.session_state.weekly_df
        st.success(
            f"🎉 Weekly स्कैन पूरा! ₹{min_price:.0f}–₹{max_price:.0f} रेंज में कुल **{len(df_w)}** शेयर मिले।"
        )
        st.dataframe(df_w, width="stretch")

        csv_w = df_w.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Weekly लिस्ट डाउनलोड करें (CSV)",
            csv_w,
            "nse_weekly_100_to_2500_0line.csv",
            "text/csv",
        )
    else:
        st.warning("तय कंडीशन और प्राइस रेंज में कोई Weekly शेयर नहीं मिला।")
else:
    st.info("👈 साइडबार से **'Weekly स्कैन शुरू करें'** बटन दबाएं, या नीचे अपनी 112 शेयरों की वॉचलिस्ट को 1-Day कैंडल पर रन करें।")
    # ==============================================================================
# भाग 2: मेरी सेव्ड वॉचलिस्ट स्कैनर (112 Shares - 1-Day Candle)
# ==============================================================================
st.divider()
st.subheader("2️⃣ मेरी सेव्ड वॉचलिस्ट स्कैनर (1-Day Candle | 112 Shares)")
st.caption(
    "आपकी 112 शेयरों की लिस्ट पहले से सेव है। चाहें तो इसमें और शेयर जोड़कर '💾 वॉचलिस्ट सेव करें' दबाएं।"
)

wl_col1, wl_col2 = st.columns([2, 1])

with wl_col1:
    watchlist_text = st.text_area(
        "वॉचलिस्ट (कॉमा, स्पेस या नई लाइन से अलग):",
        key="watchlist_input",
        height=180,
    )

with wl_col2:
    daily_filter = st.radio(
        "1-Day फ़िल्टर चुनें:",
        [
            "🔥 सिर्फ आज 1st Bar Breakout (0-Line Cross)",
            "📈 आज 0-Line के ऊपर चल रहे (Bullish)",
            "📊 सभी वॉचलिस्ट शेयर्स का स्टेटस दिखाएं (All)",
        ],
        index=0,
    )
    apply_price_on_wl = st.checkbox(
        f"वॉचलिस्ट पर भी ₹{min_price:.0f}–₹{max_price:.0f} प्राइस फ़िल्टर लगाएं",
        value=False,
    )

btn_c1, btn_c2, btn_c3 = st.columns([2, 1, 1])
run_watchlist_btn = btn_c1.button("🔎 1-Day Candle पर वॉचलिस्ट रन करें", type="primary")
save_wl_btn = btn_c2.button("💾 वॉचलिस्ट सेव करें")
reset_wl_btn = btn_c3.button(
    "🔄 112 डिफ़ॉल्ट रीलोड करें",
    on_click=reset_watchlist_callback,
)

if save_wl_btn:
    WATCHLIST_FILE.write_text(watchlist_text.strip(), encoding="utf-8")
    st.success("✅ आपकी वॉचलिस्ट `my_watchlist.txt` में सेव हो गई!")

if run_watchlist_btn:
    if apply_price_on_wl and min_price > max_price:
        st.error("⚠️ 'Min Price' की वैल्यू 'Max Price' से ज़्यादा नहीं हो सकती।")
    else:
        raw_tokens = re.split(r"[,\s\n;]+", watchlist_text.strip())
        clean_symbols = []
        for tok in raw_tokens:
            t = tok.strip().upper()
            if not t:
                continue
            if not (t.endswith(".NS") or t.endswith(".BO")):
                t = f"{t}.NS"
            if t not in clean_symbols:
                clean_symbols.append(t)

        if not clean_symbols:
            st.warning("⚠️ कृपया वॉचलिस्ट में कम से कम एक शेयर का नाम डालें।")
        else:
            total_wl = len(clean_symbols)
            batch_size = 50
            progress_bar = st.progress(0)
            status_box = st.empty()
            wl_results = []
            wl_failed = []

            for i in range(0, total_wl, batch_size):
                batch = clean_symbols[i : i + batch_size]
                done = min(i + len(batch), total_wl)
                progress_bar.progress(done / total_wl)
                status_box.text(
                    f"1-Day वॉचलिस्ट स्कैन हो रही है: {done} / {total_wl} शेयर्स..."
                )

                try:
                    batch_data = yf.download(
                        batch,
                        period="6mo",
                        interval="1d",
                        group_by="ticker",
                        auto_adjust=False,
                        progress=False,
                        threads=True,
                    )

                    for sym in batch:
                        res = analyze_woodies_cci(
                            sym,
                            batch_data,
                            timeframe_label="Daily",
                            min_p=None,
                            max_p=None,
                        )
                        if res is None:
                            wl_failed.append(sym)
                            continue

                        if apply_price_on_wl:
                            if not (min_price <= res["Close (₹)"] <= max_price):
                                continue

                        if "1st Bar Breakout" in daily_filter and res["Fresh_Cross"]:
                            wl_results.append(res)
                        elif "Bullish" in daily_filter and res["Above_Zero"]:
                            wl_results.append(res)
                        elif "All" in daily_filter:
                            wl_results.append(res)

                    time.sleep(0.1)
                except Exception:
                    wl_failed.extend(batch)
                    continue

            progress_bar.empty()
            status_box.empty()
            st.session_state.watchlist_failed = wl_failed

            if wl_results:
                st.session_state.watchlist_df = (
                    pd.DataFrame(wl_results)
                    .drop(columns=["Fresh_Cross", "Above_Zero"])
                    .sort_values(by="Today CCI", ascending=False)
                    .reset_index(drop=True)
                )
            else:
                st.session_state.watchlist_df = pd.DataFrame()

if st.session_state.watchlist_df is not None:
    if not st.session_state.watchlist_df.empty:
        df_wl = st.session_state.watchlist_df
        st.success(f"🎉 1-Day वॉचलिस्ट स्कैन पूरा! कुल **{len(df_wl)}** शेयर्स मिले।")
        st.dataframe(df_wl, width="stretch")

        csv_wl = df_wl.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 वॉचलिस्ट रिज़ल्ट डाउनलोड करें (CSV)",
            csv_wl,
            "watchlist_1d_woodies_cci.csv",
            "text/csv",
        )
    else:
        st.warning("तय 1-Day फ़िल्टर में वॉचलिस्ट का कोई शेयर नहीं मिला।")

if st.session_state.watchlist_failed:
    with st.expander(
        f"⚠️ {len(st.session_state.watchlist_failed)} शेयर्स का डेटा नहीं मिल पाया"
    ):
        st.write(", ".join(st.session_state.watchlist_failed))
