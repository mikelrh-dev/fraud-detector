#!/usr/bin/env python
"""Take a `pg_dump` of the application database, with a retention policy.

Why a script and not a cron line: the retention rule deletes files, and a cron
line cannot ask whether you meant it. Everything destructive here is behind an
explicit `--yes`, so a copy-pasted command from the runbook does the safe thing.

What this backs up, and what it deliberately does not, is documented in
`docs/runbooks/backup-restore.md`. Short version: the Postgres volume only.
Redis holds the streams and the velocity window, both rebuildable, and a
`pg_dump` of one says nothing about the other.

The database connection is read from `src.core.config.Settings` rather than
duplicated here, so there is exactly one place that knows where the database is.

Usage:
    python scripts/backup_db.py --target-dir ./backups --retention 14
    python scripts/backup_db.py --target-dir ./backups --retention 14 --prune --yes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Same operator-surface contract as scripts/export_labels.py: the documented
# invocation is `python scripts/backup_db.py ...` from the repo root, and
# without this shim that dies with `ModuleNotFoundError: No module named
# 'src'` (imports resolve it, subprocess entry does not).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Seven daily dumps is a week of history. The number that actually matters for
# data loss is the RPO, which is a property of how often this runs, not of how
# many files we keep; see the runbook. Kept finite because an unbounded default
# grows until the volume fills, which is its own outage.
DEFAULT_RETENTION = 7
DEFAULT_TARGET_DIR = Path("backups")
MANIFEST_NAME = "MANIFEST.json"

DUMP_SUFFIXES = (".custom.dump", ".sql")


class BackupError(RuntimeError):
    """The backup could not be taken."""


class ConfirmationRequired(BackupError):
    """A destructive flag was passed without the explicit confirmation.

    Raised rather than warned about. This is the difference between a backup
    script and a data-loss incident, and it must not be a warning someone can
    scroll past in a log at 03:00.
    """


@dataclass(frozen=True)
class DbTarget:
    """Where the database is, and how to authenticate to it."""

    host: str
    port: int
    user: str
    password: str
    name: str


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------


def load_settings():
    """Build `Settings` from the environment.

    A function rather than a module-level `settings` import so that importing
    this module (as the tests do) never triggers the production secret guard,
    and so a test can point it at a scratch database through the same env vars
    an operator would use.
    """
    from src.core.config import Settings

    return Settings()


def db_target_from_settings(settings) -> DbTarget:
    """Read the backup connection out of the application's own settings."""
    return DbTarget(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        name=settings.db_name,
    )


def build_pg_env(target: DbTarget) -> dict[str, str]:
    """The password goes in the environment, never in `argv`.

    `pg_dump` reads `PGPASSWORD`. Anything on the command line is visible to
    every process on the host via `ps` for as long as the dump runs, and a
    backup job is exactly the kind of long-running process someone will notice.
    """
    return {"PGPASSWORD": target.password}


# --------------------------------------------------------------------------
# Naming and retention
# --------------------------------------------------------------------------


def dump_filename(now: datetime, dump_format: str, db_name: str = "fraud_detector") -> str:
    """A dump filename that sorts by age.

    Retention below compares filenames rather than mtimes, so the timestamp has
    to be zero-padded and fixed-width: `2026011` before `20260110` would sort
    wrongly as plain strings.
    """
    stamp = now.strftime("%Y%m%d_%H%M%S")
    suffix = ".custom.dump" if dump_format == "custom" else ".sql"
    return f"{db_name}_{stamp}{suffix}"


def is_dump_file(name: str | Path) -> bool:
    """Could this be one of our dumps?

    Extension-based, deliberately: the database name is configurable, so there
    is no fixed prefix to insist on. The consequence is stated in the runbook —
    keep anything you care about out of the backup directory, because a
    `.sql` file that did not come from this script will be rotated away like
    one that did.
    """
    return str(name).endswith(DUMP_SUFFIXES)


def select_expired(dumps: Iterable[Path], retention: int) -> list[Path]:
    """Which dumps fall outside the retention window, oldest first.

    Pure: it decides, it does not delete. `prune_backups` is where anything is
    removed, which keeps the arithmetic testable without a filesystem that
    anyone has to trust.
    """
    if retention < 1:
        raise ValueError(
            f"retention must be at least 1, got {retention}: a retention of 0 "
            "would mean deleting every backup including the one just taken"
        )
    candidates = sorted(p for p in dumps if is_dump_file(p))
    return candidates[: max(0, len(candidates) - retention)]


def prune_backups(
    target_dir: Path,
    retention: int,
    confirmed: bool,
    delete_fn: Callable[[Path], None] | None = None,
) -> list[Path]:
    """Delete dumps beyond `retention`. Refuses without `confirmed`.

    Note that the check is on the *effect*: an expired set with no confirmation
    raises whether or not the caller asked for `--prune`. A confirmation flag
    that only matters when a separate flag is also present is two flags to keep
    straight at 03:00, and the wrong combination then deletes silently.
    """
    delete = delete_fn if delete_fn is not None else (lambda p: p.unlink())
    expired = select_expired(Path(target_dir).iterdir(), retention)
    if expired and not confirmed:
        raise ConfirmationRequired(
            f"refusing to delete {len(expired)} backup(s) older than the "
            f"retention of {retention}: "
            + ", ".join(p.name for p in expired[:5])
            + ("..." if len(expired) > 5 else "")
            + ". Re-run with --yes to confirm the deletion."
        )
    for path in expired:
        delete(path)
    return expired


