#!/usr/bin/env python3
import os
import sys
import json
from cloudflare import Cloudflare
from dotenv import load_dotenv

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
    # List all custom hostnames for the zone
    hostnames_response = client.custom_hostnames.list(zone_id=ZONE_ID)

    # SDK returns a pydantic model with .result
    if hasattr(hostnames_response, "result"):
        hostnames = hostnames_response.result
    else:
        hostnames = hostnames_response

    existing_id = None
    for hostname in hostnames:
        if getattr(hostname, "hostname", None) == custom_domain:
            existing_id = hostname.id
            break

    if not existing_id:
        print(json.dumps({"type": "error", "message": f"Hostname '{custom_domain}' not found"}))
        sys.exit(1)

    # Fetch full hostname details
    hostname_obj = client.custom_hostnames.get(
        custom_hostname_id=existing_id,
        zone_id=ZONE_ID
    )

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
