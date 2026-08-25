# 🖥️ IT Support Assistant — AI Operations Assistant Using Agentic AI

> **Capstone Project | IIT | AI Operations Assistant**  
> An intelligent IT support agent built with **LangGraph**, **LangChain**, and **Streamlit**, deployed on **Azure Container Apps** via GitHub Actions CI/CD.

[![Deploy to Azure](https://github.com/YOUR_USERNAME/it-support-assistant/actions/workflows/azure-deploy.yml/badge.svg)](https://github.com/YOUR_USERNAME/it-support-assistant/actions/workflows/azure-deploy.yml)

---

## 📋 Problem Statement

Enterprise IT helpdesks handle hundreds of repetitive requests daily — VPN resets, ticket status checks, software installs, and more. Employees waste time navigating portals and waiting for responses. Traditional systems lack conversational intelligence.

**This project solves that** by building an AI-powered IT Support Assistant that understands natural language, picks the right tool, executes it, and returns a clear helpful response — all in one chat interface.

---

## 💡 Solution Overview

An **Agentic AI system** where an LLM acts as an intelligent agent that:

1. **Understands** the employee's intent from natural language
2. **Decides** which tool is required (or none)
3. **Executes** the appropriate tool with validated parameters
4. **Maintains state** across multi-turn conversations
5. **Returns** a formatted, professional response
6. **Queues operational emails** (e.g., VPN first-time setup + reset) to the employee-linked email when valid

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
  (12 KB articles)    (SQLite tickets)     (10 employees)
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
| Cloud Hosting | Azure Container Apps |
| Container Registry | Azure Container Registry (ACR) |
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
│   ├── init_db.py                    ← DB schema + 8 sample tickets
│   ├── employees.json                ← 10 sample employees
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
│   ├── setup-infra.sh                ← One-click Azure resource provisioning
│   ├── deploy.sh                     ← Manual deploy script
│   └── containerapp.yaml             ← Container Apps config
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

# 5. Initialize sample database
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
| `LOG_LEVEL` | ❌ | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`) |
| `ENABLE_FILE_LOG` | ❌ | `false` | Write logs to `logs/` directory |
| `ADMIN_EMAIL` | ❌ | `helloajay21@gmail.com` | Admin inbox that receives VPN onboarding/reset notifications as a copy |

### SMTP Settings (for real VPN email delivery)

| Variable | Required | Example Value | Description |
|----------|----------|---------------|-------------|
| `SMTP_HOST` | ✅ | `smtp.office365.com` | SMTP server host |
| `SMTP_PORT` | ✅ | `587` | SMTP port |
| `SMTP_USERNAME` | ✅ | `helloajay21@gmail.com` | SMTP login username |
| `SMTP_PASSWORD` | ✅ | `your-smtp-password` | SMTP login password |
| `SMTP_FROM_EMAIL` | ✅ | `helloajay21@gmail.com` | Sender email used for VPN notifications |
| `SMTP_USE_TLS` | ❌ | `true` | Enable STARTTLS for SMTP |
| `VPN_RESET_BASE_URL` | ❌ | `https://selfservice.techcorp.com/reset-vpn` | Link included in reset email |

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

Run the one-click setup script to create all Azure resources:

```bash
cd azure
chmod +x setup-infra.sh
./setup-infra.sh
```

This script will:
- ✅ Create a **Resource Group**
- ✅ Create an **Azure Container Registry** (ACR)
- ✅ Create a **Container Apps Environment**
- ✅ Create a **Service Principal** for GitHub Actions
- ✅ **Print all GitHub Secrets** you need to copy

> 💡 The script outputs a ready-to-copy table of all secret values.

### Step 3 — Add GitHub Secrets

Go to your GitHub repository → **Settings → Secrets and variables → Actions → New repository secret**

Add these **Secrets** (sensitive values):

| Secret Name | Where to get it | Description |
|-------------|-----------------|-------------|
| `AZURE_CREDENTIALS` | Output of `setup-infra.sh` | Service principal JSON for `az login` |
| `ACR_NAME` | Output of `setup-infra.sh` | Azure Container Registry name (without `.azurecr.io`) |
| `ACR_USERNAME` | Output of `setup-infra.sh` | ACR admin username |
| `ACR_PASSWORD` | Output of `setup-infra.sh` | ACR admin password |
| `AZURE_OPENAI_ENDPOINT` | Azure Portal → your OpenAI resource | e.g. `https://myresource.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | Azure Portal → your OpenAI resource → Keys | Key 1 or Key 2 |

Add these **Variables** (non-sensitive config):

| Variable Name | Value | Description |
|---------------|-------|-------------|
| `AZURE_RESOURCE_GROUP` | `it-support-assistant-rg` | Resource group name (must match setup script) |
| `AZURE_CONTAINER_APP_NAME` | `it-support-assistant` | Container app name |
| `AZURE_LOCATION` | `eastus` | Azure region |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | Your deployed model name |
| `AZURE_OPENAI_API_VERSION` | `2024-02-01` | Azure OpenAI API version |

### Step 4 — Push to GitHub to Trigger Deployment

```bash
git add .
git commit -m "Initial deployment"
git push origin main
```

GitHub Actions will automatically:
1. Build the Docker image
2. Push to Azure Container Registry
3. Deploy to Azure Container Apps
4. Output the live URL

### Step 5 — Get Your Live URL

After the GitHub Action completes, run:
```bash
az containerapp show \
  --name it-support-assistant \
  --resource-group it-support-assistant-rg \
  --query "properties.configuration.ingress.fqdn" -o tsv
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

### Ticket Lookup
```
User:  Check my tickets. My ID is EMP1024.

Agent: 📋 Support Tickets for EMP1024 — 2 ticket(s) found:
       Active Tickets (1):
       🎫 TKT-2024-002 | Laptop running very slowly | 🟡 In Progress
       ...
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
