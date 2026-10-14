import os
import tempfile
import glob
import subprocess
import threading
import sys
import telebot
import yt_dlp
import imageio_ffmpeg
from flask import Flask

# 1. Force logs to print instantly
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# 2. Safely grab the Bot Token
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    print("🚨 WARNING: TELEGRAM_BOT_TOKEN is missing!")
    BOT_TOKEN = "123456789:DUMMY_TOKEN_TO_PREVENT_FATAL_CRASH"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# 3. Dummy Web Routes to pass Render's Health Check
@app.route('/')
def home():
    return "Bot is alive and running!", 200

@app.route('/health')
def health():
    return "OK", 200

# 4. Telegram Bot Logic
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 Welcome to the Sticker Maker Bot!\n\n"
        "Send me a link to an Instagram Reel, Twitter/X video, or TikTok.\n"
        "I will download it, format it, and send it back to you as an animated file "
        "that you can save and forward to WhatsApp!"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if "http://" not in url and "https://" not in url:
        bot.reply_to(message, "Please send a valid URL (link).")
        return

    status_msg = bot.reply_to(message, "⏳ Downloading video... (This might take a moment)")

    try:
        process_video(message.chat.id, url, status_msg)
    except Exception as e:
        bot.edit_message_text(f"❌ An error occurred: {str(e)}", chat_id=message.chat.id, message_id=status_msg.message_id)

def process_video(chat_id, url, status_msg):
    # Clean the URL
    if "?" in url:
        url = url.split("?")[0]
    url = url.replace("https://x.com/", "https://twitter.com/")

    with tempfile.TemporaryDirectory() as temp_dir:
        
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, 'video.%(ext)s'),
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'noplaylist': True,
            'playlist_items': '1',  # Force yt-dlp to ONLY grab the first video
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            bot.edit_message_text(f"❌ Failed to download video.\nError: {str(e)}", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return

        files = glob.glob(os.path.join(temp_dir, 'video.*'))
        if not files:
            bot.edit_message_text("❌ Could not locate the downloaded video.", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return
            
        input_file = files[0]
        sticker_path = os.path.join(temp_dir, 'sticker.webp')

        bot.edit_message_text("⚙️ Converting to animated WebP format...", 
                              chat_id=chat_id, message_id=status_msg.message_id)

        duration = "3" 
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe() 
        
        ffmpeg_cmd = [
            ffmpeg_exe,
            '-y', 
            '-t', duration,
            '-i', input_file,
            '-vf', 'format=rgba,scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=black@0.0,fps=15',
            '-c:v', 'libwebp',
            '-lossless', '0',
            '-compression_level', '4',
            '-q:v', '30',
            '-loop', '0',
            '-an',
            sticker_path
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            bot.edit_message_text("❌ FFmpeg conversion failed.", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return

        bot.edit_message_text("✅ Done! Sending your animated file...", 
                              chat_id=chat_id, message_id=status_msg.message_id)
        
        # Send as a DOCUMENT to prevent Telegram from freezing the animation
        with open(sticker_path, 'rb') as sticker_file:
            bot.send_document(
                chat_id, 
                sticker_file,
                caption="Here is your animated file! 👆\n\nSave this file to your computer and upload it using the '+' -> 'New Sticker' button on WhatsApp Web."
            )

def start_bot():
    print("🤖 Attempting to connect to Telegram...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"🚨 Bot polling crashed: {e}")

if __name__ == "__main__":
    print("🚀 Starting application...")
    
    # Start the bot in the background
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Start the web server in the foreground to satisfy Render
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Binding Flask web server to 0.0.0.0 on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
