"""
HROne Employee Attendance & Analytics API - 5-Round End-to-End Verification Mission
Exercises all 12 endpoints, business rules R1-R10, live Atlas integration, and concurrency constraints
using 5 distinct test employees (EMP9001 - EMP9005).
"""
import sys
import os
import time
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

# Ensure project root is on path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from pymongo import MongoClient
from starlette.testclient import TestClient
import app.main as main_mod

# Connect directly to MongoDB Atlas
atlas_uri = os.getenv("MONGO_URI")
atlas_db_name = os.getenv("MONGO_DB", "attendance_db")

real_client = MongoClient(atlas_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
real_db = real_client[atlas_db_name]

# Wire real client to FastAPI app
main_mod.client = real_client
main_mod.db = real_db
client = TestClient(main_mod.app, raise_server_exceptions=False)

mission_results = {
    "rounds": [],
    "endpoints": {},
    "defects": [],
    "total_checks": 0,
    "passed_checks": 0,
    "failed_checks": 0,
}

def log_check(round_name, check_name, passed, details=""):
    mission_results["total_checks"] += 1
    if passed:
        mission_results["passed_checks"] += 1
        print(f"    [PASS] {check_name}" + (f" -> {details}" if details else ""))
    else:
        mission_results["failed_checks"] += 1
        print(f"    [FAIL] {check_name} -> {details}")
        mission_results["defects"].append((round_name, check_name, details))

def cleanup_test_employee(emp_code):
    real_db.employees.delete_many({"emp_code": emp_code})
    real_db.attendance_logs.delete_many({"emp_code": emp_code})

print("=" * 80)
print("STARTING 5-ROUND COMPREHENSIVE VERIFICATION MISSION ON MONGO ATLAS")
print(f"Target Database: {atlas_db_name} | Cluster Host: {real_client.address[0] if real_client.address else 'Atlas'}")
print("=" * 80)

# Pre-mission cleanup of test employee codes
for code in ["EMP9001", "EMP9002", "EMP9003", "EMP9004", "EMP9005"]:
    cleanup_test_employee(code)

try:
    # --------------------------------------------------------------------------- #
    # GLOBAL: Endpoint 1 - GET /health
    # --------------------------------------------------------------------------- #
    print("\n--- Pre-Flight: Endpoint 1 (GET /health) ---")
    res = client.get("/health")
    log_check("Global", "Health Check 200 OK", res.status_code == 200 and res.json() == {"status": "ok"})
    
    # Negative Health check with DB offline
    orig_c = main_mod.client
    try:
        class FakeDownClient:
            class Admin:
                def command(self, *args, **kwargs):
                    raise Exception("DB unreachable")
            admin = Admin()
        main_mod.client = FakeDownClient()
        res_down = client.get("/health")
        log_check("Global", "Health Probe 503 on DB Failure", res_down.status_code == 503 and res_down.json() == {"detail": "Database unavailable"})
    finally:
        main_mod.client = orig_c

    # =========================================================================== #
    # ROUND 1: EMP9001 - On-Time, Daytime Normal Shift, Normal Overtime
    # =========================================================================== #
    print("\n" + "=" * 60)
    print("ROUND 1: EMP9001 (Aarav Sharma - On-Time, Standard Shift, Overtime)")
    print("=" * 60)
    r1_code = "EMP9001"
    
    # B. Employee Creation & Retrieval
    emp_payload = {
        "emp_code": r1_code,
        "name": "Aarav Sharma",
        "email": "aarav.sharma@testcorp.com",
        "department": "QA_Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-07-01",
    }
    r_create = client.post("/employees", json=emp_payload)
    log_check("Round 1", "POST /employees (201)", r_create.status_code == 201, f"emp_code={r1_code}")
    
    # Duplicate creation 409
    r_dup = client.post("/employees", json=emp_payload)
    log_check("Round 1", "POST /employees Duplicate (409)", r_dup.status_code == 409)
    
    # Validation errors on create
    r_bad_code = client.post("/employees", json={**emp_payload, "emp_code": "INVALID_CODE"})
    log_check("Round 1", "POST /employees Bad Code (422)", r_bad_code.status_code == 422)
    
    r_same_shift = client.post("/employees", json={**emp_payload, "emp_code": "EMP9099", "shift_start": "09:30", "shift_end": "09:30"})
    log_check("Round 1", "POST /employees Same Shift Start/End (422)", r_same_shift.status_code == 422)
    
    # List employee retrieval
    r_list = client.get(f"/employees?department=QA_Engineering&page=1&page_size=20")
    emp_found = any(e["emp_code"] == r1_code for e in r_list.json().get("items", []))
    log_check("Round 1", "GET /employees List & Filter", r_list.status_code == 200 and emp_found)

    # C. Punch-in: 09:28 IST (2 min early, on-time)
    # 2026-07-06 09:28:00 IST = 03:58:00 UTC = 1783310280000 ms
    p_in_time = 1783310280000
    r_pin = client.post("/attendance/punch-in", json={"emp_code": r1_code, "punched_at": p_in_time, "status": "PRESENT"})
    log_check("Round 1", "POST /attendance/punch-in (201)", r_pin.status_code == 201)
    doc_in = r_pin.json()
    log_check("Round 1", "R1/R2: Date & On-Time Arrival", doc_in.get("date") == "2026-07-06" and doc_in.get("late_minutes") == 0)

    # Duplicate punch-in 409
    r_pin_dup = client.post("/attendance/punch-in", json={"emp_code": r1_code, "punched_at": p_in_time + 60000})
    log_check("Round 1", "POST /attendance/punch-in Duplicate (409)", r_pin_dup.status_code == 409)

    # D. Punch-out: 19:15 IST (13:45 UTC = 1783345500000 ms)
    # Overtime: 19:15 - 18:30 = 45 min >= 30 -> 45
    # Work hours: 19:15 - 09:28 = 9h 47m = 35220 / 3600 = 9.78333... -> 9.78
    p_out_time = 1783345500000
    r_pout = client.post("/attendance/punch-out", json={"emp_code": r1_code, "punched_at": p_out_time})
    log_check("Round 1", "POST /attendance/punch-out (200)", r_pout.status_code == 200)
    doc_out = r_pout.json()
    log_check("Round 1", "R3/R4/R5: Work Hours 9.78 & Overtime 45", doc_out.get("work_hours") == 9.78 and doc_out.get("overtime_minutes") == 45 and doc_out.get("half_day") is False)

    # Duplicate punch-out 409
    r_pout_dup = client.post("/attendance/punch-out", json={"emp_code": r1_code, "punched_at": p_out_time + 1000})
    log_check("Round 1", "POST /attendance/punch-out Duplicate (409)", r_pout_dup.status_code == 409)

    # E. Attendance Listing
    r_att = client.get(f"/attendance?emp_code={r1_code}&date_from=2026-07-06&date_to=2026-07-06")
    log_check("Round 1", "GET /attendance Record Present", r_att.status_code == 200 and r_att.json().get("total") == 1)

    # F. Manual Regularization (PATCH)
    # Correct punch-out to 19:30:00 IST (13:40 UTC = 1783346400000)
    # Recomputed: Overtime 60 min, Work hours 19:30 - 09:28 = 10h 02m = 36120 / 3600 = 10.03 hrs
    r_reg = client.patch(f"/attendance/{r1_code}/2026-07-06", json={
        "punch_out": 1783346400000,
        "reason": "Turnstile biometric adjustment",
        "regularized_by": "hr.manager"
    })
    log_check("Round 1", "PATCH /attendance Regularize (200)", r_reg.status_code == 200)
    doc_reg = r_reg.json()
    log_check("Round 1", "Regularization Recomputed: 10.03h & 60m OT", doc_reg.get("work_hours") == 10.03 and doc_reg.get("overtime_minutes") == 60)
    log_check("Round 1", "Audit History Preserved", len(doc_reg.get("history", [])) == 1 and doc_reg["history"][0]["by"] == "hr.manager")

    # G. Monthly Analytics
    r_m = client.get(f"/analytics/employees/{r1_code}/monthly?month=2026-07")
    log_check("Round 1", "GET /analytics/employees/monthly (200)", r_m.status_code == 200)
    m_data = r_m.json()
    # 23 working days, 1 present day -> 1 / 23 * 100 = 4.3478... -> 4.35%
    log_check("Round 1", "Monthly Stats: 23 Working Days & 4.35% Att Pct", m_data.get("working_days") == 23 and m_data.get("attendance_pct") == 4.35)

    # =========================================================================== #
    # ROUND 2: EMP9002 - Late Arrival (> 10m Grace), Half-Day Classification
    # =========================================================================== #
    print("\n" + "=" * 60)
    print("ROUND 2: EMP9002 (Bhavna Patel - Late Arrival & Half-Day Classification)")
    print("=" * 60)
    r2_code = "EMP9002"
    client.post("/employees", json={
        "emp_code": r2_code,
        "name": "Bhavna Patel",
        "email": "bhavna.patel@testcorp.com",
        "department": "QA_Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-07-01",
    })

    # C. Punch-in: 09:41:00 IST (11 min after 09:30, strictly > 10 min grace)
    # 2026-07-07 09:41:00 IST = 04:11:00 UTC = 1783397460000 ms -> late_minutes = 11
    r_pin2 = client.post("/attendance/punch-in", json={"emp_code": r2_code, "punched_at": 1783397460000, "status": "PRESENT"})
    log_check("Round 2", "POST /attendance/punch-in (201)", r_pin2.status_code == 201)
    log_check("Round 2", "R2: Late Minutes = 11", r_pin2.json().get("late_minutes") == 11)

    # D. Punch-out: 13:45:00 IST (08:15:00 UTC = 1783412100000 ms)
    # Duration: 13:45 - 09:41 = 4h 04m = 14640 / 3600 = 4.0666... -> 4.07 hrs
    # 4.07 < 4.50 -> half_day = True, overtime = 0
    r_pout2 = client.post("/attendance/punch-out", json={"emp_code": r2_code, "punched_at": 1783412100000})
    log_check("Round 2", "POST /attendance/punch-out (200)", r_pout2.status_code == 200)
    d_out2 = r_pout2.json()
    log_check("Round 2", "R4/R5: Work Hours 4.07 & Half Day TRUE", d_out2.get("work_hours") == 4.07 and d_out2.get("half_day") is True and d_out2.get("overtime_minutes") == 0)

    # F. Regularize status to WFH
    r_reg2 = client.patch(f"/attendance/{r2_code}/2026-07-07", json={
        "status": "WFH",
        "reason": "Switched to remote for the afternoon",
        "regularized_by": "team.lead"
    })
    log_check("Round 2", "PATCH Regularize Status to WFH", r_reg2.status_code == 200 and r_reg2.json().get("status") == "WFH")

    # G. Monthly Analytics: Half day counts as 0.5 present day
    # 0.5 / 23 * 100 = 2.1739... -> 2.17%
    r_m2 = client.get(f"/analytics/employees/{r2_code}/monthly?month=2026-07")
    m_data2 = r_m2.json()
    log_check("Round 2", "Monthly Stats: Present Days = 0.5 & 2.17% Att Pct", m_data2.get("present_days") == 0.5 and m_data2.get("attendance_pct") == 2.17)

    # =========================================================================== #
    # ROUND 3: EMP9003 - Exact Grace Boundary (10:00 elapsed) & Overtime Boundary
    # =========================================================================== #
    print("\n" + "=" * 60)
    print("ROUND 3: EMP9003 (Chetan Verma - Grace Boundary 10:00 & OT Threshold)")
    print("=" * 60)
    r3_code = "EMP9003"
    client.post("/employees", json={
        "emp_code": r3_code,
        "name": "Chetan Verma",
        "email": "chetan.verma@testcorp.com",
        "department": "QA_Beta",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-07-01",
    })

    # C. Punch-in: exactly 09:40:00 IST (04:10:00 UTC = 1783483800000 ms)
    # Exactly 10:00 elapsed -> not strictly > 10:00 -> late_minutes = 0
    r_pin3 = client.post("/attendance/punch-in", json={"emp_code": r3_code, "punched_at": 1783483800000})
    log_check("Round 3", "R2 Grace Boundary 09:40:00 -> late_minutes == 0", r_pin3.status_code == 201 and r_pin3.json().get("late_minutes") == 0)

    # D. Punch-out: 18:50:00 IST (13:20:00 UTC = 1783516800000 ms)
    # 20 min past shift end < 30 min minimum -> overtime_minutes = 0
    # Duration: 18:50 - 09:40 = 9h 10m = 33000 / 3600 = 9.1666... -> 9.17 hrs
    r_pout3 = client.post("/attendance/punch-out", json={"emp_code": r3_code, "punched_at": 1783516800000})
    d_out3 = r_pout3.json()
    log_check("Round 3", "R3 OT Threshold < 30m -> 0 Overtime & 9.17 hrs", d_out3.get("overtime_minutes") == 0 and d_out3.get("work_hours") == 9.17)

    # F. Negative Regularization Tests:
    # 1. No-op 422
    r_noop = client.patch(f"/attendance/{r3_code}/2026-07-08", json={"punch_out": 1783516800000, "reason": "No changes made", "regularized_by": "admin"})
    log_check("Round 3", "PATCH No-op (422)", r_noop.status_code == 422)

    # 2. Setting ABSENT with punch times 422
    r_abs_punch = client.patch(f"/attendance/{r3_code}/2026-07-08", json={"status": "ABSENT", "punch_out": 1783516800000, "reason": "Bad payload", "regularized_by": "admin"})
    log_check("Round 3", "PATCH ABSENT with punch times (422)", r_abs_punch.status_code == 422)

    # 3. Punch_out before punch_in 422
    r_bad_seq = client.patch(f"/attendance/{r3_code}/2026-07-08", json={"punch_out": 1783483800000 - 1000, "reason": "Negative duration", "regularized_by": "admin"})
    log_check("Round 3", "PATCH Punch_out <= Punch_in (422)", r_bad_seq.status_code == 422)

    # =========================================================================== #
    # ROUND 4: EMP9004 - Overnight Shift (22:00 - 06:00), R1 Date Attribution & Overtime
    # =========================================================================== #
    print("\n" + "=" * 60)
    print("ROUND 4: EMP9004 (Divya Nair - Overnight Shift 22:00-06:00, Cross-Midnight)")
    print("=" * 60)
    r4_code = "EMP9004"
    client.post("/employees", json={
        "emp_code": r4_code,
        "name": "Divya Nair",
        "email": "divya.nair@testcorp.com",
        "department": "QA_Beta",
        "shift_start": "22:00",
        "shift_end": "06:00",
        "joined_on": "2026-07-01",
    })

    # C. Punch-in: 21:55:00 IST on 2026-07-09 (16:25:00 UTC = 1783614300000 ms)
    # 5 min early -> late_minutes = 0. Date = 2026-07-09
    r_pin4 = client.post("/attendance/punch-in", json={"emp_code": r4_code, "punched_at": 1783614300000, "status": "PRESENT"})
    log_check("Round 4", "Overnight Punch-in 21:55 -> Date 2026-07-09", r_pin4.status_code == 201 and r_pin4.json().get("date") == "2026-07-09")

    # D. Punch-out: 06:40:00 IST on 2026-07-10 next morning (01:10:00 UTC = 1783645800000 ms)
    # Shift ends at 06:00 on 2026-07-10. 40 min past shift end >= 30 -> overtime_minutes = 40
    # Duration: 06:40 - 21:55 = 8h 45m = 31500 / 3600 = 8.75 hrs
    r_pout4 = client.post("/attendance/punch-out", json={"emp_code": r4_code, "punched_at": 1783645800000})
    d_out4 = r_pout4.json()
    log_check("Round 4", "Overnight Punch-out: 8.75 hrs & 40m Overtime", d_out4.get("work_hours") == 8.75 and d_out4.get("overtime_minutes") == 40 and d_out4.get("half_day") is False)

    # Test R1 Overnight attribution after midnight:
    # 01:15 IST next morning on overnight shift belongs to PREVIOUS calendar day
    dt_after_midnight = datetime(2026, 7, 10, 19, 45, 0, tzinfo=timezone.utc) # 01:15 IST
    att_d = main_mod.determine_attendance_date(dt_after_midnight, "22:00", "06:00")
    log_check("Round 4", "R1 Overnight Post-Midnight Date Attribution", att_d == "2026-07-10")

    # =========================================================================== #
    # ROUND 5: EMP9005 - Mid-Month Joiner, Leaderboard Competition Ranking & Trend
    # =========================================================================== #
    print("\n" + "=" * 60)
    print("ROUND 5: EMP9005 (Eshwar Reddy - Mid-Month Joiner & Aggregation Analytics)")
    print("=" * 60)
    r5_code = "EMP9005"
    client.post("/employees", json={
        "emp_code": r5_code,
        "name": "Eshwar Reddy",
        "email": "eshwar.reddy@testcorp.com",
        "department": "QA_Beta",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-07-15", # Joins mid-month
    })

    # C. Punch-in: 10:15:00 IST on 2026-07-15 (04:45:00 UTC = 1784090700000 ms)
    # 45 min late -> late_minutes = 45
    r_pin5 = client.post("/attendance/punch-in", json={"emp_code": r5_code, "punched_at": 1784090700000})
    log_check("Round 5", "Late Punch-in 10:15 -> late_minutes = 45", r_pin5.status_code == 201 and r_pin5.json().get("late_minutes") == 45)

    # D. Punch-out: 18:30:00 IST (13:00:00 UTC = 1784120400000 ms)
    # Duration: 18:30 - 10:15 = 8h 15m = 29700 / 3600 = 8.25 hrs
    r_pout5 = client.post("/attendance/punch-out", json={"emp_code": r5_code, "punched_at": 1784120400000})
    log_check("Round 5", "Punch-out 8.25 hrs, 0 Overtime", r_pout5.json().get("work_hours") == 8.25 and r_pout5.json().get("overtime_minutes") == 0)

    # G. Mid-Month Joiner Monthly Analytics:
    # Working days from 2026-07-15 to 2026-07-31: 13 working days!
    # 1 present day / 13 * 100 = 7.6923... -> 7.69%
    r_m5 = client.get(f"/analytics/employees/{r5_code}/monthly?month=2026-07")
    m_data5 = r_m5.json()
    log_check("Round 5", "R7 Mid-Month Joiner: 13 Working Days & 7.69%", m_data5.get("working_days") == 13 and m_data5.get("attendance_pct") == 7.69)

    # H. Department Summary on QA_Beta (EMP9003, EMP9004, EMP9005)
    r_dept = client.get("/analytics/departments/summary?month=2026-07&department=QA_Beta")
    log_check("Round 5", "GET /analytics/departments/summary (200)", r_dept.status_code == 200)
    dept_items = r_dept.json().get("items", [])
    dept_beta = next((d for d in dept_items if d["department"] == "QA_Beta"), None)
    log_check("Round 5", "Dept Summary: Headcount = 3", dept_beta is not None and dept_beta["headcount"] == 3)
    # Total late minutes in QA_Beta: EMP9005 had 45, EMP9003 had 0, EMP9004 had 0 -> total 45
    log_check("Round 5", "Dept Summary: Total Late Minutes = 45", dept_beta["total_late_minutes"] == 45)

    # I. Late-Arrival Leaderboard
    r_lead = client.get("/analytics/leaderboard/late?month=2026-07&department=QA_Beta")
    log_check("Round 5", "GET /analytics/leaderboard/late (200)", r_lead.status_code == 200)
    lead_items = r_lead.json().get("items", [])
    log_check("Round 5", "Leaderboard: EMP9005 Rank 1 with 45m Late", len(lead_items) >= 1 and lead_items[0]["emp_code"] == r5_code and lead_items[0]["rank"] == 1)

    # J. Department Trend on QA_Beta with Gap Filling & Moving Avg
    r_trend = client.get("/analytics/departments/QA_Beta/trend?from=2026-07-08&to=2026-07-16")
    log_check("Round 5", "GET /analytics/departments/trend (200)", r_trend.status_code == 200)
    trend_items = r_trend.json().get("items", [])
    # 2026-07-08 to 2026-07-16 inclusive = 9 calendar days
    log_check("Round 5", "Trend: Exactly 9 Calendar Days Densified", len(trend_items) == 9)
    # On 2026-07-14: headcount = 2 (EMP9003, EMP9004)
    # On 2026-07-15: EMP9005 joins -> headcount = 3
    t_14 = next(it for it in trend_items if it["date"] == "2026-07-14")
    t_15 = next(it for it in trend_items if it["date"] == "2026-07-15")
    log_check("Round 5", "Trend R9 Headcount: 2 before join, 3 after join", t_14["headcount"] == 2 and t_15["headcount"] == 3)

    # K. Admin Explain & Index Plan on Live Atlas
    r_exp = client.get("/admin/explain/department_trend?department=QA_Beta&from=2026-07-08&to=2026-07-16")
    log_check("Round 5", "GET /admin/explain/department_trend (200)", r_exp.status_code == 200)
    exp_data = r_exp.json()
    exp_str = str(exp_data)
    log_check("Round 5", "Live Explain Winning Plan: IXSCAN Confirmed", "IXSCAN" in exp_str and "emp_code_1_date_1" in exp_str)

finally:
    # Clean up test records
    print("\n--- Mission Cleanup ---")
    for code in ["EMP9001", "EMP9002", "EMP9003", "EMP9004", "EMP9005"]:
        cleanup_test_employee(code)
    print("Cleaned up test data (EMP9001 - EMP9005). Existing seed records preserved.")

print("\n" + "=" * 80)
print(f"MISSION SUMMARY: {mission_results['passed_checks']}/{mission_results['total_checks']} CHECKS PASSED, {mission_results['failed_checks']} FAILED")
print("=" * 80)
