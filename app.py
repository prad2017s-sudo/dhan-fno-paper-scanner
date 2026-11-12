import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import websocket
import struct
import json
import threading
import time
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from html import escape

IST = ZoneInfo("Asia/Kolkata")

DHAN_API = "https://api.dhan.co/v2"
INSTRUMENT_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

MARKET_START = dt_time(9, 0)
MARKET_END = dt_time(15, 30)
REFRESH_SECONDS = 10


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="Dhan NSE F&O Sector Heatmap",
    page_icon="📊",
    layout="wide",
)


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
<style>

.block-container{
    padding-top:2.8rem;
    padding-bottom:2rem;
}

.main-title{
    font-size:26px;
    font-weight:800;
    line-height:1.3;
    white-space:normal;
    padding-top:8px;
    margin-top:4px;
    display:block;
}

.sub-title{
    color:#777;
    font-size:14px;
    margin-bottom:12px;
}

.stMetric label{
    font-size:12px;
}

.stMetric [data-testid="stMetricValue"]{
    font-size:24px;
}

.market-header{
    padding:10px 14px;
    margin-bottom:12px;
    border-radius:10px;
    background:rgba(128,128,128,.10);
    border:1px solid rgba(128,128,128,.18);
    font-size:14px;
    font-weight:700;
}

.scanner-box{
    padding:12px 14px;
    margin:8px 0 12px 0;
    border-radius:10px;
    border:1px solid rgba(128,128,128,.20);
    background:rgba(128,128,128,.07);
}

.scanner-on{
    color:#16a34a;
    font-weight:800;
}

.scanner-off{
    color:#dc2626;
    font-weight:800;
}

.closed-box{
    padding:14px;
    border-radius:10px;
    border:1px solid rgba(128,128,128,.20);
    background:rgba(128,128,128,.07);
    margin:10px 0;
}


/* =====================================================
   TOP MOVER
   ===================================================== */

.top-movers-box{
    border-radius:10px;
    border:1px solid rgba(128,128,128,.25);
    background:rgba(128,128,128,.06);
    overflow:hidden;
    margin-bottom:8px;
}

.top-movers-title{
    padding:11px 14px;
    font-size:15px;
    font-weight:800;
    border-bottom:1px solid rgba(128,128,128,.18);
}

.gainer-title{
    border-top:4px solid #16a34a;
}

.loser-title{
    border-top:4px solid #dc2626;
}


/* =====================================================
   STOCK TILE
   ===================================================== */

.stock-tile{
    width:100%;
    min-height:82px;
    border-radius:8px;
    padding:8px 4px;
    margin-bottom:8px;
    text-align:center;
    color:white;
    box-sizing:border-box;
    box-shadow:0 1px 3px rgba(0,0,0,.18);
}

.stock-name{
    font-size:13px;
    font-weight:700;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}

.stock-price{
    font-size:12px;
    margin-top:5px;
}

.stock-change{
    font-size:13px;
    font-weight:700;
    margin-top:3px;
}


/* =====================================================
   SECTOR CARD
   ===================================================== */

.sector-card{
    width:100%;
    min-height:105px;
    border-radius:10px;
    padding:10px 5px;
    color:white;
    text-align:center;
    box-shadow:0 2px 6px rgba(0,0,0,.18);
    box-sizing:border-box;
    display:flex;
    flex-direction:column;
    justify-content:center;
    align-items:center;
}

.sector-name{
    font-size:13px;
    font-weight:800;
    line-height:1.15;
    width:100%;
}

.sector-change{
    font-size:18px;
    font-weight:900;
    margin-top:8px;
    width:100%;
}

.sector-count{
    font-size:11px;
    margin-top:7px;
    width:100%;
}

.direct-chart-header{
    padding:12px 14px;
    margin:8px 0 12px 0;
    border-radius:10px;
    background:rgba(128,128,128,.08);
    border:1px solid rgba(128,128,128,.18);
    font-size:16px;
    font-weight:800;
}


/* =====================================================
   MOBILE
   ===================================================== */

@media(max-width:700px){

    .block-container{
        padding-top:2.4rem;
    }

    .main-title{
        font-size:18px;
        line-height:1.3;
        padding-top:8px;
        margin-top:4px;
    }

    .sub-title{
        font-size:11px;
        line-height:1.35;
    }

    .market-header{
        font-size:11px;
    }

    .top-movers-title{
        font-size:12px;
        padding:9px 10px;
    }

    .sector-card{
        min-height:88px;
        padding:8px 3px;
    }

    .sector-name{
        font-size:10px;
    }

    .sector-change{
        font-size:14px;
        margin-top:5px;
    }

    .sector-count{
        font-size:8px;
        margin-top:4px;
    }

    .stock-name{
        font-size:11px;
    }

    .stock-price,
    .stock-change{
        font-size:10px;
    }

    .direct-chart-header{
        font-size:14px;
    }
}

</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# DHAN SECRETS
# =========================================================

try:

    DHAN_CLIENT_ID = str(
        st.secrets["DHAN_CLIENT_ID"]
    )

    DHAN_ACCESS_TOKEN = str(
        st.secrets["DHAN_ACCESS_TOKEN"]
    )

except Exception:

    st.error(
        "Streamlit Secrets me DHAN_CLIENT_ID aur DHAN_ACCESS_TOKEN add karein."
    )

    st.stop()


