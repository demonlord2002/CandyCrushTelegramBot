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
    return zipf_frequency(word.lower(), "en") > 1.8


# ---------------- START GAME ----------------
@app.on_message(filters.command("startword") & filters.group)
async def start_game(_, msg):
    chat = msg.chat.id
    letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    games[chat] = {
        "letter": letter,
        "used": set(),
        "last_user": None,
        "streaks": {},
        "mistakes": {},
        "hard": False,
        "last_time": time.time(),
        "alive": set()
    }

    await msg.reply(
        f"""🔤🔥 **WORD CHAIN BATTLE** 🔥🔤

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
    uid = user.id
    word = msg.text.strip().upper()

    if chat not in games:
        return

    game = games[chat]

    # Register player
    game["alive"].add(uid)
    game["streaks"].setdefault(uid, 0)
    game["mistakes"].setdefault(uid, 0)

    # Skip eliminated
    if game["mistakes"][uid] >= 3:
        return

    now = time.time()
    limit = 10 if game["hard"] else 15

    # ⏱️ TIME CHECK
    if now - game["last_time"] > limit:
        game["streaks"][uid] = 0
        game["mistakes"][uid] += 1
        game["last_time"] = now

        if game["mistakes"][uid] >= 3:
            game["alive"].discard(uid)
            await msg.reply(
                f"💀 **ELIMINATED!**\n@{user.username or user.first_name}",
                reply_markup=buttons()
            )
        return

    # INVALID WORD
    if not valid_word(word):
        game["streaks"][uid] = 0
        game["mistakes"][uid] += 1
        await msg.reply(
            "❌ **INVALID WORD**\nTurn lost!",
            reply_markup=buttons()
        )
        return

    # WRONG LETTER
    if not word.startswith(game["letter"]):
        game["streaks"][uid] = 0
        game["mistakes"][uid] += 1
        await msg.reply(
            f"❌ **WRONG START!**\nMust start with **{game['letter']}**",
            reply_markup=buttons()
        )
        return

    # DUPLICATE
    if word in game["used"]:
        game["streaks"][uid] = 0
        game["mistakes"][uid] += 1
        await msg.reply(
            "❌ **WORD ALREADY USED!**",
            reply_markup=buttons()
        )
        return

    # HARD MODE
    if game["hard"]:
        if len(word) < 5 or word.endswith("S"):
            game["streaks"][uid] = 0
            game["mistakes"][uid] += 1
            await msg.reply(
                "❌ **HARD MODE RULE VIOLATION 😈**",
                reply_markup=buttons()
            )
            return

    # ACCEPT WORD
    game["used"].add(word)
    game["letter"] = word[-1]
    game["last_time"] = now

    game["streaks"][uid] += 1

    score = 1
    if game["streaks"][uid] % 3 == 0:
        score += 2

    users.update_one(
        {"user_id": uid},
        {"$inc": {"score": score}, "$set": {"name": user.first_name}},
        upsert=True
    )

    await msg.reply(
        f"""🔤🔥 **WORD CHAIN BATTLE** 🔥🔤

✅ **{word}**

🔠 Next Letter: **{game['letter']}**
👤 Player: {user.mention}
🔥 Streak: {game['streaks'][uid]}
🏆 +{score} points
👥 Players Left: {len(game['alive'])}
""",
        reply_markup=buttons()
    )


# ---------------- CALLBACKS ----------------
@app.on_callback_query()
async def callbacks(_, cb):
    chat = cb.message.chat.id

    if cb.data == "leaderboard":
        top = users.find().sort("score", -1).limit(5)
        text = "🏆 **GLOBAL LEADERBOARD** 🏆\n\n"
        for i, u in enumerate(top, 1):
            text += f"{i}. {u.get('name')} — {u.get('score',0)} pts\n"
        await cb.message.reply(text, reply_markup=buttons())
        await cb.answer()

    elif cb.data == "streak":
        await cb.answer("🔥 Keep answering correctly!")

    elif cb.data == "hard":
        if chat in games:
            games[chat]["hard"] = not games[chat]["hard"]
            mode = "ON 😈 (10s)" if games[chat]["hard"] else "OFF 🙂 (15s)"
            await cb.message.reply(f"😈 **Hard Mode {mode}**", reply_markup=buttons())
        await cb.answer()

    elif cb.data == "stop":
        games.pop(chat, None)
        await cb.message.reply("⏹ **Game stopped.**", reply_markup=buttons())
        await cb.answer()

app.run()
