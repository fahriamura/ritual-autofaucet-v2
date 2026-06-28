#!/usr/bin/env python3
"""
Browser API — REST API kontrol Playwright Chromium
Port 5001 — gue (Hermes) yg jadi AI-nya

Endpoints:
  GET  /api/screenshot  →  screenshot PNG (base64)
  POST /api/action      →  {action, text, url, key, ...}
  GET  /api/status      →  URL, title, visible text
  POST /api/start       →  start browser
  POST /api/stop        →  close browser
  GET  /api/logs        →  recent logs
"""
import os, sys, json, time, base64, threading, traceback
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

BASE = os.path.dirname(os.path.abspath(__file__))
SS_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

LOG_BUF = []
def log(msg, type="I"):
    p = {"I":"ℹ️","S":"✅","W":"⚠️","E":"❌","C":"🖱️","T":"⌨️"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {p.get(type,'ℹ️')} {msg}"
    LOG_BUF.append(line)
    if len(LOG_BUF) > 500: LOG_BUF.pop(0)
    print(line, flush=True)

STATE = {"pw": None, "browser": None, "context": None, "page": None}

# ============================================================
# PLAYWRIGHT
# ============================================================
from playwright.sync_api import sync_playwright

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
        p.set_default_timeout(30000)
        STATE.update(pw=pw, browser=b, context=ctx, page=p)
        log("✅ Browser VISIBLE started", "S")
        return True
    except Exception as e:
        log(f"❌ Browser start: {e}", "E")
        return False

def close_browser():
    try:
        if STATE["browser"]: STATE["browser"].close()
        if STATE["pw"]: STATE["pw"].stop()
    except: pass
    STATE.update(browser=None, context=None, page=None, pw=None)
    log("Browser closed", "I")

def page():
    if not STATE["page"]: start_browser()
    return STATE["page"]

# ============================================================
# ACTIONS
# ============================================================
def take_screenshot():
    p = page()
    if not p: return None
    path = os.path.join(SS_DIR, f"ss_{datetime.now().strftime('%H%M%S')}.png")
    try:
        p.screenshot(path=path, full_page=False)
        return path
    except: return None

def screenshot_b64():
    p = page()
    if not p: return None
    try:
        b = p.screenshot(full_page=False)
        return base64.b64encode(b).decode()
    except: return None

def click_text(text, partial=True):
    p = page()
    if not p: return False
    
    # Main page
    sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
            f'button:has-text("{text}")', f'a:has-text("{text}")', f'span:has-text("{text}")']
    if partial:
        for w in text.split()[:3]:
            sels.extend([f'text={w}', f'*:has-text("{w}")'])
    
    for sel in sels:
        try:
            el = p.locator(sel)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=3000)
                time.sleep(1)
                return True
        except: pass
    
    # Iframes
    for f in p.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")']:
            try:
                el = f.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=3000)
                    time.sleep(1)
                    return True
            except: pass
    
    # JS XPath
    try:
        for w in text.split():
            r = p.evaluate(f"""() => {{
                const x = document.evaluate("//*[text()[contains(., '{w}')]]", document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if(x.singleNodeValue) {{ x.singleNodeValue.click(); return true; }}
                return false;
            }}""")
            if r: time.sleep(1); return True
    except: pass
    
    return False

def click_coords(x, y):
    """Click at fraction coords (0-1)"""
    p = page()
    if not p: return False
    try:
        vp = p.viewport_size or {"width": 1920, "height": 1080}
        px = int(x * vp["width"])
        py = int(y * vp["height"])
        p.mouse.click(px, py)
        time.sleep(1)
        return True
    except: return False

def type_text(text, target=None):
    p = page()
    if not p: return False
    
    if target:
        for sel in [f'input:has-text("{target}")', 'input[type="text"]',
                    'input[type="email"]', 'input[type="password"]',
                    'input:not([type="hidden"])', 'textarea',
                    'div[contenteditable="true"]', 'div[role="textbox"]']:
            try:
                el = p.locator(sel)
                if el.count() > 0 and el.first.is_visible():
                    el.first.click()
                    time.sleep(0.3)
                    el.first.fill(text)
                    time.sleep(0.5)
                    return True
            except: pass
    
    p.keyboard.type(text, delay=50)
    time.sleep(0.5)
    return True

# ============================================================
# FLASK
# ============================================================
app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return jsonify({
        "name": "Browser API — Hermes-controlled",
        "browser": "running" if STATE["browser"] else "idle",
        "actions": "screenshot, click_text, click_coords, type, navigate, press_key, scroll, get_text, wait"
    })

@app.route("/api/start", methods=["POST"])
def api_start():
    ok = start_browser()
    return jsonify({"success": ok})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    close_browser()
    return jsonify({"success": True})

@app.route("/api/status", methods=["GET"])
def api_status():
    p = page()
    url, title, text = "", "", ""
    if p:
        try:
            url = p.url
            title = p.title()
            text = p.evaluate("document.body.innerText")[:5000]
        except: pass
    return jsonify({"browser": STATE["browser"] is not None, "url": url, 
                    "title": title, "text": text})

@app.route("/api/screenshot", methods=["GET"])
def api_screenshot():
    b64 = screenshot_b64()
    if not b64:
        return jsonify({"success": False}), 500
    return jsonify({"success": True, "image_base64": b64,
                    "image_length": len(b64)})

@app.route("/api/screenshot_file", methods=["GET"])
def api_screenshot_file():
    """Return screenshot as downloadable file"""
    path = take_screenshot()
    if not path:
        return jsonify({"success": False}), 500
    from flask import send_file
    return send_file(path, mimetype="image/png")

