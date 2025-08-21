import os
import sys
import re
import json
from dotenv import load_dotenv, set_key

def _log(msg: str):
    print(msg, file=sys.stderr)

def _json_success(message: str):
    return {"type": "success", "message": message}

def _json_error(message: str):
    return {"type": "error", "message": message}

def extract_domain_from_url(domain_input):
    """Extract clean domain from various input formats"""
    # Remove protocol if present
    domain = re.sub(r'^https?://', '', domain_input)
    # Remove trailing slash
    domain = domain.rstrip('/')
    # Remove www. prefix if present
    domain = re.sub(r'^www\.', '', domain)
    return domain

def get_base_domain(domain):
    """Extract base domain from subdomain (e.g., abc.crackiq.com -> crackiq.com)"""
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain

def update_nginx_domains(new_domain):
    """Update nginx configuration with new domain.

    Returns a dict: {"type": "success"|"error", "message": string}
    """
    # Get nginx config path from .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    
    nginx_config_path = os.getenv("NGINX_CONFIG_PATH", "/etc/nginx/conf.d/stage.conf")
    
    # Clean the domain but keep the full domain (including subdomain)
    clean_domain = extract_domain_from_url(new_domain)
    domain_to_add = clean_domain  # Use the full domain, not base domain
    
    _log(f"Processing domain: {clean_domain}")
    _log(f"Domain to add: {domain_to_add}")
    _log(f"Nginx config file: {nginx_config_path}")
    
    try:
        # Read current nginx config
        if os.path.exists(nginx_config_path):
            # Take backup of config file
            backup_path = f"{nginx_config_path}.backup"
            # import shutil
            #shutil.copy2(nginx_config_path, backup_path)
            os.system(f"sudo cp {nginx_config_path} {backup_path}")
            _log(f"INFO: Backup created at {backup_path}")
            
            with open(nginx_config_path, 'r') as f:
                config_content = f.read()
            
            # Find the server_name line (look for the main server block, not commented ones)
            server_name_pattern = r'^\s*(server_name\s+[^;]+);'
            matches = re.findall(server_name_pattern, config_content, re.MULTILINE)
            
            if matches:
                # Use the first uncommented server_name line
                current_server_name = matches[0]
                current_server_name_with_semicolon = current_server_name + ';'
                _log(f"Current server_name: {current_server_name_with_semicolon}")
                _log(f"Total server_name lines found: {len(matches)}")
                
                # Check if the FULL domain is already in the list (more precise word boundary check)
                domain_pattern = r'\b' + re.escape(domain_to_add) + r'\b'
                if re.search(domain_pattern, current_server_name):
                    _log(f"INFO: Domain {domain_to_add} already exists in nginx configuration")
                    _log(f"Domain found using pattern: {domain_pattern}")
                    return _json_success("Domain already exists in nginx configuration")
                else:
                    # Add the FULL domain to server_name (before the semicolon)
                    new_server_name_with_semicolon = current_server_name + f' {domain_to_add};'
                    updated_config = config_content.replace(current_server_name_with_semicolon, new_server_name_with_semicolon)
                    
                    # Write back to file
                    #with open(nginx_config_path, 'w') as f:
                    #    f.write(updated_config)
                    tmp_path = "/tmp/nginx_tmp.conf"
                    with open(tmp_path, 'w') as f:
                        f.write(updated_config)
                    os.system(f"sudo cp {tmp_path} {nginx_config_path}")
                    os.remove(tmp_path)




                    _log(f"SUCCESS: Added {domain_to_add} to nginx configuration")
                    _log(f"New server_name: {new_server_name_with_semicolon}")
                    
                    # Reload nginx
                    reload_result = os.system("sudo nginx -t && sudo systemctl reload nginx")
                    if reload_result == 0:
                        _log("SUCCESS: Nginx configuration reloaded")
                        return _json_success("Nginx file has been updated")
                    else:
                        _log("ERROR: Failed to reload nginx configuration")
                        return _json_error("Failed to reload nginx configuration")
            else:
                _log("ERROR: Could not find server_name line in nginx configuration")
                return _json_error("Could not find server_name line in nginx configuration")
        else:
            _log(f"ERROR: Nginx configuration file not found: {nginx_config_path}")
            return _json_error(f"Nginx configuration file not found: {nginx_config_path}")
            
    except Exception as e:
        _log(f"ERROR: Failed to update nginx configuration: {str(e)}")
        return _json_error(f"Failed to update nginx configuration: {str(e)}")
    
    return _json_success("Nginx file has been updated")

def update_env_domains(new_domain):
    """Update .env file with new domain in NGINX_DOMAINS (don't override existing).

    Returns a dict: {"type": "success"|"error", "message": string}
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    
    # Clean the domain and use the full domain (including subdomain)
    clean_domain = extract_domain_from_url(new_domain)
    domain_to_add = clean_domain  # Use full domain, not base domain
    
    try:
        # Load current env
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path)
        
        # Get current NGINX_DOMAINS or create new
        current_domains = os.getenv("NGINX_DOMAINS", "")
        domain_list = [d.strip() for d in current_domains.split(',') if d.strip()]
        
        # Add FULL domain if not already present (don't override existing)
        if domain_to_add not in domain_list:
            domain_list.append(domain_to_add)
            updated_domains = ', '.join(domain_list)
            
            # Update .env file
            set_key(env_path, "NGINX_DOMAINS", updated_domains)
            _log(f"SUCCESS: Added {domain_to_add} to .env NGINX_DOMAINS")
            _log(f"Current NGINX_DOMAINS: {updated_domains}")
            return _json_success(".env updated with domain")
        else:
            _log(f"INFO: Domain {domain_to_add} already exists in .env NGINX_DOMAINS")
            _log(f"Current NGINX_DOMAINS: {current_domains}")
            return _json_success("Domain already exists in .env NGINX_DOMAINS")
        
    except Exception as e:
        _log(f"ERROR: Failed to update .env file: {str(e)}")
        return _json_error(f"Failed to update .env file: {str(e)}")

def manage_domain_nginx(domain):
    """Main function to manage domain in both .env and nginx.

    Returns a dict (JSON-ready), primarily reflecting the nginx update confirmation.
    """
    _log(f"=== NGINX DOMAIN MANAGEMENT for {domain} ===")
    
    # Update .env file
    env_result = update_env_domains(domain)
    
    # Update nginx configuration (only on Linux)
    if os.name != 'nt':  # Not Windows
        nginx_result = update_nginx_domains(domain)
    else:
        _log("INFO: Skipping nginx update on Windows - run on Linux server")
        nginx_result = _json_error("Nginx update skipped on Windows - run on Linux server")
    
    # If env failed but nginx succeeded, append env error to message
    if env_result.get("type") == "error" and nginx_result.get("type") == "success":
        return _json_error(f"{nginx_result.get('message')} | Env error: {env_result.get('message')}")
    return nginx_result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        domain = sys.argv[1].strip()
    else:
        domain = input("Enter the domain to add to nginx (e.g., abc.crackiq.com): ").strip()
    
    # Print a single JSON confirmation or error message
    result = manage_domain_nginx(domain)
    try:
        print(json.dumps(result))
    except Exception:
        print(result)
