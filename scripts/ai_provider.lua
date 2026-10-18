local json = require("json")

local Provider = {}
Provider.__index = Provider
local BRIDGE_URL = "http://127.0.0.1:17893/complete"

function Provider.new(base_url, model, api_key)
    return setmetatable({
        base_url = (base_url or "https://api.openai.com/v1"):gsub("/+$", ""),
        model = model or "gpt-4o-mini",
        api_key = api_key or "",
    }, Provider)
end

function Provider:IsConfigured()
    return type(self.api_key) == "string" and self.api_key ~= ""
end

function Provider:Complete(messages, callback, max_tokens)
    if not self:IsConfigured() then
        callback(nil, "missing API key")
        return
    end
    local finished = false
    local function finish(content, err)
        if not finished then
            finished = true
            callback(content, err)
        end
    end
    -- Native QueryServer's supported POST form has no headers table. The local
    -- bridge adds Authorization for the configured upstream API, never a third party.
    local payload = json.encode({
        base_url = self.base_url,
        api_key = self.api_key,
        model = self.model,
        messages = messages,
        temperature = 0.2,
        max_tokens = max_tokens == 320 and 320 or 160,
        response_format = { type = "json_object" },
    })
    local ok = pcall(function()
        TheSim:QueryServer(BRIDGE_URL, function(response, success, status)
            local decoded_ok, decoded = pcall(json.decode, response or "")
            if decoded_ok and type(decoded) == "table" and decoded.error then
                local message = type(decoded.error) == "table" and decoded.error.message or decoded.error
                finish(nil, type(message) == "string" and message or "model API request failed")
                return
            end
            if not success or (status ~= nil and status ~= 200) then
                finish(nil, "local API bridge unavailable; start tools/start_ai_bridge.cmd on the server computer")
                return
            end
            if not decoded_ok or type(decoded) ~= "table" then
                finish(nil, "invalid JSON response")
                return
            end
            local content = decoded.choices and decoded.choices[1]
                and decoded.choices[1].message and decoded.choices[1].message.content
            if type(content) ~= "string" then
                finish(nil, "API response has no message content")
                return
            end
            finish(content, nil)
        end, "POST", payload)
    end)
    if not ok then
        finish(nil, "local API bridge request could not start")
    end
end

return Provider
