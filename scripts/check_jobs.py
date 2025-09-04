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
import argparse

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
        "url_prefix": "https://wd1.myworkdaysite.com/en-US/ssctech",
        "public_board_url": "https://wd1.myworkdaysite.com/recruiting/ssctech/SSCTechnologies"
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
        "url_prefix": "https://cibc.wd3.myworkdayjobs.com/en-US/cibc",
        "public_board_url": "https://cibc.wd3.myworkdayjobs.com/search"
    },
    {
        "name": "Ciena",
        "endpoint": "https://ciena.wd5.myworkdayjobs.com/wday/cxs/ciena/Careers/jobs",
        "headers": {"Content-Type": "application/json", "Accept": "application/json"},
        "payload": {},
        "url_prefix": "https://ciena.wd5.myworkdayjobs.com/en-US/ciena",
        "public_board_url": "https://ciena.wd5.myworkdayjobs.com/Careers"
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
def send_email(new_bamboo_jobs, new_workday_jobs, new_third_party_jobs, company_filter=None):
    lines = []
    workday_base_urls = {src['name']: src['url_prefix'].replace('/en-US/', '') for src in WORKDAY_SOURCES}
    workday_public_urls = {src['name']: src.get('public_board_url') for src in WORKDAY_SOURCES if src.get('public_board_url')}
    def job_matches_company(job):
        if not company_filter:
            return True
        # Check for company in BambooHR jobs
        if job.get('jobOpeningName') and company_filter.lower() in job.get('jobOpeningName', '').lower():
            return True
        # Check for company in Workday jobs
        if job.get('source') and company_filter.lower() in job.get('source', '').lower():
            return True
        # Check for company in third-party jobs
        if job.get('source') and company_filter.lower() in job.get('source', '').lower():
            return True
        return False
    # Print summary of new jobs to console
    print(f"Emailing {len([j for j in new_bamboo_jobs if job_matches_company(j)])} new BambooHR jobs:")
    for job in new_bamboo_jobs:
        if job_matches_company(job):
            company = job.get('url', '').split('.bamboohr')[0].split('//')[-1].capitalize() if job.get('url') else 'Unknown'
            print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))} @ {company}")
    print(f"Emailing {len([j for j in new_workday_jobs if job_matches_company(j)])} new Workday jobs:")
    for job in new_workday_jobs:
        if job_matches_company(job):
            company = job.get('source', 'Unknown')
            print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))} @ {company}")
            public_url = workday_public_urls.get(company)
            if public_url:
                print(f"  Public job board: {public_url}")
    print(f"Emailing {len([j for j in new_third_party_jobs if job_matches_company(j)])} new Third-Party jobs:")
    for job in new_third_party_jobs:
        if job_matches_company(job):
            company = job.get('source', 'Unknown')
            print(f"- {job.get('title', 'Unknown')} @ {company}")
    # Build email body
    if any(job_matches_company(j) for j in new_bamboo_jobs):
        lines.append("BambooHR Jobs:")
        for job in new_bamboo_jobs:
            if job_matches_company(job):
                try:
                    start = job["url"].index("https://") + len("https://")
                    end = job["url"].index(".bamboohr")
                    company = job["url"][start:end].capitalize()
                except Exception:
                    company = "Unknown"
                lines.append(f"{job['jobOpeningName']} @ {company} – {job['url']}")
        lines.append("")
    if any(job_matches_company(j) for j in new_workday_jobs):
        lines.append("Workday Jobs:")
        for job in new_workday_jobs:
            if job_matches_company(job):
                title = job.get("title", "Unknown")
                location = job.get("locationsText", "Unknown location")
                posted = job.get("postedOn", "Unknown date")
                url = job.get("externalPath", "")
                source = job.get("source", "Workday")
                base_url = workday_base_urls.get(source, None)
                public_url = workday_public_urls.get(source)
                job_line = f"[{source}] {title} | {location} | {posted}\n{url}"
                if base_url:
                    job_line += f"\nStandard job board: {base_url}"
                if public_url:
                    job_line += f"\nPublic job board: {public_url}"
                lines.append(job_line)
    if any(job_matches_company(j) for j in new_third_party_jobs):
        lines.append("Third-Party Jobs:")
        for job in new_third_party_jobs:
            if job_matches_company(job):
                title = job.get("title", "Unknown")
                location = job.get("city", job.get("career_location", [{}])[0].get("name", "Unknown location"))
                url = job.get("link", "")
                source = job.get("source", "Third-Party")
                lines.append(f"[{source}] {title} | {location}\n{url}")
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
    parser = argparse.ArgumentParser(description="Job Posting Scraper")
    parser.add_argument("--company", type=str, help="Send email for only this company (case-insensitive)")
    parser.add_argument("--clear", action="store_true", help="Clear all jobs from previous_jobs.json before running")
    parser.add_argument("--clear-company", type=str, help="Clear only jobs for this company from previous_jobs.json before running (case-insensitive)")
    parser.add_argument("--list-companies", action="store_true", help="Print all companies involved and exit")
    args = parser.parse_args()
    company_filter = args.company
    # Print all companies and exit if --list-companies is set
    if args.list_companies:
        bamboo_companies = [url.split('//')[1].split('.bamboohr')[0].capitalize() for url in ENDPOINTS]
        workday_companies = [src['name'] for src in WORKDAY_SOURCES]
        third_party_companies = [src['name'] for src in THIRD_PARTY_SOURCES]
        print("BambooHR companies:", ", ".join(bamboo_companies))
        print("Workday companies:", ", ".join(workday_companies))
        print("Third-party companies:", ", ".join(third_party_companies))
        return
    # Clear all jobs if --clear is set
    if args.clear:
        save_jobs([])
        print("Cleared all jobs from previous_jobs.json.")
        return
    # Clear jobs for a specific company if --clear-company is set
    if args.clear_company:
        old_jobs = load_previous_jobs()
        filtered_jobs = [job for job in old_jobs if not (job.get('source') and args.clear_company.lower() in job.get('source', '').lower()) and not (job.get('jobOpeningName') and args.clear_company.lower() in job.get('jobOpeningName', '').lower())]
        save_jobs(filtered_jobs)
        print(f"Cleared jobs for company '{args.clear_company}' from previous_jobs.json.")
        return
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
    print(f"Found {len([j for j in new_bamboo_postings if not company_filter or company_filter.lower() in j.get('jobOpeningName', '').lower()])} new BambooHR jobs.")
    for job in new_bamboo_postings:
        if not company_filter or company_filter.lower() in job.get('jobOpeningName', '').lower():
            company = job.get('url', '').split('.bamboohr')[0].split('//')[-1].capitalize() if job.get('url') else 'Unknown'
            print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))} @ {company}")
    print(f"Found {len([j for j in new_workday_postings if not company_filter or company_filter.lower() in j.get('source', '').lower()])} new Workday jobs.")
    for job in new_workday_postings:
        if not company_filter or company_filter.lower() in job.get('source', '').lower():
            company = job.get('source', 'Unknown')
            base_url = None
            for src in WORKDAY_SOURCES:
                if src['name'] == company:
                    base_url = src['url_prefix'].replace('/en-US/', '')
                    break
            print(f"- {job.get('jobOpeningName', job.get('title', 'Unknown'))} @ {company}" + (f" | Standard job board: {base_url}" if base_url else ""))
    print(f"Found {len([j for j in new_third_party_postings if not company_filter or company_filter.lower() in j.get('source', '').lower()])} new Third-Party jobs.")
    for job in new_third_party_postings:
        if not company_filter or company_filter.lower() in job.get('source', '').lower():
            source = job.get('source', 'Unknown')
            title = job.get('title', 'Unknown')
            location = job.get('city', job.get('career_location', [{}])[0].get('name', 'Unknown location'))
            url = job.get('link', job.get('url', ''))
            print(f"- {title} @ {source} | {location} | {url}")
    if new_bamboo_postings or new_workday_postings or new_third_party_postings:
        send_email(new_bamboo_postings, new_workday_postings, new_third_party_postings, company_filter)
    save_jobs(all_new_bamboo_jobs + all_new_workday_jobs + all_new_third_party_jobs)

if __name__ == "__main__":
    main()
