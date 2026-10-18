local json = require("json")

local Provider = {}
Provider.__index = Provider

function Provider.new(base_url, model, api_key)
    return setmetatable({
        base_url = (base_url or "https://api.openai.com/v1"):gsub("/$", ""),
        model = model or "gpt-4o-mini",
        api_key = api_key or "",
    }, Provider)
end

function Provider:IsConfigured()
    return self.api_key ~= nil and self.api_key ~= ""
end

local function escape_header_value(value)
    return tostring(value):gsub("[\r\n]", "")
end

function Provider:Complete(messages, callback)
    if not self:IsConfigured() then
        callback(nil, "missing API key")
        return
    end

    local payload = json.encode({
        model = self.model,
        messages = messages,
        temperature = 0.2,
        max_tokens = 160,
        response_format = { type = "json_object" },
    })

    local headers = {
        ["Content-Type"] = "application/json",
        ["Authorization"] = "Bearer " .. escape_header_value(self.api_key),
    }
    local url = self.base_url .. "/chat/completions"

    local ok, err = pcall(function()
        TheSim:QueryServer(url, function(response, success)
            if not success or response == nil then
                callback(nil, "HTTP request failed")
                return
            end

            local decoded_ok, decoded = pcall(json.decode, response)
            if not decoded_ok or decoded == nil then
                callback(nil, "invalid JSON response")
                return
            end

            local content = decoded.choices
                and decoded.choices[1]
                and decoded.choices[1].message
                and decoded.choices[1].message.content
            if content == nil then
                callback(nil, "API response has no message content")
                return
            end
            callback(content, nil)
        end, "POST", payload, headers)
    end)

    if not ok then
        callback(nil, tostring(err))
    end
end

return Provider
