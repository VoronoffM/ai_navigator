import os
from datetime import datetime, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")

# Маленькая функция, чтобы достать цену из объекта API
def get_price(quotation):
    return quotation.units + quotation.nano / 1e9

def get_candles():
    if not TOKEN:
        print("Error: TBANK_TOKEN not found in .env")
        return

    print("Connecting to Sandbox API...")
    
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        shares = client.instruments.shares()
        figi = None
        
        for share in shares.instruments:
            if share.ticker == "GAZP":
                figi = share.figi
                break

        if not figi:
            print("Error: GAZP not found")
            return

        print("Found FIGI: " + figi)

        now = datetime.utcnow()
        from_time = now - timedelta(days=2)

        candles = client.market_data.get_candles(
            figi=figi,
            from_=from_time,
            to=now,
            interval=CandleInterval.CANDLE_INTERVAL_5_MIN
        )

        print("Candles received: " + str(len(candles.candles)))

        if len(candles.candles) > 0:
            last = candles.candles[-1]
            # Теперь строки короткие и не будут рваться
            po = get_price(last.open)
            pc = get_price(last.close)
            
            print("--- LAST CANDLE ---")
            print("Open: " + str(round(po, 2)))
            print("Close: " + str(round(pc, 2)))

if __name__ == "__main__":
    get_candles()