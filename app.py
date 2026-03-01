import requests
import re
import time
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

BOT_TOKEN = "8602327142:AAGQbZEBY2qgw9bZmQexAkcWZJaUk9hsn7c"

CAPITAL = 1000000
RISK_PERCENT = 0.02
LEVERAGE = 10

# ===== COOLDOWN SYSTEM =====
last_signal_time = {}
COOLDOWN_SECONDS = 120


# ===== BYBIT BTC TREND =====
def get_btc_trend(interval):
    try:
        interval_map = {
            "15m": "15",
            "1h": "60"
        }

        bybit_interval = interval_map.get(interval, "15")

        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval={bybit_interval}&limit=100"
        response = requests.get(url, timeout=5).json()

        if response["retCode"] != 0:
            return "neutral", 0

        data = response["result"]["list"]
        closes = [float(candle[4]) for candle in data[::-1]]

        if len(closes) < 21:
            return "neutral", 0

        ema9 = sum(closes[-9:]) / 9
        ema21 = sum(closes[-21:]) / 21

        distance = abs(ema9 - ema21) / ema21 * 100
        trend = "bullish" if ema9 > ema21 else "bearish"

        return trend, distance

    except:
        return "neutral", 0


# ===== MAIN MESSAGE HANDLER =====
def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.upper()

    if "PAIR:" not in text or "PRICE:" not in text:
        update.message.reply_text("❌ Format salah.\nGunakan:\nPAIR: SOLUSDT\nPRICE: 90\nTF: 5\nTYPE: LONG")
        return

    try:
        pair = re.search(r"PAIR:\s*(.*)", text).group(1).strip()
        price = float(re.search(r"PRICE:\s*(.*)", text).group(1).strip())
        tf = re.search(r"TF:\s*(.*)", text).group(1).strip()

        type_match = re.search(r"TYPE:\s*(.*)", text)
        if not type_match:
            update.message.reply_text("❌ TYPE tidak ditemukan.")
            return

        raw_signal = type_match.group(1).strip()

        # ==== SIGNAL NORMALIZATION ====
        if raw_signal in ["LONG", "BUY"]:
            signal = "LONG"
        elif raw_signal in ["SHORT", "SELL"]:
            signal = "SHORT"
        else:
            update.message.reply_text("❌ TYPE harus LONG / SHORT / BUY / SELL")
            return

    except:
        update.message.reply_text("❌ Gagal membaca format. Periksa kembali.")
        return

    # ===== COOLDOWN CHECK =====
    current_time = time.time()
    key = f"{pair}_{signal}"

    if key in last_signal_time:
        if current_time - last_signal_time[key] < COOLDOWN_SECONDS:
            update.message.reply_text("⏳ Cooldown aktif. Tunggu sebentar.")
            return

    last_signal_time[key] = current_time

    # ===== BTC ANALYSIS =====
    btc_15m, dist_15m = get_btc_trend("15m")
    btc_1h, dist_1h = get_btc_trend("1h")

    score = 50

    if signal == "LONG":
        if btc_15m == "bullish":
            score += 15
        if btc_1h == "bullish":
            score += 20
    else:
        if btc_15m == "bearish":
            score += 15
        if btc_1h == "bearish":
            score += 20

    score += min(dist_15m, 10)
    score += min(dist_1h, 15)

    # ===== RISK & RR =====
    sl = round(price * 0.99, 2) if signal == "LONG" else round(price * 1.01, 2)
    tp = round(price * 1.02, 2) if signal == "LONG" else round(price * 0.98, 2)

    rr = abs(tp - price) / abs(price - sl)

    if rr >= 1.5:
        score += 10
    else:
        score -= 15

    # ===== CLASSIFICATION =====
    if score >= 85:
        label = "🔥 STRONG CONFIRM"
    elif score >= 70:
        label = "✅ VALID"
    elif score >= 60:
        label = "⚠ WEAK"
    else:
        label = "❌ REJECTED"

    message = f"""
{label}

Pair: {pair}
Direction: {signal}
Entry: {price}
SL: {sl}
TP: {tp}

RR: {round(rr,2)}
Score: {int(score)}/100

BTC 15m: {btc_15m}
BTC 1H: {btc_1h}
"""

    update.message.reply_text(message)


def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
