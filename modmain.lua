local get_config = GetModConfigData

-- Network roster fields must be registered on clients and the server before world creation.
require("ai_players_roster").Register(AddPrefabPostInit, AddClassPostConstruct)

-- The world is created after modmain is loaded.
AddSimPostInit(function()
    if GLOBAL.TheWorld.ismastersim then
        local AIPlayerManager = require("ai_player_manager")
        AIPlayerManager.new(get_config):Start()
    end
end)

-- The manager and model requests are loaded only on the world server.
