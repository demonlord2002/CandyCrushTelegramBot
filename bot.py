from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import time, random, re
from config import *

app = Client(
    "word-chain-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
users = db.users
games = {}

def buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Leaderboard", callback_data="leaderboard"),
            InlineKeyboardButton("🔥 My Streak", callback_data="streak")
        ],
        [
            InlineKeyboardButton("😈 Hard Mode", callback_data="hard"),
            InlineKeyboardButton("⏹ Stop Game", callback_data="stop")
        ]
    ])

def valid_word(word):
    return re.fullmatch(r"[A-Za-z]+", word)

@app.on_message(filters.command("startword") & filters.group)
async def start_game(_, msg):
    chat = msg.chat.id
    letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    games[chat] = {
        "letter": letter,
        "used": [],
        "last_user": None,
        "streak": 0,
        "hard": False,
        "time": time.time()
    }

    await msg.reply(
        f"""🔤🔥 WORD CHAIN BATTLE 🔥🔤

🎯 Mode: NORMAL
🔠 Starting Letter: **{letter}**
⏱️ Time Limit: 10s

🔥 Streak Bonus: ON
😈 Hard Mode: OFF
""",
        reply_markup=buttons()
    )

@app.on_message(filters.text & filters.group)
async def play(_, msg):
    chat = msg.chat.id
    user = msg.from_user
    word = msg.text.upper()

    if chat not in games:
        return

    game = games[chat]

    if not valid_word(word):
        return

    if not word.startswith(game["letter"]):
        return

    if word in game["used"]:
        return

    if game["hard"]:
        if len(word) < 5 or word.endswith("S"):
            return

    game["used"].append(word)
    game["letter"] = word[-1]

    if game["last_user"] == user.id:
        game["streak"] += 1
    else:
        game["streak"] = 1

    game["last_user"] = user.id

    score = 1
    if game["streak"] == 3:
        score += 2

    users.update_one(
        {"user_id": user.id},
        {"$inc": {"score": score}, "$set": {"name": user.first_name}},
        upsert=True
    )

    await msg.reply(
        f"""✅ **{word}**

🔠 Next Letter: **{game['letter']}**
👤 Player: {user.mention}
🔥 Streak: {game['streak']}
""",
        reply_markup=buttons()
    )

@app.on_callback_query()
async def callbacks(_, cb):
    chat = cb.message.chat.id
    data = cb.data

    if data == "leaderboard":
        top = users.find().sort("score", -1).limit(5)
        text = "🏆 **LEADERBOARD** 🏆\n\n"
        for i, u in enumerate(top, 1):
            text += f"{i}. {u.get('name')} — {u.get('score',0)} pts\n"
        await cb.answer()
        await cb.message.reply(text)

    if data == "streak":
        await cb.answer("🔥 Keep answering continuously!")

    if data == "hard":
        games[chat]["hard"] = not games[chat]["hard"]
        await cb.answer("😈 Hard Mode toggled!")

    if data == "stop":
        games.pop(chat, None)
        await cb.message.reply("⏹ Game stopped.")

app.run()
