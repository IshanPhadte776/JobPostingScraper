import os
import json
import requests
import smtplib
from email.mime.text import MIMEText

if not os.environ.get("GITHUB_ACTIONS"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

ENDPOINTS = [
    "https://giatecscientific.bamboohr.com/careers/list",
    "https://solace.bamboohr.com/careers/list",
    "https://truecontext.bamboohr.com/careers/list",
    "https://distillersr.bamboohr.com/careers/list",
    "https://recollective.bamboohr.com/careers/list"
]
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
    }
]
DATA_FILE = "data/previous_jobs.json"
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_TO = EMAIL_FROM  # sending to yourself

def fetch_jobs(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()["result"]  # Only return the job list

def fetch_workday_jobs_generic(endpoint, headers, payload):
    r = requests.post(endpoint, headers=headers, json=payload)
    r.raise_for_status()
    return r.json().get("jobPostings", [])

def load_previous_jobs():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_jobs(jobs):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

def send_email(new_bamboo_jobs, new_workday_jobs):
    lines = []
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
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)

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
            job["id"] = job.get("jobPostingId", job.get("id", ""))
            job["externalPath"] = f"{source['url_prefix']}{job.get('externalPath', '')}" if job.get("externalPath") else ""
            job["source"] = source["name"]
        all_new_workday_jobs.extend(jobs)
    old_jobs = load_previous_jobs()
    old_ids = {job["id"] for job in old_jobs}
    new_bamboo_postings = [job for job in all_new_bamboo_jobs if job["id"] not in old_ids]
    new_workday_postings = [job for job in all_new_workday_jobs if job["id"] not in old_ids]
    if new_bamboo_postings or new_workday_postings:
        send_email(new_bamboo_postings, new_workday_postings)
    save_jobs(all_new_bamboo_jobs + all_new_workday_jobs)

if __name__ == "__main__":
    main()
