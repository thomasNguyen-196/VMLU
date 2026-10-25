<#
.SYNOPSIS
Rebuild the results DB on the deploy PC from the files under the repo root.

.DESCRIPTION
Runs seed_registries -> migrate_results_to_mongo -> verify_results_db in a
throwaway python:3.12-slim container on the compose network (Mongo publishes
no host port). The repo is mounted read-only and every write is an upsert, so
a re-run is safe. Called by the seed-db job in deploy.yml and by
tools/push_data_to_pc.py, which is also how the data files reach the PC.
#>
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Network = 'vmlu_default',
    [string]$Image = 'python:3.12-slim'
)
Set-Location -LiteralPath $Root

# The root measurement_card.md is a symlink into vmlu_docs/. A Windows clone
# with core.symlinks=false writes it as a text file holding the target path,
# and core.autocrlf=true gives the target CRLF line endings: hashing either one
# stamps a card hash that matches no committed registry. Write the committed
# bytes to an ignored scratch dir and mount them over the symlink instead.
$card = 'measurement_card.md'
if ((git ls-files -s -- $card) -match '^120000 ') { $card = (git cat-file blob "HEAD:$card").Trim() }
if ($LASTEXITCODE -ne 0) { throw "cannot resolve $card in HEAD" }
git -c core.autocrlf=false checkout-index -f --prefix=.seed/ -- $card
if ($LASTEXITCODE -ne 0) { throw "cannot write $card from the index" }
$scratch = Join-Path $Root '.seed'
$cardFile = Join-Path $scratch ($card -replace '/', '\')

# No double quotes inside $steps: Windows PowerShell 5.1 passes native-command
# arguments with embedded quotes unescaped, and sh would run a truncated command.
$mongo = 'mongodb://mongo:27017/'
$steps = @(
    'pip install -q pymongo pandas tqdm python-dotenv openai',
    "python code_benchmark/seed_registries.py --uri $mongo",
    "python code_benchmark/migrate_results_to_mongo.py --uri $mongo",
    "python code_benchmark/verify_results_db.py --uri $mongo"
) -join ' && '
try {
    docker run --rm --network $Network `
        -e PYTHONDONTWRITEBYTECODE=1 -e PIP_DISABLE_PIP_VERSION_CHECK=1 -e PIP_ROOT_USER_ACTION=ignore `
        -v "${Root}:/work:ro" -v "${cardFile}:/work/measurement_card.md:ro" -w /work `
        $Image sh -c $steps
    if ($LASTEXITCODE -ne 0) { throw "seed -> migrate -> verify failed (exit $LASTEXITCODE)" }
} finally {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
