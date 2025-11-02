import logging
import asyncio
import yt_dlp
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8568636450:AAFUC3sc_tbQJc5DwZO5Rxs6Ypo9qmGpThg"

# ---------- ЛОГИ ----------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

SUPPORTED_DOMAINS = [
    "tiktok.com",
    "instagram.com",
    "youtube.com/shorts",
    "youtu.be/shorts",
    "youtube.com/watch",
]
MAX_DURATION = 20 * 60  # 20 минут

# ---------- Команда /start ----------
@dp.message(Command("start"))
async def start_command(message: Message):
    user = f"{message.from_user.full_name} (@{message.from_user.username})"
    logging.info(f"{user} запустил бота.")
    await message.answer(
        "👋 Отправь ссылку на TikTok, Instagram Reels или YouTube Shorts — я пришлю видео прямо сюда 🎬"
    )

# ---------- Основная обработка ----------
@dp.message()
async def handle_link(message: Message):
    user = f"{message.from_user.full_name} (@{message.from_user.username})"
    url = message.text.strip()
    logging.info(f"Получена ссылка от {user}: {url}")

    if not any(domain in url for domain in SUPPORTED_DOMAINS):
        await message.answer("⚠️ Поддерживаются только TikTok, Instagram Reels и YouTube 🎥")
        return

    await message.answer("📥 Обрабатываю ссылку...")

    try:
        # -------- Проверка длительности --------
        check_opts = {"quiet": True, "skip_download": True}
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", 0)
            title = info.get("title", "Видео")

        if duration and duration > MAX_DURATION:
            await message.answer(
                f"⏱ Видео слишком длинное ({duration // 60} мин). Максимум — 20 мин ⛔"
            )
            logging.warning(f"{user} отправил слишком длинное видео: {url}")
            return

        # -------- YouTube: выбор разрешения --------
        if "youtube" in url:
            formats = []
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                for f in info.get("formats", []):
                    if (
                        f.get("ext") == "mp4"
                        and f.get("height")
                        and 144 <= f["height"] <= 720
                        and f.get("filesize")
                    ):
                        formats.append(
                            (
                                f["height"],
                                f"{round(f['filesize'] / 1024 / 1024, 1)} МБ",
                                f["format_id"],
                            )
                        )

            if not formats:
                await message.answer("⚠️ Не удалось получить варианты качества. Попробуй другую ссылку.")
                return

            formats.sort(key=lambda x: x[0], reverse=True)
            buttons = [
                [InlineKeyboardButton(text=f"{h}p ({s})", callback_data=f"res|{url}|{fid}")]
                for h, s, fid in formats
            ]
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer("📹 Выбери качество видео:", reply_markup=kb)
            return

        # -------- TikTok / Instagram --------
        await download_and_send(message, url, user)

    except Exception as e:
        await message.answer("⚠️ Попробуй другую ссылку, ваше видео невозможно скачать 😔")
        _log_error(user, url, e)

# ---------- Коллбэк выбора качества ----------
@dp.callback_query(lambda c: c.data.startswith("res|"))
async def choose_resolution(callback: types.CallbackQuery):
    _, url, format_id = callback.data.split("|", 2)
    user = f"{callback.from_user.full_name} (@{callback.from_user.username})"
    await callback.message.answer("⬇️ Скачиваю выбранное качество, подожди немного...")

    try:
        ydl_opts = {
            "outtmpl": "video.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "format": format_id,
            "merge_output_format": "mp4",
            "socket_timeout": 300,  # 5 мин
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            title = info.get("title", "Видео")

        if not os.path.exists(filename):
            await callback.message.answer("⚠️ Видео не удалось сохранить. Попробуй другую ссылку 📎")
            logging.error(f"Файл не найден: {filename}")
            return

        video_file = FSInputFile(filename)
        await callback.message.answer_video(
            video_file,
            caption=f"✅ Готово! {title}",
            supports_streaming=True,
        )
        os.remove(filename)
        logging.info(f"Видео {title} отправлено пользователю {user}.")

    except Exception as e:
        await callback.message.answer(
            "⚠️ Попробуй другую ссылку, ваше видео невозможно скачать 😔"
        )
        _log_error(user, url, e)

# ---------- Универсальная функция скачивания ----------
async def download_and_send(message: Message, url: str, user: str):
    try:
        ydl_opts = {
            "outtmpl": "video.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "format": "best[ext=mp4][vcodec*=avc1][acodec*=mp4a]/best[ext=mp4]",
            "socket_timeout": 300,  # 5 мин
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            title = info.get("title", "Видео")

        if not os.path.exists(filename):
            await message.answer("⚠️ Видео не удалось сохранить. Попробуй другую ссылку 📎")
            return

        video_file = FSInputFile(filename)
        await message.answer_video(video_file, caption=f"✅ Готово! {title}", supports_streaming=True)
        os.remove(filename)
        logging.info(f"Видео успешно отправлено пользователю {user}: {title}")

    except Exception as e:
        await message.answer("⚠️ Попробуй другую ссылку, ваше видео невозможно скачать 😔")
        _log_error(user, url, e)

# ---------- Запись ошибок ----------
def _log_error(user: str, url: str, e: Exception):
    error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{error_time}] Ошибка у {user} ({url}) — {str(e)}\n"
    with open("logs/errors.log", "a", encoding="utf-8") as f:
        f.write(msg)
    logging.exception(msg)

# ---------- Запуск ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
