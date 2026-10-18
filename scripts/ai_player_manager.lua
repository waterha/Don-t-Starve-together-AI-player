local Provider = require("ai_provider")
local json = require("json")

local AIPlayerManager = {}
AIPlayerManager.__index = AIPlayerManager

local MAX_PLAYERS = 5
local DEFAULT_THINK_INTERVAL = 30
local ACTION_DISTANCE = 12

local SYSTEM_PROMPT = [[You control one companion in Don't Starve Together.
Return ONLY a JSON object: {"action":"follow|wander|say|attack|gather|wait","target":"optional short target","message":"optional short message"}.
Choose one safe action from the list. Do not invent game APIs. Keep messages under 80 characters.]]

local function clamp_count(value)
    value = tonumber(value) or 0
    return math.max(0, math.min(MAX_PLAYERS, math.floor(value)))
end

local function safe_config(name, default)
    local value = GetModConfigData(name)
    return value == nil and default or value
end

local function get_spawn_point()
    local players = AllPlayers or {}
    if players[1] and players[1].Transform then
        local x, y, z = players[1].Transform:GetWorldPosition()
        return x + 2, y, z + 2
    end
    return 0, 0, 0
end

local function say(inst, message)
    if inst and inst.components.talker and message ~= "" then
        inst.components.talker:Say(message:sub(1, 80))
    end
end

local function find_target(inst, target_name)
    if target_name == nil or target_name == "" then
        return nil
    end
    local entities = TheSim:FindEntities(inst.Transform:GetWorldPosition(), ACTION_DISTANCE)
    for _, entity in ipairs(entities) do
        if entity.prefab == target_name or entity.name == target_name then
            return entity
        end
    end
    return nil
end

function AIPlayerManager.new()
    return setmetatable({ players = {}, next_id = 0 }, AIPlayerManager)
end

function AIPlayerManager:SpawnOne(index, api_key)
    if api_key == nil or api_key == "" then
        print(string.format("[AI Players] AI %d skipped: API key is not configured", index))
        return
    end

    local x, y, z = get_spawn_point()
    local ok, inst = pcall(SpawnPrefab, "wilson")
    if not ok or inst == nil then
        print(string.format("[AI Players] AI %d could not spawn the wilson prefab", index))
        return
    end

    self.next_id = self.next_id + 1
    inst.name = "ai_player_" .. tostring(self.next_id)
    inst.Transform:SetPosition(x, y, z)
    inst:AddTag("ai_player")
    inst:AddTag("companion")
    inst._ai_index = index
    inst._ai_provider = Provider.new(
        safe_config("api_base_url", "https://api.openai.com/v1"),
        safe_config("model", "gpt-4o-mini"),
        api_key
    )
    inst._ai_busy = false
    inst._ai_last_think = 0

    self.players[#self.players + 1] = inst
    print(string.format("[AI Players] AI %d spawned as %s", index, inst.name))
end

function AIPlayerManager:ApplyAction(inst, action)
    if inst == nil or not inst:IsValid() or type(action) ~= "table" then
        return
    end

    local action_name = action.action or "wait"
    if action_name == "say" then
        say(inst, action.message or "")
    elseif action_name == "follow" then
        local player = AllPlayers and AllPlayers[1]
        if player and player:IsValid() and inst.components.locomotor then
            inst.components.locomotor:GoToEntity(player, 1.5)
        end
    elseif action_name == "wander" and inst.components.locomotor then
        local x, y, z = inst.Transform:GetWorldPosition()
        inst.components.locomotor:GoToPoint(x + math.random(-8, 8), y, z + math.random(-8, 8))
    elseif action_name == "attack" then
        local target = find_target(inst, action.target)
        if target and inst.components.combat then
            inst.components.combat:SuggestTarget(target)
            inst.components.combat:TryAttack(target)
        end
    elseif action_name == "gather" then
        say(inst, "I will look for " .. tostring(action.target or "resources") .. ".")
    end
end

function AIPlayerManager:Think(inst)
    if not inst:IsValid() or inst._ai_busy then
        return
    end
    inst._ai_busy = true

    local x, y, z = inst.Transform:GetWorldPosition()
    local context = string.format(
        "Position: %.1f, %.1f, %.1f. Nearby players: %d. Day phase: %s.",
        x, y, z, #(AllPlayers or {}), TheWorld.state and TheWorld.state.phase or "unknown"
    )
    inst._ai_provider:Complete({
        { role = "system", content = SYSTEM_PROMPT },
        { role = "user", content = context },
    }, function(content, err)
        inst._ai_busy = false
        if err ~= nil then
            print(string.format("[AI Players] AI %d request failed: %s", inst._ai_index, err))
            return
        end
        local decoded_ok, action = pcall(json.decode, content)
        if decoded_ok then
            self:ApplyAction(inst, action)
        else
            print(string.format("[AI Players] AI %d returned invalid action JSON", inst._ai_index))
        end
    end)
end

function AIPlayerManager:Start()
    local count = clamp_count(safe_config("ai_count", 0))
    local think_interval = tonumber(safe_config("request_interval", DEFAULT_THINK_INTERVAL)) or DEFAULT_THINK_INTERVAL
    think_interval = math.max(15, think_interval)
    for index = 1, count do
        self:SpawnOne(index, safe_config("ai_" .. tostring(index) .. "_api_key", ""))
    end

    TheWorld:DoPeriodicTask(think_interval, function()
        for _, inst in ipairs(self.players) do
            if inst:IsValid() then
                self:Think(inst)
            end
        end
    end)
end

return AIPlayerManager
