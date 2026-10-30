# -*- coding: utf-8 -*-
"""
Social Media Broadcaster - Master Unified Entry Point
======================================================
Coordinates all core components:
1. Telegram Remote-Control Bot (Long-Polling mode for Desktop/Server)
2. Web Management Dashboard (Flask Web UI)
3. Direct CLI Broadcasting Wizard (Facebook Pages, Groups & TikTok)
4. Account & Token Health Diagnostics

Usage:
  python main.py                  # Interactive Menu (or auto-start if non-interactive)
  python main.py --all            # Launch Telegram Bot + Web Dashboard concurrently
  python main.py --bot            # Launch Telegram Bot only
  python main.py --web            # Launch Web Dashboard only
  python main.py --status         # Check Facebook tokens, Pages, Groups, and Bot health
  python main.py --broadcast "Text" --media "path/image.jpg"
"""

import os
import sys
import time
import json
import argparse
import threading
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app as web_app
import telegram_controller
import facebook_page_service
import facebook_group_service
import tiktok_service
import khmer_linguistic_sanitizer

BANNER = """
========================================================================
   🚀 SOCIAL MEDIA BROADCASTER - MASTER CONTROLLER 🚀
   Facebook Pages • Facebook Groups • TikTok • Telegram Bot
========================================================================
"""

def print_banner():
    print(BANNER)

def check_status():
    """ពិនិត្យមើល និងបង្ហាញរបាយការណ៍ស្ថានភាពនៃគណនី និងប្រព័ន្ធទាំងអស់"""
    print_banner()
    print("🔍 [DIAGNOSTICS] កំពុងពិនិត្យសុពលភាពគណនី និងប្រព័ន្ធទាំងអស់...\n")

    cfg = telegram_controller.load_config()
    bot_token = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    fb_token = cfg.get("facebook_user_access_token") or cfg.get("facebook_access_token", "")

    # 1. Telegram Bot Status
    print("🤖 1. ស្ថានភាព TELEGRAM BOT:")
    if bot_token:
        bot_info = telegram_controller.send_telegram_api("getMe", {})
        if bot_info.get("ok"):
            res = bot_info.get("result", {})
            print(f"   • ឈ្មោះ Bot: {res.get('first_name')} (@{res.get('username')})")
            print(f"   • Bot ID: {res.get('id')}")
            print(f"   • Admin Chat ID: {chat_id or 'មិនទាន់កំណត់'}")
            print("   • ស្ថានភាព Bot: 🟢 សកម្ម និងភ្ជាប់ជោគជ័យ (Connected)")
        else:
            print(f"   • ស្ថានភាព Bot: ❌ បរាជ័យក្នុងការតភ្ជាប់ ({bot_info.get('description', 'Unknown error')})")
    else:
        print("   • ស្ថានភាព Bot: ⚠️ គ្មាន Bot Token ក្នុង config.json")

    print("-" * 72)

    # 2. Facebook Access Token Status
    print("📘 2. ស្ថានភាព FACEBOOK ACCESS TOKEN:")
    token_info = facebook_page_service.get_token_expiration_info(fb_token)
    print(f"   • សុពលភាព Token: {token_info.get('text')}")
    if token_info.get("valid"):
        rem_days = token_info.get("remaining_days")
        if rem_days is not None:
            print(f"   • ចំនួនថ្ងៃនៅសល់: {rem_days} ថ្ងៃ")
    else:
        print("   • ⚠️ សូមពិនិត្យមើល User Access Token ឡើងវិញក្នុង config.json")

    print("-" * 72)

    # 3. Facebook Connected Pages
    print("📄 3. បញ្ជី FACEBOOK PAGES:")
    pages = facebook_page_service.get_connected_pages(fb_token)
    print(f"   • ចំនួន Pages សរុប: {len(pages)} Pages")
    if pages:
        for idx, p in enumerate(pages[:8], 1):
            print(f"     [{idx}] {p.get('name')} (ID: {p.get('id')})")
        if len(pages) > 8:
            print(f"     ... និងនៅមាន {len(pages) - 8} Pages ផ្សេងទៀត។")
    else:
        fallback_page_id = cfg.get("facebook_page_id")
        if fallback_page_id:
            print(f"   • Fallback Page ID: {fallback_page_id}")
        else:
            print("   • ⚠️ គ្មាន Page ត្រូវបានរកឃើញឡើយ")

    print("-" * 72)

    # 4. Facebook Groups & Niche Stats
    print("👥 4. បញ្ជី FACEBOOK GROUPS (NICHE & COOLDOWN):")
    groups = facebook_group_service.load_groups()
    total_groups = len(groups)
    print(f"   • ចំនួនក្រុមសរុប: {total_groups} ក្រុម")

    if groups:
        now_ts = int(time.time())
        cooldown_secs = 24 * 3600
        cooldown_count = sum(1 for g in groups if (now_ts - g.get('last_posted_at', 0)) < cooldown_secs)
        auto_approved_count = sum(1 for g in groups if g.get('auto_approved', False))
        
        # Niche breakdown
        niche_counts = {}
        for g in groups:
            n = g.get('niche', 'general')
            niche_counts[n] = niche_counts.get(n, 0) + 1

        print(f"   • ក្រុមរួចរាល់សម្រាប់ផុស (Ready): {total_groups - cooldown_count} ក្រុម")
        print(f"   • ក្រុមក្នុង Cooldown 24h: {cooldown_count} ក្រុម")
        print(f"   • ក្រុម Auto-Approved: {auto_approved_count} ក្រុម")
        print("   • ការបែងចែកតាម Niche:")
        for niche_name, count in sorted(niche_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"     - {niche_name.capitalize()}: {count} ក្រុម")

    print("-" * 72)

    # 5. Dashboard URL
    print("🌐 5. ផ្ទាំងបញ្ជា WEB DASHBOARD:")
    print("   • អាសយដ្ឋាន Local: http://localhost:8899")
    print("   • អាសយដ្ឋាន Network: http://0.0.0.0:8899")
    print("========================================================================\n")

