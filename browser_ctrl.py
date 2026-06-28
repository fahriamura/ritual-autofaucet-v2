"""Browser controller — dijalankan via xvfb-run"""
import json, base64, time, os, sys
from playwright.sync_api import sync_playwright

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    page = browser.new_page()
    page.set_default_timeout(30000)
    
    # Navigate to Discord
    print("[STEP] Navigating to Discord login...", flush=True)
    page.goto("https://discord.com/login", wait_until="domcontentloaded")
    time.sleep(3)
    
    # Screenshot
    ss = page.screenshot()
    img_b64 = base64.b64encode(ss).decode()
    
    # Page info
    info = {
        "url": page.url,
        "title": page.title(),
        "text": page.evaluate("document.body.innerText")[:1000],
    }
    
    result = {
        "status": "ok",
        "screenshot_base64": img_b64,
        "info": info,
    }
    
    print(json.dumps(result), flush=True)
    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
