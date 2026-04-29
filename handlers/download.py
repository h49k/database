"""
handlers/download.py – منطق التحميل الأساسي (yt-dlp)
"""
import os
import re
import hashlib
import logging
import asyncio
import yt_dlp
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import (
    upsert_user, is_banned, log_download,
    get_daily_count, increment_daily, get_setting
)
from utils.config import PLATFORMS, MAX_FILESIZE, DAILY_LIMIT, TMP_DIR, ADMIN_IDS

from handlers.subscription import check_subscription

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}"
    r"\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)"
)

IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")
IG_COOKIES  = os.getenv("IG_COOKIES", "")   # كوكيز Instagram من Railway

# كتابة الكوكيز لملف مؤقت عند البدء
_IG_COOKIES_FILE = os.path.join(TMP_DIR, "ig_cookies.txt")
if IG_COOKIES:
    try:
        with open(_IG_COOKIES_FILE, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for pair in IG_COOKIES.split(";"):
                pair = pair.strip()
                if "=" not in pair:
                    continue
                name, value = pair.split("=", 1)
                f.write(f".instagram.com\tTRUE\t/\tTRUE\t2099999999\t{name.strip()}\t{value.strip()}\n")
    except Exception:
        _IG_COOKIES_FILE = ""


def detect_platform(url: str) -> dict | None:
    url_lower = url.lower()
    for key, info in PLATFORMS.items():
        if key in url_lower:
            return {**info, "key": key}
    return {"name": "موقع آخر", "emoji": "🌐", "color": "⚪", "key": "other"}


def get_ydl_opts(output_path: str, quality: str = "best", url: str = "") -> dict:
    base = {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_FILESIZE,
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            )
        },
    }

    # إعدادات خاصة بـ Instagram
    if url and "instagram" in url.lower():
        if _IG_COOKIES_FILE and os.path.exists(_IG_COOKIES_FILE):
            base["cookiefile"] = _IG_COOKIES_FILE
        elif IG_USERNAME and IG_PASSWORD:
            base["username"] = IG_USERNAME
            base["password"] = IG_PASSWORD

    if quality == "audio":
        base.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    elif quality == "360":
        base["format"] = "bestvideo[height<=360]+bestaudio/best[height<=360]/best"
    elif quality == "720":
        base["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    elif quality == "1080":
        base["format"] = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    else:
        base["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"

    return base


async def get_video_info(url: str) -> dict | None:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        loop = asyncio.get_event_loop()
        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        info = await loop.run_in_executor(None, _extract)
        return info
    except Exception as e:
        logger.warning(f"Info extraction failed: {e}")
        return None


async def download_video(url: str, quality: str, user_id: int) -> tuple[str | None, str | None]:
    out_template = os.path.join(TMP_DIR, f"{user_id}_%(id)s.%(ext)s")
    opts = get_ydl_opts(out_template, quality, url)

    try:
        loop = asyncio.get_event_loop()
        def _download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        filepath = await loop.run_in_executor(None, _download)

        if not os.path.exists(filepath):
            base = filepath.rsplit(".", 1)[0]
            for ext in [".mp4", ".webm", ".mkv", ".mp3", ".m4a", ".opus"]:
                candidate = base + ext
                if os.path.exists(candidate):
                    filepath = candidate
                    break

        if not os.path.exists(filepath):
            return None, "❌ فشل إيجاد الملف بعد التحميل"

        size = os.path.getsize(filepath)
        if size > MAX_FILESIZE:
            os.remove(filepath)
            return None, f"❌ الملف أكبر من الحد المسموح ({MAX_FILESIZE // 1024 // 1024} ميجا)"

        return filepath, None

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "Private" in msg or "private" in msg:
            return None, "🔒 هذا الفيديو خاص ولا يمكن تحميله"
        if "age" in msg.lower():
            return None, "🔞 هذا الفيديو محمي بقيود العمر"
        if "copyright" in msg.lower():
            return None, "©️ هذا الفيديو محمي بحقوق النشر"
        if "login" in msg.lower() or "rate" in msg.lower() or "not available" in msg.lower():
            return None, "🔐 يطلب تسجيل دخول.\nجرب رابطاً آخر أو تواصل مع المطور."
        return None, f"❌ فشل التحميل:\n`{msg[:200]}`"
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None, f"❌ خطأ غير متوقع: `{str(e)[:150]}`"


# ── Main Handler ───────────────────────────────────────────────────────────────

async def download_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    query = update.callback_query

    # ── Callback (زر الجودة) ──────────────────────────────────────────────────
    if query:
        await query.answer()
        data = query.data
        if not data.startswith("dl_"):
            return

        parts = data.split("_", 2)
        if len(parts) < 3:
            return
        quality = parts[1]
        url_key = parts[2]

        # استرجاع الـ URL من التخزين المؤقت
        url_store = ctx.bot_data.get("url_store", {})
        url = url_store.get(url_key)
        if not url:
            await query.edit_message_text("❌ انتهت صلاحية الرابط، أرسله من جديد.")
            return

        upsert_user(user.id, user.username, user.full_name)

        if not await check_subscription(update, ctx):
            return

        if is_banned(user.id) and user.id not in ADMIN_IDS:
            await query.edit_message_text("🚫 أنت محظور من استخدام هذا البوت.")
            return

        if user.id not in ADMIN_IDS and get_daily_count(user.id) >= DAILY_LIMIT:
            await query.edit_message_text(
                f"⚠️ وصلت للحد اليومي ({DAILY_LIMIT} تحميل).\n"
                "تجدد الحدود في منتصف الليل! 🌙"
            )
            return

        platform = detect_platform(url)
        await query.edit_message_text(
            f"{platform['emoji']} جاري تحميل الفيديو...\n"
            f"المنصة: *{platform['name']}* | الجودة: *{quality}*\n\n"
            "⏳ يرجى الانتظار...",
            parse_mode="Markdown"
        )

        filepath, error = await download_video(url, quality, user.id)

        if error:
            log_download(user.id, platform["key"], url, "failed")
            await query.edit_message_text(error, parse_mode="Markdown")
            return

        try:
            size_mb = os.path.getsize(filepath) / 1024 / 1024
            caption = (
                f"{platform['emoji']} *{platform['name']}*\n"
                f"📦 الحجم: `{size_mb:.1f} MB`\n"
                f"🎯 الجودة: `{quality}`\n\n"
                "✅ تم التحميل بواسطة @MediaDropBot"
            )

            ext = Path(filepath).suffix.lower()
            with open(filepath, "rb") as f:
                if ext in (".mp3", ".m4a", ".opus", ".ogg"):
                    await ctx.bot.send_audio(
                        chat_id=user.id, audio=f, caption=caption,
                        parse_mode="Markdown"
                    )
                else:
                    await ctx.bot.send_video(
                        chat_id=user.id, video=f, caption=caption,
                        parse_mode="Markdown", supports_streaming=True
                    )

            log_download(user.id, platform["key"], url, "success", int(size_mb * 1024 * 1024))
            increment_daily(user.id)

            await query.edit_message_text(
                f"✅ تم الإرسال بنجاح!\n"
                f"📊 تحميلاتك اليوم: {get_daily_count(user.id)}/{DAILY_LIMIT}"
            )

        except Exception as e:
            logger.error(f"Send error: {e}")
            log_download(user.id, platform["key"], url, "failed")
            await query.edit_message_text(f"❌ فشل إرسال الملف: `{str(e)[:200]}`", parse_mode="Markdown")

        finally:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)

        return

    # ── Message (رابط نصي) ────────────────────────────────────────────────────
    if not update.message or not update.message.text:
        return

    upsert_user(user.id, user.username, user.full_name)

    text = update.message.text.strip()

    if not await check_subscription(update, ctx):
        return

    if get_setting("maintenance") == "1" and user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "🔧 البوت في وضع الصيانة حالياً.\n"
            "سيعود قريباً إن شاء الله! ⏰"
        )
        return

    if is_banned(user.id):
        await update.message.reply_text("🚫 أنت محظور من استخدام هذا البوت.")
        return

    urls = URL_REGEX.findall(text)
    if not urls:
        await update.message.reply_text(
            "🤔 لم أجد رابطاً في رسالتك!\n"
            "أرسل رابط الفيديو مباشرة.",
            parse_mode="Markdown"
        )
        return

    url = urls[0]
    platform = detect_platform(url)

    if user.id not in ADMIN_IDS and get_daily_count(user.id) >= DAILY_LIMIT:
        await update.message.reply_text(
            f"⚠️ وصلت للحد اليومي ({DAILY_LIMIT} تحميل).\n"
            "تجدد الحدود في منتصف الليل! 🌙"
        )
        return

    info_msg = await update.message.reply_text(
        f"{platform['emoji']} جاري تحليل الرابط...",
        parse_mode="Markdown"
    )

    info = await get_video_info(url)

    if not info:
        await info_msg.edit_text(
            "❌ تعذّر قراءة معلومات الرابط.\n"
            "تأكد أن الرابط صحيح وأن الفيديو عام."
        )
        return

    title    = (info.get("title") or "بدون عنوان")[:60]
    duration = info.get("duration", 0)
    dur_str  = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "غير معروف"
    uploader = info.get("uploader") or info.get("channel") or "—"

    # ── تخزين الـ URL بـ key قصير لتجنب تجاوز حد 64 بايت ──────────────────
    url_key = hashlib.md5(url.encode()).hexdigest()[:12]
    if "url_store" not in ctx.bot_data:
        ctx.bot_data["url_store"] = {}
    ctx.bot_data["url_store"][url_key] = url

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 صوت MP3",   callback_data=f"dl_audio_{url_key}"),
        ],
        [
            InlineKeyboardButton("📱 360p",      callback_data=f"dl_360_{url_key}"),
            InlineKeyboardButton("🖥️ 720p",      callback_data=f"dl_720_{url_key}"),
            InlineKeyboardButton("🎬 1080p",     callback_data=f"dl_1080_{url_key}"),
        ],
        [
            InlineKeyboardButton("⭐ أفضل جودة", callback_data=f"dl_best_{url_key}"),
        ],
    ])

    await info_msg.edit_text(
        f"{platform['emoji']} *{platform['name']}*\n\n"
        f"📹 *{title}*\n"
        f"👤 {uploader}\n"
        f"⏱ المدة: `{dur_str}`\n\n"
        "🎯 *اختر جودة التحميل:*",
        parse_mode="Markdown",
        reply_markup=kb
        )
