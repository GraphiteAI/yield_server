from yield_server.backend.database.models import UserRole
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.crud.leadermetrics_crud import LeaderMetricsCRUD
from yield_server.backend.crud.subnetminerhotkey_crud import SubnetMinerHotkeyCRUD
from yield_server.backend.crud.user_crud import UserCRUD
from yield_server.backend.crud.copytrader_crud import CopyTraderCRUD
from yield_server.backend.crud.leaderproxy_crud import LeaderProxyCRUD
from yield_server.backend.schema.copytrader_schema import CopyTraderDemote
from yield_server.backend.schema.leader_schema import (
    LeaderCreate,
    LeaderOutPrivate,
    LeaderOutPublic,
    LeaderViolated,
    LeaderDeregistered,
    LeaderDemote,
    LeaderSetHotkey,
    LeaderGet,
    LeaderUpdate,
    LeaderUnsetHotkey,
    LeaderSetStartingBalance,
    LeaderDeactivate,
    LeaderCompleteActivation,
    LeaderAdminViolate
)
from yield_server.backend.schema.leadermetrics_schema import LeaderboardMetricsGet
from yield_server.backend.schema.subnetminerhotkey_schema import SubnetMinerHotkeyGet
from yield_server.backend.schema.user_schema import UserOutPrivate, UserGet
from yield_server.backend.schema.leaderproxy_schema import LeaderProxyGet

from yield_server.middleware.jwt_middleware import get_user_id_from_jwt, enforce_user_id_from_jwt
from yield_server.middleware.admin_middleware import validate_admin_key
from yield_server.core.subtensor_calls import get_current_block_number
from yield_server.utils.signing_utils import UnverifiedSignaturePayload, verify_signature
from yield_server.endpoints.profile_data_service import fetch_public_leader_data, LeaderPublicProfileData
from yield_server.config.constants import TOP_LEADERBOARD_SIZE, MINIMUM_STARTING_BALANCE, MAXIMUM_STARTING_BALANCE

from yield_server.core.subtensor_calls import (
    get_wallet_stakes_in_rao,
    get_wallet_stakes,
    get_subnets_info
)

from names_generator import generate_name
from fastapi import APIRouter, HTTPException, Depends
import bittensor as bt
from bittensor.utils import is_valid_ss58_address
from pydantic import BaseModel, ConfigDict
from pydantic.types import UUID4
from typing import Union, Optional, List
import os
from dotenv import load_dotenv

load_dotenv(override=True)

router = APIRouter(prefix="/api/v1/leader", tags=["leader"])
leader_crud = LeaderCRUD()
user_crud = UserCRUD()
subnet_miner_crud = SubnetMinerHotkeyCRUD()
leader_metrics_crud = LeaderMetricsCRUD()
copytrader_crud = CopyTraderCRUD()
leader_proxy_crud = LeaderProxyCRUD()

NETWORK = os.getenv("NETWORK")

class LeaderCreateRequest(BaseModel):
    alias: Optional[str] = None

class LeaderActivateRequest(BaseModel):
    signature_payload: UnverifiedSignaturePayload # --> contains the hotkey information and information needed to verify ownership

class LeaderSetHotkeyRequest(BaseModel):
    id: UUID4
    signature_payload: UnverifiedSignaturePayload

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class LeaderSetStartingBalanceRequest(BaseModel):
    id: UUID4
    account_starting_balance: float
    start_block_number: Optional[int] = None

class LeaderBalanceEligibility(BaseModel):
    eligible: bool
    balance: float

