"""gold.db DDL. user_version 순서로 적용한다."""

from __future__ import annotations

MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE gold_runs (
        run_id TEXT PRIMARY KEY,
        seed TEXT NOT NULL,
        created_at TEXT NOT NULL,
        population_sql_sha TEXT NOT NULL,
        db_snapshot TEXT,
        params TEXT NOT NULL,
        stats TEXT NOT NULL
    );

    CREATE TABLE gold_samples (
        run_id TEXT NOT NULL REFERENCES gold_runs(run_id),
        rcept_no VARCHAR(32) NOT NULL,
        dcm_no VARCHAR(32) NOT NULL,
        period VARCHAR(8) NOT NULL,
        sub_period VARCHAR(8),
        stratum VARCHAR(128) NOT NULL,
        stratum_weight REAL NOT NULL,
        sample_hash VARCHAR(16) NOT NULL,
        mode VARCHAR(8) NOT NULL,
        role VARCHAR(16) NOT NULL,
        queue_order INTEGER NOT NULL,
        status VARCHAR(16) NOT NULL,
        exclude_reason TEXT,
        meta TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        active_seconds INTEGER,
        PRIMARY KEY (run_id, rcept_no, dcm_no)
    );

    CREATE TABLE gold_labels (
        rcept_no VARCHAR(32) NOT NULL,
        dcm_no VARCHAR(32) NOT NULL,
        bundle VARCHAR(32) NOT NULL,
        subject VARCHAR(64) NOT NULL,
        pass VARCHAR(16) NOT NULL,
        verdict VARCHAR(8) NOT NULL,
        gold_value TEXT,
        shown_value TEXT,
        shown_extractor_version VARCHAR(32),
        evidence TEXT,
        error_tag VARCHAR(32),
        note TEXT NOT NULL DEFAULT '',
        labeled_at TEXT NOT NULL,
        seconds INTEGER,
        PRIMARY KEY (rcept_no, dcm_no, bundle, subject, pass)
    );

    CREATE TABLE gold_label_history (
        rcept_no VARCHAR(32) NOT NULL,
        dcm_no VARCHAR(32) NOT NULL,
        bundle VARCHAR(32) NOT NULL,
        subject VARCHAR(64) NOT NULL,
        pass VARCHAR(16) NOT NULL,
        verdict VARCHAR(8) NOT NULL,
        gold_value TEXT,
        shown_value TEXT,
        shown_extractor_version VARCHAR(32),
        evidence TEXT,
        error_tag VARCHAR(32),
        note TEXT NOT NULL DEFAULT '',
        labeled_at TEXT NOT NULL,
        seconds INTEGER,
        superseded_at TEXT NOT NULL
    );

    CREATE TABLE gold_scores (
        extractor_version VARCHAR(32) NOT NULL,
        rcept_no VARCHAR(32) NOT NULL,
        dcm_no VARCHAR(32) NOT NULL,
        bundle VARCHAR(32) NOT NULL,
        subject VARCHAR(64) NOT NULL,
        predicted TEXT,
        outcome VARCHAR(8) NOT NULL,
        scored_at TEXT NOT NULL,
        PRIMARY KEY (extractor_version, rcept_no, dcm_no, bundle, subject)
    );

    CREATE TABLE extractor_snapshots (
        extractor_version VARCHAR(32) NOT NULL,
        rcept_no VARCHAR(32) NOT NULL,
        dcm_no VARCHAR(32) NOT NULL,
        payload TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        PRIMARY KEY (extractor_version, rcept_no, dcm_no)
    );

    CREATE INDEX ix_gold_samples_queue
        ON gold_samples (run_id, period, status, queue_order);
    """,
    """
    CREATE TABLE gold_rereview (
        extractor_version TEXT NOT NULL,
        rcept_no TEXT NOT NULL,
        dcm_no TEXT NOT NULL,
        bundle TEXT NOT NULL,
        subject TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (extractor_version, rcept_no, dcm_no, bundle, subject)
    );
    """,
)
