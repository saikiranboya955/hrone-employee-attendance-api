# Employee Attendance & Analytics API

Backend service implementing HROne Engineering Assignment Contract v2.0 for employee attendance tracking, business rule calculations (R1–R10), manual regularization with audit history, and MongoDB aggregation analytics.

---

## 1. Purpose & Scope

The API tracks daily employee attendance, calculates derived metrics (work hours, late minutes, overtime, half days), manages manual HR corrections with change audit trails, and provides real-time departmental and organizational analytics executed directly within MongoDB aggregation pipelines.

---

## 2. Technology Stack

* **Language & Runtime:** Python 3.11+
* **Web Framework:** FastAPI 0.110+ (running on Uvicorn)
* **Database Driver:** PyMongo 4.7+
* **Validation & Serialisation:** Pydantic v2
* **Database:** MongoDB 6.0+ (Tested against MongoDB 7.0 on MongoDB Atlas)

---

## 3. API Reference

All instants (`punched_at`, `punch_in`, `punch_out`, `created_at`, history timestamps) are transmitted as integer epoch milliseconds and stored as UTC BSON datetimes. Calendar dates (`YYYY-MM-DD`) and shift times (`HH:MM`) are strings in Indian Standard Time (IST, UTC+05:30).

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/health` | Service and database readiness probe (`ping` check). | `200`, `503` |
| `POST` | `/employees` | Registers an employee. Requires unique `emp_code`. | `201`, `409`, `422` |
| `GET` | `/employees` | Paginated list of employees sorted by `emp_code` ascending. Filterable by department. | `200`, `422` |
| `POST` | `/attendance/punch-in` | Records daily punch-in. Computes IST date and late minutes (R1, R2). Concurrency-safe. | `201`, `404`, `409`, `422` |
| `POST` | `/attendance/punch-out` | Records punch-out. Computes work hours (R4), overtime (R3), and half-day flag (R5). | `200`, `404`, `409`, `422` |
| `GET` | `/attendance` | Paginated attendance logs sorted by `date` desc, `emp_code` asc. Filterable by employee, date range, status. | `200`, `422` |
| `PATCH` | `/attendance/{emp_code}/{date}` | Regularizes a record. Recomputes derived fields and appends an audit history entry with before/after changes. | `200`, `404`, `409`, `422` |
| `GET` | `/analytics/employees/{emp_code}/monthly` | Monthly employee summary (working days, present days, late count, total overtime, attendance percentage). | `200`, `404`, `422` |
| `GET` | `/analytics/departments/summary` | Department summary for a month. Headcount includes employees with zero logs (R9). Average over records. | `200`, `422` |
| `GET` | `/analytics/leaderboard/late` | Competition-ranked late-comers leaderboard (`$rank`: 1, 2, 2, 4). Resolves ties beyond limit cutoff. | `200`, `422` |
| `GET` | `/analytics/departments/{department}/trend` | Daily attendance series with database gap filling (`$densify`) and 7-day trailing moving average. | `200`, `404`, `422` |
| `GET` | `/admin/explain/{endpoint}` | Execution plan and stats for the main queries of the 5 key endpoints. Verifies `IXSCAN` and zero `COLLSCAN`. | `200`, `404`, `422` |

---

## 4. Setup & Configuration

### Prerequisites
* Python 3.11 or higher
* MongoDB instance (local or MongoDB Atlas cluster)

### Installation
```bash
# Clone the repository and navigate into the workspace
git clone https://github.com/saikiranboya955/hrone-employee-attendance-api.git
cd hrone-employee-attendance-api

