<#
.SYNOPSIS
  Task runner for Windows. Mirrors the Makefile.

.EXAMPLE
  .\tasks.ps1 setup
  .\tasks.ps1 pipeline -Fast
  .\tasks.ps1 check
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'setup-full', 'data', 'pipeline', 'bundle', 'api', 'web',
        'build', 'types', 'test', 'test-all', 'lint', 'fmt', 'check', 'docker', 'clean')]
    [string]$Task = 'help',

    # pipeline: fewer folds and the required fault set only, for a quick loop.
    [switch]$Fast
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root '.venv'
$py = Join-Path $venv 'Scripts\python.exe'

function Use-Venv {
    if (-not (Test-Path $py)) {
        throw "No virtualenv at $venv. Run: .\tasks.ps1 setup"
    }
}

function Invoke-Step([string]$Label, [scriptblock]$Body) {
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

switch ($Task) {
    'help' {
        @'
Tasks:
  setup       Create .venv and install the pipeline plus dev tools
  setup-full  Add SHAP, MLflow and matplotlib (optional, heavier)
  data        Download the NASA C-MAPSS dataset into data\cmapss
  pipeline    Full evaluation, then write the evidence bundle (-Fast for a quick run)
  bundle      Rebuild evidence\bundle.json from the recorded runs
  api         Serve the API on http://127.0.0.1:8000
  web         Serve the frontend on http://127.0.0.1:5173
  build       Regenerate types and build the frontend into frontend\dist
  types       Regenerate frontend types from the Pydantic schemas
  test        Run the test suite, excluding the slow full-matrix tests
  test-all    Run every test
  lint        Lint the Python and typecheck the TypeScript
  fmt         Format and apply safe lint fixes
  check       lint + test, which is what CI runs
  docker      Build the deployed replay image locally
  clean       Remove caches and local run outputs, keeping the committed bundle
'@ | Write-Host
    }

    'setup' {
        Invoke-Step 'creating the virtualenv' { python -m venv $venv }
        Invoke-Step 'installing dependencies' {
            & $py -m pip install -U pip --quiet
            & $py -m pip install -r (Join-Path $root 'backend\requirements-dev.txt')
        }
    }

    'setup-full' {
        Use-Venv
        Invoke-Step 'installing SHAP, MLflow and matplotlib' {
            & $py -m pip install -r (Join-Path $root 'backend\requirements-full.txt')
        }
    }

    'data' {
        Use-Venv
        Invoke-Step 'downloading C-MAPSS' { & $py (Join-Path $root 'scripts\fetch_data.py') }
    }

    'pipeline' {
        Use-Venv
        $args = @()
        if ($Fast) { $args += @('--fast', '--required-only') }
        Invoke-Step 'running the evaluation' {
            & $py (Join-Path $root 'scripts\run_pipeline.py') @args
        }
    }

    'bundle' {
        Use-Venv
        Invoke-Step 'rebuilding the evidence bundle' {
            & $py (Join-Path $root 'scripts\export_bundle.py')
        }
    }

    'api' {
        Use-Venv
        & $py -m uvicorn app.main:app --reload --app-dir (Join-Path $root 'backend')
    }

    'web' { Push-Location (Join-Path $root 'frontend'); try { npm run dev } finally { Pop-Location } }

    'types' {
        Use-Venv
        Invoke-Step 'generating frontend types' {
            & $py (Join-Path $root 'scripts\generate_types.py')
        }
    }

    'build' {
        & $PSCommandPath types
        Push-Location (Join-Path $root 'frontend')
        try {
            Invoke-Step 'installing frontend dependencies' { npm ci --no-audit --no-fund }
            Invoke-Step 'building the frontend' { npm run build }
        } finally { Pop-Location }
    }

    'test' {
        Use-Venv
        Invoke-Step 'running tests' { & $py -m pytest -q -m 'not slow' }
    }

    'test-all' {
        Use-Venv
        Invoke-Step 'running every test' { & $py -m pytest -q }
    }

    'lint' {
        Use-Venv
        Invoke-Step 'ruff' { & $py -m ruff check (Join-Path $root 'backend') (Join-Path $root 'scripts') }
        Push-Location (Join-Path $root 'frontend')
        try { Invoke-Step 'tsc' { npx tsc --noEmit } } finally { Pop-Location }
    }

    'fmt' {
        Use-Venv
        Invoke-Step 'ruff --fix' { & $py -m ruff check --fix (Join-Path $root 'backend') (Join-Path $root 'scripts') }
        Invoke-Step 'ruff format' { & $py -m ruff format (Join-Path $root 'backend') (Join-Path $root 'scripts') }
    }

    'check' {
        & $PSCommandPath lint
        & $PSCommandPath test
    }

    'docker' {
        Invoke-Step 'building the replay image' { docker build -t sidekick:local $root }
    }

    'clean' {
        foreach ($path in '.pytest_cache', '.ruff_cache', 'artifacts\runs', 'artifacts\exports',
            'mlruns', 'frontend\dist') {
            $full = Join-Path $root $path
            if (Test-Path $full) {
                Remove-Item -Recurse -Force $full
                Write-Host "removed $path"
            }
        }
    }
}
