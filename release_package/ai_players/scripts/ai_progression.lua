local Progression = {}

local SUPPLIES = {cutgrass = 4, twigs = 4}
local CAMP = {cutgrass = 4, twigs = 4, log = 6, rocks = 4, goldnugget = 1, flint = 2}
local PRODUCTS = {grass = "cutgrass", sapling = "twigs", sapling_moon = "twigs"}
local TREES = {evergreen = true, evergreen_sparse = true, deciduoustree = true,
    twiggytree = true, moon_tree = true}
local BOULDERS = {rock1 = true, rock2 = true, boulder = true, boulder_gold = true}
local GOLD_BOULDERS = {rock2 = true, boulder_gold = true}
local DEFAULTS = {axe = {twigs = 1, flint = 1}, pickaxe = {twigs = 2, flint = 2},
    researchlab = {log = 4, rocks = 4, goldnugget = 1}, backpack = {cutgrass = 4, twigs = 4}}

local function count(observation, name)
    local value = (observation.inventory or {})[name]
    return type(value) == "number" and math.max(0, value) or 0
end

local function equipped(observation, name)
    for _, item in pairs(observation.equipment or {}) do
        if item == name or type(item) == "table" and item.prefab == name then return true end
    end
    return false
end

local function has_tool(observation, name)
    if observation.tools ~= nil then return observation.tools[name] == true end
    return count(observation, name) > 0 or equipped(observation, name)
end

local function has_action(target, action)
    for _, value in ipairs(target.actions or {}) do
        if value == action then return true end
    end
    return false
end

local function state_for(inst)
    if type(inst._ai_progression) ~= "table" then
        inst._ai_progression = {goal = "supplies", reason = "secure light supplies", missing = {},
            blocked = false, built = {}, attempts = 0}
    end
    return inst._ai_progression
end

local function recipe_detail(observation, name)
    return (observation.recipes or observation.recipe_details or {})[name]
end

local function craftable(observation, name)
    for key, value in pairs(observation.craftable or {}) do
        if value == name or key == name and value == true then return true end
    end
    local detail = recipe_detail(observation, name)
    return type(detail) == "table" and (detail.known == true or detail.accessible == true)
        and (detail.ingredients_available == true or detail.buffered == true)
end

local function ingredients(observation, name)
    local detail = recipe_detail(observation, name)
    if type(detail) ~= "table" or type(detail.ingredients) ~= "table" then return DEFAULTS[name] or {} end
    local result = {}
    for _, ingredient in ipairs(detail.ingredients) do
        if type(ingredient.prefab) == "string" and type(ingredient.amount) == "number"
            and ingredient.amount > 0 and ingredient.amount < math.huge then
            result[ingredient.prefab] = (result[ingredient.prefab] or 0) + ingredient.amount
        end
    end
    return result
end

local function deficits(observation, wanted)
    local result = {}
    for name, amount in pairs(wanted) do
        local missing = amount - count(observation, name)
        if missing > 0 then result[name] = missing end
    end
    return result
end

local function remember_science(inst, observation, state)
    local known_guid = state.station and state.station.guid or inst._ai_camp and inst._ai_camp.guid
    if known_guid and Ents ~= nil then
        local station = Ents[known_guid]
        if not station or not station:IsValid() or station.prefab ~= "researchlab" then
            state.built.researchlab, state.station, inst._ai_camp = nil, nil, nil
        end
    end
    for _, target in ipairs(observation.structures or {}) do
        if type(target) == "table" and target.prefab == "researchlab" then
            state.built.researchlab = true
            state.station = {guid = target.guid, prefab = target.prefab}
        end
    end
    for _, target in ipairs(observation.nearby or {}) do
        if target.prefab == "researchlab" then state.built.researchlab = true end
    end
    local camp = inst._ai_camp
    if type(camp) == "table" and camp.prefab == "researchlab" then
        state.built.researchlab = true
        state.station = {guid = camp.guid, prefab = camp.prefab}
    end
    -- Only native build records or observed structures establish completion, never dispatch.
    for name, built in pairs(observation.built or {}) do
        if name == "researchlab" and built == true then state.built.researchlab = true end
    end
