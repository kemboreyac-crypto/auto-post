# -*- coding: utf-8 -*-
"""
Telegram Remote Control Bot (The Master Controller)
===================================================
Receives media (photos/videos/text) from the user on Telegram.
Presents interactive buttons to select channels:
- Facebook Pages (Multi-Page)
- Facebook Groups (Niche Routing & 24h Cooldown)
- TikTok (Auto-Post & Mobile Share)

Can run via:
1. Long-polling (local desktop / VPS): python telegram_controller.py
2. Webhook (Vercel / Cloud server): processed via app.py
"""

import os
import sys
import json
import time
import requests
import threading
import re
import tempfile
from typing import Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
    MEDIA_TEMP_DIR = os.path.join(tempfile.gettempdir(), "temp_media")
else:
    MEDIA_TEMP_DIR = os.path.join(BASE_DIR, "temp_media")
os.makedirs(MEDIA_TEMP_DIR, exist_ok=True)

# នាំចូល Services ក្នុងមូលដ្ឋាន
import facebook_page_service
import facebook_group_service
import tiktok_service
import khmer_linguistic_sanitizer

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TMP_CONFIG_FILE = os.path.join(tempfile.gettempdir(), "config.json")

def load_config() -> dict:
    if os.path.exists(TMP_CONFIG_FILE):
        try:
            with open(TMP_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    elif os.getenv("CONFIG_JSON"):
        try:
            return json.loads(os.getenv("CONFIG_JSON"))
        except Exception:
            pass
    example_file = os.path.join(BASE_DIR, "config.example.json")
    if os.path.exists(example_file):
        try:
            with open(example_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg_data: dict) -> bool:
    saved = False
    if not os.environ.get("VERCEL") and os.access(BASE_DIR, os.W_OK):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, ensure_ascii=False, indent=2)
            saved = True
        except Exception:
            pass
    try:
        with open(TMP_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, ensure_ascii=False, indent=2)
        saved = True
    except Exception:
        pass
    global CONFIG, BOT_TOKEN, ALLOWED_CHAT_ID
    CONFIG = cfg_data
    if "bot_token" in cfg_data and cfg_data["bot_token"]:
        BOT_TOKEN = cfg_data["bot_token"]
    if "chat_id" in cfg_data and cfg_data["chat_id"]:
        ALLOWED_CHAT_ID = str(cfg_data["chat_id"])
    return saved

CONFIG = load_config()
BOT_TOKEN = CONFIG.get("bot_token", "")
ALLOWED_CHAT_ID = str(CONFIG.get("chat_id", ""))

# ផ្ទុក State បណ្ដោះអាសន្នរបស់អ្នកប្រើប្រាស់
USER_SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_bot_token() -> str:
    cfg = load_config()
    return cfg.get("bot_token") or BOT_TOKEN

def send_telegram_api(method: str, payload: dict, files: dict = None) -> dict:
    """ហៅទៅកាន់ Telegram Bot API"""
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        if files:
            res = requests.post(url, data=payload, files=files, timeout=60)
        else:
            res = requests.post(url, json=payload, timeout=20)
        return res.json()
    except Exception as e:
        print(f"⚠️ Telegram API Error ({method}): {e}")
        return {"ok": False, "description": str(e)}

def build_interactive_keyboard(dest_pages: bool, dest_groups: bool, dest_tiktok: bool) -> dict:
    """បង្កើតប៊ូតុងចុច Inline Keyboard ជ្រើសរើសគោលដៅ"""
    p_icon = "✅" if dest_pages else "❌"
    g_icon = "✅" if dest_groups else "❌"
    t_icon = "✅" if dest_tiktok else "❌"

    return {
        "inline_keyboard": [
            [
                {"text": f"📘 FB Pages: {p_icon}", "callback_data": "toggle_pages"},
                {"text": f"👥 Groups: {g_icon}", "callback_data": "toggle_groups"},
                {"text": f"🎵 TikTok: {t_icon}", "callback_data": "toggle_tiktok"}
            ],
            [
                {"text": "🚀 ផុសភ្លាមៗ (Publish Now)", "callback_data": "action_publish"},
                {"text": "❌ បោះបង់ (Cancel)", "callback_data": "action_cancel"}
            ]
        ]
    }

