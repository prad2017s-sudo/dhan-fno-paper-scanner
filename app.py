import os
from datetime import datetime, time
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Dhan Live Scanner",
    page_icon="📈",
    layout="wide",
)

IST = ZoneInfo("Asia/Kolkata")

SYMBOLS = [
    "RELIANCE",
    "BHARTIARTL",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "TCS",
    "BAJFINANCE",
    "LT",
    "LICI",
    "HINDUNILVR",
]

COLUMNS = [
    "Date",
    "Time",
    "Symbol",
    "Signal",
    "Breakout Price",
    "Trigger Candle",
    "Trigger Volume",
]

st.title("📈 Dhan Live BUY / SELL Scanner")
st.caption("Market hours: 09:15–15:15 IST")

client_id = os.getenv("DHAN_CLIENT_ID", "")
access_token = os.getenv("DHAN_ACCESS_TOKEN", "")

if not client_id or not access_token:
    st.error(
        "Dhan Secrets missing. Set DHAN_CLIENT_ID "
        "and DHAN_ACCESS_TOKEN in app settings."
    )
else:
    st.success("Dhan credentials found. Live feed connection is not yet implemented.")

if "direction" not in st.session_state:
    st.session_state.direction = "BUY"

if "records" not in st.session_state:
    st.session_state.records = []

col1, col2 = st.columns(2)

with col1:
    if st.button("🟢 BUY", use_container_width=True):
        st.session_state.direction = "BUY"

with col2:
    if st.button("🔴 SELL", use_container_width=True):
        st.session_state.direction = "SELL"

st.info(f"Selected direction: {st.session_state.direction}")

st.subheader("Watchlist")
st.write(", ".join(SYMBOLS))

now = datetime.now(IST)
market_open = time(9, 15) <= now.time() < time(15, 15)

if market_open:
    st.success("Market scan window is open. Live scanning is not yet active.")
else:
    st.warning("Scan window: 09:15 AM to 03:15 PM IST.")

st.subheader("Signal Records")

df = pd.DataFrame(st.session_state.records, columns=COLUMNS)
st.dataframe(df, use_container_width=True, hide_index=True)

buffer = BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Signals")

st.download_button(
    "⬇️ Download Excel",
    data=buffer.getvalue(),
    file_name="dhan_signal_records.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.caption(f"Current IST: {now.strftime('%d-%m-%Y %H:%M:%S')}")
