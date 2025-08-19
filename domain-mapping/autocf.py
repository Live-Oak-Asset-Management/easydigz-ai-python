import os
from cloudflare import Cloudflare
import time
import sys
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

if not os.path.exists(env_path):
    raise FileNotFoundError(f"env file not found at: {env_path}")

load_dotenv(dotenv_path=env_path)

# Set your Cloudflare API token and zone ID  
ezd_zone_id = os.getenv("CF_ZONE_ID")
token = os.getenv("CF_TOKEN")

# Get SSL proxy URL from environment variable
# For Production: ssl-easy.easydigz.com
# For Staging: ssl-proxy.easydigz.com
ssl_proxy_url = os.getenv("SSL_PROXY_URL", "ssl-proxy.easydigz.com")  # Default to staging

client = Cloudflare(api_token=token)

def is_apex_domain(domain: str):
    return domain.count('.') == 1

# Step 1: Get custom domain from CLI or input
if len(sys.argv) > 1:
    custom_domain = sys.argv[1].strip().lower()
else:
    custom_domain = input("Enter your custom domain (e.g., portal.domain.com): ").strip().lower()

original_domain = custom_domain

# If user gave an apex domain (single dot), force www
if is_apex_domain(custom_domain):
    print(f"\n Apex domain detected: {custom_domain}")
    custom_domain = "www." + custom_domain
    print(f" Automatically switching to use: {custom_domain}")


# First, check if the hostname already exists and delete it if it does
try:
    # List all custom hostnames for the zone
    hostnames_response = client.custom_hostnames.list(zone_id=ezd_zone_id)
    
    # Extract the actual list of hostnames from the response
    if hasattr(hostnames_response, 'result'):
        hostnames = hostnames_response.result
    else:
        hostnames = hostnames_response

    existing_id = None
    for hostname in hostnames:
        if hostname.hostname == custom_domain:
            existing_id = hostname.id
            break

    if existing_id:
        print(f"\nFound existing hostname for {custom_domain}, deleting first...")
        client.custom_hostnames.delete(
            zone_id=ezd_zone_id,
            custom_hostname_id=existing_id
        )
        print(f"Existing hostname deleted. Waiting a moment before creating new one...")
        time.sleep(5)  # Wait a bit for deletion to propagate
        
        # Verify deletion by checking if it's gone
        print("Verifying deletion...")
        verification_response = client.custom_hostnames.list(zone_id=ezd_zone_id)
        verification_hostnames = verification_response.result if hasattr(verification_response, 'result') else verification_response
        still_exists = any(h.hostname == custom_domain for h in verification_hostnames)
        
        if still_exists:
            print("Warning: Hostname still exists after deletion attempt. Waiting longer...")
            time.sleep(10)
        else:
            print("Hostname successfully deleted.")
            
except Exception as e:
    print(f"Error checking for existing hostname: {str(e)}")
    # Continue with creation even if check fails

# Step 2: Create custom hostname with SSL (type: txt)
try:
    response = client.custom_hostnames.create(
        zone_id=ezd_zone_id,
        hostname = custom_domain,
            ssl = {
                "type": "dv",     # For SaaS onboarding / external domains
                "method": "txt"
            },
        
        extra_body={"custom_origin_server": ssl_proxy_url}
    )

    print(f"\n Creating Custom hostname : {response.hostname}")
    print(f" SSL status: {response.ssl.status}")

except Exception as e:
    print("! Failed to create custom hostname !")
    if hasattr(e, "response") and e.response is not None:
        error_response = e.response.json()
        print(error_response)
        
        # Check if it's a duplicate hostname error
        if (error_response.get('errors') and 
            any('Duplicate custom hostname found' in err.get('message', '') for err in error_response.get('errors', []))):
            print("Error: Duplicate hostname found. Please try deleting it first using /run/delete_cf endpoint.")
    else:
        print(str(e))
    exit(1)

# Step 3: Fetch updated hostname to get TXT records with retries
print("\nWaiting for SSL validation records to be generated...")
time.sleep(5)  # Initial wait

hostname_id = response.id
hostname_obj = None

# Retry fetching hostname details multiple times to get complete SSL records
MAX_FETCH_RETRIES = 5
FETCH_WAIT_SECONDS = 5