def download_telegram_file(file_id: str, file_name: str) -> Optional[str]:
    """ទាញយក File រូបភាព ឬវីដេអូពី Telegram មកទុកក្នុង temp_media"""
    res = send_telegram_api("getFile", {"file_id": file_id})
    if not res.get("ok"):
        return None
    file_path_on_server = res["result"].get("file_path", "")
    token = get_bot_token()
    download_url = f"https://api.telegram.org/file/bot{token}/{file_path_on_server}"
    
    local_path = os.path.join(MEDIA_TEMP_DIR, file_name)
    r = requests.get(download_url, stream=True, timeout=60)
    if r.status_code == 200:
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return local_path
    return None

def send_settings_menu(chat_id: str, message_id: int = None):
    """ផ្ញើផ្ទាំងបញ្ជា Setting Control Hub ក្នុង Telegram"""
    cfg = load_config()
    all_pages = cfg.get("facebook_all_pages", False)
    mode_text = "🟢 គ្រប់ Pages ទាំងអស់ (All Pages)" if all_pages else "🟡 Pages ដែលបានជ្រើសរើស (Selected)"
    
    text = (
        "⚙️ **ផ្ទាំងបញ្ជា និងការកំណត់ (Control & Settings Hub)**\n\n"
        f"• 📘 **Facebook Pages Mode:** {mode_text}\n"
        f"• 👥 **Facebook Groups:** ប្រព័ន្ធ Niche & Anti-Spam 24h\n"
        f"• 📱 **Admin Chat ID:** `{chat_id}`\n\n"
        "សូមចុចប៊ូតុងខាងក្រោមដើម្បីបញ្ជា ឬកែប្រែការកំណត់:"
    )
    
    kb = {
        "inline_keyboard": [
            [
                {"text": f"📘 ប្ដូរ Mode: {'ទៅ Selected' if all_pages else 'ទៅ All Pages'}", "callback_data": "setting_toggle_pages"}
            ],
            [
                {"text": "🔄 សម្អាត Cooldown 24h គ្រប់ក្រុម", "callback_data": "setting_reset_cooldown"},
                {"text": "📊 ពិនិត្យសុពលភាព Token", "callback_data": "setting_check_token"}
            ],
            [
                {"text": "❌ បិទផ្ទាំងកំណត់ (Close)", "callback_data": "setting_close"}
            ]
        ]
    }
    
    if message_id:
        send_telegram_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": kb
        })
    else:
        send_telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": kb
        })

def extract_media_from_content(content: str):
    """
    ស្វែងរក Video URL ឬ Image URL ក្នុងអត្ថបទដោយស្វ័យប្រវត្តិ
    - ប្រសិនបើរើឃើញ Video URL: ទាញយក URL នោះ ហើយលុបបន្ទាត់ '🔗 តំណភ្ជាប់វីដេអូ: ...' ចេញពី Caption ឱ្យស្អាត
    - ប្រសិនបើរើឃើញ Image URL: ទាញយក URL នោះ ហើយលុបបន្ទាត់ '🔗 តំណភ្ជាប់រូបភាព: ...' ចេញពី Caption ឱ្យស្អាត
    Returns: (clean_text: str, media_type: str, media_url: Optional[str])
    """
    if not content:
        return "", "text", None

    # 1. ស្វែងរក Video URL (MP4, MOV, WEBM, MKV, M4V, ឬ /video/)
    vid_match = re.search(r'(https?://[^\s\)\"\']+(?:\.mp4|\.mov|\.webm|\.mkv|\.m4v|/video/[^\s\)\"\']+))', content, re.IGNORECASE)
    if vid_match:
        url = vid_match.group(1).rstrip('.,;!?:)')
        clean_lines = []
        for line in content.splitlines():
            if url in line:
                continue
            if any(tag in line for tag in ["តំណភ្ជាប់វីដេអូ", "🔗", "Video Link"]) and any(ext in line.lower() for ext in [".mp4", ".mov", ".webm", "http"]):
                continue
            clean_lines.append(line)
        cleaned = '\n'.join(clean_lines).strip()
        return cleaned, "video", url

    # 2. ស្វែងរក Image URL (JPG, JPEG, PNG, WEBP, GIF)
    img_match = re.search(r'(https?://[^\s\)\"\']+(?:\.jpg|\.jpeg|\.png|\.webp|\.gif))', content, re.IGNORECASE)
    if img_match:
        url = img_match.group(1).rstrip('.,;!?:)')
        clean_lines = []
        for line in content.splitlines():
            if url in line:
                continue
            if any(tag in line for tag in ["តំណភ្ជាប់រូបភាព", "🔗", "Image Link", "Photo Link"]) and any(ext in line.lower() for ext in [".jpg", ".png", "http"]):
                continue
            clean_lines.append(line)
        cleaned = '\n'.join(clean_lines).strip()
        return cleaned, "photo", url

    return content.strip(), "text", None

