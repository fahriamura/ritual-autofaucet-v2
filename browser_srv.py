#!/usr/bin/env python3
"""
Browser HTTP Server — single-thread, no Flask, no greenlet conflict
Port 5001 — pure http.server + Playwright
"""
import os, sys, json, time, base64, traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
SS_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

LOG = []
def log(msg, t="I"):
    p = {"I":"·","S":"+","W":"!","E":"X","C":"*","T":"\""}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {p.get(t,'·')} {msg}"
    LOG.append(line); print(line, flush=True)

# Playwright — launched once
pw = None; browser = None; context = None; page = None

from playwright.sync_api import sync_playwright

def start():
    global pw, browser, context, page
    if browser: return
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, args=['--start-maximized','--disable-blink-features=AutomationControlled','--no-sandbox'])
    context = browser.new_context(no_viewport=True)
    page = context.new_page()
    page.set_default_timeout(15000)
    log("Browser VISIBLE started!", "S")

def shutdown():
    try:
        if browser: browser.close()
        if pw: pw.stop()
    except: pass

def act_screenshot():
    try:
        b = page.screenshot(full_page=False)
        return base64.b64encode(b).decode()
    except Exception as e:
        log(f"screenshot error: {e}", "X")
        return None

def act_click_text(text):
    sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
            f'button:has-text("{text}")', f'a:has-text("{text}")', f'span:has-text("{text}")']
    for w in text.split()[:3]:
        sels.extend([f'text={w}', f'*:has-text("{w}")'])
    for sel in sels:
        try:
            el = page.locator(sel)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=3000)
                time.sleep(0.5)
                return True
        except: pass
    for fr in page.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")']:
            try:
                el = fr.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=3000)
                    time.sleep(0.5)
                    return True
            except: pass
    return False

def act_type(text, target=None):
    if target:
        for sel in [f'input:has-text("{target}")', 'input[type="text"]', 'input[type="email"]',
                    'input[type="password"]', 'input:not([type="hidden"])', 'textarea',
                    'div[contenteditable="true"]', 'div[role="textbox"]']:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(); time.sleep(0.2)
                    el.first.fill(text); time.sleep(0.3)
                    return True
            except: pass
    page.keyboard.type(text, delay=50); time.sleep(0.3)
    return True

def act_navigate(url):
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    return True

def act_check_continue():
    for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
        for sel in [f'text={txt}', f'*:text-is("{txt}")', f'*:has-text("{txt}")']:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=2000)
                    time.sleep(1)
                    return True
            except: pass
    return False

def get_status():
    try:
        return json.dumps({
            "browser": browser is not None,
            "url": page.url,
            "title": page.title(),
            "text": page.evaluate("document.body.innerText")[:2000]
        })
    except:
        return json.dumps({"browser": browser is not None, "error": "page not ready"})

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silent
    
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        if isinstance(body, str): body = body.encode()
        self.wfile.write(body)
    
    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/api/status":
            self._send(200, get_status())
        elif p.path == "/api/screenshot":
            b64 = act_screenshot()
            self._send(200, json.dumps({"success": True, "image_base64": b64}) if b64 else json.dumps({"success": False}))
        elif p.path == "/api/logs":
            n = int(parse_qs(p.query).get("n", [50])[0])
            self._send(200, json.dumps({"logs": LOG[-n:]}))
        else:
            self._send(200, json.dumps({
                "name": "Browser Server",
                "endpoints": ["GET /api/status", "GET /api/screenshot", "GET /api/logs", "POST /api/action"]
            }))
    
    def do_POST(self):
        try:
            cl = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(cl) if cl else b"{}"
            data = json.loads(raw.decode())
        except:
            data = {}
        
        p = urlparse(self.path)
        
        if p.path == "/api/action":
            action = data.get("action", "")
            try:
                if action == "screenshot":
                    b64 = act_screenshot()
                    self._send(200, json.dumps({"success": True, "image_base64": b64}))
                elif action == "click_text":
                    txt = data.get("text", "")
                    ok = act_click_text(txt)
                    self._send(200, json.dumps({"success": ok, "text": txt}))
                elif action == "type":
                    txt = data.get("text", "")
                    target = data.get("target", "")
                    ok = act_type(txt, target)
                    self._send(200, json.dumps({"success": ok}))
                elif action == "navigate":
                    url = data.get("url", "")
                    act_navigate(url)
                    self._send(200, json.dumps({"success": True, "url": url}))
                elif action == "press_key":
                    k = data.get("key", "Enter")
                    page.keyboard.press(k)
                    self._send(200, json.dumps({"success": True, "key": k}))
                elif action == "scroll":
                    d = data.get("direction", "down")
                    page.evaluate(f"window.scrollBy(0, {500 if d=='down' else -500})")
                    self._send(200, json.dumps({"success": True}))
                elif action == "get_text":
                    txt = page.evaluate("document.body.innerText")
                    self._send(200, json.dumps({"success": True, "text": txt[:10000]}))
                elif action == "wait":
                    sec = int(data.get("seconds", 3))
                    time.sleep(sec)
                    self._send(200, json.dumps({"success": True, "waited": sec}))
                elif action == "check_continue":
                    found = act_check_continue()
                    self._send(200, json.dumps({"success": True, "clicked": found}))
                elif action == "evaluate":
                    js = data.get("js", "")
                    r = page.evaluate(js)
                    self._send(200, json.dumps({"success": True, "result": str(r)[:2000]}))
                else:
                    self._send(400, json.dumps({"success": False, "error": f"unknown: {action}"}))
            except Exception as e:
                self._send(500, json.dumps({"success": False, "error": str(e)[:500]}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5001"))
    log("="*50)
    log("BROWSER SERVER (single-thread HTTP)", "S")
    log(f"Port {port}", "S")
    log("="*50)
    
    start()
    srv = HTTPServer(("0.0.0.0", port), Handler)
    try:
        srv.serve_forever()
    finally:
        srv.server_close()
        shutdown()
