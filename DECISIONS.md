# DECISIONS.md (about 150-200 words in total - plain language, your own words)

1. **Indexes.**
We created:
* `employees.emp_code` (unique): Enforces employee code uniqueness and accelerates primary lookups.
* `attendance_logs.(emp_code, date)` (unique): Guarantees the one-record-per-day constraint and provides atomic race safety on punch-ins.
* `attendance_logs.(date, emp_code)`: Supports index-covered sorting and fast cursor pagination on list attendance.
* `attendance_logs.(date, late_minutes)`: Accelerates late-leaderboard and monthly analytics scans.
Rejected: An index on `status` alone, as low cardinality yields poor selectivity compared to compound date filters.

2. **Punch-in race.**
Both requests calculate the identical attendance date. Both attempt `insert_one`. Because `(emp_code, date)` is guarded by a database unique index, MongoDB atomically allows one insert to succeed (returning 201). The concurrent request raises a `DuplicateKeyError`, which our handler intercepts and returns as a 409 Conflict.

3. **Ties.**
The pipeline uses standard competition ranking (`$rank`), assigning tied employees identical ranks and skipping subsequent ranks (e.g., 1, 2, 2, 4). The cutoff applies `rank <= limit`, returning all tied employees at the boundary (potentially exceeding `limit` rows), ordered by `emp_code` ascending.

4. **Headcount.**
The pipeline initiates on `employees` (filtering `joined_on <= month_end`), then performs a `$lookup` onto `attendance_logs` with `preserveNullAndEmptyArrays: true`. Grouping by department and counting distinct employees ensures employees with zero attendance documents are counted.

5. **One thing you would change for 100x data.**
I would maintain pre-aggregated daily department summaries asynchronously via MongoDB Change Streams, avoiding real-time multi-collection aggregations over tens of millions of raw logs.
