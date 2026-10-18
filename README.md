# AI Players for Don't Starve Together

This repository contains a server-authoritative prototype Mod that can spawn up to five AI companions. Each companion can use a separate API key; keys may be repeated when several companions use the same model account.

## Configure in game

1. Install the main mod as usual. For editable settings in the **Installed Mods** menu before the server mod is enabled, copy the contents of `client_config_helper` to a separate sibling folder, `mods/ai_players_config`, enable **AI Players Config** as a client mod, and restart once. The helper must be a separate mod, not a nested folder inside AI Players. Local development installs may instead add `ForceEnableMod("ai_players_config")` to the game's `mods/modsettings.lua`; remove that line to stop automatically loading the helper.
2. Open **AI Players** configuration and set **AI player count** to 0-5. Exactly that many API key input boxes appear immediately; at zero, none appear.
3. Click each **AI N API key** text box and type or paste the key. Characters are masked. Keys may be repeated. Reducing the count hides unused key fields and preserves their values for later reuse.
4. Edit **API base URL** and **Model** to match your OpenAI-compatible provider.
5. Click **Apply** to save using DST's normal host configuration. Reopening preserves the values and visible key count. **Back** discards pending edits; **Reset** restores defaults, including count zero and no visible key fields.

The helper initializes the configuration UI in the frontend; a disabled server mod does not run its own frontend entry when its settings are opened. The helper also opens AI Players settings with the host configuration so changes from Installed Mods reach the server instead of going into a separate client-only configuration. Other mods retain their normal behavior. The main server mod must still be enabled for the hosted world to spawn companions. Dedicated servers can use the override example below without installing the client helper.

**Request interval** is the delay in seconds between scheduled model calls for each AI (15, 30, or 60; default 30). At 30 seconds, five configured AIs make at most about 10 calls per minute after startup. An AI with a request still in flight skips that tick. This controls decision frequency and API usage, not game frame rate or movement speed.

## API key storage

Keys are masked on screen but saved as normal DST configuration strings, without encryption by this mod. Do not put real keys in Workshop uploads, commits, screenshots, shared saves, or shared configuration files. The world server makes model requests; the mod adds no RPC to send keys to clients. Masking does not make DST's configuration storage a secret vault.

## Server setup

1. Copy this Mod directory into the server's `mods` directory.
2. Enable the Mod in the server's `modoverrides.lua`.
3. Set `ai_count` between `0` and `5`.
4. Fill the corresponding API keys. A key can be repeated for multiple AI players.
5. Set `api_base_url` and `model` if your provider is OpenAI-compatible.

Example `modoverrides.lua` entry:

```lua
return {
    ["workshop-0000000000"] = {
        configuration_options = {
            ai_count = 2,
            ai_1_api_key = "REPLACE_WITH_SERVER_SECRET_1",
            ai_2_api_key = "REPLACE_WITH_SERVER_SECRET_1",
            ai_3_api_key = "",
            ai_4_api_key = "",
            ai_5_api_key = "",
            api_base_url = "https://api.openai.com/v1",
            model = "gpt-4o-mini",
            request_interval = 30,
        },
    },
}
```

Replace the key in the example with the actual Workshop ID after publishing. For a local Mod, use the local Mod folder name supported by the server configuration.

## Current prototype behavior

- Server reads and clamps the requested count to 0-5.
- Each configured AI attempts to spawn a Wilson-based companion near the first human player.
- Every companion periodically sends a small world-state summary to the configured model.
- The model must return JSON with one action: `follow`, `wander`, `say`, `attack`, `gather`, or `wait`.
- Invalid responses and HTTP failures are logged and do not stop the world simulation.
- Requests are scheduled at the configured interval, with a minimum of 15 seconds.

This is an early implementation. DST's player prefab and HTTP callback behavior vary between game builds, so test it on a dedicated server and inspect `server_log.txt` before using it in an existing world.

## Tests

The configuration regressions use Lua 5.1 through `lupa`. Point `DST_SCRIPTS_ZIP` to your installed game's `data/databundles/scripts.zip` to exercise its native configuration screen; game source is not included in this repository. The UI test explicitly skips if that resource is unavailable.

```powershell
python -m pip install lupa
$env:DST_SCRIPTS_ZIP = 'C:\path\to\DST\data\databundles\scripts.zip'
python -m unittest discover -s tests -p 'test_*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_static.ps1
```

## Logs

On Windows, inspect:

```text
Documents/Klei/DoNotStarveTogether/server_log.txt
Documents/Klei/DoNotStarveTogether/client_log.txt
```

Never commit a real `modoverrides.lua` containing API keys.
