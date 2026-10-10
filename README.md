# iPhone 18 Pro stock → ntfy

Checks Apple Store in-store pickup for the iPhone 18 Pro Max (and optionally Pro) at stores within 50 miles of postal code. It runs on GitHub Actions once an hour and pushes alerts to the ntfy app.

Each hourly run sends:

- **An urgent alert** for any tracked size/color that newly appeared at a store since the last check. Tap it to open that exact phone on apple.com.
- **A digest** of every tracked phone that's in stock, and which stores have it.

## Setup

1. Install **ntfy** on your iPhone, tap **+**, and subscribe to your topic (the value of the NTFY_TOPIC secret).
2. The secret lives in **Settings → Secrets and variables → Actions**.
3. To test: **Actions → iPhone stock check → Run workflow**, choose mode `test`. You should get a "connected" push plus the current stock.

## Choosing phones

Edit `config.json`:

```json
"track": {
  "promax": { "storages": ["256gb", "512gb"], "colors": ["silver", "burgundy"] },
  "pro":    { "storages": [], "colors": [] }
}
```

The tracker watches every storage × color combination listed. Storages: `256gb 512gb 1tb 2tb`. Colors: `black silver glacier burgundy`. To skip one specific combo, add its part number to `exclude` (for example `"MJW64LL/A"`). Set `hourly_summary_when_nothing_in_stock` to `true` if you want an hourly "nothing yet" ping.

## Notes

- The check runs at 7 minutes past each hour. To change that, edit the `cron` line in `.github/workflows/stock-check.yml`.
- Keep the repo **public** so Actions minutes are free. The topic name stays private as a secret.
- GitHub can delay scheduled runs by a few minutes at busy times.
- GitHub pauses schedules in repos with no activity for 60 days. If that happens, re-enable it from the Actions tab.
- If Apple refuses the request, you'll get a low-priority "can't reach Apple" push (at most once every 6 hours).
