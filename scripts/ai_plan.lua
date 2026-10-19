-- Short model plans. Dispatch is only an attempt; later observations prove completion.
local Plan = {}
local ALLOWED = {gather=true, eat=true, craft=true, build=true, equip=true,
    chop=true, mine=true, explore=true, move=true, wait=true, follow=true, say=true}
local FIELDS = {action=true, target=true, target_guid=true, item=true, recipe=true, x=true, z=true}
local function finite(n) return type(n) == "number" and n == n and n > -math.huge and n < math.huge end
local function primitive(v) return finite(v) or type(v) == "string" and #v <= 128 end

function Plan.New(result, now)
    if type(result) ~= "table" or not finite(now) then return nil, "invalid plan" end
    local source = result.plan
    local legacy = source == nil
    if legacy then source = {result} end
    if type(source) ~= "table" then return nil, "invalid plan" end
    local count = 0
    for k in pairs(source) do
        if not finite(k) or k % 1 ~= 0 or k < 1 or k > 5 then return nil, "invalid plan" end
        count = count + 1
    end
    if count < 1 or count > 5 then return nil, "invalid plan" end
    local steps = {}
    for i = 1, count do
        local raw, step = source[i], {}
        if type(raw) ~= "table" then return nil, "invalid step" end
        for k, v in pairs(raw) do
            if FIELDS[k] then
                if not primitive(v) then return nil, "invalid field" end
                step[k] = v
            elseif not legacy then return nil, "invalid field" end
        end
        if type(step.action) ~= "string" or not ALLOWED[step.action] then return nil, "unsupported action" end
        if (step.action == "wait" or step.action == "follow" or step.action == "say") and i ~= count then
            return nil, "invalid terminal step"
        end
        if (step.x ~= nil or step.z ~= nil) and (not finite(step.x) or not finite(step.z)) then
            return nil, "invalid destination"
        end
        steps[i] = step
    end
    return {steps=steps, index=1, started=now, status="running", hold_seconds=5}
end

local CANCEL_REASONS = {cancelled=true, safety=true, superseded=true, reset=true}
local function finish(inst, plan, status, reason)
    plan.status, plan.reason = status, reason
    if inst then
        inst._ai_survival_work = nil
        inst._ai_pending_action = nil
    end
    return status, reason
end
function Plan.Cancel(inst, plan, reason)
    if type(plan) ~= "table" then return "failed", "cancelled" end
    return finish(inst, plan, "failed", CANCEL_REASONS[reason] and reason or "cancelled")
end
local function alive(inst)
    return inst and inst.IsValid and inst:IsValid() and inst.components
        and not (inst.HasTag and inst:HasTag("playerghost"))
        and not (inst.components.health and inst.components.health:IsDead())
end
local function busy(inst)
    return inst.sg and inst.sg:HasStateTag("busy")
        or inst.GetBufferedAction and inst:GetBufferedAction() ~= nil
        or inst.components.locomotor and inst.components.locomotor.bufferedaction ~= nil
end
local function inventory_count(o, name) return (o.inventory or {})[name] or 0 end
local function has_action(target, name)
    for _, action in ipairs(target.actions or {}) do
        if action == name or name == "gather" and (action == "pick" or action == "pickup") then return true end
    end
    return false
end
local function find_target(o, step)
    local requested = step.target_guid or step.target
    if requested == nil then return nil end
    for _, target in ipairs(o.nearby or {}) do
        if (step.target_guid ~= nil and target.guid == step.target_guid)
            or (step.target_guid == nil and (target.guid == requested or tostring(target.guid) == requested
                or target.prefab == requested)) then return target end
    end
end
local function matching_guid(o, guid)
    for _, target in ipairs(o.nearby or {}) do if target.guid == guid then return target end end
end
local function owned(inst, name)
    local inventory = inst.components.inventory
    if inventory == nil or inventory.FindItems == nil then return nil end
    for _, item in ipairs(inventory:FindItems(function(item) return item:IsValid() end)) do
        if item.prefab == name or item.GUID == name then return item end
    end
end
local function usable(inst, item, work)
    if not item or not item:IsValid() or not item.components then return false end
    local c = item.components
    if not c.equippable or c.equippable:IsRestricted(inst)
        or c.fueled and c.fueled:IsEmpty() or c.finiteuses and c.finiteuses:GetUses() <= 0 then return false end
    if work then return c.tool and c.tool:CanDoAction(work) or false end
    return true
