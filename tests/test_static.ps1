$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$modInfo = Get-Content (Join-Path $root 'modinfo.lua') -Raw
$manager = Get-Content (Join-Path $root 'scripts\ai_player_manager.lua') -Raw
$provider = Get-Content (Join-Path $root 'scripts\ai_provider.lua') -Raw

if ($modInfo -notmatch 'name = "AI Players"') { throw 'missing mod name' }
if ($modInfo -notmatch 'name = "ai_count"') { throw 'missing ai_count option' }
foreach ($i in 1..5) {
    $option = 'name = "ai_' + $i + '_api_key"'
    if ($modInfo -notmatch [regex]::Escape($option)) { throw "missing ai_${i}_api_key option" }
}
if ($manager -notmatch 'safe_config\(self, "ai_"') { throw 'manager does not read per-AI keys' }
if ($manager -notmatch 'math\.min\(MAX_PLAYERS') { throw 'AI count is not capped' }
if ($manager -notmatch 'SpawnPrefab, "wilson"') { throw 'AI spawn path missing' }
if ($provider -notmatch 'Authorization') { throw 'authorization header missing' }
if ($provider -notmatch '/chat/completions') { throw 'chat completion endpoint missing' }

Write-Output 'static Mod checks passed'
