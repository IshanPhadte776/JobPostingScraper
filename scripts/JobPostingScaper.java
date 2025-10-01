/*
JobPostingScraper.java

Java port of the Python job posting scraper with multithreading.
- Uses Java 11+ HttpClient for HTTP requests
- Uses Gson for JSON parsing
- Uses JavaMail (javax.mail) for sending email via SMTP SSL
- Uses an ExecutorService to fetch BambooHR, Workday, and Third-Party endpoints concurrently

Dependencies (Maven coordinates):
- com.google.code.gson:gson:2.10.1
- com.sun.mail:javax.mail:1.6.2 (or jakarta.mail equivalent)
- io.github.cdimascio:java-dotenv:5.2.2 (optional, for loading local .env files)

To compile & run: supply EMAIL_FROM and EMAIL_PASSWORD env vars (or use a .env file when running locally).

Author: Ishan Phadte
*/

import com.google.gson.*;
import com.google.gson.reflect.TypeToken;

import javax.mail.*;
import javax.mail.internet.InternetAddress;
import javax.mail.internet.MimeMessage;

import java.io.*;
import java.lang.reflect.Type;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;

public class JobPostingScraper {

    // Configure endpoints
    private static final List<String> BAMBOO_ENDPOINTS = List.of(
            "https://giatecscientific.bamboohr.com/careers/list",
            "https://solace.bamboohr.com/careers/list",
            "https://truecontext.bamboohr.com/careers/list",
            "https://distillersr.bamboohr.com/careers/list",
            "https://recollective.bamboohr.com/careers/list"
    );

    private static final List<Map<String, Object>> WORKDAY_SOURCES = List.of(
            Map.of("name", "SST", "endpoint", "https://wd1.myworkdaysite.com/wday/cxs/ssctech/SSCTechnologies/jobs", "headers", Map.of("Content-Type","application/json"), "payload", Map.of(), "url_prefix", "https://wd1.myworkdaysite.com/en-US/ssctech", "public_board_url", "https://wd1.myworkdayjobs.com/recruiting/ssctech/SSCTechnologies"),
            Map.of("name", "CIBC", "endpoint", "https://cibc.wd3.myworkdayjobs.com/wday/cxs/cibc/search/jobs", "headers", Map.of("Content-Type","application/json","Accept","application/json","Referer","https://cibc.wd3.myworkdayjobs.com/search?State__Region__Province=218a720b28a74c67b5c6d42c00bdadfa&jobFamilyGroup=4bbe6c74e8a70126f29430a881012510","User-Agent","Mozilla/5.0"), "payload", Map.of("appliedFacets", Map.of("State__Region__Province", List.of("218a720b28a74c67b5c6d42c00bdadfa"), "jobFamilyGroup", List.of("4bbe6c74e8a70126f29430a881012510")), "searchText", "", "locationArg", Map.of(), "sortBy", "relevance"), "url_prefix", "https://cibc.wd3.myworkdayjobs.com/en-US/cibc", "public_board_url", "https://cibc.wd3.myworkdayjobs.com/search"),
            Map.of("name", "Ciena", "endpoint", "https://ciena.wd5.myworkdayjobs.com/wday/cxs/ciena/Careers/jobs", "headers", Map.of("Content-Type","application/json","Accept","application/json"), "payload", Map.of(), "url_prefix", "https://ciena.wd5.myworkdayjobs.com/en-US/ciena", "public_board_url", "https://ciena.wd5.myworkdayjobs.com/Careers"),
            Map.of("name", "Entrust", "endpoint", "https://entrust.wd1.myworkdayjobs.com/wday/cxs/entrust/EntrustCareers/jobs", "headers", Map.of("Content-Type","application/json"), "payload", Map.of("appliedFacets", Map.of("locationCountry", List.of("a30a87ed25634629aa6c3958aa2b91ea","bc33aa3152ec42d4995f4791a106ed09"), "jobFamilyGroup", List.of("94f2a69b2507011c7bbbfc6f78076b26")), "searchText", "", "locationArg", Map.of(), "sortBy", "relevance"), "url_prefix", "https://entrust.wd1.myworkdayjobs.com/en-US/entrust", "public_board_url", "https://entrust.wd1.myworkdayjobs.com/EntrustCareers" )
    );

