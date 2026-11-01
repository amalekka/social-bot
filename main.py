import os
import sys
import time
import re
import tempfile
import shutil
import requests
import telebot
import yt_dlp

# قراءة التوكن والكوكيز الاختيارية بأمان من متغيرات البيئة (GitHub Secrets)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES")

if not TOKEN:
    print("❌ خطأ حرج: لم يتم العثور على متغير البيئة TELEGRAM_TOKEN!", file=sys.stderr)
    sys.exit(1)

try:
    print("⏳ جاري تهيئة البوت الشامل والاتصال بتليجرام...")
    bot = telebot.TeleBot(TOKEN)

    # استخراج معرف فيديو يوتيوب (Video ID) لاستخدامه في المحركات البديلة
    def extract_yt_id(url):
        match = re.search(r"(?:v=|\/shorts\/|\/embed\/|youtu\.be\/)([A-Za-z0-9_-]{11})", url)
        return match.group(1) if match else None

    # =========================================================
    # خطة الإنقاذ (Fallback): التحميل عبر خوادم Invidious & Cobalt الحديثة
    # =========================================================
    def fallback_youtube_download(url, output_dir):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        # 1. المحاولة عبر خوادم Invidious المفتوحة (لا تتأثر بحظر IP جيت هاب)
        vid_id = extract_yt_id(url)
        if vid_id:
            invidious_instances = [
                "https://inv.tux.pizza",
                "https://invidious.nerdvpn.de",
                "https://inv.nadeko.net",
                "https://invidious.jing.rocks",
                "https://yt.drgnz.club"
            ]
            for instance in invidious_instances:
                try:
                    res = requests.get(f"{instance}/api/v1/videos/{vid_id}", headers=headers, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        format_streams = data.get("formatStreams", [])
                        # البحث عن صيغة MP4 جاهزة بالصوت والصورة
                        for stream in reversed(format_streams):
                            dl_url = stream.get("url")
                            if dl_url:
                                file_path = os.path.join(output_dir, f"yt_{vid_id}.mp4")
                                with requests.get(dl_url, stream=True, timeout=120, headers=headers) as r:
                                    if r.status_code == 200:
                                        with open(file_path, "wb") as f:
                                            for chunk in r.iter_content(chunk_size=65536):
                                                f.write(chunk)
                                        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
                                            return file_path
                except Exception:
                    continue

        # 2. المحاولة عبر واجهات Cobalt الحديثة (إصدار v10)
        cobalt_apis = [
            "https://cobalt-api.kwiatekmiki.com",
            "https://cobalt.api.timelessnesses.me"
        ]
        payload = {
            "url": url,
            "videoQuality": "720",
            "filenameStyle": "basic"
        }
        for api in cobalt_apis:
            try:
                res = requests.post(api, json=payload, headers=headers, timeout=15)
                if res.status_code == 200:
                    dl_url = res.json().get("url")
                    if dl_url:
                        file_path = os.path.join(output_dir, "youtube_video.mp4")
                        with requests.get(dl_url, stream=True, timeout=120) as r:
                            r.raise_for_status()
                            with open(file_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=65536):
                                    f.write(chunk)
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
                            return file_path
            except Exception:
                continue

        return None

    # =========================================================
    # دالة التحميل الشاملة (يوتيوب + تيك توك + كافة المنصات)
    # =========================================================
    def download_media(url, output_dir):
        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'best[filesize<49M][ext=mp4]/bestvideo[filesize<40M][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
            'merge_output_format': 'mp4',
            'outtmpl': output_template,
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'geo_bypass': True,
            'extractor_args': {
                'youtube': {
                    # عميل نظارات الواقع الافتراضي والتلفاز المدمج الأقل تعرضاً للحظر في 2026
                    'player_client': ['android_vr', 'tv_embedded', 'web_creator'],
                },
                'youtubepot-bgutilhttp': {
                    'base_url': ['http://127.0.0.1:4416'],
                },
                'tiktok': {
                    'app_version': '34.0.0',
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }

        # إذا قام المطور بإضافة YOUTUBE_COOKIES في GitHub Secrets، يتم تفعيلها تلقائياً
        cookie_file = None
        if YOUTUBE_COOKIES and len(YOUTUBE_COOKIES.strip()) > 20:
            cookie_file = os.path.join(output_dir, "cookies.txt")
            with open(cookie_file, "w", encoding="utf-8") as cf:
                cf.write(YOUTUBE_COOKIES)
            ydl_opts['cookiefile'] = cookie_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception:
            # مسح ملف الكوكيز المؤقت قبل تجربة الخطة البديلة
            if cookie_file and os.path.exists(cookie_file):
                os.remove(cookie_file)
            # إذا كان الرابط من يوتيوب، انتقل فوراً لخوادم Invidious / Cobalt البديلة
            if "youtube.com" in url.lower() or "youtu.be" in url.lower():
                fallback_file = fallback_youtube_download(url, output_dir)
                if fallback_file:
                    return fallback_file
            raise Exception("تعذر التحميل، تأكد أن الرابط عام وصحيح.")
        finally:
            if cookie_file and os.path.exists(cookie_file):
                os.remove(cookie_file)
        
        files = [
            os.path.join(output_dir, f) 
            for f in os.listdir(output_dir) 
            if os.path.isfile(os.path.join(output_dir, f)) and not f.endswith(".txt")
        ]
        
        if not files:
            raise Exception("لم يتم العثور على ملف الفيديو بعد انتهاء التحميل.")
            
        return max(files, key=os.path.getsize)

    # =========================================================
    # 1. الرد على أمر /start
    # =========================================================
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        welcome_text = (
            "مرحباً بك في بوت سوشيال مجاني لتحميل الفيديوهات بجودة عالية 📥🔥\n\n"
            "يدعم التحميل المباشر من جميع المنصات:\n"
            "📺 YouTube (فيديوهات و Shorts)\n"
            "🎵 TikTok (بدون علامة مائية)\n"
            "📘 Facebook\n"
            "📸 Instagram\n"
            "🐦 Twitter (X) & Snapchat\n\n"
            "أرسل أي رابط عام وسأقوم بتحميله وإرساله لك فوراً."
        )
        bot.reply_to(message, welcome_text)

    # =========================================================
    # 2. أمر فحص الحالة (/ping)
    # =========================================================
    @bot.message_handler(commands=['ping'])
    def send_ping(message):
        bot.reply_to(message, "Pong! 🏓\nالبوت متصل ويعمل بكفاءة على جميع المنصات.")

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

        except Exception:
            user_text = "❌ تعذر تحميل الفيديو. تأكد أن الرابط عام وصحيح ولا يتجاوز الحد المسموح."
            try:
                bot.edit_message_text(user_text, message.chat.id, status.message_id)
            except Exception:
                bot.reply_to(message, user_text)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # =========================================================
    # 4. حلقة التشغيل الأبدية لمنع التوقف المفاجئ
    # =========================================================
    print("🚀 البوت الشامل متصل الآن وبوضع التشغيل المستمر (Infinity Polling)...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30, logger_level=None)
        except Exception:
            print("⚠️ انقطاع مؤقت في الشبكة، جاري إعادة الاتصال خلال 3 ثوانٍ...", file=sys.stderr)
            time.sleep(3)

except Exception as e:
    print(f"❌ خطأ فادح أثناء التشغيل: {e}", file=sys.stderr)
