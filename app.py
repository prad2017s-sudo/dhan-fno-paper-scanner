
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from io import BytesIO

# =====================================================
# CONFIGURATION
# =====================================================
st.set_page_config(
    page_title="NSE F&O Top 10 Scanner",
    page_icon="📊",
    layout="wide",
)

IST = ZoneInfo("Asia/Kolkata")
API = "https://api.dhan.co/v2"
MASTER_URL = (
    "https://images.dhan.co/api-data/"
    "api-scrip-master-detailed.csv"
)
REFRESH_SECONDS = 10
MARKET_START = dt_time(9, 15)
MARKET_END = dt_time(15, 30)

SECTOR_MAP = {
    "RELIANCE": "Energy",
    "ONGC": "Energy",
    "IOC": "Energy",
    "BPCL": "Energy",
    "HINDPETRO": "Energy",
    "GAIL": "Energy",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "TATAPOWER": "Power",
    "ADANIGREEN": "Power",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "LTIM": "IT",
    "PERSISTENT": "IT",
    "COFORGE": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "KOTAKBANK": "Banking",
    "INDUSINDBK": "Banking",
    "BANKBARODA": "Banking",
    "PNB": "Banking",
    "CANBK": "Banking",
    "FEDERALBNK": "Banking",
    "IDFCFIRSTB": "Banking",
    "BAJFINANCE": "Financial Services",
    "BAJAJFINSV": "Financial Services",
    "SHRIRAMFIN": "Financial Services",
    "CHOLAFIN": "Financial Services",
    "SBILIFE": "Financial Services",
    "HDFCLIFE": "Financial Services",
    "ICICIGI": "Financial Services",
    "LICI": "Financial Services",
    "MARUTI": "Auto",
    "TATAMOTORS": "Auto",
    "M&M": "Auto",
    "HEROMOTOCO": "Auto",
    "EICHERMOT": "Auto",
    "BAJAJ-AUTO": "Auto",
    "TVSMOTOR": "Auto",
    "ASHOKLEY": "Auto",
    "BHARATFORG": "Auto",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "VEDL": "Metals",
    "JINDALSTEL": "Metals",
    "NMDC": "Metals",
    "SAIL": "Metals",
    "COALINDIA": "Metals",
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "DABUR": "FMCG",
    "GODREJCP": "FMCG",
    "MARICO": "FMCG",
    "TATACONSUM": "FMCG",
    "VBL": "FMCG",
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "APOLLOHOSP": "Healthcare",
    "MAXHEALTH": "Healthcare",
    "FORTIS": "Healthcare",
    "LT": "Infrastructure",
    "ADANIENT": "Infrastructure",
    "ADANIPORTS": "Infrastructure",
    "ULTRACEMCO": "Cement",
    "GRASIM": "Cement",
    "AMBUJACEM": "Cement",
    "ACC": "Cement",
    "DLF": "Real Estate",
    "GODREJPROP": "Real Estate",
    "OBEROIRLTY": "Real Estate",
    "PHOENIXLTD": "Real Estate",
    "INDIGO": "Aviation",
    "TRENT": "Retail",
    "NYKAA": "Retail",
    "DMART": "Retail",
    "ZOMATO": "Internet",
    "ETERNAL": "Internet",
    "PAYTM": "Internet",
    "BEL": "Defence",
    "HAL": "Defence",
    "BDL": "Defence",
}

