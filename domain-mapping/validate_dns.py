import os
import sys
import json
import time
from dotenv import load_dotenv

try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False
    print("Warning: dnspython not installed. DNS validation will be limited.")

try:
    from cloudflare import Cloudflare
    CLOUDFLARE_AVAILABLE = True
except ImportError:
    CLOUDFLARE_AVAILABLE = False
    print("Warning: cloudflare package not available. Cloudflare status checks disabled.")

def validate_dns_records(domain):
    """Validate DNS records for a domain using both DNS lookups and Cloudflare API"""
    
    # Load environment variables
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    
    results = {
        "domain": domain,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "checks": {
            "cname": {"status": "fail", "details": "", "expected": "ssl-proxy.easydigz.com"},
            "ownership_txt": {"status": "fail", "details": "", "expected": "UUID format"},
            "ssl_txt": {"status": "fail", "details": "", "expected": "ACME challenge"}
        },
        "cloudflare_status": {"status": "unknown", "details": ""},
        "overall_status": "fail"
    }
    
    try:
        # First, get Cloudflare status if possible
        ezd_zone_id = os.getenv("CF_ZONE_ID")
        token = os.getenv("CF_TOKEN")
        
        if CLOUDFLARE_AVAILABLE and ezd_zone_id and token:
            try:
                client = Cloudflare(api_token=token)
                hostnames_response = client.custom_hostnames.list(zone_id=ezd_zone_id)
                hostnames = hostnames_response.result if hasattr(hostnames_response, 'result') else hostnames_response
                
                cf_hostname = None
                for hostname in hostnames:
                    if hostname.hostname == domain:
                        cf_hostname = hostname
                        break
                
                if cf_hostname:
                    ssl_status = cf_hostname.ssl.status if cf_hostname.ssl else "unknown"
                    results["cloudflare_status"]["status"] = ssl_status
                    results["cloudflare_status"]["details"] = f"Cloudflare SSL status: {ssl_status}"
                    print(f"Cloudflare Status: {ssl_status}")
                    
                    # Show expected DNS records from Cloudflare
                    print(f"\nCloudflare expects these DNS records:")
                    
                    # Ownership verification
                    ov = getattr(cf_hostname, "ownership_verification", None)
                    if ov and getattr(ov, "type", None) == "txt":
                        print(f"Ownership TXT: {ov.name} = {ov.value}")
                    
                    # SSL validation
                    ssl = getattr(cf_hostname, "ssl", None)
                    if ssl:
                        records = getattr(ssl, "validation_records", [])
                        for record in records:
                            txt_name = getattr(record, "txt_name", None)
                            txt_value = getattr(record, "txt_value", None)
                            if txt_name and txt_value:
                                print(f"SSL TXT: {txt_name} = {txt_value}")
                        
                        # Direct SSL txt records
                        if hasattr(ssl, "txt_name") and hasattr(ssl, "txt_value"):
                            print(f"SSL TXT (direct): {ssl.txt_name} = {ssl.txt_value}")
                else:
                    results["cloudflare_status"]["details"] = "Domain not found in Cloudflare"
                    print("Domain not found in Cloudflare custom hostnames")
            except Exception as e:
                results["cloudflare_status"]["details"] = f"Cloudflare API error: {str(e)}"
                print(f"Cloudflare API error: {str(e)}")
        
        if not DNS_AVAILABLE:
            print("\nDNS validation skipped - dnspython not available")
            results["checks"]["cname"]["details"] = "DNS validation not available"
            results["checks"]["ownership_txt"]["details"] = "DNS validation not available"
            results["checks"]["ssl_txt"]["details"] = "DNS validation not available"
        else:
            # 1. Check CNAME record
            print(f"Checking CNAME record for {domain}...")
            try:
                cname_answers = dns.resolver.resolve(domain, 'CNAME')
                cname_value = str(cname_answers[0]).rstrip('.')
                expected_cname = "ssl-proxy.easydigz.com"
                
                if cname_value == expected_cname:
                    results["checks"]["cname"]["status"] = "pass"
                    results["checks"]["cname"]["details"] = f"Correct: {cname_value}"
                    print(f"SUCCESS: CNAME record is correct: {cname_value}")
                else:
                    results["checks"]["cname"]["details"] = f"Expected: {expected_cname}, Found: {cname_value}"
                    print(f"FAIL: CNAME incorrect. Expected: {expected_cname}, Found: {cname_value}")
            except dns.resolver.NXDOMAIN:
                results["checks"]["cname"]["details"] = "Domain not found"
                print(f"FAIL: Domain not found: {domain}")
            except dns.resolver.NoAnswer:
                results["checks"]["cname"]["details"] = "No CNAME record found"
                print(f"FAIL: No CNAME record found for {domain}")
            except Exception as e:
                results["checks"]["cname"]["details"] = f"DNS error: {str(e)}"
                print(f"ERROR: DNS error checking CNAME: {str(e)}")

            # 2. Check Ownership Verification TXT record
            ownership_domain = f"_cf-custom-hostname.{domain}"
            print(f"Checking ownership TXT record for {ownership_domain}...")
            try:
                txt_answers = dns.resolver.resolve(ownership_domain, 'TXT')
                txt_values = [str(answer).strip('"') for answer in txt_answers]
                
                if txt_values:
                    # Check if any value looks like a UUID
                    uuid_found = any(len(val) == 36 and val.count('-') == 4 for val in txt_values)
                    if uuid_found:
                        results["checks"]["ownership_txt"]["status"] = "pass"
                        results["checks"]["ownership_txt"]["details"] = f"Found UUID: {txt_values}"
                        print(f"SUCCESS: Ownership TXT record found: {txt_values}")
                    else:
                        results["checks"]["ownership_txt"]["details"] = f"Found non-UUID values: {txt_values}"
                        print(f"WARNING: Found TXT records but not UUID format: {txt_values}")
                else:
                    results["checks"]["ownership_txt"]["details"] = "No TXT records found"
                    print(f"FAIL: No ownership TXT records found")
            except dns.resolver.NXDOMAIN:
                results["checks"]["ownership_txt"]["details"] = "Ownership domain not found"
                print(f"FAIL: Ownership domain not found: {ownership_domain}")
            except dns.resolver.NoAnswer:
                results["checks"]["ownership_txt"]["details"] = "No TXT record found"
                print(f"FAIL: No ownership TXT record found")
            except Exception as e:
                results["checks"]["ownership_txt"]["details"] = f"DNS error: {str(e)}"
                print(f"ERROR: DNS error checking ownership TXT: {str(e)}")

            # 3. Check SSL Validation TXT record
            ssl_domain = f"_acme-challenge.{domain}"
            print(f"Checking SSL validation TXT record for {ssl_domain}...")
            try:
                txt_answers = dns.resolver.resolve(ssl_domain, 'TXT')
                txt_values = [str(answer).strip('"') for answer in txt_answers]
                
                if txt_values:
                    # Check if any value looks like an ACME challenge (base64-like)
                    acme_found = any(len(val) > 40 and val.replace('_', '').replace('-', '').isalnum() for val in txt_values)
                    if acme_found:
                        results["checks"]["ssl_txt"]["status"] = "pass"
                        results["checks"]["ssl_txt"]["details"] = f"Found ACME challenge: {txt_values}"
                        print(f"SUCCESS: SSL validation TXT record found: {txt_values}")
                    else:
                        results["checks"]["ssl_txt"]["details"] = f"Found non-ACME values: {txt_values}"
                        print(f"WARNING: Found TXT records but not ACME format: {txt_values}")
                else:
                    results["checks"]["ssl_txt"]["details"] = "No TXT records found"
                    print(f"FAIL: No SSL validation TXT records found")
            except dns.resolver.NXDOMAIN:
                results["checks"]["ssl_txt"]["details"] = "SSL domain not found"
                print(f"FAIL: SSL validation domain not found: {ssl_domain}")
            except dns.resolver.NoAnswer:
                results["checks"]["ssl_txt"]["details"] = "No TXT record found"
                print(f"FAIL: No SSL validation TXT record found")
            except Exception as e:
                results["checks"]["ssl_txt"]["details"] = f"DNS error: {str(e)}"
                print(f"ERROR: DNS error checking SSL validation TXT: {str(e)}")

        # Determine overall status
        passed_checks = sum(1 for check in results["checks"].values() if check["status"] == "pass")
        total_checks = len(results["checks"])
        
        if passed_checks == total_checks:
            results["overall_status"] = "pass"
            print(f"\nSUCCESS: All DNS checks passed ({passed_checks}/{total_checks})")
        else:
            results["overall_status"] = "partial" if passed_checks > 0 else "fail"
            print(f"\nWARNING: DNS checks: {passed_checks}/{total_checks} passed")

        # Print summary
        print(f"\n=== DNS VALIDATION SUMMARY for {domain} ===")
        print(f"CNAME Record: {results['checks']['cname']['status'].upper()}")
        print(f"  {results['checks']['cname']['details']}")
        print(f"Ownership TXT: {results['checks']['ownership_txt']['status'].upper()}")
        print(f"  {results['checks']['ownership_txt']['details']}")
        print(f"SSL TXT: {results['checks']['ssl_txt']['status'].upper()}")
        print(f"  {results['checks']['ssl_txt']['details']}")
        print(f"Cloudflare Status: {results['cloudflare_status']['details']}")
        print(f"Overall Status: {results['overall_status'].upper()} ({passed_checks}/{total_checks} checks passed)")
        print("=" * 60)

    except Exception as e:
        error_msg = f"General validation error: {str(e)}"
        print(error_msg)
        results["error"] = error_msg

    # Output JSON for API consumption
    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        domain = sys.argv[1].strip()
    else:
        domain = input("Enter the domain to validate (e.g., abc.crackiq.com): ").strip()
    
    validate_dns_records(domain)
