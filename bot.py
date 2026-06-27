import os
import asyncio
import tempfile
import logging
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
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
CHANNEL_INVITE = os.environ.get("CHANNEL_INVITE", "https://t.me/+i3F-wztDdSlmYWNk")

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB
TG_UPLOAD_LIMIT = 49 * 1024 * 1024  # 49 MB — حد تيليغرام للرفع


async def is_subscribed(bot, user_id: int) -> bool:
    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        logger.warning("CHANNEL_ID not configured — skipping subscription check")
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
        [InlineKeyboardButton("⬇️ تحميل فيديو", callback_data="download_prompt")],
    ])


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
        "اضغط الزر أدناه أو أرسل رابطاً مباشرة 👇"
    )

    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        await update.message.reply_text(
            welcome_text,
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
        return

    subscribed = await is_subscribed(context.bot, user.id)

    if subscribed:
        await update.message.reply_text(
            welcome_text,
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )
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


async def download_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📎 أرسل لي رابط الفيديو أو الصورة وسأقوم بتحميله فوراً!\n\n"
        "مثال:\n"
        "• https://www.youtube.com/watch?v=...\n"
        "• https://www.instagram.com/p/...\n"
        "• https://www.tiktok.com/@.../video/...",
        parse_mode="HTML",
    )


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    if not CHANNEL_ID or CHANNEL_ID == "-1002000000000":
        await query.edit_message_text(
            "✅ <b>تم التحقق! أرسل لي رابط الفيديو أو الصورة.</b>",
            parse_mode="HTML",
        )
        return

    subscribed = await is_subscribed(context.bot, user.id)

    if subscribed:
        await query.edit_message_text(
            "✅ <b>تم التحقق من اشتراكك بنجاح!</b>\n\n"
            "أرسل لي رابط أي فيديو أو صورة وسأقوم بتحميلها لك بأعلى جودة ممكنة 🚀\n\n"
            "📌 يوتيوب، إنستغرام، تيك توك، تويتر/X، فيسبوك، وأكثر من 1000 منصة!",
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            "❌ <b>لم يتم الاشتراك بعد!</b>\n\n"
            "تأكد من الاشتراك في القناة ثم اضغط تحقق مرة أخرى.",
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )


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
            f"⚠️ حجم الفيديو كبير جداً ({size_mb} MB) لإرساله عبر تيليغرام.\n\n"
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
            f"⚠️ الفيديو كبير جداً للإرسال عبر تيليغرام.\n\n"
            "اضغط الزر أدناه لفتح الرابط وتنزيله مباشرة 👇",
            reply_markup=keyboard,
            parse_mode="HTML",
        )


async def download_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if CHANNEL_ID and CHANNEL_ID != "-1002000000000":
        subscribed = await is_subscribed(context.bot, user.id)
        if not subscribed:
            await update.message.reply_text(
                "⚠️ يجب الاشتراك في القناة أولاً للاستخدام البوت.",
                reply_markup=subscription_keyboard(),
            )
            return

    url = update.message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ الرجاء إرسال رابط صحيح يبدأ بـ http:// أو https://"
        )
        return

    status_msg = await update.message.reply_text("🔍 جاري فحص الفيديو...")

    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 30,
    }

    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "media")[:50]

        # تقدير الحجم قبل التنزيل
        estimated_size = info.get("filesize") or info.get("filesize_approx") or 0

        if estimated_size > MAX_FILE_SIZE:
            await status_msg.edit_text("🔗 الفيديو أكبر من 200 MB، جاري تجهيز رابط التنزيل المباشر...")
            await send_direct_link(update, status_msg, url, title, estimated_size)
            return

        await status_msg.edit_text("⏳ جاري التحميل، الرجاء الانتظار...")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "%(title).50s.%(ext)s")

            ydl_opts = {
                "outtmpl": output_path,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)

            downloaded_files = list(Path(tmpdir).iterdir())
            if not downloaded_files:
                raise Exception("لم يتم العثور على ملف بعد التحميل")

            file_path = str(downloaded_files[0])
            file_size = os.path.getsize(file_path)
            ext = Path(file_path).suffix.lower()

            # إذا تجاوز 200 MB بعد التنزيل الفعلي
            if file_size > MAX_FILE_SIZE:
                await status_msg.edit_text("🔗 الفيديو أكبر من 200 MB، جاري تجهيز رابط التنزيل المباشر...")
                await send_direct_link(update, status_msg, url, title, file_size)
                return

            await status_msg.edit_text("📤 جاري الإرسال...")

            image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

            try:
                with open(file_path, "rb") as media_file:
                    if ext in image_exts:
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
                # فشل الرفع لتيليغرام (عادةً >50MB) → أرسل رابط مباشر
                logger.warning(f"Telegram upload failed: {upload_err}")
                await status_msg.edit_text("🔗 تعذّر إرسال الملف عبر تيليغرام، جاري تجهيز رابط مباشر...")
                await send_direct_link(update, status_msg, url, title, file_size)

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(
            "❌ فشل التحميل. تأكد أن الرابط صحيح وأن المحتوى متاح للعموم."
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await status_msg.edit_text(
            "❌ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى."
        )


async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        chat_id = update.channel_post.chat_id
        chat_title = update.channel_post.chat.title
        print(f"✅ Channel ID detected: {chat_id} — {chat_title}", flush=True)
        logger.info(f"Channel ID: {chat_id} — {chat_title}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getid", getid_command))
    app.add_handler(CallbackQueryHandler(download_prompt_callback, pattern="^download_prompt$"))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_media))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, channel_post_handler))

    logger.info("Bot started!")
    print("🤖 البوت يعمل الآن...", flush=True)
    print(f"📢 CHANNEL_ID الحالي: {CHANNEL_ID or 'غير مضبوط'}", flush=True)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
