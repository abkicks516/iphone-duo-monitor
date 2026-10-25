#!/usr/bin/env python3
"""Watch Apple Store pickup availability for the iPhone Duo and push alerts via ntfy.

Configuration comes from environment variables (see README.md). Uses only the
Python standard library so it runs anywhere without installing anything.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BUY_PAGE = os.environ.get("BUY_PAGE", "https://www.apple.com/shop/buy-iphone/iphone-duo")
FULFILLMENT_URL = "https://www.apple.com/shop/retail/pickup-message"
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
)
# Apple part numbers look like "MXYZ3LL/A"; LL = US. Other regions use other codes.
PART_RE = re.compile(r'"(M[A-Z0-9]{3,4}\d?[A-Z]{1,2}/A)"')
PRICE_RE = re.compile(r'"partNumber":"(M[A-Z0-9/]+)","price":\{"fullPrice":([\d.]+)')
CHUNK = 10  # parts per fulfillment request
TZ = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))
PRICES = {}  # part -> price, filled in from the buy page
CARRIER = os.environ.get("CARRIER", "unlocked")  # unlocked, att, verizon or t-mobile
BAG_URL = "https://www.apple.com/shop/bag"
HISTORY_FILE = os.environ.get("HISTORY_FILE", "stock-history.csv")


def env_list(name):
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def http_get(url, accept="text/html"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def discover_parts():
    html = http_get(BUY_PAGE)
    parts = sorted(set(PART_RE.findall(html)))
    PRICES.update((p, float(v)) for p, v in PRICE_RE.findall(html))
    if not parts:
        snippets = sorted(set(re.findall(r'.{40}M[A-Z0-9]{4}[A-Z]{2}/A.{40}', html)))[:3]
        sys.exit(
            f"No part numbers found on {BUY_PAGE} (page {len(html)} chars). "
            f"Set PARTS manually (see README). Nearby text: {snippets}"
        )
    print(f"Discovered {len(parts)} part numbers on the buy page")
    return parts


def check_chunk(parts, location):
    params = {"pl": "true", "location": location}
    for i, p in enumerate(parts):
        params[f"parts.{i}"] = p
    url = f"{FULFILLMENT_URL}?{urllib.parse.urlencode(params)}"
    data = json.loads(http_get(url, accept="application/json"))
    body = data.get("body", {})
    stores = body.get("stores") or body.get("content", {}).get("pickupMessage", {}).get("stores", [])
    hits, titles = [], {}
    for store in stores:
        for part, info in (store.get("partsAvailability") or {}).items():
            title = (
                info.get("messageTypes", {}).get("regular", {}).get("storePickupProductTitle")
                or part
            )
            titles[part] = title
            if info.get("pickupDisplay") == "available":
                addr = store.get("address") or {}
                hours = store.get("storeHours") or {}
                hits.append(
                    {
                        "part": part,
                        "title": title,
                        "store": store.get("storeName", "?"),
                        "city": store.get("city", ""),
                        "state": store.get("state", ""),
                        "quote": info.get("pickupSearchQuote", ""),
                        "phone": store.get("phoneNumber", ""),
                        "street": addr.get("address2") or "",
                        "zip": addr.get("postalCode") or "",
                        "hours": (hours.get("hours") or [{}])[0].get("storeTimings", "")
                        if isinstance(hours.get("hours"), list)
                        else hours.get("storeTimings", ""),
                    }
                )
    return hits, titles


def matches_filters(title, include, exclude):
    t = title.lower()
    return all(k.lower() in t for k in include) and not any(k.lower() in t for k in exclude)


def product_url(part, title):
    """Buy page with storage, color and carrier preselected."""
    m = re.fullmatch(r"iPhone Duo (\d+[GT]B) (.+)", title)
    if m:
        storage, color = m.group(1).lower(), re.sub(r"\W+", "-", m.group(2).lower()).strip("-")
        return f"{BUY_PAGE}/7.6-inch-display-{storage}-{color}-{CARRIER}"
    # Unknown title format: Apple redirects this to the buy page with storage and color set.
    return f"https://www.apple.com/shop/product/{part}"


def alert_for(hit):
    """Build (title, message, click_url, actions) for one in-stock listing."""
    model = hit["title"].replace("iPhone Duo ", "")
    title = f"{model} at {hit['store']}"
    found = datetime.now(TZ).strftime("%-I:%M %p")
    price = PRICES.get(hit["part"])
    where = ", ".join(x for x in (hit["street"], hit["city"]) if x)
    lines = [
        f"{hit['title']}" + (f" - ${price:,.0f}" if price else ""),
        f"Pickup: {hit['quote']}" if hit["quote"] else "",
        f"Apple {hit['store']}: {where}" if where else f"Apple {hit['store']}",
        f"Store hours today: {hit['hours']}" if hit["hours"] else "",
        f"Found {found}. Tap to buy - these sell out in minutes.",
    ]
    url = product_url(hit["part"], hit["title"])
    # ntfy allows at most 3 buttons. "Open bag" is for a phone already waiting in your bag.
    actions = [f"view, Buy now, {url}", f"view, Open bag, {BAG_URL}"]
    if hit["phone"]:
        actions.append(f"view, Call store, tel:{re.sub(r'[^0-9+]', '', hit['phone'])}")
    return title, "\n".join(l for l in lines if l), url, "; ".join(actions)


def notify(topic, title, message, click, actions=None):
    headers = {"Title": title, "Priority": "urgent", "Tags": "iphone,rotating_light", "Click": click}
    if actions:
        headers["Actions"] = actions
    req = urllib.request.Request(
        f"{NTFY_SERVER}/{topic}",
        data=message.encode("utf-8"),
        headers={k: v.encode("ascii", "replace").decode() for k, v in headers.items()},
    )
    urllib.request.urlopen(req, timeout=30).read()


def log_history(appeared, gone, titles):
    """Append in-stock/sold-out events to the CSV, then push it if running in Actions."""
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    new_file = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a") as f:
        if new_file:
            f.write("time,event,model,store,part\n")
        for event, keys in (("in stock", appeared), ("sold out", gone)):
            for key in sorted(keys):
                part, store = key.split("@", 1)
                f.write(f"{now},{event},{titles.get(part, part)},{store},{part}\n")
    if os.environ.get("GITHUB_ACTIONS"):
        git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True)
        git("config", "user.name", "stock-monitor")
        git("config", "user.email", "stock-monitor@users.noreply.github.com")
        git("add", HISTORY_FILE)
        git("commit", "-qm", f"Stock history: {len(appeared)} in, {len(gone)} out")
        for _ in range(3):
            git("pull", "-q", "--rebase", "origin", "main")
            if git("push", "-q", "origin", "HEAD:main").returncode == 0:
                break
        else:
            print("WARNING: could not push stock history")


def load_state():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, ValueError):
        return set()


def save_state(keys):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(keys), f, indent=2)


def check_once(parts, location, include, exclude, topic, previous, verbose):
    hits, titles = [], {}
    for i in range(0, len(parts), CHUNK):
        h, t = check_chunk(parts[i : i + CHUNK], location)
        hits += h
        titles.update(t)

    watched = [p for p in parts if matches_filters(titles.get(p, p), include, exclude)]
    if verbose:
        print(f"Watching {len(watched)} of {len(parts)} models near {location}:")
        for p in watched:
            print(f"  {p}  {titles.get(p, '(no title returned)')}")
        if titles and not watched:
            print("WARNING: your keyword filters match nothing. Titles seen above / check spelling.")

    hits = [h for h in hits if h["part"] in watched]
    current = {f"{h['part']}@{h['store']}" for h in hits}
    new = [h for h in hits if f"{h['part']}@{h['store']}" not in previous]
    if current != previous:
        try:
            log_history(current - previous, previous - current, titles)
        except Exception as e:  # never let logging block an alert
            print(f"WARNING: history logging failed: {e}")

    stamp = datetime.now(TZ).strftime("%H:%M:%S")
    if new:
        for h in new:  # one alert per listing, so each links to its own model
            title, message, url, actions = alert_for(h)
            print(f"{stamp} IN STOCK: {title} ({h['part']}) {h['quote']}")
            notify(topic, title, message, url, actions)
    else:
        print(f"{stamp} No new availability ({len(hits)} already-alerted listing(s) still in stock)")
    return current  # sold-out listings drop out, so a restock re-alerts


def main():
    location = os.environ.get("ZIP_CODE")
    topic = os.environ.get("NTFY_TOPIC")
    if not location or not topic:
        sys.exit("ZIP_CODE and NTFY_TOPIC must be set")
    include = env_list("INCLUDE_KEYWORDS")  # e.g. "256GB,Black" - all must match
    exclude = env_list("EXCLUDE_KEYWORDS")  # e.g. "AT&T,Verizon"
    # Keep checking for RUN_MINUTES (0 = check once), every INTERVAL_SECONDS.
    deadline = time.time() + 60 * float(os.environ.get("RUN_MINUTES", "0"))
    interval = float(os.environ.get("INTERVAL_SECONDS", "120"))
    parts = env_list("PARTS") or discover_parts()

    state, checks, failures, first = load_state(), 0, 0, True
    while True:
        checks += 1
        try:
            state = check_once(parts, location, include, exclude, topic, state, first)
            save_state(state)
            first = False
        except Exception as e:  # one bad response shouldn't end a long run
            failures += 1
            print(f"{time.strftime('%H:%M:%S')} check failed: {type(e).__name__}: {e}")
            if failures <= 3:
                print(f"::warning::check failed: {type(e).__name__}: {e}")
        if time.time() + interval >= deadline:
            break
        time.sleep(interval)

    print(f"Done: {checks} checks, {failures} failed")
    if failures == checks:
        sys.exit(f"All {checks} checks failed")


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
