import requests
import re
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN belum di set di Railway Variables")

MAX_SIGNAL_PER_HOUR = 2

auto_signal_counter = {"hour": datetime.now().hour, "count": 0}

SCAN_PAIRS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT",
    "ARBUSDT","AVAXUSDT","DOGEUSDT","LINKUSDT","HYPEUSDT"
]

# ================= PRICE (AUTO FALLBACK) =================

def get_price(symbol):

    # ===== BYBIT =====
    try:
        r = requests.get(
            f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}",
            timeout=10
        )
        data = r.json()

        if data.get("retCode") == 0:
            result = data.get("result", {}).get("list", [])
            if result:
                return float(result[0]["lastPrice"]), "BYBIT"
    except Exception as e:
        print("BYBIT ERROR:", e)

    # ===== BINANCE =====
    try:
        r = requests.get(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",
            timeout=10
        )
        data = r.json()

        if "price" in data:
            return float(data["price"]), "BINANCE"
    except Exception as e:
        print("BINANCE ERROR:", e)

    return None, None

# ================= KLINE =================

def get_kline(symbol, interval, exchange, limit=100):
    try:
        if exchange == "BYBIT":
            r = requests.get(
                f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}",
                timeout=5
            ).json()
            if r.get("retCode") != 0:
                return []
            return r["result"]["list"]

        if exchange == "BINANCE":
            r = requests.get(
                f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}m&limit={limit}",
                timeout=5
            ).json()
            return r
    except:
        return []

    return []

# ================= INDICATORS =================

def get_trend(symbol, interval, exchange):
    data = get_kline(symbol, interval, exchange, 100)
    if len(data) < 21:
        return "neutral", 0

    if exchange == "BYBIT":
        closes = [float(c[4]) for c in data[::-1]]
    else:
        closes = [float(c[4]) for c in data]

    ema9 = sum(closes[-9:]) / 9
    ema21 = sum(closes[-21:]) / 21

    return ("bullish" if ema9 > ema21 else "bearish"), abs(ema9 - ema21) / ema21 * 100


def get_atr(symbol, exchange):
    data = get_kline(symbol, "15", exchange, 20)
    if len(data) < 20:
        return 0

    if exchange == "BYBIT":
        ranges = [float(c[2]) - float(c[3]) for c in data]
    else:
        ranges = [float(c[2]) - float(c[3]) for c in data]

    return sum(ranges) / len(ranges)


def volume_spike(symbol, exchange):
    data = get_kline(symbol, "15", exchange, 20)
    if len(data) < 20:
        return False

    if exchange == "BYBIT":
        vols = [float(c[5]) for c in data]
    else:
        vols = [float(c[5]) for c in data]

    return vols[-1] > (sum(vols[:-1]) / len(vols[:-1])) * 1.5


def breakout(symbol, exchange):
    data = get_kline(symbol, "15", exchange, 20)
    if len(data) < 20:
        return False

    if exchange == "BYBIT":
        highs = [float(c[2]) for c in data[:-1]]
        lows = [float(c[3]) for c in data[:-1]]
        last_close = float(data[0][4])
    else:
        highs = [float(c[2]) for c in data[:-1]]
        lows = [float(c[3]) for c in data[:-1]]
        last_close = float(data[-1][4])

    return last_close > max(highs) or last_close < min(lows)

# ================= CORE AI =================

def analyze_pair(pair):

    price, exchange = get_price(pair)

    if not price:
        return "PAIR_NOT_FOUND"

    pair15, dist15 = get_trend(pair, "15", exchange)
    pair5, _ = get_trend(pair, "5", exchange)

    btc1h, _ = get_trend("BTCUSDT", "60", exchange)
    btc15, _ = get_trend("BTCUSDT", "15", exchange)

    score = 50

    # Direction Logic
    if pair15 == "bullish" and btc1h == "bullish":
        signal = "LONG"
        score += 25
    elif pair15 == "bearish" and btc1h == "bearish":
        signal = "SHORT"
        score += 25
    else:
        return None

    if pair5 == pair15:
        score += 15

    if btc15 == pair15:
        score += 10

    if volume_spike(pair, exchange):
        score += 10

    if breakout(pair, exchange):
        score += 10

    atr = get_atr(pair, exchange)
    if atr == 0:
        return None

    sl_dist = atr * 1.2
    tp_dist = atr * 2

    if signal == "LONG":
        sl = round(price - sl_dist, 4)
        tp = round(price + tp_dist, 4)
    else:
        sl = round(price + sl_dist, 4)
        tp = round(price - tp_dist, 4)

    rr = abs(tp - price) / abs(price - sl)

    if rr >= 2:
        score += 10

    if score >= 90:
        label = "🎯 SNIPER"
    elif score >= 80:
        label = "🔥 STRONG"
    elif score >= 70:
        label = "✅ VALID"
    else:
        label = "⚠ WEAK"

    return pair, signal, price, sl, tp, rr, score, label, exchange

# ================= AUTO SCAN =================

def scan_market(context: CallbackContext):
    global auto_signal_counter
    current_hour = datetime.now().hour

    if auto_signal_counter["hour"] != current_hour:
        auto_signal_counter = {"hour": current_hour, "count": 0}

    if auto_signal_counter["count"] >= MAX_SIGNAL_PER_HOUR:
        return

    for pair in SCAN_PAIRS:
        result = analyze_pair(pair)

        if result and result != "PAIR_NOT_FOUND":
            auto_signal_counter["count"] += 1
            pair, signal, price, sl, tp, rr, score, label, exchange = result

            context.bot.send_message(
                chat_id=context.job.context,
                text=f"""
🔥 AUTO SIGNAL TraderDesaGopall

{label}
Exchange: {exchange}
{pair} {signal}

Entry: {round(price,4)}
SL (ATR): {sl}
TP (ATR): {tp}

RR: {round(rr,2)}
Confidence: {score}/100
"""
            )
            break

# ================= MANUAL =================

def handle_message(update: Update, context: CallbackContext):

    text = update.message.text.upper().strip()

    if re.match(r"^[A-Z]{3,15}USDT$", text):

        result = analyze_pair(text)

        if result == "PAIR_NOT_FOUND":
            update.message.reply_text("❌ TraderDesaGopall Konfirmasi Pair tidak tersedia di Bybit & Binance Futures.")
            return

        if not result:
            update.message.reply_text("❌ TraderDesaGopall Konfirmasi Tidak ada setup kuat saat ini.")
            return

        pair, signal, price, sl, tp, rr, score, label, exchange = result

        update.message.reply_text(f"""
📊 MANUAL CONFIRM TraderDesaGopall

{label}
Exchange: {exchange}
{pair} {signal}

Entry: {round(price,4)}
SL (ATR): {sl}
TP (ATR): {tp}

RR: {round(rr,2)}
Confidence: {score}/100
""")
        return

    update.message.reply_text("Kirim contoh:\nSOLUSDT")

# ================= START =================

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.job_queue.run_repeating(
        scan_market,
        interval=300,
        first=15,
        context="8602327142"
    )

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()


