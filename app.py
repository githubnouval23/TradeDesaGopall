import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import re

BOT_TOKEN = "8602327142:AAHYQxE5RPejuQvhyHhsUC0MF_ZblT4DlMU"

CAPITAL = 1000000
RISK_PERCENT = 0.02
LEVERAGE = 10

def get_btc_trend():
    data = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=50").json()
    closes = [float(candle[4]) for candle in data]
    ema9 = sum(closes[-9:]) / 9
    ema21 = sum(closes[-21:]) / 21
    return "bullish" if ema9 > ema21 else "bearish"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("❌ AI REJECTED (Lawan arah BTC)")
        return

    risk_amount = CAPITAL * RISK_PERCENT
    sl = round(price * 0.99, 2) if signal == "LONG" else round(price * 1.01, 2)
    tp = round(price * 1.02, 2) if signal == "LONG" else round(price * 0.98, 2)

    move_percent = abs(price - sl) / price
    margin = risk_amount / (move_percent * LEVERAGE)

    message = f"""
⚡ AI CONFIRMED

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

    await update.message.reply_text(message)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle_message))
app.run_polling()