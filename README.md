# 🌊 Ritual AutoFaucet — Visible Browser Edition

AutoFaucet Ritual dengan **Chromium visible** — lo liat browsernya, tinggal klik captcha manual, sisanya otomatis.

## Cara Kerja

```
1. Buka http://localhost:5000 di Chromium lo
2. Paste accounts + config
3. Klik "Start AutoFaucet"
4. Chromium TERBUKA (visible) — lo bisa liat semua step
5. Kalo ada captcha → lo klik MANUAL
6. Sisanya auto: login, wallet, input GitHub, claim faucet
```

## Kenapa Visible Browser?

Banyak situs (Discord, faucet) pake captcha canggih yang gak bisa di-solve otomatis. Dengan browser **visible**, lo tinggal:

- ✅ Liat browser kebuka sendiri
- ✅ Klik captcha pas muncul
- ✅ Sisanya jalan otomatis (login, create wallet, isi form, dll)

## Instalasi

```bash
git clone https://github.com/fahriamura/ritual-autofaucet-v2.git
cd ritual-autofaucet-v2

# Install Python deps
pip install flask playwright
playwright install chromium

# Butuh cast (Foundry) buat transaksi RIT
# Download: https://book.getfoundry.sh/getting-started/installation

# Jalankan
python3 app.py
```

## Cara Pakai

1. **Accounts** — paste array JSON akun Discord:
   ```json
   [
     {"email": "user@op.pl", "password": "pass123", "username": "user1", "email_password": "epass", "status": "pending"},
     {"email": "user2@op.pl", "password": "pass456", "username": "user2", "email_password": "epass", "status": "pending"}
   ]
   ```
2. **Config** — isi main wallet address + private keys
3. **Start** — klik tombol, browser terbuka, kerjain captcha manual
4. Pantau log & status akun di web UI

## Fitur

- ✅ Chromium visible — lo interaksi langsung
- ✅ Web UI — kontrol dari browser
- ✅ Real-time log — streaming ke web
- ✅ Status akun per-step
- ✅ Auto forward RIT ke main wallet
- ✅ Random GitHub name generator
- ✅ Multi-account support

## Struktur

```
ritual-autofaucet-v2/
├── app.py            # Main app (Flask + Playwright)
├── accounts.json     # Accounts data (auto-generated)
├── config.json       # Config data (auto-generated)
└── README.md
```

## Author

[fahriamura](https://github.com/fahriamura)
