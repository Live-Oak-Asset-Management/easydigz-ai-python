import requests
import os
import time
import dns.resolver
import boto3
from cloudflare import Cloudflare


###STAGING-LB
LISTENER_ARN = "arn:aws:elasticloadbalancing:us-east-1:305746409606:listener/app/test-lb-easydigz/38b94f60ee771160/dcba512079fbd6e5" 

EXISTING_RULE_ARN = "arn:aws:elasticloadbalancing:us-east-1:305746409606:listener-rule/app/test-lb-easydigz/38b94f60ee771160/dcba512079fbd6e5/6b449b73a067f357"


ezd_zone_id = "4436b0b7a023ab24067a60c1ccdc3ebb"
token = "oAbwwCLOFqMdRCEvxdFaZ0yde00rszvmSDFItB4p"

client = Cloudflare(api_token=token)
fixed = "ssl-proxy.easydigz.com"


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
    client = boto3.client("elbv2")
    rules = client.describe_rules(ListenerArn=listener_arn)["Rules"]
    priorities = [int(r["Priority"]) for r in rules if r["Priority"].isdigit()]
    return max(priorities, default=1) + 1




def update_existing_alb_rule(rule_arn, new_domain):
    elb = boto3.client('elbv2')

    rule = elb.describe_rules(RuleArns=[rule_arn])['Rules'][0]
    existing_domains = []

    for cond in rule['Conditions']:
        if cond['Field'] == 'host-header':
            existing_domains = cond['HostHeaderConfig']['Values']
            break

    if new_domain in existing_domains:
        print(f" Rule already exists for '{new_domain}'")
        return

    updated_domains = sorted(existing_domains + [new_domain])

    elb.modify_rule(
        RuleArn=rule_arn,
        Conditions=[{
            'Field': 'host-header',
            'HostHeaderConfig': {
                'Values': updated_domains
            }
        }]
    )

    print(f"Added '{new_domain}' to existing ALB rule.")




# === MAIN ===
# client = Cloudflare(api_token=token)


priority = get_next_priority(LISTENER_ARN)

#EXISTING_RULE_ARN = "arn:aws:elasticloadbalancing:us-east-1:305746409606:listener-rule/app/easydigz-noco-lb/5b7816be8d23b49f/88bd161d53517254/2574885b496ffef5"

#domain = "frank.ideafoundation.in"
domain = input("Enter your domain (e.g., portal.domain.com): ").strip()

if not verify_cname(domain, fixed):
    print(" Domain CNAME does not match expected proxy.")
    # exit(1)

hostname_obj = wait_for_cf_ssl(client, ezd_zone_id, domain)
if not hostname_obj:
    print(" Aborting due to inactive SSL.")
    
    exit(1)


update_existing_alb_rule(EXISTING_RULE_ARN, domain)

