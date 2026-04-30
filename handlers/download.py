"""
handlers/download.py – منطق التحميل الأساسي (yt-dlp + Custom APIs)
يدعم: YouTube, Instagram, TikTok, Facebook, Pinterest, Snapchat, وغيرها
"""
import os
import re
import glob
import hashlib
import logging
import asyncio
import aiohttp
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

# ── Regex ──────────────────────────────────────────────────────────────────────
URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}"
    r"\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)"
)

# ── Credentials (من متغيرات البيئة) ───────────────────────────────────────────
IG_USERNAME    = os.getenv("IG_USERNAME", "")
IG_PASSWORD    = os.getenv("IG_PASSWORD", "")
IG_COOKIES     = os.getenv("IG_COOKIES", "")

# ── كوكيز Instagram ملف مؤقت ──────────────────────────────────────────────────
_IG_COOKIES_FILE = os.path.join(TMP_DIR, "ig_cookies.txt")
if IG_COOKIES:
    try:
        os.makedirs(TMP_DIR, exist_ok=True)
        with open(_IG_COOKIES_FILE, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for pair in IG_COOKIES.split(";"):
                pair = pair.strip()
                if "=" not in pair:
                    continue
                name, value = pair.split("=", 1)
                f.write(
                    f".instagram.com\tTRUE\t/\tTRUE\t2099999999"
                    f"\t{name.strip()}\t{value.strip()}\n"
                )
    except Exception as e:
        logger.warning(f"Failed to write IG cookies file: {e}")
        _IG_COOKIES_FILE = ""

# ══════════════════════════════════════════════════════════════════════════════
#  API Configs
# ══════════════════════════════════════════════════════════════════════════════

# ── TikTok ────────────────────────────────────────────────────────────────────
TIKTOK_API_URL = "https://tiksave.io/api/ajaxSearch"
TIKTOK_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9,ar-IQ;q=0.8,ar;q=0.7",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://tiksave.io",
    "referer": "https://tiksave.io/ar",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}

# ── Facebook ──────────────────────────────────────────────────────────────────
FB_API_URL = "https://fbdownloader.to/api/ajaxSearch"
FB_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9,ar-IQ;q=0.8,ar;q=0.7",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://fbdownloader.to",
    "referer": "https://fbdownloader.to/ar",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}
FB_COOKIES = {
    "fpestid": "TQyMQylz-gvL1kHeSpoed1DZBd_-Y4YBDU4rVgQYEKy2H3fz6rzKpilTTsGNsyjM8XNppw",
}

# ── Pinterest ─────────────────────────────────────────────────────────────────
PINTEREST_API_URL  = "https://everyweb.net/wp-json/aio-dl/video-data/"
PINTEREST_TOKEN    = "0d8a45597e998fd21242b74089fac11b70dd1499a2ba25ad3b6100238811eafd"
PINTEREST_HEADERS  = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9,ar-IQ;q=0.8,ar;q=0.7",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://everyweb.net",
    "referer": "https://everyweb.net/pinterest/",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    ),
}
PINTEREST_COOKIES  = {
    "pll_language": "ar",
}
PINTEREST_IMG_API  = "https://api.pinterestdl.io/api/image"

# ── Snapchat ──────────────────────────────────────────────────────────────────
SNAP_API_URL     = "https://samrt-loader.com/kydwon/api/addfile"
SNAP_COOKIES     = {
    "myCookieConsent": "true",
    "PHPSESSID": "lruvkc8ljl99ks5imuc3fsca9u",
}
SNAP_HEADERS     = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,ar-IQ;q=0.8,ar;q=0.7",
    "content-type": "application/json",
    "origin": "https://samrt-loader.com",
    "referer": "https://samrt-loader.com/ar/snapchat",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
    ),
}

# ══════════════════════════════════════════════════════════════════════════════
#  Helper Functions
# ══════════════════════════════════════════════════════════════════════════════

