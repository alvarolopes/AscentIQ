"""Local encrypted backups; verify every file before reporting success."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from dashboard.settings import default_tz

MAGIC = b"ASCENTIQ-BACKUP-1\n"
CHUNK = 1024 * 1024


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def decrypt(archive, key, target):
    size = archive.stat().st_size
    with archive.open("rb") as source, target.open("wb") as dest:
        if source.read(len(MAGIC)) != MAGIC:
            raise RuntimeError("Invalid backup format")
        nonce = source.read(12)
        source.seek(-16, 2)
        tag = source.read(16)
        source.seek(len(MAGIC) + 12)
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        cipher.authenticate_additional_data(MAGIC)
        remaining = size - len(MAGIC) - 12 - 16
        while remaining:
            block = source.read(min(CHUNK, remaining))
            if not block:
                raise RuntimeError("Truncated backup")
            dest.write(cipher.update(block))
            remaining -= len(block)
        dest.write(cipher.finalize())


def verify(archive: Path, key_path: Path, temp_root: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(dir=temp_root) as folder:
        plain = Path(folder) / "restore.tar.gz"
        decrypt(archive, key_path.read_bytes(), plain)
        with tarfile.open(plain, "r:gz") as tar:
            manifest_stream = tar.extractfile("backup-manifest.json")
            if manifest_stream is None:
                raise RuntimeError("Invalid backup format")
            manifest = json.load(manifest_stream)
            seen = set()
            for item in tar:
                if not item.isfile() or item.name == "backup-manifest.json":
                    continue
                if item.name not in manifest or item.name in seen:
                    raise RuntimeError("Unexpected archive entry")
                seen.add(item.name)
                h = hashlib.sha256()
                stream = tar.extractfile(item)
                if stream is None:
                    raise RuntimeError("Unexpected archive entry")
                with stream:
                    while block := stream.read(CHUNK):
                        h.update(block)
                if h.hexdigest() != manifest[item.name]:
                    raise RuntimeError("Backup checksum mismatch")
            if seen != set(manifest):
                raise RuntimeError("Missing archive entry")
        return {"verified": True, "files": len(manifest), "sha256": file_hash(archive)}


def create_backup(root: Path, output: Path, *, database: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    key_path = output / "recovery.key"
    if not key_path.exists():
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(os.urandom(32))
    key = key_path.read_bytes()
    if len(key) != 32:
        raise RuntimeError("Invalid recovery key")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    archive = output / f"ascentiq-{stamp}.tar.gz.enc"
    with tempfile.TemporaryDirectory(dir=output) as folder:
        temp = Path(folder)
        extras = []
        if database:
            from dashboard.repository import PostgresRepository, connect, contents_digest

            dump = temp / "postgres.dump"
            with connect() as conn:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                snapshot = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
                revision = conn.execute("SELECT active_revision FROM athlete.state WHERE singleton").fetchone()[0]
                _, files = PostgresRepository().files(revision)
                dumped = subprocess.run(
                    ["pg_dump", "-Fc", "--snapshot", snapshot, "-f", str(dump)], capture_output=True
                )
                if dumped.returncode:
                    raise RuntimeError("Database backup failed")
                metadata = temp / "database-manifest.json"
                metadata.write_text(
                    json.dumps({"revision": str(revision), "datasets_digest": contents_digest(files)}), encoding="utf-8"
                )
            extras.append((dump, "database/postgres.dump"))
            extras.append((metadata, "database/manifest.json"))
        members = []
        for base in ("data", "analysis", "activities", "runtime", "docs", "scripts", "dashboard"):
            for path in sorted((root / base).rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(root)
                if any(
                    part in {"backups", "node_modules", "dist", "__pycache__", "staging", "workspaces"}
                    for part in rel.parts
                ):
                    continue
                if output.resolve() in path.resolve().parents:
                    continue
                members.append((path, "files/" + rel.as_posix()))
        for name in (".env", "compose.yaml"):
            if (root / name).is_file():
                members.append((root / name, "files/" + name))
        members += extras
        manifest = {name: file_hash(path) for path, name in members}
        manifest_file = temp / "manifest.json"
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        plain = temp / "backup.tar.gz"
        with tarfile.open(plain, "w:gz") as tar:
            for path, name in members:
                tar.add(path, arcname=name, recursive=False)
            tar.add(manifest_file, arcname="backup-manifest.json")
        nonce = os.urandom(12)
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
        cipher.authenticate_additional_data(MAGIC)
        pending = archive.with_suffix(".pending")
        with plain.open("rb") as source, pending.open("wb") as dest:
            dest.write(MAGIC + nonce)
            for block in iter(lambda: source.read(CHUNK), b""):
                dest.write(cipher.update(block))
            dest.write(cipher.finalize())
            dest.write(cipher.tag)
        pending.chmod(0o600)
        verification = verify(pending, key_path, output)
        pending.replace(archive)
    result = {
        **verification,
        "archive": archive.name,
        "database": database,
        "created_at": stamp,
        "local_date": datetime.now(default_tz()).date().isoformat(),
    }
    (output / "latest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/app"))
    parser.add_argument("--output", type=Path, default=Path("/app/runtime/backups"))
    parser.add_argument("--database", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    result = (
        verify(args.verify, args.output / "recovery.key", args.output)
        if args.verify
        else create_backup(args.root, args.output, database=args.database)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
