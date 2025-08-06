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

fixed = "ssl-proxy.easydigz.com"  #overide for specific agent-id

client = Cloudflare(api_token=token)

<<<<<<< HEAD
# Step 1: Get custom domain from user
custom_domain = input("Enter your custom domain (e.g., portal.domain.com): ").strip()
=======

# Step 1: Get custom domain from CLI or input
if len(sys.argv) > 1:
    custom_domain = sys.argv[1].strip()
else:
    custom_domain = input("Enter your custom domain (e.g., portal.domain.com): ").strip()

#custom_domain = input("Enter your custom domain (e.g., portal.domain.com): ").strip()
>>>>>>> 203a00865303c8d1507b9437e150bfbebb038acf

# Step 2: Create custom hostname with SSL (type: txt)
try:
    response = client.custom_hostnames.create(
        zone_id=ezd_zone_id,
        hostname = custom_domain,
            ssl = {
                "type": "dv",     # For SaaS onboarding / external domains
                "method": "txt"
            },
        
        extra_body={"custom_origin_server":fixed}
    )

    print(f"\n Creating Custom hostname : {response.hostname}")
    print(f" SSL status: {response.ssl.status}")

except Exception as e:
    print("! Failed to create custom hostname !")
    if hasattr(e, "response") and e.response is not None:
        print(e.response.json())
    else:
        print(str(e))
    exit(1)

# Step 3: Fetch updated hostname to get TXT records
time.sleep(2)  # Wait for propagation

hostname_id = response.id
hostname_obj = client.custom_hostnames.get(zone_id=ezd_zone_id,custom_hostname_id=hostname_id)

# Step 4: Print all TXT validation records
def print_dns_records(hostname_obj):
    print("\n Please add the following TXT records to your domain's DNS:")

    printed = False
    #General CNAME Mapping
    print("\n Add CNAME record")
    print(f"Name:   {hostname_obj.hostname}")
    print(f"Value:  {fixed}")


    # 1. ownership_verification
    ov = getattr(hostname_obj, "ownership_verification", None)
    # if ov and ov.type == "txt":
    if ov and getattr(ov, "type", None) == "txt":
        print(f"\n Ownership Verification TXT:")
        print(f"Name:  {ov.name}")
        print(f"Value: {ov.value}")
        printed = True

    # ssl = hostname_obj.ssl
    ssl = getattr(hostname_obj, "ssl", None)
    if ssl:
    # 2.a ssl.validation_records[]
        records = getattr(ssl, "validation_records", [])
        # if ssl.validation_records:
        if records:
            records = ssl.validation_records
            for record in records:
                if record.status == "pending":
                    status = getattr(record, "status", None)
                    txt_name = getattr(record, "txt_name", None)
                    txt_value = getattr(record, "txt_value", None)
                    if status == "pending" and txt_name and txt_value:
<<<<<<< HEAD
                        print(f"\n🔐 SSL Validation TXT:")
=======
                        print(f"\n SSL Validation TXT:")
>>>>>>> 203a00865303c8d1507b9437e150bfbebb038acf
                        print(f"Name:  {txt_name}")
                        print(f"Value: {txt_value}")
                        printed = True
                    
        # 2.b. ssl.txt_name / txt_value (direct)
        if hasattr(ssl, "txt_name") and hasattr(ssl, "txt_value"):
<<<<<<< HEAD
            print(f"\n🔐 SSL Validation TXT (direct):")
=======
            print(f"\n SSL Validation TXT (direct):")
>>>>>>> 203a00865303c8d1507b9437e150bfbebb038acf
            print(f"Name:  {ssl.txt_name}")
            print(f"Value: {ssl.txt_value}")
            printed = True



    if not printed:
<<<<<<< HEAD
        print("⚠️ No TXT records found yet. Please wait a few seconds and try again.")
=======
        print(" No TXT records found yet. Please wait a few seconds and try again.")
>>>>>>> 203a00865303c8d1507b9437e150bfbebb038acf



print_dns_records(hostname_obj)

# Step 2: Poll until SSL status becomes "active" or times out
MAX_RETRIES = 3
WAIT_SECONDS = 5

for attempt in range(MAX_RETRIES):
    time.sleep(WAIT_SECONDS)
    updated = client.custom_hostnames.get(zone_id=ezd_zone_id,custom_hostname_id=hostname_id    )
    ssl_status = updated.ssl.status
    print(f"Attempt {attempt+1}: SSL status = {ssl_status}")

    if ssl_status == "active":
        print("SSL is active!")
        break
    elif ssl_status in ["pending_validation", "initializing", "pending_deployment"]:
        continue
    else:
        print(f"Unexpected status: {ssl_status}")
        break
else:
    print("Timed out waiting for SSL to become active.")
<<<<<<< HEAD


    
=======
>>>>>>> 203a00865303c8d1507b9437e150bfbebb038acf
