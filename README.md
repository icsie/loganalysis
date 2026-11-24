# Network Log Analysis

A SQL-first network access log analysis platform for importing, storing, and investigating VPN and network access records.

The project is designed to analyze datasets containing 30,000 or more records while keeping PostgreSQL as the source of truth for aggregation and suspicious-activity detection.

## Overview

Network Log Analysis combines CSV ingestion, PostgreSQL analysis, and a lightweight FastAPI web application:

- **CSV ingestion:** pandas validates and prepares source files before database import.
- **SQL analysis:** PostgreSQL performs filtering, grouping, aggregation, timeline analysis, and rule-based detection.
- **API layer:** FastAPI exposes dataset management and read-only analysis endpoints.
- **Web interface:** HTML, CSS, and JavaScript provide upload and dashboard interactions without a heavy frontend framework.

The MVP follows a rule-based approach. It does not rely on machine learning or make definitive claims that a source address is malicious.

## Architecture

```text
CSV
  |
  v
pandas validation
  |
  v
PostgreSQL (logs schema)
  |
  +--> SQL statistics
  |
  +--> Rule-based detection
  |
  v
FastAPI
  |
  +--> REST API
  |
  +--> Web dashboard
```

PostgreSQL stores each imported CSV as a dedicated table. Import metadata is maintained separately in `public.import_history`.

## Planned Capabilities

- Secure, validated CSV-to-table import
- Transactional PostgreSQL imports with duplicate-table protection
- Dataset listing and import history
- Total record, unique IP, and failed-login summaries
- Top-source-IP analysis
- Hourly or daily activity timelines
- Configurable suspicious-activity rules
- Browser-based dataset selection and result dashboards
- Automated API, SQL, and import tests

## Technology

| Area | Technology |
|---|---|
| Data preparation | Python, pandas |
| Database | PostgreSQL |
| API | FastAPI |
| Web UI | HTML, CSS, JavaScript |
| Testing | pytest |
| Configuration | Environment variables / `.env` |

## Development Roadmap

1. CSV import and import-history tracking
2. Core SQL filtering, grouping, aggregation, and timelines
3. Dataset and statistics REST APIs
4. Web dashboard and CSV upload interface
5. Advanced SQL detection rules and query optimization

Each stage should remain independent enough to test and verify before advancing to the next one.

## SQL-First Principles

- Use PostgreSQL for meaningful aggregation and data analysis.
- Keep source data traceable and do not modify the original CSV.
- Use parameterized values and safely quoted PostgreSQL identifiers.
- Validate and allowlist table names before API access.
- Make every reported metric reproducible by SQL.
- Prefer clear CTEs and views when they improve testing or maintenance.

## Security and Privacy

Network logs can contain identifying or sensitive information. Raw datasets, database credentials, environment secrets, and generated dumps must not be committed to source control.

- Store secrets in environment variables or a local `.env` file.
- De-identify or use synthetic data for tests.
- Limit CSV upload size and API result counts.
- Do not expose arbitrary SQL execution.
- Never return detailed database errors to clients.
- Apply least-privilege database accounts in deployed environments.

## Repository Setup

The MVP uses PostgreSQL and Python 3.

```powershell
# Clone
git clone https://github.com/icsie/loganalysis.git
cd loganalysis

# Create a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### PostgreSQL Database

The local learning bootstrap script creates the `netlogs` database, its `logs`
schema, the `public.import_history` table, and the restricted application login.
The local `.env.local` file is ignored by Git. After cloning, create your own
copy from the safe template and set a local password:

```powershell
Copy-Item .env.example .env.local
# Edit .env.local, then run:
.\run_db_setup.ps1
```

The script uses psql-specific commands to switch databases and prompts for the
PostgreSQL administrator password. The checked-in example contains only a
password placeholder. The requested local password is weak and is only suitable
for a throwaway learning database; use a strong secret in shared or production
environments.

`dev_usr` can create dataset tables in `logs` because the CSV importer needs that
capability. It cannot create databases or roles, and it has no `CREATE` privilege
in `public`. PostgreSQL may allow connections to other databases through
cluster-wide `PUBLIC` grants; this script does not change those shared defaults.

## CSV Import

Install the requirements and initialize the local PostgreSQL database first:

```powershell
pip install -r requirements.txt
.\run_db_setup.ps1
```

After reviewing the import code, run the default CSV import from the repository
root:

```powershell
.\run.bat
```

`run.bat` uses `.venv` when it exists; otherwise it uses the Python interpreter
available on `PATH`. `main.py` scans `data\*.csv` in filename order. It skips a
file when its filename or derived `logs.<table_name>` is already in
`public.import_history`; valid remaining files are imported using SQLAlchemy and
`DataFrame.to_sql()`. Each CSV has its own transaction, uses `if_exists="fail"`,
and is recorded in `public.import_history` only after the PostgreSQL row count
matches the DataFrame. Before table creation, column names are normalized to
lowercase PostgreSQL identifiers (for example, `Source IP` becomes `source_ip`);
the CSV values are unchanged. Collisions receive a deterministic numeric suffix
and reserved words receive a `_field` suffix. The original-to-normalized mapping
is printed during import.

Pass a different directory as an argument:

```powershell
.\run.bat .\path\to\csv_directory
```

The table name is derived from the CSV filename and must start with a letter or
underscore. Invalid filenames are reported as failed while other CSV files
continue. Existing tables are never overwritten.

## QVPN Login Fail Analysis

After importing `w20261123_13_36_23.csv` into `logs.w20261123_13_36_23`, run the
analysis script from the repository root:

```powershell
psql -U postgres -d netlogs -f sql/fail_analysis.sql
```

The script reads the imported PostgreSQL table (not the CSV), selects QVPN
Service / VPN Server login failures, and stores parsed events in `logs.fail`.
It keeps usernames, source IPs, and protocols in `logs.username`,
`logs.sourceip`, and `logs.protocol`; each dimension table's `n` is the number
of parsed failure events for that value. Unmatched content is saved in
`logs.errorformats`.

The database setup configures `logs` in `search_path`, so the most frequent
source IPs can be listed with:

```sql
SELECT * FROM sourceip ORDER BY n DESC;
```

Likewise, use `SELECT * FROM username ORDER BY n DESC;` and
`SELECT * FROM protocol ORDER BY n DESC;` to see the most frequently tried
usernames and protocols. The `n` values are cumulative: running the script
again processes the source rows again and increments the counts again.

## Project Structure

The workspace structure will grow with implementation:

```text
app/          FastAPI application modules
tests/        Automated test suite
sql/          Analysis queries and migrations
templates/    Web templates
static/       Web assets
data/         Local-only CSV data (excluded from Git)
```

## Testing

The test suite will cover:

- CSV parsing and validation
- Filename and table-name safety
- Transactional import behavior
- Duplicate import protection
- SQL result correctness
- API validation and error handling
- Suspicious-activity rule outcomes

## Contributing

The repository follows a spec-driven, stage-based workflow:

1. Review the specification for the current stage.
2. Define a small, testable task.
3. Implement only the required behavior.
4. Add or update focused tests.
5. Verify SQL and API results independently.
6. Review security and privacy implications.
7. Refactor and commit once validation passes.
