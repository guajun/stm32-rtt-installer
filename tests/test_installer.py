import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "src/installer.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def git(cwd, *args):
    return subprocess.check_output(["git", "-C", str(cwd), *args], stderr=subprocess.STDOUT).decode().strip()


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stm32-rtt-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        git(self.upstream, "init")
        git(self.upstream, "config", "user.name", "Test")
        git(self.upstream, "config", "user.email", "test@example.com")
        for name in ("RTT/SEGGER_RTT.c", "RTT/SEGGER_RTT.h", "RTT/SEGGER_RTT_printf.c", "Config/SEGGER_RTT_Conf.h", "LICENSE.md"):
            p = self.upstream / name
            p.parent.mkdir(exist_ok=True)
            p.write_text("/* test fixture */\n")
        git(self.upstream, "add", ".")
        git(self.upstream, "commit", "-m", "fixture")
        git(self.upstream, "tag", "V8.9")
        git(self.upstream, "tag", "V8.10")
        self.archive = self.root / "RTT fixture.zip"
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for required in installer.REQUIRED:
                bundle.write(self.upstream / required, "RTT-8.9/" + required)
        self.project = self.root / "project with spaces"
        (self.project / "cmake/stm32cubemx").mkdir(parents=True)
        (self.project / "cmake/stm32cubemx/CMakeLists.txt").write_text("")
        self.cmake = self.project / "CMakeLists.txt"
        self.cmake.write_bytes(b"cmake_minimum_required(VERSION 3.22)\r\nproject(firmware C)\r\nadd_executable(${CMAKE_PROJECT_NAME} main.c)\r\n")
        (self.project / "main.c").write_text("int main(void) { return 0; }\n")
        git(self.project, "init")
        git(self.project, "config", "user.name", "Test")
        git(self.project, "config", "user.email", "test@example.com")
        git(self.project, "add", ".")
        git(self.project, "commit", "-m", "fixture")
        # Test-only opt in to local Git transport; production inherits Git's defaults.
        self.env = patch.dict(os.environ, {"GIT_ALLOW_PROTOCOL": "file"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def args(self, *extra):
        base = ["--project", str(self.project)]
        if "submodule" in extra:
            return [*base, "--repository", str(self.upstream), *extra]
        return [*base, "--archive", str(self.archive), "--mode", "source", *extra]

    def run_install(self, *extra):
        installer.main(self.args(*extra))

    def test_source_pinned_and_idempotent_crlf(self):
        self.run_install("--version", "V8.9", "--directory", "DebugRTT")
        state = json.loads((self.project / installer.MANIFEST).read_text())
        self.assertEqual(state["version"], "V8.9")
        self.assertFalse((self.project / "DebugRTT/.git").exists())
        self.assertTrue((self.project / "DebugRTT/LICENSE.md").is_file())
        before = self.cmake.read_bytes()
        self.run_install("--version", "V8.9", "--directory", "DebugRTT")
        self.assertEqual(before, self.cmake.read_bytes())
        self.assertNotIn(b"\n", before.replace(b"\r\n", b""))

    def test_latest_numeric_sort(self):
        with patch.object(installer, "api", side_effect=[[{"name": "V8.9"}, {"name": "V8.10"}], {"sha": "a" * 40}]), patch.object(installer, "read_url", return_value=self.archive.read_bytes()):
            installer.main(["--project", str(self.project), "--mode", "source"])
        self.assertEqual(json.loads((self.project / installer.MANIFEST).read_text())["version"], "V8.10")

    def test_submodule_and_unrelated_staging(self):
        (self.project / "other.txt").write_text("keep staged")
        git(self.project, "add", "other.txt")
        self.run_install("--mode", "submodule", "--version", "V8.9")
        self.assertTrue((self.project / "SEGGER_RTT/.git").is_file())
        self.assertIn("160000", git(self.project, "ls-files", "--stage", "SEGGER_RTT"))
        self.assertIn("other.txt", git(self.project, "diff", "--cached", "--name-only"))
        self.assertEqual(git(self.project / "SEGGER_RTT", "rev-parse", "HEAD"), git(self.upstream, "rev-parse", "V8.9"))
        self.run_install("--mode", "submodule", "--version", "V8.9")

    def test_reserved_and_traversal_rejected_before_write(self):
        original = self.cmake.read_bytes()
        for name in ("Middlewares", "middlewares", "Core", "Drivers", "../outside", "foo/bar", "A;evil", "NUL", "COM1"):
            with self.subTest(name=name), self.assertRaises(installer.InstallError):
                self.run_install("--directory", name)
        self.assertEqual(original, self.cmake.read_bytes())

    def test_invalid_version_and_existing_directory_leave_project_untouched(self):
        original = self.cmake.read_bytes()
        with self.assertRaises(installer.InstallError):
            self.run_install("--archive", str(self.root / "missing.zip"))
        self.assertFalse((self.project / "SEGGER_RTT").exists())
        (self.project / "SEGGER_RTT").mkdir()
        with self.assertRaises(installer.InstallError):
            self.run_install()
        self.assertEqual(original, self.cmake.read_bytes())

    def test_modified_source_and_different_options_rejected(self):
        self.run_install()
        with self.assertRaises(installer.InstallError):
            self.run_install("--version", "V8.9")
        (self.project / "SEGGER_RTT/RTT/SEGGER_RTT.c").write_text("edited")
        with self.assertRaises(installer.InstallError):
            self.run_install()

    def test_rollback_on_final_write_failure(self):
        original = self.cmake.read_bytes()
        write = Path.write_bytes
        def fail_manifest(path, data):
            if path.name == installer.MANIFEST:
                raise OSError("simulated disk failure")
            return write(path, data)
        with patch.object(Path, "write_bytes", fail_manifest), self.assertRaises(OSError):
            self.run_install()
        self.assertEqual(original, self.cmake.read_bytes())
        self.assertFalse((self.project / "SEGGER_RTT").exists())
        self.assertFalse((self.project / installer.INTEGRATION).exists())

    def test_existing_manual_integration_rejected(self):
        with self.cmake.open("a") as f:
            f.write("# SEGGER_RTT/RTT/SEGGER_RTT.c\n")
        with self.assertRaises(installer.InstallError):
            self.run_install()

    def test_submodule_rollback_restores_index_and_metadata(self):
        original = self.cmake.read_bytes()
        before = git(self.project, "ls-files", "--stage")
        write = Path.write_bytes
        def fail_manifest(path, data):
            if path.name == installer.MANIFEST:
                raise OSError("simulated write failure")
            return write(path, data)
        with patch.object(Path, "write_bytes", fail_manifest), self.assertRaises(OSError):
            self.run_install("--mode", "submodule")
        self.assertEqual(before, git(self.project, "ls-files", "--stage"))
        self.assertEqual(original, self.cmake.read_bytes())
        self.assertFalse((self.project / ".gitmodules").exists())
        self.assertFalse((self.project / ".git/modules/stm32-rtt").exists())
        self.assertFalse((self.project / "SEGGER_RTT").exists())

    def test_explicit_target(self):
        self.run_install("--target", "my_firmware")
        self.assertIn("target_sources(my_firmware PRIVATE", (self.project / installer.INTEGRATION).read_text())

    def test_shell_entrypoint(self):
        shell = shutil.which("sh") or ("C:/Program Files/Git/bin/sh.exe" if os.name == "nt" else None)
        if not shell:
            self.skipTest("sh not available")
        subprocess.run([shell, str(ROOT / "dist/install.sh"), *self.args("--version", "V8.9")], check=True, stdout=subprocess.PIPE)
        self.assertTrue((self.project / installer.MANIFEST).is_file())

    def test_powershell_entrypoint(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell not available")
        subprocess.run([shell, "-NoProfile", "-File", str(ROOT / "dist/install.ps1"), "-Project", str(self.project), "-Archive", str(self.archive), "-Mode", "source", "-Version", "V8.9"], check=True, stdout=subprocess.PIPE)
        self.assertTrue((self.project / installer.MANIFEST).is_file())

    def test_interactive_selection(self):
        with patch.object(installer, "prompt", side_effect=[str(self.project), "source", "github-zip", str(self.archive), "MyRTT", ""]), patch.object(installer, "install") as install:
            installer.main([])
            args = install.call_args[0][0]
            self.assertEqual((args.directory, args.mode, args.archive), ("MyRTT", "source", str(self.archive.resolve())))

    def test_no_git_no_network_local_zip(self):
        with patch.object(installer.shutil, "which", return_value=None), patch.object(installer, "git", side_effect=AssertionError("Git called")), patch.object(installer, "read_url", side_effect=AssertionError("Network called")):
            self.run_install()
            self.run_install()
        self.assertTrue((self.project / "SEGGER_RTT/LICENSE.md").is_file())

    def test_pack_root_and_inferred_format(self):
        pack = self.root / "SEGGER.RTT.pack"
        with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as bundle:
            for required in installer.REQUIRED:
                bundle.write(self.upstream / required, required)
            bundle.writestr("SEGGER.RTT.pdsc", "<package/>")
        with patch.object(installer, "git", side_effect=AssertionError("Git called")), patch.object(installer, "read_url", side_effect=AssertionError("Network called")):
            self.run_install("--archive", str(pack))
        state = json.loads((self.project / installer.MANIFEST).read_text())
        self.assertEqual(state["format"], "pack")
        self.assertEqual(state["commit"], None)
        self.assertEqual(state["archive_sha256"], installer.digest(pack))

    def test_online_pack_release_uses_http_only(self):
        pack = self.root / "test.pack"
        with zipfile.ZipFile(pack, "w") as bundle:
            for required in installer.REQUIRED:
                bundle.write(self.upstream / required, required)
            bundle.writestr("SEGGER.RTT.pdsc", "<package/>")
        release = {"tag_name": "V8.9", "assets": [{"name": "RTT.pack", "browser_download_url": "https://example.com/RTT.pack"}]}
        with patch.object(installer, "api", return_value=release) as api, patch.object(installer, "read_url", return_value=pack.read_bytes()), patch.object(installer, "git", side_effect=AssertionError("Git called")):
            installer.main(["--project", str(self.project), "--format", "pack"])
        api.assert_called_once_with("SEGGERMicro/RTT/releases/latest")

    def test_explicit_https_zip_url(self):
        with patch.object(installer, "read_url", return_value=self.archive.read_bytes()), patch.object(installer, "api", side_effect=AssertionError("API called")), patch.object(installer, "git", side_effect=AssertionError("Git called")):
            self.run_install("--archive", "https://example.com/my-rtt.zip")
        state = json.loads((self.project / installer.MANIFEST).read_text())
        self.assertEqual(state["archive_origin"], "https://example.com/my-rtt.zip")

    def test_sha256_mismatch_is_transactional(self):
        original = self.cmake.read_bytes()
        with self.assertRaisesRegex(installer.InstallError, "SHA256 mismatch"):
            self.run_install("--sha256", "a" * 64)
        self.assertEqual(self.cmake.read_bytes(), original)
        self.assertFalse((self.project / "SEGGER_RTT").exists())

    def test_modified_input_archive_detected_on_repeat(self):
        self.run_install()
        with zipfile.ZipFile(self.archive, "a") as bundle:
            bundle.writestr("extra.txt", "changed")
        with self.assertRaisesRegex(installer.InstallError, "Local archive has changed"):
            self.run_install()

    def test_archive_root_security_and_shape(self):
        original = self.cmake.read_bytes()
        scenarios = {
            "traversal": [("../escape.c", "x")],
            "absolute": [("/escape.c", "x")],
            "backslash": [("a\\escape.c", "x")],
            "noncanonical": [("a//escape.c", "x")],
            "drive": [("C:/escape.c", "x")],
            "reserved": [("NUL.txt", "x")],
            "duplicates": [("RTT/a.c", "x"), ("RTT/A.c", "y")],
            "multiple-roots": [(prefix + required, "x") for prefix in ("a/", "b/") for required in installer.REQUIRED],
            "too-deep": [("a/b/" + required, "x") for required in installer.REQUIRED],
        }
        for scenario, entries in scenarios.items():
            with self.subTest(scenario=scenario):
                with zipfile.ZipFile(self.archive, "w") as bundle:
                    for name, value in entries:
                        bundle.writestr(name, value)
                with self.assertRaises(installer.InstallError):
                    self.run_install()
                self.assertEqual(self.cmake.read_bytes(), original)
                self.assertFalse((self.project / "SEGGER_RTT").exists())

    def test_symlink_archive_rejected(self):
        with zipfile.ZipFile(self.archive, "w") as bundle:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            bundle.writestr(info, "../outside")
        with self.assertRaisesRegex(installer.InstallError, "symlinks"):
            self.run_install()

    def test_no_directory_or_other_archive_formats(self):
        for path in (self.upstream, self.root / "RTT.tar.gz", self.root / "RTT.7z"):
            with self.subTest(path=path), self.assertRaises(installer.InstallError):
                self.run_install("--archive", str(path))

    def test_source_list_versions_without_git(self):
        with patch.object(installer.shutil, "which", return_value=None), patch.object(installer, "api", return_value=[{"name": "V8.9"}]), patch.object(installer, "git", side_effect=AssertionError("Git called")):
            installer.main(["--mode", "source", "--list-versions"])

    def test_pack_versions_only_offer_releases_with_pack(self):
        releases = [{"tag_name": "V8.9", "assets": [{"name": "RTT.pack"}]}, {"tag_name": "V8.8", "assets": []}]
        with patch.object(installer, "api", return_value=releases), patch.object(installer, "git", side_effect=AssertionError("Git called")):
            versions = installer.available_versions(type("Args", (), {"mode": "source", "format": "pack", "repository": installer.UPSTREAM})())
        self.assertEqual(versions, ["V8.9"])

    def test_local_source_in_subprocess_with_empty_path(self):
        environment = dict(os.environ, PATH="")
        subprocess.run([sys.executable, str(ROOT / "src/installer.py"), "--project", str(self.project), "--archive", str(self.archive)], check=True, env=environment, stdout=subprocess.PIPE)
        self.assertTrue((self.project / installer.MANIFEST).is_file())

    def test_source_commit_download_does_not_resolve_moving_tag(self):
        with patch.object(installer, "api", side_effect=AssertionError("API called")), patch.object(installer, "read_url", return_value=self.archive.read_bytes()) as download:
            installer.main(["--project", str(self.project), "--mode", "source", "--version", "a" * 40])
        self.assertIn("/archive/" + "a" * 40 + ".zip", download.call_args[0][0])

    def test_pack_requires_description_and_unsupported_compression(self):
        with self.assertRaisesRegex(installer.InstallError, "pdsc"):
            self.run_install("--format", "pack")
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_BZIP2) as bundle:
            bundle.writestr("file", "x")
        with self.assertRaisesRegex(installer.InstallError, "stored/deflated"):
            self.run_install()


if __name__ == "__main__":
    unittest.main()
