"""Update from a checksummed stable GitHub Release, or explicitly opt into main."""
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


def upstream(channel='stable'):
    release=None;ref='main'
    if channel=='stable':
        release=json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases/latest',1024*1024))
        ref=release.get('tag_name','')
        if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'v\d+\.\d+\.\d+',ref):
            raise ValueError('Latest release is not a supported stable version')
    elif channel!='main':raise ValueError('Unsupported update channel')
    commit = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/{ref}", 1024 * 1024))["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid upstream commit")
    content = fetch(f"https://raw.githubusercontent.com/{REPO}/{commit}/{NAME}/SKILL.md", 256 * 1024)
    result={"commit": commit, "version": metadata(content.decode("utf-8-sig")), 'channel':channel}
    if release is not None:
        if ref!='v'+result['version']:raise ValueError('Release tag/version mismatch')
        archive=f'{NAME}-{ref}.zip'
        assets={a.get('name'):a for a in release.get('assets',[]) if a.get('state')=='uploaded'}
        result.update(tag=ref,release_ready=archive in assets and 'release-manifest.json' in assets)
        if result['release_ready']:
            base=f'https://github.com/{REPO}/releases/download/{ref}/'
            for key,name in [('archive_url',archive),('manifest_url','release-manifest.json')]:
                if assets[name].get('browser_download_url')!=base+name:raise ValueError('Unexpected release asset URL')
                result[key]=base+name
    return result


def checked_archive(remote):
    if remote.get('channel')!='stable':
        return fetch(f"https://codeload.github.com/{REPO}/zip/{remote['commit']}",LIMIT), None
    if not remote.get('release_ready'):raise ValueError('Stable release lacks archive/checksum manifest; no automatic main fallback')
    manifest=json.loads(fetch(remote['manifest_url'],1024*1024))
    if any(manifest.get(k)!=v for k,v in [('skill',NAME),('version',remote['version']),('commit',remote['commit'])]):
        raise ValueError('Release manifest identity mismatch')
    if manifest.get('archive')!=remote['archive_url'].rsplit('/',1)[-1]:raise ValueError('Release archive name mismatch')
    payload=fetch(remote['archive_url'],LIMIT)
    if hashlib.sha256(payload).hexdigest()!=manifest.get('archive_sha256'):raise ValueError('Release archive checksum mismatch')
    if not isinstance(manifest.get('files'),dict) or not manifest['files']:raise ValueError('Release missing file hash inventory')
    return payload,manifest


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
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
    except FileExistsError as exc:
        raise FileExistsError(f'Updater lock exists: {path}; PID={path.read_text(encoding="utf-8")}. Check the process before removing a stale lock.') from exc
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


def recover(target, folder):
    """Explicit recovery of an interrupted swap; no files are overwritten."""
    target=Path(target).absolute()
    if target.name!=NAME:raise ValueError('Recovery target must use the skill directory name')
    folder=Path(folder).resolve(strict=True)
    expected=(target.parent/('.'+NAME+'-backups')).resolve()
    if folder.parent!=expected:raise ValueError('Recovery backup outside target backup directory')
    record=json.loads((folder/'receipt-prepared.json').read_text(encoding='utf-8'))
    if Path(record['target']).resolve()!=target.resolve():raise ValueError('Recovery target mismatch')
    backup=folder/'skill'
    if not backup.is_dir() or inventory(backup)!=record['before']:raise ValueError('Recovery backup missing or changed')
    if target.exists():
        target=target_path(target)
        current=inventory(target)
        if current==record['installed']:
            record['state']='installed';receipt_write(folder,record)
            return {'status':'RECOVERED_INSTALLED','backup':str(folder)}
        raise ValueError('Recovery target exists with different files; preserve both and inspect manually')
    # Resolving the parent also rejects recovery through a relocated installation.
    if target.parent.resolve()!=Path(record['target']).parent.resolve():raise ValueError('Recovery parent changed')
    move_directory(backup,target)
    record['state']='recovered_original';receipt_write(folder,record)
    return {'status':'RECOVERED_ORIGINAL','target':str(target)}


def update(target, apply=False, channel='stable'):
    local = metadata((target / "SKILL.md").read_text(encoding="utf-8-sig"))
    remote = upstream(channel)
    status = "LOCAL_AHEAD" if version(local) > version(remote["version"]) else "UP_TO_DATE" if local == remote["version"] else "UPDATE_AVAILABLE"
    result = dict(status=status, local_version=local, remote_version=remote["version"], commit=remote["commit"], target=str(target))
    result.update(channel=channel,release_ready=remote.get('release_ready'))
    if not apply or status != "UPDATE_AVAILABLE":
        return result
    if in_git_checkout(target):
        raise ValueError("Refusing to replace a Git checkout; use an installed skill target")
    before = inventory(target)
    payload, release_manifest = checked_archive(remote)
    with tempfile.TemporaryDirectory(prefix=".triz-update-", dir=target.parent) as temporary:
        candidate = Path(temporary) / NAME
        candidate.mkdir()
        extract(payload, candidate)
        if metadata((candidate / "SKILL.md").read_text(encoding="utf-8-sig")) != remote["version"]:
            raise ValueError("Downloaded version differs from pinned metadata")
        if release_manifest is not None and inventory(candidate)!=release_manifest['files']:
            raise ValueError('Release file inventory mismatch')
        validate(candidate)
        remote["archive_sha256"] = hashlib.sha256(payload).hexdigest()
        return install(target, candidate, remote, before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", metavar="BACKUP_DIRECTORY")
    mode.add_argument('--recover',metavar='BACKUP_DIRECTORY')
    parser.add_argument("--target", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument('--channel',choices=['stable','main'],default='stable')
    args = parser.parse_args()
    try:
        if args.recover:
            target=Path(args.target).absolute()
            with lock(target):result=recover(target,args.recover)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        target = target_path(args.target)
        if args.apply or args.rollback:
            with lock(target):
                result = rollback(target, args.rollback) if args.rollback else update(target, True, args.channel)
        else:
            result = update(target, channel=args.channel)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
