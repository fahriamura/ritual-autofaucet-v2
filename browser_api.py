#!/usr/bin/env python3
"""
Browser API Server — REST API untuk kontrol browser + AI Vision
Port 5001 — semua endpoint JSON

Endpoints:
  POST /api/browser/action   — universal: screenshot, click, type, navigate, dll
  GET  /api/browser/status   — browser state
  POST /api/browser/ai_click — AI vision decides + clicks
  POST /api/browser/ai_step  — full AI-driven step
  GET  /api/logs              — recent logs
"""
import os, sys, json, time, base64, io, threading, traceback
from datetime import datetime
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

# ── Paths ────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ── Logging ──────────────────────────────────────────
LOG_BUF = []
def log(msg, type="I"):
    prefix = {"I": "ℹ️", "S": "✅", "W": "⚠️", "E": "❌", "V": "👁️", "C": "🖱️", "T": "⌨️"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {prefix.get(type,'ℹ️')} {msg}"
    LOG_BUF.append(line)
    if len(LOG_BUF) > 500:
        LOG_BUF.pop(0)
    print(line, flush=True)

def get_logs(n=50):
    return LOG_BUF[-n:]

# ── Global state ─────────────────────────────────────
browser_state = {
    "browser": None,
    "context": None,
    "page": None,
    "playwright": None,
    "running": False,
    "current_step": "idle",
    "current_account": 0,
    "total_accounts": 0,
}

# ── Vision AI ────────────────────────────────────────
try:
    from ai_vision import VisionAI
    vision = VisionAI()
    log("VisionAI loaded", "S")
except Exception as e:
    log(f"VisionAI not available: {e}", "W")
    vision = None


# ══════════════════════════════════════════════════════
# BROWSER MANAGEMENT
# ══════════════════════════════════════════════════════

def start_browser():
    """Launch visible Chromium via Playwright"""
    if browser_state["browser"]:
        return True
    
    try:
        from playwright.sync_api import sync_playwright
        
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=False,
            args=[
                '--start-maximized',
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(30000)
        
        browser_state["playwright"] = pw
        browser_state["browser"] = browser
        browser_state["context"] = context
        browser_state["page"] = page
        
        log("Browser VISIBLE started ✅", "S")
        return True
    except Exception as e:
        log(f"Browser start failed: {e}", "E")
        traceback.print_exc()
        return False

def close_browser():
    """Close browser"""
    try:
        if browser_state["browser"]:
            browser_state["browser"].close()
        if browser_state["playwright"]:
            browser_state["playwright"].stop()
    except:
        pass
    browser_state["browser"] = None
    browser_state["context"] = None
    browser_state["page"] = None
    browser_state["playwright"] = None
    log("Browser closed", "I")

def get_page():
    """Get current page, start browser if needed"""
    if not browser_state["page"]:
        if not start_browser():
            return None
    return browser_state["page"]


# ══════════════════════════════════════════════════════
# SCREENSHOT
# ══════════════════════════════════════════════════════

def take_screenshot(name=None):
    """Take screenshot, return path"""
    page = get_page()
    if not page:
        return None
    
    fname = name or f"screenshot_{datetime.now().strftime('%H%M%S')}.png"
    path = os.path.join(SCREENSHOT_DIR, fname)
    try:
        page.screenshot(path=path, full_page=False)
        log(f"📸 Screenshot saved: {fname}", "V")
        return path
    except Exception as e:
        log(f"Screenshot failed: {e}", "E")
        return None

def screenshot_b64():
    """Take screenshot, return base64"""
    page = get_page()
    if not page:
        return None
    
    try:
        b = page.screenshot(full_page=False)
        return base64.b64encode(b).decode("utf-8")
    except Exception as e:
        log(f"Screenshot b64 failed: {e}", "E")
        return None


# ══════════════════════════════════════════════════════
# CLICK — AI Vision Driven
# ══════════════════════════════════════════════════════

def click_by_text(text, partial=True):
    """Click element containing specified text — try multiple strategies"""
    page = get_page()
    if not page:
        return False
    
    strategies = []
    
    if partial:
        strategies = [
            f'text={text}',
            f'*:text-is("{text}")',
            f'*:has-text("{text}")',
            f'button:has-text("{text}")',
            f'a:has-text("{text}")',
            f'span:has-text("{text}")',
            f'[role="button"]:has-text("{text}")',
            f'input[value*="{text}"]',
        ]
        # Also try words
        words = text.split()
        if len(words) > 1:
            for w in words[:3]:
                strategies.append(f'text={w}')
                strategies.append(f'*:has-text("{w}")')
    else:
        strategies = [f'text="{text}"', f'*:text-is("{text}")']
    
    # Try main page
    for sel in strategies:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(timeout=5000)
                log(f"🖱️ Clicked '{text}' via '{sel}'", "C")
                time.sleep(1)
                return True
        except:
            pass
    
    # Try all iframes
    try:
        for frame in page.frames[1:]:
            for sel in [f'text={text}', f'*:has-text("{text}")', f'span:has-text("{text}")']:
                try:
                    el = frame.locator(sel)
                    if el.count() > 0:
                        el.first.click(timeout=5000)
                        log(f"🖱️ Clicked '{text}' in iframe '{frame.name}'", "C")
                        time.sleep(1)
                        return True
                except:
                    pass
    except:
        pass
    
    # JS XPath fallback
    try:
        clicked = page.evaluate(f"""() => {{
            const texts = [{', '.join(f'"{w}"' for w in text.split())}];
            for (const t of texts) {{
                const xpath = `//*[text()[contains(., '${{t}}')]]`;
                const r = document.evaluate(xpath, document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if (r.singleNodeValue) {{ r.singleNodeValue.click(); return true; }}
            }}
            return false;
        }}""")
        if clicked:
            log(f"🖱️ JS XPath clicked '{text}'", "C")
            time.sleep(1)
            return True
    except:
        pass
    
    log(f"⚠️ Could not find '{text}' to click", "W")
    return False

def click_by_coords(x, y):
    """Click at screen fraction coordinates (0-1 range)"""
    page = get_page()
    if not page:
        return False
    
    try:
        viewport = page.viewport_size
        if viewport:
            px = int(x * viewport['width'])
            py = int(y * viewport['height'])
            page.mouse.click(px, py)
            log(f"🖱️ Clicked at ({x:.2f}, {y:.2f}) → ({px}, {py})px", "C")
            time.sleep(1)
            return True
        else:
            page.mouse.click(int(x * 1920), int(y * 1080))
            return True
    except Exception as e:
        log(f"Coord click failed: {e}", "W")
        return False


# ══════════════════════════════════════════════════════
# AI VISION CLICK
# ══════════════════════════════════════════════════════

def ai_vision_click(instruction="What should I click next?"):
    """Use AI vision to analyze screenshot and click the right element"""
    if not vision:
        log("Vision AI not available", "W")
        return {"success": False, "error": "Vision AI not configured"}
    
    # Take screenshot
    ss_path = take_screenshot()
    if not ss_path:
        return {"success": False, "error": "Screenshot failed"}
    
    # Analyze with AI
    result = vision.analyze(ss_path, instruction)
    if not result:
        return {"success": False, "error": "AI vision analysis failed"}
    
    action = result.get("action", "")
    target = result.get("target_text", "")
    
    if action == "click" and target:
        success = click_by_text(target)
        return {
            "success": success,
            "action": action,
            "target": target,
            "reason": result.get("reason", ""),
            "observation": result.get("observation", ""),
        }
    elif action == "click" and result.get("target_coords"):
        c = result["target_coords"]
        success = click_by_coords(c.get("x", 0.5), c.get("y", 0.5))
        return {"success": success, "action": "click_coords", "coord": c}
    elif action in ("wait", "skip_account", "done"):
        return {"success": True, "action": action, "reason": result.get("reason", "")}
    elif action == "type":
        return {"success": False, "action": "type", "needs_type": result.get("type_text", ""), "target": target}
    elif action == "navigate":
        return {"success": False, "action": "navigate", "url": result.get("url", "")}
    elif action == "press_key":
        return {"success": False, "action": "press_key", "key": result.get("key", "Enter")}
    else:
        return {"success": False, "action": action, "target": target}


# ══════════════════════════════════════════════════════
# FLASK APP
# ══════════════════════════════════════════════════════

app = Flask(__name__)
CORS(app)


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "Browser API + AI Vision",
        "version": "2.0",
        "status": "running" if browser_state["browser"] else "idle",
        "endpoints": {
            "POST /api/browser/action": "browser actions",
            "GET /api/browser/status": "browser state",
            "POST /api/browser/ai_click": "AI vision click",
            "POST /api/browser/ai_step": "full AI step",
            "GET /api/logs": "recent logs",
        }
    })


