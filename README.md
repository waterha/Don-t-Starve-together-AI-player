# AI Players for Don't Starve Together

This repository contains a server-authoritative prototype Mod that can spawn up to five AI companions. Each companion can use a separate API key; keys may be repeated when several companions use the same model account.

## Configure in game

1. Install the main mod as usual. For editable settings in the **Installed Mods** menu before the server mod is enabled, copy the contents of `client_config_helper` to a separate sibling folder, `mods/ai_players_config`, enable **AI Players Config** as a client mod, and restart once. The helper must be a separate mod, not a nested folder inside AI Players. Local development installs may instead add `ForceEnableMod("ai_players_config")` to the game's `mods/modsettings.lua`; remove that line to stop automatically loading the helper.
2. Open **AI Players** configuration and set **AI player count** to 0-5. Exactly that many API key input boxes appear immediately; at zero, none appear.
3. Click each **AI N API key** text box and type or paste the key. Characters are masked. Keys may be repeated. Reducing the count hides unused key fields and preserves their values for later reuse.
4. Edit **API base URL** and **Model** to match your OpenAI-compatible provider.
5. Click **Apply** to save using DST's normal host configuration. Reopening preserves the values and visible key count. **Back** discards pending edits; **Reset** restores defaults, including count zero and no visible key fields.

6. Start the API bridge on the computer running the world server. On Windows, double-click `tools/start_ai_bridge.cmd` and keep its console open; it needs Python 3 and no extra packages. Alternatively run `python tools/ai_http_bridge.py` (`python3` on Linux). It listens only at `http://127.0.0.1:17893`; check `http://127.0.0.1:17893/health` for `{"ok":true}`. A remote dedicated server needs its own bridge on that server.
7. Enable **AI Players** in the world's **server mods**, start/resume the world, and enter with your character. Configured companions appear beside the first living human after entry, announce themselves, and follow locally. Loading only **AI Players Config** enables editing but does not spawn companions.

The helper initializes the configuration UI in the frontend; a disabled server mod does not run its own frontend entry when its settings are opened. The helper also opens AI Players settings with the host configuration so changes from Installed Mods reach the server instead of going into a separate client-only configuration. Other mods retain their normal behavior. The main server mod must still be enabled for the hosted world to spawn companions. Dedicated servers can use the override example below without installing the client helper.

**Request interval** is the delay in seconds between scheduled model calls for each AI (15, 30, or 60; default 30). At 30 seconds, five configured AIs make at most about 10 calls per minute after startup. An AI with a request still in flight skips that tick. This controls decision frequency and API usage, not game frame rate or movement speed.

## API key storage

Keys are masked on screen but saved as normal DST configuration strings, without encryption by this mod. Do not put real keys in Workshop uploads, commits, screenshots, shared saves, or shared configuration files. The world server sends each request and key to its loopback bridge, which forwards the key only as Authorization to your configured API URL. The bridge logs no request bodies or credentials. The mod adds no RPC to send keys to clients. Masking does not make DST's configuration storage a secret vault.

## Server setup

1. Copy this Mod directory into the server's `mods` directory.
2. Enable the Mod in the server's `modoverrides.lua`.
3. Set `ai_count` between `0` and `5`.
4. Fill the corresponding API keys. A key can be repeated for multiple AI players.
5. Set `api_base_url` and `model` if your provider is OpenAI-compatible.
6. Start `python tools/ai_http_bridge.py` on this server before entering the world.

Example `modoverrides.lua` entry:

```lua
return {
    ["ai_players"] = {
        enabled = true,
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

Use your actual local mod folder name as the entry key. After publishing to Workshop, replace it with `workshop-` followed by the actual Workshop ID.

## Current prototype behavior

- Server reads and clamps the requested count to 0-5.
- The surface server waits for a living human to enter, then spawns the configured Wilson-based companions nearby. Cave shards do not create a duplicate group. Companions are recreated per world session rather than saved as orphan player entities.
- They are physical server-controlled companions, not separate Steam/WeGame clients. They do not join the network player roster or consume authenticated player accounts. They do not migrate with you into caves.
- Local follow updates run every second, independently of the model interval. If the model request fails or times out, companions return to local follow.
- Every companion periodically sends position, phase and nearby prefab names to the configured model through the local bridge. The bridge adds the API's Authorization header; native DST POST uses the demonstrated four-argument `QueryServer` form.
- The model returns JSON with one action: `follow`, `wander`, `say`, `attack`, `gather`, or `wait`. Gathering dispatches PICK for ready plants or PICKUP for loose items. This does not implement full autonomous survival, crafting, tool use or base building.
- The bridge accepts a provider root, `/v1` prefix or full `/chat/completions` endpoint. A root URL gains `/v1/chat/completions`; other API prefixes gain `/chat/completions`.
- Invalid responses and HTTP failures are logged without stopping simulation. In-flight requests time out so later requests are not blocked indefinitely.
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
