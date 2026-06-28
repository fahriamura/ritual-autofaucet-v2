#!/usr/bin/env python3
"""
Ritual AutoFaucet v3 — AI Vision Browser API
═══════════════════════════════════════════════════════
Arsitektur:
  - Playwright visible Chromium (kamu liat semua)
  - AI Vision (GPT-4o/Claude) buat liat screenshot & klik otomatis
  - REST API (port 5000) — AI external bisa connect
  - 22-step flow, skip verified, auto-loop

API Endpoints:
  POST /api/faucet/start     — mulai autofaucet
  POST /api/faucet/stop      — stop
  GET  /api/faucet/status     — current state
  POST /api/browser/action    — low-level browser control
  GET  /api/browser/ai_step   — AI vision step
  GET  /api/logs              — recent logs
"""
import os, sys, json, time, re, random, string, base64, subprocess, threading, traceback
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Config ──────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
DISCORD_FILE = os.path.join(BASE, "discord.txt")
ACCOUNTS_FILE = os.path.join(BASE, "accounts.json")
CONFIG_FILE = os.path.join(BASE, "config.json")
WALLETS_FILE = "/root/ritual_wallets.txt"
SCREENSHOT_DIR = os.path.join(BASE, "screenshots")
RPC = "https://rpc.ritualfoundation.org"
DISCORD_INVITE = "https://discord.gg/ritual-net"  # ganti sesuai invite

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ── Logging ──────────────────────────────────────────
LOG_BUF = []
def log(msg, type="I"):
    prefix = {"I": "ℹ️", "S": "✅", "W": "⚠️", "E": "❌", "V": "👁️", "C": "🖱️", "T": "⌨️", "H": "🔶"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {prefix.get(type, 'ℹ️')} {msg}"
    LOG_BUF.append(line)
    if len(LOG_BUF) > 500:
        LOG_BUF.pop(0)
    print(line, flush=True)

def get_logs(n=50):
    return LOG_BUF[-n:]

# ── Data ─────────────────────────────────────────────
def parse_discord_txt(path):
    """Parse discord.txt ke list akun"""
    accounts = []
    with open(path) as f:
        lines = f.readlines()
    for line in lines[1:]:  # skip header
        parts = line.strip().split("\t")
        if len(parts) >= 6:
            accounts.append({
                "email": parts[0].strip(),
                "password": parts[1].strip(),
                "username": parts[2].strip(),
                "email_addr": parts[3].strip(),
                "email_password": parts[4].strip(),
                "email_link": parts[5].strip(),
                "status": "pending",
                "wallet": "",
                "github": "",
            })
    return accounts

def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE) as f:
            return json.load(f)
    if os.path.exists(DISCORD_FILE):
        return parse_discord_txt(DISCORD_FILE)
    return []

def save_accounts(acc):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(acc, f, indent=2)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"main_wallet": "", "openai_api_key": ""}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def random_name(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def random_github():
    adj = ['cool', 'nice', 'super', 'mega', 'epic', 'neo', 'zen', 'cyber', 'quantum', 'astro']
    noun = ['dev', 'coder', 'hacker', 'agent', 'runner', 'node', 'link', 'wave', 'flux', 'pulse']
    return f"{random.choice(adj)}-{random.choice(noun)}-{random_name(4)}"

config = load_config()
accounts = load_accounts()

# ── Playwright ──────────────────────────────────────
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ── Global State ─────────────────────────────────────
state = {
    "pw": None,
    "browser": None,
    "context": None,
    "page": None,
    "running": False,
    "current_step": "idle",
    "current_account_idx": 0,
    "total_accounts": 0,
    "wallet_index": 1,  # ritual_2 = index 1 (0-based)
}

# ── Vision AI ────────────────────────────────────────
vision = None
try:
    from ai_vision import VisionAI
    api_key = config.get("openai_api_key", "") or os.getenv("OPENAI_API_KEY", "")
    if api_key:
        vision = VisionAI(api_key=api_key)
        log("VisionAI loaded ✅", "S")
    else:
        log("VisionAI: no API key — fallback to selector-only mode", "W")
except Exception as e:
    log(f"VisionAI not available: {e}", "W")


# ══════════════════════════════════════════════════════
# LOW-LEVEL BROWSER API
# ══════════════════════════════════════════════════════

def start_browser():
    if state["browser"]:
        return True
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=False,
            args=['--start-maximized', '--disable-blink-features=AutomationControlled',
                  '--no-sandbox', '--disable-dev-shm-usage']
        )
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(30000)
        state.update(pw=pw, browser=browser, context=context, page=page)
        log("Browser VISIBLE started ✅", "S")
        return True
    except Exception as e:
        log(f"Browser start failed: {e}", "E")
        return False

