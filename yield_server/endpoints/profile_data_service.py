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
from yield_server.backend.crud.leadermetrics_crud import LeaderMetricsCRUD
from yield_server.backend.schema.leadermetrics_schema import LeaderMetricsGet, LeaderMetricsOut, LeaderMetricsSnapshotOut, LeaderboardMetricsGet, LeaderMetricsHistoryGet
from yield_server.backend.crud.leaderviolations_crud import LeaderViolationCRUD
from yield_server.backend.schema.leaderviolations_schema import LeaderViolationOut
from yield_server.backend.crud.copytradermetrics_crud import CopyTraderMetricsCRUD
from yield_server.backend.crud.leaderproxy_crud import LeaderProxyCRUD
from yield_server.backend.schema.leaderproxy_schema import LeaderProxyGet, LeaderProxyOut
from yield_server.backend.schema.copytradermetrics_schema import CopyTraderMetricsOut, CopyTraderMetricsGet, CopyTraderMetricsSnapshotOut, CopyTraderMetricsHistoryGet
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.schema.leader_schema import LeaderGet, LeaderOutPrivate, LeaderOutPublic
from yield_server.backend.crud.copytrader_crud import CopyTraderCRUD
from yield_server.backend.schema.copytrader_schema import CopyTraderGet, CopyTraderOut, SetCopyTraderForRebalancing
from yield_server.config.constants import DEFAULT_MINIMUM_PROXY_BALANCE

# TODO: refactor this import out to a utils file
from yield_server.core.subtensor_calls import get_percentage_portfolios
from yield_server.endpoints.rebalancing_service import hash_portfolio

from pydantic import BaseModel, UUID4
from fastapi import APIRouter, Depends, HTTPException

from async_substrate_interface import AsyncSubstrateInterface

from bittensor.core.chain_data import SubnetInfo
from bittensor.utils.balance import Balance
import bittensor as bt

from typing import Optional, List, Union

from datetime import datetime, timedelta

import os
from dotenv import load_dotenv

load_dotenv(override=True)

NETWORK = os.getenv("NETWORK")

if NETWORK == "test":
    URL = "wss://test.finney.opentensor.ai:443"
else:
    URL = "wss://entrypoint-finney.opentensor.ai:443"

router = APIRouter(prefix="/api/v1/yield", tags=["yield"]) # NOTE: these are the endpoints that will serve the frontend data

SUBSTRATE: Optional[AsyncSubstrateInterface] = None

async def get_substrate():
    global SUBSTRATE
    # Check if substrate exists and is connected
    if SUBSTRATE is None:
        SUBSTRATE = AsyncSubstrateInterface(url=URL)
        await SUBSTRATE.initialize()
    else:
        try:
            health = await SUBSTRATE.rpc_request("system_health", [])
            if health.get("jsonrpc", "") != "2.0": # assuming a healthy connection returns a valid JSON-RPC response
                print("Reinitializing substrate connection due to health check failure.")
                SUBSTRATE = AsyncSubstrateInterface(url=URL)
                await SUBSTRATE.initialize()
        except:
            SUBSTRATE = AsyncSubstrateInterface(url=URL)
            await SUBSTRATE.initialize()
    return SUBSTRATE

class PerformancePoint(BaseModel):
    timestamp: int
    pnl_percent_tick: float
    pnl_tick: float

class GenericProfileData(BaseModel):
    uuid: UUID4
    user_role: UserRole

class BaseParticipantProfileData(GenericProfileData):
    performance_history: Optional[List[PerformancePoint]] = None
    total_assets: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    volume: Optional[float] = None
    is_proxy_alive: Optional[bool] = None

class LeaderPublicProfileData(BaseParticipantProfileData):
    alias: str
    status: LeaderStatus
    sharpe_ratio: Optional[float] = None
    drawdown: Optional[float] = None
    num_copy_traders: Optional[int] = None
    rank: Optional[int] = None

