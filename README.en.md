# AI Players for Don't Starve Together

[简体中文](README.md) | **English**

## Contribution Language

Use Chinese for all new commit subjects and bodies. Keep the default Chinese README and this English translation in sync when behavior or setup changes; do not rewrite existing commit history.

This server-authoritative mod adds up to five AI bots. When a human enters a new world or resumes an existing save with the mod enabled, bots appear as **[AI]** entries in the in-game player list, choose their own character through the configured model, enter the world and run basic autonomous survival actions. Each bot has its own API URL, API key and model name, so different providers can be used together; repeated keys are supported.

These are mod-controlled bots. Their rows extend the in-game list; they are not separate Steam/WeGame connections, do not occupy authenticated client slots, and do not appear as connections in the external server browser.

## Configure in game

1. Install the main mod as usual. For editable settings in the **Installed Mods** menu before the server mod is enabled, copy the contents of `client_config_helper` to a separate sibling folder, `mods/ai_players_config`, enable **AI Players Config** as a client mod, and restart once. The helper must be a separate mod, not a nested folder inside AI Players. Local development installs may instead add `ForceEnableMod("ai_players_config")` to the game's `mods/modsettings.lua`; remove that line to stop automatically loading the helper.
2. Open **AI Players** configuration and set **AI player count** to 0-5. Exactly that many groups appear, each with **AI N API URL**, **AI N API key**, **AI N Model** and **AI N API format**; at zero, no provider fields appear.
3. Fill each AI's URL, key and model separately. For example, AI 1 can use a relay's URL/key/model while AI 2 uses `https://api.openai.com/v1`, its OpenAI key and `gpt-4o-mini`. Each endpoint must support its selected OpenAI-compatible Chat Completions or Responses protocol. Only keys are masked; URL and model text remain visible. Reducing the count hides unused groups and preserves all three values for reuse.
4. Blank URL/model fields fall back to the old shared settings for upgraded saves, or `https://api.openai.com/v1` and `gpt-4o-mini` for a fresh setup. Explicit per-AI values always take precedence; one AI's values never become another AI's defaults. The former shared URL/model rows are hidden.
5. Click **Apply** to save using DST's normal host configuration. Reopening preserves the values and visible group count. **Back** discards pending edits; **Reset** restores defaults, including count zero and no visible provider fields.

6. Start the API bridge on the computer running the world server. On Windows, double-click `tools/start_ai_bridge.cmd` and keep its console open; it needs Python 3 and no extra packages. Alternatively run `python tools/ai_http_bridge.py` (`python3` on Linux). It listens only at `http://127.0.0.1:17893`; check `http://127.0.0.1:17893/health` for `{"ok":true}`. A remote dedicated server needs its own bridge on that server.
7. Enable **AI Players** in the world's **server mods**, start/resume the world, and enter with your character. Open the in-game player list: each configured bot first shows **Selecting**, then its chosen character and **Alive** once it enters nearby. A dead bot shows **Dead**. Bots pursue their own food/material/light needs rather than following by default. Loading only **AI Players Config** enables editing but does not start bots. For an existing save, enable the server mod before resuming; no new world is required.

The helper initializes the configuration UI in the frontend; a disabled server mod does not run its own frontend entry when its settings are opened. The helper also opens AI Players settings with the host configuration so changes from Installed Mods reach the server instead of going into a separate client-only configuration. Other mods retain their normal behavior. The main server mod must still be enabled for the hosted world to spawn companions. Dedicated servers can use the override example below without installing the client helper.

**Request interval** is the delay in seconds between scheduled action decisions for each AI (5, 10, 15, 30, or 60; default 30). At 30 seconds, five active bots make at most about 10 scheduled calls per minute; at 10 seconds about 30, and at 5 seconds about 60. Startup additionally makes one character-selection request and one initial action request per bot. A bot with an action request still in flight skips that tick. The default has not changed: faster local actions do not require more API calls.

The local survival loop checks every **0.25 seconds**, independently of HTTP/model requests (previously 2 seconds). This reduces scheduling delay, not animation, pathfinding or provider latency. It resumes validated chopping/mining work between swings without another model request. A model command received while the bot is busy is kept for up to 10 seconds and revalidated when idle, with survival needs taking priority. Delayed wait/wander replies cannot stop existing buffered work. Autonomous goals are checked once per second; exploration retains its destination and rotates visited areas. Follow updates are limited to twice per second. Actual frame-time and end-to-end latency in a running game have not been measured.