def close_browser():
    try:
        if state["browser"]: state["browser"].close()
        if state["pw"]: state["pw"].stop()
    except: pass
    state.update(browser=None, context=None, page=None, pw=None)
    log("Browser closed", "I")

def page():
    if not state["page"]:
        start_browser()
    return state["page"]

def screenshot():
    p = page()
    if not p: return None
    path = os.path.join(SCREENSHOT_DIR, f"step_{datetime.now().strftime('%H%M%S')}.png")
    try:
        p.screenshot(path=path, full_page=False)
        return path
    except: return None

def click_by_text(text, partial=True):
    """Click element by text content — main page + iframes + JS fallback"""
    p = page()
    if not p: return False
    
    strategies = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
                  f'button:has-text("{text}")', f'a:has-text("{text}")', f'span:has-text("{text}")',
                  f'[role="button"]:has-text("{text}")']
    if partial and len(text.split()) > 1:
        for w in text.split()[:3]:
            strategies.extend([f'text={w}', f'*:has-text("{w}")'])
    
    for sel in strategies:
        try:
            el = p.locator(sel)
            if el.count() > 0 and el.first.is_visible():
                el.first.click(timeout=3000)
                time.sleep(1)
                return True
        except: pass
    
    # iframes
    for frame in p.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")', f'span:has-text("{text}")']:
            try:
                el = frame.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=3000)
                    time.sleep(1)
                    return True
            except: pass
    
    # JS XPath
    try:
        words = text.split()
        js = ";".join(f"""
            try {{ var x = document.evaluate("//*[text()[contains(., '{w}')]]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            if(x.singleNodeValue) {{ x.singleNodeValue.click(); return true; }} }} catch(e){{}}
        """ for w in words)
        clicked = p.evaluate(f"() => {{ {js} return false; }}")
        if clicked: time.sleep(1); return True
    except: pass
    
    return False

def click_via_vision(instruction="What should I click?"):
    """AI Vision: liat screenshot, klik elemen yg cocok"""
    if not vision:
        return {"success": False, "error": "Vision AI not configured"}
    
    ss = screenshot()
    if not ss:
        return {"success": False, "error": "Screenshot failed"}
    
    result = vision.analyze(ss, instruction)
    if not result:
        return {"success": False, "error": "Vision analysis failed"}
    
    action = result.get("action", "")
    target = result.get("target_text", "")
    
    if action == "click" and target:
        ok = click_by_text(target)
        return {"success": ok, "action": "click", "target": target, "analysis": result}
    elif action == "skip_account":
        return {"success": True, "action": "skip_account", "reason": result.get("reason", "")}
    elif action == "wait":
        return {"success": True, "action": "wait", "reason": result.get("reason", "")}
    elif action == "done":
        return {"success": True, "action": "done"}
    elif action == "type":
        return {"success": False, "action": "type", "needs_type": result.get("type_text",""), "target": target}
    elif action == "navigate":
        return {"success": False, "action": "navigate", "url": result.get("url","")}
    else:
        return {"success": False, "action": action, "target": target}

