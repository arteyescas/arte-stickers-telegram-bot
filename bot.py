"""
Telegram Bot to convert Video URLs (Instagram, Twitter, etc.) to Animated Stickers.
"""

import os
import tempfile
import glob
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
import yt_dlp
import imageio_ffmpeg # The portable FFmpeg library

# Fetch the token from environment variables
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

bot = telebot.TeleBot(BOT_TOKEN)

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
        process_video_and_send_sticker(message.chat.id, url, status_msg)
    except Exception as e:
        bot.edit_message_text(f"❌ An error occurred: {str(e)}", chat_id=message.chat.id, message_id=status_msg.message_id)

def process_video_and_send_sticker(chat_id, url, status_msg):
    # Clean the URL to prevent downloading comments/threads
    if "?" in url:
        url = url.split("?")[0]
    url = url.replace("https://x.com/", "https://twitter.com/")

    with tempfile.TemporaryDirectory() as temp_dir:
        
        # 1. DOWNLOAD THE VIDEO
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
            bot.edit_message_text(f"❌ Failed to download video. Ensure the post is public.\nError: {str(e)}", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return

        files = glob.glob(os.path.join(temp_dir, 'video.*'))
        if not files:
            bot.edit_message_text("❌ Could not locate the downloaded video.", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return
            
        input_file = files[0]
        sticker_path = os.path.join(temp_dir, 'sticker.webp')

        bot.edit_message_text("⚙️ Converting to animated sticker format...", 
                              chat_id=chat_id, message_id=status_msg.message_id)

        # 2. CONVERT TO WEBP VIA PORTABLE FFMPEG
        duration = "3" 
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe() # Get the path to the portable FFmpeg
        
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
            error_details = e.stderr.decode('utf-8', errors='ignore')
            bot.edit_message_text(f"❌ FFmpeg conversion failed.\nError: {error_details[:500]}", 
                                  chat_id=chat_id, message_id=status_msg.message_id)
            return

        # 3. SEND THE STICKER AS A DOCUMENT
        bot.edit_message_text("✅ Done! Sending your animated file...", 
                              chat_id=chat_id, message_id=status_msg.message_id)
        
        with open(sticker_path, 'rb') as sticker_file:
            # Send as document so Telegram doesn't freeze the animation!
            bot.send_document(
                chat_id, 
                sticker_file,
                caption="Here is your animated file! 👆\n\nSave this file to your computer and upload it using the '+' -> 'New Sticker' button on WhatsApp Web."
            )

# --- DUMMY WEB SERVER ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive and listening on Telegram!")
    
    def log_message(self, format, *args):
        pass

def keep_alive():
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    print(f"Fake web server listening on port {port}...")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    print("Bot is starting...")
    bot.infinity_polling()
