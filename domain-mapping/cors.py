from pathlib import Path
import subprocess
import sys

def add_domain_to_env(env_path, new_domain):
    env_file = Path(env_path)
    if not env_file.exists():
        raise FileNotFoundError(f"{env_path} does not exist")

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
                print(f" Added {new_origin} to CORS_ORIGINS")
            else:
                print(f"  {new_origin} already present in CORS_ORIGINS")
            line = f"{key}={','.join(origins)}"
            cors_updated = True
        updated_lines.append(line)

    if not cors_updated:
        # Add new line if CORS setting was not present
        updated_lines.append(f"CORS_ORIGINS=https://{new_domain}")
        print(f"Added new CORS line for {new_domain}")

    env_file.write_text("\n".join(updated_lines))
    print(f".env updated at {env_path}")


def restart_pm2():
    """Restart PM2 apps to pick up the updated .env files."""
    try:
        print("Restarting PM2 apps (pm2 restart all)...")
        result = subprocess.run(["pm2", "restart", "all"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr.strip())
            print(f"PM2 restart failed with exit code {result.returncode}")
        else:
            print("PM2 restart completed successfully.")
    except FileNotFoundError:
        print("PM2 is not installed or not in PATH. Skipping PM2 restart.")
    except Exception as e:
        print(f"Error restarting PM2: {e}")


# Usage /home/ubuntu/easydigz-server/.env.prod
#domain = input("Enter your custom domain for CORS:").strip()
#add_domain_to_env("/home/ubuntu/easydigz-server/.env.prod", domain)

if len(sys.argv) > 1:
    domain = sys.argv[1].strip()
else:
    domain = input("Enter your custom domain for CORS:").strip()

# Now call your function with the domain
add_domain_to_env("/home/ubuntu/easydigz-server/.env", domain)
add_domain_to_env("/home/ubuntu/easydigz-server/.env.prod", domain)
add_domain_to_env("/home/ubuntu/easydigz-server/.env.local", domain)

# Restart PM2 so apps pick up updated envs
restart_pm2()


#CORS_ORIGINS=https://easydigz.com,https://www.easydigz.com,https://*.easydigz.com,http://*.ideafoundation.co.in,https://*.ideafoundation.co.in,http://*.easydigz.com
