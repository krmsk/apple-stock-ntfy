import json, urllib.request, urllib.parse, re

POSTAL = "L5B2C9"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

# Scrape all storage tier pages for Pro only
PAGES = [
    "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro/6.3-inch-display-256gb-black",
    "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro/6.3-inch-display-512gb-black",
    "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro/6.3-inch-display-1tb-black",
    "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro/6.3-inch-display-2tb-black",
]

all_parts = set()
for page in PAGES:
    req = urllib.request.Request(page, headers={
        "User-Agent": UA, "Accept-Language": "en-CA,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        found = re.findall(r'[A-Z]{2,5}\d{2,5}[A-Z]{1,2}/[A-Z]', html)
        new = {p for p in found if p.endswith("VC/A")}
        all_parts |= new
        print(f"{page.split('display-')[1]}: {sorted(new)}")
    except Exception as e:
        print(f"ERROR {page}: {e}")

print("\nAll unique VC/A parts:", sorted(all_parts))

# Now probe them all to get labels
parts = sorted(all_parts)
results = {}
for i in range(0, len(parts), 10):
    chunk = parts[i:i+10]
    q = [("fae","true"),("pl","true"),("mts.0","regular"),("mts.1","compact"),
         ("searchNearby","true"),("location",POSTAL)]
    q += [(f"parts.{j}", p) for j, p in enumerate(chunk)]
    url = "https://www.apple.com/ca/shop/retail/pickup-message?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
        "Accept-Language": "en-CA,en;q=0.9",
        "Referer": "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    for store in data["body"].get("stores", []):
        for pn, v in (store.get("partsAvailability") or {}).items():
            if pn not in results:
                title = v.get("messageTypes", {}).get("regular", {}).get("storePickupProductTitle", "")
                results[pn] = title

print("\n=== Confirmed part numbers ===")
for pn in sorted(results):
    print(f'  "{pn}": "{results[pn]}"')
