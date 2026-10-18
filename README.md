# AI Players for Don't Starve Together

This repository contains a server-authoritative prototype Mod that can spawn up to five AI companions. Each companion can use a separate API key; keys may be repeated when several companions use the same model account.

## Important security limitation

Do not put real API keys in a public Workshop upload, Git commit, screenshot, or client-shared configuration. DST's native Mod configuration screen only supports predefined options, not arbitrary secret text input. The `ai_1_api_key` through `ai_5_api_key` options are therefore read from the server's `modoverrides.lua` file.

The Mod calls an OpenAI-compatible endpoint from the world server. Clients only install the package and receive the replicated companion entity; clients never receive the API key through this code.

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

## Logs

On Windows, inspect:

```text
Documents/Klei/DoNotStarveTogether/server_log.txt
Documents/Klei/DoNotStarveTogether/client_log.txt
```

Never commit a real `modoverrides.lua` containing API keys.
