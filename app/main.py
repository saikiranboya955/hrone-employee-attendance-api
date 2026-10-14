"""
Employee Attendance & Analytics API
Contract v2.0 - Implementation for HROne Software Engineer Hiring Assessment

Usage:
    uvicorn app.main:app --port 8000
"""

import json
import math
import os
from contextlib import asynccontextmanager
from datetime import date as dt_date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Union

from bson import json_util
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path as FPath, Query, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator, model_validator
import pymongo
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

# Load .env file only if environment variables are not already present (env vars win)
load_dotenv(override=False)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "attendance_db")

client = MongoClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]

IST = timezone(timedelta(hours=5, minutes=30))


# --------------------------------------------------------------------------- #
# Startup & Index Management
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotently create required indexes at startup
    try:
        db.employees.create_index([("emp_code", ASCENDING)], unique=True)
        db.employees.create_index([("department", ASCENDING)])
        db.employees.create_index([("joined_on", ASCENDING)])
        db.employees.create_index([("department", ASCENDING), ("joined_on", ASCENDING)])

        db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", ASCENDING)], unique=True)
        db.attendance_logs.create_index([("date", DESCENDING), ("emp_code", ASCENDING)])
        db.attendance_logs.create_index([("date", ASCENDING), ("late_minutes", ASCENDING)])
        db.attendance_logs.create_index([("status", ASCENDING), ("date", DESCENDING)])
    except Exception:
        # If database is offline at app creation, requests will handle connectivity
        pass
    yield


app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Calculation & Parsing Helpers
# --------------------------------------------------------------------------- #
def parse_epoch_millis(val: Any) -> datetime:
    """Validates integer epoch milliseconds and truncates to whole seconds (R1)."""
    if val is None or isinstance(val, bool) or not isinstance(val, int):
        raise HTTPException(status_code=422, detail="Timestamp must be an integer count of epoch milliseconds")
    if val < 100000000000 or val > 4102444800000:
        raise HTTPException(status_code=422, detail="Timestamp out of range")
    # Truncate to whole seconds per R1
    whole_seconds = val // 1000
    return datetime.fromtimestamp(whole_seconds, tz=timezone.utc)


