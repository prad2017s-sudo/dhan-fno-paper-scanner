import os, time, threading
from datetime import datetime, date, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from io import BytesIO
import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from dhanhq import DhanContext, MarketFeed

st.set_page_config(page_title="Dhan Live Scanner", page_icon="ðŸ“ˆ", layout="wide")
IST = ZoneInfo("Asia/Kolkata")
API_URL = "https://api.dhan.co/v2/charts/intraday"
WATCHLIST = {"RELIANCE":"2885","BHARTIARTL":"10604","HDFCBANK":"1333","ICICIBANK":"4963","SBIN":"3045","TCS":"11536","BAJFINANCE":"317","LT":"11483","LICI":"9480","HINDUNILVR":"1394"}
COLUMNS = ["Date","Time","Symbol","Signal","Breakout Price","Trigger Candle","Trigger Candle Type","Trigger High","Trigger Low","Trigger Volume"]

def now_ist(): return datetime.now(IST)
def market_is_open():
    n=now_ist()
    return n.weekday()<5 and dt_time(9,15)<=n.time()<=dt_time(15,15)

def credentials():
    try:
        return str(st.secrets.get("DHAN_ACCESS_TOKEN",os.getenv("DHAN_ACCESS_TOKEN",""))).strip(), str(st.secrets.get("DHAN_CLIENT_ID",os.getenv("DHAN_CLIENT_ID",""))).strip()
    except Exception:
        return os.getenv("DHAN_ACCESS_TOKEN","").strip(), os.getenv("DHAN_CLIENT_ID","").strip()

