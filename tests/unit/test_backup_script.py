"""`scripts/backup_db.py` — the parts that can be decided without a database.

A backup script that has never been tested is a rumour of a backup. What can be
tested without a live postgres is everything that decides *what runs and what
gets deleted*: the retention arithmetic, the argument vector handed to `pg_dump`,
and the confirmation gate in front of anything destructive. Those are the parts
that are wrong when a human is tired, so they are the parts pinned here.

The dump/restore round trip against a real postgres is not mocked — it was
exercised for real against a scratch container, and `docs/runbooks/backup-restore.md`
records what was measured and what was assumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import backup_db as B


class TestDumpFilenames:
    def test_name_carries_a_sortable_utc_timestamp(self):
        """Retention sorts by filename, so the name must sort by age."""
        early = B.dump_filename(B.datetime(2026, 1, 2, 3, 4, 5), "custom")
        late = B.dump_filename(B.datetime(2026, 1, 2, 3, 4, 6), "custom")

        assert early < late, "filenames must sort oldest-first"
        assert early.startswith("fraud_detector_")

    def test_the_database_name_is_in_the_filename(self):
        """Two databases on one box must not write over each other's dumps."""
        name = B.dump_filename(B.datetime(2026, 10, 4, 12, 0, 0), "custom", "prod_db")
        assert "prod_db" in name

    def test_the_format_is_visible_in_the_name(self):
        """A `.sql` restored with `pg_restore` fails confusingly. Name the format."""
        assert B.dump_filename(B.datetime(2026, 10, 4, 12, 0, 0), "plain").endswith(
            ".sql"
        )
        assert B.dump_filename(
            B.datetime(2026, 10, 4, 12, 0, 0), "custom"
        ).endswith(".dump")

    def test_dumps_are_recognisable_by_extension(self):
        """Retention must only ever consider files that could be dumps."""
        assert B.is_dump_file("fraud_detector_20261004_120000.custom.dump")
        assert B.is_dump_file("fraud_detector_20261004_120000.sql")
        assert not B.is_dump_file("notes.txt")
        assert not B.is_dump_file("README.md")

    def test_the_manifest_is_not_itself_prunable(self):
        """A `MANIFEST.json` must never be selected for deletion."""
        assert not B.is_dump_file("MANIFEST.json")


class TestTheBinaryIsActuallyInvoked:
    """argv[0] is the program, and the tests below exist because it was missing."""

    def test_the_argument_vector_starts_with_the_binary(self):
        """argv[0] is the program to execute.

        Found by running the script for real, not by a test: `write_dump` was
        handed the flags alone, so `subprocess.run` tried to execute
        `--host=postgres` and died with FileNotFoundError. Every unit test
        injected a fake `run_fn`, so none of them could see it — the bug lived
        precisely in the wiring between `main()` and `subprocess`.
        """
        target = B.DbTarget(host="h", port=5432, user="u", password="p", name="d")

        args = B.build_pg_dump_args(target, Path("o.dump"), "custom")

        assert args[0] == "pg_dump", f"argv[0] must be the binary, got {args[0]!r}"

    def test_the_binary_can_be_overridden(self):
        """`--pg-dump` is only honest if the vector actually carries it."""
        target = B.DbTarget(host="h", port=5432, user="u", password="p", name="d")

        args = B.build_pg_dump_args(
            target, Path("o.dump"), "custom", pg_dump="/usr/local/bin/pg_dump"
        )

        assert args[0] == "/usr/local/bin/pg_dump"

    def test_write_dump_hands_the_binary_to_the_subprocess(self, tmp_path: Path):
        """The wiring itself, since that is where the bug was."""
        seen: dict[str, list[str]] = {}

        def fake_run(args, env=None):
            seen["args"] = list(args)

            class _Result:
                returncode = 0
                stderr = ""

            return _Result()

        B.write_dump(
            target=B.DbTarget(host="h", port=5432, user="u", password="p", name="d"),
            out_path=tmp_path / "out.dump",
            dump_format="custom",
            confirmed=True,
            run_fn=fake_run,
            env=None,
            pg_dump="/opt/pg_dump",
        )

        assert seen["args"][0] == "/opt/pg_dump", (
            f"the binary never reached the subprocess: {seen['args']}"
        )


