"""
utils/config.py – إعدادات البوت من متغيرات البيئة
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Required ──────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
ADMIN_IDS    = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))

# ── Optional ──────────────────────────────────────────────────────────────────
MAX_FILESIZE = int(os.getenv("MAX_FILESIZE_MB", "50")) * 1024 * 1024   # bytes
DAILY_LIMIT  = int(os.getenv("DAILY_LIMIT", "20"))          # downloads per user
DB_PATH      = os.getenv("DB_PATH", "mediabot.db")
TMP_DIR      = os.getenv("TMP_DIR", "/tmp/mediabot")

# أنشئ مجلد tmp إذا ما موجود
os.makedirs(TMP_DIR, exist_ok=True)

# ── Supported Platforms ───────────────────────────────────────────────────────
PLATFORMS = {
    "youtube":   {"name": "YouTube",    "emoji": "🎬", "color": "🔴"},
    "youtu.be":  {"name": "YouTube",    "emoji": "🎬", "color": "🔴"},
    "tiktok":    {"name": "TikTok",     "emoji": "🎵", "color": "⚫"},
    "instagram": {"name": "Instagram",  "emoji": "📸", "color": "🟣"},
    "facebook":  {"name": "Facebook",   "emoji": "📘", "color": "🔵"},
    "fb.watch":  {"name": "Facebook",   "emoji": "📘", "color": "🔵"},
    "twitter":   {"name": "Twitter/X",  "emoji": "🐦", "color": "⚫"},
    "x.com":     {"name": "Twitter/X",  "emoji": "🐦", "color": "⚫"},
    "t.me":      {"name": "Telegram",   "emoji": "✈️",  "color": "🔵"},
    "twitch":    {"name": "Twitch",     "emoji": "🟣", "color": "🟣"},
    "vimeo":     {"name": "Vimeo",      "emoji": "🎞️",  "color": "🔵"},
    "reddit":    {"name": "Reddit",     "emoji": "🤖", "color": "🟠"},
    "pinterest": {"name": "Pinterest",  "emoji": "📌", "color": "🔴"},
    "snapchat":  {"name": "Snapchat",   "emoji": "👻", "color": "🟡"},
    "dailymotion":{"name":"Dailymotion","emoji": "🎥", "color": "🔵"},
    "soundcloud":{"name":"SoundCloud",  "emoji": "🎧", "color": "🟠"},
    "spotify":   {"name": "Spotify",    "emoji": "🎶", "color": "🟢"},
}
