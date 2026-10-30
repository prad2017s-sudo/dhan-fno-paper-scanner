import io
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")

st.set_page_config(
    page_title="NSE Monthly Low + Weekly High + 1-Hour Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1200px;}
    h1 {font-size: clamp(1.45rem, 4vw, 2.15rem) !important; line-height: 1.35 !important;}
    .stButton button, .stDownloadButton button {width: 100%; min-height: 2.8rem; font-weight: 600;}
    div[data-testid="stMetricValue"] {font-size: clamp(1rem, 3.3vw, 1.7rem);}
    div[data-testid="stAlert"] {line-height: 1.6;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("NSE Monthly Low + Weekly High + 1-Hour Screener")
st.caption("NSE cash market | Previous-month low test | Completed weekly high | 1-hour confirmation")

st.info(
    """
    **Scanner rules**
    1. Take the LOW of the previous fully completed calendar month (not the current month's low).
    2. Consider only fully completed weekly candles belonging to the current month. A weekly candle qualifies when its Low is at or below 1% above the previous month's Low. This includes a move below or a touch of that monthly Low.
    3. Mark the qualifying weekly candle's High. The most recent qualifying completed weekly candle is used.
    4. On the 1-hour chart, a green candle must close above that weekly High from below.
    5. Then 1-3 additional green hourly candles, followed by a red candle closing above the weekly High.
    6. The next hourly candle must break the red candle's High.
    7. Assumed entry is the red candle's High; SL is 3% and target is 6%.
    8. Only completed hourly and weekly candles are used. One signal per symbol per month.

    **Data note:** Yahoo Finance may delay or omit data. The scan is a screening/backtest estimate, not a live execution guarantee.
    """
)

EQUITY_URLS = [
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
]
FO_URLS = [
    "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv",
    "https://archives.nseindia.com/content/fo/fo_mktlots.csv",
]
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}


@st.cache_data(ttl=86400, show_spinner=False)
def get_symbols():
    equity = None
    for url in EQUITY_URLS:
        try:
            response = requests.get(url, headers=HEADERS, timeout=25)
            response.raise_for_status()
            equity = pd.read_csv(
                io.StringIO(response.content.decode("utf-8-sig", errors="replace"))
            )
            if not equity.empty:
                break
        except Exception:
            continue

    if equity is None or equity.empty:
        raise RuntimeError("NSE equity list download failed.")

    equity.columns = [str(c).strip().upper() for c in equity.columns]
    if "SYMBOL" not in equity.columns:
        raise RuntimeError("NSE list is missing the SYMBOL column.")

    if "SERIES" in equity.columns:
        equity = equity[
            equity["SERIES"].astype(str).str.strip().str.upper().eq("EQ")
        ]
    cash_symbols = set(
        equity["SYMBOL"].dropna().astype(str).str.strip().str.upper()
    )

    fo = None
    for url in FO_URLS:
        try:
            response = requests.get(url, headers=HEADERS, timeout=25)
            response.raise_for_status()
            fo = pd.read_csv(
                io.StringIO(response.content.decode("utf-8-sig", errors="replace"))
            )
            if not fo.empty:
                break
        except Exception:
            continue

    if fo is None or fo.empty:
        raise RuntimeError(
            "F&O list download failed; scan stopped to avoid including F&O stocks."
        )

    fo.columns = [str(c).strip().upper() for c in fo.columns]
    fo_symbols = set()
    for column in ("SYMBOL", "UNDERLYING", "UNDERLYING_SYMBOL"):
        if column in fo.columns:
            fo_symbols.update(
                fo[column].dropna().astype(str).str.strip().str.upper()
            )

    if not fo_symbols:
        raise RuntimeError("Could not identify the symbol column in the F&O list.")

    return sorted(cash_symbols - fo_symbols)


@st.cache_data(ttl=900, show_spinner=False)
def download_hourly(symbol):
    try:
        data = yf.Ticker(f"{symbol}.NS").history(
            period="60d",
            interval="1h",
            auto_adjust=False,
            actions=False,
            prepost=False,
        )
        if data is None or data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns]

        required = ["Open", "High", "Low", "Close"]
        if any(column not in data.columns for column in required):
            return pd.DataFrame()

        data[required] = data[required].apply(pd.to_numeric, errors="coerce")
        data = data.dropna(subset=required).sort_index()
        return data[~data.index.duplicated(keep="last")]
    except Exception:
        return pd.DataFrame()



