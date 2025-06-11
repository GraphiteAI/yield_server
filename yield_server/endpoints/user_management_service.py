from yield_server.backend.crud.user_crud import UserCRUD, UserCreateResponse
from yield_server.backend.schema.user_schema import (
    UserCreate, UserUpdate, UserRemove, UserGet, UserOutPrivate, UserGetByAddress
)

from yield_server.utils.signing_utils import UnverifiedSignaturePayload, verify_signature
from yield_server.utils.session_utils import user_login, user_logout, refresh_session
from yield_server.utils.registration_utils import reset_password

from yield_server.middleware.jwt_middleware import validate_user_jwt
from yield_server.middleware.admin_middleware import validate_admin_key

from gotrue.errors import AuthApiError
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pydantic.types import UUID4

router = APIRouter(prefix="/api/v1/session", tags=["session"])

user_crud = UserCRUD()

class UserCreationRequest(BaseModel):
    signature_payload: UnverifiedSignaturePayload
    password: str

# NOTE: this model request should only be used for development purposes
class UserCreationAdminRequest(BaseModel):
    address: str
    password: str

class UserUpdatePasswordRequest(BaseModel):
    signature_payload: UnverifiedSignaturePayload
    password: str

class UserUpdatePasswordResponse(BaseModel):
    uuid: UUID4

class UserLoginRequest(BaseModel):
    address: str
    password: str

class UserLoginResponse(BaseModel):
    jwt: str
    refresh_token: str
    uuid: UUID4

class UserRefreshRequest(BaseModel):
    refresh_token: str

class UserLogoutResponse(BaseModel):
    message: str

class UserRefreshResponse(BaseModel):
    jwt: str
    refresh_token: str
    uuid: UUID4

class UserDeleteResponse(BaseModel):
    message: str

@router.post("/create_user", response_model=UserCreateResponse, summary="[Admin] Create a user", description="Create a user")
async def create_user(user_creation_request: UserCreationRequest) -> UserCreateResponse:
    if not verify_signature(user_creation_request.signature_payload):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # check if the user already exists
    user = await user_crud.get_user_by_address(get_user_by_address=UserGetByAddress(address=user_creation_request.signature_payload.address))
    if user:
        raise HTTPException(status_code=400, detail="User already exists")
    else:
        user = UserCreate(address=user_creation_request.signature_payload.address, password=user_creation_request.password)
        try:
            created_user, user_creation_response = await user_crud.create_user(user)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating user: {e}")
        return user_creation_response

# NOTE: this endpoint should only be used for development purposes
@router.post("/development/admin/create_user", response_model=UserCreateResponse, summary="[Admin] Create a user", description="Create a user for development purposes")
async def create_user_admin(
    user_creation_request: UserCreationAdminRequest,
    is_admin: bool = Depends(validate_admin_key)
    ) -> UserCreateResponse:
    if not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # check if the user already exists
    user = await user_crud.get_user_by_address(get_user_by_address=UserGetByAddress(address=user_creation_request.address))
    if user:
        raise HTTPException(status_code=400, detail="User already exists")
    else:
        user = UserCreate(address=user_creation_request.address, password=user_creation_request.password)
        try:
            created_user, user_creation_response = await user_crud.create_user(user)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating user: {e}")
        return user_creation_response
    
@router.post("/login", response_model=UserLoginResponse, summary="[User] Login a user", description="Login a user")
async def login_user(user_login_request: UserLoginRequest) -> UserLoginResponse:
    '''
    Args:
        user_login_request (UserLoginRequest): The request body containing the coldkey and password
    
    Returns:
        dict: The JWT token and the refresh token
    '''
    try:
        session = await user_login(user_login_request.address, user_login_request.password)
    except AuthApiError as e:
        raise HTTPException(status_code=401, detail=f"Invalid credentials: {e.message}")
    return UserLoginResponse(
        jwt=session["session"]["access_token"], 
        refresh_token=session["session"]["refresh_token"], 
        uuid=session["user"]["id"]
        )

# NOTE: we use DELETE here because we are conceptually deleting the current session for this current user
@router.delete("/logout", response_model=UserLogoutResponse)
async def logout_user(
    session_jwt: str = Depends(validate_user_jwt)
):
    try:
        await user_logout(session_jwt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error logging out user: {e}")
    return UserLogoutResponse(message="User logged out successfully")

@router.patch("/update_password", response_model=UserUpdatePasswordResponse)
async def update_password(user_update_password_request: UserUpdatePasswordRequest) -> UserUpdatePasswordResponse:
    try:
        # validate the signature
        if not verify_signature(user_update_password_request.signature_payload):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # get the user
        user = await user_crud.get_user_by_address(get_user_by_address=UserGetByAddress(address=user_update_password_request.signature_payload.address))
        if user is None:
            raise HTTPException(status_code=404, detail="User not found | Please sign up for the Yield platform first")
        
        # update the password
        try:
            updated_supabase_user: dict = await reset_password(user.id, user_update_password_request.password)
        except AuthApiError as e:
            raise HTTPException(status_code=500, detail=f"Error updating password on Supabase: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating password: {e}")
    return UserUpdatePasswordResponse(
        uuid=updated_supabase_user["user"]["id"]
        )

# NOTE: using PUT here because we are replacing the current session with a new one for this current user
@router.put("/refresh_session", response_model=UserRefreshResponse)
async def refresh_user_session(
    user_refresh_request: UserRefreshRequest
    ) -> UserRefreshResponse:
    try:
        session = await refresh_session(user_refresh_request.refresh_token)
    except AuthApiError as e:
        raise HTTPException(status_code=401, detail=f"Invalid refresh token: {e.message}")
    return UserRefreshResponse(
        jwt=session["session"]["access_token"], 
        refresh_token=session["session"]["refresh_token"], 
        uuid=session["user"]["id"]
        )

@router.delete("/delete_user/{user_id}", response_model=UserDeleteResponse, summary="[Admin] Delete a user", description="Delete a user")
async def delete_user(
    user_id: UUID4,
    is_admin: bool = Depends(validate_admin_key)
    ) -> UserDeleteResponse:
    try:
        if is_admin:
            # check if the user exists
            user = await user_crud.get_user(get_user=UserGet(id=user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
            # delete the user
            success = await user_crud.remove_user(remove_user=UserRemove(id=user_id))
            if success:
                return UserDeleteResponse(message="User deleted successfully")
            else:
                raise HTTPException(status_code=400, detail="User not found")
        else:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {e}")

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