The bridge also reports invalid configuration by field (`invalid base_url`, `invalid api_key`, `invalid model`, or `invalid messages`) without echoing submitted values. Leading/trailing whitespace on URL, key and model is removed; internal key control characters remain rejected. Repeated validation errors mean requests are failing, not merely responding slowly. Check configuration before selecting a shorter interval.

## Autonomous Names and Mod Characters

Before entering the world, each AI chooses its display name and character in the same selection request; naming adds no extra request. Its roster entry becomes `[AI] Chosen name`, and later model observations include that name. UTF-8 names, including Chinese, are supported. Control characters and surrounding whitespace are removed, with a limit of 48 characters. Missing or invalid names fall back to `AI N` without discarding a valid character choice.

Candidates come from the world's built-in character list and `AddModCharacter` registrations, intersected with loaded prefabs instead of the previous nine-character list. Removed default characters, internal transformation-only characters and unloaded prefabs are excluded. **Character mods must be enabled for this world, not merely installed, and clients must load them as required by those mods.** This mod does not download or enable other mods automatically.

Invalid or timed-out choices use an available fallback. Failed mod-character spawning tries an available safe default; with no available character, no bot is spawned. Names and characters are chosen again each world session rather than persisted. Generic survival behavior does not implement every mod character's special abilities. Characters requiring real clients or custom initialization may be incompatible; third-party character mods have not each been validated in game.

## Selection Troubleshooting

