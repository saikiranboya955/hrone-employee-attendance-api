<h1 style="color:#2E86C1;">🚀 Employee Attendance & Analytics API</h1>
<p><b>FastAPI + MongoDB</b> backend for employee attendance tracking, manual regularization with audit history, and MongoDB aggregation analytics.<br>
Built strictly against <i>HROne Engineering Assignment Contract v2.0</i>.</p>

<h2 style="color:#27AE60;">⚙️ Tech Stack</h2>
<table>
  <tr><th>Component</th><th>Technology</th><th>Purpose</th></tr>
  <tr><td>Runtime</td><td>Python 3.11+</td><td>Backend service execution</td></tr>
  <tr><td>Framework</td><td>FastAPI + Uvicorn</td><td>REST API & OpenAPI 3.0 docs</td></tr>
  <tr><td>Database</td><td>MongoDB 6.0+ (PyMongo)</td><td>Document store & aggregation pipelines</td></tr>
  <tr><td>Validation</td><td>Pydantic v2</td><td>Strict contract & timestamp validation</td></tr>
</table>

<h2 style="color:#E67E22;">📌 API Endpoints</h2>
<table>
  <tr><th>Method</th><th>Endpoint</th><th>Description</th></tr>
  <tr><td>GET</td><td>/health</td><td>Health & DB readiness probe (200 / 503)</td></tr>
  <tr><td>POST</td><td>/employees</td><td>Create employee (unique <code>emp_code</code>)</td></tr>
  <tr><td>GET</td><td>/employees</td><td>List employees (paginated, department filter)</td></tr>
  <tr><td>POST</td><td>/attendance/punch-in</td><td>Punch-in (R1 IST date, R2 late minutes)</td></tr>
  <tr><td>POST</td><td>/attendance/punch-out</td><td>Punch-out (R3 overtime, R4 hours, R5 half-day)</td></tr>
  <tr><td>GET</td><td>/attendance</td><td>List attendance (paginated, date/status filter)</td></tr>
  <tr><td>PATCH</td><td>/attendance/{emp_code}/{date}</td><td>Regularize record with before/after audit history</td></tr>
  <tr><td>GET</td><td>/analytics/employees/{emp_code}/monthly</td><td>Employee monthly analytics (R7 working days)</td></tr>
  <tr><td>GET</td><td>/analytics/departments/summary</td><td>Department summary (R9 retains zero-log headcount)</td></tr>
  <tr><td>GET</td><td>/analytics/leaderboard/late</td><td>Late leaderboard with competition ranking (<code>$rank</code>)</td></tr>
  <tr><td>GET</td><td>/analytics/departments/{department}/trend</td><td>Daily series with gap-filling (<code>$densify</code>) & 7-day MA</td></tr>
  <tr><td>GET</td><td>/admin/explain/{endpoint}</td><td>Explain plan (verifies <code>IXSCAN</code> & zero <code>COLLSCAN</code>)</td></tr>
</table>

<h2 style="color:#27AE60;">🛠️ Setup & Configuration</h2>
<pre>
# 1. Clone & create virtualenv
git clone https://github.com/saikiranboya955/hrone-employee-attendance-api.git
cd hrone-employee-attendance-api
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Environment variables (.env)
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
</pre>

<h2 style="color:#C0392B;">▶️ Run</h2>
<pre>
uvicorn app.main:app --port 8000
</pre>
<ul>
  <li><a href="http://localhost:8000/docs">Interactive Swagger Docs</a> | <a href="http://localhost:8000/openapi.json">OpenAPI Spec</a></li>
  <li><i>Optional sample seed:</i> <code>python sample_seed.py</code></li>
</ul>

<h2 style="color:#16A085;">🧪 Testing</h2>
<pre>
python test_suite.py
</pre>
<p><b>Result:</b> ✅ <code>54 passed, 0 failed, 0 unverified</code><br>
<i>Covers unit math (R1–R8), contract validation, mock DB concurrency, and live Atlas integration & explain plans.</i></p>

<h2 style="color:#34495E;">📂 Project Structure</h2>
<pre>
hrone-employee-attendance-api/
├── app/
│   └── main.py              # FastAPI app, models, endpoints & aggregation pipelines
├── sample_data/             # Extended JSON sample records
├── DATA_MODEL.md            # Schema, BSON types & document shapes
├── DECISIONS.md             # Key design decisions & 100x scale strategy
├── openapi.yaml             # Authoritative contract specification
├── requirements.txt         # Dependencies
├── REVIEW.md                # 23 starter defects audit log & fixes
├── sample_seed.py           # Database seeder utility
├── test_suite.py            # Unified 54-test verification suite
└── README.md
</pre>
