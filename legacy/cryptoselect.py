import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import pytz
from openpyxl import Workbook

# Constants
THRESHOLD = 0.15
WINDOW = 20
HISTORICAL_DATA_POINTS = 200  # Number of historical data points to fetch


def get_historical_data(symbol, granularity=60):
    url = f'https://api.coinbase.com/api/v3/brokerage/products/{symbol}/candles?granularity={granularity}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            df = pd.DataFrame(data, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            df = df[['close']].rename(columns={'close': 'price'})
            return df
        else:
            print(f"Unexpected response format for {symbol}: {data}")
            return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching historical data for {symbol}: {e}")
        return pd.DataFrame()


def get_cryptos():
    print("Fetching exchange rates from Coinbase API...")
    url = 'https://api.coinbase.com/v2/exchange-rates'
    response = requests.get(url)
    data = response.json()

    if 'data' not in data:
        print("No data key in response.")
        return {}

    rates = data['data']['rates']
    cryptos = {symbol: 1 / float(rate) for symbol, rate in rates.items()}
    print(f"Fetched {len(cryptos)} cryptos.")
    return cryptos


def calculate_volatility(crypto_prices):
    volatilities = {}
    for symbol, df in crypto_prices.items():
        if not df.empty and len(df) >= WINDOW:
            df['returns'] = df['price'].pct_change()
            volatilities[symbol] = df['returns'].std()
    return volatilities


def get_top_5_cryptos(volatilities):
    sorted_volatilities = sorted(volatilities.items(), key=lambda x: x[1], reverse=True)
    return [crypto[0] for crypto in sorted_volatilities[:5]]


def get_bollinger_bands(df):
    df['MA'] = df['price'].rolling(window=WINDOW).mean()
    df['STD'] = df['price'].rolling(window=WINDOW).std()
    df['Upper Band'] = df['MA'] + (df['STD'] * 2)
    df['Lower Band'] = df['MA'] - (df['STD'] * 2)
    return df


def generate_signal(latest_price, latest_upper, latest_lower, symbol):
    global SIGNAL_CHECK, PRICE_CHECK, REPEAT_CHECK
    bollinger_percent = (latest_price - latest_lower) / (latest_upper - latest_lower)
    if THRESHOLD > bollinger_percent and SIGNAL_CHECK[symbol] <= 1 and REPEAT_CHECK[symbol] > 0:
        if PRICE_CHECK[symbol] < latest_price:
            PRICE_CHECK[symbol] = latest_price
        SIGNAL_CHECK[symbol] -= 1
        REPEAT_CHECK[symbol] = 0  # If buys are restricted once one is already done
        return "Buy"
    elif 1 - THRESHOLD < bollinger_percent and SIGNAL_CHECK[symbol] <= 0 and latest_price > PRICE_CHECK[symbol]:
        REPEAT_CHECK[symbol] = 1
        SIGNAL_CHECK[symbol] = 1
        PRICE_CHECK[symbol] = 0
        return "Sell"
    elif 1 - THRESHOLD > bollinger_percent and THRESHOLD < bollinger_percent:
        REPEAT_CHECK[symbol] = 1
        return "Hold"
    else:
        return "Hold"


def main():
    print("Fetching initial crypto data...")
    crypto_symbols = list(get_cryptos().keys())[:HISTORICAL_DATA_POINTS]
    crypto_prices = {symbol: get_historical_data(symbol + '-USD') for symbol in crypto_symbols}

    # Calculate volatilities and get top 5 cryptos immediately
    volatilities = calculate_volatility(crypto_prices)
    top_5_cryptos = get_top_5_cryptos(volatilities)
    print(f"Top 5 cryptos: {top_5_cryptos}")

    SIGNAL_CHECK = {crypto: 0 for crypto in top_5_cryptos}
    PRICE_CHECK = {crypto: 0 for crypto in top_5_cryptos}
    REPEAT_CHECK = {crypto: 1 for crypto in top_5_cryptos}

    wb = Workbook()
    ws = wb.active
    ws.append(["Time", "Crypto", "Price", "Signal"])
    last_evaluation_time = datetime.now()

    while True:
        current_time = datetime.now()
        if (current_time - last_evaluation_time) >= timedelta(hours=3):
            print("Reevaluating top 5 cryptos based on volatility...")
            crypto_prices = {symbol: get_historical_data(symbol + '-USD') for symbol in crypto_symbols}
            volatilities = calculate_volatility(crypto_prices)
            top_5_cryptos = get_top_5_cryptos(volatilities)
            SIGNAL_CHECK = {crypto: 0 for crypto in top_5_cryptos}
            PRICE_CHECK = {crypto: 0 for crypto in top_5_cryptos}
            REPEAT_CHECK = {crypto: 1 for crypto in top_5_cryptos}
            print(f"Top 5 cryptos: {top_5_cryptos}")
            last_evaluation_time = current_time

        for symbol in top_5_cryptos:
            df = crypto_prices[symbol]
            df = get_bollinger_bands(df)
            if len(df) < WINDOW:
                continue

            latest_price = df["price"].iloc[-1]
            latest_upper = df["Upper Band"].iloc[-1]
            latest_lower = df["Lower Band"].iloc[-1]
            signal = generate_signal(latest_price, latest_upper, latest_lower, symbol)
            print(f'Time: {current_time}, Crypto: {symbol}, Price: {latest_price:.2f}, Signal: {signal}')
            ws.append([current_time, symbol, latest_price, signal])

        wb.save("crypto_signals.xlsx")
        time.sleep(1)


if __name__ == '__main__':
    main()
