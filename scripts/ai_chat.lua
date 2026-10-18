-- Transport seam: native human chat remains authoritative; bots use system messages.
local Chat = {}
local registered_manager
local installed_wrapper

local function pack(...)
    return { n = select("#", ...), ... }
end

-- Remove controls and truncate at UTF-8 character boundaries without engine extensions.
function Chat.Clean(text, limit)
    if type(text) ~= "string" then return "" end
    text = text:gsub("[%z\1-\31\127]", " ")
    limit = math.max(0, math.floor(tonumber(limit) or 160))
    local parts, count, offset = {}, 0, 1
    while offset <= #text and count < limit do
        local b = text:byte(offset)
        local width = b < 128 and 1 or b >= 194 and b <= 223 and 2
            or b >= 224 and b <= 239 and 3 or b >= 240 and b <= 244 and 4 or nil
        if not width or offset + width - 1 > #text then break end
        local valid = true
        for i = 1, width - 1 do
            local c = text:byte(offset + i)
            if c < 128 or c > 191 then valid = false; break end
        end
        local second = text:byte(offset + 1)
        if width == 3 and ((b == 224 and second < 160) or (b == 237 and second >= 160))
            or width == 4 and ((b == 240 and second < 144) or (b == 244 and second >= 144)) then valid = false end
        if not valid then break end
        count = count + 1
        parts[count] = text:sub(offset, offset + width - 1)
        offset = offset + width
    end
    return table.concat(parts):match("^%s*(.-)%s*$")
end

local function observe(guid, userid, name, prefab, message, colour, whisper, isemote)
    if not registered_manager or not TheWorld or not TheWorld.ismastersim
        or TheWorld.ismastershard == false or whisper or isemote
        or type(userid) ~= "string" or userid == "" or type(message) ~= "string" then return end
    local limit = MAX_CHAT_INPUT_LENGTH or 150
    -- Native early returns do not carry a rejection result: repeat its length guard.
    if message:utf8len() > limit then return end
    registered_manager:OnChat(userid, name, message, whisper)
end

function Chat.Register(manager)
    registered_manager = manager
    if installed_wrapper then return true end
    if type(Networking_Say) ~= "function" then return false end
    local native = Networking_Say
    installed_wrapper = function(...)
        -- Preserve native errors and all return positions, including trailing nils.
        local results = pack(native(...))
        pcall(observe, ...)
        return unpack(results, 1, results.n)
    end
    Networking_Say = installed_wrapper
    return true
end

function Chat.Say(inst, text)
    if not TheWorld or not TheWorld.ismastersim or TheWorld.ismastershard == false then return false end
    if not TheNet or type(TheNet.SystemMessage) ~= "function" then return false end
    text = Chat.Clean(text, 160)
    if text == "" then return false end
    local name = Chat.Clean(inst and inst.name, 48)
    if name == "" then name = "AI" end
    TheNet:SystemMessage("[AI " .. name .. "] " .. text)
    return true
end

return Chat