def to_epoch_millis(dt: Optional[datetime]) -> Optional[int]:
    """Converts a UTC datetime object to integer epoch milliseconds."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def round_half_up(val: Union[float, Decimal, int], decimals: int = 2) -> float:
    """Rounds a number half-up to the given decimal places (R8)."""
    d = Decimal(str(val))
    target = Decimal("10") ** -decimals
    return float(d.quantize(target, rounding=ROUND_HALF_UP))


def mongo_round_half_up(expr: Any, decimals: int = 2) -> Dict[str, Any]:
    """
    MongoDB aggregation expression implementing arithmetic ROUND_HALF_UP (R8).
    Converts numbers to exact Decimal128 via $toString + $toDecimal, avoiding
    both binary floating-point representation drift and arbitrary epsilons.
    Compatible with MongoDB 4.0+.
    """
    factor = 10 ** decimals
    return {
        "$toDouble": {
            "$divide": [
                {
                    "$floor": {
                        "$add": [
                            {"$multiply": [{"$toDecimal": {"$toString": expr}}, factor]},
                            {"$toDecimal": "0.5"},
                        ]
                    }
                },
                factor,
            ]
        }
    }



def determine_attendance_date(punch_in_utc: datetime, shift_start: str, shift_end: str) -> str:
    """
    R1: Attendance date is the IST calendar date of punch_in.
    For overnight shifts (shift_end <= shift_start), if punch-in IST time is earlier than
    shift_end, it belongs to the shift that started on the previous calendar day.
    """
    punch_in_ist = punch_in_utc.astimezone(IST)
    cal_date = punch_in_ist.date()

    if shift_end <= shift_start:
        end_h, end_m = map(int, shift_end.split(":"))
        if (punch_in_ist.hour, punch_in_ist.minute, punch_in_ist.second) < (end_h, end_m, 0):
            cal_date = cal_date - timedelta(days=1)

    return cal_date.isoformat()


def compute_late_minutes(punch_in_utc: datetime, shift_start: str, date_str: str) -> int:
    """
    R2: Grace period is 10 minutes. A punch-in is late only if strictly more than
    10:00 after shift_start. When late, whole minutes (floor) elapsed since shift_start.
    """
    h, m = map(int, shift_start.split(":"))
    start_dt = datetime.fromisoformat(f"{date_str}T{h:02d}:{m:02d}:00").replace(tzinfo=IST)
    punch_in_ist = punch_in_utc.astimezone(IST)
    elapsed_seconds = (punch_in_ist - start_dt).total_seconds()

    if elapsed_seconds > 600:
        return int(elapsed_seconds // 60)
    return 0


def compute_overtime(punch_out_utc: datetime, shift_start: str, shift_end: str, date_str: str) -> int:
    """
    R3: Overtime is whole minutes (floor) between shift_end and punch_out,
    counted only when >= 30; otherwise 0.
    Handles overnight shifts where shift_end falls on the next calendar day.
    """
    h, m = map(int, shift_end.split(":"))
    cal_date = dt_date.fromisoformat(date_str)
    if shift_end <= shift_start:
        cal_date += timedelta(days=1)

    end_dt = datetime.fromisoformat(f"{cal_date.isoformat()}T{h:02d}:{m:02d}:00").replace(tzinfo=IST)
    punch_out_ist = punch_out_utc.astimezone(IST)
    diff_seconds = (punch_out_ist - end_dt).total_seconds()

    if diff_seconds < 0:
        return 0
    ot_minutes = int(diff_seconds // 60)
    return ot_minutes if ot_minutes >= 30 else 0


def compute_work_hours(punch_in_utc: datetime, punch_out_utc: datetime) -> float:
    """R4: (punch_out - punch_in) in seconds / 3600, rounded to 2 decimals half-up."""
    sec = int((punch_out_utc - punch_in_utc).total_seconds())
    hours = Decimal(sec) / Decimal(3600)
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_half_day(work_hours: Optional[float]) -> bool:
    """R5: True when rounded work_hours < 4.50."""
    if work_hours is None:
        return False
    return work_hours < 4.50


def count_working_days(month_str: str, joined_on_str: str) -> int:
    """R7: Working days are Monday - Friday, counted from joined_on for mid-month joiners."""
    y, m = map(int, month_str.split("-"))
    next_month = dt_date(y + 1, 1, 1) if m == 12 else dt_date(y, m + 1, 1)
    end_date = next_month - timedelta(days=1)
    first_date = dt_date(y, m, 1)
    joined_date = dt_date.fromisoformat(joined_on_str)

    if joined_date > end_date:
        return 0
    start_date = max(first_date, joined_date)

    count = 0
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5:  # Mon=0, Fri=4
            count += 1
        curr += timedelta(days=1)
    return count


def get_month_range(month_str: str) -> tuple[str, str]:
    """Returns ISO format (start_date, end_date) for a given YYYY-MM month."""
    y, m = map(int, month_str.split("-"))
    next_month = dt_date(y + 1, 1, 1) if m == 12 else dt_date(y, m + 1, 1)
    end_date = next_month - timedelta(days=1)
    return f"{month_str}-01", end_date.isoformat()



def format_attendance_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Formats an attendance document to match AttendanceRecord OpenAPI schema."""
    history = []
    for h in doc.get("history") or []:
        changes = {}
        for k, v in (h.get("changes") or {}).items():
            from_val = v.get("from")
            to_val = v.get("to")
            if k in ("punch_in", "punch_out"):
                from_val = to_epoch_millis(from_val) if isinstance(from_val, datetime) else from_val
                to_val = to_epoch_millis(to_val) if isinstance(to_val, datetime) else to_val
            changes[k] = {"from": from_val, "to": to_val}
        history.append({
            "at": to_epoch_millis(h.get("at")),
            "by": h.get("by"),
            "reason": h.get("reason"),
            "changes": changes,
        })

    return {
        "emp_code": doc["emp_code"],
        "date": doc["date"],
        "status": doc["status"],
        "punch_in": to_epoch_millis(doc.get("punch_in")),
        "punch_out": to_epoch_millis(doc.get("punch_out")),
        "work_hours": doc.get("work_hours"),
        "late_minutes": doc.get("late_minutes", 0),
        "overtime_minutes": doc.get("overtime_minutes", 0),
        "half_day": doc.get("half_day", False),
        "history": history,
    }


