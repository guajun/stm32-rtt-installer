"""Build standalone release entrypoints. No third-party build dependencies."""
import base64
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
payload = base64.b64encode((ROOT / "src/installer.py").read_bytes()).decode("ascii")
loader = "import base64;exec(compile(base64.b64decode('{}'),'stm32-rtt','exec'))".format(payload)
ps = '''#requires -Version 5.1
<# Standalone STM32 RTT installer. Git + Python 3.8+ required. #>
[CmdletBinding()]
param(
    [string]$Project,
    [string]$Version,
    [string]$Directory,
    [ValidateSet('submodule', 'source')][string]$Mode,
    [string]$Target,
    [string]$Repository,
    [switch]$NonInteractive,
    [switch]$ListVersions,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'
$forward = @()
foreach ($name in @('Project', 'Version', 'Directory', 'Mode', 'Target', 'Repository')) {
    if ($PSBoundParameters.ContainsKey($name)) {
        $forward += '--' + $name.ToLowerInvariant()
        $forward += [string]$PSBoundParameters[$name]
    }
}
if ($NonInteractive) { $forward += '--non-interactive' }
if ($ListVersions) { $forward += '--list-versions' }
if ($Help) { $forward += '--help' }
$pythonCommand = $null
$pythonPrefix = @()
foreach ($candidate in @('py', 'python3', 'python')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $prefix = @()
        if ($candidate -eq 'py') { $prefix = @('-3') }
        & $candidate @prefix -c 'import sys;sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) {
            $pythonCommand = $candidate
            $pythonPrefix = $prefix
            break
        }
    }
}
if (-not $pythonCommand) { throw 'Python 3.8+ is required. Install Python and add it to PATH, then retry.' }
$loader = '__LOADER__'
& $pythonCommand @pythonPrefix -c $loader @forward
if ($LASTEXITCODE -ne 0) { throw "stm32-rtt failed (exit $LASTEXITCODE)." }
'''.replace("__LOADER__", loader.replace("'", "''"))
sh = '''#!/bin/sh
# Standalone POSIX installer. Git + Python 3.8+ required.
set -eu
python_cmd=
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys;sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null; then
        python_cmd=$candidate
        break
    fi
done
if [ -z "$python_cmd" ]; then
    echo 'ERROR: Python 3.8+ is required on PATH.' >&2
    exit 1
fi
exec "$python_cmd" -c '__LOADER__' "$@"
'''.replace("__LOADER__", loader.replace("'", "'\"'\"'"))
dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
for name, content in (("install.ps1", ps), ("install.sh", sh)):
    (dist / name).write_bytes(content.encode("utf-8"))
(dist / "install.sh").chmod(0o755)
(dist / "SHA256SUMS").write_bytes("".join(
    hashlib.sha256((dist / name).read_bytes()).hexdigest() + "  " + name + "\n"
    for name in ("install.ps1", "install.sh")
).encode("ascii"))
print("Built install.ps1, install.sh and SHA256SUMS")
