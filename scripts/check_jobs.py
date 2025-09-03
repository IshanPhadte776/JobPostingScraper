# Job Posting Scraper Script
# Fetches job postings from BambooHR and Workday endpoints, checks for new jobs, and sends email notifications.
# Supports local .env secrets and GitHub Actions environment variables.
# Author: Ishan Phadte
# Last updated: 2025-09-03

import os
import json
import requests
import smtplib
from email.mime.text import MIMEText

# Load secrets from .env if running locally
if not os.environ.get("GITHUB_ACTIONS"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

# BambooHR endpoints
ENDPOINTS = [
    "https://giatecscientific.bamboohr.com/careers/list",
    "https://solace.bamboohr.com/careers/list",
    "https://truecontext.bamboohr.com/careers/list",
    "https://distillersr.bamboohr.com/careers/list",
    "https://recollective.bamboohr.com/careers/list"
]

# Workday sources (add more as needed)
WORKDAY_SOURCES = [
    {
        "name": "SST",
        "endpoint": "https://wd1.myworkdaysite.com/wday/cxs/ssctech/SSCTechnologies/jobs",
        "headers": {"Content-Type": "application/json"},
        "payload": {},
        "url_prefix": "https://wd1.myworkdaysite.com/en-US/ssctech"
    },
    {
        "name": "CIBC",
        "endpoint": "https://cibc.wd3.myworkdayjobs.com/wday/cxs/cibc/search/jobs",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "https://cibc.wd3.myworkdayjobs.com/search?State__Region__Province=218a720b28a74c67b5c6d42c00bdadfa&jobFamilyGroup=4bbe6c74e8a70126f29430a881012510",
            "User-Agent": "Mozilla/5.0 (Linux; Android 11.0; Surface Duo) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36"
        },
        "payload": {
            "appliedFacets": {
                "State__Region__Province": ["218a720b28a74c67b5c6d42c00bdadfa"],
                "jobFamilyGroup": ["4bbe6c74e8a70126f29430a881012510"]
            },
            "searchText": "",
            "locationArg": {},
            "sortBy": "relevance"
        },
        "url_prefix": "https://cibc.wd3.myworkdayjobs.com/en-US/cibc"
    },
    {
        "name": "Ciena",
        "endpoint": "https://ciena.wd5.myworkdayjobs.com/wday/cxs/ciena/Careers/jobs",
        "headers": {"Content-Type": "application/json", "Accept": "application/json"},
        "payload": {},
        "url_prefix": "https://ciena.wd5.myworkdayjobs.com/en-US/ciena"
    }
]

# Fetch jobs from third-party JSON endpoints
THIRD_PARTY_SOURCES = [
    {
        "name": "Evertz",
        "endpoint": "https://evertz.com/includes/json/careers.json"
    },
    {
        "name": "SurveyMonkey",
        "endpoint": "https://www.surveymonkey.com/content-svc/sm/content/v3/careers/?career_department=engineering&per_page=100&page=1"
    }
]

DATA_FILE = "data/previous_jobs.json"
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_TO = EMAIL_FROM  # sending to yourself

