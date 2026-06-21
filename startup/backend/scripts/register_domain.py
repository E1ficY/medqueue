import os
import json
import sys
from resend import Resend

# Load API key from environment variable
api_key = os.getenv('RESEND_API_KEY')
if not api_key:
    print('ERROR: RESEND_API_KEY not set')
    sys.exit(1)

resend = Resend(api_key)

def main():
    try:
        # List existing domains to check if already created
        domains_list = resend.Domains.list()
        existing = [d for d in domains_list.get('data', []) if d.get('name') == 'medqueue.me']
        if existing:
            domain = existing[0]
            print('DOMAIN_ALREADY_EXISTS')
        else:
            domain = resend.Domains.create({'name': 'medqueue.me'})
            print('DOMAIN_CREATED')
        print(json.dumps(domain, indent=2))
    except Exception as e:
        print('ERROR:', str(e))
        sys.exit(1)

if __name__ == '__main__':
    main()
