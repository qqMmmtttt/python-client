# 当前软件架构说明书

## 1. 项目目标

本项目是“一骑红尘：荔枝争运战”的 Python 参赛客户端。当前版本的目标不是只跑通通信样例，而是提供一个可运行、可测试、可扩展的基础策略框架：

- 能完成注册、开局、就绪、逐帧询问、动作提交和比赛结束处理。
- 能解析地图、玩家、节点、任务、天气、事件和动作结果。
- 能按策略管线拆分任务、资源、冲刺、交付和窗口争夺逻辑。
- 能记录分级日志，方便复盘任务、天气、事件、动作结果和最终动作。
- 能在当前第一轮地图上优先保证 S14 验核、S15 交付，同时在安全时间内争取任务分。

## 2. 顶层结构

```text
python-client/
├── basic_client.py                 # 兼容比赛入口，调用 lychee_basic_client.cli
├── start.sh                        # Linux/WSL 启动脚本
├── start.bat                       # Windows 启动脚本
├── example_data/                   # 示例交互文件与实际 map_config.json
├── docs/
│   ├── architecture.md             # 本说明书
│   └── strategy.md                 # 当前策略说明书
├── tests/                          # 单元测试与回归测试
└── lychee_basic_client/
    ├── protocol/                   # 分帧、消息、动作构造
    ├── runtime/                    # TCP 会话主循环
    ├── models/                     # 地图、状态、天气模型
    ├── events/                     # events/actionResults 摘要
    ├── planning/                   # 路线、任务、时间估算
    ├── rules/                      # 状态、buff、合法性基础规则
    ├── strategies/                 # 策略管线与各策略模块
    ├── observability/              # 分级日志系统
    └── testing/                    # Mock 服务端与测试夹具
```

## 3. 启动与运行流程

入口链路：

```text
start.sh / start.bat
  -> basic_client.py
  -> lychee_basic_client.cli.main()
  -> setup_logging()
  -> ClientSession.run()
```

运行时消息流：

```text
registration
  <- start
ready
  <- inquire(round=N)
StrategyPipeline.decide()
action(actions=[...])
  <- inquire(round=N+1, events/actionResults)
...
  <- over / error
```

关键代码：

- `lychee_basic_client/runtime/session.py`
  - 负责 socket 帧读取、消息分发、状态更新、策略调用和动作回传。
  - 每帧把 `tasks`、`weather`、`events`、`actionResults` 和最终 `actions` 写入重要日志。
- `lychee_basic_client/protocol/framing.py`
  - 负责 5 位十进制长度前缀的 UTF-8 JSON 分帧。
- `lychee_basic_client/protocol/actions.py`
  - 集中构造 `MOVE`、`PROCESS`、`CLAIM_TASK`、`USE_RESOURCE`、`VERIFY_GATE`、`DELIVER` 等动作字典。

## 4. 模型层

`models/` 只做数据解析和轻量查询，不做策略决策。

| 文件 | 作用 |
|---|---|
| `models/map.py` | 解析静态地图、路线边、处理点；提供邻接、最短路、最快路查询。 |
| `models/state.py` | 解析每帧动态状态，包括玩家、节点、任务、天气、事件、动作结果。 |
| `models/weather.py` | 解析当前天气和预告天气，提供路线倍率、鲜度倍率。 |

重要设计点：

- `GameMap.from_start()` 支持从 `start.map`、顶层 `nodes/edges/processNodes` 解析地图。
- `GameMap.with_runtime_edges()` 支持决赛地图或运行时边信息变化。
- `PlayerState.raw` 保留原始字段，方便新策略读取尚未建模的字段。
- `PlayerState` 已显式解析 `rushTacticUsedCount`、`squadAvailable` 等策略关键字段。

## 5. 事件层

`events/handlers.py` 将服务端的 `events[]` 和 `actionResults[]` 整理为 `EventSummary`：

- `completed_process_nodes`
- `completed_task_ids`
- `cleared_obstacle_nodes`
- `verified_gate`
- `delivered`
- `rejected_actions`

