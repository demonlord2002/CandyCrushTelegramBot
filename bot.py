import random
import time
import io
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from pymongo import MongoClient
from PIL import Image, ImageDraw, ImageFont
from config import BOT_TOKEN, MONGO_URL, GRID_SIZE, CANDIES, COOLDOWN_SECONDS, POINTS_PER_CANDY

# ─── MongoDB Setup ─────────────────────
mongo = MongoClient(MONGO_URL)
db = mongo["candy_crush"]
scores_col = db["scores"]
games_col = db["games"]

# ─── Runtime Memory ────────────────────
games = {}      # chat_id -> board
cooldowns = {}  # (chat_id, user_id) -> timestamp

# ─── Helpers ──────────────────────────
def generate_board():
    """Generates a random GRID_SIZE x GRID_SIZE board"""
    return [[random.choice(CANDIES) for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]


def find_matches(board):
    matched = [[False]*GRID_SIZE for _ in range(GRID_SIZE)]
    # rows
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
    # columns
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
    points = 0
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if matched[r][c]:
                board[r][c] = ""
                points += POINTS_PER_CANDY

    # Collapse columns
    for c in range(GRID_SIZE):
        new_col = [board[r][c] for r in range(GRID_SIZE) if board[r][c] != ""]
        new_col = [""]*(GRID_SIZE - len(new_col)) + new_col
        for r in range(GRID_SIZE):
            board[r][c] = new_col[r]

    # Fill empty spaces
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if board[r][c] == "":
                board[r][c] = random.choice(CANDIES)

    return points


def swap_and_score(board, r, c, dr, dc):
    nr, nc = r + dr, c + dc
    if not (0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE):
        return 0

    board[r][c], board[nr][nc] = board[nr][nc], board[r][c]
    matched = find_matches(board)
    total_points = 0

    if not any(True in row for row in matched):
        board[r][c], board[nr][nc] = board[nr][nc], board[r][c]
        return 0

    while True:
        matched = find_matches(board)
        if not any(True in row for row in matched):
            break
        total_points += remove_matches(board, matched)

    return total_points


def add_score(chat_id, user, points):
    if points <= 0:
        return
    scores_col.update_one(
        {"chat_id": chat_id, "user_id": user.id},
        {"$set": {"username": user.username or user.first_name},
         "$inc": {"score": points}},
        upsert=True
    )


# ─── Board Image Generator ─────────────
def generate_board_image(board):
    cell_size = 60
    margin = 50
    width = GRID_SIZE * cell_size + margin
    height = GRID_SIZE * cell_size + margin
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Font for emojis and numbers
    try:
        font = ImageFont.truetype("arial.ttf", 32)
        num_font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
        num_font = ImageFont.load_default()

    # Draw column numbers
    for c in range(GRID_SIZE):
        x = margin + c*cell_size + 20
        y = 10
        draw.text((x, y), str(c+1), font=num_font, fill="black")
    
    # Draw row numbers and emojis
    for r in range(GRID_SIZE):
        y = margin + r*cell_size + 10
        draw.text((10, y), str(r+1), font=num_font, fill="black")
        for c in range(GRID_SIZE):
            x = margin + c*cell_size + 10
            draw.text((x, y), board[r][c], font=font, fill="black")
            # Draw cell border
            draw.rectangle([margin + c*cell_size, margin + r*cell_size,
                            margin + (c+1)*cell_size, margin + (r+1)*cell_size],
                           outline="black", width=2)

    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio


# ─── Commands ──────────────────────────
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return

    board = generate_board()
    chat_id = update.effective_chat.id
    games[chat_id] = board
    games_col.update_one({"chat_id": chat_id}, {"$set": {"active": True}}, upsert=True)

    board_img = generate_board_image(board)
    await update.message.reply_photo(
        board_img,
        caption="🍬🍭 Candy Crush Arena Started! 🍓🍫\n🎮 Use: MATCH <row> <col> <L/R/U/D>\nExample: MATCH 2 3 L"
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


# ─── Gameplay ──────────────────────────
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
        r, c = int(r)-1, int(c)-1
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
        board_img = generate_board_image(board)
        await update.message.reply_photo(
            board_img,
            caption=f"💥 Sweet Crush! +{points} points 🎉"
        )
    else:
        await update.message.reply_text("❌ No match 😅 Try again!")


# ─── Main ─────────────────────────────
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
