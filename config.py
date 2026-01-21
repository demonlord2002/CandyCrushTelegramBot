import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

GRID_SIZE = 8               # 8x8 board
COOLDOWN_SECONDS = 10       # cooldown between moves
POINTS_PER_CANDY = 10       # points for each matched candy

# Emoji candies
CANDIES = ["🍬", "🍭", "🍫", "🍪", "🍓", "🍇", "🍉", "🍋", "🍒"]
