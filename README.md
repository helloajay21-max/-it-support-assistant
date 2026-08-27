# 🖥️ AI Operations Assistant Using Agentic AI

> **Capstone Project | IIT | AI Operations Assistant**  
> An intelligent IT support agent built with **LangGraph**, **LangChain**, and **Streamlit**, deployed on **Azure App Service (container)** via GitHub Actions CI/CD.

[![Deploy to Azure](https://github.com/helloajay21-max/-it-support-assistant/actions/workflows/azure-deploy.yml/badge.svg)](https://github.com/helloajay21-max/-it-support-assistant/actions/workflows/azure-deploy.yml)

---

## 📋 Problem Statement

Enterprise IT helpdesks handle hundreds of repetitive requests daily — VPN resets, ticket status checks, software installs, and more. Employees waste time navigating portals and waiting for responses. Traditional systems lack conversational intelligence.

**This project solves that** by building an AI-powered operations assistant that understands natural language, picks the right tool, executes it, and returns a clear helpful response — all in one chat interface.

---

## 💡 Solution Overview

An **Agentic AI system** where an LLM acts as an intelligent agent that:

1. **Understands** the employee's intent from natural language
2. **Decides** which tool is required (or none)
3. **Executes** the appropriate tool with validated parameters
4. **Maintains state** across multi-turn conversations
5. **Returns** a formatted, professional response
6. **Sends and logs operational emails** (e.g., VPN first-time setup + reset) to the employee-linked email when valid
7. **Supports secure multi-user access** with admin-only approvals and self-service profile correction for normal users

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                      STREAMLIT CHAT INTERFACE                        │
│   Chat Input │ Message History │ Tool Activity Log │ Quick Prompts   │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ User Message
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       LANGGRAPH WORKFLOW                             │
│                                                                      │
│   START ──► [Intent Node] ──► Conditional Router                    │
│                                      │                              │
│              ┌───────────────────────┼───────────────────┐          │
│              ▼                       ▼                   ▼          │
│   [Knowledge Search Node]  [Ticket Lookup Node]  [Ticket Creation]  │
│              │                       │                   │          │
│              └───────────────────────┴───────────────────┘          │
│                                      │                              │
│                              [Response Node]                        │
│                                      │                              │
│                                     END                             │
└──────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
  knowledge_base.json    tickets.db          employees.json
  (12 KB articles)    (SQLite tickets)     (Admin + Arti seed users)
```

### LangGraph State
```
AgentState {
  messages[]        ← full conversation (add_messages reducer)
  employee_id       ← persisted across turns
  intent            ← knowledge_search | ticket_lookup | ticket_creation | employee_registration | employee_deletion | general
  pending_ticket    ← in-progress ticket data for multi-turn creation
  awaiting_info     ← multi-turn collection flag
  awaiting_field    ← which field we are waiting for
  tool_output       ← raw tool result
  turn_count        ← session turn counter
}
```

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|-----------|
| Agent Orchestration | LangGraph ≥ 1.0 |
| LLM Framework | LangChain ≥ 1.0 |
| Language Model | Azure OpenAI GPT-4o **or** OpenAI GPT-4o-mini |
| User Interface | Streamlit ≥ 1.35 |
| Local Database | SQLite (Python built-in `sqlite3`) |
| Sample Data | JSON files (knowledge base, employees) |
| Container | Docker |
| Cloud Hosting | Azure App Service (custom container) |
| Container Registry | Docker Hub |
| CI/CD | GitHub Actions |
| Language | Python 3.11 |

---

## 📁 Project Structure

```
it-support-assistant/
│
├── app.py                            ← Streamlit entry point
│
├── agent/
│   ├── state.py                      ← AgentState (Pydantic + add_messages)
│   ├── nodes.py                      ← All graph node implementations
│   ├── graph.py                      ← LangGraph workflow definition
│   └── router.py                     ← Conditional routing functions
│
├── tools/
│   ├── knowledge_search.py           ← Tool 1: Search IT knowledge base
│   ├── ticket_lookup.py              ← Tool 2: Look up support tickets
│   ├── ticket_creation.py            ← Tool 3: Create new tickets (with validation)
│   ├── employee_registration.py      ← Tool 4: Register employees (with validation)
│   └── employee_deletion.py          ← Tool 5: Deactivate/delete employees
│
├── data/
│   ├── init_db.py                    ← DB schema + core-user retention logic
│   ├── employees.json                ← Admin + Arti seed users
│   ├── knowledge_base.json           ← 12 IT how-to/troubleshooting articles
│   └── tickets.db                    ← SQLite database (auto-created; includes email_dispatch_log)
│
├── utils/
│   └── logger.py                     ← Centralised logging
│
├── .streamlit/
│   └── config.toml                   ← Streamlit theme + server settings
│
├── azure/
│   └── deploy.sh                     ← Manual container deploy helper
│
├── scripts/
│   ├── create_azure_resources.sh     ← Azure App Service provisioning
│   ├── create_service_principal.sh   ← GitHub Actions service principal helper
│   ├── set_env.ps1                   ← Local env helper
│   └── README_ENV.md                 ← Env + GitHub secrets setup notes
│
│
├── .github/
│   └── workflows/
│       └── azure-deploy.yml          ← GitHub Actions CI/CD pipeline
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## ⚙️ Local Setup & Run

### Prerequisites
- Python 3.11+
- Azure OpenAI **or** OpenAI API key

### Steps

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/it-support-assistant.git
cd it-support-assistant

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add your API key (see Environment Variables section below)

# 5. Initialize database
python data/init_db.py

# 6. Run
streamlit run app.py
```

Open **http://localhost:8501**

---

## 🔑 Environment Variables

Create a `.env` file from `.env.example`. **Never commit `.env` to GitHub.**

### Option A — Azure OpenAI *(recommended for Azure deployment)*

| Variable | Required | Example Value | Description |
|----------|----------|---------------|-------------|
| `AZURE_OPENAI_ENDPOINT` | ✅ | `https://myresource.openai.azure.com/` | Your Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | ✅ | `abc123...` | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | ✅ | `gpt-4o` | Deployed model name in Azure |
| `AZURE_OPENAI_API_VERSION` | ✅ | `2024-02-01` | Azure OpenAI API version |

### Option B — Standard OpenAI

| Variable | Required | Example Value | Description |
|----------|----------|---------------|-------------|
| `OPENAI_API_KEY` | ✅ | `sk-...` | OpenAI API key |
| `OPENAI_MODEL` | ❌ | `gpt-4o-mini` | Model name (default: `gpt-4o-mini`) |

### Application Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SQLITE_DB_PATH` | ❌ | `data/tickets.db` | SQLite database file path |
| `WEBSITES_ENABLE_APP_SERVICE_STORAGE` | Azure only | `true` | Keeps `/home` persistent for App Service SQLite storage |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`) |
| `ENABLE_FILE_LOG` | ❌ | `false` | Write logs to `logs/` directory |
| `ADMIN_EMAIL` | ❌ | `helloajay21@gmail.com` | Admin inbox for approval notifications; only this admin can approve or reject requests in the dashboard |
| `ADMIN_PASSWORD` | ❌ | _(empty)_ | Admin login password used for Ajay Kumar's secure approval access |

Normal users can correct their own stored profile details from the **Update My Details** screen after login. This is the recommended way to fix an invalid email address so response emails and approval notifications can be delivered correctly.

### SMTP Settings (for real VPN email delivery)

| Variable | Required | Example Value | Description |
|----------|----------|---------------|-------------|
| `SMTP_HOST` | ✅ | `smtp.gmail.com` | SMTP server host |
| `SMTP_PORT` | ✅ | `587` | SMTP port (`587` for STARTTLS, `465` for direct SSL) |
| `SMTP_USERNAME` | ✅ | `your-mailbox@gmail.com` | SMTP login username |
| `SMTP_PASSWORD` | ✅ | `app-password-without-spaces` | SMTP login password (use App Password for Gmail) |
| `SMTP_FROM_EMAIL` | ✅ | `your-mailbox@gmail.com` | Sender email used for VPN notifications |
| `SMTP_USE_TLS` | ❌ | `true` | Enable STARTTLS upgrade (port 587) |
| `SMTP_USE_SSL` | ❌ | `false` | Use direct SSL connection (port 465) — set `true` if STARTTLS is blocked |
| `VPN_RESET_BASE_URL` | ❌ | `https://selfservice.techcorp.com/reset-vpn` | Link included in reset email |

> **Gmail tip:** Create a dedicated [App Password](https://myaccount.google.com/apppasswords). Use port `587` + `SMTP_USE_TLS=true` (default) **or** port `465` + `SMTP_USE_SSL=true`.

---

## ☁️ Azure Deployment

### Step 1 — Prerequisites

```bash
# Install Azure CLI
# https://docs.microsoft.com/en-us/cli/azure/install-azure-cli

az login
az account show   # confirm correct subscription
```

### Step 2 — Provision Azure Infrastructure

Run the Azure App Service setup script:

```bash
chmod +x scripts/create_azure_resources.sh
./scripts/create_azure_resources.sh
```

This script will:
- ✅ Create a **Resource Group**
- ✅ Create an **App Service Plan**
- ✅ Create an **Azure Web App**
- ✅ Enable persistent `/home` storage for SQLite
- ✅ Apply the base runtime settings for the app

> 💡 Then run `./scripts/create_service_principal.sh` and add the GitHub secrets listed below.

### Step 3 — Add GitHub Secrets

Go to your GitHub repository → **Settings → Secrets and variables → Actions → New repository secret**

Add these **Secrets**:

| Secret Name | Description |
|-------------|-------------|
| `AZURE_CREDENTIALS` | Service principal JSON for `az login` |
| `DOCKERHUB_USERNAME` | Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
| `RESOURCE_GROUP` | Azure resource group that contains the web app |
| `WEBAPP_NAME` | Azure App Service web app name |
| `OPENAI_API_KEY` | OpenAI API key used by the assistant |
| `ADMIN_EMAIL` | Admin inbox for approval links and VPN copy emails |
| `ADMIN_PASSWORD` | Admin login password for Ajay Kumar |
| `SMTP_HOST` | SMTP host, e.g. `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port, e.g. `587` |
| `SMTP_USERNAME` | SMTP login username |
| `SMTP_PASSWORD` | SMTP app password / relay password |
| `SMTP_FROM_EMAIL` | Sender mailbox used by the app |
| `SMTP_USE_TLS` | `true` for STARTTLS (port 587) |
| `SMTP_USE_SSL` | `false` (set `true` for direct SSL on port 465) |
| `VPN_RESET_BASE_URL` | Link included in VPN reset emails |

The deployment workflow applies the runtime configuration on every push to `main`, including:
- persistent App Service storage (`WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`)
- SQLite path (`/home/data/tickets.db`)
- secure admin login via `ADMIN_PASSWORD`
- SMTP and VPN notification settings

### Step 4 — Push to GitHub to Trigger Deployment

```bash
git add .
git commit -m "Initial deployment"
git push origin main
```

GitHub Actions will automatically:
1. Build the Docker image
2. Push it to Docker Hub
3. Update Azure App Service to the new container image
4. Apply the Azure runtime settings
5. Restart the web app and output the live URL

### Step 5 — Get Your Live URL

After the GitHub Action completes, run:
```bash
az webapp show \
  --name your-webapp-name \
  --resource-group your-resource-group \
  --query defaultHostName -o tsv
```

Or check the GitHub Actions run log for the URL.

---

## 🐳 Docker (Local)

```bash
# Build and run with docker-compose
cp .env.example .env   # add your API keys
docker-compose up --build

# Access at http://localhost:8501
```

---

## 💬 Sample Interactions

### Knowledge Search
```
User:  How do I reset my VPN password?

Agent: 📚 Knowledge Base Article: "How to Reset VPN Password" (KB001)
       1. Visit https://selfservice.techcorp.com
       2. Click 'Reset VPN Credentials'
       3. Enter your employee email and ID
       4. Check email for reset link (valid 30 mins)
       ...
```

### Ticket Lookup — specific employee
```
User:  Check my tickets. My ID is EMP1024.

Agent: 📋 Support Tickets for EMP1024 — 2 ticket(s) found:
       Active Tickets (1):
       🎫 TKT-2024-002 | Laptop running very slowly | 🟡 In Progress
       ...
```

### Ticket Lookup — all employees (org-wide)
```
User:  Show all tickets

Agent: 🏢 All Tickets — Organization-Wide (11 total)
       | # | Ticket ID | Employee ID | Name | Title | Status | Priority |
       ...
       (full org snapshot with all employees)
```

### Direct VPN Setup Email (sidebar button — no conversation needed)
```
1. Enter Employee ID in the "📧 Send VPN Setup Email" sidebar section
2. Click "📤 Send VPN Setup Email with Password"
→ ✅ VPN setup + password reset emails sent to employee's registered email
```

### Ticket Creation (multi-turn)
```
User:  My VPN is not working. Please raise a ticket.

Agent: I'll create that for you! What is your employee ID?

User:  EMP1024

Agent: Here are the ticket details:
       Title: VPN connection issue | Category: VPN | Priority: Medium
       Shall I create this ticket? (Yes/No)

User:  Yes

Agent: ✅ Ticket TKT-2024-009 created! IT will respond within 4 hours.
```

### Employee Registration (manager-aware)
```

### First-time VPN setup (new employee)
```
User:  I am a new employee. Help me set up VPN. My ID is EMP1026.

Agent: 🔐 First-Time VPN Setup ...
       ✅ Dispatched first-time setup and password-reset emails to linked employee email
```
User:  Register new employee: Jane Smith, jane@techcorp.com, HR, Carol Davis

Agent: Please confirm:
       Name: Jane Smith
       Email: jane@techcorp.com
       Department: HR
       Manager: Carol Davis
       Role: Employee
       Shall I register this employee? (Yes/No)
```

---

## 🔑 Key Design Decisions

| Decision | Reason |
|----------|--------|
| **LangGraph over plain LangChain** | Enables stateful multi-turn conversations with typed state, conditional routing, and clear node/edge separation |
| **Pydantic AgentState** | Type safety, IDE support, and LangGraph's `add_messages` reducer for proper message accumulation |
| **SQLite for tickets** | Zero-dependency, file-based, portable — perfect for a local/demo system |
| **Azure OpenAI + OpenAI fallback** | Works in both enterprise (Azure) and development (OpenAI) environments |
| **Duplicate ticket detection** | Prevents ticket flooding by checking for open tickets in same category before creating |
| **Multi-turn confirmation** | Agent always confirms ticket details before creating — safety-first design |

---

## ⚠️ Limitations

- SQLite is not suitable for high-concurrency production use → migrate to Azure SQL or PostgreSQL
- No user authentication — employee ID is self-reported
- Knowledge base is static JSON → production would use Azure AI Search with vector embeddings
- No email notifications on ticket creation
- Single-replica state — conversation state is per browser session

---

## 📊 Evaluation Criteria Coverage

| Criterion | Status |
|-----------|--------|
| Functional Completeness | ✅ All 3 tools + multi-turn state + duplicate check + validation |
| GenAI / LLM Usage | ✅ Intent detection, parameter extraction, response generation |
| LangGraph Architecture | ✅ State, Nodes, Edges, Conditional Routing, Tool Execution |
| Tool Calling | ✅ `@tool` decorated LangChain tools with typed parameters |
| State Management | ✅ `AgentState` with `add_messages` reducer, persisted across turns |
| Code Quality | ✅ Type hints, docstrings, logger, modular structure |
| Error Handling | ✅ Validation in all tools, graceful fallbacks in all nodes |
| User Experience | ✅ Streamlit chat UI, tool activity log, quick prompts, reset |
| Documentation | ✅ This README + inline docstrings |
| Engineering Practices | ✅ `.env`, `.gitignore`, Docker, GitHub Actions CI/CD, Azure deployment |
