#!/usr/bin/env python3
"""
browser_srv.py — Browser API Server (Flask + threading.Lock)
Hermes controls via: curl http://localhost:5001/api/...

NO greenlet issues — threading.Lock protects all Playwright calls.
"""
import os, sys, json, time, base64, threading, traceback
from datetime import datetime
from flask import Flask, jsonify, request

BASE = os.path.dirname(os.path.abspath(__file__))
SS_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

LOG = []
def log(msg, t="I"):
    p = {"I":"·","S":"+","W":"!","E":"X","C":">","T":"#","V":"*"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {p.get(t,'·')} {msg}"
    LOG.append(line); print(line, flush=True)

# ── Playwright (protected by lock) ──────────────────
from playwright.sync_api import sync_playwright

_lock = threading.Lock()
PW = None; BROWSER = None; CONTEXT = None; PAGE = None

def start_browser():
    global PW, BROWSER, CONTEXT, PAGE
    with _lock:
        if BROWSER: return True
        try:
            PW = sync_playwright().start()
            BROWSER = PW.chromium.launch(
                headless=False,
                args=['--start-maximized','--disable-blink-features=AutomationControlled',
                      '--no-sandbox','--disable-dev-shm-usage']
            )
            CONTEXT = BROWSER.new_context(no_viewport=True)
            PAGE = CONTEXT.new_page()
            PAGE.set_default_timeout(15000)
            log("Browser VISIBLE started!", "S")
            return True
        except Exception as e:
            log(f"Browser start failed: {e}", "E")
            return False

def close_browser():
    global BROWSER, CONTEXT, PAGE, PW
    with _lock:
        try:
            if BROWSER: BROWSER.close()
            if PW: PW.stop()
        except: pass
        BROWSER = CONTEXT = PAGE = PW = None

# ── Actions (all use _lock) ─────────────────────────

def _click_text(text):
    with _lock:
        if not PAGE: return False
        sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
                f'button:has-text("{text}")', f'a:has-text("{text}")']
        for w in text.split()[:3]:
            sels.extend([f'text={w}', f'*:has-text("{w}")'])
        for sel in sels:
            try:
                el = PAGE.locator(sel)
                if el.count() > 0 and el.first.is_visible():
                    el.first.click(timeout=3000)
                    time.sleep(0.5)
                    return True
            except: pass
        # iframes
        for fr in PAGE.frames[1:]:
            for sel in [f'text={text}', f'*:has-text("{text}")']:
                try:
                    el = fr.locator(sel)
                    if el.count() > 0:
                        el.first.click(timeout=3000)
                        time.sleep(0.5)
                        return True
                except: pass
        return False

def _screenshot():
    with _lock:
        if not PAGE: return None
        try:
            b = PAGE.screenshot(full_page=False)
            return base64.b64encode(b).decode()
        except: return None

def _navigate(url):
    with _lock:
        if not PAGE: return False
        PAGE.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        return True

def _get_text():
    with _lock:
        if not PAGE: return ""
        try: return PAGE.evaluate("document.body.innerText")[:10000]
        except: return ""

def _check_continue():
    with _lock:
        if not PAGE: return False
        for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
            for sel in [f'text={txt}', f'*:has-text("{txt}")']:
                try:
                    el = PAGE.locator(sel)
                    if el.count() > 0 and el.first.is_visible():
                        el.first.click(timeout=2000)
                        return True
                except: pass
        return False

# ── Flask App ───────────────────────────────────────
app = Flask(__name__)

@app.after_request
def cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    return response

@app.route("/")
def index():
    return jsonify({"name": "Browser API", "browser": BROWSER is not None,
                    "actions": "screenshot,click_text,navigate,type,press_key,scroll,check_continue,get_text,status"})

@app.route("/api/status")
def api_status():
    with _lock:
        url, title = "", ""
        if PAGE:
            try: url = PAGE.url
            except: pass
            try: title = PAGE.title()
            except: pass
    return jsonify({"browser": BROWSER is not None, "url": url, "title": title})

@app.route("/api/screenshot")
def api_screenshot():
    b64 = _screenshot()
    if not b64: return jsonify({"error": "no browser"}), 500
    return jsonify({"image_base64": b64, "length": len(b64)})

@app.route("/api/action", methods=["POST"])
def api_action():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    
    if not BROWSER:
        return jsonify({"error": "browser not started"}), 500
    
    try:
        if action == "screenshot":
            b64 = _screenshot()
            return jsonify({"image_base64": b64})
        
        elif action in ("click_text", "click"):
            text = data.get("text", "")
            if not text: return jsonify({"error": "no text"}), 400
            ok = _click_text(text)
            return jsonify({"success": ok, "text": text})
        
        elif action == "navigate":
            url = data.get("url", "")
            if not url: return jsonify({"error": "no url"}), 400
            ok = _navigate(url)
            return jsonify({"success": ok, "url": url})
        
        elif action == "type":
            text = data.get("text", "")
            with _lock:
                PAGE.keyboard.type(text, delay=50)
            return jsonify({"success": True})
        
        elif action == "press_key" or action == "press":
            key = data.get("key", "Enter")
            with _lock:
                PAGE.keyboard.press(key)
            return jsonify({"success": True, "key": key})
        
        elif action == "scroll":
            d = data.get("direction", "down")
            px = int(data.get("pixels", 500))
            with _lock:
                PAGE.evaluate(f"window.scrollBy(0, {px if d=='down' else -px})")
            return jsonify({"success": True})
        
        elif action == "check_continue":
            ok = _check_continue()
            return jsonify({"success": True, "clicked": ok})
        
        elif action == "get_text" or action == "text":
            txt = _get_text()
            return jsonify({"text": txt[:5000]})
        
        elif action == "status":
            with _lock:
                url = PAGE.url if PAGE else ""
            return jsonify({"url": url})
        
        elif action == "click_coords":
            x = float(data.get("x", 0.5))
            y = float(data.get("y", 0.5))
            with _lock:
                vp = PAGE.viewport_size or {"width": 1920, "height": 1080}
                PAGE.mouse.click(int(x * vp["width"]), int(y * vp["height"]))
            return jsonify({"success": True})
        
        elif action == "fill":
            text = data.get("text", "")
            sel = data.get("selector", "input")
            with _lock:
                el = PAGE.locator(sel).first
                el.click()
                el.fill(text)
            return jsonify({"success": True})
        
        elif action == "wait":
            sec = int(data.get("seconds", 3))
            time.sleep(sec)
            return jsonify({"success": True, "waited": sec})
        
        elif action == "evaluate" or action == "eval":
            js = data.get("js", "")
            with _lock:
                r = PAGE.evaluate(js)
            return jsonify({"result": str(r)[:2000]})
        
        elif action == "url":
            with _lock:
                u = PAGE.url if PAGE else ""
            return jsonify({"url": u})
        
        else:
            return jsonify({"error": f"unknown action: {action}"}), 400
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs")
def api_logs():
    n = int(request.args.get("n", 50))
    return jsonify({"logs": LOG[-n:]})

# ── MAIN ────────────────────────────────────────────
if __name__ == "__main__":
    log("=" * 50, "I")
    log("BROWSER API — Flask + threading.Lock", "S")
    log("Port 5001", "S")
    log("=" * 50, "I")
    
    start_browser()
    
    try:
        app.run(host="0.0.0.0", port=5001, debug=False, use_reloader=False, threaded=True)
    finally:
        close_browser()