end
local function find_tool(inst, step)
    local inventory = inst.components.inventory
    local work = ACTIONS and ACTIONS[step.action == "chop" and "CHOP" or "MINE"]
    if inventory == nil or inventory.FindItems == nil or work == nil then return nil end
    for _, item in ipairs(inventory:FindItems(function(item) return item:IsValid() end)) do
        if (step.item == nil or item.prefab == step.item or item.GUID == step.item) and usable(inst, item, work) then return item end
    end
end
local function structure_target(inst, o, step)
    local requested = step.target_guid or step.target
    for _, target in ipairs(o.structures or {}) do
        if target.prefab == "researchlab" and (target.guid == requested or tostring(target.guid) == requested
            or target.prefab == requested) then return target end
    end
    local station = inst._ai_progression and inst._ai_progression.station
    local camp = inst._ai_camp
    if station and station.guid and Ents and Ents[station.guid] and Ents[station.guid]:IsValid() then
        local e = Ents[station.guid]
        if e.prefab == "researchlab" and e.Transform then
            local x, _, z = e.Transform:GetWorldPosition()
            return {guid=e.GUID, prefab=e.prefab, x=x, z=z}
        end
    end
    if camp and camp.prefab == "researchlab" then return camp end
end
local function prepare(inst, o, step)
    local s = {action={}, counts={}, structures={}}
    for k, v in pairs(step) do s.action[k] = v end
    for k, v in pairs(o.inventory or {}) do s.counts[k] = v end
    for _, v in ipairs(o.structures or {}) do s.structures[v.guid] = true end
    s.hunger = o.hunger and o.hunger.current
    local name = step.action
    if name == "gather" or name == "chop" or name == "mine" then
        local target = find_target(o, step)
        if not target or target.guid == nil or not has_action(target, name) then return nil, "target unavailable" end
        s.guid, s.action.target_guid = target.guid, target.guid
        if name == "gather" then
            s.product = target.product or target.prefab
            if type(s.product) ~= "string" then return nil, "target unavailable" end
        else
            if not finite(target.work_left) or target.work_left <= 0 then return nil, "target unavailable" end
            s.work_left, s.tool = target.work_left, find_tool(inst, step)
            if not s.tool then return nil, "tool unavailable" end
            s.action.item = s.tool.GUID or s.tool.prefab
        end
    elseif name == "craft" or name == "build" then
        s.product = step.recipe or step.item or step.target
        local detail = (o.recipes or {})[s.product]
        if not detail or not detail.accessible or not (detail.ingredients_available or name == "build" and detail.buffered) then
            return nil, "recipe unavailable"
        end
        local recipe = GetValidRecipe and GetValidRecipe(s.product)
        s.product = recipe and recipe.product or s.product
    elseif name == "eat" or name == "equip" then
        s.product = step.item or step.target
        s.item = owned(inst, s.product)
        if not s.item or inventory_count(o, s.item.prefab) <= 0 then return nil, "item unavailable" end
        s.product = s.item.prefab
        if name == "equip" and not usable(inst, s.item) then return nil, "item unavailable" end
        if name == "eat" and not finite(s.hunger) then return nil, "item unavailable" end
    elseif name == "move" then
        local target = structure_target(inst, o, step)
        if not target or not finite(target.x) or not finite(target.z) then return nil, "target unavailable" end
        s.destination, s.guid = {x=target.x, z=target.z}, target.guid
        if target.guid then s.action.target_guid, s.action.target = target.guid, nil end
    end
    return s
end
local function at_destination(inst, destination)
    if not destination or not inst.Transform then return false end
    local x, _, z = inst.Transform:GetWorldPosition()
    return (x-destination.x)^2 + (z-destination.z)^2 <= 9
