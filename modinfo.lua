name = "AI Players"
description = "Adds up to five server-controlled AI companions backed by an OpenAI-compatible model API."
author = "waterha"
version = "0.1.0"
forumthread = ""
api_version = 10
dst_compatible = true
all_clients_require_mod = true
client_only_mod = false

configuration_options = {
    {
        name = "ai_count",
        label = "AI player count",
        hover = "Number of AI companions to spawn (0-5).",
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
        name = "ai_1_api_key",
        label = "AI 1 API key",
        hover = "Server-side key. Do not publish this configuration or Workshop item.",
        options = { { description = "Not configured", data = "" } },
        default = "",
    },
    {
        name = "ai_2_api_key",
        label = "AI 2 API key",
        hover = "Server-side key. Do not publish this configuration or Workshop item.",
        options = { { description = "Not configured", data = "" } },
        default = "",
    },
    {
        name = "ai_3_api_key",
        label = "AI 3 API key",
        hover = "Server-side key. Do not publish this configuration or Workshop item.",
        options = { { description = "Not configured", data = "" } },
        default = "",
    },
    {
        name = "ai_4_api_key",
        label = "AI 4 API key",
        hover = "Server-side key. Do not publish this configuration or Workshop item.",
        options = { { description = "Not configured", data = "" } },
        default = "",
    },
    {
        name = "ai_5_api_key",
        label = "AI 5 API key",
        hover = "Server-side key. Do not publish this configuration or Workshop item.",
        options = { { description = "Not configured", data = "" } },
        default = "",
    },
    {
        name = "api_base_url",
        label = "API base URL",
        hover = "OpenAI-compatible API base URL.",
        options = { { description = "OpenAI", data = "https://api.openai.com/v1" } },
        default = "https://api.openai.com/v1",
    },
    {
        name = "model",
        label = "Model",
        hover = "Model name accepted by the configured API.",
        options = { { description = "gpt-4o-mini", data = "gpt-4o-mini" } },
        default = "gpt-4o-mini",
    },
    {
        name = "request_interval",
        label = "Request interval",
        hover = "Seconds between model requests per AI.",
        options = {
            { description = "15 seconds", data = 15 },
            { description = "30 seconds", data = 30 },
            { description = "60 seconds", data = 60 },
        },
        default = 30,
    },
}
