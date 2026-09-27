"""Dispatch AFTER human confirmation. Telegram bot, generic webhook, or local log fallback."""
import os, json, urllib.request, urllib.parse

def dispatch(alert, out_dir):
    msg = f"[SmartCCTV] {alert['camera']} score {alert['score']} zone={alert.get('zone')} reasons={', '.join(alert['reasons'])} clip={alert.get('clip')}"
    tok, chat, hook = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"), os.getenv("WEBHOOK_URL")
    try:
        if tok and chat:
            urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                                   urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode(), timeout=10); return "telegram"
        if hook:
            urllib.request.urlopen(urllib.request.Request(hook, json.dumps(alert).encode(), {"Content-Type": "application/json"}), timeout=10); return "webhook"
    except Exception as e: msg += f" (send failed: {e})"
    open(f"{out_dir}/dispatched.log", "a").write(msg + "\n"); return "local_log"
