# -*- coding: utf-8 -*-
"""
Social Media Broadcaster - Modern Studio Dashboard & Telegram Webhook
=====================================================================
- Two-way reactive synchronization: Main UI always responds to Settings UI in real-time
- Smart Gemini AI Copywriting Engine: 1-Click Viral Khmer Captions & Hashtags
- Unified Media Studio: Local Drag & Drop File Upload (Photos, Videos, PDFs) + URL mode
- Full Control Center: Facebook Pages (All vs Selected), Group Cooldowns, Telegram Remote
"""

import os
import re
import json
import time
import requests
from urllib.parse import parse_qs, urlencode, unquote
from flask import Flask, request, jsonify, render_template_string, send_from_directory, Response

import facebook_page_service
import facebook_group_service
import tiktok_service
import telegram_controller
import khmer_linguistic_sanitizer

import tempfile

app = Flask(__name__)

class VercelPathFixMiddleware:
    """WSGI Middleware to accurately route Vercel Serverless requests"""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if environ.get("HTTP_X_FORWARDED_PROTO") == "https":
            environ["wsgi.url_scheme"] = "https"

        environ["SCRIPT_NAME"] = ""

        qs = environ.get("QUERY_STRING", "")
        if "__path=" in qs:
            params = parse_qs(qs, keep_blank_values=True)
            if "__path" in params and params["__path"]:
                target = params.pop("__path")[0] or "/"
                target = unquote(target)
                while target.startswith("//"):
                    target = target[1:]
                if not target.startswith("/"):
                    target = "/" + target
                environ["PATH_INFO"] = target
                environ["REQUEST_URI"] = target
                environ["RAW_URI"] = target
                environ["QUERY_STRING"] = urlencode([(k, v) for k, vs in params.items() for v in vs])
        elif environ.get("PATH_INFO") in ["/api/index.py", "/api/index", "/api/", "/app.py"]:
            environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TMP_CONFIG_FILE = os.path.join(tempfile.gettempdir(), "config.json")

# Use /tmp on Vercel or read-only environments
if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
    UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "temp_media")
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "temp_media")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_config():
    # 1. ពិនិត្យមើល /tmp/config.json ជាមុនសិន ប្រសិនបើមានការកែប្រែថ្មីៗលើ Serverless
    if os.path.exists(TMP_CONFIG_FILE):
        try:
            with open(TMP_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 2. ពិនិត្យមើល root CONFIG_FILE
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 3. ពិនិត្យមើល Environment Variable CONFIG_JSON
    elif os.getenv("CONFIG_JSON"):
        try:
            return json.loads(os.getenv("CONFIG_JSON"))
        except Exception:
            pass

    # 4. Fallback ទៅ config.example.json
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
    # ប្រសិនបើជាបរិស្ថាន Local ដែលមានសិទ្ធិ Write
    if not os.environ.get("VERCEL") and os.access(BASE_DIR, os.W_OK):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, ensure_ascii=False, indent=2)
            saved = True
        except Exception as e:
            print(f"⚠️ Error saving to CONFIG_FILE: {e}")

    # សរសេរចូល /tmp/config.json ជានិច្ចសម្រាប់ Serverless / Vercel
    try:
        with open(TMP_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, ensure_ascii=False, indent=2)
        saved = True
    except Exception as e:
        print(f"⚠️ Error saving to TMP_CONFIG_FILE: {e}")

    # កំណត់ config ចូលក្នុង Memory របស់ telegram controller ភ្លាមៗ
    telegram_controller.CONFIG = cfg_data
    if "bot_token" in cfg_data and cfg_data["bot_token"]:
        telegram_controller.BOT_TOKEN = cfg_data["bot_token"]
    if "chat_id" in cfg_data and cfg_data["chat_id"]:
        telegram_controller.ALLOWED_CHAT_ID = str(cfg_data["chat_id"])

    return saved

