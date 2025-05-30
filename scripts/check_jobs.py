import os
import json
import requests
import smtplib
from email.mime.text import MIMEText

ENDPOINTS = [
    "https://giatecscientific.bamboohr.com/careers/list",
    "https://solace.bamboohr.com/careers/list"
]
DATA_FILE = "data/previous_jobs.json"
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_TO = EMAIL_FROM  # sending to yourself

def fetch_jobs(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def load_previous_jobs():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_jobs(jobs):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

def send_email(new_jobs):
    body = "\n\n".join(f"{job['jobOpeningName']} - {job['location']} - {job['url']}" for job in new_jobs)
    msg = MIMEText(body)
    msg["Subject"] = "🆕 New Job Postings Detected"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)

def main():
    all_new_jobs = []
    for url in ENDPOINTS:
        jobs = fetch_jobs(url)
        for job in jobs:
            job["url"] = f"{url.rstrip('/list')}/careers/{job['id']}"
        all_new_jobs.extend(jobs)

    old_jobs = load_previous_jobs()
    old_ids = {job["id"] for job in old_jobs}
    new_postings = [job for job in all_new_jobs if job["id"] not in old_ids]

    if new_postings:
        send_email(new_postings)
    save_jobs(all_new_jobs)

if __name__ == "__main__":
    main()
