# Design Studies Elective Finder

A searchable list of every elective on the NC State Design Studies BA, matched to the sections that NC State Class Search currently shows: meeting days and times, rooms, instructors, restrictions and open seats.

The site is one static page (`index.html`) that reads `data/electives.json`. A GitHub Action refreshes that file every morning and republishes the site.

## One-time setup

1. Create a **public** repository on GitHub and push the contents of this folder to the `main` branch.
2. In the repository, open **Settings, Pages**, and set **Source** to **GitHub Actions**.
3. Open the **Actions** tab, choose **Refresh data and deploy site**, and press **Run workflow**. The first run publishes the site.
4. Your site will be at `https://<your-username>.github.io/<repository-name>/`. The link also appears in the finished workflow run.

## How the refresh works

- **Every day at 10:17 UTC** (about 6 a.m. Eastern in summer and 5 a.m. in winter), the workflow runs `scripts/collector.py`. It reads the elective lists from the catalog page, asks Class Search for each subject in each posted term, and writes `data/electives.json` and `data/electives.csv`.
- The workflow commits the new files and republishes the site. The page shows the time of the latest collection. The daily commit also counts as repository activity, which keeps GitHub from pausing the schedule.
- If the catalog page or Class Search changes its layout, the collector stops instead of publishing bad data, the workflow shows a red failure, and the site keeps its last good version.
- Terms are detected automatically. New terms appear once Class Search posts their schedules, and finished terms drop off.
- Uploading a change to `index.html` or another file republishes the site without collecting new data. To collect right away, use **Actions, Refresh data and deploy site, Run workflow**.

## Using the page

- **Sorting.** Click any column heading to sort, and click again to reverse. Course and Elective category order the courses. The section headings (Section, Days and time, Location, Instructor, Seats) order the sections inside each course and then order the courses by their first section. Empty values always sort last. On narrow screens a Sort by menu does the same job.
- **Day and time filters.** Pick the weekdays you can attend and a window such as "starts no earlier than 1:00 PM" and "ends no later than 5:00 PM". The list keeps only sections whose meetings all fit. Sections with no set meeting time, such as online or TBD, always fit.
- **Advisor approval courses.** `supplement.json` lists courses that are not on the catalog's elective lists but usually count with an advisor's approval (for example DS 492 Special Topics). They are collected like any other course and shown in the "Advisor approval (not on catalog list)" category. To add or remove one, edit that file (`code` and `title`) and commit. A course that the catalog already lists keeps its catalog category.

## The Refresh data button

The button asks a small relay (a free Cloudflare Worker, code in `worker/refresh-worker.js`) to start the same workflow that runs each morning, then checks every ten seconds until the new data is published, usually within two to three minutes. If a collection finished in the last 15 minutes, the relay declines and the page shows the data already published, so repeated clicks never send repeated requests to NC State.

The relay's address is the `REFRESH_URL` line near the top of the script in `index.html`. The relay holds a GitHub token that can only start workflows in this repository. The token has an expiry date: before it passes, create a new one and replace the `GITHUB_TOKEN` secret in the Cloudflare Worker settings. If `REFRESH_URL` is empty, the button only reloads the data the site has already published. When you open the page from your own computer, the relay refuses the request, so the button shows a short error and keeps the data already loaded.

Test the relay code with `node worker/refresh-worker.test.mjs`.

## Run it on your own computer

```
pip install -r requirements.txt
python scripts/collector.py          # refreshes data/
python -m unittest discover -s test  # offline tests against saved pages
python -m http.server 8000           # then open http://localhost:8000
```

## Things to know

- Style: NC State brand colors (Wolfpack Red, Carmichael Aqua, Hunt Yellow, Bio-Indigo) and the Roboto type family, loaded from Google Fonts. The page uses no NC State logo.
- GitHub pauses scheduled workflows in a repository with no activity for 60 days. The daily data commit counts as activity. If the refresh ever stops, open the Actions tab and re-enable it.
- The collector makes about 120 requests per run, three at a time, with short pauses. Please keep the schedule at daily or slower.
- The wildcard entries in the catalog (WL 2xx to 4xx) are not expanded. The specific language courses the catalog lists are included.
- The CSV has one row per section, plus one row for each course with no posted section in any term.
- This is an unofficial convenience tool. Class Search and the catalog are the sources of record, and advisors can confirm restrictions and approvals.
