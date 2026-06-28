#!/usr/bin/env python3
"""
Browser Remote Server — single-thread HTTP, no Flask, no greenlet issues.
Responds to curl commands from Hermes.
"""
import json, time, base64, os, sys, threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

LOG = []
def log(msg, t="I"):
    p = {"I":"·", "S":"+", "W":"!", "E":"x", "C":"~", "T":"`"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {p.get(t,'·')} {msg}"
    LOG.append(line)
    if len(LOG) > 200: LOG.pop(0)
    print(line, flush=True)

# Starts here
from playwright.sync_api import sync_playwright

STATE = {"pw": None, "browser": None, "context": None, "page": None}

def page():
    return STATE.get("page")

def start_browser():
    if STATE["browser"]: return True
    try:
        pw = sync_playwright().start()
        b = pw.chromium.launch(
            headless=False,
            args=['--start-maximized','--disable-blink-features=AutomationControlled',
                  '--no-sandbox','--disable-dev-shm-usage']
        )
        ctx = b.new_context(no_viewport=True)
        p = ctx.new_page()
        p.set_default_timeout(15000)
        STATE.update(pw=pw, browser=b, context=ctx, page=p)
        log("Browser VISIBLE started!", "S")
        return True
    except Exception as e:
        log(f"Browser error: {e}", "E")
        return False

def screenshot_b64():
    p = page()
    if not p: return None
    try:
        b = p.screenshot(full_page=False)
        return base64.b64encode(b).decode()
    except: return None

def click_text(text):
    p = page()
    if not p: return False
    sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
            f'button:has-text("{text}")', f'span:has-text("{text}")']
    for w in text.split()[:3]:
        sels.extend([f'text={w}', f'*:has-text("{w}")'])
    
    for sel in sels:
        try:
            el = p.locator(sel)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=3000)
                time.sleep(0.5)
                return True
        except: pass
    
    for f in p.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")']:
            try:
                el = f.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=3000)
                    time.sleep(0.5)
                    return True
            except: pass
    return False

def type_text(text, target=None):
    p = page()
    if not p: return False
    if target:
        for sel in [f'input[placeholder*="{target}"]', 'input[type="text"]', 'input[type="email"]',
                    'input:not([type="hidden"])', 'div[contenteditable="true"]']:
            try:
                el = p.locator(sel)
                if el.count() > 0 and el.first.is_visible():
                    el.first.fill(text)
                    return True
            except: pass
    p.keyboard.type(text, delay=50)
    return True

# ── HTTP Handler ────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path.startswith("/api/status"):
                p = page()
                resp = {
                    "browser": STATE["browser"] is not None,
                    "url": p.url if p else "",
                    "title": p.title() if p else "",
                    "logs": LOG[-10:]
                }
                self._json(resp)
            
            elif self.path.startswith("/api/screenshot"):
                b64 = screenshot_b64()
                if b64:
                    self._json({"success": True, "image_base64": b64})
                else:
                    self._json({"success": False}, 500)
            
            else:
                self._json({"name": "Browser Remote Server", "status": "ok"})
        except Exception as e:
            self._json({"error": str(e)}, 500)
    
    def do_POST(self):
        try:
            length = int(self.headers.get('content-length', 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
            action = body.get("action", "")
            p = page()
            if not p:
                self._json({"success": False, "error": "Browser not ready"})
                return
            
            if action == "navigate":
                url = body.get("url", "")
                p.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                self._json({"success": True, "url": url})
            
            elif action == "click_text":
                text = body.get("text", "")
                ok = click_text(text)
                self._json({"success": ok, "text": text})
            
            elif action == "type":
                text = body.get("text", "")
                target = body.get("target", "")
                ok = type_text(text, target)
                self._json({"success": ok})
            
            elif action == "press_key":
                key = body.get("key", "Enter")
                p.keyboard.press(key)
                self._json({"success": True})
            
            elif action == "get_text":
                txt = p.evaluate("document.body.innerText")
                self._json({"success": True, "text": txt[:10000]})
            
            elif action == "wait":
                sec = int(body.get("seconds", 3))
                time.sleep(sec)
                self._json({"success": True, "waited": sec})
            
            elif action == "screenshot":
                b64 = screenshot_b64()
                self._json({"success": True, "image_base64": b64})
            
            elif action == "check_continue":
                found = False
                for txt in ["Continue in Browser", "Open in Browser", "Continue"]:
                    if click_text(txt):
                        found = True
                        break
                self._json({"success": True, "clicked_continue": found})
            
            elif action == "multi":
                results = []
                for a in body.get("actions", []):
                    at = a.get("action", "")
                    if at == "click_text":
                        results.append({"action": at, "text": a.get("text"), "ok": click_text(a.get("text",""))})
                    elif at == "wait":
                        time.sleep(int(a.get("seconds",2)))
                        results.append({"action": at})
                    elif at == "navigate":
                        p.goto(a.get("url",""), wait_until="domcontentloaded", timeout=30000)
                        results.append({"action": at})
                    elif at == "type":
                        type_text(a.get("text",""), a.get("target",""))
                        results.append({"action": at})
                    elif at == "press_key":
                        p.keyboard.press(a.get("key","Enter"))
                        results.append({"action": at})
                self._json({"success": True, "results": results})
            
            else:
                self._json({"success": False, "error": f"Unknown: {action}"})
        
        except Exception as e:
            self._json({"success": False, "error": str(e)})
    
    def _json(self, data, code=200):
        j = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(j)))
        self.end_headers()
        self.wfile.write(j)
    
    def log_message(self, format, *args):
        pass  # suppress default logging

# ── Main ────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5001"))
    log("="*50, "I")
    log("BROWSER SERVER (single-thread HTTP)", "S")
    log(f"Port {port}", "S")
    log("="*50, "I")
    
    start_browser()
    
    server = HTTPServer(("0.0.0.0", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        if STATE["browser"]: STATE["browser"].close()
        if STATE["pw"]: STATE["pw"].stop()