@app.route("/api/browser/status", methods=["GET"])
def api_status():
    page = get_page()
    url = ""
    title = ""
    if page:
        try:
            url = page.url
            title = page.title()
        except:
            pass
    
    return jsonify({
        "browser_running": browser_state["browser"] is not None,
        "url": url,
        "title": title,
        "current_step": browser_state["current_step"],
        "running": browser_state["running"],
        "screenshots_dir": SCREENSHOT_DIR,
    })


@app.route("/api/browser/action", methods=["POST"])
def api_action():
    """Universal browser action endpoint"""
    data = request.get_json(silent=True) or {}
    action = data.get("action", "screenshot")
    page = get_page()
    
    if not page:
        return jsonify({"success": False, "error": "Browser not started"}), 400
    
    try:
        if action == "screenshot":
            b64 = screenshot_b64()
            return jsonify({"success": True, "image_base64": b64,
                           "image_length": len(b64) if b64 else 0})
        
        elif action == "click_text":
            text = data.get("text", "")
            partial = data.get("partial", True)
            if not text:
                return jsonify({"success": False, "error": "No text provided"}), 400
            ok = click_by_text(text, partial)
            return jsonify({"success": ok, "action": "click_text", "target": text})
        
        elif action == "click_coords":
            x = float(data.get("x", 0.5))
            y = float(data.get("y", 0.5))
            ok = click_by_coords(x, y)
            return jsonify({"success": ok, "action": "click_coords", "x": x, "y": y})
        
        elif action == "type":
            text = data.get("text", "")
            target = data.get("target", "")
            
            # Click target first if specified
            if target:
                click_by_text(target, partial=True)
                time.sleep(0.5)
            
            # Focus and type
            try:
                # Try to type into active/focused element
                page.keyboard.type(text, delay=50)
                log(f"⌨️ Typed: '{text[:50]}'", "T")
                return jsonify({"success": True, "action": "type"})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 400
        
        elif action == "fill":
            """Type into a specific element by selector/text"""
            text = data.get("text", "")
            selector = data.get("selector", "")
            target_text = data.get("target", "")
            
            locator = None
            if selector:
                locator = page.locator(selector)
            elif target_text:
                # Find input near this text
                for sel in [f'input:has-text("{target_text}")',
                           f'input[placeholder*="{target_text}"]',
                           f'textarea:has-text("{target_text}")',
                           f'[contenteditable="true"]',
                           'input[type="text"]',
                           'input[type="email"]',
                           'input[type="password"]',
                           'input:not([type="hidden"])']:
                    try:
                        l = page.locator(sel)
                        if l.count() > 0:
                            locator = l.first
                            break
                    except:
                        pass
            
            if locator:
                locator.click()
                time.sleep(0.2)
                locator.fill(text)
                log(f"⌨️ Filled '{text[:30]}'", "T")
                return jsonify({"success": True})
            else:
                # Fallback: type keyboard
                page.keyboard.type(text, delay=50)
                return jsonify({"success": True, "fallback": "keyboard_type"})
        
        elif action == "navigate":
            url = data.get("url", "")
            if not url:
                return jsonify({"success": False, "error": "No URL"}), 400
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            log(f"🌐 Navigated to {url}", "I")
            return jsonify({"success": True, "url": url})
        
        elif action == "press_key":
            key = data.get("key", "Enter")
            page.keyboard.press(key)
            log(f"⌨️ Pressed key: {key}", "T")
            return jsonify({"success": True, "key": key})
        
        elif action == "scroll":
            direction = data.get("direction", "down")
            if direction == "down":
                page.evaluate("window.scrollBy(0, 500)")
            else:
                page.evaluate("window.scrollBy(0, -500)")
            return jsonify({"success": True, "direction": direction})
        
        elif action == "get_text":
            text = page.evaluate("document.body.innerText")
            return jsonify({"success": True, "text": text[:5000]})
        
        elif action == "wait":
            sec = int(data.get("seconds", 3))
            time.sleep(sec)
            return jsonify({"success": True, "waited": sec})
        
        elif action == "evaluate":
            js = data.get("js", "")
            result = page.evaluate(js)
            return jsonify({"success": True, "result": str(result)[:1000]})
        
        else:
            return jsonify({"success": False, "error": f"Unknown action: {action}"}), 400
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/browser/ai_click", methods=["POST"])
def api_ai_click():
    """AI vision decides what to click and does it"""
    data = request.get_json(silent=True) or {}
    instruction = data.get("instruction", "What should I click next?")
    context = data.get("context", "")
    
    full_instruction = context + "\n\n" + instruction if context else instruction
    result = ai_vision_click(full_instruction)
    
    return jsonify(result)


