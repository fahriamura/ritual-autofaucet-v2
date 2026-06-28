#!/usr/bin/env python3
"""
Ritual AutoFaucet — Full Headless Automation
Runs directly, no Flask API needed.
"""
import os, sys, json, time, re, random, string, base64, subprocess, traceback
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ── Config ──────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
DISCORD_FILE = os.path.join(BASE, "discord.txt")
ACCOUNTS_FILE = os.path.join(BASE, "accounts.json")
CONFIG_FILE = os.path.join(BASE, "config.json")
WALLETS_FILE = "/root/ritual_wallets.txt"
SS_DIR = os.path.join(BASE, "screenshots")
RPC = "https://rpc.ritualfoundation.org"
DISCORD_INVITE = "https://discord.gg/ritual-net"

os.makedirs(SS_DIR, exist_ok=True)

LOG = []
def log(msg, t="I"):
    p = {"I":"ℹ️","S":"✅","W":"⚠️","E":"❌","C":"🖱️","T":"⌨️","H":"🔶","V":"📸"}
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {p.get(t,'ℹ️')} {msg}"
    LOG.append(line)
    print(line, flush=True)

def ss(page, name):
    path = os.path.join(SS_DIR, f"{name}_{datetime.now().strftime('%H%M%S')}.png")
    page.screenshot(path=path)
    log(f"Screenshot: {path}", "V")
    return path

# ── Data ─────────────────────────────────────────────
def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE) as f:
                acc = json.load(f)
                if acc: return acc
        except: pass
    acc = parse_discord_txt(DISCORD_FILE)
    save_accounts(acc)
    return acc

def parse_discord_txt(path):
    acc = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()
    for line in lines[1:]:
        parts = line.strip().split("\t")
        if len(parts) >= 6:
            acc.append({
                "email": parts[0].strip(),
                "password": parts[1].strip(),
                "username": parts[2].strip(),
                "email_addr": parts[3].strip(),
                "email_password": parts[4].strip(),
                "email_link": parts[5].strip(),
                "status": "pending",
            })
    return acc

def save_accounts(acc):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(acc, f, indent=2)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"main_wallet": "", "done": []}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def random_git():
    adj = ['cool','nice','super','mega','epic','neo','zen','cyber','quantum','astro','nova']
    noun = ['dev','coder','hacker','agent','runner','node','link','wave','flux','pulse','apex']
    return f"{random.choice(adj)}-{random.choice(noun)}-{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789',k=4))}"

def get_wallet(idx):
    """Get wallet address from ritual_wallets.txt"""
    if os.path.exists(WALLETS_FILE):
        with open(WALLETS_FILE) as f:
            for line in f:
                m = re.search(r'ritual_(\d+)=(\S+)', line)
                if m and int(m.group(1)) == idx + 2:  # ritual_2 = idx 0
                    return m.group(2)
    # Fallback: create new
    try:
        r = subprocess.run("cast wallet new --rpc-url https://rpc.ritualfoundation.org 2>/dev/null",
                          shell=True, capture_output=True, text=True, timeout=10)
        for line in r.stdout.split('\n'):
            if 'Address:' in line:
                return line.split('Address:')[1].strip()
    except: pass
    return f"0x{''.join(random.choices('0123456789abcdef', k=40))}"

# ── Browser Actions ─────────────────────────────────
def click_text(page, text, timeout=3000):
    """Click element by visible text"""
    sels = [f'text={text}', f'*:text-is("{text}")', f'*:has-text("{text}")',
            f'button:has-text("{text}")', f'a:has-text("{text}")', 
            f'span:has-text("{text}")', f'[role="button"]:has-text("{text}")']
    for w in text.split()[:3]:
        sels.extend([f'text={w}', f'*:has-text("{w}")'])
    
    for sel in sels:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(timeout=timeout)
                time.sleep(0.5)
                return True
        except: pass
    
    # Iframes
    for fr in page.frames[1:]:
        for sel in [f'text={text}', f'*:has-text("{text}")']:
            try:
                el = fr.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=timeout)
                    time.sleep(0.5)
                    return True
            except: pass
    return False

def check_continue(page):
    """Auto-click Continue in Browser if visible"""
    for txt in ["Continue in Browser", "Open in Browser", "Continue", "Open App"]:
        for sel in [f'text={txt}', f'*:text-is("{txt}")', f'*:has-text("{txt}")',
                   f'span:has-text("{txt}")', f'button:has-text("{txt}")']:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=2000)
                    log(f"Auto-clicked '{txt}'!", "C")
                    time.sleep(2)
                    return True
            except: pass
    return False