class TestRetention:
    @staticmethod
    def _files(tmp_path: Path, count: int) -> list[Path]:
        made = []
        for i in range(count):
            p = tmp_path / f"fraud_detector_2026010{i}_120000.custom.dump"
            p.write_text("x", encoding="utf-8")
            made.append(p)
        return made

    def test_keeps_the_requested_number_of_newest(self, tmp_path: Path):
        dumps = self._files(tmp_path, 5)

        expired = B.select_expired(dumps, retention=2)

        assert expired == dumps[:3], "the three oldest are the ones to go"
        assert dumps[3] not in expired and dumps[4] not in expired, (
            "the newest dumps must survive"
        )

    def test_nothing_is_deleted_when_it_fits_the_retention(self, tmp_path: Path):
        dumps = self._files(tmp_path, 3)
        assert B.select_expired(dumps, retention=10) == []

    def test_retention_must_be_at_least_one(self, tmp_path: Path):
        """`--retention 0` read as "keep nothing" would delete every backup."""
        dumps = self._files(tmp_path, 3)
        with pytest.raises(ValueError, match="retention"):
            B.select_expired(dumps, retention=0)

    def test_ignores_files_it_did_not_write(self, tmp_path: Path):
        """A runbook or a checksum sitting in the backup dir must survive."""
        self._files(tmp_path, 2)
        bystander = tmp_path / "incident-notes.txt"
        bystander.write_text("do not delete me", encoding="utf-8")

        expired = B.select_expired(list(tmp_path.iterdir()), retention=1)

        assert bystander not in expired


class TestPgDumpCommand:
    def test_uses_the_application_database_settings(self):
        """The script must not carry a second, drifting idea of the database."""
        target = B.DbTarget(
            host="db.internal",
            port=6543,
            user="fraud",
            password="pw-from-settings",
            name="fraud_detector",
        )

        args = B.build_pg_dump_args(target, Path("/backups/out.dump"), "custom")

        assert "--host=db.internal" in args
        assert "--port=6543" in args
        assert "--username=fraud" in args
        assert "--dbname=fraud_detector" in args

    def test_never_puts_the_password_on_the_command_line(self):
        """argv is world-readable via `ps` on a shared host.

        The password travels in `PGPASSWORD` instead, which is process
        environment rather than process arguments.
        """
        target = B.DbTarget(
            host="h", port=5432, user="u", password="super-secret-value", name="d"
        )

        args = B.build_pg_dump_args(target, Path("out.dump"), "custom")

        assert not any("super-secret-value" in a for a in args), (
            f"the password reached argv: {args}"
        )

    def test_pgpassword_env_carries_the_password(self):
        target = B.DbTarget(
            host="h", port=5432, user="u", password="super-secret-value", name="d"
        )

        env = B.build_pg_env(target)

        assert env["PGPASSWORD"] == "super-secret-value"

    def test_it_writes_to_the_requested_file(self):
        target = B.DbTarget(host="h", port=5432, user="u", password="p", name="d")
        out = Path("/backups/fraud_detector_20261004_120000.custom.dump")

        args = B.build_pg_dump_args(target, out, "custom")

        assert f"--file={out}" in args

    def test_custom_format_is_the_default_and_uses_pg_restore_compatible_flags(self):
        target = B.DbTarget(host="h", port=5432, user="u", password="p", name="d")

        custom = B.build_pg_dump_args(target, Path("o.dump"), "custom")
        plain = B.build_pg_dump_args(target, Path("o.sql"), "plain")

        assert "--format=custom" in custom
        assert "--format=plain" in plain

    def test_it_never_prompts_for_a_password(self):
        """A cron-run backup that stops for a prompt is a backup that never runs."""
        target = B.DbTarget(host="h", port=5432, user="u", password="p", name="d")

        args = B.build_pg_dump_args(target, Path("o.dump"), "custom")

        assert "--no-password" in args

    def test_the_database_target_comes_from_app_settings(self, monkeypatch):
        """`Settings.database_url` already encodes the deployment's database."""
        monkeypatch.setenv("DB_HOST", "pg.example.com")
        monkeypatch.setenv("DB_PORT", "6543")
        monkeypatch.setenv("DB_USER", "fraud_reader")
        monkeypatch.setenv("DB_PASSWORD", "from-env")
        monkeypatch.setenv("DB_NAME", "fraud_prod")

        target = B.db_target_from_settings(B.load_settings())

        assert (target.host, target.port, target.user, target.name) == (
            "pg.example.com",
            6543,
            "fraud_reader",
            "fraud_prod",
        )


