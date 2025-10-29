from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

import os
import json
import datetime
import boto3
from botocore.exceptions import ClientError

from scraper import core  # your scraper module

app = FastAPI(title="Job Scraper API")

# Allow requests from any origin (for local dev). Change for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# S3 integration: if AWS_S3_BUCKET is set, use S3 for previous_jobs and status files.
S3_BUCKET = os.getenv("AWS_S3_BUCKET") or None
s3_client = boto3.client("s3") if S3_BUCKET else None

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _local_read(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _local_write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _s3_read(key):
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return []
        raise


def _s3_write(key, data):
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(data, indent=2, default=str).encode("utf-8"))


@app.get("/")
def root():
    return {"message": "Job Scraper API running!"}


@app.get("/jobs")
def get_jobs():
    try:
        if S3_BUCKET:
            jobs = _s3_read("previous_jobs.json")
        else:
            file_path = os.path.join(DATA_DIR, "previous_jobs.json")
            jobs = _local_read(file_path)
        return {"status": "success", "jobs": jobs}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/scrape")
def scrape_jobs_endpoint(background_tasks: BackgroundTasks, company: str = None):
    """
    Start scraping in background. Returns a taskId. Frontend should poll /scrape/status/{taskId}.
    """
    try:
        scrape_task_id = f"scrape_{company if company else 'all'}_{os.urandom(4).hex()}"

        def process_scrape(task_id, company_filter):
            try:
                # Run the actual scraper (synchronous)
                result = core.scrape_jobs(company_filter=company_filter)

                # Convert results to plain dicts and normalize fields
                json_compatible_result = []
                for job in result:
                    if hasattr(job, "__dict__"):
                        job_dict = dict(job.__dict__)
                    elif isinstance(job, dict):
                        job_dict = dict(job)
                    else:
                        try:
                            job_dict = dict(job)
                        except Exception:
                            job_dict = {"title": str(job)}

                    job_dict.setdefault("title", job_dict.get("title") or job_dict.get("jobOpeningName") or "No Title")
                    job_dict.setdefault("url", job_dict.get("url") or job_dict.get("externalPath") or "#")
                    job_dict.setdefault("company", job_dict.get("company") or job_dict.get("companyName") or company_filter or "Unknown")
                    job_dict.setdefault("type", job_dict.get("type") or job_dict.get("employmentStatus") or "Not Specified")

                    json_compatible_result.append(job_dict)

                # Persist previous jobs
                if S3_BUCKET:
                    _s3_write("previous_jobs.json", json_compatible_result)
                else:
                    file_path = os.path.join(DATA_DIR, "previous_jobs.json")
                    _local_write(file_path, json_compatible_result)

                # Write status payload
                status_payload = {
                    "status": "completed",
                    "jobs": jsonable_encoder(json_compatible_result),
                    "count": len(json_compatible_result),
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                }
                status_key = f"{task_id}.json"
                if S3_BUCKET:
                    _s3_write(status_key, status_payload)
                else:
                    status_path = os.path.join(DATA_DIR, status_key)
                    _local_write(status_path, status_payload)
            except Exception as err:
                status_payload = {
                    "status": "error",
                    "error": str(err),
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                }
                status_key = f"{task_id}.json"
                if S3_BUCKET:
                    _s3_write(status_key, status_payload)
                else:
                    status_path = os.path.join(DATA_DIR, status_key)
                    _local_write(status_path, status_payload)

        # enqueue background task
        background_tasks.add_task(process_scrape, scrape_task_id, company)

        return JSONResponse(content={"status": "started", "message": "Job scraping started", "taskId": scrape_task_id})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/scrape/status/{task_id}")
def get_scrape_status(task_id: str):
    """
    Poll this to get status. Returns 'pending' if status file not present yet.
    If a completed/error status file is found, returns it and removes the status file.
    """
    try:
        status_key = f"{task_id}.json"
        if S3_BUCKET:
            try:
                obj = s3_client.get_object(Bucket=S3_BUCKET, Key=status_key)
                status = json.loads(obj["Body"].read().decode("utf-8"))
                # remove status file after read
                s3_client.delete_object(Bucket=S3_BUCKET, Key=status_key)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    return JSONResponse(content={"status": "pending", "message": "Task is still running"})
                raise
        else:
            status_path = os.path.join(DATA_DIR, status_key)
            if not os.path.exists(status_path):
                return JSONResponse(content={"status": "pending", "message": "Task is still running"})
            status = _local_read(status_path)
            try:
                os.remove(status_path)
            except Exception:
                pass

        return JSONResponse(content=status)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/companies")
def list_companies():
    """
    Read job_sources.json from local data directory (this file should be present in backend/data).
    """
    try:
        file_path = os.path.join(DATA_DIR, "job_sources.json")
        data = _local_read(file_path) if os.path.exists(file_path) else {}
        companies = {
            "bamboohr": [url.split("//")[1].split(".bamboohr")[0] for url in data.get("ENDPOINTS", [])],
            "workday": [s.get("name") for s in data.get("WORKDAY_SOURCES", [])],
            "third_party": [s.get("name") for s in data.get("THIRD_PARTY_SOURCES", [])],
        }
        return {"status": "success", "companies": companies}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})