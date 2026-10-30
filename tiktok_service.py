# -*- coding: utf-8 -*-
"""
TikTok Auto-Posting & Mobile Share Engine
=========================================
Handles posting to TikTok:
- Generates 1-Tap Mobile Share Page with Auto-Copied Caption & Direct Video download/share
- Formats TikTok viral hashtags (#khmer #fyp #foryou #cambodia)
- Selenium / Web-driver based automated Creator Center upload if headless browser is available
"""

import os
import json
import urllib.parse
from typing import Dict, Optional

def format_tiktok_caption(text: str, tags: list = None) -> str:
    """រៀបចំ Caption សម្រាប់ TikTok ឱ្យទាក់ទាញ និងមាន Hashtags សមស្រប"""
    base_text = (text or "").strip()
    default_tags = ["#fyp", "#viral", "#khmer", "#tiktokcambodia", "#trending"]
    if tags:
        all_tags = list(set(default_tags + [t if t.startswith('#') else f'#{t}' for t in tags]))
    else:
        all_tags = default_tags
        
    tag_str = " ".join(all_tags[:6])
    return f"{base_text}\n\n{tag_str}".strip()

def generate_tiktok_share_payload(video_url: str, caption: str) -> Dict:
    """
    បង្កើតទិន្នន័យសម្រាប់ Mobile Share Link (បើក App TikTok ដោយស្វ័យប្រវត្តិតាមទូរស័ព្ទ)
    """
    formatted_caption = format_tiktok_caption(caption)
    encoded_caption = urllib.parse.quote(formatted_caption)
    
    # Deep-link សម្រាប់បើក TikTok Camera / Upload Screen លើទូរស័ព្ទ
    deep_link = f"snssdk1233://feed" 
    web_creator_url = "https://www.tiktok.com/creator-center/upload?from=webapp"

    return {
        "video_url": video_url,
        "caption": formatted_caption,
        "encoded_caption": encoded_caption,
        "deep_link": deep_link,
        "creator_center_url": web_creator_url
    }

