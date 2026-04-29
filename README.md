# ⬇️ MediaDrop Bot

بوت تيليغرام لتحميل الفيديوهات من جميع المنصات، مع لوحة أدمن كاملة.

---

## 🌐 المنصات المدعومة

| المنصة | الحالة |
|--------|--------|
| 🎬 YouTube | ✅ |
| 🎵 TikTok | ✅ |
| 📸 Instagram | ✅ |
| 📘 Facebook | ✅ |
| 🐦 Twitter / X | ✅ |
| ✈️ Telegram | ✅ |
| 🟣 Twitch | ✅ |
| 🎞️ Vimeo | ✅ |
| 🤖 Reddit | ✅ |
| 📌 Pinterest | ✅ |
| 👻 Snapchat | ✅ |
| 🎧 SoundCloud | ✅ |
| 🎥 Dailymotion | ✅ |
| 🌐 +1000 موقع آخر (عبر yt-dlp) | ✅ |

---

## 🚀 الرفع على Railway

### الخطوة 1: إنشاء البوت
1. افتح [@BotFather](https://t.me/BotFather) في تيليغرام
2. أرسل `/newbot` واتبع التعليمات
3. احفظ الـ **BOT_TOKEN**

### الخطوة 2: احصل على ID الأدمن
- ابعث رسالة لـ [@userinfobot](https://t.me/userinfobot) لتحصل على ID حسابك

### الخطوة 3: الرفع على Railway

```bash
# 1. سجل دخول على railway.app
# 2. أنشئ مشروع جديد → Deploy from GitHub
# 3. ارفع الملفات لـ GitHub ثم اربط المشروع
```

أو باستخدام Railway CLI:
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### الخطوة 4: إضافة متغيرات البيئة
في Railway → Settings → Variables أضف:

```
BOT_TOKEN    = توكن البوت
ADMIN_IDS    = ID الأدمن
MAX_FILESIZE_MB = 50
DAILY_LIMIT  = 20
```

### الخطوة 5: تشغيل البوت
بعد الرفع، Railway سيشغل البوت تلقائياً. 🎉

---

## 📁 هيكل المشروع

```
mediabot/
├── bot.py                  # نقطة الدخول الرئيسية
├── requirements.txt        # المكتبات المطلوبة
├── nixpacks.toml           # إعدادات Railway (تثبيت ffmpeg)
├── railway.json            # إعدادات النشر
├── Procfile                # أمر التشغيل
├── .env.example            # مثال على المتغيرات
├── handlers/
│   ├── start.py            # /start و /help
│   ├── download.py         # منطق التحميل
│   └── admin.py            # لوحة الأدمن
├── database/
│   └── db.py               # SQLite database
└── utils/
    └── config.py           # الإعدادات
```

---

## 🛡️ أوامر الأدمن

| الأمر | الوصف |
|-------|-------|
| `/admin` | فتح لوحة الإدارة الكاملة |
| `/broadcast رسالة` | إرسال رسالة لجميع المستخدمين |
| `/ban USER_ID` | حظر مستخدم |
| `/unban USER_ID` | رفع الحظر عن مستخدم |
| `/stats` | عرض الإحصائيات التفصيلية |

---

## ⚙️ لوحة الأدمن تحتوي على:
- 📊 إحصائيات مفصلة (مستخدمين، تحميلات، منصات)
- 👥 قائمة جميع المستخدمين
- 🚫 إدارة المحظورين
- 📢 بث رسائل جماعية
- 🔧 وضع الصيانة
- ⚙️ تغيير رسالة الترحيب
- 📋 آخر التحميلات

---

## 🔧 التطوير المحلي

```bash
git clone <repo>
cd mediabot
pip install -r requirements.txt

# أنشئ ملف .env من المثال
cp .env.example .env
# عدّل القيم في .env

python bot.py
```

---

## 📝 ملاحظات
- يستخدم **SQLite** لقاعدة البيانات (لا يحتاج إعداد)
- يستخدم **yt-dlp** للتحميل (يدعم +1000 موقع)
- يستخدم **FFmpeg** للتحويل (مثبت تلقائياً على Railway)
- الحد الأقصى للملف: 50 ميجا (حد تيليغرام المجاني)
