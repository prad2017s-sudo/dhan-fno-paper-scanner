
import os
import time
from datetime import datetime
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
st.caption("Market time: 09:15 AM – 03:15 PM IST")

# Dhan credentials are read from GitHub Secrets.
client_id = os.getenv("DHAN_CLIENT_ID", "")
access_token = os.getenv("DHAN_ACCESS_TOKEN", "")

if not client_id or not access_token:
    st.error(
        "Dhan credentials missing. Check GitHub Secrets: "
        "DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN."
    )

st.subheader("Select scan direction")

left, right = st.columns(2)

with left:
    if st.button("🟢 BUY", use_container_width=True):
        st.session_state["direction"] = "BUY"

with right:
    if st.button("🔴 SELL", use_container_width=True):
        st.session_state["direction"] = "SELL"

direction = st.session_state.get("direction", None)

if direction:
    st.info(f"Selected direction: {direction}")

st.subheader("Watchlist")
st.write(", ".join(SYMBOLS))

if "records" not in st.session_state:
    st.session_state["records"] = []

records = st.session_state["records"]

st.subheader("Signal Records")

if records:
    df = pd.DataFrame(records, columns=COLUMNS)
    st.dataframe(df, use_container_width=True, hide_index=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Signals")

    st.download_button(
        "⬇️ Download Excel",
        data=output.getvalue(),
        file_name="dhan_signal_records.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )
else:
    st.info("अभी कोई signal record नहीं है।")

now = datetime.now(IST)
st.caption(f"Current time (IST): {now.strftime('%d-%m-%Y %H:%M:%S')}")

if now.hour < 9 or (now.hour == 9 and now.minute < 15):
    st.warning("Scanner window सुबह 09:15 बजे शुरू होगी।")
elif now.hour > 15 or (now.hour == 15 and now.minute >= 15):
    st.warning("Scanner window दोपहर 03:15 बजे बंद होगी।")
