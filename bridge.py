#!/usr/bin/env python3
"""
bridge.py — Connect ke server, terima JSON commands, jalanin di browser
Windows: python bridge.py 76.13.18.146 5099
"""
import asyncio, json, base64, time, sys
from playwright.async_api import async_playwright

SERVER_HOST = sys.argv[1] if len(sys.argv) > 1 else "76.13.18.146"
SERVER_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5099
page = None
browser = None

async def main():
    global page, browser
    
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=['--start-maximized', '--disable-blink-features=AutomationControlled']
    )
    page = await browser.new_page()
    
    print(f"Browser ready — connecting to {SERVER_HOST}:{SERVER_PORT}", flush=True)
    
    # Connect to server
    reader, writer = await asyncio.open_connection(SERVER_HOST, SERVER_PORT)
    print(f"Connected! Waiting for commands...", flush=True)
    
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=60)
            if not line:
                break
            cmd = json.loads(line.decode().strip())
            action = cmd.get("action", "")
            result = {"ok": True}
            
            if action == "screenshot":
                b = await page.screenshot(full_page=False)
                result["image_base64"] = base64.b64encode(b).decode()
                result["size"] = len(b)
            
            elif action == "navigate":
                url = cmd.get("url", "")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                result["url"] = page.url
            
            elif action == "click_text":
                text = cmd.get("text", "")
                try:
                    el = page.get_by_text(text, exact=False)
                    if await el.count() > 0:
                        await el.first.click(timeout=5000)
                        await asyncio.sleep(0.5)
                        result["clicked"] = text
                    else:
                        result["ok"] = False
                        result["not_found"] = text
                except Exception as e:
                    result["ok"] = False
                    result["error"] = str(e)
            
            elif action == "type":
                text = cmd.get("text", "")
                await page.keyboard.type(text, delay=50)
                result["typed"] = text
            
            elif action == "press":
                key = cmd.get("key", "Enter")
                await page.keyboard.press(key)
                result["key"] = key
            
            elif action == "status":
                result.update({
                    "url": page.url,
                    "title": await page.title(),
                    "text": (await page.evaluate("document.body.innerText"))[:2000]
                })
            
            elif action == "wait":
                sec = int(cmd.get("seconds", 3))
                await asyncio.sleep(sec)
                result["waited"] = sec
            
            elif action == "eval":
                js = cmd.get("js", "")
                r = await page.evaluate(js)
                result["result"] = str(r)[:2000]
            
            elif action == "fill":
                text = cmd.get("text", "")
                sel = cmd.get("selector", "input")
                el = page.locator(sel).first
                await el.fill(text)
                result["filled"] = text
            
            else:
                result["ok"] = False
                result["error"] = f"unknown: {action}"
            
            writer.write((json.dumps(result) + "\n").encode())
            await writer.drain()
            
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            writer.write((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
            await writer.drain()
    
    writer.close()
    await browser.close()
    await pw.stop()

asyncio.run(main())