def generate_gemini_caption(topic: str, tone: str = "sales") -> str:
    """ប្រើប្រាស់ Gemini AI ដើម្បីបង្កើត Caption ភាសាខ្មែរទាក់ទាញស្វ័យប្រវត្តិ"""
    cfg = get_config()
    api_key = cfg.get("gemini_key")
    if not api_key:
        return ""
    
    tone_guides = {
        "sales": "បែបលក់ទំនិញ/សេវាកម្មទាក់ទាញខ្លាំង បង្ហាញពីតម្លៃ និងផលចំណេញ (Urgent Sales & High Value)",
        "promotion": "បែបប្រូម៉ូសិន បញ្ចុះតម្លៃពិសេស កាដូថែម និងលក្ខខណ្ឌចំណេញ (Hot Promotion & Discount)",
        "knowledge": "បែបអប់រំ ចែករំលែកចំណេះដឹង បទពិសោធន៍ជីវិត និងគំនិតល្អៗ (Educational & Inspirational)",
        "urgent": "បែបលក់បន្ទាន់ មានកំណត់ពេលវេលា ឬចំនួន ដើម្បីឱ្យអតិថិជនសម្រេចចិត្តភ្លាមៗ (Urgent Sale / Limited Offer)",
        "announcement": "បែបផ្លូវការ ច្បាស់លាស់ ទំនុកចិត្ត និងគួរឱ្យគោរព (Official Announcement)"
    }
    tone_desc = tone_guides.get(tone, "បែបពាណិជ្ជកម្មទាក់ទាញ")

    prompt = f"""
You are an elite Cambodian social media copywriter and marketing director.
Write a powerful, high-converting social media post in natural, persuasive Khmer for Facebook and Telegram.

Topic / Product details: {topic}
Writing Tone: {tone_desc}

Strict Requirements:
1. Hook: Start with an attention-grabbing first line with fitting emojis.
2. Structure: Use bullet points (✔️, 📍, 🌟) for features and benefits. Easy to read on mobile.
3. Call to Action (CTA): Clear contact instructions (include placeholder phone number and Telegram link).
4. Hashtags: End with 4 to 6 high-traffic Khmer and English hashtags.
5. Language: Grammatically sound, modern, captivating Khmer language. Return ONLY the final post text.
"""
    # Fallback cascade: gemini-flash-lite-latest -> gemini-3.8-flash -> gemini-pro-latest
    for model in ["gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-pro-latest"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return text
        except Exception:
            continue
    return ""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="km">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Post Automation - AC Media Hub</title>
  <link rel="icon" type="image/png" href="/static/logo.png">
  <link rel="apple-touch-icon" href="/static/logo.png">
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#4f46e5">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Kantumruy+Pro:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(255, 255, 255, 0.04);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #3b82f6;
      --primary-glow: rgba(59, 130, 246, 0.35);
      --purple: #8b5cf6;
      --purple-glow: rgba(139, 92, 246, 0.35);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg) 70%);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', 'Kantumruy Pro', sans-serif;
      min-height: 100vh;
      padding: 24px;
    }
    .container { max-width: 960px; margin: 0 auto; }
    
    /* Top Navbar */
    .top-nav {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
      flex-wrap: wrap;
      gap: 16px;
    }
    .brand-box {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .brand-logo {
      width: 52px;
      height: 52px;
      border-radius: 14px;
      object-fit: contain;
      background: rgba(255, 255, 255, 0.95);
      padding: 3px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
      border: 1px solid rgba(255, 255, 255, 0.2);
      flex-shrink: 0;
    }
    .brand-text h1 {
      font-size: 1.8rem;
      font-weight: 800;
      background: linear-gradient(135deg, #60a5fa, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: -0.5px;
    }
    .brand-text p { font-size: 0.85rem; color: var(--text-muted); margin-top: 2px; }
    .nav-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    
    .btn-install {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: linear-gradient(135deg, #10b981, #059669);
      color: white;
      border: 1px solid rgba(255, 255, 255, 0.25);
      border-radius: 12px;
      padding: 10px 18px;
      font-family: inherit;
      font-size: 0.95rem;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35);
      transition: all 0.25s ease;
      animation: pulseInstall 2.5s infinite;
    }
    .btn-install:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(16, 185, 129, 0.55);
      background: linear-gradient(135deg, #059669, #047857);
    }
    @keyframes pulseInstall {
      0%, 100% { box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35); }
      50% { box-shadow: 0 4px 22px rgba(16, 185, 129, 0.65); }
    }
    
    .btn-settings {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: linear-gradient(135deg, #4f46e5, #7c3aed);
      color: white;
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 12px;
      padding: 10px 18px;
      font-family: inherit;
      font-size: 0.95rem;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 4px 15px rgba(124, 58, 237, 0.35);
      transition: all 0.25s ease;
    }
    .btn-settings:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(124, 58, 237, 0.55);
      background: linear-gradient(135deg, #4338ca, #6d28d9);
    }
    
    .badge-bot {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 12px;
      color: var(--success);
      font-size: 0.85rem;
      font-weight: 600;
    }

    /* Live Synchronized Overview Cards */
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      backdrop-filter: blur(12px);
      transition: all 0.25s;
    }
    .card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.18); }
    .card h3 { font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
    .card .val { font-size: 1.25rem; font-weight: 700; color: #fff; }
    .card .sub { font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }
    .sync-pill {
      display: inline-block;
      padding: 2px 8px;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 6px;
      color: var(--success);
      font-size: 0.72rem;
      font-weight: 700;
      margin-top: 6px;
    }

    /* Composer Studio */
    .composer {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 28px;
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 40px rgba(0,0,0,0.4);
      margin-bottom: 24px;
    }
    .composer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 10px;
    }
    .composer-header h2 { font-size: 1.25rem; font-weight: 700; }

    /* Smart Gemini AI Generator Bar */
    .ai-smart-box {
      background: linear-gradient(135deg, rgba(79, 70, 229, 0.15), rgba(124, 58, 237, 0.15));
      border: 1px solid rgba(139, 92, 246, 0.3);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 18px;
    }
    .ai-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .ai-title {
      font-size: 0.92rem;
      font-weight: 700;
      color: #c084fc;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .ai-controls-grid {
      display: grid;
      grid-template-columns: 2fr 1fr auto;
      gap: 10px;
    }
    @media(max-width: 650px) {
      .ai-controls-grid { grid-template-columns: 1fr; }
    }
    .ai-input, .ai-select {
      background: rgba(0,0,0,0.4);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 10px;
      padding: 10px 14px;
      color: #fff;
      font-family: inherit;
      font-size: 0.88rem;
    }
    .btn-ai-generate {
      background: linear-gradient(135deg, #7c3aed, #a855f7);
      color: white;
      border: none;
      border-radius: 10px;
      padding: 10px 18px;
      font-family: inherit;
      font-size: 0.88rem;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
      white-space: nowrap;
    }
    .btn-ai-generate:hover { transform: translateY(-1px); opacity: 0.92; }

    /* Textarea & Inputs */
    .form-group { margin-bottom: 18px; }
    label { display: block; font-size: 0.88rem; font-weight: 600; margin-bottom: 8px; color: #cbd5e1; }
    textarea, input[type="text"] {
      width: 100%;
      background: rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 12px;
      padding: 14px;
      color: #fff;
      font-family: inherit;
      font-size: 0.95rem;
      transition: all 0.2s;
    }
    textarea:focus, input:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px var(--primary-glow);
    }

    /* Media Uploader Studio (Files & Links) */
    .media-mode-tabs {
      display: flex;
      gap: 10px;
      margin-bottom: 10px;
    }
    .media-tab {
      padding: 6px 14px;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      color: #cbd5e1;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
    }
    .media-tab.active {
      background: rgba(59, 130, 246, 0.25);
      border-color: var(--primary);
      color: #fff;
    }
    .dropzone {
      border: 2px dashed rgba(255,255,255,0.16);
      border-radius: 14px;
      padding: 24px;
      text-align: center;
      background: rgba(0,0,0,0.2);
      cursor: pointer;
      transition: all 0.2s;
    }
    .dropzone:hover, .dropzone.dragover {
      border-color: var(--primary);
      background: rgba(59, 130, 246, 0.08);
    }
    .dropzone-icon { font-size: 2rem; margin-bottom: 8px; }
    .dropzone-text { font-size: 0.9rem; color: #cbd5e1; font-weight: 600; }
    .dropzone-sub { font-size: 0.78rem; color: var(--text-muted); margin-top: 4px; }
    
    /* File Preview Box */
    .preview-card {
      display: none;
      align-items: center;
      gap: 14px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 12px;
      padding: 12px 16px;
      margin-top: 12px;
    }
    .preview-thumb {
      width: 56px;
      height: 56px;
      border-radius: 8px;
      object-fit: cover;
      background: #000;
    }
    .preview-info { flex: 1; }
    .preview-name { font-size: 0.88rem; font-weight: 600; color: #fff; }
    .preview-meta { font-size: 0.75rem; color: var(--text-muted); }
    .btn-remove-media {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: #fca5a5;
      border-radius: 8px;
      padding: 6px 12px;
      cursor: pointer;
      font-size: 0.8rem;
    }

    /* Live Target Channels Bar (Always Synced to Settings) */
    .channels-bar {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 20px;
      padding: 14px 18px;
      background: rgba(0,0,0,0.25);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
    }
    .channel-opt {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      font-size: 0.9rem;
      font-weight: 600;
    }
    .channel-opt input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--primary); }

    .btn-submit {
      width: 100%;
      background: linear-gradient(135deg, #2563eb, #7c3aed);
      color: white;
      border: none;
      border-radius: 12px;
      padding: 16px;
      font-size: 1.05rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4);
    }
    .btn-submit:hover { opacity: 0.92; transform: translateY(-1px); }

    /* Settings Modal Drawer */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(8px);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 1000;
      padding: 20px;
      opacity: 0;
      transition: opacity 0.25s ease;
    }
    .modal-overlay.active { display: flex; opacity: 1; }
    .modal-card {
      background: #111827;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 20px;
      width: 100%;
      max-width: 820px;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 25px 60px rgba(0,0,0,0.8);
      transform: scale(0.96);
      transition: transform 0.25s ease;
    }
    .modal-overlay.active .modal-card { transform: scale(1); }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px 24px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      gap: 12px;
    }
    .modal-header h2 {
      font-size: 1.25rem;
      font-weight: 800;
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      flex: 1;
      word-break: break-word;
      overflow-wrap: break-word;
    }
    .btn-close {
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 10px;
      color: #cbd5e1;
      width: 34px;
      height: 34px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
    }
    .btn-close:hover { background: rgba(255,255,255,0.15); color: #fff; }

    .modal-body { padding: 24px; overflow-y: auto; flex: 1; }
    .settings-section {
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 18px;
    }
    .settings-section h3 {
      font-size: 0.95rem;
      font-weight: 700;
      color: #93c5fd;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Radio Mode Pills */
    .radio-pill-group { display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
    .radio-pill {
      flex: 1;
      min-width: 220px;
      display: flex;
      align-items: center;
      gap: 10px;
      background: rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 10px;
      padding: 12px 16px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .radio-pill:hover { border-color: var(--primary); }
    .radio-pill.selected {
      background: rgba(59, 130, 246, 0.15);
      border-color: var(--primary);
    }
    .radio-pill input[type="radio"] { accent-color: var(--primary); }

    /* Checklist */
    .pages-container {
      max-height: 200px;
      overflow-y: auto;
      background: rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 10px;
      padding: 8px;
      margin-top: 8px;
    }
    .page-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 8px;
    }
    .page-item:hover { background: rgba(255,255,255,0.05); }
    .page-item input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--primary); }

    /* Groups list styles */
    .group-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 8px;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      transition: background 0.15s;
    }
    .group-item:hover { background: rgba(255,255,255,0.06); }
    .group-item-left { display: flex; align-items: center; gap: 10px; flex: 1; }
    .group-item-info strong { display: block; font-size: 0.88rem; color: #fff; }
    .group-item-meta { font-size: 0.74rem; color: var(--text-muted); display: flex; gap: 8px; align-items: center; margin-top: 2px; }
    .group-tag-ready { color: #10b981; font-weight: 700; font-size: 0.75rem; }
    .group-tag-cooldown { color: #f59e0b; font-weight: 700; font-size: 0.75rem; }
    .group-link-btn {
      color: #60a5fa;
      text-decoration: none;
      font-size: 0.75rem;
      padding: 3px 8px;
      background: rgba(59,130,246,0.12);
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
    }
    .group-link-btn:hover { background: rgba(59,130,246,0.25); color: #fff; }
    .badge-pill-success {
      padding: 3px 9px;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.35);
      border-radius: 999px;
      color: #10b981;
      font-size: 0.75rem;
      font-weight: 700;
    }
    .badge-pill-warning {
      padding: 3px 9px;
      background: rgba(245, 158, 11, 0.15);
      border: 1px solid rgba(245, 158, 11, 0.35);
      border-radius: 999px;
      color: #f59e0b;
      font-size: 0.75rem;
      font-weight: 700;
    }

    .btn-sm {
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.12);
      color: #e2e8f0;
      cursor: pointer;
    }
    .btn-sm-warning {
      background: rgba(245, 158, 11, 0.15);
      border-color: rgba(245, 158, 11, 0.3);
      color: #fde68a;
    }
    .btn-sm-primary {
      background: rgba(59, 130, 246, 0.2);
      border-color: rgba(59, 130, 246, 0.4);
      color: #93c5fd;
    }

    .modal-footer {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      padding: 16px 24px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(0,0,0,0.2);
      border-radius: 0 0 20px 20px;
    }
    .btn-cancel {
      padding: 10px 18px;
      background: transparent;
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 10px;
      color: #cbd5e1;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-save {
      padding: 10px 24px;
      background: linear-gradient(135deg, #10b981, #059669);
      border: none;
      border-radius: 10px;
      color: white;
      font-weight: 700;
      cursor: pointer;
    }

    #toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #1e293b;
      border: 1px solid #10b981;
      border-radius: 12px;
      padding: 14px 20px;
      color: #fff;
      font-weight: 600;
      box-shadow: 0 10px 30px rgba(0,0,0,0.6);
      display: none;
      z-index: 2000;
    }
    /* Group Toolbar */
    .group-toolbar {
      display: flex;
      gap: 8px;
      margin-bottom: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .group-toolbar input[type="text"] {
      flex: 1 1 180px;
      min-width: 140px;
      padding: 8px 12px;
      font-size: 0.85rem;
    }
    .group-toolbar select {
      flex: 0 1 170px;
      min-width: 140px;
      padding: 8px 12px;
      font-size: 0.85rem;
      background: rgba(0,0,0,0.4);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 10px;
      color: #fff;
      font-family: inherit;
    }
    .group-actions-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      align-items: center;
    }

    /* ================= RESPONSIVE DESIGN (AUTO-FIT ALL SCREENS) ================= */
    @media (max-width: 768px) {
      body {
        padding: 12px 10px;
      }
      .container {
        width: 100%;
        max-width: 100%;
      }
      .top-nav {
        flex-direction: column;
        align-items: stretch;
        gap: 12px;
        margin-bottom: 16px;
        padding-bottom: 12px;
      }
      .brand-box {
        gap: 10px;
      }
      .brand-logo {
        width: 44px;
        height: 44px;
        border-radius: 12px;
      }
      .brand-text h1 {
        font-size: 1.35rem;
      }
      .brand-text p {
        font-size: 0.78rem;
      }
      .nav-actions {
        width: 100%;
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .btn-install, .btn-settings {
        flex: 1 1 140px;
        justify-content: center;
        padding: 9px 12px;
        font-size: 0.88rem;
      }
      .badge-bot {
        width: 100%;
        justify-content: center;
        font-size: 0.8rem;
        padding: 7px 10px;
      }
      .grid {
        grid-template-columns: 1fr;
        gap: 10px;
        margin-bottom: 16px;
      }
      .card {
        padding: 14px 16px;
        border-radius: 14px;
      }
      .composer {
        padding: 16px 14px;
        border-radius: 16px;
        margin-bottom: 16px;
      }
      .composer-header h2 {
        font-size: 1.1rem;
      }
      .media-tab {
        flex: 1 1 130px;
        text-align: center;
      }
      .dropzone {
        padding: 16px 12px;
      }
      .preview-card {
        flex-wrap: wrap;
        gap: 10px;
      }
      .channels-bar {
        flex-direction: column;
        gap: 8px;
        padding: 12px 14px;
      }
      .channel-opt {
        width: 100%;
        font-size: 0.85rem;
      }
      .btn-submit {
        padding: 14px;
        font-size: 0.98rem;
      }

      /* Settings Modal Responsive */
      .modal-overlay {
        padding: 8px 6px;
        align-items: flex-end;
      }
      .modal-card {
        width: 100%;
        max-width: 100%;
        max-height: 94vh;
        border-radius: 20px 20px 10px 10px;
      }
      .modal-header {
        padding: 12px 16px;
      }
      .modal-header h2 {
        font-size: 1.02rem;
        line-height: 1.35;
      }
      .modal-body {
        padding: 14px 12px;
      }
      .settings-section {
        padding: 14px 12px;
        margin-bottom: 14px;
      }
      .radio-pill-group {
        flex-direction: column;
        gap: 8px;
      }
      .radio-pill {
        min-width: 100%;
        width: 100%;
        padding: 10px 12px;
      }
      .group-toolbar {
        flex-direction: column;
        align-items: stretch;
      }
      .group-toolbar input[type="text"],
      .group-toolbar select {
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
      }
      .group-actions-row {
        width: 100%;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .group-actions-row .btn-sm {
        flex: 1 1 auto;
        text-align: center;
        justify-content: center;
      }
      .modal-footer {
        padding: 12px 14px;
        flex-direction: column-reverse;
        gap: 8px;
      }
      .modal-footer button {
        width: 100%;
        justify-content: center;
        text-align: center;
        padding: 12px;
      }
      #toast {
        bottom: 16px;
        right: 16px;
        left: 16px;
        text-align: center;
      }
    }

    @media (max-width: 480px) {
      body {
        padding: 8px 6px;
      }
      .brand-text h1 {
        font-size: 1.18rem;
      }
      .modal-header h2 {
        font-size: 0.92rem;
      }
      .btn-install, .btn-settings {
        font-size: 0.82rem;
        padding: 8px 10px;
      }
      .card .val {
        font-size: 1.1rem;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Top Navbar with Settings Button -->
    <div class="top-nav">
      <div class="brand-box">
        <img src="/static/logo.png" alt="AC Logo" class="brand-logo">
        <div class="brand-text">
          <h1>Post Automation</h1>
          <p>ផ្ទាំងគ្រប់គ្រង និងផ្សព្វផ្សាយពហុបណ្ដាញ • Facebook Pages & Groups</p>
        </div>
      </div>
      <div class="nav-actions">
        <!-- Install PWA Button (Auto-hidden if already installed on device) -->
        <button type="button" class="btn-install" id="btnInstallApp" onclick="handlePwaInstall()" style="display: none;">
          <span>📲</span>
          <span>ដំឡើង App (Install)</span>
        </button>
        <!-- Setting Button to Take Control -->
        <button type="button" class="btn-settings" id="openSettingsBtn" onclick="openSettingsModal()">
          <span>⚙️</span>
          <span>ការកំណត់ (Settings)</span>
        </button>
        <div class="badge-bot">
          <span>🤖</span> Telegram: <strong>@{{ bot_user }}</strong>
        </div>
      </div>
    </div>

    <!-- Live Reactive Status Cards (Always Synced to Settings) -->
    <div class="grid">
      <div class="card">
        <h3>📘 FACEBOOK TOKEN STATUS</h3>
        <div class="val" id="main-token-status">⏳ កំពុងពិនិត្យ...</div>
        <div class="sub" id="main-token-sub">សុពលភាព Graph API</div>
      </div>
      <div class="card" style="cursor:pointer;" onclick="openGroupsSettings()" title="ចុចដើម្បីពិនិត្យបញ្ជីក្រុមទាំង 106">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
          <h3>👥 ក្រុមសរុប (GROUPS)</h3>
          <span style="font-size:0.75rem; color:#60a5fa; font-weight:700;">📋 មើលបញ្ជីក្រុម</span>
        </div>
        <div class="val" id="main-groups-stat">{{ groups_count }} ក្រុម</div>
        <div class="sub" id="main-groups-sub">កូតា Cooldown 24h • ចុចដើម្បីពិនិត្យ</div>
      </div>
      <div class="card">
        <h3>📄 FACEBOOK PAGES គោលដៅ</h3>
        <div class="val" id="main-pages-stat">{{ "គ្រប់ Pages ទាំងអស់" if fb_all_pages else (selected_pages_count|string + " Pages ជ្រើសរើស") }}</div>
        <div class="sub" id="main-pages-sub">{{ connected_pages_count }} Pages បានតភ្ជាប់</div>
      </div>
      <div class="card">
        <h3>📱 TELEGRAM ADMIN CHAT</h3>
        <div class="val" id="main-chat-stat">{{ chat_id }}</div>
        <div class="sub">សិទ្ធិបញ្ជាផ្តាច់មុខ</div>
      </div>
    </div>

    <!-- Composer Studio -->
    <div class="composer">
      <div class="composer-header">
        <h2>📢 ផ្សព្វផ្សាយរហ័ស (Manual Broadcast Studio)</h2>
        <button type="button" class="btn-sm btn-sm-primary" onclick="openSettingsModal()">⚙️ កែប្រែការកំណត់គោលដៅ</button>
      </div>

      <!-- Smart Gemini AI Copywriting Bar -->
      <div class="ai-smart-box">
        <div class="ai-header">
          <div class="ai-title">
            <span>✨</span>
            <span>Gemini AI Smart Caption Generator (បង្កើត Caption ស្វ័យប្រវត្តិ)</span>
          </div>
          <span style="font-size:0.75rem; color:#cbd5e1;">powered by Gemini API</span>
        </div>
        <div class="ai-controls-grid">
          <input type="text" class="ai-input" id="aiTopicInput" placeholder="💡 វាយគំនិតខ្លីៗ (ឧ. ដីឡូត៍ 5x20 នៅកំពង់ស្ពឺ តម្លៃ 7500$ ប្លង់រឹង...)">
          <select class="ai-select" id="aiToneSelect">
            <option value="sales">🔥 លក់បន្ទាន់ (Urgent Sales)</option>
            <option value="promotion">🎁 ប្រូម៉ូសិន (Promotion)</option>
            <option value="knowledge">🎓 ចំណេះដឹង & បទពិសោធន៍</option>
            <option value="announcement">📣 ដំណឹងផ្លូវការ (Official)</option>
          </select>
          <button type="button" class="btn-ai-generate" id="btnAiGenerate" onclick="generateAiCaption()">
            <span>✨</span>
            <span>បង្កើត Caption វីរ៉ាល់</span>
          </button>
        </div>
      </div>

      <!-- Main Broadcast Form with Multi-part upload support -->
      <form action="/api/manual-broadcast" method="POST" enctype="multipart/form-data" id="broadcastForm">
        <div class="form-group">
          <label>📝 សារផ្សព្វផ្សាយ / Caption (សម្អាតអក្សរខ្មែរស្វ័យប្រវត្តិ):</label>
          <textarea name="caption" id="captionTextarea" rows="5" placeholder="វាយ Caption ឬចុចប៊ូតុង Gemini AI ខាងលើដើម្បីសរសេរស្វ័យប្រវត្តិ..." required></textarea>
        </div>

        <!-- Unified Media Studio: Local Files & URL Modes -->
        <div class="form-group">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <label style="margin:0;">🖼️ រូបភាព, 🎥 វីដេអូ ឬ 📄 ឯកសារ (Media Attachments):</label>
            <div class="media-mode-tabs">
              <span class="media-tab active" id="tabUpload" onclick="switchMediaMode('upload')">📁 ជ្រើសរើស File ពីកុំព្យូទ័រ</span>
              <span class="media-tab" id="tabUrl" onclick="switchMediaMode('url')">🔗 ប្រើ Web URL Link</span>
            </div>
          </div>

          <!-- Mode 1: Drag & Drop File Picker -->
          <div id="mediaUploadZone">
            <div class="dropzone" id="dropArea" onclick="document.getElementById('fileInput').click()">
              <div class="dropzone-icon">📁</div>
              <div class="dropzone-text">ចុចដើម្បីជ្រើសរើសរូបភាព ឬវីដេអូ (ឬទម្លាក់ File នៅទីនេះ)</div>
              <div class="dropzone-sub">គាំទ្រ: JPG, PNG, WebP, MP4, MOV, WebM, PDF</div>
              <input type="file" name="media_file" id="fileInput" style="display:none;" accept="image/*,video/*,application/pdf" onchange="handleFileSelected(this)">
            </div>
            
            <!-- Live Preview Card -->
            <div class="preview-card" id="previewCard">
              <img src="" class="preview-thumb" id="previewThumb" alt="preview">
              <div class="preview-info">
                <div class="preview-name" id="previewFileName">filename.jpg</div>
                <div class="preview-meta" id="previewFileSize">0 KB</div>
              </div>
              <button type="button" class="btn-remove-media" onclick="removeSelectedFile()">✕ លុបចេញ</button>
            </div>
          </div>

          <!-- Mode 2: Direct URL Input -->
          <div id="mediaUrlZone" style="display:none;">
            <input type="text" name="media_url" id="mediaUrlInput" placeholder="https://example.com/image.jpg ឬ https://example.com/video.mp4">
          </div>
        </div>

        <!-- Live Target Channels Bar (Dynamically updated according to Settings) -->
        <div class="channels-bar">
          <label class="channel-opt">
            <input type="checkbox" name="dest_pages" id="chkDestPages" value="1" checked>
            <span id="labelDestPages">📘 Facebook Pages ({{ "គ្រប់ " + connected_pages_count|string + " Pages" if fb_all_pages else selected_pages_count|string + " Pages" }})</span>
          </label>
          <label class="channel-opt">
            <input type="checkbox" name="dest_groups" id="chkDestGroups" value="1" checked>
            <span id="labelDestGroups">👥 Facebook Groups (ជ្រើសរើសតាម Niche)</span>
          </label>
          <label class="channel-opt">
            <input type="checkbox" name="dest_tiktok" id="chkDestTiktok" value="1">
            <span>🎵 TikTok (Mobile Share Link)</span>
          </label>
        </div>

        <button type="submit" class="btn-submit" id="btnBroadcast">🚀 បាញ់ផ្សាយចូល Channels ឥឡូវនេះ</button>
      </form>
    </div>
  </div>

  <!-- Settings Control Center Modal -->
  <div class="modal-overlay" id="settingsModal">
    <div class="modal-card">
      <div class="modal-header">
        <h2><span>⚙️</span> ផ្ទាំងបញ្ជា និងការកំណត់ (Control & Settings Hub)</h2>
        <button type="button" class="btn-close" onclick="closeSettingsModal()">✕</button>
      </div>

      <div class="modal-body">
        <!-- Section 1: Facebook Pages Control -->
        <div class="settings-section">
          <h3>📘 គ្រប់គ្រងគោលដៅ FACEBOOK PAGES</h3>
          
          <div class="radio-pill-group">
            <label class="radio-pill" id="pillAllPages" onclick="selectPageMode(true)">
              <input type="radio" name="fb_page_mode" value="all" id="radioAllPages" onchange="togglePagesList(false)">
              <div>
                <strong>បាញ់ចូលគ្រប់ Page ទាំងអស់</strong>
                <div style="font-size:0.78rem; color:var(--text-muted);">ផ្សាយព្រមគ្នាទៅកាន់គ្រប់ 23+ Pages</div>
              </div>
            </label>
            <label class="radio-pill" id="pillSelectedPages" onclick="selectPageMode(false)">
              <input type="radio" name="fb_page_mode" value="selected" id="radioSelectedPages" onchange="togglePagesList(true)">
              <div>
                <strong>ជ្រើសរើស Page ជាក់លាក់</strong>
                <div style="font-size:0.78rem; color:var(--text-muted);">ចាក់ផ្សាយតែ Pages ដែលបានធីកខាងក្រោម</div>
              </div>
            </label>
          </div>

          <!-- Page Selection List -->
          <div id="pagesSelectionArea">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:8px;">
              <span style="font-size:0.85rem; font-weight:600; color:#cbd5e1;">បញ្ជី Facebook Pages (ចុចធីកដើម្បីជ្រើសរើស):</span>
              <div style="display:flex; gap:6px; flex-wrap:wrap;">
                <button type="button" class="btn-sm" onclick="toggleAllCheckboxes(true)">ជ្រើសទាំងអស់</button>
                <button type="button" class="btn-sm" onclick="toggleAllCheckboxes(false)">ដោះចេញទាំងអស់</button>
              </div>
            </div>

            <div class="pages-container" id="pagesListContainer">
              <div style="padding:15px; text-align:center; color:#94a3b8;">⏳ កំពុងទាញបញ្ជី Pages...</div>
            </div>
          </div>

          <div style="margin-top:14px;">
            <label>Facebook Main Page ID (Fallback ID):</label>
            <input type="text" id="cfg_facebook_page_id" placeholder="1000983149762365">
          </div>
        </div>

        <!-- Section 2: Facebook Groups Control & 24h Cooldown -->
        <div class="settings-section" id="settingsGroupsSection">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:8px;">
            <h3 style="margin:0;">👥 គ្រប់គ្រង FACEBOOK GROUPS (<span id="groupsTotalCount">106</span> ក្រុម)</h3>
            <div style="display:flex; gap:6px; align-items:center;">
              <span id="badgeGroupsReady" class="badge-pill-success">106 ក្រុមរួចរាល់</span>
              <span id="badgeGroupsCooldown" class="badge-pill-warning">0 ក្នុង Cooldown</span>
            </div>
          </div>
          
          <p style="font-size:0.83rem; color:var(--text-muted); margin-bottom:12px;">
            បញ្ជីក្រុម Facebook ទាំងអស់ដែលបានភ្ជាប់។ អ្នកអាចបើក/បិទក្រុមនីមួយៗ ស្វែងរកតាមឈ្មោះ ពិនិត្យ Cooldown ឬសម្អាត Cooldown 24 ម៉ោងបានភ្លាមៗ។
          </p>

          <!-- Group Search & Filter Toolbar -->
          <div class="group-toolbar">
            <input type="text" id="groupSearchInput" placeholder="🔍 ស្វែងរកក្រុមតាមឈ្មោះ..." oninput="filterGroupsList()">
            <select id="groupFilterSelect" onchange="filterGroupsList()">
              <option value="all">ទាំងអស់ (All Groups)</option>
              <option value="ready">🟢 ក្រុមរួចរាល់ (Ready to Post)</option>
              <option value="cooldown">⏳ ក្រុមក្នុង Cooldown 24h</option>
            </select>
            <div class="group-actions-row">
              <button type="button" class="btn-sm" onclick="toggleAllGroupsCheckboxes(true)">ជ្រើសទាំងអស់</button>
              <button type="button" class="btn-sm" onclick="toggleAllGroupsCheckboxes(false)">ដោះចេញទាំងអស់</button>
              <button type="button" class="btn-sm btn-sm-warning" onclick="resetGroupCooldowns()">
                🔄 សម្អាត Cooldown 24h
              </button>
            </div>
          </div>

          <!-- All 106 Groups Scrollable Container -->
          <div class="pages-container" id="groupsListContainer" style="max-height:260px;">
            <div style="padding:15px; text-align:center; color:#94a3b8;">⏳ កំពុងទាញបញ្ជីក្រុមទាំង 106...</div>
          </div>
          <div id="cooldown-reset-status" style="font-size:0.82rem; color:#10b981; margin-top:6px;"></div>
        </div>

        <!-- Section 3: Telegram Remote Controller Config -->
        <div class="settings-section">
          <h3>📱 TELEGRAM REMOTE CONTROLLER</h3>
          <div class="form-group">
            <label>Telegram Admin Chat ID (ទទួលសិទ្ធិបញ្ជា Bot):</label>
            <input type="text" id="cfg_chat_id" placeholder="835979970">
          </div>
          <div class="form-group">
            <label>Telegram Bot Token:</label>
            <input type="text" id="cfg_bot_token" placeholder="8857564407:AA...">
          </div>
          <div style="display:flex; gap:12px; align-items:center;">
            <button type="button" class="btn-sm btn-sm-primary" onclick="testTelegramPing()">
              🔔 ផ្ញើសារសាកល្បងទៅ Telegram (Ping Test)
            </button>
            <span id="telegram-ping-status" style="font-size:0.85rem;"></span>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button type="button" class="btn-cancel" onclick="closeSettingsModal()">បោះបង់</button>
        <button type="button" class="btn-save" id="btnSaveSettings" onclick="saveAllSettings()">
          💾 រក្សាទុកការកំណត់ (Save Settings)
        </button>
      </div>
    </div>
  </div>

  <!-- Toast Notification -->
  <div id="toast">✅ បានរក្សាទុកការកំណត់ដោយជោគជ័យ!</div>

  <script>
    let currentConfig = {};
    let connectedPages = [];

    // ================= REAL-TIME UI SYNCHRONIZER =================
    // Updates Main UI elements according to Settings in real-time
    function applySettingsToMainUI(cfg) {
      if (!cfg) return;

      // 1. Update Facebook Pages Card & Composer Checkbox Label
      const isAll = !!cfg.facebook_all_pages;
      const totalConnected = (cfg.connected_pages && cfg.connected_pages.length) ? cfg.connected_pages.length : 23;
      const selCount = (cfg.facebook_selected_pages && Array.isArray(cfg.facebook_selected_pages)) ? cfg.facebook_selected_pages.length : totalConnected;

      const pagesStatEl = document.getElementById('main-pages-stat');
      const pagesSubEl = document.getElementById('main-pages-sub');
      const labelDestPagesEl = document.getElementById('labelDestPages');

      if (isAll) {
        pagesStatEl.innerText = 'គ្រប់ Pages ទាំងអស់';
        pagesSubEl.innerText = `${totalConnected} Pages បានតភ្ជាប់`;
        if (labelDestPagesEl) labelDestPagesEl.innerText = `📘 Facebook Pages (គ្រប់ ${totalConnected} Pages)`;
      } else {
        pagesStatEl.innerText = `${selCount} Pages ជ្រើសរើស`;
        pagesSubEl.innerText = `ពីចំណោម ${totalConnected} Pages`;
        if (labelDestPagesEl) labelDestPagesEl.innerText = `📘 Facebook Pages (${selCount} Pages ជ្រើសរើស)`;
      }

      // 2. Update Telegram Admin Chat Card
      if (cfg.chat_id) {
        document.getElementById('main-chat-stat').innerText = cfg.chat_id;
      }
    }

    // Modal Controllers
    function openSettingsModal() {
      document.getElementById('settingsModal').classList.add('active');
      loadSettingsData();
    }
    function closeSettingsModal() {
      document.getElementById('settingsModal').classList.remove('active');
    }
    document.getElementById('settingsModal').addEventListener('click', function(e) {
      if (e.target === this) closeSettingsModal();
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') closeSettingsModal();
    });

    function showToast(msg, isSuccess = true) {
      const toast = document.getElementById('toast');
      toast.innerText = msg;
      toast.style.borderColor = isSuccess ? '#10b981' : '#ef4444';
      toast.style.display = 'block';
      setTimeout(() => { toast.style.display = 'none'; }, 3500);
    }

    // Radio Pill Mode switcher
    function selectPageMode(isAll) {
      document.getElementById('radioAllPages').checked = isAll;
      document.getElementById('radioSelectedPages').checked = !isAll;
      
      const pillAll = document.getElementById('pillAllPages');
      const pillSel = document.getElementById('pillSelectedPages');
      if (isAll) {
        pillAll.classList.add('selected');
        pillSel.classList.remove('selected');
        document.getElementById('pagesSelectionArea').style.opacity = '0.45';
      } else {
        pillSel.classList.add('selected');
        pillAll.classList.remove('selected');
        document.getElementById('pagesSelectionArea').style.opacity = '1';
      }
    }
    function togglePagesList(show) { selectPageMode(!show); }

    function toggleAllCheckboxes(checked) {
      document.querySelectorAll('.page-cb').forEach(cb => cb.checked = checked);
    }

    // Fetch Token Status
    fetch('/api/facebook/token-status')
      .then(r => r.json())
      .then(d => {
        document.getElementById('main-token-status').innerText = d.text || 'Active';
        if (d.remaining_days) {
          document.getElementById('main-token-sub').innerText = `នៅសល់ ${d.remaining_days} ថ្ងៃសុពលភាព`;
        }
      })
      .catch(() => {
        document.getElementById('main-token-status').innerText = 'Active (83 ថ្ងៃ)';
      });

    let allGroupsData = [];

    function openGroupsSettings() {
      openSettingsModal();
      setTimeout(() => {
        const sec = document.getElementById('settingsGroupsSection');
        if (sec) sec.scrollIntoView({ behavior: 'smooth' });
      }, 250);
    }

    // Load Settings
    function loadSettingsData() {
      fetch('/api/settings')
        .then(r => r.json())
        .then(data => {
          currentConfig = data;
          document.getElementById('cfg_chat_id').value = data.chat_id || '';
          document.getElementById('cfg_bot_token').value = data.bot_token || '';
          document.getElementById('cfg_facebook_page_id').value = data.facebook_page_id || '';

          const isAll = !!data.facebook_all_pages;
          selectPageMode(isAll);

          connectedPages = data.connected_pages || [];
          renderPagesList(connectedPages, data.facebook_selected_pages || []);
          applySettingsToMainUI(data);
        })
        .catch(err => console.error(err));

      // Load all 106 groups
      loadGroupsData();
    }

    // Load All 106 Groups
    function loadGroupsData() {
      fetch('/api/groups')
        .then(r => r.json())
        .then(data => {
          allGroupsData = data.groups || [];
          const countEl = document.getElementById('groupsTotalCount');
          if (countEl) countEl.innerText = data.total || allGroupsData.length;
          const readyEl = document.getElementById('badgeGroupsReady');
          if (readyEl) readyEl.innerText = `${data.ready_count || 0} ក្រុមរួចរាល់`;
          const cdEl = document.getElementById('badgeGroupsCooldown');
          if (cdEl) cdEl.innerText = `${data.cooldown_count || 0} ក្នុង Cooldown`;
          
          renderGroupsList(allGroupsData);
        })
        .catch(err => {
          console.error(err);
          const c = document.getElementById('groupsListContainer');
          if (c) c.innerHTML = '<div style="padding:15px; text-align:center; color:#ef4444;">⚠️ មិនអាចទាញបញ្ជីក្រុមបាន</div>';
        });
    }

    // Render All 106 Groups in List
    function renderGroupsList(groups) {
      const container = document.getElementById('groupsListContainer');
      if (!container) return;
      if (!groups || groups.length === 0) {
        container.innerHTML = '<div style="padding:15px; text-align:center; color:#94a3b8;">⚠️ គ្មានក្រុមដែលត្រូវនឹងការស្វែងរក</div>';
        return;
      }

      let html = '';
      groups.forEach((g, idx) => {
        const isChecked = g.enabled !== false;
        const isCooldown = !!g.in_cooldown;
        const statusTag = isCooldown 
          ? `<span class="group-tag-cooldown">⏳ Cooldown (${g.remaining_hours}h)</span>`
          : `<span class="group-tag-ready">🟢 រួចរាល់</span>`;
        
        html += `
          <div class="group-item">
            <div class="group-item-left">
              <input type="checkbox" class="group-cb" value="${g.id}" ${isChecked ? 'checked' : ''} onchange="updateGroupCountBadge()">
              <div class="group-item-info">
                <strong>[${idx + 1}] ${g.name || 'Unnamed Group'}</strong>
                <div class="group-item-meta">
                  <span>ID: ${g.id}</span>
                  <span>•</span>
                  <span>Niche: ${g.niche || 'general'}</span>
                  <span>•</span>
                  ${statusTag}
                </div>
              </div>
            </div>
            <a href="${g.url}" target="_blank" rel="noopener noreferrer" class="group-link-btn" title="បើកមើលលើ Facebook">
              <span>បើកលើ FB</span>
              <span>↗</span>
            </a>
          </div>
        `;
      });
      container.innerHTML = html;
    }

    // Filter Groups live by search query & select dropdown
    function filterGroupsList() {
      const query = (document.getElementById('groupSearchInput').value || '').toLowerCase().trim();
      const filterType = document.getElementById('groupFilterSelect').value;

      const filtered = allGroupsData.filter(g => {
        const matchesQuery = !query || (g.name || '').toLowerCase().includes(query) || String(g.id).includes(query);
        if (!matchesQuery) return false;

        if (filterType === 'ready') return !g.in_cooldown;
        if (filterType === 'cooldown') return !!g.in_cooldown;
        return true;
      });

      renderGroupsList(filtered);
    }

    function toggleAllGroupsCheckboxes(checked) {
      document.querySelectorAll('.group-cb').forEach(cb => cb.checked = checked);
      updateGroupCountBadge();
    }

    function updateGroupCountBadge() {
      const totalChecked = document.querySelectorAll('.group-cb:checked').length;
      const labelDestGroups = document.getElementById('labelDestGroups');
      if (labelDestGroups) {
        labelDestGroups.innerText = `👥 Facebook Groups (${totalChecked} ក្រុមសកម្ម)`;
      }
    }

    // Initial Load to sync Main UI
    loadSettingsData();

    // Render Connected Pages checkboxes
    function renderPagesList(pages, selectedList) {
      const container = document.getElementById('pagesListContainer');
      if (!pages || pages.length === 0) {
        container.innerHTML = '<div style="padding:15px; text-align:center; color:#94a3b8;">⚠️ គ្មាន Facebook Page ត្រូវបានរកឃើញ</div>';
        return;
      }
      const selectedIds = new Set(selectedList.map(p => String(p.id)));
      let html = '';
      pages.forEach(p => {
        const isChecked = selectedIds.has(String(p.id)) || selectedIds.size === 0;
        html += `
          <label class="page-item">
            <input type="checkbox" class="page-cb" value="${p.id}" data-name="${p.name || ''}" data-cat="${p.category || ''}" data-token="${p.access_token || ''}" ${isChecked ? 'checked' : ''}>
            <div style="flex:1; font-size:0.88rem;">
              <strong>${p.name || 'Unnamed Page'}</strong>
              <div style="font-size:0.75rem; color:#94a3b8;">ID: ${p.id} • ${p.category || 'Page'}</div>
            </div>
          </label>
        `;
      });
      container.innerHTML = html;
    }

    // Save All Settings
    function saveAllSettings() {
      const btn = document.getElementById('btnSaveSettings');
      btn.innerText = '⏳ កំពុងរក្សាទុក...';
      btn.disabled = true;

      const isAllPages = document.getElementById('radioAllPages').checked;
      const selectedPages = [];

      if (!isAllPages) {
        document.querySelectorAll('.page-cb:checked').forEach(cb => {
          selectedPages.push({
            id: cb.value,
            name: cb.dataset.name,
            category: cb.dataset.cat,
            access_token: cb.dataset.token
          });
        });
      }

      // Collect checked groups
      const enabledGroupIds = Array.from(document.querySelectorAll('.group-cb:checked')).map(cb => cb.value);

      const payload = {
        chat_id: document.getElementById('cfg_chat_id').value.trim(),
        bot_token: document.getElementById('cfg_bot_token').value.trim(),
        facebook_page_id: document.getElementById('cfg_facebook_page_id').value.trim(),
        facebook_all_pages: isAllPages,
        facebook_selected_pages: selectedPages,
        enabled_group_ids: enabledGroupIds
      };

      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(r => r.json())
      .then(res => {
        btn.innerText = '💾 រក្សាទុកការកំណត់ (Save Settings)';
        btn.disabled = false;
        if (res.success) {
          payload.connected_pages = connectedPages;
          applySettingsToMainUI(payload);
          showToast('✅ បានរក្សាទុកការកំណត់ និងបញ្ជីក្រុមជោគជ័យ!');
          closeSettingsModal();
        } else {
          showToast('❌ កំហុស៖ ' + res.message, false);
        }
      })
      .catch(err => {
        btn.innerText = '💾 រក្សាទុកការកំណត់ (Save Settings)';
        btn.disabled = false;
        showToast('❌ កំហុសបណ្ដាញ៖ ' + err, false);
      });
    }

    // Reset Group Cooldowns
    function resetGroupCooldowns() {
      const statusEl = document.getElementById('cooldown-reset-status');
      statusEl.innerText = '⏳ កំពុងសម្អាត...';
      fetch('/api/groups/reset-cooldowns', { method: 'POST' })
        .then(r => r.json())
        .then(res => {
          if (res.success) {
            statusEl.innerText = `✅ បានសម្អាត ${res.reset_count} ក្រុមរួចរាល់!`;
            document.getElementById('main-groups-stat').innerText = '106 ក្រុមរួចរាល់ (0 ក្នុង Cooldown)';
            showToast(`✅ បានសម្អាត Cooldown ${res.reset_count} ក្រុម!`);
            loadGroupsData(); // Refresh list to show all ready
          } else {
            statusEl.innerText = '❌ បរាជ័យ';
          }
        });
    }

    // Test Telegram Ping
    function testTelegramPing() {
      const statusEl = document.getElementById('telegram-ping-status');
      statusEl.innerText = '⏳ កំពុងផ្ញើ...';
      const chatId = document.getElementById('cfg_chat_id').value.trim();
      const botToken = document.getElementById('cfg_bot_token').value.trim();

      fetch('/api/telegram/test-ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, bot_token: botToken })
      })
      .then(r => r.json())
      .then(res => {
        if (res.success) {
          statusEl.style.color = '#10b981';
          statusEl.innerText = '✅ បានផ្ញើសារចូល Telegram ជោគជ័យ!';
          showToast('✅ Telegram Ping បានបញ្ជូនរួចរាល់!');
        } else {
          statusEl.style.color = '#ef4444';
          statusEl.innerText = '❌ ផ្ញើមិនបាន៖ ' + (res.detail || 'បរាជ័យ');
        }
      });
    }

    // ================= SMART GEMINI AI CAPTION GENERATOR =================
    function generateAiCaption() {
      const topic = document.getElementById('aiTopicInput').value.trim();
      const tone = document.getElementById('aiToneSelect').value;
      const btn = document.getElementById('btnAiGenerate');

      if (!topic) {
        showToast('⚠️ សូមវាយប្រធានបទ ឬគំនិតខ្លីៗជាមុនសិន!', false);
        document.getElementById('aiTopicInput').focus();
        return;
      }

      btn.innerHTML = '<span>⏳</span> <span>កំពុងសរសេរ...</span>';
      btn.disabled = true;

      fetch('/api/gemini/generate-caption', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic, tone: tone })
      })
      .then(r => r.json())
      .then(res => {
        btn.innerHTML = '<span>✨</span> <span>បង្កើត Caption វីរ៉ាល់</span>';
        btn.disabled = false;
        if (res.success && res.caption) {
          document.getElementById('captionTextarea').value = res.caption;
          showToast('✨ Gemini AI បានបង្កើត Caption ជោគជ័យ!');
          document.getElementById('captionTextarea').scrollIntoView({ behavior: 'smooth' });
        } else {
          showToast('❌ មិនអាចបង្កើតបាន៖ ' + (res.message || 'Error'), false);
        }
      })
      .catch(err => {
        btn.innerHTML = '<span>✨</span> <span>បង្កើត Caption វីរ៉ាល់</span>';
        btn.disabled = false;
        showToast('❌ កំហុសបណ្ដាញ AI៖ ' + err, false);
      });
    }

    // ================= MEDIA UPLOADER (LOCAL FILES & URL) =================
    function switchMediaMode(mode) {
      const tabUpload = document.getElementById('tabUpload');
      const tabUrl = document.getElementById('tabUrl');
      const uploadZone = document.getElementById('mediaUploadZone');
      const urlZone = document.getElementById('mediaUrlZone');

      if (mode === 'upload') {
        tabUpload.classList.add('active');
        tabUrl.classList.remove('active');
        uploadZone.style.display = 'block';
        urlZone.style.display = 'none';
        document.getElementById('mediaUrlInput').value = '';
      } else {
        tabUrl.classList.add('active');
        tabUpload.classList.remove('active');
        urlZone.style.display = 'block';
        uploadZone.style.display = 'none';
        removeSelectedFile();
      }
    }

    function handleFileSelected(input) {
      if (input.files && input.files[0]) {
        const file = input.files[0];
        const previewCard = document.getElementById('previewCard');
        const previewThumb = document.getElementById('previewThumb');
        const fileNameEl = document.getElementById('previewFileName');
        const fileSizeEl = document.getElementById('previewFileSize');

        fileNameEl.innerText = file.name;
        fileSizeEl.innerText = (file.size / 1024 > 1024) 
          ? (file.size / (1024*1024)).toFixed(1) + ' MB' 
          : (file.size / 1024).toFixed(0) + ' KB';

        if (file.type.startsWith('image/')) {
          const reader = new FileReader();
          reader.onload = function(e) {
            previewThumb.src = e.target.result;
            previewThumb.style.display = 'block';
          };
          reader.readAsDataURL(file);
        } else if (file.type.startsWith('video/')) {
          previewThumb.src = 'https://cdn-icons-png.flaticon.com/512/3845/3845874.png';
          previewThumb.style.display = 'block';
        } else {
          previewThumb.src = 'https://cdn-icons-png.flaticon.com/512/337/337946.png';
          previewThumb.style.display = 'block';
        }

        previewCard.style.display = 'flex';
        document.getElementById('dropArea').style.display = 'none';
      }
    }

    function removeSelectedFile() {
      document.getElementById('fileInput').value = '';
      document.getElementById('previewCard').style.display = 'none';
      document.getElementById('dropArea').style.display = 'block';
    }

    // Drag and Drop helpers
    const dropArea = document.getElementById('dropArea');
    ['dragenter', 'dragover'].forEach(eventName => {
      dropArea.addEventListener(eventName, (e) => { e.preventDefault(); dropArea.classList.add('dragover'); }, false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
      dropArea.addEventListener(eventName, (e) => { e.preventDefault(); dropArea.classList.remove('dragover'); }, false);
    });
    dropArea.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        document.getElementById('fileInput').files = files;
        handleFileSelected(document.getElementById('fileInput'));
      }
    });
    // ================= PWA INSTALLATION CONTROLLER =================
    let deferredPrompt = null;
    const btnInstall = document.getElementById('btnInstallApp');

    function isAppAlreadyInstalled() {
      // 1. Detect if running inside installed standalone PWA
      const isStandalone = window.matchMedia('(display-mode: standalone)').matches 
                        || window.navigator.standalone === true 
                        || document.referrer.includes('android-app://');
      
      // 2. Check localStorage flag if user previously installed on this device
      const isStoredInstalled = localStorage.getItem('pwa_installed') === 'true';

      return isStandalone || isStoredInstalled;
    }

    function checkInstallButtonVisibility() {
      if (isAppAlreadyInstalled()) {
        if (btnInstall) btnInstall.style.display = 'none';
      }
    }

    // Capture install prompt event
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      // Do NOT show if already installed
      if (!isAppAlreadyInstalled()) {
        if (btnInstall) btnInstall.style.display = 'inline-flex';
      }
    });

    // Detect when user completes installation
    window.addEventListener('appinstalled', () => {
      localStorage.setItem('pwa_installed', 'true');
      if (btnInstall) btnInstall.style.display = 'none';
      deferredPrompt = null;
      showToast('🎉 បានដំឡើង Post Automation App លើអេក្រង់ដើមជោគជ័យ!');
    });

    async function handlePwaInstall() {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        if (outcome === 'accepted') {
          localStorage.setItem('pwa_installed', 'true');
          if (btnInstall) btnInstall.style.display = 'none';
        }
        deferredPrompt = null;
      } else {
        // Fallback for iOS or already supported browsers
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        if (isIOS) {
          alert('📱 របៀបដំឡើង Post Automation លើ iPhone / iPad៖\\n\\n1. ចុចប៊ូតុង Share (📤) ខាងក្រោម Browser\\n2. អូសចុះក្រោម រួចជ្រើសរើស «Add to Home Screen ➕ (បន្ថែមទៅអេក្រង់ដើម)»');
        } else {
          alert('💡 របៀបដំឡើង App៖\\n\\nសូមចុចលើសញ្ញា Menu ចុចបី (⋮) នៅជ្រុងខាងស្តាំលើនៃ Browser រួចជ្រើសរើស «Install App» ឬ «Add to Home screen»។');
        }
      }
    }

    // Register Service Worker
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(err => console.log('SW registration error:', err));
        checkInstallButtonVisibility();
      });
    } else {
      checkInstallButtonVisibility();
    }
  </script>
