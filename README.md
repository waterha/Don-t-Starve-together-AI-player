# 饥荒：联机版 AI 玩家

**简体中文** | [English](README.en.md)

这是一个由服务器控制的 AI 玩家模组，支持同时启用 0–5 个机器人。在新世界或已启用模组的旧存档中，真人进入后，机器人会先以 **[AI]** 条目出现在游戏内玩家列表，自行通过模型选择角色，再进入世界执行基础自主生存动作。每个 AI 都有独立的 API 地址、API Key 和模型名称，可以混用不同服务商，也可以重复使用同一个 Key。

这些是模组控制的机器人，玩家列表由模组扩展。它们不是独立的 Steam/WeGame 网络客户端，不占用经过身份认证的客户端席位，也不会作为连接出现在外部服务器浏览器中。

## 游戏内配置

1. 安装主模组。若需要在尚未启用服务器模组时，通过“已安装模组”菜单编辑配置，请将 `client_config_helper` 的内容复制到独立的同级目录 `mods/ai_players_config`，启用客户端模组 **AI Players Config**，然后重启一次游戏。配置助手必须是独立模组，不能只是主模组里的子目录。本地开发安装也可在游戏的 `mods/modsettings.lua` 中加入 `ForceEnableMod("ai_players_config")`；删除这一行即可取消自动加载。
2. 打开 **AI Players** 配置，将 **AI player count** 设为 0–5。界面会显示相同数量的配置组，每组包含 **AI N API URL**、**AI N API key** 和 **AI N Model**；数量为 0 时不显示服务商字段。
3. 分别填写每个 AI 的地址、Key 和模型。例如，AI 1 可以使用中转服务的地址、Key 和模型，AI 2 使用 `https://api.openai.com/v1`、自己的 OpenAI Key 和 `gpt-4o-mini`。接口须兼容 OpenAI Chat Completions。只有 Key 会遮挡显示，地址和模型保持可见。减少 AI 数量只会隐藏多余配置组，不会清除已填内容。
4. 地址或模型留空时，升级存档优先使用旧版共享配置；全新配置默认使用 `https://api.openai.com/v1` 和 `gpt-4o-mini`。每个 AI 显式填写的值始终优先，且不会成为其他 AI 的默认值。旧版共享地址、模型字段已隐藏。
5. 点击 **Apply**，通过游戏原生的主机配置机制保存。重新打开后会保留字段及组数；**Back** 放弃未保存的修改；**Reset** 恢复默认值，包括 AI 数量为 0、隐藏所有服务商字段。
6. 在运行世界服务器的电脑上启动 API 桥接程序。Windows 可双击 `tools/start_ai_bridge.cmd` 并保持窗口打开；需要 Python 3，无需额外依赖。也可运行 `python tools/ai_http_bridge.py`，Linux 使用 `python3`。桥接仅监听 `http://127.0.0.1:17893`，访问 `http://127.0.0.1:17893/health` 应返回 `{"ok":true}`。远程专用服务器必须在服务器本机启动桥接。
7. 在世界的“服务器模组”中启用 **AI Players**，创建或继续世界，然后用真人角色进入。打开游戏内玩家列表，各机器人先显示 **Selecting**，选角并在真人附近进入后显示所选角色和 **Alive**，死亡后显示 **Dead**。机器人默认独立处理食物、材料和照明需求，而不是跟随。仅启用配置助手不会启动机器人。旧存档只需在继续游戏前启用服务器模组，无需重新建档。

配置助手负责在前端初始化输入界面：未启用的服务器模组不会因为打开配置页而自动执行自己的前端入口。助手还会使用主机配置打开 AI Players 设置，避免在“已安装模组”中修改的内容被保存到独立的客户端配置。其他模组行为保持不变。世界仍须启用主模组才能生成机器人；专用服务器可直接使用下方配置示例，无需安装客户端助手。

## 反应速度与请求间隔

**Request interval** 是每个 AI 定时请求模型作出动作决策的间隔，单位为秒，可选 5、10、15、30、60，默认 30。五个活跃机器人在 30 秒间隔下，每分钟最多约 10 次定时请求；10 秒间隔约 30 次，5 秒间隔约 60 次。启动时每个机器人还会额外发送一次选角请求和一次初始动作请求。若上一次动作请求尚未完成，会跳过本次定时请求。默认间隔没有缩短，加快本地动作不需要增加 API 调用。

本地生存循环每 **0.25 秒**检查一次，独立于 HTTP 和模型请求，旧版为 2 秒。这减少的是调度等待，不会缩短动画、寻路或服务商响应时间。砍树、挖矿会在重新验证目标和工具后连续执行，不必每一下都请求模型。忙碌时收到的模型动作最多保留 10 秒，空闲后重新验证，生存需求优先。延迟返回的等待、闲逛指令不会打断已有缓冲动作。空闲探索重试间隔由 8 秒缩短到 2 秒，跟随更新最多每秒两次。尚未在实际游戏中测量帧耗时或端到端响应速度。

桥接会按字段报告无效配置：`invalid base_url`、`invalid api_key`、`invalid model` 或 `invalid messages`，不会回显提交的值。地址、Key 和模型首尾空白会被去除；Key 内部控制字符仍会被拒绝。反复出现校验错误表示请求失败，不只是响应慢，应先检查配置，再考虑缩短请求间隔。

## API Key 存储与安全

Key 在界面中遮挡显示，但以普通游戏配置字符串保存，本模组不会加密。不要把真实 Key 放进创意工坊上传内容、Git 提交、截图、共享存档或共享配置文件。

