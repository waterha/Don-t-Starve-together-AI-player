local Provider = require("ai_provider")
local json = require("json")

local AIPlayerManager = {}
AIPlayerManager.__index = AIPlayerManager

local MAX_PLAYERS = 5
local DEFAULT_THINK_INTERVAL = 30
local ACTION_DISTANCE = 12
local SYSTEM_PROMPT = [[You control one companion in Don't Starve Together.
Return ONLY a JSON object: {"action":"follow|wander|say|attack|gather|wait","target":"optional nearby prefab","message":"optional short message"}.
Choose one safe action. Gather only pickable plants or loose items. Keep messages under 80 characters.]]

local function safe_config(self, name, default)
    local value = self.get_config(name)
    return value == nil and default or value
end

local function is_human(player)
    return player and player:IsValid() and player.Transform
        and player.userid and player.userid ~= "" and not player:HasTag("ai_player")
        and not player:HasTag("playerghost")
end

local function find_human()
    for _, player in ipairs(AllPlayers or {}) do
        if is_human(player) then
            return player
        end
    end
end

local function say(inst, message)
    if inst.components.talker and type(message) == "string" and message ~= "" then
        inst.components.talker:Say(message:sub(1, 80))
    end
end

local function nearby(inst)
    local x, y, z = inst.Transform:GetWorldPosition()
    return TheSim:FindEntities(x, y, z, ACTION_DISTANCE, nil, { "INLIMBO", "FX", "DECOR" })
end

local function find_target(inst, target_name)
    if type(target_name) ~= "string" or target_name == "" then
        return
    end
    for _, entity in ipairs(nearby(inst)) do
        if entity ~= inst and (entity.prefab == target_name or entity.name == target_name) then
            return entity
        end
    end
end

function AIPlayerManager.new(get_config)
    return setmetatable({ players = {}, by_index = {}, next_id = 0, get_config = get_config }, AIPlayerManager)
end

