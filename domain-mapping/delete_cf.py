import os
from cloudflare import Cloudflare
import sys
import json
from dotenv import load_dotenv

def delete_custom_hostname(custom_domain):
    """Delete a custom hostname from Cloudflare"""
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')

    if not os.path.exists(env_path):
        print(f"Warning: env file not found at: {env_path}")
        print("Please make sure you have Cloudflare API credentials set.")

    load_dotenv(dotenv_path=env_path)

    # Set your Cloudflare API token and zone ID  
    ezd_zone_id = os.getenv("CF_ZONE_ID")
    token = os.getenv("CF_TOKEN")

    if not ezd_zone_id or not token:
        error_msg = "Error: CF_ZONE_ID or CF_TOKEN environment variables not set."
        print(error_msg)
        result = {
            "success": False,
            "message": error_msg,
            "hostname": custom_domain
        }
        print(json.dumps(result))
        sys.exit(1)

    client = Cloudflare(api_token=token)

    try:
        # List all custom hostnames for the zone
        print(f"Searching for hostname: {custom_domain}")
        hostnames_response = client.custom_hostnames.list(zone_id=ezd_zone_id)
        
        # Extract the actual list of hostnames from the response
        if hasattr(hostnames_response, 'result'):
            hostnames = hostnames_response.result
        else:
            hostnames = hostnames_response
        
        hostname_id = None
        hostname_details = None
        
        # Find the matching hostname
        for hostname in hostnames:
            if hostname.hostname == custom_domain:
                hostname_id = hostname.id
                hostname_details = hostname
                break
        
        if not hostname_id:
            message = f"Custom hostname '{custom_domain}' not found in Cloudflare."
            print(message)
            result = {
                "success": True,
                "message": f"No custom hostname found for '{custom_domain}' - nothing to delete.",
                "hostname": custom_domain,
                "status": "not_found"
            }
            print(json.dumps(result))
            return result
        
        # Display what will be deleted
        print(f"\nPreparing to delete the following from Cloudflare:")
        print(f"- Custom hostname: {custom_domain}")
        print(f"- Hostname ID: {hostname_id}")
        
        # Show SSL details if available
        ssl_status = "unknown"
        if hasattr(hostname_details, "ssl") and hostname_details.ssl:
            ssl_status = hostname_details.ssl.status
            print(f"- SSL certificate (status: {ssl_status})")
        
        # Show origin server if available
        origin_server = None
        if hasattr(hostname_details, "custom_origin_server"):
            origin_server = hostname_details.custom_origin_server
            print(f"- CNAME pointing to: {origin_server}")
        
        # Skip confirmation if --auto-confirm flag is present
        if "--auto-confirm" not in sys.argv:    
            confirmation = input("\nConfirm deletion? (y/n): ").strip().lower()
            if confirmation != 'y':
                print("Deletion cancelled.")
                result = {
                    "success": False,
                    "message": "Deletion cancelled by user",
                    "hostname": custom_domain
                }
                print(json.dumps(result))
                sys.exit(0)
        else:
            print("Auto-confirming deletion...")
            
        # Delete the custom hostname
        response = client.custom_hostnames.delete(
            zone_id=ezd_zone_id,
            custom_hostname_id=hostname_id
        )
        
        print(f"Successfully deleted custom hostname: {custom_domain}")
        print(f"Response: {response}")
        
        result = {
            "success": True,
            "message": f"Successfully deleted custom hostname: {custom_domain}",
            "hostname": custom_domain,
            "id": hostname_id,
            "details": {
                "ssl_status_before_deletion": ssl_status,
                "origin_server_before_deletion": origin_server,
                "txt_records": "removed",
                "all_cloudflare_configurations": "removed"
            }
        }
        print(json.dumps(result))
        return result
        
    except Exception as e:
        error_msg = f"Error deleting custom hostname: {str(e)}"
        print(error_msg)
        if hasattr(e, "response") and e.response is not None:
            try:
                print(e.response.json())
            except:
                print(f"Response error: {e.response}")
        
        result = {
            "success": False,
            "message": error_msg,
            "hostname": custom_domain,
            "error": str(e)
        }
        print(json.dumps(result))
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        custom_domain = sys.argv[1].strip()
    else:
        custom_domain = input("Enter the custom domain to delete (e.g., portal.example.com): ").strip()
        
    delete_custom_hostname(custom_domain)
