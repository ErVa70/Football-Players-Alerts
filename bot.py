import os
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = "@formerbarcaplayers"

message = "Hello from my Barcelona Players Bot! ⚽"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

data = {
    "chat_id": CHANNEL,
    "text": message
}

response = requests.post(url, data=data)

print(response.json())
