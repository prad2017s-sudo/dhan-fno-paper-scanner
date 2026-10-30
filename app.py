import io
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")

st.set_page_config(
    page_title="NSE 1-Hour Monthly High Breakout Screener",
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

st.title("NSE 1-Hour Monthly High Breakout Screener")
st.caption("NSE cash market | 1-hour candles | Monthly high breakout | Red-candle confirmation")

st.info(
    """
    **Scanner rules**
    1. The first green 1-hour candle of the current month must close above the previous completed month's High, with the previous candle closing at or below that High.
    2. After the breakout candle, exactly 1, 2, or 3 additional green 1-hour candles must form.
    3. The next candle must be red and its Close must remain above the previous month's High.
    4. The immediately following candle must break the red candle's High (its High must be greater than the red candle's High).
    5. Only one signal per symbol per month. The currently forming 1-hour candle is ignored.

    **Important:** Yahoo Finance generally provides only a limited recent history for 1-hour data. The scanner needs enough hourly data to include the previous month's High.
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


def scan_symbol(symbol, minimum_price, maximum_price):
    data = download_hourly(symbol)
    if data.empty or len(data) < 10:
        return None

    now = datetime.now(IST)
    data = remove_incomplete_hourly_candle(data, now)
    if len(data) < 10:
        return None

    latest_price = float(data["Close"].iloc[-1])
    if not minimum_price <= latest_price <= maximum_price:
        return None

    dates = pd.DatetimeIndex(data.index)
    month_start = pd.Timestamp(now.year, now.month, 1, tz="Asia/Kolkata")
    previous_month_end = month_start - pd.Timedelta(nanoseconds=1)
    previous_month_start = pd.Timestamp(
        previous_month_end.year, previous_month_end.month, 1, tz="Asia/Kolkata"
    )

    previous_month_mask = (
        (dates >= previous_month_start) & (dates <= previous_month_end)
    )
    previous_month = data.loc[previous_month_mask]
    if previous_month.empty:
        return None

    previous_month_high = float(previous_month["High"].max())

    current_month_positions = [
        i for i, date in enumerate(dates)
        if date >= month_start
    ]
    if len(current_month_positions) < 4:
        return None

    # Find only the first green hourly breakout candle of this month.
    breakout_i = None
    for i in current_month_positions:
        if i == 0:
            continue
        candle = data.iloc[i]
        previous = data.iloc[i - 1]
        if (
            float(candle["Close"]) > float(candle["Open"])
            and float(candle["Close"]) > previous_month_high
            and float(previous["Close"]) <= previous_month_high
        ):
            breakout_i = i
            break

    if breakout_i is None:
        return None

    green_count = 0
    red_i = None

    # After breakout: 1-3 extra green candles, then a red candle.
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
            if 1 <= green_count <= 3 and close_price > previous_month_high:
                red_i = j
            break

        # A doji interrupts the pattern.
        break

    if red_i is None:
        return None

    # The candle immediately after the red candle must break its High.
    trigger_i = red_i + 1
    if trigger_i >= len(data):
        return None

    red_candle = data.iloc[red_i]
    trigger_candle = data.iloc[trigger_i]
    red_high = float(red_candle["High"])
    trigger_high = float(trigger_candle["High"])

    if trigger_high <= red_high:
        return None

    # Assumed entry is the red candle's High, once the next candle breaks it.
    # SL is 3% below entry and target is 10% above entry.
    entry_price = red_high
    stop_loss = entry_price * 0.97
    target_price = entry_price * 1.10

    # Check only candles AFTER the breakout-trigger candle.
    outcome = "Pending"
    outcome_date = ""
    outcome_price = float("nan")

    for k in range(trigger_i + 1, len(data)):
        later = data.iloc[k]
        hit_sl = float(later["Low"]) <= stop_loss
        hit_target = float(later["High"]) >= target_price

        # If both levels occur in one hourly candle, count SL first:
        # OHLC data cannot show which level was touched first.
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
            outcome = "10% Target hit"
            outcome_date = str(dates[k])
            outcome_price = target_price
            break

    one_year_low = float(data["Low"].tail(252 * 6).min())
    percent_above_low = (
        ((latest_price / one_year_low) - 1.0) * 100.0
        if one_year_low > 0 else float("nan")
    )

    close_series = data["Close"].astype(float)
    ma20 = float(close_series.tail(20).mean()) if len(close_series) >= 20 else float("nan")
    ma50 = float(close_series.tail(50).mean()) if len(close_series) >= 50 else float("nan")
    rising_trend = (
        bool(latest_price > ma20 and ma20 > ma50)
        if pd.notna(ma20) and pd.notna(ma50) else False
    )

    return {
        "Symbol": symbol,
        "Rising Trend": "Yes" if rising_trend else "No",
        "Latest 1H Close (INR)": round(latest_price, 2),
        "Previous Month High (INR)": round(previous_month_high, 2),
        "Breakout Date-Time": str(dates[breakout_i]),
        "Extra Green Candles": green_count,
        "Red Candle Date-Time": str(dates[red_i]),
        "Red Candle Close (INR)": round(float(red_candle["Close"]), 2),
        "Red Candle High (INR)": round(red_high, 2),
        "High-Break Candle Date-Time": str(dates[trigger_i]),
        "High-Break Candle High (INR)": round(trigger_high, 2),
        "Assumed Entry (INR)": round(entry_price, 2),
        "Stop-Loss -3% (INR)": round(stop_loss, 2),
        "Target +10% (INR)": round(target_price, 2),
        "Trade Result": outcome,
        "Result Date-Time": outcome_date,
        "Exit Level (INR)": round(outcome_price, 2) if pd.notna(outcome_price) else "",
        "52-Week Low Estimate (INR)": round(one_year_low, 2),
        "% Above 52-Week Low Estimate": round(percent_above_low, 2),
    }


with st.sidebar:
    st.header("Scan Settings")
    min_price = st.number_input(
        "Minimum Price (INR)", min_value=0.0, value=100.0, step=10.0
    )
    max_price = st.number_input(
        "Maximum Price (INR)", min_value=1.0, value=5000.0, step=100.0
    )
    scan_size = st.selectbox(
        "Stocks to Scan",
        ["All eligible cash stocks", "First 100 (test)", "First 250"],
    )
    st.caption(
        "1-hour historical data is limited by the data provider. Full scan may take several minutes."
    )

if min_price > max_price:
    st.error("Minimum price must not exceed maximum price.")
    st.stop()

metric1, metric2, metric3 = st.columns(3)
metric1.metric("Timeframe", "1 Hour")
metric2.metric("Price Range", f"INR {min_price:g} - {max_price:g}")
metric3.metric("Market", "NSE Cash (F&O excluded)")

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
                match = scan_symbol(symbol, min_price, max_price)
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
                file_name="nse_1hour_monthly_high_breakout.csv",
                mime="text/csv",
                use_container_width=True,
            )

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                result_df.to_excel(writer, index=False, sheet_name="1H Signals")

            st.download_button(
                "Download Results Excel",
                data=excel_buffer.getvalue(),
                file_name="nse_1hour_monthly_high_breakout.xlsx",
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
    st.write("Set the price range in the sidebar and press Scan Stocks Now.")
    st.caption("Results will appear here after scanning.")

with st.expander("Scanner Rules"):
    st.markdown(
        """
        1. NSE EQ cash-market symbols are scanned and symbols in the NSE F&O list are excluded.
        2. The first green 1-hour candle of the current month must close above the previous completed month's High from below.
        3. Exactly 1, 2, or 3 additional green 1-hour candles must follow.
        4. The next candle must be red and close above the previous month's High.
        5. The immediately following candle must have a High greater than the red candle's High.
        6. Assumed entry is the red candle's High; stop-loss is 3% below entry and target is 10% above entry.
        7. Subsequent completed hourly candles are checked to see whether SL or target was reached first.
        8. If both levels occur in one hourly candle, the result is conservatively counted as SL.
        9. If neither level is reached in available data, the result is Pending.
        10. Only one signal per symbol per month.
        11. The currently forming 1-hour candle is ignored.
        """
    )

st.caption(
    "Educational screening tool only — not a buy/sell recommendation. "
    "Intraday data may be delayed, incomplete, or unavailable."
)
