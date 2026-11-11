import requests
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates

PRODUCT_ID = "BTC-USD"
GRANULARITY = 60
ROLLING_WINDOW = 20
TIMEFRAME_HOURS = 1


LOCAL_TIMEZONE = "America/New_York"

def fetch_data():
    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(hours=TIMEFRAME_HOURS)

    url = f"https://api.exchange.coinbase.com/products/{PRODUCT_ID}/candles"
    params = {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "granularity": GRANULARITY
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an error for bad status codes
        data = response.json()
    except Exception as e:
        print("Error fetching data:", e)
        return None
    df = pd.DataFrame(data, columns=["time", "low", "high", "open", "close", "volume"])

    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

    if LOCAL_TIMEZONE is not None:
        df["time"] = df["time"].dt.tz_convert(LOCAL_TIMEZONE)

    df.sort_values("time", inplace=True)
    df.set_index("time", inplace=True)

    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])

    df["MA"] = df["close"].rolling(window=ROLLING_WINDOW).mean()
    df["STD"] = df["close"].rolling(window=ROLLING_WINDOW).std()
    df["Upper"] = df["MA"] + (2 * df["STD"])
    df["Lower"] = df["MA"] - (2 * df["STD"])

    df["EMA"] = df["close"].ewm(span=ROLLING_WINDOW, adjust=False).mean()

    return df

fig, ax = plt.subplots(figsize=(10, 6))
plt.title(f"{PRODUCT_ID} Price with Bollinger Bands and EMA")


def animate(i):
    df = fetch_data()
    if df is None or df.empty:
        return

    ax.clear()

    ax.plot(df.index, df["close"], label="Close", color="blue")

    ax.plot(df.index, df["EMA"], label="EMA", color="orange")

    ax.plot(df.index, df["Upper"], label="Upper Band", color="green", linestyle="--")
    ax.plot(df.index, df["Lower"], label="Lower Band", color="red", linestyle="--")

    current_price = df["close"].iloc[-1]

    ax.text(0.02, 0.75, f"Current Price: ${current_price:.2f}", transform=ax.transAxes,
            fontsize=12, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    ax.xaxis_date()

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=df.index.tz))
    fig.autofmt_xdate()

    ax.set_xlabel("Time" + (f" ({LOCAL_TIMEZONE})" if LOCAL_TIMEZONE else " (UTC)"))
    ax.set_ylabel("Price (USD)")
    ax.legend(loc="upper left")
    ax.grid(True)
    plt.tight_layout()


ani = animation.FuncAnimation(fig, animate, interval=100)

plt.show()
