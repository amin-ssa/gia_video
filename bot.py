import os
import re
import json
import tempfile
import logging
import aiohttp
from pathlib import Path
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
CHANNEL_INVITE = os.environ.get("CHANNEL_INVITE", "https://t.me/+i3F-wztDdSlmYWNk")

MAX_FILE_SIZE = 200 * 1024 * 1024
TG_UPLOAD_LIMIT = 49 * 1024 * 1024

# Conversation states
WAITING_IG_USERNAME = 1


# ─── Helpers ────────────────────────────────────────────────────────────────

async def is_subscribed(bot, user_id: int) -> bool:
    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        return True
    try:
        member = await bot.get_chat_member(chat_id=int(CHANNEL_ID), user_id=user_id)
        return member.status in [
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
        ]
    except Exception as e:
        logger.warning(f"Subscription check failed: {e}")
        return False


def subscription_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=CHANNEL_INVITE)],
        [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")],
    ])


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ تحميل فيديو", callback_data="download_prompt"),
         InlineKeyboardButton("🎵 تحميل MP3", callback_data="mp3_prompt")],
        [InlineKeyboardButton("🎛️ اختيار الجودة", callback_data="quality_menu"),
         InlineKeyboardButton("📊 فحص حساب انستا", callback_data="ig_check")],
    ])


