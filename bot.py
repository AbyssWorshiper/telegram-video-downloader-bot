import os
import subprocess
import logging
from uuid import uuid4
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG = {
    "token": "YOUR TOKEN",
    "local_api_url": "http://localhost:8081",
    "cookies_file": "cookies.txt",
    "resolution": "1920x1080",
    "format": "mp4",
    "temp_dir": "downloads",
    "start_message": "ping"
}

os.makedirs(CONFIG["temp_dir"], exist_ok=True)

def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(CONFIG["start_message"])
    try:
        await context.bot.pin_chat_message(update.effective_chat.id, msg.message_id, disable_notification=True)
    except Exception:
        pass

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    file_id = str(uuid4())
    original_template = os.path.join(CONFIG["temp_dir"], f"{file_id}_original.%(ext)s")
    final_path = os.path.join(CONFIG["temp_dir"], f"{file_id}.{CONFIG['format']}")

    height = CONFIG["resolution"].split("x")[1]

    dl_cmd = [
        "yt-dlp",
        "--cookies", CONFIG["cookies_file"],
        "-f", f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}]/b",
        "-o", original_template,
        "--no-playlist",
        "--extractor-args", "youtube:player_client=default",
        "--user-agent", "Mozilla/5.0",
        "--remote-components", "ejs:npm",
        "--js-runtimes", "deno",
        url
    ]
    ok, out = run_command(dl_cmd)

    if not ok:
        dl_cmd = [
            "yt-dlp",
            "--cookies", CONFIG["cookies_file"],
            "-f", "b",
            "-o", original_template,
            "--no-playlist",
            "--extractor-args", "youtube:player_client=default",
            "--user-agent", "Mozilla/5.0",
            "--remote-components", "ejs:npm",
            "--js-runtimes", "deno",
            url
        ]
        ok, out = run_command(dl_cmd)

    if not ok:
        await update.message.reply_text(f"Download failed: {out[:500]}")
        return

    original_file = None
    for ext in ['mp4', 'webm', 'mkv', 'avi', 'mov', 'flv', '3gp', 'm4a']:
        test_path = os.path.join(CONFIG["temp_dir"], f"{file_id}_original.{ext}")
        if os.path.exists(test_path):
            original_file = test_path
            break

    if not original_file:
        for f in os.listdir(CONFIG["temp_dir"]):
            if f.startswith(file_id):
                original_file = os.path.join(CONFIG["temp_dir"], f)
                break

    if not original_file:
        await update.message.reply_text("File not found")
        return

    file_ext = os.path.splitext(original_file)[1].lower()

    if file_ext == f".{CONFIG['format']}":
        os.rename(original_file, final_path)
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", original_file,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-vf", f"scale='min(1920,iw)':'min({height},ih)':force_original_aspect_ratio=decrease",
            "-movflags", "+faststart",
            "-preset", "fast",
            "-crf", "23",
            final_path
        ]
        ok, out = run_command(ffmpeg_cmd)
        os.remove(original_file)

        if not ok:
            await update.message.reply_text(f"Convert failed: {out[:500]}")
            return

    if not os.path.exists(final_path):
        await update.message.reply_text("File not created")
        return

    curl_cmd = [
        "curl", "-4", "-s",
        "--connect-timeout", "10",
        "--max-time", "300",
        "-F", f"video=@{final_path}",
        "-F", f"chat_id={update.effective_chat.id}",
        "-F", "supports_streaming=true",
        f"https://api.telegram.org/bot{CONFIG['token']}/sendVideo"
    ]
    ok, out = run_command(curl_cmd)
    if not ok:
        await update.message.reply_text(f"Upload failed: {out[:500]}")
    else:
        await update.message.reply_text("Video sent successfully!")

    os.remove(final_path)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(str(context.error)[:500])

def main():
    app = Application.builder().token(CONFIG["token"]).connect_timeout(30).read_timeout(30).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
