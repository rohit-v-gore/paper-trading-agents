import requests
import pandas as pd
import datetime
import pytz
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates
import openpyxl

PRODUCT_ID = "BTC-USD"
WINDOW = 14
HISTORY_LIMIT = 60
OVERBOUGHT = 70
OVERSOLD = 30
SIGNAL_CHECK = 0
PRICE_CHECK = 0
REPEAT_CHECK = 1

local_tz = pytz.timezone("America/New_York")

data_points = []
sell_signals = []
buy_signals = []
export_data = []


def fetch_current_price():
    url = f"https://api.exchange.coinbase.com/products/{PRODUCT_ID}/ticker"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return float(data["price"])
    except Exception as e:
        print("Error fetching current price:", e)
        return None


def update_data():
    global HISTORY_LIMIT
    current_price = fetch_current_price()
    if current_price is None:
        return
    current_time = datetime.datetime.now(local_tz)
    data_points.append({"time": current_time, "price": current_price})
    if HISTORY_LIMIT < WINDOW:
        HISTORY_LIMIT = WINDOW


def calculate_rsi(df, window=14):
    delta = df["price"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()

    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def generate_signal(latest_price,latest_rsi):
    global SIGNAL_CHECK
    global PRICE_CHECK
    global REPEAT_CHECK
    if latest_rsi < OVERSOLD and SIGNAL_CHECK <=1 and REPEAT_CHECK >0:
       if PRICE_CHECK < latest_price:
           PRICE_CHECK = latest_price
       SIGNAL_CHECK -=1
       REPEAT_CHECK = 0
       return "Buy"
    elif latest_rsi > OVERBOUGHT and SIGNAL_CHECK <= 0 and latest_price > PRICE_CHECK:
        REPEAT_CHECK=1
        SIGNAL_CHECK=1
        PRICE_CHECK = 0
        return "Sell"
    else:
        return "Hold"


fig, ax1 = plt.subplots(figsize=(10, 6))
fig.canvas.manager.set_window_title("LUCRUS LLP - BTC Price & RSI")

ax2 = ax1.twinx()


def animate(i):

    update_data()

    if not data_points:
        return

    df = pd.DataFrame(data_points)

    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    df = calculate_rsi(df, WINDOW)

    if len(df) < WINDOW:
        return

    latest_price = df["price"].iloc[-1]
    latest_rsi = df["RSI"].iloc[-1]

    signal = generate_signal(latest_price, latest_rsi)
    export_data.append({
        "time": df.index[-1].strftime('%H:%M:%S'),
        "price": latest_price,
        "RSI": latest_rsi,
        "signal": signal
    })

    df_export = pd.DataFrame(export_data)
    df_export.to_excel("BTC_RSI_Signals.xlsx", index=False)
    print(f"Exported to Excel: {len(export_data)} rows")

    if signal == "Buy":
        buy_signals.append(df.index[-1])
    if signal == "Sell":
        sell_signals.append(df.index[-1])


    ax1.clear()
    ax2.clear()

    ax1.plot(df.index, df["price"], label="BTC Price", color="blue", linewidth=2)
    ax1.set_ylabel("Price (USD)", color="blue")
    ax1.tick_params(axis='y', labelcolor="blue")
    ax1.set_title(f"Bitcoin Price & RSI - {PRODUCT_ID}")

    ax2.plot(df.index, df["RSI"], label="RSI", color="purple", linewidth=2)
    ax2.axhline(OVERBOUGHT, color="red", linestyle="--", label="Overbought (70)")
    ax2.axhline(OVERSOLD, color="green", linestyle="--", label="Oversold (30)")
    ax2.set_ylabel("RSI", color="purple")
    ax2.tick_params(axis='y', labelcolor="purple")

    if buy_signals:
        for buy_time in buy_signals:
            ax1.axvline(buy_time, color="red", linestyle="--",alpha=0.8)
    if sell_signals:
        for sell_time in sell_signals:
            ax1.axvline(sell_time, color="green", linestyle="--",alpha=0.8)

    annotation_text = (
        f"BTC Price: ${latest_price:.2f}\n"
        f"RSI: {latest_rsi:.2f}\n"
        f"Signal: {signal}"
        f"Highest Purchase Price: ${PRICE_CHECK}"
    )
    ax1.text(0.02, 0.85, annotation_text, transform=ax1.transAxes,
             fontsize=12, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S', tz=local_tz))
    fig.autofmt_xdate()

    ax1.set_xlabel("Time (EST)")
    ax1.set_ylabel("Price (USD)")
    fig.canvas.manager.set_window_title("LUCRUS LLP")
    ax1.set_title(f"{PRODUCT_ID} BUY/SELL Technical Indicators (Time Interval - Seconds)")
    ax1.legend(loc="upper left")
    ax2.legend(loc="upper right")
    ax1.grid(False)
    plt.tight_layout()

    print(
        f"[{df.index[-1].strftime('%H:%M:%S')}] Price: ${latest_price:.2f} | RSI: {latest_rsi:.2f} | Signal: {signal}")


ani = animation.FuncAnimation(fig, animate, interval=1000)
plt.show()