def quality_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 360p", callback_data="q_360"),
         InlineKeyboardButton("🟢 720p", callback_data="q_720")],
        [InlineKeyboardButton("🟡 1080p", callback_data="q_1080"),
         InlineKeyboardButton("⭐ أعلى جودة", callback_data="q_best")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


# ─── Start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    welcome_text = (
        f"أهلاً {user.first_name}! 👋\n\n"
        "🎬 <b>بوت تحميل الفيديوهات</b>\n\n"
        "📌 <b>المنصات المدعومة:</b>\n"
        "• يوتيوب 🎥\n"
        "• إنستغرام 📸\n"
        "• تيك توك 🎵\n"
        "• تويتر / X 🐦\n"
        "• فيسبوك 👍\n"
        "• وأكثر من 1000 منصة أخرى!\n\n"
        "اختر من القائمة أو أرسل رابطاً مباشرة 👇"
    )

    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        await update.message.reply_text(welcome_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return

    subscribed = await is_subscribed(context.bot, user.id)

    if subscribed:
        await update.message.reply_text(welcome_text, reply_markup=main_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"أهلاً {user.first_name}! 👋\n\n"
            "⚠️ <b>للاستخدام يجب الاشتراك في قناتنا أولاً</b>\n\n"
            "1️⃣ اضغط على زر الاشتراك أدناه\n"
            "2️⃣ اشترك في القناة\n"
            "3️⃣ ارجع واضغط <b>تحقق من الاشتراك</b>",
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )


async def getid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(
        f"🆔 <b>معرف هذه المحادثة:</b>\n<code>{chat.id}</code>\n\n"
        f"النوع: {chat.type}\n"
        f"الاسم: {chat.title or chat.username or chat.first_name}",
        parse_mode="HTML",
    )


# ─── Callback Buttons ────────────────────────────────────────────────────────

async def download_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mode"] = "video"
    await query.message.reply_text(
        "📎 أرسل لي رابط الفيديو أو الصورة وسأقوم بتحميله فوراً!\n\n"
        "مثال:\n"
        "• https://www.youtube.com/watch?v=...\n"
        "• https://www.instagram.com/p/...\n"
        "• https://www.tiktok.com/@.../video/...",
        parse_mode="HTML",
    )


async def mp3_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mode"] = "mp3"
    await query.message.reply_text(
        "🎵 أرسل لي رابط الفيديو وسأستخرج الصوت بصيغة MP3!\n\n"
        "مثال:\n"
        "• https://www.youtube.com/watch?v=...\n"
        "• https://www.tiktok.com/@.../video/...",
        parse_mode="HTML",
    )


async def quality_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current = context.user_data.get("quality", "best")
    labels = {"360": "360p", "720": "720p", "1080": "1080p", "best": "أعلى جودة"}
    await query.edit_message_text(
        f"🎛️ <b>اختر جودة التحميل</b>\n\nالجودة الحالية: <b>{labels.get(current, 'أعلى جودة')}</b>\n\n"
        "بعد الاختيار أرسل الرابط مباشرة.",
        reply_markup=quality_keyboard(),
        parse_mode="HTML",
    )


async def quality_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    q = query.data.replace("q_", "")
    context.user_data["quality"] = q
    context.user_data["mode"] = "video"
    labels = {"360": "360p 🔵", "720": "720p 🟢", "1080": "1080p 🟡", "best": "أعلى جودة ⭐"}
    await query.edit_message_text(
        f"✅ تم اختيار الجودة: <b>{labels.get(q, q)}</b>\n\nأرسل لي الرابط الآن 👇",
        parse_mode="HTML",
    )


async def back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 <b>بوت تحميل الفيديوهات</b>\n\nاختر من القائمة أو أرسل رابطاً مباشرة 👇",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        await query.edit_message_text(
            "✅ <b>تم التحقق! اختر من القائمة أو أرسل رابطاً.</b>",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
        return

    subscribed = await is_subscribed(context.bot, user.id)
    if subscribed:
        await query.edit_message_text(
            "✅ <b>تم التحقق من اشتراكك بنجاح!</b>\n\nاختر من القائمة أو أرسل رابطاً 👇",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            "❌ <b>لم يتم الاشتراك بعد!</b>\n\nتأكد من الاشتراك ثم اضغط تحقق مرة أخرى.",
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )


# ─── Instagram Account Checker ───────────────────────────────────────────────

def extract_ig_username(text: str) -> str:
    text = text.strip()
    # رابط إنستغرام — استخراج اسم المستخدم
    patterns = [
        r"instagram\.com/([A-Za-z0-9_.]+)/?$",
        r"instagram\.com/([A-Za-z0-9_.]+)/?\?",
        r"instagr\.am/([A-Za-z0-9_.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            username = m.group(1)
            # تجاهل مسارات خاصة
            if username.lower() not in ("p", "reel", "stories", "explore", "accounts", "tv"):
                return username.lower()
    # اسم مستخدم مباشر أو @username
    clean = text.lstrip("@").split("?")[0].rstrip("/")
    if re.match(r'^[A-Za-z0-9_.]{1,30}$', clean):
        return clean.lower()
    return ""


async def ig_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mode"] = "ig_check"
    await query.message.reply_text(
        "📊 <b>فحص حساب إنستغرام</b>\n\n"
        "أرسل رابط الحساب أو اسم المستخدم:\n\n"
        "✅ <code>https://www.instagram.com/cristiano/</code>\n"
        "✅ <code>cristiano</code>\n"
        "✅ <code>@cristiano</code>",
        parse_mode="HTML",
    )


async def check_instagram_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    username = extract_ig_username(raw)
    context.user_data["mode"] = None

    if not username:
        await update.message.reply_text(
            "❌ تعذّر استخراج اسم المستخدم.\n\n"
            "أرسل رابط الحساب مثل:\n"
            "<code>https://www.instagram.com/cristiano/</code>",
            parse_mode="HTML",
        )
        return

    status_msg = await update.message.reply_text(f"🔍 جاري فحص حساب @{username} ...")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; SM-G991B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Mobile Safari/537.36 Instagram/313.0.0.0"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ar,en;q=0.9",
        "x-ig-app-id": "936619743392459",
        "x-requested-with": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/{username}/",
    }

    try:
        async with aiohttp.ClientSession() as session:
            # المصدر الأول: web_profile_info
            api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                raw_text = await resp.text()

                if resp.status == 404:
                    await status_msg.edit_text(
                        f"❌ <b>الحساب غير موجود أو محذوف</b>\n\n@{username}",
                        parse_mode="HTML",
                    )
                    return

                if resp.status == 401 or resp.status == 403:
                    await status_msg.edit_text(
                        f"🔒 <b>الحساب خاص أو مقيّد</b>\n\n"
                        f"@{username} لا يسمح بالوصول العام للبيانات.\n\n"
                        f"🔗 <a href='https://www.instagram.com/{username}/'>افتح الحساب مباشرة</a>",
                        parse_mode="HTML",
                        disable_web_page_preview=False,
                    )
                    return

                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")

                try:
                    data = json.loads(raw_text)
                except Exception:
                    raise Exception("فشل تحليل البيانات")

                user = data.get("data", {}).get("user", {})

                if not user:
                    await status_msg.edit_text(
                        f"⚠️ <b>لا توجد بيانات كافية</b>\n\n"
                        f"إنستغرام لم يُرجع بيانات للحساب @{username}.\n"
                        f"قد يكون الحساب محظوراً أو خاصاً جداً.",
                        parse_mode="HTML",
                    )
                    return

        # ── استخراج البيانات ───────────────────────────────────────
        full_name      = user.get("full_name") or "—"
        followers      = user.get("edge_followed_by", {}).get("count", 0)
        following      = user.get("edge_follow", {}).get("count", 0)
        posts          = user.get("edge_owner_to_timeline_media", {}).get("count", 0)
        is_private     = user.get("is_private", False)
        is_verified    = user.get("is_verified", False)
        is_business    = user.get("is_business_account", False)
        is_professional= user.get("is_professional_account", False)
        bio            = user.get("biography", "") or ""
        external_url   = user.get("external_url") or ""
        category       = user.get("category_name") or ""
        profile_pic    = user.get("profile_pic_url_hd") or user.get("profile_pic_url") or ""
        highlight_reel = user.get("highlight_reel_count", 0)
        igtv_count     = user.get("edge_felix_video_timeline", {}).get("count", 0)
        blocked        = user.get("blocked_by_viewer", False)
        restricted     = user.get("restricted_by_viewer", False)

        # ── تقييم الصحة ───────────────────────────────────────────
        score = 100
        risks = []
        goods = []

        # المنشورات
        if posts == 0:
            score -= 35
            risks.append("🚫 لا يوجد أي منشور — خطر حظر مرتفع")
        elif posts < 5:
            score -= 15
            risks.append(f"⚠️ عدد المنشورات قليل جداً ({posts})")
        elif posts < 20:
            score -= 5
            goods.append(f"✅ {posts} منشور (معقول)")
        else:
            goods.append(f"✅ {posts} منشور (نشاط جيد)")

        # المتابعون
        if followers == 0:
            score -= 25
            risks.append("🚫 صفر متابعين")
        elif followers < 10:
            score -= 15
            risks.append(f"⚠️ متابعون قليلون جداً ({followers})")
        elif followers < 100:
            score -= 5
            goods.append(f"✅ {followers:,} متابع")
        else:
            goods.append(f"✅ {followers:,} متابع")

        # نسبة المتابعين/المتابَعين
        if following > 0 and followers >= 0:
            ratio = following / max(followers, 1)
            if ratio > 20:
                score -= 25
                risks.append(f"🚫 نسبة متابَعين/متابعين خطرة ({following:,}/{max(followers,1):,})")
            elif ratio > 5:
                score -= 10
                risks.append(f"⚠️ نسبة متابَعين مرتفعة ({following:,} تتابع / {followers:,} يتابعك)")
            else:
                goods.append(f"✅ نسبة متابعين طبيعية")

        # السيرة الذاتية
        if not bio:
            score -= 10
            risks.append("⚠️ لا توجد سيرة ذاتية (Bio)")
        elif len(bio) < 20:
            score -= 5
            risks.append("⚠️ السيرة الذاتية قصيرة جداً")
        else:
            goods.append("✅ سيرة ذاتية كاملة")

        # صورة الملف الشخصي
        if not profile_pic:
            score -= 10
            risks.append("⚠️ لا توجد صورة ملف شخصي")
        else:
            goods.append("✅ صورة ملف شخصي موجودة")

        # التوثيق والنوع
        if is_verified:
            score = min(100, score + 15)
            goods.append("✅ حساب موثّق رسمياً ✔️")

        if is_business or is_professional:
            goods.append(f"✅ حساب {'تجاري' if is_business else 'مهني'}")

        # رابط خارجي
        if external_url:
            goods.append("✅ رابط خارجي موجود")

        # القيود والحظر
        if blocked:
            score -= 50
            risks.append("🚫 الحساب محظور من عرض البيانات")
        if restricted:
            score -= 20
            risks.append("⚠️ الحساب مقيّد")

        # الحساب الخاص
        if is_private:
            score -= 5
            risks.append("🔒 الحساب خاص (يؤثر على النمو)")

        score = max(0, min(100, score))

        # ── تحديد الحالة ──────────────────────────────────────────
        if score >= 80:
            health_icon = "🟢"
            health_text = "صحة ممتازة"
            ban_risk = "خطر حظر منخفض جداً"
        elif score >= 60:
            health_icon = "🟡"
            health_text = "صحة جيدة"
            ban_risk = "خطر حظر منخفض"
        elif score >= 40:
            health_icon = "🟠"
            health_text = "يحتاج تحسين"
            ban_risk = "خطر حظر متوسط"
        else:
            health_icon = "🔴"
            health_text = "وضع خطر"
            ban_risk = "خطر حظر مرتفع ⚠️"

        # نصيحة مخصصة
        if score < 40:
            tip = ("💡 <b>توصيات عاجلة:</b>\n"
                   "• أضف منشورات حقيقية يومياً\n"
                   "• أضف سيرة ذاتية وصورة ملف\n"
                   "• قلّل من عمليات المتابعة/الإلغاء السريعة\n"
                   "• تفاعل بشكل طبيعي مع المنشورات")
        elif score < 70:
            tip = ("💡 <b>توصيات لتحسين الحساب:</b>\n"
                   "• زد من تكرار النشر\n"
                   "• أكمل بيانات الملف الشخصي\n"
                   "• تفاعل مع متابعيك")
        else:
            tip = "💡 الحساب في وضع جيد. استمر في النشاط الطبيعي والمنتظم."

        # ── بناء التقرير ──────────────────────────────────────────
        result = (
            f"{health_icon} <b>تقرير فحص @{username}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 الاسم الكامل: <b>{full_name}</b>\n"
            f"{'🔒 خاص' if is_private else '🌐 عام'} | "
            f"{'✔️ موثّق' if is_verified else '○ غير موثّق'}"
            f"{' | ' + category if category else ''}\n\n"
            f"📊 <b>الإحصائيات:</b>\n"
            f"• 👥 المتابعون: <b>{followers:,}</b>\n"
            f"• 👣 يتابع: <b>{following:,}</b>\n"
            f"• 📸 المنشورات: <b>{posts}</b>\n"
        )

        if igtv_count:
            result += f"• 📹 IGTV: {igtv_count}\n"
        if highlight_reel:
            result += f"• 🔵 Highlights: {highlight_reel}\n"

        result += (
            f"\n🏥 <b>تقييم الصحة: {score}/100</b>\n"
            f"📌 الحالة: {health_text}\n"
            f"🚨 {ban_risk}\n\n"
        )

        if goods:
            result += "✅ <b>نقاط قوة:</b>\n" + "\n".join(goods) + "\n\n"
        if risks:
            result += "⚠️ <b>نقاط ضعف / مخاطر:</b>\n" + "\n".join(risks) + "\n\n"

        result += tip

        if external_url:
            result += f"\n\n🔗 <a href='{external_url}'>الموقع الإلكتروني</a>"

        await status_msg.edit_text(result, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Instagram check error: {e}")
        await status_msg.edit_text(
            f"❌ تعذّر فحص الحساب @{username}.\n\n"
            "السبب المحتمل: إنستغرام يحجب الطلبات أحياناً. حاول مرة أخرى بعد قليل.",
            parse_mode="HTML",
        )


# ─── Direct Link for Large Files ─────────────────────────────────────────────

async def send_direct_link(update, status_msg, url: str, title: str, file_size: int):
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        direct_url = info.get("url") or info.get("webpage_url") or url
        size_mb = file_size // (1024 * 1024)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ تنزيل الفيديو مباشرة", url=direct_url)],
        ])
        await status_msg.edit_text(
            f"📦 <b>{title}</b>\n\n"
            f"⚠️ حجم الفيديو ({size_mb} MB) كبير جداً للإرسال عبر تيليغرام.\n\n"
            "اضغط الزر أدناه لتنزيله مباشرة على جهازك 👇",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Direct link error: {e}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 فتح الرابط الأصلي", url=url)],
        ])
        await status_msg.edit_text(
            "⚠️ الفيديو كبير جداً للإرسال. اضغط الزر للتنزيل المباشر 👇",
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ─── Download Media ───────────────────────────────────────────────────────────

async def download_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    mode = context.user_data.get("mode")

    # إذا كان في وضع فحص انستا
    if mode == "ig_check":
        await check_instagram_account(update, context)
        return

    # التحقق من الاشتراك
    if CHANNEL_ID and CHANNEL_ID != "-1002000000000":
        subscribed = await is_subscribed(context.bot, user.id)
        if not subscribed:
            await update.message.reply_text(
                "⚠️ يجب الاشتراك في القناة أولاً.",
                reply_markup=subscription_keyboard(),
            )
            return

    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ الرجاء إرسال رابط صحيح يبدأ بـ http:// أو https://\n\n"
            "أو اختر من القائمة:",
            reply_markup=main_keyboard(),
        )
        return

    quality = context.user_data.get("quality", "best")
    is_mp3 = mode == "mp3"

    status_msg = await update.message.reply_text("🔍 جاري فحص الفيديو...")

    info_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 30}

    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "media")[:50]
        estimated_size = info.get("filesize") or info.get("filesize_approx") or 0

        if not is_mp3 and estimated_size > MAX_FILE_SIZE:
            await status_msg.edit_text("🔗 الفيديو أكبر من 200 MB، جاري تجهيز رابط التنزيل المباشر...")
            await send_direct_link(update, status_msg, url, title, estimated_size)
            return

        if is_mp3:
            await status_msg.edit_text("🎵 جاري استخراج الصوت MP3...")
        else:
            labels = {"360": "360p", "720": "720p", "1080": "1080p", "best": "أعلى جودة"}
            await status_msg.edit_text(f"⏳ جاري التحميل بجودة {labels.get(quality, quality)}...")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "%(title).50s.%(ext)s")

            if is_mp3:
                ydl_opts = {
                    "outtmpl": output_path,
                    "format": "bestaudio/best",
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                    "quiet": True,
                    "no_warnings": True,
                    "socket_timeout": 30,
                }
            else:
                fmt_map = {
                    "360": "bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]",
                    "720": "bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]",
                    "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]",
                    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                }
                ydl_opts = {
                    "outtmpl": output_path,
                    "format": fmt_map.get(quality, fmt_map["best"]),
                    "merge_output_format": "mp4",
                    "quiet": True,
                    "no_warnings": True,
                    "socket_timeout": 30,
                }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)

            downloaded_files = list(Path(tmpdir).iterdir())
            if not downloaded_files:
                raise Exception("لم يتم العثور على ملف")

            file_path = str(downloaded_files[0])
            file_size = os.path.getsize(file_path)
            ext = Path(file_path).suffix.lower()

            if not is_mp3 and file_size > MAX_FILE_SIZE:
                await status_msg.edit_text("🔗 الفيديو أكبر من 200 MB، جاري تجهيز رابط التنزيل المباشر...")
                await send_direct_link(update, status_msg, url, title, file_size)
                return

            await status_msg.edit_text("📤 جاري الإرسال...")

            image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

            try:
                with open(file_path, "rb") as media_file:
                    if is_mp3 or ext == ".mp3":
                        await update.message.reply_audio(
                            audio=media_file,
                            title=title,
                            caption=f"🎵 <b>{title}</b>",
                            parse_mode="HTML",
                        )
                    elif ext in image_exts:
                        await update.message.reply_photo(
                            photo=media_file,
                            caption=f"📥 <b>{title}</b>",
                            parse_mode="HTML",
                        )
                    else:
                        await update.message.reply_video(
                            video=media_file,
                            caption=f"📥 <b>{title}</b>",
                            parse_mode="HTML",
                            supports_streaming=True,
                        )
                await status_msg.delete()
            except Exception as upload_err:
                logger.warning(f"Upload failed: {upload_err}")
                await status_msg.edit_text("🔗 تعذّر الإرسال، جاري تجهيز رابط مباشر...")
                await send_direct_link(update, status_msg, url, title, file_size)

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text("❌ فشل التحميل. تأكد أن الرابط صحيح وأن المحتوى متاح للعموم.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await status_msg.edit_text("❌ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.")


async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        chat_id = update.channel_post.chat_id
        chat_title = update.channel_post.chat.title
        print(f"✅ Channel ID: {chat_id} — {chat_title}", flush=True)
        logger.info(f"Channel ID: {chat_id} — {chat_title}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getid", getid_command))

    app.add_handler(CallbackQueryHandler(download_prompt_callback, pattern="^download_prompt$"))
    app.add_handler(CallbackQueryHandler(mp3_prompt_callback, pattern="^mp3_prompt$"))
    app.add_handler(CallbackQueryHandler(quality_menu_callback, pattern="^quality_menu$"))
    app.add_handler(CallbackQueryHandler(quality_select_callback, pattern="^q_(360|720|1080|best)$"))
    app.add_handler(CallbackQueryHandler(back_main_callback, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(ig_check_callback, pattern="^ig_check$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_media))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, channel_post_handler))

    logger.info("Bot started!")
    print("🤖 البوت يعمل الآن...", flush=True)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