def run_telegram_bot():
    """ចាប់ផ្ដើម Telegram Bot ក្នុងទម្រង់ Long-Polling"""
    print_banner()
    print("🤖 កំពុងដំណើរការ Telegram Bot Remote Controller (Long-Polling)...")
    print("📱 អ្នកអាចផ្ញើរូបភាព វីដេអូ ឬសារអក្សរចូល Bot ពីទូរស័ព្ទដៃបានគ្រប់ពេល!")
    print("🛑 ចុច [Ctrl + C] ដើម្បីបញ្ឈប់ Bot។\n")
    try:
        telegram_controller.start_polling()
    except KeyboardInterrupt:
        print("\n🛑 Telegram Bot ត្រូវបានបញ្ឈប់។")
    except Exception as e:
        print(f"\n⚠️ Telegram Bot Exception: {e}")

def run_web_dashboard(host: str = "0.0.0.0", port: int = 8899):
    """ចាប់ផ្ដើម Web Dashboard (Flask Server)"""
    print_banner()
    print(f"🌐 កំពុងដំណើរការ Web Management Dashboard នៅលើ http://{host}:{port} ...")
    print("💻 បើក Browser របស់អ្នកដើម្បីមើលផ្ទាំងបញ្ជា និងផ្សព្វផ្សាយ។")
    print("🛑 ចុច [Ctrl + C] ដើម្បីបញ្ឈប់ Server។\n")
    try:
        web_app.app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 Web Dashboard ត្រូវបានបញ្ឈប់។")
    except Exception as e:
        print(f"\n⚠️ Web Server Exception: {e}")

def run_all(host: str = "0.0.0.0", port: int = 8899):
    """ដំណើរការទាំង Telegram Bot និង Web Dashboard ដំណាលគ្នា (Concurrently)"""
    print_banner()
    print("🚀 កំពុងដំណើរការប្រព័ន្ធទាំងមូល (All Services Concurrent Mode):")
    print("   [1] 🤖 Telegram Bot Remote Controller: កំពុងរត់ក្នុង Background Thread")
    print(f"   [2] 🌐 Web Dashboard: http://localhost:{port} (http://{host}:{port})")
    print("-" * 72)
    print("💡 ព័ត៌មានជំនួយ:")
    print("   • ផ្ញើរូបភាព ឬវីដេអូទៅកាន់ Telegram Bot របស់អ្នកដើម្បីបាញ់ផ្សាយភ្លាមៗ។")
    print(f"   • ឬចូលទៅកាន់ Dashboard តាមរយៈ http://localhost:{port} ដើម្បីបញ្ជា។")
    print("🛑 ចុច [Ctrl + C] ដើម្បីបញ្ឈប់សេវាកម្មទាំងអស់។\n")

    # Start Telegram Bot in background daemon thread
    bot_thread = threading.Thread(
        target=telegram_controller.start_polling,
        name="TelegramBotThread",
        daemon=True
    )
    bot_thread.start()

    # Give the thread a moment to initialize
    time.sleep(1)

    # Run Web Dashboard on main thread
    try:
        web_app.app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 បានទទួលការបញ្ជាឱ្យបញ្ឈប់ (Shutdown Signal)... កំពុងបិទសេវាកម្មទាំងអស់។")
    except Exception as e:
        print(f"\n⚠️ កំហុសក្នុងពេលដំណើរការ: {e}")

