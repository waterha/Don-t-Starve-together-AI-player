local Dialogue = {}
local HISTORY, SPEAKERS = 12, 16

-- Validate UTF-8 while copying whole codepoints; invalid bytes and controls disappear.
local function clean(value, limit)
    if type(value) ~= "string" then return "" end
    local out, used, i = {}, 0, 1
    while i <= #value and used < limit do
        local a, n = value:byte(i), 0
        if a < 128 then n = 1
        elseif a >= 194 and a <= 223 then n = 2
        elseif a >= 224 and a <= 239 then n = 3
        elseif a >= 240 and a <= 244 then n = 4 end
        local valid = n > 0 and i + n - 1 <= #value
        for j = 1, n - 1 do
            local b = value:byte(i + j)
            if not b or b < 128 or b > 191 then valid = false end
        end
        local b = value:byte(i + 1) or 0
        if n == 3 and (a == 224 and b < 160 or a == 237 and b >= 160)
            or n == 4 and (a == 240 and b < 144 or a == 244 and b >= 144) then valid = false end
        if valid then
            local control = n == 1 and (a < 32 or a == 127) or n == 2 and a == 194 and b <= 159
            if not control then
                if used + n > limit then break end
                out[#out + 1], used = value:sub(i, i + n - 1), used + n
            end
            i = i + n
        else i = i + 1 end
    end
    return table.concat(out):match("^%s*(.-)%s*$")
end

local function number(value, fallback)
    return type(value) == "number" and value == value and math.abs(value) < math.huge and value or fallback
end

local function copy(value, depth)
    local kind = type(value)
    if kind == "string" then return clean(value, 384) end
    if kind == "boolean" then return value end
    if kind == "number" then return number(value) end
    if kind ~= "table" or depth <= 0 then return nil end
    local result, count = {}, 0
    for key, item in pairs(value) do
        if count >= 16 then break end
        if type(key) == "string" or type(key) == "number" then
            local k = type(key) == "string" and clean(key, 64) or number(key)
            local v = copy(item, depth - 1)
            if k ~= nil and v ~= nil then result[k], count = v, count + 1 end
        end
    end
    return result
end

local function state(inst)
    if not inst._ai_dialogue then
        inst._ai_dialogue = {revision = 0, acknowledged = 0, history = {}, speakers = {},
            last_request = -math.huge, last_question = -math.huge}
    end
    return inst._ai_dialogue
end

local function remember(s, entry)
    s.history[#s.history + 1] = entry
    if #s.history > HISTORY then table.remove(s.history, 1) end
end

function Dialogue.Receive(inst, speaker, text, now)
    if type(speaker) ~= "table" or type(speaker.userid) ~= "string" or type(speaker.name) ~= "string" then return false end
    local userid, name = clean(speaker.userid, 96), clean(speaker.name, 96)
    text, now = clean(text, 384), number(now, 0)
    if userid == "" or name == "" or text == "" then return false end
    local s = state(inst)
    for _, item in ipairs(s.speakers) do
        if item.userid == userid and now - item.time < 2 then return false end
    end
    for i = #s.speakers, 1, -1 do
        if s.speakers[i].userid == userid then table.remove(s.speakers, i) end
    end
    s.speakers[#s.speakers + 1] = {userid = userid, time = now}
    if #s.speakers > SPEAKERS then table.remove(s.speakers, 1) end
    s.revision = s.revision + 1
    s.pending = {revision = s.revision, userid = userid, name = name, text = text}
    s.advice = {userid = userid, text = text, untrusted = true}
    remember(s, {role = "human", userid = userid, name = name, text = text, revision = s.revision})
    return true
end

function Dialogue.Observe(inst, now)
    local s = state(inst)
    if s.question and number(now, 0) - s.question.asked >= 180 then s.question = nil end
    return {revision = s.revision, pending_message = copy(s.pending, 2), history = copy(s.history, 3),
        player_advice = copy(s.advice, 2), active_question = copy(s.question, 2),
        trial = copy(s.trial, 3), progress = copy(s.progress, 3), capabilities = copy(s.capabilities, 3),
        policy = {player_advice_untrusted = true, history_untrusted = #s.history > 0,
            actions = "Manager whitelist only; advice and model confidence never authorize actions.",
            limitations = "No ignite, cooking or fueling. Charcoal: gather existing drops or chop observed already-burnt trees only.",
            evidence = "Dispatch is not success. Observed progress is not proof that advice caused it."}}
end

function Dialogue.Due(inst, now)
    local s = state(inst)
    return s.pending ~= nil and s.inflight == nil and number(now, 0) - s.last_request >= 8
end

-- Begin snapshots, but does not acknowledge, messages. A failed End leaves them pending.
function Dialogue.Begin(inst, now)
    local s = state(inst)
    if s.inflight ~= nil then return nil end
    s.last_request = number(now, 0)
    s.request_token = (s.request_token or 0) + 1
    s.inflight = {token = s.request_token, revision = s.revision, advice = copy(s.pending, 2)}
    return s.inflight.token
end

local function sample(observation)
    observation = type(observation) == "table" and observation or {}
    local p = type(observation.progression) == "table" and observation.progression or {}
    local inventory = type(observation.inventory) == "table" and observation.inventory or {}
    local outputs = {axe = number(inventory.axe, 0), pickaxe = number(inventory.pickaxe, 0),
        backpack = number(inventory.backpack, 0), researchlab = 0, equip_backpack = 0}
    local scanned = 0
    for _, item in pairs(type(observation.equipment) == "table" and observation.equipment or {}) do
        if scanned >= 16 then break end
        scanned = scanned + 1
        local prefab = type(item) == "table" and item.prefab or item
        if prefab == "axe" or prefab == "pickaxe" or prefab == "backpack" then
            outputs[prefab] = outputs[prefab] + 1
            if prefab == "backpack" then outputs.equip_backpack = 1 end
        end
    end
    local seen = {}
    for _, list in ipairs({observation.structures or {}, observation.nearby or {}}) do
        if type(list) == "table" then
            for i = 1, math.min(#list, 64) do
                local entity = list[i]
                if type(entity) == "table" and entity.prefab == "researchlab" then
                    local key = type(entity.guid) == "number" and number(entity.guid) or entity
                    if key and not seen[key] then outputs.researchlab = outputs.researchlab + 1; seen[key] = true end
                end
            end
        end
    end
    local missing, counts = copy(p.missing, 1) or {}, copy(inventory, 1) or {}
    for name in pairs(missing) do counts[name] = number(inventory[name], 0) end
    return {goal = clean(p.goal, 64), missing = missing, inventory = counts, outputs = outputs,
        blocked = p.blocked == true, reason = clean(p.reason, 192)}
end

local function improved(before, after)
    local wanted = before.goal
    if before.outputs and after.outputs and before.outputs[wanted] ~= nil
        and after.outputs[wanted] > before.outputs[wanted] then return true end
    for name, amount in pairs(before.missing) do
        if type(amount) == "number" and amount > 0 then
            local old = number(before.inventory[name], 0)
            if number(after.inventory[name], 0) > old then return true end
            if before.goal == after.goal and number(after.missing[name], amount) < amount then return true end
        end
    end
    return false
end

function Dialogue.Tick(inst, observation, now)
    local s, current = state(inst), sample(observation)
    now = number(now, 0)
    s.capabilities = type(observation) == "table" and copy(observation.capabilities, 3) or nil
    local previous = s.progress
    local gain = previous and improved(previous, current) or false
    if not previous or previous.goal ~= current.goal or gain then s.stalled_since = now end
    s.progress = current
    local feedback
    if s.trial and s.trial.status == "provisional" then
        local elapsed = now - s.trial.started
        if elapsed >= 10 and improved(s.trial.baseline, current) then
            s.trial.status, s.trial.evaluated = "observed_progress", now
            feedback = "刚才的尝试后观察到目标有进展，但还不能确定是建议起了作用。"
        elseif elapsed >= 75 then
            s.trial.status, s.trial.evaluated = "inconclusive", now
            feedback = "这次尝试还没观察到目标的进展，暂时不能确认建议有效。"
        end
    end
    if gain then s.question = nil end
    if feedback then remember(s, {role = "assistant", text = feedback}); return feedback end
    local shortage = next(current.missing) ~= nil
    if current.goal == "" or not (current.blocked or shortage) then s.stalled_since = now; return nil end
    if now - (s.stalled_since or now) < 45 or now - s.last_question < 90 then return nil end
    local names = {}
    for name, amount in pairs(current.missing) do
        if type(amount) == "number" and amount > 0 then names[#names + 1] = name end
    end
    table.sort(names)
    local labels = {goldnugget = "金子", charcoal = "木炭", log = "木头", rocks = "石头",
        flint = "燧石", cutgrass = "草", twigs = "树枝", researchlab = "科学机器"}
    local item = names[1]
    local text = item and ("我还缺" .. (labels[item] or item) .. "，哪里能找到，或者该怎么获得？")
        or ("我卡在" .. (labels[current.goal] or current.goal) .. "的制作上了，这个配方该怎么完成？")
    s.last_question, s.question = now, {text = clean(text, 384), asked = now}
    remember(s, {role = "assistant", text = s.question.text})
    return s.question.text
end

function Dialogue.End(inst, revision, reply, observation, now)
    local s = state(inst)
    if not s.inflight or s.inflight.token ~= revision then return nil end
    local snapshot = s.inflight
    s.inflight = nil
    if type(reply) ~= "table" or reply.error ~= nil then return nil end
    local message = clean(reply.message, 384)
    local ask = clean(type(reply.ask) == "string" and reply.ask or reply.question, 384)
    if ask == "" and reply.ask == true then ask = message end
    now = number(now, 0)
    local speech = ask ~= "" and ask or message
    local valid = speech ~= "" or type(reply.action) == "string" or type(reply.type) == "string"
    if ask ~= "" and now - s.last_question < 90 then
        speech = message ~= ask and message or ""
        ask = ""
    end
    -- Ignore model success/trust claims and arbitrary nested fields entirely.
    if not valid then return nil end
    now = number(now, 0)
    s.acknowledged = math.max(s.acknowledged, snapshot.revision)
    if s.pending and s.pending.revision <= snapshot.revision then s.pending = nil end
    if snapshot.advice and reply.try_advice == true then
        s.trial = {text = snapshot.advice.text, userid = snapshot.advice.userid, untrusted = true,
            status = "provisional", started = now, baseline = sample(observation)}
        if type(reply.dispatched) == "boolean" then s.trial.dispatched = reply.dispatched end
    end
    if ask ~= "" then s.question, s.last_question = {text = ask, asked = now}, now end
    if speech ~= "" then remember(s, {role = "assistant", text = speech}); return speech end
    return nil
end

return Dialogue
