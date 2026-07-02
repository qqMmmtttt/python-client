# Python 基础客户端

这是一个最小 Python 参赛客户端。它使用 `pyproject.toml` 作为常规 Python 工程元数据，运行时只依赖 Python 标准库。

它演示了：

- 5 位十进制 UTF-8 字节长度分帧。
- `registration` / `start` / `ready` / `inquire` / `action` 流程。
- 使用 `actions: []` 发送空动作心跳。

## 项目结构

当前代码按职责拆分，后续策略扩展应优先放入对应目录：

```text
lychee_basic_client/
├── protocol/       # TCP 分帧、消息封装、动作构造
├── runtime/        # 客户端会话主循环
├── models/         # 静态地图、动态局面状态、天气状态
├── events/         # events[] 分类和摘要
├── strategies/     # 任务、资源、交付、对抗等策略模块
├── rules/          # 合法动作与规则判断
├── planning/       # 路径规划、路线 profile 和目标选择
├── observability/  # 分级日志
└── testing/        # Mock 服务端和测试样例
```

默认策略管线当前包含一版基础得分策略：

- 沿实际地图的保守主路线向 S14 推进。
- 在固定处理站自动提交 `PROCESS` / `DOCK`。
- 宫宴冲刺阶段在 S14 提交 `VERIFY_GATE`。
- 已验核后移动到 S15 并提交 `DELIVER`。
- 任务分未到关键阈值时，会在交付安全时间内主动规划高价值任务目标，优先争取 90+ 任务基础分。
- 遇到障碍时，如存在对应 T04 清障任务，会优先用 `CLAIM_TASK` 清障拿分，而不是直接 `CLEAR`。
- 路线上遇到可领取的关键资源、窗口争夺和简单阻挡时做保守处理。
- 进入交付危险时间窗后停止追任务，优先 S14 验核和 S15 交付。

后续可以在 `strategies/` 下继续增强任务选择、资源使用、窗口博弈、小分队和对抗策略。

更详细的工程说明见 `docs/architecture.md`，当前策略说明见 `docs/strategy.md`。

路线策略通过 `--route-profile` 控制：

- `auto`：默认值。第一轮地图签名匹配时使用保守路线，否则回退到通用动态图搜索。
- `first-round-safe`：强制使用第一轮保守路线，只要该路线在当前地图上连通。
- `generic`：不使用任何固定路线，完全按当前地图、天气和阻挡做动态图搜索。

策略层通过 `StrategyContext` 获取当前局面和事件摘要，天气影响由 `WeatherState` 统一解析，路线决策由 `RoutePolicy` 统一处理，避免任务、资源、交付和对抗策略互相耦合。

## 日志

默认日志目录为 `logs/`，可通过 `--log-dir` 修改：

- `info.log`：调试和普通运行信息。
- `important.log`：连接、开局、每帧任务摘要、天气、关键事件、动作结果和最终动作。
- `error.log`：错误和异常堆栈。

## 运行环境

- Windows：Windows 10/11，安装 Python 后在 PowerShell 或 CMD 中运行。
- Linux/WSL2：安装 Python 后在 shell 中运行。
- Python 版本：Python 3.9 或更高版本。
- 必需命令：Windows 推荐 `py -3`，Linux/WSL2 推荐 `python3`。
- 第三方依赖：无，只使用 Python 标准库。

## 检查

Windows PowerShell/CMD：

```powershell
py -3 -m py_compile basic_client.py
py -3 -m unittest discover -s tests
```

Linux/WSL2：

```bash
python3 -m py_compile basic_client.py
python3 -m unittest discover -s tests
```

## 可选的可编辑安装

Windows PowerShell/CMD：

```powershell
py -3 -m pip install -e .
```

Linux/WSL2：

```bash
python3 -m pip install -e .
```

完成可编辑安装后，可以使用下面的控制台命令：

```bash
lychee-basic-python-client --host 127.0.0.1 --port 30000 --player-id 1006 --player-name BasicPy --version 0.1
```

## 不安装直接运行

Windows PowerShell/CMD：

```powershell
py -3 .\basic_client.py --host 127.0.0.1 --port 30000 --player-id 1006 --player-name BasicPy --version 0.1
```

Linux/WSL2：

```bash
python3 basic_client.py --host 127.0.0.1 --port 30000 --player-id 1006 --player-name BasicPy --version 0.1
```
