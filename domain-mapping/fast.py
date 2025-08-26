import os, sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import platform
import logging
import json
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from subprocess import run, PIPE
from dotenv import load_dotenv
from datetime import datetime
import pymysql
import asyncio
import time

# Set up logging (log to stdout for PM2 to capture)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout  # Ensures logs go to stdout (for PM2 to capture)
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Load environment variables
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

if not os.path.exists(env_path):
    raise FileNotFoundError(f"env file not found at: {env_path}")

load_dotenv(dotenv_path=env_path)

ZONE_ID = os.getenv("CF_ZONE_ID")
TOKEN = os.getenv("CF_TOKEN")

# === Platform-aware Configuration ===
def get_environment_config():
    """Get platform-specific configuration"""
    if platform.system() == "Windows":
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        python_bin = sys.executable
    else:
        scripts_dir = os.getenv("SCRIPTS_DIR", "/home/ubuntu/easydigz-python/domain-mapping")
        python_bin = os.getenv("PYTHON_BIN", "/home/ubuntu/easydigz-python/venv/bin/python")
    
    return scripts_dir, python_bin

SCRIPTS_DIR, PYTHON_BIN = get_environment_config()
print(f"Platform: {platform.system()}")
print(f"Scripts directory: {SCRIPTS_DIR}")
print(f"Python binary: {PYTHON_BIN}")

# === Script Executor ===
def run_script(script_name: str, args=None):
    if args is None:
        args = []
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    logger.info(f"Executing script: {script_name} with args: {args}")
    logger.info(f"Script path: {script_path}")
    
    if not os.path.isfile(script_path):
        error_msg = f"Script '{script_name}' not found at {script_path}"
        logger.error(error_msg)
        raise HTTPException(status_code=404, detail=error_msg)
    
    try:
        logger.info(f"Running command: {[PYTHON_BIN, script_path] + args}")
        result = run(
            [PYTHON_BIN, script_path] + args,
            stdout=PIPE,
            stderr=PIPE,
            text=True
        )
        
        logger.info(f"Script exit code: {result.returncode}")
        logger.info(f"Script stdout: {result.stdout}")
        logger.info(f"Script stderr: {result.stderr}")
        
        return {
            "script": script_name,
            "args": args,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }
    except Exception as e:
        error_msg = f"Execution error: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

# === API Endpoints ===
@app.get("/run/delete_cf")
def run_delete_cf(domain: str = Query(..., description="Custom domain to delete from Cloudflare")):
    return run_script("delete_cf.py", [domain])

@app.get("/run/validate_dns")
def run_validate_dns(domain: str = Query(..., description="Custom domain to validate DNS records")):
    return run_script("validate_dns.py", [domain])

@app.get("/run/nginx_manager")
def run_nginx_manager(domain: str = Query(..., description="Custom domain to add to nginx configuration")):
    logger.info(f"nginx_manager endpoint called with domain: {domain}")
    result = run_script("nginx_manager.py", [domain])
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict) and "type" in payload and "message" in payload:
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"type": "error", "message": err_msg}

@app.get("/run/cors")
def run_cors(domain: str = Query(..., description="Custom domain for CORS")):
    result = run_script("cors.py", [domain])
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict) and "type" in payload and "message" in payload:
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse CORS stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"type": "error", "message": err_msg}

@app.get("/run/alb")
def run_alb(domain: str = Query(..., description="Custom domain to add to ALB")):
    return run_script("alb.py", [domain])

@app.get("/run/dbkp")
def run_dbkp(
    domain: str = Query(..., description="Custom domain (e.g., portal.example.com)"),
    agent_id: str = Query(..., description="Agent ID for the domain")
):
    return run_script("dbkp.py", [domain, agent_id])

@app.get("/run/checkStatus")
def run_checkStatus(domain: str = Query(..., description="Custom domain")):
    return run_script("checkStatus.py", [domain])

# === Auth0 Management Endpoints ===
@app.get("/run/auth0_add")
def run_auth0_add(
    domain: str = Query(..., description="Custom domain to add to Auth0"),
    client_id: str = Query(None, description="Optional Auth0 client ID to update")
):
    args = ["add", domain]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_add stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth0_remove")
def run_auth0_remove(
    domain: str = Query(..., description="Custom domain to remove from Auth0"),
    client_id: str = Query(None, description="Optional Auth0 client ID to update")
):
    args = ["remove", domain]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_remove stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth0_list")
def run_auth0_list(client_id: str = Query(None, description="Optional Auth0 client ID to inspect")):
    args = ["list"]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_list stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth0_canonicalize")
def run_auth0_canonicalize(client_id: str = Query(None, description="Optional Auth0 client ID to canonicalize")):
    args = ["canonicalize"]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_canonicalize stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth0_populate")
def run_auth0_populate(client_id: str = Query(None, description="Optional Auth0 client ID to populate logout/origins from callbacks")):
    args = ["populate"]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_populate stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth0_set_origins")
