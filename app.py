import requests
import re
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext

BOT_TOKEN = "8602327142:AAGQbZEBY2qgw9bZmQexAkcWZJaUk9hsn7c"

CAPITAL = 1000000
RISK_PERCENT = 0.02
LEVERAGE = 10


def get_btc_trend():
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=50"
        response = requests.get(url, timeout=5)
        data = response.json()

        if not isinstance(data, list):
            return "neutral"

        closes = [float(candle[4]) for candle in data]

        if len(closes) < 21:
            return "neutral"

        ema9 = sum(closes[-9:]) / 9
        ema21 = sum(closes[-21:]) / 21

        return "bullish" if ema9 > ema21 else "bearish"

    except Exception:
        return "neutral"


def handle_message(update: Update, context: CallbackContext):
    text = update.message.text

    if "PAIR:" not in text:
        return

    pair = re.search(r"PAIR:\s*(.*)", text).group(1)
    price = float(re.search(r"PRICE:\s*(.*)", text).group(1))
    tf = re.search(r"TF:\s*(.*)", text).group(1)
    signal = re.search(r"TYPE:\s*(.*)", text).group(1)

    btc_trend = get_btc_trend()
    confidence = 70

    if signal == "LONG" and btc_trend == "bearish":
        confidence -= 40

    if signal == "SHORT" and btc_trend == "bullish":
        confidence -= 40

    if confidence < 60:
        update.message.reply_text("❌ TradeDesaGopall REJECTED (Lawan arah BTC)")
        return

    risk_amount = CAPITAL * RISK_PERCENT

    if signal == "LONG":
        sl = round(price * 0.99, 2)
        tp = round(price * 1.02, 2)
    else:
        sl = round(price * 1.01, 2)
        tp = round(price * 0.98, 2)

    move_percent = abs(price - sl) / price
    margin = risk_amount / (move_percent * LEVERAGE)

    message = f"""
⚡ TradeDesaGopall CONFIRMED

Pair: {pair}
TF: {tf}
Direction: {signal}
Entry: {price}
SL: {sl}
TP: {tp}

Risk: Rp{int(risk_amount)}
Margin: Rp{int(margin)}
Leverage: {LEVERAGE}x
Confidence: {confidence}%
BTC Trend: {btc_trend}
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


