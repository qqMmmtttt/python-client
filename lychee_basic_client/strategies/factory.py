from lychee_basic_client.config import Config

from .combat import CombatStrategy
from .delivery import DeliveryStrategy
from .guard import GuardStrategy
from .pipeline import StrategyPipeline
from .resources import ResourceStrategy
from .routing import RoutePolicy
from .rush import RushStrategy
from .squad import SquadStrategy
from .tasks import TaskStrategy


# 策略管线的排列顺序就是“先观察/先产出”的顺序；最终是否被采纳还会由
# StrategyPipeline 按动作类别和优先级合并。这里集中列出每层策略职责，
# 方便后续新增策略时先判断应插入哪一层，而不是把逻辑塞进单个大文件。
STRATEGY_PIPELINE_STAGES = (
    ("CombatStrategy", "窗口争夺：处理南岭驿等窗口牌局，不占主交付路线规划职责"),
    ("SquadStrategy", "小分队：探路、清障、削弱设卡，和主车队动作并行"),
    ("TaskStrategy", "皇榜任务：在不影响主线交付的前提下领取/完成任务"),
    ("ResourceStrategy", "资源道具：领取并使用马、冰鉴、情报、船权等资源"),
    ("RushStrategy", "终局急策：宫宴冲刺阶段的加速/保护类急策"),
    ("GuardStrategy", "主动设卡：领先到关键节点时阻挡对手"),
    ("DeliveryStrategy", "主线交付：固定处理、验核、破障破关、移动和最终交付"),
)


def build_strategy(config: Config) -> StrategyPipeline:
    route_policy = RoutePolicy(config)
    return StrategyPipeline(
        [
            CombatStrategy(),
            SquadStrategy(route_policy),
            TaskStrategy(route_policy),
            ResourceStrategy(route_policy),
            RushStrategy(),
            GuardStrategy(route_policy),
            DeliveryStrategy(route_policy),
        ]
    )
