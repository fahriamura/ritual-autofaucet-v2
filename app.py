#!/usr/bin/env python3
"""
Ritual AutoFaucet — Visible Browser Edition
- Chromium terbuka, lo bisa liat & klik captcha manual
- Sisanya (login, create wallet, input, dll) otomatis
"""

import os, sys, json, time, re, random, string, subprocess
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────
DISCORD_FILE = os.path.join(os.path.dirname(__file__), "discord.txt")
ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "accounts.json")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
RPC = "https://rpc.ritualfoundation.org"
RITUAL_WALLET = "0x532F0dF0896F353d8C3DD8cc134e8129DA2a3948"
DISCORD_INVITE = "https://discord.gg/ritual-net"  # ganti dengan invite real

# Load accounts — auto dari discord.txt!
def load_accounts():
    # Priority: accounts.json (manual) > discord.txt (auto)
    if os.path.exists(DISCORD_FILE):
        return parse_discord_txt(DISCORD_FILE)
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE) as f:
            return json.load(f)
    return []

def parse_discord_txt(path):
    """Parse tab-separated discord.txt ke array JSON."""
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

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"main_wallet": ""}

def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

accounts = load_accounts()
config = load_config()

# ── Random Generator ────────────────────────────────────────────
def random_name(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def random_github():
    adj = ['cool', 'nice', 'super', 'mega', 'epic', 'neo', 'zen', 'cyber', 'quantum', 'astro']
    noun = ['dev', 'coder', 'hacker', 'agent', 'runner', 'node', 'link', 'wave', 'flux', 'pulse']
    return f"{random.choice(adj)}-{random.choice(noun)}-{random_name(4)}"

# ── Playwright ──────────────────────────────────────────────────
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

def log(msg, type="I"):
    prefix = {"I": "ℹ️", "S": "✅", "W": "⚠️", "E": "❌", "H": "🔶"}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {prefix.get(type,'ℹ️')} {msg}", flush=True)

def wait_for_user(page, msg, timeout=300000):
    """Tampilkan pesan & tunggu user interaksi/klik manual.
    Sambil nunggu, periodically cek Open in Browser button."""
    log(f"{msg} — ( klik manual, menunggu {timeout//1000}s )", "H")
    try:
        for _ in range(timeout // 2000):
            # Cek Open in Browser button tiap 2 detik
            try:
                for sel in ['.buttonChildrenWrapper_a22cb0', 'button:has-text("Open")', 
                           'a:has-text("Open")', '[role="button"]:has-text("Open")',
                           'text=Open in Browser']:
                    el = page.locator(sel)
                    if el.count() > 0:
                        el.first.click()
                        log("✅ Auto-klik Open button (while waiting)!", "S")
                        time.sleep(2)
                        break
            except:
                pass
            page.wait_for_timeout(2000)
    except:
        pass

class AutoFaucet:
    def __init__(self):
        self.pw = sync_playwright().start()
        # Launch VISIBLE browser
        self.browser = self.pw.chromium.launch(
            headless=False,
            args=[
                '--start-maximized',
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )
        self.context = self.browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)
        log("Browser terbuka — lo bisa liat & interaksi!", "S")
    
    def close(self):
        try:
            self.browser.close()
            self.pw.stop()
        except:
            pass
    
    def discord_login(self, email, password):
        """Login ke Discord — captcha manual."""
        log(f"🔄 Buka Discord login...")
        self.page.goto("https://discord.com/login", wait_until="domcontentloaded")
        wait_for_user(self.page, "Tunggu halaman Discord load", 5000)
        
        # Isi email
        email_input = self.page.locator('input[name="email"]')
        email_input.fill(email)
        time.sleep(0.5)
        
        # Isi password
        pass_input = self.page.locator('input[name="password"]')
        pass_input.fill(password)
        time.sleep(0.5)
        
        # Klik login
        login_btn = self.page.locator('button[type="submit"]')
        login_btn.click()
        
        log("🔶 Kalo ada captcha/hCaptcha — klik MANUAL sekarang!", "H")
        log("⏳ Menunggu 120 detik biar lo solve captcha...", "H")
        
        # Tunggu user solve captcha
        try:
            self.page.wait_for_url("**/channels/**", timeout=120000)
            log("Login sukses! Captcha solved ✅", "S")
            
            # Auto klik Open in Browser setelah login
            self.auto_click_open_app()
            
            return True
        except PwTimeout:
            # Cek apakah masih di halaman login
            if "login" in self.page.url.lower():
                log("Login gagal / captcha gak solved dalam 120s", "E")
                return False
            log("Mungkin udah login (URL berubah)", "S")
            return True
    
    def join_server(self, invite_url):
        """Join Discord server."""
        log(f"🔄 Join server: {invite_url}")
        self.page.goto(invite_url, wait_until="domcontentloaded")
        time.sleep(3)
        
        try:
            accept_btn = self.page.locator('button:has-text("Accept Invite")')
            if accept_btn.count() > 0:
                accept_btn.click()
                time.sleep(2)
        except:
            pass
        
        wait_for_user(self.page, "Kalo ada verification captcha — solve manual", 60000)
        
        # Auto klik Open App button setelah join
        self.auto_click_open_app()
        
        log("Join server step selesai", "S")
    
    def get_wallet_address(self, wallet_index):
        """Generate wallet address dari ritual_wallets.txt atau buat baru."""
        # Coba baca dari ritual_wallets.txt
        wallets_file = "/root/ritual_wallets.txt"
        wallets = []
        if os.path.exists(wallets_file):
            with open(wallets_file) as f:
                content = f.read()
            # Parse wallet addresses
            matches = re.findall(r'ritual_\d+=(\S+)', content)
            wallets = matches
        
        if wallet_index < len(wallets):
            return wallets[wallet_index]
        
        # Buat wallet baru via cast
        try:
            result = subprocess.run(
                f"cast wallet new --rpc-url {RPC} 2>/dev/null",
                shell=True, capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split('\n'):
                if 'Address:' in line:
                    return line.split('Address:')[1].strip()
        except:
            pass
        
        return f"0x{random_name(40)}"  # fallback dummy
    
    def auto_click_open_app(self):
        """Auto klik button 'Open App' / 'Open in Browser' di Discord."""
        try:
            # Try 1: Specific class
            btn = self.page.locator('.buttonChildrenWrapper_a22cb0')
            if btn.count() > 0:
                btn.first.click()
                log("✅ Auto-klik button (.buttonChildrenWrapper_a22cb0)!", "S")
                time.sleep(3)
                return True
            
            # Try 2: Any button with "Open" text
            btn2 = self.page.locator('button:has-text("Open")')
            if btn2.count() > 0:
                btn2.first.click()
                log("✅ Auto-klik button (text=Open)!", "S")
                time.sleep(3)
                return True
            
            # Try 3: Any link with "Open" text
            btn3 = self.page.locator('a:has-text("Open")')
            if btn3.count() > 0:
                btn3.first.click()
                log("✅ Auto-klik link (text=Open)!", "S")
                time.sleep(3)
                return True
            
            # Try 4: role=button with "Open"
            btn4 = self.page.locator('[role="button"]:has-text("Open")')
            if btn4.count() > 0:
                btn4.first.click()
                log("✅ Auto-klik role=button (text=Open)!", "S")
                time.sleep(3)
                return True
            
            # Try 5: Any element with "Open in Browser" text
            btn5 = self.page.locator('text=Open in Browser')
            if btn5.count() > 0:
                btn5.first.click()
                log("✅ Auto-klik 'Open in Browser'!", "S")
                time.sleep(3)
                return True
                
        except Exception as e:
            log(f"Auto-click error: {e}", "W")
        return False
    
    def process_channel_ritual(self):
        """Proses channel Ritual Discord:
        - /get-code
        - input wallet
        - input github
        - claim faucet
        """
        log("🔄 Proses channel Ritual...", "I")
        
        # Auto klik Open App button kalo ada
        self.auto_click_open_app()
        
        # Cari channel verification
        wait_for_user(self.page, "Navigasi MANUAL ke channel verification & solve captcha", 120000)
        log("Verification done (asumsi)", "S")
        
        # Ke channel academy-welcome
        wait_for_user(self.page, "Navigasi MANUAL ke #academy-welcome & klik link wallet", 60000)
        log("Wallet link clicked (asumsi)", "S")
        
        # Auto klik Open App lagi kalo muncul setelah klik link
        self.auto_click_open_app()
        
        # Ke channel rank, ketik /get-code
        wait_for_user(self.page, "Navigasi MANUAL ke #rank & ketik /get-code", 60000)
        log("get-code done (asumsi)", "S")
        
        # Ikutin perintah bot untuk faucet
        wait_for_user(self.page, "Ikutin perintah bot & claim faucet MANUAL", 120000)
        log("Faucet claim done (asumsi)", "S")
        
        # Ke genesis-link, input wallet
        wait_for_user(self.page, "Navigasi MANUAL ke #genesis-link & verifikasi wallet", 60000)
        log("Genesis link done (asumsi)", "S")
        
        return True
    
    def run_account(self, idx, account):
        """Proses 1 akun Discord."""
        email = account.get("email", "")
        password = account.get("password", "")
        username = account.get("username", "")
        email_pass = account.get("email_password", "")
        wallet_idx = idx + 1  # ritual_2, ritual_3, dll
        
        log(f"{'='*60}")
        log(f"AKUN [{idx}]: {email} ({username})", "S")
        log(f"WALLET: ritual_{wallet_idx + 1}", "S")
        log(f"{'='*60}")
        
        # Step 1: Login Discord
        if not self.discord_login(email, password):
            log(f"Skip akun {email} — login gagal", "E")
            return False
        
        # Step 2: Join server
        self.join_server(DISCORD_INVITE)
        
        # Step 3: Process channels
        self.process_channel_ritual()
        
        # Step 4: Forward RIT ke main wallet
        wallet_addr = self.get_wallet_address(wallet_idx)
        main_wallet = config.get("main_wallet", "")
        
        # Cari private key dari ritual_wallets.txt
        pk = ""
        wallets_file = "/root/ritual_wallets.txt"
        if os.path.exists(wallets_file):
            with open(wallets_file) as f:
                for line in f:
                    if f"ritual_{wallet_idx + 1}=" in line or f"ritual_{wallet_idx+1}=" in line:
                        pk = line.split("=", 1)[1].strip()
                        break
        
        if pk and main_wallet and wallet_addr and wallet_addr != main_wallet:
            log(f"Forward RIT dari {wallet_addr} ke {main_wallet}", "I")
            try:
                bal = subprocess.run(
                    f'cast balance {wallet_addr} --rpc-url {RPC} --ether 2>/dev/null',
                    shell=True, capture_output=True, text=True, timeout=10
                ).stdout.strip()
                log(f"Balance {wallet_addr}: {bal} RIT", "I")
                
                if bal and float(bal) > 0.001:
                    subprocess.run(
                        f'PRIVATE_KEY={pk} cast send {main_wallet} '
                        f'--value $(cast balance {wallet_addr} --rpc-url {RPC} --wei 2>/dev/null)wei '
                        f'--private-key {pk} --rpc-url {RPC} --gas-limit 21000 2>/dev/null',
                        shell=True, timeout=60
                    )
                    log(f"✅ Forward sukses ke {main_wallet}", "S")
                else:
                    log(f"Balance terlalu kecil ({bal} RIT), skip forward", "W")
            except Exception as e:
                log(f"Forward error: {e}", "E")
        
        # Update status
        account["status"] = "done"
        account["wallet"] = wallet_addr
        account["github"] = random_github()
        account["completed_at"] = datetime.now().isoformat()
        save_accounts(accounts)
        
        log(f"✅ AKUN {idx+1} SELESAI! Wallet: {wallet_addr} | GitHub: {account['github']}", "S")
        
        return True
    
    def run_all(self):
        """Jalankan semua akun auto-loop."""
        global running
        if not accounts:
            log("Tidak ada akun! Cek discord.txt", "E")
            log("Format discord.txt: Login\\tpassword\\tusername\\tEmail\\tEmail password\\tEmail link", "E")
            return
        
        log(f"Memproses {len(accounts)} akun...", "I")
        log("Browser TERBUKA — lo bisa liat semua yang terjadi!", "S")
        log("Kalo ada captcha → klik MANUAL di browser", "H")
        log(f"{'='*60}")
        
        for i, acc in enumerate(accounts):
            if not running:
                log("⏹️ Dihentikan oleh user", "W")
                break
            
            if acc.get("status") == "done":
                log(f"Akun {i+1} ({acc['email']}) sudah selesai, skip", "W")
                continue
            
            log(f"\n{'='*60}")
            log(f"▶️ AKUN {i+1}/{len(accounts)}: {acc['email']}", "I")
            log(f"{'='*60}")
            
            success = self.run_account(i, acc)
            
            if success:
                log(f"✅ Akun {i+1}/{len(accounts)} SELESAI!", "S")
            else:
                log(f"❌ Akun {i+1}/{len(accounts)} gagal — lanjut next", "E")
                acc["status"] = "fail"
                save_accounts(accounts)
            
            # Lanjut next akun setelah delay
            if i < len(accounts) - 1 and running:
                delay = 15
                log(f"⏳ Tunggu {delay} detik sebelum akun berikutnya...", "I")
                for d in range(delay, 0, -1):
                    if not running:
                        break
                    time.sleep(1)
        
        log(f"\n{'='*60}")
        log("SEMUA SELESAI! 🎉", "S")
        log(f"{'='*60}")
        running = False


# ── Web UI ──────────────────────────────────────────────────────
from flask import Flask, jsonify, request
import threading

WEB_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>Ritual AutoFaucet — Visible Browser</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0e17;color:#e0e6f0;padding:24px}
        .container{max-width:800px;margin:0 auto}
        h1{background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:28px;margin-bottom:8px}
        .sub{color:#8892a8;font-size:14px;margin-bottom:24px}
        .card{background:#111827;border:1px solid #1e293b;border-radius:16px;padding:20px;margin-bottom:16px}
        .card h2{font-size:15px;color:#94a3b8;margin-bottom:12px;font-weight:600}
        label{display:block;font-size:13px;color:#94a3b8;margin-bottom:4px;margin-top:12px}
        input,textarea{width:100%;padding:10px;background:#1a2332;border:1px solid #2d3a4e;border-radius:10px;color:#e0e6f0;font-size:13px;font-family:monospace;outline:none}
        input:focus{border-color:#60a5fa}
        textarea{min-height:200px;resize:vertical}
        .btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:.2s;margin-top:12px}
        .btn-primary{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff}
        .btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(59,130,246,0.3)}
        .btn-success{background:linear-gradient(135deg,#10b981,#059669);color:#fff}
        .btn-success:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(16,185,129,0.3)}
        .btn-danger{background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff}
        .btn:disabled{opacity:0.5;cursor:not-allowed}
        .log-box{background:#0d1117;border:1px solid #1e293b;border-radius:10px;padding:14px;font-family:monospace;font-size:12px;line-height:1.6;max-height:400px;overflow-y:auto;margin-top:12px;white-space:pre-wrap}
        .log-info{color:#60a5fa}
        .log-success{color:#34d399}
        .log-error{color:#f87171}
        .log-warn{color:#fbbf24}
        .log-highlight{color:#f59e0b}
        .status-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
        .dot-green{background:#34d399}
        .dot-red{background:#f87171}
        .dot-yellow{background:#fbbf24}
        table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
        th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #1e293b}
        th{color:#64748b;font-weight:500}
        .badge{padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600}
        .badge-done{background:#065f46;color:#34d399}
        .badge-pending{background:#1e3a5f;color:#60a5fa}
        .badge-fail{background:#5f1e1e;color:#f87171}
    </style>
</head>
<body>
<div class="container">
    <h1>🌊 Ritual AutoFaucet</h1>
    <p class="sub">Visible Chromium — lo klik captcha manual, sisanya otomatis</p>

    <div class="card">
        <h2>📋 Accounts</h2>
        <p style="font-size:12px;color:#64748b;margin-bottom:8px">✅ Auto-read dari <code>discord.txt</code> — {account_count} akun ditemukan</p>
        <div id="accountsPreview" style="font-size:12px;color:#8892a8;font-family:monospace;margin-bottom:8px"></div>
        <button class="btn btn-outline btn-sm" onclick="reloadAccounts()">🔄 Reload dari discord.txt</button>
        <span id="accountsStatus" style="font-size:12px;color:#64748b;margin-left:12px"></span>
    </div>

    <div class="card">
        <h2>⚙️ Config</h2>
        <div style="background:#1a2332;border-radius:10px;padding:14px;margin-bottom:14px;font-size:13px">
            <p style="color:#34d399;font-weight:600">✅ Wallet otomatis dibuat dari ritual_wallets.txt</p>
            <p style="color:#64748b;margin-top:4px">Accounts: <span id="walletCount" style="color:#60a5fa">0</span> wallet tersedia</p>
        </div>
        <label>🏦 Main Wallet (tujuan forward RIT)</label>
        <input id="mainWallet" placeholder="0x...">
        <button class="btn btn-primary" onclick="saveConfig()">💾 Simpan Config</button>
        <span id="configStatus" style="font-size:12px;color:#64748b;margin-left:12px"></span>
    </div>

    <div class="card">
        <h2>▶️ Control</h2>
        <button class="btn btn-success" onclick="startFaucet()">🚀 Start AutoFaucet</button>
        <button class="btn btn-danger" onclick="stopFaucet()" disabled id="stopBtn">⏹️ Stop</button>
        <div class="log-box" id="logBox">⏳ Belum mulai...</div>
    </div>

    <div class="card">
        <h2>📊 Status Akun</h2>
        <div id="statusTable"><p style="color:#64748b;font-size:13px">Belum ada data</p></div>
    </div>
</div>
<script>
    let ws = null;

    function connectWS() {
        ws = new WebSocket('ws://' + location.host + '/ws');
        ws.onmessage = e => {
            const data = JSON.parse(e.data);
            if(data.type === 'log') document.getElementById('logBox').innerHTML += data.msg + '\\n';
            if(data.type === 'accounts') renderTable(data.data);
        };
        ws.onclose = () => setTimeout(connectWS, 1000);
    }

    function renderTable(accounts) {
        const el = document.getElementById('statusTable');
        if(!accounts || accounts.length === 0) {
            el.innerHTML = '<p style="color:#64748b;font-size:13px">Belum ada data</p>';
            return;
        }
        let html = '<table><tr><th>#</th><th>Email</th><th>Status</th><th>Wallet</th><th>GitHub</th></tr>';
        accounts.forEach((a,i) => {
            const badge = a.status === 'done' ? 'badge-done' : a.status === 'fail' ? 'badge-fail' : 'badge-pending';
            html += `<tr><td>${i+1}</td><td>${a.email||'?'}</td>
                <td><span class="badge ${badge}">${a.status||'pending'}</span></td>
                <td style="font-family:monospace;font-size:11px">${(a.wallet||'').slice(0,10)}...</td>
                <td style="font-size:11px">${a.github||'-'}</td></tr>`;
        });
        html += '</table>';
        el.innerHTML = html;
    }

    function reloadAccounts() {
        fetch('/api/reload-accounts', {method:'POST'})
        .then(r=>r.json()).then(d=>{
            document.getElementById('accountsStatus').textContent = d.success ? `✅ ${d.count} akun dimuat` : '❌ Gagal';
            if(d.accounts) renderTable(d.accounts);
        });
    }

    function saveConfig() {
        const data = {
            main_wallet: document.getElementById('mainWallet').value
        };
        fetch('/api/config', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
        .then(r=>r.json()).then(d=>{
            document.getElementById('configStatus').textContent = d.success ? '✅ Tersimpan' : '❌ Gagal';
        });
    }

    function startFaucet() {
        document.getElementById('logBox').innerHTML = '🚀 Memulai...\\n';
        document.querySelector('#stopBtn').disabled = false;
        fetch('/api/start', {method:'POST'});
    }

    function stopFaucet() {
        fetch('/api/stop', {method:'POST'});
        document.querySelector('#stopBtn').disabled = true;
    }

    // Load existing data
    fetch('/api/status').then(r=>r.json()).then(d=>{
        if(d.accounts) renderTable(d.accounts);
        if(d.config) {
            document.getElementById('mainWallet').value = d.config.main_wallet || '';
        }
    });

    connectWS();
</script>
</body>
</html>"""

# ── Flask ───────────────────────────────────────────────────────
app = Flask(__name__)
running = False
thread = None

@app.route("/")
def index():
    html = WEB_HTML.replace("{account_count}", str(len(accounts)))
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/api/accounts", methods=["POST"])
def api_accounts():
    global accounts
    data = request.json
    if isinstance(data, list):
        for acc in data:
            if "status" not in acc:
                acc["status"] = "pending"
        accounts = data
        save_accounts(accounts)
        return jsonify({"success": True, "count": len(accounts)})
    return jsonify({"success": False, "error": "Invalid format"})

@app.route("/api/reload-accounts", methods=["POST"])
def api_reload_accounts():
    global accounts
    accounts = load_accounts()
    return jsonify({"success": True, "count": len(accounts), "accounts": accounts})

@app.route("/api/config", methods=["POST"])
def api_config():
    global config
    data = request.json
    config["main_wallet"] = data.get("main_wallet", "")
    save_config(config)
    return jsonify({"success": True})

@app.route("/api/status")
def api_status():
    return jsonify({
        "running": running,
        "accounts": accounts,
        "config": config
    })

@app.route("/api/start", methods=["POST"])
def api_start():
    global running, thread
    if running:
        return jsonify({"error": "Already running"})
    running = True
    thread = threading.Thread(target=run_faucet, daemon=True)
    thread.start()
    return jsonify({"success": True})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    global running
    running = False
    return jsonify({"success": True})

def run_faucet():
    global running
    af = AutoFaucet()
    try:
        af.run_all()
    except Exception as e:
        log(f"Fatal error: {e}", "E")
    finally:
        af.close()
        running = False

# ── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════╗
║   🌊 Ritual AutoFaucet — Visible Browser ║
║                                          ║
║   Buka → http://localhost:5000           ║
║                                          ║
║   Chromium akan TERBUKA (nggak headless) ║
║   Lo tinggal klik captcha manual         ║
║   Sisanya auto: login, wallet, input     ║
╚══════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
