import os
import sys
import platform
import logging
import json
from fastapi import FastAPI, HTTPException, Query
from subprocess import run, PIPE
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
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
        # Windows development environment
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        python_bin = sys.executable
    else:
        # Linux production environment - read from .env
        scripts_dir = os.getenv("SCRIPTS_DIR", "/home/ubuntu/easydigz-python/domain-mapping")
        python_bin = os.getenv("PYTHON_BIN", "/home/ubuntu/easydigz-python/venv/bin/python")
    
    return scripts_dir, python_bin

SCRIPTS_DIR, PYTHON_BIN = get_environment_config()
print(f"Platform: {platform.system()}")
print(f"Scripts directory: {SCRIPTS_DIR}")
print(f"Python binary: {PYTHON_BIN}")

# === Script Executor ===
def run_script(script_name: str, args: list = []):
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
@app.get("/run/autocf")
def run_autocf(domain: str = Query(..., description="Custom domain (e.g., portal.example.com)")):
    return run_script("autocf.py", [domain])

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
    # Attempt to return the script's JSON stdout directly
    stdout = (result.get("stdout") or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict) and "type" in payload and "message" in payload:
                return payload
        except Exception as e:
            logger.warning(f"Failed to parse stdout as JSON: {e}")
    # If parsing failed or no stdout, return an error JSON with details
    err_msg = (result.get("stderr") or result.get("stdout") or "Unknown error").strip()
    return {"type": "error", "message": err_msg}

@app.get("/test/nginx_manager")
def test_nginx_manager(domain: str = Query(..., description="Test nginx manager script")):
    """Test endpoint to check nginx_manager script directly"""
    logger.info(f"Testing nginx_manager with domain: {domain}")
    script_path = os.path.join(SCRIPTS_DIR, "nginx_manager.py")
    logger.info(f"Script exists: {os.path.exists(script_path)}")
    return {"script_exists": os.path.exists(script_path), "script_path": script_path, "domain": domain}


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
    return {
            "script": "alb.py",
            "args": "",
            "exit_code": "",
            "stdout": "",
            "stderr": ""
        }
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
