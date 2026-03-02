def get_price(symbol):
    try:
        r = requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
            timeout=10
        )

        if r.status_code != 200:
            print("HTTP ERROR:", r.status_code, r.text)
            return None

        data = r.json()

        # Kalau Binance bilang invalid symbol
        if "code" in data and data["code"] != 0:
            print("INVALID SYMBOL:", data)
            return "INVALID"

        if "price" in data:
            return float(data["price"])

        return None

    except Exception as e:
        print("SPOT ERROR:", e)
        return None
