import requests
import re
import os
import threading
import time
from datetime import datetime
from flask import Flask, request
from telegram import Bot, Update

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN or not WEBHOOK_URL or not CHAT_ID:
    raise Exception("BOT_TOKEN / WEBHOOK_URL / CHAT_ID belum diset")

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

SCAN_INTERVAL = 300
MAX_SIGNAL_PER_HOUR = 2

auto_signal_counter = {"hour": datetime.now().hour, "count": 0}

SCAN_PAIRS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT",
    "ARBUSDT","AVAXUSDT","DOGEUSDT","LINKUSDT"
]

BASE_URL = "https://api.binance.com"

# ================= BINANCE =================

def get_price(symbol):
    try:
        r = requests.get(
    f"{BASE_URL}/api/v3/ticker/price?symbol={symbol}",
    timeout=10
)

        if "code" in data:
            return None

        return float(data["price"])
    except:
        return None


def get_kline(symbol, interval, limit=100):
    try:
       r = requests.get(
    f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}m&limit={limit}",
    timeout=10
)
        return r.json()
    except:
        return []

# ================= INDICATORS =================

def get_trend(symbol, interval):
    data = get_kline(symbol, interval, 100)
    if len(data) < 21:
        return None

    closes = [float(c[4]) for c in data]

    ema9 = sum(closes[-9:]) / 9
    ema21 = sum(closes[-21:]) / 21

    return "bullish" if ema9 > ema21 else "bearish"


def get_atr(symbol):
    data = get_kline(symbol, "15", 20)
    if len(data) < 20:
        return 0

    ranges = [float(c[2]) - float(c[3]) for c in data]
    return sum(ranges) / len(ranges)

# ================= ANALYSIS =================

def analyze_pair(pair):

    price = get_price(pair)
    if not price:
        return None

    pair15 = get_trend(pair,"15")
    pair5 = get_trend(pair,"5")
    btc1h = get_trend("BTCUSDT","60")

    if not pair15 or not btc1h:
        return None

    score = 50

    if pair15 == "bullish" and btc1h == "bullish":
        signal="LONG"
        score+=25
    elif pair15 == "bearish" and btc1h == "bearish":
        signal="SHORT"
        score+=25
    else:
        return None

    if pair5 == pair15:
        score+=15

    atr = get_atr(pair)
    if atr == 0:
        return None

    sl = round(price - atr*1.2,4) if signal=="LONG" else round(price + atr*1.2,4)
    tp = round(price + atr*2,4) if signal=="LONG" else round(price - atr*2,4)

    rr = abs(tp-price)/abs(price-sl)

    if rr < 1.8:
        return None

    return pair, signal, price, sl, tp, rr, score

# ================= AUTO SCANNER =================

def auto_scan_loop():
    global auto_signal_counter

    print("AUTO SCANNER STARTED")

    while True:
        try:
            current_hour = datetime.now().hour

            if auto_signal_counter["hour"] != current_hour:
                auto_signal_counter = {"hour": current_hour, "count": 0}

            if auto_signal_counter["count"] < MAX_SIGNAL_PER_HOUR:

                for pair in SCAN_PAIRS:

                    result = analyze_pair(pair)

                    if result:

                        auto_signal_counter["count"] += 1
                        pair, signal, price, sl, tp, rr, score = result

                        print("SIGNAL:", pair, signal)

                        bot.send_message(
                            chat_id=CHAT_ID,
                            text=f"""
🔥 AUTO SIGNAL FUTURES

{pair} {signal}

Entry: {round(price,4)}
SL: {sl}
TP: {tp}

RR: {round(rr,2)}
Confidence: {score}/100
"""
                        )

                        break

        except Exception as e:
            print("AUTO ERROR:", e)

        time.sleep(SCAN_INTERVAL)

# ================= WEBHOOK =================

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)

    if update.message and update.message.text:
        text = update.message.text.upper().strip()

        if re.match(r"^[A-Z]{3,15}USDT$", text):

            result = analyze_pair(text)

            if not result:
                bot.send_message(
                    chat_id=update.message.chat_id,
                    text="❌ Tidak ada setup kuat saat ini."
                )
                return "ok"

            pair, signal, price, sl, tp, rr, score = result

            bot.send_message(
                chat_id=update.message.chat_id,
                text=f"""
📊 MANUAL CONFIRM FUTURES

{pair} {signal}

Entry: {round(price,4)}
SL: {sl}
TP: {tp}

RR: {round(rr,2)}
Confidence: {score}/100
"""
            )

    return "ok"

# ================= START =================

# JALAN SELALU (TIDAK TERGANTUNG __main__)
thread = threading.Thread(target=auto_scan_loop)
thread.daemon = True
thread.start()

# Set webhook sekali saat boot
requests.get(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/{BOT_TOKEN}"
)

