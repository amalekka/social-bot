import os
import sys
import tempfile
import shutil
import telebot
import yt_dlp

# قراءة التوكن بأمان من متغيرات البيئة (لتجنب كشفه داخل الكود)
TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TOKEN:
    print("❌ خطأ حرج: لم يتم العثور على متغير البيئة TELEGRAM_TOKEN!", file=sys.stderr)
    sys.exit(1)

try:
    print("⏳ جاري تهيئة البوت الشامل والاتصال بتليجرام...")
    bot = telebot.TeleBot(TOKEN)

    # =========================================================
    # دالة التحميل الموحدة والذكية لجميع منصات السوشيال ميديا
    # =========================================================
    def download_media(url, output_dir):
        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best', 
            'outtmpl': output_template,
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            # التعديل السحري لتخطي حظر المنصات الكبرى مثل يوتيوب
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            raise Exception(f"تعذر التحميل، تأكد أن الرابط عام وصحيح ولا يوجد حظر:\n{str(e)}")
        
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        
        if not files:
            raise Exception("لم يتم العثور على ملف الفيديو بعد انتهاء التحميل.")
            
        return max(files, key=os.path.getsize)

    # =========================================================
    # 1. الترحيب بالمستخدم (أمر /start)
    # =========================================================
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        welcome_text = (
            "مرحباً بك في البوت الشامل للتحميل 📥🔥\n\n"
            "يمكنني التحميل لك من جميع منصات السوشيال ميديا باحترافية:\n"
            "📺 YouTube (فيديوهات وصور مصغرة وشورتس)\n"
            "📘 Facebook\n"
            "📸 Instagram\n"
            "🐦 Twitter / X\n"
            "👻 Snapchat\n"
            "🎵 TikTok\n"
            "وغيرها الكثير من المنصات الداعمة!\n\n"
            "فقط أرسل الرابط وسأقوم بالازم فوراً."
        )
        bot.reply_to(message, welcome_text)
        print(f"✅ تم استقبال /start من المستخدم: {message.chat.first_name}")

    # =========================================================
    # 2. أمر فحص الحالة والسرعة (/ping)
    # =========================================================
    @bot.message_handler(commands=['ping'])
    def send_ping(message):
        bot.reply_to(message, "Pong! 🏓\nالنظام الشامل يعمل بكفاءة وأمان تام.")
        print(f"⚡ تم تنفيذ أمر /ping بنجاح")

    # =========================================================
    # 3. معالجة الروابط لجميع المنصات وتحميلها وإرسالها
    # =========================================================
    @bot.message_handler(func=lambda message: True)
    def handle_message(message):
        url = message.text.strip()

        # التحقق الأولي من صحة الرابط
        if not url.startswith("http"):
            bot.reply_to(message, "❌ عذراً، يرجى إرسال رابط صحيح يبدأ بـ http أو https.")
            return

        status = bot.reply_to(message, "⏳ جاري التحقق وجلب الميديا من المنصة المستهدفة...\nيرجى الانتظار.")
        temp_dir = tempfile.mkdtemp(prefix="social_download_")

        try:
            print(f"📥 طلب تحميل جديد من {message.from_user.first_name}: {url}")
            
            # تنفيذ عملية التحميل
            video = download_media(url, temp_dir)
            size_mb = os.path.getsize(video) / (1024 * 1024)
            
            # فحص حجم الملف لكي لا يتجاوز حد تليجرام للبوتات (50 ميجابايت)
            if size_mb > 49.5:
                bot.edit_message_text(
                    f"❌ عذراً، حجم الملف كبير جداً ({size_mb:.2f} MB).\nأقصى حجم مسموح به لرفع الملفات عبر البوت هو 50 ميجابايت.", 
                    message.chat.id, 
                    status.message_id
                )
                return

            print(f"✅ تم التحميل بنجاح: {os.path.basename(video)} ({size_mb:.2f} MB)")
            bot.edit_message_text(
                f"📤 تم التحميل بنجاح ({size_mb:.2f} MB)!\n⏳ جاري رفع وإرسال الفيديو إليك...", 
                message.chat.id, 
                status.message_id
            )

            # رفع الفيديو إلى تليجرام مع مهلة انتظار 5 دقائق لضمان عدم حدوث انقطاع
            with open(video, "rb") as file:
                bot.send_video(
                    message.chat.id, 
                    file, 
                    caption="✅ تم التحميل والإرسال بنجاح عبر البوت الشامل",
                    timeout=300 
                )

            bot.delete_message(message.chat.id, status.message_id)
            print("📤 تم إرسال الملف للمستخدم بنجاح وتطهير الملفات المؤقتة")

        except Exception as e:
            print(f"❌ خطأ أثناء المعالجة: {e}", file=sys.stderr)
            try:
                bot.edit_message_text(f"❌ فشل التحميل أو الرفع:\n\n{e}", message.chat.id, status.message_id)
            except:
                bot.reply_to(message, f"❌ فشل التحميل أو الرفع:\n{e}")
        finally:
            # تنظيف الذاكرة وحذف الملفات المؤقتة تلقائياً لمنع امتلاء السيرفر
            shutil.rmtree(temp_dir, ignore_errors=True)

    # =========================================================
    # 4. تشغيل حلقة الاستقبال المستمرة (Polling)
    # =========================================================
    print("🚀 البوت الشامل متصل الآن وينتظر الروابط من جميع المنصات...")
    bot.polling(none_stop=True, timeout=60)

except Exception as e:
    print(f"❌ حدث خطأ فادح في إقلاع البوت: {e}", file=sys.stderr)