def run_auth0_set_origins(
    origins: str = Query(..., description="Comma-separated list of web origins to set"),
    client_id: str = Query(None, description="Optional Auth0 client ID")
):
    args = ["set-origins", origins]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_set_origins stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth0_add_domain")
def run_auth0_add_domain(
    domain: str = Query(..., description="Full domain URL to add to all Auth0 sections (e.g., https://crackiq.com)"),
    client_id: str = Query(None, description="Optional Auth0 client ID")
):
    args = ["add-all", domain]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_add_domain stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth0_remove_domain")
def run_auth0_remove_domain(
    domain: str = Query(..., description="Full domain URL to remove from all Auth0 sections (e.g., https://crackiq.com)"),
    client_id: str = Query(None, description="Optional Auth0 client ID")
):
    args = ["remove-all", domain]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth0_remove_domain stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}


@app.get("/run/auth_update")
def run_auth_update(
    domain: str = Query(..., description="Full domain URL to add to all Auth0 sections (e.g., https://crackiq.com)"),
    client_id: str = Query(None, description="Optional Auth0 client ID")
):
    """Admin route to add domain to all Auth0 sections (callbacks, logout URLs, web origins)"""
    args = ["add-all", domain]
    if client_id:
        args.append(client_id)
    result = run_script("auth0_manager.py", args)
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse auth_update stdout as JSON: {e}")
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"success": False, "message": err_msg}

# === Restart Endpoint ===
@app.post("/restart")
def restart_service():
    """Restart the FastAPI service via PM2"""
    try:
        result = run(
            ["pm2", "restart", "easydigz-api-server"],
            stdout=PIPE,
            stderr=PIPE,
            text=True
        )
        return {
            "message": "Service restarted",
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restart failed: {str(e)}")


from helpers_cf import (
    get_custom_hostname_obj,
    all_three_present,
    build_dns_block,
    derive_status_from_obj,
    make_autocf_envelope,
)

@app.get("/run/autocf")
def run_autocf(
    domain: str = Query(..., description="Custom domain (e.g., portal.example.com)"),
    background_tasks: BackgroundTasks = None
):
    logger.info(f"/run/autocf called for domain={domain}")
    # Run the script quickly and then start background polling
    res = run_script("autocf.py", [domain])  # returns fast
    logger.info(f"autocf.py completed with exit_code={res.get('exit_code')} for domain={domain}")
    if background_tasks is None:
        logger.warning("BackgroundTasks is None; polling will not be scheduled.")
    else:
        logger.info("Scheduling background task: _poll_until_all_three_and_save")
        background_tasks.add_task(_poll_until_all_three_and_save, domain)
        logger.info("Background task scheduled")
    
    # Send quick response to the user
    res["status"] = "pending"  # Initial status
    return res


import requests

async def _poll_until_all_three_and_save(domain: str, max_seconds=900, every_seconds=10):
    """
    Polls checkStatus.py until all three records are visible in stdout.
    Then saves the 'autocf-like' envelope with status 'generated'.
    Exits early if we reach 'applied' first (still acceptable to save).
    """
    started = asyncio.get_event_loop().time()  # using async time for accurate delay tracking
    logger.info(f"[poll] Started for domain={domain} max_seconds={max_seconds} every_seconds={every_seconds}")

    # Check if the domain is apex, and if so, add 'www.' prefix
    if domain.count('.') == 1:  # It's an apex domain
        domain = "www." + domain
        logger.info(f"[poll] Apex domain detected; using {domain}")

    while asyncio.get_event_loop().time() - started < max_seconds:
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        attempt_num = int((asyncio.get_event_loop().time() - started) / every_seconds) + 1
        logger.info(f"[poll] Attempt {attempt_num} at {now_str} for domain={domain}")

        # Fetch current state from Cloudflare directly (same path as test_polling)
        try:
            obj = get_custom_hostname_obj(domain)
        except Exception as e:
            logger.error(f"[poll] Error fetching custom hostname for {domain}: {e}")
            obj = None

        if not obj:
            logger.info(f"[poll] Custom hostname not found for {domain}; calling Cloudflare API")
            # Make an API call to fetch the custom hostname again
            try:
                response = requests.get(
                    f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/custom_hostnames?hostname={domain}",
                    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
                )
                response.raise_for_status()  # Will raise an error if the status code is not 2xx
                cloudflare_data = response.json()
                logger.info(f"[poll] Cloudflare API response: {cloudflare_data}")

                if cloudflare_data["success"] and cloudflare_data["result"]:
                    obj = cloudflare_data["result"][0]  # Use the first result
                    logger.info(f"[poll] Custom hostname found via API: {obj['hostname']}")
                else:
                    logger.error(f"[poll] Custom hostname not found in Cloudflare API response.")
                    return {"status": "error", "message": "Custom hostname not found in Cloudflare API response."}
            except requests.exceptions.RequestException as e:
                logger.error(f"[poll] Error fetching custom hostname from Cloudflare API: {str(e)}")
                return {"status": "error", "message": f"API Error: {str(e)}"}

        # Derive status from CF object
        derived = derive_status_from_obj(obj)
        present = all_three_present(obj)
        logger.info(f"[poll] Derived status={derived} all_three_present={present} for domain={domain}")

        # Save only when all 3 records are found
        if present:
            logger.info(f"[poll] All 3 records present for {domain}; creating envelope and saving to DB")
            envelope = make_autocf_envelope(domain, obj, status="generated")
            try:
                envelope_size = len(json.dumps(envelope, ensure_ascii=False))
            except Exception:
                envelope_size = -1
            logger.info(f"[poll] Envelope prepared (bytes~{envelope_size}); calling _save_response_to_db for {domain}")
            _save_response_to_db(domain, envelope)
            logger.info(f"[poll] Save complete for {domain}; exiting (status=generated)")
            return

        # If CF shows 'active', persist too (status: applied)
        if derived == "applied":
            logger.info(f"[poll] SSL Active for {domain}; creating envelope and saving to DB")
            envelope = make_autocf_envelope(domain, obj, status="applied")
            try:
                envelope_size = len(json.dumps(envelope, ensure_ascii=False))
            except Exception:
                envelope_size = -1
            logger.info(f"[poll] Envelope prepared (bytes~{envelope_size}); calling _save_response_to_db for {domain}")
            _save_response_to_db(domain, envelope)
            logger.info(f"[poll] Save complete for {domain}; exiting (status=applied)")
            return

        # Log that we are still waiting
        logger.info(f"[poll] Attempt {attempt_num}: Waiting for SSL validation to complete for {domain} (status={derived})")
        await asyncio.sleep(every_seconds)  # Non-blocking sleep to allow the event loop to continue

    logger.error(f"[poll] Timeout reached after {max_seconds} seconds for {domain}")


# Basic PG config (matches the style of your sample)
# === DB CONFIGURATION ===
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': int(os.getenv('DB_PORT', 3306))  # default to 3306 if missing
}