策略层不直接扫描复杂事件列表，而是通过 `StrategyContext.from_state()` 获得摘要。这样后续增加事件类型时，只需要扩展事件层。

## 6. 规划层

`planning/` 负责可复用的路线和任务判断。

| 文件 | 作用 |
|---|---|
| `planning/route_profiles.py` | 第一轮地图保守主路线，用于显式 `first-round-safe` 兜底。 |
| `strategies/routing.py` | `RoutePolicy`，按 `--route-profile` 决定使用固定路线还是动态图搜索。 |
| `planning/estimates.py` | 估算路线耗时、交付剩余耗时，纳入天气路线倍率和固定处理时间。 |
| `planning/tasks.py` | 皇榜任务可用性、站位点、任务优先级、任务安全时间窗。 |

路线 profile：

- `auto`：默认值。交付策略先保证 S02 前段交接，之后按当前地图、天气、处理耗时、障碍和设卡做动态图搜索；当前地图在无暴雨时会优先进入 S04/S05 水路。
- `first-round-safe`：强制使用第一轮保守陆路路线。
- `generic`：完全按当前地图动态图搜索，便于决赛地图变化；不额外启用第一轮固定路线。

## 7. 规则层

`rules/` 放置跨策略共享的规则常量和判断。

| 文件 | 作用 |
|---|---|
| `rules/states.py` | 统一定义 `ROUTE_EDGE_STATES`、`NODE_BUSY_STATES`、`MAIN_ACTION_BUSY_STATES`。 |
| `rules/buffs.py` | 统一判断马类和疾行令等移动 buff。 |
| `rules/legal.py` | 基础动作合法性辅助函数。 |

这层的价值是避免各策略重复维护状态集合。之前 `WAITING` 漏出忙碌状态导致路线边反复提交 `ICE_BOX`，现在已通过公共状态定义和回归测试锁定。

## 8. 策略层

默认策略由 `strategies/factory.py` 装配：

```python
StrategyPipeline(
    [
        CombatStrategy(),
        SquadStrategy(),
        TaskStrategy(),
        ResourceStrategy(),
        RushStrategy(),
        DeliveryStrategy(route_policy),
    ]
)
```

管线按任务书的动作类别上限合并动作：同帧最多 1 个主车队动作、1 个小分队动作、1 个窗口出牌动作和 1 个急策额度。多个策略给出同类别动作时，前面的策略保留，后面的同类别动作跳过；不同类别会合并提交，例如主车队 `MOVE` 可以和 `SQUAD_SCOUT` 同帧发送。

| 策略 | 文件 | 职责 |
|---|---|---|
| 窗口策略 | `strategies/combat.py` | 参与窗口争夺时出牌，优先使用护卫点、献贡、文书、强行。 |
| 小分队策略 | `strategies/squad.py` | 在普通阶段提前探路 S04/S05/S11/S13/S14；发现主线未来障碍时优先派小分队清障。 |
| 任务策略 | `strategies/tasks.py` | 当前节点可安全完成任务时提交 `CLAIM_TASK`，并记忆被拒任务避免重复卡死。 |
| 资源策略 | `strategies/resources.py` | 领取关键资源和情报；按规则使用冰鉴、马类和 `INTEL`；路线边只允许马类资源。 |
| 急策策略 | `strategies/rush.py` | 冲刺阶段路线边、无移动 buff、时间偏紧时使用 `RUSH_SPEED`。 |
| 交付策略 | `strategies/delivery.py` | 固定处理、路由、障碍/设卡处理、S14 验核、S15 交付。 |

## 9. 防卡死机制

当前已实现的关键防护：

