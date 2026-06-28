#!/usr/bin/env python3
"""
bridge_server.py — TCP server (port 5099)
Windows bridge connects here. I send commands via /tmp/bridge_cmd
"""
import socket, threading, time, os, json

BRIDGE = None  # single bridge connection

def handle(conn):
    global BRIDGE
    BRIDGE = conn
    print("BRIDGE CONNECTED!", flush=True)
    
    # Read responses from bridge
    try:
        buf = b""
        while True:
            data = conn.recv(4096)
            if not data: break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    r = json.loads(line.decode())
                    print(f"RESULT: {json.dumps(r)[:200]}", flush=True)
                except:
                    pass
    except:
        pass
    finally:
        print("BRIDGE DISCONNECTED", flush=True)
        BRIDGE = None
        conn.close()

def send(cmd):
    if BRIDGE:
        try:
            BRIDGE.sendall((json.dumps(cmd) + "\n").encode())
            return True
        except:
            BRIDGE = None
    return False

def cmd_reader():
    """Read commands from /tmp/bridge_cmd"""
    while True:
        try:
            with open("/tmp/bridge_cmd", "r") as f:
                line = f.readline().strip()
            if line:
                os.truncate("/tmp/bridge_cmd", 0)  # Hanya Python 3.7+
                cmd = json.loads(line) if line.startswith("{") else {"action": line}
                send(cmd)
        except: pass
        time.sleep(0.5)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", 5099))
server.listen(1)
print(f"BRIDGE SERVER listening on :5099", flush=True)

threading.Thread(target=cmd_reader, daemon=True).start()

while True:
    conn, addr = server.accept()
    print(f"Connection from {addr}", flush=True)
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