# --------------------------------------------------------------------------
# The dump itself
# --------------------------------------------------------------------------


def build_pg_dump_args(
    target: DbTarget,
    out_path: Path,
    dump_format: str,
    pg_dump: str = "pg_dump",
) -> list[str]:
    """The `pg_dump` argument vector, binary first.

    Password-free by construction — see `build_pg_env`.

    `argv[0]` is the program, which is easy to leave off: the flags alone read
    like a complete command, and `subprocess` will happily try to execute
    `--host=...` as a filename. Found by running the script against a real
    server, after every unit test had passed against a stubbed `run_fn`.
    """
    if dump_format not in {"custom", "plain"}:
        raise ValueError(f"unknown dump format: {dump_format!r}")
    return [
        pg_dump,
        f"--host={target.host}",
        f"--port={target.port}",
        f"--username={target.user}",
        f"--dbname={target.name}",
        f"--file={out_path}",
        f"--format={dump_format}",
        # Without this, a wrong password turns a cron backup into a job that
        # hangs on a prompt until someone notices.
        "--no-password",
    ]


def _default_run(args: Sequence[str], env: dict[str, str]):
    return subprocess.run(args, env=env, capture_output=True, text=True, check=False)


def write_dump(
    target: DbTarget,
    out_path: Path,
    dump_format: str,
    confirmed: bool,
    run_fn: Callable[..., object] | None = None,
    env: dict[str, str] | None = None,
    pg_dump: str = "pg_dump",
) -> Path:
    """Run `pg_dump` into `out_path`.

    Refuses to overwrite an existing dump without confirmation: the file already
    there is the last known-good copy, and replacing it with a dump taken during
    a bad window is how a recoverable incident becomes an unrecoverable one.
    """
    out_path = Path(out_path)
    if out_path.exists() and not confirmed:
        raise ConfirmationRequired(
            f"{out_path.name} already exists. Refusing to overwrite the last "
            "known-good dump without confirmation; re-run with --yes."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = build_pg_dump_args(target, out_path, dump_format, pg_dump=pg_dump)
    run = run_fn if run_fn is not None else _default_run
    process_env = {**os.environ, **(env if env is not None else build_pg_env(target))}

    result = run(args, env=process_env)  # type: ignore[call-arg]
    code = getattr(result, "returncode", 0)
    if code != 0:
        # `pg_dump` writes its own diagnostics to stderr; do not swallow them.
        # A truncated dump that "succeeded" is worse than no dump.
        stderr = getattr(result, "stderr", "") or ""
        raise BackupError(f"pg_dump failed (exit {code}): {stderr.strip()}")
    return out_path


def sha256_of(path: Path) -> str:
    """Checksum, read in chunks so a multi-gigabyte dump is not held in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(db_name: str, entries: Sequence[dict]) -> str:
    """A record of what was backed up, safe to store and share.

    Checksums and names only. The backup directory is the one place an operator
    is likely to sync somewhere else, so nothing credential-shaped may end up in
    a file that lives next to the dumps.
    """
    return json.dumps(
        {
            "db_name": db_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entries": list(entries),
        },
        indent=2,
        sort_keys=True,
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="pg_dump the application database and rotate old dumps.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=DEFAULT_TARGET_DIR,
        help="Directory to write the dump into. Created if missing.",
    )
    parser.add_argument(
        "--retention",
        type=int,
        default=DEFAULT_RETENTION,
        help="How many dumps to keep. Older ones are pruned (destructive).",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Rotate old dumps according to --retention. Requires --yes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Confirm the destructive parts: rotating old dumps and "
            "overwriting an existing dump. Never implied by --prune."
        ),
    )
    parser.add_argument(
        "--format",
        dest="dump_format",
        choices=("custom", "plain"),
        default="custom",
        help="pg_dump format. 'custom' needs pg_restore; 'plain' is plain SQL.",
    )
    parser.add_argument(
        "--pg-dump",
        default="pg_dump",
        help="pg_dump binary, for when it is not on PATH.",
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="Skip writing the checksum manifest next to the dump.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Take one backup, then optionally rotate. Returns a process exit code."""
    args = build_parser().parse_args(argv)

    if shutil.which(args.pg_dump) is None and not Path(args.pg_dump).exists():
        print(
            f"error: pg_dump binary not found: {args.pg_dump}. "
            "Install the postgres client, or pass --pg-dump with its path.",
            file=sys.stderr,
        )
        return 2

    try:
        target = db_target_from_settings(load_settings())
        target_dir = Path(args.target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        out_path = target_dir / dump_filename(
            datetime.now(timezone.utc), args.dump_format, target.name
        )
        write_dump(
            target=target,
            out_path=out_path,
            dump_format=args.dump_format,
            confirmed=args.yes,
            env=build_pg_env(target),
            pg_dump=args.pg_dump,
        )
        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"wrote {out_path} ({size_mb:.1f} MiB)")

        if not args.no_manifest:
            manifest_path = target_dir / MANIFEST_NAME
            manifest_path.write_text(
                build_manifest(
                    target.name,
                    [{"path": out_path.name, "sha256": sha256_of(out_path)}],
                ),
                encoding="utf-8",
            )
            print(f"wrote {manifest_path}")

        if args.prune:
            pruned = prune_backups(
                target_dir, retention=args.retention, confirmed=args.yes
            )
            print(f"pruned {len(pruned)} dump(s) beyond retention {args.retention}")
        else:
            print(
                f"retention is {args.retention} but --prune was not passed; "
                "nothing was deleted"
            )
    except ConfirmationRequired as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
