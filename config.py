# ==============================
# Job Monitor Configuration
# ==============================

# Target job websites
SITES = {
    "CAMH": "https://iaemup.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CAMH/jobs",
    #"Siriraj": "https://www2.si.mahidol.ac.th/th/division/hr/jobs/template/index.php",
    #"Mahidol / Ramathibodi": "https://muhr.mahidol.ac.th/E-Recruitment/index.php",
}


# ==============================
# Personal job profile
# ==============================

# High relevance keywords.
# Jobs containing these terms will receive higher scores.

INTEREST_KEYWORDS = [

    # Psychiatry / mental health
    "psychiatry",
    "psychiatric",
    "mental health",
    "behavioral",
    #"จิตเวช",
    #"สุขภาพจิต",
    #"จิตวิทยา",

    # AI / Machine learning / Data science
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "data science",
    "data scientist",
    "clinical data",
    "digital health",
    "ai",

    # Precision medicine / omics
    "precision medicine",
    "precision psychiatry",
    "genomics",
    "genomic",
    "multi-omics",
    "omics",
    "bioinformatics",
    "computational",

    # Research positions
    "research scientist",
    "research fellow",
    "research associate",
    "postdoctoral",
    "postdoc",
    "scientist",
    "researcher",

    # Thai research keywords
    #"วิจัย",
    #"ปัญญาประดิษฐ์",
]


# ==============================
# Keywords to exclude
# ==============================

# These jobs are usually irrelevant for the career goal.

EXCLUDE_KEYWORDS = [

    # Administrative
    "administration",
    "administrative",
    "finance",
    "accounting",
    "human resource",
    "hr officer",
    "director",
    "worker",
    "engineer",
    "officer",
    "clerk",

    # Hospital support jobs
    "nurse",
    "nursing",
    "pharmacist",
    "technician",
    "security",
    "driver",
    "maintenance",
    "manager",

    # Non-research clinical jobs
    "clinical assistant",
    "patient service",
    "therapist",
    "psychologist",
    "counsellor",
    "counselor",
]


# title exclude keywords
TITLE_EXCLUDE_KEYWORDS = EXCLUDE_KEYWORDS

# Use longer, more specific phrases from the full job description text, and avoid matching generic boilerplate such as “Reporting to the Manager.”
CONTEXT_EXCLUDE_PHRASES = [
    "registered nurse",
    "pharmacy technician",
    "security guard",
    "human resources officer",
    "front desk",
    "patient service representative",

     # Newly added
    "legal assistant",
    "legal counsel",
    "legal counsel",
    "department secretary",
    "community partnerships coordinator",
    "organizational development",
    "engagement coordinator",
    "co-facilitator",
    "community partnerships coordinator",
    "engagement coordinator",
]


# ==============================
# Scope keywords 
# ==============================
SCOPE_WEIGHTS = {
    "psychiatry": 5,
    "psychiatric": 5,
    "mental health": 4,        
    "precision psychiatry": 6,
    "schizophrenia": 5,
    "bipolar": 5,
    "adhd": 5,
    "autism": 5,
    "neurodevelopmental": 5,
}

# ==============================
# Method keywords 
# ==============================
METHOD_WEIGHTS = {
    "machine learning": 3,
    "artificial intelligence": 2,
    "data science": 2,
    "data scientist": 2,
    "clinical data": 2,
    "computational": 2,
    "bioinformatics": 2,
    "genomics": 2,
    "multi-omics": 2,
    "precision medicine": 2,
    "digital health": 2,
}

# ==============================
# Title keywords 
# ==============================
TITLE_WEIGHTS = {
    "research scientist": 1,
    "research fellow": 1,
    "research associate": 1,
    "postdoctoral": 1,
    "postdoc": 1,
    "researcher": 1,
    "scientist": 1,
}


# ==============================
# Browser settings
# ==============================

# False = show browser window during scraping
# True = background mode

HEADLESS = True

TIMEOUT_MS = 45_000


# ------------------------------------------------------------
# LLM-based semantic review using a local Ollama model
# ------------------------------------------------------------

LLM_SCREENING = {

    # Master switch
    "enabled": True,

    # Ollama model
    "model": "gemma4:e4b",

    # Ollama API
    "ollama_url": "http://localhost:11434/api/chat",

    # ----------------------------------------------------------
    # Keyword pre-filter
    # ----------------------------------------------------------
    # Only jobs with keyword score >= threshold are sent to the LLM.
    # Set to 0 to analyse every scraped job.
    "keyword_prefilter_threshold": 0,

    # ----------------------------------------------------------
    # LLM runtime
    # ----------------------------------------------------------
    "timeout_s": 60,
    "max_retries": 2,

    # Official Gemma 4 sampling
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 64,

    # ----------------------------------------------------------
    # Recommendation thresholds
    # ----------------------------------------------------------
    "strong_apply_threshold": 8,
    "apply_threshold": 5,
    "maybe_threshold": 2,

    # ----------------------------------------------------------
    # Cache
    # Avoid re-evaluating unchanged jobs
    # ----------------------------------------------------------
    "enable_cache": True,
    "cache_folder": ".cache",
    "cache_expire_days": 30,

}

# Research profile incorporated into the LLM prompt.
# Modify this configuration to adjust the screening criteria without changing llm_screener.py.
RESEARCHER_PROFILE = """
You are evaluating research-oriented job postings for the following researcher.

Profile
-------
Researcher specializing in structural-infromed representation of cognition, computational psychiatry, and clinical prediction modeling.

Research expertise
------------------
- Machine learning for clinical prediction
- Statistical modeling
- Risk prediction
- Prognostic modeling
- Treatment response prediction
- Remission and relapse prediction
- Longitudinal cohort analysis
- Bayesian statistical modeling
- Biostatistics
- R and Python programming

Biomedical background
---------------------
- Psychiatry
- Schizophrenia
- Psychosis
- Major depressive disorder (MDD)
- Precision psychiatry
- Multi-omics
- Bioinformatics
- Proteomics

Preferred positions
-------------------
- Postdoctoral Fellow
- Research Fellow
- Research Scientist
- Research Associate
- Scientist
- Data scientist working on clinical research

Highly preferred research topics
--------------------------------
- Psychiatric disorders
- Mental health
- Neurodevelopmental disorders
- Clinical outcome prediction
- Risk prediction
- Prognostic modeling
- Precision medicine
- Precision psychiatry
- Machine learning in healthcare
- AI for medicine
- Clinical data science
- Cohort studies
- Longitudinal studies
- Translational research

Preferred methodologies
-----------------------
- Machine learning
- Statistical prediction models
- Survival analysis
- Bayesian methods
- Clinical epidemiology
- Explainable AI
- Data science
- Bioinformatics
- Clinical informatics

Less preferred
--------------
- General neuroscience without computational modeling
- Basic biology without quantitative analysis
- Pure software engineering

Not suitable
------------
- Wet-lab only research
- Animal experiments
- Cell culture
- Molecular biology without computational work
- Hospital administration
- Finance
- Human resources
- Nursing
- Pharmacy
- Clinical service positions
- IT infrastructure
- Technical support

Evaluation objective
--------------------
Evaluate whether the job is a good career fit based on research direction,
methodology, disease area, and long-term career development,
rather than simply matching keywords.
"""
