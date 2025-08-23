import os, sys
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

if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)

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
    # Run the script quickly and then start background polling
    res = run_script("autocf.py", [domain])  # returns fast
    background_tasks.add_task(_poll_until_all_three_and_save, domain)
    
    # Send quick response to the user
    res["status"] = "pending"  # Initial status
    return res

async def _poll_until_all_three_and_save(domain: str, max_seconds=900, every_seconds=10):
    """
    Polls checkStatus.py until all three records are visible in stdout.
    Then saves the 'autocf-like' envelope with status 'generated'.
    Exits early if we reach 'applied' first (still acceptable to save).
    """
    started = asyncio.get_event_loop().time()  # using async time for accurate delay tracking
    logger.info(f"Started polling for domain {domain}")

    while asyncio.get_event_loop().time() - started < max_seconds:
        logger.info(f"Polling attempt for {domain} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        # Replace with your custom hostname fetching logic
        r = run_script("checkStatus.py", [domain])  # reuse your existing script call
        stdout = r.get("stdout") or ""
        exit_code = r.get("exit_code", 1)

        # Derive status from what CF currently returns
        derived = derive_status_from_obj(stdout)
        logger.info(f"Derived status for {domain}: {derived}")

        # Save only when all 3 records are found and script succeeded
        if exit_code == 0 and all_three_present(stdout):
            envelope = make_autocf_envelope(domain, r, status="generated")
            _save_response_to_db(domain, envelope)
            logger.info(f"All 3 records found for {domain}, saved to DB.")
            return

        # If CF shows 'active', it's safe to persist too (status: applied)
        if exit_code == 0 and derived == "applied":
            envelope = make_autocf_envelope(domain, r, status="applied")
            _save_response_to_db(domain, envelope)
            logger.info(f"SSL Active for {domain}, saved to DB.")
            return

        # Log that we are still waiting
        logger.info(f"Attempt {int((asyncio.get_event_loop().time() - started) / every_seconds)}: Waiting for SSL validation to complete for {domain}.")
        await asyncio.sleep(every_seconds)  # Non-blocking sleep to allow the event loop to continue

    logger.error(f"Timeout reached after {max_seconds} seconds of polling for {domain}.")


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
    if not domain:
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
        conn = pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            port=DB_CONFIG["port"],
            charset="utf8mb4",
            autocommit=False,
        )
        with conn.cursor() as cur:
            cur.execute(sql, (payload_json, domain))
        conn.commit()

        # Optional: warn if no row was updated (i.e., domain not pre-inserted)
        if cur.rowcount == 0:
            logger.warning(f"WARNING: No row updated for domain '{domain}'. Did you insert the mapping first?")
        else:
            logger.info(f"Validation payload saved for: {domain}")

    except Exception as e:
        if conn:
            try: conn.rollback()
            except: pass
        logger.error("Failed to save validation payload:", e)
    finally:
        if conn:
            conn.close()

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
