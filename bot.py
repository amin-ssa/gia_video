# ══════════════════════════════════════════════════════════════════════════════
#  Telegram Bot — Video Downloader + Instagram Checker + Voice Cloning
# ══════════════════════════════════════════════════════════════════════════════

# ─── IMPORTS ──────────────────────────────────────────────────────────────────
import os
import re
import json
import tempfile
import logging
import asyncio
from pathlib import Path

import aiohttp
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN      = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "").strip()
CHANNEL_INVITE = os.environ.get("CHANNEL_INVITE", "https://t.me/+i3F-wztDdSlmYWNk")
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_KEY", "")
GEMINI_KEY     = os.environ.get("GEMINI_KEY", "")

MAX_FILE_SIZE  = 200 * 1024 * 1024
TG_UPLOAD_LIMIT =  49 * 1024 * 1024

EL_CLONE_URL = "https://api.elevenlabs.io/v1/voices/add"
EL_TTS_URL   = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
EL_DEL_URL   = "https://api.elevenlabs.io/v1/voices/{voice_id}"

# ══════════════════════════════════════════════════════════════════════════════
#  ░░  KEYBOARDS  ░░
# ══════════════════════════════════════════════════════════════════════════════

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬇️ تحميل فيديو",         callback_data="download_prompt"),
            InlineKeyboardButton("🎵 تحميل MP3",            callback_data="mp3_prompt"),
        ],
        [
            InlineKeyboardButton("🎛️ اختيار الجودة",        callback_data="quality_menu"),
            InlineKeyboardButton("📊 فحص انستا",             callback_data="ig_check"),
        ],
        [
            InlineKeyboardButton("🎤 استنساخ الصوت",        callback_data="voice_clone"),
        ],
        [
            InlineKeyboardButton("🧠 تحميل فيديو مع تحليل", callback_data="smart_download"),
        ],
    ])


