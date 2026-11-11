
import requests
import pandas as pd
import datetime
import pytz
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates
import openpyxl

PRODUCT_ID = "BTC-USD"
WINDOW = 20
HISTORY_LIMIT = 60
THRESHOLD = 0.15
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
        current_price = float(data["price"])
        return current_price
    except Exception as e:
        print("Error fetching current price:", e)
        return None


def update_data():
    global HISTORY_LIMIT
    current_price = fetch_current_price()
    if current_price is None:
        return
    current_time = datetime.datetime.now()
    data_points.append({"time": current_time, "price": current_price})
    if HISTORY_LIMIT < WINDOW:
        HISTORY_LIMIT = WINDOW


def calculate_bollinger_bands(df, window):
    df["MA"] = df["price"].rolling(window=window).mean()
    df["EMA"] = df["price"].ewm(span=window, adjust=False).mean()
    df["STD"] = df["price"].rolling(window=window).std()
    df["Upper"] = df["MA"] + (2 * df["STD"])
    df["Lower"] = df["MA"] - (2 * df["STD"])
    return df


def generate_signal(latest_price, latest_upper, latest_lower):
    global SIGNAL_CHECK
    global PRICE_CHECK
    global REPEAT_CHECK
    bollinger_percent = (latest_price-latest_lower)/(latest_upper-latest_lower)
    if THRESHOLD > bollinger_percent and SIGNAL_CHECK<=1 and REPEAT_CHECK>0:
        if PRICE_CHECK < latest_price:
            PRICE_CHECK = latest_price
        SIGNAL_CHECK -= 1
        REPEAT_CHECK = 0 #If buys are restricted once one is already done
        return "Buy"
    elif 1-THRESHOLD < bollinger_percent and SIGNAL_CHECK<=0 and latest_price>PRICE_CHECK:
        REPEAT_CHECK = 1
        SIGNAL_CHECK = 1
        PRICE_CHECK = 0
        return "Sell"
    elif 1-THRESHOLD > bollinger_percent and THRESHOLD < bollinger_percent:
        REPEAT_CHECK = 1
        return "Hold"
    else:
        return "Hold"
    





fig, ax = plt.subplots(figsize=(10, 6))
fig.canvas.manager.set_window_title("LUCRUS LLP")
plt.title(f"{PRODUCT_ID} BUY/SELL Technical Indicators (Time Interval - Seconds)")
ax.set_xlabel("Time (EST)")
ax.set_ylabel("Price (USD)")
ax.set_title(f"{PRODUCT_ID} BUY/SELL Technical Indicators (Time Interval - Seconds)")
ax.legend(loc="upper left")
ax.grid(True)
plt.tight_layout()
ax.text(0.5, 0.5, "Loading Data... Creating Plot...", ha="center", va="center", fontsize=35, color="black", transform=ax.transAxes)


def animate(i):

    update_data()

    if not data_points:
        return

    df = pd.DataFrame(data_points)

    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    df = calculate_bollinger_bands(df, WINDOW)


    if len(df) < WINDOW:
        return

    latest_price = df["price"].iloc[-1]
    latest_upper = df["Upper"].iloc[-1]
    latest_lower = df["Lower"].iloc[-1]

    signal = generate_signal(latest_price, latest_upper, latest_lower)
    export_data.append({
        "time": df.index[-1].strftime('%H:%M:%S'),
        "price": latest_price,
        "upper": latest_upper,
        "lower": latest_lower,
        "signal": signal
    })
     # Interval to export data (every 5th update)
    df_export = pd.DataFrame(export_data)
    df_export.to_excel("BTC_Buy_Sell_Signals.xlsx", index=False)
    print(f"Exported to Excel: {len(export_data)} rows")
    
    if signal == "Buy":
        buy_signals.append(df.index[-1])
    if signal == "Sell":
        sell_signals.append(df.index[-1])

    
    ax.clear()
    ax.plot(df.index, df["price"], label=f"Price ({PRODUCT_ID})", color="blue")
    ax.set_xlim(df.index.min(), df.index.max())
    ax.plot(df.index, df["Upper"], label="Upper Band", color="purple", linestyle="--")
    ax.plot(df.index, df["Lower"], label="Lower Band", color="orange", linestyle="--")
    ax.plot(df.index, df["EMA"], label=f"EMA ({WINDOW})", color="black", linestyle="--")
    ax.fill_between(df.index, df["Upper"], df["Lower"], color='lightgray', alpha=0.5)



    if buy_signals:
        for buy_time in buy_signals:
            ax.axvline(buy_time,color="red", linestyle="--", alpha=0.8)
    if sell_signals:
        for sell_time in sell_signals:
            ax.axvline(sell_time,color="green", linestyle="--", alpha=0.8)
    
    annotation_text = (
        f"Current Price: ${latest_price:.2f}\n"
        f"Upper Band: ${latest_upper:.2f}\n"
        f"Lower Band: ${latest_lower:.2f}\n"
        f"Signal: {signal}\n"
        f"Highest Purchase Price: ${PRICE_CHECK}"
    )
    ax.text(0.02, 0.23, annotation_text, transform=ax.transAxes,
            fontsize=12, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S', tz=local_tz))
    fig.autofmt_xdate()

    ax.set_xlabel("Time (EST)")
    ax.set_ylabel("Price (USD)")
    fig.canvas.manager.set_window_title("LUCRUS LLP")
    ax.set_title(f"{PRODUCT_ID} BUY/SELL Technical Indicators (Time Interval - Seconds)")
    ax.legend(loc="upper left")
    ax.grid(True)
    plt.tight_layout()

    print(
        f"[{df.index[-1].strftime('%H:%M:%S')}] Price: ${latest_price:.2f} | Upper: ${latest_upper:.2f} | Lower: ${latest_lower:.2f} | Signal: {signal}")


ani = animation.FuncAnimation(fig, animate, interval=300000)

plt.show()