class LeaderPrivateProfileData(LeaderPublicProfileData):
    account_starting_balance: Optional[float] = None
    start_block_number: Optional[int] = None
    hotkey: Optional[str] = None
    violation_message: Optional[str] = None
    proxy_address: Optional[str] = None
    proxy_address_balance: Optional[float] = None

class CopyTraderProfileData(BaseParticipantProfileData):
    chosen_leader_id: Optional[UUID4] = None
    chosen_leader_alias: Optional[str] = None
    target_proxy: Optional[str] = None
    free_balance: Optional[float] = None

user_crud = UserCRUD()
copytrader_crud = CopyTraderCRUD()
leader_crud = LeaderCRUD()
leader_metrics_crud = LeaderMetricsCRUD()
copytrader_metrics_crud = CopyTraderMetricsCRUD()
leader_violation_crud = LeaderViolationCRUD()
leader_proxy_crud = LeaderProxyCRUD()

def convert_to_tao(tao_amount: int) -> float:
    return tao_amount / 10**9

def convert_to_percentage(proportion: float) -> float:
    return round(proportion * 100, 4)

def convert_metric_to_performance(metrics: List[LeaderMetricsSnapshotOut]) -> List[PerformancePoint]:
    # Impute Day 0 performance
    day_zero_date = metrics[0].snapshot_date - timedelta(days=1)
    day_zero_performance_point = PerformancePoint(timestamp=convert_date_to_timestamp(day_zero_date), pnl_percent_tick=0, pnl_tick=0)
    return [day_zero_performance_point] + [PerformancePoint(timestamp=convert_date_to_timestamp(metric.snapshot_date), pnl_percent_tick=convert_to_percentage(metric.pnl_percent), pnl_tick=convert_to_tao(metric.pnl)) for metric in metrics]


async def fetch_private_copytrader_data(user_id: UUID4) -> CopyTraderProfileData:
    copytrader_data: CopyTraderOut = await copytrader_crud.get_copytrader(CopyTraderGet(id=user_id))
    substrate = await get_substrate()
    ## Implement your own function to get the unprocessed balance on-chain
    unprocessed_balance = 0
    processed_balance = Balance(unprocessed_balance["data"]["free"])

    try:
        copytrader_metrics: CopyTraderMetricsOut = await copytrader_metrics_crud.get_metrics(CopyTraderMetricsGet(copytrader_id=user_id))
        copytrader_metric_history: List[CopyTraderMetricsSnapshotOut] = await copytrader_metrics_crud.get_metrics_history(CopyTraderMetricsHistoryGet(copytrader_id=user_id))
    except ValueError as e:
        copytrader_metrics = None
        copytrader_metric_history = None
    
    is_proxy_alive = False
    if copytrader_data.target_proxy:
        try:
            leader_proxy: LeaderProxyOut = await leader_proxy_crud.get_proxy(LeaderProxyGet(proxy_id=copytrader_data.target_proxy))
            # check whether the leader is violated by checking if the leader_proxy is still associated with the leader
            if leader_proxy.balance > DEFAULT_MINIMUM_PROXY_BALANCE and leader_proxy.leader_id:
                is_proxy_alive = True
        except ValueError:
            is_proxy_alive = False
            
    return CopyTraderProfileData(
        uuid=copytrader_data.id,
        user_role=copytrader_data.role,
        chosen_leader_id=copytrader_data.chosen_leader_id,
        chosen_leader_alias=copytrader_data.chosen_leader_alias,
        target_proxy=copytrader_data.target_proxy,
        performance_history=convert_metric_to_performance(copytrader_metric_history) if copytrader_metric_history else None,
        total_assets=convert_to_tao(copytrader_metrics.total_assets) if isinstance(copytrader_metrics, CopyTraderMetricsOut) else None,
        pnl=convert_to_tao(copytrader_metrics.pnl) if isinstance(copytrader_metrics, CopyTraderMetricsOut) else None,
        pnl_percent=convert_to_percentage(copytrader_metrics.pnl_percent) if isinstance(copytrader_metrics, CopyTraderMetricsOut) else None,
        volume=convert_to_tao(copytrader_metrics.volume) if isinstance(copytrader_metrics, CopyTraderMetricsOut) else None,
        is_proxy_alive=is_proxy_alive,
        free_balance=processed_balance.tao
    )

