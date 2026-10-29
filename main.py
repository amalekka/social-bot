import os
import sys
import tempfile
import shutil
import telebot
import yt_dlp

# قراءة التوكن من متغيرات البيئة للأمان التام
TOKEN = os.environ.get("TELEGRAM_TOKEN", "9106700553:AAEvVYD7Mt8XRvDguyPmfyah8RUDY7cI0Xw")

try:
    print("⏳ جاري تهيئة البوت والاتصال بتليجرام...")
    bot = telebot.TeleBot(TOKEN)

    def download_facebook(url, output_dir):
        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_template,
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            raise Exception(f"خطأ من مكتبة التحميل:\n{str(e)}")
        
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        
        if not files:
            raise Exception("لم يتم العثور على ملف الفيديو بعد انتهاء التحميل.")
            
        return max(files, key=os.path.getsize)

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        welcome_text = (
            "مرحباً! 👋\n"
            "البوت يعمل بنجاح وبسرعة فائقة 📱✅\n\n"
            "📥 أرسل رابط فيديو عام من Facebook وسأقوم بتحميله وإرساله لك."
        )
        bot.reply_to(message, welcome_text)

    @bot.message_handler(commands=['ping'])
    def send_ping(message):
        bot.reply_to(message, "Pong! 🏓\nالاتصال مستقر ويعمل بكفاءة.")

    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        url = message.text.strip()

        if not ("facebook.com" in url.lower() or "fb.watch" in url.lower()):
            bot.reply_to(message, "❌ أرسل رابط فيديو من Facebook فقط.")
            return

        status = bot.reply_to(message, "⏳ جاري تحميل الفيديو...\nيرجى الانتظار.")
        temp_dir = tempfile.mkdtemp(prefix="fb_download_")

        try:
            video = download_facebook(url, temp_dir)
            size_mb = os.path.getsize(video) / (1024 * 1024)

            bot.edit_message_text(
                f"📤 تم التحميل بنجاح ({size_mb:.2f} MB)!\n⏳ جاري رفع الفيديو للتليجرام...",
                message.chat.id, status.message_id
            )

            with open(video, "rb") as file:
                bot.send_video(
                    message.chat.id, 
                    file, 
                    caption="✅ تم تحميل الفيديو بنجاح",
                    timeout=300 
                )

            bot.delete_message(message.chat.id, status.message_id)

        except Exception as e:
            try:
                bot.edit_message_text(f"❌ فشل التحميل أو الرفع:\n\n{e}", message.chat.id, status.message_id)
            except Exception:
                bot.reply_to(message, f"❌ فشل التحميل أو الرفع:\n{e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    print("🚀 البوت يعمل الآن وينتظر الرسائل (Polling)...")
    bot.polling(none_stop=True, timeout=60)

except Exception as e:
    print(f"❌ حدث خطأ فادح: {e}", file=sys.stderr)
