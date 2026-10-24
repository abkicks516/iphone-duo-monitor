#!/usr/bin/env python3
"""Watch Apple Store pickup availability for the iPhone Duo and push alerts via ntfy.

Configuration comes from environment variables (see README.md). Uses only the
Python standard library so it runs anywhere without installing anything.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

BUY_PAGE = os.environ.get("BUY_PAGE", "https://www.apple.com/shop/buy-iphone/iphone-duo")
FULFILLMENT_URL = "https://www.apple.com/shop/fulfillment-messages"
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
)
# Apple part numbers look like "MXYZ3LL/A"; LL = US. Other regions use other codes.
PART_RE = re.compile(r'"(M[A-Z0-9]{3,4}\d?[A-Z]{1,2}/A)"')
CHUNK = 10  # parts per fulfillment request


def env_list(name):
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def http_get(url, accept="text/html"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def discover_parts():
    html = http_get(BUY_PAGE)
    parts = sorted(set(PART_RE.findall(html)))
    if not parts:
        snippets = sorted(set(re.findall(r'.{40}M[A-Z0-9]{4}[A-Z]{2}/A.{40}', html)))[:3]
        sys.exit(
            f"No part numbers found on {BUY_PAGE} (page {len(html)} chars). "
            f"Set PARTS manually (see README). Nearby text: {snippets}"
        )
    print(f"Discovered {len(parts)} part numbers on the buy page")
    return parts


def check_chunk(parts, location):
    params = {"pl": "true", "mts.0": "regular", "location": location}
    for i, p in enumerate(parts):
        params[f"parts.{i}"] = p
    url = f"{FULFILLMENT_URL}?{urllib.parse.urlencode(params)}"
    data = json.loads(http_get(url, accept="application/json"))
    stores = data.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
    hits, titles = [], {}
    for store in stores:
        for part, info in (store.get("partsAvailability") or {}).items():
            title = (
                info.get("messageTypes", {}).get("regular", {}).get("storePickupProductTitle")
                or part
            )
            titles[part] = title
            if info.get("pickupDisplay") == "available":
                hits.append(
                    {
                        "part": part,
                        "title": title,
                        "store": store.get("storeName", "?"),
                        "city": store.get("city", ""),
                        "quote": info.get("pickupSearchQuote", ""),
                    }
                )
    return hits, titles


def matches_filters(title, include, exclude):
    t = title.lower()
    return all(k.lower() in t for k in include) and not any(k.lower() in t for k in exclude)


def notify(topic, title, message, click):
    req = urllib.request.Request(
        f"{NTFY_SERVER}/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "urgent", "Tags": "iphone,rotating_light", "Click": click},
    )
    urllib.request.urlopen(req, timeout=30).read()


def load_state():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, ValueError):
        return set()


def save_state(keys):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(keys), f, indent=2)


def main():
    location = os.environ.get("ZIP_CODE")
    topic = os.environ.get("NTFY_TOPIC")
    if not location or not topic:
        sys.exit("ZIP_CODE and NTFY_TOPIC must be set")
    include = env_list("INCLUDE_KEYWORDS")  # e.g. "256GB,Black" - all must match
    exclude = env_list("EXCLUDE_KEYWORDS")  # e.g. "AT&T,Verizon"
    parts = env_list("PARTS") or discover_parts()

    hits, titles = [], {}
    for i in range(0, len(parts), CHUNK):
        h, t = check_chunk(parts[i : i + CHUNK], location)
        hits += h
        titles.update(t)

    watched = [p for p in parts if matches_filters(titles.get(p, p), include, exclude)]
    print(f"Watching {len(watched)} of {len(parts)} models near {location}:")
    for p in watched:
        print(f"  {p}  {titles.get(p, '(no title returned)')}")
    if titles and not watched:
        print("WARNING: your keyword filters match nothing. Titles seen above / check spelling.")

    hits = [h for h in hits if h["part"] in watched]
    current = {f"{h['part']}@{h['store']}" for h in hits}
    previous = load_state()
    new = [h for h in hits if f"{h['part']}@{h['store']}" not in previous]

    if new:
        lines = [f"{h['title']} - {h['store']} ({h['city']}) {h['quote']}".strip() for h in new]
        print("IN STOCK:\n  " + "\n  ".join(lines))
        notify(topic, f"iPhone Duo in stock at {len(new)} spot(s)!", "\n".join(lines), BUY_PAGE)
    else:
        print(f"No new availability ({len(hits)} already-alerted listing(s) still in stock)")

    save_state(current)  # forget sold-out listings so a restock re-alerts


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"::error::{e.code}")
        raise
    except Exception as e:
        detail = getattr(e, "read", lambda: b"")()[:300]
        print(f"::error::{type(e).__name__}: {e} {detail!r}")
        raise
