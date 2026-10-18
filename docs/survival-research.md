# DST AI 生存与发展研究

核验日期：2026-10-18。范围：默认陆地开局、普通角色独立生存至基础营地；不包含完整战斗、洞穴、海洋或所有角色技能树。本文只记录机制摘要和 AI 策略，不复制原生完整代码。

## 资料与可信度

- **主要证据：本机已安装版本的原生脚本**。归档绝对路径：`E:\WeGameApps\rail_apps\饥荒：联机版(2000004)\data\databundles\scripts.zip`。下文 `[N: ...]` 均表示此归档内的相对路径及原始行号。配方和 builder 关键行还与仓库既有 `local_reference/native_recipes.lua`、`local_reference/native_components_builder.lua` 交叉核对。
- [Klei 官方游戏页](https://www.klei.com/games/dont-starve-together) 与 [Klei 发布的 Steam 商店页](https://store.steampowered.com/app/322330/Dont_Starve_Together/) 已直接访问。商店定位明确包含战斗、耕作、建造、探索，不是无限采集模拟；它们不提供下列具体配方/API 的完整技术说明。
- [Klei 官方论坛 DST 入口](https://kleiforums.com/forums/forum/73-dont-starve-together/) 已访问，确认开发日志、更新和模组工具讨论入口。论坛中的普通玩家发言不是 Klei 官方机制规范，本文不将其当作已证实配方来源。旧 `forums.kleientertainment.com` 地址会跨域跳转到 `kleiforums.com`。
- **次级资料**：[社区 Wiki 的科学机器页](https://dontstarve.wiki.gg/wiki/Science_Machine) 已访问，仅用于交叉理解“靠近原型站、首次制作后记住配方”。该页同时展示单机和 DST 版本，不能直接把所有配方列表搬给 DST；本文的数量和 API 均以本机原生脚本为准。
- 检索限制：调用过 `web_search`，返回缺少 `DEEPSEEK_API_KEY`，因此未能完成关键词网页搜索；没有配置密钥、安装工具或修改游戏。随后用 `web_fetch` 直接读取上述官方网址与明确标记的社区资料。不能声称做了完整官方新手指南检索。

## 核心结论：采集必须服务于可完成目标

**建议的控制结构，不是游戏硬编码规则**：每次决策先处理致命风险，然后推进一个明确里程碑；只有下一目标的材料有缺口时才采集。保留正在执行的动作，观察实际成功事件、库存和建筑状态之后再切换阶段。不要按“附近能采什么”无限循环。

建议阶段：

1. `secure_light_and_food`：有角色能吃的食物、有照明或至少保留一根火把所需材料。紧急危险可打断任何发展阶段。
2. `make_tools`：持有可用斧头和镐；有角色起始专用工具时以实际工具能力替代，不重复造同类工具。
3. `find_gold`：在可达区域探索或回访已发现的含金矿石，取得科学机器材料，不把普通矿石等同于金矿。
4. `place_science`：选安全、可达的陆地位置，预制并放置一台科学机器，记录位置并确认实体真实存在。
5. `prototype_essentials`：走到机器有效范围内，原型背包、绳索、长矛、木甲，按库存和风险调整次序。
6. `establish_base`：固定营地、可补燃料的照明、稳定食物路线和基础防护；再选择二本、烹饪锅与季节准备。

每阶段应有 `goal / missing_materials / target / started_at / progress / failure_reason`。例如科学机器目标完成条件应是“附近发现自己可使用的 researchlab 或已确认放置成功”，不是“发出 build 动作”。多 AI 可共享营地设施，不能每个都无条件建一台。阶段名称、共享规则和超时数值是实现建议。

## 精确开局配方

所有数量为未折扣、普通角色的原生配方；角色技能可能覆盖。运行时应读取 `AllRecipes`/builder 材料规则，而非把此表当成所有世界的最终真值。[N: `scripts/recipes.lua:382-515`; `scripts/components/builder.lua:500-515`]

| 产物 / prefab | 材料 | 初始科技 | 原生位置 |
| --- | --- | --- | --- |
| 斧头 `axe` | 树枝 1 + 燧石 1 | `TECH.NONE` | `scripts/recipes.lua:393` |
| 镐 `pickaxe` | 树枝 2 + 燧石 2 | `TECH.NONE` | `scripts/recipes.lua:395` |
| 火把 `torch` | 草 2 + 树枝 2 | `TECH.NONE` | `scripts/recipes.lua:425` |
| 营火 `campfire` | 草 3 + 木头 2 | `TECH.NONE` | `scripts/recipes.lua:426` |
| 石头营火 `firepit` | 木头 2 + 石头 12 | `TECH.NONE` | `scripts/recipes.lua:427` |
| 科学机器 `researchlab` | 金块 1 + 木头 4 + 石头 4 | `TECH.NONE` | `scripts/recipes.lua:382` |
| 背包 `backpack` | 草 4 + 树枝 4 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:515` |
| 绳索 `rope` | 草 3 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:457` |
| 长矛 `spear` | 树枝 2 + 绳索 1 + 燧石 1 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:478` |
| 木甲 `armorwood` | 木头 8 + 绳索 2 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:497` |
| 木板 `boards` | 木头 4 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:459` |
| 石砖 `cutstone` | 石头 3 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:460` |
| 电子元件 `transistor` | 金块 2 + 石砖 1 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:462` |
| 炼金引擎 `researchlab2` | 木板 4 + 石砖 2 + 电子元件 2 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:383` |
| 烹饪锅 `cookpot` | 石砖 3 + 木炭 6 + 树枝 6 | `TECH.SCIENCE_ONE` | `scripts/recipes.lua:475` |

从空库存造斧头、镐和一根备用火把，至少需要树枝 5、燧石 3、草 2；**科学机器材料另算**，食物与后续燃料另算。这是由配方相加得到的预算，不是游戏建议库存上限。不可把预留照明材料全花在背包、绳索上。炼金引擎的精炼材料展开为木头 16、石头 12、金块 4，均不含已建科学机器与其他装备成本。

金矿证据：`rock2` 掉落表含石头 3、金块 1、燧石 1 的必掉项，以及额外金块 0.25、燧石 0.60 的概率项；`rock1` 必掉石头 3、硝石 1、燧石 1，没有同样的金块项。应针对 `rock2`/实际掉落定义找金，不把 `rock_flintless` 等所有可挖石头当成有金。[N: `scripts/prefabs/rocks.lua:65-105`]

## 饥饿、黄昏和黑暗

- 原生默认一天为 `30 * 16 = 480` 秒，默认白天 10 段、黄昏 4 段、夜晚 2 段，脚本明确注明季节会改变构成。不要硬编码每天固定几点天黑；读取世界当前阶段和剩余时间。[N: `scripts/tuning.lua:19-29`]
- 普通基线每日消耗 75 饥饿，实际消耗受角色、burnrate 和 modifier 影响。饥饿为零后会通过 health 持续扣血，或执行角色覆盖逻辑。采集动作不会暂停饥饿。[N: `scripts/tuning.lua:41,120`; `scripts/components/hunger.lua:146-162`]
- 黑暗攻击检查实际 `IsInLight()` 和夜视/无敌等条件，不只是 `isnight`。普通角色陷入真正黑暗后，初始攻击计时是 5 到 10 秒。仅在夜晚开始才找草做火把存在致命延迟；应在黄昏提前保留、制作或接近照明。[N: `scripts/components/grue.lua:111-123`]
- 建议：真正无光时立即生存处理；黄昏检查火把库存、手持装备和剩余燃料；夜晚不要为了远处普通材料离开可靠光源。可持续营火还需要补燃料动作，不能以“建筑存在”等同于“现在有光”。这些是依据上述机制制定的调度规则。

## Builder 接口与原型契约

以下签名以本机版本为准；它们是服务端组件，不可从函数名推断成功语义。[N: `scripts/components/builder.lua`]

### 读状态

- `Builder:HasIngredients(recipe)` 接收配方对象，检查材料。`Builder:CanBuild(recipe_name)` 是已弃用的材料检查别名，**不是科技/角色权限判断**。[N: `scripts/components/builder.lua:918-952`]
- `Builder:KnowsRecipe(recipe, ignore_tempbonus, cached_tech_trees)` 支持配方名或对象。已记录配方/工作站配方会通过；否则检查角色科技 bonus。`TECH.NONE` 的斧、镐自然可通过。**附近科学机器不等于 KnowsRecipe 自动 true**。[N: `scripts/components/builder.lua:841-916`]
- `Builder:CanLearn(recname)` 检查角色 tag、禁用 tag、技能树条件，不表示材料已够，也不表示附近科技已够。[N: `scripts/components/builder.lua:954-970`]
- `Builder:EvaluateTechTrees()` 在有效原型站附近更新 `accessible_tech_trees` 与 `current_prototyper`。默认搜索距离 `TUNING.RESEARCH_MACHINE_DIST = 4`。找到了地图上的机器但没有走近，仍不具备原型条件。[N: `scripts/components/builder.lua:235-299`; `scripts/tuning.lua:343`]

### 物品制作

- `Builder:MakeRecipeFromMenu(recipe, skin)` 包含已知配方与 `CanLearn + CanPrototypeRecipe(recipe.level, self.accessible_tech_trees)` 两条合法入口；成功动作回调负责激活机器和解锁。需要 inventory 对自己处于打开/可用状态。这个函数没有可当成成功布尔值的返回值。[N: `scripts/components/builder.lua:1041-1111`]
- `Builder:MakeRecipe(recipe, pt, rot, skin, onsuccess)` 是较低层的异步入队：检查状态、材料或缓冲，然后推入 `ACTIONS.BUILD`。返回 true 表示动作已入队，不是产物已生成。它本身不完成上述科技学习门禁，不能借此跳过原型流程。[N: `scripts/components/builder.lua:629-644`]
- 原型物品不能简单用 `if not KnowsRecipe then fail` 拒绝；这样会把“机器在旁但尚未学会”的配方永久挡住。也不要为方便直接 `UnlockRecipe`，那会脱离正常制作成本与成功事件。

### 建筑两阶段

1. 获取 `recipe = GetValidRecipe(recname)`，确认角色/科技可用、材料够，选择可达且安全的候选落点。
2. `Builder:BufferBuild(recname)` 在非重复缓冲、材料够且科技合法时扣除材料，并 `SetBuildBuffered(recname, true)`；首次原型建筑的解锁也在这里完成。它没有可依赖的成功布尔返回值。[N: `scripts/components/builder.lua:1131-1182`]
3. 读 `Builder:IsBuildBuffered(recname)` 确认已缓冲。之后 `Builder:MakeRecipeAtPoint(recipe, pt, rot, skin)` 要求建筑有 placer、已知/允许缓冲放置、已有缓冲，以及 `TheWorld.Map:CanDeployRecipeAtPoint(pt, recipe, rot, self.inst)` 通过。它也没有成功布尔返回值。[N: `scripts/components/builder.lua:1113-1124`]
4. 真正 `DoBuild` 会清除缓冲并创建产物。仅发出动作不能标记营地已建成，要等成功回调或对应建筑实体。[N: `scripts/components/builder.lua:657-725`]

**恢复与幂等建议**：已有缓冲的 `BufferBuild` 不再扣材料；不合法落点的 `MakeRecipeAtPoint` 不会清掉缓冲。因此每 tick 优先恢复已有缓冲，重新选择合法落点；不要清缓冲或重新造一份。行动仍在排队时不要每 tick 重复 PushAction。这个保护不等于完整事务回滚：低层 `DoBuild` 会在 SpawnPrefab 前清缓冲，仍需记录失败并观察真实产物。建筑间距和地形合法性让原生 `CanDeployRecipeAtPoint` 判断，不要仅凭平面距离手写“空位”。

## 角色饮食必须查询原生组件

- `Eater:CanEat(food)` 仅用可尝试食物组测试；`Eater:Eat(food, feeder)` 真正成功的条件是 `Eater:PrefersToEat(food)`。只检查 `edible` 或 `CanEat` 会反复尝试角色拒食的物品。[N: `scripts/components/eater.lua:230-235,320-354`]
- 薇格弗德 `wathgrithr`：`SetDiet({ FOODGROUP.OMNI }, { FOODTYPE.MEAT, FOODTYPE.GOODIES })`，可显示尝试吃杂食的动作，但实际偏好限制更窄。不要给她套“胡萝卜/浆果应急”通用方案。[N: `scripts/prefabs/wathgrithr.lua:168`]
- 沃特 `wurt`：可吃和偏好均为 `FOODGROUP.VEGETARIAN`。[N: `scripts/prefabs/wurt.lua:665`]
- 沃利 `warly`：偏好 tag 为 `preparedfood` 或 `pre-preparedfood`；有 foodmemory，重复食物会应用记忆乘数；饥饿消耗率为 Wilson 基线乘 `WARLY_HUNGER_RATE_MODIFIER`，当前值 1.2。不能只让他采生浆果。[N: `scripts/prefabs/warly.lua:30-42`; `scripts/tuning.lua:4597`]
- 沃拓克斯 `wortox`：普通食物 health/hunger/sanity 吸收乘 `WORTOX_FOOD_MULT`，当前为 0.5；不能用普通食物数量直接估算他的续航。[N: `scripts/prefabs/wortox.lua:771`; `scripts/tuning.lua:4526`]
- 食物效果应调用 `food.components.edible:GetHunger(eater)`、`GetHealth(eater)`、`GetSanity(eater)`，结合 eater 吸收率和 foodmemory；不是只读基础字段。新鲜度、角色 affinity 等会改变效果。[N: `scripts/components/edible.lua:72-143`; `scripts/components/eater.lua:235-280`]

建议选择候选食物时先校验实体有效、edible 存在、`PrefersToEat`，再权衡饥饿收益、生命/理智代价、腐败和食物记忆。怪物肉、蘑菇和腐败食物不能统一视作安全应急食物；模组角色尤其应以运行时 eater/edible 为准，而不是角色名白名单。

## 探索、地图记忆与可行营地

原生地图探索器在 `player_classified.MapExplorer` 上；玩家存档使用 `RecordAllMaps()` 与 `LearnAllMaps()`，原生地图揭示组件使用 `RevealArea(...)`。这说明原生地图是独立状态，**不能把服务器全局实体列表当作角色已经发现的一切**。[N: `scripts/prefabs/player_common.lua:1858,1876-1877`; `scripts/components/maprevealer.lua:79-85`]

**实现建议**：仅从角色当次可观测/近距离发现结果建立自己的资源记忆，存 prefab、位置、发现时间、上次成功到达、是否已采空/危险/不可达。`FindEntities` 的局部结果不等于全图规划；走向未访问的陆地区块或已知目标时，应检查地形和路径失败，避免圆周随机游走。不要使用全图揭示 API 给 AI 偷看。

已发现金矿但暂时缺镐，应先补工具再回访；目标采空或连续不可达，应给坐标短期冷却，不能无限重试。资源充足时停止常规采集，推动建造/原型；没有发现目标时才扩大探索。营地先选择远离已观察敌对生物、可达、有食物路线和木材的陆地，不必开局寻找所谓唯一完美位置。

独立推进的合理最小闭环是：工具 → 金块/石头/木头 → 科学机器 → 背包/绳索/武器/护甲 → 固定照明与食物路线 → 炼金引擎/锅和季节准备。木炭获取、锅内烹饪、补火、装备与战斗都是额外动作能力；若实现尚不支持，必须将其标成后续能力，不能在提示词里声称机器人已经会做。

## 给实现与测试的验收条件

这些是工程建议，不是已执行游戏测试：

- 普通角色无工具时，能从拾取资源推进到斧/镐，而非只增加原料库存。
- 找到并采完 `rock2` 后，科学机器材料够就尝试合法放置；如果落点失败，保留缓冲换点，不重复扣料。
- 无配方记忆的角色走到科学机器范围内可原型背包/绳索；远离机器后已学会的普通配方仍能制作。
- 食物选择分别覆盖 wathgrithr、wurt、warly，保证不是“有食物但一直拒食”。
- 黄昏预备光源，实际无光立即中断发展动作；不会把仅存在但熄灭的营火当作安全。
- 观察阶段、当前目标和失败原因；限制资源库存目标；路径/放置/动作失败后有有限重试与替代目标。
- 测试要模拟正常的异步动作完成，不能将 `MakeRecipeFromMenu` / `MakeRecipeAtPoint` 的 nil 返回误判成失败，也不能把低层入队 true 当作成功建成。