for fetch_attempt in range(MAX_FETCH_RETRIES):
    try:
        hostname_obj = client.custom_hostnames.get(zone_id=ezd_zone_id, custom_hostname_id=hostname_id)
        
        # Check if we have complete SSL validation records
        ssl = getattr(hostname_obj, "ssl", None)
        has_ssl_records = False
        
        if ssl:
            # Check for validation_records
            records = getattr(ssl, "validation_records", [])
            if records and len(records) > 0:
                has_ssl_records = True
            
            # Check for direct txt_name/txt_value
            if hasattr(ssl, "txt_name") and hasattr(ssl, "txt_value"):
                has_ssl_records = True
        
        if has_ssl_records:
            print(f"SSL validation records found on attempt {fetch_attempt + 1}")
            break
        else:
            print(f"Attempt {fetch_attempt + 1}: SSL validation records not yet available, waiting...")
            if fetch_attempt < MAX_FETCH_RETRIES - 1:  # Don't wait on the last attempt
                time.sleep(FETCH_WAIT_SECONDS)
                
    except Exception as e:
        print(f"Error fetching hostname details on attempt {fetch_attempt + 1}: {str(e)}")
        if fetch_attempt < MAX_FETCH_RETRIES - 1:
            time.sleep(FETCH_WAIT_SECONDS)

# Step 4: Print all TXT validation records
def print_dns_records(hostname_obj):
    print("\n=== DNS RECORDS TO ADD ===")
    print("\nPlease add the following records to your domain's DNS:")

    printed_ssl_records = False
    
    # General CNAME Mapping (always show this)
    print(f"\n1. CNAME record:")
    print(f"   Name:  {hostname_obj.hostname}")
    print(f"   Value: {ssl_proxy_url}")

    # 1. ownership_verification
    ov = getattr(hostname_obj, "ownership_verification", None)
    if ov and getattr(ov, "type", None) == "txt":
        print(f"\n2. Ownership Verification TXT:")
        print(f"   Name:  {ov.name}")
        print(f"   Value: {ov.value}")

    # 2. SSL validation records
    ssl = getattr(hostname_obj, "ssl", None)
    if ssl:
        print(f"\n3. SSL Validation Records:")
        
        # 2.a ssl.validation_records[] (array of records)
        records = getattr(ssl, "validation_records", [])
        if records:
            for i, record in enumerate(records):
                status = getattr(record, "status", "unknown")
                txt_name = getattr(record, "txt_name", None)
                txt_value = getattr(record, "txt_value", None)
                
                if txt_name and txt_value:
                    print(f"   SSL TXT Record {i+1} (status: {status}):")
                    print(f"   Name:  {txt_name}")
                    print(f"   Value: {txt_value}")
                    printed_ssl_records = True
                    
        # 2.b. ssl.txt_name / txt_value (direct properties)
        if hasattr(ssl, "txt_name") and hasattr(ssl, "txt_value"):
            print(f"   SSL TXT Record (direct):")
            print(f"   Name:  {ssl.txt_name}")
            print(f"   Value: {ssl.txt_value}")
            printed_ssl_records = True
            
        # Show SSL status
        ssl_status = getattr(ssl, "status", "unknown")
        print(f"\n   SSL Status: {ssl_status}")
        
    if not printed_ssl_records:
        print(f"   WARNING: SSL validation records not yet available.")
        print(f"   Please wait a few moments and check again, or")
    
    print("\n" + "="*50)



print_dns_records(hostname_obj)

# Step 5: Poll until SSL status becomes "active" or times out
if hostname_obj:
    MAX_RETRIES = 3
    WAIT_SECONDS = 5

    for attempt in range(MAX_RETRIES):
        time.sleep(WAIT_SECONDS)
        try:
            updated = client.custom_hostnames.get(zone_id=ezd_zone_id, custom_hostname_id=hostname_id)
            ssl_status = updated.ssl.status if updated.ssl else "unknown"
            print(f"Attempt {attempt+1}: SSL status = {ssl_status}")

            if ssl_status == "active":
                print("SUCCESS: SSL is active!")
                break
            elif ssl_status in ["pending_validation", "initializing", "pending_deployment"]:
                continue
            else:
                print(f"WARNING: Unexpected status: {ssl_status}")
                break
        except Exception as e:
            print(f"Error checking SSL status on attempt {attempt+1}: {str(e)}")
    else:
        print("TIMEOUT: Timed out waiting for SSL to become active.")
        print("NOTE: This is normal - SSL validation can take several minutes after DNS records are added.")
else:
    print("ERROR: Could not retrieve hostname details. Please check your Cloudflare configuration.")