def ai_step(context_msg):
    """Satu step AI vision: screenshot → analyze → execute → return result"""
    ss = screenshot()
    b64_data = None
    if ss:
        with open(ss, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode()
    
    instruction = f"""Current step: {state['current_step']}
Account {state['current_account_idx']+1}/{state['total_accounts']}

{context_msg}

Look at the screenshot. What should the automation do NOW?
- If "Continue in Browser" or "Open in Browser" → CLICK it (this is critical!)
- If login form → I need to type credentials
- If captcha/verification/image puzzle → WAIT, user will solve
- If "Already Verified" or duplicate → SKIP_ACCOUNT
- If form/input field → TYPE into it
- If "Accept Invite" → CLICK it
- If complete → DONE"""

    ai_result = None
    if vision:
        ai_result = vision.analyze(ss, instruction) if ss else None

    p = page()
    return {
        "screenshot_base64": b64_data,
        "ai_analysis": ai_result,
        "browser_url": p.url if p else "",
        "browser_title": p.title() if p else "",
        "current_step": state["current_step"],
    }


# ══════════════════════════════════════════════════════
# 22-STEP FAUCET ORCHESTRATOR
# ══════════════════════════════════════════════════════

def run_faucet_loop():
    """Main orchestrator — loop 10 accounts, execute 22-step flow"""
    global accounts, config
    state["running"] = True
    
    acc_list = load_accounts()
    state["total_accounts"] = len(acc_list)
    
    if not acc_list:
        log("No accounts found! Check discord.txt", "E")
        state["running"] = False
        return
    
    log(f"🚀 Starting autofaucet: {len(acc_list)} accounts", "S")
    log("Browser VISIBLE — you can see everything happening!", "S")
    
    for idx, acc in enumerate(acc_list):
        if not state["running"]:
            log("⏹️ Stopped by user", "W")
            break
        
        if acc.get("status") in ("done", "skip"):
            log(f"Account {idx+1} ({acc['email']}) already done/skipped", "W")
            continue
        
        state["current_account_idx"] = idx
        state["wallet_index"] = idx + 1  # ritual_2, ritual_3, ...
        
        try:
            process_one_account(idx, acc)
        except Exception as e:
            log(f"Account {idx+1} error: {e}", "E")
            traceback.print_exc()
            acc["status"] = "fail"
            save_accounts(acc_list)
        
        # Delay before next account
        if idx < len(acc_list) - 1 and state["running"]:
            log("⏳ Waiting 15s before next account...", "I")
            time.sleep(15)
    
    log("🏁 AUTOFACUET COMPLETE!", "S")
    state["running"] = False


def process_one_account(idx, acc):
    """22-step flow untuk 1 akun"""
    email = acc["email"]
    password = acc["password"]
    email_addr = acc.get("email_addr", "")
    email_pass = acc.get("email_password", "")
    email_link = acc.get("email_link", "")
    p = page()
    
    log(f"{'='*60}", "I")
    log(f"▶️ ACCOUNT {idx+1}: {email}", "S")
    log(f"{'='*60}", "I")
    
    # ── STEP 1: Login Discord ───────────────────────
    state["current_step"] = "1_login_discord"
    log("STEP 1: Login to Discord...", "I")
    p.goto("https://discord.com/login", wait_until="domcontentloaded")
    time.sleep(3)
    
    # AI vision: detect login form
    ai_step("Logging into Discord. Fill email and password fields.")
    
    # Fill credentials
    try:
        p.locator('input[name="email"]').fill(email)
        time.sleep(0.5)
        p.locator('input[name="password"]').fill(password)
        time.sleep(0.5)
        p.locator('button[type="submit"]').click()
        log("Credentials filled, submitted login", "S")
    except:
        log("Could not fill login form — user do it manually", "W")
    
    # Wait for user to solve captcha (90s)
    log("🔶 Solve captcha/hCaptcha manually if any... (90s)", "H")
    wait_and_check_continue(p, 90)
    
    # ── STEP 2-3: IP Verification → Open onet.pl ────
    state["current_step"] = "2_ip_verification"
    
    # Check if redirected to verification page
    current_url = p.url
    if "verify" in current_url.lower() or "new-ip" in current_url.lower() or "login" in current_url.lower():
        log("STEP 2: IP verification detected! Opening email...", "I")
        
        # Open onet.pl in new tab
        email_tab = state["context"].new_page()
        email_tab.goto("https://onet.pl", wait_until="domcontentloaded")
        time.sleep(3)
        
        # ── STEP 3: Login onet.pl ───────────────────
        state["current_step"] = "3_login_email"
        log("STEP 3: Logging into onet.pl email...", "I")
        ai_step_ctx(email_tab, "Logging into onet.pl email. Find the login button and enter credentials.")
        
        # Try to find and click login button on onet.pl
        for sel in ['a:has-text("Poczta")', 'a:has-text("poczta")', 'a[href*="poczta"]',
                    'button:has-text("Zaloguj")', 'a:has-text("Zaloguj")']:
            try:
                el = email_tab.locator(sel)
                if el.count() > 0:
                    el.first.click()
                    time.sleep(3)
                    break
            except: pass
        
        # Fill email login
        try:
            for sel in ['input[name="login"]', 'input[type="email"]', 'input[name="email"]',
                        'input[id*="login"]', 'input[id*="email"]']:
                try:
                    el = email_tab.locator(sel)
                    if el.count() > 0:
                        el.first.fill(email_addr)
                        time.sleep(0.5)
                        break
                except: pass
            
            # Click next/continue
            for sel in ['button:has-text("Dalej")', 'button:has-text("Next")', 'button[type="submit"]']:
                try:
                    el = email_tab.locator(sel)
                    if el.count() > 0:
                        el.first.click()
                        time.sleep(2)
                        break
                except: pass
            
            # Fill password
            for sel in ['input[type="password"]', 'input[name="password"]', 'input[id*="pass"]']:
                try:
                    el = email_tab.locator(sel)
                    if el.count() > 0:
                        el.first.fill(email_pass)
                        time.sleep(0.5)
                        break
                except: pass
            
            # Submit
            for sel in ['button:has-text("Zaloguj")', 'button:has-text("Sign in")', 'button[type="submit"]']:
                try:
                    el = email_tab.locator(sel)
                    if el.count() > 0:
                        el.first.click()
                        time.sleep(3)
                        break
                except: pass
        except:
            log("Could not auto-fill email login — do manually", "W")
            time.sleep(30)
        
        # ── STEP 4: Click Powiadomienia ────────────
        state["current_step"] = "4_click_notification"
        log("STEP 4: Looking for Discord verification email...", "I")
        
        # Try to click Powiadomienia (notifications section in onet.pl email)
        ai_step_ctx(email_tab, "Looking for Discord verification email in onet.pl inbox. Click on Powiadomienia or find verification email.")
        
        # Cari email dari Discord
        for sel in ['text=Discord', 'text=discord', 'text=Weryfikacja', 'text=verification',
                    'text=Powiadomienia', 'tr:has-text("Discord")', 'a:has-text("Discord")',
                    'span:has-text("Discord")']:
            try:
                el = email_tab.locator(sel)
                if el.count() > 0:
                    el.first.click()
                    time.sleep(3)
                    log("Clicked Discord verification email", "C")
                    break
            except: pass
        
        # ── STEP 5: Click verification link in email ─
        state["current_step"] = "5_click_verify_link"
        log("STEP 5: Clicking verification link in email...", "I")
        ai_step_ctx(email_tab, "In Discord verification email. Click the verification button/link (usually blue button with 'Verify' or link starting with click.discord.com)")
        
        # Try to find verification link
        for sel in ['a:has-text("Verify")', 'a[href*="discord.com/verify"]', 'a[href*="click.discord.com"]',
                    'a[href*="discord"]', 'td:has-text("Verify") a', 'a:has-text("Weryfikuj")']:
            try:
                el = email_tab.locator(sel)
                if el.count() > 0:
                    href = el.first.get_attribute("href") or ""
                    if "discord" in href.lower() or "verify" in href.lower():
                        log(f"Found verify link: {href[:80]}...", "S")
                        el.first.click()
                        time.sleep(5)
                        break
            except: pass
        
        email_tab.close()
        
        # ── STEP 6: Back to Discord ────────────────
        state["current_step"] = "6_back_to_discord"
        log("STEP 6: Back to Discord (IP verified now)", "I")
        time.sleep(3)
        p.goto("https://discord.com/login", wait_until="domcontentloaded")
        time.sleep(3)
        
        # Fill login again if needed
        try:
            p.locator('input[name="email"]').fill(email)
            p.locator('input[name="password"]').fill(password)
            p.locator('button[type="submit"]').click()
            log("Re-logged in after IP verification", "S")
        except: pass
        
        log("🔶 Solve any captcha... (60s)", "H")
        wait_and_check_continue(p, 60)
    else:
        log("No IP verification needed or already verified ✅", "S")
    
    # ── STEP 7: Resend verification email ──────────
    state["current_step"] = "7_resend_verification"
    log("STEP 7: Resend verification email (if needed)...", "I")
    wait_and_check_continue(p, 10)
    
    # Check if we need to resend
    try:
        resend = p.locator('button:has-text("Resend")')
        if resend.count() > 0:
            resend.first.click()
            log("Clicked 'Resend' verification email", "C")
            time.sleep(5)
    except: pass
    
    # ── STEP 8: Open latest verification in onet.pl ─
    state["current_step"] = "8_recheck_email"
    log("STEP 8: Re-checking email for latest verification...", "I")
    
    # Check if we need to go back to email
    try:
        if p.locator('text=Verify Your Email').count() > 0 or p.locator('text=verify').count() > 0:
            email_tab2 = state["context"].new_page()
            email_tab2.goto(email_link or f"https://poczta.onet.pl/", wait_until="domcontentloaded")
            time.sleep(5)
            
            # Find latest Discord email
            for sel in ['text=Discord', 'tr:has-text("Discord")', 'a:has-text("Discord")']:
                try:
                    el = email_tab2.locator(sel)
                    if el.count() > 0:
                        el.first.click()
                        time.sleep(3)
                        break
                except: pass
            
            # Click verification link
            for sel in ['a:has-text("Verify")', 'a[href*="discord"]', 'a[href*="click.discord"]']:
                try:
                    el = email_tab2.locator(sel)
                    if el.count() > 0:
                        el.first.click()
                        time.sleep(5)
                        break
                except: pass
            
            email_tab2.close()
            time.sleep(3)
            
            # Back to Discord
            p.goto("https://discord.com/login")
            time.sleep(3)
            try:
                p.locator('input[name="email"]').fill(email)
                p.locator('input[name="password"]').fill(password)
                p.locator('button[type="submit"]').click()
            except: pass
            wait_and_check_continue(p, 60)
    except: pass
    
    # ── STEP 9: Join Ritual Server ─────────────────
    state["current_step"] = "9_join_server"
    log("STEP 9: Joining Ritual server...", "I")
    p.goto(DISCORD_INVITE, wait_until="domcontentloaded")
    time.sleep(5)
    
    # Accept invite
    try:
        for sel in ['button:has-text("Accept Invite")', 'button:has-text("Terima")',
                    'button:has-text("Join")', 'button:has-text("Accept")']:
            el = p.locator(sel)
            if el.count() > 0:
                el.first.click()
                time.sleep(3)
                log("Clicked Accept Invite ✅", "C")
                break
    except: pass
    
    # Fix: jangan auto-klik sembarangan — AI vision aja yg decide
    log("🔶 Solve any CAPTCHA (checkmark/images)...", "H")
    wait_and_check_continue(p, 90)
    
    # ── STEP 10: Verify in #verification ────────────
    state["current_step"] = "10_verify_channel"
    log("STEP 10: Verify in #verification channel...", "I")
    ai_step("Just joined Ritual server. Navigate to #verification channel. If 'Already Verified' → SKIP_ACCOUNT.")
    time.sleep(30)  # User solves captcha
    
    # Check if already verified
    for txt in ["already verified", "already have", "Already Verified", "already verified"]:
        if txt.lower() in p.evaluate("document.body.innerText").lower():
            log(f"'{txt}' detected — SKIPPING account!", "S")
            acc["status"] = "skip"
            save_accounts(load_accounts())
            return
    
    # ── STEP 11: CAPTCHA process ────────────────────
    state["current_step"] = "11_captcha"
    log("STEP 11: CAPTCHA solving... (user solves manually)", "H")
    wait_and_check_continue(p, 120)
    
    # ── STEP 12: Go to #academy-welcome ─────────────
    state["current_step"] = "12_academy_welcome"
    log("STEP 12: Go to #academy-welcome channel...", "I")
    ai_step("Navigate to #academy-welcome channel in the Ritual Discord server. Find and click the wallet link.")
    wait_and_check_continue(p, 60)
    
    # ── STEP 13: Click wallet link ─────────────────
    state["current_step"] = "13_click_wallet"
    log("STEP 13: Click wallet link...", "I")
    for txt in ["wallet", "Wallet", "create wallet", "link", "get-started"]:
        if click_by_text(txt):
            time.sleep(5)
            break
    
    # Auto-click Continue in Browser (critical fix!)
    for _ in range(15):  # 30s polling
        if click_by_text("Continue in Browser") or click_by_text("Open in Browser"):
            log("✅ Continue in Browser clicked!", "S")
            break
        time.sleep(2)
    
    # ── STEP 14: Get wallet address ────────────────
    state["current_step"] = "14_get_wallet"
    wallet_idx = state["wallet_index"]
    wallet_addr = get_wallet_address(wallet_idx)
    log(f"Using wallet: {wallet_addr} (ritual_{wallet_idx+1})", "S")
    
    # ── STEP 15-16: Fill GitHub & Twitter ──────────
    state["current_step"] = "15_fill_github"
    gh_name = random_github()
    log(f"STEP 15: Fill GitHub: {gh_name}", "I")
    
    # AI vision for form filling
    ai_step(f"Fill in the form with GitHub username: {gh_name}")
    
    # Try to find and fill GitHub field
    for sel in ['input[placeholder*="github"]', 'input[name*="github"]', 
                'input[placeholder*="GitHub"]', 'input[id*="github"]',
                'input[type="text"]', 'input:not([type="hidden"])']:
        try:
            el = p.locator(sel)
            if el.count() > 0:
                el.first.click()
                time.sleep(0.3)
                el.first.fill(gh_name)
                log(f"Filled GitHub: {gh_name}", "T")
                break
        except: pass
    
    time.sleep(2)
    
    # Twitter
    state["current_step"] = "16_fill_twitter"
    tw_name = random_github()
    log(f"STEP 16: Fill Twitter: @{tw_name}", "I")
    
    for sel in ['input[placeholder*="twitter"]', 'input[name*="twitter"]',
                'input[placeholder*="Twitter"]', 'input[id*="twitter"]',
                'input[type="text"]', 'input:not([type="hidden"])']:
        try:
            el = p.locator(sel)
            if el.count() > 0:
                el.first.click()
                time.sleep(0.3)
                el.first.fill(tw_name)
                log(f"Filled Twitter: @{tw_name}", "T")
                break
        except: pass
    
    time.sleep(2)
    
    # ── STEP 17: Go to #rank → /get-code ──────────
    state["current_step"] = "17_get_code"
    log("STEP 17: Go to #rank channel and type /get-code...", "I")
    ai_step("Navigate to #rank channel in the Ritual Discord. Click on the message input box and type /get-code")
    
    # Try to type in Discord chat
    for sel in ['div[role="textbox"]', 'div[contenteditable="true"]', 
                'textarea', 'input[type="text"]']:
        try:
            el = p.locator(sel)
            if el.count() > 0:
                el.first.click()
                time.sleep(1)
                p.keyboard.type("/get-code", delay=100)
                time.sleep(1)
                p.keyboard.press("Enter")
                log("Sent /get-code", "T")
                break
        except: pass
    
    time.sleep(5)
    
    # ── STEP 18: Follow bot for faucet ──────────────
    state["current_step"] = "18_faucet_bot"
    log("STEP 18: Follow bot instructions for faucet...", "I")
    ai_step("The faucet bot responded. Follow the instructions on screen. Look for buttons/codes to claim the faucet.")
    wait_and_check_continue(p, 120)
    
    # ── STEP 19: Deploy agent ──────────────────────
    state["current_step"] = "19_deploy_agent"
    log("STEP 19: Deploy agent as instructed...", "I")
    ai_step("Follow the deploy agent instructions shown on screen. Fill in any required fields.")
    wait_and_check_continue(p, 120)
    
    # ── STEP 20: Go to #genesis-link, verify wallet ─
    state["current_step"] = "20_genesis_link"
    log("STEP 20: Go to #genesis-link, verify wallet...", "I")
    ai_step(f"Navigate to #genesis-link channel. Verify wallet address: {wallet_addr}")
    
    # Fill wallet address
    for sel in ['input[type="text"]', 'input:not([type="hidden"])', 'textarea']:
        try:
            el = p.locator(sel)
            if el.count() > 0:
                el.first.click()
                time.sleep(0.5)
                el.first.fill(wallet_addr)
                log(f"Filled wallet: {wallet_addr}", "T")
                time.sleep(1)
                p.keyboard.press("Enter")
                break
        except: pass
    
    wait_and_check_continue(p, 60)
    
    # ── STEP 21: Forward RIT to main wallet ─────────
    state["current_step"] = "21_forward_rit"
    log("STEP 21: Forwarding RIT to main wallet...", "I")
    forward_rit_to_main(wallet_idx, wallet_addr)
    
    # ── STEP 22: Done ──────────────────────────────
    state["current_step"] = "22_done"
    acc["status"] = "done"
    acc["wallet"] = wallet_addr
    acc["github"] = gh_name
    acc["completed_at"] = datetime.now().isoformat()
    save_accounts(load_accounts())
    
    log(f"✅ ACCOUNT {idx+1} COMPLETE! Wallet: {wallet_addr}", "S")


def get_wallet_address(wallet_index):
    """Get wallet address from ritual_wallets.txt or create new"""
    wallets = []
    if os.path.exists(WALLETS_FILE):
        with open(WALLETS_FILE) as f:
            content = f.read()
        matches = re.findall(r'ritual_(\d+)=(\S+)', content)
        for num, addr in matches:
            if int(num) == wallet_index + 1:  # ritual_2 = index 1
                return addr
    
    # Create new wallet
    try:
        result = subprocess.run(
            f"cast wallet new --rpc-url {RPC} 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split('\n'):
            if 'Address:' in line:
                addr = line.split('Address:')[1].strip()
                log(f"New wallet created: {addr}", "S")
                return addr
    except: pass
    
    return f"0x{random_name(40)}"


def forward_rit_to_main(wallet_idx, wallet_addr):
    """Forward RIT tokens to main wallet"""
    main_wallet = config.get("main_wallet", "")
    if not main_wallet or wallet_addr == main_wallet:
        log("No main wallet configured or same address, skip forward", "W")
        return
    
    pk = ""
    if os.path.exists(WALLETS_FILE):
        with open(WALLETS_FILE) as f:
            for line in f:
                if f"ritual_{wallet_idx+1}=" in line:
                    pk = line.split("=", 1)[1].strip()
                    break
    
    if not pk:
        log(f"No private key for wallet {wallet_idx+1}", "W")
        return
    
    try:
        bal = subprocess.run(
            f'cast balance {wallet_addr} --rpc-url {RPC} --ether 2>/dev/null',
            shell=True, capture_output=True, text=True, timeout=10
        ).stdout.strip()
        log(f"Balance: {bal} RIT", "I")
        
        if bal and float(bal) > 0.001:
            subprocess.run(
                f'PRIVATE_KEY={pk} cast send {main_wallet} '
                f'--value $(cast balance {wallet_addr} --rpc-url {RPC} --wei 2>/dev/null)wei '
                f'--private-key {pk} --rpc-url {RPC} --gas-limit 21000 2>/dev/null',
                shell=True, timeout=60
            )
            log(f"✅ Forwarded to {main_wallet}", "S")
        else:
            log(f"Balance too low ({bal} RIT), skip forward", "W")
    except Exception as e:
        log(f"Forward error: {e}", "E")


def wait_and_check_continue(page, seconds):
    """Wait with auto-detect 'Continue in Browser' / 'Open in Browser' button"""
    for _ in range(seconds * 2):  # 0.5s intervals
        if not state["running"]:
            break
        try:
            # Cek Continue in Browser di main page
            for txt in ["Continue in Browser", "Open in Browser", "Open in Browser", "Continue"]:
                for sel in [f'text={txt}', f'*:text-is("{txt}")', f'*:has-text("{txt}")',
                           f'span:has-text("{txt}")', f'button:has-text("{txt}")',
                           f'a:has-text("{txt}")']:
                    try:
                        el = page.locator(sel)
                        if el.count() > 0 and el.first.is_visible():
                            el.first.click(timeout=2000)
                            log(f"✅ Auto-clicked '{txt}'!", "S")
                            time.sleep(2)
                            return  # Success, exit early
                    except: pass
            
            # Cek di iframes
            for frame in page.frames[1:]:
                for txt in ["Continue in Browser", "Open in Browser", "Continue"]:
                    try:
                        el = frame.locator(f'text={txt}')
                        if el.count() > 0:
                            el.first.click(timeout=2000)
                            log(f"✅ Clicked '{txt}' in iframe!", "S")
                            time.sleep(2)
                            return
                    except: pass
            
            # JS force-click
            try:
                page.evaluate("""() => {
                    for (const t of ['Continue in Browser', 'Open in Browser', 'Continue']) {
                        const x = document.evaluate('//*[text()[contains(., "' + t + '")]]', document, null, 
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                        if (x.singleNodeValue) { x.singleNodeValue.click(); return true; }
                    }
                    return false;
                }""")
            except: pass
        except: pass
        
        time.sleep(0.5)


def ai_step_ctx(tab, msg):
    """AI step for a specific tab (not main page)"""
    ss_path = os.path.join(SCREENSHOT_DIR, f"tab_{datetime.now().strftime('%H%M%S')}.png")
    try:
        tab.screenshot(path=ss_path)
    except: pass


# ══════════════════════════════════════════════════════
# FLASK API
# ══════════════════════════════════════════════════════

app = Flask(__name__)
CORS(app)


@app.route("/")
def index():
    return jsonify({
        "service": "Ritual AutoFaucet v3 — AI Vision",
        "browser": "running" if state["browser"] else "idle",
        "running": state["running"],
        "accounts": len(accounts),
        "endpoints": {
            "POST /api/faucet/start": "start autofaucet",
            "POST /api/faucet/stop": "stop",
            "GET /api/faucet/status": "current state",
            "POST /api/browser/action": "browser control",
            "GET /api/browser/ai_step": "AI vision analysis",
            "GET /api/logs": "logs",
        }
    })


@app.route("/api/faucet/start", methods=["POST"])
def api_start():
    if state["running"]:
        return jsonify({"success": False, "error": "Already running"}), 400
    
    data = request.get_json(silent=True) or {}
    main_wallet = data.get("main_wallet", "") or config.get("main_wallet", "")
    if main_wallet:
        config["main_wallet"] = main_wallet
        save_config(config)
    
    thread = threading.Thread(target=run_faucet_loop, daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "Autofaucet started"})


@app.route("/api/faucet/stop", methods=["POST"])
def api_stop():
    state["running"] = False
    return jsonify({"success": True})


@app.route("/api/faucet/status", methods=["GET"])
def api_status():
    p = page()
    return jsonify({
        "running": state["running"],
        "current_step": state["current_step"],
        "account": state["current_account_idx"] + 1,
        "total": state["total_accounts"],
        "browser_url": p.url if p else "",
        "wallet_index": state["wallet_index"] + 1,
        "main_wallet": config.get("main_wallet", ""),
    })


@app.route("/api/browser/action", methods=["POST"])
def api_browser_action():
    """Low-level browser control"""
    data = request.get_json(silent=True) or {}
    action = data.get("action", "screenshot")
    p = page()
    if not p:
        return jsonify({"success": False, "error": "Browser not started"})
    
    try:
        if action == "screenshot":
            b64 = None
            ss = screenshot()
            if ss:
                with open(ss, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
            return jsonify({"success": True, "image_base64": b64})
        
        elif action == "click_text":
            text = data.get("text", "")
            ok = click_by_text(text)
            return jsonify({"success": ok})
        
        elif action == "navigate":
            url = data.get("url", "")
            p.goto(url, wait_until="domcontentloaded", timeout=30000)
            return jsonify({"success": True, "url": url})
        
        elif action == "type":
            text = data.get("text", "")
            p.keyboard.type(text, delay=50)
            return jsonify({"success": True})
        
        elif action == "fill":
            text = data.get("text", "")
            sel = data.get("selector", "input[type='text']")
            try:
                el = p.locator(sel).first
                el.click()
                el.fill(text)
            except:
                p.keyboard.type(text, delay=50)
            return jsonify({"success": True})
        
        elif action == "press_key":
            key = data.get("key", "Enter")
            p.keyboard.press(key)
            return jsonify({"success": True})
        
        elif action == "evaluate":
            js = data.get("js", "")
            result = p.evaluate(js)
            return jsonify({"success": True, "result": str(result)[:1000]})
        
        elif action == "get_text":
            text = p.evaluate("document.body.innerText")
            return jsonify({"success": True, "text": text[:10000]})
        
        else:
            return jsonify({"success": False, "error": f"Unknown: {action}"})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/browser/ai_step", methods=["POST"])
def api_ai_step():
    """Take screenshot + AI analyze + return result"""
    data = request.get_json(silent=True) or {}
    context = data.get("context", "Automate the Ritual faucet flow")
    result = ai_step(context)
    return jsonify(result)


@app.route("/api/logs", methods=["GET"])
def api_logs():
    n = request.args.get("n", 50, type=int)
    return jsonify({"logs": get_logs(n)})


@app.route("/api/browser/start", methods=["POST"])
def api_start_browser():
    ok = start_browser()
    return jsonify({"success": ok})


@app.route("/api/browser/stop", methods=["POST"])
def api_stop_browser():
    state["running"] = False
    close_browser()
    return jsonify({"success": True})


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5000"))
    log("=" * 60, "I")
    log("🚀 RITUAL AUTOFACUET v3 — AI VISION", "S")
    log(f"📡 API Server on port {port}", "S")
    log("🔍 OpenAI Vision: {'✅' if vision else '❌ (set OPENAI_API_KEY)'}", "I")
    log(f"📋 Accounts: {len(accounts)}", "I")
    log("=" * 60, "I")
    
    # Auto-start browser
    start_browser()
    
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    finally:
        close_browser()
