# config.py
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

GRID_SIZE = 8
COOLDOWN_SECONDS = 10
POINTS_PER_CANDY = 10

CANDIES = [
    "🍬", "🍭", "🍫", "🍪",
    "🍓", "🍇", "🍉", "🍒", "🍋"
]
