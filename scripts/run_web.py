#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ads_autopilot.override_web_server import build_server

server=build_server(ROOT)
host,port=server.server_address[:2]
print(f"Owner Web listening on http://{host}:{port}")
try: server.serve_forever(poll_interval=0.5)
except KeyboardInterrupt: pass
finally: server.server_close()
