# Design Studies Elective Finder

A searchable list of every elective on the NC State Design Studies BA, matched to the sections that NC State Class Search currently shows: meeting days and times, rooms, instructors, restrictions and open seats.

The site is a single static page (`index.html`) that reads `data/electives.json`. A GitHub Action refreshes that file every morning and republishes the site.

## One-time setup

1. Create a **public** repository on GitHub and push the contents of this folder to the `main` branch.
2. In the repository, open **Settings, Pages**, and set **Source** to **GitHub Actions**.
3. Open the **Actions** tab, choose **Refresh data and deploy site**, and press **Run workflow**. The first run publishes the site.
4. Your site will be at `https://<your-username>.github.io/<repository-name>/`. The link also appears in the finished workflow run.

The repository ships with a snapshot taken on October 7, 2026, so the site works as soon as step 3 finishes. The first scheduled run replaces it with fresh data and full restriction notes.

## How the refresh works

- **Every day at about 6 a.m. Eastern**, the workflow runs `scripts/collector.py`. It reads the elective lists from the catalog page, asks Class Search for each subject in each posted term, and writes `data/electives.json` and `data/electives.csv`.
- The workflow commits the new files and republishes the site. The page shows the time of the latest collection, so a visitor can see that the data is current. The daily commit also counts as repository activity, which keeps GitHub from pausing the schedule.
- If the catalog page or Class Search changes its layout, the collector stops instead of publishing bad data, the workflow shows a red failure, and the site keeps its last good version.
- Terms are detected automatically. New terms appear once Class Search posts their schedules, and finished terms drop off.

## Sorting

Click any column heading to sort by it, and click again to reverse the order. The Course and Elective category headings order the courses. The section headings (Section, Days and time, Location, Instructor, Seats) order the sections inside each course and then order the courses by their first section. Empty values always sort last. On narrow screens, where the heading row is hidden, a Sort by menu does the same job.

## Day and time filters

Under "Filter by day and time" on the page, pick the weekdays you can attend and a window such as "starts no earlier than 1:00 PM" and "ends no later than 5:00 PM". The list then shows only sections whose meetings all fit. Sections with no set meeting time, such as online or TBD, always fit. The filters work on the data already loaded, so they need no extra files or settings.

## Courses that need advisor approval

`supplement.json` lists courses that are not on the catalog's elective lists but usually count with an advisor's approval (for example DS 492 Special Topics). They are collected like any other course and tagged "Advisor approval (not on catalog list)" in the Elective category column. To add or remove one, edit the list in that file (`code` and `title`) and commit; the site refreshes on the next run. A course that the catalog already lists keeps its catalog tags.

## The Reload data button

**Reload data** fetches the newest published `data/electives.json` and redraws the list without losing your filters. It does not contact NC State, because browsers block pages from reading Class Search directly.

**Refresh from NC State** appears when the site is served from `github.io`. It opens the workflow page, where a maintainer presses **Run workflow** to collect new data right away. The run takes about two minutes. After it finishes, press Reload data. A one-click refresh for every visitor would need a server or a stored access token, which a public static page cannot hold safely, so the button leads to GitHub instead.

## Run it on your own computer

```
pip install -r requirements.txt
python scripts/collector.py          # refreshes data/
python -m unittest discover -s test  # offline tests against saved pages
python -m http.server 8000           # then open http://localhost:8000
```

## Things to know

- GitHub pauses scheduled workflows in a repository with no activity for 60 days. The daily data commit counts as activity. If the refresh ever stops, open the Actions tab and re-enable it.
- The collector makes about 120 requests per run, three at a time, with short pauses. Please keep the schedule at daily or slower.
- The wildcard entries in the catalog (WL 2xx to 4xx) are not expanded. The specific language courses the catalog lists are included.
- This is an unofficial convenience tool. Class Search and the catalog are the sources of record, and advisors can confirm restrictions and approvals.
# design-studies-electives