@app.route("/api/action", methods=["POST"])
def api_action():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    p = page()
    if not p:
        return jsonify({"success": False, "error": "Browser not started"})
    
    try:
        if action == "screenshot":
            b64 = screenshot_b64()
            return jsonify({"success": True, "image_base64": b64})
        
        elif action == "click_text":
            text = data.get("text", "")
            if not text: return jsonify({"success": False, "error": "no text"})
            ok = click_text(text, data.get("partial", True))
            return jsonify({"success": ok, "text": text})
        
        elif action == "click_coords":
            x = float(data.get("x", 0.5))
            y = float(data.get("y", 0.5))
            ok = click_coords(x, y)
            return jsonify({"success": ok, "x": x, "y": y})
        
        elif action == "type":
            text = data.get("text", "")
            target = data.get("target", "")
            ok = type_text(text, target)
            return jsonify({"success": ok})
        
        elif action == "navigate":
            url = data.get("url", "")
            if not url: return jsonify({"success": False, "error": "no url"})
            p.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            return jsonify({"success": True, "url": url})
        
        elif action == "press_key":
            key = data.get("key", "Enter")
            p.keyboard.press(key)
            return jsonify({"success": True, "key": key})
        
        elif action == "scroll":
            d = data.get("direction", "down")
            px = int(data.get("pixels", 500))
            if d == "down": p.evaluate(f"window.scrollBy(0, {px})")
            else: p.evaluate(f"window.scrollBy(0, -{px})")
            return jsonify({"success": True, "direction": d})
        
        elif action == "get_text":
            text = p.evaluate("document.body.innerText")
            return jsonify({"success": True, "text": text[:10000]})
        
        elif action == "wait":
            sec = int(data.get("seconds", 3))
            time.sleep(sec)
            return jsonify({"success": True, "waited": sec})
        
        elif action == "evaluate":
            js = data.get("js", "")
            r = p.evaluate(js)
            return jsonify({"success": True, "result": str(r)[:2000]})
        
        elif action == "check_continue":
            """Cari & klik Continue in Browser di semua konteks"""
            found = False
            # Main page
            for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
                for sel in [f'text={txt}', f'*:text-is("{txt}")', f'*:has-text("{txt}")',
                           f'span:has-text("{txt}")']:
                    try:
                        el = p.locator(sel)
                        if el.count() > 0 and el.first.is_visible():
                            el.first.click(timeout=2000)
                            found = True
                            break
                    except: pass
                if found: break
            # Iframes
            if not found:
                for f in p.frames[1:]:
                    for txt in ["Continue in Browser", "Open in Browser"]:
                        try:
                            el = f.locator(f'text={txt}')
                            if el.count() > 0:
                                el.first.click(timeout=2000)
                                found = True
                                break
                        except: pass
                        if found: break
            # JS
            if not found:
                try:
                    p.evaluate("""() => {
                        for(const t of ['Continue in Browser','Open in Browser','Continue']) {
                            const x = document.evaluate("//*[text()[contains(., '" + t + "')]]", 
                                document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                            if(x.singleNodeValue) { x.singleNodeValue.click(); return true; }
                        }
                        return false;
                    }""")
                except: pass
            
            return jsonify({"success": True, "clicked_continue": found})
        
        elif action == "multi":
            """Execute multiple actions in sequence"""
            actions = data.get("actions", [])
            results = []
            for a in actions:
                a_type = a.get("action", "")
                if a_type == "click_text":
                    results.append({"action": "click_text", "text": a.get("text"),
                                    "success": click_text(a.get("text",""))})
                elif a_type == "type":
                    results.append({"action": "type", "text": a.get("text"),
                                    "success": type_text(a.get("text",""), a.get("target",""))})
                elif a_type == "wait":
                    time.sleep(int(a.get("seconds", 2)))
                    results.append({"action": "wait", "seconds": a.get("seconds")})
                elif a_type == "check_continue":
                    p2 = page()
                    if p2:
                        for txt in ["Continue in Browser", "Open in Browser"]:
                            try:
                                el = p2.locator(f'text={txt}')
                                if el.count() > 0:
                                    el.first.click()
                                    results.append({"action": "click_continue", "success": True})
                                    break
                            except: pass
                elif a_type == "navigate":
                    p2 = page()
                    if p2:
                        p2.goto(a.get("url",""), wait_until="domcontentloaded", timeout=30000)
                        results.append({"action": "navigate", "url": a.get("url")})
                elif a_type == "press_key":
                    p2 = page()
                    if p2:
                        p2.keyboard.press(a.get("key","Enter"))
                        results.append({"action": "press_key", "key": a.get("key")})
                elif a_type == "scroll":
                    p2 = page()
                    if p2:
                        d = a.get("direction","down")
                        p2.evaluate(f"window.scrollBy(0, {500 if d=='down' else -500})")
                        results.append({"action": "scroll", "direction": d})
            
            return jsonify({"success": True, "results": results})
        
        else:
            return jsonify({"success": False, "error": f"Unknown: {action}"})
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/logs", methods=["GET"])
def api_logs():
    n = request.args.get("n", 50, type=int)
    return jsonify({"logs": LOG_BUF[-n:], "total": len(LOG_BUF)})

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5001"))
    log("="*50, "I")
    log("🚀 BROWSER API SERVER", "S")
    log(f"📡 Port {port}", "S")
    log("🧠 AI = Hermes (vision_analyze + terminal)", "S")
    log("="*50, "I")
    
    start_browser()
    
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=False)
    finally:
        close_browser()
