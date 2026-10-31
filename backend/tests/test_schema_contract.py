"""Schema-contract tests: listings.available_quantity is a
PostgreSQL GENERATED column, not a writable nullable column.

These tests guard the correction made 2026-10-31, when the
Milestone 4 audit incorrectly reported available_quantity as a
nullable column without automatic calculation. The verified live
definition is:

    available_quantity integer GENERATED ALWAYS AS
    (total_quantity - reserved_quantity - sold_quantity) STORED

They read only repository files — they never connect to live
Supabase and never apply a migration. The baseline file is a
tracking-only consolidated copy; it must never be applied to
production, and this correction adds no new migration file.
"""

import re
from pathlib import Path

# tests/ lives under backend/, so the repo root is two levels up.
REPO = Path(__file__).resolve().parents[2]

BASELINE = REPO / "supabase/migrations/20261031060000_remote_schema_baseline.sql"
TYPES = REPO / "packages/types/src/database.ts"
ARCHITECTURE = REPO / "docs/architecture.md"

GENERATED_FORMULA = "total_quantity - reserved_quantity - sold_quantity"


def _listings_table_sql() -> str:
    sql = BASELINE.read_text()
    match = re.search(r'create table public\."listings" \((.*?)\n\);\n', sql, re.S)
    assert match, "listings table not found in baseline"
    return match.group(1)


def _listings_type_section(section: str) -> str:
    """Return the listings Row/Insert/Update block from database.ts.

    The listings block ends with a Relationships section, so the
    section is located from the listings table start rather than
    by matching the first closing brace (which ends the Row)."""
    text = TYPES.read_text()
    start = text.find("listings: {")
    assert start >= 0, "listings table not found in database.ts"
    block = text[start : start + 6000]
    match = re.search(rf"{section}: \{{(.*?)\n        \}}", block, re.S)
    assert match, f"listings {section} not found in database.ts"
    return match.group(1)


def test_baseline_represents_generated_stored_column():
    table = _listings_table_sql()
    line = next(ln.strip() for ln in table.splitlines() if '"available_quantity"' in ln)
    assert line == (
        '"available_quantity" integer generated always as '
        f"({GENERATED_FORMULA}) stored,"
    ), line
    # No nullable plain column, no default, no trigger definition
    # for availability anywhere in the baseline.
    assert not re.search(
        r"create trigger .*available_quantity", BASELINE.read_text(), re.I
    )


def test_no_new_migration_created_for_this_correction():
    migration_files = sorted(
        p.name for p in (REPO / "supabase/migrations").glob("*.sql")
    )
    assert migration_files == ["20261031060000_remote_schema_baseline.sql"], (
        f"this correction must not add a production migration; found: {migration_files}"
    )
    assert "DO NOT APPLY THIS FILE TO THE LIVE PROJECT" in BASELINE.read_text()


def test_types_row_is_non_nullable_number():
    row = _listings_type_section("Row")
    line = next(ln.strip() for ln in row.splitlines() if "available_quantity" in ln)
    assert line == "available_quantity: number", line


def test_types_insert_and_update_omit_generated_column():
    # A generated column is database-managed and must not be
    # writable through application types.
    for section in ("Insert", "Update"):
        block = _listings_type_section(section)
        assert "available_quantity" not in block, section


def test_types_no_other_generated_column_regression():
    # available_quantity is the only listings column that is
    # Row-only; every other Row column remains in Insert or Update.
    row = _listings_type_section("Row")
    insert = _listings_type_section("Insert")
    update = _listings_type_section("Update")

    def keys(block: str) -> set[str]:
        return set(re.findall(r"^\s*([a-z_0-9]+)\??:", block, re.M))

    assert keys(row) - keys(insert) - keys(update) == {"available_quantity"}


def test_docs_state_generated_behaviour_not_a_blocker():
    docs = ARCHITECTURE.read_text()
    assert "GENERATED ALWAYS AS" in docs
    assert GENERATED_FORMULA in docs
    assert "No trigger or additional migration is needed for availability" in docs
    assert "PostgreSQL" in docs and "recalculates it automatically" in docs
    assert "Merchants cannot directly modify the generated availability" in docs


def test_docs_no_longer_claim_availability_is_broken():
    docs = ARCHITECTURE.read_text()
    for stale in (
        "available_quantity is never maintained",
        "available_quantity NULL",
        "BLOCKS public visibility and activation",
        "migration is needed to repair availability",
        "NO generated expression",
    ):
        assert stale not in docs, stale


def test_docs_keep_published_at_separate():
    docs = ARCHITECTURE.read_text()
    # published_at is a separate, still-open issue: it must still
    # be documented as such, and must not be silently fixed here.
    assert "SEPARATE, still open" in docs
    assert "published_at" in docs
    assert "No trigger or publication-behaviour change is introduced" in docs
