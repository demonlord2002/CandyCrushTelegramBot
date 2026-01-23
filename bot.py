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

# ---------- UI ----------
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

# ---------- START GAME ----------
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
⏱️ Time Limit: {TIME_LIMIT}s

🔥 Streak Bonus: ON
😈 Hard Mode: OFF
""",
        reply_markup=buttons()
    )

# ---------- GAME PLAY ----------
@app.on_message(filters.text & filters.group)
async def play(_, msg):
    chat = msg.chat.id
    user = msg.from_user
    word = msg.text.strip().upper()

    if chat not in games:
        return

    game = games[chat]
    now = time.time()
    limit = HARD_TIME_LIMIT if game["hard"] else TIME_LIMIT

    # ⏱️ TIME CHECK (IMPORTANT FIX)
    if now - game["last_time"] > limit:
        game["streak"] = 0
        game["last_user"] = None
        game["last_time"] = now
        return await msg.reply(
            f"""💥 TIME’S UP!

😵 No valid word for **{game['letter']}**
➡️ New round started!"""
        )

    # WORD VALIDATION
    if not valid_word(word):
        return

    if not word.startswith(game["letter"]):
        return await msg.reply(
            f"❌ INVALID START!\nWord must begin with **{game['letter']}**"
        )

    if word in game["used"]:
        return await msg.reply("❌ WORD ALREADY USED!")

    if game["hard"]:
        if len(word) < 5:
            return await msg.reply("❌ TOO SHORT 😬\nMinimum 5 letters required!")
        if word.endswith("S"):
            return await msg.reply("❌ PLURAL WORD NOT ALLOWED 🚫")

    # ACCEPT WORD
    game["used"].add(word)
    game["letter"] = word[-1]
    game["last_time"] = now

    # 🔥 STREAK LOGIC (FIXED)
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
        {
            "$inc": {"score": score},
            "$set": {"name": user.first_name}
        },
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

# ---------- CALLBACKS ----------
@app.on_callback_query()
async def callbacks(_, cb):
    chat = cb.message.chat.id
    data = cb.data

    if data == "leaderboard":
        top = users.find().sort("score", -1).limit(5)
        text = "🏆 **LEADERBOARD** 🏆\n\n"
        for i, u in enumerate(top, 1):
            text += f"{i}. {u.get('name')} — {u.get('score',0)} pts\n"
        await cb.message.reply(text)
        await cb.answer()

    elif data == "streak":
        await cb.answer("🔥 Answer continuously to earn bonus points!")

    elif data == "hard":
        if chat in games:
            games[chat]["hard"] = not games[chat]["hard"]
            mode = "ON 😈" if games[chat]["hard"] else "OFF 🙂"
            await cb.message.reply(f"😈 Hard Mode: {mode}")
        await cb.answer()

    elif data == "stop":
        games.pop(chat, None)
        await cb.message.reply("⏹ Game stopped.")
        await cb.answer()

app.run()
