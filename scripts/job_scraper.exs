# job_scraper.exs
Mix.install([
  {:httpoison, "~> 2.1"},
  {:jason, "~> 1.2"},
  {:swoosh, "~> 1.14"},
  {:gen_smtp, "~> 1.2"},
  {:dotenv_parser, "~> 2.0"},
  {:certifi, "~> 2.12"},
])

if System.get_env("GITHUB_ACTIONS") != "true" do
  case DotenvParser.load_file(".env") do
    {:ok, env} when map_size(env) > 0 ->
      Enum.each(env, fn {key, value} -> System.put_env(key, value) end)
      IO.puts("✅ .env file loaded successfully with #{map_size(env)} variables")

    {:ok, env} when map_size(env) == 0 ->
      IO.puts("⚠️ .env file is empty, nothing to load")

    :ok ->
      IO.puts("⚠️ .env file already loaded or empty")

    {:error, reason} ->
      IO.puts("❌ Failed to load .env file: #{inspect(reason)}")
  end
end




defmodule JobScraper do
  @previous_jobs_file "data/previous_jobs.json"
  @job_sources_file "data/job_sources.json"
  @email_from System.get_env("EMAIL_FROM")
  @email_password System.get_env("EMAIL_PASSWORD")
  @email_to @email_from

  import Swoosh.Email

  # Configure Swoosh SMTP adapter
  defp mailer_config do
    [
      adapter: Swoosh.Adapters.SMTP,
      relay: "smtp.gmail.com",
      username: System.get_env("EMAIL_FROM"),
      password: System.get_env("EMAIL_PASSWORD"),
      ssl: true,
      port: 465,
      retries: 2,
      auth: :always,
      tls_options: [
        verify: :verify_peer,
        cacerts: :certifi.cacerts() # <— load trusted certs manually
      ]
    ]
  end

  # Load JSON from a file
  def load_json(file) do
    case File.read(file) do
      {:ok, content} ->
        case Jason.decode(content) do
          {:ok, data} -> data
          {:error, err} ->
            IO.puts("Failed to decode JSON from #{file}: #{inspect(err)}")
            []
        end

      {:error, reason} ->
        IO.puts("Failed to read file #{file}: #{inspect(reason)}")
        []
    end
  end

  # Save JSON to a file
  def save_json(file, data) do
    File.mkdir_p!("data")
    File.write!(file, Jason.encode!(data, pretty: true))
  end

  # Load previous jobs
  def load_previous_jobs do
    load_json(@previous_jobs_file)
  end

  # Load job sources
  def load_job_sources do
    data = load_json(@job_sources_file)

    endpoints = Map.get(data, "ENDPOINTS", [])
    workday_sources = Map.get(data, "WORKDAY_SOURCES", [])
    third_party_sources = Map.get(data, "THIRD_PARTY_SOURCES", [])

    {endpoints, workday_sources, third_party_sources}
  end

  # Fetch BambooHR jobs
  def fetch_bamboo_jobs(url) do
    {:ok, resp} = HTTPoison.get(url)
    data = Jason.decode!(resp.body)
    jobs = Map.get(data, "jobs", []) # <- extract list safely

    Enum.map(jobs, fn job ->
      Map.put(job, "url", "#{String.trim_trailing(url, "/list")}/careers/#{job["id"]}")
    end)
  rescue
    err ->
      IO.puts("Error fetching BambooHR jobs from #{url}: #{inspect(err)}")
      []
  end

  # Fetch Workday jobs
  def fetch_workday_jobs(src) do
    {:ok, resp} = HTTPoison.post(src["endpoint"], Jason.encode!(src["payload"]), src["headers"])
    jobs = Map.get(Jason.decode!(resp.body), "jobPostings", [])

    Enum.map(jobs, fn job ->
      external_path = job["externalPath"] || ""
      job
      |> Map.put("id", job["bulletFields"] |> List.first() || external_path)
      |> Map.put("externalPath", "#{src["url_prefix"]}#{external_path}")
      |> Map.put("source", src["name"])
    end)
  rescue
    err ->
      IO.puts("Error fetching Workday jobs from #{src["name"]}: #{inspect(err)}")
      []
  end

  # Fetch third-party jobs
  def fetch_third_party_jobs(src) do
    {:ok, resp} = HTTPoison.get(src["endpoint"])
    jobs = Jason.decode!(resp.body)

    Enum.map(jobs, &Map.put(&1, "source", src["name"]))
  rescue
    err ->
      IO.puts("Error fetching third-party jobs from #{src["name"]}: #{inspect(err)}")
      []
  end

  defp send_email(new_jobs) do
    body =
      new_jobs
      |> Enum.map(fn job -> "- #{job["id"]}: #{job["url"]}" end)
      |> Enum.join("\n")

    email =
      new()
      |> from(@email_from)
      |> to(@email_to)
      |> subject("New Job Postings")
      |> text_body(body)

    case Swoosh.Adapters.SMTP.deliver(email, mailer_config()) do
      {:ok, _} -> IO.puts("✅ Email sent successfully!")
      {:error, reason} -> IO.puts("❌ Failed to send email: #{inspect(reason)}")
    end
  end

  # Main function
  def main do
    prev_jobs = load_previous_jobs()
    old_ids = MapSet.new(Enum.map(prev_jobs, & &1["id"]))

    {endpoints, workday_sources, third_party_sources} = load_job_sources()

    # Fetch all jobs concurrently
    bamboo_tasks = Enum.map(endpoints, &Task.async(fn -> fetch_bamboo_jobs(&1) end))
    workday_tasks = Enum.map(workday_sources, &Task.async(fn -> fetch_workday_jobs(&1) end))
    third_party_tasks = Enum.map(third_party_sources, &Task.async(fn -> fetch_third_party_jobs(&1) end))

    bamboo_jobs = Enum.flat_map(bamboo_tasks, &Task.await(&1, 30_000))
    workday_jobs = Enum.flat_map(workday_tasks, &Task.await(&1, 30_000))
    third_party_jobs = Enum.flat_map(third_party_tasks, &Task.await(&1, 30_000))

    all_jobs = bamboo_jobs ++ workday_jobs ++ third_party_jobs

    # Filter new jobs
    new_jobs = Enum.filter(all_jobs, fn job -> not MapSet.member?(old_ids, job["id"]) end)

    if length(new_jobs) > 0 do
      send_email(new_jobs)
    else
      IO.puts("No new jobs found")
    end

    save_json(@previous_jobs_file, all_jobs)
  end
end

JobScraper.main()