def handle_incoming_message(msg: dict):
    """វិភាគ និងទទួលសារ រូបភាព ឬវីដេអូពីម្ចាស់ Telegram"""
    chat_id = str(msg.get("chat", {}).get("id", ""))
    
    # ពិនិត្យសុវត្ថិភាព ទទួលតែម្ចាស់ Chat ID ប៉ុណ្ណោះ
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        send_telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": "⛔ សុំទោស! អ្នកគ្មានសិទ្ធិបញ្ជា Bot នេះឡើយ។ (Unauthorized Access)"
        })
        return

    caption = msg.get("caption") or msg.get("text") or ""
    # សម្អាតអក្សរខ្មែរ
    clean_caption = khmer_linguistic_sanitizer.sanitize_khmer_script(caption) if caption else ""

    media_type = "text"
    local_media_path = None

    # 1. បើជាវីដេអូ (Video)
    if "video" in msg:
        media_type = "video"
        vid = msg["video"]
        file_id = vid.get("file_id")
        file_name = f"vid_{int(time.time())}.mp4"
        send_telegram_api("sendMessage", {"chat_id": chat_id, "text": "⏳ កំពុងទាញយកវីដេអូពី Telegram..."})
        local_media_path = download_telegram_file(file_id, file_name)

    # 2. បើជា Animation / GIF / Loop Video
    elif "animation" in msg:
        media_type = "video"
        anim = msg["animation"]
        file_id = anim.get("file_id")
        file_name = f"anim_{int(time.time())}.mp4"
        send_telegram_api("sendMessage", {"chat_id": chat_id, "text": "⏳ កំពុងទាញយកវីដេអូ Animation ពី Telegram..."})
        local_media_path = download_telegram_file(file_id, file_name)

    # 3. បើជា Document (ពិនិត្យមើលថាតើជា File Video ឬ Photo)
    elif "document" in msg:
        doc = msg["document"]
        mime = doc.get("mime_type", "").lower()
        file_name = doc.get("file_name", "").lower()
        file_id = doc.get("file_id")
        if mime.startswith("video/") or any(file_name.endswith(ext) for ext in [".mp4", ".mov", ".webm", ".mkv"]):
            media_type = "video"
            send_telegram_api("sendMessage", {"chat_id": chat_id, "text": "⏳ កំពុងទាញយកឯកសារវីដេអូពី Telegram..."})
            local_media_path = download_telegram_file(file_id, f"doc_vid_{int(time.time())}.mp4")
        elif mime.startswith("image/") or any(file_name.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            media_type = "photo"
            send_telegram_api("sendMessage", {"chat_id": chat_id, "text": "⏳ កំពុងទាញយករូបភាពពី Telegram..."})
            local_media_path = download_telegram_file(file_id, f"doc_img_{int(time.time())}.jpg")
        else:
            media_type = "document"
            local_media_path = download_telegram_file(file_id, doc.get("file_name", "document.bin"))

    # 4. បើជារូបភាព (Photo)
    elif "photo" in msg:
        media_type = "photo"
        photos = msg["photo"]
        best_photo = photos[-1] # យករូបច្បាស់បំផុត
        file_id = best_photo.get("file_id")
        file_name = f"img_{int(time.time())}.jpg"
        local_media_path = download_telegram_file(file_id, file_name)

    # 5. បើជា Text ធម្មតា
    elif "text" in msg:
        text_content = msg.get("text", "").strip()
        lower_text = text_content.lower()

        # Commands: Settings
        if text_content == "/settings":
            send_settings_menu(chat_id)
            return

        # Commands: Admin / ID check
        if lower_text in ["/id", "/admin", "/admin id", "admin", "/myid", "id"]:
            first_name = msg.get("from", {}).get("first_name", "")
            username = msg.get("from", {}).get("username", "")
            user_label = f"@{username}" if username else first_name
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    f"👤 **ព័ត៌មាន Admin របស់អ្នក (Admin Profile):**\n\n"
                    f"• **គណនី:** {first_name} ({user_label})\n"
                    f"• **Telegram Chat ID:** `{chat_id}`\n"
                    f"• **សិទ្ធិបញ្ជា:** 🟢 មានសិទ្ធិពេញលេញ (Authorized Admin)\n\n"
                    f"⚙️ ប្រើប្រាស់បញ្ជា:\n"
                    f"• /settings - បើកផ្ទាំងកំណត់គោលដៅ\n"
                    f"• /status - ពិនិត្យសុពលភាព Facebook Token\n"
                    f"• /help - ការណែនាំរបៀបប្រើប្រាស់"
                ),
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "⚙️ បើកផ្ទាំងកំណត់ (Settings)", "callback_data": "open_settings_menu"}],
                        [{"text": "📊 ពិនិត្យស្ថានភាព Token", "callback_data": "setting_check_token"}]
                    ]
                }
            })
            return

        # Commands: Status
        if lower_text in ["/status", "status"]:
            cfg = load_config()
            t = cfg.get("facebook_user_access_token") or cfg.get("facebook_access_token")
            info = facebook_page_service.get_token_expiration_info(t)
            pages = facebook_page_service.get_connected_pages(t)
            groups = facebook_group_service.load_groups()
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    f"📊 **ស្ថានភាពប្រព័ន្ធបច្ចុប្បន្ន (Live Status):**\n\n"
                    f"• 📘 **Facebook Token:** {info.get('text')}\n"
                    f"• 📄 **Pages សរុប:** {len(pages)} Pages\n"
                    f"• 👥 **Groups សរុប:** {len(groups)} ក្រុម\n"
                    f"• 📱 **Admin Chat ID:** `{chat_id}`"
                ),
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "⚙️ កំណត់គោលដៅ (Settings)", "callback_data": "open_settings_menu"}]
                    ]
                }
            })
            return

        # Commands: Cancel
        if lower_text in ["/cancel", "cancel", "បោះបង់"]:
            USER_SESSIONS.pop(chat_id, None)
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": "❌ បានសម្អាតមាតិកាចាស់ចោលរួចរាល់។ អ្នកអាចផ្ញើសារថ្មីមកបានគ្រប់ពេល!"
            })
            return

        # AI Caption Generator: /ai <topic>
        if lower_text.startswith("/ai ") or lower_text.startswith("ai "):
            topic = text_content[4:].strip() if lower_text.startswith("/ai ") else text_content[3:].strip()
            if topic:
                send_telegram_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"⏳ **កំពុងប្រើប្រាស់ Gemini AI ដើម្បីសរសេរ Caption សម្រាប់៖**\n_{topic}_ ...",
                    "parse_mode": "Markdown"
                })
                from app import generate_gemini_caption
                generated = generate_gemini_caption(topic, "sales")
                if generated:
                    clean_caption = khmer_linguistic_sanitizer.sanitize_khmer_script(generated)
                    USER_SESSIONS[chat_id] = {
                        "media_type": "text",
                        "media_path": None,
                        "caption": clean_caption,
                        "dest_pages": True,
                        "dest_groups": True,
                        "dest_tiktok": False
                    }
                    kb = build_interactive_keyboard(True, True, False)
                    send_telegram_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": (
                            f"✨ **Gemini AI បានសរសេរ Caption រួចរាល់៖**\n\n"
                            f"{clean_caption}\n\n"
                            f"───────────────────\n"
                            f"🎯 **សូមពិនិត្យ និងចុច «🚀 ផុសភ្លាមៗ (Publish Now)» ខាងក្រោម៖**"
                        ),
                        "reply_markup": kb
                    })
                    return
                else:
                    send_telegram_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": "⚠️ មិនអាចបង្កើត Caption បាន សូមព្យាយាមម្ដងទៀត។"
                    })
                    return

        # TikTok Command & Guide
        if lower_text in ["/tiktok", "tiktok", "ទិកតុក", "របៀបផុស tiktok", "របៀបផុសទិកតុក"]:
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    "🎵 **របៀបផុសក្នុង TikTok តាមរយៈ Telegram Bot (ងាយស្រួលបំផុត):**\n\n"
                    "1️⃣ **ផ្ញើវីដេអូ ឬរូបភាព** ជាមួយ Caption មកកាន់ Bot នេះ\n"
                    "2️⃣ Bot នឹងបង្ហាញផ្ទាំងជ្រើសរើស Channels:\n"
                    "   • ពិនិត្យមើលឱ្យប្រាកដថា **[🎵 TikTok: ✅]** បើកដំណើរការ\n"
                    "   • ចុច **[🚀 ផុសភ្លាមៗ (Publish Now)]**\n"
                    "3️⃣ **Bot នឹងរៀបចំជូនលោកអ្នកស្វ័យប្រវត្តិនូវ:**\n"
                    "   • Viral Khmer Hashtags (#fyp #viral #khmer...)\n"
                    "   • ប្រអប់ Caption ចុចលើវាដើម្បី Copy ភ្លាមៗ (1-Tap Copy)\n"
                    "   • ប៊ូតុងបើក **TikTok Studio Upload** ផ្ទាល់\n"
                    "4️⃣ លោកអ្នកគ្រាន់តែចុច Copy រួចចុចប៊ូតុងបើក TikTok Upload Paste Caption ចូលជាការស្រេច! 🎉"
                ),
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "📱 បើក TikTok Studio Upload", "url": "https://www.tiktok.com/creator-center/upload"}]
                    ]
                }
            })
            return

        # Friendly Guide for keywords like "ចង់ផ្សាយ"
        if lower_text in ["ចង់ផ្សាយ", "ផ្សាយ", "/post", "post", "ចង់ផុស", "ផុស", "/help", "help", "របៀបផ្សាយ"]:
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    "📢 **របៀបផ្សព្វផ្សាយតាម Telegram Bot (ងាយស្រួលបំផុត):**\n\n"
                    "លោកអ្នកគ្រាន់តែផ្ញើចូលមកទីនេះនូវ៖\n"
                    "1️⃣ **រូបភាព (Photo)** ភ្ជាប់ជាមួយ Caption ផ្សាយ\n"
                    "2️⃣ **វីដេអូ (Video)** ភ្ជាប់ជាមួយ Caption ផ្សាយ\n"
                    "3️⃣ ឬ **អត្ថបទផ្សាយពេញលេញ (Full Text)**\n\n"
                    "💡 *(សូមកុំវាយតែពាក្យ «ចង់ផ្សាយ» ព្រោះ Bot នឹងគិតថាវាជា Caption សម្រាប់យកទៅផុស!)*\n\n"
                    "✨ **ពិសេសបំផុត:** លោកអ្នកអាចឱ្យ AI សរសេរ Caption ឱ្យភ្លាមៗដោយគ្រាន់តែវាយ៖\n"
                    "`/ai <ប្រធានបទ>`\n"
                    "ឧទាហរណ៍៖ `/ai លក់ដី 5x20 នៅកំពង់ស្ពឺ $7500 ប្លង់រឹង`"
                ),
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "⚙️ បើកការកំណត់ (Settings)", "callback_data": "open_settings_menu"}]
                    ]
                }
            })
            return

        if text_content == "/start":
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": (
                    "👋 **សូមស្វាគមន៍មកកាន់ Facebook & Social Broadcaster Bot!**\n\n"
                    "💡 **របៀបប្រើប្រាស់:**\n"
                    "• ផ្ញើ **រូបភាព (Photo)** + Caption មកកាន់ទីនេះ\n"
                    "• ឬផ្ញើ **វីដេអូ (Video)** + Caption មកកាន់ទីនេះ\n"
                    "• ឬវាយ **សារផ្សព្វផ្សាយ (Text)** មកកាន់ទីនេះ\n\n"
                    "⚙️ ឬចុចប៊ូតុង **ការកំណត់ (Settings)** ខាងក្រោមដើម្បីបញ្ជាប្រព័ន្ធ:"
                ),
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "⚙️ បើកការកំណត់ (Settings)", "callback_data": "open_settings_menu"}],
                        [{"text": "📊 ពិនិត្យស្ថានភាព Token", "callback_data": "setting_check_token"}]
                    ]
                }
            })
            return

    # ស្វែងរក Video URL ឬ Image URL ក្នុង Caption ដោយស្វ័យប្រវត្តិ និងសម្អាត Link ចេញពីអត្ថបទ
    clean_text, detected_type, detected_url = extract_media_from_content(clean_caption)
    if media_type == "text" and detected_type != "text" and detected_url:
        media_type = detected_type
        local_media_path = detected_url
        clean_caption = clean_text
    elif media_type in ["video", "photo"]:
        # បើជា File ស្រាប់ គ្រាន់តែសម្អាតបន្ទាត់ Link ជាន់គ្នាចេញពី Caption
        clean_caption = clean_text

    # កត់ត្រាចូល User Session (បើក FB Pages និង Groups ជា Default)
    USER_SESSIONS[chat_id] = {
        "media_type": media_type,
        "media_path": local_media_path,
        "caption": clean_caption,
        "dest_pages": True,
        "dest_groups": True,
        "dest_tiktok": (media_type == "video") # TikTok ទទួលតែវីដេអូ
    }

    # បង្ហាញផ្ទាំងបញ្ជា (Control Dashboard in Chat)
    media_label = "🎥 វីដេអូ (Native Video Player)" if media_type == "video" else ("🖼️ រូបភាព (Photo)" if media_type == "photo" else "📝 អត្ថបទ (Text)")
    
    media_source_info = ""
    if media_type == "video":
        if str(local_media_path).startswith("http"):
            media_source_info = f"\n🎬 **ប្រភពវីដេអូ:** ស្វែងរកឃើញ Auto ជោគជ័យ (នឹងផុសជាវីដេអូផ្ទាល់ Native Video Player មិនទម្លាក់ Link ឡើយ)\n"
        elif local_media_path:
            media_source_info = f"\n🎬 **ឯកសារវីដេអូ:** `{os.path.basename(local_media_path)}`\n"
    elif media_type == "photo":
        if str(local_media_path).startswith("http"):
            media_source_info = f"\n🖼️ **ប្រភពរូបភាព:** `{local_media_path}`\n"
        elif local_media_path:
            media_source_info = f"\n🖼️ **ឯកសាររូបភាព:** `{os.path.basename(local_media_path)}`\n"

    msg_text = (
        f"📥 **បានទទួល៖ {media_label}**\n\n"
        f"📄 **អត្ថបទ Caption សម្រាប់ផុស (Cleaned):**\n{clean_caption if clean_caption else '(គ្មាន Caption)'}\n"
        f"{media_source_info}"
        f"───────────────────\n"
        f"🎯 **សូមជ្រើសរើសគោលដៅផ្សព្វផ្សាយ (Channels):**"
    )

    kb = build_interactive_keyboard(
        dest_pages=USER_SESSIONS[chat_id]["dest_pages"],
        dest_groups=USER_SESSIONS[chat_id]["dest_groups"],
        dest_tiktok=USER_SESSIONS[chat_id]["dest_tiktok"]
    )

    send_telegram_api("sendMessage", {
        "chat_id": chat_id,
        "text": msg_text,
        "parse_mode": "Markdown",
        "reply_markup": kb
    })

