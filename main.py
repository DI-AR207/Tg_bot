#!/usr/bin/env python
"""
Telegram bot: /videos command sends a video, never repeating one to the
same user until they've seen every video at least once.

Videos are auto-collected from a Telegram CHANNEL — whenever you post a
video in that channel, the bot picks it up and adds it to its list
automatically (bot must be an admin in the channel).

Includes a tiny web server so it can run as a free Render Web Service
(Render's free tier requires the app to bind to a port).

SETUP:
1. pip install -r requirements.txt
2. Set BOT_TOKEN as an environment variable (don't hardcode it)
3. Add your bot to your channel as an ADMIN
4. Post videos in the channel — the bot will automatically capture them.
5. Users send /videos to your bot in a private chat to get a video.
"""

import os
from dotenv import load_dotenv
import json
import random
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
load_dotenv()

BOT_TOKEN =os.getenv("API_TOKEN")

VIDEOS_FILE = "videos.json"        # all known video file_ids
SENT_FILE = "sent_videos.json"     # per-user: which videos they've already received

# --- Tiny web server (keeps Render's free Web Service alive) ---
web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Bot is running."


def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)


# --- Storage helpers: all videos ---
def load_videos() -> list:
    if os.path.exists(VIDEOS_FILE):
        try:
            with open(VIDEOS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    return []


def save_videos(video_list: list) -> None:
    with open(VIDEOS_FILE, "w") as f:
        json.dump(video_list, f)


def add_video(file_id: str) -> None:
    video_list = load_videos()
    if file_id not in video_list:
        video_list.append(file_id)
        save_videos(video_list)
        logger.info(f"Added new video. Total videos: {len(video_list)}")


# --- Storage helpers: per-user sent history ---
def load_sent() -> dict:
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}


def save_sent(sent_data: dict) -> None:
    with open(SENT_FILE, "w") as f:
        json.dump(sent_data, f)


def get_sent_for_user(user_id: int) -> list:
    sent_data = load_sent()
    return sent_data.get(str(user_id), [])


def mark_sent(user_id: int, file_id: str) -> None:
    sent_data = load_sent()
    key = str(user_id)
    sent_data.setdefault(key, [])
    if file_id not in sent_data[key]:
        sent_data[key].append(file_id)
    save_sent(sent_data)


def reset_sent_for_user(user_id: int) -> None:
    sent_data = load_sent()
    sent_data[str(user_id)] = []
    save_sent(sent_data)


# --- Handlers ---
async def channel_video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fires whenever a video is posted in the channel the bot is admin of."""
    post = update.channel_post
    if post and post.video:
        add_video(post.video.file_id)


async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    all_videos = load_videos()

    if not all_videos:
        await update.message.reply_text(
            "No videos available yet. Please check back later."
        )
        return

    already_sent = get_sent_for_user(user_id)
    available = [v for v in all_videos if v not in already_sent]

    if not available:
        # User has seen every video — reset their history and start over
        reset_sent_for_user(user_id)
        available = all_videos
        await update.message.reply_text(
            "You've seen all available videos! Starting over."
        )

    choice = random.choice(available)
    await update.message.reply_video(video=choice)
    mark_sent(user_id, choice)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send /videos to get a video."
    )


def main() -> None:
    threading.Thread(target=run_web, daemon=True).start()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .connect_timeout(10)
        .read_timeout(10)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("videos", videos))
    app.add_handler(
        MessageHandler(filters.VIDEO & filters.UpdateType.CHANNEL_POST, channel_video_handler)
    )

    print("Bot is running... Press Ctrl+C to stop.")
    app.run_polling(poll_interval=0.5)


if __name__ == "__main__":
    main()