# Create and activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### Environment Variables
Configure the database connection via environment variables or a local `.env` file in the repository root:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
```

> **Note on configuration precedence:** Environment variables set in the shell always take precedence over values defined in `.env`. Credentials and `.env` files must never be committed to source control.

---

## 5. Running the Application

Start the Uvicorn ASGI server:

```bash
uvicorn app.main:app --port 8000
```

* **Interactive API Documentation (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **OpenAPI 3.0 Specification:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

All database indexes (`employees.emp_code`, `attendance_logs.(emp_code, date)`, etc.) are created idempotently at application startup during the FastAPI lifespan handler.

### Optional: Seeding Sample Data
To load the sample documents from `sample_data/`:

```bash
python sample_seed.py
```

---

## 6. Verification & Test Suite

The test suite (`test_suite.py`) provides end-to-end verification across four isolated test categories:

```bash
python test_suite.py
```

### Test Categories
1. **Category 1: Pure Unit Tests (Business Rules R1–R8):**
   * Instant parsing and second truncation (R1).
   * IST attendance date attribution for daytime and overnight shifts (R1).
   * Grace period boundary and late calculation (R2).
   * Overtime threshold qualification and overnight shift end comparison (R3).
   * Arithmetic half-up work hours rounding (R4).
   * Half-day threshold checks (R5).
   * Working day counts for full-month and mid-month joiners (R7).
   * Arithmetic `ROUND_HALF_UP` tie boundary sweeps (R8).
2. **Category 2: API Contract & Validation Errors:**
   * HTTP 503 database-down readiness probe.
   * HTTP 422 input validation (employee codes, matching shift start/end, seconds timestamp rejection, inverted date ranges).
   * HTTP 404 resource-not-found handling on unknown endpoints and departments.
3. **Category 3: CRUD, Concurrency & Logic (Mocked Database):**
   * Employee creation and duplicate rejection (`409`).
   * Punch-in and duplicate punch-in race safety (`409`).
   * Punch-out and atomic single-winner punch-out concurrency (`409`).
   * Regularization and no-op update rejection (`422`).
   * Weekend rate nulling, zero-log weekdays, and short date range trend behavior.
4. **Category 4: Real Database Integration (Live MongoDB Atlas):**
   * Validates active unique indexes on Atlas.
   * Exercises full employee lifecycles across five distinct scenarios (`EMP9001`–`EMP9005`): standard daytime shifts, late arrivals with half-day classification (0.5 present days), exact grace/overtime boundaries, overnight shifts across midnight, and mid-month joiners.
   * Verifies multi-employee cross-collection aggregations (headcount retention for zero-log employees, competition ranking with ties, gap densification with dynamic headcount shifts).
   * Executes MongoDB `explain` with `executionStats` across all five endpoints, confirming index scan (`IXSCAN`) utilization and zero collection scans (`COLLSCAN`).

> **Data Safety:** Integration tests use dedicated test codes (`EMP7777`, `EMP9001`–`EMP9005`). Pre- and post-test teardown is executed in guarded `finally` blocks, ensuring seeded records (`EMP0001`–`EMP0006`) are never overwritten or deleted.

---

## 7. Project Structure

```text
├── app/
│   ├── __init__.py
│   └── main.py              # Consolidated FastAPI application, models, helpers, and pipelines
├── sample_data/
│   ├── employees.json        # Extended JSON sample employee records
│   └── attendance_logs.json  # Extended JSON sample attendance logs
├── DATA_MODEL.md             # Collection schemas, BSON types, and sample document reference
├── DECISIONS.md              # Architectural decisions (indexes, concurrency, ranking, headcount, scale)
├── openapi.yaml              # Authoritative OpenAPI 3.0 API contract
├── README.md                 # Technical service documentation
├── requirements.txt          # Python package dependencies
├── REVIEW.md                 # Code review log of starter defects with reproduction steps and fixes
├── sample_seed.py            # Utility script to seed sample data into MongoDB
└── test_suite.py             # Complete verification test suite (unit, contract, mock, and live Atlas)
```

---

## 8. Design Decisions & Limitations

1. **Concurrency Safety:**
   * **Punch-in:** Guarded by the unique compound index `attendance_logs.(emp_code, date)`. Simultaneous punch-ins for the same date result in exactly one insert and `DuplicateKeyError` (mapped to `409 Conflict`) for concurrent attempts.
   * **Punch-out:** Executed via atomic `find_one_and_update({"_id": ..., "punch_out": None}, ...)`, guaranteeing exactly one `200 OK` on simultaneous requests.
   * **Regularization:** Employs optimistic locking on the `history` array state, preventing concurrent corrections from overwriting audit entries.
2. **Database-Side Analytics:**
   * Trend generation relies on `$unionWith` (using an indexed lookup on `employees`) combined with `$densify` and `$setWindowFields`. All gap filling, moving averages, and dynamic headcounts are evaluated directly within the database engine.
   * All rounding adheres to arithmetic `ROUND_HALF_UP` (R8), implemented via exact base-10 Decimal128 conversion in aggregation pipelines to avoid binary floating-point drift.
3. **Known Limitations:**
   * **Real-time lookup overhead:** Department summaries execute a `$lookup` from `employees` to `attendance_logs`. On datasets with tens of millions of records, this should be migrated to pre-aggregated daily summaries maintained asynchronously via MongoDB Change Streams (as detailed in `DECISIONS.md`).
