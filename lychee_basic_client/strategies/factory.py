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


def build_strategy(config: Config) -> StrategyPipeline:
    route_policy = RoutePolicy(config)
    return StrategyPipeline(
        [
            CombatStrategy(),
            SquadStrategy(route_policy),
            TaskStrategy(),
            ResourceStrategy(),
            RushStrategy(),
            GuardStrategy(),
            DeliveryStrategy(route_policy),
        ]
    )
