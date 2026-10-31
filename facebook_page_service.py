# -*- coding: utf-8 -*-
"""
Facebook Pages Auto-Broadcaster Engine
======================================
Handles posting to Facebook Pages via Graph API:
- Text posts (Feed updates)
- Single and multi-photo uploads
- Video & Facebook Reels uploads
- Multi-page broadcast in parallel or sequence
- Live Token validity & expiration monitoring
"""

import os
import json
import time
import requests
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

def get_token_expiration_info(access_token: str) -> dict:
    """ពិនិត្យមើលសុពលភាព និងចំនួនថ្ងៃនៅសល់របស់ Facebook Access Token"""
    if not access_token:
        return {"valid": False, "text": "❌ គ្មាន Token"}
    try:
        url = f"https://graph.facebook.com/debug_token?input_token={access_token}&access_token={access_token}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json().get('data', {})
            is_valid = data.get('is_valid', False)
            if not is_valid:
                return {"valid": False, "text": "❌ Token អស់សុពលភាព"}
            
            exp_ts = data.get('data_access_expires_at') or data.get('expires_at')
            if not exp_ts or exp_ts == 0:
                return {"valid": True, "never_expires": True, "text": "🟢 សកម្មជានិច្ច (Never Expires)", "remaining_days": 999}
            
            remaining_seconds = exp_ts - time.time()
            if remaining_seconds <= 0:
                return {"valid": False, "text": "❌ Token ផុតកំណត់ហើយ", "remaining_days": 0}
            
            days = int(remaining_seconds / 86400)
            return {
                "valid": True,
                "remaining_days": days,
                "expires_at": exp_ts,
                "text": f"⏳ នៅសល់ {days} ថ្ងៃ"
            }
    except Exception as e:
        return {"valid": False, "text": f"⚠️ ពិនិត្យមិនបាន: {str(e)}"}
    return {"valid": False, "text": "❌ មិនអាចផ្ទៀងផ្ទាត់"}

def get_connected_pages(user_access_token: str) -> List[Dict]:
    """ទាញយកបញ្ជី Facebook Pages ទាំងអស់ដែល User កាន់កាប់"""
    if not user_access_token:
        return []
    try:
        url = f"{GRAPH_API_BASE}/me/accounts?fields=id,name,access_token,category,tasks&limit=100&access_token={user_access_token}"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            return res.json().get('data', [])
    except Exception as e:
        print(f"⚠️ Error fetching user pages: {e}")
    return []

