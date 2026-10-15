import os
from datetime import datetime, time
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Dhan Live Scanner",
    page_icon="📈",
    layout="wide",
)

IST = ZoneInfo("Asia/Kolkata")

SHARES = {
    "RELIANCE": "2885",
    "BHARTIARTL": "10604",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "SBIN": "3045",
    "TCS": "11536",
    "BAJFINANCE": "317",
    "LT": "11483",
    "LICI": "9480",
    "HINDUNILVR": "1394",
}

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
st.caption("Market time: 09:15–15:15 IST")

client_id = os.getenv("DHAN_CLIENT_ID", "")
access_token = os.getenv("DHAN_ACCESS_TOKEN", "")

if not client_id or not access_token:
    st.error("DHAN_CLIENT_ID या DHAN_ACCESS_TOKEN Secret नहीं मिला।")
else:
    st.success("Dhan credentials मिले।")

if "direction" not in st.session_state:
    st.session_state.direction = "BUY"

if "records" not in st.session_state:
    st.session_state.records = []

if "scanner_enabled" not in st.session_state:
    st.session_state.scanner_enabled = False

buy_col, sell_col = st.columns(2)

with buy_col:
    if st.button("🟢 BUY", use_container_width=True):
        st.session_state.direction = "BUY"
        st.session_state.scanner_enabled = True

with sell_col:
    if st.button("🔴 SELL", use_container_width=True):
        st.session_state.direction = "SELL"
        st.session_state.scanner_enabled = True

st.info(f"Selected direction: {st.session_state.direction}")

st.subheader("Watchlist")
st.dataframe(
    pd.DataFrame(
        [{"Symbol": name, "Security ID": sid}
         for name, sid in SHARES.items()]
    ),
    use_container_width=True,
    hide_index=True,
)

now = datetime.now(IST)
market_open = time(9, 15) <= now.time() < time(15, 15)

if not market_open:
    st.warning("स्कैनिंग का समय सुबह 09:15 से दोपहर 03:15 IST है।")
elif st.session_state.scanner_enabled:
    st.warning(
        "चयन सेव है। लाइव WebSocket और breakout logic अभी जोड़ना बाकी है; "
        "अभी कोई वास्तविक सिग्नल नहीं बन रहा।"
    )
else:
    st.info("स्कैन शुरू करने के लिए BUY या SELL चुनें।")

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
    mime=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    use_container_width=True,
)

st.caption(f"Current IST: {now.strftime('%d-%m-%Y %H:%M:%S')}")

# Refreshing the page alone does not connect a market feed.
if st.session_state.scanner_enabled and market_open:
    st_autorefresh(interval=5000, key="ui_refresh")
