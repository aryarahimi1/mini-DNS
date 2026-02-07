# Mini DNS API

A simplified yet realistic DNS service API built with FastAPI. Supports A records (IPv4) and CNAME records (aliases), with real-world DNS constraints including CNAME chaining, circular reference detection, and TTL-based record expiration with async background cleanup.

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** SQLite via SQLAlchemy (async) + aiosqlite
- **Validation:** Pydantic v2
- **Server:** Uvicorn
- **Python:** 3.13+

## Project Structure

```
dns2/
├── main.py              # Entry point — starts Uvicorn server
├── app/
│   ├── app.py           # FastAPI app, route handlers, lifespan (TTL cleanup)
│   ├── db.py            # SQLAlchemy models, engine, session management
│   ├── dns_logic.py     # Core DNS logic — validation, conflict checks, CNAME resolution, TTL
│   └── schemas.py       # Pydantic request/response schemas
├── tests/
│   ├── conftest.py      # Test fixtures — async client, in-memory DB
│   ├── test_endpoints.py # Integration tests for all API endpoints
│   └── test_validation.py # Unit tests for hostname/IPv4 validation
├── pyproject.toml       # Project metadata and dependencies
└── README.md
```

## Setup Instructions

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd dns2

# Install dependencies with uv
uv sync

# Or with pip
pip install -r pyproject.toml
```

### Running the Server

```bash
# With uv
uv run python main.py

# Or directly
python main.py
```

The server starts at `http://localhost:8000`.

### API Documentation (Swagger)

Once the server is running, interactive API docs are available at:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## API Endpoints

### 1. Add DNS Record

**`POST /api/dns`**

Creates a new A or CNAME record.

**Request Body:**

```json
{
  "type": "A",
  "hostname": "example.com",
  "value": "192.168.1.1",
  "ttl": 3600
}
```

```json
{
  "type": "CNAME",
  "hostname": "alias.example.com",
  "value": "example.com",
  "ttl": 7200
}
```

**Success Response (200):**

```json
{
  "hostname": "example.com",
  "type": "A",
  "value": "192.168.1.1",
  "createdAt": "2026-02-06 12:00:00"
}
```

**Error Responses:**

| Status | Detail | Cause |
|--------|--------|-------|
| 400 | Invalid hostname | Hostname fails DNS format validation |
| 400 | Invalid IPv4 address | A record value is not a valid IPv4 address |
| 400 | Invalid CNAME target hostname | CNAME value is not a valid hostname |
| 409 | CNAME conflict | Adding CNAME to hostname with existing records, or adding A record to hostname that has a CNAME |
| 409 | Duplicate record | Exact same hostname + type + value already exists |
| 422 | Validation error | TTL out of range (must be 1–86400), or missing/invalid fields |

**Example:**

```bash
curl -X POST http://localhost:8000/api/dns \
  -H "Content-Type: application/json" \
  -d '{"type": "A", "hostname": "example.com", "value": "192.168.1.1", "ttl": 3600}'
```

---

### 2. Resolve Hostname

**`GET /api/dns/{hostname}`**

Resolves a hostname to its IP addresses. If the hostname has a CNAME record, it follows the chain until it reaches A records.

**Success Response — A Record (200):**

```json
{
  "hostname": "example.com",
  "resolvedIps": ["192.168.1.1", "192.168.1.2"],
  "recordType": "A",
  "pointsTo": null
}
```

**Success Response — CNAME (200):**

```json
{
  "hostname": "alias.example.com",
  "resolvedIps": ["192.168.1.1", "192.168.1.2"],
  "recordType": "CNAME",
  "pointsTo": "example.com"
}
```

**Error Responses:**

| Status | Detail | Cause |
|--------|--------|-------|
| 400 | CNAME circular reference detected | CNAME chain forms a loop |
| 404 | Hostname not found | No active records exist for this hostname |

**Example:**

```bash
curl http://localhost:8000/api/dns/example.com
```

---

### 3. List DNS Records for Hostname

**`GET /api/dns/{hostname}/records`**

Returns all active (non-expired) records for a given hostname.

**Success Response (200):**

```json
{
  "hostname": "example.com",
  "records": [
    { "type": "A", "value": "192.168.1.1" },
    { "type": "A", "value": "192.168.1.2" }
  ]
}
```

**Error Responses:**

| Status | Detail | Cause |
|--------|--------|-------|
| 404 | Hostname not found | No active records exist for this hostname |

**Example:**

```bash
curl http://localhost:8000/api/dns/example.com/records
```

---

### 4. Delete DNS Record

**`DELETE /api/dns/{hostname}?type={type}&value={value}`**

Deletes a specific DNS record matching the hostname, type, and value.

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| type | Yes | Record type (`A` or `CNAME`) |
| value | Yes | Record value (IP address or target hostname) |

**Success Response (200):**