@router.post("/declare_leader", response_model=LeaderOutPrivate)
async def declare_leader(
    leader_create: LeaderCreateRequest,
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> LeaderOutPrivate:
    try:
        # check if the user is already a leader
        existing_user = await user_crud.get_user(UserGet(id=current_user))
        if not existing_user:
            raise ValueError("User not found | Please register as a user first")
        if existing_user.role != UserRole.GENERIC:
            if existing_user.role == UserRole.LEADER:
                raise ValueError("User is already a leader")
            else:
                # demote the copytrader to generic
                await copytrader_crud.demote_copytrader(CopyTraderDemote(id=current_user))
        
        leader_create: LeaderCreate = LeaderCreate(
            id=current_user,
            alias=leader_create.alias if leader_create.alias else generate_name(),
            account_starting_balance=0.0,
            start_block_number= 0
        )
        leader = await leader_crud.create_new_leader(leader_create)
        return leader
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/all", response_model=List[LeaderOutPublic])
async def get_all_leader() -> List[LeaderOutPublic]:
    leaders_out: List[LeaderOutPublic] = await leader_crud.get_all_leaders()
    return leaders_out

@router.patch("/activate_leader")
async def activate_leader(
    activate_leader: LeaderActivateRequest,
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
    ) -> LeaderOutPrivate:
    # validate the signature:
    if not verify_signature(activate_leader.signature_payload):
        raise HTTPException(status_code=400, detail="Invalid signature")
    # get the leader address
    try:
        leader_private: LeaderOutPrivate = await leader_crud.get_leader_by_id_private(LeaderGet(id=current_user))
        leader_address = leader_private.address
        if not is_valid_ss58_address(leader_address):
            raise HTTPException(status_code=400, detail=f"Invalid leader address: {leader_address}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # get the current block number
    subtensor = bt.AsyncSubtensor(NETWORK)
    current_block_number = await subtensor.block
    # get the leader stakes
    stakes = await get_wallet_stakes(leader_address, async_subtensor=subtensor)
    subnets_info = await get_subnets_info(subtensor)
    leader_account_balance = await get_wallet_stakes_in_rao(subnets_info, stakes)
    # check leader account balance
    complete_leader_activation = LeaderCompleteActivation(
        id=current_user,
        hotkey=activate_leader.signature_payload.address,
        account_starting_balance=leader_account_balance,
        start_block_number=current_block_number
    )
    leader_out: LeaderOutPrivate = await leader_crud.complete_leader_activation(complete_leader_activation)
    return leader_out

@router.get("/balance_eligibility", response_model=LeaderBalanceEligibility)
async def get_balance_eligibility(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
    ) -> LeaderBalanceEligibility:
    leader_out: LeaderOutPrivate = await leader_crud.get_leader_by_id_private(LeaderGet(id=current_user))
    leader_address = leader_out.address
    # get the current block number
    try:
        subtensor = bt.AsyncSubtensor(NETWORK)
        # get the leader stakes
        stakes = await get_wallet_stakes(leader_address, async_subtensor=subtensor)
        subnets_info = await get_subnets_info(subtensor)
    except:
        raise HTTPException(status_code=500, detail=f"Subtensor connections overloaded. Please try again later.")
    leader_account_balance = await get_wallet_stakes_in_rao(subnets_info, stakes)
    if leader_account_balance < MINIMUM_STARTING_BALANCE:
        raise HTTPException(status_code=400, detail=f"Leader net account value of {round(leader_account_balance/1e9, 2)} TAO is less than the minimum starting balance of {round(MINIMUM_STARTING_BALANCE/1e9, 2)} TAO")
    if leader_account_balance > MAXIMUM_STARTING_BALANCE:
        raise HTTPException(status_code=400, detail=f"Leader net account value of {round(leader_account_balance/1e9, 2)} TAO is greater than the maximum starting balance of {round(MAXIMUM_STARTING_BALANCE/1e9, 2)} TAO")
    return LeaderBalanceEligibility(
        eligible=True,
        balance=round(leader_account_balance/1e9, 2)
    )

@router.patch("/bind_hotkey", response_model=LeaderOutPrivate, summary="[Admin] Bind a hotkey", description="Bind a hotkey to a leader")
async def bind_hotkey(
    bind_hotkey: LeaderSetHotkeyRequest,
    is_admin: bool = Depends(validate_admin_key)
    ) -> LeaderOutPrivate:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        # Check signature for the incoming hotkey request
        if not verify_signature(bind_hotkey.signature_payload):
            raise HTTPException(status_code=400, detail="Invalid signature")
        # check if the user exists
        user = await user_crud.get_user(UserGet(id=bind_hotkey.id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # check if the user is a leader
        if user.role != UserRole.LEADER:
            raise HTTPException(status_code=400, detail="User is not a leader")

        hotkey = bind_hotkey.signature_payload.address
        # check if the hotkey exists
        subnet_miner_hotkey = await subnet_miner_crud.get_hotkey(SubnetMinerHotkeyGet(hotkey=hotkey))
        if not subnet_miner_hotkey:
            raise HTTPException(status_code=404, detail="Hotkey not found")
        set_hotkey = LeaderSetHotkey(
            id=bind_hotkey.id,
            hotkey=hotkey
        )
        leader_out: LeaderOutPrivate = await leader_crud.set_hotkey(set_hotkey)
        return leader_out
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/unbind_hotkey", response_model=LeaderOutPrivate, summary="[Admin] Unbind a hotkey", description="Unbind a hotkey from a leader")
async def unbind_hotkey(
    unset_hotkey: LeaderUnsetHotkey,
    is_admin: bool = Depends(validate_admin_key)
    ) -> LeaderOutPrivate:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        # check if the user exists
        user = await user_crud.get_user(UserGet(id=unset_hotkey.id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # check if the user is a leader
        if user.role != UserRole.LEADER:
            raise HTTPException(status_code=400, detail="User is not a leader")
        leader_out: LeaderOutPrivate = await leader_crud.unset_hotkey(unset_hotkey)
        return leader_out
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# NOTE: we return user out because the leader is deleted
@router.delete("/demote_leader", response_model=UserOutPrivate)
async def demote_leader(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
    ) -> UserOutPrivate:
    demote_leader = LeaderDemote(
        id=current_user
    )
    user_out: UserOutPrivate = await leader_crud.demote_leader(demote_leader)
    return user_out

# NOTE: as leaders are initiated with starting balance 0, we need an admin endpoint to set the starting balance and leader status to active when the leader is done setting up their account
@router.patch("/set_starting_balance", response_model=LeaderOutPrivate, summary="[Admin] Set a starting balance", description="Set a starting balance for a leader")
async def set_starting_balance(
    set_starting_balance: LeaderSetStartingBalanceRequest,
    is_admin: bool = Depends(validate_admin_key)
    ) -> LeaderOutPrivate:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not set_starting_balance.start_block_number:
        set_starting_balance.start_block_number = await get_current_block_number()
    set_starting_balance = LeaderSetStartingBalance(
        id=set_starting_balance.id,
        account_starting_balance=set_starting_balance.account_starting_balance,
        start_block_number=set_starting_balance.start_block_number
    )
    leader_out: LeaderOutPrivate = await leader_crud.set_starting_balance(set_starting_balance)
    return leader_out

# NOTE: this is a public endpoint that anyone can access
@router.get("/{leader_id}", response_model=LeaderPublicProfileData)
async def get_leader_profile_data(
    leader_id: UUID4,
) -> LeaderPublicProfileData:
    return await fetch_public_leader_data(leader_id)

# returns the top 10 leaderboard
# NOTE: this router path is a workaround to avoid conflicts in the nginx routing
@router.get("board")
async def get_leaderboard_data() -> List[LeaderPublicProfileData]:
    leader_uuids = await leader_metrics_crud.get_active_leader_uuids(LeaderboardMetricsGet(top_n=TOP_LEADERBOARD_SIZE))
    return [await fetch_public_leader_data(leader_id) for leader_id in leader_uuids]

# returns all the leaderboard data
# NOTE: this router path is a workaround to avoid conflicts in the nginx routing
@router.get("board/all")
async def get_all_leaderboard_data() -> List[LeaderPublicProfileData]:
    leader_uuids = await leader_metrics_crud.get_active_leader_uuids(LeaderboardMetricsGet())
    return [await fetch_public_leader_data(leader_id) for leader_id in leader_uuids]


@router.patch("/deactivate_leader", response_model=LeaderOutPrivate, summary="[Admin] Deactivate a leader", description="Deactivate a leader by setting their status to inactive")
async def deactivate_leader(
    deactivate_leader: LeaderDeactivate,
    is_admin: bool = Depends(validate_admin_key)
    ) -> LeaderOutPrivate:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    leader_out: LeaderOutPrivate = await leader_crud.deactivate_leader(deactivate_leader)
    return leader_out

@router.patch("/violate_leader", response_model=LeaderOutPrivate, summary="[Admin] Violate a leader", description="Violate a leader by setting their status to violated")
async def violate_leader(
    violate_leader: LeaderAdminViolate,
    is_admin: bool = Depends(validate_admin_key)
    ) -> LeaderOutPrivate:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        leader_out: LeaderOutPrivate = await leader_crud.admin_violate_leader(LeaderAdminViolate(id=violate_leader.id, message=violate_leader.message))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return leader_out

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Yield Leader Management API",
    description="API for managing leaders",
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

