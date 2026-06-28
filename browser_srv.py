#!/usr/bin/env python3
"""
Browser API — pure http.server (NO Flask)
Single Playwright instance, thread-safe request handling
"""
import os, sys, json, time, base64, threading, traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
SS_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

LOG = []
def log(msg, t="I"):
    p = {"I":"·","S":"+","W":"!","E":"x","C":">","T":"\"","V":"*"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {p.get(t,'·')} {msg}"
    LOG.append(line)
    if len(LOG) > 500: LOG.pop(0)
    print(line, flush=True)

# ============================================================
# Playwright
# ============================================================
from playwright.sync_api import sync_playwright

PLAYWRIGHT = None
BROWSER = None
CONTEXT = None
PAGE = None
LOCK = threading.Lock()

def ensure_browser():
    global PLAYWRIGHT, BROWSER, CONTEXT, PAGE
    if PLAYWRIGHT:
        return True
    try:
        PLAYWRIGHT = sync_playwright().start()
        BROWSER = PLAYWRIGHT.chromium.launch(
            headless=False,
            args=['--start-maximized', '--no-sandbox']
        )
        CONTEXT = BROWSER.new_context(no_viewport=True)
        PAGE = CONTEXT.new_page()
        PAGE.set_default_timeout(15000)
        log("Browser VISIBLE started!", "S")
        return True
    except Exception as e:
        log(f"Browser start: {e}", "E")
        return False

def get_text():
    try:
        return PAGE.evaluate("document.body.innerText")[:5000]
    except: return ""

def take_screenshot():
    path = os.path.join(SS_DIR, f"ss_{datetime.now().strftime('%H%M%S')}.png")
    try:
        PAGE.screenshot(path=path)
        return path
    except: return None

def click_by_text(text):
    sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
            f'button:has-text("{text}")', f'a:has-text("{text}")', f'span:has-text("{text}")']
    for w in text.split()[:3]:
        sels.extend([f'text={w}', f'*:has-text("{w}")'])
    
    for sel in sels:
        try:
            el = PAGE.locator(sel)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=3000)
                return True
        except: pass
    
    # Frames
    for f in PAGE.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")']:
            try:
                el = f.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=3000)
                    return True
            except: pass
    return False

# ============================================================
# HTTP Handler
# ============================================================
class Handler(BaseHTTPRequestHandler):
    
    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)
    
    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        path = urlparse(self.path).path
        
        with LOCK:
            if path == '/api/status':
                url, title = "", ""
                try:
                    url = PAGE.url
                    title = PAGE.title()
                except: pass
                self._json({"browser": True, "url": url, "title": title,
                           "text": get_text()[:500]})
            
            elif path == '/api/screenshot':
                ss = take_screenshot()
                if ss:
                    with open(ss, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    self._json({"success": True, "image_base64": b64})
                else:
                    self._json({"success": False})
            
            elif path == '/api/logs':
                self._json({"logs": LOG[-50:]})
            
            else:
                self._json({"error": "not found"}, 404)
    
    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_body()
        
        with LOCK:
            try:
                if path == '/api/action':
                    action = data.get('action', '')
                    
                    if action == 'navigate':
                        url = data.get('url', '')
                        PAGE.goto(url, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(2)
                        self._json({"success": True, "url": url})
                    
                    elif action == 'click_text':
                        text = data.get('text', '')
                        ok = click_by_text(text)
                        self._json({"success": ok, "text": text})
                    
                    elif action == 'click_coords':
                        x = float(data.get('x', 0.5))
                        y = float(data.get('y', 0.5))
                        vp = PAGE.viewport_size or {"width": 1920, "height": 1080}
                        PAGE.mouse.click(int(x*vp["width"]), int(y*vp["height"]))
                        self._json({"success": True})
                    
                    elif action == 'type':
                        text = data.get('text', '')
                        target = data.get('target', '')
                        if target:
                            click_by_text(target)
                            time.sleep(0.3)
                        # Try to find input
                        found = False
                        for sel in ['input[type="text"]', 'input[type="email"]', 
                                    'input[type="password"]', 'input:not([type="hidden"])',
                                    'textarea', 'div[contenteditable="true"]']:
                            try:
                                el = PAGE.locator(sel)
                                if el.count() > 0 and el.first.is_visible():
                                    el.first.fill(text)
                                    found = True
                                    break
                            except: pass
                        if not found:
                            PAGE.keyboard.type(text, delay=50)
                        self._json({"success": True})
                    
                    elif action == 'fill':
                        text = data.get('text', '')
                        sel = data.get('selector', '')
                        if sel:
                            try:
                                el = PAGE.locator(sel)
                                if el.count() > 0:
                                    el.first.fill(text)
                                    self._json({"success": True})
                                    return
                            except: pass
                        self._json({"success": False, "error": "no element"})
                    
                    elif action == 'press_key':
                        key = data.get('key', 'Enter')
                        PAGE.keyboard.press(key)
                        self._json({"success": True})
                    
                    elif action == 'scroll':
                        d = data.get('direction', 'down')
                        px = int(data.get('pixels', 500))
                        PAGE.evaluate(f"window.scrollBy(0, {px if d=='down' else -px})")
                        self._json({"success": True})
                    
                    elif action == 'screenshot':
                        ss = take_screenshot()
                        with open(ss, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        self._json({"success": True, "image_base64": b64})
                    
                    elif action == 'get_text':
                        self._json({"success": True, "text": get_text()})
                    
                    elif action == 'check_continue':
                        found = False
                        for txt in ["Continue in Browser", "Open in Browser", "Open App"]:
                            for sel in [f'text={txt}', f'*:text-is("{txt}")', f'span:has-text("{txt}")']:
                                try:
                                    el = PAGE.locator(sel)
                                    if el.count() > 0 and el.first.is_visible():
                                        el.first.click(timeout=2000)
                                        found = True
                                        break
                                except: pass
                            if found: break
                        if not found:
                            for f in PAGE.frames[1:]:
                                for txt in ["Continue in Browser", "Open in Browser"]:
                                    try:
                                        el = f.locator(f'text={txt}')
                                        if el.count() > 0:
                                            el.first.click(timeout=2000)
                                            found = True
                                            break
                                    except: pass
                                    if found: break
                        self._json({"success": True, "clicked": found})
                    
                    elif action == 'wait':
                        sec = int(data.get('seconds', 3))
                        time.sleep(sec)
                        self._json({"success": True})
                    
                    else:
                        self._json({"success": False, "error": f"unknown: {action}"})
                
                else:
                    self._json({"error": "not found"}, 404)
            
            except Exception as e:
                self._json({"success": False, "error": str(e)})
    
    def log_message(self, format, *args):
        msg = format % args
        if "/api/" in msg:
            log(f"HTTP: {msg}", "I")

# ============================================================
# Main
# ============================================================
from socketserver import ThreadingMixIn

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads (built-in ThreadingMixIn)"""
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5001"))
    log("="*50)
    log("BROWSER API — pure http.server", "S")
    log(f"Port {port}", "S")
    log("="*50)
    
    ensure_browser()
    
    server = ThreadedHTTPServer(("0.0.0.0", port), Handler)
    log(f"Listening on :{port}", "S")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down...")
    finally:
        if BROWSER: BROWSER.close()
        if PLAYWRIGHT: PLAYWRIGHT.stop()
