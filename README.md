# SPARK - Data Protection & PII Detection Toolkit

**SPARK** is a comprehensive data protection platform that detects, manages, and remediates personally identifiable information (PII) across local files, databases, and cloud storage. It enables organizations to maintain compliance, protect privacy, and automatically handle sensitive data discovery.

---

## 📋 Overview

SPARK is a full-stack application built to help organizations:

- **Discover** PII and sensitive data across multiple sources
- **Monitor** data access and device compliance
- **Remediate** identified risks through automated actions
- **Audit** all data operations for compliance reporting
- **Manage** organization-wide data protection policies

### Key Components

| Component    | Technology                   | Purpose                                                                |
| ------------ | ---------------------------- | ---------------------------------------------------------------------- |
| **Frontend** | React 18 + TypeScript + Vite | Web dashboard for data access, audit, and incident management          |
| **Backend**  | Python FastAPI               | RESTful API for authentication, device management, and data operations |
| **Agent**    | Go 1.24                      | Local device agent for scanning and remediation                        |
| **Database** | MongoDB                      | Session, organization, and audit data storage                          |

---

## 🏗️ Architecture

### Directory Structure

```
dpdp/
├── frontend/           # React SPA dashboard
│   ├── src/
│   │   ├── pages/     # Page components (Dashboard, DataAccess, Requests, etc.)
│   │   ├── components/# Reusable UI components
│   │   ├── api/       # API client functions & auth headers
│   │   ├── redux/     # State management (auth, orgs, context)
│   │   └── lib/       # Utilities and constants
│   ├── package.json
│   └── vite.config.ts
│
├── backend/            # FastAPI server
│   ├── api/
│   │   ├── agents/    # Device enrollment, heartbeat, tasks, installer
│   │   ├── cloud/     # Cloud storage integration (S3, Azure, GCP)
│   │   ├── db_api/    # Database sources and scanning routes
│   │   ├── identity/  # Signup, login, sessions, org management
│   │   ├── middleware.py # OrgAuthContext dependency & authorization
│   │   └── unified_requests.py # Master DSR request lifecycle endpoints
│   ├── services/      # Business logic (PII detection, RequestStateManager, masking)
│   │   ├── persistence/ # MongoDB connection & index management
│   │   ├── cloud_storage/ # AWS/Azure/GCP cloud service adapters
│   │   └── db/        # Database connectors & scanner engine
│   ├── main.py
│   └── requirements.txt
│
├── agent-go/           # Go agent (runs on local devices)
│   ├── cmd/agent/     # Agent binary entrypoint and polling
│   ├── internal/      # Scanner engine, client, PII detector, GUI
│   ├── install.ps1    # PowerShell agent installer
│   └── go.mod
│
└── mock_**/            # Mock data for testing (S3, Azure, GCP, HR, DBs)
```

---

## 🚀 Quick Start

### Prerequisites

- **Node.js** 18+ (for frontend)
- **Python** 3.8+ (for backend)
- **Go** 1.24+ (for agent)
- **MongoDB** (for data storage)
- **Git**

### Installation

1. **Clone the repository**

   ```bash
   git clone <repo-url>
   cd dpdp
   ```

