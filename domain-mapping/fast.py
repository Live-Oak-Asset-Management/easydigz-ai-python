from fastapi import FastAPI, HTTPException, Query
from subprocess import run, PIPE
import os

app = FastAPI()

# === Configuration ===
SCRIPTS_DIR = "/home/ubuntu/easydigz-python/domain-mapping"
PYTHON_BIN = "/home/ubuntu/easydigz-python/venv/bin/python"

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
