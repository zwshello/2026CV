<#
.SYNOPSIS
    Create the dedicated Windows venv used to fine-tune YOLO on the sim
    dataset. Designed for an RTX 4050 Laptop (CUDA 12.1).

.DESCRIPTION
    1. Creates `.venv-train` next to this script (i.e. inside `vision/`).
    2. Upgrades pip / wheel.
    3. Installs PyTorch + torchvision from the CUDA 12.1 wheel index.
    4. Installs everything else from `requirements-train.txt`.
    5. Verifies that CUDA is visible.

    Re-running is safe — the venv is reused. Pass -Recreate to nuke and
    rebuild it.

    Why training is on Windows (not the Linux moving disk):
    - The Ubuntu install on the portable drive currently boots inside a
      VirtualBox VM. VirtualBox does not support NVIDIA GPU passthrough,
      so `nvidia-smi` is unavailable and PyTorch falls back to CPU even
      though the host has an RTX 4050. Training YOLOv8s on CPU is too
      slow for the project schedule, so we keep training on Windows
      native and copy the resulting weights back into the Linux ROS 2
      pipeline for inference.

.PARAMETER Python
    Path to the system Python interpreter to use as the venv base. Defaults
    to whatever `py -3.11` resolves to (Ultralytics + torch wheels are most
    reliable on 3.10–3.11). Override if you want 3.12.

.PARAMETER Recreate
    Delete the existing `.venv-train` before recreating it.

.EXAMPLE
    pwsh -File vision/setup_train_env.ps1

.EXAMPLE
    pwsh -File vision/setup_train_env.ps1 -Recreate -Python "C:\\Python311\\python.exe"
#>

[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $here ".venv-train"

if ($Recreate -and (Test-Path $venv)) {
    Write-Host "Removing existing venv: $venv"
    Remove-Item -Recurse -Force $venv
}

# Pick a base Python: prefer the user-specified one, then `py -3.11`,
# then `py -3.10`, finally fall back to whatever `python` is on PATH.
function Resolve-BasePython {
    param([string]$Hint)

    if ($Hint) {
        if (-not (Test-Path $Hint)) { throw "Specified Python not found: $Hint" }
        return $Hint
    }

    foreach ($v in @("3.11", "3.10", "3.12")) {
        try {
            $exe = (& py "-$v" -c "import sys; print(sys.executable)" 2>$null).Trim()
            if ($exe -and (Test-Path $exe)) { return $exe }
        } catch { }
    }

    try {
        $exe = (& python -c "import sys; print(sys.executable)" 2>$null).Trim()
        if ($exe -and (Test-Path $exe)) { return $exe }
    } catch { }

    throw "No suitable Python interpreter found. Install Python 3.10 or 3.11."
}

if (-not (Test-Path $venv)) {
    $base = Resolve-BasePython -Hint $Python
    Write-Host "Creating venv at $venv (base: $base)"
    & $base -m venv $venv
}

$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { throw "venv python missing: $venvPython" }

Write-Host "Upgrading pip / wheel"
& $venvPython -m pip install --upgrade pip wheel --quiet

Write-Host "Installing PyTorch (CUDA 12.1 wheels) — this may take a while"
& $venvPython -m pip install ``
    --index-url https://download.pytorch.org/whl/cu121 ``
    "torch==2.3.1" "torchvision==0.18.1"

Write-Host "Installing remaining requirements"
& $venvPython -m pip install -r (Join-Path $here "requirements-train.txt") --quiet

Write-Host "Verifying CUDA visibility"
$verify = @"
import torch
print(f'torch: {torch.__version__}')
print(f'cuda available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'device: {torch.cuda.get_device_name(0)}')
    print(f'capability: {torch.cuda.get_device_capability(0)}')
else:
    print('WARNING: CUDA not visible — training will fall back to CPU.')
"@
& $venvPython -c $verify

Write-Host ""
Write-Host "Done. Activate the env with:"
Write-Host "    $venv\Scripts\Activate.ps1"
Write-Host "Then train with e.g.:"
Write-Host "    python vision\train_sim.py --data <path-to-dataset.yaml>"
