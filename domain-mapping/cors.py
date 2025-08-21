from pathlib import Path
import subprocess
import sys
import json


def _log(msg: str):
    print(msg, file=sys.stderr)


def _json_success(message: str):
    return {"type": "success", "message": message}


def _json_error(message: str):
    return {"type": "error", "message": message}

def add_domain_to_env(env_path, new_domain):
    env_file = Path(env_path)
    if not env_file.exists():
        return False, f"{env_path} does not exist"

    try:
        lines = env_file.read_text().splitlines()
        updated_lines = []
        cors_updated = False

        for line in lines:
            if line.startswith("CORS_ORIGINS="):
                key, current_val = line.split("=", 1)
                origins = [x.strip() for x in current_val.split(",") if x.strip()]
                new_origin = f"https://{new_domain}"
                if new_origin not in origins:
                    origins.append(new_origin)
                    _log(f"Added {new_origin} to CORS_ORIGINS in {env_path}")
                else:
                    _log(f"{new_origin} already present in CORS_ORIGINS in {env_path}")
                line = f"{key}={','.join(origins)}"
                cors_updated = True
            updated_lines.append(line)

        if not cors_updated:
            # Add new line if CORS setting was not present
            updated_lines.append(f"CORS_ORIGINS=https://{new_domain}")
            _log(f"Added new CORS line for {new_domain} in {env_path}")

        env_file.write_text("\n".join(updated_lines))
        _log(f".env updated at {env_path}")
        return True, f"Updated {env_path}"
    except Exception as e:
        return False, f"Failed updating {env_path}: {e}"


def restart_pm2(proc: str | int = "3"):
    """Restart a specific PM2 app (default: id 3) to pick up the updated .env files."""
    proc_str = str(proc)
    try:
        _log(f"Restarting PM2 process {proc_str} as ubuntu user...")
        result = subprocess.run(["su", "-", "ubuntu", "-c", f"pm2 restart {proc_str} --update-env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.stdout:
            _log(result.stdout.strip())
        if result.returncode != 0:
            if result.stderr:
                _log(result.stderr.strip())
            _log(f"PM2 restart failed with exit code {result.returncode}")
        else:
            _log("PM2 restart completed successfully.")
    except FileNotFoundError:
        _log("PM2 is not installed or not in PATH. Skipping PM2 restart.")
    except Exception as e:
        _log(f"Error restarting PM2: {e}")


# Usage /home/ubuntu/easydigz-server/.env.prod
#domain = input("Enter your custom domain for CORS:").strip()
#add_domain_to_env("/home/ubuntu/easydigz-server/.env.prod", domain)

def manage_cors(domain: str):
    _log(f"=== CORS DOMAIN UPDATE for {domain} ===")
    env_paths = [
        "/home/ubuntu/easydigz-server/.env",
        "/home/ubuntu/easydigz-server/.env.prod",
        "/home/ubuntu/easydigz-server/.env.local",
    ]

    errors = []
    for p in env_paths:
        ok, msg = add_domain_to_env(p, domain)
        if not ok:
            errors.append(msg)

    # Restart only PM2 process 3 so apps pick up updated envs
    try:
        restart_pm2("3")
    except Exception as e:
        _log(f"PM2 restart encountered an error: {e}")

    if errors:
        return _json_error("; ".join(errors))
    return _json_success("Cors file has been updated")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        domain = sys.argv[1].strip()
    else:
        domain = input("Enter your custom domain for CORS:").strip()

    result = manage_cors(domain)
    try:
        print(json.dumps(result))
    except Exception:
        print(result)


#CORS_ORIGINS=https://easydigz.com,https://www.easydigz.com,https://*.easydigz.com,http://*.ideafoundation.co.in,https://*.ideafoundation.co.in,http://*.easydigz.com