end

local function choose_goal(inst, observation)
    local state = state_for(inst)
    remember_science(inst, observation, state)
    local goal, reason, missing, recipe
    local supplies = deficits(observation, SUPPLIES)
    if next(supplies) ~= nil then
        goal, reason, missing = "supplies", "secure four grass and four twigs for light", supplies
    elseif state.built.researchlab and not equipped(observation, "backpack") then
        if count(observation, "backpack") > 0 then
            goal, reason, missing = "equip_backpack", "equip the actually observed backpack", {}
        else
            goal, reason, recipe = "backpack", "prototype a backpack at the observed science machine", "backpack"
        end
    elseif state.built.researchlab then
        goal, reason, missing = "maintain", "maintain finite camp reserves, then explore", deficits(observation, CAMP)
    elseif type(recipe_detail(observation, "researchlab")) == "table"
        and recipe_detail(observation, "researchlab").buffered == true then
        goal, reason, missing, recipe = "researchlab", "place the natively buffered science machine", {}, "researchlab"
    elseif not has_tool(observation, "axe") and count(observation, "log") < 6 then
        goal, reason, recipe = "axe", "obtain a real axe before chopping logs", "axe"
    elseif count(observation, "log") < 6 then
        goal, reason, missing = "logs", "collect six logs for early camp and research", deficits(observation, {log = 6})
    elseif not has_tool(observation, "pickaxe")
        and (count(observation, "rocks") < 4 or count(observation, "goldnugget") < 1) then
        goal, reason, recipe = "pickaxe", "obtain a real pickaxe before mining", "pickaxe"
    elseif count(observation, "rocks") < 4 or count(observation, "goldnugget") < 1 then
        goal, reason, missing = "minerals", "collect four rocks and one gold for science", deficits(observation, {rocks = 4, goldnugget = 1})
    else
        goal, reason, recipe = "researchlab", "build a science machine using its observed recipe", "researchlab"
    end
    missing = missing or deficits(observation, ingredients(observation, recipe))
    if (goal == "maintain" or goal == "researchlab") and missing.log and not has_tool(observation, "axe") then
        goal, reason, recipe = "axe", "replace the axe needed for camp logs", "axe"
        missing = deficits(observation, ingredients(observation, recipe))
    elseif (goal == "maintain" or goal == "researchlab")
        and (missing.rocks or missing.goldnugget or missing.flint) and not has_tool(observation, "pickaxe") then
        goal, reason, recipe = "pickaxe", "replace the pickaxe needed for camp minerals", "pickaxe"
        missing = deficits(observation, ingredients(observation, recipe))
    end
    if state.goal ~= goal then state.blocked, state.attempts = false, 0 end
    state.goal, state.reason, state.missing, state.recipe = goal, reason, missing, recipe
    return state
end

local function gather_target(observation, missing)
    local best, distance
    for _, target in ipairs(observation.nearby or {}) do
        local product = target.product or PRODUCTS[target.prefab] or target.prefab
        if missing[product] and (has_action(target, "pick") or has_action(target, "pickup")) then
            local d = type(target.distance) == "number" and target.distance or math.huge
            if best == nil or d < distance then best, distance = target, d end
        end
    end
    return best
end

local function targeted(action, target, item)
    if target.guid == nil and type(target.prefab) ~= "string" then return nil end
    return {action = action, target_guid = target.guid, target = target.guid or target.prefab, item = item}
end

