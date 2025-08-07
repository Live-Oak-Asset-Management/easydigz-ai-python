import requests
import os
import time
import dns.resolver
import boto3
from cloudflare import Cloudflare
import sys
from dotenv import load_dotenv

from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

if not os.path.exists(env_path):
    raise FileNotFoundError(f"env file not found at: {env_path}")

load_dotenv(dotenv_path=env_path)
### STAGING-LB
LISTENER_ARN = os.getenv("LISTENER_ARN")
EXISTING_RULE_ARN = os.getenv("EXISTING_RULE_ARN")
# AWS credentials (STAGING)
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")

ezd_zone_id = os.getenv("CF_ZONE_ID")
token = os.getenv("CF_TOKEN")

client = Cloudflare(api_token=token)
fixed = "ssl-proxy.easydigz.com"
# Create boto3 session with explicit credentials
aws_session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

elb = aws_session.client("elbv2")
# === CONFIG END ===

def verify_cname(domain, expected):
    try:
        result = dns.resolver.resolve(domain, "CNAME")
        for r in result:
            cname_target = str(r.target).rstrip(".").lower()
            print(f"CNAME for {domain} points to {cname_target}")
            return cname_target == expected.rstrip(".").lower()
    except Exception as e:
        print(f"DNS check failed: {e}")
        return False


def wait_for_cf_ssl(client, zone_id, hostname, timeout=300):
    print(f" Checking SSL Status for {hostname}  ...")
    start = time.time()
    while time.time() - start < timeout:
        # Get hostname by listing and matching
        hostnames = client.custom_hostnames.list(zone_id=zone_id).result
        hostname_obj = next((h for h in hostnames if h.hostname == hostname), None)

        if not hostname_obj:
            print(" Hostname not found in CF")
            return None

        ssl_status = hostname_obj.ssl.status
        print(f" SSL status: {ssl_status}")
        if ssl_status == "active":
            print("SSL is active")
            return hostname_obj
        time.sleep(10)
    print(" Timed out waiting for SSL")
    return None


def get_next_priority(listener_arn):
    rules = elb.describe_rules(ListenerArn=listener_arn)["Rules"]
    priorities = [int(r["Priority"]) for r in rules if r["Priority"].isdigit()]
    return max(priorities, default=1) + 1


def update_existing_alb_rule(rule_arn, new_domain):
    rule = elb.describe_rules(RuleArns=[rule_arn])["Rules"][0]
    existing_domains = []

    for cond in rule["Conditions"]:
        if cond["Field"] == "host-header":
            existing_domains = cond["HostHeaderConfig"]["Values"]
            break

    if new_domain in existing_domains:
        print(f" Rule already exists for '{new_domain}'")
        return

    updated_domains = sorted(existing_domains + [new_domain])

    elb.modify_rule(
        RuleArn=rule_arn,
        Conditions=[{
            "Field": "host-header",
            "HostHeaderConfig": {
                "Values": updated_domains
            }
        }]
    )

    print(f"Added '{new_domain}' to existing ALB rule.")


# === MAIN ===
if len(sys.argv) > 1:
    domain = sys.argv[1].strip()
else:
    domain = input("Enter your domain (e.g., portal.domain.com): ").strip()

if not verify_cname(domain, fixed):
    print("Domain CNAME does not match expected proxy.")
    # exit(1)

hostname_obj = wait_for_cf_ssl(client, ezd_zone_id, domain)
if not hostname_obj:
    print("Aborting due to inactive SSL.")
    exit(1)

update_existing_alb_rule(EXISTING_RULE_ARN, domain)
