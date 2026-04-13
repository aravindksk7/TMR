#!/usr/bin/env bash
# docker/entrypoint.sh
# Orchestrates the full test sequence inside the pipeline container.
#
# Usage (via docker-compose CMD):
#   test          — unit tests + integration DB tests (default)
#   unit          — unit tests only (no DB required)
#   integration   — integration tests only
#   shell         — drop into bash for manual inspection
#   seed          — initialise DBs and seed dim_date, then exit

set -euo pipefail

SQL_SERVER="sqlserver"
SQL_PORT="1433"
SA_PASSWORD="Pipeline_Test_P@ss1"
SQLCMD="/opt/mssql-tools18/bin/sqlcmd"

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Wait for SQL Server to accept connections ──────────────────────────────────
wait_for_sql() {
    info "Waiting for SQL Server at ${SQL_SERVER}:${SQL_PORT} ..."
    local retries=40
    until python - <<'PYEOF' 2>/dev/null
import pyodbc, sys
dsn = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER=sqlserver,1433;DATABASE=master;"
    "UID=sa;PWD=Pipeline_Test_P@ss1;TrustServerCertificate=yes;"
    "Connect Timeout=3;"
)
try:
    conn = pyodbc.connect(dsn, timeout=3)
    conn.execute("SELECT 1")
    conn.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
PYEOF
    do
        retries=$((retries - 1))
        if [ $retries -le 0 ]; then
            error "SQL Server did not become ready in time"
            exit 1
        fi
        warn "  not ready yet, retrying in 3s (${retries} left)..."
        sleep 3
    done
    info "SQL Server is ready."
}

# ── Create databases ───────────────────────────────────────────────────────────
create_databases() {
    info "Creating Staging_DB and Reporting_DB ..."
    $SQLCMD -S "${SQL_SERVER},${SQL_PORT}" -U sa -P "${SA_PASSWORD}" \
            -i /app/docker/create_databases.sql -b -C
    info "Databases ready."
}

# ── Run init_db.sql on both DBs ────────────────────────────────────────────────
init_schema() {
    info "Applying DDL to Staging_DB ..."
    $SQLCMD -S "${SQL_SERVER},${SQL_PORT}" -U sa -P "${SA_PASSWORD}" \
            -d Staging_DB -i /app/scripts/init_staging_db.sql -b -C

    info "Applying DDL to Reporting_DB ..."
    $SQLCMD -S "${SQL_SERVER},${SQL_PORT}" -U sa -P "${SA_PASSWORD}" \
            -d Reporting_DB -i /app/scripts/init_reporting_db.sql -b -C

    info "DDL applied."
}

# ── Seed dim_date ─────────────────────────────────────────────────────────────
seed_dim_date() {
    info "Seeding dim_date (2018-01-01 → 2030-12-31) ..."
    python -m qa_pipeline.scripts.seed_dim_date \
        --start 2018-01-01 \
        --end   2030-12-31
    info "dim_date seeded."
}

# ── Run pytest ────────────────────────────────────────────────────────────────
run_unit_tests() {
    info "Running unit tests (no live DB required) ..."
    python -m pytest tests/ -m "not integration" \
        --tb=short -q \
        --color=yes \
        -x
}

run_integration_tests() {
    info "Running integration / DB smoke tests ..."
    python -m pytest tests/integration/ -m "integration" \
        --tb=short -v \
        --color=yes
}

# ── Main dispatch ─────────────────────────────────────────────────────────────
CMD="${1:-test}"

case "$CMD" in
    unit)
        info "=== Unit tests only ==="
        run_unit_tests
        ;;

    integration)
        info "=== Integration tests only ==="
        wait_for_sql
        create_databases
        init_schema
        seed_dim_date
        run_integration_tests
        ;;

    seed)
        info "=== DB initialisation only ==="
        wait_for_sql
        create_databases
        init_schema
        seed_dim_date
        info "Done."
        ;;

    shell)
        info "Dropping into bash shell ..."
        exec bash
        ;;

    test|*)
        info "=== Full test suite (unit + integration) ==="
        # Unit tests first — fast feedback, no DB needed
        run_unit_tests
        UNIT_EXIT=$?

        # DB setup + integration tests
        wait_for_sql
        create_databases
        init_schema
        seed_dim_date
        run_integration_tests
        INT_EXIT=$?

        if [ $UNIT_EXIT -ne 0 ] || [ $INT_EXIT -ne 0 ]; then
            error "One or more test suites failed (unit=$UNIT_EXIT integration=$INT_EXIT)"
            exit 1
        fi

        info "All tests passed."
        ;;
esac