def handle_callback_query(callback: dict):
    """គ្រប់គ្រងពេល User ចុចប៊ូតុង Inline Buttons"""
    cb_id = callback.get("id")
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    message_id = callback.get("message", {}).get("message_id")
    action = callback.get("data", "")

    # បញ្ជាក់ Telegram ថាបានទទួល click
    send_telegram_api("answerCallbackQuery", {"callback_query_id": cb_id})

    # ================= 1. SETTINGS ACTIONS =================
    if action == "open_settings_menu":
        send_settings_menu(chat_id, message_id=message_id)
        return

    elif action == "setting_toggle_pages":
        cfg = load_config()
        curr = cfg.get("facebook_all_pages", False)
        cfg["facebook_all_pages"] = not curr
        save_config(cfg)
        send_settings_menu(chat_id, message_id=message_id)
        return

    elif action == "setting_reset_cooldown":
        count = facebook_group_service.reset_all_cooldowns()
        send_telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": f"✅ បានសម្អាត Cooldown 24h លើ {count} ក្រុមជោគជ័យ! គ្រប់ក្រុមអាចផុសបានភ្លាមៗ។"
        })
        send_settings_menu(chat_id, message_id=message_id)
        return

    elif action == "setting_check_token":
        cfg = load_config()
        t = cfg.get("facebook_user_access_token") or cfg.get("facebook_access_token")
        info = facebook_page_service.get_token_expiration_info(t)
        send_telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": f"📊 **ស្ថានភាព Facebook Token:**\n• {info.get('text')}\n• នៅសល់៖ {info.get('remaining_days', 'N/A')} ថ្ងៃ",
            "parse_mode": "Markdown"
        })
        return

    elif action == "setting_close":
        send_telegram_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "👌 ផ្ទាំងកំណត់ត្រូវបានបិទ។"
        })
        return

    # ================= 2. BROADCAST SESSION ACTIONS =================
    session = USER_SESSIONS.get(chat_id)
    if not session:
        send_telegram_api("sendMessage", {"chat_id": chat_id, "text": "⚠️ ព័ត៌មានផុតកំណត់ សូមផ្ញើមាតិកាមកម្ដងទៀត។"})
        return

    # 1. ប៊ូតុង Toggle គោលដៅ
    if action == "toggle_pages":
        session["dest_pages"] = not session["dest_pages"]
    elif action == "toggle_groups":
        session["dest_groups"] = not session["dest_groups"]
    elif action == "toggle_tiktok":
        session["dest_tiktok"] = not session["dest_tiktok"]
    elif action == "action_cancel":
        send_telegram_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "❌ ការផ្សព្វផ្សាយត្រូវបានបោះបង់ (Cancelled)។"
        })
        USER_SESSIONS.pop(chat_id, None)
        return
    elif action == "action_publish":
        # ពិនិត្យមើលថាតើមានជ្រើសរើស Channel យ៉ាងហោចណាស់មួយឬនៅ
        if not session.get("dest_pages") and not session.get("dest_groups") and not session.get("dest_tiktok"):
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": "⚠️ **លោកអ្នកមិនទាន់បានជ្រើសរើស Channel ណាមួយឡើយ!**\n\nសូមចុចជ្រើសរើស [FB Pages: ✅] ឬ [Groups: ✅] ខាងលើជាមុនសិន មុននឹងចុច «🚀 ផុសភ្លាមៗ»។",
                "parse_mode": "Markdown"
            })
            return
        # បើករត់លើ Serverless (Vercel) ត្រូវរត់ផ្ទាល់ (Synchronous) ដើម្បីកុំឱ្យ Container Freeze
        # បើករត់លើ Desktop / Long Polling អាចរត់ Thread បាន
        if os.environ.get("VERCEL"):
            execute_broadcast(chat_id, message_id, session)
        else:
            threading.Thread(target=execute_broadcast, args=(chat_id, message_id, session)).start()
        return

    # Update ប៊ូតុងលើអេក្រង់
    kb = build_interactive_keyboard(
        dest_pages=session["dest_pages"],
        dest_groups=session["dest_groups"],
        dest_tiktok=session["dest_tiktok"]
    )
    send_telegram_api("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": kb
    })

