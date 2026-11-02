import os
import sys
import time
import re
import subprocess
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

    def get_valid_video_file(output_dir):
        files = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if os.path.isfile(os.path.join(output_dir, f))
            and not f.endswith((".txt", ".part", ".ytdl", ".temp"))
        ]
        if not files:
            return None
        biggest = max(files, key=os.path.getsize)
        return biggest if os.path.getsize(biggest) > 30000 else None

    # =========================================================
    # المحرك الرديف 1: مكتبة PyTubeFix لتحميل ملف الفيديو مباشرة عند حدوث 403
    # =========================================================
    def download_with_pytubefix(url, output_dir):
        try:
            from pytubefix import YouTube
            clients = ['ANDROID_VR', 'MWEB', 'IOS', 'WEB']
            for client in clients:
                try:
                    yt = YouTube(url, client=client)
                    # البحث عن ملف فيديو MP4 مدمج بالصوت والصورة ويناسب حجم تليجرام
                    stream = (
                        yt.streams.filter(progressive=True, file_extension='mp4')
                        .order_by('resolution')
                        .desc()
                        .first()
                    )
                    if stream and stream.filesize_mb and stream.filesize_mb <= 49.5:
                        out_file = stream.download(output_path=output_dir, filename="yt_pytube.mp4")
                        if out_file and os.path.exists(out_file) and os.path.getsize(out_file) > 30000:
                            return out_file

                    # إذا كان الفيديو طويلاً، نختار دقة 360p أو 480p وندمج الصوت والصورة بـ ffmpeg
                    v_stream = (
                        yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True, res="360p").first()
                        or yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').asc().first()
                    )
                    a_stream = yt.streams.filter(adaptive=True, only_audio=True).order_by('abr').asc().first()

                    if v_stream and a_stream:
                        v_path = v_stream.download(output_path=output_dir, filename="v_temp.mp4")
                        a_path = a_stream.download(output_path=output_dir, filename="a_temp.m4a")
                        merged_path = os.path.join(output_dir, "yt_merged.mp4")
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", v_path, "-i", a_path, "-c:v", "copy", "-c:a", "aac", merged_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=120
                        )
                        if os.path.exists(merged_path) and os.path.getsize(merged_path) > 30000:
                            return merged_path
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # =========================================================
    # المحرك الرديف 2: سحب ملف الفيديو MP4 إلى السيرفر عبر الخوادم الوسيطة
    # =========================================================
    def fallback_youtube_download(url, output_dir):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
        vid_id = extract_yt_id(url)
        if not vid_id:
            return None

        # تجربة PyTubeFix أولاً لتحميل ملف الفيديو مباشرة
        pytube_file = download_with_pytubefix(f"https://www.youtube.com/watch?v={vid_id}", output_dir)
        if pytube_file:
            return pytube_file

        # إذا فشل، يسحب السيرفر ملف الفيديو MP4 من المحول السحابي ويحفظه لإرساله كفيديو للمستخدم
        for fmt in ["480", "360", "720"]:
            try:
                init_url = f"https://p.oceansaver.in/ajax/download.php?format={fmt}&url=https://www.youtube.com/watch?v={vid_id}"
                res = requests.get(init_url, headers=headers, timeout=15).json()
                if res.get("success") and res.get("id"):
                    task_id = res["id"]
                    for _ in range(30):
                        time.sleep(2)
                        prog = requests.get(f"https://p.oceansaver.in/ajax/progress.php?id={task_id}", headers=headers, timeout=10).json()
                        if prog.get("success") == 1 and prog.get("download_url"):
                            dl_url = prog["download_url"]
                            file_path = os.path.join(output_dir, f"yt_video_{vid_id}.mp4")
                            with requests.get(dl_url, stream=True, timeout=180, headers=headers) as r:
                                if r.status_code == 200:
                                    with open(file_path, "wb") as f:
                                        for chunk in r.iter_content(chunk_size=65536):
                                            if chunk:
                                                f.write(chunk)
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
                                        return file_path
                            break
            except Exception:
                continue

        return None

    # =========================================================
    # الدالة الرئيسية لتحميل ملف الفيديو (يوتيوب + تيك توك + كافة المنصات)
    # =========================================================
    def download_media(url, output_dir):
        output_template = os.path.join(output_dir, "video_%(id)s.%(ext)s")
        is_youtube = "youtube.com" in url.lower() or "youtu.be" in url.lower()

        cookie_file = None
        if YOUTUBE_COOKIES and len(YOUTUBE_COOKIES.strip()) > 20:
            cookie_file = os.path.join(output_dir, "cookies.txt")
            with open(cookie_file, "w", encoding="utf-8") as cf:
                cf.write(YOUTUBE_COOKIES)

        # صيغ ذكية تدعم الفيديوهات العادية الطويلة والقصيرة بما لا يتجاوز 50 ميجابايت
        yt_format = (
            "best[ext=mp4][filesize<49M]/best[ext=mp4][filesize_approx<49M]/"
            "bestvideo[ext=mp4][filesize<38M]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/"
            "best[height<=480][ext=mp4]/18/best"
        )

        client_profiles = [
            ['tv', 'web_embedded'],
            ['ios', 'android_vr'],
            ['mweb']
        ] if is_youtube else [['default']]

        for clients in client_profiles:
            ydl_opts = {
                'format': yt_format if is_youtube else 'best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'outtmpl': output_template,
                'restrictfilenames': True,
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
                'geo_bypass': True,
                'source_address': '0.0.0.0',
                'cachedir': False,
                'nocheckcertificate': True,
                'concurrent_fragment_downloads': 4,
                'retries': 5,
                'fragment_retries': 5,
                'extractor_args': {
                    'youtubepot-bgutilhttp': {
                        'base_url': ['http://127.0.0.1:4416'],
                    },
                    'tiktok': {
                        'app_version': '34.0.0',
                    }
                }
            }

            if is_youtube:
                ydl_opts['extractor_args']['youtube'] = {'player_client': clients}

            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                video_file = get_valid_video_file(output_dir)
                if video_file:
                    if cookie_file and os.path.exists(cookie_file):
                        os.remove(cookie_file)
                    return video_file
            except Exception as err:
                print(f"⚠️ محاولة بديلة بعد خطأ: {err}", file=sys.stderr)
                for f in os.listdir(output_dir):
                    if f.endswith((".part", ".ytdl", ".temp")):
                        try:
                            os.remove(os.path.join(output_dir, f))
                        except Exception:
                            pass

        if cookie_file and os.path.exists(cookie_file):
            os.remove(cookie_file)

        # إذا رفض يوتيوب التحميل عبر yt-dlp، يقوم المحرك الرديف بتحميل ملف الفيديو نفسه وإرجاعه
        if is_youtube:
            fallback_file = fallback_youtube_download(url, output_dir)
            if fallback_file:
                return fallback_file

        raise Exception("تعذر التحميل، تأكد أن الرابط عام وليس خاص.")

    # =========================================================
    # 1. الرد على أمر /start
    # =========================================================
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        welcome_text = (
            "مرحباً بك في بوت سوشيال مجاني لتحميل الفيديوهات بجودة عالية📥🔥\n\n"
            "البوت يدعم تحميل الفيديوهات من جميع منصات سوشيال ميديا والمنصات التالية:\n"
            "📺 YouTube (فيديوهات عادية و Shorts)\n"
            "🎵 TikTok (بدون علامة مائية)\n"
            "📘 Facebook\n"
            "📸 Instagram\n"
            "🐦 Twitter (X) & Snapchat\n\n"
            "أرسل أي رابط الفيديو وانتظر ثواني حتي يصلك الفيديو."
        )
        bot.reply_to(message, welcome_text)

    # =========================================================
    # 2. أمر فحص الحالة (/ping)
    # =========================================================
    @bot.message_handler(commands=['ping'])
    def send_ping(message):
        bot.reply_to(message, "Pong! 🏓\nالبوت متصل ويعمل بكفاءة على جميع المنصات.")

    # =========================================================
    # 3. استقبال الروابط وتحميل وإرسال ملف الفيديو للمستخدم
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
                    f"❌ عذراً، حجم الفيديو كبير ({size_mb:.2f} MB).\nأقصى حجم مسموح به لبوتات تليجرام هو 50 ميجابايت.",
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
                    caption="✅ تم التحميل الفيديو بنجاح",
                    supports_streaming=True,
                    timeout=300
                )

            bot.delete_message(message.chat.id, status.message_id)

        except Exception:
            user_text = "❌ تعذر تحميل الفيديو. تأكد أن الرابط عام وليس خاص ولا يتجاوز الحد المسموح."
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