@st.cache_data(ttl=3600, show_spinner=False)
def download_daily(symbol):
    try:
        data = yf.Ticker(f"{symbol}.NS").history(
            period="2y", interval="1d", auto_adjust=False, actions=False, prepost=False
        )
        if data is None or data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns]
        required = ["Low"]
        if any(column not in data.columns for column in required):
            return pd.DataFrame()
        data[required] = data[required].apply(pd.to_numeric, errors="coerce")
        data = data.dropna(subset=required).sort_index()
        return data[~data.index.duplicated(keep="last")]
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def download_weekly(symbol):
    try:
        data = yf.Ticker(f"{symbol}.NS").history(
            period="2y", interval="1wk", auto_adjust=False, actions=False, prepost=False
        )
        if data is None or data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns]
        required = ["High", "Low", "Close"]
        if any(column not in data.columns for column in required):
            return pd.DataFrame()
        data[required] = data[required].apply(pd.to_numeric, errors="coerce")
        data = data.dropna(subset=required).sort_index()
        return data[~data.index.duplicated(keep="last")]
    except Exception:
        return pd.DataFrame()


def localize_market_index(data):
    idx = pd.DatetimeIndex(pd.to_datetime(data.index))
    if idx.tz is None:
        idx = idx.tz_localize("Asia/Kolkata")
    else:
        idx = idx.tz_convert("Asia/Kolkata")
    return idx


def get_previous_month_low_and_weekly_high(symbol, now):
    daily = download_daily(symbol)
    weekly = download_weekly(symbol)
    if daily.empty or weekly.empty:
        return None

    daily_idx = localize_market_index(daily)
    month_start = pd.Timestamp(now.year, now.month, 1, tz="Asia/Kolkata")
    prev_month_end = month_start - pd.Timedelta(nanoseconds=1)
    prev_month_start = pd.Timestamp(
        prev_month_end.year, prev_month_end.month, 1, tz="Asia/Kolkata"
    )
    prev_mask = (daily_idx >= prev_month_start) & (daily_idx <= prev_month_end)
    prev_month = daily.loc[prev_mask]
    if prev_month.empty:
        return None
    previous_month_low = float(prev_month["Low"].min())

    weekly_idx = localize_market_index(weekly)
    # Yahoo weekly bars are normally stamped at the start of the week (Monday).
    # A weekly candle is complete after Friday's NSE close (15:30 IST).
    weekly_end = weekly_idx.normalize() + pd.Timedelta(days=4, hours=15, minutes=30)
    completed_mask = (weekly_idx >= month_start) & (weekly_end <= pd.Timestamp(now))
    completed_weekly = weekly.loc[completed_mask].copy()
    if completed_weekly.empty:
        return None

    qualifying = completed_weekly[
        completed_weekly["Low"].astype(float) <= previous_month_low * 1.01
    ]
    if qualifying.empty:
        return None

    chosen = qualifying.iloc[-1]
    chosen_date = qualifying.index[-1]
    return previous_month_low, float(chosen["High"]), str(chosen_date)

def remove_incomplete_hourly_candle(data, now):
    """Keep completed hourly bars; discard only the currently forming bar."""
    if data.empty:
        return data

    idx = pd.DatetimeIndex(pd.to_datetime(data.index))
    if idx.tz is None:
        # Yahoo Finance normally returns timezone-aware NSE timestamps.
        # If it does not, interpret them as India time.
        idx = idx.tz_localize("Asia/Kolkata")
    else:
        idx = idx.tz_convert("Asia/Kolkata")

    completed = (idx + pd.Timedelta(hours=1)) <= pd.Timestamp(now)
    result = data.loc[completed].copy()
    result.index = idx[completed]
    return result


