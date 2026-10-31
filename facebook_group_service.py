# -*- coding: utf-8 -*-
"""
Facebook Groups Auto-Poster Engine (Strict Niche & 24h Anti-Spam)
================================================================
Handles automated broadcasting to Facebook Groups:
- Cookie-based session posting
- Strict Niche Isolation (Knowledge, Tech, Agriculture, Real Estate, Services)
- 24-Hour Cooldown Filter per group to avoid spam flags
- Auto-Approved Detection and Instant Validation
- Automatically updates 'last_posted_at' in facebook_groups.json
"""

import os
import re
import json
import time
import requests
from typing import List, Dict, Tuple, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GROUPS_FILE = os.path.join(BASE_DIR, "facebook_groups.json")
COOKIES_FILE = os.path.join(BASE_DIR, "facebook_cookies.json")

def get_active_groups_file() -> str:
    """ប្រើប្រាស់ /tmp លើ Vercel Serverless ដើម្បីអាចកត់ត្រា Cooldown បានដោយគ្មាន Error Read-only"""
    if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
        import tempfile, shutil
        tmp_file = os.path.join(tempfile.gettempdir(), "facebook_groups.json")
        if not os.path.exists(tmp_file) and os.path.exists(GROUPS_FILE):
            try:
                shutil.copy2(GROUPS_FILE, tmp_file)
            except Exception:
                pass
        if os.path.exists(tmp_file):
            return tmp_file
    return GROUPS_FILE

def load_groups() -> List[Dict]:
    """ទាញយកបញ្ជីក្រុមទាំងអស់ពី JSON"""
    target = get_active_groups_file()
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading groups file: {e}")
    return []

def save_groups(groups: List[Dict]):
    """រក្សាទុកបញ្ជីក្រុម"""
    target = get_active_groups_file()
    try:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving groups file: {e}")

NICHE_MAPPINGS = {
    "real_estate": {
        "keywords": [
            "ដីឡូតិ៍", "ដីឡូត៍", "លក់ដី", "ទិញដី", "ដីធ្លី", "លក់ផ្ទះ", "ទិញផ្ទះ", "ផ្ទះល្វែង", 
            "ផ្ទះវីឡា", "បុរី", "ខុនដូ", "អចលនទ្រព្យ", "ប្លង់រឹង", "ទីតាំងល្អ", "លក់បន្ទាន់", "គម្រោងដី"
        ],
        "allowed_group_types": ["real_estate", "business"]
    },
    "agriculture": {
        "keywords": [
            "កសិកម្ម", "ចិញ្ចឹមគោ", "សត្វគោ", "ពូជគោ", "ចិញ្ចឹមមាន់", "សត្វមាន់", "ចិញ្ចឹមទា", 
            "ចិញ្ចឹមត្រី", "ដំណាំ", "ជីកសិកម្ម", "ជីធម្មជាតិ", "កសិដ្ឋាន", "ដាំបន្លែ", "ដាំដុះ", "សត្វពាហនៈ", "កសិផល"
        ],
        "allowed_group_types": ["agriculture"]
    },
    "tech": {
        "keywords": [
            "ai", "បច្ចេកវិទ្យា", "computer", "phone", "app", "software", "chatgpt", 
            "programming", "system", "ទូរស័ព្ទដៃ", "កុំព្យូទ័រ"
        ],
        "allowed_group_types": ["tech", "knowledge", "general"]
    },
    "knowledge": {
        "keywords": [
            "ចំណេះដឹង", "ទស្សនវិជ្ជា", "គំនិតល្អ", "ការអប់រំ", "ប្រវត្តិសាស្ត្រ", "វិទ្យាសាស្ត្រ", 
            "មេរៀនជីវិត", "បទពិសោធន៍", "kanitha", "សៀវភៅ", "ការគិត", "ទស្សនៈ"
        ],
        "allowed_group_types": ["knowledge", "general", "education"]
    },
    "services": {
        "keywords": [
            "សេវាកម្ម", "ការងារ", "ប្រាក់ខែ", "ជ្រើសរើសបុគ្គលិក", "ហាងទំនិញ", "ផ្សារទិញលក់", 
            "ដឹកជញ្ជូន", "ទេសចរណ៍", "សណ្ឋាគារ"
        ],
        "allowed_group_types": ["services", "general"]
    }
}

