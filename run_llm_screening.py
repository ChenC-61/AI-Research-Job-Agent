"""
llm_screener.py

Semantic screening of job postings using a local Ollama model.
Sits AFTER scraping (which now pulls full JD text), BEFORE producing
the final report.

Design notes (this version):

1. Boilerplate stripping (NEW): full JDs now include institution
   self-description, compensation/benefits blocks, DEI statements, and
   (for bilingual sites like CAMH) a duplicate French version of the same
   text. None of that helps the LLM judge fit -- it only adds tokens,
   which is exactly what was causing ~1 min/job and memory pressure on a
   16GB Mac even when only screening short summaries. strip_boilerplate()
   removes it BEFORE the text is sent to Ollama.

2. This does NOT depend on the scraper's keyword Score for its judgment.
   The keyword score (from job_monitor.py) is a cheap, coarse first-pass
   filter for VOLUME (how many postings even reach this stage); the LLM's
   verdict is an independent judgment based on actual JD content. The
   optional keyword_prefilter_threshold in config still exists purely to
   control how many jobs get LLM-screened at all (cost control), not to
   influence the verdict itself.

3. Verdict is a 4-option enum (skip/maybe/apply/strong_apply), not a
   numeric score. A prior version used a 0-10 fit_score, and the model
   did not reliably derive that number from its own stated reasoning
   (e.g. reason="does not align with computational psychiatry" +
   fit_score=10). Keeping the closed-enum design deliberately -- do not
   reintroduce a free-form numeric score.

Requires: requests, pandas, openpyxl.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta

import requests
import pandas as pd

from config import (
    LLM_SCREENING,
    RESEARCHER_PROFILE,
    TITLE_EXCLUDE_KEYWORDS,
    CONTEXT_EXCLUDE_PHRASES,
)


# ------------------------------------------------------------
# Boilerplate stripping
# ------------------------------------------------------------
# Everything from the first matching marker onward is dropped. These
# markers are deliberately generic (not CAMH-specific) so this holds up
# as more institutions get added. Add new markers here as you spot more
# boilerplate patterns from other sites.
BOILERPLATE_MARKERS = [
    # compensation / benefits
    "compensation & benefits",
    "compensation and benefits",
    "total rewards",
    "salary range",
    "hiring range",
    "pension plan",
    # DEI / equal opportunity / application logistics boilerplate
    "equity, diversity, and inclusion",
    "equity, diversity and inclusion",
    "we are committed to diversity",
    "accommodations during the application",
    "accommodation during the recruitment",
    "equal opportunity employer",
    "thank you to all who apply",
    "only those selected for an interview will be contacted",
    "land acknowledg",  # covers "acknowledgment" / "acknowledgement"
]

# Rough French-detection via stopword density. Deliberately simple (no
# extra dependency like langdetect) -- this only needs to catch "this
# sentence is basically French", not do real language ID.
_FRENCH_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "et", "à", "un", "une", "pour",
    "avec", "est", "dans", "sur", "qui", "que", "vous", "nous", "votre",
    "notre", "nos", "leurs", "ces", "cette", "sont", "aux", "au",
}
_WORD_RE = re.compile(r"[a-zàâçéèêëîïôûùüÿñæœ]+", re.IGNORECASE)


def _looks_french(sentence: str) -> bool:
    words = _WORD_RE.findall(sentence.lower())
    if len(words) < 8:
        return False
    hits = sum(1 for w in words if w in _FRENCH_STOPWORDS)
    return (hits / len(words)) > 0.15


def _drop_french_sentences(text: str) -> str:
    # NOTE: the scraper's strip_html() collapses all whitespace to single
    # spaces, so paragraph breaks are already gone by the time this runs.
    # Split on sentence boundaries instead of paragraphs for that reason.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if not _looks_french(s)]
    return " ".join(kept)


def strip_boilerplate(text: str) -> str:
    """Remove institution boilerplate, benefits/DEI blocks, and duplicate
    French text from a full JD before it's sent to the LLM. Safe to call
    on already-short text (summary-only jobs) -- it's a no-op if none of
    the markers are present."""
    if not text:
        return text

    lower = text.lower()
    cut_at = len(text)
    for marker in BOILERPLATE_MARKERS:
        idx = lower.find(marker)
        if idx != -1:
            cut_at = min(cut_at, idx)
    text = text[:cut_at]

    text = _drop_french_sentences(text)
    return text.strip()


# ------------------------------------------------------------
# JSON schema passed to Ollama's `format` param.
# ------------------------------------------------------------
# IMPORTANT: field order matters. Structured/constrained generation fills
# fields in the order they appear in the schema, so "reason" comes BEFORE
# "verdict" -- this forces the model to reason first and derive the
# verdict from that reasoning, instead of blurting a verdict and
# rationalizing it after.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "verdict": {
            "type": "string",
            "enum": ["skip", "maybe", "apply", "strong_apply"],
        },
    },
    "required": ["reason", "verdict"],
}

VERDICT_TO_TIER = {
    "skip": "Skip",
    "maybe": "Maybe",
    "apply": "Apply",
    "strong_apply": "Strong Apply",
}

# Bump this whenever RESPONSE_SCHEMA, SYSTEM_PROMPT, or strip_boilerplate
# change meaningfully -- forces a cache miss (real LLM call) after an
# upgrade instead of silently serving results computed under old rules.
SCHEMA_VERSION = "v3-boilerplate-stripped"


def _cache_path(cfg: dict) -> str:
    folder = cfg.get("cache_folder", ".cache")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "llm_screening_cache.json")


def _job_hash(title: str, context: str, cfg: dict) -> str:
    model = cfg.get("model", "")
    raw = f"{SCHEMA_VERSION}||{model}||{title.strip()}||{(context or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cache(cfg: dict) -> dict:
    if not cfg.get("enable_cache", True):
        return {}
    path = _cache_path(cfg)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict, cfg: dict) -> None:
    if not cfg.get("enable_cache", True):
        return
    with open(_cache_path(cfg), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _cache_entry_valid(entry: dict, cfg: dict) -> bool:
    expire_days = cfg.get("cache_expire_days", 30)
    try:
        ts = datetime.fromisoformat(entry["_cached_at"])
    except (KeyError, ValueError):
        return False
    if datetime.now() - ts >= timedelta(days=expire_days):
        return False
    if entry.get("verdict") not in VERDICT_TO_TIER:
        return False
    return True


# ------------------------------------------------------------
# Prompt
# ------------------------------------------------------------
# Deliberately generic / structural. It does NOT hardcode disease names,
# methodologies, or position titles -- those all live in RESEARCHER_PROFILE
# (config.py), which is the single source of truth and gets interpolated
# into the user prompt at call time. This avoids the rubric silently going
# stale if you edit the profile but forget to also edit this file.
SYSTEM_PROMPT = """You are screening job postings for a researcher. \
You will be given the researcher's profile and a single job posting \
(boilerplate such as institutional branding, benefits, and DEI statements \
has already been stripped out -- what remains is the actual role content).

