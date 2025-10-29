import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
# DATA FILES
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "previous_jobs.json")
JOB_SOURCES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_sources.json")

# Load job sources from JSON
def load_job_sources(file_path=JOB_SOURCES_FILE):
    with open(file_path, "r") as f:
        data = json.load(f)
    return (
        data.get("ENDPOINTS", []),
        data.get("WORKDAY_SOURCES", []),
        data.get("THIRD_PARTY_SOURCES", []),
        data.get("FAILED_COMPANIES", []),
        data.get("LOTS_OF_WORK", [])
    )

ENDPOINTS, WORKDAY_SOURCES, THIRD_PARTY_SOURCES, FAILED_COMPANIES, LOTS_OF_WORK = load_job_sources()

# ------------------- JOB FETCHERS -------------------

def fetch_jobs(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()["result"]

def fetch_workday_jobs_generic(endpoint, headers, payload):
    r = requests.post(endpoint, headers=headers, json=payload)
    r.raise_for_status()
    return r.json().get("jobPostings", [])

def fetch_third_party_jobs(endpoint):
    r = requests.get(endpoint)
    r.raise_for_status()
    return r.json()

# ------------------- JOB STORAGE -------------------

def load_previous_jobs():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_jobs(jobs):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

# ------------------- EMAIL -------------------

def send_email(new_bamboo_jobs, new_workday_jobs, new_third_party_jobs, company_filter=None):
    load_dotenv()
    EMAIL_FROM = os.environ.get("EMAIL_FROM")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
    EMAIL_TO = EMAIL_FROM  # send to yourself

    print("Preparing to send email...")

    if not EMAIL_FROM or not EMAIL_PASSWORD:
        print("Email not configured. Skipping sending email.")
        # Still return jobs so frontend can display them
        return new_bamboo_jobs + new_workday_jobs + new_third_party_jobs

    lines = []
    all_new_jobs = []

    # Basic job formatting
    for job_list, label in [
        (new_bamboo_jobs, "BambooHR"),
        (new_workday_jobs, "Workday"),
        (new_third_party_jobs, "Third-Party")
    ]:
        if job_list:
            lines.append(f"{label} Jobs:")
            for job in job_list:
                title = job.get("jobOpeningName") or job.get("title") or "Unknown"
                url = job.get("url") or job.get("externalPath") or job.get("link") or ""
                source = job.get("source") or label
                lines.append(f"{title} @ {source} – {url}")
            lines.append("")
            all_new_jobs.extend(job_list)

    if not lines:
        print("No new jobs to email.")
        return all_new_jobs

    body = "\n\n".join(lines)
    msg = MIMEText(body)
    msg["Subject"] = "New Job Postings"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    print("Sending email...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        print("Email sent!")
    except Exception as e:
        print("Error sending email:", e)

    return all_new_jobs  # <-- return jobs to frontend    
# ------------------- SCRAPER MAIN FUNCTION -------------------

def scrape_jobs(company_filter=None):
    # BambooHR jobs
    all_new_bamboo_jobs = []
    for url in ENDPOINTS:
        jobs = fetch_jobs(url)
        for job in jobs:
            job["url"] = f"{url.rstrip('/list')}/careers/{job['id']}"
        all_new_bamboo_jobs.extend(jobs)

    # Workday jobs
    all_new_workday_jobs = []
    for src in WORKDAY_SOURCES:
        jobs = fetch_workday_jobs_generic(src["endpoint"], src["headers"], src["payload"])
        for job in jobs:
            job_id = job.get("bulletFields", [job.get("externalPath")])[0]
            job["id"] = job_id
            job["externalPath"] = f"{src['url_prefix']}{job.get('externalPath','')}" \
                if job.get("externalPath") and not job.get("externalPath","").startswith("http") \
                else job.get("externalPath")
            job["source"] = src["name"]
        all_new_workday_jobs.extend(jobs)

    # Third-party jobs
    all_new_third_party_jobs = []
    for src in THIRD_PARTY_SOURCES:
        jobs = fetch_third_party_jobs(src["endpoint"])
        for job in jobs:
            job["source"] = src["name"]
        all_new_third_party_jobs.extend(jobs)

    # Compare with previous jobs
    old_jobs = load_previous_jobs()
    old_ids = {job["id"] for job in old_jobs if "id" in job}

    new_bamboo_postings = [j for j in all_new_bamboo_jobs if j["id"] not in old_ids]
    new_workday_postings = [j for j in all_new_workday_jobs if j["id"] not in old_ids]
    new_third_party_postings = [j for j in all_new_third_party_jobs if j["id"] not in old_ids]

    # Save all jobs for next run
    save_jobs(all_new_bamboo_jobs + all_new_workday_jobs + all_new_third_party_jobs)

    # Send email (does not need to return jobs)
    send_email(new_bamboo_postings, new_workday_postings, new_third_party_postings, company_filter)

    # Return new jobs for frontend consumption
    all_new_jobs = new_bamboo_postings + new_workday_postings + new_third_party_postings

    # Apply company filter if requested
    if company_filter:
        all_new_jobs = [
            j for j in all_new_jobs
            if company_filter.lower() in (j.get('jobOpeningName') or j.get('title') or '').lower()
            or company_filter.lower() in (j.get('source') or '').lower()
        ]

    return all_new_jobs