    private static final List<Map<String, String>> THIRD_PARTY_SOURCES = List.of(
            Map.of("name", "Evertz", "endpoint", "https://evertz.com/includes/json/careers.json"),
            Map.of("name", "SurveyMonkey", "endpoint", "https://www.surveymonkey.com/content-svc/sm/content/v3/careers/?career_department=engineering&per_page=100&page=1")
    );

    private static final String DATA_FILE = "data/previous_jobs.json";

    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(20))
            .build();

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    // Basic Job representation (keeps it flexible)
    static class Job extends HashMap<String, Object> {}

    public static void main(String[] args) throws Exception {
        // Optionally load .env when not running in CI
        if (System.getenv("GITHUB_ACTIONS") == null) {
            try {
                // optional dependency: java-dotenv, if present
                Class.forName("io.github.cdimascio.dotenv.Dotenv");
                io.github.cdimascio.dotenv.Dotenv dotenv = io.github.cdimascio.dotenv.Dotenv.load();
                System.out.println("Loaded .env variables (if any)");
            } catch (ClassNotFoundException ignored) {
                // dotenv not available; continue
            }
        }

        Map<String, String> cli = parseArgs(args);
        String companyFilter = cli.get("company");
        if (Boolean.parseBoolean(cli.getOrDefault("list-companies", "false"))) {
            listCompanies();
            return;
        }
        if (Boolean.parseBoolean(cli.getOrDefault("clear", "false"))) {
            saveJobs(Collections.emptyList());
            System.out.println("Cleared all jobs from previous_jobs.json.");
            return;
        }
        if (cli.containsKey("clear-company")) {
            String clearCompany = cli.get("clear-company");
            List<Job> old = loadPreviousJobs();
            List<Job> filtered = old.stream().filter(j -> !matchesCompany(j, clearCompany)).collect(Collectors.toList());
            saveJobs(filtered);
            System.out.println("Cleared jobs for company '" + clearCompany + "' from previous_jobs.json.");
            return;
        }

        // Multithreaded fetches using ExecutorService
        ExecutorService ex = Executors.newFixedThreadPool(8);
        try {
            List<Future<List<Job>>> futures = new ArrayList<>();
            // BambooHR fetch tasks
            for (String url : BAMBOO_ENDPOINTS) {
                futures.add(ex.submit(() -> fetchBamboo(url)));
            }
            // Workday fetch tasks
            for (Map<String, Object> src : WORKDAY_SOURCES) {
                futures.add(ex.submit(() -> fetchWorkdayGeneric(src)));
            }
            // Third-party fetch tasks
            for (Map<String, String> src : THIRD_PARTY_SOURCES) {
                futures.add(ex.submit(() -> fetchThirdParty(src)));
            }

            // collect results
            List<Job> allNew = new ArrayList<>();
            for (Future<List<Job>> f : futures) {
                try {
                    List<Job> partial = f.get(45, TimeUnit.SECONDS);
                    if (partial != null) allNew.addAll(partial);
                } catch (TimeoutException te) {
                    System.err.println("A fetch timed out: " + te.getMessage());
                }
            }

            List<Job> oldJobs = loadPreviousJobs();
            Set<Object> oldIds = oldJobs.stream().map(j -> j.get("id")).collect(Collectors.toSet());

            List<Job> newPostings = allNew.stream().filter(j -> !oldIds.contains(j.get("id"))).collect(Collectors.toList());

            // Print summary
            System.out.println("Found " + newPostings.size() + " new jobs.");
            for (Job j : newPostings) {
                if (companyFilter == null || matchesCompany(j, companyFilter)) {
                    System.out.println("- " + j.getOrDefault("jobOpeningName", j.getOrDefault("title", "Unknown")) + " @ " + j.getOrDefault("source", j.getOrDefault("company", "Unknown")));
                }
            }

            if (!newPostings.isEmpty()) {
                sendEmail(newPostings, companyFilter);
            }

            // Save all jobs as the new baseline
            saveJobs(allNew);

        } finally {
            ex.shutdownNow();
        }
    }

    // ---------- Helpers ----------
    private static Map<String, String> parseArgs(String[] args) {
        Map<String, String> map = new HashMap<>();
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--company":
                    if (i + 1 < args.length) map.put("company", args[++i]);
                    break;
                case "--clear":
                    map.put("clear", "true");
                    break;
                case "--clear-company":
                    if (i + 1 < args.length) map.put("clear-company", args[++i]);
                    break;
                case "--list-companies":
                    map.put("list-companies", "true");
                    break;
                default:
                    // ignore unknown
            }
        }
        return map;
    }

    private static void listCompanies() {
        List<String> bamboo = BAMBOO_ENDPOINTS.stream().map(u -> u.split("//")[1].split("\\\\.bamboohr")[0]).map(s -> capitalize(s)).collect(Collectors.toList());
        List<String> workday = WORKDAY_SOURCES.stream().map(s -> (String) s.get("name")).collect(Collectors.toList());
        List<String> third = THIRD_PARTY_SOURCES.stream().map(s -> s.get("name")).collect(Collectors.toList());
        System.out.println("BambooHR companies: " + String.join(", ", bamboo));
        System.out.println("Workday companies: " + String.join(", ", workday));
        System.out.println("Third-party companies: " + String.join(", ", third));
    }

    private static String capitalize(String s) {
        if (s == null || s.isEmpty()) return s;
        return s.substring(0,1).toUpperCase() + s.substring(1);
    }

    private static List<Job> fetchBamboo(String url) {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .GET()
                    .build();
            HttpResponse<String> res = CLIENT.send(req, HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() >= 200 && res.statusCode() < 300) {
                JsonObject root = JsonParser.parseString(res.body()).getAsJsonObject();
                JsonArray result = root.getAsJsonArray("result");
                Type t = new TypeToken<List<Map<String, Object>>>(){}.getType();
                List<Map<String, Object>> list = GSON.fromJson(result, t);
                List<Job> jobs = new ArrayList<>();
                for (Map<String, Object> m : list) {
                    Job j = new Job();
                    j.putAll(m);
                    Object id = m.getOrDefault("id", m.get("jobId"));
                    j.put("id", id);
                    String jobUrl = url.replaceAll("/list$", "") + "/careers/" + id;
                    j.put("url", jobUrl);
                    j.put("source", url.split("//")[1].split("\\\\.bamboohr")[0]);
                    jobs.add(j);
                }
                return jobs;
            } else {
                System.err.println("Bamboo fetch failed for " + url + " status=" + res.statusCode());
            }
        } catch (Exception e) {
            System.err.println("Error fetching Bamboo: " + e.getMessage());
        }
        return Collections.emptyList();
    }

    private static List<Job> fetchWorkdayGeneric(Map<String, Object> src) {
        try {
            String endpoint = (String) src.get("endpoint");
            Map<String, String> headers = (Map<String, String>) src.get("headers");
            Object payload = src.get("payload");
            String jsonPayload = GSON.toJson(payload);
            HttpRequest.Builder b = HttpRequest.newBuilder().uri(URI.create(endpoint)).POST(HttpRequest.BodyPublishers.ofString(jsonPayload));
            if (headers != null) headers.forEach(b::header);
            HttpRequest req = b.build();
            HttpResponse<String> res = CLIENT.send(req, HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() >= 200 && res.statusCode() < 300) {
                JsonObject root = JsonParser.parseString(res.body()).getAsJsonObject();
                JsonArray postings = root.has("jobPostings") ? root.getAsJsonArray("jobPostings") : new JsonArray();
                Type t = new TypeToken<List<Map<String, Object>>>(){}.getType();
                List<Map<String, Object>> list = GSON.fromJson(postings, t);
                List<Job> jobs = new ArrayList<>();
                for (Map<String, Object> m : list) {
                    Job j = new Job();
                    j.putAll(m);
                    // try to mimic Python behavior
                    Object jobId = m.getOrDefault("externalPath", m.getOrDefault("bulletFields", null));
                    j.put("id", jobId != null ? jobId : UUID.randomUUID().toString());
                    j.put("source", src.get("name"));
                    // normalize externalPath
                    if (m.containsKey("externalPath")) {
                        String ep = (String) m.get("externalPath");
                        String prefix = (String) src.get("url_prefix");
                        if (!ep.startsWith("http") && prefix != null) ep = prefix + ep;
                        j.put("externalPath", ep);
                    }
                    jobs.add(j);
                }
                return jobs;
            } else {
                System.err.println("Workday fetch failed for " + src.get("name") + " status=" + res.statusCode());
            }
        } catch (Exception e) {
            System.err.println("Error fetching Workday: " + e.getMessage());
        }
        return Collections.emptyList();
    }

    private static List<Job> fetchThirdParty(Map<String, String> src) {
        try {
            String endpoint = src.get("endpoint");
            HttpRequest req = HttpRequest.newBuilder().uri(URI.create(endpoint)).GET().build();
            HttpResponse<String> res = CLIENT.send(req, HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() >= 200 && res.statusCode() < 300) {
                Type t = new TypeToken<List<Map<String, Object>>>(){}.getType();
                List<Map<String, Object>> list = GSON.fromJson(res.body(), t);
                List<Job> jobs = new ArrayList<>();
                if (list != null) {
                    for (Map<String, Object> m : list) {
                        Job j = new Job();
                        j.putAll(m);
                        j.put("source", src.get("name"));
                        if (!j.containsKey("id")) j.put("id", UUID.randomUUID().toString());
                        jobs.add(j);
                    }
                }
                return jobs;
            } else {
                System.err.println("Third-party fetch failed for " + src.get("name") + " status=" + res.statusCode());
            }
        } catch (Exception e) {
            System.err.println("Error fetching third-party: " + e.getMessage());
        }
        return Collections.emptyList();
    }

    private static List<Job> loadPreviousJobs() {
        try {
            Path p = Path.of(DATA_FILE);
            if (!Files.exists(p)) return new ArrayList<>();
            String content = Files.readString(p, StandardCharsets.UTF_8);
            Type tt = new TypeToken<List<Job>>(){}.getType();
            List<Job> list = GSON.fromJson(content, tt);
            return list != null ? list : new ArrayList<>();
        } catch (Exception e) {
            System.err.println("Could not load previous jobs: " + e.getMessage());
            return new ArrayList<>();
        }
    }

    private static void saveJobs(List<Job> jobs) {
        try {
            Path p = Path.of(DATA_FILE);
            Files.createDirectories(p.getParent());
            String json = GSON.toJson(jobs);
            Files.writeString(p, json, StandardCharsets.UTF_8);
        } catch (Exception e) {
            System.err.println("Could not save jobs: " + e.getMessage());
        }
    }

    private static boolean matchesCompany(Job job, String companyFilter) {
        String f = companyFilter.toLowerCase();
        if (job.containsKey("jobOpeningName") && job.get("jobOpeningName").toString().toLowerCase().contains(f)) return true;
        if (job.containsKey("source") && job.get("source").toString().toLowerCase().contains(f)) return true;
        if (job.containsKey("title") && job.get("title").toString().toLowerCase().contains(f)) return true;
        return false;
    }

    private static void sendEmail(List<Job> newJobs, String companyFilter) {
        String from = System.getenv("EMAIL_FROM");
        String password = System.getenv("EMAIL_PASSWORD");
        if (from == null || password == null) {
            System.err.println("EMAIL_FROM or EMAIL_PASSWORD not set in environment.");
            return;
        }

        StringBuilder body = new StringBuilder();
        for (Job j : newJobs) {
            if (companyFilter == null || matchesCompany(j, companyFilter)) {
                String title = (String) j.getOrDefault("jobOpeningName", j.getOrDefault("title", "Unknown")).toString();
                String source = j.getOrDefault("source", "Unknown").toString();
                String url = j.getOrDefault("url", j.getOrDefault("externalPath", "")).toString();
                body.append(String.format("[%s] %s\n%s\n\n", source, title, url));
            }
        }

        Properties props = new Properties();
        props.put("mail.smtp.host", "smtp.gmail.com");
        props.put("mail.smtp.socketFactory.port", "465");
        props.put("mail.smtp.socketFactory.class", "javax.net.ssl.SSLSocketFactory");
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.port", "465");

        Session session = Session.getInstance(props, new javax.mail.Authenticator() {
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(from, password);
            }
        });

        try {
            Message message = new MimeMessage(session);
            message.setFrom(new InternetAddress(from));
            message.setRecipients(Message.RecipientType.TO, InternetAddress.parse(from));
            message.setSubject("New Job Postings");
            message.setText(body.toString());
            Transport.send(message);
            System.out.println("Email sent!");
        } catch (MessagingException e) {
            System.err.println("Failed to send email: " + e.getMessage());
        }
    }
}
