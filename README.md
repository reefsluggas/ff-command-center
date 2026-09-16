# FF Command Center

Full fantasy football snapshot site. Sleeper data (leagues, rosters, matchups,
injuries, trending waiver adds) loads live in the browser on every visit — no
server, no keys. FantasyPros Expert Consensus Rankings are fetched by a
scheduled GitHub Action and power the start/sit suggestions.

## Setup (one time, ~5 minutes)

1. Create a new GitHub repo (public or private, either works) and upload
   everything in this folder, keeping the structure:

   ```
   index.html
   data/rankings.json
   scripts/fetch_rankings.py
   .github/workflows/rankings.yml
   ```

2. Enable GitHub Pages: repo **Settings → Pages → Source: Deploy from a
   branch → main / (root)**. Your site will be live at
   `https://<your-username>.github.io/<repo-name>/` in a minute or two.

   The site is fully functional at this point — everything except the
   start/sit suggestions works with no further setup.

3. (Enables suggestions) Request a free API key at
   https://www.fantasypros.com/apis/ then add it to the repo:
   **Settings → Secrets and variables → Actions → New repository secret**,
   name it `FANTASYPROS_API_KEY`.

4. Run the Action once manually to confirm: **Actions → Update consensus
   rankings → Run workflow**. After it finishes, `data/rankings.json` will be
   populated and the site shows ECR columns and suggestions on next load.

The Action then runs on its own 4x per day (midnight, 6am, noon, 6pm UTC),
which includes 8am ET so Sunday mornings are always fresh.

## How the pieces work

- **index.html** — the whole site. Fetches Sleeper client-side, reads
  `data/rankings.json` for consensus ranks, matches players by normalized
  name + position (defenses by team abbreviation).
- **scripts/fetch_rankings.py** — pulls weekly ECR for PPR, Half PPR, and
  Standard, so each league's suggestions use that league's actual scoring.
  Fails safe: if the key is missing or the API is down, it leaves the last
  good rankings file alone.
- **Start/sit logic** — a bench player is suggested over a starter when his
  consensus rank is at least 5 spots better, or whenever a starter is
  Out/Doubtful/IR/Suspended and a healthy ranked bench player is eligible
  for that slot. Bench eligibility respects slot types (FLEX, SuperFlex,
  WR/TE, etc.).

## Changing things

- Username lives at the top of the `<script>` block in `index.html`
  (`CONFIG.username`).
- Suggestion aggressiveness: `CONFIG.suggThreshold` (default 5 — lower
  means more suggestions).
- Yahoo league support would follow the same pattern as rankings: a fetcher
  script in the Action writes `data/yahoo.json`, and the site reads it.
  Deliberately left out for now.
