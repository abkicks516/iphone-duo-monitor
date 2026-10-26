# iPhone Duo stock monitor

Every 60 seconds, around the clock, this checks Apple Store pickup availability near one or more ZIP codes, for one or more people. When a model you want shows up in stock, it sends a push notification to your phone through [ntfy](https://ntfy.sh). Tapping the notification opens Apple's buy page.

You get one alert per model/store combination. If that listing sells out and comes back later, you get alerted again.

## Setup

1. **Phone:** install the ntfy app ([iOS](https://apps.apple.com/app/ntfy/id1625396347)) and subscribe to a hard-to-guess topic name such as `duo-watch-` followed by random characters. Anyone who knows the name can read the topic.
2. **GitHub:** push this folder to a new **public** repo. Public repos get unlimited free Actions minutes, and this monitor runs nonstop.
3. Edit the `matrix` list in `.github/workflows/monitor.yml`. Each entry is one person's watcher, with its own alerts:
   - `zip`: one or more ZIP codes, comma-separated. Each covers roughly the 12 nearest Apple Stores.
   - `topic`: that person's ntfy topic.
   - `exclude`: optional words that skip a model, e.g. `1TB,2TB`. `INCLUDE_KEYWORDS` works the other way (all words must match).
   - `carrier`: what the Buy link selects: `unlocked`, `verizon`, `att`, `t-mobile` or `verizon-apple-upgrade`.
   - `history`: the CSV file that watcher logs restocks to.
4. Go to **Actions → iPhone Duo stock monitor → Run workflow** to start it. After that it keeps itself running.

To test notifications, run `curl -d "test" ntfy.sh/<your-topic>`.

## Run locally

```sh
ZIP_CODE=10001,07078 NTFY_TOPIC=your-topic INCLUDE_KEYWORDS=256GB python3 monitor.py
```

## Notes

- This uses Apple's unofficial `retail/pickup-message` endpoint, which powers the "Check availability" button on apple.com. Apple can change it without notice.
- Every time a model appears or sells out at a store, it's logged to that watcher's history CSV in this repo (Eastern time), so you can see restock patterns.
- Each run checks every 60 seconds for about 5h40m. A run is queued every 30 minutes, so the next one starts as soon as the current one ends.
- GitHub disables scheduled workflows after 60 days without repo activity. Re-enable it in the Actions tab.
- Topics in a public repo are visible to anyone, who could then read or send alerts. If that matters, change the topic name.
- It only checks in-store pickup, which is usually where restocks appear first. It doesn't track online shipping dates.
