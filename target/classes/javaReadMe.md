# Job Posting Scraper (Java, Multithreaded)

A Java 11+ multithreaded scraper that fetches job postings from BambooHR, Workday, and other endpoints, compares against previous data, and sends an email notification when new jobs are posted.

---

## Requirements
- Java 11+
- Maven 3+
- SMTP account (e.g. Gmail App Password)

---

# Job Posting Scraper (Java)

## Setup

1. Install dependencies and build the JAR:
```bash
mvn clean package
```

2. Run the scraper:

```bash
java -jar target/job-posting-scraper-1.0-SNAPSHOT-jar-with-dependencies.jar
```


Additionally Custom Commands 

Only scrape jobs for one company:
java -jar target/job-posting-scraper-1.0-SNAPSHOT-jar-with-dependencies.jar --company solace

Clear all previous job data:
java -jar target/job-posting-scraper-1.0-SNAPSHOT-jar-with-dependencies.jar --clear

Clear jobs for a specific company:
java -jar target/job-posting-scraper-1.0-SNAPSHOT-jar-with-dependencies.jar --clear-company solace

