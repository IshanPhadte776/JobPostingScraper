import { useState } from 'react'
import './App.css'

const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000';

function App() {
  const [output, setOutput] = useState('Select an action above to get started');
  const [jobs, setJobs] = useState([]);
  const [companies, setCompanies] = useState({});
  const [activeView, setActiveView] = useState('none'); // 'none', 'scrape', 'previous', 'companies'
  const [loading, setLoading] = useState({
    scrape: false,
    jobs: false,
    companies: false
  });

  const fetchData = async (url, method = "GET", body = null) => {
    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : null
      });
      if (!res.ok) throw new Error(res.statusText);
      return await res.json();
    } catch (err) {
      setOutput("Error: " + err);
      throw err;
    }
  };

  const getJobClass = (employmentStatus) => {
    if (!employmentStatus) return "";
    const status = employmentStatus.toLowerCase();
    if (status.includes("full")) return "full-time";
    if (status.includes("part")) return "part-time";
    if (status.includes("contract") || status.includes("temp")) return "contract";
    return "";
  };

  const handleScrapeAll = async () => {
    setActiveView('scrape');
    setCompanies({});
    setJobs([]);
    setLoading(prev => ({ ...prev, scrape: true }));
    setOutput("Starting job scraping process... ⏳");

    try {
      const data = await fetchData(`${API_URL}/scrape`);
      if (data.status !== "started" || !data.taskId) {
        throw new Error("Failed to start scraping process");
      }

      const taskId = data.taskId;
      setOutput("Scraping jobs from all sources... This may take a minute... ⏳");

      const checkStatus = async () => {
        try {
          const statusData = await fetchData(`${API_URL}/scrape/status/${taskId}`);
          console.log("Status check returned:", statusData);

          if (statusData.status === "error") {
            throw new Error(statusData.error || "Failed to scrape jobs");
          }

          if (statusData.status === "completed") {
            setJobs(statusData.jobs);
            setOutput(`Successfully scraped ${statusData.jobs.length} jobs! (${new Date(statusData.timestamp).toLocaleTimeString()})`);
            setLoading(prev => ({ ...prev, scrape: false }));
            return true;
          }

          return false;
        } catch (err) {
          if (err.message.includes("404")) return false;
          throw err;
        }
      };

      const pollInterval = setInterval(async () => {
        try {
          const isDone = await checkStatus();
          if (isDone) clearInterval(pollInterval);
        } catch (err) {
          setOutput("❌ Error checking scrape status: " + err);
          clearInterval(pollInterval);
          setLoading(prev => ({ ...prev, scrape: false }));
        }
      }, 2000);

      setTimeout(() => {
        clearInterval(pollInterval);
        if (loading.scrape) {
          setLoading(prev => ({ ...prev, scrape: false }));
          setOutput("⚠️ Scraping is taking longer than expected. Please check 'Get Previous Jobs' in a few minutes.");
        }
      }, 5 * 60 * 1000);

    } catch (err) {
      setOutput("❌ Error starting job scrape: " + err);
      setLoading(prev => ({ ...prev, scrape: false }));
    }
  };

  const handleGetJobs = async () => {
    setActiveView('previous');
    setCompanies({});
    setJobs([]);
    setLoading(prev => ({ ...prev, jobs: true }));
    setOutput("Fetching previous jobs...");

    try {
      const data = await fetchData(`${API_URL}/jobs`);
      if (data.status === "success") {
        setJobs(data.jobs);
        setOutput(`Loaded ${data.jobs.length} previous jobs!`);
      } else {
        throw new Error(data.message || "Failed to fetch jobs");
      }
    } catch (err) {
      setOutput("❌ Error loading jobs: " + err);
    } finally {
      setLoading(prev => ({ ...prev, jobs: false }));
    }
  };

  const handleGetCompanies = async () => {
    setActiveView('companies');
    setCompanies({});
    setJobs([]);
    setLoading(prev => ({ ...prev, companies: true }));
    setOutput("Fetching companies...");

    try {
      const data = await fetchData(`${API_URL}/companies`);
      if (data.status !== "success") {
        throw new Error(data.message || "Failed to fetch companies");
      }

      setOutput("Companies loaded! Click any company to scrape its jobs.");
      setCompanies(data.companies || {});
      setJobs([]);
    } catch (err) {
      setOutput("❌ Error loading companies: " + err);
    } finally {
      setLoading(prev => ({ ...prev, companies: false }));
    }
  };

  const handleCompanyClick = async (company) => {
    setOutput(`Scraping jobs for ${company}...`);
    try {
      const res = await fetchData(`${API_URL}/scrape?company=${encodeURIComponent(company)}`);
      if (res.status === "success") {
        setJobs(res.jobs);
        setOutput(`Found ${res.jobs.length} jobs for ${company}!`);
      } else {
        throw new Error(res.message || "Failed to scrape jobs");
      }
    } catch (err) {
      setOutput("❌ Error scraping company: " + err);
    }
  };

  return (
    <div className="container">
      <h1>Job Scraper Dashboard</h1>

      <div className="button-container">
        <button 
          className={`btn ${activeView === 'scrape' ? 'active' : ''}`} 
          onClick={handleScrapeAll} 
          disabled={loading.scrape}
        >
          Scrape All Jobs
        </button>
        <button 
          className={`btn ${activeView === 'previous' ? 'active' : ''}`}
          onClick={handleGetJobs} 
          disabled={loading.jobs}
        >
          Get Previous Jobs
        </button>
        <button 
          className={`btn ${activeView === 'companies' ? 'active' : ''}`}
          onClick={handleGetCompanies} 
          disabled={loading.companies}
        >
          List Companies
        </button>
      </div>

      {/* Companies Container */}
      {activeView === 'companies' && Object.entries(companies).length > 0 && (
        <div className="companies-container">
          {Object.entries(companies).map(([type, companyList]) => (
            <div key={type} className="company-group">
              <div className="group-title">
                {type.replace("_", " ").toUpperCase()}
              </div>
              {companyList.map(company => (
                <div
                  key={company}
                  className="company-card"
                  onClick={() => handleCompanyClick(company)}
                >
                  {company}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Loading State */}
      {(loading.scrape || loading.jobs || loading.companies) && (
        <div className="loading">Loading...</div>
      )}

      {/* Jobs Container */}
      {(activeView === 'scrape' || activeView === 'previous') && (
        <div className="job-cards">
          {jobs.length === 0 && !loading.scrape && !loading.jobs ? (
            <div style={{ textAlign: 'center', padding: '2rem' }}>No jobs found</div>
          ) : (
            jobs.map((job, index) => {
              const location = [job.city, job.state, job.location].filter(Boolean).join(", ");
              return (
                <div key={index} className={`job-card ${getJobClass(job.type)}`}>
                  <div className="job-title">{job.title || "No title"}</div>
                  {job.company && (
                    <div className="job-info">
                      <strong>Company:</strong> {job.company}
                    </div>
                  )}
                  {job.department && (
                    <div className="job-info">
                      <strong>Dept:</strong> {job.department}
                    </div>
                  )}
                  {job.type && (
                    <div className="job-info">
                      <strong>Type:</strong> {job.type}
                    </div>
                  )}
                  {location && (
                    <div className="job-info">
                      <strong>Location:</strong> {location}
                    </div>
                  )}
                  <a className="job-link" href={job.url} target="_blank" rel="noopener noreferrer">
                    Apply Now
                  </a>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Output Section */}
      <div>
        <h2>Output:</h2>
        <pre className="output">{output}</pre>
      </div>
    </div>
  )
}


export default App
