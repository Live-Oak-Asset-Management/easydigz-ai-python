#!/usr/bin/env python3
import os
import sys
import json
from cloudflare import Cloudflare
from dotenv import load_dotenv
import requests
from types import SimpleNamespace
from helpers_cf import get_custom_hostname_obj


def _log(msg: str):
    print(msg, file=sys.stderr)

# --- Load environment ---
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
if not os.path.exists(env_path):
    raise FileNotFoundError(f"env file not found at: {env_path}")

load_dotenv(dotenv_path=env_path)

ZONE_ID = os.getenv("CF_ZONE_ID")
TOKEN   = os.getenv("CF_TOKEN")

client = Cloudflare(api_token=TOKEN)

# --- Get domain from CLI args ---
if len(sys.argv) > 1:
    custom_domain = sys.argv[1].strip().lower()
else:
    print(json.dumps({"type": "error", "message": "Usage: python checkStatus.py <domain>"}))
    sys.exit(1)

try:
    # Prefer helper that directly finds the object
    hostname_obj = get_custom_hostname_obj(custom_domain)

    # Fallback to REST API if not found via helper/SDK
    if not hostname_obj:
        _log(f"[checkStatus] Helper did not find hostname for {custom_domain}; calling Cloudflare REST API")
        try:
            resp = requests.get(
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/custom_hostnames",
                params={"hostname": custom_domain},
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json() or {}
            _log(f"[checkStatus] REST API success={data.get('success')} result_count={len(data.get('result') or [])}")
            if data.get("success") and (data.get("result") or []):
                # Convert first result dict to attribute-style object recursively
                def to_obj(d):
                    if isinstance(d, dict):
                        return SimpleNamespace(**{k: to_obj(v) for k, v in d.items()})
                    if isinstance(d, list):
                        return [to_obj(x) for x in d]
                    return d

                hostname_obj = to_obj((data.get("result") or [])[0])
            else:
                print(json.dumps({"type": "error", "message": "Custom hostname not found."}))
                sys.exit(1)
        except requests.RequestException as e:
            print(json.dumps({"type": "error", "message": f"API Error: {str(e)}"}))
            sys.exit(1)

    # --- Parse statuses ---
    ssl_status = getattr(hostname_obj.ssl, "status", "unknown")
    verification_status = getattr(hostname_obj, "status", "unknown")

    # Build human message
    parts = []

    # Verification (Cloudflare-level)
    if verification_status == "active":
        parts.append("Verification Completed")
    elif verification_status in ["pending", "pending_deployment", "pending_validation"]:
        parts.append("Verification Pending")
    else:
        parts.append(f"Verification: {verification_status}")

    # SSL
    if ssl_status == "active":
        parts.append("SSL Completed")
    elif ssl_status in ["pending_validation", "initializing", "pending"]:
        parts.append("SSL Pending")
    else:
        parts.append(f"SSL: {ssl_status}")

    # CNAME check — if verification is done, CNAME must have resolved
    if verification_status == "active":
        cname_msg = "CNAME Completed"
    else:
        cname_msg = "CNAME Pending"

    parts.insert(0, cname_msg)

    # --- Final type ---
    if verification_status == "active" and ssl_status == "active":
        resp_type = "success"
    else:
        resp_type = "pending"

    result = {
        "type": resp_type,
        "message": ", ".join(parts)
    }

    print(json.dumps(result))

except Exception as e:
    print(json.dumps({"type": "error", "message": f"Cloudflare error: {str(e)}"}))
    sys.exit(1)
