# job_scraper_simple.exs
Mix.install([
  {:httpoison, "~> 2.1"},
  {:jason, "~> 1.2"}
])

defmodule JobScraper do
  @previous_jobs_file "data/previous_jobs.json"
  @job_sources_file "data/job_sources.json"

  # ----------------------------
  # JSON utilities
  # ----------------------------
  def load_json(file) do
    case File.read(file) do
      {:ok, content} ->
        case Jason.decode(content) do
          {:ok, data} -> data
          {:error, err} ->
            IO.puts("Failed to decode JSON from #{file}: #{inspect(err)}")
            %{}
        end

      {:error, reason} ->
        IO.puts("Failed to read file #{file}: #{inspect(reason)}")
        %{}
    end
  end

  def save_json(file, data) do
    File.mkdir_p!("data")
    File.write!(file, Jason.encode!(data, pretty: true))
  end

  # ----------------------------
  # Load previous jobs
  # ----------------------------
  def load_previous_jobs do
    jobs = load_json(@previous_jobs_file)
    IO.puts("Loaded previous jobs:")
    IO.inspect(jobs)
    jobs
  end

  # ----------------------------
  # Load job sources
  # ----------------------------
  def load_job_sources do
    data = load_json(@job_sources_file)
    IO.puts("Loaded job sources:")

    endpoints = Map.get(data, "ENDPOINTS", [])
    workday_sources = Map.get(data, "WORKDAY_SOURCES", [])
    third_party_sources = Map.get(data, "THIRD_PARTY_SOURCES", [])

    IO.inspect(endpoints, label: "BambooHR endpoints")
    IO.inspect(workday_sources, label: "Workday sources")
    IO.inspect(third_party_sources, label: "Third-party sources")

    {endpoints, workday_sources, third_party_sources}
  end

  # ----------------------------
  # Fetch jobs from BambooHR
  # ----------------------------
  def fetch_bamboo_jobs(endpoints) do
    Enum.flat_map(endpoints, fn url ->
      IO.puts("Fetching BambooHR jobs from #{url}")

      case HTTPoison.get(url) do
        {:ok, %HTTPoison.Response{status_code: 200, body: body}} ->
          jobs = Jason.decode!(body)["result"] || []
          Enum.map(jobs, fn job ->
            Map.put(job, "url", "#{String.trim_trailing(url, "/list")}/careers/#{job["id"]}")
          end)

        {:error, err} ->
          IO.puts("Failed to fetch BambooHR jobs from #{url}: #{inspect(err)}")
          []
      end
    end)
  end

  # ----------------------------
  # Fetch jobs from Workday
  # ----------------------------
  def fetch_workday_jobs(sources) do
    Enum.flat_map(sources, fn src ->
      IO.puts("Fetching Workday jobs for #{src["name"]}")

      headers = Map.to_list(src["headers"])
      payload = Jason.encode!(src["payload"])

      case HTTPoison.post(src["endpoint"], payload, headers) do
        {:ok, %HTTPoison.Response{status_code: 200, body: body}} ->
          jobs = Jason.decode!(body)["jobPostings"] || []
          Enum.map(jobs, fn job ->
            external_path = job["externalPath"] || ""
            job
            |> Map.put("id", job["bulletFields"] |> List.first() || external_path)
            |> Map.put("externalPath", "#{src["url_prefix"]}#{external_path}")
            |> Map.put("source", src["name"])
          end)

        {:error, err} ->
          IO.puts("Failed to fetch Workday jobs for #{src["name"]}: #{inspect(err)}")
          []
      end
    end)
  end

  # ----------------------------
  # Fetch third-party jobs
  # ----------------------------
  def fetch_third_party_jobs(sources) do
    Enum.flat_map(sources, fn src ->
      IO.puts("Fetching third-party jobs for #{src["name"]}")

      case HTTPoison.get(src["endpoint"]) do
        {:ok, %HTTPoison.Response{status_code: 200, body: body}} ->
          jobs = Jason.decode!(body) || []
          Enum.map(jobs, &Map.put(&1, "source", src["name"]))

        {:error, err} ->
          IO.puts("Failed to fetch third-party jobs for #{src["name"]}: #{inspect(err)}")
          []
      end
    end)
  end

  # ----------------------------
  # Find new jobs
  # ----------------------------
  def find_new_jobs(previous_jobs, current_jobs) do
    old_ids = MapSet.new(Enum.map(previous_jobs, & &1["id"]))
    Enum.filter(current_jobs, fn job -> not MapSet.member?(old_ids, job["id"]) end)
  end

  # ----------------------------
  # Send email (demo)
  # ----------------------------
  def send_email(new_jobs) do
    IO.puts("Sending email notification for #{length(new_jobs)} new jobs...")
    Enum.each(new_jobs, fn job ->
      IO.puts("- #{job["jobOpeningName"]} (#{job["url"] || job["externalPath"]}) [#{job["source"] || "BambooHR"}]")
    end)
  end

  # ----------------------------
  # Main function
  # ----------------------------
  def main do
    prev_jobs = load_previous_jobs()
    {endpoints, workday_sources, third_party_sources} = load_job_sources()

    bamboo_jobs = fetch_bamboo_jobs(endpoints)
    workday_jobs = fetch_workday_jobs(workday_sources)
    third_party_jobs = fetch_third_party_jobs(third_party_sources)

    all_jobs = bamboo_jobs ++ workday_jobs ++ third_party_jobs
    new_jobs = find_new_jobs(prev_jobs, all_jobs)

    IO.puts("Found #{length(new_jobs)} new job(s)")
    IO.inspect(new_jobs)

    if length(new_jobs) > 0 do
      send_email(new_jobs)
    end

    save_json(@previous_jobs_file, all_jobs)
    IO.puts("Saved current jobs to #{@previous_jobs_file}")
  end
end

JobScraper.main()