def detect_caption_niche(caption: str) -> str:
    """វិភាគរក Niche នៃអត្ថបទ/Caption ជាមួយប្រព័ន្ធពិន្ទុតាមប្រវែងពាក្យ (Weighted Matching)"""
    text = (caption or "").lower()
    scores = {}
    for niche, conf in NICHE_MAPPINGS.items():
        score = 0
        for kw in conf["keywords"]:
            if kw in text:
                score += len(kw) # ពាក្យកាន់តែវែង និងជាក់លាក់ ផ្ដល់ពិន្ទុកាន់តែខ្ពស់
        scores[niche] = score

    best_niche = max(scores, key=scores.get)
    return best_niche if scores[best_niche] > 0 else "general"

def filter_niche_groups(caption: str = "", max_groups: int = 15, cooldown_hours: int = 24) -> Tuple[List[Dict], str]:
    """
    ជ្រើសរើសក្រុមដែលត្រូវនឹង Niche និងឆ្លងកាត់ការពិនិត្យ 24h Cooldown
    """
    all_groups = load_groups()
    if not all_groups:
        return [], "general"
        
    niche = detect_caption_niche(caption)
    now_ts = int(time.time())
    cooldown_secs = cooldown_hours * 3600

    filtered = []
    for g in all_groups:
        g_name = g.get('name', '').lower()
        g_type = g.get('niche', 'general')

        # 1. ត្រួតពិនិត្យ 24-Hour Cooldown
        last_posted = g.get('last_posted_at', 0)
        if last_posted and (now_ts - last_posted < cooldown_secs):
            continue

        # 2. ពិនិត្យភាពត្រូវគ្នានៃ Niche (Strict Isolation)
        if niche == "real_estate":
            if any(w in g_name for w in ["ដី", "ផ្ទះ", "អចលនទ្រព្យ", "ទិញលក់"]) or g_type in ["real_estate", "business"]:
                filtered.append(g)

        elif niche == "agriculture":
            if any(w in g_name for w in ["កសិកម្ម", "គោ", "មាន់", "ដាំដុះ"]) or g_type == "agriculture":
                filtered.append(g)

        elif niche == "knowledge":
            if any(w in g_name for w in ["ចិញ្ចឹមគោ", "កសិកម្ម", "ដី", "ផ្ទះ", "ទិញលក់", "បូមលូ", "បង្គន់"]):
                continue
            if g_type in ["knowledge", "education"] or any(k in g_name for k in ["គំនិត", "kanitha", "ខ្មែរ", "ចំណេះដឹង", "ទស្សន"]):
                filtered.append(g)

        elif niche == "tech":
            if any(w in g_name for w in ["ចិញ្ចឹមគោ", "ដី", "ផ្ទះ", "បូមលូ", "បង្គន់"]):
                continue
            if g_type in ["tech", "knowledge"] or any(k in g_name for k in ["tech", "ai", "it", "phone"]):
                filtered.append(g)

        else:
            # ករណីទូទៅ មិនរាប់បញ្ចូលក្រុមចិញ្ចឹមសត្វ ឬដីធ្លីឡើយ
            if not any(w in g_name for w in ["ចិញ្ចឹមគោ", "ដី", "ផ្ទះ", "បូមលូ", "បង្គន់"]):
                filtered.append(g)

    # ផ្ដល់អាទិភាពក្រុមណាដែលជា Auto-Approved
    filtered.sort(key=lambda x: (not x.get('auto_approved', False), x.get('last_posted_at', 0)))
    return filtered[:max_groups], niche

def mark_group_posted(group_id: str):
    """កត់ត្រាពេលវេលាដែលបានផុសចុងក្រោយដើម្បីការពារ Cooldown"""
    all_groups = load_groups()
    now_ts = int(time.time())
    for g in all_groups:
        if str(g.get('id')) == str(group_id):
            g['last_posted_at'] = now_ts
            break
    save_groups(all_groups)

def reset_all_cooldowns() -> int:
    """លុប 24h Cooldown ពីគ្រប់ក្រុមទាំងអស់ ដើម្បីអាចផុសសារជាថ្មីបានភ្លាមៗ"""
    all_groups = load_groups()
    count = 0
    for g in all_groups:
        if g.get('last_posted_at', 0) > 0:
            g['last_posted_at'] = 0
            count += 1
    save_groups(all_groups)
    return count

