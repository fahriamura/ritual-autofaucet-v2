
import asyncio, json, sys
from playwright.async_api import async_playwright

async def main():
    pw = await async_playwright().start()
    
    # Connect ke Chrome di Windows via SSH tunnel WebSocket
    # Karena HTTP gak jalan, kita coba langsung websocket
    ws_url = "ws://localhost:9222/devtools/browser/"
    
    # Get browser endpoint
    import aiohttp
    async with aiohttp.ClientSession() as session:
        # First get the page list via HTTP
        try:
            async with session.get("http://localhost:9222/json", timeout=5) as resp:
                pages = await resp.json()
                print("PAGES:", json.dumps(pages, indent=2))
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    print("WS URL:", ws_url)
        except Exception as e:
            print(f"HTTP failed: {e}")
            
            # Try direct websocket to browser
            try:
                async with session.get("http://localhost:9222/json/version", timeout=5) as resp:
                    version = await resp.json()
                    ws_url = version["webSocketDebuggerUrl"]
                    print("Browser WS:", ws_url)
            except Exception as e2:
                print(f"Version endpoint failed: {e2}")
    
    await pw.stop()

asyncio.run(main())
