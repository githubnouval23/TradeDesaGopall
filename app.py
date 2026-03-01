import requests
import re
import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN belum di set di Railway Variables")

CAPITAL = 1000000
RISK_PERCENT = 0.02
MAX_SIGNAL_PER_HOUR = 2

DATA_FILE = "performance.json"

auto_signal_counter = {"hour": datetime.now().hour, "count": 0}

SCAN_PAIRS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT",
    "ARBUSDT","AVAXUSDT","DOGEUSDT","LINKUSDT","HYPEUSDT"
]

# ================= PERFORMANCE TRACKER =================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"total":0,"wins":0,"losses":0}
    with open(DATA_FILE,"r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE,"w") as f:
        json.dump(data,f)

performance = load_data()

# ================= BINANCE API =================

def get_price(symbol):
    try:
        r = requests.get(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",
            timeout=10
        ).json()
        return float(r["price"])
    except:
        return None

def get_kline(symbol, interval, limit=100):
    try:
        return requests.get(
            f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}m&limit={limit}",
            timeout=10
        ).json()
    except:
        return []

# ================= INDICATORS =================

def get_trend(symbol, interval):
    data = get_kline(symbol, interval, 100)
    if len(data) < 21:
        return "neutral", 0

    closes = [float(c[4]) for c in data]

    ema9 = sum(closes[-9:]) / 9
    ema21 = sum(closes[-21:]) / 21

    return ("bullish" if ema9 > ema21 else "bearish"), abs(ema9-ema21)/ema21*100

def get_atr(symbol):
    data = get_kline(symbol, "15", 20)
    if len(data) < 20:
        return 0
    ranges = [float(c[2])-float(c[3]) for c in data]
    return sum(ranges)/len(ranges)

def volume_spike(symbol):
    data = get_kline(symbol, "15", 20)
    if len(data) < 20:
        return False
    vols = [float(c[5]) for c in data]
    return vols[-1] > (sum(vols[:-1])/len(vols[:-1]))*1.5

def breakout(symbol):
    data = get_kline(symbol, "15", 20)
    if len(data) < 20:
        return False
    highs = [float(c[2]) for c in data[:-1]]
    lows = [float(c[3]) for c in data[:-1]]
    last_close = float(data[-1][4])
    return last_close > max(highs) or last_close < min(lows)

def detect_regime():
    _, dist = get_trend("BTCUSDT", "60")
    return "TRENDING" if dist > 0.3 else "RANGING"

# ================= CORE ENGINE =================

def analyze_pair(pair):

    price = get_price(pair)
    if not price:
        return "PAIR_NOT_FOUND"

    pair15,_ = get_trend(pair,"15")
    pair5,_ = get_trend(pair,"5")
    btc1h,_ = get_trend("BTCUSDT","60")
    btc15,_ = get_trend("BTCUSDT","15")

    regime = detect_regime()

    score = 50

    if pair15=="bullish" and btc1h=="bullish":
        signal="LONG"
        score+=25
    elif pair15=="bearish" and btc1h=="bearish":
        signal="SHORT"
        score+=25
    else:
        return None

    if pair5==pair15:
        score+=15

    if btc15==pair15:
        score+=10

    if volume_spike(pair):
        score+=10

    if breakout(pair):
        score+=10

    atr = get_atr(pair)
    if atr==0:
        return None

    sl_dist = atr*1.2
    tp_dist = atr*2

    if signal=="LONG":
        sl=round(price-sl_dist,4)
        tp=round(price+tp_dist,4)
    else:
        sl=round(price+sl_dist,4)
        tp=round(price-tp_dist,4)

    rr = abs(tp-price)/abs(price-sl)

    min_rr = 2 if regime=="TRENDING" else 1.3

    if rr < min_rr:
        return None

    risk_amount = CAPITAL*RISK_PERCENT
    position_size = risk_amount/abs(price-sl)

    if score>=90:
        label="🎯 SNIPER"
    elif score>=80:
        label="🔥 STRONG"
    elif score>=70:
        label="✅ VALID"
    else:
        label="⚠ WEAK"

    return pair,signal,price,sl,tp,rr,score,label,regime,round(position_size,2)

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

        if result and result!="PAIR_NOT_FOUND":
            auto_signal_counter["count"]+=1
            pair,signal,price,sl,tp,rr,score,label,regime,pos_size=result

            context.bot.send_message(
                chat_id=context.job.context,
                text=f"""
🔥 AUTO SIGNAL TraderDesaGopall

{label}
{pair} {signal}

Entry: {round(price,4)}
SL: {sl}
TP: {tp}

RR: {round(rr,2)}
Regime: {regime}
Confidence: {score}/100
Position Size: {pos_size}
"""
            )
            break

# ================= MANUAL =================

def handle_message(update: Update, context: CallbackContext):

    text=update.message.text.upper().strip()

    if re.match(r"^[A-Z]{3,15}USDT$",text):

        result=analyze_pair(text)

        if result=="PAIR_NOT_FOUND":
            update.message.reply_text("❌ TraderDesaGopall Konfirmasi Pair tidak tersedia di Binance Futures.")
            return

        if not result:
            update.message.reply_text("❌ TraderDesaGopall Konfirmasi Tidak ada setup kuat saat ini.")
            return

        pair,signal,price,sl,tp,rr,score,label,regime,pos_size=result

        winrate = (performance["wins"]/performance["total"]*100) if performance["total"]>0 else 0

        update.message.reply_text(f"""
📊 MANUAL CONFIRM TraderDesaGopall

{label}
{pair} {signal}

Entry: {round(price,4)}
SL: {sl}
TP: {tp}

RR: {round(rr,2)}
Regime: {regime}
Confidence: {score}/100
Position Size: {pos_size}

Winrate Bot: {round(winrate,2)}%
""")
        return

    update.message.reply_text("Kirim contoh:\nBTCUSDT")

# ================= START =================

def main():
    updater=Updater(BOT_TOKEN,use_context=True)
    dp=updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.job_queue.run_repeating(
        scan_market,
        interval=300,
        first=15,
        context="8602327142"
    )

    updater.start_polling()
    updater.idle()

if __name__=="__main__":
    main()
