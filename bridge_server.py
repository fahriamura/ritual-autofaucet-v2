#!/usr/bin/env python3
"""
bridge_server.py — relay antara Windows bridge (port 5099) dan gue (port 5098)
Windows ↔ port 5099 → relay → port 5098 ↔ gue (curl / socket)
"""
import socket, threading, json, sys

BRIDGE = None
lock = threading.Lock()

def handle_bridge(conn):
    """Windows bridge connects here"""
    global BRIDGE
    with lock:
        BRIDGE = conn
    print("BRIDGE CONNECTED!", flush=True)
    
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
                    print(f"RESULT: {json.dumps(r)[:200]}", flush=True)
                    # Store last result
                    with lock:
                        LAST_RESULT["data"] = r
                except: pass
        except: break
    
    with lock:
        BRIDGE = None
    print("BRIDGE DISCONNECTED", flush=True)

def handle_cmd(conn):
    """Gue connects here (port 5098) — send cmd, get result"""
    buf = b""
    while True:
        try:
            data = conn.recv(4096)
            if not data: break
            buf += data
            if b"\n" in buf:
                cmd_line, buf = buf.split(b"\n", 1)
                cmd = json.loads(cmd_line.decode())
                
                with lock:
                    if not BRIDGE:
                        conn.sendall(json.dumps({"ok": False, "error": "bridge disconnected"}).encode() + b"\n")
                        continue
                    # Forward to Windows bridge
                    try:
                        BRIDGE.sendall((json.dumps(cmd) + "\n").encode())
                    except:
                        conn.sendall(json.dumps({"ok": False, "error": "send failed"}).encode() + b"\n")
                        continue
                
                # Wait for response
                # Note: handle_bridge stores in LAST_RESULT
                import time
                time.sleep(2)
                
                with lock:
                    result = LAST_RESULT.get("data", {"ok": True, "status": "sent"})
                    LAST_RESULT["data"] = None
                
                conn.sendall((json.dumps(result) + "\n").encode())
        except: break
    conn.close()

LAST_RESULT = {"data": None}

# Start servers
server_b = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_b.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_b.bind(("0.0.0.0", 5099))
server_b.listen(1)

server_c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_c.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_c.bind(("0.0.0.0", 5098))
server_c.listen(1)

print("BRIDGE SERVER: Windows port 5099 | CMD port 5098", flush=True)

# Accept bridge connection
b_conn, b_addr = server_b.accept()
print(f"Bridge from {b_addr}", flush=True)
threading.Thread(target=handle_bridge, args=(b_conn,), daemon=True).start()

# Accept cmd connections
while True:
    c_conn, c_addr = server_c.accept()
    print(f"CMD from {c_addr}", flush=True)
    threading.Thread(target=handle_cmd, args=(c_conn,), daemon=True).start()
