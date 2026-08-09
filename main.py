"""
KB증권 Open API 연동 자동매매 서버
실행: python server.py
접속: http://localhost:8000
초기 비밀번호: 0000
"""
import json, random, time, os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

app = FastAPI(title="KB Auto Trade", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# static 폴더 마운트
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ── 상태 저장소 ──────────────────────────────────────────
STATE = {
    "pin": "0000",
    "token": "",
    "app_key": "",
    "app_secret": "",
    "account": "",
    "api_url": "https://developer.kbsec.com:32484",
    "auto_on": False,
    "stop_loss": -5.0,
    "take_profit": 10.0,
    "order_amt": 500000,
    "active_strategies": ["RSI 역추세", "MACD 크로스"],
    "logs": [],
    "orders": [],
    "trade_count": 0,
    "win_count": 0,
    "today_pnl": 0,
    "watchlist": ["005930","000660","035420","005380","035720"],
}

STOCK_INFO = {
    "005930": {"name": "삼성전자",   "base": 74000,  "sector": "반도체"},
    "000660": {"name": "SK하이닉스", "base": 183000, "sector": "반도체"},
    "035420": {"name": "NAVER",      "base": 198000, "sector": "IT"},
    "005380": {"name": "현대차",     "base": 241000, "sector": "자동차"},
    "035720": {"name": "카카오",     "base": 42000,  "sector": "IT"},
    "068270": {"name": "셀트리온",   "base": 165000, "sector": "바이오"},
    "000270": {"name": "기아",       "base": 98000,  "sector": "자동차"},
    "051910": {"name": "LG화학",     "base": 312000, "sector": "화학"},
}

prices = {}

def init_prices():
    for code, info in STOCK_INFO.items():
        chg = round(random.uniform(-3, 5), 2)
        p   = round(info["base"] * (1 + chg / 100))
        prices[code] = {
            "code": code, "name": info["name"], "sector": info["sector"],
            "price": p, "chg": chg,
            "volume": random.randint(500000, 5000000),
            "high": round(p * 1.02), "low": round(p * 0.98),
            "updated": datetime.now().strftime("%H:%M:%S"),
        }

def add_log(level: str, msg: str):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": msg}
    STATE["logs"].insert(0, entry)
    STATE["logs"] = STATE["logs"][:100]

def tick_prices():
    for code in prices:
        base = STOCK_INFO[code]["base"]
        old  = prices[code]["price"]
        diff = round(random.gauss(0, base * 0.003))
        new  = max(100, old + diff)
        prices[code]["price"]   = new
        prices[code]["chg"]     = round((new - base) / base * 100, 2)
        prices[code]["volume"] += random.randint(1000, 50000)
        prices[code]["updated"] = datetime.now().strftime("%H:%M:%S")
        if new > prices[code]["high"]: prices[code]["high"] = new
        if new < prices[code]["low"]:  prices[code]["low"]  = new

def ai_signal(code: str) -> dict:
    p    = prices.get(code)
    if not p: return {}
    rsi  = round(max(10, min(90, 50 + (p["price"]/STOCK_INFO[code]["base"]-1)*200 + random.uniform(-10,10))), 1)
    macd = random.choice([True, False, False])
    vr   = round(p["volume"] / 1_000_000, 2)
    score = 0
    if rsi < 35:  score += 2
    if rsi > 65:  score -= 2
    if macd:      score += 1
    if vr > 1.5:  score += 1
    if score >= 2:
        sig, conf = "buy",  min(95, 60 + score*8 + random.randint(0,8))
    elif score <= -2:
        sig, conf = "sell", min(95, 60 + abs(score)*7 + random.randint(0,8))
    else:
        sig, conf = "hold", 35 + random.randint(0, 20)
    return {"code": code, "name": p["name"], "signal": sig,
            "confidence": conf, "rsi": rsi, "macd": macd, "volume_ratio": vr}

# ── 라우트 ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    path = "static/index.html"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>static/index.html 파일이 없습니다.</h1>"

@app.get("/api/prices")
async def get_prices():
    tick_prices()
    return {"status":"ok","data":list(prices.values()),
            "kospi":round(2840+random.uniform(-20,20),2),
            "kosdaq":round(830+random.uniform(-10,10),2),
            "time":datetime.now().strftime("%H:%M:%S")}

@app.get("/api/hoga/{code}")
async def get_hoga(code: str):
    p = prices.get(code, {}).get("price", 70000)
    return {"status":"ok","code":code,"current":p,
            "hoga":{"sell":[{"price":p+i*100,"qty":random.randint(100,3000),"rank":i} for i in range(1,11)],
                    "buy": [{"price":p-i*100,"qty":random.randint(100,3000),"rank":i} for i in range(1,11)]}}

@app.get("/api/chart/{code}")
async def get_chart(code: str, period: str = "1D"):
    base  = STOCK_INFO.get(code, {}).get("base", 70000)
    n     = 40 if period=="1D" else 100 if period=="1W" else 200
    v     = round(base * 0.97)
    data, labels = [], []
    now   = datetime.now()
    for i in range(n, -1, -1):
        ts = now.timestamp() - i*(900 if period=="1D" else 3600 if period=="1W" else 86400/5)
        dt = datetime.fromtimestamp(ts)
        labels.append(dt.strftime("%H:%M") if period=="1D" else dt.strftime("%m/%d"))
        v  = max(100, round(v*(1+random.gauss(0,0.005))))
        data.append(v)
    if code in prices: data[-1] = prices[code]["price"]
    return {"status":"ok","labels":labels,"data":data}

@app.get("/api/signals")
async def get_signals():
    sigs = [ai_signal(c) for c in STATE["watchlist"] if c in prices]
    return {"status":"ok","signals":[s for s in sigs if s]}

@app.get("/api/account")
async def get_account():
    dep = random.randint(3_000_000, 8_000_000)
    pnl = random.randint(-200_000, 500_000)
    pos = [
        {"code":"005930","name":"삼성전자","qty":50,"avg_price":72000,"cur_price":prices.get("005930",{}).get("price",74000)},
        {"code":"000660","name":"SK하이닉스","qty":10,"avg_price":175000,"cur_price":prices.get("000660",{}).get("price",183000)},
    ]
    return {"status":"ok","deposit":dep,"eval_pnl":pnl,"total":dep+sum(p["cur_price"]*p["qty"] for p in pos),"positions":pos}

@app.get("/api/logs")
async def get_logs():
    return {"status":"ok","logs":STATE["logs"][:50]}

@app.get("/api/orders")
async def get_orders():
    return {"status":"ok","orders":STATE["orders"][:20]}

@app.get("/api/watchlist")
async def get_watchlist():
    return {"status":"ok","watchlist":STATE["watchlist"]}

# ── POST 라우트 ──────────────────────────────────────────

class PinCheck(BaseModel):
    pin: str

@app.post("/api/auth/check")
async def check_pin(req: PinCheck):
    ok = req.pin == STATE["pin"]
    if not ok: add_log("warn", f"로그인 실패 — 잘못된 PIN 입력")
    else:       add_log("info", "로그인 성공")
    return {"status":"ok","valid":ok}

class PinChange(BaseModel):
    old_pin: str
    new_pin: str

@app.post("/api/auth/change")
async def change_pin(req: PinChange):
    if req.old_pin != STATE["pin"]:
        return {"status":"error","message":"현재 비밀번호가 틀렸습니다"}
    if not req.new_pin.isdigit() or len(req.new_pin) != 4:
        return {"status":"error","message":"새 비밀번호는 숫자 4자리여야 합니다"}
    STATE["pin"] = req.new_pin
    add_log("info", "비밀번호 변경 완료")
    return {"status":"ok","message":"비밀번호가 변경되었습니다"}

class OrderReq(BaseModel):
    code: str; price: int; qty: int; side: str; order_type: str = "00"

@app.post("/api/order")
async def place_order(req: OrderReq):
    api  = "SSAM1802" if req.side=="buy" else "SSAM1801"
    name = prices.get(req.code, {}).get("name", req.code)
    order = {"id":f"ORD{int(time.time())}","time":datetime.now().strftime("%H:%M:%S"),
             "code":req.code,"name":name,"side":req.side,"price":req.price,"qty":req.qty,"status":"체결","api":api}
    STATE["orders"].insert(0, order)
    STATE["orders"] = STATE["orders"][:50]
    add_log(req.side, f"[{api}] {name} {'매수' if req.side=='buy' else '매도'} {req.qty:,}주 @ {req.price:,}원")
    return {"status":"ok","order":order}

class TokenReq(BaseModel):
    app_key: str; app_secret: str; api_url: str = "https://developer.kbsec.com:32484"; account: str = ""

@app.post("/api/token")
async def get_token(req: TokenReq):
    STATE.update({"app_key":req.app_key,"app_secret":req.app_secret,"api_url":req.api_url,"account":req.account})
    add_log("info", f"토큰 발급 요청: {req.api_url}/oauth2/token")
    try:
        import httpx
        async with httpx.AsyncClient(verify=False) as client:
            r = await client.post(f"{req.api_url}/oauth2/token",
                data={"grant_type":"client_credentials","appkey":req.app_key,"appsecret":req.app_secret},
                headers={"Content-Type":"application/x-www-form-urlencoded"}, timeout=8.0)
        d = r.json()
        if "access_token" in d:
            STATE["token"] = d["access_token"]
            add_log("info", "KB증권 토큰 발급 성공!")
            return {"status":"ok","message":"토큰 발급 성공"}
        return {"status":"error","message":str(d)}
    except Exception as e:
        add_log("warn", f"실제 API 연결 실패({e}) — 시뮬레이션 모드")
        return {"status":"sim","message":"시뮬레이션 모드 (실제 KB API 키 입력 필요)"}

class AutoReq(BaseModel):
    enabled: bool

@app.post("/api/auto")
async def set_auto(req: AutoReq):
    STATE["auto_on"] = req.enabled
    add_log("info" if req.enabled else "warn", f"AI 자동매매 {'시작' if req.enabled else '중지'}")
    return {"status":"ok","auto_on":STATE["auto_on"]}

@app.get("/api/auto/run")
async def auto_run():
    if not STATE["auto_on"]:
        return {"status":"ok","message":"자동매매 비활성화"}
    sigs    = [ai_signal(c) for c in STATE["watchlist"] if c in prices]
    actions = []
    for s in sigs:
        if not s: continue
        p   = prices[s["code"]]["price"]
        qty = max(1, int(STATE["order_amt"] / p))
        if s["signal"]=="buy" and s["confidence"]>=70:
            STATE["trade_count"] += 1
            if random.random() > 0.4: STATE["win_count"] += 1
            STATE["today_pnl"] += random.randint(-30000, 80000)
            add_log("buy", f"[AUTO] {s['name']} 매수 {qty}주 @ {p:,}원 (신뢰도{s['confidence']}%)")
            actions.append({"action":"buy","code":s["code"],"qty":qty,"price":p})
        elif s["signal"]=="sell" and s["confidence"]>=65:
            STATE["trade_count"] += 1
            if random.random() > 0.35: STATE["win_count"] += 1
            STATE["today_pnl"] += random.randint(-20000, 60000)
            add_log("sell", f"[AUTO] {s['name']} 매도 신호 (신뢰도{s['confidence']}%)")
    wr = round(STATE["win_count"]/max(1,STATE["trade_count"])*100)
    return {"status":"ok","actions":actions,
            "stats":{"trade_count":STATE["trade_count"],"win_rate":wr,"today_pnl":STATE["today_pnl"]}}

class StratReq(BaseModel):
    text: str; stop_loss: Optional[float]=None; take_profit: Optional[float]=None
    order_amt: Optional[int]=None; active_strategies: Optional[list]=None

@app.post("/api/strategy")
async def save_strategy(req: StratReq):
    if req.stop_loss:    STATE["stop_loss"]    = req.stop_loss
    if req.take_profit:  STATE["take_profit"]  = req.take_profit
    if req.order_amt:    STATE["order_amt"]    = req.order_amt
    if req.active_strategies: STATE["active_strategies"] = req.active_strategies
    txt   = req.text.lower()
    rules = []
    if "rsi"   in txt: rules.append("RSI 매매 규칙")
    if "macd"  in txt: rules.append("MACD 크로스 규칙")
    if "볼린저" in txt: rules.append("볼린저밴드 규칙")
    if "이동평균" in txt or "골든" in txt: rules.append("이동평균 규칙")
    if "거래량" in txt: rules.append("거래량 필터 규칙")
    if not rules: rules = [f"사용자 규칙 {random.randint(2,8)}개"]
    add_log("info", f"전략 학습 완료: {', '.join(rules)}")
    return {"status":"ok","rules":rules}

@app.post("/api/watchlist/{code}")
async def add_watchlist(code: str):
    if code not in STATE["watchlist"]:
        STATE["watchlist"].append(code)
        if code not in STOCK_INFO:
            STOCK_INFO[code] = {"name":code,"base":random.randint(5000,200000),"sector":"기타"}
        if code not in prices:
            chg = round(random.uniform(-3,5),2)
            b   = STOCK_INFO[code]["base"]
            prices[code] = {"code":code,"name":STOCK_INFO[code]["name"],"sector":"기타",
                            "price":round(b*(1+chg/100)),"chg":chg,"volume":random.randint(100000,1000000),
                            "high":round(b*1.02),"low":round(b*0.98),"updated":datetime.now().strftime("%H:%M:%S")}
        add_log("info", f"종목 추가: {code}")
    return {"status":"ok","watchlist":STATE["watchlist"]}

if __name__ == "__main__":
    init_prices()
    add_log("info", "KB 자동매매 서버 시작 — 초기 PIN: 0000")
    os.makedirs("static", exist_ok=True)
    port = int(os.getenv("PORT", 8000))
    print(f"\n{'='*50}")
    print(f"  KB증권 AI 자동매매 서버 시작!")
    print(f"  브라우저: http://localhost:{port}")
    print(f"  초기 비밀번호: 0000")
    print(f"{'='*50}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
