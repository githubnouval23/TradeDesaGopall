import requests
import re
import time
import json
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN belum di set di Railway Variables")

CAPITAL = 1000000
MAX_DAILY_LOSS_PERCENT = 6
COOLDOWN_SECONDS = 120
MAX_SIGNAL_PER_HOUR = 2

DATA_FILE = "trade_data.json"

last_signal_time = {}
auto_signal_counter = {"hour": datetime.now().hour, "count": 0}

SCAN_PAIRS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT",
    "ARBUSDT","AVAXUSDT","DOGEUSDT","LINKUSDT","HYPEUSDT"
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

# ================= EXCHANGE DETECTOR =================

def bybit_pair_exists(symbol):
    try:
        r = requests.get(
            f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}",
            timeout=5
        ).json()
        return r.get("retCode")==0 and r.get("result",{}).get("list")
    except:
        return False

def binance_pair_exists(symbol):
    try:
        r = requests.get(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",
            timeout=5
        )
        return r.status_code==200
    except:
        return False

def detect_exchange(symbol):
    if bybit_pair_exists(symbol):
        return "BYBIT"
    if binance_pair_exists(symbol):
        return "BINANCE"
    return None

# ================= PRICE =================

def get_price(symbol, exchange):
    try:
        if exchange=="BYBIT":
            r = requests.get(
                f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}",
                timeout=5
            ).json()
            return float(r["result"]["list"][0]["lastPrice"])

        if exchange=="BINANCE":
            r = requests.get(
                f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",
                timeout=5
            ).json()
            return float(r["price"])
    except:
        return None

# ================= KLINE =================

def get_kline(symbol, interval, exchange, limit=100):
    try:
        if exchange=="BYBIT":
            r = requests.get(
                f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}",
                timeout=5
            ).json()
            if r.get("retCode")!=0:
                return []
            return r["result"]["list"]

        if exchange=="BINANCE":
            r = requests.get(
                f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}m&limit={limit}",
                timeout=5
            ).json()
            return r
    except:
        return []

# ================= TREND =================

def get_trend(symbol, interval, exchange):
    try:
        data = get_kline(symbol, interval, exchange, 100)
        if len(data)<21:
            return "neutral",0

        if exchange=="BYBIT":
            closes=[float(c[4]) for c in data[::-1]]
        else:
            closes=[float(c[4]) for c in data]

        ema9=sum(closes[-9:])/9
        ema21=sum(closes[-21:])/21

        return ("bullish" if ema9>ema21 else "bearish"), abs(ema9-ema21)/ema21*100
    except:
        return "neutral",0

# ================= CORE =================

def analyze_pair(pair):

    exchange = detect_exchange(pair)
    if not exchange:
        return "PAIR_NOT_FOUND"

    price = get_price(pair, exchange)
    if not price:
        return None

    pair15,_ = get_trend(pair,"15",exchange)
    pair5,_ = get_trend(pair,"5",exchange)
    btc1h,_ = get_trend("BTCUSDT","60",exchange)

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

    if score<70:
        return None

    sl=round(price*0.995,4) if signal=="LONG" else round(price*1.005,4)
    tp=round(price*1.01,4) if signal=="LONG" else round(price*0.99,4)

    rr=abs(tp-price)/abs(price-sl)

    return pair,signal,price,sl,tp,rr,score,exchange

# ================= AUTO =================

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
            pair,signal,price,sl,tp,rr,score,exchange=result

            context.bot.send_message(
                chat_id=context.job.context,
                text=f"""
🔥 AUTO SIGNAL TradeDesaGopall

Exchange: {exchange}
{pair} {signal}
Entry: {round(price,4)}
SL: {sl}
TP: {tp}
RR: {round(rr,2)}
Score: {score}
"""
            )
            break

# ================= MANUAL =================

def handle_message(update: Update, context: CallbackContext):

    text=update.message.text.upper().strip()

    if re.match(r"^[A-Z]{3,15}USDT$",text):

        result=analyze_pair(text)

        if result=="PAIR_NOT_FOUND":
            update.message.reply_text("❌ Pair tidak tersedia di Bybit & Binance Futures.")
            return

        if not result:
            update.message.reply_text("❌ TradeDesaGopall Tidak ada setup kuat saat ini.")
            return

        pair,signal,price,sl,tp,rr,score,exchange=result

        update.message.reply_text(f"""
📊 MANUAL CONFIRM TradeDesaGopall

Exchange: {exchange}
{pair} {signal}
Entry: {round(price,4)}
SL: {sl}
TP: {tp}
RR: {round(rr,2)}
Score: {score}
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