DHAN_HEADERS = {
    "Content-Type": "application/json",
    "access-token": DHAN_ACCESS_TOKEN,
    "client-id": DHAN_CLIENT_ID,
}


# =========================================================
# MARKET TIME HELPERS
# =========================================================

def market_is_open(now=None):

    if now is None:
        now = datetime.now(IST)

    current = now.time()

    return (
        current >= MARKET_START
        and current <= MARKET_END
    )


def market_status_text(now=None):

    if now is None:
        now = datetime.now(IST)

    current = now.time()

    if current < MARKET_START:
        return "Market not started"

    if current > MARKET_END:
        return "Market closed"

    return "Market open"


# =========================================================
# SECTOR MAP
# =========================================================

SECTOR_MAP = {

    "ASHOKLEY":"AUTOMOBILE",
    "BAJAJ-AUTO":"AUTOMOBILE",
    "EICHERMOT":"AUTOMOBILE",
    "HEROMOTOCO":"AUTOMOBILE",
    "M&M":"AUTOMOBILE",
    "MARUTI":"AUTOMOBILE",
    "MOTHERSON":"AUTOMOBILE",
    "TATAMOTORS":"AUTOMOBILE",
    "TVSMOTOR":"AUTOMOBILE",
    "BHARATFORG":"AUTOMOBILE",
    "BOSCHLTD":"AUTOMOBILE",
    "EXIDEIND":"AUTOMOBILE",
    "MRF":"AUTOMOBILE",
    "TIINDIA":"AUTOMOBILE",
    "UNOMINDA":"AUTOMOBILE",

    "AUBANK":"BANKING",
    "AXISBANK":"BANKING",
    "BANDHANBNK":"BANKING",
    "BANKBARODA":"BANKING",
    "CANBK":"BANKING",
    "FEDERALBNK":"BANKING",
    "HDFCBANK":"BANKING",
    "ICICIBANK":"BANKING",
    "IDFCFIRSTB":"BANKING",
    "INDUSINDBK":"BANKING",
    "KOTAKBANK":"BANKING",
    "PNB":"BANKING",
    "SBIN":"BANKING",
    "YESBANK":"BANKING",

    "BAJFINANCE":"FINANCIAL SERVICES",
    "BAJAJFINSV":"FINANCIAL SERVICES",
    "CHOLAFIN":"FINANCIAL SERVICES",
    "HDFCAMC":"FINANCIAL SERVICES",
    "LICHSGFIN":"FINANCIAL SERVICES",
    "MUTHOOTFIN":"FINANCIAL SERVICES",
    "PFC":"FINANCIAL SERVICES",
    "RECLTD":"FINANCIAL SERVICES",
    "SHRIRAMFIN":"FINANCIAL SERVICES",
    "MCX":"FINANCIAL SERVICES",
    "JIOFIN":"FINANCIAL SERVICES",

    "HDFCLIFE":"INSURANCE",
    "ICICIGI":"INSURANCE",
    "ICICIPRULI":"INSURANCE",
    "LICI":"INSURANCE",
    "SBILIFE":"INSURANCE",

    "COFORGE":"IT",
    "HCLTECH":"IT",
    "INFY":"IT",
    "LTIM":"IT",
    "LTTS":"IT",
    "MPHASIS":"IT",
    "OFSS":"IT",
    "PERSISTENT":"IT",
    "TCS":"IT",
    "TECHM":"IT",
    "WIPRO":"IT",

    "AUROPHARMA":"PHARMA",
    "BIOCON":"PHARMA",
    "CIPLA":"PHARMA",
    "DIVISLAB":"PHARMA",
    "DRREDDY":"PHARMA",
    "GLENMARK":"PHARMA",
    "GRANULES":"PHARMA",
    "LAURUSLABS":"PHARMA",
    "LUPIN":"PHARMA",
    "MANKIND":"PHARMA",
    "SUNPHARMA":"PHARMA",
    "TORNTPHARM":"PHARMA",
    "ZYDUSLIFE":"PHARMA",
    "APOLLOHOSP":"PHARMA",
    "MAXHEALTH":"PHARMA",

    "BRITANNIA":"FMCG",
    "COLPAL":"FMCG",
    "DABUR":"FMCG",
    "HINDUNILVR":"FMCG",
    "ITC":"FMCG",
    "MARICO":"FMCG",
    "NESTLEIND":"FMCG",
    "TATACONSUM":"FMCG",
    "UBL":"FMCG",

    "ADANIENT":"METALS & MINING",
    "HINDALCO":"METALS & MINING",
    "HINDZINC":"METALS & MINING",
    "JINDALSTEL":"METALS & MINING",
    "JSWSTEEL":"METALS & MINING",
    "NATIONALUM":"METALS & MINING",
    "NMDC":"METALS & MINING",
    "SAIL":"METALS & MINING",
    "TATASTEEL":"METALS & MINING",
    "VEDL":"METALS & MINING",

    "BPCL":"OIL & GAS",
    "COALINDIA":"OIL & GAS",
    "GAIL":"OIL & GAS",
    "HINDPETRO":"OIL & GAS",
    "IOC":"OIL & GAS",
    "ONGC":"OIL & GAS",
    "PETRONET":"OIL & GAS",
    "RELIANCE":"OIL & GAS",

    "ADANIENSOL":"POWER",
    "ADANIPOWER":"POWER",
    "NTPC":"POWER",
    "POWERGRID":"POWER",
    "TATAPOWER":"POWER",

    "ACC":"CEMENT",
    "AMBUJACEM":"CEMENT",
    "DALBHARAT":"CEMENT",
    "SHREECEM":"CEMENT",
    "ULTRACEMCO":"CEMENT",

    "GRASIM":"CONSTRUCTION",
    "LT":"CONSTRUCTION",

    "DLF":"REALTY",
    "GODREJPROP":"REALTY",
    "LODHA":"REALTY",
    "OBEROIRLTY":"REALTY",
    "PRESTIGE":"REALTY",

    "BHARTIARTL":"TELECOM",
    "INDUSTOWER":"TELECOM",

    "DMART":"CONSUMER",
    "NYKAA":"CONSUMER",
    "TRENT":"CONSUMER",

    "ATUL":"CHEMICALS",
    "DEEPAKNTR":"CHEMICALS",
    "PIDILITIND":"CHEMICALS",
    "SRF":"CHEMICALS",
    "UPL":"CHEMICALS",

    "INDIGO":"AVIATION",
    "INDHOTEL":"HOTELS",

    "BEL":"DEFENCE",
    "HAL":"DEFENCE",
    "BHEL":"DEFENCE",

    "ABB":"CAPITAL GOODS",
    "CUMMINSIND":"CAPITAL GOODS",
    "SIEMENS":"CAPITAL GOODS",
    "THERMAX":"CAPITAL GOODS",

    "PVRINOX":"MEDIA",
    "CONCOR":"LOGISTICS",

    "IRCTC":"RAILWAYS",
    "IRFC":"RAILWAYS",
    "RVNL":"RAILWAYS",
}


