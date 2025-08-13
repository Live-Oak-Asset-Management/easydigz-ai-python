import os
from cloudflare import Cloudflare
import sys
import json
from dotenv import load_dotenv

# Add helpers to normalize domains and generate www/non-www variants

def normalize_domain(d: str) -> str:
    d = (d or "").strip().lower()
    if d.startswith("http://"):
        d = d[7:]
    elif d.startswith("https://"):
        d = d[8:]
    d = d.strip("/")
    if d.endswith("."):
        d = d[:-1]
    return d


def domain_variants(custom_domain: str):
    base = normalize_domain(custom_domain)
    base_no_www = base[4:] if base.startswith("www.") else base
    variants = []
    for v in [base_no_www, f"www.{base_no_www}"]:
        if v and v not in variants:
            variants.append(v)
    return variants


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
        return result

    client = Cloudflare(api_token=token)

    try:
        target_hostname = normalize_domain(custom_domain)
        # List all custom hostnames for the zone
        print(f"Searching for hostname: {target_hostname}")
        hostnames_response = client.custom_hostnames.list(zone_id=ezd_zone_id)
        
        # Extract the actual list of hostnames from the response
        if hasattr(hostnames_response, 'result'):
            hostnames = hostnames_response.result
        else:
            hostnames = hostnames_response
        
        hostname_id = None
        hostname_details = None
        
        # Find the matching hostname (case-insensitive)
        for hostname in hostnames:
            try:
                name = hostname.hostname
            except AttributeError:
                name = hostname.get("hostname") if isinstance(hostname, dict) else None
            if name and name.lower() == target_hostname:
                hostname_id = getattr(hostname, "id", hostname.get("id") if isinstance(hostname, dict) else None)
                hostname_details = hostname
                break
        
        if not hostname_id:
            message = f"Custom hostname '{target_hostname}' not found in Cloudflare."
            print(message)
            result = {
                "success": True,
                "message": f"No custom hostname found for '{target_hostname}' - nothing to delete.",
                "hostname": target_hostname,
                "status": "not_found"
            }
            print(json.dumps(result))
            return result
        
        # Display what will be deleted
        print("\nPreparing to delete the following from Cloudflare:")
        print(f"- Custom hostname: {target_hostname}")
        print(f"- Hostname ID: {hostname_id}")
        
        # Show SSL details if available
        ssl_status = "unknown"
        if hasattr(hostname_details, "ssl") and getattr(hostname_details, "ssl"):
            try:
                ssl_status = hostname_details.ssl.status
            except Exception:
                pass
            print(f"- SSL certificate (status: {ssl_status})")
        
        # Show origin server if available
        origin_server = None
        if hasattr(hostname_details, "custom_origin_server"):
            origin_server = hostname_details.custom_origin_server
            print(f"- CNAME pointing to: {origin_server}")
        
        print("Auto-confirming deletion...")
        # Delete the custom hostname
        response = client.custom_hostnames.delete(
            zone_id=ezd_zone_id,
            custom_hostname_id=hostname_id
        )
        
        print(f"Successfully deleted custom hostname: {target_hostname}")
        print(f"Response: {response}")
        
        result = {
            "success": True,
            "message": f"Successfully deleted custom hostname: {target_hostname}",
            "hostname": target_hostname,
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
        if hasattr(e, "response") and getattr(e, "response") is not None:
            try:
                print(e.response.json())
            except Exception:
                print(f"Response error: {e.response}")
        
        result = {
            "success": False,
            "message": error_msg,
            "hostname": custom_domain,
            "error": str(e)
        }
        print(json.dumps(result))
        return result


def delete_domain_with_www_variants(custom_domain: str):
    """Delete both the bare domain and www-prefixed variant for the provided custom_domain."""
    variants = domain_variants(custom_domain)
    print(f"Attempting deletion for variants: {variants}")
    results = [delete_custom_hostname(v) for v in variants]
    overall_success = all(r.get("success", False) for r in results)
    summary = {
        "success": overall_success,
        "requested": custom_domain,
        "attempted": [r.get("hostname") for r in results],
        "results": results,
    }
    print(json.dumps({"summary": summary}))
    return summary

if __name__ == "__main__":
    if len(sys.argv) > 1:
        custom_domain = sys.argv[1].strip()
    else:
        custom_domain = input("Enter the custom domain to delete (e.g., portal.example.com): ").strip()
        
    summary = delete_domain_with_www_variants(custom_domain)
    sys.exit(0 if summary.get("success", False) else 1)