def fetch_intraday(token, symbol, sid, day=None):
    day = day or now_ist().date()
    payload={"securityId":str(sid),"exchangeSegment":"NSE_EQ","instrument":"EQUITY","interval":"5","oi":False,"fromDate":day.strftime("%Y-%m-%d"),"toDate":(day+timedelta(days=1)).strftime("%Y-%m-%d")}
    r=requests.post(API_URL,headers={"access-token":token,"Content-Type":"application/json","Accept":"application/json"},json=payload,timeout=20)
    if r.status_code==429: raise RuntimeError("Dhan historical API rate limit (HTTP 429). Wait and retry.")
    r.raise_for_status()
    d=r.json()
    if not isinstance(d,dict) or not d.get("timestamp"): return pd.DataFrame(columns=["DateTime","Open","High","Low","Close","Volume","Symbol"])
    df=pd.DataFrame({"timestamp":d.get("timestamp",[]),"Open":d.get("open",[]),"High":d.get("high",[]),"Low":d.get("low",[]),"Close":d.get("close",[]),"Volume":d.get("volume",[])})
    df["DateTime"]=pd.to_datetime(df.pop("timestamp"),unit="s",utc=True).dt.tz_convert(IST)
    df["Symbol"]=symbol
    for c in ["Open","High","Low","Close","Volume"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.dropna(subset=["DateTime","Open","High","Low","Close"])
    df=df[df["DateTime"].dt.date==day]
    df["Volume"]=df["Volume"].fillna(0).astype("int64")
    return df[["DateTime","Open","High","Low","Close","Volume","Symbol"]].sort_values("DateTime").reset_index(drop=True)

class Scanner:
    def __init__(self):
        self.lock=threading.RLock(); self.direction=None; self.status="Loading historical opening candles..."
        self.started=False; self.records=[]; self.items={}; self.token=""; self.client_id=""; self.chart=pd.DataFrame()
        for sym,sid in WATCHLIST.items():
            self.items[sid]={"symbol":sym,"ltp":None,"last_cum_volume":None,"candle":None,"completed":[],"baseline_min":None,"baseline_ready":False,"reference":None,"feed_time":None,"history_error":""}
    def load_history(self):
        self.token,self.client_id=credentials()
        if not self.token or not self.client_id:
            self.status="Credentials missing: add DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID in Streamlit Secrets."
            return
        errors=[]; opening_times={dt_time(9,15),dt_time(9,20),dt_time(9,25)}
        for sym,sid in WATCHLIST.items():
            try:
                df=fetch_intraday(self.token,sym,sid)
                with self.lock:
                    self.chart=pd.concat([self.chart,df],ignore_index=True)
                    op=df[df["DateTime"].dt.time.isin(opening_times)].sort_values("DateTime")
                    item=self.items[sid]
                    if len(op)==3 and now_ist().time()>=dt_time(9,30):
                        item["completed"]=[{"start":r.DateTime.to_pydatetime(),"open":float(r.Open),"high":float(r.High),"low":float(r.Low),"close":float(r.Close),"volume":int(r.Volume)} for r in op.itertuples(index=False)]
                        item["baseline_min"]=min(c["volume"] for c in item["completed"]); item["baseline_ready"]=True
                    elif now_ist().time()>=dt_time(9,30): item["history_error"]="Opening 3 candles not returned"
            except Exception as e:
                errors.append(f"{sym}: {str(e)[:70]}")
                self.items[sid]["history_error"]=str(e)[:100]
            time.sleep(.35)
        self.status=("History loaded; some errors: "+"; ".join(errors[:3])) if errors else "Opening candles loaded; starting live feed..."
    def start(self):
        with self.lock:
            if self.started:return
            self.started=True
        self.load_history()
        threading.Thread(target=self.feed_loop,daemon=True,name="dhan-live-feed").start()
    def select(self,direction):
        with self.lock:
            self.direction=direction
            for item in self.items.values(): item["reference"]=None
            self.status=f"{direction} selected â€” waiting for qualifying candle and breakout"
    def record(self,item,direction,price,ref):
        t=now_ist()
        with self.lock:
            self.records.append({"Date":t.strftime("%Y-%m-%d"),"Time":t.strftime("%H:%M:%S"),"Symbol":item["symbol"],"Signal":direction,"Breakout Price":round(price,2),"Trigger Candle":ref["start"].strftime("%H:%M"),"Trigger Candle Type":ref["kind"],"Trigger High":round(ref["high"],2),"Trigger Low":round(ref["low"],2),"Trigger Volume":int(ref["volume"])})
            item["reference"]=None
    def feed_loop(self):
        instruments=[(MarketFeed.NSE,sid,MarketFeed.Full) for sid in WATCHLIST.values()]
        wait=10
        while True:
            feed=None
            try:
                if not self.token or not self.client_id:self.token,self.client_id=credentials()
                if not self.token or not self.client_id:
                    self.status="Dhan credentials missing"; time.sleep(30); continue
                feed=MarketFeed(DhanContext(self.client_id,self.token),instruments,version="v2")
                self.status="Connecting to Dhan WebSocket..."
                feed.run_forever()
                self.status="WebSocket connected"; wait=10
                while True:
                    packet=feed.get_data()
                    if isinstance(packet,dict): self.on_tick(packet)
                    elif isinstance(packet,list):
                        for p in packet:
                            if isinstance(p,dict): self.on_tick(p)
            except Exception as e:
                self.status=f"Feed error/reconnecting in {wait}s: {str(e)[:120]}"
                try:
                    if feed: feed.close_connection()
                except Exception: pass
                time.sleep(wait); wait=min(wait*2,60)
    def on_tick(self,p):
        sid=str(p.get("security_id",p.get("securityId","")))
        if sid not in self.items:return
        try: price=float(p.get("LTP",p.get("ltp",0))); cv=int(p.get("volume",p.get("total_volume",0)) or 0)
        except (TypeError,ValueError):return
        if price<=0:return
        stamp=now_ist(); item=self.items[sid]
        with self.lock: item["ltp"]=price; item["feed_time"]=stamp.strftime("%H:%M:%S"); direction=self.direction
        prev=item["last_cum_volume"]
        delta=max(0,cv-prev) if prev is not None and cv>=prev else 0
        item["last_cum_volume"]=cv
        start=stamp.replace(minute=(stamp.minute//5)*5,second=0,microsecond=0)
        c=item["candle"]
        if c is None or c["start"]!=start:
            if c is not None:
                item["completed"].append(c); item["completed"]=item["completed"][-100:]
            c={"start":start,"open":price,"high":price,"low":price,"close":price,"volume":delta}; item["candle"]=c
        else:
            c["high"]=max(c["high"],price); c["low"]=min(c["low"],price); c["close"]=price; c["volume"]+=delta
        if not market_is_open() or direction not in ("BUY","SELL") or stamp.time()<dt_time(9,30) or not item["baseline_ready"]:return
        completed=item["completed"]
        if not completed:return
        latest=completed[-1]
        if latest["start"]<start and latest["start"]!=item.get("last_checked_reference"):
            item["last_checked_reference"]=latest["start"]
            if latest["volume"]<item["baseline_min"]:
                if direction=="BUY" and latest["close"]<latest["open"]: item["reference"]={**latest,"kind":"RED"}
                elif direction=="SELL" and latest["close"]>latest["open"]: item["reference"]={**latest,"kind":"GREEN"}
        ref=item["reference"]
        if not ref or start<=ref["start"]:return
        if direction=="BUY" and ref["kind"]=="RED" and price>ref["high"]:self.record(item,"BUY",price,ref)
        elif direction=="SELL" and ref["kind"]=="GREEN" and price<ref["low"]:self.record(item,"SELL",price,ref)

@st.cache_resource
def get_scanner(): return Scanner()
scanner=get_scanner(); scanner.start()
st.title("ðŸ“ˆ Dhan Live BUY / SELL Scanner")
st.caption("NSE cash watchlist | 09:15â€“15:15 IST | Signals only â€” no automatic orders")
a,b=st.columns(2)
with a:
    if st.button("ðŸŸ¢ BUY",use_container_width=True):scanner.select("BUY")
with b:
    if st.button("ðŸ”´ SELL",use_container_width=True):scanner.select("SELL")
with scanner.lock:
    status=scanner.status; direction=scanner.direction; records=list(scanner.records); chart=scanner.chart.copy()
    prices=[{"Symbol":x["symbol"],"LTP":x["ltp"],"Last Feed Time":x["feed_time"],"Opening Min Volume":x["baseline_min"],"Opening 3 Candles Ready":x["baseline_ready"],"History Error":x["history_error"]} for x in scanner.items.values()]
st.write("**Scanner status:**",status); st.write("**Selected direction:**",direction or "Not selected")
st.info("BUY: à¤•à¤® à¤µà¥‰à¤²à¥à¤¯à¥‚à¤® à¤µà¤¾à¤²à¥€ red candle à¤•à¥‡ High à¤•à¥‡ à¤Šà¤ªà¤° price à¤œà¤¾à¤¤à¥‡ à¤¹à¥€ signal. SELL: à¤•à¤® à¤µà¥‰à¤²à¥à¤¯à¥‚à¤® à¤µà¤¾à¤²à¥€ green candle à¤•à¥‡ Low à¤•à¥‡ à¤¨à¥€à¤šà¥‡ price à¤œà¤¾à¤¤à¥‡ à¤¹à¥€ signal.")
st.subheader("Live Prices and Opening Volume")
st.dataframe(pd.DataFrame(prices),use_container_width=True,hide_index=True)

st.subheader("Today's Full 5-Minute Chart")
if st.button("ðŸ“Š Reload Today's Full Chart from Dhan",use_container_width=True):
    token,client_id=credentials()
    if not token or not client_id: st.error("Streamlit Secrets à¤®à¥‡à¤‚ DHAN_ACCESS_TOKEN à¤”à¤° DHAN_CLIENT_ID à¤¸à¥‡à¤Ÿ à¤•à¤°à¥‡à¤‚.")
    else:
        frames=[]; errors=[]; progress=st.progress(0)
        for i,(sym,sid) in enumerate(WATCHLIST.items(),1):
            try:
                d=fetch_intraday(token,sym,sid)
                if not d.empty:frames.append(d)
            except Exception as e:errors.append(f"{sym}: {str(e)[:70]}")
            progress.progress(i/len(WATCHLIST)); time.sleep(.35)
        if frames:
            st.session_state["today_chart"]=pd.concat(frames,ignore_index=True).sort_values(["Symbol","DateTime"])
            st.success(f"Loaded {len(st.session_state['today_chart'])} five-minute candles.")
        if errors:st.warning("Some symbols failed: "+"; ".join(errors[:4]))
if "today_chart" in st.session_state:chart=st.session_state["today_chart"]
if not chart.empty:
    opts=["All"]+sorted(chart["Symbol"].dropna().unique().tolist())
    sym=st.selectbox("Chart symbol",opts); view=chart if sym=="All" else chart[chart["Symbol"]==sym]
    st.dataframe(view,use_container_width=True,hide_index=True)
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine="openpyxl") as w:view.to_excel(w,index=False,sheet_name="5-Min Chart")
    st.download_button("â¬‡ï¸ Download Chart Excel",buf.getvalue(),f"dhan_5min_chart_{now_ist():%Y%m%d}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
else:st.caption("à¤ªà¥‚à¤°à¥‡ à¤¦à¤¿à¤¨ à¤•à¤¾ chart à¤¦à¥‡à¤–à¤¨à¥‡ à¤•à¥‡ à¤²à¤¿à¤ à¤Šà¤ªà¤° button à¤¦à¤¬à¤¾à¤à¤.")
st.subheader("Signal Records")
rdf=pd.DataFrame(records,columns=COLUMNS); st.dataframe(rdf,use_container_width=True,hide_index=True)
buf=BytesIO()
with pd.ExcelWriter(buf,engine="openpyxl") as w:
    rdf.to_excel(w,index=False,sheet_name="Signals"); pd.DataFrame(prices).to_excel(w,index=False,sheet_name="Live Status")
st.download_button("â¬‡ï¸ Download Signals Excel",buf.getvalue(),f"dhan_signals_{now_ist():%Y%m%d}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
st.caption("Current IST: "+now_ist().strftime("%d-%m-%Y %H:%M:%S"))
st.caption("Live feed may pause if Streamlit/browser sleeps or Dhan returns HTTP 429. No orders are placed automatically.")
st_autorefresh(interval=10000,key="refresh_scanner")
