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

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Frontend** | React 18 + TypeScript + Vite | Web dashboard for data access, audit, and incident management |
| **Backend** | Python FastAPI | RESTful API for authentication, device management, and data operations |
| **Agent** | Go 1.24 | Local device agent for scanning and remediation |
| **Database** | MongoDB | Session, organization, and audit data storage |

---

## 🏗️ Architecture

### Directory Structure

```
dpdp/
├── frontend/           # React SPA dashboard
│   ├── src/
│   │   ├── pages/     # Page components (Dashboard, DataAccess, etc.)
│   │   ├── components/# Reusable UI components
│   │   ├── api/       # API client functions
│   │   ├── redux/     # State management
│   │   └── lib/       # Utilities and constants
│   ├── package.json
│   └── vite.config.ts
│
├── backend/            # FastAPI server
│   ├── api/
│   │   ├── local/     # Local device APIs (tasks, devices, results)
│   │   ├── cloud/     # Cloud storage integration (S3, Azure, GCP)
│   │   └── combined/  # Auth and organization endpoints
│   ├── services/      # Business logic
│   ├── main.py
│   └── requirements.txt
│
├── agent-go/           # Go agent (runs on devices)
│   ├── cmd/agent/     # Main agent binary
│   ├── internal/      # Agent configuration and logic
│   └── go.mod
│
└── mock_**/            # Mock data for testing (S3, Azure, GCP, etc.)
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

## 🔐 Authentication Flow

### User Registration & Login

1. **Signup** → User creates account with email/password
2. **Login** → User authenticates, receives session token
3. **Token Storage** → Token stored in localStorage and Redux state
4. **Authorization** → All API requests include `Authorization: Bearer <token>` header

### Organization Management

- Users can create and join organizations
- Each organization has:
  - Admin API keys (for device management)
  - Agent tokens (for device communication)
  - Device enrollment codes
  - User memberships with roles

### Logout

[See [LOGOUT_FLOW_EXPLAINED.md](LOGOUT_FLOW_EXPLAINED.md) for detailed explanation]

**Simple flow:**
1. User clicks "Log out" → Dropdown closes immediately
2. Frontend makes POST `/auth/logout` request with token
3. Backend marks session token as revoked
4. Frontend clears all auth state (Redux + localStorage)
5. User redirected to login page

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

### Authentication

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/signup` | Register new user |
| POST | `/auth/login` | Login and get session token |
| POST | `/auth/logout` | Logout and revoke token |
| GET | `/auth/organisations` | Get user's organizations |

### Devices

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/devices` | List organization devices |
| POST | `/devices/approval-requests` | Get pending device approvals |
| POST | `/devices/approve` | Approve device enrollment |

### Requests (Tasks)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/tasks` | Create scanning request |
| GET | `/tasks` | List requests |
| GET | `/tasks/{id}/results` | Get request results |
| POST | `/results` | Submit scan results |

### Cloud Integration

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/cloud/scan-cloud` | Scan cloud storage |
| POST | `/cloud/remediate` | Remediate cloud data |

---

## 🗂️ Frontend Pages

| Route | Purpose |
|-------|---------|
| `/login` | User authentication |
| `/` | Main dashboard |
| `/access-data` | Data source management and scanning |
| `/audit` | Audit logs and activity tracking |
| `/incidents` | Incident management |
| `/data-protection` | Protection policies and settings |
| `/data-inventory` | Data source catalog |
| `/infrastructure` | Infrastructure and integrations |
| `/requests` | Manage scanning/remediation requests |
| `/consent` | Consent management |
| `/profile` | User profile settings |

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
future database scans are separated by `data_sources.source_type`, not by
separate databases or duplicate collections.

| Collection | Purpose |
| --- | --- |
| `organizations`, `users`, `org_memberships`, `sessions` | Tenant and authentication records. |
| `data_sources` | Every scanning target. `source_type` is `local_device`, `cloud_storage`, or future `database`; `org_id` scopes every record. |
| `data_source_approval_requests` | Approval workflow for enrollable sources, currently local devices. |
| `scan_jobs` | Cloud scans, device cron runs, and future database scan executions. |
| `pii_classifications` | Findings from every source. Documents carry `org_id`, `data_source_id`, `source_type`, and `location`. |
| `data_subject_requests` | The master DPDP request: `request_type`, `data_principal`, verification/status lifecycle, SLA, submission channel, and timestamps. |
| `request_tasks` | One fan-out task per request/data source, with execution status, `scan_job_id`, embedded `result_summary`, action, and completion time. |
| `data_source_vulnerabilities` | Current vulnerability evidence per data source. |
| `audit_logs` | Immutable operational/audit events; new writers should include `org_id`, actor, entity, diff, IP, and `created_at`. |
| `redaction_records` | Idempotency/evidence records for local deletion and masking actions. |

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
`pii_classifications`; `cloud_logs` and `device_cron_logs` into `scan_jobs`;
cloud `user_requests` and local `device_tasks` into `data_subject_requests`
plus `request_tasks`; and devices into `data_sources`. Re-running it updates
the same canonical documents. Validate the counts and application traffic on
the new database before archiving legacy databases manually.

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
version: '3.8'
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
