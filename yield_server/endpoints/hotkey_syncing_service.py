import bittensor as bt

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.types import UUID4
from typing import Union, Optional, List

from yield_server.backend.schema.subnetminerhotkey_schema import (
    SubnetMinerHotkeyOut,
    SubnetMinerHotkeyCreate,
    SubnetMinerHotkeyDeregister,
    SubnetMinerHotkeyRemove,
    SubnetMinerHotkeyGet
)
from yield_server.middleware.admin_middleware import validate_admin_key
from yield_server.middleware.jwt_middleware import enforce_user_id_from_jwt
from yield_server.backend.crud.subnetminerhotkey_crud import SubnetMinerHotkeyCRUD

router = APIRouter(prefix="/api/v1/hotkey", tags=["hotkey"])

subnet_miner_hotkey_crud = SubnetMinerHotkeyCRUD()

@router.post("/create_hotkey", summary="[Admin] Create a hotkey", description="Create a hotkey for a subnet miner")
async def create_test_hotkey(
    create_hotkey: SubnetMinerHotkeyCreate,
    is_admin: bool = Depends(validate_admin_key)
) -> SubnetMinerHotkeyOut:
    try:
        subnet_miner_hotkey = await subnet_miner_hotkey_crud.register_hotkey(create_hotkey)
        return subnet_miner_hotkey
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_all_hotkeys", summary="Get all hotkeys", description="Get all hotkeys for a subnet miner")
async def get_all_hotkeys(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> List[SubnetMinerHotkeyOut]:
    # NOTE: we simply use the jwt to ensure that the user is authenticated but the hotkey information is available to all users
    subnet_miner_hotkeys = await subnet_miner_hotkey_crud.get_all_hotkeys()
    return subnet_miner_hotkeys

@router.get("/get_hotkey/{hotkey}")
async def get_hotkey(
    hotkey: str,
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> SubnetMinerHotkeyOut:
    # NOTE: we simply use the jwt to ensure that the user is authenticated but the hotkey information is available to all users
    get_hotkey = SubnetMinerHotkeyGet(hotkey=hotkey)
    try:
        subnet_miner_hotkey = await subnet_miner_hotkey_crud.get_hotkey(get_hotkey)
        return subnet_miner_hotkey
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/remove_hotkey", summary="[Admin] Remove a hotkey", description="Remove a hotkey for a subnet miner")
async def remove_hotkey(
    remove_hotkey: SubnetMinerHotkeyRemove,
    is_admin: bool = Depends(validate_admin_key)
) -> bool:
    return await subnet_miner_hotkey_crud.remove_hotkey(remove_hotkey)

@router.put("/deregister_hotkey", summary="[Admin] Deregister a hotkey", description="Deregister a hotkey for a subnet miner")
async def deregister_hotkey(
    deregister_hotkey: SubnetMinerHotkeyDeregister,
    is_admin: bool = Depends(validate_admin_key)
) -> SubnetMinerHotkeyOut:
    try:
        subnet_miner_hotkey = await subnet_miner_hotkey_crud.deregister_hotkey(deregister_hotkey)
        return subnet_miner_hotkey
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Yield Hotkey Syncing API",
    description="API for syncing hotkeys",
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