```json
{
  "message": "Record deleted successfully",
  "deleted": {
    "hostname": "example.com",
    "type": "A",
    "value": "192.168.1.1",
    "createdAt": "2026-02-06 12:00:00"
  }
}
```

**Error Responses:**

| Status | Detail | Cause |
|--------|--------|-------|
| 404 | Record not found | No record matches the given hostname, type, and value |

**Example:**

```bash
curl -X DELETE "http://localhost:8000/api/dns/example.com?type=A&value=192.168.1.1"
```

---

## Implementation Decisions

### Why FastAPI + Async SQLAlchemy?

I chose FastAPI for its native async support and automatic OpenAPI documentation generation. Paired with SQLAlchemy's async engine and aiosqlite, the entire request path is non-blocking. This matters for a DNS service where low latency is critical — no request blocks the event loop waiting for database I/O.

### Why SQLite?

For a mini DNS service, SQLite keeps the setup simple with zero external dependencies (no database server to install). The schema uses proper constraints (`UniqueConstraint`, `CheckConstraint`) and indexes on `hostname` and `(hostname, type)` to ensure data integrity at the database level, not just in application code. This would translate directly to PostgreSQL or MySQL for a production deployment.

### Separating Business Logic from Schemas

Initially, I had DNS constraint checks (CNAME conflicts, duplicate detection, hostname/IP validation) embedded directly in the Pydantic schemas and route handlers. This worked but made the code harder to follow — validation logic was scattered across schemas and endpoints. I refactored all business logic into a dedicated `dns_logic.py` module so that route handlers stay thin (they only call validation functions and return responses) and all DNS rules live in one place. This separation makes the logic easier to test in isolation, easier to reason about, and easier to extend if new record types are added later.

### DNS Constraint Enforcement

Real DNS has strict rules around CNAME records: a hostname with a CNAME cannot have any other records, and each hostname can have at most one CNAME. These constraints are enforced in the `check_cname_conflict` function in `dns_logic.py` at the application level before any record is persisted. This mirrors how authoritative DNS servers reject conflicting zone entries.

### CNAME Chain Resolution

CNAME resolution is recursive — when resolving a hostname that points to another CNAME, the service follows the chain until it reaches A records. To prevent infinite loops (e.g., `a.com → b.com → a.com`), a `visited` set tracks hostnames already seen in the chain. If a cycle is detected, the API returns a `400` error with a clear message identifying the circular reference.

### Validation Approach

- **Hostnames** are validated against RFC 1123 rules: labels separated by dots, 1–63 characters per label, alphanumeric with hyphens (not leading/trailing), minimum two labels, max 253 characters total.
- **IPv4 addresses** are validated manually (not via regex) to reject leading zeros (e.g., `01.02.03.04`) which are ambiguous in some systems.
- **CNAME targets** are validated as hostnames since they must point to valid DNS names.
- **TTL** is constrained to 1–86400 seconds (1 day max) via Pydantic's `Field` validator.

### TTL Expiration (Async Background Processing)

Each DNS record has a TTL (Time To Live) field that determines how long the record remains active. The TTL system works in two layers:

1. **Query-time filtering:** Every endpoint that reads records passes them through `filter_expired()`, which compares each record's age (`now - created_at`) against its TTL. Expired records are excluded from responses immediately — the user never sees stale data.

2. **Background cleanup:** A background `asyncio` task runs on a 60-second interval during the application lifespan. It scans all records, deletes any that have exceeded their TTL, and logs the count of removed records. This keeps the database clean without impacting request latency.

This two-layer approach was chosen because relying only on background cleanup would create a window where expired records are still returned to users. And relying only on query-time filtering would leave expired rows accumulating in the database indefinitely. The combination ensures both correctness and cleanliness.

The background task is started via FastAPI's `lifespan` context manager and cancelled cleanly on shutdown. Errors in the cleanup task are caught and logged without crashing the server.

---

## AI Tool Usage

I used **Cursor AI** (in-editor AI) during development:

- **Cursor Tab (autocomplete):** Used for inline code completion while writing logic — it suggested boilerplate patterns, function signatures, and common SQLAlchemy/FastAPI patterns that I accepted or modified as needed.
- **Cursor AI Agent (one session):** Used to review the codebase for potential issues. The agent caught a missing `raise` before an `HTTPException`, identified unused imports, flagged that validation functions were defined but not called in endpoints, and suggested using a typed Pydantic `RecordItem` schema instead of plain dicts for the records list response.
- **Cursor AI Agent (test generation):** Used to help generate the test suite structure and test cases. I specified what scenarios needed coverage (CNAME conflicts, circular references, TTL expiration, validation edge cases, etc.) and the agent helped write the pytest test files with the async test client setup.
- **README drafting:** Used AI to help structure and format the API documentation, endpoint tables, and error response descriptions.

All core logic — the DNS constraint enforcement, CNAME chaining with circular detection, TTL expiration design, database schema, and the overall architecture — was designed and implemented by me. The AI assisted with code completion speed, catching oversights during review, generating tests, and formatting documentation.
