import os
import sys
import tempfile
import shutil
import telebot
import yt_dlp

TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TOKEN:
    print("❌ خطأ حرج: لم يتم العثور على متغير البيئة TELEGRAM_TOKEN!", file=sys.stderr)
    sys.exit(1)

try:
    print("⏳ جاري تهيئة البوت والاتصال بتليجرام...")
    bot = telebot.TeleBot(TOKEN)

    def download_media(url, output_dir):
        # التحقق ومنع روابط يوتيوب نهائياً
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            raise Exception("YouTube_Not_Supported")

        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best', 
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
            if "YouTube_Not_Supported" in str(e):
                raise Exception("عذراً، خدمة التحميل من يوتيوب غير مدعومة حالياً.")
            raise Exception("تعذر التحميل، تأكد أن الرابط عام وصحيح.")
        
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        
        if not files:
            raise Exception("لم يتم العثور على ملف الفيديو بعد انتهاء التحميل.")
            
        return max(files, key=os.path.getsize)

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        welcome_text = (
            "مرحباً بك في بوت التحميل 📥🔥\n\n"
            "يمكنني التحميل لك من فيسبوك، انستقرام، تيك توك، تويتر، وباقي المنصات (ما عدا يوتيوب).\n"
            "فقط أرسل الرابط وسأقوم باللازم فوراً."
        )
        bot.reply_to(message, welcome_text)

    @bot.message_handler(commands=['ping'])
    def send_ping(message):
        bot.reply_to(message, "Pong! 🏓\nالبوت يعمل بكفاءة.")

    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        url = message.text.strip()

        if not url.startswith("http"):
            bot.reply_to(message, "❌ يرجى إرسال رابط صحيح يبدأ بـ http أو https.")
            return

        status = bot.reply_to(message, "⏳ جاري معالجة الطلب...\nيرجى الانتظار.")
        temp_dir = tempfile.mkdtemp(prefix="media_")

        try:
            video = download_media(url, temp_dir)
            size_mb = os.path.getsize(video) / (1024 * 1024)
            
            if size_mb > 49.5:
                bot.edit_message_text(f"❌ عذراً، حجم الملف كبير جداً ({size_mb:.2f} MB). أقصى حجم 50 ميجابايت.", message.chat.id, status.message_id)
                return

            bot.edit_message_text(f"📤 تم التحميل ({size_mb:.2f} MB)!\n⏳ جاري الإرسال...", message.chat.id, status.message_id)

            with open(video, "rb") as file:
                bot.send_video(message.chat.id, file, caption="✅ تم التحميل بنجاح", timeout=300)

            bot.delete_message(message.chat.id, status.message_id)

        except Exception as e:
            # رسالة خطأ عامة ونظيفة للمستخدم بدون روابط فنية معقدة
            error_msg = str(e)
            if "عذراً" in error_msg:
                user_text = f"❌ {error_msg}"
            else:
                user_text = "❌ فشل التحميل، تأكد أن الرابط عام ومن منصة مدعومة."
            
            try:
                bot.edit_message_text(user_text, message.chat.id, status.message_id)
            except:
                bot.reply_to(message, user_text)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    print("🚀 البوت متصل الآن وينتظر الروابط...")
    bot.polling(none_stop=True, timeout=60)

except Exception as e:
    print(f"❌ خطأ فادح: {e}", file=sys.stderr)
