"""Publish a PR page and its own standalone installers under Pages /pr/<number>/.

Copies main's docs into the site root and keeps other previews. Requires gh + git.
Does not merge the PR or publish/replace a Release.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = "guajun/stm32-rtt-installer"
SITE = "https://guajun.github.io/stm32-rtt-installer/"


def run(*command, cwd=ROOT):
    return subprocess.check_output(command, cwd=cwd).decode("utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="existing directory for the temporary publishing checkout")
    args = parser.parse_args()
    if args.pr <= 0:
        parser.error("PR number must be positive")
    pr = json.loads(run("gh", "pr", "view", str(args.pr), "--repo", REPO, "--json", "headRefOid,headRefName"))
    sha = run("git", "rev-parse", "HEAD")
    if sha != pr["headRefOid"] or run("git", "status", "--porcelain"):
        raise SystemExit("Commit and push the exact PR head before publishing its preview.")
    run(sys.executable, str(ROOT / "tools/build.py"))
    run("git", "fetch", "origin", "main")
    branch_exists = bool(run("git", "ls-remote", "--heads", "origin", "gh-pages"))
    pages = json.loads(run("gh", "api", "repos/" + REPO + "/pages"))
    source_changed = pages.get("source") != {"branch": "gh-pages", "path": "/"}
    preview_url = SITE + "pr/{}/".format(args.pr)
    with tempfile.TemporaryDirectory(prefix="rtt-pages-", dir=args.work_dir) as scratch:
        checkout = Path(scratch)
        run("git", "init", "-b", "gh-pages", cwd=checkout)
        run("git", "remote", "add", "origin", run("git", "remote", "get-url", "origin"), cwd=checkout)
        ssh_command = subprocess.run(["git", "config", "--get", "core.sshCommand"], cwd=ROOT, capture_output=True, text=True)
        if ssh_command.returncode == 0:
            run("git", "config", "core.sshCommand", ssh_command.stdout.strip(), cwd=checkout)
        if branch_exists:
            run("git", "fetch", "origin", "gh-pages", cwd=checkout)
            run("git", "checkout", "-B", "gh-pages", "FETCH_HEAD", cwd=checkout)
        # Preserve the main website. Serve main's docs, not this PR's docs, at root.
        for name in run("git", "ls-tree", "-r", "--name-only", "origin/main", "docs/").splitlines():
            destination = checkout / Path(name).relative_to("docs")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(subprocess.check_output(["git", "show", "origin/main:" + name], cwd=ROOT))
        preview = checkout / "pr" / str(args.pr)
        preview.mkdir(parents=True, exist_ok=True)
        html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        html = html.replace("https://github.com/guajun/stm32-rtt-installer/releases/download/v1.1.0/", preview_url)
        banner = '<aside id="preview-banner" class="preview-banner">PR #{} 预览 · {} · {} · <a href="https://github.com/{}/pull/{}">审阅 Pull Request ↗</a> · 下方命令运行本分支脚本。</aside>'.format(args.pr, pr["headRefName"], sha[:7], REPO, args.pr)
        html = html.replace("<main>", "<main>\n" + banner, 1)
        (preview / "index.html").write_bytes(html.encode("utf-8"))
        for name in ("install.ps1", "install.sh", "SHA256SUMS"):
            shutil.copyfile(ROOT / "dist" / name, preview / name)
        (preview / "preview.json").write_text(json.dumps(dict(pr=args.pr, branch=pr["headRefName"], commit=sha), indent=2), encoding="utf-8")
        (checkout / ".nojekyll").touch()
        run("git", "add", ".", cwd=checkout)
        changes = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=checkout)
        if changes.returncode:
            run("git", "commit", "-m", "Publish PR #{} preview at {}".format(args.pr, sha[:7]), cwd=checkout)
            run("git", "push", "origin", "gh-pages", cwd=checkout)
    if source_changed:
        run("gh", "api", "--method", "PUT", "repos/" + REPO + "/pages", "-f", "build_type=legacy", "-f", "source[branch]=gh-pages", "-f", "source[path]=/")
        run("gh", "api", "--method", "POST", "repos/" + REPO + "/pages/builds")
    # With the source already configured, the push itself schedules one build.
    print(preview_url)


if __name__ == "__main__":
    main()
