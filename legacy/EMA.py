import requests
import pandas as pd
import datetime
import pytz
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates

PRODUCT_ID = "BTC-USD"
EMA_SPAN = 20
HISTORY_LIMIT = 120
THRESHOLD = 0.0001

local_tz = pytz.timezone("America/New_York")

data_points = []


def fetch_current_price():
    url = f"https://api.exchange.coinbase.com/products/{PRODUCT_ID}/ticker"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        current_price = float(data["price"])
        return current_price
    except Exception as e:
        print("Error fetching current price:", e)
        return None


def update_data():
    current_price = fetch_current_price()
    if current_price is None:
        return
    current_time = datetime.datetime.now(local_tz)
    data_points.append({"time": current_time, "price": current_price})
    if len(data_points) > HISTORY_LIMIT:
        del data_points[0]


def calculate_ema(df, span):
    df["EMA"] = df["price"].ewm(span=span, adjust=False).mean()
    return df


def generate_signal(latest_price, latest_ema):
    if latest_price > latest_ema * (1 + THRESHOLD):
        return "Buy"
    elif latest_price < latest_ema * (1 - THRESHOLD):
        return "Sell"
    else:
        return "Hold"


fig, ax = plt.subplots(figsize=(10, 6))
plt.title(f"{PRODUCT_ID} Price with EMA (Updating Every Second)")


def animate(i):
    update_data()
    if not data_points:
        return
    df = pd.DataFrame(data_points)
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)

    df = calculate_ema(df, EMA_SPAN)

    latest_price = df["price"].iloc[-1]
    latest_ema = df["EMA"].iloc[-1]
    signal = generate_signal(latest_price, latest_ema)

    ax.clear()
    ax.plot(df.index, df["price"], label="Price", color="blue")
    ax.plot(df.index, df["EMA"], label=f"EMA ({EMA_SPAN})", color="orange")

    annotation_text = (
        f"Current Price: ${latest_price:.2f}\n"
        f"EMA: ${latest_ema:.2f}\n"
        f"Signal: {signal}"
    )
    ax.text(0.02, 0.85, annotation_text, transform=ax.transAxes,
            fontsize=12, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S', tz=local_tz))
    fig.autofmt_xdate()

    ax.set_xlabel("Time (EST)")
    ax.set_ylabel("Price (USD)")
    ax.set_title(f"{PRODUCT_ID} Price with EMA (Updating Every Second)")
    ax.legend(loc="upper left")
    ax.grid(True)
    plt.tight_layout()

    print(
        f"[{df.index[-1].strftime('%H:%M:%S')}] Price: ${latest_price:.2f} | EMA: ${latest_ema:.2f} | Signal: {signal}")


ani = animation.FuncAnimation(fig, animate, interval=1000)

plt.show()