from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from subprocess import run, PIPE
import os
import sys
import platform

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# === Configuration ===
# Detect environment - server (Linux) or local (Windows)
IS_LOCAL = platform.system().lower() == "windows"

if IS_LOCAL:
    # Local development paths (Windows)
    SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
    PYTHON_BIN = sys.executable
else:
    # Server paths (Linux)
    SCRIPTS_DIR = "/home/ubuntu/easydigz-python/domain-mapping"
    PYTHON_BIN = "/home/ubuntu/easydigz-python/venv/bin/python"

# === Script Executor ===
def run_script(script_name: str, args: list = []):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    print(f"Looking for script at: {script_path}")
    
    if not os.path.isfile(script_path):
        available_files = os.listdir(SCRIPTS_DIR)
        raise HTTPException(status_code=404, detail=f"Script '{script_name}' not found at {script_path}. Available files: {available_files}")
    
    try:
        print(f"Running script: {script_path}")
        print(f"Using Python: {PYTHON_BIN}")
        print(f"Arguments: {args}")
        
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
    # if IS_LOCAL:
    #     # Use mock script for local development
    #     return run_script("mock_autocf.py", [domain])
    # else:
    #     return run_script("autocf.py", [domain])
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
