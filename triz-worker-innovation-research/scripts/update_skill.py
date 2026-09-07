"""Check/update the installed skill from the pinned GitHub main commit; retain rollback."""
import sys
sys.dont_write_bytecode = True
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import time
import urllib.request
import uuid
import zipfile

NAME = "triz-worker-innovation-research"
REPO = "luchi2333/" + NAME
LIMIT = 50 * 1024 * 1024


def metadata(text):
    front = text.split("---", 2)
    if len(front) != 3 or front[0].strip():
        raise ValueError("Missing skill frontmatter")
    if not re.search(r"(?m)^name: " + NAME + r"\s*$", front[1]):
        raise ValueError("Unexpected skill name")
    match = re.search(r'(?m)^  version: [\"\x27]?(\d+\.\d+\.\d+)[\"\x27]?\s*$', front[1])
    if not match:
        raise ValueError("Expected stable major.minor.patch version")
    return match[1]


def version(value):
    return tuple(map(int, value.split(".")))


def fetch(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": NAME + "-updater"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Download exceeds size limit")
    return data


def upstream():
    commit = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/main", 1024 * 1024))["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid upstream commit")
    content = fetch(f"https://raw.githubusercontent.com/{REPO}/{commit}/{NAME}/SKILL.md", 256 * 1024)
    return {"commit": commit, "version": metadata(content.decode("utf-8-sig"))}


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Linked files/directories are not supported")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def target_path(value):
    raw = Path(value).absolute()
    for path in (raw, *raw.parents):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Target must not pass through a link/junction")
    target = raw.resolve(strict=True)
    metadata((target / "SKILL.md").read_text(encoding="utf-8-sig"))
    return target


def extract(payload, destination):
    seen, total, count = set(), 0, 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if len(archive.infolist()) > 10000:
            raise ValueError("Too many archive entries")
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename).parts
            if (entry.filename.startswith("/") or "\\" in entry.filename or
                    any(p in ("..", ".") or ":" in p or p.endswith((" ", ".")) for p in parts)):
                raise ValueError("Unsafe archive path")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Archive links are forbidden")
            if len(parts) < 3 or parts[1] != NAME or entry.is_dir():
                continue
            relative = Path(*parts[2:])
            if any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in relative.parts):
                raise ValueError("Reserved archive path")
            key = relative.as_posix().casefold()
            if key in seen:
                raise ValueError("Duplicate archive path")
            seen.add(key)
            total += entry.file_size
            if total > LIMIT:
                raise ValueError("Expanded archive exceeds limit")
            output = destination / relative
            output.resolve().relative_to(destination.resolve())
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(entry))
            count += 1
    if not count:
        raise ValueError("Skill payload missing")


def validate(candidate):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    run = subprocess.run([sys.executable, "-B", str(candidate / "scripts/validate_skill.py"), "--strict"],
                         cwd=candidate, env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
    try:
        passed = json.loads(run.stdout)["status"] == "PASS"
    except (ValueError, KeyError):
        passed = False
    if run.returncode or not passed:
        raise ValueError("Downloaded package failed strict validation; original retained. " + (run.stderr or run.stdout)[-2000:])


def receipt_write(folder, record):
    content = json.dumps(record, ensure_ascii=False, indent=2)
    # Keep a separate per-state journal even if the process stops while writing the index.
    (folder / ("receipt-" + record["state"] + ".json")).write_text(content, encoding="utf-8")
    with (folder / "receipt.json").open("w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


@contextlib.contextmanager
def lock(target):
    path = target.parent / ("." + target.name + ".update.lock")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        path.unlink()


def move_directory(source, destination):
    if destination.exists():
        raise FileExistsError(str(destination))
    source.rename(destination)


def install(target, candidate, remote, before):
    if inventory(target) != before:
        raise ValueError("Target changed during download; update cancelled")
    after = inventory(candidate)
    folder = target.parent / ("." + NAME + "-backups") / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    record = dict(target=str(target), before=before, installed=after, upstream=remote, state="prepared")
    receipt_write(folder, record)
    move_directory(target, folder / "skill")
    try:
        move_directory(candidate, target)
        if inventory(target) != after:
            raise ValueError("Installed hashes differ")
        record["state"] = "installed"
        receipt_write(folder, record)
    except BaseException:
        if target.exists():
            move_directory(target, folder / "failed-candidate")
        move_directory(folder / "skill", target)
        raise
    return {"status": "UPDATED", "version": remote["version"], "commit": remote["commit"], "backup": str(folder)}


def rollback(target, folder):
    folder = Path(folder).resolve(strict=True)
    expected = (target.parent / ("." + NAME + "-backups")).resolve()
    if folder.parent != expected:
        raise ValueError("Backup must be in the target updater backup directory")
    record = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
    if record["target"] != str(target) or record["state"] != "installed":
        raise ValueError("Backup does not describe an installed update for this target")
    if inventory(target) != record["installed"] or inventory(folder / "skill") != record["before"]:
        raise ValueError("Current skill or backup changed; rollback refused to preserve edits")
    move_directory(target, folder / "replaced")
    try:
        move_directory(folder / "skill", target)
    except BaseException:
        move_directory(folder / "replaced", target)
        raise
    record["state"] = "rolled_back"
    receipt_write(folder, record)
    return {"status": "ROLLED_BACK", "preserved_new_version": str(folder / "replaced")}


def in_git_checkout(target):
    return any((p / ".git").exists() for p in (target, *target.parents))


def update(target, apply=False):
    local = metadata((target / "SKILL.md").read_text(encoding="utf-8-sig"))
    remote = upstream()
    status = "LOCAL_AHEAD" if version(local) > version(remote["version"]) else "UP_TO_DATE" if local == remote["version"] else "UPDATE_AVAILABLE"
    result = dict(status=status, local_version=local, remote_version=remote["version"], commit=remote["commit"], target=str(target))
    if not apply or status != "UPDATE_AVAILABLE":
        return result
    if in_git_checkout(target):
        raise ValueError("Refusing to replace a Git checkout; use an installed skill target")
    before = inventory(target)
    payload = fetch(f"https://codeload.github.com/{REPO}/zip/{remote['commit']}", LIMIT)
    with tempfile.TemporaryDirectory(prefix=".triz-update-", dir=target.parent) as temporary:
        candidate = Path(temporary) / NAME
        candidate.mkdir()
        extract(payload, candidate)
        if metadata((candidate / "SKILL.md").read_text(encoding="utf-8-sig")) != remote["version"]:
            raise ValueError("Downloaded version differs from pinned metadata")
        validate(candidate)
        remote["archive_sha256"] = hashlib.sha256(payload).hexdigest()
        return install(target, candidate, remote, before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", metavar="BACKUP_DIRECTORY")
    parser.add_argument("--target", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args()
    try:
        target = target_path(args.target)
        if args.apply or args.rollback:
            with lock(target):
                result = rollback(target, args.rollback) if args.rollback else update(target, True)
        else:
            result = update(target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
