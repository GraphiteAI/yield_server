from yield_server.backend.database.models import UserRole
from yield_server.backend.crud.copytrader_crud import CopyTraderCRUD
from yield_server.backend.crud.user_crud import UserCRUD
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.schema.leader_schema import LeaderDemote
from yield_server.backend.schema.user_schema import UserGet
from yield_server.backend.schema.copytrader_schema import (
    CopyTraderCreate,
    CopyTraderChooseLeader,
    CopyTraderGet,
    CopyTraderOut,
    CopyTraderDemote,
    CopyTraderSetProxy,
    CopyTraderProxyBindOut,
    CopyTraderRemoveProxy,
)

from yield_server.backend.schema.user_schema import UserOutPrivate, UserGet

from yield_server.middleware.jwt_middleware import enforce_user_id_from_jwt

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
import bittensor as bt
from bittensor.utils import is_valid_ss58_address
from scalecodec.utils.ss58 import ss58_encode
from pydantic.types import UUID4
import os
from dotenv import load_dotenv

load_dotenv(override=True)

router = APIRouter(prefix="/api/v1/copytrader", tags=["copytrader"])
copytrader_crud = CopyTraderCRUD()
user_crud = UserCRUD()
leader_crud = LeaderCRUD()

class CopyTraderAddProxyRequest(BaseModel):
    extrinsic_hash: str
    block_number: int
    target_proxy: str

    @field_validator("target_proxy")
    def validate_target_proxy(cls, v):
        if not is_valid_ss58_address(v):
            try:
                v = ss58_encode(v)
            except:
                raise ValueError("Invalid proxy address")
        return v

class CopyTraderRemoveProxyRequest(BaseModel):
    extrinsic_hash: str
    block_number: int

NETWORK = os.getenv("NETWORK")

@router.post("/declare_copytrader", response_model=CopyTraderOut)
async def declare_copytrader(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> CopyTraderOut:
    try:
        # demote the user to generic first
        existing_user = await user_crud.get_user(UserGet(id=current_user))
        if not existing_user:
            raise ValueError("User not found | Please register as a user first")
        if existing_user.role != UserRole.GENERIC:
            if existing_user.role == UserRole.COPYTRADER:
                raise ValueError("User is already a copytrader")
            else:
                await leader_crud.demote_leader(LeaderDemote(id=current_user))
        # get the current block number
        subtensor = bt.AsyncSubtensor(NETWORK)
        current_block_number = await subtensor.block
        # get the leader stakes
        # stakes = await get_wallet_stakes(existing_user.address, async_subtensor=subtensor)
        # subnets_info = await get_subnets_info(subtensor)
        # copytrader_account_balance = await get_wallet_stakes_in_rao(subnets_info, stakes)
        copytrader_create = CopyTraderCreate(
            id = current_user,
            account_starting_balance = 0,
            last_proxy_block = current_block_number, # prevent replay attacks
            next_rebalance_block = current_block_number # prevent replay attacks
        )
        copytrader = await copytrader_crud.create_new_copytrader(copytrader_create)
        return copytrader
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_proxy_data/{leader_id}", response_model=CopyTraderProxyBindOut)
async def get_proxy_data(
    leader_id: UUID4,
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> CopyTraderProxyBindOut:
    choose_leader = CopyTraderChooseLeader(
        id = current_user,
        leader_id = leader_id
    )
    try:
        return await copytrader_crud.get_proxy_data(choose_leader)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/add_proxy", response_model=CopyTraderOut)
async def add_proxy(
    add_proxy: CopyTraderAddProxyRequest,
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> CopyTraderOut:
    try:
        # check if the user is a copytrader
        existing_copytrader = await copytrader_crud.get_copytrader(CopyTraderGet(id=current_user))
        full_add_proxy = CopyTraderSetProxy(
            id = current_user,
            copytrader_address = existing_copytrader.address,
            target_proxy = add_proxy.target_proxy,
            extrinsic_hash = add_proxy.extrinsic_hash,
            block_number = add_proxy.block_number
        )
        return await copytrader_crud.set_proxy(full_add_proxy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/remove_proxy", response_model=CopyTraderOut)
async def remove_proxy(
    remove_proxy: CopyTraderRemoveProxyRequest,
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> CopyTraderOut:
    try:
        existing_copytrader = await copytrader_crud.get_copytrader(CopyTraderGet(id=current_user))
        full_remove_proxy = CopyTraderRemoveProxy(
            id = current_user,
            copytrader_address = existing_copytrader.address,
            extrinsic_hash = remove_proxy.extrinsic_hash,
            block_number = remove_proxy.block_number
        )
        return await copytrader_crud.remove_proxy(full_remove_proxy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_copytrader", response_model=CopyTraderOut)
async def get_copytrader(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> CopyTraderOut:
    get_copytrader = CopyTraderGet(id=current_user)
    try:
        return await copytrader_crud.get_copytrader(get_copytrader)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/demote_copytrader", response_model=UserOutPrivate)
async def demote_copytrader(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> UserOutPrivate:
    try:
        return await copytrader_crud.demote_copytrader(CopyTraderDemote(id=current_user))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Yield CopyTrader Management API",
    description="API for managing copytraders",
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