# Fetch jobs from a BambooHR endpoint
def fetch_jobs(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()["result"]  # Only return the job list

# Fetch jobs from a Workday endpoint
def fetch_workday_jobs_generic(endpoint, headers, payload):
    r = requests.post(endpoint, headers=headers, json=payload)
    r.raise_for_status()
    return r.json().get("jobPostings", [])

# Fetch jobs from third-party JSON endpoints
def fetch_third_party_jobs(endpoint):
    r = requests.get(endpoint)
    r.raise_for_status()
    return r.json()

# Load previous jobs from file
def load_previous_jobs():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

# Save jobs to file
def save_jobs(jobs):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

# Send email notification for new jobs
# This function sends an email and prints a summary to the console
# including the number and names of new jobs found.
def send_email(new_bamboo_jobs, new_workday_jobs):
    lines = []
    # Print summary of new jobs to console
    print(f"Emailing {len(new_bamboo_jobs)} new BambooHR jobs:")
    for job in new_bamboo_jobs:
        print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))}")
    print(f"Emailing {len(new_workday_jobs)} new Workday jobs:")
    for job in new_workday_jobs:
        print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))}")
    # Build email body
    if new_bamboo_jobs:
        lines.append("BambooHR Jobs:")
        for job in new_bamboo_jobs:
            try:
                start = job["url"].index("https://") + len("https://")
                end = job["url"].index(".bamboohr")
                company = job["url"][start:end].capitalize()
            except Exception:
                company = "Unknown"
            lines.append(f"{job['jobOpeningName']} @ {company} – {job['url']}")
        lines.append("")
    if new_workday_jobs:
        lines.append("Workday Jobs:")
        for job in new_workday_jobs:
            title = job.get("title", "Unknown")
            location = job.get("locationsText", "Unknown location")
            posted = job.get("postedOn", "Unknown date")
            url = job.get("externalPath", "")
            source = job.get("source", "Workday")
            lines.append(f"[{source}] {title} | {location} | {posted}\n{url}")
    body = "\n\n".join(lines)
    msg = MIMEText(body)
    msg["Subject"] = "New Job Postings"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    # Email sending
    print("Sending email...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)
    print("Email sent!")

# Main script logic
# Fetch jobs, compare with previous, send email if new jobs found, and update job file
def main():
    all_new_bamboo_jobs = []
    for url in ENDPOINTS:
        jobs = fetch_jobs(url)
        for job in jobs:
            job["url"] = f"{url.rstrip('/list')}/careers/{job['id']}"
        all_new_bamboo_jobs.extend(jobs)
    all_new_workday_jobs = []
    for source in WORKDAY_SOURCES:
        jobs = fetch_workday_jobs_generic(source["endpoint"], source["headers"], source["payload"])
        for job in jobs:
            job_id = job["bulletFields"][0] if job.get("bulletFields") and len(job["bulletFields"]) else job.get("externalPath", "")
            job["id"] = job_id
            job["externalPath"] = f"{source['url_prefix']}{job.get('externalPath', '')}" if job.get("externalPath") and not job.get("externalPath", "").startswith("http") else job.get("externalPath", "")
            job["source"] = source["name"]
        all_new_workday_jobs.extend(jobs)
    all_new_third_party_jobs = []
    for source in THIRD_PARTY_SOURCES:
        jobs = fetch_third_party_jobs(source["endpoint"])
        for job in jobs:
            job["source"] = source["name"]
        all_new_third_party_jobs.extend(jobs)
    old_jobs = load_previous_jobs()
    old_ids = {job["id"] for job in old_jobs}
    new_bamboo_postings = [job for job in all_new_bamboo_jobs if job["id"] not in old_ids]
    new_workday_postings = [job for job in all_new_workday_jobs if job["id"] not in old_ids]
    new_third_party_postings = [job for job in all_new_third_party_jobs if job["id"] not in old_ids]
    # Print summary of new jobs found
    print(f"Found {len(new_bamboo_postings)} new BambooHR jobs.")
    for job in new_bamboo_postings:
        print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))}")
    print(f"Found {len(new_workday_postings)} new Workday jobs.")
    for job in new_workday_postings:
        print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))}")
    print(f"Found {len(new_third_party_postings)} new Third-Party jobs.")
    for job in new_third_party_postings:
        print(f"- {job.get('title', 'Unknown')}")
    if new_bamboo_postings or new_workday_postings or new_third_party_postings:
        send_email(new_bamboo_postings, new_workday_postings + new_third_party_postings)
    save_jobs(all_new_bamboo_jobs + all_new_workday_jobs + all_new_third_party_jobs)

if __name__ == "__main__":
    main()
