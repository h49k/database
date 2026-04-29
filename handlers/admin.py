"""
handlers/admin.py – لوحة الأدمن الكاملة مع أزرار Inline
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import (
    get_stats, get_all_users, ban_user, unban_user,
    get_setting, set_setting
)
from utils.config import ADMIN_IDS

logger = logging.getLogger(__name__)

# ─── Decorator: Admin only ────────────────────────────────────────────────────
def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in ADMIN_IDS:
            target = update.message or (update.callback_query and update.callback_query.message)
            if update.callback_query:
                await update.callback_query.answer("⛔ ليس لديك صلاحية!", show_alert=True)
            elif update.message:
                await update.message.reply_text("⛔ هذا الأمر للأدمن فقط!")
            return
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ─── Main Admin Panel ─────────────────────────────────────────────────────────

def build_admin_keyboard() -> InlineKeyboardMarkup:
    maintenance = get_setting("maintenance") == "1"
    maint_text = "✅ تفعيل الموقع" if maintenance else "🔧 وضع الصيانة"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 الإحصائيات",     callback_data="admin_stats"),
            InlineKeyboardButton("👥 المستخدمين",     callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("📢 بث رسالة",       callback_data="admin_broadcast"),
            InlineKeyboardButton("🚫 المحظورين",       callback_data="admin_banned"),
        ],
        [
            InlineKeyboardButton(maint_text,           callback_data="admin_maintenance"),
            InlineKeyboardButton("📢 الاشتراك الإجباري", callback_data="admin_sub"),
        ],
        [
            InlineKeyboardButton("⚙️ الإعدادات",      callback_data="admin_settings"),
        ],
        [
            InlineKeyboardButton("📋 آخر التحميلات",   callback_data="admin_recent"),
            InlineKeyboardButton("🔄 تحديث",           callback_data="admin_refresh"),
        ],
    ])


@admin_only
async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    maintenance = get_setting("maintenance") == "1"
    status_icon = "🔴 صيانة" if maintenance else "🟢 يعمل"

    text = (
        "╔══════════════════════════╗\n"
        "║   🛡️  *لوحة الإدارة*  🛡️   ║\n"
        "╚══════════════════════════╝\n\n"
        f"🔵 الحالة: *{status_icon}*\n\n"
        f"👥 إجمالي المستخدمين: `{stats['total_users']}`\n"
        f"⬇️ إجمالي التحميلات: `{stats['total_dl']}`\n"
        f"📅 تحميلات اليوم: `{stats['today_dl']}`\n"
        f"🏆 أكثر منصة: `{stats['top_platform']}`\n"
        f"🚫 المحظورون: `{stats['banned']}`\n\n"
        "اختر من القائمة أدناه:"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=build_admin_keyboard()
    )


# ─── Callback Router ──────────────────────────────────────────────────────────

@admin_only
async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_stats":
        await _show_stats(query)

    elif data == "admin_users":
        await _show_users(query)

    elif data == "admin_banned":
        await _show_banned(query)

    elif data == "admin_broadcast":
        ctx.user_data["awaiting_broadcast"] = True
        await query.edit_message_text(
            "📢 *بث رسالة*\n\n"
            "أرسل الرسالة التي تريد إرسالها لجميع المستخدمين.\n"
            "يدعم: النصوص والصور والفيديوهات\n\n"
            "اكتب /cancel للإلغاء.",
            parse_mode="Markdown"
        )

    elif data == "admin_maintenance":
        current = get_setting("maintenance")
        new_val = "0" if current == "1" else "1"
        set_setting("maintenance", new_val)
        status = "🔧 تم تفعيل وضع الصيانة" if new_val == "1" else "✅ تم إعادة تشغيل البوت"
        await query.answer(status, show_alert=True)
        # إعادة تحميل اللوحة
        stats = get_stats()
        maintenance = new_val == "1"
        status_icon = "🔴 صيانة" if maintenance else "🟢 يعمل"
        text = (
            "╔══════════════════════════╗\n"
            "║   🛡️  *لوحة الإدارة*  🛡️   ║\n"
            "╚══════════════════════════╝\n\n"
            f"🔵 الحالة: *{status_icon}*\n\n"
            f"👥 إجمالي المستخدمين: `{stats['total_users']}`\n"
            f"⬇️ إجمالي التحميلات: `{stats['total_dl']}`\n"
            f"📅 تحميلات اليوم: `{stats['today_dl']}`\n"
            f"🏆 أكثر منصة: `{stats['top_platform']}`\n"
            f"🚫 المحظورون: `{stats['banned']}`\n\n"
            "اختر من القائمة أدناه:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=build_admin_keyboard())

    elif data == "admin_settings":
        await _show_settings(query, ctx)

    elif data == "admin_sub":
        # تحويل للوحة الاشتراك الإجباري
        from handlers.subscription import sub_admin_panel
        await sub_admin_panel(update, ctx)

    elif data == "admin_recent":
        await _show_recent(query)

    elif data == "admin_refresh":
        stats = get_stats()
        await query.answer("✅ تم التحديث")
        maintenance = get_setting("maintenance") == "1"
        status_icon = "🔴 صيانة" if maintenance else "🟢 يعمل"
        text = (
            "╔══════════════════════════╗\n"
            "║   🛡️  *لوحة الإدارة*  🛡️   ║\n"
            "╚══════════════════════════╝\n\n"
            f"🔵 الحالة: *{status_icon}*\n\n"
            f"👥 إجمالي المستخدمين: `{stats['total_users']}`\n"
            f"⬇️ إجمالي التحميلات: `{stats['total_dl']}`\n"
            f"📅 تحميلات اليوم: `{stats['today_dl']}`\n"
            f"🏆 أكثر منصة: `{stats['top_platform']}`\n"
            f"🚫 المحظورون: `{stats['banned']}`\n\n"
            "اختر من القائمة أدناه:"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=build_admin_keyboard())

    elif data.startswith("admin_unban_"):
        uid = int(data.split("_")[2])
        unban_user(uid)
        await query.answer(f"✅ تم رفع الحظر عن {uid}")
        await _show_banned(query)

    elif data == "admin_back":
        stats = get_stats()
        maintenance = get_setting("maintenance") == "1"
        status_icon = "🔴 صيانة" if maintenance else "🟢 يعمل"
        text = (
            "╔══════════════════════════╗\n"
            "║   🛡️  *لوحة الإدارة*  🛡️   ║\n"
            "╚══════════════════════════╝\n\n"
            f"🔵 الحالة: *{status_icon}*\n\n"
            f"👥 المستخدمين: `{stats['total_users']}`\n"
            f"⬇️ التحميلات: `{stats['total_dl']}`\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=build_admin_keyboard())

    elif data == "admin_set_welcome":
        ctx.user_data["awaiting_welcome"] = True
        await query.edit_message_text(
            "✏️ أرسل رسالة الترحيب الجديدة:\n\n"
            "اكتب /cancel للإلغاء."
        )


# ─── Sub-pages ────────────────────────────────────────────────────────────────

async def _show_stats(query):
    from database.db import get_conn
    conn = get_conn()

    # إحصائيات المنصات
    platforms = conn.execute(
        "SELECT platform, COUNT(*) as c FROM downloads WHERE status='success' "
        "GROUP BY platform ORDER BY c DESC LIMIT 8"
    ).fetchall()

    # إحصائيات آخر 7 أيام
    week = conn.execute(
        "SELECT date(created_at) as d, COUNT(*) as c FROM downloads "
        "WHERE status='success' AND date(created_at) >= date('now','-7 days') "
        "GROUP BY d ORDER BY d"
    ).fetchall()
    conn.close()

    stats = get_stats()

    platforms_text = "\n".join(
        f"  {'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '▪️'} {r['platform']}: `{r['c']}`"
        for i, r in enumerate(platforms)
    ) or "  لا توجد بيانات بعد"

    week_text = "\n".join(
        f"  📅 {r['d']}: `{r['c']}`"
        for r in week
    ) or "  لا توجد بيانات"

    text = (
        "📊 *الإحصائيات التفصيلية*\n\n"
        f"👥 إجمالي المستخدمين: `{stats['total_users']}`\n"
        f"⬇️ إجمالي التحميلات: `{stats['total_dl']}`\n"
        f"📅 اليوم: `{stats['today_dl']}`\n"
        f"🚫 المحظورون: `{stats['banned']}`\n\n"
        "🏆 *أكثر المنصات استخداماً:*\n"
        f"{platforms_text}\n\n"
        "📈 *آخر 7 أيام:*\n"
        f"{week_text}"
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ رجوع", callback_data="admin_back")
    ]])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def _show_users(query):
    users = get_all_users()
    if not users:
        text = "👥 لا يوجد مستخدمون بعد."
    else:
        lines = []
        for u in users[:20]:  # أول 20
            icon = "🚫" if u["is_banned"] else "✅"
            name = u["full_name"] or u["username"] or str(u["user_id"])
            lines.append(f"{icon} `{u['user_id']}` | {name[:20]} | ⬇️{u['total_dl']}")
        text = f"👥 *المستخدمون* ({len(users)} إجمالاً)\n\n" + "\n".join(lines)
        if len(users) > 20:
            text += f"\n\n_...و {len(users)-20} آخرين_"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ رجوع", callback_data="admin_back")
    ]])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def _show_banned(query):
    users = [u for u in get_all_users() if u["is_banned"]]
    if not users:
        text = "✅ لا يوجد مستخدمون محظورون."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="admin_back")]])
    else:
        text = f"🚫 *المحظورون* ({len(users)})\n\n"
        buttons = []
        for u in users[:10]:
            name = u["full_name"] or u["username"] or str(u["user_id"])
            text += f"• `{u['user_id']}` — {name[:20]}\n"
            buttons.append([
                InlineKeyboardButton(
                    f"✅ رفع حظر {name[:15]}",
                    callback_data=f"admin_unban_{u['user_id']}"
                )
            ])
        buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="admin_back")])
        kb = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def _show_settings(query, ctx):
    welcome = get_setting("welcome_msg") or "—"
    maintenance = "🔴 مفعّل" if get_setting("maintenance") == "1" else "🟢 معطّل"

    text = (
        "⚙️ *الإعدادات*\n\n"
        f"📝 رسالة الترحيب:\n`{welcome[:100]}`\n\n"
        f"🔧 وضع الصيانة: {maintenance}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تغيير رسالة الترحيب", callback_data="admin_set_welcome")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="admin_back")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def _show_recent(query):
    from database.db import get_conn
    conn = get_conn()
    rows = conn.execute(
        "SELECT d.user_id, d.platform, d.status, d.created_at, u.full_name "
        "FROM downloads d LEFT JOIN users u ON d.user_id=u.user_id "
        "ORDER BY d.created_at DESC LIMIT 15"
    ).fetchall()
    conn.close()

    if not rows:
        text = "📋 لا توجد تحميلات بعد."
    else:
        lines = []
        for r in rows:
            icon = "✅" if r["status"] == "success" else "❌"
            name = (r["full_name"] or str(r["user_id"]))[:12]
            lines.append(f"{icon} {r['platform']} | {name} | {r['created_at'][11:16]}")
        text = "📋 *آخر التحميلات:*\n\n" + "\n".join(lines)

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ رجوع", callback_data="admin_back")]])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


# ─── Broadcast ────────────────────────────────────────────────────────────────

@admin_only
async def broadcast_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    الاستخدام: /broadcast رسالتك هنا
    """
    args = update.message.text.split(None, 1)
    if len(args) < 2:
        await update.message.reply_text(
            "📢 *كيفية البث:*\n`/broadcast رسالتك هنا`",
            parse_mode="Markdown"
        )
        return

    message_text = args[1]
    users = get_all_users()
    active_users = [u for u in users if not u["is_banned"]]

    progress = await update.message.reply_text(
        f"📢 جاري إرسال الرسالة لـ {len(active_users)} مستخدم..."
    )

    sent = 0
    failed = 0
    for u in active_users:
        try:
            await ctx.bot.send_message(
                chat_id=u["user_id"],
                text=f"📢 *رسالة من الإدارة:*\n\n{message_text}",
                parse_mode="Markdown"
            )
            sent += 1
        except Exception:
            failed += 1

    await progress.edit_text(
        f"✅ *اكتمل البث*\n\n"
        f"✅ تم الإرسال: `{sent}`\n"
        f"❌ فشل: `{failed}`\n"
        f"📊 الإجمالي: `{len(active_users)}`",
        parse_mode="Markdown"
    )


