"""Website readers and report writer for the three-job-site monitor."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
import pandas as pd
from openpyxl import load_workbook

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from config import (
    HEADLESS,
    EXCLUDE_KEYWORDS,
    SCOPE_WEIGHTS,
    METHOD_WEIGHTS,
    TITLE_WEIGHTS,
    SITES,
    TIMEOUT_MS,
    TITLE_EXCLUDE_KEYWORDS,
    CONTEXT_EXCLUDE_PHRASES,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
HISTORY_PATH = DATA_DIR / "history.json"
OUTPUT_DIR = ROOT / "outputs"
REPORT_PATH = OUTPUT_DIR / "job_report.xlsx"
DEBUG_DIR = ROOT / "debug" 

# Keep Chromium with this project. This also works on computers where the
# system browser-cache folder is locked down.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "work" / "ms-playwright"))


@dataclass(frozen=True)
class Job:
    site: str
    title: str
    url: str
    context: str = ""

    @property
    def key(self) -> str:
        source = self.url or f"{self.site}|{self.title}|{self.context}"
        return hashlib.sha256(source.casefold().encode()).hexdigest()[:20]


    @property
    def is_excluded(self) -> bool:
        title_text = self.title.casefold()
        if any(kw.casefold() in title_text for kw in TITLE_EXCLUDE_KEYWORDS):
            return True

        context_text = self.context.casefold()
        if any(phrase.casefold() in context_text for phrase in CONTEXT_EXCLUDE_PHRASES):
            return True

        return False

    @property
    def score(self) -> int:
        if self.is_excluded:
            return 0

        text = f"{self.title} {self.context}".casefold()

        has_scope = any(kw.casefold() in text for kw in SCOPE_WEIGHTS)
        if not has_scope:
            return 0

        score = 0
        for kw, weight in {**SCOPE_WEIGHTS, **METHOD_WEIGHTS, **TITLE_WEIGHTS}.items():
            if kw.casefold() in text:
                score += weight

        return score
    

    @property
    def matched_keywords(self) -> str:

        if self.is_excluded:
           return ""

        text = f"{self.title} {self.context}".casefold()

        matches = []

        for keyword in {**SCOPE_WEIGHTS, **METHOD_WEIGHTS, **TITLE_WEIGHTS}:
          if keyword.casefold() in text:
            matches.append(keyword)

        return ", ".join(matches)


    @property
    def is_interesting(self) -> bool:
        return self.score >= 5


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_same_domain(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def wait_for_stable_anchors(page: Page, base_url: str, max_wait_ms: int = 20_000, poll_ms: int = 1_000) -> None:
    """Wait until the link count is unchanged twice; more reliable than `networkidle` on dynamic job sites.
    """
    page.wait_for_timeout(1_000)  # Allow time for the initial render
    elapsed = 0
    last_count = -1
    stable_hits = 0
    while elapsed < max_wait_ms:
        count = len(page_anchors(page, base_url))
        if count == last_count and count > 0:
            stable_hits += 1
            if stable_hits >= 2:  # Consider stable only after two identical checks
                return
        else:
            stable_hits = 0
        last_count = count
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    # Ignore timeout and continue scraping, though results may be incomplete

def dump_debug(page: Page, site: str) -> None:      
    DEBUG_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w]+", "_", site)
    page.screenshot(path=str(DEBUG_DIR / f"{safe}.png"), full_page=True)
    (DEBUG_DIR / f"{safe}.html").write_text(page.content(), encoding="utf-8")


def page_anchors(page: Page, base_url: str, allow_domains: set[str] | None = None) -> list[dict[str, str]]:
    rows = page.locator("a").evaluate_all(
        """anchors => anchors.map(a => {
            const parent = a.closest('tr, li, article, [role=listitem], .job, .card, .row') || a.parentElement;
            return {
              text: (a.innerText || a.textContent || '').trim(),
              href: a.href || '',
              context: (parent?.innerText || '').trim(),
              visible: !!(a.offsetWidth || a.offsetHeight || a.getClientRects().length)
            };
        })"""
    )
    allowed = allow_domains or {urlparse(base_url).netloc}
    result = []
    for row in rows:
        text = normalise(row["text"])
        href = row["href"]
        if row["visible"] and text and href and urlparse(href).netloc in allowed:
            result.append({"text": text, "href": href, "context": normalise(row["context"])})
    return result


def scrape_mahidol(page: Page, site: str, url: str) -> list[Job]:
    # This is the public Mahidol e-Recruitment detail-page pattern, including
    # Ramathibodi vacancies: .../user/job/view.php?id=12345
    jobs = []
    for a in page_anchors(page, url):
        if "/user/job/view.php" in a["href"] and a["text"]:
            jobs.append(Job(site, a["text"], a["href"], a["context"]))
    return deduplicate(jobs)


CAMH_API_TEMPLATE = (
    "https://iaemup.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    "?onlyData=true"
    "&expand=requisitionList.workLocation,requisitionList.otherWorkLocations,requisitionList.secondaryLocations,flexFieldsFacet.values,requisitionList.requisitionFlexFields"
    "&finder=findReqs;siteNumber=CX_1,facetsList=LOCATIONS%3BWORK_LOCATIONS%3BWORKPLACE_TYPES%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS,limit=25,offset={offset},sortBy=POSTING_DATES_DESC"
)


# 复用同一套 Oracle Recruiting Cloud API 结构的机构,加在这里就行,不用写新函数
ORACLE_SITES = {
    "CAMH": {
        "base_url": "https://iaemup.fa.ocs.oraclecloud.com",
        "site_number": "CX_1",
    },
    # "Siriraj": {...},  # 如果它也是 Oracle 系统的话
}

import re
from html import unescape

def strip_html(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_oracle_job_detail(page: Page, site: str, job_id: str) -> str:
    cfg = ORACLE_SITES[site]
    api_url = (
        f"{cfg['base_url']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
        f'?expand=all&onlyData=true&finder=ById;Id="{job_id}",siteNumber={cfg["site_number"]}'
    )
    response = page.request.get(api_url)
    if response.status != 200:
        return ""
    items = response.json().get("items", [])
    if not items:
        return ""
    req = items[0]  # 注意:这里直接就是 req,不是 items[0]["requisitionList"][0]
    parts = [req.get("ExternalDescriptionStr", ""),
             req.get("ExternalQualificationsStr", "")]
    return strip_html(" ".join(p for p in parts if p))


def scrape_camh(page: Page, site: str, url: str) -> list[Job]:
    page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    page.wait_for_timeout(1_500)

    jobs: list[Job] = []
    offset = 0
    limit = 25
    total = None

    while total is None or offset < total:
        api_url = CAMH_API_TEMPLATE.format(offset=offset)
        response = page.request.get(api_url)
        if response.status != 200:
            break
        data = response.json()
        items = data.get("items", [])
        if not items:
            break

        meta = items[0]
        total = meta.get("TotalJobsCount", 0)
        req_list = meta.get("requisitionList", [])
        if not req_list:
            break

        for req in req_list:
            job_id = req.get("Id")
            title = normalise(req.get("Title") or "")
            location = req.get("PrimaryLocation") or ""
            if not (job_id and title):
                continue

            job_url = f"{url.rsplit('/jobs', 1)[0]}/job/{job_id}"
            full_desc = get_oracle_job_detail(page, site, job_id)
            context = normalise(f"{location} {full_desc or req.get('ShortDescriptionStr', '')}")
            jobs.append(Job(site, title, job_url, context))

        offset += limit

    return deduplicate(jobs)


def scrape_siriraj(page: Page, site: str, url: str):
    jobs = []
    anchors = page_anchors(page, url, allow_domains={"www2.si.mahidol.ac.th", "muhr.mahidol.ac.th"})
    for a in anchors:
        if "/user/job/view.php" in a["href"] and a["text"]:
            jobs.append(Job(site, a["text"], a["href"], a["context"]))
    return deduplicate(jobs)


def scrape_generic(page: Page, site: str, url: str) -> list[Job]:
    """Small fallback for a site whose markup has changed."""
    ignore = {"apply", "search jobs", "view all jobs", "more", "read more"}
    jobs = []
    for a in page_anchors(page, url):
        text, href = a["text"], a["href"].casefold()
        if text.casefold() not in ignore and len(text) > 3 and "job" in href:
            jobs.append(Job(site, text, a["href"], a["context"]))
    return deduplicate(jobs)


def deduplicate(jobs: Iterable[Job]) -> list[Job]:
    seen: set[str] = set()
    result = []
    for job in jobs:
        if job.key not in seen:
            seen.add(job.key)
            result.append(job)
    return result


def scrape_site(browser: Browser, site: str, url: str) -> list[Job]:
    page = browser.new_page(viewport={"width": 1440, "height": 1100})

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        wait_for_stable_anchors(page, url)

        if site == "Mahidol / Ramathibodi":
            jobs = scrape_mahidol(page, site, url)

        elif site == "CAMH":
            jobs = scrape_camh(page, site, url)

        else:
            jobs = scrape_siriraj(page, site, url)

        if not jobs:                    
            dump_debug(page, site) 

        return jobs

    finally:
        page.close()


def scrape_all(playwright) -> tuple[dict[str, list[Job]], dict[str, str]]:
    browser = playwright.chromium.launch(headless=HEADLESS)
    all_jobs: dict[str, list[Job]] = {}
    errors: dict[str, str] = {}
    try:
        for site, url in SITES.items():
            try:
                all_jobs[site] = scrape_site(browser, site, url)
            except Exception as exc:  # Keep the other sites running if one fails.
                all_jobs[site] = []
                errors[site] = f"{type(exc).__name__}: {normalise(str(exc))}"
    finally:
        browser.close()
    return all_jobs, errors


def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {"jobs": {}, "first_run": True}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError(f"History file is not valid JSON: {HISTORY_PATH}")


def save_history(all_jobs: dict[str, list[Job]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": {site: [asdict(job) for job in jobs] for site, jobs in all_jobs.items()},
    }
    HISTORY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def new_jobs(all_jobs: dict[str, list[Job]], previous: dict) -> dict[str, list[Job]]:
    previous_keys = {
        Job(**job).key
        for jobs in previous.get("jobs", {}).values()
        for job in jobs
    }
    return {site: [job for job in jobs if job.key not in previous_keys] for site, jobs in all_jobs.items()}

def write_report(
    all_jobs: dict[str, list[Job]],
    additions: dict[str, list[Job]],
    errors: dict[str, str],
    first_run: bool,
):

    print("DEBUG all_jobs:")
    for site, jobs in all_jobs.items():
        print(site, len(jobs))

    OUTPUT_DIR.mkdir(exist_ok=True)

    rows = []

    for site in SITES:
        for job in all_jobs[site]:
            if job.is_excluded:
                continue
            rows.append(
                {
                    "Site": job.site,
                    "Title": job.title,
                    "Score": job.score,
                    "Matched keywords": job.matched_keywords,
                    "URL": job.url,
                    "Context": job.context,
                }
            )

    df = pd.DataFrame(rows)

    df.to_excel(
    REPORT_PATH,
    index=False
)

# Improve Excel readability
    wb = load_workbook(REPORT_PATH)
    ws = wb.active

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"

    wb.save(REPORT_PATH)
