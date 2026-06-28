#!/usr/bin/env python3
"""
bridge.py — TCP server di port 5099, async Playwright
Gue kirim JSON, dia jalanin di browser Windows, return JSON
"""
import asyncio, json, base64, time, sys, struct
from playwright.async_api import async_playwright

HOST = "0.0.0.0"
PORT = 5099
page = None
browser = None
pw = None

async def handle(reader, writer):
    global page
    try:
        data = await asyncio.wait_for(reader.readline(), timeout=30)
        if not data:
            return
        line = data.decode().strip()
        cmd = json.loads(line) if line.startswith("{") else {"action": line}
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
                    # Fallback: locator
                    loc = page.locator(f'text={text}')
                    if await loc.count() > 0:
                        await loc.first.click(timeout=5000)
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
                "text": await page.evaluate("document.body.innerText")[:2000]
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

        elif action == "shutdown":
            result["shutdown"] = True

        else:
            result["ok"] = False
            result["error"] = f"unknown: {action}"

        writer.write((json.dumps(result) + "\n").encode())
        await writer.drain()

        if result.get("shutdown"):
            await browser.close()
            await pw.stop()
            sys.exit(0)

    except asyncio.TimeoutError:
        pass
    except Exception as e:
        writer.write((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
        await writer.drain()
    finally:
        writer.close()

async def main():
    global page, browser, pw
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=['--start-maximized', '--disable-blink-features=AutomationControlled']
    )
    page = await browser.new_page()

    server = await asyncio.start_server(handle, HOST, PORT)
    print(f"BRIDGE READY on {HOST}:{PORT}", flush=True)

    try:
        async with server:
            await server.serve_forever()
    except:
        await browser.close()
        await pw.stop()

asyncio.run(main())
