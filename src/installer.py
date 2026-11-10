#!/usr/bin/env python3
"""Install SEGGER RTT into an STM32CubeMX CMake project (Python 3.8+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

UPSTREAM = "https://github.com/SEGGERMicro/RTT.git"
BEGIN = "# BEGIN stm32-rtt (managed)"
END = "# END stm32-rtt (managed)"
MANIFEST = ".stm32-rtt.json"
INTEGRATION = "cmake/segger-rtt.cmake"
WARNING = "Do not use Middlewares as the folder name: STM32CubeMX manages that directory."
REQUIRED = ("RTT/SEGGER_RTT.c", "RTT/SEGGER_RTT.h", "RTT/SEGGER_RTT_printf.c", "Config/SEGGER_RTT_Conf.h", "LICENSE.md")
MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_EXTRACTED = 200 * 1024 * 1024


def read_url(url, limit=MAX_DOWNLOAD):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise InstallError("Archive and API URLs must use HTTPS.")
    request = urllib.request.Request(url, headers={"User-Agent": "stm32-rtt-installer/1.1", "Accept": "application/vnd.github+json" if "api.github.com/" in url else "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if urllib.parse.urlsplit(response.geturl()).scheme != "https":
                raise InstallError("Refusing a redirect to a non-HTTPS URL.")
            data = response.read(limit + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise InstallError("Download failed for {}: {}".format(url, error))
    if len(data) > limit:
        raise InstallError("Download exceeds the size limit.")
    return data


def api(path):
    return json.loads(read_url("https://api.github.com/repos/" + path, 8 * 1024 * 1024))


def github_repo(repository):
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", repository)
    if not match:
        raise InstallError("Online source mode requires a GitHub repository URL; use --archive for a ZIP/pack URL or local file.")
    return match.group(1)


def source_tags(repository):
    repo = github_repo(repository)
    names = []
    for page in range(1, 11):
        batch = api(repo + "/tags?per_page=100&page=" + str(page))
        names.extend(item["name"] for item in batch)
        if len(batch) < 100:
            break
    return sorted(names, key=lambda x: tuple(int(n) for n in re.findall(r"\d+", x)))


def available_versions(args):
    if args.mode == "submodule":
        return tags(args.repository)
    if args.format == "pack":
        releases = api(github_repo(args.repository) + "/releases?per_page=100")
        return [release["tag_name"] for release in releases if not release.get("draft") and not release.get("prerelease") and any(asset["name"].lower().endswith(".pack") for asset in release["assets"])]
    return source_tags(args.repository)


def archive_input(args):
    if args.archive:
        if urllib.parse.urlsplit(args.archive).scheme in ("http", "https"):
            if not args.archive.startswith("https://"):
                raise InstallError("Archive URLs must use HTTPS.")
            return args.archive, args.version if args.version != "latest" else "external", None
        path = Path(args.archive).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in (".pack", ".zip"):
            raise InstallError("--archive must be an existing .pack/.zip file or an HTTPS URL; directories are not supported.")
        if path.stat().st_size > MAX_DOWNLOAD:
            raise InstallError("Archive exceeds the size limit.")
        return str(path), args.version if args.version != "latest" else "local", None
    repo = github_repo(args.repository)
    version = args.version
    if args.format == "pack":
        release = api(repo + ("/releases/latest" if version == "latest" else "/releases/tags/" + urllib.parse.quote(version, safe="")))
        assets = [asset for asset in release["assets"] if asset["name"].lower().endswith(".pack")]
        if len(assets) != 1:
            raise InstallError("Expected exactly one .pack release asset; pass --archive with its URL explicitly.")
        return assets[0]["browser_download_url"], release["tag_name"], None
    if version == "latest":
        releases = [tag for tag in source_tags(args.repository) if re.fullmatch(r"[vV]?\d+(?:\.\d+)+", tag)]
        if not releases:
            raise InstallError("No numeric version tags found; pass --version.")
        version = releases[-1]
    # Resolve a tag to a commit before downloading the snapshot. Full SHA is already pinned.
    commit = version.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", version) else api(repo + "/commits/" + urllib.parse.quote(version, safe=""))["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise InstallError("GitHub returned an invalid commit SHA.")
    return "https://github.com/{}/archive/{}.zip".format(repo, commit), version, commit


def unpack_archive(archive, destination, archive_format):
    """Validate every ZIP member before writing. Accept pack root or one GitHub wrapper."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > 10000 or sum(item.file_size for item in members) > MAX_EXTRACTED:
                raise InstallError("Archive has too many entries or exceeds the extracted size limit.")
            seen = set()
            for item in members:
                name = item.filename.rstrip("/")
                parts = PurePosixPath(name).parts
                if not parts or name.startswith("/") or "\\" in name or any(part in (".", "..") or ":" in part or part.endswith((" ", ".")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", part) for part in parts):
                    raise InstallError("Unsafe archive path: " + name)
                if stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                    raise InstallError("Archive symlinks and encrypted entries are not supported.")
                if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise InstallError("Only stored/deflated ZIP entries are supported.")
                key = name.casefold()
                if key in seen or ".git" in [part.lower() for part in parts]:
                    raise InstallError("Duplicate archive path or Git metadata: " + name)
                seen.add(key)
            candidates = []
            file_names = {item.filename for item in members if not item.is_dir()}
            prefixes = {""} | {item.filename.split("/", 1)[0] + "/" for item in members if "/" in item.filename}
            for prefix in prefixes:
                if all(prefix + required in file_names for required in REQUIRED):
                    candidates.append(prefix)
            if len(candidates) != 1:
                raise InstallError("Archive must contain exactly one RTT root (directly or under one wrapper), including RTT/, Config/ and LICENSE.md.")
            prefix = candidates[0]
            if archive_format == "pack" and not any(name.startswith(prefix) and name[len(prefix):].endswith(".pdsc") and "/" not in name[len(prefix):] for name in file_names):
                raise InstallError("Pack format requires a .pdsc description beside RTT/ and Config/.")
            destination.mkdir()
            for item in members:
                if item.is_dir() or not item.filename.startswith(prefix):
                    continue
                relative = item.filename[len(prefix):]
                if not relative:
                    continue
                path = destination.joinpath(*PurePosixPath(relative).parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(item) as src, path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise InstallError("Invalid or unsupported ZIP/pack: " + str(error))


class InstallError(Exception):
    pass


def git(*args, cwd=None, check=True):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    result = subprocess.run(["git", *map(str, args)], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise InstallError("git {} failed: {}".format(args[0], result.stderr.decode("utf-8", "replace").strip()))
    return result


def out(*args, **kwargs):
    return git(*args, **kwargs).stdout.decode("utf-8", "replace").strip()


def tags(repository):
    raw = out("ls-remote", "--tags", "--refs", "--", repository)
    names = [line.split("\trefs/tags/", 1)[1] for line in raw.splitlines() if "\trefs/tags/" in line]
    # Only numeric release tags participate in 'latest'; other refs remain selectable.
    return sorted(names, key=lambda x: tuple(int(n) for n in re.findall(r"\d+", x)))


def prompt(label, default):
    # curl | sh consumes stdin. Read the terminal explicitly on POSIX.
    if os.name != "nt" and not sys.stdin.isatty():
        try:
            with open("/dev/tty", "r+") as tty:
                tty.write("{} [{}]: ".format(label, default))
                tty.flush()
                answer = tty.readline()
        except OSError:
            raise InstallError("No interactive terminal. Pass --non-interactive (or installation options).")
    else:
        try:
            answer = input("{} [{}]: ".format(label, default))
        except EOFError:
            raise InstallError("No interactive input. Pass --non-interactive.")
    return answer.strip() or default


def integration(directory, target):
    return '''# Generated by stm32-rtt. Included after the executable target is created.
if(NOT TARGET {target})
    message(FATAL_ERROR "RTT target does not exist; rerun installer with --target <executable>.")
endif()
target_sources({target} PRIVATE
    "${{CMAKE_CURRENT_LIST_DIR}}/../{directory}/RTT/SEGGER_RTT.c"
    "${{CMAKE_CURRENT_LIST_DIR}}/../{directory}/RTT/SEGGER_RTT_printf.c"
)
target_include_directories({target} PRIVATE
    "${{CMAKE_CURRENT_LIST_DIR}}/../{directory}/RTT"
    "${{CMAKE_CURRENT_LIST_DIR}}/../{directory}/Config"
)
'''.format(directory=directory, target=target)


def validate_directory(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", name):
        raise InstallError("Directory must be a single folder name (letters, numbers, '_' or '-', max 64).")
    if name.lower() in {"middlewares", "core", "drivers", "cmake", "build", "con", "prn", "aux", "nul"} or re.fullmatch(r"(?i)(com|lpt)[0-9]", name):
        raise InstallError("Reserved or CubeMX-managed directory: {}. {}".format(name, WARNING))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_tree(path):
    # Git object files may be read-only on Windows.
    def retry(function, name, error):
        os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
        function(name)
    shutil.rmtree(path, onerror=retry)


def install(args):
    validate_directory(args.directory)
    if args.target and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.+-]*", args.target):
        raise InstallError("Invalid CMake target name.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./+-]*", args.version) or ".." in args.version:
        raise InstallError("Invalid version: use latest, an upstream tag, or a commit SHA.")
    project = Path(args.project).expanduser().resolve()
    cmake = project / "CMakeLists.txt"
    if not cmake.is_file() or not (project / "cmake/stm32cubemx/CMakeLists.txt").is_file():
        raise InstallError("Expected an STM32CubeMX CMake project (CMakeLists.txt and cmake/stm32cubemx/CMakeLists.txt).")
    if cmake.is_symlink() or (project / "cmake").is_symlink():
        raise InstallError("CMake paths must not be symbolic links.")
    original = cmake.read_bytes()
    text = original.decode("utf-8-sig").replace("\r\n", "\n")
    state_path = project / MANIFEST
    destination = project / args.directory
    include_path = project / INTEGRATION
    target = args.target or "${CMAKE_PROJECT_NAME}"
    fragment = integration(args.directory, target)
    block = '{}\ninclude("${{CMAKE_CURRENT_LIST_DIR}}/{}")\n{}\n'.format(BEGIN, INTEGRATION, END)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        expected = dict(directory=args.directory, mode=args.mode, requested_version=args.version, target=target, repository=args.repository,
                        format=args.format, requested_archive=args.archive, expected_sha256=args.sha256)
        if any(state.get(k) != v for k, v in expected.items()):
            raise InstallError("RTT is already installed with different options. Review/remove the existing integration before changing options.")
        if text.count(BEGIN) != 1 or block not in text or not include_path.is_file() or include_path.read_text(encoding="utf-8") != fragment:
            raise InstallError("Existing RTT integration has changed; refusing to overwrite it.")
        for name, sha in state["files"].items():
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name or ":" in name:
                raise InstallError("Invalid path in installed manifest.")
            path = destination / name
            if not path.is_file() or digest(path) != sha:
                raise InstallError("Installed RTT source changed or is missing: " + name)
        if args.mode == "submodule" and out("rev-parse", "HEAD", cwd=destination) != state["commit"]:
            raise InstallError("RTT submodule commit has changed.")
        if args.archive and not args.archive.startswith("https://") and digest(Path(args.archive)) != state["archive_sha256"]:
            raise InstallError("Local archive has changed since installation.")
        print("Already installed: {} ({})".format(state["version"], state["commit"] or "archive sha256:" + state["archive_sha256"]))
        print(json.dumps(state, ensure_ascii=False))
        return
    if destination.exists() or destination.is_symlink() or include_path.exists() or include_path.is_symlink():
        raise InstallError("Destination or cmake/segger-rtt.cmake already exists; no files were overwritten.")
    if re.search(r"SEGGER_RTT|segger[-_]rtt|stm32-rtt", text, re.I):
        raise InstallError("Existing RTT integration detected in CMakeLists.txt. Review/remove it before installing.")
    modules_path = project / ".gitmodules"
    modules_before = modules_path.read_bytes() if modules_path.exists() else None
    if args.mode == "submodule":
        if out("rev-parse", "--show-toplevel", cwd=project).replace("\\", "/").lower() != project.as_posix().lower():
            raise InstallError("Submodule mode requires the project to be the Git repository root.")
        out("rev-parse", "--verify", "HEAD", cwd=project)
        if out("status", "--porcelain", "--", ".gitmodules", args.directory, cwd=project):
            raise InstallError("Commit/stash changes to .gitmodules and the destination before installing a submodule.")
        if out("config", "--get-regexp", r"^submodule\.stm32-rtt\.", cwd=project, check=False):
            raise InstallError("A Git submodule named stm32-rtt already exists.")
        if modules_before is not None and out("config", "--file", ".gitmodules", "--get-regexp", r"^submodule\.stm32-rtt\.", cwd=project, check=False):
            raise InstallError(".gitmodules already contains a submodule named stm32-rtt.")
        module_store = Path(out("rev-parse", "--git-path", "modules/stm32-rtt", cwd=project))
        if not module_store.is_absolute():
            module_store = project / module_store
        if module_store.exists():
            raise InstallError("Git metadata for stm32-rtt already exists; inspect it before installing.")
    version = args.version
    if args.mode == "submodule" and version == "latest":
        releases = [t for t in tags(args.repository) if re.fullmatch(r"[vV]?\d+(?:\.\d+)+", t)]
        if not releases:
            raise InstallError("No release tags found; specify --version explicitly.")
        version = releases[-1]
    with tempfile.TemporaryDirectory(prefix="stm32-rtt-") as temp:
        checkout = Path(temp) / "RTT"
        archive_sha = archive_origin = None
        if args.mode == "submodule":
            out("clone", "--quiet", "--no-checkout", "--", args.repository, checkout)
            ref = version if re.fullmatch(r"[0-9a-fA-F]{40}", version) else "refs/tags/" + version
            commit = out("rev-parse", "--verify", ref + "^{commit}", cwd=checkout)
            out("checkout", "--quiet", "--detach", commit, cwd=checkout)
        else:
            archive_origin, version, commit = archive_input(args)
            archive_path = Path(temp) / "download.zip"
            if archive_origin.startswith("https://"):
                archive_path.write_bytes(read_url(archive_origin))
            else:
                shutil.copyfile(archive_origin, archive_path)
            archive_sha = digest(archive_path)
            if args.sha256 and archive_sha != args.sha256:
                raise InstallError("Archive SHA256 mismatch; project was not modified.")
            unpack_archive(archive_path, checkout, args.format)
        for required in REQUIRED:
            if not (checkout / required).is_file():
                raise InstallError("Selected version is missing " + required)
        files = {p.relative_to(checkout).as_posix(): digest(p) for p in checkout.rglob("*") if p.is_file() and ".git" not in p.relative_to(checkout).parts}
        state = dict(schema=2, installer_version="1.1.0", repository=args.repository, requested_version=args.version,
                     version=version, commit=commit, directory=args.directory, mode=args.mode, target=target, files=files,
                     format=args.format, requested_archive=args.archive, expected_sha256=args.sha256,
                     archive_origin=archive_origin, archive_sha256=archive_sha)
        submodule_started = False
        try:
            if args.mode == "source":
                shutil.copytree(checkout, destination, ignore=shutil.ignore_patterns(".git"))
            else:
                submodule_started = True
                out("submodule", "add", "--name", "stm32-rtt", "--", args.repository, args.directory, cwd=project)
                out("checkout", "--quiet", "--detach", commit, cwd=destination)
                out("add", "--", args.directory, cwd=project)
            include_path.write_text(fragment, encoding="utf-8", newline="\n") if sys.version_info >= (3, 10) else include_path.write_bytes(fragment.encode())
            newline = "\r\n" if b"\r\n" in original else "\n"
            cmake.write_bytes(original + (newline + block.replace("\n", newline)).encode("utf-8"))
            state_path.write_bytes((json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        except BaseException:
            cmake.write_bytes(original)
            include_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            if submodule_started:
                git("submodule", "deinit", "-f", "--", args.directory, cwd=project, check=False)
                git("rm", "--cached", "-f", "--ignore-unmatch", "--", args.directory, cwd=project, check=False)
                git("config", "--remove-section", "submodule.stm32-rtt", cwd=project, check=False)
                if module_store.exists():
                    remove_tree(module_store)
                if modules_before is None:
                    modules_path.unlink(missing_ok=True)
                    git("rm", "--cached", "--ignore-unmatch", "--", ".gitmodules", cwd=project, check=False)
                else:
                    modules_path.write_bytes(modules_before)
                    git("add", "--", ".gitmodules", cwd=project, check=False)
            if destination.exists():
                remove_tree(destination)
            raise
    print("Installed RTT {} ({}) into {}".format(version, commit or "archive sha256:" + archive_sha, destination))
    print("CMake updated. Configure/build your firmware, then call SEGGER_RTT_WriteString or SEGGER_RTT_printf.")
    if args.mode == "submodule":
        print("Git staged .gitmodules and the submodule gitlink; review and commit all installation files.")
    print(json.dumps(state, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stm32-rtt-installer", description=__doc__, epilog=WARNING)
    parser.add_argument("--project", default=".", help="CubeMX CMake project root (default: current directory)")
    parser.add_argument("--version", default="latest", help="upstream tag, full commit SHA, or latest release tag")
    parser.add_argument("--directory", default="SEGGER_RTT", help="single folder name; never Middlewares")
    parser.add_argument("--mode", choices=("submodule", "source"), help="default: submodule; --archive/--format imply source")
    parser.add_argument("--format", choices=("pack", "github-zip"), help="source format; inferred from archive extension, otherwise github-zip")
    parser.add_argument("--archive", help="HTTPS URL or local .pack/.zip file; no directories, no Git required")
    parser.add_argument("--sha256", help="expected source archive SHA256 (optional)")
    parser.add_argument("--target", help="CMake executable target (default: ${CMAKE_PROJECT_NAME})")
    parser.add_argument("--non-interactive", action="store_true", help="use defaults without prompts")
    parser.add_argument("--list-versions", action="store_true", help="list upstream tags and exit")
    parser.add_argument("--repository", default=UPSTREAM, help="Git mirror URL (default: SEGGER official repository)")
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)
    args.mode = args.mode or ("source" if args.archive or args.format else "submodule")
    if not argv:
        args.project = prompt("CubeMX CMake project root", args.project)
        args.mode = prompt("Install mode (submodule / source)", args.mode)
        if args.mode not in ("submodule", "source"):
            raise InstallError("Mode must be submodule or source.")
        if args.mode == "source":
            args.format = prompt("Archive format (pack / github-zip)", "github-zip")
            args.archive = prompt("Local .pack/.zip or HTTPS URL (empty = official online download)", "") or None
        if not args.archive:
            if args.mode == "source":
                print("Available versions: " + ", ".join(available_versions(args)))
            elif shutil.which("git"):
                print("Available upstream tags: " + ", ".join(tags(args.repository)))
            args.version = prompt("RTT version (tag / full SHA / latest)", args.version)
        args.directory = prompt("RTT folder (NOT Middlewares)", args.directory)
        args.target = prompt("CMake target (empty = project name)", "") or None
    if args.mode == "submodule":
        if args.archive or args.format or args.sha256:
            parser.error("--archive, --format and --sha256 apply only to source mode.")
        if not shutil.which("git"):
            parser.error("Git is required for submodule mode. Source .pack/.zip installs do not require Git.")
    else:
        args.format = args.format or ("pack" if args.archive and urllib.parse.urlsplit(args.archive).path.lower().endswith(".pack") else "github-zip")
        if args.format not in ("pack", "github-zip"):
            parser.error("Source format must be pack or github-zip.")
        if args.sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
            parser.error("--sha256 requires 64 hexadecimal characters.")
        args.sha256 = args.sha256.lower() if args.sha256 else None
        if args.archive and not args.archive.startswith(("https://", "http://")):
            args.archive = str(Path(args.archive).expanduser().resolve())
    if args.list_versions:
        if args.archive:
            parser.error("--list-versions cannot be combined with --archive (local/explicit URL installs do not query GitHub).")
        print("\n".join(available_versions(args)))
        return
    print(WARNING, file=sys.stderr)
    install(args)


if __name__ == "__main__":
    try:
        main()
    except (InstallError, OSError, ValueError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Installation cancelled.", file=sys.stderr)
        sys.exit(130)
