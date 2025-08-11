import os
import sys
import platform
from fastapi import FastAPI, HTTPException, Query
from subprocess import run, PIPE

app = FastAPI()

# === Platform-aware Configuration ===
def get_environment_config():
    """Get platform-specific configuration"""
    if platform.system() == "Windows":
        # Windows development environment
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        python_bin = sys.executable
    else:
        # Linux production environment
        scripts_dir = "/home/ubuntu/easydigz-python/domain-mapping"
        python_bin = "/home/ubuntu/easydigz-python/venv/bin/python"
    
    return scripts_dir, python_bin

SCRIPTS_DIR, PYTHON_BIN = get_environment_config()
print(f"Platform: {platform.system()}")
print(f"Scripts directory: {SCRIPTS_DIR}")
print(f"Python binary: {PYTHON_BIN}")

# === Script Executor ===
def run_script(script_name: str, args: list = []):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=404, detail=f"Script '{script_name}' not found at {script_path}")
    
    try:
        result = run(
            [PYTHON_BIN, script_path] + args,
            stdout=PIPE,
            stderr=PIPE,
            text=True
        )
        return {
            "script": script_name,
            "args": args,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")

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
    return run_script("nginx_manager.py", [domain])
    

@app.get("/run/cors")
def run_cors(domain: str = Query(..., description="Custom domain for CORS")):
    return run_script("cors.py", [domain])

@app.get("/run/alb")
def run_alb(domain: str = Query(..., description="Custom domain to add to ALB")):
    return run_script("alb.py", [domain])

@app.get("/run/dbkp")
def run_dbkp(
    domain: str = Query(..., description="Custom domain (e.g., portal.example.com)"),
    agent_id: str = Query(..., description="Agent ID for the domain")
):
    return run_script("dbkp.py", [domain, agent_id])
