import os
import sys
import time
import tempfile
import shutil
import telebot
import yt_dlp

# قراءة التوكن بأمان من متغيرات البيئة (GitHub Secrets)
TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TOKEN:
    print("❌ خطأ حرج: لم يتم العثور على متغير البيئة TELEGRAM_TOKEN!", file=sys.stderr)
    sys.exit(1)

try:
    print("⏳ جاري تهيئة البوت والاتصال بتليجرام...")
    bot = telebot.TeleBot(TOKEN)

    # =========================================================
    # دالة التحميل الموحدة للمنصات (مع استبعاد يوتيوب)
    # =========================================================
    def download_media(url, output_dir):
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            raise Exception("YouTube_Not_Supported")

        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best', 
            'outtmpl': output_template,
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True  # منع طباعة شريط التحميل المئوي في اللوج للحفاظ على نظافته
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            if "YouTube_Not_Supported" in str(e):
                raise Exception("عذراً، التحميل من يوتيوب غير مدعوم.")
            raise Exception("تعذر التحميل، تأكد أن الرابط عام وصحيح.")
        
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        
        if not files:
            raise Exception("لم يتم العثور على ملف الفيديو بعد انتهاء التحميل.")
            
        return max(files, key=os.path.getsize)

    # =========================================================
    # 1. الرد على أمر /start
    # =========================================================
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        welcome_text = (
            "مرحباً بك في بوت التحميل الشامل 📥🔥\n\n"
            "يمكنني التحميل من فيسبوك، انستقرام، تيك توك، تويتر (X)، سناب شات، وباقي المنصات (ما عدا يوتيوب).\n\n"
            "فقط أرسل الرابط العام وسأقوم بتحميله وإرساله لك فوراً."
        )
        bot.reply_to(message, welcome_text)

    # =========================================================
    # 2. أمر فحص الحالة (/ping)
    # =========================================================
    @bot.message_handler(commands=['ping'])
    def send_ping(message):
        bot.reply_to(message, "Pong! 🏓\nالبوت متصل ويعمل بكفاءة.")

    # =========================================================
    # 3. استقبال الروابط ومعالجتها
    # =========================================================
    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        if not message.text:
            return
            
        url = message.text.strip()

        if not url.startswith("http"):
            bot.reply_to(message, "❌ يرجى إرسال رابط صحيح يبدأ بـ http أو https.")
            return

        status = bot.reply_to(message, "⏳ جاري معالجة الرابط وتحميل الفيديو...\nيرجى الانتظار.")
        temp_dir = tempfile.mkdtemp(prefix="media_")

        try:
            video = download_media(url, temp_dir)
            size_mb = os.path.getsize(video) / (1024 * 1024)
            
            # فحص الحد الأقصى المسموح به لبوتات تليجرام (50 ميجابايت)
            if size_mb > 49.5:
                bot.edit_message_text(
                    f"❌ عذراً، حجم الفيديو كبير ({size_mb:.2f} MB).\nأقصى حجم مسموح به عبر تليجرام هو 50 ميجابايت.", 
                    message.chat.id, 
                    status.message_id
                )
                return

            bot.edit_message_text(
                f"📤 تم التحميل ({size_mb:.2f} MB)!\n⏳ جاري إرسال الفيديو إليك...", 
                message.chat.id, 
                status.message_id
            )

            with open(video, "rb") as file:
                bot.send_video(
                    message.chat.id, 
                    file, 
                    caption="✅ تم التحميل بنجاح", 
                    timeout=300
                )

            bot.delete_message(message.chat.id, status.message_id)

        except Exception as e:
            # إظهار رسائل عامة ونظيفة للمستخدم دون أي أكواد أو روابط خطأ
            error_msg = str(e)
            if "عذراً" in error_msg:
                user_text = f"❌ {error_msg}"
            else:
                user_text = "❌ تعذر تحميل الفيديو. تأكد أن الرابط عام وصحيح ومن منصة مدعومة."
            
            try:
                bot.edit_message_text(user_text, message.chat.id, status.message_id)
            except Exception:
                bot.reply_to(message, user_text)
        finally:
            # مسح الملفات المؤقتة فوراً لمنع أي تخزين على السيرفر
            shutil.rmtree(temp_dir, ignore_errors=True)

    # =========================================================
    # 4. حلقة التشغيل الأبدية لمنع التوقف المفاجئ
    # =========================================================
    print("🚀 البوت متصل الآن وبوضع التشغيل المستمر (Infinity Polling)...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30, logger_level=None)
        except Exception as err:
            print("⚠️ انقطاع مؤقت في الشبكة، جاري إعادة الاتصال خلال 3 ثوانٍ...", file=sys.stderr)
            time.sleep(3)

except Exception as e:
    print(f"❌ خطأ فادح أثناء التشغيل: {e}", file=sys.stderr)
