#!/usr/bin/env python3
"""CDP client — connects to Chrome DevTools Protocol via SSH tunnel"""
import json, urllib.request, sys, time

HOST = "localhost"
PORT = 9222

def get(path):
    try:
        url = f"http://{HOST}:{PORT}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def ws_send(ws_url, method, params=None):
    """Send CDP command via WebSocket (requires websocket-client)"""
    try:
        from websocket import create_connection
        ws = create_connection(ws_url, timeout=10)
        msg = {"id": 1, "method": method, "params": params or {}}
        ws.send(json.dumps(msg))
        reply = json.loads(ws.recv())
        ws.close()
        return reply
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # 1. Get version info
    ver = get("/json/version")
    print("VERSION:", json.dumps(ver, indent=2))
    
    # 2. Get targets (tabs)
    targets = get("/json/list")
    print("\nTABS:", json.dumps(targets, indent=2)[:500])
    
    # 3. If targets available, get the first one
    if isinstance(targets, list) and targets:
        ws_url = targets[0].get("webSocketDebuggerUrl", "")
        if ws_url:
            print(f"\nWS URL: {ws_url}")
            
            # Navigate to Discord
            result = ws_send(ws_url, "Page.navigate", {"url": "https://discord.com/login"})
            print(f"Navigated: {json.dumps(result, indent=2)}")