def _save_response_to_db(domain: str, envelope: dict):
    """
    MySQL version (pymysql):
    Updates domain_agent_mapping.validation_success_data for the given domain.
    Saves the exact envelope (args/script/stderr/stdout/exit_code), omitting 'status'.
    """
    logger.info(f"[db] _save_response_to_db called for domain={domain}")
    if not domain:
        logger.error("[db] domain is required but missing")
        raise ValueError("domain is required")

    # Mirror your stored shape exactly (drop 'status')
    payload = dict(envelope or {})
    payload.pop("status", None)
    payload_json = json.dumps(payload, ensure_ascii=False)

    sql = """
        UPDATE domain_agent_mapping
           SET validation_success_data = %s,
               updated_at = NOW()
         WHERE domain = %s
    """

    conn = None
    try:
        logger.info("[db] Opening DB connection")
        conn = pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            port=DB_CONFIG["port"],
            charset="utf8mb4",
            autocommit=False,
        )
        logger.info("[db] Connection established; executing UPDATE")
        with conn.cursor() as cur:
            cur.execute(sql, (payload_json, domain))
            rowcount = cur.rowcount
            logger.info(f"[db] UPDATE executed; rowcount={rowcount}")
        conn.commit()
        logger.info("[db] Commit successful")

        # Optional: warn if no row was updated (i.e., domain not pre-inserted)
        if cur.rowcount == 0:
            logger.warning(f"[db] WARNING: No row updated for domain '{domain}'. Did you insert the mapping first?")
        else:
            logger.info(f"[db] Validation payload saved for: {domain}")

    except Exception as e:
        if conn:
            try: conn.rollback()
            except: pass
        logger.error(f"[db] Failed to save validation payload for domain={domain}: {e}")
    finally:
        if conn:
            conn.close()
            logger.info("[db] Connection closed")

@app.get("/test_polling")
async def test_polling(domain: str):
    """
    This is a test function to manually trigger the background polling
    and see if all 3 records are available.
    """
    logger.info(f"Received request for test_polling with domain: {domain}")

    try:
        # Fetch custom hostname object from Cloudflare
        obj = get_custom_hostname_obj(domain)
        
        if not obj:
            logger.error(f"Custom hostname not found for {domain}")
            return {"status": "error", "message": "Domain not found in Cloudflare"}

        logger.info(f"Found custom hostname: {obj.hostname}")
        
        # Check if all 3 records are present
        if all_three_present(obj):
            # Build and return the DNS block (for demonstration)
            dns_block = build_dns_block(obj)
            logger.info(f"All records found for {domain}. DNS Block: {dns_block}")
            return {"status": "success", "message": "All records found", "dns_block": dns_block}

        # If not all records are present, log and inform the user
        logger.warning(f"Not all records present for {domain}. Waiting for records.")
        return {"status": "pending", "message": "DNS records still pending."}

    except Exception as e:
        logger.error(f"Error in polling for domain {domain}: {str(e)}")
        return {"status": "error", "message": f"Error: {str(e)}"}
