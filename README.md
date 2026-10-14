<h1 style="color:#2E86C1;">🚀 Employee Attendance & Analytics API</h1>
<p><b>FastAPI + MongoDB</b> backend for employee attendance tracking, regularization, audit history, and analytics.<br>
Developed for <i>HROne Engineering Assignment Contract v2.0</i>.</p>

<h2 style="color:#27AE60;">⚙️ Tech Stack</h2>
<table>
  <tr><th>Technology</th><th>Usage</th></tr>
  <tr><td>Python</td><td>Backend development</td></tr>
  <tr><td>FastAPI</td><td>REST API</td></tr>
  <tr><td>MongoDB</td><td>Database & aggregation</td></tr>
  <tr><td>PyMongo</td><td>Database operations</td></tr>
  <tr><td>Pydantic</td><td>Request validation</td></tr>
  <tr><td>Uvicorn</td><td>Application server</td></tr>
</table>

<h2 style="color:#E67E22;">📌 API Endpoints</h2>
<table>
  <tr><th>Method</th><th>Endpoint</th><th>Description</th></tr>
  <tr><td>GET</td><td>/health</td><td>Check service health</td></tr>
  <tr><td>POST</td><td>/employees</td><td>Create employee</td></tr>
  <tr><td>GET</td><td>/employees</td><td>List employees</td></tr>
  <tr><td>POST</td><td>/attendance/punch-in</td><td>Punch-in</td></tr>
  <tr><td>POST</td><td>/attendance/punch-out</td><td>Punch-out</td></tr>
  <tr><td>GET</td><td>/attendance</td><td>View attendance</td></tr>
  <tr><td>PATCH</td><td>/attendance/{emp_code}/{date}</td><td>Correct attendance</td></tr>
  <tr><td>GET</td><td>/analytics/employees/{emp_code}/monthly</td><td>Employee monthly analytics</td></tr>
  <tr><td>GET</td><td>/analytics/departments/summary</td><td>Department summary</td></tr>
  <tr><td>GET</td><td>/analytics/leaderboard/late</td><td>Late arrivals leaderboard</td></tr>
</table>

<h2 style="color:#9B59B6;">⚡ Setup</h2>
<pre>
git clone https://github.com/saikiranboya955/hrone-employee-attendance-api.git
cd hrone-employee-attendance-api
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
</pre>

<h3 style="color:#F39C12;">.env file</h3>
<pre>
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
</pre>

<h2 style="color:#C0392B;">▶️ Run</h2>
<pre>
uvicorn app.main:app --port 8000
</pre>
<ul>
  <li><a href="http://localhost:8000/docs">Swagger UI</a></li>
  <li><a href="http://localhost:8000/openapi.json">OpenAPI Spec</a></li>
</ul>

<h2 style="color:#16A085;">🧪 Testing</h2>
<pre>
python test_suite.py
</pre>
<p><b>Result:</b> ✅ 54 passed, 0 failed</p>

<h2 style="color:#34495E;">📂 Project Structure</h2>
<pre>
hrone-employee-attendance-api/
├── app/
│   └── main.py
├── sample_data/
│   ├── employees.json
│   └── attendance_logs.json
├── DATA_MODEL.md
├── DECISIONS.md
├── openapi.yaml
├── requirements.txt
├── REVIEW.md
├── sample_seed.py
├── test_suite.py
└── README.md
</pre>