def run_cli_broadcast(caption: str, media_path: Optional[str] = None,
                      dest_pages: bool = True, dest_groups: bool = True, dest_tiktok: bool = False):
    """ផ្សព្វផ្សាយមាតិកាផ្ទាល់ពី Command Line (CLI Direct Broadcast)"""
    print_banner()
    if not caption and not media_path:
        print("❌ សូមបញ្ជាក់ Caption ឬ Media Path សម្រាប់ផ្សព្វផ្សាយ!")
        return

    # Sanitize and polish caption
    polished_caption = khmer_linguistic_sanitizer.sanitize_khmer_text(caption)
    
    media_type = "text"
    if media_path:
        lower_path = media_path.lower()
        if any(lower_path.endswith(ext) for ext in [".mp4", ".mov", ".mkv", ".webm"]):
            media_type = "video"
        elif any(lower_path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            media_type = "photo"

    cfg = telegram_controller.load_config()
    chat_id = str(cfg.get("chat_id", ""))

    print("📢 [CLI BROADCAST WIZARD]")
    print(f"   • សារ / Caption: {polished_caption[:80]}..." if len(polished_caption) > 80 else f"   • សារ / Caption: {polished_caption}")
    print(f"   • Media File: {media_path or 'គ្មាន (Text Only)'}")
    print(f"   • Media Type: {media_type}")
    print(f"   • គោលដៅ: Pages={dest_pages}, Groups={dest_groups}, TikTok={dest_tiktok}")
    print("-" * 72)
    print("🚀 កំពុងចាប់ផ្ដើមការផ្សព្វផ្សាយ... សូមរង់ចាំ...")

    session = {
        "media_type": media_type,
        "media_path": media_path or "",
        "caption": polished_caption,
        "dest_pages": dest_pages,
        "dest_groups": dest_groups,
        "dest_tiktok": dest_tiktok
    }

    telegram_controller.execute_broadcast(chat_id=chat_id, message_id=0, session=session)
    print("\n✅ ការផ្សព្វផ្សាយត្រូវបានបញ្ជូនទៅកាន់ Channels រួចរាល់! សូមពិនិត្យរបាយការណ៍លើ Telegram។")

def interactive_menu():
    """បង្ហាញ Menu អន្តរកម្មសម្រាប់អ្នកប្រើប្រាស់ជ្រើសរើស"""
    while True:
        print_banner()
        print("សូមជ្រើសរើសជម្រើសខាងក្រោម:")
        print("  [1] 🌟 ចាប់ផ្ដើម Telegram Bot + Web Dashboard (ណែនាំ - Recommended)")
        print("  [2] 🤖 ចាប់ផ្ដើម Telegram Bot Only (Long-Polling)")
        print("  [3] 🌐 ចាប់ផ្ដើម Web Dashboard Only (http://localhost:8899)")
        print("  [4] 📊 ពិនិត្យស្ថានភាពគណនី និងប្រព័ន្ធ (Facebook Token, Pages, Groups)")
        print("  [5] 📢 ផ្សព្វផ្សាយរហ័សតាម CLI (Manual Direct Broadcast)")
        print("  [6] 🔄 សម្អាត Cooldown 24h គ្រប់ Facebook Groups (Reset Cooldowns)")
        print("  [7] ⚙️ ប្ដូរ Mode Facebook Pages (Toggle All Pages vs Selected Pages)")
        print("  [0] ❌ ចាកចេញ (Exit)")
        print("=" * 72)

        try:
            choice = input("👉 បញ្ចូលជម្រើសរបស់អ្នក [លំនាំដើម: 1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 លាហើយ!")
            break

        if choice in ["1", ""]:
            run_all()
            break
        elif choice == "2":
            run_telegram_bot()
            break
        elif choice == "3":
            run_web_dashboard()
            break
        elif choice == "4":
            check_status()
            input("\n👉 ចុច Enter ដើម្បីត្រឡប់ទៅ Menu ដើមវិញ...")
        elif choice == "5":
            print("\n--- [បង្កើតការផ្សាយរហ័ស] ---")
            caption_input = input("📝 បញ្ចូល Caption / សារ: ").strip()
            media_input = input("🖼️ បញ្ចូល File Path រូប/វីដេអូ ឬ URL (ចុច Enter បើគ្មាន): ").strip()
            target_input = input("🎯 ជ្រើសរើសគោលដៅ [1: ទាំងអស់ (All), 2: Pages តែប៉ុណ្ណោះ, 3: Groups តែប៉ុណ្ណោះ] [លំនាំដើម: 1]: ").strip()

            d_pages = target_input in ["1", "", "2"]
            d_groups = target_input in ["1", "", "3"]

            run_cli_broadcast(
                caption=caption_input,
                media_path=media_input if media_input else None,
                dest_pages=d_pages,
                dest_groups=d_groups,
                dest_tiktok=False
            )
            input("\n👉 ចុច Enter ដើម្បីត្រឡប់ទៅ Menu ដើមវិញ...")
        elif choice == "6":
            count = facebook_group_service.reset_all_cooldowns()
            print(f"\n✅ បានសម្អាត Cooldown 24h លើ Facebook Groups ចំនួន {count} ក្រុមជោគជ័យ! ឥឡូវគ្រប់ក្រុមអាចផុសបានភ្លាមៗ។")
            input("\n👉 ចុច Enter ដើម្បីត្រឡប់ទៅ Menu ដើមវិញ...")
        elif choice == "7":
            cfg = telegram_controller.load_config()
            curr = cfg.get("facebook_all_pages", False)
            cfg["facebook_all_pages"] = not curr
            with open(os.path.join(BASE_DIR, "config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            new_mode = "គ្រប់ Pages ទាំងអស់ (All Pages)" if cfg["facebook_all_pages"] else "Pages ដែលបានជ្រើសរើស (Selected Pages)"
            print(f"\n✅ បានផ្លាស់ប្ដូរ Facebook Pages Mode ទៅជា៖ {new_mode}")
            input("\n👉 ចុច Enter ដើម្បីត្រឡប់ទៅ Menu ដើមវិញ...")
        elif choice == "0":
            print("👋 លាហើយ! អរគុណសម្រាប់ការប្រើប្រាស់។")
            break
        else:
            print("⚠️ ជម្រើសមិនត្រឹមត្រូវ សូមជ្រើសរើសម្ដងទៀត!\n")
            time.sleep(1)

def main():
    parser = argparse.ArgumentParser(
        description="🚀 Social Media Broadcaster - Master Unified Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-a", "--all", action="store_true", help="Launch Telegram Bot + Web Dashboard concurrently")
    parser.add_argument("-b", "--bot", action="store_true", help="Launch Telegram Bot long-polling only")
    parser.add_argument("-w", "--web", action="store_true", help="Launch Web Dashboard server only")
    parser.add_argument("-s", "--status", action="store_true", help="Check Facebook tokens, Pages, Groups, and Bot health")
    parser.add_argument("-m", "--menu", action="store_true", help="Display interactive console menu")
    
    # Broadcast arguments
    parser.add_argument("-p", "--broadcast", type=str, metavar="CAPTION", help="Broadcast a message directly via CLI")
    parser.add_argument("--media", type=str, default="", help="Path or URL to photo or video for broadcast")
    parser.add_argument("--no-pages", action="store_true", help="Exclude Facebook Pages from broadcast")
    parser.add_argument("--no-groups", action="store_true", help="Exclude Facebook Groups from broadcast")
    parser.add_argument("--tiktok", action="store_true", help="Include TikTok in broadcast")

    # Server configuration
    parser.add_argument("--port", type=int, default=8899, help="Web Dashboard port (default: 8899)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Web Dashboard host (default: 0.0.0.0)")

    args = parser.parse_args()

    # Route based on flags
    if args.status:
        check_status()
    elif args.broadcast:
        run_cli_broadcast(
            caption=args.broadcast,
            media_path=args.media or None,
            dest_pages=not args.no_pages,
            dest_groups=not args.no_groups,
            dest_tiktok=args.tiktok
        )
    elif args.bot:
        run_telegram_bot()
    elif args.web:
        run_web_dashboard(host=args.host, port=args.port)
    elif args.all:
        run_all(host=args.host, port=args.port)
    elif args.menu:
        interactive_menu()
    else:
        # If run without flags, check if interactive terminal
        if sys.stdin.isatty():
            interactive_menu()
        else:
            # Non-interactive / headless environment (e.g. background service or container)
            run_all(host=args.host, port=args.port)

if __name__ == "__main__":
    main()

