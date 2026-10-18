local Survival = {}
local RADIUS = 12

local function valid(inst)
    return inst ~= nil and inst:IsValid() and inst.components ~= nil
        and not inst:HasTag("playerghost")
end

local function busy(inst)
    return (inst.sg ~= nil and inst.sg:HasStateTag("busy"))
        or (inst.GetBufferedAction ~= nil and inst:GetBufferedAction() ~= nil)
        or (inst.components.locomotor ~= nil and inst.components.locomotor.bufferedaction ~= nil)
end

local function items(inst)
    local inventory = inst.components.inventory
    return inventory ~= nil and inventory:FindItems(function(item) return item:IsValid() end) or {}
end

local function count_inventory(inst)
    local counts = {}
    for _, item in ipairs(items(inst)) do
        local stack = item.components.stackable
        local name = item.prefab
        if name ~= nil then counts[name] = (counts[name] or 0) + (stack ~= nil and stack:StackSize() or 1) end
    end
    return counts
end

local function nearby(inst)
    local x, y, z = inst.Transform:GetWorldPosition()
    local entities = TheSim:FindEntities(x, y, z, RADIUS, nil, {"INLIMBO", "FX", "DECOR", "playerghost"})
    local result = {}
    for _, target in ipairs(entities) do
        if target ~= inst and valid(target) and target.Transform ~= nil then result[#result + 1] = target end
    end
    table.sort(result, function(a, b) return inst:GetDistanceSqToInst(a) < inst:GetDistanceSqToInst(b) end)
    return result
end

local function safe_resource(target)
    local c = target.components
    return not target:HasTag("fire") and not target:HasTag("hostile") and not target:HasTag("player")
        and not (c.burnable ~= nil and c.burnable:IsBurning())
        and not (c.projectile ~= nil and c.projectile:IsThrown())
end

local function gather_action(inst, target)
    if not safe_resource(target) then return nil end
    local c, inventory = target.components, inst.components.inventory
    if inventory == nil then return nil end
    if c.pickable ~= nil and c.pickable:CanBePicked() then
        if inventory:IsFull() then return nil end
        return ACTIONS.PICK
    end
    if c.inventoryitem ~= nil and c.inventoryitem.canbepickedup and c.inventoryitem.owner == nil
        and inventory:CanAcceptCount(target, 1) > 0 then
        return ACTIONS.PICKUP
    end
end

local function usable_equipment(inst, item)
    local c = item.components
    return c.equippable ~= nil and not c.equippable:IsRestricted(inst)
        and not (c.fueled ~= nil and c.fueled:IsEmpty())
        and not (c.finiteuses ~= nil and c.finiteuses:GetUses() <= 0)
end

local function edible(inst, item)
    local eater, food = inst.components.eater, item.components.edible
    return eater ~= nil and food ~= nil and eater:CanEat(item) and eater:PrefersToEat(item)
        and food:GetHunger(inst) > 0 and food:GetHealth(inst) >= 0 and food:GetSanity(inst) >= 0
end

local function find_item(inst, name, predicate)
    for _, item in ipairs(items(inst)) do
        if (name == nil or item.prefab == name or item.GUID == name)
            and (predicate == nil or predicate(inst, item)) then return item end
    end
end

local function push(inst, target, action, item, point)
    local locomotor = inst.components.locomotor
    if locomotor == nil or action == nil then return false end
    -- Native PushAction has no success return; this reports dispatch, not completion.
    locomotor:PushAction(BufferedAction(inst, target, action, item, point), true)
    return true
end

local RECIPES = {"torch", "axe", "pickaxe", "campfire", "firepit", "researchlab", "backpack"}
local BUILDINGS = {campfire = true, firepit = true, researchlab = true}

local function accessible(builder, recipe)
    if builder:KnowsRecipe(recipe) then return true end
    return builder.CanLearn ~= nil and builder:CanLearn(recipe.name)
        and CanPrototypeRecipe ~= nil
        and CanPrototypeRecipe(recipe.level, builder.accessible_tech_trees or {}) or false
end

local function crafting_allowed(inst, builder)
    local inventory = inst.components.inventory
    return builder ~= nil and not builder.freebuildmode and inventory ~= nil
        and inventory:IsOpenedBy(inst)
end

local function light(inst)
    local phase = TheWorld.state ~= nil and TheWorld.state.phase or "unknown"
    local watcher = inst.LightWatcher
    local value = watcher ~= nil and watcher:GetLightValue() or nil
    local hand = inst.components.inventory ~= nil and inst.components.inventory:GetEquippedItem(EQUIPSLOTS.HANDS) or nil
    local in_light
    if watcher ~= nil and watcher.IsInLight ~= nil then in_light = watcher:IsInLight()
    else in_light = value ~= nil and value > .075
        or value == nil and (phase == "day" or phase == "dusk") end
    return {phase = phase, value = value, in_light = in_light,
        torch_equipped = hand ~= nil and hand.prefab == "torch" and usable_equipment(inst, hand) or false}
end

local function needs_torch(inst)
    local illumination = light(inst)
    return not illumination.in_light and not illumination.torch_equipped
end

local function craft(inst, name)
    if name == "torch" and (not needs_torch(inst) or find_item(inst, "torch", usable_equipment)) then return false end
    local builder = inst.components.builder
    local recipe = type(name) == "string" and GetValidRecipe(name) or nil
    if not crafting_allowed(inst, builder) or recipe == nil or recipe.placer ~= nil
        or not accessible(builder, recipe) or not builder:HasIngredients(recipe) then return false end
    -- The native menu path unlocks prototypes on success and returns no value.
    builder:MakeRecipeFromMenu(recipe)
    return busy(inst) and true or false
end

local function build(inst, name)
    if not BUILDINGS[name] then return false end
    local builder, map = inst.components.builder, TheWorld.Map
    local recipe = GetValidRecipe(name)
    if not crafting_allowed(inst, builder) or recipe == nil or recipe.placer == nil
        or not accessible(builder, recipe) or map == nil
        or (not builder:IsBuildBuffered(name) and not builder:HasIngredients(recipe)) then return false end
    local x, y, z = inst.Transform:GetWorldPosition()
    for _, radius in ipairs({2, 4, 6}) do
        for step = 0, 7 do
            local angle = step * math.pi / 4
            local point = Vector3(x + math.cos(angle) * radius, y, z + math.sin(angle) * radius)
            if map:IsPassableAtPoint(point.x, 0, point.z)
                and not map:IsGroundTargetBlocked(point)
                and map:CanDeployRecipeAtPoint(point, recipe, 0, inst) then
                if not builder:IsBuildBuffered(name) then builder:BufferBuild(name) end
                if not builder:IsBuildBuffered(name) then return false end
                builder:MakeRecipeAtPoint(recipe, point, 0)
                return busy(inst) and true or false
            end
        end
    end
    return false
end

local function equip(inst, item)
    if item ~= nil and item.prefab == "torch" and not needs_torch(inst) then return false end
    local inventory = inst.components.inventory
    if inventory == nil or item == nil or not usable_equipment(inst, item) then return false end
    if inventory:GetEquippedItem(item.components.equippable.equipslot) == item then return false end
    return inventory:Equip(item) == true
end

local function status(component, current, maximum)
    if component == nil then return {} end
    return {current = component[current], max = component[maximum], percent = component:GetPercent()}
end

local function threat(inst, target)
    local combat = target.components.combat
    return combat ~= nil and combat.target == inst
        and not (target.components.health ~= nil and target.components.health:IsDead())
end

-- Keep entity references only on the bot; observations remain serializable.
local function work_intent(inst)
    local intent = inst._ai_survival_work
    if intent == nil then return nil end
    local target, tool, work = intent.target, intent.tool, intent.action
    local workable = valid(target) and target.components.workable or nil
    local inventory = inst.components.inventory
    if workable == nil or target.Transform == nil
        or inst:GetDistanceSqToInst(target) > RADIUS * RADIUS
        or not safe_resource(target) or not workable:CanBeWorked()
        or workable:GetWorkAction() ~= work or not valid(tool)
        or not usable_equipment(inst, tool) or tool.components.tool == nil
        or not tool.components.tool:CanDoAction(work)
        or find_item(inst, nil, function(_, item) return item == tool end) == nil
        or inventory:GetEquippedItem(tool.components.equippable.equipslot) ~= tool then
        inst._ai_survival_work = nil
        return nil
    end
    return intent
end

function Survival.Observe(inst)
    if not valid(inst) then return {} end
    local observation = {
        health = status(inst.components.health, "currenthealth", "maxhealth"),
        hunger = status(inst.components.hunger, "current", "max"),
        sanity = status(inst.components.sanity, "current", "max"),
        inventory = count_inventory(inst), equipment = {}, nearby = {}, threats = {},
        light = light(inst), busy = busy(inst) and true or false, craftable = {},
        recipes = {}, structures = {}, tools = {}, food_count = 0,
    }
    for _, item in ipairs(items(inst)) do
        if usable_equipment(inst, item) then observation.tools[item.prefab] = true end
        if edible(inst, item) then
            local stack = item.components.stackable
            observation.food_count = observation.food_count + (stack ~= nil and stack:StackSize() or 1)
        end
    end
    local inventory = inst.components.inventory
    for slot, item in pairs(inventory ~= nil and inventory.equipslots or {}) do
        observation.equipment[tostring(slot)] = item.prefab
    end
    for _, target in ipairs(nearby(inst)) do
        local descriptor = {guid = target.GUID, prefab = target.prefab,
            distance = math.sqrt(inst:GetDistanceSqToInst(target)), actions = {}}
        if BUILDINGS[target.prefab] and safe_resource(target) then
            local tx, ty, tz = target.Transform:GetWorldPosition()
            observation.structures[#observation.structures + 1] = {guid = target.GUID, prefab = target.prefab,
                x = tx, y = ty, z = tz, distance = descriptor.distance}
        end
        local action = gather_action(inst, target)
        if action ~= nil then descriptor.actions[#descriptor.actions + 1] = action == ACTIONS.PICK and "pick" or "pickup" end
        local pickable = target.components.pickable
        if pickable and type(pickable.product) == "string" then descriptor.product = pickable.product end
        local workable = target.components.workable
        if workable and workable.GetWorkLeft then descriptor.work_left = workable:GetWorkLeft() end
        if safe_resource(target) and workable ~= nil and workable:CanBeWorked() then
            local work = workable:GetWorkAction()
            if work == ACTIONS.CHOP or work == ACTIONS.MINE then
                descriptor.actions[#descriptor.actions + 1] = work == ACTIONS.CHOP and "chop" or "mine"
            end
        end
        if #descriptor.actions > 0 and #observation.nearby < 24 then observation.nearby[#observation.nearby + 1] = descriptor end
        if threat(inst, target) then observation.threats[#observation.threats + 1] = descriptor end
    end
    local builder = inst.components.builder
    if builder ~= nil and not builder.freebuildmode then
        for _, name in ipairs(RECIPES) do
            local recipe = GetValidRecipe(name)
            if recipe ~= nil then
                local detail = {known = builder:KnowsRecipe(recipe), accessible = accessible(builder, recipe),
                    ingredients_available = builder:HasIngredients(recipe),
                    buffered = builder.IsBuildBuffered ~= nil and builder:IsBuildBuffered(name) or false,
                    ingredients = {}}
                for _, ingredient in ipairs(recipe.ingredients or {}) do
                    detail.ingredients[#detail.ingredients + 1] = {prefab = ingredient.type, amount = ingredient.amount}
                end
                observation.recipes[name] = detail
                if detail.accessible and (detail.ingredients_available or detail.buffered) then
                    observation.craftable[#observation.craftable + 1] = name
                end
            end
        end
    end
    return observation
end

local function explicit_override(inst, dispatched)
    if dispatched then inst._ai_survival_work = nil end
    return dispatched
end

function Survival.Apply(inst, action)
    if not valid(inst) or busy(inst) or type(action) ~= "table" then return false end
    if inst.components.health ~= nil and inst.components.health:IsDead() then return false end
    local name = action.action or action.type
    if name == "build" then
        return explicit_override(inst, build(inst, action.recipe or action.item or action.target))
    end
    if name == "craft" then
        return explicit_override(inst, craft(inst, action.recipe or action.item or action.target))
    end
    if name == "equip" then
        return explicit_override(inst, equip(inst, find_item(inst, action.item or action.target, usable_equipment)))
    end
    if name == "eat" then
        local item = find_item(inst, action.item or action.target, edible)
        return explicit_override(inst, item ~= nil and push(inst, nil, ACTIONS.EAT, item) or false)
    end
    if name ~= "gather" and name ~= "pick" and name ~= "pickup" and name ~= "chop" and name ~= "mine" then return false end
    local requested = action.target_guid or action.target
    if type(requested) ~= "string" and type(requested) ~= "number" then return false end
    for _, target in ipairs(nearby(inst)) do
        if target.GUID == requested or target.prefab == requested or target.name == requested then
            if name == "gather" or name == "pick" or name == "pickup" then
                local game_action = gather_action(inst, target)
                if game_action ~= nil and (name == "gather" or (name == "pick" and game_action == ACTIONS.PICK)
                    or (name == "pickup" and game_action == ACTIONS.PICKUP)) then
                    return explicit_override(inst, push(inst, target, game_action))
                end
            else
                local work = name == "chop" and ACTIONS.CHOP or ACTIONS.MINE
                local workable = target.components.workable
                if safe_resource(target) and workable ~= nil and workable:CanBeWorked() and workable:GetWorkAction() == work then
                    local tool = find_item(inst, action.item, function(actor, item)
                        return usable_equipment(actor, item) and item.components.tool ~= nil and item.components.tool:CanDoAction(work)
                    end)
                    if tool ~= nil then
                        local inventory = inst.components.inventory
                        if inventory:GetEquippedItem(tool.components.equippable.equipslot) ~= tool and not equip(inst, tool) then return false end
                        if push(inst, target, work, tool) then
                            inst._ai_survival_work = {target = target, tool = tool, action = work}
                            return true
                        end
                        return false
                    end
                end
            end
        end
    end
    return false
end

local function gather_for(inst, entities, wanted)
    for _, target in ipairs(entities) do
        local pickable = target.components.pickable
        local product = pickable ~= nil and pickable.product or target.prefab
        if wanted(product, target) then
            local action = gather_action(inst, target)
            if action ~= nil then return push(inst, target, action) end
        end
    end
    return false
end

function Survival.CanDevelop(inst)
    if not valid(inst) or busy(inst) then return false end
    local illumination = light(inst)
    if not illumination.in_light and not illumination.torch_equipped then return false end
    local hunger = inst.components.hunger
    if hunger and hunger:GetPercent() < .1 then return false end
    for _, target in ipairs(nearby(inst)) do
        if threat(inst, target) and inst:GetDistanceSqToInst(target) < 36 then return false end
    end
    return true
end

function Survival.Tick(inst, skip_work)
    if not valid(inst) or busy(inst) or inst.components.locomotor == nil then return false end
    if inst.components.health ~= nil and inst.components.health:IsDead() then
        inst._ai_survival_work = nil
        return false
    end
    work_intent(inst)
    local entities = nearby(inst)
    for _, target in ipairs(entities) do
        if threat(inst, target) and inst:GetDistanceSqToInst(target) < 36 then
            inst._ai_survival_work = nil
            local x, y, z = inst.Transform:GetWorldPosition()
            local tx, _, tz = target.Transform:GetWorldPosition()
            local dx, dz = x - tx, z - tz
            local distance = math.sqrt(dx * dx + dz * dz)
            if distance < .01 then dx, dz, distance = 1, 0, 1 end
            -- Try both lateral routes if the direct escape points into water.
            for _, offset in ipairs({0, .8, -.8}) do
                local px = x + (dx / distance - dz / distance * offset) * 6
                local pz = z + (dz / distance + dx / distance * offset) * 6
                if TheWorld.Map ~= nil and TheWorld.Map:IsPassableAtPoint(px, 0, pz)
                    and not TheWorld.Map:IsGroundTargetBlocked(Vector3(px, 0, pz)) then
                    return push(inst, nil, ACTIONS.WALKTO, nil, Vector3(px, y, pz))
                end
            end
            return false
        end
    end
    local illumination = light(inst)
    local function prepare_light()
        if illumination.torch_equipped then return false end
        local torch = find_item(inst, "torch", usable_equipment)
        if torch ~= nil then return equip(inst, torch) end
        return craft(inst, "torch")
    end
    if not illumination.in_light then
        inst._ai_survival_work = nil
        if prepare_light() then return true end
    end
    local hunger = inst.components.hunger
    if hunger ~= nil and hunger:GetPercent() < .6 then
        local food = find_item(inst, nil, edible)
        if food ~= nil then
            inst._ai_survival_work = nil
            return push(inst, nil, ACTIONS.EAT, food)
        end
    end
    local counts = count_inventory(inst)
    if (counts.cutgrass or 0) < 4 or (counts.twigs or 0) < 4 then
        if gather_for(inst, entities, function(product)
            return (product == "cutgrass" and (counts.cutgrass or 0) < 4)
                or (product == "twigs" and (counts.twigs or 0) < 4)
        end) then return true end
    end
    if not illumination.in_light and not illumination.torch_equipped then return false end
    local food_count = 0
    for _, item in ipairs(items(inst)) do
        if edible(inst, item) then food_count = food_count + (item.components.stackable ~= nil and item.components.stackable:StackSize() or 1) end
    end
    local stored_plants = (counts.berries or 0) + (counts.berries_juicy or 0) + (counts.carrot or 0)
    if math.max(food_count, stored_plants) < 6 then
        if gather_for(inst, entities, function(product, target)
            return (target.components.edible ~= nil and edible(inst, target))
                or product == "berries" or product == "berries_juicy" or product == "carrot"
        end) then return true end
    end
    local intent = not skip_work and work_intent(inst) or nil
    if intent ~= nil then
        if push(inst, intent.target, intent.action, intent.tool) then return true end
        inst._ai_survival_work = nil
    end
    return false
end

return Survival
