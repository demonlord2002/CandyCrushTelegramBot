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

def mode_text(game):
    return (
        "😈 HARD MODE | ⏱ 10s | Min 5 letters | No plurals"
        if game["hard"]
        else "🙂 NORMAL MODE | ⏱ 15s | 3 streak = +2 bonus"
    )

def valid_word(word):
    if not re.fullmatch(r"[A-Za-z]+", word):
        return False
    return zipf_frequency(word.lower(), "en") > 1.8


# ---------------- START GAME ----------------
@app.on_message(filters.command("startword"))
async def start_game(_, msg):
    # Only groups
    if msg.chat.type not in ("group", "supergroup"):
        return await msg.reply("❌ This game works **only in groups**.")

    # Optional: only allow admins to start (comment if you want all members)
    # member = await app.get_chat_member(msg.chat.id, msg.from_user.id)
    # if member.status not in ("administrator", "creator"):
    #     return await msg.reply("🚫 Only **group admins** can start the game.")

    # Bot must be admin
    bot_member = await app.get_chat_member(msg.chat.id, app.me.id)
    if bot_member.status not in ("administrator", "creator"):
        return await msg.reply("⚠️ Please **promote me as admin** to start the game.")

    chat = msg.chat.id
    letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    games[chat] = {
        "letter": letter,
        "used": set(),
        "streaks": {},
        "hard": False,
        "last_time": time.time(),
        "alive": set(),
        "round": 1,
        "failed_round": set(),
        "message_id": None
    }

    sent = await msg.reply(
        f"""🔤🔥 **WORD CHAIN BATTLE** 🔥🔤

🎯 Round: 1
🎮 {mode_text(games[chat])}
🔠 Starting Letter: **{letter}**

🧠 Rules:
• Correct word = +1 point  
• 3 streak = +2 bonus  
• Hard mode: 5+ letters, no plurals  

👇 Type a word to play!
""",
        reply_markup=buttons()
    )

    games[chat]["message_id"] = sent.id



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

    if uid in game["failed_round"]:
        return

    game["alive"].add(uid)
    game["streaks"].setdefault(uid, 0)

    now = time.time()
    limit = 10 if game["hard"] else 15

    # ⏱ TIME OVER
    if now - game["last_time"] > limit:
        game["failed_round"].add(uid)
        game["streaks"][uid] = 0
        return await msg.reply(f"⏱ {user.mention} **time over!** Wait next round.")

    if not valid_word(word):
        game["streaks"][uid] = 0
        return await msg.reply("❌ Invalid English word.")

    if not word.startswith(game["letter"]):
        game["streaks"][uid] = 0
        return await msg.reply(f"❌ Word must start with **{game['letter']}**")

    if word in game["used"]:
        game["streaks"][uid] = 0
        return await msg.reply("❌ Word already used.")

    if game["hard"] and (len(word) < 5 or word.endswith("S")):
        game["streaks"][uid] = 0
        return await msg.reply("😈 Hard Mode rule broken! (5+ letters, no plurals)")

    # ✅ ACCEPT WORD
    game["used"].add(word)
    game["letter"] = word[-1]
    game["last_time"] = now
    game["streaks"][uid] += 1
    game["round"] += 1
    game["failed_round"].clear()

    score = 1
    if game["streaks"][uid] % 3 == 0:
        score += 2

    users.update_one(
        {"user_id": uid},
        {
            "$inc": {"score": score},
            "$set": {
                "name": user.first_name,
                "user_id": uid
            }
        },
        upsert=True
    )

    await app.edit_message_text(
        chat,
        game["message_id"],
        f"""🔤🔥 **WORD CHAIN BATTLE** 🔥🔤

🎯 Round: {game['round']}
🎮 {mode_text(game)}

✅ **{word}**
🔠 Next Letter: **{game['letter']}**

👤 Player: {user.mention}
🔥 Streak: {game['streaks'][uid]}
🏆 +{score} points
""",
        reply_markup=buttons()
    )


# ---------------- CALLBACKS ----------------
@app.on_callback_query()
async def callbacks(_, cb):
    chat = cb.message.chat.id
    uid = cb.from_user.id

    if cb.data == "streak":
        game = games.get(chat)
        streak = game["streaks"].get(uid, 0) if game else 0
        user_db = users.find_one({"user_id": uid}) or {}
        score = user_db.get("score", 0)

        await cb.answer(
            f"🔥 Your Streak: {streak}\n🏆 Total Points: {score}",
            show_alert=True
        )

    elif cb.data == "leaderboard":
        top = users.find().sort("score", -1).limit(5)
        text = "🏆 **GLOBAL LEADERBOARD** 🏆\n\n"

        for i, u in enumerate(top, 1):
            name = u.get("name", "Player")
            uid = u["user_id"]
            text += f"{i}. [{name}](tg://user?id={uid}) — {u.get('score',0)} pts\n"

        await cb.message.reply(text, disable_web_page_preview=True)

    elif cb.data == "hard":
        if chat in games:
            games[chat]["hard"] = not games[chat]["hard"]
            await cb.answer("😈 Hard Mode toggled!")

    elif cb.data == "stop":
        games.pop(chat, None)
        await cb.message.reply("⏹ **Game stopped.**")

app.run()