def quality_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔵 360p",  callback_data="q_360"),
            InlineKeyboardButton("🟢 720p",  callback_data="q_720"),
        ],
        [
            InlineKeyboardButton("🟡 1080p", callback_data="q_1080"),
            InlineKeyboardButton("⭐ أعلى",  callback_data="q_best"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


def subscription_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة",       url=CHANNEL_INVITE)],
        [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")],
    ])


def voice_clone_keyboard(has_voice: bool = False):
    rows = []
    if has_voice:
        rows.append([InlineKeyboardButton("🗑️ حذف الصوت المستنسخ", callback_data="vc_delete")])
    rows.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def smart_quality_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔵 360p",  callback_data="sdq_360"),
            InlineKeyboardButton("🟢 720p",  callback_data="sdq_720"),
        ],
        [
            InlineKeyboardButton("🟡 1080p", callback_data="sdq_1080"),
            InlineKeyboardButton("⭐ أعلى جودة", callback_data="sdq_best"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


def smart_platform_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 إنستغرام", callback_data="sdp_instagram"),
            InlineKeyboardButton("🎵 تيك توك",  callback_data="sdp_tiktok"),
        ],
        [
            InlineKeyboardButton("▶️ يوتيوب",   callback_data="sdp_youtube"),
        ],
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  HELPERS  ░░
# ══════════════════════════════════════════════════════════════════════════════

async def is_subscribed(bot, user_id: int) -> bool:
    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        return True
    try:
        member = await bot.get_chat_member(chat_id=int(CHANNEL_ID), user_id=user_id)
        return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception as e:
        logger.warning(f"Subscription check failed: {e}")
        return False


async def check_subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        return True
    subscribed = await is_subscribed(context.bot, update.effective_user.id)
    if not subscribed:
        await update.message.reply_text(
            "⚠️ يجب الاشتراك في القناة أولاً.",
            reply_markup=subscription_keyboard(),
        )
    return subscribed


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  SECTION A — START & BASIC COMMANDS  ░░
# ══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome = (
        f"أهلاً {user.first_name}! 👋\n\n"
        "🎬 <b>بوت تحميل الفيديوهات</b>\n\n"
        "📌 <b>المنصات المدعومة:</b>\n"
        "• يوتيوب 🎥 • إنستغرام 📸 • تيك توك 🎵\n"
        "• تويتر/X 🐦 • فيسبوك 👍 • وأكثر من 1000 منصة!\n\n"
        "🎤 <b>ميزة جديدة:</b> استنساخ الصوت بالذكاء الاصطناعي\n\n"
        "اختر من القائمة 👇"
    )
    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        await update.message.reply_text(welcome, reply_markup=main_keyboard(), parse_mode="HTML")
        return

    subscribed = await is_subscribed(context.bot, user.id)
    if subscribed:
        await update.message.reply_text(welcome, reply_markup=main_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"أهلاً {user.first_name}! 👋\n\n"
            "⚠️ <b>للاستخدام يجب الاشتراك في قناتنا أولاً</b>\n\n"
            "1️⃣ اضغط على زر الاشتراك\n"
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


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  SECTION B — MENU CALLBACKS  ░░
# ══════════════════════════════════════════════════════════════════════════════

async def download_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mode"] = "video"
    await query.message.reply_text(
        "📎 أرسل رابط الفيديو أو الصورة وسأقوم بتحميله فوراً!\n\n"
        "مثال:\n"
        "• https://www.youtube.com/watch?v=...\n"
        "• https://www.instagram.com/p/...\n"
        "• https://www.tiktok.com/@.../video/...",
    )


async def mp3_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mode"] = "mp3"
    await query.message.reply_text(
        "🎵 أرسل رابط الفيديو وسأستخرج الصوت بصيغة MP3!\n\n"
        "• https://www.youtube.com/watch?v=...\n"
        "• https://www.tiktok.com/@.../video/...",
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
    context.user_data["mode"] = None
    await query.edit_message_text(
        "🎬 <b>القائمة الرئيسية</b>\n\nاختر من القائمة أو أرسل رابطاً مباشرة 👇",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        await query.edit_message_text(
            "✅ <b>تم! اختر من القائمة أو أرسل رابطاً.</b>",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
        return
    subscribed = await is_subscribed(context.bot, user.id)
    if subscribed:
        await query.edit_message_text(
            "✅ <b>تم التحقق من اشتراكك بنجاح!</b>\n\nاختر من القائمة 👇",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            "❌ <b>لم يتم الاشتراك بعد!</b>\n\nتأكد من الاشتراك ثم اضغط تحقق مرة أخرى.",
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  SECTION C — VIDEO & AUDIO DOWNLOADER  ░░
# ══════════════════════════════════════════════════════════════════════════════

async def _send_direct_link(update, status_msg, url: str, title: str, size_bytes: int):
    size_mb = round(size_bytes / 1024 / 1024, 1)
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            direct_url = info.get("url") or url
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ تنزيل الفيديو مباشرة", url=direct_url)],
        ])
        await status_msg.edit_text(
            f"📦 <b>{title}</b>\n\n"
            f"⚠️ الحجم ({size_mb} MB) كبير جداً للإرسال عبر تيليغرام.\n\n"
            "اضغط الزر أدناه لتنزيله مباشرة 👇",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Direct link error: {e}")
        await status_msg.edit_text(
            "⚠️ الفيديو كبير جداً. اضغط الزر للتنزيل المباشر 👇",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 فتح الرابط الأصلي", url=url)]]),
            parse_mode="HTML",
        )


async def download_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    mode = context.user_data.get("mode")

    # ── route to other handlers ──────────────────────────────────────────────
    if mode == "ig_check":
        await _check_instagram_account(update, context)
        return
    if mode == "voice_clone_waiting_text":
        await _handle_voice_text(update, context)
        return
    if mode == "smart_dl_url":
        await _handle_smart_dl_url(update, context)
        return

    # ── subscription gate ────────────────────────────────────────────────────
    if not await check_subscription_gate(update, context):
        return

    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ الرجاء إرسال رابط صحيح يبدأ بـ http:// أو https://\n\nأو اختر من القائمة:",
            reply_markup=main_keyboard(),
        )
        return

    quality = context.user_data.get("quality", "best")
    is_mp3  = mode == "mp3"

    status_msg = await update.message.reply_text("🔍 جاري فحص الفيديو...")
    info_opts  = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 30}

    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title          = info.get("title", "media")[:50]
        estimated_size = info.get("filesize") or info.get("filesize_approx") or 0

        if not is_mp3 and estimated_size > MAX_FILE_SIZE:
            await status_msg.edit_text("🔗 الفيديو أكبر من 200 MB، جاري تجهيز رابط التنزيل المباشر...")
            await _send_direct_link(update, status_msg, url, title, estimated_size)
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
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }],
                    "quiet": True, "no_warnings": True, "socket_timeout": 30,
                }
            else:
                fmt_map = {
                    "360":  "bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]",
                    "720":  "bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]",
                    "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]",
                    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                }
                ydl_opts = {
                    "outtmpl": output_path,
                    "format": fmt_map.get(quality, fmt_map["best"]),
                    "merge_output_format": "mp4",
                    "quiet": True, "no_warnings": True, "socket_timeout": 30,
                }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)

            files = list(Path(tmpdir).iterdir())
            if not files:
                raise Exception("لم يتم العثور على ملف")

            file_path = str(files[0])
            file_size = os.path.getsize(file_path)
            ext       = Path(file_path).suffix.lower()

            if not is_mp3 and file_size > MAX_FILE_SIZE:
                await status_msg.edit_text("🔗 الفيديو أكبر من 200 MB، جاري تجهيز رابط التنزيل المباشر...")
                await _send_direct_link(update, status_msg, url, title, file_size)
                return

            await status_msg.edit_text("📤 جاري الإرسال...")
            image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

            try:
                with open(file_path, "rb") as f:
                    if is_mp3 or ext == ".mp3":
                        await update.message.reply_audio(
                            audio=f, title=title,
                            caption=f"🎵 <b>{title}</b>", parse_mode="HTML",
                        )
                    elif ext in image_exts:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"📥 <b>{title}</b>", parse_mode="HTML",
                        )
                    else:
                        await update.message.reply_video(
                            video=f,
                            caption=f"📥 <b>{title}</b>",
                            parse_mode="HTML", supports_streaming=True,
                        )
                await status_msg.delete()
            except Exception as upload_err:
                logger.warning(f"Upload failed: {upload_err}")
                await status_msg.edit_text("🔗 تعذّر الإرسال، جاري تجهيز رابط مباشر...")
                await _send_direct_link(update, status_msg, url, title, file_size)

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text("❌ فشل التحميل. تأكد أن الرابط صحيح وأن المحتوى متاح للعموم.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await status_msg.edit_text("❌ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.")


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  SECTION D — INSTAGRAM ACCOUNT CHECKER  ░░
# ══════════════════════════════════════════════════════════════════════════════

def _extract_ig_username(text: str) -> str:
    text = text.strip()
    for pat in [
        r"instagram\.com/([A-Za-z0-9_.]+)/?$",
        r"instagram\.com/([A-Za-z0-9_.]+)/?\?",
        r"instagr\.am/([A-Za-z0-9_.]+)",
    ]:
        m = re.search(pat, text)
        if m:
            u = m.group(1)
            if u.lower() not in ("p", "reel", "stories", "explore", "accounts", "tv"):
                return u.lower()
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
        "✅ <code>cristiano</code>   ✅ <code>@cristiano</code>",
        parse_mode="HTML",
    )