async def fetch_private_leader_data(user_id: UUID4) -> LeaderPrivateProfileData:
    leader_data: LeaderOutPrivate = await leader_crud.get_leader_by_id_private(LeaderGet(id=user_id))
    if leader_data.status != LeaderStatus.ACTIVE:
        leader_metrics = None
        leader_metric_history = None
    else:
        try:
            leader_metrics: LeaderMetricsOut = await leader_metrics_crud.get_metrics(LeaderMetricsGet(leader_id=user_id))
            leader_metric_history: List[LeaderMetricsSnapshotOut] = await leader_metrics_crud.get_metrics_history(LeaderMetricsHistoryGet(leader_id=user_id))
        except ValueError as e:
            leader_metrics = None
            leader_metric_history = None
    
    leader_violation = None
    if leader_data.status == LeaderStatus.VIOLATED:
        # get the latest violation message
        try:
            leader_violation: LeaderViolationOut = await leader_violation_crud.get_violation(leader_data.id)
        except ValueError as e:
            pass

    proxy_address_balance = None
    if leader_data.proxy_address:
        try:
            leader_proxy: LeaderProxyOut = await leader_proxy_crud.get_proxy(LeaderProxyGet(proxy_id=leader_data.proxy_address))
            proxy_address_balance = leader_proxy.balance
        except ValueError as e:
            proxy_address_balance = None
        
    is_proxy_alive = proxy_address_balance > DEFAULT_MINIMUM_PROXY_BALANCE if (proxy_address_balance and leader_data.status == LeaderStatus.ACTIVE) else False
    
    return LeaderPrivateProfileData(
        uuid=leader_data.id,
        user_role=leader_data.role,
        alias=leader_data.alias,
        status=leader_data.status,
        sharpe_ratio=leader_metrics.sharpe_ratio if isinstance(leader_metrics, LeaderMetricsOut) else None,
        drawdown=convert_to_percentage(leader_metrics.drawdown) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        num_copy_traders=leader_metrics.num_copy_traders if isinstance(leader_metrics, LeaderMetricsOut) else None,
        performance_history=convert_metric_to_performance(leader_metric_history) if leader_metric_history else None,
        total_assets=convert_to_tao(leader_metrics.total_assets) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        account_starting_balance=convert_to_tao(leader_data.account_starting_balance) if isinstance(leader_data, LeaderOutPrivate) else None,
        start_block_number=leader_data.start_block_number if isinstance(leader_data, LeaderOutPrivate) else None,
        pnl=convert_to_tao(leader_metrics.pnl) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        pnl_percent=convert_to_percentage(leader_metrics.pnl_percent) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        volume=convert_to_tao(leader_metrics.volume) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        hotkey=leader_data.hotkey,
        rank=leader_metrics.rank if isinstance(leader_metrics, LeaderMetricsOut) else None,
        violation_message=leader_violation.violation_message if isinstance(leader_violation, LeaderViolationOut) else None,
        proxy_address=leader_data.proxy_address if isinstance(leader_data, LeaderOutPrivate) else None,
        proxy_address_balance=convert_to_tao(proxy_address_balance) if proxy_address_balance else None,
        is_proxy_alive=is_proxy_alive if isinstance(leader_data, LeaderOutPrivate) else None
    )

