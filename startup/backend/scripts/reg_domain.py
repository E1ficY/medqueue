import urllib.request
import json

key = "re_AEtnQLGf_AfwD3n8MHffW7mMBvfGvuTQ8"
headers = {
    "Authorization": "Bearer " + key,
    "Content-Type": "application/json",
    "User-Agent": "python-resend/2.0.0",
}

req = urllib.request.Request("https://api.resend.com/domains", headers=headers)
try:
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    print("LIST OK:", json.dumps(data, indent=2))
    existing = [d for d in data.get("data", []) if d.get("name") == "medqueue.me"]
    if existing:
        print("EXISTS:", json.dumps(existing[0], indent=2))
    else:
        payload = json.dumps({"name": "medqueue.me"}).encode()
        req2 = urllib.request.Request(
            "https://api.resend.com/domains", data=payload, headers=headers
        )
        resp2 = urllib.request.urlopen(req2)
        print("CREATED:", json.dumps(json.loads(resp2.read()), indent=2))
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code)
    print(e.read().decode())
except Exception as ex:
    print("ERROR:", ex)
