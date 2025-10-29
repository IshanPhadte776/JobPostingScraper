# Job Posting FastAPI Dashboard

A web application that scrapes job postings from multiple sources including BambooHR, Workday, and third-party job boards. It consists of a FastAPI backend and a simple HTML/JavaScript frontend.

## Features

- Fetch jobs from multiple sources:
  - BambooHR endpoints
  - Workday job boards
  - Third-party JSON endpoints (Evertz, SurveyMonkey)
- View all previously scraped jobs
- Filter jobs by company
- Simple and responsive web interface

## Prerequisites

- Python 3.7+
- pip (Python package installer)

## Installation

1. Clone the repository:
```sh
git clone <repository-url>
cd job_posting_fast_api
```

2. Install backend dependencies:
```sh
pip install -r requirements.txt
```

## Configuration

1. Create a `.env` file in the `job_posting_fast_api` directory:
```sh
EMAIL_FROM=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
```

## Running the Application

1. Start the backend server:
```sh
cd job_posting_fast_api/backend
python -m uvicorn main:app --reload
```

2. Open the frontend:
- Navigate to `job_posting_fast_api/frontend`
- Open `index.html` in your web browser
- Or serve it using a simple HTTP server:
```sh
python -m http.server 8080
```

## API Endpoints

- `GET /`: API health check
- `GET /jobs`: Get all previously scraped jobs
- `GET /scrape`: Trigger new job scraping
- `GET /companies`: List all configured companies

## Project Structure

```
job_posting_fast_api/
├── backend/
│   ├── main.py           # FastAPI application
│   ├── scraper/          # Job scraping logic
│   └── data/             # JSON data files
├── frontend/
│   └── index.html        # Web interface
└── requirements.txt      # Python dependencies
```

## License

MIT