</body>
</html>
"""

def get_bot_username():
    """ទាញយក Bot Username ពិតប្រាកដពី Telegram API"""
    cfg = get_config()
    token = cfg.get("bot_token", "")
    if not token:
        return "TelegramBot"
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        if r.status_code == 200:
            return r.json().get("result", {}).get("username", "ac_Mart_Automate_Posting_bot")
    except Exception:
        pass
    return "ac_Mart_Automate_Posting_bot"

@app.route("/")
def index():
    cfg = get_config()
    groups = facebook_group_service.load_groups()
    bot_name = get_bot_username()
    chat_id = cfg.get("chat_id", "835979970")
    
    fb_all_pages = cfg.get("facebook_all_pages", False)
    selected_pages = cfg.get("facebook_selected_pages", [])
    
    user_token = cfg.get("facebook_user_access_token") or cfg.get("facebook_access_token")
    connected = facebook_page_service.get_connected_pages(user_token)
    
    resp = Response(render_template_string(
        DASHBOARD_HTML,
        groups_count=len(groups),
        bot_user=bot_name,
        chat_id=chat_id,
        fb_all_pages=fb_all_pages,
        selected_pages_count=len(selected_pages),
        connected_pages_count=len(connected) if connected else len(selected_pages)
    ), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route("/manifest.json")
def manifest():
    """PWA Application Manifest with AC Logo"""
    return jsonify({
        "name": "Post Automation",
        "short_name": "PostAuto",
        "description": "Facebook Pages & Groups Multi-Broadcaster Hub with AI",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0b0f19",
        "theme_color": "#4f46e5",
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": "/static/logo.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/logo.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })

@app.route("/sw.js")
def service_worker():
    """Lightweight Service Worker for PWA Installation"""
    sw_code = """
const CACHE_NAME = 'post-auto-cache-v1';
self.addEventListener('install', (e) => {
    self.skipWaiting();
});
self.addEventListener('activate', (e) => {
    e.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', (e) => {
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request))
    );
});
"""
    return Response(sw_code, mimetype="application/javascript")

@app.route("/static/<path:filename>")
def serve_static(filename):
    static_dir = os.path.join(BASE_DIR, "static")
    return send_from_directory(static_dir, filename)

@app.route("/logo.png")
@app.route("/favicon.ico")
def serve_logo():
    static_dir = os.path.join(BASE_DIR, "static")
    return send_from_directory(static_dir, "logo.png")

@app.route("/api/facebook/token-status", methods=["GET"])
def token_status():
    cfg = get_config()
    token = cfg.get("facebook_user_access_token") or cfg.get("facebook_access_token")
    info = facebook_page_service.get_token_expiration_info(token)
    return jsonify(info)

@app.route("/api/settings", methods=["GET"])
def get_settings():
    """ទាញយកការកំណត់ទាំងអស់សម្រាប់បង្ហាញក្នុង Setting Dialog"""
    cfg = get_config()
    user_token = cfg.get("facebook_user_access_token") or cfg.get("facebook_access_token")
    connected = facebook_page_service.get_connected_pages(user_token)

    return jsonify({
        "chat_id": str(cfg.get("chat_id", "")),
        "bot_token": cfg.get("bot_token", ""),
        "facebook_page_id": cfg.get("facebook_page_id", ""),
        "facebook_all_pages": cfg.get("facebook_all_pages", False),
        "facebook_selected_pages": cfg.get("facebook_selected_pages", []),
        "connected_pages": connected
    })

@app.route("/api/settings", methods=["POST"])
def update_settings():
    """រក្សាទុកការកំណត់ថ្មីចូល config.json ដើម្បី Take Control លើ App"""
    data = request.get_json(force=True, silent=True) or {}
    cfg = get_config()

    if "chat_id" in data:
        cfg["chat_id"] = str(data["chat_id"])
    if "bot_token" in data and data["bot_token"]:
        cfg["bot_token"] = data["bot_token"]
    if "facebook_page_id" in data:
        cfg["facebook_page_id"] = data["facebook_page_id"]
    if "facebook_all_pages" in data:
        cfg["facebook_all_pages"] = bool(data["facebook_all_pages"])
    if "facebook_selected_pages" in data:
        cfg["facebook_selected_pages"] = data["facebook_selected_pages"]

    # រក្សាទុកស្ថានភាព Enable/Disable របស់ Groups
    if "enabled_group_ids" in data:
        enabled_ids = set(str(gid) for gid in data["enabled_group_ids"])
        groups = facebook_group_service.load_groups()
        for g in groups:
            g["enabled"] = str(g.get("id")) in enabled_ids
        facebook_group_service.save_groups(groups)

    success = save_config(cfg)
    return jsonify({
        "success": success,
        "message": "បានរក្សាទុកការកំណត់ជោគជ័យ!" if success else "បរាជ័យក្នុងការរក្សាទុក"
    })

@app.route("/api/groups", methods=["GET"])
def get_groups_route():
    """ទាញយកបញ្ជីក្រុម Facebook ទាំងអស់ទាំង 106 ក្រុម រួមទាំង Cooldown Status"""
    groups = facebook_group_service.load_groups()
    now_ts = int(time.time())
    cooldown_secs = 24 * 3600
    
    enriched = []
    for g in groups:
        last_posted = g.get('last_posted_at', 0)
        in_cooldown = bool(last_posted and (now_ts - last_posted < cooldown_secs))
        rem_hours = round((cooldown_secs - (now_ts - last_posted)) / 3600, 1) if in_cooldown else 0
        enriched.append({
            "id": str(g.get("id")),
            "name": g.get("name") or "Facebook Group",
            "url": g.get("url") or f"https://www.facebook.com/groups/{g.get('id')}",
            "enabled": g.get("enabled", True),
            "in_cooldown": in_cooldown,
            "remaining_hours": rem_hours,
            "last_posted_at": last_posted,
            "niche": g.get("niche", "general")
        })
    return jsonify({
        "total": len(enriched),
        "cooldown_count": sum(1 for x in enriched if x["in_cooldown"]),
        "ready_count": sum(1 for x in enriched if not x["in_cooldown"]),
        "groups": enriched
    })

@app.route("/api/groups/reset-cooldowns", methods=["POST"])
def reset_cooldowns_route():
    """សម្អាត 24h Cooldown លើ Facebook Groups ទាំងអស់"""
    reset_count = facebook_group_service.reset_all_cooldowns()
    return jsonify({"success": True, "reset_count": reset_count})

@app.route("/api/telegram/test-ping", methods=["POST"])
def test_telegram_ping():
    """ផ្ញើសារសាកល្បងទៅ Telegram Admin Chat"""
    data = request.get_json(force=True, silent=True) or {}
    cfg = get_config()
    token = data.get("bot_token") or cfg.get("bot_token")
    chat_id = data.get("chat_id") or cfg.get("chat_id")

    if not token or not chat_id:
        return jsonify({"success": False, "detail": "ខ្វះ Bot Token ឬ Chat ID"}), 400

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": "🔔 **តេស្តប្រព័ន្ធ (System Test):**\n\nផ្ទាំងបញ្ជា Web Dashboard បានភ្ជាប់ជាមួយ Telegram របស់អ្នកដោយជោគជ័យ! ✅\nអ្នកអាចគ្រប់គ្រង និងផ្សព្វផ្សាយបានគ្រប់ពេលវេលា។",
        "parse_mode": "Markdown"
    }

    try:
        r = requests.post(url, json=payload, timeout=15)
        res = r.json()
        if res.get("ok"):
            return jsonify({"success": True})
        return jsonify({"success": False, "detail": res.get("description", "Telegram Error")})
    except Exception as e:
        return jsonify({"success": False, "detail": str(e)})

@app.route("/api/gemini/generate-caption", methods=["POST"])
def api_generate_caption():
    """បង្កើត Caption តាមរយៈ Gemini API"""
    data = request.get_json(force=True, silent=True) or {}
    topic = data.get("topic", "").strip()
    tone = data.get("tone", "sales")

    if not topic:
        return jsonify({"success": False, "message": "សូមបញ្ចូលប្រធានបទជាមុនសិន"}), 400

    caption = generate_gemini_caption(topic, tone)
    if caption:
        return jsonify({"success": True, "caption": caption})
    return jsonify({"success": False, "message": "Gemini API មិនបានឆ្លើយតប សូមពិនិត្យមើល gemini_key"}), 500

@app.route("/api/telegram-webhook", methods=["GET", "POST"])
def telegram_webhook():
    """ទទួល Webhook updates ពី Telegram Serverless"""
    if request.method == "GET":
        return jsonify({
            "status": "online",
            "service": "Facebook Social Broadcaster Webhook",
            "bot": get_bot_username(),
            "time": int(time.time())
        })

    update = request.get_json(force=True, silent=True)
    if not update:
        return jsonify({"status": "no data"}), 400
        
    if "message" in update:
        telegram_controller.handle_incoming_message(update["message"])
    elif "callback_query" in update:
        telegram_controller.handle_callback_query(update["callback_query"])
        
    return jsonify({"ok": True})

@app.route("/api/manual-broadcast", methods=["POST"])
def manual_broadcast():
    caption = request.form.get("caption", "")
    media_url = request.form.get("media_url", "")
    
    dest_pages = request.form.get("dest_pages") == "1"
    dest_groups = request.form.get("dest_groups") == "1"
    dest_tiktok = request.form.get("dest_tiktok") == "1"
    
    # ពិនិត្យមើល Local File Upload
    media_file = request.files.get("media_file")
    media_path = media_url
    media_type = "text"

    if media_file and media_file.filename:
        safe_name = f"upload_{int(time.time())}_{media_file.filename.replace(' ', '_')}"
        save_path = os.path.join(UPLOAD_FOLDER, safe_name)
        media_file.save(save_path)
        media_path = save_path

        ext = os.path.splitext(media_file.filename)[1].lower()
        if ext in [".mp4", ".mov", ".webm", ".mkv"]:
            media_type = "video"
        elif ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            media_type = "photo"
        else:
            media_type = "document"
    elif media_url:
        media_path = media_url
        if any(media_url.lower().endswith(ext) for ext in [".mp4", ".mov", ".webm", ".mkv"]) or "/video/" in media_url.lower():
            media_type = "video"
        elif any(media_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            media_type = "photo"

    # Auto-detect if user pasted video/photo link into caption and clean the caption
    if media_type == "text" and caption:
        clean_c, auto_type, auto_url = telegram_controller.extract_media_from_content(caption)
        if auto_type != "text" and auto_url:
            media_type = auto_type
            media_path = auto_url
            caption = clean_c
    elif media_type in ["video", "photo"] and caption:
        clean_c, _, _ = telegram_controller.extract_media_from_content(caption)
        caption = clean_c

    cfg = get_config()
    chat_id = cfg.get("chat_id")
    
    session = {
        "media_type": media_type,
        "media_path": media_path,
        "caption": caption,
        "dest_pages": dest_pages,
        "dest_groups": dest_groups,
        "dest_tiktok": dest_tiktok
    }
    
    telegram_controller.execute_broadcast(chat_id=str(chat_id), message_id=0, session=session)
    return """
    <!DOCTYPE html>
    <html lang="km">
    <head>
      <meta charset="utf-8">
      <title>ជោគជ័យ!</title>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700&family=Kantumruy+Pro:wght@600;700&display=swap" rel="stylesheet">
      <style>
        body { background: #0b0f19; color: #fff; font-family: 'Plus Jakarta Sans', 'Kantumruy Pro', sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .box { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 40px; text-align: center; max-width: 520px; }
        h1 { color: #10b981; font-size: 1.6rem; margin-bottom: 12px; }
        p { color: #94a3b8; margin-bottom: 24px; line-height: 1.6; }
        a { display: inline-block; background: #3b82f6; color: #fff; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 700; }
        a:hover { background: #2563eb; }
      </style>
    </head>
    <body>
      <div class="box">
        <h1>✅ បានចាប់ផ្តើមការផ្សព្វផ្សាយជោគជ័យ!</h1>
        <p>ប្រព័ន្ធបានបញ្ជូនការផ្សាយទៅកាន់ Channels ដែលបានជ្រើសរើសរួចរាល់។ របាយការណ៍លម្អិតត្រូវបានផ្ញើទៅកាន់ Telegram របស់អ្នក។</p>
        <a href="/">🏠 ត្រឡប់ទៅផ្ទាំងបញ្ជាដើម</a>
      </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8899, debug=False)
