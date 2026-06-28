#!/usr/bin/env python3
"""
Browser Server — pure Python http.server, NO Flask/threading conflicts
Runs on Windows, controlled via SSH tunnel from Hermes on Linux
"""
import sys, os, json, time, base64, traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from playwright.sync_api import sync_playwright

PORT = 5001
SS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

STATE = {"pw": None, "browser": None, "context": None, "page": None}

def log(msg, t="I"):
    p = {"I":"·","S":"+","W":"!","E":"X","C":"*","T":"~","V":"#"}
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {p.get(t,'·')} {msg}", flush=True)

def start_browser():
    if STATE["browser"]: return True
    pw = sync_playwright().start()
    b = pw.chromium.launch(
        headless=False,
        args=['--disable-blink-features=AutomationControlled','--no-sandbox']
    )
    ctx = b.new_context(no_viewport=True)
    p = ctx.new_page()
    p.set_default_timeout(30000)
    STATE.update(pw=pw, browser=b, context=ctx, page=p)
    log("Browser VISIBLE started!", "S")
    return True

def page(): return STATE["page"]

# ═══════════════════════════════════════════════════
# HANDLER
# ═══════════════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # silent

    def _ok(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _err(self, msg, code=500):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(json.dumps({"success": False, "error": msg}).encode())

    def _read(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length)) if length else {}
        except:
            return {}

    def do_GET(self):
        p = page()
        if not p:
            self._err("Browser not started")
            return

        if self.path == "/api/status":
            try:
                text = p.evaluate("document.body.innerText")
                self._ok({"url": p.url, "title": p.title(),
                          "text": text[:3000], "browser": True})
            except Exception as e:
                self._err(str(e))

        elif self.path == "/api/screenshot":
            try:
                path = os.path.join(SS_DIR, f"ss_{datetime.now().strftime('%H%M%S')}.png")
                p.screenshot(path=path, full_page=False)
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                self._ok({"image_base64": b64, "path": path})
            except Exception as e:
                self._err(str(e))

        elif self.path.startswith("/api/check_continue"):
            found = False
            for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
                for sel in [f'text={txt}', f'*:has-text("{txt}")', f'span:has-text("{txt}")']:
                    try:
                        el = p.locator(sel)
                        if el.count() > 0 and el.first.is_visible():
                            el.first.click(timeout=2000)
                            time.sleep(2)
                            found = True
                            break
                    except: pass
                if found: break
            if not found:
                for fr in p.frames[1:]:
                    for txt in ["Continue in Browser", "Open in Browser"]:
                        try:
                            el = fr.locator(f'text={txt}')
                            if el.count() > 0:
                                el.first.click(timeout=2000)
                                time.sleep(2)
                                found = True
                                break
                        except: pass
                    if found: break
            self._ok({"clicked_continue": found})

        else:
            self._err(f"Unknown GET: {self.path}", 404)

    def do_POST(self):
        p = page()
        if not p:
            self._err("Browser not started")
            return
        data = self._read()
        action = data.get("action", "")

        try:
            if action == "navigate":
                url = data.get("url", "")
                p.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                log(f"# {url[:60]}", "V")
                self._ok({"success": True})

            elif action == "click_text":
                text = data.get("text", "")
                found = False
                sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
                        f'button:has-text("{text}")', f'a:has-text("{text}")',
                        f'span:has-text("{text}")', f'[role="button"]:has-text("{text}")']
                for w in text.split()[:3]:
                    sels.extend([f'text={w}', f'*:has-text("{w}")'])
                for sel in sels:
                    try:
                        el = p.locator(sel)
                        if el.count() > 0 and el.first.is_visible():
                            el.first.click(timeout=3000)
                            time.sleep(1)
                            found = True
                            break
                    except: pass
                if not found:
                    for fr in p.frames[1:]:
                        for sel in [f'text={text}', f'*:has-text("{text}")']:
                            try:
                                el = fr.locator(sel)
                                if el.count() > 0:
                                    el.first.click(timeout=3000)
                                    time.sleep(1)
                                    found = True
                                    break
                            except: pass
                        if found: break
                log(f"* click '{text}' = {found}", "C")
                self._ok({"success": found, "text": text})

            elif action == "type":
                text = data.get("text", "")
                target = data.get("target", "")
                if target:
                    for sel in [f'input:has-text("{target}")', 'input[type="text"]',
                                'input[type="email"]', 'input[type="password"]',
                                'input:not([type="hidden"])', 'textarea',
                                'div[contenteditable="true"]', 'div[role="textbox"]']:
                        try:
                            el = p.locator(sel).first
                            if el.is_visible():
                                el.click()
                                time.sleep(0.3)
                                el.fill(text)
                                break
                        except: pass
                else:
                    p.keyboard.type(text, delay=50)
                log(f"~ typed '{text[:30]}'", "T")
                self._ok({"success": True})

            elif action == "fill":
                text = data.get("text", "")
                sel = data.get("selector", "input")
                try:
                    el = p.locator(sel).first
                    el.fill(text)
                    self._ok({"success": True})
                except:
                    self._ok({"success": False, "error": str(traceback.format_exc())})

            elif action == "press_key":
                key = data.get("key", "Enter")
                p.keyboard.press(key)
                self._ok({"success": True})

            elif action == "scroll":
                d = data.get("direction", "down")
                p.evaluate(f"window.scrollBy(0, {500 if d == 'down' else -500})")
                self._ok({"success": True})

            elif action == "check_continue":
                found = False
                for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
                    for sel in [f'text={txt}', f'*:has-text("{txt}")', f'span:has-text("{txt}")']:
                        try:
                            el = p.locator(sel)
                            if el.count() > 0 and el.first.is_visible():
                                el.first.click(timeout=2000)
                                time.sleep(2)
                                found = True
                                break
                        except: pass
                    if found: break
                if not found:
                    for fr in p.frames[1:]:
                        for txt in ["Continue in Browser", "Open in Browser"]:
                            try:
                                el = fr.locator(f'text={txt}')
                                if el.count() > 0:
                                    el.first.click(timeout=2000)
                                    time.sleep(2)
                                    found = True
                                    break
                            except: pass
                        if found: break
                self._ok({"clicked_continue": found})

            elif action == "wait":
                time.sleep(int(data.get("seconds", 3)))
                self._ok({"success": True})

            else:
                self._err(f"Unknown: {action}")

        except Exception as e:
            self._err(str(e))

# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    log("="*50, "I")
    log("BROWSER API (single-thread HTTP)", "S")
    log(f"Port {PORT}", "S")
    log("="*50, "I")
    
    start_browser()
    
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down...", "I")
        server.shutdown()