def scan_symbol(symbol, investment_per_stock):
    now = datetime.now(IST)
    levels = get_previous_month_low_and_weekly_high(symbol, now)
    if levels is None:
        return None
    previous_month_low, weekly_high, weekly_candle_date = levels

    data = download_hourly(symbol)
    if data.empty or len(data) < 10:
        return None
    data = remove_incomplete_hourly_candle(data, now)
    if len(data) < 10:
        return None

    latest_price = float(data["Close"].iloc[-1])

    dates = pd.DatetimeIndex(data.index)
    month_start = pd.Timestamp(now.year, now.month, 1, tz="Asia/Kolkata")
    current_month_positions = [i for i, date in enumerate(dates) if date >= month_start]
    if len(current_month_positions) < 4:
        return None

    # First green hourly close above the selected completed weekly candle's High.
    breakout_i = None
    for i in current_month_positions:
        if i == 0:
            continue
        candle = data.iloc[i]
        previous = data.iloc[i - 1]
        if (
            float(candle["Close"]) > float(candle["Open"])
            and float(candle["Close"]) > weekly_high
            and float(previous["Close"]) <= weekly_high
        ):
            breakout_i = i
            break
    if breakout_i is None:
        return None

    green_count = 0
    red_i = None
    for j in range(breakout_i + 1, len(data)):
        candle = data.iloc[j]
        open_price = float(candle["Open"])
        close_price = float(candle["Close"])
        if close_price > open_price:
            green_count += 1
            if green_count > 3:
                return None
            continue
        if close_price < open_price:
            if 1 <= green_count <= 3 and close_price > weekly_high:
                red_i = j
            break
        break
    if red_i is None:
        return None

    trigger_i = red_i + 1
    if trigger_i >= len(data):
        return None
    red_candle = data.iloc[red_i]
    trigger_candle = data.iloc[trigger_i]
    red_high = float(red_candle["High"])
    trigger_high = float(trigger_candle["High"])
    if trigger_high <= red_high:
        return None

    # Entry assumed at the red candle's High after the following candle breaks it.
    entry_price = red_high
    if entry_price > investment_per_stock:
        return None  # At least one whole share must fit within the per-stock budget.
    quantity = int(investment_per_stock // entry_price)
    actual_investment = quantity * entry_price
    stop_loss = entry_price * 0.97
    target_price = entry_price * 1.06
    estimated_sl_loss = quantity * (entry_price - stop_loss)
    estimated_target_profit = quantity * (target_price - entry_price)

    outcome = "Pending"
    outcome_date = ""
    outcome_price = float("nan")
    for k in range(trigger_i + 1, len(data)):
        later = data.iloc[k]
        hit_sl = float(later["Low"]) <= stop_loss
        hit_target = float(later["High"]) >= target_price
        if hit_sl and hit_target:
            outcome = "SL hit (both levels same candle; counted as SL)"
            outcome_date = str(dates[k])
            outcome_price = stop_loss
            break
        if hit_sl:
            outcome = "SL hit"
            outcome_date = str(dates[k])
            outcome_price = stop_loss
            break
        if hit_target:
            outcome = "6% Target hit"
            outcome_date = str(dates[k])
            outcome_price = target_price
            break

    one_year_low = float(data["Low"].tail(252 * 6).min())
    percent_above_low = ((latest_price / one_year_low) - 1.0) * 100.0 if one_year_low > 0 else float("nan")
    close_series = data["Close"].astype(float)
    ma20 = float(close_series.tail(20).mean()) if len(close_series) >= 20 else float("nan")
    ma50 = float(close_series.tail(50).mean()) if len(close_series) >= 50 else float("nan")
    rising_trend = bool(latest_price > ma20 and ma20 > ma50) if pd.notna(ma20) and pd.notna(ma50) else False

    return {
        "Symbol": symbol,
        "Rising Trend": "Yes" if rising_trend else "No",
        "Latest 1H Close (INR)": round(latest_price, 2),
        "Previous Month Low (INR)": round(previous_month_low, 2),
        "Qualifying Weekly Candle Date": weekly_candle_date,
        "Weekly Candle High (INR)": round(weekly_high, 2),
        "1H Breakout Date-Time": str(dates[breakout_i]),
        "Extra Green 1H Candles": green_count,
        "Red Candle Date-Time": str(dates[red_i]),
        "Red Candle Close (INR)": round(float(red_candle["Close"]), 2),
        "Red Candle High (INR)": round(red_high, 2),
        "High-Break Candle Date-Time": str(dates[trigger_i]),
        "Assumed Entry (INR)": round(entry_price, 2),
        "Shares with Budget": quantity,
        "Actual Investment (INR)": round(actual_investment, 2),
        "Stop-Loss -3% (INR)": round(stop_loss, 2),
        "Estimated SL Loss (INR)": round(estimated_sl_loss, 2),
        "Target +6% (INR)": round(target_price, 2),
        "Estimated Target Profit (INR)": round(estimated_target_profit, 2),
        "Trade Result": outcome,
        "Result Date-Time": outcome_date,
        "Exit Level (INR)": round(outcome_price, 2) if pd.notna(outcome_price) else "",
        "52-Week Low Estimate (INR)": round(one_year_low, 2),
        "% Above 52-Week Low Estimate": round(percent_above_low, 2),
    }


with st.sidebar:
    st.header("Scan Settings")
    investment_per_stock = st.number_input(
        "Investment per stock (INR)", min_value=500.0, value=5000.0, step=500.0
    )
    scan_size = st.selectbox(
        "Stocks to Scan",
        ["All eligible cash stocks", "First 100 (test)", "First 250"],
    )
    st.caption(
        "Whole-share quantity is calculated from the per-stock budget. Stocks priced above the budget are skipped."
    )

metric1, metric2, metric3 = st.columns(3)
metric1.metric("Timeframe", "1 Hour")
metric2.metric("Budget / Stock", f"₹{investment_per_stock:,.0f}")
metric3.metric("SL / Target", "3% / 6%")

if st.button("Scan Stocks Now", type="primary", use_container_width=True):
    try:
        with st.spinner("Loading NSE symbol lists..."):
            symbols = get_symbols()

        if scan_size.startswith("First 100"):
            symbols = symbols[:100]
        elif scan_size.startswith("First 250"):
            symbols = symbols[:250]

        st.write(f"**Stocks to scan:** {len(symbols)}")
        results = []
        failures = 0
        progress = st.progress(0)
        status = st.empty()

        for number, symbol in enumerate(symbols, start=1):
            status.write(f"Checking **{symbol}** ({number}/{len(symbols)})")
            try:
                match = scan_symbol(symbol, investment_per_stock)
                if match:
                    results.append(match)
            except Exception:
                failures += 1
            progress.progress(number / max(1, len(symbols)))

        status.empty()
        progress.empty()
        result_df = pd.DataFrame(results)

        if not result_df.empty:
            result_df["Rising Trend Sort"] = result_df["Rising Trend"].eq("Yes").astype(int)
            result_df = result_df.sort_values(
                ["Rising Trend Sort", "% Above 52-Week Low Estimate", "Symbol"],
                ascending=[False, True, True],
            ).drop(columns=["Rising Trend Sort"]).reset_index(drop=True)

            st.success(f"Scan complete: {len(result_df)} matching stock(s).")
            st.dataframe(result_df, use_container_width=True, hide_index=True)

            st.download_button(
                "Download Results CSV",
                data=result_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="nse_monthly_low_weekly_high_1hour.csv",
                mime="text/csv",
                use_container_width=True,
            )

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                result_df.to_excel(writer, index=False, sheet_name="1H Signals")

            st.download_button(
                "Download Results Excel",
                data=excel_buffer.getvalue(),
                file_name="nse_monthly_low_weekly_high_1hour.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.warning("No stocks matched all the 1-hour rules in this scan.")

        if failures:
            st.caption(
                f"{failures} symbol(s) could not be checked due to data/network errors."
            )

    except Exception as error:
        st.error(f"Scan failed: {error}")
else:
    st.write("Set the investment per stock in the sidebar and press Scan Stocks Now.")
    st.caption("Results will appear here after scanning.")

with st.expander("Scanner Rules"):
    st.markdown(
        """
        1. Use the previous fully completed calendar month's Low; do not use the current month's Low.
        2. Use only fully completed weekly candles that start in the current month.
        3. A weekly candle qualifies when its Low is at or below 1% above the previous month's Low.
        4. The most recent qualifying weekly candle's High becomes the 1-hour breakout level.
        5. A green 1-hour candle must close above that weekly High from below.
        6. Then 1-3 additional green hourly candles, followed by a red candle closing above the weekly High.
        7. The next hourly candle must break the red candle's High.
        8. Assumed entry is the red candle's High; SL is 3% below entry and target is 6% above entry.
        9. Later completed hourly candles are checked; if SL and target occur in the same candle, count SL first.
        10. If neither level is reached in available data, the result is Pending.
        11. Only one signal per symbol per month. Incomplete weekly and hourly candles are ignored.
        """
    )

st.caption(
    "Educational screening tool only — not a buy/sell recommendation. "
    "Intraday data may be delayed, incomplete, or unavailable."
)
