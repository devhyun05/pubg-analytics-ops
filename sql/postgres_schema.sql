CREATE SCHEMA IF NOT EXISTS analytics_ops;

CREATE TABLE IF NOT EXISTS analytics_ops.pipeline_runs (
    run_id UUID PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    input_checksum CHAR(64) NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    quality_status TEXT NOT NULL
        CHECK (quality_status IN ('NOT_CHECKED', 'PASS', 'FAIL')),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_seconds NUMERIC(12, 3),
    input_rows BIGINT NOT NULL DEFAULT 0,
    output_rows BIGINT NOT NULL DEFAULT 0,
    failed_rows BIGINT NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_started
    ON analytics_ops.pipeline_runs (pipeline_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_batch
    ON analytics_ops.pipeline_runs (batch_id, started_at DESC);

CREATE TABLE IF NOT EXISTS analytics_ops.quality_check_results (
    run_id UUID NOT NULL
        REFERENCES analytics_ops.pipeline_runs (run_id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL,
    check_name TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PASS', 'FAIL')),
    checked_rows BIGINT NOT NULL,
    error_count BIGINT NOT NULL,
    error_rate NUMERIC(12, 9) NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (run_id, check_name)
);

CREATE INDEX IF NOT EXISTS idx_quality_results_batch_checked
    ON analytics_ops.quality_check_results (batch_id, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_quality_results_status
    ON analytics_ops.quality_check_results (status, checked_at DESC);

CREATE TABLE IF NOT EXISTS analytics_ops.environmental_hotspots (
    batch_id TEXT NOT NULL,
    source_run_id UUID NOT NULL
        REFERENCES analytics_ops.pipeline_runs (run_id),
    map TEXT NOT NULL,
    killed_by TEXT NOT NULL,
    grid_size_m INTEGER NOT NULL CHECK (grid_size_m > 0),
    grid_x INTEGER NOT NULL,
    grid_y INTEGER NOT NULL,
    death_count BIGINT NOT NULL,
    match_count BIGINT NOT NULL,
    date_count BIGINT NOT NULL,
    share_pct NUMERIC(12, 6) NOT NULL,
    heat_rank INTEGER NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        batch_id,
        map,
        killed_by,
        grid_size_m,
        grid_x,
        grid_y
    )
);

CREATE INDEX IF NOT EXISTS idx_hotspots_map_cause_rank
    ON analytics_ops.environmental_hotspots (
        map,
        killed_by,
        heat_rank
    );

CREATE OR REPLACE VIEW analytics_ops.latest_pipeline_runs AS
SELECT DISTINCT ON (pipeline_name)
    run_id,
    pipeline_name,
    batch_id,
    status,
    quality_status,
    started_at,
    finished_at,
    duration_seconds,
    input_rows,
    output_rows,
    failed_rows,
    error_message
FROM analytics_ops.pipeline_runs
ORDER BY pipeline_name, started_at DESC;

CREATE OR REPLACE VIEW analytics_ops.latest_environmental_hotspots AS
WITH latest_successful_run AS (
    SELECT run_id
    FROM analytics_ops.pipeline_runs
    WHERE pipeline_name = 'environmental_hotspot_publish'
      AND status = 'SUCCEEDED'
    ORDER BY finished_at DESC
    LIMIT 1
)
SELECT hotspots.*
FROM analytics_ops.environmental_hotspots AS hotspots
INNER JOIN latest_successful_run
    ON hotspots.source_run_id = latest_successful_run.run_id;

CREATE OR REPLACE VIEW analytics_ops.quality_run_summary AS
SELECT
    runs.run_id,
    runs.batch_id,
    runs.started_at,
    runs.quality_status,
    COUNT(results.check_name) AS check_count,
    COUNT(*) FILTER (WHERE results.status = 'FAIL') AS failed_check_count,
    COALESCE(SUM(results.error_count), 0) AS rule_error_count
FROM analytics_ops.pipeline_runs AS runs
LEFT JOIN analytics_ops.quality_check_results AS results
    ON runs.run_id = results.run_id
GROUP BY
    runs.run_id,
    runs.batch_id,
    runs.started_at,
    runs.quality_status;
