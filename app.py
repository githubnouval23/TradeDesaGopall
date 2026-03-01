import requests
import re
import time
import json
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

BOT_TOKEN = "8602327142:AAExdkvQ7Iazx1_EmHm1flKHawnt_w78O9w"

CAPITAL = 1000000
MAX_DAILY_LOSS_PERCENT = 6
COOLDOWN_SECONDS = 120
MAX_SIGNAL_PER_HOUR = 2

DATA_FILE = "trade_data.json"

last_signal_time = {}
auto_signal_counter = {"hour": datetime.now().hour, "count": 0}

SCAN_PAIRS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT",
    "ARBUSDT","AVAXUSDT","DOGEUSDT","LINKUSDT", "HYPEUSDT"
]

# ================= DATA =================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"total":0,"wins":0,"losses":0,"daily_loss":0,"last_day":datetime.now().strftime("%Y-%m-%d")}
    with open(DATA_FILE,"r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f)

trade_data = load_data()

def reset_daily():
    today = datetime.now().strftime("%Y-%m-%d")
    if trade_data["last_day"] != today:
        trade_data["daily_loss"] = 0
        trade_data["last_day"] = today
        save_data(trade_data)

# ================= MARKET =================

def get_price(symbol):
    try:
        r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}",timeout=5).json()
        return float(r["result"]["list"][0]["lastPrice"])
    except:
        return None

def get_kline(symbol, interval, limit=100):
    r = requests.get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}",timeout=5).json()
    if r["retCode"]!=0:
        return []
    return r["result"]["list"]

def get_trend(symbol, interval):
    try:
        data = get_kline(symbol, interval, 100)
        closes=[float(c[4]) for c in data[::-1]]
        ema9=sum(closes[-9:])/9
        ema21=sum(closes[-21:])/21
        return ("bullish" if ema9>ema21 else "bearish"), abs(ema9-ema21)/ema21*100
    except:
        return "neutral",0

def get_atr(symbol):
    try:
        data=get_kline(symbol,"15",20)
        ranges=[float(c[2])-float(c[3]) for c in data]
        return sum(ranges)/len(ranges)
    except:
        return 0

def is_sideways(symbol):
    try:
        data=get_kline(symbol,"15",30)
        highs=[float(c[2]) for c in data]
        lows=[float(c[3]) for c in data]
        return (max(highs)-min(lows)) < (sum([h-l for h,l in zip(highs,lows)])/len(highs))*2
    except:
        return False

def detect_regime():
    _,dist=get_trend("BTCUSDT","60")
    return "TRENDING" if dist>0.3 else "RANGING"

def volume_spike(symbol):
    try:
        data=get_kline(symbol,"15",20)
        vols=[float(c[5]) for c in data]
        return vols[-1] > (sum(vols[:-1])/len(vols[:-1]))*1.5
    except:
        return False

def breakout(symbol):
    try:
        data=get_kline(symbol,"15",20)
        highs=[float(c[2]) for c in data[:-1]]
        last_close=float(data[0][4])
        return last_close>max(highs) or last_close<min(highs)
    except:
        return False

# ================= CORE ANALYSIS =================

def analyze_pair(pair):
    price=get_price(pair)
    if not price: return None

    if is_sideways(pair): return None

    btc1h,_=get_trend("BTCUSDT","60")
    pair15,dist15=get_trend(pair,"15")
    pair5,_=get_trend(pair,"5")
    regime=detect_regime()

    score=50

    if pair15=="bullish" and btc1h=="bullish":
        signal="LONG"
        score+=30
    elif pair15=="bearish" and btc1h=="bearish":
        signal="SHORT"
        score+=30
    else:
        return None

    if pair5==pair15:
        score+=15

    if volume_spike(pair): score+=10
    if breakout(pair): score+=10

    atr=get_atr(pair)
    sl_dist=atr*1.2
    tp_dist=atr*2

    if signal=="LONG":
        sl=round(price-sl_dist,4)
        tp=round(price+tp_dist,4)
    else:
        sl=round(price+sl_dist,4)
        tp=round(price-tp_dist,4)

    rr=abs(tp-price)/abs(price-sl)
    min_rr=1.8 if regime=="TRENDING" else 1.3

    if rr<min_rr: return None

    if score<75: return None

    return pair,signal,price,sl,tp,rr,score,regime

# ================= AUTO SCAN =================

def scan_market(context: CallbackContext):
    global auto_signal_counter
    current_hour=datetime.now().hour

    if auto_signal_counter["hour"]!=current_hour:
        auto_signal_counter={"hour":current_hour,"count":0}

    if auto_signal_counter["count"]>=MAX_SIGNAL_PER_HOUR:
        return

    for pair in SCAN_PAIRS:
        result=analyze_pair(pair)
        if result:
            auto_signal_counter["count"]+=1
            pair,signal,price,sl,tp,rr,score,regime=result

            context.bot.send_message(
                chat_id=context.job.context,
                text=f"""
🔥 AUTO SIGNAL

{pair} {signal}
Entry: {round(price,4)}
SL: {sl}
TP: {tp}
RR: {round(rr,2)}
Score: {score}
Regime: {regime}
"""
            )
            break

# ================= MANUAL =================

def handle_message(update: Update, context: CallbackContext):
    reset_daily()

    text=update.message.text.upper().strip()

    # Kalau cuma kirim pair saja
    if re.match(r"^[A-Z]{3,10}USDT$",text):
        pair=text
        result=analyze_pair(pair)
        if not result:
            update.message.reply_text("❌ Tidak ada setup kuat saat ini.")
            return

        pair,signal,price,sl,tp,rr,score,regime=result

        update.message.reply_text(f"""
📊 MANUAL CONFIRM

{pair} {signal}
Entry: {round(price,4)}
SL: {sl}
TP: {tp}
RR: {round(rr,2)}
Score: {score}
Regime: {regime}
""")
        return

    update.message.reply_text("Kirim contoh:\nSOLUSDT")

# ================= START =================

def main():
    updater=Updater(BOT_TOKEN,use_context=True)
    dp=updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.job_queue.run_repeating(
        scan_market,
        interval=300,
        first=15,
        context="GANTI_DENGAN_CHAT_ID_KAMU"
    )

    updater.start_polling()
    updater.idle()

if __name__=="__main__":
    main()