- `MOVING/WAITING`：站点动作全部停手；资源策略只允许马类资源；无动作时提交 `actions: []` 让路线继续推进。
- 固定处理站：每次重新停靠 S02/S04/S05/S11/S13 都重新要求 `PROCESS`，处理完成后才离站。
- S04 登船处理：统一提交 `PROCESS`，与任务书保持一致。
- S14：非冲刺阶段不验核，冲刺阶段提交 `VERIFY_GATE`；只有 `breakOrderReady=true`、急策未用且成本足够时才绑定 `BREAK_ORDER`。
- S15：未验核时返回 S14；已验核且满足好果/鲜度条件时立即 `DELIVER`；安全区不再使用资源。
- 破关令：不单独发送 `BREAK_ORDER`，也不在 `breakOrderReady=false` 时绑定到验核，避免业务前提不满足导致整包 error。
- 任务拒绝：被 `CLAIM_TASK` 拒绝的任务实例会进入本局黑名单，不再抢占主线。
- 小分队：作为独立类别和主车队动作同帧提交，不会阻塞移动、处理或交付。
- 障碍：优先 T04 拿分清障；无 T04 时有余量用 `CLEAR`，时间紧或无好果时 `FORCED_PASS`。
- 设卡：有余量且有果品时攻坚，否则强制通行，避免长期停在阻挡前。

## 10. 日志系统

日志由 `observability/logging_setup.py` 初始化，默认写入 `logs/`：

| 文件 | 内容 |
|---|---|
| `trace.log` | 最低级别，完整记录每条入站/出站消息，包括方向、消息名、round、playerId、长度前缀、body 字节数和 JSON。 |
| `info.log` | 调试和普通运行信息，也记录可恢复的 warning。 |
| `important.log` | 开局、每帧状态、任务、天气、事件、动作结果、策略决策来源和最终动作。 |
| `error.log` | 协议错误、读帧异常、启动前错误等可能导致异常退赛或程序无法运行的问题。 |

`trace.log` 用于协议级复盘，例如判断长度前缀和 JSON body 是否对齐。`important.log` 是策略级复盘主文件，能够直接定位任务、天气、事件、拒绝码、决策策略和最终动作。

## 11. 测试系统

测试位于 `tests/`，当前覆盖：

- 协议动作构造、消息构造、分帧。
- 地图、状态、天气解析。
- 策略管线类别合并与同类别冲突跳过。
- 任务规划、T04 障碍处理。
- S14 验核、S15 交付、S04 处理、固定处理重入。
- 路线边 `WAITING/MOVING` 资源限制回归。
- 冲刺阶段 `RUSH_SPEED` 使用。
- 默认动态水路选择、暴雨回避水路、显式保守陆路 profile。
- 情报领取/使用、小分队探路/清障。
- 日志分级输出。

运行：

```powershell
py -3 -m unittest discover -s tests
py -3 -m compileall -q lychee_basic_client tests basic_client.py
```

## 12. 扩展规范

后续新增能力时建议遵循：

- 新规则常量放在 `rules/`，不要在多个策略里重复写状态集合。
- 新目标选择算法放在 `planning/`，策略层只调用规划结果。
- 新策略放在 `strategies/`，通过 `factory.py` 加入管线。
- 需要跨帧记忆的策略只保存最小状态，例如已拒绝任务、已尝试资源。
- 每个新增卡死风险都要加回归测试，尤其是业务拒绝后是否会重复提交同一动作。

## 13. 当前完成度

| 模块 | 完成度 | 说明 |
|---|---:|---|
| 通信协议 | 90% | 基础收发、分帧、动作封装完整；复杂字段仍保留 raw 扩展。 |
| 数据模型 | 88% | 覆盖核心状态、地图、天气、玩家资源、小分队数量和破关令准备态；悬赏可继续细化。 |
| 日志系统 | 90% | 已分级落盘，重要日志足够复盘当前策略。 |
| 测试系统 | 83% | 核心策略和回归用例已覆盖，缺完整比赛仿真器。 |
| 路线规划 | 85% | 支持默认动态水路/天气绕行和显式第一轮固定路线；可继续加入更精细对手代价。 |
| 任务策略 | 70% | 支持安全时间窗和拒绝记忆；尚未做复杂对手博弈。 |
| 资源策略 | 82% | 支持冰鉴、马类、情报领取与使用；文书资源主动规划待扩展。 |
| 对抗策略 | 65% | 有基础窗口出牌、小分队探路/清障和阻挡处理；主动设卡、防守收益待扩展。 |
| 交付策略 | 88% | 当前地图可完整走到 S15 交付；极端对手干扰仍需更强仿真和博弈。 |
