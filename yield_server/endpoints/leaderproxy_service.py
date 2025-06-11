'''
[DEPRECATED]

DO NOT RUN THIS SERVICE --> This service is not longer used
'''

from yield_server.backend.crud.leaderproxy_crud import LeaderProxyCRUD
from yield_server.backend.schema.leaderproxy_schema import (
    LeaderProxyCreate, LeaderProxyGet, LeaderProxyGetByLeader, LeaderProxyOut
)

from yield_server.utils.signing_utils import UnverifiedSignaturePayload, verify_signature

from yield_server.middleware.jwt_middleware import validate_user_jwt
from yield_server.middleware.admin_middleware import validate_admin_key

from gotrue.errors import AuthApiError
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pydantic.types import UUID4

router = APIRouter(prefix="/api/v1/leaderproxy", tags=["leaderproxy"])

leaderproxy_crud = LeaderProxyCRUD()

class LeaderProxyCreateRequest(BaseModel):
    signature_payload: UnverifiedSignaturePayload

class LeaderProxyCreateResponse(BaseModel):
    uuid: UUID4


@router.post("/create_proxy", response_model=LeaderProxyCreateResponse)
async def create_proxy(leaderproxy_creation_request: LeaderProxyCreateRequest,
                       is_admin: bool = Depends(validate_admin_key)) -> LeaderProxyCreateResponse:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # check if the user already exists
    user = await leaderproxy_crud.get_proxy(get_user_by_address=LeaderProxyGet(proxy_id=leaderproxy_creation_request.signature_payload.address))
    if user:
        raise HTTPException(status_code=400, detail="User already exists")
    else:
        user = LeaderProxyCreate(proxy_id=leaderproxy_creation_request.signature_payload.address, leader_id=leaderproxy_creation_request.signature_payload.address)
        try:
            leaderproxy_creation_response: LeaderProxyOut = await leaderproxy_crud.create_proxy(user)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating user: {e}")
        return leaderproxy_creation_response

@router.get("/get_proxy", response_model=LeaderProxyOut)
async def get_proxy(get_proxy: LeaderProxyGet,
                    is_admin: bool = Depends(validate_admin_key)) -> LeaderProxyOut:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await leaderproxy_crud.get_proxy(get_proxy)

@router.get("/get_proxy_by_leader", response_model=LeaderProxyOut)
async def get_proxy_by_leader(get_leader_proxy: LeaderProxyGetByLeader,
                              is_admin: bool = Depends(validate_admin_key)) -> LeaderProxyOut:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await leaderproxy_crud.get_proxy_by_leader(get_leader_proxy)

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Yield User Management API",
    description="API for managing users and their sessions",
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

