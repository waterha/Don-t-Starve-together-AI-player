local Provider = require("ai_provider")
local Survival = require("ai_survival")
local Roster = require("ai_players_roster")
local json = require("json")

local AIPlayerManager = {}
AIPlayerManager.__index = AIPlayerManager

local MAX_PLAYERS = 5
local CHARACTERS = { "wilson", "willow", "wolfgang", "wendy", "wx78", "wickerbottom", "woodie", "wathgrithr", "webber" }
local SYSTEM_PROMPT = [[You independently play a survivor in Don't Starve Together.
Return ONLY JSON: {"action":"gather|eat|craft|equip|chop|mine|wander|say|attack|wait|follow","target":"nearby prefab or GUID","item":"inventory prefab","recipe":"recipe name","message":"short text"}.
Use the observed inventory, nearby resources, hunger, health, light and threats. Collect food and materials, eat before starving, prepare a torch before night, and avoid dangerous combat. Never attack players. Craft only recipes you can actually make. Do not just follow the human; pursue your own survival.]]

local function safe_config(self, name, default)
    local value = self.get_config(name)
    return value == nil and default or value
end

local function provider_option(self, index, name, default)
    local value = safe_config(self, "ai_" .. index .. "_" .. name, "")
    if type(value) == "string" and value ~= "" then return value end
    -- Retain old shared settings only as a fallback for pre-upgrade saves.
    value = safe_config(self, name, default)
    return type(value) == "string" and value ~= "" and value or default
end

local function new_provider(self, index, api_key)
    return Provider.new(provider_option(self, index, "api_base_url", "https://api.openai.com/v1"),
        provider_option(self, index, "model", "gpt-4o-mini"), api_key)
end

local function is_human(player)
    return player and player:IsValid() and player.Transform and player.userid and player.userid ~= ""
        and not player:HasTag("ai_player") and not player:HasTag("playerghost")
end

local function find_human()
    for _, player in ipairs(AllPlayers or {}) do
        if is_human(player) then return player end
    end
end

local function alive(inst)
    return inst and inst:IsValid() and not inst:HasTag("playerghost")
        and not (inst.components.health and inst.components.health:IsDead())
end

local function available(inst)
    return alive(inst) and not (inst.sg and inst.sg:HasStateTag("busy"))
        and not (inst.GetBufferedAction and inst:GetBufferedAction())
        and not (inst.components.locomotor and inst.components.locomotor.bufferedaction)
end

local function say(inst, message)
    if inst.components.talker and type(message) == "string" and message ~= "" then
        inst.components.talker:Say(message:sub(1, 160))
    end
end

local function nearby(inst)
    local x, y, z = inst.Transform:GetWorldPosition()
    return TheSim:FindEntities(x, y, z, 12, nil, { "INLIMBO", "FX", "DECOR" })
end

local function permitted_character(name)
    for _, character in ipairs(CHARACTERS) do
        if character == name then return character end
    end
end

function AIPlayerManager.new(get_config)
    return setmetatable({ players = {}, by_index = {}, slots = {}, get_config = get_config }, AIPlayerManager)
end

function AIPlayerManager:PublishRoster()
    local records = {}
    for index = 1, self.count or 0 do
        local slot = self.slots[index]
        if slot then
            records[#records + 1] = { index = index, name = "AI " .. index, status = slot.status,
                character = slot.character, GUID = slot.inst and slot.inst:IsValid() and slot.inst.GUID or nil }
        end
    end
    Roster.Publish(records)
end

