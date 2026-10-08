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
- **Course descriptions.** Once a week, the collector also reads each subject's page in the course catalog and writes `data/catalog.json` (description, credits, prerequisites, corequisites, and when the course is typically offered). Selecting a course title on the page opens these details in a pop-up. If the catalog cannot be read, the previous file is kept and the pop-up shows a short message with a catalog link.
- **Related word forms.** After the collector, the workflow runs `scripts/build-lemmas.js`, which uses the open source `wink-lemmatizer` package to write `data/lemmas.json`, a small table that maps words in the course titles and descriptions to their base forms. The page uses it so that a search for "woman" also finds "women", and "teaching" also finds "teach". If that step fails, the previous table is kept and search still works with exact words and word beginnings.
- **Seat history.** Each collection also adds one snapshot of open seats, by class number, to `data/history.json`. Fourteen days are kept. Seat trends on the page (for example "down 4 in the past week" and "Filling fast") appear after about three days of daily collection and grow more reliable as the history builds.
- The workflow commits the new files and republishes the site. The page shows the time of the latest collection. The daily commit also counts as repository activity, which keeps GitHub from pausing the schedule.
- If the catalog page or Class Search changes its layout, the collector stops instead of publishing bad data, the workflow shows a red failure, and the site keeps its last good version.
- Terms are detected automatically. New terms appear once Class Search posts their schedules, and finished terms drop off.
- Uploading a change to `index.html` or another file republishes the site without collecting new data. To collect right away, use **Actions, Refresh data and deploy site, Run workflow**.

## Using the page

- **Sorting.** Click any column heading to sort, and click again to reverse. Course and Elective category order the courses. The section headings (Section, Days and time, Location, Instructor, Seats) order the sections inside each course and then order the courses by their first section. Empty values always sort last. On narrow screens a Sort by menu does the same job.
- **Day and time filters.** Pick the weekdays you can attend and a window such as "starts no earlier than 1:00 PM" and "ends no later than 5:00 PM". The list keeps only sections whose meetings all fit. Sections with no set meeting time, such as online or TBD, always fit.
- **Search.** The search box matches course codes, titles, topics, instructors, class numbers and catalog description words. It ignores accents and capitalization, understands related word forms, and ranks courses whose title contains the whole phrase first. Matching description words are shown under the course title.
- **Shareable links.** The address in the browser changes with the term, search, filters and sort. **Copy link to this view** copies it, so an advisor can send a student exactly the list they were looking at. Links carry no personal information.
- **My plan.** **Add to my plan** on a section saves it in the visitor's own browser (nothing is sent anywhere). **View my plan** opens the list with credits per term, warnings for sections that overlap in time, and optional fields for a student name and advisor notes. **Print or save as PDF** produces a one page advising sheet. **Copy plan as text** produces a plain text version organized by term, with one labeled block per course, for pasting into an email.
- **Seat dots and category colors.** A green dot means plenty of seats, yellow means few left, red means closed. Each elective category has its own color. Class numbers appear next to each section and are the numbers to enter in MyPack.
- **Advisor approval courses.** `supplement.json` lists courses that are not on the catalog's elective lists but usually count with an advisor's approval (for example DS 492 Special Topics). They are collected like any other course and shown in the "Advisor approval (not on catalog list)" category. To add or remove one, edit that file (`code` and `title`) and commit. A course that the catalog already lists keeps its catalog category.

## The Refresh data button

The button asks a small relay (a free Cloudflare Worker, code in `worker/refresh-worker.js`) to start the same workflow that runs each morning, then checks every ten seconds until the new data is published, usually within two to three minutes. If a collection finished in the last 15 minutes, the relay declines and the page shows the data already published, so repeated clicks never send repeated requests to NC State.

The relay's address is the `REFRESH_URL` line near the top of the script in `index.html`. The relay holds a GitHub token that can only start workflows in this repository. The token has an expiry date: before it passes, create a new one and replace the `GITHUB_TOKEN` secret in the Cloudflare Worker settings. If `REFRESH_URL` is empty, the button only reloads the data the site has already published. When you open the page from your own computer, the relay refuses the request, so the button shows a short error and keeps the data already loaded.

Test the relay code with `node worker/refresh-worker.test.mjs`.

## Run it on your own computer

```
pip install -r requirements.txt
python scripts/collector.py          # refreshes data/
npm install --no-save wink-lemmatizer@3.0.4 && node scripts/build-lemmas.js   # optional: related word forms
python -m unittest discover -s test  # offline tests against saved pages
python -m http.server 8000           # then open http://localhost:8000
```

## Things to know

- Style: NC State brand colors (Wolfpack Red, Carmichael Aqua, Hunt Yellow, Bio-Indigo) and the Roboto type family, loaded from Google Fonts. The page uses no NC State logo.
- GitHub pauses scheduled workflows in a repository with no activity for 60 days. The daily data commit counts as activity. If the refresh ever stops, open the Actions tab and re-enable it.
- The collector makes about 120 requests per run, three at a time, with short pauses. Please keep the schedule at daily or slower.
- The wildcard entries in the catalog (WL 2xx to 4xx) are not expanded. The specific language courses the catalog lists are included.
- The CSV has one row per section (including its class number), plus one row for each course with no posted section in any term.
- This is an unofficial convenience tool. Class Search and the catalog are the sources of record, and advisors can confirm restrictions and approvals.
