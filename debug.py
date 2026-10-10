import json, urllib.request, urllib.parse

POSTAL = "L5B2C9"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

# Exactly the first chunk the script sends
CHUNK = ["MJQ34VC/A", "MJQ44VC/A", "MJR74VC/A", "MJQ64VC/A", "MJQ74VC/A"]

for n in [1, 2, 3, 4, 5]:
    parts = CHUNK[:n]
    q = [("fae","true"),("pl","true"),("mts.0","regular"),("mts.1","compact"),
         ("searchNearby","true"),("location", POSTAL)]
    q += [(f"parts.{i}", p) for i, p in enumerate(parts)]
    url = "https://www.apple.com/ca/shop/retail/pickup-message?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en;q=0.9",
        "Referer": "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    body = data["body"]
    stores = body.get("stores")
    content = body.get("content")
    if isinstance(stores, list):
        print(f"{n} parts: ✓ body.stores — {len(stores)} stores")
    elif isinstance(content, dict) and not content:
        print(f"{n} parts: ✗ body.content is empty dict")
    elif isinstance(content, dict):
        print(f"{n} parts: body.content keys={list(content.keys())}")
    else:
        print(f"{n} parts: body keys={list(body.keys())}")
