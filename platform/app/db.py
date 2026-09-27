import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from schema import SCHEMA


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def initialize() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


def upsert_project(dataset_path: str, title: str, structure: dict) -> str:
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO projects (id, dataset_path, title, structure)
               VALUES (%s, %s, %s, %s::jsonb)
               ON CONFLICT (dataset_path) DO UPDATE SET title=EXCLUDED.title,
                 structure=EXCLUDED.structure, updated_at=now()
               RETURNING id""",
            (uuid.uuid4(), dataset_path, title, json.dumps(structure)),
        ).fetchone()
        return str(row["id"])


def upsert_asset(project_id: str, dataset_path: str, media_kind: str, role: str,
                 confidence: float, cues: list[str], size_bytes: int | None) -> str:
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO source_assets (id, project_id, dataset_path, media_kind, role, confidence, cues, size_bytes)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
               ON CONFLICT (dataset_path) DO UPDATE SET project_id=EXCLUDED.project_id,
                 role=EXCLUDED.role, confidence=EXCLUDED.confidence, cues=EXCLUDED.cues, size_bytes=EXCLUDED.size_bytes
               RETURNING id""",
            (uuid.uuid4(), project_id, dataset_path, media_kind, role, confidence, json.dumps(cues), size_bytes),
        ).fetchone()
        return str(row["id"])


def create_job(project_id: str, asset_id: str | None, input_path: str, digest: str) -> tuple[str, bool]:
    with connect() as conn:
        existing = conn.execute(
            """SELECT id FROM conversion_jobs
               WHERE input_path=%s AND input_sha256=%s
               ORDER BY created_at DESC LIMIT 1""",
            (input_path, digest),
        ).fetchone()
        if existing:
            return str(existing["id"]), False
        job_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO conversion_jobs (id, project_id, source_asset_id, input_path, input_sha256, state)
               VALUES (%s, %s, %s, %s, %s, 'queued')""",
            (job_id, project_id, asset_id, input_path, digest),
        )
    return job_id, True


def job(job_id: str) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM conversion_jobs WHERE id=%s", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    return row


def set_job(job_id: str, state: str, warning_count: int | None = None, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE conversion_jobs SET state=%s, warning_count=COALESCE(%s, warning_count),
               error_summary=%s, finished_at=CASE WHEN %s IN ('completed','completed_with_warnings','failed') THEN now() ELSE NULL END
               WHERE id=%s""",
            (state, warning_count, error, state, job_id),
        )


