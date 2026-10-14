"""
Telegram Bot to convert Video URLs (Instagram, Twitter, etc.) to Animated Stickers.

Prerequisites for running locally:
1. pip install pyTelegramBotAPI yt-dlp
2. Install FFmpeg on your system (must be in PATH)
3. Set your TELEGRAM_BOT_TOKEN environment variable.
"""

import os
import tempfile
import glob
import subprocess
import telebot
import yt_dlp
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Fetch the token from environment variables (Best practice for hosting on Render)
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not BOT_TOKEN:
    # Fallback for local testing if you don't want to set env variables
    # Replace 'YOUR_TOKEN_HERE' with your actual bot token from BotFather, 
    # but never commit your actual token to a public GitHub repo!
    BOT_TOKEN = 'YOUR_TOKEN_HERE' 

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 Welcome to the Sticker Maker Bot!\n\n"
        "Send me a link to an Instagram Reel, Twitter/X video, or TikTok.\n"
        "I will download it, format it, and send it back to you as an animated sticker "
        "that you can save and forward to WhatsApp!"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    # Basic check to see if the message contains a link
    if "http://" not in url and "https://" not in url:
        bot.reply_to(message, "Please send a valid URL (link).")
        return

    status_msg = bot.reply_to(message, "⏳ Downloading video... (This might take a moment)")

    # Run the processing logic
    try:
        process_video_and_send_sticker(message.chat.id, url, status_msg)
    except Exception as e:
        bot.edit_message_text(f"❌ An error occurred: {str(e)}", chat_id=message.chat.id, message_id=status_msg.message_id)

def process_video_and_send_sticker(chat_id, url, status_msg):
    # Create a temporary directory that automatically cleans up after itself
    with tempfile.TemporaryDirectory() as temp_dir:
        
        # 1. DOWNLOAD THE VIDEO
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, 'video.%(ext)s'),
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            bot.edit_message_text(f"❌ Failed to download video. Ensure the post is public.\nError: {str(e)}", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return

        # Locate the downloaded file
        files = glob.glob(os.path.join(temp_dir, 'video.*'))
        if not files:
            bot.edit_message_text("❌ Could not locate the downloaded video.", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return
            
        input_file = files[0]
        sticker_path = os.path.join(temp_dir, 'sticker.webp')

        bot.edit_message_text("⚙️ Converting to animated sticker format...", 
                              chat_id=chat_id, message_id=status_msg.message_id)

        # 2. CONVERT TO WEBP VIA FFMPEG
        # Extract the first 3 seconds (to keep size under 500kb limit)
        # Scale/Pad to exactly 512x512 with transparent background at 15fps
        duration = "3" 
        
        ffmpeg_cmd = [
            'ffmpeg',
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
            error_details = e.stderr.decode('utf-8', errors='ignore')
            bot.edit_message_text(f"❌ FFmpeg conversion failed.\nError: {error_details[:500]}", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return

        # 3. SEND THE STICKER TO THE USER
        bot.edit_message_text("✅ Done! Sending your sticker...", 
                              chat_id=chat_id, message_id=status_msg.message_id)
        
        with open(sticker_path, 'rb') as sticker_file:
            bot.send_sticker(chat_id, sticker_file)
            
        # Optional: delete the status message entirely once done
        # bot.delete_message(chat_id, status_msg.message_id)

if __name__ == "__main__":
    # --- RENDER FREE TIER DUMMY SERVER ---
    # Render requires free services to act like a website and bind to a port.
    # This tiny server runs in the background just to keep Render happy.
    class DummyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is alive and listening on Telegram!")

    def keep_alive():
        port = int(os.getenv('PORT', 8080))
        server = HTTPServer(('0.0.0.0', port), DummyHandler)
        server.serve_forever()

    # Start the dummy web server in a separate thread
    threading.Thread(target=keep_alive, daemon=True).start()
    # -------------------------------------

    print("Bot is starting...")
    # infinity_polling keeps the bot running even if it encounters temporary network errors
    bot.infinity_polling()