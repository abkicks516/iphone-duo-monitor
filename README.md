# iPhone Duo stock monitor

Every 60 seconds, around the clock, this checks Apple Store pickup availability near your ZIP code. When a model you want shows up in stock, it sends a push notification to your phone through [ntfy](https://ntfy.sh). Tapping the notification opens Apple's buy page.

You get one alert per model/store combination. If that listing sells out and comes back later, you get alerted again.

## Setup

1. **Phone:** install the ntfy app ([iOS](https://apps.apple.com/app/ntfy/id1625396347)) and subscribe to a hard-to-guess topic name such as `duo-watch-` followed by random characters. Anyone who knows the name can read the topic.
2. **GitHub:** push this folder to a new **public** repo. Public repos get unlimited free Actions minutes, and this monitor runs nonstop.
3. In the repo, go to **Settings → Secrets and variables → Actions**:
   - **Secret** `NTFY_TOPIC`: your topic name
   - **Variable** `ZIP_CODE`: e.g. `94103`
   - **Variable** `INCLUDE_KEYWORDS` (optional): comma-separated words that must *all* appear in the product title, e.g. `256GB,Black`
   - **Variable** `EXCLUDE_KEYWORDS` (optional): e.g. `AT&T,Verizon,T-Mobile`
   - **Variable** `PARTS` (optional): exact part numbers such as `MABC1LL/A,MABD2LL/A`. Leave this blank to auto-discover them from the buy page.
4. Go to **Actions → iPhone Duo stock monitor → Run workflow** to run it once. The log lists every model it watches, using Apple's titles. Use those titles to adjust your keywords.

To test notifications, run `curl -d "test" ntfy.sh/<your-topic>`.

## Run locally

```sh
ZIP_CODE=94103 NTFY_TOPIC=your-topic INCLUDE_KEYWORDS=256GB python3 monitor.py
```

## Notes

- This uses Apple's unofficial `retail/pickup-message` endpoint, which powers the "Check availability" button on apple.com. Apple can change it without notice.
- Every time a model appears or sells out at a store, it's logged to `stock-history.csv` in this repo (Eastern time), so you can see restock patterns.
- Each run checks every 60 seconds for about 5h40m. A run is queued every 30 minutes, so the next one starts as soon as the current one ends.
- GitHub disables scheduled workflows after 60 days without repo activity. Re-enable it in the Actions tab.
- Keep your topic in the `NTFY_TOPIC` secret, never in the code. Anyone who knows the topic name can read and send alerts.
- It only checks in-store pickup, which is usually where restocks appear first. It doesn't track online shipping dates.
