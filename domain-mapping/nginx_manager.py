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
    """Extract clean domain from various input formats (keep www if provided)"""
    # Remove protocol if present
    domain = re.sub(r'^https?://', '', domain_input)
    # Remove trailing slash
    domain = domain.rstrip('/')
    return domain  # Keep 'www.' if present

def get_base_domain(domain):
    """Extract base domain from subdomain (e.g., abc.crackiq.com -> crackiq.com)"""
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain

def get_www_variants(domain):
    """Return both bare and www variants of a domain"""
    base = re.sub(r'^www\.', '', domain)
    return [base, f"www.{base}"]

def update_nginx_domains(new_domain):
    """Update nginx configuration with new domain(s)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    
    nginx_config_path = os.getenv("NGINX_CONFIG_PATH", "/etc/nginx/conf.d/stage.conf")
    
    clean_domain = extract_domain_from_url(new_domain)
    domains_to_add = get_www_variants(clean_domain)

    _log(f"Processing domain: {clean_domain}")
    _log(f"Domains to add: {domains_to_add}")
    _log(f"Nginx config file: {nginx_config_path}")
    
    try:
        if os.path.exists(nginx_config_path):
            backup_path = f"{nginx_config_path}.backup"
            os.system(f"sudo cp {nginx_config_path} {backup_path}")
            _log(f"INFO: Backup created at {backup_path}")
            
            with open(nginx_config_path, 'r') as f:
                config_content = f.read()
            
            server_name_pattern = r'^\s*(server_name\s+[^;]+);'
            matches = re.findall(server_name_pattern, config_content, re.MULTILINE)
            
            if matches:
                current_server_name = matches[0]
                current_server_name_with_semicolon = current_server_name + ';'
                _log(f"Current server_name: {current_server_name_with_semicolon}")
                _log(f"Total server_name lines found: {len(matches)}")

                new_server_name_with_semicolon = current_server_name_with_semicolon
                updated = False

                for domain_to_add in domains_to_add:
                    domain_pattern = r'\b' + re.escape(domain_to_add) + r'\b'
                    if not re.search(domain_pattern, current_server_name):
                        new_server_name_with_semicolon = new_server_name_with_semicolon.replace(
                            ';', f' {domain_to_add};'
                        )
                        updated = True
                        _log(f"Adding {domain_to_add} to server_name")

                if updated:
                    updated_config = config_content.replace(
                        current_server_name_with_semicolon,
                        new_server_name_with_semicolon
                    )
                    tmp_path = "/tmp/nginx_tmp.conf"
                    with open(tmp_path, 'w') as f:
                        f.write(updated_config)
                    os.system(f"sudo cp {tmp_path} {nginx_config_path}")
                    os.remove(tmp_path)

                    _log(f"SUCCESS: Updated server_name to {new_server_name_with_semicolon}")

                    reload_result = os.system("sudo nginx -t && sudo systemctl reload nginx")
                    if reload_result == 0:
                        _log("SUCCESS: Nginx configuration reloaded")
                        return _json_success("Nginx file has been updated")
                    else:
                        _log("ERROR: Failed to reload nginx configuration")
                        return _json_error("Failed to reload nginx configuration")
                else:
                    _log("INFO: Domains already exist in nginx configuration")
                    return _json_success("Domains already exist in nginx configuration")
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
    """Update .env file with new domain(s) in NGINX_DOMAINS."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    
    clean_domain = extract_domain_from_url(new_domain)
    domains_to_add = get_www_variants(clean_domain)

    try:
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path)
        
        current_domains = os.getenv("NGINX_DOMAINS", "")
        domain_list = [d.strip() for d in current_domains.split(',') if d.strip()]
        
        updated = False
        for domain_to_add in domains_to_add:
            if domain_to_add not in domain_list:
                domain_list.append(domain_to_add)
                updated = True
                _log(f"Adding {domain_to_add} to .env NGINX_DOMAINS")

        if updated:
            updated_domains = ', '.join(domain_list)
            set_key(env_path, "NGINX_DOMAINS", updated_domains)
            _log(f"SUCCESS: Updated .env NGINX_DOMAINS -> {updated_domains}")
            return _json_success(".env updated with domain(s)")
        else:
            _log(f"INFO: Domains already exist in .env NGINX_DOMAINS")
            return _json_success("Domains already exist in .env NGINX_DOMAINS")
        
    except Exception as e:
        _log(f"ERROR: Failed to update .env file: {str(e)}")
        return _json_error(f"Failed to update .env file: {str(e)}")

def manage_domain_nginx(domain):
    """Main function to manage domain in both .env and nginx."""
    _log(f"=== NGINX DOMAIN MANAGEMENT for {domain} ===")
    
    env_result = update_env_domains(domain)
    
    if os.name != 'nt':  # Only on Linux
        nginx_result = update_nginx_domains(domain)
    else:
        _log("INFO: Skipping nginx update on Windows")
        nginx_result = _json_error("Nginx update skipped on Windows - run on Linux server")
    
    if env_result.get("type") == "error" and nginx_result.get("type") == "success":
        return _json_error(f"{nginx_result.get('message')} | Env error: {env_result.get('message')}")
    return nginx_result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        domain = sys.argv[1].strip()
    else:
        domain = input("Enter the domain to add to nginx (e.g., abc.com): ").strip()
    
    result = manage_domain_nginx(domain)
    try:
        print(json.dumps(result))
    except Exception:
        print(result)