def format_employee_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Formats an employee document to match Employee OpenAPI schema."""
    return {
        "emp_code": doc["emp_code"],
        "name": doc["name"],
        "email": doc["email"],
        "department": doc["department"],
        "shift_start": doc["shift_start"],
        "shift_end": doc["shift_end"],
        "joined_on": doc["joined_on"],
        "created_at": to_epoch_millis(doc.get("created_at")),
    }


# --------------------------------------------------------------------------- #
# Aggregation Pipeline Builders (Shared between endpoints and explain)
# --------------------------------------------------------------------------- #
def build_employee_monthly_pipeline(emp_code: str, month: str) -> List[Dict[str, Any]]:
    month_start, month_end = get_month_range(month)
    return [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {"$gte": month_start, "$lte": month_end},
            }
        },
        {
            "$project": {
                "date": 1,
                "status": 1,
                "late_minutes": {"$ifNull": ["$late_minutes", 0]},
                "overtime_minutes": {"$ifNull": ["$overtime_minutes", 0]},
                "half_day": {"$ifNull": ["$half_day", False]},
                "dayOfWeek": {"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}},
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$dayOfWeek", [2, 3, 4, 5, 6]]},
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                ]
                            },
                            {"$cond": ["$half_day", 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
                "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
                "total_late_minutes": {"$sum": "$late_minutes"},
                "total_overtime_minutes": {"$sum": "$overtime_minutes"},
            }
        },
    ]


def build_department_summary_pipeline(month: str, department: Optional[str] = None) -> List[Dict[str, Any]]:
    month_start, month_end = get_month_range(month)

    match_emp = {"joined_on": {"$lte": month_end}}
    if department:
        match_emp["department"] = department

    return [
        {"$match": match_emp},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"emp": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$emp"]},
                                    {"$gte": ["$date", month_start]},
                                    {"$lte": ["$date", month_end]},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "department": "$department",
                "emp_code": "$emp_code",
                "logs": "$logs",
                "dayOfWeek": {
                    "$cond": [
                        {"$ifNull": ["$logs.date", False]},
                        {"$dayOfWeek": {"$dateFromString": {"dateString": "$logs.date"}}},
                        None,
                    ]
                },
            }
        },
        {
            "$group": {
                "_id": "$department",
                "employees": {"$addToSet": "$emp_code"},
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$dayOfWeek", [2, 3, 4, 5, 6]]},
                                    {"$in": ["$logs.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                ]
                            },
                            {"$cond": [{"$ifNull": ["$logs.half_day", False]}, 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "work_hours_list": {
                    "$push": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$logs.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$ne": ["$logs.work_hours", None]},
                                ]
                            },
                            "$logs.work_hours",
                            "$$REMOVE",
                        ]
                    }
                },
                "late_count": {
                    "$sum": {"$cond": [{"$gt": ["$logs.late_minutes", 0]}, 1, 0]}
                },
                "total_late_minutes": {"$sum": {"$ifNull": ["$logs.late_minutes", 0]}},
                "leave_count": {
                    "$sum": {"$cond": [{"$eq": ["$logs.status", "LEAVE"]}, 1, 0]}
                },
                "on_duty_count": {
                    "$sum": {"$cond": [{"$eq": ["$logs.status", "ON_DUTY"]}, 1, 0]}
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "headcount": {"$size": "$employees"},
                "present_days": mongo_round_half_up("$present_days", 2),
                "avg_work_hours": {
                    "$cond": [
                        {"$gt": [{"$size": "$work_hours_list"}, 0]},
                        mongo_round_half_up({"$avg": "$work_hours_list"}, 2),
                        None,
                    ]
                },
                "late_count": "$late_count",
                "total_late_minutes": "$total_late_minutes",
                "leave_count": "$leave_count",
                "on_duty_count": "$on_duty_count",
            }
        },
        {"$sort": {"department": 1}},
    ]


def build_late_leaderboard_pipeline(month: str, limit: int, department: Optional[str] = None) -> List[Dict[str, Any]]:
    month_start, month_end = get_month_range(month)
    pipeline = [
        {
            "$match": {
                "date": {"$gte": month_start, "$lte": month_end},
                "late_minutes": {"$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1},
            }
        },
        {"$match": {"total_late_minutes": {"$gt": 0}}},
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "emp",
            }
        },
        {"$unwind": "$emp"},
    ]

    if department:
        pipeline.append({"$match": {"emp.department": department}})

    pipeline.extend([
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}},
            }
        },
        {"$match": {"rank": {"$lte": limit}}},
        {
            "$project": {
                "_id": 0,
                "rank": "$rank",
                "emp_code": "$_id",
                "name": "$emp.name",
                "department": "$emp.department",
                "total_late_minutes": "$total_late_minutes",
                "late_count": "$late_count",
            }
        },
        {"$sort": {"total_late_minutes": -1, "emp_code": 1}},
    ])
    return pipeline


def build_department_trend_pipeline(
    emp_codes: List[str],
    from_date: str,
    to_date: str,
    dept_joined_dates: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    MongoDB aggregation pipeline for department daily trend.
    Generates exact date rows in-database using $unionWith + $densify,
    computes dynamic headcount, working-day rates, and 7-day trailing moving average
    via $setWindowFields with four-decimal half-up rounding.
    """
    from_dt = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
    to_dt_plus_1 = (datetime.fromisoformat(to_date) + timedelta(days=1)).replace(tzinfo=timezone.utc)
    joined_dates_input = dept_joined_dates if dept_joined_dates is not None else []

    return [
        # Stage 1: Fast index scan on attendance_logs (IXSCAN via emp_code_1_date_1)
        {
            "$match": {
                "emp_code": {"$in": emp_codes},
                "date": {"$gte": from_date, "$lte": to_date},
            }
        },
        # Stage 2: Aggregate attendance counts for existing records
        {
            "$group": {
                "_id": "$date",
                "present_count": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                            {"$cond": [{"$ifNull": ["$half_day", False]}, 0.5, 1.0]},
                            0.0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}
                },
            }
        },
        # Stage 3: Database-side guarantee of at least one seed document for $densify even if 0 logs matched
        # Uses an indexed match on emp_code to ensure IXSCAN and eliminate COLLSCAN from executionStats
        {
            "$unionWith": {
                "coll": "employees",
                "pipeline": [
                    {"$match": {"emp_code": emp_codes[0] if emp_codes else {"$exists": True}}},
                    {"$limit": 1},
                    {
                        "$project": {
                            "_id": {"$literal": from_date},
                            "present_count": {"$literal": 0.0},
                            "late_count": {"$literal": 0},
                        }
                    },
                ],
            }
        },
        # Stage 4: Deduplicate the seed document with any actual record on from_date
        {
            "$group": {
                "_id": "$_id",
                "present_count": {"$max": "$present_count"},
                "late_count": {"$max": "$late_count"},
            }
        },
        # Stage 5: Project date as BSON Date for $densify
        {
            "$project": {
                "_id": 0,
                "date_str": "$_id",
                "date_dt": {"$dateFromString": {"dateString": "$_id"}},
                "present_count": 1,
                "late_count": 1,
            }
        },
        # Stage 6: Densify missing dates across the exact calendar range [from_date, to_date]
        # Upper bound is exclusive in $densify, so to_dt_plus_1 includes up to to_date
        {
            "$densify": {
                "field": "date_dt",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [from_dt, to_dt_plus_1],
                },
            }
        },
        # Stage 7: Format date string and default missing counts on gap-filled rows
        {
            "$addFields": {
                "date": {
                    "$cond": [
                        {"$ifNull": ["$date_str", False]},
                        "$date_str",
                        {"$dateToString": {"format": "%Y-%m-%d", "date": "$date_dt"}},
                    ]
                },
                "present_count": {"$ifNull": ["$present_count", 0.0]},
                "late_count": {"$ifNull": ["$late_count", 0]},
                "dayOfWeek": {"$dayOfWeek": "$date_dt"},
            }
        },
        # Stage 8: Boundary check - strictly enforce [from_date, to_date] with no extra dates
        {
            "$match": {
                "date": {"$gte": from_date, "$lte": to_date},
            }
        },
        # Stage 9: Calculate is_working_day and dynamic headcount for each date
        {
            "$addFields": {
                "is_working_day": {"$in": ["$dayOfWeek", [2, 3, 4, 5, 6]]},
                "headcount": {
                    "$size": {
                        "$filter": {
                            "input": joined_dates_input,
                            "as": "j",
                            "cond": {"$lte": ["$$j", "$date"]},
                        }
                    }
                },
            }
        },
        # Stage 10: Calculate attendance_rate (null on weekends or headcount 0; 0.0 on zero-log weekdays)
        {
            "$addFields": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                {"$eq": ["$is_working_day", True]},
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        {"$divide": ["$present_count", "$headcount"]},
                        None,
                    ]
                }
            }
        },
        # Stage 11: 7-calendar-row trailing window moving average (ignores null rates)
        {
            "$setWindowFields": {
                "sortBy": {"date": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {
                            "documents": [-6, "current"]
                        },
                    }
                },
            }
        },
        # Stage 12: Strict ROUND_HALF_UP rounding (not banker's rounding) and schema projection
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "is_working_day": 1,
                "headcount": 1,
                "present_count": mongo_round_half_up("$present_count", 2),
                "late_count": 1,
                "attendance_rate": {
                    "$cond": [
                        {"$ne": ["$attendance_rate", None]},
                        mongo_round_half_up("$attendance_rate", 4),
                        None,
                    ]
                },
                "moving_avg_7d": {
                    "$cond": [
                        {"$ne": ["$moving_avg_7d", None]},
                        mongo_round_half_up("$moving_avg_7d", 4),
                        None,
                    ]
                },
            }
        },
        {"$sort": {"date": 1}},
    ]


