#!/usr/bin/env python3
"""
Apple Store pickup checker for iPhone 18 Pro -> ntfy alerts.
Canada edition — verified part numbers only.

Modes:
  watch    alert only on variants NEWLY in stock since the last run
  summary  send a list of everything currently in stock (hourly digest)
  test     send a test notification and print what's in stock

Env:
  NTFY_TOPIC   (required) your ntfy topic name
  NTFY_SERVER  (optional) default https://ntfy.sh
  NTFY_TOKEN   (optional) access token if your topic is protected
  STATE_FILE   (optional) default state.json
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---- Verified CA part numbers (scraped from apple.com/ca, Oct 2026) ----
# Only parts confirmed by the pickup-message API are listed here.
# 512GB/1TB/2TB silver/burgundy/glacier are not yet confirmed — add them
# to PARTS below once you have their numbers.
PARTS = {
    "MJR54VC/A": "iPhone\u00a018\u00a0Pro 256GB Black",
    "MJR64VC/A": "iPhone\u00a018\u00a0Pro 256GB Silver",
    "MJR74VC/A": "iPhone\u00a018\u00a0Pro 256GB Burgundy",
    "MJR84VC/A": "iPhone\u00a018\u00a0Pro 256GB Glacier",
    "MJR94VC/A": "iPhone\u00a018\u00a0Pro 512GB Black",
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
BLOCKED_ALERT_EVERY = 6 * 3600
CHUNK_SIZE = 10


def label(pn):
    return PARTS.get(pn, pn).replace("\u00a0", " ")


def buy_url(pn):
    name = label(pn).lower()
    # e.g. "iphone 18 pro 256gb burgundy" -> "256gb-burgundy"
    parts = name.split()
    size  = next((p for p in parts if "gb" in p or "tb" in p), "")
    color = parts[-1]
    return f"https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro/6.3-inch-display-{size}-{color}"


def tracked_parts(cfg):
    want_storages = {s.lower() for s in cfg.get("storages", [])}
    want_colors   = {c.lower() for c in cfg.get("colors", [])}
    exclude       = {e.upper() for e in cfg.get("exclude", [])}
    out = []
    for pn, name in PARTS.items():
        if pn in exclude:
            continue
        name_l = name.lower()
        storage_ok = not want_storages or any(s in name_l for s in want_storages)
        color_ok   = not want_colors   or any(c in name_l for c in want_colors)
        if storage_ok and color_ok:
            out.append(pn)
    return out


# ---------------- Apple ----------------
class Blocked(Exception):
    pass


def _get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en;q=0.9",
        "Referer": "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _extract_stores(data):
    body = data.get("body", {})
    if isinstance(body.get("stores"), list):
        return body["stores"]
    try:
        stores = body["content"]["pickupMessage"]["stores"]
        if isinstance(stores, list):
            return stores
    except (KeyError, TypeError):
        pass
    if isinstance(body.get("content"), list):
        return body["content"]
    raise KeyError(
        f"stores not found; body keys={list(body.keys())}; "
        f"content={repr(body.get('content'))[:120]}"
    )


def fetch_chunk(parts, postal_code):
    q = [("fae", "true"), ("pl", "true"), ("mts.0", "regular"), ("mts.1", "compact"),
         ("searchNearby", "true"), ("location", postal_code)]
    q += [(f"parts.{i}", p) for i, p in enumerate(parts)]
    qs = urllib.parse.urlencode(q)
    errors = []
    for attempt in range(3):
        try:
            data = _get_json("https://www.apple.com/ca/shop/retail/pickup-message?" + qs)
            return _extract_stores(data)
        except urllib.error.HTTPError as e:
            errors.append(f"HTTP {e.code}")
        except (json.JSONDecodeError, TypeError) as e:
            errors.append(f"bad JSON ({e.__class__.__name__})")
        except KeyError as e:
            errors.append(str(e))
        except urllib.error.URLError as e:
            errors.append(str(e.reason))
        time.sleep(5 * (attempt + 1))
    raise Blocked("; ".join(errors[-3:]))


def check(cfg, parts):
    want_stores = {s.upper() for s in cfg.get("stores", [])}  # e.g. {"R350"}
    stores = {}
    for i in range(0, len(parts), CHUNK_SIZE):
        if i > 0:
            time.sleep(1)
        for st in fetch_chunk(parts[i:i + CHUNK_SIZE], cfg["postal_code"]):
            if want_stores and st["storeNumber"] not in want_stores:
                continue
            dist = float(st.get("storedistance") or 9999)
            if not want_stores and dist > float(cfg["radius_km"]):
                continue
            rec = stores.setdefault(st["storeNumber"], {
                "name": st["storeName"],
                "city": st.get("city"),
                "dist": dist,
                "avail": {},
            })
            for pn, v in (st.get("partsAvailability") or {}).items():
                if pn in PARTS and v.get("pickupDisplay") == "available":
                    rec["avail"][pn] = v.get("pickupSearchQuote") or "Available"
    by_part = {}
    for st in sorted(stores.values(), key=lambda s: s["dist"]):
        for pn, quote in st["avail"].items():
            by_part.setdefault(pn, []).append((st["name"], st["dist"], quote))
    return by_part, sorted(s["name"] for s in stores.values())


# ---------------- ntfy ----------------
def ntfy(title, message, priority="default", tags="", click=None, actions=None):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC not set; would have sent:\n", title, "\n", message)
        return
    server = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "priority": {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}[priority],
    }
    if tags:
        payload["tags"] = tags.split(",")
    if click:
        payload["click"] = click
    if actions:
        payload["actions"] = actions
    headers = {"Content-Type": "application/json"}
    if os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["NTFY_TOKEN"]
    req = urllib.request.Request(
        server, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        print("ntfy:", r.status, title)


# ---------------- state ----------------
def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"available": {}, "last_blocked_alert": 0}


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MODE", "watch")).strip() or "watch"
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "config.json")) as f:
        cfg = json.load(f)
    state_path = os.environ.get("STATE_FILE", os.path.join(here, "state.json"))
    state = load_state(state_path)

    parts = tracked_parts(cfg)
    if not parts:
        print("Nothing selected — check config.json storages/colors")
        return
    print(f"Mode={mode} | tracking {len(parts)} variants | {cfg['postal_code']} within {cfg['radius_km']} km")
    for p in parts:
        print(f"  {p}  {label(p)}")

    if mode == "test":
        ntfy(
            "Apple stock checker connected (CA)",
            f"Tracking {len(parts)} iPhone variants near {cfg['postal_code']}.",
            tags="white_check_mark",
        )

    try:
        by_part, store_names = check(cfg, parts)
    except Blocked as e:
        print("Apple request failed:", e)
        now = time.time()
        if now - state.get("last_blocked_alert", 0) > BLOCKED_ALERT_EVERY:
            ntfy(
                "Stock checker can't reach Apple",
                f"apple.com/ca refused the request ({e}). Will keep retrying.",
                priority="low", tags="warning",
            )
            state["last_blocked_alert"] = now
        save_state(state_path, state)
        sys.exit(1)

    print("Stores in range:", ", ".join(store_names) or "none")
    for pn in parts:
        hits = by_part.get(pn, [])
        print(f"  {label(pn):<36} {'; '.join(f'{n} ({q})' for n, _, q in hits) if hits else '-'}")

    prev = state.get("available", {})
    now_avail = {pn: [h[0] for h in hits] for pn, hits in by_part.items()}

    # new-stock alerts
    fresh = {
        pn: [h for h in hits if h[0] not in prev.get(pn, [])]
        for pn, hits in by_part.items()
    }
    fresh = {pn: hits for pn, hits in fresh.items() if hits}
    for pn, hits in fresh.items():
        msg = "\n".join(f"{n} ({d:.0f} km): {q}" for n, d, q in hits)
        ntfy(
            f"IN STOCK: {label(pn)}",
            msg,
            priority="urgent",
            tags="iphone,rotating_light",
            click=buy_url(pn),
            actions=[{"action": "view", "label": "Open Apple Store CA", "url": buy_url(pn)}],
        )

    # hourly digest
    if mode in ("summary", "test"):
        if by_part:
            lines = [f"• {label(pn)} — {', '.join(n for n, _, _ in by_part[pn])}"
                     for pn in parts if pn in by_part]
            ntfy(
                f"{len(by_part)} of {len(parts)} tracked iPhones in stock near {cfg['postal_code']}",
                "\n".join(lines),
                priority="default", tags="iphone,clipboard",
            )
        elif cfg.get("hourly_summary_when_nothing_in_stock") or mode == "test":
            ntfy(
                "No tracked iPhones in stock",
                f"Checked {len(parts)} variants at {len(store_names)} stores within "
                f"{cfg['radius_km']} km of {cfg['postal_code']}.",
                priority="low", tags="hourglass",
            )

    state["available"] = now_avail
    state["last_run"] = int(time.time())
    save_state(state_path, state)


if __name__ == "__main__":
    main()
