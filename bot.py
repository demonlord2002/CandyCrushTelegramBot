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
from config import BOT_TOKEN, MONGO_URL, BOARD_SIZE, CANDIES, COOLDOWN_SECONDS

# ─── CONFIG ─────────────────────────────
GRID_SIZE = 8  # 8x8 board
POINTS_PER_CANDY = 10

# ─── MONGO ──────────────────────────────
mongo = MongoClient(MONGO_URL)
db = mongo["candy_crush"]
scores_col = db["scores"]
games_col = db["games"]

# ─── MEMORY ─────────────────────────────
games = {}      # chat_id -> board
cooldowns = {}  # (chat_id, user_id) -> timestamp

# ─── HELPERS ────────────────────────────
def generate_board():
    """Generates a random GRID_SIZE x GRID_SIZE board"""
    return [[random.choice(CANDIES) for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]


def board_to_text(board):
    """Return string representation of the board"""
    return "\n".join("".join(row) for row in board)


def find_matches(board):
    """Find all matches of 3 or more same emojis in rows and columns"""
    matched = [[False]*GRID_SIZE for _ in range(GRID_SIZE)]
    # Check rows
    for r in range(GRID_SIZE):
        count = 1
        for c in range(1, GRID_SIZE):
            if board[r][c] == board[r][c-1]:
                count += 1
            else:
                if count >= 3:
                    for i in range(c-count, c):
                        matched[r][i] = True
                count = 1
        if count >= 3:
            for i in range(GRID_SIZE-count, GRID_SIZE):
                matched[r][i] = True

    # Check columns
    for c in range(GRID_SIZE):
        count = 1
        for r in range(1, GRID_SIZE):
            if board[r][c] == board[r-1][c]:
                count += 1
            else:
                if count >= 3:
                    for i in range(r-count, r):
                        matched[i][c] = True
                count = 1
        if count >= 3:
            for i in range(GRID_SIZE-count, GRID_SIZE):
                matched[i][c] = True

    return matched


def remove_matches(board, matched):
    """Remove matched candies and collapse board, return points earned"""
    points = 0
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if matched[r][c]:
                board[r][c] = ""
                points += POINTS_PER_CANDY

    # Collapse board
    for c in range(GRID_SIZE):
        empty = [r for r in range(GRID_SIZE) if board[r][c] == ""]
        if empty:
            new_col = [board[r][c] for r in range(GRID_SIZE) if board[r][c] != ""]
            new_col = [""]*(GRID_SIZE - len(new_col)) + new_col
            for r in range(GRID_SIZE):
                board[r][c] = new_col[r]

    # Fill empty spaces with new candies
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if board[r][c] == "":
                board[r][c] = random.choice(CANDIES)

    return points


def swap_and_score(board, r, c, dr, dc):
    """Swap two candies, check matches, return points earned"""
    nr, nc = r + dr, c + dc
    if not (0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE):
        return 0

    board[r][c], board[nr][nc] = board[nr][nc], board[r][c]
    matched = find_matches(board)
    points = sum(POINTS_PER_CANDY for row in matched for m in row if m)
    if points == 0:
        board[r][c], board[nr][nc] = board[nr][nc], board[r][c]  # revert
        return 0
    else:
        # remove all matches recursively
        total_points = 0
        while True:
            matched = find_matches(board)
            if not any(True in row for row in matched):
                break
            total_points += remove_matches(board, matched)
        return total_points


def add_score(chat_id, user, points):
    """Update MongoDB leaderboard"""
    if points <= 0:
        return
    scores_col.update_one(
        {"chat_id": chat_id, "user_id": user.id},
        {"$set": {"username": user.username or user.first_name},
         "$inc": {"score": points}},
        upsert=True
    )


# ─── COMMANDS ───────────────────────────
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return

    board = generate_board()
    chat_id = update.effective_chat.id
    games[chat_id] = board
    games_col.update_one({"chat_id": chat_id}, {"$set": {"active": True}}, upsert=True)

    await update.message.reply_text(
        "🍬🍭 **Candy Crush Arena Started!** 🍓🍫\n\n"
        "🎮 Play using: `MATCH <row> <col> <L/R/U/D>`\n"
        "Example: `MATCH 2 3 L`\n\n"
        f"{board_to_text(board)}",
        parse_mode="Markdown"
    )


async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games.pop(chat_id, None)
    games_col.update_one({"chat_id": chat_id}, {"$set": {"active": False}})

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


# ─── GAMEPLAY ───────────────────────────
async def handle_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in games:
        return

    now = time.time()
    last = cooldowns.get((chat_id, user.id), 0)
    if now - last < COOLDOWN_SECONDS:
        await update.message.reply_text("⏳ Slow down 😄 wait a few seconds")
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
    points = swap_and_score(board, r, c, *moves[d])

    if points > 0:
        add_score(chat_id, user, points)
        cooldowns[(chat_id, user.id)] = now
        await update.message.reply_text(
            f"💥 **Sweet Crush!** 🍬🍬🍬\n"
            f"+{points} points 🎉\n\n"
            f"{board_to_text(board)}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ No match 😅 Try again!")


# ─── MAIN ───────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_game))
    app.add_handler(CommandHandler("end", end_game))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(MessageHandler(filters.Regex(r"^MATCH"), handle_match))

    print("🍬 Candy Crush Bot running...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
