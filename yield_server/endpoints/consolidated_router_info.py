from yield_server.endpoints import (
    leader_management_router,
    copytrader_management_router,
    profile_data_router,
    health_router,
    leader_metrics_router,
    user_management_router,
    portfolio_router,
    # leaderproxy_router,
    hotkey_sync_router,
    rebalance_router,
    copytrader_metrics_router,
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create FastAPI app
app = FastAPI(
    title="Development Yield Server Endpoint",
    description="Docs for Test Environment Yield Server"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For testing; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leader_management_router)
app.include_router(copytrader_management_router)
app.include_router(profile_data_router)
app.include_router(health_router)
app.include_router(leader_metrics_router)
app.include_router(user_management_router)
app.include_router(portfolio_router)
# app.include_router(leaderproxy_router)
app.include_router(hotkey_sync_router)
app.include_router(rebalance_router)
app.include_router(copytrader_metrics_router)

