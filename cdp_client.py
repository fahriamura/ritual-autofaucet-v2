"""
Hermes CDP Client — connect ke Chrome di Windows via SSH tunnel.
Gak ada threading issue — Playwright connect_over_cdp().
"""
import os, sys, json, time, base64, subprocess
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    arg2 = sys.argv[3] if len(sys.argv) > 3 else ""
    
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            context = browser.new_context(no_viewport=True)
            page = context.new_page()
        else:
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
        
        page.set_default_timeout(15000)
        
        if cmd == "status":
            info = {
                "url": page.url,
                "title": page.title(),
                "text": page.evaluate("document.body.innerText")[:500],
            }
            print(json.dumps(info))
        
        elif cmd == "navigate":
            page.goto(arg, wait_until="domcontentloaded")
            time.sleep(2)
            print(json.dumps({"ok": True, "url": page.url}))
        
        elif cmd == "click":
            text = arg
            for sel in [f'text={text}', f'*:has-text("{text}")', f'button:has-text("{text}")',
                       f'a:has-text("{text}")', f'span:has-text("{text}")']:
                try:
                    el = page.locator(sel)
                    if el.count() > 0:
                        el.first.click(timeout=3000)
                        time.sleep(1)
                        print(json.dumps({"ok": True, "clicked": text}))
                        return
                except: pass
            print(json.dumps({"ok": False, "error": f"Could not click '{text}'"}))
        
        elif cmd == "type":
            text, target = arg, arg2
            if target:
                for sel in [f'input[placeholder*="{target}"]', f'input[name="{target}"]', 'input']:
                    try:
                        el = page.locator(sel)
                        if el.count() > 0:
                            el.first.fill(text)
                            print(json.dumps({"ok": True}))
                            return
                    except: pass
            page.keyboard.type(text, delay=50)
            print(json.dumps({"ok": True}))
        
        elif cmd == "screenshot":
            b = page.screenshot()
            path = f"/tmp/cdp_ss_{int(time.time())}.png"
            with open(path, "wb") as f:
                f.write(b)
            print(json.dumps({"ok": True, "path": path, "size": len(b)}))
        
        elif cmd == "press":
            page.keyboard.press(arg)
            print(json.dumps({"ok": True, "key": arg}))
        
        elif cmd == "scroll":
            d = arg or "down"
            page.evaluate(f"window.scrollBy(0, {500 if d=='down' else -500})")
            print(json.dumps({"ok": True}))
        
        elif cmd == "eval":
            r = page.evaluate(arg)
            print(json.dumps({"ok": True, "result": str(r)[:2000]}))
        
        elif cmd == "fill_form":
            # arg = "email:user@x.com,password:pass123" format
            pairs = arg.split(",")
            for pair in pairs:
                k, v = pair.split(":", 1)
                try:
                    page.locator(f'input[name="{k}"]').fill(v)
                    time.sleep(0.3)
                except: pass
            print(json.dumps({"ok": True}))
        
        else:
            print(json.dumps({"error": f"Unknown cmd: {cmd}"}))
    
    finally:
        # Don't close browser — user masih pake
        pw.stop()

if __name__ == "__main__":
    main()
