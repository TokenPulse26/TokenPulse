#!/usr/bin/env python3
"""TokenPulse local verification script for agents and testers."""

from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request


def fetch_json(url: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", None) or resp.getcode()
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = None
            return {"ok": True, "status": status, "data": data, "raw": body}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"ok": False, "status": None, "error": str(e.reason)}
    except Exception as e:  # noqa: BLE001 - keep script resilient
        return {"ok": False, "status": None, "error": str(e)}


def fetch_status(url: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            return {"ok": status == 200, "status": status}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"ok": False, "status": None, "error": str(e.reason)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": None, "error": str(e)}


def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def exists(path: pathlib.Path) -> bool:
    return path.exists()


def main() -> int:
    home = pathlib.Path.home()
    install_dir = home / ".tokenpulse"
    dashboard_py = install_dir / "web-dashboard.py"
    logs_dir = install_dir / "logs"
    db_path = home / "Library" / "Application Support" / "com.tokenpulse.desktop" / "tokenpulse.db"

    print("TokenPulse verification report")
    print("================================")

    proxy = fetch_json("http://127.0.0.1:4100/health")
    proxy_ok = proxy.get("ok") and proxy.get("status") == 200
    print("1) Proxy health (http://127.0.0.1:4100/health):")
    if proxy_ok:
        data = proxy.get("data") or {}
        status = data.get("status", "unknown")
        version = data.get("version", "unknown")
        tracked = data.get("total_requests_tracked", "unknown")
        print(f"   - HTTP: {proxy['status']} (ok)")
        print(f"   - status: {status}")
        print(f"   - version: {version}")
        print(f"   - total_requests_tracked: {tracked}")
    else:
        print(f"   - NOT REACHABLE ({proxy.get('error', 'unknown error')})")

    dashboard = fetch_status("http://127.0.0.1:4200/")
    dashboard_ok = dashboard.get("ok") and dashboard.get("status") == 200
    print("2) Dashboard (http://127.0.0.1:4200/):")
    if dashboard_ok:
        print("   - HTTP: 200 (ok)")
    else:
        status = dashboard.get("status")
        err = dashboard.get("error", "no response")
        print(f"   - NOT REACHABLE (status={status}, error={err})")

    print("3) Local files:")
    install_exists = exists(install_dir)
    dashboard_exists = exists(dashboard_py)
    logs_exists = exists(logs_dir)
    print(f"   - {install_dir}: {'present' if install_exists else 'missing'}")
    print(f"   - {dashboard_py}: {'present' if dashboard_exists else 'missing'}")
    print(f"   - {logs_dir}: {'present' if logs_exists else 'missing'}")

    print("4) Database:")
    if db_path.exists():
        size = db_path.stat().st_size
        print(f"   - {db_path}: present ({human_size(size)})")
    else:
        print(f"   - {db_path}: missing")

    requests = fetch_json("http://127.0.0.1:4100/api/requests?limit=5")
    visible_requests = 0
    print("5) Recent requests (http://127.0.0.1:4100/api/requests?limit=5):")
    if requests.get("ok") and requests.get("status") == 200:
        data = requests.get("data")
        if isinstance(data, list):
            visible_requests = len(data)
        elif isinstance(data, dict):
            rows = data.get("requests")
            if isinstance(rows, list):
                visible_requests = len(rows)
        print(f"   - API reachable, requests visible: {visible_requests}")
    else:
        print(f"   - NOT REACHABLE ({requests.get('error', 'unknown error')})")

    print("6) Optional local model services (informational only):")
    ollama = fetch_status("http://127.0.0.1:11434")
    lmstudio = fetch_status("http://127.0.0.1:1234")
    print(f"   - Ollama (11434): {'reachable' if ollama.get('status') else 'not detected'}")
    print(f"   - LM Studio (1234): {'reachable' if lmstudio.get('status') else 'not detected'}")

    install_complete = install_exists and dashboard_exists and logs_exists
    proxy_down = not proxy_ok
    dash_down = not dashboard_ok

    summary = "READY"
    if not install_complete:
        summary = "INSTALL INCOMPLETE"
    elif proxy_down:
        summary = "PROXY DOWN"
    elif dash_down:
        summary = "DASHBOARD DOWN"
    elif visible_requests == 0:
        summary = "INSTALLED BUT NO TRAFFIC YET"

    print("\nSUMMARY:")
    print(f"{summary}")

    print("\nNext steps:")
    if summary == "READY":
        print("- TokenPulse is healthy and has seen recent traffic.")
    elif summary == "INSTALLED BUT NO TRAFFIC YET":
        print("- Install looks good. Route one AI tool through http://localhost:4100 and send a test request.")
    elif summary == "PROXY DOWN":
        print("- Start or restart the proxy, then re-run this script.")
    elif summary == "DASHBOARD DOWN":
        print("- Start or restart the dashboard service, then re-run this script.")
    else:
        print("- Re-run install.sh and ensure files under ~/.tokenpulse are created.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
