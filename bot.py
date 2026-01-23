from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from wordfreq import zipf_frequency
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

# ---------------- UI ----------------
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
    if not re.fullmatch(r"[A-Za-z]+", word):
        return False
    # intelligent English check
    return zipf_frequency(word.lower(), "en") > 1.5

# ---------------- START GAME ----------------
@app.on_message(filters.command("startword") & filters.group)
async def start_game(_, msg):
    chat = msg.chat.id
    letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    games[chat] = {
        "letter": letter,
        "used": set(),
        "last_user": None,
        "streak": 0,
        "hard": False,
        "last_time": time.time()
    }

    await msg.reply(
        f"""🔤🔥 WORD CHAIN BATTLE 🔥🔤

🎯 Mode: NORMAL
🔠 Starting Letter: **{letter}**
⏱️ Time Limit: 15s

🔥 Streak Bonus: ON
😈 Hard Mode: OFF

👇 Type a word to play!
""",
        reply_markup=buttons()
    )

# ---------------- GAME PLAY ----------------
@app.on_message(filters.text & filters.group)
async def play(_, msg):
    chat = msg.chat.id
    user = msg.from_user
    word = msg.text.strip().upper()

    if chat not in games:
        return

    game = games[chat]
    now = time.time()
    limit = 10 if game["hard"] else 15

    # ⏱️ TIME CHECK
    if now - game["last_time"] > limit:
        game["streak"] = 0
        game["last_user"] = None
        game["last_time"] = now
        return await msg.reply(
            f"""💥 TIME’S UP!

😵 No valid word for **{game['letter']}**
➡️ Game continues!"""
        )

    # INVALID / NON-MEANING WORD
    if not valid_word(word):
        game["streak"] = 0
        game["last_user"] = None
        return await msg.reply(
            "❌ NOT A REAL WORD 🤔\nYour turn lost! Others continue 👇"
        )

    # WRONG START LETTER
    if not word.startswith(game["letter"]):
        game["streak"] = 0
        game["last_user"] = None
        return await msg.reply(
            f"❌ WRONG LETTER!\nWord must start with **{game['letter']}**"
        )

    # DUPLICATE WORD
    if word in game["used"]:
        game["streak"] = 0
        game["last_user"] = None
        return await msg.reply(
            "❌ WORD ALREADY USED!\nTurn skipped 😬"
        )

    # HARD MODE RULES
    if game["hard"]:
        if len(word) < 5:
            game["streak"] = 0
            game["last_user"] = None
            return await msg.reply(
                "❌ TOO SHORT 😈\nMinimum 5 letters!"
            )
        if word.endswith("S"):
            game["streak"] = 0
            game["last_user"] = None
            return await msg.reply(
                "❌ PLURAL WORD 🚫\nNo S / ES allowed!"
            )

    # ACCEPT WORD
    game["used"].add(word)
    game["letter"] = word[-1]
    game["last_time"] = now

    if game["last_user"] == user.id:
        game["streak"] += 1
    else:
        game["streak"] = 1

    game["last_user"] = user.id

    score = 1
    if game["streak"] % 3 == 0:
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
🏆 +{score} points
""",
        reply_markup=buttons()
    )

# ---------------- CALLBACKS ----------------
@app.on_callback_query()
async def callbacks(_, cb):
    chat = cb.message.chat.id
    data = cb.data

    if data == "leaderboard":
        top = users.find().sort("score", -1).limit(5)
        text = "🏆 **GLOBAL LEADERBOARD** 🏆\n\n"
        for i, u in enumerate(top, 1):
            text += f"{i}. {u.get('name')} — {u.get('score',0)} pts\n"
        await cb.message.reply(text)
        await cb.answer()

    elif data == "streak":
        await cb.answer("🔥 Keep answering correctly to build streaks!")

    elif data == "hard":
        if chat in games:
            games[chat]["hard"] = not games[chat]["hard"]
            mode = "ON 😈 (10s)" if games[chat]["hard"] else "OFF 🙂 (15s)"
            await cb.message.reply(f"😈 Hard Mode {mode}")
        await cb.answer()

    elif data == "stop":
        games.pop(chat, None)
        await cb.message.reply("⏹ Game stopped.")
        await cb.answer()

app.run()
