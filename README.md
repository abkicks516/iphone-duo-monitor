# iPhone Duo stock monitor

Every ~5 minutes this checks Apple Store pickup availability near your ZIP code. When a model you want shows up in stock, it sends a push notification to your phone through [ntfy](https://ntfy.sh). Tapping the notification opens Apple's buy page.

You get one alert per model/store combination. If that listing sells out and comes back later, you get alerted again.

## Setup

1. **Phone:** install the ntfy app ([iOS](https://apps.apple.com/app/ntfy/id1625396347)) and subscribe to a hard-to-guess topic name such as `duo-watch-7f3k9q`. Anyone who knows the name can read the topic.
2. **GitHub:** push this folder to a new repo. A private repo is fine.
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
ZIP_CODE=94103 NTFY_TOPIC=duo-watch-7f3k9q INCLUDE_KEYWORDS=256GB python3 monitor.py
```

## Notes

- This uses Apple's unofficial `retail/pickup-message` endpoint, which powers the "Check availability" button on apple.com. Apple can change it without notice.
- GitHub can delay scheduled runs, and it disables them after 60 days without repo activity.
- It only checks in-store pickup, which is usually where restocks appear first. It doesn't track online shipping dates.
