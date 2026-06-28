#!/usr/bin/env python3
"""
browser_srv.py — SINGLE-THREAD browser control server
NO Flask, NO threading — pure socket. Zero greenlet errors.

Hermes controls me via: curl http://localhost:5001/...
"""
import socket, json, time, base64, os, sys, traceback
from datetime import datetime
from urllib.parse import urlparse, parse_qs

LOG = []
def log(msg, t="I"):
    p = {"I":"·","S":"+","W":"!","E":"X","C":">","T":"#","V":"*"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {p.get(t,'·')} {msg}"
    LOG.append(line)
    print(line, flush=True)

BASE = os.path.dirname(os.path.abspath(__file__))
SS_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

# ── Playwright ──────────────────────────────────────
from playwright.sync_api import sync_playwright

PW = None
BROWSER = None
CONTEXT = None
PAGE = None

def start_browser():
    global PW, BROWSER, CONTEXT, PAGE
    if BROWSER: return True
    try:
        PW = sync_playwright().start()
        BROWSER = PW.chromium.launch(
            headless=False,
            args=['--start-maximized', '--disable-blink-features=AutomationControlled',
                  '--no-sandbox', '--disable-dev-shm-usage']
        )
        CONTEXT = BROWSER.new_context(no_viewport=True)
        PAGE = CONTEXT.new_page()
        PAGE.set_default_timeout(30000)
        log("Browser VISIBLE started!", "S")
        return True
    except Exception as e:
        log(f"Browser fail: {e}", "E")
        return False

def close_browser():
    global BROWSER, PW
    try:
        if BROWSER: BROWSER.close()
        if PW: PW.stop()
    except: pass
    BROWSER = None; PW = None
    log("Browser closed", "I")

# ── Actions ──────────────────────────────────────────
def do_screenshot():
    try:
        b = PAGE.screenshot(full_page=False)
        return 200, {"image_base64": base64.b64encode(b).decode()}
    except Exception as e:
        return 500, {"error": str(e)}

def do_status():
    try:
        url = PAGE.url
        title = PAGE.title()
        text = PAGE.evaluate("document.body.innerText")[:1000]
        return 200, {"browser": True, "url": url, "title": title, "text": text}
    except Exception as e:
        return 200, {"browser": True, "error": str(e)}

def do_click(data):
    text = data.get("text", "")
    if not text:
        return 400, {"error": "no text"}
    
    # Strategy: try multiple selectors + iframes + JS
    sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
            f'button:has-text("{text}")', f'a:has-text("{text}")', f'span:has-text("{text}")']
    for w in text.split()[:3]:
        sels.extend([f'text={w}', f'*:has-text("{w}")'])
    
    for sel in sels:
        try:
            el = PAGE.locator(sel)
            if el.count() > 0:
                el.first.click(timeout=3000)
                time.sleep(1)
                return 200, {"success": True, "method": sel}
        except: pass
    
    # Iframes
    for fr in PAGE.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")']:
            try:
                el = fr.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=3000)
                    time.sleep(1)
                    return 200, {"success": True, "method": f"iframe:{sel}"}
            except: pass
    
    # JS XPath
    try:
        for w in text.split():
            r = PAGE.evaluate(f"""() => {{
                const x = document.evaluate("//*[text()[contains(., '{w}')]]", document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                if(x.singleNodeValue) {{ x.singleNodeValue.click(); return true; }}
                return false;
            }}""")
            if r: time.sleep(1); return 200, {"success": True, "method": "xpath"}
    except: pass
    
    return 200, {"success": False, "text": text}

def do_type(data):
    text = data.get("text", "")
    target = data.get("target", "")
    
    # Try to find input by target text
    if target:
        for sel in ['input[type="text"]', 'input[type="email"]', 'input[type="password"]',
                    'input:not([type="hidden"])', 'textarea', 'div[contenteditable="true"]',
                    'div[role="textbox"]']:
            try:
                el = PAGE.locator(sel)
                if el.count() > 0:
                    el.first.click()
                    time.sleep(0.3)
                    el.first.fill(text)
                    time.sleep(0.5)
                    return 200, {"success": True}
            except: pass
    
    # Keyboard type
    PAGE.keyboard.type(text, delay=50)
    time.sleep(0.5)
    return 200, {"success": True}

def do_navigate(data):
    url = data.get("url", "")
    if not url: return 400, {"error": "no url"}
    PAGE.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    return 200, {"success": True, "url": url}

def do_press(data):
    key = data.get("key", "Enter")
    PAGE.keyboard.press(key)
    return 200, {"success": True, "key": key}

def do_scroll(data):
    d = data.get("direction", "down")
    px = int(data.get("pixels", 500))
    if d == "down": PAGE.evaluate(f"window.scrollBy(0, {px})")
    else: PAGE.evaluate(f"window.scrollBy(0, -{px})")
    return 200, {"success": True}

def do_text():
    try:
        text = PAGE.evaluate("document.body.innerText")
        return 200, {"text": text[:10000]}
    except: return 500, {"error": "fail"}

def do_wait(data):
    sec = int(data.get("seconds", 3))
    time.sleep(sec)
    return 200, {"waited": sec}

