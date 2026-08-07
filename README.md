# AI Research Job Agent

A Python pipeline that scrapes academic job postings, applies rule-based
keyword filtering, and uses a locally-hosted LLM to semantically evaluate
each posting against a configurable research profile — surfacing a ranked
shortlist instead of requiring manual review of every listing.

## Features
- Playwright-based scraping of target career sites, including full job description retrieval (not just titles)
- Rule-based keyword pre-filtering to control screening volume/cost
- Local LLM semantic screening (Ollama) — judges disease-area and methodology fit against a structured researcher profile, not just keyword overlap
- Structured JSON output with reasoning + verdict (skip / maybe / apply / strong apply)
- Excel report generation with formatted, filterable output

## Technologies

- Python
- Playwright
- Pandas
- OpenPyXL
- Ollama
