#!/usr/bin/env python3
"""Server — terima koneksi bridge.py dari Windows, forward commands"""
import asyncio, json, sys, os

bridge_writer = None
pending = {}

async def handle_client(reader, writer):
    global bridge_writer
    bridge_writer = writer
    peername = writer.get_extra_info('peername')
    print(f"BRIDGE CONNECTED from {peername}", flush=True)
    
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=300)
            if not line: break
            data = line.decode().strip()
            msg = json.loads(data)
            req_id = msg.get("id", "")
            if req_id and req_id in pending:
                pending[req_id].set_result(msg)
            else:
                print(f"RESP: {json.dumps(msg)[:200]}", flush=True)
        except asyncio.TimeoutError:
            break
        except: break
    
    bridge_writer = None
    print("Bridge disconnected", flush=True)

async def handle_cmd(reader, writer):
    """Local command interface — send commands to bridge"""
    global bridge_writer
    try:
        data = await asyncio.wait_for(reader.readline(), timeout=30)
        if not data: return
        cmd = json.loads(data.decode().strip())
        
        if bridge_writer is None:
            writer.write(json.dumps({"ok": False, "error": "no bridge"}).encode() + b"\n")
            await writer.drain()
            writer.close()
            return
        
        # Add id for matching response
        import uuid
        req_id = str(uuid.uuid4())[:8]
        cmd["id"] = req_id
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        pending[req_id] = fut
        
        bridge_writer.write((json.dumps(cmd) + "\n").encode())
        await bridge_writer.drain()
        
        try:
            result = await asyncio.wait_for(fut, timeout=30)
            writer.write((json.dumps(result) + "\n").encode())
        except asyncio.TimeoutError:
            writer.write(json.dumps({"ok": False, "error": "timeout"}).encode() + b"\n")
        
        await writer.drain()
    except Exception as e:
        try:
            writer.write(json.dumps({"ok": False, "error": str(e)}).encode() + b"\n")
            await writer.drain()
        except: pass
    finally:
        writer.close()

async def main():
    # Bridge listener
    server1 = await asyncio.start_server(handle_client, "0.0.0.0", 5099)
    print(f"Waiting for bridge on 0.0.0.0:5099", flush=True)
    
    # Command listener (local only)
    server2 = await asyncio.start_server(handle_cmd, "127.0.0.1", 5098)
    print(f"Command interface on 127.0.0.1:5098", flush=True)
    print(f"Send: echo '{{\"action\":\"navigate\",\"url\":\"https://discord.com\"}}' | nc 127.0.0.1 5098", flush=True)
    
    async with server1, server2:
        await asyncio.gather(server1.serve_forever(), server2.serve_forever())

asyncio.run(main())