2. **Setup Backend**

   ```bash
   cd backend

   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt

   # Setup environment variables
   cp .env.example .env
   # Edit .env with your MongoDB connection and CORS settings

   # Run server
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Setup Frontend**

   ```bash
   cd frontend

   # Install dependencies
   bun install  # or npm install

   # Setup environment variables
   cp .env.example .env
   # Set VITE_API_URL=http://localhost:8000

   # Start dev server
   bun run dev  # or npm run dev
   # Opens at http://localhost:5173
   ```

4. **Setup Go Agent** (Optional)

   ```bash
   cd agent-go

   # Build the agent
   go build -o dpdp-agent ./cmd/agent

   # Run the agent
   ./dpdp-agent
   ```

---

## 🔐 Authentication & Organization Context

### User Registration & Login

1. **Signup** → User creates account with email/password
2. **Login** → User authenticates, receives session token and organization memberships
3. **Token Storage** → Token stored in localStorage and Redux state (`auth.token`, `auth.currentOrgId`)
4. **Org Isolation** → All protected API requests include `Authorization: Bearer <token>` and `X-Org-Id: <org_id>` headers (handled via `OrgAuthContext` middleware)

### Organization Management

- Users can belong to multiple organizations with specific roles (`admin`, `member`, `owner`)
- `resolve_org_context` dependency verifies user membership in requested organization
- Each organization provides:
  - Admin API keys (`X-Admin-Key` for administrative actions)
  - Agent tokens (for Go local agent endpoints)
  - Isolated data sources, scanning tasks, findings, and audit logs

### Logout

1. User clicks "Log out" → Dropdown closes immediately
2. Frontend sends `POST /auth/logout` request with session token
3. Backend marks session token as revoked
4. Frontend clears state (Redux + localStorage) and redirects to `/login`

---

## 📊 Core Features

### 1. Data Access Management

**Path:** `/access-data`

- **Local Files**: Scan local directories on registered devices
- **Database**: Connect to SQL/NoSQL databases and scan tables
- **Cloud Storage**: Scan AWS S3, Azure Blob, GCP Cloud Storage

**Workflow:**

1. Register devices through agent installation
2. Approve device enrollment requests
3. Create scanning requests (formerly "tasks")
4. Monitor request status and results
5. View PII findings and remediation options

### 2. Device Management

Devices are registered through automated agent installation:

- **Automatic Registration**: Agent registers itself on startup
- **Approval Workflow**: Admin reviews and approves devices
- **Health Monitoring**: Track last seen, activity status, agent version
- **Daily Scan Reports**: Automatic reports on device health

### 3. Request Execution

Scanning requests:

- **Access Requests**: Find PII matching a query
- **Update Requests**: Replace PII with new values
- **Delete Requests**: Remove PII from files
- **Expiration**: Requests auto-expire after 24 hours
- **Device Targeting**: Run on all devices or select specific ones

### 4. Audit & Incidents

- **Access Audit**: Track all data access operations
- **Incident Management**: Create and track data exposure incidents
- **Consent Management**: Track user consent and preferences
- **Data Inventory**: Catalog all data sources and classifications

### 5. Dashboard

Unified view of:

- Organization statistics (devices, users, requests)
- Recent activities and incidents
- Data protection posture
- Compliance status

---

## 🔧 API Endpoints

### Identity & Auth

| Method | Endpoint              | Purpose                                |
| ------ | --------------------- | -------------------------------------- |
| POST   | `/auth/signup`        | Register new user                      |
| POST   | `/auth/login`         | Login and receive token & org access   |
| POST   | `/auth/logout`        | Logout and revoke session token        |
| GET    | `/auth/organisations` | Get user's member organizations        |

### Unified Data Subject Requests (DSR)

| Method | Endpoint                 | Purpose                                                               |
| ------ | ------------------------ | --------------------------------------------------------------------- |
| POST   | `/requests`              | Create master DSR (Access / Update / Delete) across cloud, local, db  |
| GET    | `/requests`              | List org DSR requests with canonical status & filters                 |
| GET    | `/requests/{id}`         | Get master request detail with task fan-out and source scan results   |
| POST   | `/requests/{id}/approve` | Admin approval for pending requests to trigger remediation            |

### Devices & Agent Management

| Method | Endpoint                     | Purpose                                          |
| ------ | ---------------------------- | ------------------------------------------------ |
| POST   | `/devices/register`          | Register new agent / device                      |
| GET    | `/devices`                   | List org registered devices and activity status  |
| POST   | `/devices/heartbeat`         | Update device liveness timestamp                 |
| GET    | `/devices/approval-requests` | List pending device approval requests            |
| POST   | `/devices/approve`           | Approve/reject pending device enrollment         |
| GET    | `/devices/tasks`             | Device task polling (called by Go agent)         |
| POST   | `/devices/cron-runs`         | Register/update agent cron scan execution logs   |

### Cloud Integration

| Method | Endpoint              | Purpose                                         |
| ------ | --------------------- | ----------------------------------------------- |
| POST   | `/cloud/connect`      | Connect cloud storage provider (AWS/Azure/GCP)  |
| GET    | `/cloud/data-sources` | List connected cloud storage sources            |
| POST   | `/cloud/scan-cloud`   | Initiate cloud storage PII classification scan  |
| POST   | `/cloud/search`       | Search cloud objects for data subject matches   |

### Database Sources & Scans

| Method | Endpoint             | Purpose                                           |
| ------ | -------------------- | ------------------------------------------------- |
| POST   | `/db/connect`        | Register database connection (Postgres, SQLite)   |
| GET    | `/db/sources`        | List registered database sources                  |
| POST   | `/db/scan-database`  | Initiate database PII scan across tables/columns  |

---

## 🗂️ Frontend Pages

| Route              | Purpose                              |
| ------------------ | ------------------------------------ |
| `/login`           | User authentication                  |
| `/`                | Main dashboard                       |
| `/access-data`     | Data source management and scanning  |
| `/audit`           | Audit logs and activity tracking     |
| `/incidents`       | Incident management                  |
| `/data-protection` | Protection policies and settings     |
| `/data-inventory`  | Data source catalog                  |
| `/infrastructure`  | Infrastructure and integrations      |
| `/requests`        | Manage scanning/remediation requests |
| `/consent`         | Consent management                   |
| `/profile`         | User profile settings                |

---

## 🛠️ Development

### Frontend Development

```bash
cd frontend

