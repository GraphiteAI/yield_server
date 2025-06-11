from .leader_management_service import router as leader_management_router
from .copytrader_management_service import router as copytrader_management_router
from .profile_data_service import router as profile_data_router
from .health import router as health_router
from .leader_metrics_service import router as leader_metrics_router
from .copytrader_metrics_service import router as copytrader_metrics_router
from .profile_data_service import router as profile_data_router
from .hotkey_syncing_service import router as hotkey_sync_router
# from .leaderproxy_service import router as leaderproxy_router
from .portfolio_service import router as portfolio_router
from .rebalancing_service import router as rebalance_router
from .user_management_service import router as user_management_router

__all__ = [
    "leader_management_router",
    "copytrader_management_router",
    "profile_data_router",
    "health_router",
    "leader_metrics_router",
    "user_management_router",
    "portfolio_router",
    # "leaderproxy_router",
    "hotkey_sync_router",
    "rebalance_router",
    "copytrader_metrics_router",
]