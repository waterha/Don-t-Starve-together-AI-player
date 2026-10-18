$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$modInfo = Get-Content (Join-Path $root 'modinfo.lua') -Raw
$manager = Get-Content (Join-Path $root 'scripts\ai_player_manager.lua') -Raw
$provider = Get-Content (Join-Path $root 'scripts\ai_provider.lua') -Raw
$bridge = Get-Content (Join-Path $root 'tools\ai_http_bridge.py') -Raw

if ($modInfo -notmatch 'name = "AI Players"') { throw 'missing mod name' }
if ($modInfo -notmatch 'name = "ai_count"') { throw 'missing ai_count option' }
foreach ($i in 1..5) {
    foreach ($field in @('api_base_url', 'api_key', 'model')) {
        $option = 'name = "ai_' + $i + '_' + $field + '"'
        if ($modInfo -notmatch [regex]::Escape($option)) { throw "missing ai_${i}_${field} option" }
    }
}
if ($manager -notmatch 'safe_config\(self, "ai_"') { throw 'manager does not read per-AI keys' }
if ($manager -notmatch 'math\.min\(MAX_PLAYERS') { throw 'AI count is not capped' }
if ($manager -notmatch 'pcall\(SpawnPrefab, character\)' -or $manager -notmatch 'MODCHARACTERLIST') { throw 'registered character spawn path missing' }
if ($bridge -notmatch 'Authorization') { throw 'authorization header missing' }
if ($bridge -notmatch '/chat/completions') { throw 'chat completion endpoint missing' }
if ($provider -notmatch '127\.0\.0\.1:17893/complete') { throw 'local bridge endpoint missing' }

Write-Output 'static Mod checks passed'