Version 0.2.7 fixes the mismatch between DST's private `json.encode` and standard HTTP JSON. Apostrophes in prompts could become invalid `\\'` escapes, causing `invalid completion request` before the model received anything. Outbound requests now use compliant encoding with complete control-character escaping. The bridge normalizes Unicode escapes in both the response envelope and model JSON content to UTF-8, preventing misread Chinese names or escaped character identifiers. Restart the world server and API bridge after upgrading; existing provider settings and request counts are unchanged.

`model selected character willow` confirms a model choice. `character selection failed (...); fallback wilson` records fallback with a fixed reason for configuration/API errors, timeout, invalid JSON, or an unavailable character. Logs include no keys or response bodies. The model may still legitimately choose Wilson; this fix does not force randomized characters. Unavailable APIs retain a safe fallback, and gathering alone does not prove connectivity because local planning works independently.

## Goal-Driven Progression

The previous local loop only restocked grass, twigs and food; it had no technology milestones or building-placement capability. Each bot now retains an independent session goal: **light supplies -> axe -> logs -> pickaxe -> rocks and gold -> science machine -> approach the station, prototype and equip a backpack -> bounded reserves and exploration**. An observed existing science machine can be reused. Safety and food remain higher priority; goal checks run once per second without increasing scheduled API calls.

The system prompt includes verified starter knowledge. Observations include the current goal, missing materials, last dispatched action, blocked reason, recipe technology/material status, nearby structures and usable tools. Gathering targets actual shortages. Missing resources trigger exploration toward less-visited legal land, and repeated attempts without observed progress try another route. Changing chop/mine work remaining counts as progress. Exploration memory is bounded, not full-map navigation.

Real-material placement supports science machines, campfires and fire pits using native terrain validation. The local planner pursues science; campfires remain model-requested actions. Native build buffers are reused after invalid placement without paying twice. Only actual inventory, equipment, structures or native completion events confirm a milestone, never command dispatch. Prototyping retains native character, technology, inventory and success-callback gates; recipes are not unlocked for free.

See the [research notes](docs/survival-research.md) for evidence and recipe sources. This is a starter progression loop, not complete autonomy: rope/armor/alchemy/cooking, automatic fueling, resource-route memory, complex diets/combat and seasonal strategies remain incomplete or unsupported. Long-term survival for every default/mod character is not guaranteed. Goals and bot inventories do not persist across world sessions.

Version 0.2.9 announces model-offline authentication failures after selection fallback or a public-chat request receiving `401` / an invalid key. Notices are limited to once per bot per 60 seconds; failed chat remains pending. Confirm a valid **API key** in the provider console, not a website password or other credential, then Apply and restart the world. Switching to Responses cannot make rejected credentials valid. Local help questions, spawn introductions and survival do not prove successful model access.

## Conversation, Help and Advice Trials

Public speech is routed to one living bot: **no @mention or bot name is required**. Simply say `Hello, what are you doing?` in public chat. `@AI1` or `@ChosenName` is optional targeted routing. Otherwise the latest still-active bot question takes precedence, then proximity to the speaker. One message does not trigger all five bots. Whispers, emotes, unknown senders and non-living human characters are excluded. Replies use labeled `[AI Name]` system chat plus talker bubbles, never a forged client identity. Autonomous model ticks execute actions silently; public speech is reserved for human-chat replies or rate-limited help when genuinely stuck.

- About 45 seconds without material/recipe progress triggers a Chinese help question. Autonomous model ticks never speak; help questions are generated only by the local stall detector. Help has a 90-second cooldown, and active questions expire after about 180 seconds.
- Human replies are **untrusted suggestions**, not orders. The model may clarify, disagree, or explicitly attempt a concrete suggestion as a provisional hypothesis. Trials require at least 10 seconds and observed shortage progress for a progress report; after 75 seconds without progress they become inconclusive. Progress is not causal proof or permanent recipe learning. Greetings do not create trials.
- Once a bot receives advice, its model actions remain deterministically restricted for that session: no prompted attacks, ignition, dropping/giving items, or code execution; crafting/building uses the existing whitelist and chopping/mining is limited to supported natural trees/rocks. Native food, inventory, materials, tool, technology and environmental checks still apply. Autonomous survival does not wait for conversation HTTP requests. Rejected operations are not reported as successful.
- Charcoal illustrates the capability limit: bots may ask how it is obtained, gather existing charcoal or chop observed already-burnt supported trees. **Controlled ignition is not implemented.** Asking a bot to burn a base does not unlock an action or generate missing gameplay code.
- Each bot retains at most 12 bounded conversation entries. A speaker's messages to the same bot are accepted at most once every 2 seconds. Chat-triggered extra requests have an 8-second minimum interval and share the existing in-flight lock. New arrivals survive older replies. The latest message is pending, while preceding messages remain in bounded history. Failed requests preserve the pending message for retry.

**Cost and privacy:** Chat can add model calls beyond the unchanged periodic schedule, at most roughly 7.5 chat-triggered calls per bot per minute, usually fewer due to in-flight requests. Pending-chat output budgets increase from 160 to at most 320 tokens for short replies. Public speech, game sender identifiers and bounded history are sent through the loopback bridge to that bot's configured provider. AI replies are public to the shard. Never post credentials or private information. Conversation/trial memory is session-only, not persisted learning. Tests execute installed native Lua chat callbacks with mocked engine calls; real host/remote C++ callback delivery and display are still unverified.

## Responses API (0.2.8)

Each group now has **AI N API format**: `chat_completions` (default for backward compatibility) or `responses`. Select **Responses** when required by your provider, then supply its API URL, key and model (for example, `gpt-6.1-sol`). Protocols are not guessed from model names, and failed calls never automatically retry through another protocol.

Responses accepts a root URL, `/v1` prefix or full `/v1/responses` endpoint. Roots gain `/v1/responses`; other prefixes gain `/responses`. A Chat Completions endpoint cannot be used with Responses or vice versa. The bridge sends `input`, `max_output_tokens` and `text.format`, disables streaming and storage, omits `temperature`, and extracts message `output_text` from `output`. Refused, incomplete or textless responses fail explicitly instead of becoming successful choices.

Responses uses an output budget of **2048 tokens per call**, including reasoning tokens, to reduce JSON truncation with the previous 160/320 budgets. Actual usage is provider-dependent; the budget may still be exhausted. Chat Completions budgets and request cadence are unchanged. Protocol support does not fix `HTTP 401`: valid authorization, quota and protocol access are still required. Restart the game and bridge, select Responses and **Apply** before resuming the world. Local tests cover the native JSON codec, real HTTP bridge, Chinese names and a non-Wilson selection; no paid provider or real game window was tested.

## API key storage

Keys are masked on screen but saved as normal DST configuration strings, without encryption by this mod. Do not put real keys in Workshop uploads, commits, screenshots, shared saves, or shared configuration files. The world server sends each request and key to its loopback bridge, which forwards the key only as Authorization to your configured API URL. The bridge logs no request bodies or credentials. The mod adds no RPC to send keys to clients. Masking does not make DST's configuration storage a secret vault.

## Server setup

1. Copy this Mod directory into the server's `mods` directory.
2. Enable the Mod in the server's `modoverrides.lua`.
3. Set `ai_count` between `0` and `5`.
4. Fill `ai_N_api_base_url`, `ai_N_api_key`, `ai_N_model` and `ai_N_api_format` (`chat_completions` or `responses`, defaulting to the former) for each AI. A key can be repeated for multiple AI players.
5. Each URL must support the selected protocol. Different AIs can use different providers and model names.
6. Start `python tools/ai_http_bridge.py` on this server before entering the world.

Example `modoverrides.lua` entry:

```lua
return {
    ["ai_players"] = {
        enabled = true,
        configuration_options = {
            ai_count = 2,
            ai_1_api_base_url = "https://relay.example/v1",
            ai_1_api_key = "REPLACE_WITH_RELAY_SECRET",
            ai_1_model = "REPLACE_WITH_RELAY_MODEL_NAME",
            ai_1_api_format = "responses",
            ai_2_api_base_url = "https://api.openai.com/v1",
            ai_2_api_key = "REPLACE_WITH_OPENAI_SECRET",
            ai_2_model = "gpt-4o-mini",
            request_interval = 30,
        },
    },
}
```

Use your actual local mod folder name as the entry key. After publishing to Workshop, replace it with `workshop-` followed by the actual Workshop ID.

## Bot lifecycle and current behavior

- The surface server clamps the configured count to 0-5 and starts after the first living human enters. The same path handles a new world and enabling the mod before resuming an existing save.
- Each configured key creates an **[AI] AI N** player-list row in **Selecting** state. The model independently chooses a name and an available built-in or enabled mod character. After selection, the character spawns on safe ground near the human and the row changes to **Alive**. Duplicate human/bot join events do not create duplicate bots. Missing keys skip their bot.
- If selection fails, returns an unsupported character or exceeds 60 seconds, a supported default character is used. This fallback is logged. A disconnected human delays entry until a human returns. There is no requirement to run or click through an additional real client's character-selection screen.
- The model receives health, hunger, sanity, inventory counts, equipment, nearby usable resources and GUIDs, threats, light, phase, recipe access/materials, structures and the current development goal. It can request gathering, eating, item crafting/equipping, chopping/mining with owned tools, whitelisted building placement, exploration, moving toward a discovered science station, speech, waiting, following or attacking non-player targets.
- The local quarter-second survival loop avoids imminent attackers, eats suitable owned food when hungry, gathers food and bounded grass/twig supplies, and crafts/equips a torch using actual ingredients only when light is needed. Bright dusk reserves materials without crafting or equipping; already-lit nights do not trigger another torch. Model commands share this guard. An equipped torch is not automatically stowed merely because its own light illuminates the bot. Pending movement/work and busy stategraph actions are preserved. Bots have no free supplies, health or invincibility. Model failures leave this local behavior running.
- Bot rows use normal scrolling and show status and character. They have no real-client profile, mute, kick, ban or account actions. They do not alter the network client table or authenticated player count.
- Bots use native character prefabs, which participate in some native player gameplay systems even without client identities. This is still an early bot implementation, not a complete player replacement.
- Death is shown as **Ghost**. The bot asks the team once in public chat about revival help, waits 60 seconds, then searches for a usable touchstone or an enabled resurrection portal and attempts to revive itself. After native resurrection it continues with the same character and AI slot; without a usable point it remains a ghost. Bots and their inventories are recreated each world session, rather than persisted as authenticated player sessions. They do not migrate into caves, and the player-list snapshot is currently replicated within the surface shard only.
- Crafting supports torches, axes, pickaxes and backpacks, including native prototyping near a compatible station. Placement supports science machines, campfires and fire pits. Complete base management, advanced pathfinding, seasons/boss strategies and reliable long-term autonomous survival are not implemented.
- The bridge accepts a provider root, `/v1` prefix or full `/chat/completions` endpoint. A root URL gains `/v1/chat/completions`; other API prefixes gain `/chat/completions`. The bridge adds Authorization; native DST POST uses its supported four-argument `QueryServer` form.

The Lua regression suite covers entry, independent character selection, list replication, local actions and request failures. Native-engine smoke testing in an isolated offline WeGame runtime was blocked before Lua initialization by Rail (`Please make sure the TGP is running!`, result 2). Actual game rendering, remote replication and long-running survival have not been validated.

## Tests

The regressions use Lua 5.1 through `lupa`. Point `DST_SCRIPTS_ZIP` to your installed game's `data/databundles/scripts.zip` to exercise its actual configuration and player-list screen Lua with mocked engine/widgets; game source is not included in this repository. Native-screen tests explicitly skip if that resource is unavailable. HTTP tests run the real local bridge against fixture upstream servers, without paid model calls.

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
