#!/usr/bin/env python3
"""
Ritual AutoFaucet Launcher — starts Browser API (port 5001)
AI = Hermes (vision_analyze + terminal)

Cara pake:
  1. python app.py                 → starts browser + API
  2. python browser_api.py         → same thing

Hermes (gue) yg jadi AI-nya:
  terminal("curl localhost:5001/api/screenshot | ...")  → get screenshot
  vision_analyze("screenshot.png")                       → lihat browser
  terminal("curl -X POST localhost:5001/api/action ...") → klik/type

Contoh:
  # Dapat screenshot
  curl localhost:5001/api/screenshot > ss.json

  # Klik "Continue in Browser"
  curl -X POST localhost:5001/api/action \
    -H "Content-Type: application/json" \
    -d '{"action":"click_text","text":"Continue in Browser"}'

  # Multi action (execute sequence)
  curl -X POST localhost:5001/api/action \
    -H "Content-Type: application/json" \
    -d '{"action":"multi","actions":[
      {"action":"click_text","text":"Email"},
      {"action":"type","text":"user@email.com"},
      {"action":"press_key","key":"Tab"},
      {"action":"type","text":"password123"},
      {"action":"click_text","text":"Log In"}
    ]}'
"""
import os, sys, subprocess, time, signal

BASE = os.path.dirname(os.path.abspath(__file__))
API_SCRIPT = os.path.join(BASE, "browser_api.py")

def log(msg):
    print(f"[LAUNCHER] {msg}", flush=True)

if __name__ == "__main__":
    port = os.getenv("API_PORT", "5001")
    log(f"🚀 Starting Browser API on port {port}...")
    log(f"🧠 AI: Hermes (vision + terminal)")
    log(f"📸 Screenshots: {os.path.join(BASE, 'screenshots')}/")
    log(f"")
    log(f"  curl {os.uname().nodename}:{port}/api/status")
    log(f"  curl {os.uname().nodename}:{port}/api/screenshot")
    log(f"  curl -X POST {os.uname().nodename}:{port}/api/action -d '{{\"action\":\"click_text\",\"text\":\"Login\"}}'")
    log(f"")

    # Start browser API
    proc = subprocess.Popen(
        [sys.executable, API_SCRIPT],
        env={**os.environ, "API_PORT": str(port)},
        stdout=sys.stdout, stderr=sys.stderr
    )

    def cleanup(s, f):
        log("Shutting down...")
        proc.terminate()
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    proc.wait()
