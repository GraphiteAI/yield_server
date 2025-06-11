'''
This service hosts the endpoints that dynamically generates the appropriate response value based on the incoming uuid request.

The endpoints are:
/profile - returns the leader/copytrader's profile data
'''

from yield_server.backend.database.models import UserRole, LeaderStatus
from yield_server.middleware.jwt_middleware import enforce_user_id_from_jwt
from yield_server.utils.time import convert_date_to_timestamp
from yield_server.backend.crud.user_crud import UserCRUD
from yield_server.backend.schema.user_schema import UserGetRole

from yield_server.core.get_portfolio import get_protected_portfolio_info, get_protected_portfolio_info_leader

from pydantic import BaseModel, UUID4
from fastapi import APIRouter, Depends, HTTPException

from typing import Optional, List, Union
from async_substrate_interface import AsyncSubstrateInterface

import os
from dotenv import load_dotenv

load_dotenv(override=True)

NETWORK = os.getenv("NETWORK")

if NETWORK == "test":
    URL = "wss://test.finney.opentensor.ai:443"
else:
    URL = "wss://entrypoint-finney.opentensor.ai:443"

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"]) # NOTE: these are the endpoints that will serve the frontend data

class PortfolioData(BaseModel):
    portfolio_data: dict

user_crud = UserCRUD()

# --- Substrate connection management ---
substrate = None

async def get_substrate():
    global substrate
    # Check if substrate exists and is connected
    if substrate is None:
        substrate = AsyncSubstrateInterface(url=URL)
        await substrate.initialize()
    else:
        try:
            health = await substrate.rpc_request("system_health", [])
            if health.get("jsonrpc", "") != "2.0": # assuming a healthy connection returns a valid JSON-RPC response
                print("Reinitializing substrate connection due to health check failure.")
                substrate = AsyncSubstrateInterface(url=URL)
                await substrate.initialize()
        except:
            substrate = AsyncSubstrateInterface(url=URL)
            await substrate.initialize()
    return substrate

# --- Endpoints ---
# Profile endpoint only allows access to the user's own profile
@router.get("/profile", response_model=PortfolioData)
async def get_profile_data(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> PortfolioData:
    user_address = await user_crud.get_user_address(UserGetRole(id=current_user))
    user_role = await user_crud.get_user_role(UserGetRole(id=current_user))
    
    print(f"portfolio/profile User address: {user_address}")
    substrate_conn = await get_substrate()
    if user_role == UserRole.LEADER:
        portfolio = await get_protected_portfolio_info_leader(user_address, substrate_conn)
    else:
        portfolio = await get_protected_portfolio_info(user_address, substrate_conn)
    return PortfolioData(portfolio_data=portfolio)

# Leader profile endpoint allows anyone access to the leader's profile data
@router.get("/leader/{leader_id}", response_model=PortfolioData)
async def get_profile_data(
    leader_id: UUID4
) -> PortfolioData:
    user_address = await user_crud.get_user_address(UserGetRole(id=leader_id))
    user_role = await user_crud.get_user_role(UserGetRole(id=leader_id))
    if user_role == UserRole.LEADER:
        substrate_conn = await get_substrate()
        portfolio = await get_protected_portfolio_info_leader(user_address, substrate_conn)
        return PortfolioData(portfolio_data=portfolio)
    else:
        raise HTTPException(status_code=500, detail="User is not a leader")



from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Yield Frontend Data API",
    description="API for serving frontend data",
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

