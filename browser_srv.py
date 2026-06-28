#!/usr/bin/env python3
"""
Browser API — SINGLE-THREADED HTTP server (no Flask!)
Port 5001 — Hermes controls via curl
"""
import os, sys, json, time, base64, traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
SS_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

def log(msg, t="I"):
    p = {"I":" ","S":"+","W":"*","E":"!","C":">","T":"#"}
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {p.get(t,' ')} {msg}", flush=True)

# ── Global Playwright ─────────────────────────────────
pw = None
browser = None
context = None
page = None

def start_browser():
    global pw, browser, context, page
    if browser: return
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=False,
        args=['--start-maximized', '--disable-blink-features=AutomationControlled',
              '--no-sandbox', '--disable-dev-shm-usage']
    )
    context = browser.new_context(no_viewport=True)
    page = context.new_page()
    page.set_default_timeout(15000)
    log("Browser VISIBLE started!", "S")

def close_browser():
    global pw, browser, context, page
    try:
        if browser: browser.close()
        if pw: pw.stop()
    except: pass
    browser = context = page = pw = None

def ss_path():
    p = os.path.join(SS_DIR, f"ss_{datetime.now().strftime('%H%M%S')}.png")
    page.screenshot(path=p, full_page=False)
    return p

def ss_b64():
    return base64.b64encode(page.screenshot(full_page=False)).decode()

def click_text(text):
    """Find & click element by text"""
    sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
            f'button:has-text("{text}")', f'a:has-text("{text}")', f'span:has-text("{text}")']
    if len(text.split()) > 1:
        for w in text.split()[:3]:
            sels.extend([f'text={w}', f'*:has-text("{w}")'])
    
    for sel in sels:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(timeout=3000)
                time.sleep(0.5)
                return True
        except: pass
    
    # Iframes
    for fr in page.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")']:
            try:
                el = fr.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=3000)
                    time.sleep(0.5)
                    return True
            except: pass
    
    # JS XPath
    try:
        for w in text.split():
            r = page.evaluate(f"""() => {{
                var x = document.evaluate("//*[text()[contains(., '{w}')]]", document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if(x && x.singleNodeValue) {{ x.singleNodeValue.click(); return true; }}
                return false;
            }}""")
            if r: time.sleep(0.5); return True
    except: pass
    return False

def check_continue():
    """Auto-click Continue in Browser"""
    for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
        for sel in [f'text={txt}', f'*:text-is("{txt}")', f'*:has-text("{txt}")',
                   f'span:has-text("{txt}")', f'button:has-text("{txt}")']:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=2000)
                    time.sleep(2)
                    return True
            except: pass
    # Iframes
    for fr in page.frames[1:]:
        for txt in ["Continue in Browser", "Open in Browser"]:
            try:
                el = fr.locator(f'text={txt}')
                if el.count() > 0:
                    el.first.click(timeout=2000)
                    time.sleep(2)
                    return True
            except: pass
    return False

# ── HTTP Handler ─────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._route("GET")
    
    def do_POST(self):
        self._route("POST")
    
    def _route(self, method):
        try:
            path = self.path.split("?")[0]
            
            if path == "/api/status":
                self._json({
                    "browser": browser is not None,
                    "url": page.url if page else "",
                    "title": page.title() if page else "",
                })
            
            elif path == "/api/screenshot":
                b64 = ss_b64()
                self._json({"success": True, "image_base64": b64})
            
            elif path == "/api/logs":
                self._json({"ok": True})
            
            elif path == "/api/action":
                # POST only
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode() if length else "{}"
                data = json.loads(body)
                action = data.get("action", "")
                
                if action == "screenshot":
                    b64 = ss_b64()
                    self._json({"success": True, "image_base64": b64, "len": len(b64)})
                
                elif action == "click_text":
                    text = data.get("text", "")
                    ok = click_text(text)
                    self._json({"success": ok, "text": text})
                
                elif action == "navigate":
                    url = data.get("url", "")
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(2)
                    self._json({"success": True, "url": url})
                
                elif action == "type":
                    text = data.get("text", "")
                    page.keyboard.type(text, delay=70)
                    self._json({"success": True})
                
                elif action == "fill":
                    text = data.get("text", "")
                    sel = data.get("selector", "")
                    if sel:
                        try:
                            el = page.locator(sel)
                            if el.count() > 0:
                                el.first.fill(text)
                        except: pass
                    self._json({"success": True})
                
                elif action == "press_key":
                    key = data.get("key", "Enter")
                    page.keyboard.press(key)
                    self._json({"success": True})
                
                elif action == "check_continue":
                    ok = check_continue()
                    self._json({"success": ok, "clicked": ok})
                
                elif action == "get_text":
                    txt = page.evaluate("document.body.innerText")
                    self._json({"success": True, "text": txt[:5000]})
                
                elif action == "wait":
                    sec = int(data.get("seconds", 3))
                    time.sleep(sec)
                    self._json({"success": True})
                
                elif action == "multi":
                    actions = data.get("actions", [])
                    results = []
                    for a in actions:
                        at = a.get("action", "")
                        if at == "click_text":
                            results.append({"a": "click", "ok": click_text(a.get("text",""))})
                        elif at == "type":
                            page.keyboard.type(a.get("text",""), delay=70)
                            results.append({"a": "type", "ok": True})
                        elif at == "navigate":
                            page.goto(a.get("url",""), wait_until="domcontentloaded")
                            results.append({"a": "nav", "ok": True})
                        elif at == "wait":
                            time.sleep(int(a.get("seconds",2)))
                            results.append({"a": "wait", "ok": True})
                        elif at == "check_continue":
                            results.append({"a": "cont", "ok": check_continue()})
                        elif at == "press_key":
                            page.keyboard.press(a.get("key","Enter"))
                            results.append({"a": "key", "ok": True})
                    self._json({"success": True, "results": results})
                
                elif action == "eval":
                    js = data.get("js", "")
                    r = page.evaluate(js)
                    self._json({"success": True, "result": str(r)[:2000]})
                
                else:
                    self._json({"error": f"Unknown: {action}"}, 400)
            
            else:
                self._json({"error": "Not found"}, 404)
        
        except Exception as e:
            traceback.print_exc()
            self._json({"success": False, "error": str(e)}, 500)
    
    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

# ── Main ─────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5001"))
    log("="*50)
    log("BROWSER API (single-thread HTTP)", "S")
    log(f"Port {port}", "S")
    log("="*50)
    
    start_browser()
    
    server = HTTPServer(("0.0.0.0", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        close_browser()
