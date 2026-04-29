"""
handlers/start.py – /start و /help
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import upsert_user, get_setting
from utils.config import PLATFORMS


async def start_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.full_name)

    welcome = get_setting("welcome_msg") or "مرحباً! 🎉"

    platforms_list = "\n".join(
        f"  {v['emoji']} {v['name']}" for k, v in PLATFORMS.items()
        if k not in ("youtu.be", "fb.watch", "x.com")  # نخفي الـ aliases
    )

    text = f"""
╔══════════════════════════╗
║   ⬇️  *MediaDrop Bot*  ⬇️   ║
╚══════════════════════════╝

{welcome}

أرسل أي رابط فيديو وسأحمّله لك فوراً! 🚀

*المنصات المدعومة:*
{platforms_list}

📌 فقط أرسل الرابط مباشرة!
"""

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 كيفية الاستخدام", callback_data="help_usage"),
            InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats"),
        ],
        [
            InlineKeyboardButton("💬 الدعم", url="https://t.me/your_support"),
        ]
    ])

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def help_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = """
📖 *كيفية الاستخدام*

1️⃣ انسخ رابط الفيديو من أي منصة
2️⃣ أرسله هنا مباشرة
3️⃣ اختر جودة التحميل
4️⃣ انتظر ثوانٍ وستصلك الملف! ✅

*الأوامر المتاحة:*
/start – الصفحة الرئيسية
/help – المساعدة
/stats – إحصائياتك

*ملاحظات:*
• الحد الأقصى للملف: 50 ميجا
• الحد اليومي: 20 تحميل
• بعض الفيديوهات الخاصة غير قابلة للتحميل
"""
    await update.message.reply_text(text, parse_mode="Markdown")
