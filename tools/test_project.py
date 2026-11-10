"""Run real CubeMX project install/build checks on Windows or Linux/WSL.

The input project is never edited. Each case gets its own copy under --work-dir.
Requires CMake, Ninja, Arm GNU toolchain, Python and Git for the test matrix.
Local archive installers are additionally tested with Git absent from PATH.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "V8.58.0"
PACK = "https://github.com/SEGGERMicro/RTT/releases/download/V8.58.0/SEGGER.RTT.8.58.0.pack"
ZIP = "https://github.com/SEGGERMicro/RTT/archive/refs/tags/V8.58.0.zip"


def fingerprint(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts}


def run(command, log, cwd=None, env=None):
    log.write("\n$ " + subprocess.list2cmdline(list(map(str, command))) + "\n")
    log.flush()
    result = subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=240)
    output = result.stdout.decode("utf-8", "replace")
    log.write(output)
    log.flush()
    if result.returncode:
        raise RuntimeError("Command failed ({}): {}\n{}".format(result.returncode, command[0], output[-2500:]))
    return output


def install_command(project, options):
    version = next((value for key, value in options if key == "Version"), VERSION)
    options = [(key, value) for key, value in options if key != "Version"]
    if os.name == "nt":
        shell = shutil.which("powershell")
        def quote(value):
            return "'" + str(value).replace("'", "''") + "'"
        command = "& ([scriptblock]::Create([IO.File]::ReadAllText({}))) -Project {} -Version {} -NonInteractive".format(
            quote(ROOT / "dist/install.ps1"), quote(project), quote(version))
        for key, value in options:
            command += " -" + key + " " + quote(value)
        return [shell, "-NoProfile", "-Command", command]
    command = ["/bin/sh", str(ROOT / "dist/install.sh"), "--project", str(project), "--version", version, "--non-interactive"]
    for key, value in options:
        command += ["--" + key.lower(), str(value)]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=ROOT / "tests/e2e-install")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--skip-build", action="store_true", help="use existing dist scripts (for simultaneous platform runs)")
    args = parser.parse_args()
    fixture = args.project.resolve()
    work = args.work_dir.resolve()
    report_dir = args.report_dir.resolve()
    if not (fixture / "cmake/stm32cubemx/CMakeLists.txt").is_file():
        parser.error("Expected a CubeMX CMake project")
    if work == fixture or fixture in work.parents or work in fixture.parents:
        parser.error("Use a work directory outside the fixture")
    if report_dir == fixture or fixture in report_dir.parents:
        parser.error("Keep reports outside the original fixture")
    work.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    required = ["cmake", "ninja", "arm-none-eabi-gcc", "arm-none-eabi-nm", "arm-none-eabi-size", "git"]
    for tool in required:
        if not shutil.which(tool):
            parser.error("Missing test dependency: " + tool)
    before = fingerprint(fixture)
    (report_dir / "fixture-before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    versions = {name: subprocess.check_output([name, "--version"]).decode("utf-8", "replace").splitlines()[0]
                for name in ("cmake", "ninja", "arm-none-eabi-gcc", "git")}
    versions["python"] = sys.version
    host = "Windows PowerShell 5.1" if os.name == "nt" else "Linux/WSL POSIX sh"
    with (report_dir / "setup.log").open("w", encoding="utf-8") as log:
        if not args.skip_build:
            run([sys.executable, ROOT / "tools/build.py"], log)
        for name, url in (("RTT.pack", PACK), ("RTT.zip", ZIP)):
            request = urllib.request.Request(url, headers={"User-Agent": "stm32-rtt-installer-e2e"})
            with urllib.request.urlopen(request, timeout=60) as response:
                (work / name).write_bytes(response.read())
    local_options = lambda name: [("Archive", str(work / name)), ("Sha256", hashlib.sha256((work / name).read_bytes()).hexdigest())]
    cases = [
        ("baseline", None, False),
        ("official pack", [("Mode", "source"), ("Format", "pack")], False),
        ("official github zip", [("Mode", "source"), ("Format", "github-zip")], False),
        ("https pack", [("Format", "pack"), ("Archive", PACK)], False),
        ("https github zip", [("Format", "github-zip"), ("Archive", ZIP)], False),
        ("local pack no git", local_options("RTT.pack"), True),
        ("local github zip no git", local_options("RTT.zip"), True),
        ("submodule", [("Mode", "submodule")], False),
        ("release copy", [("Mode", "source"), ("Version", "release")], False),
        ("main copy", [("Mode", "source"), ("Version", "main")], False),
        ("release submodule", [("Mode", "submodule"), ("Version", "release")], False),
        ("main submodule", [("Mode", "submodule"), ("Version", "main")], False),
    ]
    results = []
    for name, options, offline in cases:
        started = time.monotonic()
        destination = work / name
        result = dict(case=name, platform=host, project=str(destination), builds=[], passed=False)
        log_path = report_dir / (name.replace(" ", "-") + ".log")
        submodule = options is not None and ("Mode", "submodule") in options
        try:
            shutil.copytree(fixture, destination, ignore=shutil.ignore_patterns(".git", "build", "SEGGER_RTT", ".stm32-rtt.json"))
            with log_path.open("w", encoding="utf-8") as log:
                if submodule:
                    # The provided fixture ignores all files. Adjust only this test copy.
                    (destination / ".gitignore").write_text("build/\n", encoding="utf-8")
                    for command in (["git", "init"], ["git", "config", "user.name", "RTT E2E"],
                                    ["git", "config", "user.email", "e2e@example.com"], ["git", "add", "."],
                                    ["git", "commit", "-m", "CubeMX test baseline"]):
                        run(command, log, cwd=destination)
                if options is not None:
                    env = dict(os.environ)
                    if offline:
                        if os.name == "nt":
                            env["PATH"] = str(Path(sys.executable).parent)
                        else:
                            shim = work / "python only PATH"
                            shim.mkdir(exist_ok=True)
                            if not (shim / "python3").exists():
                                (shim / "python3").symlink_to(sys.executable)
                            env["PATH"] = str(shim)
                        assert shutil.which("git", path=env["PATH"]) is None
                        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
                            env[key] = "http://127.0.0.1:9"
                        env["NO_PROXY"] = env["no_proxy"] = ""
                    command = install_command(destination, options)
                    run(command, log, env=env)
                    installation_before = {p: (destination / p).read_bytes() for p in ("CMakeLists.txt", ".stm32-rtt.json", "cmake/segger-rtt.cmake")}
                    run(command, log, env=env)
                    assert all((destination / p).read_bytes() == value for p, value in installation_before.items()), "Repeat modified installation"
                    result["idempotent"] = True
                    state = json.loads((destination / ".stm32-rtt.json").read_text(encoding="utf-8"))
                    result["archive_sha256"] = state.get("archive_sha256")
                    result["commit"] = state.get("commit")
                    result["git_absent"] = offline
                    main_file = destination / "Core/Src/main.c"
                    main = main_file.read_text(encoding="utf-8")
                    assert "/* USER CODE BEGIN Includes */" in main and "/* USER CODE BEGIN 2 */" in main
                    main = main.replace("/* USER CODE BEGIN Includes */", '/* USER CODE BEGIN Includes */\n#include "SEGGER_RTT.h"', 1)
                    main = main.replace("/* USER CODE BEGIN 2 */", '/* USER CODE BEGIN 2 */\n  SEGGER_RTT_WriteString(0, "E2E RTT\\n");\n  SEGGER_RTT_printf(0, "E2E value=%u\\n", 123u);', 1)
                    main_file.write_bytes(main.encode("utf-8"))
                    if submodule:
                        assert "160000" in run(["git", "ls-files", "--stage", "SEGGER_RTT"], log, cwd=destination)
                    else:
                        assert not (destination / "SEGGER_RTT/.git").exists()
                for preset in ("Debug", "Release"):
                    run(["cmake", "--preset", preset], log, cwd=destination)
                    run(["cmake", "--build", "--preset", preset, "--parallel", "8"], log, cwd=destination)
                    elfs = list((destination / "build" / preset).glob("*.elf"))
                    assert len(elfs) == 1, "Expected one linked ELF"
                    symbols = run(["arm-none-eabi-nm", "--defined-only", elfs[0]], log)
                    if options is not None:
                        for symbol in ("SEGGER_RTT_WriteString", "SEGGER_RTT_printf", "_SEGGER_RTT"):
                            assert any(line.split()[-1] == symbol for line in symbols.splitlines() if line.split()), "Missing linked symbol " + symbol
                    size = run(["arm-none-eabi-size", elfs[0]], log)
                    result["builds"].append(dict(preset=preset, elf=str(elfs[0]), size=size.strip(), rtt_symbols=options is not None))
                result["passed"] = True
        except Exception as error:
            result["error"] = str(error)
        result["seconds"] = round(time.monotonic() - started, 2)
        result["log"] = str(log_path)
        results.append(result)
        print(("PASS " if result["passed"] else "FAIL ") + host + " :: " + name, flush=True)
        (report_dir / "results.json").write_text(json.dumps(dict(platform=host, tools=versions, fixture=str(fixture), fixture_unchanged=before == fingerprint(fixture), results=results), indent=2), encoding="utf-8")
    assert before == fingerprint(fixture), "Original fixture changed"
    print("FIXTURE_UNCHANGED", flush=True)
    if not all(item["passed"] for item in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
