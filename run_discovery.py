"""Run the job monitor: python main.py"""

import os
from pathlib import Path

# This must be set before Playwright launches Chromium.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parent / "work" / "ms-playwright"))

from playwright.sync_api import sync_playwright

from job_monitor import (
    Job,
    REPORT_PATH,
    load_history,
    new_jobs,
    save_history,
    scrape_all,
    write_report,
)


def main() -> None:
    previous = load_history()
    print("Checking job sources...")
    with sync_playwright() as playwright:
        all_jobs, errors = scrape_all(playwright)

    additions = new_jobs(all_jobs, previous)
    first_run = previous.get("first_run", False)
    write_report(all_jobs, additions, errors, first_run)

    # Do not overwrite history for a failed website; otherwise a temporary
    # outage would make every vacancy look new on the following run.
    old_jobs = previous.get("jobs", {})
    merged = {
        site: all_jobs[site] if site not in errors else [Job(**job) for job in old_jobs.get(site, [])]
        for site in all_jobs
    }
    save_history(merged)

    print(f"Report written to: {REPORT_PATH}")
    for site, jobs in all_jobs.items():
        suffix = f" (could not read: {errors[site]})" if site in errors else ""
        print(f"- {site}: {len(jobs)} openings, {len(additions[site])} new{suffix}")


if __name__ == "__main__":
    main()
