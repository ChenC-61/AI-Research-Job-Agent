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

# These jobs are usually irrelevant for your career goal.

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


# title 用原来那套完整关键词表就够(标题本身足够说明岗位性质)
TITLE_EXCLUDE_KEYWORDS = EXCLUDE_KEYWORDS

# 完整JD正文只用更长、更具体的短语,避免命中"Reporting to the Manager"这类模板句
CONTEXT_EXCLUDE_PHRASES = [
    "registered nurse",
    "pharmacy technician",
    "security guard",
    "human resources officer",
    "front desk",
    "patient service representative",

     # 本次新增
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
# Scope keywords —— 你的硬约束,决定"值不值得考虑"
# 单独命中就该有相当分量,因为这是 non-negotiable criteria
# ==============================
SCOPE_WEIGHTS = {
    "psychiatry": 5,
    "psychiatric": 5,
    "mental health": 4,        # 权重比psychiatry低一点,因为它更容易在机构介绍里泛化出现
    "precision psychiatry": 6,
    "schizophrenia": 5,
    "bipolar": 5,
    "adhd": 5,
    "autism": 5,
    "neurodevelopmental": 5,
}

# ==============================
# Method keywords —— 你的技能匹配,证明"这活儿你能干、你想干"
# 单独出现分量不够,要配合scope才有意义
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
# Title keywords —— 最弱的信号
# researcher/postdoc/scientist 任何学科都能叫,单独出现几乎没有筛选力
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


# ==============================================================
# 追加到你现有 config.py 末尾
# ==============================================================

# ------------------------------------------------------------
# LLM 语义复核（Ollama 本地模型）
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

# 你的研究画像，会被拼进 LLM prompt 里。
# 改这里就能调整筛选口径，不用碰 llm_screener.py 的代码。
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