@app.route("/api/browser/ai_step", methods=["POST"])
def api_ai_step():
    """Full AI-driven step: look → decide → execute → return result"""
    data = request.get_json(silent=True) or {}
    context = data.get("context", "Automate the Ritual faucet flow")
    
    # 1. Take screenshot
    ss_path = take_screenshot("ai_step.png")
    if not ss_path:
        return jsonify({"success": False, "error": "Screenshot failed"})
    
    screenshot_b64_data = screenshot_b64()
    
    # 2. Analyze with vision (if available)
    ai_result = None
    if vision:
        instruction = f"""Current automation step: {browser_state.get('current_step', 'unknown')}

Context: {context}

Look at the screenshot. What should the automation do NEXT?
- If you see "Continue in Browser" or "Open in Browser" → CLICK it
- If you see a login form → type credentials
- If you see captcha/verification → WAIT (user solves)
- If already on correct page → describe what to click next
- If already verified / duplicate → SKIP_ACCOUNT
- If complete → DONE"""
        
        ai_result = vision.analyze(ss_path, instruction)
    
    # Return full state
    return jsonify({
        "success": True,
        "screenshot_base64": screenshot_b64_data,
        "ai_analysis": ai_result,
        "browser_url": get_page().url if get_page() else "",
        "browser_title": get_page().title() if get_page() else "",
        "current_step": browser_state.get("current_step", "idle"),
    })


@app.route("/api/browser/screenshot", methods=["GET"])
def api_screenshot():
    """Get current screenshot as PNG"""
    b64 = screenshot_b64()
    if not b64:
        return jsonify({"success": False}), 500
    return jsonify({"success": True, "image_base64": b64})


@app.route("/api/browser/start", methods=["POST"])
def api_start_browser():
    ok = start_browser()
    return jsonify({"success": ok})


@app.route("/api/browser/stop", methods=["POST"])
def api_stop_browser():
    browser_state["running"] = False
    close_browser()
    return jsonify({"success": True})


@app.route("/api/logs", methods=["GET"])
def api_logs():
    n = request.args.get("n", 50, type=int)
    return jsonify({"logs": get_logs(n), "total": len(LOG_BUF)})


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5001"))
    log(f"🚀 Browser API Server starting on port {port}...", "S")
    log(f"📸 Screenshots: {SCREENSHOT_DIR}", "I")
    
    # Auto-start browser
    start_browser()
    
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    finally:
        close_browser()
