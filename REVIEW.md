<h1 style="color:#2E86C1;">📝 Code Review - Defects in app/main.py</h1>

<table border="1" cellspacing="0" cellpadding="6">
  <tr style="background-color:#34495E; color:#ECF0F1;">
    <th>#</th>
    <th>Where</th>
    <th>What is wrong</th>
    <th>How you'd notice</th>
    <th>Fix Applied</th>
  </tr>
  
  <tr>
    <td>1</td>
    <td>compute_late_minutes</td>
    <td>Timezone mismatch (UTC vs IST)</td>
    <td>Punch-in at 10:05 IST miscalculated</td>
    <td>Converted to IST before diff</td>
  </tr>
  
  <tr style="background-color:#F9E79F;">
    <td>2</td>
    <td>compute_late_minutes</td>
    <td>Grace period boundary defect</td>
    <td>09:40:01 returned 0 late minutes</td>
    <td>Check elapsed_seconds > 600 before flooring</td>
  </tr>
  
  <tr>
    <td>3</td>
    <td>compute_work_hours</td>
    <td>Banker's rounding instead of half-up</td>
    <td>2.525 hrs → 2.52 instead of 2.53</td>
    <td>Used Decimal with ROUND_HALF_UP</td>
  </tr>
  
  <tr style="background-color:#F9E79F;">
    <td>4</td>
    <td>compute_overtime</td>
    <td>Missing 30-min threshold</td>
    <td>15 mins overtime incorrectly counted</td>
    <td>Added >=30 min qualification</td>
  </tr>
  
  <tr>
    <td>5</td>
    <td>compute_overtime</td>
    <td>Fails on overnight shifts</td>
    <td>22:00–06:00 miscalculated >24 hrs</td>
    <td>Shift end rolled to next day</td>
  </tr>
  
  <tr style="background-color:#F9E79F;">
    <td>6</td>
    <td>compute_overtime</td>
    <td>Naive vs aware datetime subtraction</td>
    <td>TypeError on subtraction</td>
    <td>Enforced UTC awareness, converted to IST</td>
  </tr>
  
  <tr>
    <td>7</td>
    <td>health endpoint</td>
    <td>Always returns ok</td>
    <td>DB down still gave 200</td>
    <td>Added MongoDB ping + 503 error</td>
  </tr>
  
  <tr style="background-color:#F9E79F;">
    <td>8</td>
    <td>create_employee</td>
    <td>Race condition, duplicate emp_code</td>
    <td>Concurrent POST created duplicates</td>
    <td>Unique index + DuplicateKeyError handling</td>
  </tr>
  
  <tr>
    <td>9</td>
    <td>create_employee</td>
    <td>created_at stored as naive datetime</td>
    <td>Returned ISO string instead of epoch</td>
    <td>Stored UTC + returned epoch millis</td>
  </tr>
  
  <tr style="background-color:#F9E79F;">
    <td>10</td>
    <td>EmployeeIn model</td>
    <td>Missing regex & validation</td>
    <td>Shift_start == shift_end accepted</td>
    <td>Added regex + validation rules</td>
  </tr>
  
  <!-- Continue pattern for all defects -->
</table>

<h2 style="color:#27AE60;">✅ Non-Defects (Confirmed Correct)</h2>
<ul>
  <li>Synchronous PyMongo usage in FastAPI (threadpool safe)</li>
  <li>Environment variable fallback with <code>load_dotenv()</code></li>
  <li>Pydantic v2 <code>model_dump()</code> usage</li>
</ul>
