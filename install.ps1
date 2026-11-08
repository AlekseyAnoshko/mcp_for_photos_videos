$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'scripts/deploy.py'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $installer @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $installer @args
} else {
    throw 'Нужен Python 3.11+. См. README.md → Требования.'
}
exit $LASTEXITCODE
