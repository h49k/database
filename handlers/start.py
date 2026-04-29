"""
handlers/start.py – /start و /help
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import upsert_user, get_setting, get_daily_count
from utils.config import PLATFORMS, ADMIN_IDS, DAILY_LIMIT


async def start_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.full_name)

    welcome = get_setting("welcome_msg") or "مرحباً! 🎉"

    # نخفي الـ aliases المكررة
    seen = set()
    platforms_list = ""
    for k, v in PLATFORMS.items():
        if v["name"] not in seen:
            platforms_list += f"  {v['emoji']} {v['name']}\n"
            seen.add(v["name"])

    text = (
        "╔══════════════════════════╗\n"
        "║   ⬇️  *MediaDrop Bot*  ⬇️   ║\n"
        "╚══════════════════════════╝\n\n"
        f"{welcome}\n\n"
        "أرسل أي رابط فيديو وسأحمّله لك فوراً! 🚀\n\n"
        "*المنصات المدعومة:*\n"
        f"{platforms_list}\n"
        "📌 فقط أرسل الرابط مباشرة!"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 كيفية الاستخدام", callback_data="help_usage"),
            InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats"),
        ],
    ])

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def help_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ انسخ رابط الفيديو من أي منصة\n"
        "2️⃣ أرسله هنا مباشرة\n"
        "3️⃣ اختر جودة التحميل\n"
        "4️⃣ انتظر ثوانٍ وستصلك الملف! ✅\n\n"
        "*الأوامر المتاحة:*\n"
        "/start – الصفحة الرئيسية\n"
        "/help – المساعدة\n"
        "/stats – إحصائياتك\n\n"
        "*ملاحظات:*\n"
        "• الحد الأقصى للملف: 50 ميجا\n"
        f"• الحد اليومي: {DAILY_LIMIT} تحميل\n"
        "• بعض الفيديوهات الخاصة غير قابلة للتحميل"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
