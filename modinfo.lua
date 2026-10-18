name = "AI Players"
description = "Adds up to five AI bots with independent model providers, character selection and basic autonomous survival."
author = "waterha"
version = "0.2.5"
ai_players_config_ui = true
forumthread = ""
api_version = 10
dst_compatible = true
all_clients_require_mod = true
client_only_mod = false

configuration_options = {
    {
        name = "ai_count",
        label = "AI player count",
        hover = "Number of AI bots to list, select characters and enter after a human joins (0-5).",
        options = {
            { description = "0", data = 0 },
            { description = "1", data = 1 },
            { description = "2", data = 2 },
            { description = "3", data = 3 },
            { description = "4", data = 4 },
            { description = "5", data = 5 },
        },
        default = 0,
    },
    {
        name = "ai_1_api_base_url", label = "AI 1 API URL",
        hover = "AI 1's OpenAI-compatible URL. Blank uses your previous shared URL, or https://api.openai.com/v1.",
        options = { { description = "Default / previous URL", data = "" } }, default = "",
    },
    {
        name = "ai_1_api_key", label = "AI 1 API key",
        hover = "AI 1's key for its own URL. Stored in host settings; do not share saved configuration.",
        options = { { description = "Not configured", data = "" } }, default = "",
    },
    {
        name = "ai_1_model", label = "AI 1 Model",
        hover = "Model name accepted by AI 1's provider. Blank uses your previous shared model, or gpt-4o-mini.",
        options = { { description = "Default / previous model", data = "" } }, default = "",
    },
    {
        name = "ai_2_api_base_url", label = "AI 2 API URL",
        hover = "AI 2's OpenAI-compatible URL. Blank uses your previous shared URL, or https://api.openai.com/v1.",
        options = { { description = "Default / previous URL", data = "" } }, default = "",
    },
    {
        name = "ai_2_api_key", label = "AI 2 API key",
        hover = "AI 2's key for its own URL. Stored in host settings; do not share saved configuration.",
        options = { { description = "Not configured", data = "" } }, default = "",
    },
    {
        name = "ai_2_model", label = "AI 2 Model",
        hover = "Model name accepted by AI 2's provider. Blank uses your previous shared model, or gpt-4o-mini.",
        options = { { description = "Default / previous model", data = "" } }, default = "",
    },
    {
        name = "ai_3_api_base_url", label = "AI 3 API URL",
        hover = "AI 3's OpenAI-compatible URL. Blank uses your previous shared URL, or https://api.openai.com/v1.",
        options = { { description = "Default / previous URL", data = "" } }, default = "",
    },
    {
        name = "ai_3_api_key", label = "AI 3 API key",
        hover = "AI 3's key for its own URL. Stored in host settings; do not share saved configuration.",
        options = { { description = "Not configured", data = "" } }, default = "",
    },
    {
        name = "ai_3_model", label = "AI 3 Model",
        hover = "Model name accepted by AI 3's provider. Blank uses your previous shared model, or gpt-4o-mini.",
        options = { { description = "Default / previous model", data = "" } }, default = "",
    },
    {
        name = "ai_4_api_base_url", label = "AI 4 API URL",
        hover = "AI 4's OpenAI-compatible URL. Blank uses your previous shared URL, or https://api.openai.com/v1.",
        options = { { description = "Default / previous URL", data = "" } }, default = "",
    },
    {
        name = "ai_4_api_key", label = "AI 4 API key",
        hover = "AI 4's key for its own URL. Stored in host settings; do not share saved configuration.",
        options = { { description = "Not configured", data = "" } }, default = "",
    },
    {
        name = "ai_4_model", label = "AI 4 Model",
        hover = "Model name accepted by AI 4's provider. Blank uses your previous shared model, or gpt-4o-mini.",
        options = { { description = "Default / previous model", data = "" } }, default = "",
    },
    {
        name = "ai_5_api_base_url", label = "AI 5 API URL",
        hover = "AI 5's OpenAI-compatible URL. Blank uses your previous shared URL, or https://api.openai.com/v1.",
        options = { { description = "Default / previous URL", data = "" } }, default = "",
    },
    {
        name = "ai_5_api_key", label = "AI 5 API key",
        hover = "AI 5's key for its own URL. Stored in host settings; do not share saved configuration.",
        options = { { description = "Not configured", data = "" } }, default = "",
    },
    {
        name = "ai_5_model", label = "AI 5 Model",
        hover = "Model name accepted by AI 5's provider. Blank uses your previous shared model, or gpt-4o-mini.",
        options = { { description = "Default / previous model", data = "" } }, default = "",
    },
    {
        name = "request_interval", label = "Request interval",
        hover = "Seconds between model requests per AI; 5/10 seconds use more API calls. Local actions update every 0.25 seconds independently. In-flight requests skip a tick.",
        options = {
            { description = "5 seconds", data = 5 },
            { description = "10 seconds", data = 10 },
            { description = "15 seconds", data = 15 },
            { description = "30 seconds", data = 30 },
            { description = "60 seconds", data = 60 },
        },
        default = 30,
    },
    -- Hidden by the configuration UI. Retained so old saved settings remain readable.
    {
        name = "api_base_url", label = "Legacy API URL",
        options = { { description = "OpenAI", data = "https://api.openai.com/v1" } },
        default = "https://api.openai.com/v1",
    },
    {
        name = "model", label = "Legacy model",
        options = { { description = "gpt-4o-mini", data = "gpt-4o-mini" } },
        default = "gpt-4o-mini",
    },
}