function AIPlayerManager:SpawnOne(index, api_key, owner, character)
    owner = is_human(owner) and owner or find_human()
    if not owner then return end
    local slot = self.slots[index]
    character = permitted_character(character) or "wilson"
    local ok, inst = pcall(SpawnPrefab, character)
    if not ok or not inst then
        if character ~= "wilson" then ok, inst = pcall(SpawnPrefab, "wilson"); character = "wilson" end
        if not ok or not inst then
            if slot then slot.status = "dead"; self:PublishRoster() end
            print(string.format("[AI Players] AI %d could not spawn", index))
            return
        end
    end
    inst.name = "AI " .. index
    inst:AddTag("ai_player")
    inst:AddTag("companion")
    inst.persists = false
    local x, y, z = owner.Transform:GetWorldPosition()
    local px, pz = x + 2 + index, z + 2
    if TheWorld.Map and not TheWorld.Map:IsPassableAtPoint(px, 0, pz) then px, pz = x, z end
    inst.Transform:SetPosition(px, y, pz)
    if inst.components.playercontroller then inst.components.playercontroller:Enable(false) end
    inst._ai_index, inst._ai_owner, inst._ai_mode = index, owner, "autonomous"
    inst._ai_provider = slot and slot.provider or new_provider(self, index, api_key)
    inst._ai_busy = false
    self.players[#self.players + 1] = inst
    self.by_index[index] = inst
    if slot then
        slot.inst, slot.character, slot.status = inst, character, "alive"
        inst:ListenForEvent("death", function()
            slot.status = "dead"
            self:PublishRoster()
        end)
        inst:ListenForEvent("onremove", function()
            slot.status = "dead"
            self:PublishRoster()
        end)
    end
    self:PublishRoster()
    say(inst, "AI " .. index .. ": " .. character .. ". I'll find food and prepare for night.")
    print(string.format("[AI Players] AI %d entered as %s", index, character))
    -- An immediate decision complements the local survival loop; later calls use the configured interval.
    inst:DoTaskInTime(1, function() if alive(inst) then self:Think(inst) end end)
end

function AIPlayerManager:BeginSelection(index)
    local slot = self.slots[index]
    if not slot or slot.selecting_started or slot.status ~= "selecting" then return end
    slot.selecting_started = true
    local finished, timeout = false, nil
    local function finish(content, err)
        if finished then return end
        finished = true
        if timeout then timeout:Cancel() end
        local ok, result = pcall(json.decode, content or "")
        local selected = ok and type(result) == "table" and permitted_character(result.character) or nil
        if not selected then
            selected = CHARACTERS[((index - 1) % #CHARACTERS) + 1]
            print(string.format("[AI Players] AI %d character selection unavailable; using %s", index, selected))
        end
        slot.character = selected
        -- A disconnected human does not leave an unseen bot at the origin.
        if not find_human() then
            slot.status, slot.selecting_started = "selecting", false
            self:PublishRoster()
            return
        end
        self:SpawnOne(index, self.keys[index], find_human(), selected)
    end
    timeout = TheWorld:DoTaskInTime(60, function() finish(nil, "selection timed out") end)
    slot.provider:Complete({
        { role = "system", content = 'Choose your own playable character. Return ONLY JSON {"character":"prefab"}. Allowed: ' .. table.concat(CHARACTERS, ", ") .. '. Prefer a character suitable for autonomous survival. Do not return an action.' },
        { role = "user", content = "You are AI " .. index .. ". Other bots choose independently. Select your character and enter the world." },
    }, finish)
end

function AIPlayerManager:EnsureCompanions()
    if not find_human() then return end
    for index = 1, self.count do
        if self.keys[index] then
            local slot = self.slots[index]
            if not slot then
                slot = { status = "selecting", provider = new_provider(self, index, self.keys[index]) }
                self.slots[index] = slot
                self:PublishRoster()
            end
            if slot.status == "selecting" and not slot.selecting_started then
                TheWorld:DoTaskInTime(1, function() self:BeginSelection(index) end)
            end
        end
    end
end

function AIPlayerManager:Follow(inst)
    local owner = is_human(inst._ai_owner) and inst._ai_owner or find_human()
    inst._ai_owner = owner
    if not owner or not inst.components.locomotor then return end
    local x, _, z = inst.Transform:GetWorldPosition()
    local px, _, pz = owner.Transform:GetWorldPosition()
    if (x - px)^2 + (z - pz)^2 > 9 then inst.components.locomotor:GoToEntity(owner, nil, true)
    else inst.components.locomotor:Stop() end
end

function AIPlayerManager:Wander(inst)
    if not inst.components.locomotor then return end
    local x, y, z = inst.Transform:GetWorldPosition()
    local px, pz = x + math.random(-4, 4), z + math.random(-4, 4)
    if not TheWorld.Map or TheWorld.Map:IsPassableAtPoint(px, 0, pz) then
        inst.components.locomotor:GoToPoint(Vector3(px, y, pz))
    end
end

function AIPlayerManager:ApplyAction(inst, action)
    if not alive(inst) or type(action) ~= "table" then return end
    local name = action.action or "wait"
    if name == "say" then say(inst, action.message)
    elseif name == "follow" then inst._ai_mode = "follow"; self:Follow(inst)
    elseif name == "wander" then inst._ai_mode = "autonomous"; self:Wander(inst)
    elseif name == "wait" then
        inst._ai_mode = "autonomous"
        if inst.components.locomotor then inst.components.locomotor:Stop() end
    elseif name == "attack" and available(inst) then
        if type(action.target) ~= "string" and type(action.target) ~= "number" then return end
        for _, target in ipairs(nearby(inst)) do
            if (target.prefab == action.target or target.GUID == tonumber(action.target))
                and target ~= inst and not target:HasTag("player") and target.components.combat then
                inst._ai_mode = "autonomous"
                inst.components.locomotor:PushAction(BufferedAction(inst, target, ACTIONS.ATTACK), true)
                break
            end
        end
    elseif available(inst) and Survival.Apply(inst, action) then
        inst._ai_mode = "autonomous"
    end
end

function AIPlayerManager:Think(inst)
    if not alive(inst) or inst._ai_busy or not find_human() then return end
    inst._ai_busy = true
    local observation = Survival.Observe(inst)
    local x, y, z = inst.Transform:GetWorldPosition()
    observation.position, observation.character = { x = x, y = y, z = z }, inst.prefab
    observation.phase = TheWorld.state and TheWorld.state.phase or "unknown"
    local finished, timeout = false, nil
    local function finish(content, err)
        if finished then return end
        finished = true
        if timeout then timeout:Cancel() end
        inst._ai_busy = false
        if not alive(inst) then return end
        if err then
            inst._ai_mode = "autonomous"
            print(string.format("[AI Players] AI %d request failed: %s", inst._ai_index, err))
            return
        end
        local ok, action = pcall(json.decode, content)
        if ok and type(action) == "table" then self:ApplyAction(inst, action)
        else print(string.format("[AI Players] AI %d returned invalid action JSON", inst._ai_index)) end
    end
    timeout = inst:DoTaskInTime(60, function() finish(nil, "model request timed out; using local survival") end)
    inst._ai_provider:Complete({ { role = "system", content = SYSTEM_PROMPT },
        { role = "user", content = json.encode(observation) } }, finish)
end

function AIPlayerManager:Start()
    if TheWorld.ismastershard == false then return end
    self.count = math.max(0, math.min(MAX_PLAYERS, math.floor(tonumber(safe_config(self, "ai_count", 0)) or 0)))
    self.keys = {}
    for index = 1, self.count do
        local key = safe_config(self, "ai_" .. index .. "_api_key", "")
        if type(key) == "string" and key ~= "" then self.keys[index] = key
        else print(string.format("[AI Players] AI %d skipped: API key is not configured", index)) end
    end
    print(string.format("[AI Players] Configured %d bots; waiting for human world entry", self.count))
    TheWorld:ListenForEvent("ms_playerjoined", function(_, player)
        if is_human(player) then TheWorld:DoTaskInTime(1, function() self:EnsureCompanions() end) end
    end)
    -- Covers enabling the mod on an existing save and a human already present at startup.
    TheWorld:DoTaskInTime(1, function() self:EnsureCompanions() end)
    TheWorld:DoPeriodicTask(2, function()
        for _, inst in ipairs(self.players) do
            if alive(inst) then
                local acted = Survival.Tick(inst)
                if not acted and available(inst) then
                    if inst._ai_mode == "follow" then self:Follow(inst)
                    elseif not inst._ai_next_wander or GetTime() >= inst._ai_next_wander then
                        inst._ai_next_wander = GetTime() + 8
                        self:Wander(inst)
                    end
                end
            end
        end
    end)
    local interval = math.max(15, tonumber(safe_config(self, "request_interval", 30)) or 30)
    TheWorld:DoPeriodicTask(interval, function()
        for _, inst in ipairs(self.players) do if alive(inst) then self:Think(inst) end end
    end)
end

return AIPlayerManager