def post_to_single_page(page_id: str, page_token: str, message: str, 
                        image_url: Optional[str] = None, 
                        image_path: Optional[str] = None,
                        video_url: Optional[str] = None, 
                        video_path: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """
    ផុសមាតិកា (អក្សរ, រូបភាព, ឬវីដេអូ) ទៅកាន់ Facebook Page មួយ
    - ធានាថាការផុស Video ត្រូវតែជា Native Video Player (មានប៊ូតុង Play/Pause, សំឡេង) មិនមែនជា Text Link ឡើយ
    - សម្អាតបន្ទាត់តំណភ្ជាប់ URL ចេញពី Description ដោយស្វ័យប្រវត្តិ
    Returns: (success: bool, message: str, post_id: Optional[str])
    """
    try:
        # សម្អាត Link វីដេអូចេញពី Description ពេលផុសជា Video
        if (video_url or video_path) and message:
            clean_desc_lines = []
            for line in message.splitlines():
                if video_url and video_url in line:
                    continue
                if any(tag in line for tag in ["តំណភ្ជាប់វីដេអូ", "🔗", "Video Link"]) and any(ext in line.lower() for ext in [".mp4", ".mov", ".webm", "http"]):
                    continue
                clean_desc_lines.append(line)
            message = "\n".join(clean_desc_lines).strip()

        # 1. ករណីផុសវីដេអូ (Native Video / Reels)
        if video_path and os.path.exists(video_path):
            url = f"{GRAPH_API_BASE}/{page_id}/videos"
            with open(video_path, 'rb') as f:
                files = {'source': f}
                data = {'description': message, 'access_token': page_token}
                res = requests.post(url, data=data, files=files, timeout=180)
                if res.status_code == 200:
                    vid_id = res.json().get('id')
                    return True, "Published native video successfully", vid_id
                return False, f"Video upload failed: {res.text}", None

        elif video_url:
            url = f"{GRAPH_API_BASE}/{page_id}/videos"
            payload = {'file_url': video_url, 'description': message, 'access_token': page_token}
            try:
                res = requests.post(url, data=payload, timeout=90)
                if res.status_code == 200:
                    vid_id = res.json().get('id')
                    return True, "Published native video URL successfully", vid_id
                print(f"⚠️ file_url method returned {res.status_code}: {res.text}. Trying fallback download...")
            except Exception as direct_err:
                print(f"⚠️ file_url request exception: {direct_err}. Trying fallback download...")

            # Fallback: Download video locally then upload as binary source
            try:
                import tempfile
                temp_dir = os.path.join(tempfile.gettempdir(), "fb_uploads")
                os.makedirs(temp_dir, exist_ok=True)
                temp_vid = os.path.join(temp_dir, f"fb_temp_{int(time.time())}.mp4")
                dl_res = requests.get(video_url, stream=True, timeout=90)
                if dl_res.status_code == 200:
                    with open(temp_vid, 'wb') as tf:
                        for chunk in dl_res.iter_content(chunk_size=1024*1024):
                            if chunk:
                                tf.write(chunk)
                    with open(temp_vid, 'rb') as tf:
                        files = {'source': tf}
                        data = {'description': message, 'access_token': page_token}
                        res_source = requests.post(url, data=data, files=files, timeout=180)
                    if os.path.exists(temp_vid):
                        os.remove(temp_vid)
                    if res_source.status_code == 200:
                        vid_id = res_source.json().get('id')
                        return True, "Published native video via fallback successfully", vid_id
                    return False, f"Fallback video post failed: {res_source.text}", None
            except Exception as fallback_err:
                return False, f"Video upload fallback exception: {str(fallback_err)}", None

            return False, f"Video URL post failed: {res.text if 'res' in locals() else 'Unknown error'}", None

        # 2. ករណីផុសរូបភាព (Photo)
        if image_path and os.path.exists(image_path):
            url = f"{GRAPH_API_BASE}/{page_id}/photos"
            with open(image_path, 'rb') as f:
                files = {'source': f}
                data = {'caption': message, 'access_token': page_token}
                res = requests.post(url, data=data, files=files, timeout=60)
                if res.status_code == 200:
                    photo_id = res.json().get('id')
                    return True, "Published photo successfully", photo_id
                return False, f"Photo upload failed: {res.text}", None

        elif image_url:
            url = f"{GRAPH_API_BASE}/{page_id}/photos"
            payload = {'url': image_url, 'caption': message, 'access_token': page_token}
            res = requests.post(url, data=payload, timeout=30)
            if res.status_code == 200:
                photo_id = res.json().get('id')
                return True, "Published photo URL successfully", photo_id
            return False, f"Photo URL post failed: {res.text}", None

        # 3. ករណីផុសតែអក្សរ (Text Status Update)
        url = f"{GRAPH_API_BASE}/{page_id}/feed"
        payload = {'message': message, 'access_token': page_token}
        res = requests.post(url, data=payload, timeout=20)
        if res.status_code == 200:
            post_id = res.json().get('id')
            return True, "Published text post successfully", post_id
        return False, f"Text post failed: {res.text}", None

    except Exception as e:
        return False, f"Exception: {str(e)}", None

def broadcast_to_all_pages(pages_list: List[Dict], message: str,
                           image_url: Optional[str] = None, image_path: Optional[str] = None,
                           video_url: Optional[str] = None, video_path: Optional[str] = None) -> List[Dict]:
    """
    បាញ់ផុសទៅកាន់គ្រប់ Pages ទាំងអស់ក្នុងបញ្ជីដោយប្រើ Parallel ThreadPool លឿន និងរហ័ស
    """
    valid_pages = [p for p in pages_list if p.get('id') and p.get('access_token')]
    if not valid_pages:
        return []

    results = []

    def _post_page(page: Dict) -> Dict:
        p_id = page.get('id')
        p_name = page.get('name', 'Page')
        p_token = page.get('access_token')
        ok, msg, post_id = post_to_single_page(
            page_id=p_id,
            page_token=p_token,
            message=message,
            image_url=image_url,
            image_path=image_path,
            video_url=video_url,
            video_path=video_path
        )
        return {
            "page_id": p_id,
            "page_name": p_name,
            "success": ok,
            "message": msg,
            "post_id": post_id
        }

    # ដំណើរការ 5 Threads ដំណាលគ្នា ដើម្បីឱ្យការផ្សាយចំណាយពេលត្រឹម 5-8 វិនាទី
    max_workers = min(5, len(valid_pages))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_post_page, p) for p in valid_pages]
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"success": False, "message": str(e), "post_id": None})

    return results

