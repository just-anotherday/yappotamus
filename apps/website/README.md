# yappotamus

My personal portfolio project.

## Frontend (React + Tailwind)

The new immersive frontend is now implemented in:

- `frontend/app`

### Run locally

```bash
npm install --prefix frontend/app
npm run dev --prefix frontend/app
```

### Build

```bash
npm run build --prefix frontend/app
```

### Migrated pages/components

- Home
- Projects
  - slimeScraper game loader
  - nuclear easter egg
  - AI chat companion panel
- Recipes catalog
- Dynamic Pan Mee recipe page
  - servings scaler
  - image modal
  - quick navigation + back-to-top
  - print recipe

### Legacy static frontend

The original static HTML/CSS/JS site remains under `frontend/` for reference during migration.

## Cloudflare analytics + console troubleshooting notes

- If browser console shows a Cloudflare beacon CORS error like:
  - `Access to script at https://static.cloudflareinsights.com/beacon.min.js/... blocked by CORS`
- In Cloudflare Web Analytics / RUM, disable **Automatic setup** first to confirm the source.
- If analytics is needed later, prefer **manual snippet installation** over automatic injection.

## Static site audio note (ORB/CORS)

- For the legacy static page (`frontend/index.html`), the bugle easter-egg audio is configured to load locally:
  - `assets/military-bugle-call-491.mp3`
- This avoids browser `net::ERR_BLOCKED_BY_ORB` issues from third-party audio hosts.
- Ensure that MP3 file exists in `frontend/assets/` before deployment.
