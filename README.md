#  GitMetrics: GitHub Portfolio Analyzer

An elegant, production-ready full-stack web application that processes real-time public developer metrics from the GitHub REST API v3. The system parses profile metadata, repository configurations, language distributions, and recent activity streams to compute a dynamic **Portfolio Score (0-100)** along with diagnostic actionable feedback (Strengths and Areas to Improve).

---

##  Tech Stack & Architecture

### Backend
* **Python 3.10+**: Core runtime environment.
* **FastAPI**: Selected for its asynchronous capabilities, automated OpenAPI documentation generation, high speed, and industry preference among modern backend engineering teams.
* **Jinja2 & Starlette**: Used for routing engine mechanics and serving template responses smoothly.
* **Requests**: Layered synchronous HTTP networking framework handling upstream integrations.

### Frontend
* **Vanilla HTML5 & Semantic CSS3**: Designed without heavy client-side frameworks (e.g., React, Vue) to emphasize raw DOM performance, minimalistic bundle overhead, and clean architectural separation.
* **Modern JavaScript (ES6+)**: Utilizes native asynchronous `async/await` fetch paradigms to render UI changes on a single-page application (SPA) wrapper.

---

##  Project Structure

```text
github-portfolio-analyzer/
│
├── app/                        # Monolithic Core Backend Services
│   ├── main.py                 # FastAPI Application Factory, Routing, & Exception Handlers
│   ├── github_api.py           # Core upstream REST client wrapping the GitHub API
│   └── analyzer.py             # Rule-engine compute pipeline (Scores, Grades, & Diagnostics)
│
├── templates/                  # Frontend User Interface Matrices
│   └── index.html              # Core Single Page Application Layout & Javascript Router
│
├── static/                     # System Performance Assets
│   └── style.css               # Production-grade CSS variables & Grid/Flexbox UI tokens
│
├── .gitignore                  # Target paths omitted from version control (e.g., venv/)
└── requirements.txt            # Declared system dependencies and constraints
```
---

### Evaluation Metrics Engine
The application evaluates user portfolios across several critical vectors:

Profile Completeness: Assesses user details, biography text presence, and account age metrics.

Repository Integrity: Examines fork-to-star ratios, overall project impact, and documentation quality (analyzing description coverage across public repositories).

Language Distribution: Tallies codebase diversity across development stacks (Python, JavaScript, C, etc.).

Activity Stream Analysis: Tracks real-time event updates over a rolling 30-day window to evaluate developer consistency.

---

### Local Installation & Deployment
Follow these instructions to establish a local testing instance:

1. Clone the Workspace
Bash
git clone [https://github.com/YOUR-USERNAME/github-portfolio-analyzer.git](https://github.com/YOUR-USERNAME/github-portfolio-analyzer.git)
cd github-portfolio-analyzer

2. Isolate Dependencies (Virtual Environment)
On Windows (PowerShell):

PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1

3. Install Requirements
Bash
pip install -r requirements.txt

4. Authenticate Upstairs API Requests (Highly Recommended)
To prevent unauthenticated rate-limiting threshold ceilings (60 requests/hour), configure a GitHub Personal Access Token (classic token without specific scopes is sufficient):

On Windows (PowerShell):

PowerShell
$env:GITHUB_TOKEN="your_personal_access_token"

5. Initialize the Uvicorn ASGI Server
Bash
uvicorn app.main:app --reload --port 8000
Navigate to http://127.0.0.1:8000 inside your web browser.

---

### Future Engineering Roadmap
To take this platform to enterprise scale, the next logical software development phases include:

Asynchronous I/O Network Refactoring: Upgrading requests to httpx or aiohttp inside github_api.py to completely unlock FastAPI's concurrent request capabilities.

Caching Middleware: Integrating a Redis in-memory cache layer with a 30-minute Time-To-Live (TTL) configuration to prevent duplicated round-trips to GitHub's infrastructure.

Enhanced UI Visualization: Swapping native CSS layout bars for a Chart.js integration to present multi-dimensional polar and doughnut charts mapping software language profiles.
