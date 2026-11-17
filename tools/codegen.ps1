param([Parameter(Mandatory=$true)][string]$Rexglue)
$ErrorActionPreference = 'Stop'
$portRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location (Join-Path $portRoot 'app')
try {
    New-Item -ItemType Directory -Force (Join-Path $portRoot 'out') | Out-Null
    $env:REX_MAX_JUMP_TABLE_ENTRIES = '4096'
    $env:REXGLUE_DUMP_IMAGE = Join-Path $portRoot 'out/default_image.bin'
    & $Rexglue codegen mtg15_manifest.toml
    if ($LASTEXITCODE -ne 0) { throw 'Code generation failed' }
    [IO.File]::WriteAllText((Join-Path $portRoot 'app/generated/codegen_profile.txt'), 'optimised')
} finally { Pop-Location }
