from json import dumps
from coinbase.rest import RESTClient


api_key=''
api_secret=''

client = RESTClient(api_key, api_secret)

accounts = client.get_accounts()
print(dumps(accounts.to_dict(), indent=2))

order = client.market_order_buy(client_order_id="clientOrderId3", product_id="BTC-USD", quote_size="1")
print(dumps(order.to_dict(), indent=2))