local function select_action(observation, state)
    if state.goal == "equip_backpack" then return {action = "equip", item = "backpack"} end
    if state.goal == "backpack" then
        for _, structure in ipairs(observation.structures or {}) do
            if structure.prefab == "researchlab" and type(structure.distance) == "number" and structure.distance > 3 then
                return targeted("move", structure)
            end
        end
        if not craftable(observation, "backpack") and state.station and state.station.guid then
            local detail = recipe_detail(observation, "backpack")
            if type(detail) ~= "table" or not (detail.known or detail.accessible) then
                return targeted("move", state.station)
            end
        end
    end
    local target = gather_target(observation, state.missing)
    if target then return targeted("gather", target) end
    if state.recipe and next(state.missing) == nil then
        if craftable(observation, state.recipe) then
            return {action = state.recipe == "researchlab" and "build" or "craft", recipe = state.recipe}
        end
        state.blocked = true
        state.reason = "recipe unavailable: " .. state.recipe
        return {action = "explore"}
    end
    if state.missing.log and has_tool(observation, "axe") then
        for _, tree in ipairs(observation.nearby or {}) do
            if TREES[tree.prefab] and has_action(tree, "chop") then return targeted("chop", tree, "axe") end
        end
    end
    if (state.missing.rocks or state.missing.goldnugget or state.missing.flint)
        and has_tool(observation, "pickaxe") then
        for _, rock in ipairs(observation.nearby or {}) do
            if BOULDERS[rock.prefab] and has_action(rock, "mine")
                and (not state.missing.goldnugget or GOLD_BOULDERS[rock.prefab]) then
                return targeted("mine", rock, "pickaxe")
            end
        end
    end
    state.blocked = next(state.missing) ~= nil
    if state.blocked then state.reason = "needed resources are not available nearby" end
    return {action = "explore"}
end

local function copy_fields(value)
    if type(value) ~= "table" then return value end
    local result = {}
    for key, item in pairs(value) do
        if type(item) == "string" or type(item) == "number" or type(item) == "boolean" then result[key] = item end
    end
    return result
end

function Progression.Observe(inst, observation)
    local state = choose_goal(inst, type(observation) == "table" and observation or {})
    return {goal = state.goal, reason = state.reason, missing = copy_fields(state.missing),
        last_action = copy_fields(state.last_action), blocked = state.blocked and true or false}
end

function Progression.Record(inst, action, dispatched)
    local state = state_for(inst)
    action = copy_fields(action)
    state.last_action = type(action) == "table" and {action = action.action or action.type,
        target_guid = action.target_guid, target = action.target, recipe = action.recipe,
        item = action.item, dispatched = dispatched == true} or nil
    if dispatched ~= true then state.blocked = true end
end

local function fingerprint(observation, state, action)
    local parts = {state.goal, action.action, tostring(action.target_guid or action.target or action.recipe or "")}
    local names = {}
    for name in pairs(state.missing) do names[#names + 1] = name end
    table.sort(names)
    for _, name in ipairs(names) do parts[#parts + 1] = name .. ":" .. tostring(count(observation, name)) end
    if action.action == "chop" or action.action == "mine" then
        for _, target in ipairs(observation.nearby or {}) do
            if target.guid == action.target_guid and type(target.work_left) == "number" then
                parts[#parts + 1] = "work:" .. tostring(target.work_left)
            end
        end
    end
    if action.action == "move" then
        for _, structure in ipairs(observation.structures or {}) do
            if structure.guid == action.target_guid then parts[#parts + 1] = tostring(structure.distance) end
        end
    end
    return table.concat(parts, "|")
end

function Progression.Tick(inst, observation, apply_fn)
    if inst == nil or type(apply_fn) ~= "function" then return false end
    observation = type(observation) == "table" and observation or {}
    local state = choose_goal(inst, observation)
    if observation.busy then return false end
    state.blocked = false
    local action = select_action(observation, state)
    local signature = fingerprint(observation, state, action)
    if signature ~= state.signature then state.signature, state.attempts = signature, 0 end
    if action.action ~= "explore" and state.attempts >= 3 then
        state.blocked, state.reason = true, "target made no observed progress; explore another route"
        action = {action = "explore"}
        state.attempts = 0
    end
    local dispatched = apply_fn(action) == true
    if action.action ~= "explore" then state.attempts = state.attempts + 1 end
    Progression.Record(inst, action, dispatched)
    if not dispatched then state.reason = "native action rejected; goal remains incomplete" end
    return dispatched
end

return Progression
