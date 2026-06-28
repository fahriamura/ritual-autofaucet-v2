#!/usr/bin/env python3
"""
bridge.py — menerima perintah via stdin, jalanin Playwright, return hasil via stdout
Format: JSON lines — kirim JSON, terima JSON
CMD: {"action":"screenshot"} → {"ok":true, "image_base64":"..."}
     {"action":"click_text", "text":"Log In"} → {"ok":true}
     {"action":"navigate", "url":"https://..."} → {"ok":true}
     {"action":"type", "text":"hello"}
     {"action":"status"} → {"url":"...", "title":"..."}
"""
import sys, json, base64, time, os
from playwright.sync_api import sync_playwright

# Start browser
pw = sync_playwright().start()
browser = pw.chromium.launch(
    headless=False,
    args=['--start-maximized']
)
page = browser.new_page()

# Signal ready
print(json.dumps({"ok": True, "status": "ready", "url": "about:blank"}), flush=True)

# Command loop
for line in sys.stdin:
    line = line.strip()
    if not line or line == "exit":
        break
    
    try:
        cmd = json.loads(line) if line.startswith("{") else {"action": line}
        action = cmd.get("action", "")

        if action == "screenshot":
            b = page.screenshot(full_page=False)
            b64 = base64.b64encode(b).decode()
            print(json.dumps({"ok": True, "image_base64": b64, "size": len(b)}), flush=True)

        elif action == "navigate":
            url = cmd.get("url", cmd.get("text", ""))
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            print(json.dumps({"ok": True, "url": page.url}), flush=True)

        elif action == "click_text":
            text = cmd.get("text", "")
            if not text:
                print(json.dumps({"ok": False, "error": "no text"}), flush=True)
                continue
            sel = page.get_by_text(text, exact=False)
            if sel.count() > 0:
                sel.first.click(timeout=5000)
                time.sleep(1)
                print(json.dumps({"ok": True, "clicked": text}), flush=True)
            else:
                print(json.dumps({"ok": False, "not_found": text}), flush=True)

        elif action == "type":
            text = cmd.get("text", "")
            page.keyboard.type(text, delay=50)
            print(json.dumps({"ok": True, "typed": text}), flush=True)

        elif action == "status":
            info = {
                "url": page.url,
                "title": page.title() if page.url else "",
                "text": page.evaluate("document.body.innerText")[:1000]
            }
            print(json.dumps({"ok": True, **info}), flush=True)

        elif action == "wait":
            sec = cmd.get("seconds", 3)
            time.sleep(sec)
            print(json.dumps({"ok": True, "waited": sec}), flush=True)

        elif action == "press":
            key = cmd.get("key", "Enter")
            page.keyboard.press(key)
            print(json.dumps({"ok": True, "key": key}), flush=True)

        elif action == "close":
            break

        else:
            print(json.dumps({"ok": False, "error": f"unknown: {action}"}), flush=True)

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), flush=True)

# Cleanup
browser.close()
pw.stop()
print(json.dumps({"ok": True, "status": "closed"}), flush=True)
