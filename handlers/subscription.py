"""
handlers/subscription.py – نظام الاشتراك الإجباري
✅ يدعم: قنوات متعددة، حد أقصى للمشتركين، إيقاف تلقائي
"""
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from database.db import get_setting, set_setting
from utils.config import ADMIN_IDS

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DB helpers  (تُخزَّن القنوات كـ JSON في جدول settings)
# ─────────────────────────────────────────────────────────────────────────────

CHANNELS_KEY   = "sub_channels"      # list of {id, username, name, limit, count, active}
SUB_ACTIVE_KEY = "sub_active"        # "1" | "0"  – هل الاشتراك الإجباري مفعّل؟


def _load_channels() -> list[dict]:
    raw = get_setting(CHANNELS_KEY)
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _save_channels(channels: list[dict]):
    set_setting(CHANNELS_KEY, json.dumps(channels, ensure_ascii=False))


def is_sub_active() -> bool:
    """هل الاشتراك الإجباري مفعّل حالياً؟"""
    return get_setting(SUB_ACTIVE_KEY) == "1"


def set_sub_active(val: bool):
    set_setting(SUB_ACTIVE_KEY, "1" if val else "0")


# ─────────────────────────────────────────────────────────────────────────────
# Core check
# ─────────────────────────────────────────────────────────────────────────────

async def check_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    تحقق هل المستخدم مشترك في جميع القنوات الإجبارية.
    إذا لا → يرسل رسالة الاشتراك ويرجع False.
    إذا نعم → يرجع True (يكمل البوت طبيعي).
    أدمن → دائماً True.
    """
    user = update.effective_user

    # الأدمن معفي دائماً
    if user.id in ADMIN_IDS:
        return True

    # الاشتراك الإجباري مطفي؟
    if not is_sub_active():
        return True

    channels = _load_channels()
    active_channels = [c for c in channels if c.get("active", True)]

    if not active_channels:
        return True

    not_joined = []
    for ch in active_channels:
        try:
            member = await ctx.bot.get_chat_member(ch["id"], user.id)
            if member.status in ("left", "kicked", "restricted"):
                not_joined.append(ch)
        except TelegramError as e:
            logger.warning(f"get_chat_member error for {ch['id']}: {e}")
            # إذا ما قدر يتحقق، نعتبره غير مشترك
            not_joined.append(ch)

    if not not_joined:
        return True

    # ── بناء رسالة الاشتراك ──────────────────────────────────────────────────
    buttons = []
    for ch in not_joined:
        label = ch.get("name") or ch.get("username") or str(ch["id"])
        link  = f"https://t.me/{ch['username'].lstrip('@')}" if ch.get("username") else ch.get("invite_link", "#")
        buttons.append([InlineKeyboardButton(f"📢 {label}", url=link)])

    buttons.append([
        InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="sub_verify")
    ])

    text = (
        "🔒 *اشتراك إجباري*\n\n"
        "للاستمرار في استخدام البوت، يجب الاشتراك في القنوات التالية:\n\n"
        + "\n".join(f"  📌 {ch.get('name', ch['id'])}" for ch in not_joined)
        + "\n\n_بعد الاشتراك اضغط زر التحقق ✅_"
    )

    target = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        try:
            await update.callback_query.answer("⚠️ يجب الاشتراك أولاً!", show_alert=True)
        except Exception:
            pass
        await update.callback_query.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    return False


async def verify_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """زر 'تحققت من الاشتراك'"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    channels = _load_channels()
    active_channels = [c for c in channels if c.get("active", True)]

    not_joined = []
    for ch in active_channels:
        try:
            member = await ctx.bot.get_chat_member(ch["id"], user.id)
            if member.status in ("left", "kicked", "restricted"):
                not_joined.append(ch)
        except TelegramError:
            not_joined.append(ch)

    if not_joined:
        buttons = []
        for ch in not_joined:
            label = ch.get("name") or ch.get("username") or str(ch["id"])
            link  = f"https://t.me/{ch['username'].lstrip('@')}" if ch.get("username") else ch.get("invite_link", "#")
            buttons.append([InlineKeyboardButton(f"📢 {label}", url=link)])
        buttons.append([InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="sub_verify")])

        await query.edit_message_text(
            "❌ *لم تشترك في جميع القنوات بعد!*\n\n"
            + "\n".join(f"  ❗ {ch.get('name', ch['id'])}" for ch in not_joined)
            + "\n\n_اشترك ثم اضغط التحقق مرة أخرى_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ✅ مشترك في الكل
    await query.edit_message_text(
        "✅ *تم التحقق بنجاح!*\n\n"
        "أهلاً بك! الآن يمكنك استخدام البوت بحرية 🎉\n"
        "أرسل رابط الفيديو الذي تريد تحميله ⬇️",
        parse_mode="Markdown"
    )

    # ── تحديث عداد الاشتراكات ────────────────────────────────────────────────
    _increment_sub_counts(ctx, user.id)


def _increment_sub_counts(ctx, user_id: int):
    """
    زِد عداد كل قناة وتحقق من الحد الأقصى.
    إذا وصلت قناة للحد → عطّلها تلقائياً.
    إذا كل القنوات وصلت حدها → أوقف الاشتراك الإجباري كله.
    """
    channels = _load_channels()
    changed = False

    for ch in channels:
        if not ch.get("active", True):
            continue
        limit = ch.get("limit", 0)
        ch["count"] = ch.get("count", 0) + 1
        changed = True

        if limit > 0 and ch["count"] >= limit:
            ch["active"] = False
            logger.info(
                f"📢 القناة '{ch.get('name', ch['id'])}' وصلت الحد ({limit}). تم إيقافها."
            )

    if changed:
        _save_channels(channels)

    # إذا كل القنوات النشطة وصلت حدها → أوقف الاشتراك الإجباري
    active_remaining = [c for c in channels if c.get("active", True) and c.get("limit", 0) > 0]
    if not active_remaining:
        all_with_limit = [c for c in channels if c.get("limit", 0) > 0]
        if all_with_limit:
            set_sub_active(False)
            logger.info("🛑 جميع القنوات وصلت الحد. تم إيقاف الاشتراك الإجباري تلقائياً.")


# ─────────────────────────────────────────────────────────────────────────────
# Admin: إدارة القنوات
# ─────────────────────────────────────────────────────────────────────────────

def build_sub_admin_kb() -> InlineKeyboardMarkup:
    active = is_sub_active()
    toggle_text = "🔴 إيقاف الاشتراك الإجباري" if active else "🟢 تفعيل الاشتراك الإجباري"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_text, callback_data="sub_toggle")],
        [
            InlineKeyboardButton("➕ إضافة قناة",    callback_data="sub_add"),
            InlineKeyboardButton("🗑️ حذف قناة",      callback_data="sub_remove"),
        ],
        [InlineKeyboardButton("📋 القنوات الحالية",  callback_data="sub_list")],
        [InlineKeyboardButton("🔄 إعادة تعيين العدادات", callback_data="sub_reset_counts")],
        [InlineKeyboardButton("◀️ رجوع للوحة الرئيسية", callback_data="admin_back")],
    ])