# --------------------------------------------------------------------------- #
# Request Schemas
# --------------------------------------------------------------------------- #
class EmployeeCreate(BaseModel):
    emp_code: str = Field(..., pattern=r"^EMP\d{4,6}$")
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(..., min_length=1, max_length=50)
    shift_start: str = Field("09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field("18:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def validate_shift_and_joined(self):
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        try:
            dt_date.fromisoformat(self.joined_on)
        except ValueError:
            raise ValueError("joined_on must be a valid date YYYY-MM-DD")
        return self


class PunchInRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    status: str = Field("PRESENT", pattern=r"^(PRESENT|WFH|ON_DUTY)$")

    @field_validator("punched_at")
    @classmethod
    def validate_punched_at(cls, v):
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("punched_at must be an integer count of epoch milliseconds")
            if v < 100000000000 or v > 4102444800000:
                raise ValueError("punched_at out of range")
        return v


class PunchOutRequest(BaseModel):
    emp_code: str
    punched_at: Optional[int] = Field(None, ge=100000000000, le=4102444800000)

    @field_validator("punched_at")
    @classmethod
    def validate_punched_at(cls, v):
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("punched_at must be an integer count of epoch milliseconds")
            if v < 100000000000 or v > 4102444800000:
                raise ValueError("punched_at out of range")
        return v


class RegularizeRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=200)
    regularized_by: str = Field(..., min_length=1, max_length=50)
    status: Optional[str] = Field(None, pattern=r"^(PRESENT|ABSENT|LEAVE|WFH|ON_DUTY)$")
    punch_in: Optional[int] = Field(None, ge=100000000000, le=4102444800000)
    punch_out: Optional[int] = Field(None, ge=100000000000, le=4102444800000)

    @field_validator("punch_in", "punch_out")
    @classmethod
    def validate_instants(cls, v):
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("Timestamp must be an integer count of epoch milliseconds")
            if v < 100000000000 or v > 4102444800000:
                raise ValueError("Timestamp out of range")
        return v


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeCreate):
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="emp_code already exists")
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return format_employee_doc(doc)


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = {}
    if department:
        q["department"] = department
    total = db.employees.count_documents(q)
    skip = (page - 1) * page_size
    cursor = db.employees.find(q).sort("emp_code", ASCENDING).skip(skip).limit(page_size)
    items = [format_employee_doc(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInRequest):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    ts = parse_epoch_millis(body.punched_at) if body.punched_at is not None else datetime.now(timezone.utc).replace(microsecond=0)
    d = determine_attendance_date(ts, emp["shift_start"], emp["shift_end"])
    late_mins = compute_late_minutes(ts, emp["shift_start"], d)

    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": late_mins,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="already punched in for this date")

    return format_attendance_doc(doc)


@app.post("/attendance/punch-out", status_code=200)
def punch_out(body: PunchOutRequest):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    ts = parse_epoch_millis(body.punched_at) if body.punched_at is not None else datetime.now(timezone.utc).replace(microsecond=0)

    # Find the most recent record whose punch_in is at or before punched_at
    rec = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": ts}},
        sort=[("punch_in", DESCENDING)],
    )
    if not rec:
        raise HTTPException(status_code=404, detail="No open punch-in record found")

    if rec.get("punch_out") is not None:
        raise HTTPException(status_code=409, detail="Record already punched out")

    punch_in_dt = rec["punch_in"]
    if punch_in_dt.tzinfo is None:
        punch_in_dt = punch_in_dt.replace(tzinfo=timezone.utc)

    diff_sec = (ts - punch_in_dt).total_seconds()
    if diff_sec <= 0:
        raise HTTPException(status_code=422, detail="punched_at must be strictly after punch_in")
    if diff_sec > 24 * 3600:
        raise HTTPException(status_code=422, detail="punched_at cannot be more than 24 hours after punch_in")

    work_hours = compute_work_hours(punch_in_dt, ts)
    overtime = compute_overtime(ts, emp["shift_start"], emp["shift_end"], rec["date"])
    half_day = compute_half_day(work_hours)

    # Atomic update to guarantee exactly one 200 on concurrent punch-outs
    updated = db.attendance_logs.find_one_and_update(
        {"_id": rec["_id"], "punch_out": None},
        {
            "$set": {
                "punch_out": ts,
                "work_hours": work_hours,
                "overtime_minutes": overtime,
                "half_day": half_day,
            }
        },
        return_document=pymongo.ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Record already punched out")

    return format_attendance_doc(updated)


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    status: Optional[str] = Query(None, pattern=r"^(PRESENT|ABSENT|LEAVE|WFH|ON_DUTY)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if date_from:
        try:
            dt_date.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date_from")
    if date_to:
        try:
            dt_date.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date_to")

    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be greater than date_to")

    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status

    total = db.attendance_logs.count_documents(q)
    skip = (page - 1) * page_size
    cursor = (
        db.attendance_logs.find(q)
        .sort([("date", DESCENDING), ("emp_code", ASCENDING)])
        .skip(skip)
        .limit(page_size)
    )
    items = [format_attendance_doc(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.patch("/attendance/{emp_code}/{date}")
def regularize_attendance(
    emp_code: str = FPath(...),
    date: str = FPath(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    body: RegularizeRequest = ...,
):
    try:
        dt_date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date path parameter")

    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    rec = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not rec:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    # If setting ABSENT or LEAVE, supplying punch_in or punch_out is 422
    if body.status in ("ABSENT", "LEAVE") and (body.punch_in is not None or body.punch_out is not None):
        raise HTTPException(status_code=422, detail="Cannot provide punch times when setting status to ABSENT or LEAVE")

    target_status = body.status if body.status is not None else rec["status"]

    if target_status in ("ABSENT", "LEAVE"):
        final_punch_in = None
        final_punch_out = None
        final_work_hours = None
        final_late_minutes = 0
        final_overtime_minutes = 0
        final_half_day = False
    else:
        # Presence status requires punch_in
        if body.punch_in is not None:
            final_punch_in = parse_epoch_millis(body.punch_in)
        else:
            final_punch_in = rec.get("punch_in")

        if final_punch_in is None:
            raise HTTPException(status_code=422, detail="A presence status requires punch_in")

        if final_punch_in.tzinfo is None:
            final_punch_in = final_punch_in.replace(tzinfo=timezone.utc)

        # punch_in must stay on the record's attendance date per R1
        in_att_date = determine_attendance_date(final_punch_in, emp["shift_start"], emp["shift_end"])
        if in_att_date != date:
            raise HTTPException(status_code=422, detail="punch_in must stay on the record's attendance date")

        # Determine punch_out
        if body.punch_out is not None:
            final_punch_out = parse_epoch_millis(body.punch_out)
        else:
            final_punch_out = rec.get("punch_out")

        if final_punch_out is not None:
            if final_punch_out.tzinfo is None:
                final_punch_out = final_punch_out.replace(tzinfo=timezone.utc)
            diff_sec = (final_punch_out - final_punch_in).total_seconds()
            if diff_sec <= 0:
                raise HTTPException(status_code=422, detail="punch_out must be strictly after punch_in")
            if diff_sec > 24 * 3600:
                raise HTTPException(status_code=422, detail="punch_out cannot be more than 24 hours after punch_in")
            final_work_hours = compute_work_hours(final_punch_in, final_punch_out)
            final_overtime_minutes = compute_overtime(final_punch_out, emp["shift_start"], emp["shift_end"], date)
            final_half_day = compute_half_day(final_work_hours)
        else:
            final_work_hours = None
            final_overtime_minutes = 0
            final_half_day = False

        final_late_minutes = compute_late_minutes(final_punch_in, emp["shift_start"], date)

    # Detect fields that actually changed
    changes = {}
    candidate_fields = [
        ("status", target_status),
        ("punch_in", final_punch_in),
        ("punch_out", final_punch_out),
        ("work_hours", final_work_hours),
        ("late_minutes", final_late_minutes),
        ("overtime_minutes", final_overtime_minutes),
        ("half_day", final_half_day),
    ]

    for field_name, new_val in candidate_fields:
        old_val = rec.get(field_name)
        if field_name in ("punch_in", "punch_out"):
            old_ms = to_epoch_millis(old_val)
            new_ms = to_epoch_millis(new_val)
            if old_ms != new_ms:
                changes[field_name] = {"from": old_val, "to": new_val}
        else:
            if old_val != new_val:
                changes[field_name] = {"from": old_val, "to": new_val}

    if not changes:
        raise HTTPException(status_code=422, detail="Request changes nothing")

    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    history_entry = {
        "at": now_dt,
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }

    # Concurrent edits must not silently lose each other's history
    curr_history = rec.get("history", [])
    updated = db.attendance_logs.find_one_and_update(
        {"_id": rec["_id"], "history": curr_history},
        {
            "$set": {
                "status": target_status,
                "punch_in": final_punch_in,
                "punch_out": final_punch_out,
                "work_hours": final_work_hours,
                "late_minutes": final_late_minutes,
                "overtime_minutes": final_overtime_minutes,
                "half_day": final_half_day,
            },
            "$push": {"history": history_entry},
        },
        return_document=pymongo.ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Concurrent regularization conflict")

    return format_attendance_doc(updated)


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(
    emp_code: str = FPath(...),
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    working_days = count_working_days(month, emp["joined_on"])
    pipeline = build_employee_monthly_pipeline(emp_code, month)

    agg_res = list(db.attendance_logs.aggregate(pipeline))
    if agg_res:
        row = agg_res[0]
        present_days = float(row.get("present_days", 0.0))
        leave_days = int(row.get("leave_days", 0))
        late_count = int(row.get("late_count", 0))
        total_late = int(row.get("total_late_minutes", 0))
        total_ot = int(row.get("total_overtime_minutes", 0))
    else:
        present_days = 0.0
        leave_days = 0
        late_count = 0
        total_late = 0
        total_ot = 0

    att_pct = round_half_up((present_days / working_days) * 100.0, 2) if working_days > 0 else None

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": round_half_up(present_days, 2),
        "leave_days": leave_days,
        "late_count": late_count,
        "total_late_minutes": total_late,
        "total_overtime_minutes": total_ot,
        "attendance_pct": att_pct,
    }


@app.get("/analytics/departments/summary")
def department_summary(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = None,
):
    pipeline = build_department_summary_pipeline(month, department)
    items = list(db.employees.aggregate(pipeline))
    return {"month": month, "items": items}


@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None,
):
    pipeline = build_late_leaderboard_pipeline(month, limit, department)
    items = list(db.attendance_logs.aggregate(pipeline))
    return {"month": month, "items": items}


@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str = FPath(...),
    from_date: str = Query(..., alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str = Query(..., alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    if db.employees.count_documents({"department": department}) == 0:
        raise HTTPException(status_code=404, detail="Department not found")

    try:
        d_start = dt_date.fromisoformat(from_date)
        d_end = dt_date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format in from/to")

    if d_end < d_start:
        raise HTTPException(status_code=422, detail="'to' date must be >= 'from' date")
    if (d_end - d_start).days > 92:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 92 days")

    expected_days = (d_end - d_start).days + 1

    dept_employees = list(db.employees.find({"department": department}, {"_id": 0, "emp_code": 1, "joined_on": 1}))
    emp_codes = [e["emp_code"] for e in dept_employees]
    dept_joined_dates = [e["joined_on"] for e in dept_employees]

    pipeline = build_department_trend_pipeline(emp_codes, from_date, to_date, dept_joined_dates)
    items = list(db.attendance_logs.aggregate(pipeline))

    return {"department": department, "items": items}


@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str = FPath(...),
    emp_code: Optional[str] = None,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    status: Optional[str] = Query(None, pattern=r"^(PRESENT|ABSENT|LEAVE|WFH|ON_DUTY)$"),
    from_date: Optional[str] = Query(None, alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: Optional[str] = Query(None, alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if endpoint == "attendance_list":
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from cannot be greater than date_to")
        q = {}
        if emp_code:
            q["emp_code"] = emp_code
        if date_from or date_to:
            q["date"] = {}
            if date_from:
                q["date"]["$gte"] = date_from
            if date_to:
                q["date"]["$lte"] = date_to
        if status:
            q["status"] = status
        skip = (page - 1) * page_size
        command = {
            "explain": {
                "find": "attendance_logs",
                "filter": q,
                "sort": {"date": -1, "emp_code": 1},
                "skip": skip,
                "limit": page_size,
            },
            "verbosity": "executionStats",
        }
        raw_explain = db.command(command)
        serializable_explain = json.loads(json_util.dumps(raw_explain))
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": serializable_explain}

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(status_code=422, detail="emp_code and month are required")
        pipeline = build_employee_monthly_pipeline(emp_code, month)
        command = {
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        raw_explain = db.command(command)
        serializable_explain = json.loads(json_util.dumps(raw_explain))
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": serializable_explain}

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(status_code=422, detail="month is required")
        pipeline = build_department_summary_pipeline(month, department)
        command = {
            "explain": {
                "aggregate": "employees",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        raw_explain = db.command(command)
        serializable_explain = json.loads(json_util.dumps(raw_explain))
        return {"endpoint": endpoint, "collection": "employees", "explain": serializable_explain}

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(status_code=422, detail="month is required")
        pipeline = build_late_leaderboard_pipeline(month, limit, department)
        command = {
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        raw_explain = db.command(command)
        serializable_explain = json.loads(json_util.dumps(raw_explain))
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": serializable_explain}

    elif endpoint == "department_trend":
        if not department or not from_date or not to_date:
            raise HTTPException(status_code=422, detail="department, from, and to are required")
        if db.employees.count_documents({"department": department}) == 0:
            raise HTTPException(status_code=404, detail="Department not found")
        dept_employees = list(db.employees.find({"department": department}, {"_id": 0, "emp_code": 1, "joined_on": 1}))
        emp_codes = [e["emp_code"] for e in dept_employees]
        dept_joined_dates = [e["joined_on"] for e in dept_employees]
        pipeline = build_department_trend_pipeline(emp_codes, from_date, to_date, dept_joined_dates)
        command = {
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
        raw_explain = db.command(command)
        serializable_explain = json.loads(json_util.dumps(raw_explain))
        return {"endpoint": endpoint, "collection": "attendance_logs", "explain": serializable_explain}

    else:
        raise HTTPException(status_code=404, detail=f"Unknown endpoint '{endpoint}' for explain")