async def _check_instagram_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = None
    username = _extract_ig_username(update.message.text or "")
    if not username:
        await update.message.reply_text(
            "❌ تعذّر استخراج اسم المستخدم.\n\n"
            "أرسل رابط مثل:\n<code>https://www.instagram.com/cristiano/</code>",
            parse_mode="HTML",
        )
        return

    status_msg = await update.message.reply_text(f"🔍 جاري فحص حساب @{username} ...")

    hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    info = {}

    def parse_num(s):
        if not s:
            return 0
        try:
            return int(re.sub(r'[^0-9]', '', s))
        except Exception:
            return 0

    try:
        async with aiohttp.ClientSession() as session:

            # ── 1. Picuki ────────────────────────────────────────────────────
            try:
                async with session.get(
                    f"https://www.picuki.com/profile/{username}",
                    headers=hdrs, timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        fm  = re.search(r'(\d[\d,\.]+)\s*[Ff]ollowers', html)
                        fom = re.search(r'(\d[\d,\.]+)\s*[Ff]ollowing', html)
                        pm  = re.search(r'(\d[\d,\.]+)\s*[Pp]osts', html)
                        nm  = re.search(r'<div class="profile-name-top"[^>]*>(.*?)</div>', html, re.S)
                        bm  = re.search(r'<div class="profile-description"[^>]*>(.*?)</div>', html, re.S)
                        if fm or pm:
                            info = {
                                "source":       "picuki",
                                "full_name":    re.sub(r'<[^>]+>', '', nm.group(1)).strip() if nm else "—",
                                "followers":    parse_num(fm.group(1) if fm else ""),
                                "following":    parse_num(fom.group(1) if fom else ""),
                                "posts":        parse_num(pm.group(1) if pm else ""),
                                "bio":          re.sub(r'<[^>]+>', '', bm.group(1)).strip() if bm else "",
                                "is_verified":  "verified" in html.lower(),
                                "is_private":   "private account" in html.lower(),
                                "is_business":  False, "profile_pic": "",
                                "external_url": "", "blocked": False, "restricted": False,
                            }
            except Exception as e:
                logger.warning(f"Picuki failed: {e}")

            # ── 2. Imginn ────────────────────────────────────────────────────
            if not info:
                try:
                    async with session.get(
                        f"https://imginn.com/{username}/",
                        headers=hdrs, timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            fm  = re.search(r'([\d,]+)\s*</span>\s*[Ff]ollowers', html)
                            fom = re.search(r'([\d,]+)\s*</span>\s*[Ff]ollowing', html)
                            pm  = re.search(r'([\d,]+)\s*</span>\s*[Pp]osts', html)
                            nm  = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
                            if fm or pm:
                                info = {
                                    "source":       "imginn",
                                    "full_name":    re.sub(r'<[^>]+>', '', nm.group(1)).strip() if nm else "—",
                                    "followers":    parse_num(fm.group(1) if fm else ""),
                                    "following":    parse_num(fom.group(1) if fom else ""),
                                    "posts":        parse_num(pm.group(1) if pm else ""),
                                    "bio":          "",
                                    "is_verified":  "verified" in html.lower(),
                                    "is_private":   False, "is_business": False,
                                    "profile_pic":  "", "external_url": "",
                                    "blocked":      False, "restricted": False,
                                }
                except Exception as e:
                    logger.warning(f"Imginn failed: {e}")

            # ── 3. Instagram HTML JSON-LD ─────────────────────────────────────
            if not info:
                try:
                    async with session.get(
                        f"https://www.instagram.com/{username}/",
                        headers=hdrs, timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp:
                        if resp.status == 404:
                            await status_msg.edit_text(
                                f"❌ <b>الحساب غير موجود أو محذوف</b>\n\n@{username}",
                                parse_mode="HTML",
                            )
                            return
                        html = await resp.text()
                        ld_m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
                        if ld_m:
                            ld = json.loads(ld_m.group(1))
                            info = {
                                "source":       "ld+json",
                                "full_name":    ld.get("name", "—"),
                                "followers":    0, "following": 0, "posts": 0,
                                "bio":          ld.get("description", ""),
                                "is_verified":  False, "is_private": False,
                                "is_business":  False, "profile_pic": "",
                                "external_url": "", "blocked": False, "restricted": False,
                            }
                except Exception as e:
                    logger.warning(f"IG HTML fallback failed: {e}")

        if not info:
            await status_msg.edit_text(
                f"⚠️ <b>تعذّر جلب بيانات @{username}</b>\n\n"
                "إنستغرام يحجب الطلبات أحياناً. حاول مرة أخرى بعد دقيقة.\n\n"
                f"🔗 <a href='https://www.instagram.com/{username}/'>افتح الحساب مباشرة</a>",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return

    except Exception as e:
        logger.error(f"Instagram check error: {e}")
        await status_msg.edit_text(f"❌ خطأ أثناء فحص الحساب: {e}")
        return

    # ── Build health report ──────────────────────────────────────────────────
    full_name   = info.get("full_name") or "—"
    followers   = info.get("followers", 0)
    following   = info.get("following", 0)
    posts       = info.get("posts", 0)
    is_private  = info.get("is_private", False)
    is_verified = info.get("is_verified", False)
    is_business = info.get("is_business", False)
    bio         = info.get("bio", "") or ""
    external_url= info.get("external_url") or ""
    profile_pic = info.get("profile_pic") or ""
    blocked     = info.get("blocked", False)
    restricted  = info.get("restricted", False)

    score = 100
    risks, goods = [], []

    if posts == 0:
        score -= 35; risks.append("🚫 لا يوجد أي منشور — خطر حظر مرتفع")
    elif posts < 5:
        score -= 15; risks.append(f"⚠️ منشورات قليلة جداً ({posts})")
    elif posts < 20:
        score -= 5;  goods.append(f"✅ {posts} منشور (معقول)")
    else:
        goods.append(f"✅ {posts} منشور (نشاط جيد)")

    if followers == 0:
        score -= 25; risks.append("🚫 صفر متابعين")
    elif followers < 10:
        score -= 15; risks.append(f"⚠️ متابعون قليلون جداً ({followers})")
    else:
        goods.append(f"✅ {followers:,} متابع")

    if following > 0:
        ratio = following / max(followers, 1)
        if ratio > 20:
            score -= 25; risks.append("🚫 نسبة متابَعين/متابعين خطرة جداً")
        elif ratio > 5:
            score -= 10; risks.append(f"⚠️ نسبة متابَعين مرتفعة")
        else:
            goods.append("✅ نسبة متابعين طبيعية")

    if not bio:
        score -= 10; risks.append("⚠️ لا توجد سيرة ذاتية (Bio)")
    elif len(bio) < 20:
        score -= 5;  risks.append("⚠️ سيرة ذاتية قصيرة جداً")
    else:
        goods.append("✅ سيرة ذاتية كاملة")

    if not profile_pic:
        score -= 10; risks.append("⚠️ لا توجد صورة ملف شخصي")
    else:
        goods.append("✅ صورة ملف شخصي موجودة")

    if is_verified:
        score = min(100, score + 15); goods.append("✅ حساب موثّق رسمياً ✔️")
    if is_business:
        goods.append("✅ حساب تجاري")
    if external_url:
        goods.append("✅ رابط خارجي موجود")
    if blocked:
        score -= 50; risks.append("🚫 الحساب محظور")
    if restricted:
        score -= 20; risks.append("⚠️ الحساب مقيّد")
    if is_private:
        score -= 5;  risks.append("🔒 الحساب خاص (يؤثر على النمو)")

    score = max(0, min(100, score))

    if score >= 80:
        icon, txt, risk = "🟢", "صحة ممتازة",  "خطر حظر منخفض جداً"
    elif score >= 60:
        icon, txt, risk = "🟡", "صحة جيدة",     "خطر حظر منخفض"
    elif score >= 40:
        icon, txt, risk = "🟠", "يحتاج تحسين",  "خطر حظر متوسط"
    else:
        icon, txt, risk = "🔴", "وضع خطر",       "خطر حظر مرتفع ⚠️"

    if score < 40:
        tip = "💡 أضف منشورات حقيقية يومياً، سيرة ذاتية وصورة ملف، وقلّل المتابعات السريعة."
    elif score < 70:
        tip = "💡 زد من تكرار النشر وأكمل بيانات ملفك الشخصي."
    else:
        tip = "💡 الحساب في وضع جيد. استمر في النشاط الطبيعي والمنتظم."

    report = (
        f"{icon} <b>تقرير فحص @{username}</b>\n"
        f"{'━'*28}\n"
        f"👤 <b>الاسم:</b> {full_name}\n"
        f"{'🔒 خاص' if is_private else '🌐 عام'}"
        f"{'  |  ✔️ موثّق' if is_verified else ''}"
        f"{'  |  🏢 تجاري' if is_business else ''}\n\n"
        f"📊 <b>الإحصائيات:</b>\n"
        f"• المنشورات:  <b>{posts:,}</b>\n"
        f"• المتابعون: <b>{followers:,}</b>\n"
        f"• المتابَعون: <b>{following:,}</b>\n\n"
        f"🏥 <b>صحة الحساب:</b> {icon} {txt}\n"
        f"🎯 <b>النقاط:</b> {score}/100\n"
        f"⚠️ <b>تقدير الحظر:</b> {risk}\n\n"
    )
    if bio:
        report += f"📝 <b>السيرة الذاتية:</b>\n{bio[:200]}\n\n"
    if goods:
        report += "✅ <b>نقاط إيجابية:</b>\n" + "\n".join(goods) + "\n\n"
    if risks:
        report += "⚠️ <b>نقاط مخاطرة:</b>\n" + "\n".join(risks) + "\n\n"
    report += f"{tip}\n\n🔗 <a href='https://www.instagram.com/{username}/'>فتح الحساب</a>"

    await status_msg.edit_text(report, parse_mode="HTML", disable_web_page_preview=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  SECTION E — VOICE CLONING (ElevenLabs)  ░░
# ══════════════════════════════════════════════════════════════════════════════

async def voice_clone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not ELEVENLABS_KEY:
        await query.message.reply_text(
            "⚙️ <b>ميزة استنساخ الصوت غير مفعّلة بعد</b>\n\n"
            "للتفعيل:\n"
            "1️⃣ سجّل حساباً مجانياً على <a href='https://elevenlabs.io'>elevenlabs.io</a>\n"
            "2️⃣ احصل على مفتاح API من الإعدادات\n"
            "3️⃣ أضفه كـ Secret باسم <code>ELEVENLABS_KEY</code>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    context.user_data["mode"] = "voice_clone_waiting_media"
    has_voice = bool(context.user_data.get("voice_clone_id"))

    text = (
        "🎤 <b>استنساخ الصوت بالذكاء الاصطناعي</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>الخطوة 1:</b> أرسل ملفاً صوتياً أو فيديو يحتوي على الصوت الذي تريد استنساخه.\n\n"
        "📌 <b>نصائح للحصول على أفضل نتيجة:</b>\n"
        "• المدة المثلى: 30 ثانية — 3 دقائق\n"
        "• صوت نظيف بدون ضوضاء خلفية\n"
        "• متحدث واحد فقط في المقطع\n\n"
        "📎 <b>الصيغ المقبولة:</b> mp3, ogg, wav, m4a, mp4, mov"
    )
    if has_voice:
        text += "\n\n♻️ لديك صوت مستنسخ بالفعل. إرسال ملف جديد سيستبدله."

    await query.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=voice_clone_keyboard(has_voice),
    )


async def handle_voice_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives audio/video file and clones the voice via ElevenLabs."""
    if not update.message:
        return
    if context.user_data.get("mode") != "voice_clone_waiting_media":
        return

    msg = update.message
    tg_file = None

    if msg.audio:
        tg_file = msg.audio
    elif msg.voice:
        tg_file = msg.voice
    elif msg.video:
        tg_file = msg.video
    elif msg.video_note:
        tg_file = msg.video_note
    elif msg.document and msg.document.mime_type and (
        msg.document.mime_type.startswith("audio/") or
        msg.document.mime_type.startswith("video/")
    ):
        tg_file = msg.document

    if not tg_file:
        await msg.reply_text(
            "❌ الرجاء إرسال ملف صوتي أو فيديو.\n\n"
            "الصيغ المقبولة: mp3, ogg, wav, m4a, mp4, mov"
        )
        return

    status_msg = await msg.reply_text("📥 جاري تحميل الملف...")

    try:
        file_obj = await context.bot.get_file(tg_file.file_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = os.path.join(tmpdir, "input_media")
            await file_obj.download_to_drive(raw_path)

            await status_msg.edit_text("🔄 جاري تحويل الصوت...")

            mp3_path = os.path.join(tmpdir, "voice_sample.mp3")
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", raw_path,
                "-ar", "44100", "-ac", "1", "-b:a", "128k",
                mp3_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
                raise Exception(f"ffmpeg failed: {stderr.decode()[:200]}")

            await status_msg.edit_text("🧠 جاري استنساخ الصوت بالذكاء الاصطناعي...")

            with open(mp3_path, "rb") as f:
                audio_bytes = f.read()

        # ── Delete previous clone if exists ──────────────────────────────────
        old_id = context.user_data.get("voice_clone_id")
        if old_id:
            try:
                async with aiohttp.ClientSession() as s:
                    await s.delete(
                        EL_DEL_URL.format(voice_id=old_id),
                        headers={"xi-api-key": ELEVENLABS_KEY},
                    )
            except Exception:
                pass

        # ── Upload to ElevenLabs ──────────────────────────────────────────────
        form = aiohttp.FormData()
        form.add_field("name", f"clone_{update.effective_user.id}")
        form.add_field("description", "Telegram bot voice clone")
        form.add_field("files", audio_bytes, filename="voice.mp3", content_type="audio/mpeg")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                EL_CLONE_URL,
                headers={"xi-api-key": ELEVENLABS_KEY},
                data=form,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    err = data.get("detail", {})
                    raise Exception(err.get("message", str(data)) if isinstance(err, dict) else str(err))
                voice_id = data.get("voice_id")

        context.user_data["voice_clone_id"] = voice_id
        context.user_data["mode"] = "voice_clone_waiting_text"

        await status_msg.edit_text(
            "✅ <b>تم استنساخ الصوت بنجاح!</b>\n\n"
            "<b>الخطوة 2:</b> الآن أرسل لي النص الذي تريده بصوت الشخص المستنسخ.\n\n"
            "💬 يمكنك الكتابة بأي لغة (عربي، إنجليزي، فرنسي...)",
            parse_mode="HTML",
            reply_markup=voice_clone_keyboard(True),
        )

    except Exception as e:
        logger.error(f"Voice clone media error: {e}")
        context.user_data["mode"] = None
        await status_msg.edit_text(
            f"❌ <b>فشل استنساخ الصوت</b>\n\n{str(e)[:300]}\n\n"
            "تأكد من جودة الملف الصوتي وحاول مرة أخرى.",
            parse_mode="HTML",
        )


async def _handle_voice_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates TTS with the cloned voice."""
    voice_id = context.user_data.get("voice_clone_id")
    if not voice_id:
        context.user_data["mode"] = None
        await update.message.reply_text(
            "❌ لم يتم استنساخ أي صوت بعد.\n\n"
            "اضغط على زر 🎤 استنساخ الصوت من القائمة.",
            reply_markup=main_keyboard(),
        )
        return

    text = update.message.text.strip()
    if len(text) > 2500:
        await update.message.reply_text("❌ النص طويل جداً! الحد الأقصى 2500 حرف.")
        return

    status_msg = await update.message.reply_text("🔊 جاري توليد الصوت...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                EL_TTS_URL.format(voice_id=voice_id),
                headers={
                    "xi-api-key": ELEVENLABS_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "style": 0.0,
                        "use_speaker_boost": True,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    raise Exception(err[:300])
                audio_bytes = await resp.read()

        await status_msg.delete()
        preview = text[:100] + ("..." if len(text) > 100 else "")
        await update.message.reply_voice(
            voice=audio_bytes,
            caption=f"🎤 <b>صوت مستنسخ</b>\n<i>{preview}</i>",
            parse_mode="HTML",
        )
        await update.message.reply_text(
            "✅ <b>تم!</b> أرسل نصاً آخر لتوليد صوت جديد بنفس الصوت المستنسخ.\n\n"
            "أو اضغط 🗑️ لحذف الصوت والبدء من جديد.",
            parse_mode="HTML",
            reply_markup=voice_clone_keyboard(True),
        )

    except Exception as e:
        logger.error(f"TTS error: {e}")
        await status_msg.edit_text(
            f"❌ <b>فشل توليد الصوت</b>\n\n{str(e)[:300]}",
            parse_mode="HTML",
        )


async def vc_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    voice_id = context.user_data.get("voice_clone_id")
    if voice_id:
        try:
            async with aiohttp.ClientSession() as s:
                await s.delete(
                    EL_DEL_URL.format(voice_id=voice_id),
                    headers={"xi-api-key": ELEVENLABS_KEY},
                )
        except Exception:
            pass
        context.user_data["voice_clone_id"] = None
    context.user_data["mode"] = None
    await query.edit_message_text(
        "🗑️ <b>تم حذف الصوت المستنسخ.</b>\n\nاختر من القائمة 👇",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  SECTION F — SMART DOWNLOAD WITH CONTENT ANALYSIS  ░░
# ══════════════════════════════════════════════════════════════════════════════

async def smart_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mode"] = "smart_dl_url"
    context.user_data.pop("smart_dl_info", None)
    await query.message.reply_text(
        "🧠 <b>تحميل فيديو مع تحليل المحتوى</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "أرسل لي رابط الفيديو الذي تريد تحميله:\n\n"
        "• https://www.youtube.com/watch?v=...\n"
        "• https://www.tiktok.com/@.../video/...\n"
        "• https://www.instagram.com/reel/...\n"
        "• أو أي رابط فيديو آخر",
        parse_mode="HTML",
    )


async def _handle_smart_dl_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: user sent URL → fetch info → show quality selection."""
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ الرجاء إرسال رابط صحيح يبدأ بـ http:// أو https://",
        )
        return

    status_msg = await update.message.reply_text("🔍 جاري فحص الفيديو...")
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 30}) as ydl:
            info = ydl.extract_info(url, download=False)

        title    = info.get("title", "فيديو")[:120]
        duration = info.get("duration", 0)
        channel  = info.get("uploader") or info.get("channel") or info.get("creator") or ""
        desc     = info.get("description", "") or ""
        tags     = info.get("tags") or []
        thumb    = info.get("thumbnail", "")
        size_b   = info.get("filesize") or info.get("filesize_approx") or 0
        size_mb  = round(size_b / 1024 / 1024, 1) if size_b else 0

        context.user_data["smart_dl_info"] = {
            "url":     url,
            "title":   title,
            "channel": channel,
            "desc":    desc[:1500],
            "tags":    tags[:30],
            "thumb":   thumb,
            "duration": duration,
        }
        context.user_data["mode"] = "smart_dl_quality"

        dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "—"
        size_str = f"{size_mb} MB" if size_mb else "غير محدد"

        await status_msg.edit_text(
            f"📹 <b>{title}</b>\n\n"
            f"📺 <b>القناة:</b> {channel or '—'}\n"
            f"⏱ <b>المدة:</b> {dur_str}\n"
            f"📦 <b>الحجم المقدّر:</b> {size_str}\n\n"
            "🎛️ <b>اختر جودة التحميل:</b>",
            reply_markup=smart_quality_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Smart DL info error: {e}")
        context.user_data["mode"] = "smart_dl_url"
        await status_msg.edit_text(
            "❌ تعذّر فحص الفيديو. تأكد من الرابط وحاول مرة أخرى.\n\n"
            f"<code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


async def smart_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: quality chosen → download → send file or link → show platform button."""
    query = update.callback_query
    await query.answer()

    info_stored = context.user_data.get("smart_dl_info")
    if not info_stored:
        await query.edit_message_text(
            "⚠️ انتهت الجلسة. ابدأ من جديد.",
            reply_markup=main_keyboard(),
        )
        return

    quality = query.data.replace("sdq_", "")   # 360 | 720 | 1080 | best
    url     = info_stored["url"]
    title   = info_stored["title"]
    context.user_data["mode"] = None

    labels = {"360": "360p 🔵", "720": "720p 🟢", "1080": "1080p 🟡", "best": "أعلى جودة ⭐"}
    await query.edit_message_text(
        f"⏳ جاري التحميل بجودة <b>{labels.get(quality, quality)}</b>...\n\n"
        f"📹 <i>{title[:60]}</i>",
        parse_mode="HTML",
    )

    fmt_map = {
        "360":  "bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]",
        "720":  "bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]",
        "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]",
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
    }

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "%(title).60s.%(ext)s")
            ydl_opts = {
                "outtmpl": output_path,
                "format": fmt_map.get(quality, fmt_map["best"]),
                "merge_output_format": "mp4",
                "quiet": True, "no_warnings": True, "socket_timeout": 60,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)

            files = list(Path(tmpdir).iterdir())
            if not files:
                raise Exception("لم يُنشأ أي ملف")

            file_path = str(files[0])
            file_size = os.path.getsize(file_path)
            size_mb   = round(file_size / 1024 / 1024, 1)

            # ── Build the result keyboard ──────────────────────────────────────
            platform_row = [InlineKeyboardButton("📣 اختيار منصة النشر", callback_data="smart_choose_platform")]

            if file_size <= TG_UPLOAD_LIMIT:
                # Upload to Telegram
                await query.message.reply_text("📤 جاري الإرسال...")
                with open(file_path, "rb") as f:
                    sent_msg = await query.message.reply_video(
                        video=f,
                        caption=f"📥 <b>{title}</b>\n\n📦 الحجم: {size_mb} MB",
                        parse_mode="HTML",
                        supports_streaming=True,
                    )
                await query.message.reply_text(
                    "✅ <b>تم التحميل!</b>\n\n"
                    "اختر منصة النشر ليعطيك البوت نصاً وهاشتاغات جاهزة 👇",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([platform_row]),
                )
            else:
                # File too big → get direct URL
                try:
                    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl2:
                        raw_info = ydl2.extract_info(url, download=False)
                        direct_url = raw_info.get("url") or url
                    dl_btn = InlineKeyboardButton(f"⬇️ تنزيل الفيديو ({size_mb} MB)", url=direct_url)
                except Exception:
                    dl_btn = InlineKeyboardButton("🔗 فتح الرابط الأصلي", url=url)

                await query.message.reply_text(
                    f"📦 <b>{title}</b>\n\n"
                    f"⚠️ الحجم ({size_mb} MB) كبير جداً للإرسال عبر تيليغرام.\n"
                    "اضغط الزر أدناه للتنزيل المباشر 👇\n\n"
                    "ثم اختر منصة النشر للحصول على النص والهاشتاغات:",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[dl_btn], platform_row]),
                )

        # Mark that we have info ready for platform step
        context.user_data["smart_dl_ready"] = True

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Smart DL download error: {e}")
        await query.message.reply_text(
            "❌ فشل التحميل. تأكد أن المحتوى متاح للعموم وحاول مرة أخرى.",
            reply_markup=main_keyboard(),
        )
    except Exception as e:
        logger.error(f"Smart DL unexpected: {e}")
        await query.message.reply_text(
            f"❌ حدث خطأ: {str(e)[:200]}",
            reply_markup=main_keyboard(),
        )


# ── Caption & Hashtag Generator ──────────────────────────────────────────────

def _template_caption(platform: str, title: str, desc: str, tags: list, channel: str) -> str:
    """Generate a platform-specific caption using video metadata."""
    # Clean & build hashtags
    raw_tags = [t for t in (tags or []) if isinstance(t, str) and len(t) > 1]
    ht = ["#" + re.sub(r'[^\w\u0600-\u06FF]', '', t.replace(' ', '_')) for t in raw_tags[:18]]
    ht = [h for h in ht if len(h) > 2]

    platform_ht = {
        "instagram": ["#instagram", "#reels", "#اكسبلور", "#trending", "#viral", "#انستقرام"],
        "tiktok":    ["#tiktok", "#fyp", "#foryoupage", "#viral", "#trending", "#تيك_توك", "#اكسبلور"],
        "youtube":   ["#youtube", "#يوتيوب", "#shorts", "#viral"],
    }
    extra = [h for h in platform_ht.get(platform, []) if h not in ht]
    all_ht = (ht + extra)[:20]
    tags_block = " ".join(all_ht)

    short_desc = ""
    if desc:
        clean = re.sub(r'\n+', ' ', desc).strip()
        short_desc = clean[:200] + ("..." if len(clean) > 200 else "")

    src_line = f"📺 المصدر: {channel}" if channel else ""

    if platform == "instagram":
        caption = (
            f"🎬 {title}\n\n"
            f"{short_desc + chr(10) + chr(10) if short_desc else ''}"
            f"{src_line + chr(10) + chr(10) if src_line else ''}"
            f"👇 شاهد الفيديو كاملاً في البروفايل\n\n"
            f"{'━' * 20}\n"
            f"{tags_block}"
        )
    elif platform == "tiktok":
        caption = (
            f"{title} ✨\n\n"
            f"{src_line + chr(10) if src_line else ''}"
            f"{tags_block}"
        )
    elif platform == "youtube":
        caption = (
            f"📹 {title}\n\n"
            f"{short_desc + chr(10) + chr(10) if short_desc else ''}"
            f"{src_line + chr(10) if src_line else ''}"
            f"\n🔖 كلمات مفتاحية:\n{tags_block}"
        )
    else:
        caption = f"{title}\n\n{tags_block}"

    return caption


async def _ai_caption(platform: str, title: str, desc: str, tags: list, channel: str) -> str:
    """Generate AI caption via Gemini API (falls back to template if no key)."""
    if not GEMINI_KEY:
        return _template_caption(platform, title, desc, tags, channel)

    platform_names = {
        "instagram": "إنستغرام (Reels / Posts)",
        "tiktok":    "تيك توك (TikTok)",
        "youtube":   "يوتيوب (YouTube Shorts / Videos)",
    }
    tags_str = ", ".join(tags[:20]) if tags else "غير متوفرة"
    prompt = (
        f"أنت خبير تسويق رقمي عربي. اكتب محتوى جاهزاً للنشر على {platform_names.get(platform, platform)} "
        f"للفيديو التالي:\n\n"
        f"العنوان: {title}\n"
        f"القناة/المصدر: {channel or 'غير محدد'}\n"
        f"الوصف: {desc[:600] if desc else 'غير متوفر'}\n"
        f"الكلمات المفتاحية: {tags_str}\n\n"
        f"اكتب:\n"
        f"1. نص منشور جذاب باللغة العربية (3-5 جمل) يشجع على المشاهدة، مع ايموجيات مناسبة\n"
        f"2. 15-20 هاشتاغ مناسب للمنصة (مزيج عربي وإنجليزي)\n\n"
        f"الرد يكون جاهزاً للنسخ والنشر مباشرةً بدون أي شرح إضافي."
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.8, "maxOutputTokens": 1200},
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.warning(f"Gemini AI failed ({e}), using template")
        return _template_caption(platform, title, desc, tags, channel)


async def smart_platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3: platform chosen → generate & send caption + hashtags."""
    query = update.callback_query
    await query.answer()

    info = context.user_data.get("smart_dl_info")
    if not info:
        await query.answer("⚠️ انتهت الجلسة، ابدأ من جديد.", show_alert=True)
        return

    platform_map = {
        "sdp_instagram": ("instagram", "📸 إنستغرام"),
        "sdp_tiktok":    ("tiktok",    "🎵 تيك توك"),
        "sdp_youtube":   ("youtube",   "▶️ يوتيوب"),
    }
    platform_key, platform_label = platform_map.get(query.data, ("instagram", "إنستغرام"))

    await query.message.reply_text(f"🧠 جاري توليد المحتوى لـ {platform_label}...")

    caption = await _ai_caption(
        platform  = platform_key,
        title     = info.get("title", ""),
        desc      = info.get("desc", ""),
        tags      = info.get("tags", []),
        channel   = info.get("channel", ""),
    )

    source_note = "✨ (مُولَّد بالذكاء الاصطناعي)" if GEMINI_KEY else "📝 (قالب جاهز)"
    header = (
        f"{platform_label} — <b>نص جاهز للنشر</b> {source_note}\n"
        f"{'━' * 30}\n\n"
    )

    # Send in a copyable code block for easy copying
    await query.message.reply_text(
        header,
        parse_mode="HTML",
    )
    await query.message.reply_text(
        caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تغيير المنصة", callback_data="smart_choose_platform")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main")],
        ]),
    )


async def smart_choose_platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show platform selection menu."""
    query = update.callback_query
    await query.answer()

    info = context.user_data.get("smart_dl_info")
    if not info:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "⚠️ انتهت الجلسة. ابدأ من جديد.",
            reply_markup=main_keyboard(),
        )
        return

    await query.message.reply_text(
        f"📣 <b>اختر المنصة التي ستنشر عليها الفيديو</b>\n\n"
        f"📹 <i>{info.get('title', '')[:80]}</i>\n\n"
        "سيُولَّد لك نص جذاب وهاشتاغات مناسبة للمنصة المختارة 👇",
        parse_mode="HTML",
        reply_markup=smart_platform_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  SECTION G — CHANNEL POST ID LOGGER  ░░
# ══════════════════════════════════════════════════════════════════════════════

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        cid   = update.channel_post.chat_id
        title = update.channel_post.chat.title
        print(f"✅ Channel ID: {cid} — {title}", flush=True)
        logger.info(f"Channel ID: {cid} — {title}")


# ══════════════════════════════════════════════════════════════════════════════
#  ░░  MAIN  ░░
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Commands ─────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("getid", getid_command))

    # ── Inline button callbacks ───────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(download_prompt_callback,    pattern="^download_prompt$"))
    app.add_handler(CallbackQueryHandler(mp3_prompt_callback,         pattern="^mp3_prompt$"))
    app.add_handler(CallbackQueryHandler(quality_menu_callback,       pattern="^quality_menu$"))
    app.add_handler(CallbackQueryHandler(quality_select_callback,     pattern="^q_(360|720|1080|best)$"))
    app.add_handler(CallbackQueryHandler(back_main_callback,          pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(ig_check_callback,           pattern="^ig_check$"))
    app.add_handler(CallbackQueryHandler(voice_clone_callback,          pattern="^voice_clone$"))
    app.add_handler(CallbackQueryHandler(vc_delete_callback,            pattern="^vc_delete$"))
    app.add_handler(CallbackQueryHandler(smart_download_callback,       pattern="^smart_download$"))
    app.add_handler(CallbackQueryHandler(smart_quality_callback,        pattern="^sdq_(360|720|1080|best)$"))
    app.add_handler(CallbackQueryHandler(smart_choose_platform_callback,pattern="^smart_choose_platform$"))
    app.add_handler(CallbackQueryHandler(smart_platform_callback,       pattern="^sdp_(instagram|tiktok|youtube)$"))

    # ── Media messages (for voice cloning) ───────────────────────────────────
    media_filter = (
        filters.AUDIO | filters.VOICE | filters.VIDEO |
        filters.VIDEO_NOTE | filters.Document.AUDIO | filters.Document.VIDEO
    )
    app.add_handler(MessageHandler(media_filter, handle_voice_media))

    # ── Text messages (download + Instagram check + voice text) ──────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_media))

    # ── Channel posts ─────────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, channel_post_handler))

    logger.info("Bot started!")
    print("🤖 البوت يعمل الآن...", flush=True)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
