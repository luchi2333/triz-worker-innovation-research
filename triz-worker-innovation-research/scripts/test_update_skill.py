"""Offline updater regression tests; never downloads or recursively validates a package."""
import sys
sys.dont_write_bytecode = True
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import update_skill as u


def skill(v):
    return f'---\nname: {u.NAME}\nmetadata:\n  version: "{v}"\n---\n'


def archive(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, content in entries:
            z.writestr(name, content)
    return buffer.getvalue()


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / u.NAME
        self.target.mkdir()
        (self.target / "SKILL.md").write_text(skill("1.0.0"), encoding="utf-8")
        self.remote = {"version": "2.0.0", "commit": "a" * 40}
        self.payload = archive([(f"root/{u.NAME}/SKILL.md", skill("2.0.0"))])

    def perform(self, **kwargs):
        with patch.object(u, "in_git_checkout", return_value=False), patch.object(u, "upstream", return_value=dict(self.remote)), patch.object(u, "fetch", return_value=self.payload), patch.object(u, "validate", **kwargs):
            return u.update(self.target, True)

    def test_semver(self):
        self.assertGreater(u.version("2.10.0"), u.version("2.9.9"))

    def test_wrong_metadata(self):
        for content in ("plain", skill("2.0.0").replace(u.NAME, "other"), skill("2.0.0-beta")):
            with self.assertRaises(ValueError): u.metadata(content)

    def test_check_read_only(self):
        before = u.inventory(self.target)
        with patch.object(u, "upstream", return_value=self.remote), patch.object(u, "fetch") as download:
            self.assertEqual(u.update(self.target)["status"], "UPDATE_AVAILABLE")
            download.assert_not_called()
        self.assertEqual(before, u.inventory(self.target))

    def test_no_downgrade_or_same_version(self):
        for remote, status in (("0.9.0", "LOCAL_AHEAD"), ("1.0.0", "UP_TO_DATE")):
            with patch.object(u, "upstream", return_value=dict(self.remote, version=remote)), patch.object(u, "fetch") as download:
                self.assertEqual(u.update(self.target, True)["status"], status)
                download.assert_not_called()

    def test_unsafe_archives(self):
        for name in ("../evil", "/evil", "root/../evil", "root/x\\evil", f"root/{u.NAME}/CON.txt"):
            with self.assertRaises(ValueError): u.extract(archive([(name, "x")]), self.root / "stage")

    def test_symlink(self):
        item = zipfile.ZipInfo(f"root/{u.NAME}/link")
        item.external_attr = 0o120777 << 16
        with self.assertRaises(ValueError): u.extract(archive([(item, "target")]), self.root / "stage")

    def test_case_collision(self):
        with self.assertRaises(ValueError):
            u.extract(archive([(f"root/{u.NAME}/A", "x"), (f"root/{u.NAME}/a", "y")]), self.root / "stage")

    def test_missing_and_oversize(self):
        with self.assertRaises(ValueError): u.extract(archive([("root/readme", "x")]), self.root / "stage")
        with patch.object(u, "LIMIT", 1), self.assertRaises(ValueError): u.extract(self.payload, self.root / "stage")

    def test_failed_validation_preserves_original(self):
        before = u.inventory(self.target)
        with self.assertRaises(ValueError): self.perform(side_effect=ValueError("invalid"))
        self.assertEqual(before, u.inventory(self.target))

    def test_update_and_rollback(self):
        before = u.inventory(self.target)
        result = self.perform(return_value=None)
        self.assertEqual(result["status"], "UPDATED")
        backup = Path(result["backup"])
        self.assertEqual(before, u.inventory(backup / "skill"))
        self.assertEqual(u.rollback(self.target, backup)["status"], "ROLLED_BACK")
        self.assertEqual(before, u.inventory(self.target))
        self.assertTrue((backup / "replaced/SKILL.md").exists())

    def test_rollback_preserves_new_edits(self):
        result = self.perform(return_value=None)
        (self.target / "custom.txt").write_text("user edit")
        with self.assertRaises(ValueError): u.rollback(self.target, result["backup"])
        self.assertEqual((self.target / "custom.txt").read_text(), "user edit")

    def test_git_checkout_refused(self):
        (self.root / ".git").mkdir()
        with patch.object(u, "upstream", return_value=self.remote), self.assertRaises(ValueError):
            u.update(self.target, True)

    def test_concurrent_edit_refused(self):
        def edit(candidate): (self.target / "edit.txt").write_text("changed")
        with self.assertRaises(ValueError): self.perform(side_effect=edit)
        self.assertTrue((self.target / "edit.txt").exists())

    def test_swap_failure_restores_original(self):
        original = Path.rename
        before = u.inventory(self.target)
        def rename(path, destination):
            if path.parent.name.startswith(".triz-update-"):
                raise OSError("simulated swap failure")
            return original(path, destination)
        with patch.object(Path, "rename", rename), self.assertRaises(OSError): self.perform(return_value=None)
        self.assertEqual(before, u.inventory(self.target))

    def test_commit_pinning(self):
        with patch.object(u, "fetch", side_effect=[json.dumps({"sha": "b" * 40}).encode(), skill("2.0.0").encode()]) as fetch:
            self.assertEqual(u.upstream('main')["commit"], "b" * 40)
            self.assertIn("/" + "b" * 40 + "/", fetch.call_args.args[0])

    def test_lock_exclusion(self):
        with u.lock(self.target):
            with self.assertRaises(FileExistsError):
                with u.lock(self.target): pass

    def test_interrupted_swap_recovery(self):
        folder=self.root/('.'+u.NAME+'-backups')/'interrupted';folder.mkdir(parents=True)
        before=u.inventory(self.target)
        u.receipt_write(folder,dict(state='prepared',target=str(self.target),before=before,installed={}))
        u.move_directory(self.target,folder/'skill')
        self.assertFalse(self.target.exists())
        self.assertEqual(u.recover(self.target,folder)['status'],'RECOVERED_ORIGINAL')
        self.assertEqual(u.inventory(self.target),before)

    def test_recovery_does_not_overwrite_existing_target(self):
        folder=self.root/('.'+u.NAME+'-backups')/'interrupted';folder.mkdir(parents=True)
        import shutil
        shutil.copytree(self.target,folder/'skill')
        u.receipt_write(folder,dict(state='prepared',target=str(self.target),before=u.inventory(self.target),installed={}))
        (self.target/'user.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError,'preserve both'):u.recover(self.target,folder)
        self.assertEqual((self.target/'user.txt').read_text(),'keep')


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if result.wasSuccessful(): print("SKILL_UPDATER_SELF_TEST_PASS")
    raise SystemExit(0 if result.wasSuccessful() else 1)