# Development server with hot reload
bun run dev

# Build for production
bun run build

# Run linter
bun run lint

# Run tests
bun run test
```

### Backend Development

```bash
cd backend

# Development server with auto-reload
uvicorn main:app --reload

# Run with specific host/port
uvicorn main:app --host 0.0.0.0 --port 8000

# Check code with linting tools
pylint backend/
```

### Agent Development

```bash
cd agent-go

# Build for current platform
go build -o dpdp-agent ./cmd/agent

# Build for specific platform
GOOS=windows GOARCH=amd64 go build -o dpdp-agent.exe ./cmd/agent
GOOS=darwin GOARCH=amd64 go build -o dpdp-agent-darwin ./cmd/agent
```

---

## 🗃️ Database Schema

### Key Collections (MongoDB)

### Canonical storage model

Runtime storage uses one Mongo database, selected with `DPDP_DB_NAME` (default
`dpdp_platform`). `ATLAS_URL` selects the Mongo server. Local, cloud, and
database scans are separated by `data_sources.source_type` (or their own
tables, for database sources), not by separate databases or duplicate
collections.

| Collection                                              | Purpose                                                                                                                                                                |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `organizations`, `users`, `org_memberships`, `sessions` | Tenant and authentication records.                                                                                                                                     |
| `data_sources`                                          | Every local/cloud scanning target. `source_type` is `local_device` or `cloud_storage`; `org_id` scopes every record.                                                   |
| `data_source_approval_requests`                         | Approval workflow for enrollable sources, currently local devices.                                                                                                     |
| `database_sources`                                      | Registered database-engine connections (Postgres, SQLite, ...); kept separate because connection configs differ in shape from `data_sources`.                          |
| `agent_scan_logs`                                       | Legacy local device/agent scan execution history.                                                                                                                      |
| `agent_cron_runs`                                       | Canonical local-agent daily cron runs with status, timing, and vulnerability counts.                                                                                  |
| `cloud_scan_logs`                                       | Cloud storage scan execution history.                                                                                                                                  |
| `database_scan_runs`                                    | Database-engine scan execution history.                                                                                                                                |
| `pii_classifications`                                   | Findings from local/cloud sources. Documents carry `org_id`, `data_source_id`, `source_type`, and `location`.                                                          |
| `database_findings`                                     | Column-level PII findings from database scans.                                                                                                                         |
| `data_subject_requests`                                 | The master DPDP request: `request_type`, `data_principal`, verification/status lifecycle, SLA, submission channel, and timestamps.                                     |
| `request_tasks`                                         | One fan-out task per request/data source, with execution status, `scan_job_id`, embedded `result_summary`, action, and completion time.                                |
| `data_source_vulnerabilities`                           | Current vulnerability evidence per data source.                                                                                                                        |
| `audit_logs`                                            | Immutable operational/audit trail shared by local, cloud, and database actions; every writer includes `org_id`, actor, entity, `source_type`, action, and `timestamp`. |
| `redaction_records`                                     | Idempotency/evidence records for local deletion and masking actions.                                                                                                   |

The API keeps compatibility fields such as `organisation_id`, `device_id`, and
task `id` while clients transition. They are aliases within the same canonical
documents—not extra collections. New code should use `org_id` and
`data_source_id`.

#### Migrating existing Mongo data

The migration is intentionally opt-in. Starting the API **does not alter,
rename, or delete** the old `cloud_db`, `dpdp_local_db`, or
`dpdp_combined_db` collections. Run a dry run first, then apply the idempotent
backfill:

```bash
python -m backend.scripts.migrate_to_canonical_storage
python -m backend.scripts.migrate_to_canonical_storage --apply
```

It copies `cloud_classification` and `device_results` into
`pii_classifications`; `cloud_logs` into `cloud_scan_logs` and
`device_cron_logs` into `agent_scan_logs`; cloud `user_requests` and local
`device_tasks` into `data_subject_requests` plus `request_tasks`; and devices
into `data_sources`. Re-running it updates the same canonical documents.
Validate the counts and application traffic on the new database before
archiving legacy databases manually.

**users**

- User accounts with email, password hash, name
- Created and updated timestamps

**sessions**

- Session tokens with user_id
- Revoked flag (for logout)
- Creation and expiration timestamps

**organizations**

- Organization details and configuration
- Admin API keys, agent tokens
- Device enrollment codes

**org_memberships**

- User-to-organization relationships
- User roles (admin, member)

**devices**

- Device registration info (device_id, hostname)
- Approval status
- Last seen timestamp, agent version

**device_tasks**

- Scanning/remediation requests
- Query parameters, target devices
- Status (pending, completed, expired)
- Expiration timestamp

**device_results**

- Scan results for each task
- Matches found, file count
- Remediation data

---

## 🔒 Security Considerations

### Token Management

- Session tokens stored in MongoDB with `revoked` flag
- Tokens can be manually revoked (logout)
- No automatic expiration (revocation-based model)
- Tokens transmitted in Authorization headers only

### Password Security

- Passwords hashed with PBKDF2-SHA256 (120,000 iterations)
- Random salt per password
- Never stored or logged in plain text

### CORS

Configurable via `CORS_ORIGINS` environment variable:

```
CORS_ORIGINS=http://localhost:5173,http://localhost:8000
```

### Data Isolation

- Organization-level isolation in database
- Users can only access their organizations
- Device tokens scoped to organization
- All queries filter by organization_id

---

## 📝 Environment Variables

### Backend (.env)

```env
# Database
MONGODB_URI=mongodb://localhost:27017/dpdp
DATABASE_NAME=dpdp