def fill_field(page, placeholder_text, value):
    """Fill input field by placeholder/name"""
    for sel in [f'input[placeholder*="{placeholder_text}"]', f'input[name*="{placeholder_text}"]',
                f'input[aria-label*="{placeholder_text}"]', f'input[id*="{placeholder_text}"]',
                'input[type="text"]', 'input:not([type="hidden"])',
                'div[contenteditable="true"]', 'div[role="textbox"]']:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.fill(value)
                time.sleep(0.3)
                return True
        except: pass
    return False

# ── Main Flow ────────────────────────────────────────
def process_one_account(page, idx, acc):
    """Run through all steps for one account"""
    email = acc["email"]
    pw = acc["password"]
    email_addr = acc.get("email_addr", email)
    email_pw = acc.get("email_password", "")
    
    log(f"{'='*60}")
    log(f"ACCOUNT {idx+1}: {email}", "S")
    log(f"{'='*60}")
    
    # ── STEP 1: Discord Login ────────────────────────
    log("STEP 1: Discord login...", "I")
    page.goto("https://discord.com/login", wait_until="domcontentloaded")
    time.sleep(3)
    ss(page, "01_login_page")
    
    # Fill credentials
    try:
        page.locator('input[name="email"]').fill(email)
        time.sleep(0.5)
        page.locator('input[name="password"]').fill(pw)
        time.sleep(0.5)
        page.locator('button[type="submit"]').click()
        log("Credentials submitted", "S")
    except Exception as e:
        log(f"Cannot auto-fill login form: {e}", "W")
        ss(page, "01_error")
    
    # Wait & check what happened
    for i in range(90):
        check_continue(page)
        time.sleep(1)
        
        # Check page text periodically
        if i % 15 == 0:
            body = page.evaluate("document.body.innerText")[:300].lower()
            log(f"Page check ({i}s): {body[:150]}", "I")
        
        if "/channels/" in page.url:
            log("Login SUCCESS! Redirected to channels ✅", "S")
            break
        
        if "verify" in page.url.lower() or "mfa" in page.url.lower():
            log("MFA/Verification required", "H")
            ss(page, "01_verify")
            break
        
        if "new login" in page.evaluate("document.body.innerText").lower():
            log("New login location detected! Need email verification", "H")
            ss(page, "01_new_ip")
            break
        
        if "captcha" in page.evaluate("document.body.innerText").lower():
            log("CAPTCHA detected! Taking screenshot...", "H")
            ss(page, "01_captcha")
            break
    else:
        body = page.evaluate("document.body.innerText")[:500]
        log(f"Login wait expired. Page: {page.url}", "W")
        log(f"Page text: {body[:300]}", "I")
        ss(page, "01_after_wait")
    
    # ── CHECK: is login page still showing? = verification needed ────
    body = page.evaluate("document.body.innerText").lower()
    still_on_login = ("email" in body and "password" in body and "/channels/" not in page.url)
    
    if still_on_login:
        log("⚠️ Masih di halaman login — Discord minta verifikasi IP!", "H")
        log("🔄 FLOW: onet.pl → verifikasi email → Discord → resend → onet.pl → Discord", "I")
        
        ctx = page.context
        email_page = ctx.new_page()
        
        # ── STEP 3: Login onet.pl ──────────────────
        log("STEP 3: Login onet.pl...", "I")
        email_page.goto("https://poczta.onet.pl/", wait_until="domcontentloaded")
        time.sleep(5)
        ss(email_page, "02_onet_login")
        
        # Cari & klik "Poczta" / login button
        for txt in ["Poczta", "Zaloguj", "Zaloguj się", "Log in"]:
            try:
                el = email_page.locator(f'text={txt}')
                if el.count() > 0:
                    el.first.click()
                    time.sleep(3)
                    log(f"Clicked {txt} on onet.pl", "C")
                    break
            except: pass
        
        # Isi email
        for sel in ['input[name="login"]', 'input[type="email"]', 'input[id*="login"]', 
                    'input[aria-label*="login"]', 'input', 'input[type="text"]']:
            try:
                el = email_page.locator(sel).first
                if el.is_visible():
                    el.fill(email_addr)
                    log(f"Filled email: {email_addr}", "T")
                    time.sleep(0.5)
                    break
            except: pass
        
        # Klik next / go to password
        for txt in ["Dalej", "Next", "Kontynuuj", "Continue"]:
            try:
                el = email_page.locator(f'text={txt}')
                if el.count() > 0:
                    el.first.click()
                    time.sleep(3)
                    break
            except: pass
        
        email_page.keyboard.press("Enter")
        time.sleep(3)
        
        # Isi password
        for sel in ['input[type="password"]', 'input[name="password"]', 'input[id*="pass"]',
                    'input[aria-label*="hasło"]', 'input[aria-label*="password"]']:
            try:
                el = email_page.locator(sel).first
                if el.is_visible():
                    el.fill(email_pw)
                    log("Filled password", "T")
                    time.sleep(0.5)
                    break
            except: pass
        
        # Submit
        for txt in ["Zaloguj", "Zaloguj się", "Sign in", "Log in"]:
            try:
                el = email_page.locator(f'text={txt}')
                if el.count() > 0:
                    el.first.click()
                    time.sleep(5)
                    break
            except: pass
        
        email_page.keyboard.press("Enter")
        time.sleep(3)
        ss(email_page, "02_onet_inbox")
        
        # ── STEP 4: Klik Powiadomienia ──────────────────
        log("STEP 4: Klik Powiadomienia untuk cari email Discord...", "I")
        
        # User instruction: klik span dengan class go3592846988 / contain Powiadomienia
        # Dan juga span dengan "Nowe: 2" / "New" badge
        for selector in [
            'span.go3592846988',
            '[class*="Powiadomienia"]',
            '[class*="side-menu-item"]',
        ]:
            try:
                el = email_page.locator(selector)
                if el.count() > 0 and el.first.is_visible():
                    el.first.click()
                    log(f"Clicked Powiadomienia via '{selector}'!", "C")
                    time.sleep(3)
                    break
            except: pass
        
        # Fallback: click by text
        if not click_text(email_page, "Powiadomienia"):
            click_text(email_page, "Nieprzeczytane")
            click_text(email_page, "Nowe:")
            click_text(email_page, "Discord")
        
        time.sleep(3)
        ss(email_page, "02_powiadomienia")
        
        # ── STEP 5: Klik verify link di email ──────
        log("STEP 5: Klik link verifikasi Discord di email...", "I")
        
        # Cari & klik email dari Discord
        for sel in ['text=Discord', 'text=discord', 'tr:has-text("Discord")',
                    'a:has-text("Discord")', 'span:has-text("Discord")',
                    'text=Weryfikacja', 'text=verification']:
            try:
                el = email_page.locator(sel)
                if el.count() > 0:
                    el.first.click()
                    log(f"Clicked Discord email via '{sel}'", "C")
                    time.sleep(3)
                    break
            except: pass
        
        ss(email_page, "02_discord_email")
        
        # Cari tombol verifikasi di isi email
        # User instruction: <td bgcolor="#5865f2"> <a href="https://click.discord.com/...">
        verify_clicked = False
        for sel in [
            'a[href*="click.discord.com"]',
            'a[href*="discord.com/verify"]',
            'a[href*="verify"]',
            'a:has-text("Verify")',
            'a:has-text("Weryfikuj")',
            'td[bgcolor="#5865f2"] a',
            'a:has-text("Verify Email")',
        ]:
            try:
                el = email_page.locator(sel)
                if el.count() > 0:
                    href = el.first.get_attribute("href") or ""
                    log(f"Clicking verify link: {href[:100]}", "C")
                    el.first.click()
                    time.sleep(5)
                    verify_clicked = True
                    break
            except: pass
        
        if not verify_clicked:
            log("⚠️ Verify link not found — cari manual", "W")
            body_email = email_page.evaluate("document.body.innerText")
            log(f"Email body: {body_email[:300]}", "I")
        
        # ── STEP 6: Back to Discord ────────────────
        log("STEP 6: Kembali ke Discord (IP verified)...", "I")
        email_page.close()
        time.sleep(3)
        
        # Back to main page
        page.goto("https://discord.com/login", wait_until="domcontentloaded")
        time.sleep(5)
        ss(page, "02_after_verify")
        
        # ── STEP 7-8: Resend + re-check email ──────
        log("STEP 7: Re-login + resend verification...", "I")
        
        # Fill login again
        try:
            page.locator('input[name="email"]').fill(email)
            time.sleep(0.3)
            page.locator('input[name="password"]').fill(pw)
            time.sleep(0.3)
            page.locator('button[type="submit"]').click()
            log("Re-submitted login", "S")
        except: pass
        
        # Wait 10s for redirect
        for i in range(20):
            check_continue(page)
            time.sleep(0.5)
            if "/channels/" in page.url:
                log("Login SUCCESS after email verification ✅", "S")
                return "ok"
        
        # Check if needing resend
        body2 = page.evaluate("document.body.innerText").lower()
        if "resend" in body2 or "verify your email" in body2:
            log("Masih perlu resend verification — buka email lagi...", "H")
            
            # Klik resend di Discord
            for txt in ["Resend", "Wyślij ponownie", "Send again"]:
                try:
                    el = page.locator(f'text={txt}')
                    if el.count() > 0:
                        el.first.click()
                        log(f"Clicked {txt}", "C")
                        time.sleep(5)
                        break
                except: pass
            
            # ── STEP 8: Buka onet.pl lagi, klik verif terbaru ──
            email_page2 = ctx.new_page()
            email_page2.goto("https://poczta.onet.pl/", wait_until="domcontentloaded")
            time.sleep(5)
            
            # Auto-login (seharusnya sudah login via session)
            # Cari Discord terbaru
            for sel in ['text=Discord', 'tr:has-text("Discord")', 'a:has-text("Discord")']:
                try:
                    el = email_page2.locator(sel)
                    if el.count() > 0:
                        el.first.click()
                        time.sleep(3)
                        break
                except: pass
            
            # Klik verify link lagi
            for sel in ['a[href*="click.discord.com"]', 'a[href*="verify"]', 'a:has-text("Verify")']:
                try:
                    el = email_page2.locator(sel)
                    if el.count() > 0:
                        el.first.click()
                        log("Clicked latest verify link", "C")
                        time.sleep(5)
                        break
                except: pass
            
            email_page2.close()
            time.sleep(3)
            
            # Re-login Discord
            page.goto("https://discord.com/login", wait_until="domcontentloaded")
            time.sleep(3)
            try:
                page.locator('input[name="email"]').fill(email)
                page.locator('input[name="password"]').fill(pw)
                page.locator('button[type="submit"]').click()
            except: pass
            
            for i in range(30):
                check_continue(page)
                time.sleep(1)
                if "/channels/" in page.url:
                    log("Login SUCCESS after resend + verify ✅", "S")
                    return "ok"
        
        # Default: login failed
        log(f"❌ Login gagal setelah verifikasi. Page: {page.url}", "E")
        body_final = page.evaluate("document.body.innerText")[:400]
        log(f"Page final: {body_final[:200]}", "I")
        ss(page, "02_login_failed")
        return "fail"
    
    # Wait for fresh login to fully load
    for i in range(30):
        check_continue(page)
        time.sleep(1)
        if "/channels/" in page.url:
            break
    
    # ── SKIP CHECK: Already verified? ───────────────
    body = page.evaluate("document.body.innerText").lower()
    if "already verified" in body or "already have" in body:
        log("⚠️ Account ALREADY VERIFIED — skipping!", "H")
        acc["status"] = "skip"
        save_accounts(load_accounts())
        return "skip"
    
    # ── JOIN SERVER ──────────────────────────────────
    log("Joining Ritual server...", "I")
    page.goto(DISCORD_INVITE, wait_until="domcontentloaded")
    time.sleep(5)
    ss(page, "03_join_server")
    
    click_text(page, "Accept Invite") or click_text(page, "Join")
    time.sleep(5)
    
    # Check for Continue in Browser
    for _ in range(20):
        if check_continue(page):
            break
        time.sleep(1)
    
    # ── Server verification ─────────────────────────
    log("Looking for verification channel...", "I")
    click_text(page, "verify") or click_text(page, "verification")
    time.sleep(5)
    ss(page, "04_verification")
    
    # RECAP: User needs to solve captcha here
    log("🔶 CAPTCHA TIME — user needs to solve captcha on screen", "H")
    log("📸 Screenshot saved, waiting 120s for captcha solving...", "H")
    
    for i in range(60):
        check_continue(page)
        time.sleep(2)
    
    # ── Navigate to academy-welcome ─────────────────
    click_text(page, "academy-welcome") or click_text(page, "academy")
    time.sleep(5)
    ss(page, "05_academy")
    
    click_text(page, "wallet") or click_text(page, "Wallet") or click_text(page, "link")
    time.sleep(5)
    
    for _ in range(20):
        if check_continue(page):
            break
        time.sleep(1)
    
    # ── Get wallet ───────────────────────────────────
    wallet_addr = get_wallet(idx)
    log(f"Wallet: {wallet_addr}", "S")
    
    # ── Fill form ───────────────────────────────────
    gh_name = random_git()
    tw_name = random_git()
    log(f"GitHub: {gh_name}, Twitter: @{tw_name}", "I")
    
    for sel in ['input[placeholder*="github"]', 'input[name*="github"]', 'input[id*="github"]']:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.fill(gh_name)
                time.sleep(0.5)
                break
        except: pass
    
    for sel in ['input[placeholder*="twitter"]', 'input[name*="twitter"]', 'input[id*="twitter"]']:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.fill(tw_name)
                time.sleep(0.5)
                break
        except: pass
    
    # ── /get-code ───────────────────────────────────
    click_text(page, "rank")
    time.sleep(3)
    
    # Type /get-code in chat
    for sel in ['div[contenteditable="true"]', 'div[role="textbox"]', 'textarea']:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click()
                time.sleep(1)
                page.keyboard.type("/get-code", delay=100)
                time.sleep(1)
                page.keyboard.press("Enter")
                log("Sent /get-code", "T")
                break
        except: pass
    
    time.sleep(5)
    ss(page, "06_getcode")
    
    # Wait for bot response & faucet
    log("Waiting for bot response & faucet (120s)...", "I")
    for i in range(60):
        check_continue(page)
        time.sleep(2)
    
    # ── Genesis link ─────────────────────────────────
    click_text(page, "genesis-link") or click_text(page, "genesis")
    time.sleep(5)
    
    # Fill wallet address
    for sel in ['input[type="text"]', 'input:not([type="hidden"])', 'textarea']:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.fill(wallet_addr)
                time.sleep(0.5)
                page.keyboard.press("Enter")
                break
        except: pass
    
    time.sleep(5)
    ss(page, "07_genesis")
    
    # ── Forward RIT ──────────────────────────────────
    cfg = load_config()
    main_wallet = cfg.get("main_wallet", "")
    
    if main_wallet and wallet_addr != main_wallet:
        pik = ""
        if os.path.exists(WALLETS_FILE):
            with open(WALLETS_FILE) as f:
                for line in f:
                    m = re.search(fr'ritual_{idx+2}=(\S+)', line)
                    if m:
                        pik = m.group(1).strip()
                        break
        
        if pik:
            try:
                bal = subprocess.run(
                    f'cast balance {wallet_addr} --rpc-url {RPC} --ether 2>/dev/null',
                    shell=True, capture_output=True, text=True, timeout=10
                ).stdout.strip()
                log(f"Balance: {bal} RIT", "I")
                
                if bal and float(bal) > 0.001:
                    subprocess.run(
                        f'cast send {main_wallet} --private-key {pik} '
                        f'--value $(cast balance {wallet_addr} --rpc-url {RPC} --wei)wei '
                        f'--rpc-url {RPC} --gas-limit 21000 2>/dev/null',
                        shell=True, timeout=60
                    )
                    log("✅ Forwarded RIT to main wallet", "S")
            except: pass
    
    # ── Mark done ───────────────────────────────────
    acc["status"] = "done"
    acc["wallet"] = wallet_addr
    acc["github"] = gh_name
    save_accounts(load_accounts())
    
    log(f"✅ ACCOUNT {idx+1} DONE!", "S")
    return "done"

# ── MAIN ────────────────────────────────────────────
def main():
    accounts = load_accounts()
    if not accounts:
        log("No accounts! Create discord.txt first", "E")
        return
    
    log(f"Loaded {len(accounts)} accounts", "S")
    
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    page.set_default_timeout(15000)  # 15s default timeout
    
    try:
        for idx, acc in enumerate(accounts):
            if acc.get("status") in ("done", "skip"):
                log(f"Account {idx+1} already {acc['status']} — skip", "W")
                continue
            
            try:
                result = process_one_account(page, idx, acc)
                log(f"Account {idx+1} result: {result}", "S")
            except Exception as e:
                log(f"Account {idx+1} CRASHED: {e}", "E")
                traceback.print_exc()
                acc["status"] = "fail"
                save_accounts(accounts)
            
            if idx < len(accounts) - 1:
                log("⏳ Waiting 10s before next account...", "I")
                time.sleep(10)
    
    finally:
        browser.close()
        pw.stop()
    
    log("🏁 ALL ACCOUNTS PROCESSED!", "S")

if __name__ == "__main__":
    main()
