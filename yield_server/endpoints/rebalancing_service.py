from yield_server.middleware.admin_middleware import validate_admin_key
from yield_server.core.subtensor_calls import get_percentage_portfolios
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.crud.leaderportfolio_crud import LeaderPortfolioCRUD
from yield_server.backend.schema.leaderportfolio_schema import (
    LeaderPortfolioUpsert,
    LeaderPortfolioOut,
)
from yield_server.backend.schema.leader_schema import LeaderOutPrivate, LeaderGet
from yield_server.backend.database.models import LeaderStatus
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, UUID4

router = APIRouter(prefix="/api/v1/rebalancing", tags=["rebalancing"])

class RebalanceRequest(BaseModel):
    leader_id: UUID4

def hash_portfolio(portfolio_distribution: dict) -> str:
    return hashlib.sha256(json.dumps(portfolio_distribution).encode()).hexdigest()

leader_crud = LeaderCRUD()
leader_portfolio_crud = LeaderPortfolioCRUD()

@router.post("/set_rebalanced", response_model=LeaderPortfolioOut, summary="[Admin] Set a rebalanced portfolio", description="Set a rebalanced portfolio for a leader")
async def set_rebalanced(
    rebalance_request: RebalanceRequest,
    is_admin: bool = Depends(validate_admin_key)
):
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # get the address of the leader
    leader: LeaderOutPrivate = await leader_crud.get_leader_by_id_private(LeaderGet(id=rebalance_request.leader_id))
    if not leader:
        raise HTTPException(status_code=404, detail="Leader not found")
    elif leader.status != LeaderStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Leader is not active")
    leader_ss58_address = leader.address
    portfolio_distributions: dict[str, dict[int, float]] = await get_percentage_portfolios(coldkeys=[leader_ss58_address]) # dict of dict representing the portfolio distributions
    portfolio_distribution = portfolio_distributions[leader_ss58_address]
    portfolio_hash = hash_portfolio(portfolio_distribution)

    return await leader_portfolio_crud.upsert_portfolio(LeaderPortfolioUpsert(
        leader_id=rebalance_request.leader_id,
        portfolio_distribution=portfolio_distribution,
        portfolio_hash=portfolio_hash
    ))



from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn
app = FastAPI(
    title="Yield Rebalancing Service",
    description="API for serving rebalancing requests",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://taotrader.xyz"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