function AIPlayerManager:SpawnOne(index, api_key, owner)
    if type(api_key) ~= "string" or api_key == "" then
        return
    end
    owner = is_human(owner) and owner or find_human()
    if not owner then
        return
    end
    local ok, inst = pcall(SpawnPrefab, "wilson")
    if not ok or not inst then
        print(string.format("[AI Players] AI %d could not spawn the wilson prefab", index))
        return
    end

    self.next_id = self.next_id + 1
    inst.name = "AI Companion " .. tostring(index)
    inst:AddTag("ai_player")
    inst:AddTag("companion")
    -- These server entities are recreated on entry, never loaded as orphan players.
    inst.persists = false
    local x, y, z = owner.Transform:GetWorldPosition()
    local offset = 2 + index
    if TheWorld.Map and not TheWorld.Map:IsPassableAtPoint(x + offset, 0, z + 2) then
        offset = 0
        inst.Transform:SetPosition(x, y, z)
    else
        inst.Transform:SetPosition(x + offset, y, z + 2)
    end
    if inst.components.playercontroller then
        inst.components.playercontroller:Enable(false)
    end
    inst._ai_index = index
    inst._ai_owner = owner
    inst._ai_mode = "follow"
    inst._ai_provider = Provider.new(
        safe_config(self, "api_base_url", "https://api.openai.com/v1"),
        safe_config(self, "model", "gpt-4o-mini"), api_key
    )
    inst._ai_busy = false
    self.players[#self.players + 1] = inst
    self.by_index[index] = inst
    say(inst, "I'm your AI companion. I'll follow you.")
    print(string.format("[AI Players] AI %d spawned beside a human player", index))
end

function AIPlayerManager:EnsureCompanions()
    local owner = find_human()
    if not owner then
        return
    end
    for index = 1, self.count do
        local existing = self.by_index[index]
        if self.keys[index] and (not existing or not existing:IsValid()) then
            self:SpawnOne(index, self.keys[index], owner)
        end
    end
end

function AIPlayerManager:Follow(inst)
    local owner = is_human(inst._ai_owner) and inst._ai_owner or find_human()
    inst._ai_owner = owner
    if not owner or not inst.components.locomotor then
        return
    end
    local x, _, z = inst.Transform:GetWorldPosition()
    local px, _, pz = owner.Transform:GetWorldPosition()
    if (x - px) * (x - px) + (z - pz) * (z - pz) > 9 then
        -- The second native argument is a BufferedAction, not a follow distance.
        inst.components.locomotor:GoToEntity(owner, nil, true)
    else
        inst.components.locomotor:Stop()
    end
end

function AIPlayerManager:ApplyAction(inst, action)
    if not inst or not inst:IsValid() or type(action) ~= "table" then
        return
    end
    local name = action.action or "wait"
    if name == "say" then
        say(inst, action.message)
    elseif name == "follow" then
        inst._ai_mode = "follow"
        self:Follow(inst)
    elseif name == "wander" and inst.components.locomotor then
        local x, y, z = inst.Transform:GetWorldPosition()
        inst._ai_mode = "wander"
        inst.components.locomotor:GoToPoint(Vector3(x + math.random(-4, 4), y, z + math.random(-4, 4)))
    elseif name == "wait" then
        inst._ai_mode = "wait"
        if inst.components.locomotor then inst.components.locomotor:Stop() end
    elseif name == "attack" or name == "gather" then
        local target = find_target(inst, action.target)
        if not target or not inst.components.locomotor then return end
        local game_action
        if name == "attack" and target.components.combat and not target:HasTag("player") then
            game_action = ACTIONS.ATTACK
        elseif name == "gather" and target.components.pickable and target.components.pickable:CanBePicked() then
            game_action = ACTIONS.PICK
        elseif name == "gather" and target.components.inventoryitem and target.components.inventoryitem.canbepickedup then
            game_action = ACTIONS.PICKUP
        end
        if game_action then
            inst._ai_mode = name
            inst.components.locomotor:PushAction(BufferedAction(inst, target, game_action), true)
        end
    end
end

function AIPlayerManager:Think(inst)
    if not inst:IsValid() or inst._ai_busy or not find_human() then return end
    inst._ai_busy = true
    local x, y, z = inst.Transform:GetWorldPosition()
    local names = {}
    for _, entity in ipairs(nearby(inst)) do
        if entity.prefab and #names < 20 then names[#names + 1] = entity.prefab end
    end
    local context = string.format("Position: %.1f, %.1f, %.1f. Day phase: %s. Nearby prefabs: %s.",
        x, y, z, TheWorld.state and TheWorld.state.phase or "unknown", table.concat(names, ", "))
    local finished = false
    local timeout
    local function finish(content, err)
        if finished then return end
        finished = true
        if timeout then timeout:Cancel() end
        inst._ai_busy = false
        if not inst:IsValid() then return end
        if err then
            inst._ai_mode = "follow"
            print(string.format("[AI Players] AI %d request failed: %s", inst._ai_index, err))
            return
        end
        local ok, action = pcall(json.decode, content)
        if ok and type(action) == "table" then
            self:ApplyAction(inst, action)
        else
            print(string.format("[AI Players] AI %d returned invalid action JSON", inst._ai_index))
        end
    end
    timeout = inst:DoTaskInTime(60, function() finish(nil, "model request timed out; following locally") end)
    inst._ai_provider:Complete({
        { role = "system", content = SYSTEM_PROMPT },
        { role = "user", content = context },
    }, finish)
end

function AIPlayerManager:Start()
    if TheWorld.ismastershard == false then
        print("[AI Players] Companion spawning is handled by the surface shard")
        return
    end
    self.count = math.max(0, math.min(MAX_PLAYERS, math.floor(tonumber(safe_config(self, "ai_count", 0)) or 0)))
    self.keys = {}
    for index = 1, self.count do
        local key = safe_config(self, "ai_" .. tostring(index) .. "_api_key", "")
        if type(key) == "string" and key ~= "" then
            self.keys[index] = key
        else
            print(string.format("[AI Players] AI %d skipped: API key is not configured", index))
        end
    end
    print(string.format("[AI Players] Configured %d companions; waiting for human world entry", self.count))
    TheWorld:ListenForEvent("ms_playerjoined", function(_, player)
        if is_human(player) then
            TheWorld:DoTaskInTime(1, function() self:EnsureCompanions() end)
        end
    end)
    TheWorld:DoTaskInTime(1, function() self:EnsureCompanions() end)
    TheWorld:DoPeriodicTask(1, function()
        for _, inst in ipairs(self.players) do
            if inst:IsValid() and inst._ai_mode == "follow" then self:Follow(inst) end
        end
    end)
    local interval = math.max(15, tonumber(safe_config(self, "request_interval", DEFAULT_THINK_INTERVAL)) or DEFAULT_THINK_INTERVAL)
    TheWorld:DoPeriodicTask(interval, function()
        for _, inst in ipairs(self.players) do
            if inst:IsValid() then self:Think(inst) end
        end
    end)
end

return AIPlayerManager
