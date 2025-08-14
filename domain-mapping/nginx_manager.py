import os
import sys
import re
from dotenv import load_dotenv, set_key

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
    """Update nginx configuration with new domain"""
    # Get nginx config path from .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    
    nginx_config_path = os.getenv("NGINX_CONFIG_PATH", "/etc/nginx/conf.d/stage.conf")
    
    # Clean the domain but keep the full domain (including subdomain)
    clean_domain = extract_domain_from_url(new_domain)
    domain_to_add = clean_domain  # Use the full domain, not base domain
    
    print(f"Processing domain: {clean_domain}")
    print(f"Domain to add: {domain_to_add}")
    print(f"Nginx config file: {nginx_config_path}")
    
    try:
        # Read current nginx config
        if os.path.exists(nginx_config_path):
            # Take backup of config file
            backup_path = f"{nginx_config_path}.backup"
            # import shutil
            #shutil.copy2(nginx_config_path, backup_path)
            os.system(f"sudo cp {nginx_config_path} {backup_path}")
            print(f"INFO: Backup created at {backup_path}")
            
            with open(nginx_config_path, 'r') as f:
                config_content = f.read()
            
            # Find the server_name line (look for the main server block, not commented ones)
            server_name_pattern = r'^\s*(server_name\s+[^;]+);'
            matches = re.findall(server_name_pattern, config_content, re.MULTILINE)
            
            if matches:
                # Use the first uncommented server_name line
                current_server_name = matches[0]
                current_server_name_with_semicolon = current_server_name + ';'
                print(f"Current server_name: {current_server_name_with_semicolon}")
                print(f"Total server_name lines found: {len(matches)}")
                
                # Check if the FULL domain is already in the list (more precise word boundary check)
                domain_pattern = r'\b' + re.escape(domain_to_add) + r'\b'
                if re.search(domain_pattern, current_server_name):
                    print(f"INFO: Domain {domain_to_add} already exists in nginx configuration")
                    print(f"Domain found using pattern: {domain_pattern}")
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




                    print(f"SUCCESS: Added {domain_to_add} to nginx configuration")
                    print(f"New server_name: {new_server_name_with_semicolon}")
                    
                    # Reload nginx
                    reload_result = os.system("sudo nginx -t && sudo systemctl reload nginx")
                    if reload_result == 0:
                        print("SUCCESS: Nginx configuration reloaded")
                    else:
                        print("ERROR: Failed to reload nginx configuration")
                        return False
            else:
                print("ERROR: Could not find server_name line in nginx configuration")
                return False
        else:
            print(f"ERROR: Nginx configuration file not found: {nginx_config_path}")
            return False
            
    except Exception as e:
        print(f"ERROR: Failed to update nginx configuration: {str(e)}")
        return False
    
    return True

def update_env_domains(new_domain):
    """Update .env file with new domain in NGINX_DOMAINS (don't override existing)"""
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
            print(f"SUCCESS: Added {domain_to_add} to .env NGINX_DOMAINS")
            print(f"Current NGINX_DOMAINS: {updated_domains}")
        else:
            print(f"INFO: Domain {domain_to_add} already exists in .env NGINX_DOMAINS")
            print(f"Current NGINX_DOMAINS: {current_domains}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to update .env file: {str(e)}")
        return False

def manage_domain_nginx(domain):
    """Main function to manage domain in both .env and nginx"""
    print(f"=== NGINX DOMAIN MANAGEMENT for {domain} ===")
    
    # Update .env file
    env_success = update_env_domains(domain)
    
    # Update nginx configuration (only on Linux)
    nginx_success = True
    if os.name != 'nt':  # Not Windows
        nginx_success = update_nginx_domains(domain)
    else:
        print("INFO: Skipping nginx update on Windows - run on Linux server")
    
    # Summary
    if env_success and nginx_success:
        print("SUCCESS: Domain management completed successfully")
        return True
    else:
        print("WARNING: Some operations failed")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        domain = sys.argv[1].strip()
    else:
        domain = input("Enter the domain to add to nginx (e.g., abc.crackiq.com): ").strip()
    
    manage_domain_nginx(domain)