世界服务器将每次请求及 Key 发送给本机回环桥接；桥接仅通过 Authorization 请求头将 Key 转发到你配置的 API 地址，不记录请求正文或凭据。模组未添加向客户端发送 Key 的 RPC。输入框遮挡不等于配置存储具备保密能力。

## 专用服务器配置

1. 将主模组目录复制到服务器的 `mods` 目录。
2. 在服务器的 `modoverrides.lua` 中启用模组。
3. 将 `ai_count` 设为 `0`–`5`。
4. 为每个 AI 填写 `ai_N_api_base_url`、`ai_N_api_key` 和 `ai_N_model`。多个 AI 可以重复使用同一个 Key。
5. 每个地址都须兼容 OpenAI Chat Completions；不同 AI 可以使用不同的服务商和模型名称。
6. 进入世界前，在服务器本机启动 `python tools/ai_http_bridge.py`。

`modoverrides.lua` 示例：

```lua
return {
    ["ai_players"] = {
        enabled = true,
        configuration_options = {
            ai_count = 2,
            ai_1_api_base_url = "https://relay.example/v1",
            ai_1_api_key = "REPLACE_WITH_RELAY_SECRET",
            ai_1_model = "REPLACE_WITH_RELAY_MODEL_NAME",
            ai_2_api_base_url = "https://api.openai.com/v1",
            ai_2_api_key = "REPLACE_WITH_OPENAI_SECRET",
            ai_2_model = "gpt-4o-mini",
            request_interval = 30,
        },
    },
}
```

配置条目的键应使用实际本地模组文件夹名。发布到创意工坊后，改为 `workshop-` 加实际创意工坊 ID。

## 生命周期与当前能力

- 地表服务器将数量限制在 0–5，并在第一个存活真人进入后启动。新世界与启用模组后继续的旧存档使用同一启动流程。
- 每个配置了 Key 的槽位会先创建 **[AI] AI N** 玩家列表条目，状态为 **Selecting**。模型独立选择支持的基础角色，随后在真人附近的安全地面生成，状态变为 **Alive**。重复加入事件不会重复生成机器人；缺少 Key 的槽位会跳过。
- 选角失败、返回不支持的角色或超过 60 秒时，使用支持的默认角色并记录回退信息。如果真人已断开，等待真人返回后再进入。无需额外启动真实客户端或手动点击选角界面。
- 模型可观察生命、饥饿、理智、背包数量、装备、附近可用资源及 GUID、威胁、光照、时段和可制作的物品配方；可请求采集、进食、制作或装备物品、使用已有工具砍树或挖矿、闲逛、说话、等待、跟随，以及攻击非玩家目标。
- 本地四分之一秒生存循环会躲避迫近的攻击者、饥饿时吃适合且已持有的食物、收集食物和限量草枝，并使用真实材料制作或装备火把。已有移动、工作和忙碌状态会被保留。机器人没有免费物资、生命或无敌能力；模型请求失败时，本地生存行为仍会运行。
- 玩家列表支持正常滚动，显示状态与角色。机器人没有真实客户端的个人资料、静音、踢出、封禁或账号操作，不修改网络客户端表和已认证玩家数量。
- 机器人使用原生角色预制体，即使没有客户端身份，也会参与部分原生玩家玩法系统。目前仍是早期实现，不是完整玩家替代品。
- 死亡显示为 **Dead**，尚无自动复活。机器人及背包每次世界会话都会重新创建，不作为已认证玩家会话持久保存。机器人不会迁移到洞穴，列表快照目前也仅在地表分片内复制。
- 制作仅支持已知且无需地面放置的物品配方，例如火把、斧头、镐子。尚未实现放置式基地建设、高级寻路、季节或 Boss 策略，以及可靠的长期自主生存。
- 桥接接受服务商根地址、`/v1` 前缀或完整 `/chat/completions` 地址。根地址补齐 `/v1/chat/completions`，其他 API 前缀补齐 `/chat/completions`。桥接添加 Authorization，游戏原生 POST 使用已知支持的四参数 `QueryServer` 调用方式。

Lua 回归覆盖进入世界、独立选角、列表复制、本地动作和请求失败。隔离离线 WeGame 环境的原生引擎冒烟测试在 Lua 初始化前被 Rail 阻止，报错 `Please make sure the TGP is running!`，结果码为 2。实际游戏画面、远端复制和长期生存尚未验证。

## 测试

回归通过 `lupa` 使用 Lua 5.1。将 `DST_SCRIPTS_ZIP` 指向已安装游戏的 `data/databundles/scripts.zip`，即可在模拟引擎与控件环境下测试实际配置页和玩家列表 Lua。本仓库不包含游戏源码；资源不可用时，原生界面测试会明确跳过。HTTP 测试使用真实本地桥接连接测试服务端，不调用付费模型。

```powershell
python -m pip install lupa
$env:DST_SCRIPTS_ZIP = 'C:\path\to\DST\data\databundles\scripts.zip'
python -m unittest discover -s tests -p 'test_*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\test_static.ps1
```

## 日志

Windows 下可检查：

```text
Documents/Klei/DoNotStarveTogether/server_log.txt
Documents/Klei/DoNotStarveTogether/client_log.txt
```

不要提交包含真实 API Key 的 `modoverrides.lua`。

## 贡献约定

后续新增提交的标题和正文均使用中文，不改写已有提交历史。功能或配置方式改变时，请同步更新默认中文说明与[英文版](README.en.md)。