# ─── Ban / Unban Commands ─────────────────────────────────────────────────────

@admin_only
async def ban_user_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الاستخدام: /ban USER_ID"""
    args = update.message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await update.message.reply_text("❌ الاستخدام: `/ban USER_ID`", parse_mode="Markdown")
        return

    uid = int(args[1])
    ban_user(uid)
    await update.message.reply_text(f"🚫 تم حظر المستخدم `{uid}`", parse_mode="Markdown")


@admin_only
async def unban_user_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الاستخدام: /unban USER_ID"""
    args = update.message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await update.message.reply_text("❌ الاستخدام: `/unban USER_ID`", parse_mode="Markdown")
        return

    uid = int(args[1])
    unban_user(uid)
    await update.message.reply_text(f"✅ تم رفع الحظر عن `{uid}`", parse_mode="Markdown")


# ─── Stats Command ────────────────────────────────────────────────────────────

async def stats_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """متاح للجميع – يعرض إحصائيات المستخدم"""
    from database.db import get_daily_count, get_conn
    user = update.effective_user
    conn = get_conn()
    row = conn.execute(
        "SELECT total_dl FROM users WHERE user_id=?", (user.id,)
    ).fetchone()
    conn.close()

    total  = row["total_dl"] if row else 0
    today  = get_daily_count(user.id)

    text = (
        f"📊 *إحصائياتك*\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"🆔 ID: `{user.id}`\n"
        f"⬇️ إجمالي تحميلاتك: `{total}`\n"
        f"📅 تحميلات اليوم: `{today}/{DAILY_LIMIT}`\n"
    )

    # إذا أدمن، أضف إحصائيات عامة
    if user.id in ADMIN_IDS:
        s = get_stats()
        text += (
            f"\n*─ إحصائيات البوت ─*\n"
            f"👥 إجمالي المستخدمين: `{s['total_users']}`\n"
            f"⬇️ إجمالي التحميلات: `{s['total_dl']}`\n"
            f"📅 تحميلات اليوم: `{s['today_dl']}`\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")