The profile below is organized into sections such as "Preferred \
positions", "Highly preferred research topics", "Preferred \
methodologies", "Less preferred", and "Not suitable" -- use these \
categories as the source of truth for what counts as a fit. Do NOT rely \
on keyword overlap alone -- judge from the actual duties described. A \
title can look unrelated but be a strong fit (e.g. a cohort-study analyst \
role that touches the profile's target disease area), and a title can \
look related but be a weak fit (e.g. a role in the "Not suitable" \
category despite a related-sounding title).

Disease-area / domain fit against the profile's preferred topics is a \
hard requirement -- a role outside that domain, or matching the "Not \
suitable" section, cannot be "apply" or "strong_apply" regardless of how \
strong the methodology match is. Within the domain, how well the role's \
methodology matches the profile's "Preferred methodologies" section is \
what separates "maybe" from "apply"/"strong_apply".

First write one concise sentence of reasoning that weighs the role's \
actual duties against the profile's preferred/less-preferred/not-suitable \
categories. Then choose verdict using this rubric, and make sure the \
verdict matches what you just wrote -- if your reasoning says the role \
matches "Not suitable" or is out of domain, the verdict must be "skip", \
never "strong_apply":

skip         = matches the profile's "Not suitable" section, OR is \
               outside the profile's target disease area / research \
               domain entirely.
maybe        = right domain, but methodology falls in "Less preferred" \
               (e.g. no computational/quantitative component), or the \
               role is too broad/administrative to confirm a genuine \
               research or modeling component.
apply        = right domain, genuine research or data component matching \
               the profile's interests, but not a strong methodology \
               match to "Preferred methodologies" (e.g. adjacent \
               computational role, not the core modeling work described).
strong_apply = right domain AND core duties clearly match the profile's \
               "Preferred methodologies" and "Highly preferred research \
               topics" -- this is the kind of role the profile describes \
               itself as seeking.

Respond only with the requested JSON."""


def build_user_prompt(title: str, context: str, profile: str) -> str:
    context = strip_boilerplate((context or "").strip())
    return f"""RESEARCHER PROFILE:
{profile.strip()}

JOB POSTING:
Title: {title.strip()}
Description: {context if context else "(no additional context available, judge from title alone)"}

Judge fit and whether to apply. Respond with JSON only."""


def query_ollama(title: str, context: str, profile: str, cfg: dict) -> dict:
    """Call local Ollama chat endpoint with structured JSON output.
    Returns {verdict, reason} or an error dict.
    verdict is one of "skip" / "maybe" / "apply" / "strong_apply"."""
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(title, context, profile)},
        ],
        "format": RESPONSE_SCHEMA,
        "stream": False,
        "options": {
            # These are just reasonable starting defaults, not a vendor
            # recommendation for any specific model -- tune in
            # LLM_SCREENING (config.py) for whatever model you're
            # actually running.
            "temperature": cfg.get("temperature", 1.0),
            "top_k": cfg.get("top_k", 64),
            "top_p": cfg.get("top_p", 0.95),
            "min_p": cfg.get("min_p", 0.0),
            "num_ctx": cfg.get("num_ctx", 8192),
            "num_predict": cfg.get("num_predict", 1024),
        },
    }

    last_err = None
    for attempt in range(cfg.get("max_retries", 2) + 1):
        try:
            resp = requests.post(
                cfg["ollama_url"], json=payload, timeout=cfg.get("timeout_s", 60)
            )
            resp.raise_for_status()
            raw_content = resp.json()["message"]["content"]
            parsed = json.loads(raw_content)

            if not all(k in parsed for k in ("reason", "verdict")):
                raise ValueError(f"missing keys in LLM response: {parsed}")
            if parsed["verdict"] not in VERDICT_TO_TIER:
                raise ValueError(f"unexpected verdict value: {parsed['verdict']!r}")

            return parsed

        except Exception as e:  # noqa: BLE001 - want to retry on any failure
            last_err = e
            time.sleep(1.5 * (attempt + 1))

    return {
        "verdict": None,
        "reason": f"LLM call failed after retries: {last_err}",
    }


def _excluded_by_keyword(title: str, title_exclude_keywords):
    """Cheap hard filter run BEFORE the LLM call. Title-only match --
    a psychiatry research job's description can mention "assistant" or
    "administrative support" in passing without the role itself being
    administrative, so context is deliberately not checked here."""
    title_lower = title.lower()
    for kw in title_exclude_keywords:
        if kw.lower() in title_lower:
            return kw
    return None


def _excluded_by_context_phrase(context: str, context_exclude_phrases):
    """Same idea as _excluded_by_keyword but for the longer, more specific
    phrases in CONTEXT_EXCLUDE_PHRASES (config.py) -- these are checked
    against the full JD text, mirroring the same filter job_monitor.py
    applies at the keyword-scoring stage, so a job that's already excluded
    there doesn't also cost an LLM call here."""
    context_lower = (context or "").lower()
    for phrase in context_exclude_phrases:
        if phrase.lower() in context_lower:
            return phrase
    return None


def screen_jobs(
    df: pd.DataFrame,
    title_col: str = "Title",
    context_col: str = "Context",
    keyword_score_col: str = "Score",
    cfg: dict = None,
    profile: str = None,
    title_exclude_keywords=None,
    context_exclude_phrases=None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run LLM screening over a DataFrame of scraped jobs.

    Adds columns: LLM_Tier, LLM_Reason, LLM_Relevant.
    LLM_Tier is one of "Strong Apply" / "Apply" / "Maybe" / "Skip", read
    directly from the model's "verdict" field -- there is no numeric score
    being translated into a tier.

    Filters run before any LLM call, in order (all zero LLM cost, all
    volume/cost filters -- none of them influence the verdict for jobs
    that do reach the LLM):
      1. Title exclude-keyword hard filter (TITLE_EXCLUDE_KEYWORDS in
         config): title-only match, e.g. "nurse", "therapist".
      2. Context exclude-phrase filter (CONTEXT_EXCLUDE_PHRASES in
         config): full-JD-text match against longer, more specific
         phrases, mirroring the same filter job_monitor.py applies at the
         keyword-scoring stage.
      3. Optional keyword_prefilter_threshold (cfg): jobs below this
         keyword Score are skipped entirely (0 = screen everything that
         passes filters 1-2).

    Before each LLM call, the job's context is run through
    strip_boilerplate() to remove institutional branding, benefits/DEI
    blocks, and duplicate French text -- this is what actually saves time
    and memory versus screening the raw full JD.

    Results are cached (keyed on title+stripped-context+model+schema hash)
    when cfg['enable_cache'] is True.
    """
    cfg = cfg or LLM_SCREENING
    profile = profile or RESEARCHER_PROFILE
    title_exclude_keywords = (
        title_exclude_keywords if title_exclude_keywords is not None else TITLE_EXCLUDE_KEYWORDS
    )
    context_exclude_phrases = (
        context_exclude_phrases if context_exclude_phrases is not None else CONTEXT_EXCLUDE_PHRASES
    )

    if not cfg.get("enabled", True):
        if verbose:
            print("LLM screening disabled in config; skipping.")
        return df

    threshold = cfg.get("keyword_prefilter_threshold", 0)
    cache = _load_cache(cfg)
    cache_hits, cache_misses, excluded_count = 0, 0, 0

    reason_col, tier_col = [], []

    total = len(df)
    for i, row in df.iterrows():
        title = str(row.get(title_col, ""))
        raw_context = str(row.get(context_col, "")) if context_col in df.columns else ""
        kw_score = row.get(keyword_score_col, 0) if keyword_score_col in df.columns else 0

        matched_exclude = _excluded_by_keyword(title, title_exclude_keywords)
        if matched_exclude:
            excluded_count += 1
            reason_col.append(f"excluded by keyword filter: title contains '{matched_exclude}'")
            tier_col.append("Skip")
            if verbose:
                print(f"[{i + 1}/{total}] excluded (title keyword '{matched_exclude}'): {title[:60]}")
            continue

        matched_phrase = _excluded_by_context_phrase(raw_context, context_exclude_phrases)
        if matched_phrase:
            excluded_count += 1
            reason_col.append(f"excluded by keyword filter: JD contains '{matched_phrase}'")
            tier_col.append("Skip")
            if verbose:
                print(f"[{i + 1}/{total}] excluded (context phrase '{matched_phrase}'): {title[:60]}")
            continue

        if threshold and kw_score is not None and kw_score < threshold:
            reason_col.append("skipped (below keyword pre-filter threshold)")
            tier_col.append("")
            continue

        stripped_context = strip_boilerplate(raw_context)
        job_key = _job_hash(title, stripped_context, cfg)
        cached_entry = cache.get(job_key)

        if cached_entry and _cache_entry_valid(cached_entry, cfg):
            result = cached_entry
            cache_hits += 1
            if verbose:
                print(f"[{i + 1}/{total}] cache hit: {title[:70]}")
        else:
            if verbose:
                before, after = len(raw_context), len(stripped_context)
                print(
                    f"[{i + 1}/{total}] LLM screening ({before}->{after} chars): {title[:60]}"
                )
            result = query_ollama(title, stripped_context, profile, cfg)
            result["_cached_at"] = datetime.now().isoformat()
            cache[job_key] = result
            cache_misses += 1

        reason_col.append(result["reason"])
        tier_col.append(VERDICT_TO_TIER.get(result.get("verdict"), ""))

    _save_cache(cache, cfg)
    if verbose:
        print(f"\nExcluded by title keyword filter (no LLM call): {excluded_count}")
        if cfg.get("enable_cache", True):
            print(f"Cache: {cache_hits} hits, {cache_misses} new LLM calls.")

    out = df.copy()
    out["LLM_Reason"] = reason_col
    out["LLM_Tier"] = tier_col
    out["LLM_Relevant"] = out["LLM_Tier"].isin(["Maybe", "Apply", "Strong Apply"])

    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run LLM semantic screening on a scraped jobs Excel file."
    )
    parser.add_argument("input_xlsx", help="Path to existing scraped jobs Excel file")
    parser.add_argument(
        "-o", "--output", help="Output path (default: overwrite input with _llm suffix)"
    )
    parser.add_argument("--title-col", default="Title")
    parser.add_argument("--context-col", default="Context")
    parser.add_argument("--score-col", default="Score")
    args = parser.parse_args()

    df_in = pd.read_excel(args.input_xlsx)
    df_out = screen_jobs(
        df_in,
        title_col=args.title_col,
        context_col=args.context_col,
        keyword_score_col=args.score_col,
    )

    out_path = args.output or args.input_xlsx.replace(".xlsx", "_llm.xlsx")
    df_out.to_excel(out_path, index=False)
    print(f"\nDone. Wrote {len(df_out)} rows -> {out_path}")

    tier_counts = df_out["LLM_Tier"].value_counts()
    for tier in ["Strong Apply", "Apply", "Maybe", "Skip"]:
        print(f"  {tier}: {tier_counts.get(tier, 0)}")
