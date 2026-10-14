<h1 style="color:#2E86C1;">📋 Starter Code Review (REVIEW.md)</h1>
<p>Audit log of defects identified and resolved in starter <code>app/main.py</code> against <i>HROne Contract v2.0</i>:</p>

<table>
  <thead>
    <tr style="background-color:#F2F4F4;">
      <th>#</th>
      <th>Where (Function / Lines)</th>
      <th>Defect</th>
      <th>Failing Input / Symptom</th>
      <th>How It Was Fixed</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><b>1</b></td>
      <td><code>compute_late_minutes</code> (33–37)</td>
      <td>Timezone mismatch; applied IST hour directly onto UTC datetime via <code>.replace()</code>.</td>
      <td>Punch-in at 10:05 IST (04:35 UTC) yielded -4h 55m instead of 35 late minutes.</td>
      <td>Converted <code>punch_in</code> to IST and constructed shift start in IST.</td>
    </tr>
    <tr>
      <td><b>2</b></td>
      <td><code>compute_late_minutes</code> (36–37)</td>
      <td>Truncated elapsed seconds before checking <code>&gt; 10</code> grace period (R2).</td>
      <td>Punch-in at <code>09:40:01</code> for <code>09:30</code> shift gave <code>0</code> instead of <code>10</code>.</td>
      <td>Evaluated <code>elapsed_seconds &gt; 600</code> before floor division.</td>
    </tr>
    <tr>
      <td><b>3</b></td>
      <td><code>compute_work_hours</code> (41)</td>
      <td>Python <code>round()</code> uses banker's rounding (round half to even) instead of half-up (R4).</td>
      <td>Work duration of 2.525 hours rounded down to <code>2.52</code> instead of <code>2.53</code>.</td>
      <td>Implemented <code>decimal.Decimal</code> with explicit <code>ROUND_HALF_UP</code>.</td>
    </tr>
    <tr>
      <td><b>4</b></td>
      <td><code>compute_overtime</code> (44–47)</td>
      <td>Missing 30-minute qualification threshold (R3).</td>
      <td>Punch-out 15 min after shift end returned <code>15</code> overtime minutes instead of <code>0</code>.</td>
      <td>Returned overtime only if <code>diff_minutes &gt;= 30</code>, otherwise <code>0</code>.</td>
    </tr>
    <tr>
      <td><b>5</b></td>
      <td><code>compute_overtime</code> (44–47)</td>
      <td>Overnight shifts (<code>shift_end &lt;= shift_start</code>) evaluated end on same calendar date.</td>
      <td>22:00–06:00 shift with 06:40 punch-out computed &gt; 24 hours of overtime.</td>
      <td>Added +1 calendar day to shift end when <code>shift_end &lt;= shift_start</code>.</td>
    </tr>
    <tr>
      <td><b>6</b></td>
      <td><code>compute_overtime</code> (46)</td>
      <td>Naive and timezone-aware datetime subtraction.</td>
      <td>Calling with naive DB datetime raised <code>TypeError</code>.</td>
      <td>Enforced UTC awareness and converted both datetimes to IST.</td>
    </tr>
    <tr>
      <td><b>7</b></td>
      <td><code>health</code> (72–74)</td>
      <td>Hardcoded <code>{"status": "ok"}</code> without testing MongoDB connectivity.</td>
      <td>Returned <code>200</code> when MongoDB was stopped instead of required <code>503</code>.</td>
      <td>Added <code>client.admin.command('ping')</code> inside try/except block.</td>
    </tr>
    <tr>
      <td><b>8</b></td>
      <td><code>create_employee</code> (79–83)</td>
      <td>Check-then-insert race condition; lacked DB unique index on <code>emp_code</code>.</td>
      <td>Concurrent <code>POST /employees</code> with duplicate <code>emp_code</code> created duplicates.</td>
      <td>Added unique index on <code>employees.emp_code</code>; caught duplicate key -&gt; <code>409</code>.</td>
    </tr>
    <tr>
      <td><b>9</b></td>
      <td><code>create_employee</code> (82)</td>
      <td><code>created_at</code> stored as naive local time and returned as ISO string.</td>
      <td>Returned ISO string violating OpenAPI integer epoch milliseconds contract.</td>
      <td>Stored UTC BSON datetime truncated to seconds; returned integer epoch ms.</td>
    </tr>
    <tr>
      <td><b>10</b></td>
      <td><code>EmployeeIn</code> (53–60)</td>
      <td>Missing schema constraints; accepted identical shift start and end times.</td>
      <td><code>shift_start: "09:30", shift_end: "09:30"</code> returned <code>201</code> instead of <code>422</code>.</td>
      <td>Added regex patterns and validator requiring <code>shift_start != shift_end</code>.</td>
    </tr>
    <tr>
      <td><b>11</b></td>
      <td><code>list_employees</code> (93)</td>
      <td>Pagination offset formula off-by-one: <code>skip = page * page_size</code>.</td>
      <td><code>page=1&amp;page_size=20</code> skipped items 1–20 and returned 21–40.</td>
      <td>Corrected offset formula to <code>skip = (page - 1) * page_size</code>.</td>
    </tr>
    <tr>
      <td><b>12</b></td>
      <td><code>list_employees</code> (94)</td>
      <td>Total count ignored active filters, executing <code>count_documents({})</code> on collection.</td>
      <td><code>GET /employees?department=Sales</code> returned total company headcount.</td>
      <td>Updated to <code>db.employees.count_documents(q)</code>.</td>
    </tr>
    <tr>
      <td><b>13</b></td>
      <td><code>list_employees</code> (95)</td>
      <td>Missing deterministic sort order mandated by contract.</td>
      <td>Returned documents in natural MongoDB insertion order.</td>
      <td>Added <code>.sort("emp_code", ASCENDING)</code>.</td>
    </tr>
    <tr>
      <td><b>14</b></td>
      <td><code>punch_in</code> (101)</td>
      <td>Unchecked employee lookup result.</td>
      <td>Calling <code>/punch-in</code> with unregistered <code>emp_code</code> raised unhandled 500.</td>
      <td>Added check: <code>if not emp: raise HTTPException(404, "Employee not found")</code>.</td>
    </tr>
    <tr>
      <td><b>15</b></td>
      <td><code>punch_in</code> (104–105)</td>
      <td>Check-then-insert race condition on attendance records.</td>
      <td>Concurrent punch-ins for same employee/date both returned <code>201</code>.</td>
      <td>Added unique compound index <code>attendance_logs.(emp_code, date)</code> -&gt; <code>409</code>.</td>
    </tr>
    <tr>
      <td><b>16</b></td>
      <td><code>punch_in</code> (102–103)</td>
      <td>Attendance date ignored IST and overnight shift attribution (R1).</td>
      <td>Overnight punch-in at 01:15 IST not attributed to shift start calendar date.</td>
      <td>Attributed pre-shift-end overnight punches to previous calendar day.</td>
    </tr>
    <tr>
      <td><b>17</b></td>
      <td><code>punch_in</code> (118–121)</td>
      <td>Returned MongoDB internal document ID (<code>doc["id"] = str(inserted_id)</code>).</td>
      <td>Response schema contained unexpected <code>"id"</code> key and raw datetimes.</td>
      <td>Formatted document strictly to <code>AttendanceRecord</code> schema without <code>_id</code>.</td>
    </tr>
    <tr>
      <td><b>18</b></td>
      <td><code>list_attendance</code> (144–147)</td>
      <td>Loaded entire collection into Python memory with <code>list(find())</code>.</td>
      <td>Triggered out-of-memory pressure and request timeouts on ~100k records.</td>
      <td>Offloaded filtering, sorting (<code>date</code> desc, <code>emp_code</code> asc), and paging to DB cursor.</td>
    </tr>
    <tr>
      <td><b>19</b></td>
      <td><code>list_attendance</code> (136–141)</td>
      <td>Missing date range order validation (<code>date_from &gt; date_to</code>).</td>
      <td>Querying <code>date_from=2026-07-10&amp;date_to=2026-07-01</code> returned <code>200</code> with empty list.</td>
      <td>Added explicit check raising <code>HTTPException(422)</code>.</td>
    </tr>
    <tr>
      <td><b>20</b></td>
      <td><code>build_department_trend_pipeline</code></td>
      <td>Native <code>$round</code> banker's rounding and float precision drift on ties (R8).</td>
      <td>Tie boundary <code>0.06245</code> rounded down to <code>0.0624</code> with native <code>$round</code>.</td>
      <td>Replaced with exact base-10 Decimal128 conversion in aggregation pipeline.</td>
    </tr>
    <tr>
      <td><b>21</b></td>
      <td><code>monthly_analytics</code></td>
      <td>Hardcoded calendar end date string <code>f"{month}-31"</code>.</td>
      <td>Queries for Feb, Apr, Jun, Sep, Nov produced invalid calendar date bounds.</td>
      <td>Added dynamic <code>get_month_range()</code> using <code>calendar.monthrange</code>.</td>
    </tr>
    <tr>
      <td><b>22</b></td>
      <td><code>explain_endpoint</code></td>
      <td>Unhandled <code>Decimal128</code> BSON serialization in FastAPI response.</td>
      <td><code>GET /admin/explain/department_trend</code> crashed FastAPI encoder with <code>500</code>.</td>
      <td>Serialized using <code>json.loads(json_util.dumps(raw_explain))</code>.</td>
    </tr>
    <tr>
      <td><b>23</b></td>
      <td><code>build_department_trend_pipeline</code> (Stage 3)</td>
      <td>Unindexed <code>{"$limit": 1}</code> in <code>$unionWith</code> caused <code>COLLSCAN</code> in executionStats.</td>
      <td>Explain output revealed <code>COLLSCAN</code> on <code>employees</code>.</td>
      <td>Added indexed <code>{"$match": {"emp_code": emp_codes[0]}}</code> before <code>$limit</code> -&gt; <code>IXSCAN: True, COLLSCAN: False</code>.</td>
    </tr>
  </tbody>
</table>

---

<h2 style="color:#27AE60;">✅ Examined &amp; Determined NOT to be Defects</h2>
<ul>
  <li><b>Synchronous PyMongo with FastAPI:</b> Using standard <code>def</code> endpoints on FastAPI's external AnyIO worker threadpool prevents event-loop blocking without async complexity.</li>
  <li><b>Environment Variable Fallback:</b> <code>load_dotenv(override=False)</code> correctly prioritizes real injected system environment variables over local <code>.env</code> values.</li>
  <li><b>Pydantic v2 <code>model_dump()</code>:</b> Using <code>model_dump()</code> instead of deprecated <code>dict()</code> is modern and expected in Pydantic v2.</li>
</ul>