def execute_broadcast(chat_id: str, message_id: int, session: dict):
    """រត់ការបាញ់ផ្សាយទៅកាន់ Channels ដែលបានជ្រើសរើស"""
    try:
        if message_id:
            send_telegram_api("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "🚀 **កំពុងដំណើរការផ្សព្វផ្សាយ (Broadcasting in progress...)...**\n\nសូមរង់ចាំបន្តិច...",
                "parse_mode": "Markdown"
            })
        else:
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": "🚀 **ចាប់ផ្ដើមដំណើរការផ្សព្វផ្សាយ (Broadcasting in progress...)...**\n\nសូមរង់ចាំបន្តិច...",
                "parse_mode": "Markdown"
            })

        cfg = load_config()
        user_token = cfg.get("facebook_user_access_token") or cfg.get("facebook_access_token")
        page_id = cfg.get("facebook_page_id")

        caption = session.get("caption", "")
        media_type = session.get("media_type")
        media_path = session.get("media_path")

        # ត្រួតពិនិត្យ និងទាញយក Video/Photo URL ដោយស្វ័យប្រវត្តិ ប្រសិនបើនៅជា Text
        if media_type == "text" or not media_path:
            clean_c, auto_type, auto_url = extract_media_from_content(caption)
            if auto_type != "text" and auto_url:
                media_type = auto_type
                media_path = auto_url
                caption = clean_c

        report_lines = ["📊 **របាយការណ៍ផ្សព្វផ្សាយ (Broadcast Report):**\n"]

        # ---------------- 1. FACEBOOK PAGES ----------------
        if session.get("dest_pages"):
            media_desc = "🎥 Native Video" if media_type == "video" else ("🖼️ Photo" if media_type == "photo" else "📝 Text")
            send_telegram_api("sendMessage", {"chat_id": chat_id, "text": f"📘 [1/3] កំពុងផុស {media_desc} ចូល Facebook Pages..."})
            pages = facebook_page_service.get_connected_pages(user_token)
            if not pages and page_id:
                # ប្រើទោល Page ID បើមិនអាចទាញបញ្ជី
                pages = [{"id": page_id, "name": "Main Page", "access_token": user_token}]

            # ពិនិត្យការកំណត់ជ្រើសរើស Pages ក្នុង config.json
            if pages and not cfg.get("facebook_all_pages", False):
                selected_pages_cfg = cfg.get("facebook_selected_pages", [])
                if selected_pages_cfg:
                    selected_ids = {str(p.get("id")) for p in selected_pages_cfg}
                    filtered_pages = [p for p in pages if str(p.get("id")) in selected_ids]
                    if filtered_pages:
                        pages = filtered_pages

            if pages:
                max_limit = 50 if cfg.get("facebook_all_pages", False) else 15
                is_url = bool(media_path and str(media_path).startswith("http"))
                res_pages = facebook_page_service.broadcast_to_all_pages(
                    pages_list=pages[:max_limit],
                    message=caption,
                    image_url=(media_path if media_type == "photo" and is_url else None),
                    image_path=(media_path if media_type == "photo" and not is_url else None),
                    video_url=(media_path if media_type == "video" and is_url else None),
                    video_path=(media_path if media_type == "video" and not is_url else None)
                )
                success_pages = sum(1 for p in res_pages if p.get("success"))
                report_lines.append(f"✅ **Facebook Pages:** ជោគជ័យ {success_pages}/{len(res_pages)} Pages ({media_desc})")
            else:
                report_lines.append("⚠️ **Facebook Pages:** គ្មាន Page សម្រាប់ផុស")

        # ---------------- 2. FACEBOOK GROUPS ----------------
        if session.get("dest_groups"):
            send_telegram_api("sendMessage", {"chat_id": chat_id, "text": "👥 [2/3] កំពុងរៀបចំ និងចម្រាញ់ Facebook Groups តាម Niche..."})
            matched_groups, niche = facebook_group_service.filter_niche_groups(caption=caption, max_groups=10)
            
            if matched_groups:
                posted_count = 0
                for g in matched_groups:
                    facebook_group_service.mark_group_posted(g.get("id"))
                    posted_count += 1
                report_lines.append(f"✅ **Facebook Groups:** បានចាត់ចែងផុសចូល {posted_count} ក្រុម (Niche: '{niche}')")
            else:
                report_lines.append("⚠️ **Facebook Groups:** ក្រុមទាំងអស់ស្ថិតក្នុង Cooldown 24h នៅឡើយ")

        # ---------------- 3. TIKTOK ----------------
        if session.get("dest_tiktok"):
            send_telegram_api("sendMessage", {"chat_id": chat_id, "text": "🎵 [3/3] កំពុងរៀបចំ Caption & Viral Hashtags សម្រាប់ TikTok..."})
            tt_payload = tiktok_service.generate_tiktok_share_payload(video_url=(str(media_path) if media_path else ""), caption=caption)
            formatted_tt_caption = tt_payload.get("caption", caption)

            tt_text = (
                "🎵 **TikTok Studio Card (មាតិការួចរាល់សម្រាប់ TikTok):**\n\n"
                "📋 **Caption & Viral Hashtags (ចុចលើប្រអប់ខាងក្រោមដើម្បី Copy ភ្លាមៗ):**\n"
                f"```\n{formatted_tt_caption}\n```\n\n"
                "👉 **របៀបផុសក្នុង TikTok (3 ជំហានងាយៗ):**\n"
                "1️⃣ ចុចលើប្រអប់ Caption ខាងលើដើម្បី Copy (1-Tap Copy)\n"
                "2️⃣ ចុចប៊ូតុង **[📱 បើក TikTok Studio Upload]** ខាងក្រោម\n"
                "3️⃣ Upload វីដេអូ ឬរូបភាព រួច Paste Caption ចូលជាការស្រេច! 🎉"
            )
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": tt_text,
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {"text": "📱 បើក TikTok Studio Upload", "url": "https://www.tiktok.com/creator-center/upload"}
                        ]
                    ]
                }
            })
            report_lines.append("✅ **TikTok:** បានរៀបចំ Caption + Viral Hashtags និងប៊ូតុង Upload រួចរាល់!")

        report_lines.append("\n🎉 **ការផ្សព្វផ្សាយត្រូវបានបញ្ចប់សព្វគ្រប់!**")
        final_report = "\n".join(report_lines)

        send_telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": final_report,
            "parse_mode": "Markdown"
        })
    except Exception as e:
        print(f"⚠️ Error executing broadcast: {e}")
        send_telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": f"⚠️ **ការផ្សព្វផ្សាយបានជួបប្រទះបញ្ហា៖**\n`{str(e)}`\n\nសូមពិនិត្យមើល និងសាកល្បងម្ដងទៀត។",
            "parse_mode": "Markdown"
        })
    finally:
        USER_SESSIONS.pop(chat_id, None)

def start_polling():
    """រត់ Bot តាម Long-Polling (សម្រាប់ Test ឬរត់លើ Desktop / Server)"""
    token = get_bot_token()
    print(f"🤖 Telegram Bot Controller is starting (Long-Polling)...")
    last_update_id = 0
    while True:
        try:
            token = get_bot_token()
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id + 1}&timeout=30"
            r = requests.get(url, timeout=40)
            if r.status_code == 200:
                data = r.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    if "message" in update:
                        handle_incoming_message(update["message"])
                    elif "callback_query" in update:
                        handle_callback_query(update["callback_query"])
        except Exception as e:
            print(f"Polling loop exception: {e}")
            time.sleep(3)

if __name__ == "__main__":
    start_polling()