def record_stage(job_id: str, stage: str, state: str, command: list[str], exit_code: int | None,
                 stdout: str, stderr: str, metrics: dict) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO conversion_stages (job_id, stage, state, command, exit_code, stdout, stderr, metrics, finished_at)
               VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, now())""",
            (job_id, stage, state, json.dumps(command), exit_code, stdout, stderr, json.dumps(metrics)),
        )


def record_artifact(job_id: str, stage: str, kind: str, path: Path, work_root: Path) -> None:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    with connect() as conn:
        conn.execute(
            """INSERT INTO conversion_artifacts (job_id, stage, kind, work_path, sha256, size_bytes)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (job_id, work_path) DO NOTHING""",
            (job_id, stage, kind, str(path.relative_to(work_root)), digest.hexdigest(), path.stat().st_size),
        )


def job_details(job_id: str) -> dict:
    with connect() as conn:
        result = job(job_id)
        result["stages"] = conn.execute("SELECT stage, state, exit_code, metrics, created_at, finished_at FROM conversion_stages WHERE job_id=%s ORDER BY id", (job_id,)).fetchall()
        result["artifacts"] = conn.execute("SELECT stage, kind, work_path, sha256, size_bytes FROM conversion_artifacts WHERE job_id=%s ORDER BY id", (job_id,)).fetchall()
        result["published"] = conn.execute("SELECT publication, target_path, sha256, size_bytes, created_at FROM published_artifacts WHERE job_id=%s ORDER BY id", (job_id,)).fetchall()
        return result


def oda_artifact(job_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """SELECT j.id AS job_id, j.input_path, a.work_path, a.sha256, a.size_bytes
               FROM conversion_jobs j JOIN conversion_artifacts a ON a.job_id=j.id
               WHERE j.id=%s AND j.state IN ('completed', 'completed_with_warnings')
                 AND a.stage='oda' AND a.kind='dxf'""",
            (job_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"no completed ODA DXF for job {job_id}")
    return row


def completed_oda_artifacts(limit: int | None = None, destination: str = "both") -> list[dict]:
    missing_publications = []
    if destination in {"dataset", "both"}:
        missing_publications.append("dataset_dxf")
    if destination in {"portable", "both"}:
        missing_publications.append("portable_dxf")
    query = """SELECT DISTINCT ON (j.input_path) j.id AS job_id, j.input_path,
                      a.work_path, a.sha256, a.size_bytes
               FROM conversion_jobs j
               JOIN conversion_artifacts a ON a.job_id=j.id
               JOIN conversion_stages s ON s.job_id=j.id
                 AND s.stage='oda' AND s.state='completed'
               WHERE a.stage='oda' AND a.kind='dxf'"""
    params: tuple = ()
    if missing_publications:
        query += """ AND EXISTS (
          SELECT 1 FROM unnest(%s::text[]) wanted(publication)
          WHERE NOT EXISTS (
            SELECT 1
            FROM published_artifacts p
            JOIN conversion_jobs published_job ON published_job.id=p.job_id
            WHERE published_job.input_path=j.input_path
              AND p.publication=wanted.publication
          )
        )"""
        params = (missing_publications,)
    query += " ORDER BY j.input_path, j.created_at DESC"
    if limit:
        query += " LIMIT %s"
        params += (limit,)
    with connect() as conn:
        return conn.execute(query, params).fetchall()


def batch_summary() -> dict:
    with connect() as conn:
        states = conn.execute(
            "SELECT state, count(*) AS count FROM conversion_jobs GROUP BY state ORDER BY state"
        ).fetchall()
        publications = conn.execute(
            """SELECT publication, count(*) AS count, COALESCE(sum(size_bytes), 0) AS size_bytes
               FROM published_artifacts GROUP BY publication ORDER BY publication"""
        ).fetchall()
        oda = conn.execute(
            """SELECT state, count(*) AS count,
                      COALESCE(sum((metrics->>'input_bytes')::bigint), 0) AS input_bytes
               FROM conversion_stages WHERE stage='oda' GROUP BY state ORDER BY state"""
        ).fetchall()
    return {"jobs": states, "oda_stages": oda, "publications": publications}


def failed_libredwg_job_ids(limit: int | None = None) -> list[str]:
    query = """SELECT j.id
               FROM conversion_jobs j
               WHERE j.state='failed'
                 AND EXISTS (
                   SELECT 1 FROM conversion_stages s
                   WHERE s.job_id=j.id AND s.stage='oda' AND s.state='completed'
                 )
               ORDER BY j.created_at"""
    params: tuple = ()
    if limit:
        query += " LIMIT %s"
        params = (limit,)
    with connect() as conn:
        return [str(row["id"]) for row in conn.execute(query, params).fetchall()]


def all_libredwg_job_ids(limit: int | None = None) -> list[str]:
    query = """SELECT DISTINCT ON (j.input_path) j.id
               FROM conversion_jobs j
               WHERE EXISTS (
                 SELECT 1 FROM conversion_stages s
                 WHERE s.job_id=j.id AND s.stage='oda' AND s.state='completed'
               )
               ORDER BY j.input_path, j.created_at DESC"""
    params: tuple = ()
    if limit:
        query = f"SELECT id FROM ({query}) selected LIMIT %s"
        params = (limit,)
    with connect() as conn:
        return [str(row["id"]) for row in conn.execute(query, params).fetchall()]


def record_publication(job_id: str, publication: str, target_path: str, digest: str, size_bytes: int) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO published_artifacts (job_id, publication, target_path, sha256, size_bytes)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (publication, target_path) DO UPDATE SET
                 job_id=EXCLUDED.job_id, sha256=EXCLUDED.sha256, size_bytes=EXCLUDED.size_bytes, created_at=now()""",
            (job_id, publication, target_path, digest, size_bytes),
        )
