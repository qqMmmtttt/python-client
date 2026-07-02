from lychee_basic_client.config import Config

from .combat import CombatStrategy
from .delivery import DeliveryStrategy
from .pipeline import StrategyPipeline
from .resources import ResourceStrategy
from .routing import RoutePolicy
from .tasks import TaskStrategy


def build_strategy(config: Config) -> StrategyPipeline:
    route_policy = RoutePolicy(config)
    return StrategyPipeline(
        [
            CombatStrategy(),
            TaskStrategy(),
            ResourceStrategy(),
            DeliveryStrategy(route_policy),
        ]
    )
