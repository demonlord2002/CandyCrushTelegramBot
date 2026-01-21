import random
import time
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from pymongo import MongoClient
from config import (
    BOT_TOKEN,
    MONGO_URL,
    BOARD_SIZE,
    CANDIES,
    COOLDOWN_SECONDS
)

# ─── MongoDB ─────────────────────────────
mongo = MongoClient(MONGO_URL)
db = mongo["candy_crush"]
scores_col = db["scores"]
games_col = db["games"]

# ─── Runtime memory ──────────────────────
games = {}      # chat_id -> board
cooldowns = {}  # (chat_id, user_id) -> timestamp


# ─── Helpers ─────────────────────────────
def generate_board():
    return [[random.choice(CANDIES) for _ in range(BOARD_SIZE)]
            for _ in range(BOARD_SIZE)]


def board_to_text(board):
    return "\n".join("".join(row) for row in board)


def is_match(board):
    # rows
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE - 2):
            if board[r][c] == board[r][c+1] == board[r][c+2]:
                return True

    # columns
    for c in range(BOARD_SIZE):
        for r in range(BOARD_SIZE - 2):
            if board[r][c] == board[r+1][c] == board[r+2][c]:
                return True

    return False


def swap_and_validate(board, r, c, dr, dc):
    nr, nc = r + dr, c + dc
    if not (0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE):
        return False

    board[r][c], board[nr][nc] = board[nr][nc], board[r][c]
    valid = is_match(board)

    if not valid:
        board[r][c], board[nr][nc] = board[nr][nc], board[r][c]

    return valid


def add_score(chat_id, user):
    scores_col.update_one(
        {"chat_id": chat_id, "user_id": user.id},
        {
            "$set": {
                "username": user.username or user.first_name
            },
            "$inc": {"score": 10}
        },
        upsert=True
    )


# ─── Commands ────────────────────────────
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return

    board = generate_board()
    chat_id = update.effective_chat.id

    games[chat_id] = board
    games_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"active": True}},
        upsert=True
    )

    await update.message.reply_text(
        "🍬🍭 **Candy Crush Arena Started!** 🍓🍫\n\n"
        "🎮 How to play:\n"
        "`MATCH <row> <col> <L/R/U/D>`\n\n"
        "Example: `MATCH 2 3 L`\n\n"
        f"{board_to_text(board)}",
        parse_mode="Markdown"
    )


async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games.pop(chat_id, None)

    games_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"active": False}}
    )

    top = scores_col.find({"chat_id": chat_id}).sort("score", -1).limit(3)

    text = "🏁 **Game Over!** 🍬\n\n🏆 Winners:\n"
    for i, u in enumerate(top, start=1):
        text += f"{i}️⃣ @{u['username']} — {u['score']} pts 🍭\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users = scores_col.find({"chat_id": chat_id}).sort("score", -1).limit(10)

    text = "🏆 **Candy Crush Leaderboard** 🍬\n\n"
    for i, u in enumerate(users, start=1):
        text += f"{i}. @{u['username']} — {u['score']} 🍓\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ─── Gameplay ────────────────────────────
async def handle_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in games:
        return

    now = time.time()
    last = cooldowns.get((chat_id, user.id), 0)
    if now - last < COOLDOWN_SECONDS:
        await update.message.reply_text("⏳ Slow down 😄 wait few seconds")
        return

    try:
        _, r, c, d = update.message.text.split()
        r, c = int(r) - 1, int(c) - 1
        d = d.upper()
    except:
        return

    moves = {"L": (0, -1), "R": (0, 1), "U": (-1, 0), "D": (1, 0)}
    if d not in moves:
        return

    board = games[chat_id]
    if swap_and_validate(board, r, c, *moves[d]):
        add_score(chat_id, user)
        cooldowns[(chat_id, user.id)] = now

        await update.message.reply_text(
            f"💥 **Sweet Crush!** 🍬🍬🍬\n"
            f"+10 points 🎉\n\n"
            f"{board_to_text(board)}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ No match 😅 Try again!")


# ─── Main ────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_game))
    app.add_handler(CommandHandler("end", end_game))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(MessageHandler(filters.Regex(r"^MATCH"), handle_match))

    print("🍬 Candy Crush Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
