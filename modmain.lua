if TheWorld.ismastersim then
    local AIPlayerManager = require("ai_player_manager")
    AddSimPostInit(function()
        AIPlayerManager.new():Start()
    end)
end

-- API keys and model requests are intentionally never loaded on clients.
