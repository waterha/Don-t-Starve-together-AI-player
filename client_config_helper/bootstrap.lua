local G = GLOBAL
if G.TheNet and G.TheNet:IsDedicated() then
    return
end
local targets = {}
local config_ui = G.package.loaded["ai_players_config_ui"]

for _, name in G.ipairs(G.KnownModIndex:GetModNames()) do
    local info = G.KnownModIndex:GetModInfo(name)
    if info and info.ai_players_config_ui then
        targets[name] = true
        if not config_ui then
            local loader = G.kleiloadlua(G.MODS_ROOT .. name .. "/scripts/ai_players_config_ui.lua")
            if G.type(loader) == "function" then
                config_ui = loader()
                G.package.loaded["ai_players_config_ui"] = config_ui
            end
        end
    end
end

if config_ui then
    -- Installed-mod settings normally use the CLIENT configuration. This server
    -- mod needs the host configuration so values entered here reach the world.
    local screen_class = G.require("screens/redux/modconfigurationscreen")
    if not screen_class.ai_players_host_settings then
        screen_class.ai_players_host_settings = true
        local constructor = screen_class._ctor
        screen_class._ctor = function(self, name, client_config, ...)
            local info = G.KnownModIndex:GetModInfo(name)
            if info and info.ai_players_config_ui then
                client_config = false
            end
            constructor(self, name, client_config, ...)
        end
    end
    for name in G.pairs(targets) do
        config_ui.Register(name, AddClassPostConstruct)
    end
    G.print("[AI Players Config] Editable host configuration ready")
else
    G.print("[AI Players Config] AI Players server mod not found")
end