async def fetch_public_leader_data(user_id: UUID4) -> LeaderPublicProfileData:
    leader_data: LeaderOutPrivate = await leader_crud.get_leader_by_id_private(LeaderGet(id=user_id))
    if leader_data.status != LeaderStatus.ACTIVE:
        leader_metrics = None
        leader_metric_history = None
    else:
        try:
            leader_metrics: LeaderMetricsOut = await leader_metrics_crud.get_metrics(LeaderMetricsGet(leader_id=user_id))
            leader_metric_history: List[LeaderMetricsSnapshotOut] = await leader_metrics_crud.get_metrics_history(LeaderMetricsHistoryGet(leader_id=user_id))
        except ValueError as e:
            leader_metrics = None
            leader_metric_history = None

    is_proxy_alive = False
    if leader_data.proxy_address and leader_data.status == LeaderStatus.ACTIVE:
        try:
            leader_proxy: LeaderProxyOut = await leader_proxy_crud.get_proxy(LeaderProxyGet(proxy_id=leader_data.proxy_address))
            if leader_proxy.balance > DEFAULT_MINIMUM_PROXY_BALANCE:
                is_proxy_alive = True
        except ValueError:
            is_proxy_alive = False

    return LeaderPublicProfileData(
        uuid=leader_data.id,
        user_role=leader_data.role,
        alias=leader_data.alias,
        status=leader_data.status,
        sharpe_ratio=leader_metrics.sharpe_ratio if isinstance(leader_metrics, LeaderMetricsOut) else None,
        drawdown=convert_to_percentage(leader_metrics.drawdown) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        num_copy_traders=leader_metrics.num_copy_traders if isinstance(leader_metrics, LeaderMetricsOut) else None,
        performance_history=convert_metric_to_performance(leader_metric_history) if leader_metric_history else None,
        total_assets=convert_to_tao(leader_metrics.total_assets) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        pnl=convert_to_tao(leader_metrics.pnl) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        pnl_percent=convert_to_percentage(leader_metrics.pnl_percent) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        volume=convert_to_tao(leader_metrics.volume) if isinstance(leader_metrics, LeaderMetricsOut) else None,
        rank=leader_metrics.rank if isinstance(leader_metrics, LeaderMetricsOut) else None,
        is_proxy_alive=is_proxy_alive if isinstance(leader_data, LeaderOutPrivate) else None
    )

# Profile endpoint only allows access to the user's own profile
@router.get("/profile", response_model=Union[GenericProfileData, LeaderPrivateProfileData, CopyTraderProfileData])
async def get_profile_data(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> Union[GenericProfileData, LeaderPrivateProfileData, CopyTraderProfileData]:
    user_role: Optional[UserRole] = await user_crud.get_user_role(UserGetRole(id=current_user))
    if user_role is None:
        raise HTTPException(status_code=404, detail=f"User {current_user} not found")
    if user_role == UserRole.LEADER:
        return await fetch_private_leader_data(current_user)
    elif user_role == UserRole.COPYTRADER:
        return await fetch_private_copytrader_data(current_user)
    else:
        return GenericProfileData(uuid=current_user, user_role=user_role)
    
# NOTE: we simply respond with a 200 status code on success
@router.patch("/rebalance")
async def rebalance_proxy(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
):
    # update the copytrader's portfolio hash and distribution to their current portfolio
    # get the copytrader's address
    copytrader_data: CopyTraderOut = await copytrader_crud.get_copytrader(CopyTraderGet(id=current_user))
    if not copytrader_data:
        raise HTTPException(status_code=404, detail=f"Copytrader {current_user} not found")
    copytrader_ss58_address = copytrader_data.address
    portfolio_distributions: dict[str, dict[int, float]] = await get_percentage_portfolios(coldkeys=[copytrader_ss58_address]) # dict of dict representing the portfolio distributions
    portfolio_distribution = portfolio_distributions[copytrader_ss58_address]
    portfolio_hash = hash_portfolio(portfolio_distribution)

    # update the copytrader's portfolio hash and distribution
    try:
        await copytrader_crud.set_copytrader_for_rebalancing(SetCopyTraderForRebalancing(id=current_user, portfolio_hash=portfolio_hash))
        return {"message": f"Copytrader {current_user} has been set for rebalancing"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting copytrader for rebalancing: {e}")




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

