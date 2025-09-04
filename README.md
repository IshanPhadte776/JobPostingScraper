# Job Posting Scraper

This Python script fetches job postings from BambooHR, Workday, and third-party job boards (e.g., Evertz, SurveyMonkey), checks for new jobs, and sends email notifications. It supports local `.env` secrets and GitHub Actions environment variables for secure credential management.

## Features
- Fetch jobs from multiple BambooHR and Workday endpoints
- Fetch jobs from third-party JSON endpoints
- Detect new job postings and send email notifications
- Filter email notifications by company
- Supports local and CI/CD (GitHub Actions) environments

## Requirements
- Python 3.7+
- `requests` library
- `python-dotenv` (for local .env support)

Install dependencies:
```
pip install -r requirements.txt
```

## Usage

Run the script:
```
python scripts/check_jobs.py
```

### Arguments

| Argument      | Description                                                      | Example Usage                                 |
|--------------|------------------------------------------------------------------|------------------------------------------------|
| `--company`  | Send email for only this company (case-insensitive).             | `python scripts/check_jobs.py --company Evertz`|
| `--clear`        | Clear all jobs from previous_jobs.json before running.                | `python scripts/check_jobs.py --clear`                |
| `--clear-company`| Clear only jobs for this company from previous_jobs.json before running (case-insensitive). | `python scripts/check_jobs.py --clear-company Evertz`|

- If no arguments are provided, the script will send an email for all new jobs from all companies.
- If `--company` is specified, only jobs matching the company name will be included in the email and summary.

## Environment Variables

Set the following in your `.env` file (for local runs) or as secrets in GitHub Actions:
```
EMAIL_FROM=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
```

## Adding New Sources
- To add a new BambooHR or Workday endpoint, update the `ENDPOINTS` or `WORKDAY_SOURCES` list in `scripts/check_jobs.py`.
- To add a new third-party JSON endpoint, update the `THIRD_PARTY_SOURCES` list.

## Output
- Console summary of new jobs found
- Email notification with job details
- Updates `data/previous_jobs.json` to track previously seen jobs

## License
MIT