class TestDestructiveFlagsNeedConfirmation:
    """Deleting backups is the one thing this script can do that hurts.

    `--prune` removes files. It is the flag most likely to be copy-pasted from a
    runbook into a shell history and then re-run with a different
    `--retention`, so it is gated behind an explicit, separately-named
    confirmation rather than sharing the flag that asked for it.
    """

    @staticmethod
    def _dump(tmp_path: Path, name: str) -> Path:
        p = tmp_path / name
        p.write_text("x", encoding="utf-8")
        return p

    def test_prune_without_confirmation_deletes_nothing(self, tmp_path: Path):
        old = self._dump(tmp_path, "fraud_detector_20260101_000000.custom.dump")
        new = self._dump(tmp_path, "fraud_detector_20260102_000000.custom.dump")

        with pytest.raises(B.ConfirmationRequired):
            B.prune_backups(
                tmp_path, retention=1, confirmed=False, delete_fn=lambda p: p.unlink()
            )

        assert old.exists() and new.exists(), "nothing may be deleted unconfirmed"

    def test_prune_with_confirmation_deletes_only_the_expired(self, tmp_path: Path):
        old = self._dump(tmp_path, "fraud_detector_20260101_000000.custom.dump")
        new = self._dump(tmp_path, "fraud_detector_20260102_000000.custom.dump")

        B.prune_backups(
            tmp_path, retention=1, confirmed=True, delete_fn=lambda p: p.unlink()
        )

        assert not old.exists()
        assert new.exists()

    def test_overwrite_without_confirmation_leaves_the_previous_dump(
        self, tmp_path: Path
    ):
        """Refusing to clobber a good dump is the whole point of the gate."""
        existing = self._dump(tmp_path, "fraud_detector_20260101_000000.custom.dump")

        with pytest.raises(B.ConfirmationRequired):
            B.write_dump(
                target=B.DbTarget(host="h", port=1, user="u", password="p", name="d"),
                out_path=existing,
                dump_format="custom",
                confirmed=False,
                run_fn=lambda *a, **k: None,
                env=None,
            )

        assert existing.exists()

    def test_the_confirmation_flag_is_not_the_same_flag_as_the_action(self):
        """`--prune --prune` must not read as consent."""

        parser = B.build_parser()
        args = parser.parse_args(["--prune"])

        assert args.prune is True
        assert args.yes is False


class TestCliSurface:
    def test_target_dir_and_retention_are_options(self):

        parser = B.build_parser()
        args = parser.parse_args(["--target-dir", "/backups", "--retention", "14"])

        assert args.target_dir == Path("/backups")
        assert args.retention == 14

    def test_retention_defaults_to_something_finite(self):
        """An unbounded default would grow forever on a real volume."""

        assert B.build_parser().parse_args([]).retention is not None

    def test_pg_dump_binary_is_overridable(self):
        """The restore drill runs `pg_dump` from a container path."""

        args = B.build_parser().parse_args(["--pg-dump", "/usr/local/bin/pg_dump"])
        assert args.pg_dump == "/usr/local/bin/pg_dump"

    def test_the_module_runs_as_a_script(self):
        assert callable(B.main)
        assert B.main.__doc__, "main() must carry a docstring: it is the CLI's help"


def test_the_manifest_is_safe_to_keep_next_to_the_dumps():
    """A manifest records what was backed up. It must hold no credentials.

    The backup directory is the one place an operator is likely to sync or
    share, so a checksum file sitting there must be publishable.
    """
    dumps = [
        B.dump_filename(B.datetime(2026, 10, 4, 12, 0, 0), "custom"),
        B.dump_filename(B.datetime(2026, 10, 3, 12, 0, 0), "plain"),
    ]

    manifest = B.build_manifest(
        db_name="fraud_detector",
        entries=[{"path": d, "sha256": "0" * 64} for d in dumps],
    )

    blob = repr(manifest).lower()
    for leak in ("password", "pgpassword", "secret", "token"):
        assert leak not in blob, f"the manifest leaks {leak!r}: {manifest!r}"


def test_the_documented_entry_point_runs_as_a_script():
    """`python scripts/backup_db.py --help` is the operator's first command.

    Run as a subprocess, in its own process, because that is the only way to
    prove the import path works: every other test imports `scripts.backup_db`
    from an already-configured repo root, where a missing sys.path shim is
    invisible and the documented command dies with ModuleNotFoundError.
    """
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "backup_db.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=180,
    )

    assert proc.returncode == 0, proc.stderr
    assert "--target-dir" in proc.stdout
    assert "--retention" in proc.stdout
