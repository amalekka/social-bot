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

    def extract_yt_id(url):
        match = re.search(r"(?:v=|\/shorts\/|\/embed\/|youtu\.be\/)([A-Za-z0-9_-]{11})", url)
        return match.group(1) if match else None

    # =========================================================
    # خطة الإنقاذ (Fallback): التحميل عبر بروكسي Invidious المباشر (يتخطى 403 نهائياً)
    # =========================================================
    def fallback_youtube_download(url, output_dir):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

        vid_id = extract_yt_id(url)
        if vid_id:
            invidious_instances = [
                "https://inv.tux.pizza",
                "https://invidious.nerdvpn.de",
                "https://inv.nadeko.net",
                "https://invidious.jing.rocks",
                "https://yt.drgnz.club"
            ]
            # 1. المحاولة الأولى: التحميل المباشر عبر مسار البروكسي المدمج (يتجنب خطأ 403 المرتبط بالـ IP)
            for instance in invidious_instances:
                try:
                    # itag 18 هو صيغة MP4 قياسية مدمجة (صوت وصورة) تعمل مع كل الفيديوهات
                    direct_proxy_url = f"{instance}/latest_version?id={vid_id}&itag=18&local=true"
                    file_path = os.path.join(output_dir, f"yt_{vid_id}.mp4")
                    with requests.get(direct_proxy_url, stream=True, timeout=90, headers=headers, allow_redirects=True) as r:
                        if r.status_code == 200:
                            with open(file_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=65536):
                                    if chunk:
                                        f.write(chunk)
                            if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
                                return file_path
                except Exception:
                    continue

            # 2. المحاولة الثانية: عبر API Invidious مع إجبار خاصية local=true
            for instance in invidious_instances:
                try:
                    res = requests.get(f"{instance}/api/v1/videos/{vid_id}", headers=headers, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        format_streams = data.get("formatStreams", [])
                        for stream in reversed(format_streams):
                            dl_url = stream.get("url")
                            if dl_url:
                                # إضافة local=true لإجبار السيرفر الوسيط على تمرير الفيديو وعدم إعطاء 403
                                if "local=true" not in dl_url:
                                    dl_url += "&local=true" if "?" in dl_url else "?local=true"
                                file_path = os.path.join(output_dir, f"yt_api_{vid_id}.mp4")
                                with requests.get(dl_url, stream=True, timeout=120, headers=headers) as r:
                                    if r.status_code == 200:
                                        with open(file_path, "wb") as f:
                                            for chunk in r.iter_content(chunk_size=65536):
                                                if chunk:
                                                    f.write(chunk)
                                        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
                                            return file_path
                except Exception:
                    continue

        return None

    # =========================================================
    # دالة التحميل الشاملة (مع حل جذري لمشكلة HTTP Error 403)
    # =========================================================
    def download_media(url, output_dir):
        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")
        
        ydl_opts = {
            # تفضيل صيغ البث المتكامل (m3u8/mp4) التي لا تخضع لحظر 403 مثل صيغ DASH المنفصلة
            'format': 'best[filesize<49M][ext=mp4]/best[height<=720][ext=mp4]/18/best',
            'merge_output_format': 'mp4',
            'outtmpl': output_template,
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
            'geo_bypass': True,
            # حل أساسي لخطأ 403: إجبار الاتصال على IPv4 فقط ومسح الكاش القديم
            'source_address': '0.0.0.0',
            'cachedir': False,
            'nocheckcertificate': True,
            'Retries': 5,
            'fragment_retries': 5,
            'extractor_args': {
                'youtube': {
                    # إزالة web_creator لأنه يسبب 403، والاعتماد على ios و android_vr (بث HLS مستقر)
                    'player_client': ['ios', 'android_vr', 'tv_embedded'],
                    'player_skip': ['webpage', 'configs'],
                },
                'youtubepot-bgutilhttp': {
                    'base_url': ['http://127.0.0.1:4416'],
                },
                'tiktok': {
                    'app_version': '34.0.0',
                }
            }
        }

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
            if cookie_file and os.path.exists(cookie_file):
                os.remove(cookie_file)
            # إذا حدث خطأ 403 في الفيديوهات الطويلة، يتدخل البروكسي الوسيط فوراً لتحميل الفيديو
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
            if os.path.isfile(os.path.join(output_dir, f)) and not f.endswith(".txt") and not f.endswith(".part")
        ]
        
        if not files:
            # محاولة أخيرة عبر البروكسي إذا انتهى yt-dlp بدون إخراج ملف مكتمل
            if "youtube.com" in url.lower() or "youtu.be" in url.lower():
                fallback_file = fallback_youtube_download(url, output_dir)
                if fallback_file:
                    return fallback_file
            raise Exception("لم يتم العثور على ملف الفيديو بعد انتهاء التحميل.")
            
        return max(files, key=os.path.getsize)

    # =========================================================
    # 1. الرد على أمر /start
    # =========================================================
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        welcome_text = (
            "مرحباً بك في بوت التحميل الشامل 📥🔥\n\n"
            "يدعم التحميل المباشر من جميع المنصات:\n"
            "📺 YouTube (فيديوهات عادية و Shorts)\n"
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