def detect_platform(url: str) -> dict:
    url_lower = url.lower()
    for key, info in PLATFORMS.items():
        if key in url_lower:
            return {**info, "key": key}
    return {"name": "موقع آخر", "emoji": "🌐", "color": "⚪", "key": "other"}


def _esc(text: str) -> str:
    """Escape Markdown special chars."""
    for ch in ["_", "*", "`", "[", "]"]:
        text = text.replace(ch, f"\\{ch}")
    return text


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

    if url and "instagram" in url.lower():
        if _IG_COOKIES_FILE and os.path.exists(_IG_COOKIES_FILE):
            base["cookiefile"] = _IG_COOKIES_FILE
        elif IG_USERNAME and IG_PASSWORD:
            base["username"] = IG_USERNAME
            base["password"] = IG_PASSWORD

    format_map = {
        "audio": None,
        "360":   "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
        "720":   "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "1080":  "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "best":  "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    }

    if quality == "audio":
        base["format"] = "bestaudio/best"
        base["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        base["format"] = format_map.get(quality, format_map["best"])

    return base


def _find_downloaded_file(prefix: str) -> str | None:
    """
    ابحث عن الملف المُحمَّل بعد انتهاء yt-dlp.
    يعالج حالة postprocessing (مثلاً .mp3 بعد extraction)
    وحالة الامتدادات المتعددة (.mp4, .webm, .mkv, ...).
    """
    # نمط: prefix_*.* — كل الملفات اللي تبدأ بنفس الـ prefix
    candidates = glob.glob(f"{prefix}*")
    if not candidates:
        return None

    # نفضل mp4 ثم mp3 ثم أي شيء آخر
    priority = [".mp4", ".mp3", ".m4a", ".webm", ".mkv", ".opus", ".ogg"]
    for ext in priority:
        for c in candidates:
            if c.endswith(ext) and os.path.getsize(c) > 0:
                return c

    # أي ملف غير فارغ
    for c in candidates:
        if os.path.getsize(c) > 0:
            return c

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Custom API Downloaders
# ══════════════════════════════════════════════════════════════════════════════

async def _download_file_to_disk(download_url: str, filepath: str) -> bool:
    """تحميل ملف من رابط مباشر وحفظه على القرص."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    return False
                with open(filepath, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        f.write(chunk)
        return os.path.exists(filepath) and os.path.getsize(filepath) > 0
    except Exception as e:
        logger.warning(f"_download_file_to_disk error: {e}")
        return False


async def download_tiktok(url: str, user_id: int) -> tuple[str | None, str | None]:
    """تحميل TikTok عبر tiksave.io API."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"q": url, "lang": "ar"}
            async with session.post(
                TIKTOK_API_URL,
                headers=TIKTOK_HEADERS,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None, f"❌ TikTok API فشل (status {resp.status})"
                data = await resp.json(content_type=None)

        # استخراج رابط الفيديو بدون علامة مائية
        links = data.get("links") or data.get("data", {}).get("links", [])
        video_url = None

        # نفضل الرابط بدون علامة مائية
        for item in links:
            label = (item.get("label") or item.get("quality") or "").lower()
            if "watermark" not in label and item.get("url"):
                video_url = item["url"]
                break

        if not video_url and links:
            video_url = links[0].get("url")

        if not video_url:
            return None, "❌ لم يُعثر على رابط تحميل TikTok"

        filepath = os.path.join(TMP_DIR, f"{user_id}_tiktok.mp4")
        ok = await _download_file_to_disk(video_url, filepath)
        if not ok:
            return None, "❌ فشل تحميل ملف TikTok"

        return filepath, None

    except Exception as e:
        logger.error(f"download_tiktok error: {e}")
        return None, f"❌ خطأ TikTok: `{str(e)[:150]}`"


async def download_facebook(url: str, user_id: int, quality: str = "hd") -> tuple[str | None, str | None]:
    """تحميل Facebook عبر fbdownloader.to API."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"q": url, "lang": "ar"}
            async with session.post(
                FB_API_URL,
                headers=FB_HEADERS,
                cookies=FB_COOKIES,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None, f"❌ Facebook API فشل (status {resp.status})"
                data = await resp.json(content_type=None)

        links = data.get("links") or []
        video_url = None

        # نفضل HD ثم SD
        preferred = ["hd", "sd"] if quality in ("720", "1080", "best") else ["sd", "hd"]
        for qual in preferred:
            for item in links:
                label = (item.get("label") or item.get("quality") or "").lower()
                if qual in label and item.get("url"):
                    video_url = item["url"]
                    break
            if video_url:
                break

        if not video_url and links:
            video_url = links[0].get("url")

        if not video_url:
            return None, "❌ لم يُعثر على رابط تحميل Facebook"

        filepath = os.path.join(TMP_DIR, f"{user_id}_facebook.mp4")
        ok = await _download_file_to_disk(video_url, filepath)
        if not ok:
            return None, "❌ فشل تحميل ملف Facebook"

        return filepath, None

    except Exception as e:
        logger.error(f"download_facebook error: {e}")
        return None, f"❌ خطأ Facebook: `{str(e)[:150]}`"


async def download_pinterest(url: str, user_id: int) -> tuple[str | None, str | None]:
    """تحميل Pinterest (فيديو أو صورة) عبر everyweb.net API."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = f"url={url}&token={PINTEREST_TOKEN}"
            async with session.post(
                PINTEREST_API_URL,
                headers=PINTEREST_HEADERS,
                cookies=PINTEREST_COOKIES,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None, f"❌ Pinterest API فشل (status {resp.status})"
                data = await resp.json(content_type=None)

        medias = data.get("medias") or []
        if not medias:
            return None, "❌ لم يُعثر على محتوى Pinterest"

        media   = medias[0]
        dl_url  = media.get("url") or media.get("download_url")
        ext     = "mp4" if media.get("type") == "video" else "jpg"

        if not dl_url:
            return None, "❌ لم يُعثر على رابط تحميل Pinterest"

        filepath = os.path.join(TMP_DIR, f"{user_id}_pinterest.{ext}")
        ok = await _download_file_to_disk(dl_url, filepath)
        if not ok:
            return None, "❌ فشل تحميل ملف Pinterest"

        return filepath, None

    except Exception as e:
        logger.error(f"download_pinterest error: {e}")
        return None, f"❌ خطأ Pinterest: `{str(e)[:150]}`"


async def download_snapchat(url: str, user_id: int) -> tuple[str | None, str | None]:
    """تحميل Snapchat عبر samrt-loader.com API."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"link": url}
            async with session.post(
                SNAP_API_URL,
                headers=SNAP_HEADERS,
                cookies=SNAP_COOKIES,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None, f"❌ Snapchat API فشل (status {resp.status})"
                data = await resp.json(content_type=None)

        # استخراج رابط الفيديو
        dl_url = (
            data.get("VideoHD")
            or data.get("VideoSD")
            or data.get("video")
            or data.get("url")
        )
        if not dl_url:
            for key in ("data", "result", "media"):
                obj = data.get(key, {})
                if isinstance(obj, dict):
                    dl_url = obj.get("url") or obj.get("VideoHD") or obj.get("VideoSD")
                    if dl_url:
                        break

        if not dl_url:
            return None, "❌ لم يُعثر على رابط تحميل Snapchat"

        filepath = os.path.join(TMP_DIR, f"{user_id}_snapchat.mp4")
        ok = await _download_file_to_disk(dl_url, filepath)
        if not ok:
            return None, "❌ فشل تحميل ملف Snapchat"

        return filepath, None

    except Exception as e:
        logger.error(f"download_snapchat error: {e}")
        return None, f"❌ خطأ Snapchat: `{str(e)[:150]}`"


# ══════════════════════════════════════════════════════════════════════════════
#  yt-dlp Downloader (YouTube, Instagram, Twitter/X, وغيرها)
# ══════════════════════════════════════════════════════════════════════════════

async def get_video_info(url: str) -> dict | None:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        # ✅ FIX 1: استخدام get_running_loop() بدل get_event_loop()
        loop = asyncio.get_running_loop()
        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        return await loop.run_in_executor(None, _extract)
    except Exception as e:
        logger.warning(f"Info extraction failed: {e}")
        return None


async def download_video_ytdlp(url: str, quality: str, user_id: int) -> tuple[str | None, str | None]:
    """تحميل عبر yt-dlp (YouTube, Instagram, Twitter/X, إلخ)."""
    # ✅ FIX 2: prefix ثابت لكل user — نبحث عنه بعد التحميل بـ glob
    file_prefix = os.path.join(TMP_DIR, f"{user_id}_ytdlp")
    out_template = f"{file_prefix}_%(id)s.%(ext)s"
    opts = get_ydl_opts(out_template, quality, url)

    try:
        # ✅ FIX 1: استخدام get_running_loop() بدل get_event_loop()
        loop = asyncio.get_running_loop()

        def _download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, _download)

        # ✅ FIX 2: البحث عن الملف بـ glob بدل prepare_filename
        # prepare_filename لا يعرف الامتداد الصحيح بعد postprocessing
        filepath = _find_downloaded_file(file_prefix)

        if not filepath:
            return None, "❌ فشل إيجاد الملف بعد التحميل"

        size = os.path.getsize(filepath)
        if size > MAX_FILESIZE:
            os.remove(filepath)
            return None, f"❌ الملف أكبر من الحد المسموح ({MAX_FILESIZE // 1024 // 1024} ميجا)"

        return filepath, None

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "private" in msg.lower():
            return None, "🔒 هذا الفيديو خاص ولا يمكن تحميله"
        if "age" in msg.lower():
            return None, "🔞 هذا الفيديو محمي بقيود العمر"
        if "copyright" in msg.lower():
            return None, "©️ هذا الفيديو محمي بحقوق النشر"
        if "login" in msg.lower() or "rate" in msg.lower() or "not available" in msg.lower():
            return None, "🔐 يطلب تسجيل دخول.\nجرب رابطاً آخر أو تواصل مع المطور."
        return None, f"❌ فشل التحميل:\n`{msg[:200]}`"
    except Exception as e:
        logger.error(f"yt-dlp download error: {e}")
        return None, f"❌ خطأ غير متوقع: `{str(e)[:150]}`"


# ══════════════════════════════════════════════════════════════════════════════
#  Router: يختار المُحمِّل المناسب حسب المنصة
# ══════════════════════════════════════════════════════════════════════════════

async def smart_download(url: str, quality: str, user_id: int) -> tuple[str | None, str | None]:
    """
    يوجّه طلب التحميل للـ API المناسب:
    - TikTok   → tiksave.io
    - Facebook → fbdownloader.to
    - Pinterest→ everyweb.net
    - Snapchat → samrt-loader.com
    - باقي المواقع → yt-dlp
    """
    url_lower = url.lower()

    if "tiktok.com" in url_lower or "vm.tiktok" in url_lower:
        filepath, err = await download_tiktok(url, user_id)
        if err:
            logger.info(f"TikTok API failed, falling back to yt-dlp: {err}")
            return await download_video_ytdlp(url, quality, user_id)
        return filepath, None

    if "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.com" in url_lower:
        filepath, err = await download_facebook(url, user_id, quality)
        if err:
            logger.info(f"Facebook API failed, falling back to yt-dlp: {err}")
            return await download_video_ytdlp(url, quality, user_id)
        return filepath, None

    if "pinterest.com" in url_lower or "pin.it" in url_lower:
        return await download_pinterest(url, user_id)

    if "snapchat.com" in url_lower or "snap.com" in url_lower:
        return await download_snapchat(url, user_id)

    # الباقي: YouTube, Instagram, Twitter/X, إلخ
    return await download_video_ytdlp(url, quality, user_id)


# ══════════════════════════════════════════════════════════════════════════════
#  Main Telegram Handler
# ══════════════════════════════════════════════════════════════════════════════

async def _send_media(ctx, user_id: int, filepath: str, caption: str):
    """إرسال الملف (فيديو / صوت / صورة) للمستخدم."""
    ext = Path(filepath).suffix.lower()
    with open(filepath, "rb") as f:
        if ext in (".mp3", ".m4a", ".opus", ".ogg"):
            await ctx.bot.send_audio(
                chat_id=user_id, audio=f,
                caption=caption, parse_mode="Markdown"
            )
        elif ext in (".jpg", ".jpeg", ".png", ".webp"):
            await ctx.bot.send_photo(
                chat_id=user_id, photo=f,
                caption=caption, parse_mode="Markdown"
            )
        else:
            await ctx.bot.send_video(
                chat_id=user_id, video=f,
                caption=caption, parse_mode="Markdown",
                supports_streaming=True
            )


async def download_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    query = update.callback_query

    # ── Callback: زر اختيار الجودة ────────────────────────────────────────────
    if query:
        await query.answer()
        data = query.data or ""

        if not data.startswith("dl_"):
            return

        parts = data.split("_", 2)
        if len(parts) < 3:
            return

        quality = parts[1]
        url_key = parts[2]

        url_store = ctx.bot_data.get("url_store", {})
        url       = url_store.get(url_key)
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
            parse_mode="Markdown",
        )

        filepath, error = await smart_download(url, quality, user.id)

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

            await _send_media(ctx, user.id, filepath, caption)
            log_download(user.id, platform["key"], url, "success", int(size_mb * 1024 * 1024))
            increment_daily(user.id)

            await query.edit_message_text(
                f"✅ تم الإرسال بنجاح!\n"
                f"📊 تحميلاتك اليوم: {get_daily_count(user.id)}/{DAILY_LIMIT}"
            )

        except Exception as e:
            logger.error(f"Send error: {e}")
            log_download(user.id, platform["key"], url, "failed")
            await query.edit_message_text(
                f"❌ فشل إرسال الملف: `{str(e)[:200]}`",
                parse_mode="Markdown",
            )

        finally:
            # ✅ FIX 3: تنظيف كل ملفات الـ user بعد الإرسال (يشمل temp fragments)
            _cleanup_user_files(user.id)

        return

    # ── Message: رابط نصي ─────────────────────────────────────────────────────
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
        )
        return

    url      = urls[0]
    platform = detect_platform(url)

    if user.id not in ADMIN_IDS and get_daily_count(user.id) >= DAILY_LIMIT:
        await update.message.reply_text(
            f"⚠️ وصلت للحد اليومي ({DAILY_LIMIT} تحميل).\n"
            "تجدد الحدود في منتصف الليل! 🌙"
        )
        return

    info_msg = await update.message.reply_text(
        f"{platform['emoji']} جاري تحليل الرابط..."
    )

    # ── Pinterest / Snapchat: لا حاجة لمعلومات مسبقة، نزّل مباشرة ──────────
    url_lower = url.lower()
    if "pinterest.com" in url_lower or "pin.it" in url_lower or \
       "snapchat.com" in url_lower or "snap.com" in url_lower:

        await info_msg.edit_text(
            f"{platform['emoji']} جاري التحميل...\n⏳ يرجى الانتظار..."
        )
        filepath, error = await smart_download(url, "best", user.id)

        if error:
            log_download(user.id, platform["key"], url, "failed")
            await info_msg.edit_text(error, parse_mode="Markdown")
            return

        try:
            size_mb = os.path.getsize(filepath) / 1024 / 1024
            caption = (
                f"{platform['emoji']} *{platform['name']}*\n"
                f"📦 الحجم: `{size_mb:.1f} MB`\n\n"
                "✅ تم التحميل بواسطة @MediaDropBot"
            )
            await _send_media(ctx, user.id, filepath, caption)
            log_download(user.id, platform["key"], url, "success", int(size_mb * 1024 * 1024))
            increment_daily(user.id)
            await info_msg.edit_text(
                f"✅ تم الإرسال بنجاح!\n"
                f"📊 تحميلاتك اليوم: {get_daily_count(user.id)}/{DAILY_LIMIT}"
            )
        except Exception as e:
            logger.error(f"Send error: {e}")
            log_download(user.id, platform["key"], url, "failed")
            await info_msg.edit_text(
                f"❌ فشل إرسال الملف: `{str(e)[:200]}`",
                parse_mode="Markdown",
            )
        finally:
            _cleanup_user_files(user.id)
        return

    # ── باقي المنصات: عرض معلومات + أزرار الجودة ────────────────────────────
    info = await get_video_info(url)

    if not info:
        await info_msg.edit_text(
            "❌ تعذّر قراءة معلومات الرابط.\n"
            "تأكد أن الرابط صحيح وأن الفيديو عام."
        )
        return

    title    = _esc((info.get("title") or "بدون عنوان")[:60])
    duration = info.get("duration", 0)
    dur_str  = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "غير معروف"
    uploader = _esc(info.get("uploader") or info.get("channel") or "—")

    # تخزين الرابط بـ key قصير (≤ 64 بايت في callback_data)
    url_key = hashlib.md5(url.encode()).hexdigest()[:12]
    if "url_store" not in ctx.bot_data:
        ctx.bot_data["url_store"] = {}
    ctx.bot_data["url_store"][url_key] = url

    # أزرار TikTok / Facebook تختلف (لا 1080p مثلاً)
    is_tiktok = "tiktok" in url_lower or "vm.tiktok" in url_lower
    is_fb     = "facebook.com" in url_lower or "fb.watch" in url_lower

    if is_tiktok:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎵 صوت MP3",    callback_data=f"dl_audio_{url_key}")],
            [InlineKeyboardButton("⭐ أفضل جودة",  callback_data=f"dl_best_{url_key}")],
        ])
    elif is_fb:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎵 صوت MP3",    callback_data=f"dl_audio_{url_key}")],
            [
                InlineKeyboardButton("📱 SD",       callback_data=f"dl_360_{url_key}"),
                InlineKeyboardButton("🖥️ HD",       callback_data=f"dl_720_{url_key}"),
            ],
        ])
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎵 صوت MP3",    callback_data=f"dl_audio_{url_key}")],
            [
                InlineKeyboardButton("📱 360p",     callback_data=f"dl_360_{url_key}"),
                InlineKeyboardButton("🖥️ 720p",     callback_data=f"dl_720_{url_key}"),
                InlineKeyboardButton("🎬 1080p",    callback_data=f"dl_1080_{url_key}"),
            ],
            [InlineKeyboardButton("⭐ أفضل جودة",  callback_data=f"dl_best_{url_key}")],
        ])

    await info_msg.edit_text(
        f"{platform['emoji']} *{platform['name']}*\n\n"
        f"📹 *{title}*\n"
        f"👤 {uploader}\n"
        f"⏱ المدة: `{dur_str}`\n\n"
        "🎯 *اختر جودة التحميل:*",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Cleanup Helper
# ══════════════════════════════════════════════════════════════════════════════

def _cleanup_user_files(user_id: int):
    """حذف كل الملفات المؤقتة الخاصة بالمستخدم من TMP_DIR."""
    patterns = [
        os.path.join(TMP_DIR, f"{user_id}_*"),
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except Exception:
                pass