async def sub_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """نقطة دخول لوحة الاشتراك من لوحة الأدمن"""
    channels  = _load_channels()
    active    = is_sub_active()
    status    = "🟢 مفعّل" if active else "🔴 موقوف"

    total_verified = sum(c.get("count", 0) for c in channels)
    ch_lines = []
    for c in channels:
        state = "✅" if c.get("active", True) else "⛔"
        limit_str = f"/{c['limit']}" if c.get("limit", 0) > 0 else "/∞"
        ch_lines.append(
            f"  {state} {c.get('name','—')} | 👤{c.get('count',0)}{limit_str}"
        )

    text = (
        "📢 *إدارة الاشتراك الإجباري*\n\n"
        f"الحالة: *{status}*\n"
        f"إجمالي التحققات: `{total_verified}`\n\n"
        "*القنوات:*\n"
        + ("\n".join(ch_lines) if ch_lines else "  لا توجد قنوات بعد")
    )

    query = update.callback_query
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=build_sub_admin_kb())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=build_sub_admin_kb())


async def sub_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالج callbacks لوحة الاشتراك"""
    query = update.callback_query
    user  = update.effective_user
    await query.answer()
    data  = query.data

    if user.id not in ADMIN_IDS:
        await query.answer("⛔ للأدمن فقط!", show_alert=True)
        return

    # ── التبديل ───────────────────────────────────────────────────────────────
    if data == "sub_toggle":
        new_val = not is_sub_active()
        set_sub_active(new_val)
        status = "🟢 تم تفعيل الاشتراك الإجباري" if new_val else "🔴 تم إيقاف الاشتراك الإجباري"
        await query.answer(status, show_alert=True)
        await sub_admin_panel(update, ctx)

    # ── إضافة قناة ───────────────────────────────────────────────────────────
    elif data == "sub_add":
        ctx.user_data["sub_step"] = "awaiting_channel"
        await query.edit_message_text(
            "➕ *إضافة قناة جديدة*\n\n"
            "أرسل معرف القناة بهذا الشكل:\n\n"
            "`@username حد_الاشتراك`\n\n"
            "مثال:\n"
            "`@mychannel 100`\n"
            "→ يتوقف بعد 100 شخص يتحققون\n\n"
            "`@mychannel 0`\n"
            "→ بلا حد (الاشتراك دائم)\n\n"
            "اكتب /cancel للإلغاء",
            parse_mode="Markdown"
        )

    # ── حذف قناة ─────────────────────────────────────────────────────────────
    elif data == "sub_remove":
        channels = _load_channels()
        if not channels:
            await query.answer("لا توجد قنوات!", show_alert=True)
            return
        buttons = [
            [InlineKeyboardButton(
                f"🗑️ {c.get('name', c['id'])}",
                callback_data=f"sub_del_{i}"
            )]
            for i, c in enumerate(channels)
        ]
        buttons.append([InlineKeyboardButton("◀️ رجوع", callback_data="sub_panel")])
        await query.edit_message_text(
            "🗑️ *اختر القناة للحذف:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("sub_del_"):
        idx      = int(data.split("_")[2])
        channels = _load_channels()
        if 0 <= idx < len(channels):
            removed = channels.pop(idx)
            _save_channels(channels)
            await query.answer(f"✅ تم حذف {removed.get('name', removed['id'])}", show_alert=True)
        await sub_admin_panel(update, ctx)

    # ── قائمة القنوات ─────────────────────────────────────────────────────────
    elif data == "sub_list":
        channels = _load_channels()
        if not channels:
            await query.edit_message_text(
                "📋 لا توجد قنوات مضافة بعد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ رجوع", callback_data="sub_panel")
                ]])
            )
            return

        lines = []
        for i, c in enumerate(channels, 1):
            state     = "✅ نشط" if c.get("active", True) else "⛔ متوقف"
            limit_str = f"{c['limit']}" if c.get("limit", 0) > 0 else "∞"
            lines.append(
                f"*{i}.* {c.get('name','—')}\n"
                f"   🆔 `{c['id']}`\n"
                f"   📊 {c.get('count',0)} / {limit_str} تحقق\n"
                f"   الحالة: {state}"
            )

        await query.edit_message_text(
            "📋 *القنوات المضافة:*\n\n" + "\n\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="sub_panel")
            ]])
        )

    # ── إعادة تعيين العدادات ─────────────────────────────────────────────────
    elif data == "sub_reset_counts":
        channels = _load_channels()
        for c in channels:
            c["count"]  = 0
            c["active"] = True
        _save_channels(channels)
        set_sub_active(True)
        await query.answer("✅ تم إعادة تعيين جميع العدادات وتفعيل القنوات", show_alert=True)
        await sub_admin_panel(update, ctx)

    # ── العودة للوحة الاشتراك ─────────────────────────────────────────────────
    elif data == "sub_panel":
        await sub_admin_panel(update, ctx)


async def handle_add_channel_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    يستقبل رسالة الأدمن عند إضافة قناة.
    يرجع True إذا عالج الرسالة، False إذا لم تكن خطوة إضافة قناة.
    """
    if ctx.user_data.get("sub_step") != "awaiting_channel":
        return False

    if update.effective_user.id not in ADMIN_IDS:
        return False

    text  = update.message.text.strip()
    parts = text.split()

    if len(parts) < 1:
        await update.message.reply_text("❌ تنسيق خاطئ. مثال: `@mychannel 100`", parse_mode="Markdown")
        return True

    username_raw = parts[0]
    limit        = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0

    # تأكد من وجود @ في البداية
    if not username_raw.startswith("@"):
        username_raw = "@" + username_raw

    # جلب معلومات القناة من تيليغرام
    try:
        chat: Chat = await ctx.bot.get_chat(username_raw)
        ch_id    = chat.id
        ch_name  = chat.title or username_raw
        ch_user  = chat.username or ""
    except TelegramError as e:
        await update.message.reply_text(
            f"❌ لم أتمكن من الوصول للقناة `{username_raw}`\n"
            f"تأكد أن البوت أدمن في القناة!\n\n`{e}`",
            parse_mode="Markdown"
        )
        ctx.user_data.pop("sub_step", None)
        return True

    # إضافة للقائمة
    channels = _load_channels()

    # لا تكرر
    if any(c["id"] == ch_id for c in channels):
        await update.message.reply_text(
            f"⚠️ القناة `{ch_name}` مضافة مسبقاً!",
            parse_mode="Markdown"
        )
        ctx.user_data.pop("sub_step", None)
        return True

    channels.append({
        "id":       ch_id,
        "username": ch_user,
        "name":     ch_name,
        "limit":    limit,
        "count":    0,
        "active":   True,
    })
    _save_channels(channels)

    # تفعيل الاشتراك الإجباري تلقائياً
    set_sub_active(True)

    ctx.user_data.pop("sub_step", None)

    limit_str = f"`{limit}` شخص" if limit > 0 else "بلا حد"
    await update.message.reply_text(
        f"✅ *تمت إضافة القناة بنجاح!*\n\n"
        f"📢 الاسم: `{ch_name}`\n"
        f"🆔 ID: `{ch_id}`\n"
        f"🎯 الحد: {limit_str}\n\n"
        f"🟢 الاشتراك الإجباري مفعّل الآن.",
        parse_mode="Markdown"
    )
    return True