# =========================================================
# MASTER DATA
# =========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def load_master():

    return pd.read_csv(
        INSTRUMENT_URL,
        low_memory=False
    )


@st.cache_data(ttl=3600, show_spinner=False)
def build_universe():

    df = load_master().copy()

    needed = [
        "EXCH_ID",
        "SEGMENT",
        "INSTRUMENT",
        "UNDERLYING_SYMBOL",
        "UNDERLYING_SECURITY_ID",
    ]

    missing = [
        c
        for c in needed
        if c not in df.columns
    ]

    if missing:

        raise ValueError(
            "Master columns missing: "
            + ", ".join(missing)
        )

    df = df[
        df["EXCH_ID"]
        .astype(str)
        .str.upper()
        .eq("NSE")
        &
        df["SEGMENT"]
        .astype(str)
        .str.upper()
        .eq("D")
        &
        df["INSTRUMENT"]
        .astype(str)
        .str.upper()
        .isin([
            "FUTSTK",
            "OPTSTK"
        ])
    ].copy()

    df["Symbol"] = (
        df["UNDERLYING_SYMBOL"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["sid_num"] = pd.to_numeric(
        df["UNDERLYING_SECURITY_ID"],
        errors="coerce"
    )

    df = df[
        df["sid_num"].notna()
    ].copy()

    df["Security ID"] = (
        df["sid_num"]
        .astype("int64")
        .astype(str)
    )

    df = df[
        [
            "Symbol",
            "Security ID"
        ]
    ].drop_duplicates(
        "Symbol"
    )

    df["Sector"] = (
        df["Symbol"]
        .map(SECTOR_MAP)
        .fillna("UNCLASSIFIED")
    )

    return df.reset_index(
        drop=True
    )


# =========================================================
# DHAN WEBSOCKET
# =========================================================

class DhanQuoteFeed:

    def __init__(self):

        self.lock = threading.Lock()
        self.quotes = {}
        self.error = None
        self.ids = set()
        self.thread = None
        self.stop_event = threading.Event()
        self.ws = None

    def start(self, ids):

        clean = set()

        for x in ids:

            try:

                n = int(
                    float(
                        str(x).strip()
                    )
                )

                if n > 0:
                    clean.add(n)

            except Exception:
                pass

        if not clean:
            return

        with self.lock:

            if (
                clean == self.ids
                and self.thread
                and self.thread.is_alive()
            ):
                return

            self.stop_event.set()

            if self.ws:

                try:
                    self.ws.close()
                except Exception:
                    pass

            self.ids = clean
            self.stop_event = threading.Event()
            self.error = None

            self.thread = threading.Thread(
                target=self._run,
                args=(
                    sorted(clean),
                    self.stop_event
                ),
                daemon=True
            )

            self.thread.start()

    def stop(self):

        with self.lock:

            self.stop_event.set()

            ws = self.ws

            self.ws = None
            self.ids = set()

        if ws:

            try:
                ws.close()
            except Exception:
                pass

    def _run(
        self,
        ids,
        stop_event
    ):

        ws = None

        try:

            url = (
                "wss://api-feed.dhan.co"
                "?version=2"
                f"&token={DHAN_ACCESS_TOKEN}"
                f"&clientId={DHAN_CLIENT_ID}"
                "&authType=2"
            )

            ws = websocket.create_connection(
                url,
                timeout=10,
                enable_multithread=True
            )

            with self.lock:
                self.ws = ws

            for i in range(
                0,
                len(ids),
                100
            ):

                if stop_event.is_set():
                    break

                chunk = ids[
                    i:i + 100
                ]

                payload = {
                    "RequestCode": 17,
                    "InstrumentCount": len(chunk),
                    "InstrumentList": [
                        {
                            "ExchangeSegment": "NSE_EQ",
                            "SecurityId": str(s)
                        }
                        for s in chunk
                    ],
                }

                ws.send(
                    json.dumps(payload)
                )

            while not stop_event.is_set():

                try:

                    msg = ws.recv()

                except Exception:

                    if stop_event.is_set():
                        break

                    continue

                if not isinstance(
                    msg,
                    (bytes, bytearray)
                ):
                    continue

                if len(msg) < 8:
                    continue

                try:

                    code = msg[0]

                    sid = struct.unpack_from(
                        "<I",
                        msg,
                        4
                    )[0]

                    key = str(sid)

                    with self.lock:

                        q = self.quotes.setdefault(
                            key,
                            {}
                        )

                        if (
                            code == 6
                            and len(msg) >= 12
                        ):

                            prev = struct.unpack_from(
                                "<f",
                                msg,
                                8
                            )[0]

                            if prev > 0:

                                q["prev_close"] = float(
                                    prev
                                )

                                if q.get(
                                    "last_price"
                                ) is not None:

                                    q["net_change"] = float(
                                        q["last_price"]
                                        - prev
                                    )

                        elif (
                            code == 4
                            and len(msg) >= 50
                        ):

                            ltp = struct.unpack_from(
                                "<f",
                                msg,
                                8
                            )[0]

                            if ltp <= 0:
                                continue

                            volume = struct.unpack_from(
                                "<I",
                                msg,
                                22
                            )[0]

                            q["last_price"] = float(
                                ltp
                            )

                            q["volume"] = int(
                                volume
                            )

                            q["received_at"] = time.time()

                            q["day_open"] = float(
                                struct.unpack_from(
                                    "<f",
                                    msg,
                                    34
                                )[0]
                            )

                            q["day_high"] = float(
                                struct.unpack_from(
                                    "<f",
                                    msg,
                                    42
                                )[0]
                            )

                            q["day_low"] = float(
                                struct.unpack_from(
                                    "<f",
                                    msg,
                                    46
                                )[0]
                            )

                            prev = q.get(
                                "prev_close"
                            )

                            if (
                                prev
                                and prev > 0
                            ):

                                q["net_change"] = float(
                                    ltp - prev
                                )

                        self.error = None

                except Exception:
                    continue

        except Exception as e:

            with self.lock:
                self.error = str(e)

        finally:

            with self.lock:

                if self.ws is ws:
                    self.ws = None

    def snapshot(self):

        with self.lock:

            return (
                dict(self.quotes),
                self.error
            )


@st.cache_resource
def get_quote_feed():

    return DhanQuoteFeed()


QUOTE_FEED = get_quote_feed()


def get_quotes(ids):

    QUOTE_FEED.start(ids)

    return QUOTE_FEED.snapshot()


# =========================================================
# MARKET DATAFRAME
# =========================================================

def make_market_dataframe(
    universe
):

    ids = universe[
        "Security ID"
    ].tolist()

    data, err = get_quotes(
        ids
    )

    rows = []

    for _, r in universe.iterrows():

        sid = str(
            r["Security ID"]
        )

        q = data.get(
            sid,
            {}
        )

        price = q.get(
            "last_price"
        )

        prev = q.get(
            "prev_close"
        )

        net = q.get(
            "net_change"
        )

        change = None

        if (
            price is not None
            and prev is not None
            and float(prev) > 0
        ):

            change = (
                (
                    float(price)
                    - float(prev)
                )
                / float(prev)
                * 100.0
            )

        elif (
            price is not None
            and net is not None
        ):

            base = (
                float(price)
                - float(net)
            )

            if base > 0:

                change = (
                    float(net)
                    / base
                    * 100.0
                )

        rows.append(
            {
                "Symbol": r["Symbol"],
                "Security ID": sid,
                "Sector": r["Sector"],
                "Price": price,
                "Previous Close": prev,
                "Dhan Net Change": net,
                "Volume": q.get(
                    "volume"
                ),
                "Change %": change,
            }
        )

    return (
        pd.DataFrame(rows),
        err
    )


# =========================================================
# DHAN FALLBACK
# =========================================================

@st.cache_data(
    ttl=8,
    show_spinner=False
)
def dhan_quote_change_fallback(
    security_ids_tuple
):

    ids = []

    for x in security_ids_tuple:

        try:

            n = int(
                float(
                    str(x).strip()
                )
            )

            if n > 0:
                ids.append(n)

        except Exception:
            pass

    result = {}

    if not ids:
        return result

    try:

        resp = requests.post(
            f"{DHAN_API}/marketfeed/quote",
            headers=DHAN_HEADERS,
            json={
                "NSE_EQ": ids[:1000]
            },
            timeout=15
        )

        if resp.status_code == 200:

            payload = (
                resp.json()
                .get("data", {})
                .get("NSE_EQ", {})
                or {}
            )

            for sid, q in payload.items():

                if not isinstance(
                    q,
                    dict
                ):
                    continue

                ltp = q.get(
                    "last_price"
                )

                net = q.get(
                    "net_change"
                )

                ohlc = (
                    q.get("ohlc")
                    or {}
                )

                close = ohlc.get(
                    "close"
                )

                if ltp is None:
                    continue

                item = {
                    "last_price": float(
                        ltp
                    ),
                    "volume": q.get(
                        "volume"
                    ),
                }

                if net is not None:

                    item[
                        "net_change"
                    ] = float(net)

                    base = (
                        float(ltp)
                        - float(net)
                    )

                    if base > 0:

                        item[
                            "prev_close"
                        ] = base

                if close is not None:

                    try:

                        pc = float(
                            close
                        )

                        if pc > 0:

                            item[
                                "prev_close"
                            ] = pc

                            item[
                                "net_change"
                            ] = (
                                float(ltp)
                                - pc
                            )

                    except Exception:
                        pass

                result[
                    str(sid)
                ] = item

    except Exception:
        pass

    return result


def enrich_missing_changes(
    market
):

    missing = market[
        "Change %"
    ].isna()

    if not missing.any():
        return market

    ids = tuple(
        market.loc[
            missing,
            "Security ID"
        ]
        .astype(str)
        .tolist()
    )

    fallback = dhan_quote_change_fallback(
        ids
    )

    for idx in market.index[
        missing
    ]:

        sid = str(
            market.at[
                idx,
                "Security ID"
            ]
        )

        q = fallback.get(
            sid
        )

        if not q:
            continue

        if (
            pd.isna(
                market.at[
                    idx,
                    "Price"
                ]
            )
            and q.get(
                "last_price"
            ) is not None
        ):

            market.at[
                idx,
                "Price"
            ] = q[
                "last_price"
            ]

        if q.get(
            "prev_close"
        ) is not None:

            market.at[
                idx,
                "Previous Close"
            ] = q[
                "prev_close"
            ]

        if q.get(
            "net_change"
        ) is not None:

            market.at[
                idx,
                "Dhan Net Change"
            ] = q[
                "net_change"
            ]

        price = market.at[
            idx,
            "Price"
        ]

        prev = market.at[
            idx,
            "Previous Close"
        ]

        net = market.at[
            idx,
            "Dhan Net Change"
        ]

        try:

            if (
                pd.notna(price)
                and pd.notna(prev)
                and float(prev) > 0
            ):

                market.at[
                    idx,
                    "Change %"
                ] = (
                    (
                        float(price)
                        - float(prev)
                    )
                    / float(prev)
                    * 100.0
                )

            elif (
                pd.notna(price)
                and pd.notna(net)
            ):

                base = (
                    float(price)
                    - float(net)
                )

                if base > 0:

                    market.at[
                        idx,
                        "Change %"
                    ] = (
                        float(net)
                        / base
                        * 100.0
                    )

        except Exception:
            pass

    return market


# =========================================================
# COLORS
# =========================================================

def tile_color(x):

    if pd.isna(x):
        return "#777"

    x = float(x)

    if x >= 2:
        return "#006b2e"

    if x >= 1.5:
        return "#008f3d"

    if x >= 1:
        return "#16a34a"

    if x >= .5:
        return "#3fbd63"

    if x > 0:
        return "#72d08a"

    if x == 0:
        return "#777"

    if x > -.5:
        return "#ef8585"

    if x > -1:
        return "#e34b4b"

    if x > -1.5:
        return "#d21f2f"

    if x > -2:
        return "#b80016"

    return "#8f0010"


def sector_bg(x):

    return tile_color(x)


# =========================================================
# TOP GAINERS / LOSERS
# =========================================================

def show_top_movers(
    market
):

    live_market = market[
        market["Price"].notna()
        &
        market["Change %"].notna()
    ].copy()

    live_count = len(
        live_market
    )

    if live_market.empty:

        st.info(
            "Live share change data abhi available nahi hai."
        )

        return

    gainers = (
        live_market
        .sort_values(
            "Change %",
            ascending=False
        )
        .head(5)
    )

    losers = (
        live_market
        .sort_values(
            "Change %",
            ascending=True
        )
        .head(5)
    )

    col1, col2 = st.columns(
        2,
        gap="small"
    )

    with col1:

        st.markdown(
            f"""
            <div class="top-movers-box">
                <div class="top-movers-title gainer-title">
                    🟢 Top Gainers ({live_count} Live Shares)
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        for _, r in gainers.iterrows():

            symbol = str(
                r["Symbol"]
            )

            change = float(
                r["Change %"]
            )

            button_text = (
                f"🟢 {symbol}    {change:+.2f}%"
            )

            if st.button(
                button_text,
                key=f"top_gain_{symbol}",
                use_container_width=True
            ):

                st.session_state.selected_stock = (
                    symbol
                )

                st.session_state.top_mover_open = True

                st.rerun()

    with col2:

        st.markdown(
            f"""
            <div class="top-movers-box">
                <div class="top-movers-title loser-title">
                    🔴 Top Losers ({live_count} Live Shares)
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        for _, r in losers.iterrows():

            symbol = str(
                r["Symbol"]
            )

            change = float(
                r["Change %"]
            )

            button_text = (
                f"🔴 {symbol}    {change:+.2f}%"
            )

            if st.button(
                button_text,
                key=f"top_loss_{symbol}",
                use_container_width=True
            ):

                st.session_state.selected_stock = (
                    symbol
                )

                st.session_state.top_mover_open = True

                st.rerun()


# =========================================================
# CHART DATA
# =========================================================

def get_chart_data(
    security_id,
    timeframe
):

    now = datetime.now(
        IST
    )

    today = now.date()

    if timeframe == "1D":

        endpoint = (
            f"{DHAN_API}/charts/historical"
        )

        payload = {
            "securityId": str(
                security_id
            ),
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "expiryCode": 0,
            "oi": False,
            "fromDate": (
                f"{today - timedelta(days=180)} "
                "00:00:00"
            ),
            "toDate": now.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

    else:

        endpoint = (
            f"{DHAN_API}/charts/intraday"
        )

        payload = {
            "securityId": str(
                security_id
            ),
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "interval": {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "1h": "60"
            }[
                timeframe
            ],
            "oi": False,
            "fromDate": (
                f"{today} 09:15:00"
            ),
            "toDate": now.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

    try:

        r = requests.post(
            endpoint,
            headers=DHAN_HEADERS,
            json=payload,
            timeout=20
        )

        r.raise_for_status()

        d = r.json()

        n = min(
            len(
                d.get(
                    "timestamp",
                    []
                )
            ),
            len(
                d.get(
                    "open",
                    []
                )
            ),
            len(
                d.get(
                    "high",
                    []
                )
            ),
            len(
                d.get(
                    "low",
                    []
                )
            ),
            len(
                d.get(
                    "close",
                    []
                )
            )
        )

        if n == 0:

            return (
                pd.DataFrame(),
                None
            )

        out = pd.DataFrame(
            {
                "Timestamp":
                    d["timestamp"][:n],

                "Open":
                    d["open"][:n],

                "High":
                    d["high"][:n],

                "Low":
                    d["low"][:n],

                "Close":
                    d["close"][:n],

                "Volume":
                    (
                        d.get(
                            "volume",
                            []
                        )[:n]
                        if d.get(
                            "volume"
                        )
                        else [0] * n
                    ),
            }
        )

        out["Timestamp"] = (
            pd.to_datetime(
                out["Timestamp"],
                unit="s",
                utc=True,
                errors="coerce"
            )
            .dt
            .tz_convert(
                IST
            )
        )

        for c in [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]:

            out[c] = pd.to_numeric(
                out[c],
                errors="coerce"
            )

        out = out.dropna(
            subset=[
                "Timestamp",
                "Open",
                "High",
                "Low",
                "Close"
            ]
        )

        return (
            out.sort_values(
                "Timestamp"
            ),
            None
        )

    except Exception as e:

        return (
            pd.DataFrame(),
            str(e)
        )


# =========================================================
# CHART
# =========================================================

def show_chart(
    row
):

    symbol = row[
        "Symbol"
    ]

    tf = st.radio(
        "Chart Timeframe",
        [
            "1m",
            "5m",
            "15m",
            "1h",
            "1D"
        ],
        index=1,
        horizontal=True,
        key="tf_" + str(symbol)
    )

    chart, err = get_chart_data(
        row["Security ID"],
        tf
    )

    st.markdown(
        f"""
        <div class="direct-chart-header">
            📊 {escape(str(symbol))} - {tf} Dhan Chart
        </div>
        """,
        unsafe_allow_html=True
    )

    if err:

        st.warning(
            "Dhan chart unavailable: "
            + str(err)
        )

        return

    if chart.empty:

        st.info(
            "Chart data available nahi hai."
        )

        return

    if tf == "1D":

        fig = go.Figure(
            go.Candlestick(
                x=chart["Timestamp"],
                open=chart["Open"],
                high=chart["High"],
                low=chart["Low"],
                close=chart["Close"]
            )
        )

        fig.update_layout(
            height=520,
            margin=dict(
                l=5,
                r=5,
                t=10,
                b=5
            ),
            xaxis_rangeslider_visible=False
        )

    else:

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=.04,
            row_heights=[
                .76,
                .24
            ]
        )

        fig.add_trace(
            go.Candlestick(
                x=chart["Timestamp"],
                open=chart["Open"],
                high=chart["High"],
                low=chart["Low"],
                close=chart["Close"]
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Bar(
                x=chart["Timestamp"],
                y=chart["Volume"],
                name="Volume"
            ),
            row=2,
            col=1
        )

        fig.update_layout(
            height=620,
            margin=dict(
                l=5,
                r=5,
                t=10,
                b=5
            ),
            xaxis_rangeslider_visible=False,
            showlegend=False
        )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"chart_{symbol}_{tf}"
    )


# =========================================================
# SESSION STATE
# =========================================================

if "scanner_on" not in st.session_state:

    st.session_state.scanner_on = True

if "selected_sector" not in st.session_state:

    st.session_state.selected_sector = None

if "selected_stock" not in st.session_state:

    st.session_state.selected_stock = None

if "top_mover_open" not in st.session_state:

    st.session_state.top_mover_open = False


# =========================================================
# HEADER / SCANNER CONTROL
# =========================================================

header_col, control_col = st.columns(
    [3.5, 1.5],
    gap="small"
)

with header_col:

    st.markdown(
        '<div class="main-title">'
        'Dhan NSE F&O Sector Heatmap'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">'
        'NSE F&O Stocks - Dhan Live Market Data - Paper Trading Only'
        '</div>',
        unsafe_allow_html=True
    )

with control_col:

    scanner_value = st.toggle(
        "Scanner ON/OFF",
        value=st.session_state.scanner_on,
        key="scanner_toggle"
    )

    if scanner_value != st.session_state.scanner_on:

        st.session_state.scanner_on = scanner_value

        if not scanner_value:

            # OFF karte hi Dhan WebSocket band
            QUOTE_FEED.stop()

            st.toast(
                "Scanner OFF - Dhan live feed band.",
                icon="⛔"
            )

        else:

            st.toast(
                "Scanner ON - Dhan live feed start hoga.",
                icon="▶️"
            )

        st.rerun()


# =========================================================
# CURRENT TIME / MARKET WINDOW
# =========================================================

now = datetime.now(IST)

market_open = market_is_open(now)

if st.session_state.scanner_on:

    if market_open:

        st.markdown(
            """
            <div class="scanner-box">
                <span class="scanner-on">
                    🟢 Scanner ON
                </span>
                &nbsp; | &nbsp;
                Dhan live feed active
                &nbsp; | &nbsp;
                Auto refresh: 10 seconds
                &nbsp; | &nbsp;
                Market: 09:00 - 15:30
            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        # Market closed hone par Dhan bhi stop
        QUOTE_FEED.stop()

        st.markdown(
            f"""
            <div class="closed-box">
                <b>🔴 Market Closed</b><br>
                Market window: 09:00 - 15:30 IST<br>
                Current time: {now.strftime("%H:%M:%S")} IST<br>
                Dhan live feed automatically stopped.
            </div>
            """,
            unsafe_allow_html=True
        )

else:

    QUOTE_FEED.stop()

    st.markdown(
        """
        <div class="scanner-box">
            <span class="scanner-off">
                🔴 Scanner OFF
            </span>
            &nbsp; | &nbsp;
            Automatic scan band hai.
            &nbsp; | &nbsp;
            Dhan live feed band hai.
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# MAIN LIVE APP
# =========================================================

def render_heatmap():

    now = datetime.now(IST)

    # -----------------------------------------------------
    # Market closed protection
    # -----------------------------------------------------

    if not market_is_open(now):

        QUOTE_FEED.stop()

        st.info(
            "09:00-15:30 ke bahar automatic Dhan scanning nahi chalegi."
        )

        return

    # -----------------------------------------------------
    # Universe
    # -----------------------------------------------------

    try:

        universe = build_universe()

        market, feed_error = (
            make_market_dataframe(
                universe
            )
        )

        market = enrich_missing_changes(
            market
        )

    except Exception as e:

        st.error(
            f"F&O Universe Error: {e}"
        )

        return

    total = len(
        market
    )

    live = int(
        market["Price"]
        .notna()
        .sum()
    )

    changes = int(
        market["Change %"]
        .notna()
        .sum()
    )

    coverage = (
        live / total * 100
        if total
        else 0
    )

    # -----------------------------------------------------
    # TOP STATS
    # -----------------------------------------------------

    s1, s2, s3, s4 = st.columns(
        4
    )

    s1.metric(
        "F&O Underlyings",
        total
    )

    s2.metric(
        "Dhan Connection",
        "LIVE" if live > 0 else "WAIT"
    )

    s3.metric(
        "Live Quotes",
        live
    )

    s4.metric(
        "Quote Coverage",
        f"{coverage:.1f}%"
    )

    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    st.markdown(
        f"""
        <div class="market-header">
            <b>
                {now.strftime("%d %b %Y")}
                &nbsp;|&nbsp;
                {now.strftime("%H:%M:%S IST")}
            </b>
            &nbsp;&nbsp;
            <span style="font-weight:600;color:#666;">
                Last Update: {now.strftime("%H:%M:%S IST")}
                &nbsp;|&nbsp;
                Next automatic update: 10 sec
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # FEED STATUS
    # -----------------------------------------------------

    if live < total:

        st.info(
            f"{live}/{total} quotes available. "
            "Dhan WebSocket remaining quotes receive kar raha hai."
        )

    else:

        st.success(
            f"{live}/{total} quotes available. Dhan WebSocket LIVE."
        )

    if feed_error:

        st.warning(
            "Dhan live feed error: "
            + str(feed_error)
        )

    # -----------------------------------------------------
    # DIRECT TOP MOVER CHART
    # -----------------------------------------------------

    selected_top_stock = (
        st.session_state.selected_stock
    )

    if (
        st.session_state.top_mover_open
        and selected_top_stock
    ):

        selected_rows = market[
            market["Symbol"]
            == selected_top_stock
        ]

        if not selected_rows.empty:

            selected_row = (
                selected_rows.iloc[0]
            )

            back_col, _ = st.columns(
                [1, 5]
            )

            with back_col:

                if st.button(
                    "← Back",
                    key="back_top_mover",
                    use_container_width=True
                ):

                    st.session_state.top_mover_open = False
                    st.session_state.selected_stock = None

                    st.rerun()

            st.markdown(
                f"""
                <div class="direct-chart-header">
                    📈 {escape(str(selected_top_stock))}
                    &nbsp; | &nbsp;
                    Top Gainer / Loser
                </div>
                """,
                unsafe_allow_html=True
            )

            show_chart(
                selected_row
            )

            return

    # -----------------------------------------------------
    # TOP MOVERS
    # -----------------------------------------------------

    show_top_movers(
        market
    )

    # -----------------------------------------------------
    # SECTOR AVERAGES
    # -----------------------------------------------------

    averages = (
        market
        .groupby(
            "Sector",
            as_index=False
        )
        .agg(
            SectorChange=(
                "Change %",
                "mean"
            )
        )
    )

    counts = (
        market
        .groupby(
            "Sector"
        )
        .size()
        .rename(
            "Count"
        )
    )

    averages = averages.join(
        counts,
        on="Sector"
    )

    averages = (
        averages
        .sort_values(
            "SectorChange",
            ascending=False,
            na_position="last"
        )
        .reset_index(
            drop=True
        )
    )

    sector = (
        st.session_state.selected_sector
    )

    # -----------------------------------------------------
    # SECTOR SCREEN
    # -----------------------------------------------------

    if not sector:

        st.subheader(
            "Sector Heatmap"
        )

        st.caption(
            "Sector tap karo → F&O stocks → stock select karo → Dhan chart."
        )

        for start in range(
            0,
            len(averages),
            5
        ):

            chunk = averages.iloc[
                start:start + 5
            ]

            cols = st.columns(
                5,
                gap="small"
            )

            for col, (_, s) in zip(
                cols,
                chunk.iterrows()
            ):

                sector_name = str(
                    s["Sector"]
                )

                ch = s[
                    "SectorChange"
                ]

                count = int(
                    s["Count"]
                )

                if pd.isna(ch):

                    txt = "--"

                else:

                    txt = (
                        f"{float(ch):+.2f}%"
                    )

                safe_sector = escape(
                    sector_name
                )

                card_html = (
                    '<div class="sector-card" '
                    f'style="background:{sector_bg(ch)};">'
                    f'<div class="sector-name">{safe_sector}</div>'
                    f'<div class="sector-change">{txt}</div>'
                    f'<div class="sector-count">{count} F&amp;O</div>'
                    '</div>'
                )

                with col:

                    st.markdown(
                        card_html,
                        unsafe_allow_html=True
                    )

                    if st.button(
                        f"Open {sector_name}",
                        key="sec_" + sector_name,
                        use_container_width=True
                    ):

                        st.session_state.selected_sector = (
                            sector_name
                        )

                        st.session_state.selected_stock = None
                        st.session_state.top_mover_open = False

                        st.rerun()

        return

    # -----------------------------------------------------
    # INVALID SECTOR
    # -----------------------------------------------------

    if sector not in set(
        averages["Sector"]
    ):

        st.session_state.selected_sector = None
        st.session_state.selected_stock = None
        st.session_state.top_mover_open = False

        st.rerun()

    # -----------------------------------------------------
    # BACK
    # -----------------------------------------------------

    back_col, _ = st.columns(
        [1, 5]
    )

    with back_col:

        if st.button(
            "← Back",
            key="back_to_sectors",
            use_container_width=True
        ):

            st.session_state.selected_sector = None
            st.session_state.selected_stock = None
            st.session_state.top_mover_open = False

            st.rerun()

    # -----------------------------------------------------
    # SELECTED SECTOR
    # -----------------------------------------------------

    sdf = market[
        market["Sector"]
        == sector
    ].copy()

    sdf = sdf.sort_values(
        "Change %",
        ascending=False,
        na_position="last"
    )

    st.markdown(
        f"""
        <div class="direct-chart-header">
            {escape(str(sector))} - F&O Stocks
        </div>
        """,
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # STOCK TILES
    # -----------------------------------------------------

    for start in range(
        0,
        len(sdf),
        5
    ):

        chunk = sdf.iloc[
            start:start + 5
        ]

        cols = st.columns(
            5,
            gap="small"
        )

        for col, (_, r) in zip(
            cols,
            chunk.iterrows()
        ):

            ch = r[
                "Change %"
            ]

            price = r[
                "Price"
            ]

            ch_txt = (
                "--"
                if pd.isna(ch)
                else f"{float(ch):+.2f}%"
            )

            p_txt = (
                "--"
                if pd.isna(price)
                else f"Rs. {float(price):,.2f}"
            )

            symbol = escape(
                str(r["Symbol"])
            )

            with col:

                stock_html = (
                    '<div class="stock-tile" '
                    f'style="background:{tile_color(ch)};">'
                    f'<div class="stock-name">{symbol}</div>'
                    f'<div class="stock-price">{p_txt}</div>'
                    f'<div class="stock-change">{ch_txt}</div>'
                    '</div>'
                )

                st.markdown(
                    stock_html,
                    unsafe_allow_html=True
                )

                if st.button(
                    "Select",
                    key=(
                        f"stk_{sector}_{r['Symbol']}"
                    ),
                    use_container_width=True
                ):

                    st.session_state.selected_stock = (
                        r["Symbol"]
                    )

                    st.session_state.top_mover_open = False

                    st.rerun()

    # -----------------------------------------------------
    # SELECTED STOCK
    # -----------------------------------------------------

    selected = (
        st.session_state.selected_stock
    )

    if (
        selected
        and selected in set(
            sdf["Symbol"]
        )
    ):

        show_chart(
            sdf[
                sdf["Symbol"]
                == selected
            ].iloc[0]
        )

    else:

        st.info(
            "Stock select karo, uska Dhan live chart yahan khulega."
        )


# =========================================================
# RUN CONTROL
# =========================================================

if (
    st.session_state.scanner_on
    and market_is_open()
):

    @st.fragment(
        run_every=f"{REFRESH_SECONDS}s"
    )
    def live_heatmap():

        render_heatmap()

    live_heatmap()

else:

    # OFF / market closed:
    # No automatic fragment refresh.
    # Dhan WebSocket already stopped above.

    if st.session_state.scanner_on:

        st.info(
            "Scanner ON hai, lekin market window 09:00-15:30 ke bahar hai. "
            "Dhan live feed band hai."
        )

    else:

        st.info(
            "Scanner OFF hai. Automatic refresh aur Dhan live feed dono band hain."
        )