# Server
CORS_ORIGINS=http://localhost:5173,http://localhost:8000
PORT=8000

# Agent Build (optional)
AGENT_SOURCE_PATH=/path/to/agent-go
AGENT_BUILD_ON_DOWNLOAD=1
AGENT_BUILD_TIMEOUT=300
```

### Frontend (.env)

```env
# API Configuration
VITE_API_URL=http://localhost:8000
```

### Agent (.env)

```env
# Server Configuration
API_SERVER=http://localhost:8000
ORG_ID=<from-organization>
AGENT_TOKEN=<from-organization>

# Local scanning paths
SCAN_PATHS=/home,/var

# Remediation settings
ENABLE_DELETE=true
ENABLE_UPDATE=true
```

---

## 🧪 Testing

### Frontend Tests

```bash
cd frontend
bun run test          # Run tests
bun run test:watch   # Watch mode
```

### Backend Tests

```bash
cd backend
pytest tests/
```

---

## 🐳 Docker Deployment

### Build Images

```bash
# Backend image
docker build -f Dockerfile -t dpdp-backend .

# Frontend image (separate Dockerfile if available)
docker build -f frontend/Dockerfile -t dpdp-frontend ./frontend
```

### Run with Docker Compose

```yaml
version: "3.8"
services:
  mongodb:
    image: mongo:latest
    ports:
      - "27017:27017"

  backend:
    image: dpdp-backend
    ports:
      - "8000:8000"
    environment:
      MONGODB_URI: mongodb://mongodb:27017/dpdp

  frontend:
    image: dpdp-frontend
    ports:
      - "80:80"
```

---

## 📚 Additional Resources

- [Logout Flow Explanation](LOGOUT_FLOW_EXPLAINED.md) - Detailed logout implementation
- [API Documentation](docs/API.md) - Comprehensive API reference
- [Agent Configuration](agent-go/README.md) - Go agent setup and usage
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions

---

## 🤝 Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes with clear commits
3. Test locally before pushing
4. Submit a pull request with detailed description

---

## 📄 License

[Add your license here]

---

## 🆘 Support

For issues, questions, or suggestions:

1. Check [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
2. Review existing issues
3. Create a new issue with detailed reproduction steps

---

**Last Updated:** August 2026
**Version:** 1.0.0
