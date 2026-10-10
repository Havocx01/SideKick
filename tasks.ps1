# Windows tasks. Run .\tasks.ps1 help for the available commands.
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'setup-full', 'data', 'pipeline', 'bundle', 'api', 'web',
        'build', 'types', 'docker')]
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
  setup       Create .venv and install the app and training dependencies
  setup-full  Add optional MLflow run tracking
  data        Download the NASA C-MAPSS dataset into data\cmapss
  pipeline    Full evaluation, then write the evidence bundle (-Fast for a quick run)
  bundle      Rebuild evidence\bundle.json from the recorded runs
  api         Serve the API on http://127.0.0.1:8140
  web         Serve the frontend on http://127.0.0.1:5173
  build       Regenerate types and build the frontend into frontend\dist
  types       Regenerate frontend types from the Pydantic schemas
  docker      Build the hosted demo image locally
'@ | Write-Host
    }

    'setup' {
        Invoke-Step 'creating the virtualenv' { python -m venv $venv }
        Invoke-Step 'installing dependencies' {
            & $py -m pip install -U pip --quiet
            & $py -m pip install -r (Join-Path $root 'backend\requirements-train.txt')
        }
    }

    'setup-full' {
        Use-Venv
        Invoke-Step 'installing MLflow' {
            & $py -m pip install -r (Join-Path $root 'backend\requirements-full.txt')
        }
    }

    'data' {
        Use-Venv
        Invoke-Step 'downloading C-MAPSS' { & $py (Join-Path $root 'scripts\fetch_data.py') }
    }

    'pipeline' {
        Use-Venv
        $pipelineArgs = @()
        if ($Fast) { $pipelineArgs += @('--fast', '--required-only') }
        Invoke-Step 'running the evaluation' {
            & $py (Join-Path $root 'scripts\run_pipeline.py') @pipelineArgs
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
        $serverArgs = @('app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8140', '--app-dir', (Join-Path $root 'backend'))
        $envFile = Join-Path $root '.env'
        if (Test-Path -LiteralPath $envFile -PathType Leaf) {
            $serverArgs += @('--env-file', $envFile)
        }
        & $py -m uvicorn @serverArgs
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

    'docker' {
        Invoke-Step 'building the demo image' { docker build -t sidekick:local $root }
    }
}
