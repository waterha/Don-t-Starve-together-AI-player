local json = require("json")

local Roster = {}
local registered = false
local pending = "[]"
local MAX_BOTS = 5
local MAX_PAYLOAD = 4096
local DIRTY_EVENT = "ai_players_roster_dirty"
local VALID_STATUS = { selecting = true, alive = true, dead = true }

local function clean_name(value, index, fallback)
    if type(value) ~= "string" then
        return fallback or "Bot " .. index
    end
    local chars = {}
    -- Keep complete UTF-8 characters, dropping control bytes and excessive names.
    for char in value:gmatch("[\32-\126\194-\244][\128-\191]*") do
        if char ~= "\127" then
            chars[#chars + 1] = char
            if #chars == 48 then
                break
            end
        end
    end
    local name = table.concat(chars):match("^%s*(.-)%s*$")
    return name ~= "" and name or fallback or "Bot " .. index
end

Roster.CleanName = clean_name

local function sanitize(slots)
    local result, seen = {}, {}
    if type(slots) ~= "table" then
        return result
    end
    for _, slot in ipairs(slots) do
        if type(slot) == "table" then
            local index = slot.index
            if type(index) == "number" and index >= 1 and index <= MAX_BOTS
                and index == math.floor(index) and not seen[index]
                and VALID_STATUS[slot.status] then
                local character = type(slot.character) == "string" and slot.character or ""
                if #character > 128 or character:find("[^%w_%-]") then
                    character = ""
                end
                local record = {
                    index = index,
                    name = clean_name(slot.name, index),
                    status = slot.status,
                    character = character,
                }
                if type(slot.GUID) == "number" and slot.GUID > 0
                    and slot.GUID < 9007199254740992 and slot.GUID == math.floor(slot.GUID) then
                    record.GUID = slot.GUID
                end
                result[#result + 1] = record
                seen[index] = true
                if #result == MAX_BOTS then
                    break
                end
            end
        end
    end
    table.sort(result, function(a, b) return a.index < b.index end)
    return result
end

local function payload()
    local net = TheWorld ~= nil and TheWorld.net or nil
    return net ~= nil and net._ai_players_roster ~= nil and net._ai_players_roster:value() or ""
end

function Roster.GetSlots()
    local data = payload()
    if type(data) ~= "string" or #data == 0 or #data > MAX_PAYLOAD then
        return {}
    end
    local ok, slots = pcall(json.decode, data)
    return ok and sanitize(slots) or {}
end

-- Public records: {index=1..5, name=string, status="selecting"|"alive"|"dead",
-- character=prefab_name, GUID=optional_entity_guid}. No identity or config fields.
function Roster.Publish(slots)
    if TheWorld == nil or not TheWorld.ismastersim then
        return false
    end
    local ok, data = pcall(json.encode, sanitize(slots))
    if not ok or type(data) ~= "string" or #data > MAX_PAYLOAD then
        return false
    end
    pending = data
    local net = TheWorld.net
    if net ~= nil and net._ai_players_roster ~= nil and net._ai_players_roster:value() ~= data then
        net._ai_players_roster:set(data)
    end
    return true
end

local function attach_network(inst)
    if inst._ai_players_roster == nil then
        inst._ai_players_roster = net_string(inst.GUID, "ai_players.roster", DIRTY_EVENT)
    end
    -- World.net may not yet be assigned during prefab construction.
    inst:DoTaskInTime(0, function()
        if TheWorld ~= nil and TheWorld.ismastersim then
            inst._ai_players_roster:set(pending)
        end
    end)
end

local function configure_screen(screen)
    if screen._ai_roster_hooked then
        return
    end
    screen._ai_roster_hooked = true
    local Text = require("widgets/text")
    local Image = require("widgets/image")
    local native_init, native_update = screen.DoInit, screen.OnUpdate
    local last_payload

    local function update_backgrounds(list)
        local count = math.min(list.widgets_per_view, #list.items)
        screen.bgs = screen.bgs or {}
        while #screen.bgs > count do
            table.remove(screen.bgs):Kill()
        end
        for i = #screen.bgs + 1, count do
            local bg = list:AddChild(Image("images/scoreboard.xml", "row.tex"))
            bg:SetTint(1, 1, 1, i % 2 == 0 and .85 or .5)
            bg:SetPosition(-170, 165 - 65 * (i - 1))
            bg:MoveToBack()
            screen.bgs[i] = bg
        end
    end

    local function refresh()
        local list = screen.scroll_list
        if list == nil then
            return
        end
        if not list._ai_roster_hooked then
            list._ai_roster_hooked = true
            local native_row = list.updatefn
            list.updatefn = function(row, record, index)
                if row._ai_character ~= nil then
                    row._ai_character:Hide()
                end
                if record == nil or not record._ai_bot then
                    if row._ai_age_state ~= nil then
                        row.age:SetSize(row._ai_age_state.size)
                        if row._ai_age_state.shown then
                            row.age:Show()
                        else
                            row.age:Hide()
                        end
                        row._ai_age_state = nil
                    end
                    return native_row(row, record, index)
                end
                if row._ai_age_state == nil then
                    row._ai_age_state = { size = row.age:GetSize(), shown = row.age:IsVisible() }
                end
                row.age:SetSize(25)
                row:Show()
                row.userid, row.ishost, row.focus_forward = nil, false, nil
                row.displayName = "[AI] " .. record.name
                row.mute.image.inst:DisableMute()
                for _, key in ipairs({ "viewprofile", "mute", "kick", "ban", "useractions", "adminBadge", "perf", "profileFlair", "number", "highlight" }) do
                    if row[key] ~= nil then
                        row[key]:Hide()
                    end
                end
                row.name:SetTruncatedString(row.displayName, row.name._align.maxwidth, row.name._align.maxchars, true)
                local width = row.name:GetRegionSize()
                row.name:SetPosition(row.name._align.x + width * .5, 0, 0)
                row.name:SetColour(1, 1, 1, 1)
                row.age:SetString(record.status == "selecting" and "Selecting" or record.status == "dead" and "Dead" or "Alive")
                row.age:Show()
                row.characterBadge:Set(record.character, DEFAULT_PLAYER_COLOUR, false, 0)
                row.characterBadge:Show()
                if row._ai_character == nil then
                    row._ai_character = row:AddChild(Text(UIFONT, 25))
                    row._ai_character:SetPosition(175, 0, 0)
                end
                row._ai_character:SetTruncatedString(record.character, 230, 32, true)
                row._ai_character:Show()
            end
        end
        local combined = {}
        -- Copy the native data; never append to the engine's client table.
        for _, client in ipairs(list.items) do
            if not client._ai_bot then
                combined[#combined + 1] = client
            end
        end
        for _, slot in ipairs(Roster.GetSlots()) do
            slot._ai_bot = true
            combined[#combined + 1] = slot
        end
        list:SetList(combined)
        update_backgrounds(list)
        last_payload = payload()
    end

    screen.DoInit = function(self, ...)
        native_init(self, ...)
        refresh()
    end
    screen.OnUpdate = function(self, dt)
        native_update(self, dt)
        if last_payload ~= payload() then
            refresh()
        end
    end
end

local NAME_DIRTY_EVENT = "ai_players_name_dirty"

local function attach_player_name(inst)
    if inst._ai_players_name ~= nil then return end
    inst._ai_players_name = net_string(inst.GUID, "ai_players.display_name", NAME_DIRTY_EVENT)
    local function refresh_name()
        local name = inst._ai_players_name:value()
        if name ~= "" then inst.name = name end
    end
    inst:ListenForEvent(NAME_DIRTY_EVENT, refresh_name)
    inst:DoTaskInTime(0, refresh_name)
end

function Roster.SetName(inst, value, index)
    local name = clean_name(value, index, "AI " .. index)
    if TheWorld == nil or not TheWorld.ismastersim then return false end
    inst.name = name
    if inst._ai_players_name ~= nil then inst._ai_players_name:set(name) end
    if inst.components.named ~= nil then inst.components.named:SetName(name) end
    return true
end

function Roster.Register(add_prefab_post_init, add_class_post_construct, add_player_post_init)
    if registered then
        return
    end
    registered = true
    if add_player_post_init then add_player_post_init(attach_player_name) end
    add_prefab_post_init("forest_network", attach_network)
    add_prefab_post_init("cave_network", attach_network)
    add_class_post_construct("screens/playerstatusscreen", configure_screen)
end

return Roster
