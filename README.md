# Employee Attendance & Analytics API

Production-grade FastAPI + MongoDB backend implementing Contract v2.0 for employee attendance tracking, business rule validation, manual corrections with audit history, and MongoDB aggregation analytics.

## Prerequisites
* Python 3.11+
* MongoDB 6.0+ (Tested against MongoDB 7.0 / Atlas M0)

## Quick Start

1. **Install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows PowerShell: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   Create a local `.env` file (or set system environment variables):
   ```env
   MONGO_URI=mongodb://localhost:27017
   MONGO_DB=attendance_db
   ```
   *Note: Real environment variables take priority over `.env`.*

3. **Run local verification test suite:**
   ```bash
   python test_suite.py
   ```

4. **Run 5-round live Atlas verification mission:**
   ```bash
   python verify_5_rounds.py
   ```

5. **Seed sample data (optional):**
   ```bash
   python sample_seed.py
   ```

6. **Start the API:**

   ```bash
   uvicorn app.main:app --port 8000 --reload
   ```

## Interactive API Documentation
* Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
* OpenAPI Spec: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

## Submission Files
* `app/main.py`: Consolidated, production-ready FastAPI service.
* `requirements.txt`: Minimal required Python dependencies.
* `REVIEW.md`: Comprehensive audit of starter defects with reproduction steps.
* `DECISIONS.md`: Architectural decisions regarding indexes, concurrency, ranking, and scale.
* `test_suite.py`: Comprehensive 49-test unit, contract, mongomock, and live Atlas integration test suite.
* `verify_5_rounds.py`: 5-round E2E verification mission script with automated test data cleanup.

