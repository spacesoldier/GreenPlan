import os
import re
import shutil
import subprocess
import hashlib
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from celery_app import app
from db import job, record_artifact, record_stage, set_job

WORK_ROOT = Path(os.environ.get("WORK_ROOT", "/work"))
DATASET_ROOT = Path(os.environ.get("DATASET_ROOT", "/dataset"))
ARCHIVE_ROOT = Path(os.environ.get("ARCHIVE_ROOT", "/archive-extracted"))
INTAKE_ROOT = Path(os.environ.get("INTAKE_ROOT", "/intake"))


def source_path(input_path: str) -> Path:
    """Resolve a virtual dataset path from the dataset or extracted archives."""
    for root in (DATASET_ROOT, ARCHIVE_ROOT):
        candidate = (root / input_path).resolve()
        if root.resolve() in candidate.parents and candidate.is_file():
            return candidate
    raise FileNotFoundError(input_path)


def run(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def domain_connect():
    return psycopg.connect(os.environ["DOMAIN_DATABASE_URL"])


def intake_path(locator: str) -> Path:
    root = INTAKE_ROOT.resolve()
    candidate = (root / locator).resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise FileNotFoundError(locator)
    return candidate


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_intake_attempt(
    revision_id: str,
    asset_id: str,
    stage: str,
    state: str,
    *,
    progress: float,
    command: list[str] | None = None,
    stdout: str = "",
    stderr: str = "",
    metrics: dict | None = None,
    error: str | None = None,
) -> None:
    with domain_connect() as connection:
        current = connection.execute(
            """SELECT attempt_no,state FROM intake.processing_stage_attempts
               WHERE revision_id=%s AND source_asset_id=%s AND stage=%s
               ORDER BY attempt_no DESC LIMIT 1""",
            (revision_id, asset_id, stage),
        ).fetchone()
        if current and (current[1] not in {"completed", "completed_with_warnings", "failed", "blocked", "cancelled"} or state != "running"):
            attempt_no = current[0]
        else:
            attempt_no = (current[0] + 1) if current else 1
        connection.execute(
            """INSERT INTO intake.processing_stage_attempts(
                   revision_id,source_asset_id,stage,attempt_no,state,progress,command,
                   stdout,stderr,metrics,error_summary,started_at,finished_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       CASE WHEN %s='running' THEN now() ELSE NULL END,
                       CASE WHEN %s IN ('completed','completed_with_warnings','failed','blocked','cancelled') THEN now() ELSE NULL END)
               ON CONFLICT (revision_id,source_asset_id,stage,attempt_no) DO UPDATE SET
                 state=EXCLUDED.state,progress=EXCLUDED.progress,command=EXCLUDED.command,
                 stdout=EXCLUDED.stdout,stderr=EXCLUDED.stderr,metrics=EXCLUDED.metrics,
                 error_summary=EXCLUDED.error_summary,
                 started_at=COALESCE(intake.processing_stage_attempts.started_at,EXCLUDED.started_at),
                 finished_at=EXCLUDED.finished_at""",
            (
                revision_id, asset_id, stage, attempt_no, state, progress, Jsonb(command or []),
                stdout, stderr, Jsonb(metrics or {}), error, state, state,
            ),
        )


@app.task(name="tasks.intake_libredwg_probe", bind=True)
def intake_libredwg_probe(
    self, job_id: str, revision_id: str, asset_id: str, source_locator: str, relative_path: str,
) -> dict:
    source = intake_path(source_locator)
    job_dir = INTAKE_ROOT / "jobs" / job_id / "libredwg"
    job_dir.mkdir(parents=True, exist_ok=True)
    output = job_dir / "source.json"
    command = ["dwgread", "-v1", "-O", "JSON", "-o", str(output), str(source)]
    update_intake_attempt(revision_id, asset_id, "direct_dwg_read", "running", progress=0.15, command=command)
    with domain_connect() as connection:
        connection.execute("UPDATE intake.conversion_jobs SET state='libredwg_running' WHERE id=%s", (job_id,))
    try:
        result = run(command, 900)
        findings = [line for line in result.stderr.splitlines() if re.search(r"warning|error|fail|unsupported", line, re.I)]
        metrics = {
            "reader": "LibreDWG",
            "reader_version": os.environ.get("LIBREDWG_VERSION", "unknown"),
            "warning_lines": len(findings),
            "json_bytes": output.stat().st_size if output.exists() else 0,
            "relative_path": relative_path,
            "capability": "diagnostic_partial",
        }
        state = "completed_with_warnings" if findings or result.returncode != 0 else "completed"
        update_intake_attempt(
            revision_id, asset_id, "direct_dwg_read", state, progress=1,
            command=command, stdout=result.stdout, stderr=result.stderr, metrics=metrics,
        )
        with domain_connect() as connection:
            connection.execute(
                """INSERT INTO intake.conversion_stages(
                       job_id,stage,state,command,exit_code,stdout,stderr,metrics,finished_at)
                   VALUES (%s,'libredwg',%s,%s,%s,%s,%s,%s,now())""",
                (job_id, state, Jsonb(command), result.returncode, result.stdout, result.stderr, Jsonb(metrics)),
            )
            connection.execute("UPDATE intake.conversion_jobs SET state='oda_running',warning_count=%s WHERE id=%s", (len(findings), job_id))
    except Exception as exc:
        update_intake_attempt(
            revision_id, asset_id, "direct_dwg_read", "failed", progress=1,
            command=command, error=repr(exc),
        )
        with domain_connect() as connection:
            connection.execute("UPDATE intake.conversion_jobs SET state='oda_running',error_summary=%s WHERE id=%s", (f"LibreDWG: {exc}", job_id))
    finally:
        output.unlink(missing_ok=True)
    intake_oda_convert.apply_async(
        args=[job_id, revision_id, asset_id, source_locator, relative_path], queue="oda",
    )
    return {"job_id": job_id, "next": "oda"}


@app.task(name="tasks.intake_oda_convert", bind=True)
def intake_oda_convert(
    self, job_id: str, revision_id: str, asset_id: str, source_locator: str, relative_path: str,
) -> dict:
    source = intake_path(source_locator)
    job_dir = INTAKE_ROOT / "jobs" / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "oda"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    staged = input_dir / "source.dwg"
    shutil.copy2(source, staged)
    command = ["/usr/local/bin/convert-dwg", str(input_dir), str(output_dir), "0", "1", "*.dwg"]
    update_intake_attempt(revision_id, asset_id, "oda_conversion", "running", progress=0.1, command=command)
    try:
        result = run(command, int(os.environ.get("ODA_TIMEOUT", "900")) + 30)
        outputs = list(output_dir.glob("*.dxf"))
        if result.returncode != 0 or len(outputs) != 1 or outputs[0].stat().st_size == 0:
            raise RuntimeError(f"ODA returned {result.returncode} and produced {len(outputs)} DXF")
        final_dir = INTAKE_ROOT / "derived" / revision_id / asset_id
        final_dir.mkdir(parents=True, exist_ok=True)
        final = final_dir / "source.dxf"
        os.replace(outputs[0], final)
        digest = file_sha256(final)
        locator = final.relative_to(INTAKE_ROOT).as_posix()
        metrics = {
            "converter": "ODA File Converter",
            "input_bytes": source.stat().st_size,
            "output_bytes": final.stat().st_size,
            "output_sha256": digest,
            "target_version": "ACAD2018",
            "relative_path": relative_path,
        }
        update_intake_attempt(
            revision_id, asset_id, "oda_conversion", "completed", progress=1,
            command=command, stdout=result.stdout, stderr=result.stderr, metrics=metrics,
        )
        with domain_connect() as connection:
            connection.execute(
                """INSERT INTO intake.conversion_stages(
                       job_id,stage,state,command,exit_code,stdout,stderr,metrics,finished_at)
                   VALUES (%s,'oda','completed',%s,%s,%s,%s,%s,now())""",
                (job_id, Jsonb(command), result.returncode, result.stdout, result.stderr, Jsonb(metrics)),
            )
            connection.execute(
                """INSERT INTO intake.conversion_artifacts(
                       job_id,source_asset_id,stage,kind,storage_locator,sha256,size_bytes)
                   VALUES (%s,%s,'oda','dxf',%s,%s,%s)
                   ON CONFLICT (job_id,storage_locator) DO NOTHING""",
                (job_id, asset_id, locator, digest, final.stat().st_size),
            )
            row = connection.execute("SELECT warning_count FROM intake.conversion_jobs WHERE id=%s", (job_id,)).fetchone()
            final_state = "completed_with_warnings" if row and row[0] else "completed"
            connection.execute(
                "UPDATE intake.conversion_jobs SET state=%s,finished_at=now(),error_summary=NULL WHERE id=%s",
                (final_state, job_id),
            )
        return {"job_id": job_id, "storage_locator": locator, **metrics}
    except Exception as exc:
        update_intake_attempt(
            revision_id, asset_id, "oda_conversion", "failed", progress=1,
            command=command, error=repr(exc),
        )
        with domain_connect() as connection:
            connection.execute(
                "UPDATE intake.conversion_jobs SET state='failed',error_summary=%s,finished_at=now() WHERE id=%s",
                (f"ODA: {exc}", job_id),
            )
            connection.execute(
                """INSERT INTO intake.fidelity_findings(
                       revision_id,source_asset_id,code,severity,stage,title,detail,evidence)
                   VALUES (%s,%s,'oda_conversion_failed','critical','oda',
                           'DWG не удалось преобразовать в DXF',%s,%s)""",
                (revision_id, asset_id, str(exc), Jsonb({"job_id": job_id})),
            )
        raise


@app.task(name="tasks.oda_convert", bind=True)
def oda_convert(self, job_id: str) -> dict:
    data = job(job_id)
    try:
        source = source_path(data["input_path"])
    except FileNotFoundError:
        set_job(job_id, "failed", error="input is outside dataset or does not exist")
        raise
    job_dir = WORK_ROOT / "jobs" / job_id
    input_dir, output_dir = job_dir / "input", job_dir / "oda"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    staged = input_dir / "source.dwg"
    shutil.copy2(source, staged)
    set_job(job_id, "oda_running")
    command = ["/usr/local/bin/convert-dwg", str(input_dir), str(output_dir), "0", "1", "*.dwg"]
    try:
        result = run(command, int(os.environ.get("ODA_TIMEOUT", "900")) + 30)
    except Exception as exc:
        record_stage(job_id, "oda", "failed", command, None, "", repr(exc), {})
        set_job(job_id, "failed", error=f"ODA launcher: {exc}")
        raise
    dxf_files = list(output_dir.glob("*.dxf"))
    metrics = {"dxf_count": len(dxf_files), "input_bytes": staged.stat().st_size}
    state = "completed" if result.returncode == 0 and len(dxf_files) == 1 else "failed"
    record_stage(job_id, "oda", state, command, result.returncode, result.stdout, result.stderr, metrics)
    record_artifact(job_id, "input", "dwg", staged, WORK_ROOT)
    for file in dxf_files:
        record_artifact(job_id, "oda", "dxf", file, WORK_ROOT)
    if state == "failed":
        set_job(job_id, "failed", error="ODA did not produce exactly one DXF")
        raise RuntimeError("ODA did not produce exactly one DXF")
    set_job(job_id, "libredwg_queued")
    libredwg_probe.apply_async(args=[job_id], queue="libredwg")
    return {"job_id": job_id, **metrics}


@app.task(name="tasks.libredwg_probe", bind=True)
def libredwg_probe(self, job_id: str) -> dict:
    data = job(job_id)
    set_job(job_id, "libredwg_running")
    job_dir = WORK_ROOT / "jobs" / job_id
    staged, output = job_dir / "input" / "source.dwg", job_dir / "libredwg" / "source.json"
    if not staged.exists():
        try:
            source = source_path(data["input_path"])
        except FileNotFoundError:
            set_job(job_id, "failed", error="LibreDWG source is outside dataset or missing")
            raise
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, staged)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["dwgread", "-v1", "-O", "JSON", "-o", str(output), str(staged)]
    try:
        result = run(command, 900)
    except Exception as exc:
        record_stage(job_id, "libredwg", "failed", command, None, "", repr(exc), {})
        set_job(job_id, "failed", error=f"LibreDWG launcher: {exc}")
        if os.environ.get("WORK_KEEP_INPUT", "false").lower() not in {"1", "true", "yes"}:
            staged.unlink(missing_ok=True)
        if os.environ.get("LIBREDWG_KEEP_JSON", "false").lower() not in {"1", "true", "yes"}:
            output.unlink(missing_ok=True)
        raise
    findings = [line for line in result.stderr.splitlines() if re.search(r"warning|error|fail|unsupported", line, re.I)]
    metrics = {
        "libredwg_version": os.environ.get("LIBREDWG_VERSION", "unknown"),
        "warning_lines": len(findings),
        "json_bytes": output.stat().st_size if output.exists() else 0,
    }
    state = "completed" if result.returncode == 0 and output.exists() else "failed"
    record_stage(job_id, "libredwg", state, command, result.returncode, result.stdout, result.stderr, metrics)
    keep_json = os.environ.get("LIBREDWG_KEEP_JSON", "false").lower() in {"1", "true", "yes"}
    if output.exists() and keep_json:
        record_artifact(job_id, "libredwg", "json", output, WORK_ROOT)
    if output.exists() and not keep_json:
        output.unlink()
    if os.environ.get("WORK_KEEP_INPUT", "false").lower() not in {"1", "true", "yes"}:
        staged.unlink(missing_ok=True)
    if state == "failed":
        set_job(job_id, "failed", warning_count=len(findings), error="LibreDWG did not produce JSON")
        raise RuntimeError("LibreDWG did not produce JSON")
    set_job(job_id, "completed_with_warnings" if findings else "completed", warning_count=len(findings))
    return {"job_id": job_id, **metrics}