st.markdown("""
<style>
.block-container {padding-top: 1rem;}
div[data-testid="stMetric"] {
    background: #142033;
    padding: 12px;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

st.title("📊 NSE F&O Top 10 Activity Scanner")
st.caption(
    "Dhan live quotes · Top 10 activity ranking · "
    "Sector heatmap · Display-only scanner"
)

# =====================================================
# DHAN AUTHENTICATION
# =====================================================
def get_credentials():
    try:
        client_id = str(st.secrets["DHAN_CLIENT_ID"]).strip()
        token = str(st.secrets["DHAN_ACCESS_TOKEN"]).strip()
        if client_id and token:
            return client_id, token
    except Exception:
        pass
    return "", ""


CLIENT_ID, ACCESS_TOKEN = get_credentials()


def headers():
    return {
        "access-token": ACCESS_TOKEN,
        "client-id": CLIENT_ID,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def market_is_open():
    now = datetime.now(IST)
    return (
        now.weekday() < 5
        and MARKET_START <= now.time() <= MARKET_END
    )


# =====================================================
# LOAD DHAN INSTRUMENT MASTER
# =====================================================
@st.cache_data(ttl=3600, show_spinner=False)
def load_fno_universe():
    response = requests.get(MASTER_URL, timeout=30)
    response.raise_for_status()

    df = pd.read_csv(
        BytesIO(response.content),
        low_memory=False,
    )
    df.columns = [str(c).strip().upper() for c in df.columns]

    def col(*names):
        for name in names:
            if name in df.columns:
                return name
        return None

    exchange_col = col("EXCH_ID", "SEM_EXM_EXCH_ID")
    segment_col = col("SEGMENT", "SEM_SEGMENT")
    instrument_col = col("INSTRUMENT", "SEM_INSTRUMENT_NAME")
    security_col = col("SECURITY_ID", "SEM_SMST_SECURITY_ID")
    underlying_col = col("UNDERLYING_SYMBOL")
    symbol_col = col(
        "SYMBOL_NAME",
        "TRADING_SYMBOL",
        "SYMBOL",
        "SEM_TRADING_SYMBOL",
    )

    if not all([
        exchange_col,
        segment_col,
        instrument_col,
        security_col,
    ]):
        raise ValueError(
            "Dhan instrument master ke required columns nahi mile."
        )

    for c in [exchange_col, segment_col, instrument_col]:
        df[c] = df[c].astype(str).str.strip().str.upper()

    # NSE stock futures identify the F&O-eligible stock universe.
    futures = df[
        (df[exchange_col] == "NSE")
        & (df[segment_col] == "D")
        & (df[instrument_col] == "FUTSTK")
    ].copy()

    if underlying_col and not futures.empty:
        fno_symbols = set(
            futures[underlying_col]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
        )
    elif symbol_col and not futures.empty:
        fno_symbols = set(
            futures[symbol_col]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
        )
    else:
        raise ValueError(
            "Stock futures ke underlying symbols nahi mile."
        )

    # Map each underlying to its NSE equity security ID.
    equities = df[
        (df[exchange_col] == "NSE")
        & (df[segment_col] == "E")
    ].copy()

    if not symbol_col:
        raise ValueError("Equity symbol column nahi mila.")

    equities["_SYMBOL"] = (
        equities[symbol_col]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    equities = equities[equities["_SYMBOL"].isin(fno_symbols)]

    # Remove non-numeric/invalid IDs.
    equities["_SID"] = pd.to_numeric(
        equities[security_col], errors="coerce"
    )
    equities = equities.dropna(subset=["_SID"])
    equities["_SID"] = equities["_SID"].astype("int64")

    equities = equities.drop_duplicates("_SYMBOL")

    if equities.empty:
        raise ValueError(
            "F&O symbols ke NSE equity IDs nahi mile. "
            "Dhan master CSV columns check karein."
        )

    result = pd.DataFrame({
        "symbol": equities["_SYMBOL"],
        "security_id": equities["_SID"].astype(int),
    })

    result["sector"] = result["symbol"].map(SECTOR_MAP).fillna("Other")

    return result.sort_values("symbol").reset_index(drop=True)


# =====================================================
# FETCH LIVE QUOTE + VOLUME FOR ALL F&O STOCKS
# One quote snapshot per refresh; Top 10 is selected locally.
# =====================================================
def get_quotes(universe):
    result = {}
    ids = universe["security_id"].astype(int).tolist()

    # Dhan market quote supports up to 1000 IDs per request.
    for start in range(0, len(ids), 1000):
        batch = ids[start:start + 1000]

        response = requests.post(
            f"{API}/marketfeed/quote",
            headers=headers(),
            json={"NSE_EQ": batch},
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()

        if str(body.get("status", "")).lower() != "success":
            raise RuntimeError(
                str(body.get("remarks") or body.get("message") or body)
            )

        data = body.get("data", {}).get("NSE_EQ", {})

        for sid, item in data.items():
            try:
                sid = int(sid)
                ltp = float(item.get("last_price") or 0)
                volume = int(item.get("volume") or 0)
                ohlc = item.get("ohlc") or {}
                prev_close = float(ohlc.get("close") or 0)

                if ltp <= 0:
                    continue

                result[sid] = {
                    "security_id": sid,
                    "ltp": ltp,
                    "volume": volume,
                    "last_quantity": int(item.get("last_quantity") or 0),
                    "buy_quantity": int(item.get("buy_quantity") or 0),
                    "sell_quantity": int(item.get("sell_quantity") or 0),
                    "open": float(ohlc.get("open") or 0),
                    "high": float(ohlc.get("high") or 0),
                    "low": float(ohlc.get("low") or 0),
                    "prev_close": prev_close,
                    "change_pct": (
                        (ltp - prev_close) / prev_close * 100
                        if prev_close > 0 else 0.0
                    ),
                }
            except (TypeError, ValueError):
                continue

    return result


# =====================================================
# SIDEBAR
# =====================================================
with st.sidebar:
    st.header("⚙️ Scanner Settings")
    scanner_on = st.toggle("Scanner ON/OFF", value=True)
    auto_refresh = st.toggle("Auto refresh (10 sec)", value=True)
    st.caption("NSE regular market: 09:15–15:30 IST")
    st.caption("Only the 10 highest-activity stocks are displayed.")
    st.caption("No real orders are placed by this app.")

if not scanner_on:
    st.warning("Scanner OFF hai. Live quote request nahi ki ja rahi.")
    st.stop()

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error(
        "Streamlit Secrets mein DHAN_CLIENT_ID aur "
        "DHAN_ACCESS_TOKEN set karein."
    )
    st.stop()

try:
    universe = load_fno_universe()
except Exception as exc:
    st.error(f"F&O universe load nahi hua: {exc}")
    st.stop()

if universe.empty:
    st.error("NSE F&O universe khaali hai.")
    st.stop()

# =====================================================
# LIVE DATA AND ACTIVITY RANKING
# =====================================================
now = datetime.now(IST)

try:
    with st.spinner("NSE F&O shares ki activity check ho rahi hai..."):
        quote_map = get_quotes(universe)
except Exception as exc:
    st.error(f"Dhan quote API error: {exc}")
    st.info(
        "Token validity, Dhan API access aur quote API response "
        "check karein. Credentials chat ya GitHub mein share na karein."
    )
    st.stop()

if not quote_map:
    st.error("Dhan se koi valid NSE equity quote nahi mila.")
    st.stop()

quotes = pd.DataFrame(list(quote_map.values()))
quotes = quotes.merge(
    universe[["symbol", "security_id", "sector"]],
    on="security_id",
    how="left",
    suffixes=("", "_master"),
)

quotes["symbol"] = quotes["symbol"].fillna("")
quotes["sector"] = quotes["sector"].fillna("Other")
quotes = quotes[quotes["symbol"] != ""].copy()

# Track cumulative volume between app refreshes.
# Delta volume is a better measure of current activity than
# total volume alone. On the first sample, use traded turnover.
if "previous_volumes" not in st.session_state:
    st.session_state.previous_volumes = {}

previous = st.session_state.previous_volumes
deltas = []

for _, row in quotes.iterrows():
    sid = int(row["security_id"])
    current_volume = int(row["volume"])
    old_volume = previous.get(sid)

    if old_volume is None or current_volume < old_volume:
        delta = 0
    else:
        delta = current_volume - old_volume

    deltas.append(delta)

quotes["volume_delta"] = deltas

# Save the current cumulative volume for the next refresh.
st.session_state.previous_volumes = {
    int(row["security_id"]): int(row["volume"])
    for _, row in quotes.iterrows()
}

# Value traded in the most recent interval.
quotes["interval_turnover"] = (
    quotes["volume_delta"] * quotes["ltp"]
)

# Fallback ranking for the first sample or when no volume
# has changed since the last refresh.
quotes["cumulative_turnover"] = quotes["volume"] * quotes["ltp"]

has_activity = quotes["volume_delta"].sum() > 0

if has_activity:
    quotes["activity_score"] = quotes["interval_turnover"]
    ranking_method = "Recent traded activity (volume change)"
else:
    quotes["activity_score"] = quotes["cumulative_turnover"]
    ranking_method = "Cumulative traded turnover (initial/fallback)"

# Rank all eligible NSE F&O underlying shares and retain only 10.
top10 = (
    quotes.sort_values(
        ["activity_score", "volume", "last_quantity"],
        ascending=False,
    )
    .head(10)
    .copy()
    .reset_index(drop=True)
)

if top10.empty:
    st.error("Top 10 ke liye valid quotes available nahi hain.")
    st.stop()

top10.insert(0, "rank", range(1, len(top10) + 1))

st.caption(
    f"Time: {now.strftime('%d-%b-%Y %H:%M:%S')} IST · "
    f"Universe checked: {len(quotes)} · "
    f"Displayed: {len(top10)} · Ranking: {ranking_method}"
)

if not market_is_open():
    st.warning(
        "Regular market hours ke bahar hain. Data stale ho sakta hai; "
        "is waqt live activity ranking par bharosa na karein."
    )

# =====================================================
# SUMMARY: ONLY THE SELECTED TOP 10
# =====================================================
advances = int((top10["change_pct"] > 0).sum())
declines = int((top10["change_pct"] < 0).sum())
unchanged = int((top10["change_pct"] == 0).sum())

a, b, c, d = st.columns(4)
a.metric("Top 10 Stocks", len(top10))
b.metric("Advances", advances)
c.metric("Declines", declines)
d.metric("Unchanged", unchanged)

if advances > declines:
    st.success("Top 10 breadth: BUY SIDE bias (advances > declines)")
elif declines > advances:
    st.error("Top 10 breadth: SELL SIDE bias (declines > advances)")
else:
    st.info("Top 10 breadth: NEUTRAL")

# =====================================================
# TOP 10 TABLE
# =====================================================
st.subheader("🏆 Top 10 Most Active NSE F&O Shares")

display = top10[
    [
        "rank", "symbol", "sector", "ltp", "change_pct",
        "volume", "volume_delta", "interval_turnover",
        "open", "high", "low",
    ]
].copy()

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "rank": st.column_config.NumberColumn("Rank"),
        "symbol": st.column_config.TextColumn("Symbol"),
        "sector": st.column_config.TextColumn("Sector"),
        "ltp": st.column_config.NumberColumn("LTP", format="₹ %.2f"),
        "change_pct": st.column_config.NumberColumn(
            "Change %", format="%.2f%%"
        ),
        "volume": st.column_config.NumberColumn("Day Volume"),
        "volume_delta": st.column_config.NumberColumn(
            f"Volume Change (~{REFRESH_SECONDS}s)"
        ),
        "interval_turnover": st.column_config.NumberColumn(
            "Interval Turnover", format="₹ %.0f"
        ),
        "open": st.column_config.NumberColumn("Open", format="₹ %.2f"),
        "high": st.column_config.NumberColumn("High", format="₹ %.2f"),
        "low": st.column_config.NumberColumn("Low", format="₹ %.2f"),
    },
)

# =====================================================
# SECTOR HEATMAP - TOP 10 ONLY
# =====================================================
st.subheader("🔥 Sector Heatmap (Top 10 Only)")

sector_df = (
    top10.groupby("sector")
    .agg(
        avg_change=("change_pct", "mean"),
        stocks=("symbol", "count"),
        advances=("change_pct", lambda s: int((s > 0).sum())),
        declines=("change_pct", lambda s: int((s < 0).sum())),
    )
    .reset_index()
    .sort_values("avg_change", ascending=False)
)

fig = px.treemap(
    sector_df,
    path=["sector"],
    values="stocks",
    color="avg_change",
    color_continuous_scale=[
        "#c62828", "#ef5350", "#263238", "#66bb6a", "#1b5e20"
    ],
    color_continuous_midpoint=0,
    hover_data=["avg_change", "stocks", "advances", "declines"],
)
fig.update_traces(
    texttemplate="%{label}<br>%{color:.2f}%<br>%{value} stock(s)"
)
fig.update_layout(
    height=400,
    margin=dict(t=10, l=5, r=5, b=5),
)
st.plotly_chart(fig, use_container_width=True)

# =====================================================
# TOP 10 GAINERS AND LOSERS
# =====================================================
st.subheader("🚀 Top 10 ke Gainers aur Losers")
left, right = st.columns(2)

with left:
    st.markdown("#### 🟢 Gainers")
    st.dataframe(
        top10.sort_values("change_pct", ascending=False)
        [["symbol", "ltp", "change_pct"]].head(10),
        use_container_width=True,
        hide_index=True,
        column_config={
            "ltp": st.column_config.NumberColumn("LTP", format="₹ %.2f"),
            "change_pct": st.column_config.NumberColumn(
                "Change %", format="%.2f%%"
            ),
        },
    )

with right:
    st.markdown("#### 🔴 Losers")
    st.dataframe(
        top10.sort_values("change_pct", ascending=True)
        [["symbol", "ltp", "change_pct"]].head(10),
        use_container_width=True,
        hide_index=True,
        column_config={
            "ltp": st.column_config.NumberColumn("LTP", format="₹ %.2f"),
            "change_pct": st.column_config.NumberColumn(
                "Change %", format="%.2f%%"
            ),
        },
    )

# =====================================================
# CHANGE % CHART - TOP 10 ONLY
# =====================================================
st.subheader("📈 Top 10 Share Performance")

bar = px.bar(
    top10.sort_values("change_pct"),
    x="change_pct",
    y="symbol",
    orientation="h",
    color="change_pct",
    color_continuous_scale=[
        "#c62828", "#ef5350", "#777777", "#66bb6a", "#1b5e20"
    ],
    color_continuous_midpoint=0,
    labels={"change_pct": "Change (%)", "symbol": "Stock"},
)
bar.update_layout(
    height=420,
    margin=dict(t=10, l=5, r=5, b=5),
)
st.plotly_chart(bar, use_container_width=True)

# =====================================================
# STATUS
# =====================================================
st.subheader("🛰️ Scanner Status")
s1, s2, s3 = st.columns(3)
s1.metric("Quote Source", "Dhan REST API")
s2.metric("Refresh", f"{REFRESH_SECONDS} seconds")
s3.metric(
    "Market Session",
    "OPEN" if market_is_open() else "CLOSED / OUTSIDE HOURS",
)

st.caption(
    "Activity ranking uses interval volume change when available; "
    "the initial sample uses cumulative traded turnover. "
    "This is a ranking of underlying NSE equity shares, not F&O "
    "contract turnover or an official NSE ranking. "
    "Market breadth is calculated only from these 10 shares. "
    "The app does not place real orders and is not financial advice."
)

# =====================================================
# AUTO REFRESH
# =====================================================
if auto_refresh:
    time.sleep(REFRESH_SECONDS)
    st.rerun()
