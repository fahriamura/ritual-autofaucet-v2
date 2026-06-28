"""
start_chrome.bat — jalankan Chrome dengan remote debugging port 9222
Double-click aja, atau run dari terminal.
"""
import subprocess, os, sys

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

chrome = None
for p in CHROME_PATHS:
    if os.path.exists(p):
        chrome = p
        break

if not chrome:
    print("Chrome not found! Install Chrome dulu.")
    sys.exit(1)

USER_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")
os.makedirs(USER_DATA, exist_ok=True)

print(f"Starting Chrome: {chrome}")
print(f"Profile: {USER_DATA}")
print(f"Debug port: 9222")
print()

subprocess.Popen([
    chrome,
    f"--remote-debugging-port=9222",
    f"--user-data-dir={USER_DATA}",
    "--no-first-run",
    "--no-default-browser-check",
    "--start-maximized",
], shell=False)

print("✅ Chrome started with remote debugging!")
print("Now forward the port via SSH:")
print("  ssh -R 9222:localhost:9222 root@76.13.18.146")
print()

input("Press Enter to close Chrome...")