@app.task(name="tasks.libredwg_dxf_probe", bind=True)
def libredwg_dxf_probe(self, job_id: str) -> dict:
    """Exercise LibreDWG's DXF writer without treating it as the canonical export."""
    data = job(job_id)
    job_dir = WORK_ROOT / "jobs" / job_id
    staged = job_dir / "input" / "source.dwg"
    output = job_dir / "libredwg-dxf" / "source.dxf"
    if not staged.exists():
        source = source_path(data["input_path"])
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, staged)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["dwg2dxf", "-v1", "--as", "r2018", "-y", "-o", str(output), str(staged)]
    try:
        result = run(command, 900)
    except Exception as exc:
        record_stage(job_id, "libredwg_dxf", "failed", command, None, "", repr(exc), {
            "libredwg_version": os.environ.get("LIBREDWG_VERSION", "unknown")
        })
        raise
    findings = [line for line in result.stderr.splitlines() if re.search(r"warning|error|fail|unsupported", line, re.I)]
    metrics = {
        "libredwg_version": os.environ.get("LIBREDWG_VERSION", "unknown"),
        "warning_lines": len(findings),
        "dxf_bytes": output.stat().st_size if output.exists() else 0,
        "target_version": "r2018",
    }
    state = "completed" if result.returncode == 0 and output.is_file() and output.stat().st_size > 0 else "failed"
    record_stage(job_id, "libredwg_dxf", state, command, result.returncode, result.stdout, result.stderr, metrics)
    output.unlink(missing_ok=True)
    if os.environ.get("WORK_KEEP_INPUT", "false").lower() not in {"1", "true", "yes"}:
        staged.unlink(missing_ok=True)
    if state == "failed":
        raise RuntimeError("LibreDWG did not produce DXF")
    return {"job_id": job_id, **metrics}