def do_check_continue():
    """Find and click Continue in Browser"""
    for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
        for sel in [f'text={txt}', f'*:text-is("{txt}")', f'*:has-text("{txt}")']:
            try:
                el = PAGE.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=2000)
                    time.sleep(1)
                    return 200, {"clicked": True, "text": txt}
            except: pass
    return 200, {"clicked": False}


# ── HTTP ROUTER ──────────────────────────────────────
def handle_request(method, path, query, body):
    """Route HTTP request to the right action"""
    
    if path == "/" or path == "":
        return 200, {"name": "browser_srv", "version": "1.0", 
                     "actions": "status,screenshot,click,type,navigate,press,scroll,text,wait,check_continue"}
    
    elif path == "/api/status":
        return do_status()
    
    elif path == "/api/screenshot":
        return do_screenshot()
    
    elif path == "/api/action":
        action = query.get("action", [body.get("action", "")])[0] if isinstance(query.get("action"), list) else body.get("action", "")
        if not action:
            return 400, {"error": "no action"}
        
        if action == "screenshot": return do_screenshot()
        elif action == "status": return do_status()
        elif action == "click_text" or action == "click": return do_click(body)
        elif action == "click_coords":
            x = float(body.get("x", 0.5)); y = float(body.get("y", 0.5))
            vp = PAGE.viewport_size or {"width": 1920, "height": 1080}
            PAGE.mouse.click(int(x * vp["width"]), int(y * vp["height"]))
            return 200, {"success": True}
        elif action == "type": return do_type(body)
        elif action == "navigate": return do_navigate(body)
        elif action == "press_key" or action == "press": return do_press(body)
        elif action == "scroll": return do_scroll(body)
        elif action == "text" or action == "get_text": return do_text()
        elif action == "wait": return do_wait(body)
        elif action == "check_continue": return do_check_continue()
        elif action == "eval" or action == "evaluate":
            js = body.get("js", "")
            r = PAGE.evaluate(js)
            return 200, {"result": str(r)[:2000]}
        else:
            return 400, {"error": f"unknown action: {action}"}
    
    elif path == "/api/logs":
        n = int(query.get("n", [50])[0]) if isinstance(query.get("n"), list) else int(query.get("n", 50))
        return 200, {"logs": LOG[-n:]}
    
    else:
        return 404, {"error": f"not found: {path}"}


# ── HTTP Server ──────────────────────────────────────
def parse_http(data):
    """Parse raw HTTP into method, path, query, body"""
    try:
        parts = data.split(b"\r\n\r\n", 1)
        header = parts[0].decode("utf-8", errors="replace")
        body_raw = parts[1] if len(parts) > 1 else b""
        
        lines = header.split("\r\n")
        first = lines[0].split(" ")
        method = first[0]
        full_path = first[1] if len(first) > 1 else "/"
        
        parsed = urlparse(full_path)
        path = parsed.path
        query_str = parse_qs(parsed.query)
        
        body = {}
        if body_raw:
            try:
                body = json.loads(body_raw.decode("utf-8"))
            except:
                try:
                    body = dict(parse_qs(body_raw.decode("utf-8")))
                except:
                    pass
        
        return method, path, query_str, body
    except Exception as e:
        log(f"Parse error: {e}", "W")
        return "GET", "/", {}, {}

def run_server(host="0.0.0.0", port=5001):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(5)
    sock.settimeout(1.0)  # 1s timeout so we can check keyboard interrupt
    
    log(f"Listening on {host}:{port}", "S")
    
    while True:
        try:
            conn, addr = sock.accept()
            log(f"Connected: {addr[0]}", "I")
            
            try:
                conn.settimeout(10)
                data = b""
                while True:
                    try:
                        chunk = conn.recv(8192)
                        if not chunk: break
                        data += chunk
                        if b"\r\n\r\n" in data:
                            content_len = 0
                            for line in data.split(b"\r\n"):
                                if line.lower().startswith(b"content-length:"):
                                    content_len = int(line.split(b":")[1].strip())
                            if content_len == 0 or len(data.split(b"\r\n\r\n", 1)[1]) >= content_len:
                                break
                    except socket.timeout:
                        break
                
                if data:
                    method, path, query, body = parse_http(data)
                    
                    try:
                        code, result = handle_request(method, path, query, body)
                    except Exception as e:
                        code, result = 500, {"error": str(e)}
                        traceback.print_exc()
                    
                    if isinstance(result, dict):
                        result = json.dumps(result, default=str)
                    resp = f"HTTP/1.1 {code} OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\nContent-Length: {len(result.encode())}\r\n\r\n{result}"
                    conn.sendall(resp.encode())
                else:
                    conn.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            except Exception as e:
                log(f"Conn error: {e}", "W")
            finally:
                conn.close()
        
        except socket.timeout:
            continue
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Accept error: {e}", "W")
            time.sleep(0.1)
    
    sock.close()
    log("Server stopped", "I")

# ── MAIN ─────────────────────────────────────────────
if __name__ == "__main__":
    log("=" * 50, "I")
    log("BROWSER API — pure http.server", "S")
    log(f"Port 5001", "S")
    log("=" * 50, "I")
    
    start_browser()
    
    try:
        run_server("0.0.0.0", 5001)
    except KeyboardInterrupt:
        pass
    finally:
        close_browser()
