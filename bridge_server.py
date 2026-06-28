#!/usr/bin/env python3
"""
bridge_server.py — relay antara Windows bridge (port 5099) dan gue (port 5098)
Windows ↔ port 5099 → relay → port 5098 ↔ gue (curl / socket)
Supports bridge reconnection.
"""
import socket, threading, json, sys, select

BRIDGE = None
LAST_RESULT = {"data": None}
lock = threading.Lock()

def handle_bridge(conn, addr):
    """Windows bridge connects here"""
    global BRIDGE
    old = None
    with lock:
        old = BRIDGE
        BRIDGE = conn
    if old:
        try: old.close()
        except: pass
    print(f"BRIDGE CONNECTED from {addr}", flush=True)
    
    buf = b""
    while True:
        try:
            data = conn.recv(4096)
            if not data: break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    r = json.loads(line.decode())
                    with lock:
                        LAST_RESULT["data"] = r
                    # Don't flood logs
                    if r.get("action") != "screenshot":
                        print(f"RESULT: {json.dumps(r)[:200]}", flush=True)
                except: pass
        except: break
    
    with lock:
        if BRIDGE is conn:
            BRIDGE = None
    print(f"BRIDGE DISCONNECTED from {addr}", flush=True)
    try: conn.close()
    except: pass

def handle_cmd(conn, addr):
    """Gue connects here (port 5098) — send cmd, get result"""
    buf = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data: break
            buf += data
            if b"\n" in buf:
                cmd_line, buf = buf.split(b"\n", 1)
                cmd = json.loads(cmd_line.decode())
                
                with lock:
                    bridge = BRIDGE
                
                if not bridge:
                    conn.sendall(json.dumps({"ok": False, "error": "bridge disconnected"}).encode() + b"\n")
                    continue
                
                # Forward to Windows bridge
                try:
                    bridge.sendall((json.dumps(cmd) + "\n").encode())
                except:
                    conn.sendall(json.dumps({"ok": False, "error": "send failed"}).encode() + b"\n")
                    continue
                
                # Wait for response
                import time
                waited = 0
                result = None
                while waited < 12:
                    time.sleep(0.5)
                    waited += 0.5
                    with lock:
                        r = LAST_RESULT.get("data")
                    if r:
                        result = r
                        with lock:
                            LAST_RESULT["data"] = None
                        break
                
                if result:
                    conn.sendall((json.dumps(result) + "\n").encode())
                else:
                    conn.sendall((json.dumps({"ok": False, "error": "timed out"}) + "\n").encode())
    except:
        pass
    try: conn.close()
    except: pass

# Start servers
server_b = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_b.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_b.bind(("0.0.0.0", 5099))
server_b.listen(5)
server_b.setblocking(False)

server_c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_c.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_c.bind(("0.0.0.0", 5098))
server_c.listen(5)
server_c.setblocking(False)

print("BRIDGE SERVER: Windows port 5099 | CMD port 5098 (persistent)", flush=True)

# Event loop with select — handles both ports
sockets = [server_b, server_c]
while True:
    readable, _, _ = select.select(sockets, [], [], 1.0)
    for s in readable:
        conn, addr = s.accept()
        if s is server_b:
            print(f"Bridge connecting from {addr}...", flush=True)
            threading.Thread(target=handle_bridge, args=(conn, addr), daemon=True).start()
        else:
            print(f"CMD from {addr}", flush=True)
            threading.Thread(target=handle_cmd, args=(conn, addr), daemon=True).start()
