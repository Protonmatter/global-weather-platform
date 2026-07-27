import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "apps" / "operator-console" / "drizzle"


def apply_migration(connection: sqlite3.Connection, name: str) -> None:
    sql = (MIGRATIONS / name).read_text(encoding="utf-8")
    connection.executescript(sql.replace("--> statement-breakpoint", ""))


def test_legacy_digest_and_fixture_migrations_are_fail_closed() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE observations (
          id TEXT PRIMARY KEY,
          content_digest TEXT NOT NULL,
          source_id TEXT NOT NULL,
          quality_disposition TEXT NOT NULL,
          quality_flags TEXT NOT NULL
        );
        CREATE TABLE model_cycles (id TEXT PRIMARY KEY);
        INSERT INTO observations VALUES (
          'legacy-observation', '', 'validation-set/nyc', 'accept', '[]'
        );
        INSERT INTO model_cycles VALUES ('gefs-35-20260724t18z');
        INSERT INTO model_cycles VALUES ('real-cycle');
        """
    )

    apply_migration(connection, "0002_mark_legacy_observation_digests.sql")
    apply_migration(connection, "0003_quarantine_legacy_fixtures.sql")

    observation = connection.execute(
        "SELECT content_digest, quality_disposition, quality_flags FROM observations"
    ).fetchone()
    assert observation == (
        "legacy:unknown",
        "quarantine",
        '["synthetic_validation_fixture"]',
    )
    cycles = connection.execute("SELECT id FROM model_cycles ORDER BY id").fetchall()
    assert cycles == [("real-cycle",)]