end
local function evidence(inst, o, s, name)
    if name == "gather" or name == "craft" then
        if inventory_count(o, s.product) > (s.counts[s.product] or 0) then return true end
        if name == "gather" and not matching_guid(o, s.guid) then
            local target = Ents and Ents[s.guid]
            if not target or not target:IsValid() then return false, "target unavailable" end
        end
        return false
    elseif name == "build" then
        for _, target in ipairs(o.structures or {}) do
            if target.prefab == s.product and target.guid ~= nil and not s.structures[target.guid] then return true end
        end
    elseif name == "eat" then
        return inventory_count(o, s.product) < (s.counts[s.product] or 0)
            and o.hunger and finite(o.hunger.current) and o.hunger.current > s.hunger
    elseif name == "equip" then
        local inventory = inst.components.inventory
        return usable(inst, s.item) and inventory
            and inventory:GetEquippedItem(s.item.components.equippable.equipslot) == s.item
    elseif name == "chop" or name == "mine" then
        local target = matching_guid(o, s.guid)
        local entity = Ents and Ents[s.guid]
        -- Finished resources can disappear from Observe's actionable nearby list.
        local workable = entity and entity:IsValid() and entity.components and entity.components.workable
        local left = target and target.work_left or workable and workable.GetWorkLeft and workable:GetWorkLeft()
        if finite(left) and left < s.work_left then s.progress = true; s.work_left = left end
        if finite(left) and left <= 0 and s.progress then return true end
        if not target and (not entity or not entity:IsValid()) then
            if s.progress then return true end
            return false, "target unavailable"
        end
        local work = ACTIONS and ACTIONS[name == "chop" and "CHOP" or "MINE"]
        if not usable(inst, s.tool, work) or owned(inst, s.tool.GUID or s.tool.prefab) ~= s.tool then
            return false, "tool unavailable"
        end
    elseif name == "explore" or name == "move" then
        if name == "move" and s.guid and Ents and (not Ents[s.guid] or not Ents[s.guid]:IsValid()) then
            return false, "target unavailable"
        end
        return at_destination(inst, s.destination)
    end
    return false
end

-- apply_fn(inst, action) must report dispatch with true. observe_fn(inst) returns
-- Survival.Observe shape. Manager owns urgent safety and continued work/follow.
function Plan.Tick(inst, plan, now, apply_fn, observe_fn)
    if type(plan) ~= "table" then return "failed", "invalid plan" end
    if plan.status ~= "running" then return plan.status, plan.reason end
    if not finite(now) or now < plan.started then return finish(inst, plan, "failed", "invalid time") end
    if not alive(inst) then return finish(inst, plan, "failed", "actor unavailable") end
    if now - plan.started >= 180 then return finish(inst, plan, "failed", "plan timeout") end
    local step = plan.steps[plan.index]
    plan.step_started = plan.step_started or now
    local limit = (step.action == "chop" or step.action == "mine") and 60 or 45
    if now - plan.step_started >= limit then return finish(inst, plan, "failed", "step timeout") end
    local s = plan.snapshot
    if s then
        if now - s.dispatched < .25 then return "running", "awaiting evidence" end
        local done, reason
        if step.action == "wait" or step.action == "follow" or step.action == "say" then
            done = now >= s.hold_until
        else
            local ok, o = pcall(observe_fn, inst)
            if not ok or type(o) ~= "table" then return finish(inst, plan, "failed", "observation unavailable") end
            done, reason = evidence(inst, o, s, step.action)
        end
        if reason then return finish(inst, plan, "failed", reason) end
        if done then
            plan.index, plan.snapshot, plan.step_started = plan.index + 1, nil, nil
            inst._ai_survival_work = nil
            if plan.index > #plan.steps then return finish(inst, plan, "completed", "plan completed") end
            return "running", "step completed"
        end
        return "running", "awaiting evidence"
    end
    -- Never let manager ApplyAction queue an old action behind native work.
    if busy(inst) or not inst.components.locomotor then return "running", "actor busy" end
    local ok, o = pcall(observe_fn, inst)
    if not ok or type(o) ~= "table" then return finish(inst, plan, "failed", "observation unavailable") end
    local reason
    s, reason = prepare(inst, o, step)
    if not s then return finish(inst, plan, "failed", reason) end
    s.dispatched = now
    if step.action == "wait" or step.action == "follow" or step.action == "say" then
        local hold = finite(plan.hold_seconds) and math.max(0, plan.hold_seconds) or 5
        s.hold_until = now + (step.action == "say" and 0 or hold)
    end
    -- The snapshot exists before a synchronous equip/craft callback can change state.
    plan.snapshot = s
    if step.action ~= "say" then
        local applied, dispatched = pcall(apply_fn, inst, s.action)
        if not applied or dispatched ~= true then return finish(inst, plan, "failed", "action rejected") end
    end
    if step.action == "explore" then
        local destination = inst._ai_exploration and inst._ai_exploration.destination
        if not destination or not finite(destination.x) or not finite(destination.z) then
            return finish(inst, plan, "failed", "destination unavailable")
        end
        s.destination = {x=destination.x, z=destination.z}
    end
    return "running", "awaiting evidence"
end
return Plan
