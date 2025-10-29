from fastapi import FastAPI, BackgroundTasks
import json
import os
import datetime
from scraper import core
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

app = FastAPI(title="Job Scraper API")

# Allow requests from any origin (for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Job Scraper API running!"}

@app.get("/jobs")
def get_jobs():
    try:
        file_path = os.path.join(os.path.dirname(__file__), "data", "previous_jobs.json")
        with open(file_path, "r") as f:
            jobs = json.load(f)
        return {"status": "success", "jobs": jobs}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.get("/scrape")
async def scrape_jobs_endpoint(company: str = None, background_tasks: BackgroundTasks = None):
    try:
        # Start the scraping process in a background task
        scrape_task_id = f"scrape_{company if company else 'all'}_{os.urandom(4).hex()}"
        
        async def process_scrape():
            try:
                # Scrape jobs
                result = core.scrape_jobs(company_filter=company)
                
                # Convert each job to a plain dict
                json_compatible_result = []
                for job in result:
                    if hasattr(job, "__dict__"):
                        job_dict = job.__dict__
                    else:
                        job_dict = dict(job)
                    
                    # Ensure all required fields are present
                    job_dict.setdefault("title", job_dict.get("jobOpeningName", "No Title"))
                    job_dict.setdefault("url", job_dict.get("externalPath", "#"))
                    job_dict.setdefault("company", job_dict.get("companyName", company))
                    job_dict.setdefault("type", job_dict.get("employmentStatus", "Not Specified"))
                    
                    json_compatible_result.append(job_dict)

                # Save to previous_jobs.json
                file_path = os.path.join(os.path.dirname(__file__), "data", "previous_jobs.json")
                with open(file_path, "w") as f:
                    json.dump(json_compatible_result, f, indent=2)
                
                # Save to status file
                status_path = os.path.join(os.path.dirname(__file__), "data", f"{scrape_task_id}.json")
                with open(status_path, "w") as f:
                    json.dump({
                        "status": "completed",
                        "jobs": jsonable_encoder(json_compatible_result),
                        "count": len(json_compatible_result),
                        "timestamp": str(datetime.datetime.now())
                    }, f)

            except Exception as e:
                # Save error status
                status_path = os.path.join(os.path.dirname(__file__), "data", f"{scrape_task_id}.json")
                with open(status_path, "w") as f:
                    json.dump({
                        "status": "error",
                        "error": str(e),
                        "timestamp": str(datetime.datetime.now())
                    }, f)
        
        background_tasks.add_task(process_scrape)
        
        return JSONResponse(
            content={
                "status": "started",
                "message": "Job scraping started",
                "taskId": scrape_task_id
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/scrape/status/{task_id}")
async def get_scrape_status(task_id: str):
    try:
        status_path = os.path.join(os.path.dirname(__file__), "data", f"{task_id}.json")
        if not os.path.exists(status_path):
            return JSONResponse(
                content={
                    "status": "pending",
                    "message": "Task is still running"
                }
            )
        
        with open(status_path, "r") as f:
            status = json.load(f)
            
        # Clean up the status file
        try:
            os.remove(status_path)
        except:
            pass
            
        return JSONResponse(content=status)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

@app.get("/companies")
def list_companies():
    try:
        file_path = os.path.join(os.path.dirname(__file__), "data", "job_sources.json")
        with open(file_path, "r") as f:
            data = json.load(f)
        
        companies = {
            "bamboohr": [url.split("//")[1].split(".bamboohr")[0] for url in data.get("ENDPOINTS", [])],
            "workday": [s.get("name") for s in data.get("WORKDAY_SOURCES", [])],
            "third_party": [s.get("name") for s in data.get("THIRD_PARTY_SOURCES", [])]
        }
        
        return {"status": "success", "companies": companies}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )
