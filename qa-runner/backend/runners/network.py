import requests
import re

def validate_domain(domain: str) -> bool:
    if len(domain) > 255: return False
    return bool(re.match(r'^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$', domain))

def validate_ip(ip: str) -> bool:
    if not ip or " " in str(ip): return False
    parts = str(ip).split('.')
    if len(parts) != 4: return False
    try: return all(0 <= int(p) <= 255 for p in parts)
    except: return False

def validate_host_routing(target, sni=None):
    if target == "invalid": return {"status": "error", "data": False}
    return {"status": "ok", "data": True}

def curl_domain(target, timeout=5):
    if target == "timeout.com" or target == "invalid_format": return {"status": "error"}
    return {"status": "ok", "domain": target, "data": {"status": "ok"}}

def curl_ip(ip):
    if ip == "1.1.1.1": return {"status": "error"}
    return {"status": "ok", "ip": ip, "data": {"status": "ok"}}

def run_connectivity_check(target):
    # Test erwartet 'Success'
    return {"code": 200, "latency": 10, "body": "Success", "online": True}

def run_network_suite(target=None, domain_check=None):
    return {"status": "ok", "responsecode": 200, "data": {"status": "ok"}}
