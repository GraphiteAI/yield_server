from yield_server.backend.database.models import User, UserRole
from yield_server.backend.schema.user_schema import (
    UserCreate, 
    UserUpdate, 
    UserRemove, 
    UserOutPrivate, 
    UserGet,
    UserGetByAddress,
    UserGetRole
)

from yield_server.utils.time import get_timestamp
from yield_server.utils.registration_utils import create_new_user, delete_user
from yield_server.backend.database.db import async_session

from typing import Optional, Tuple, List
from pydantic import BaseModel
from pydantic.types import UUID4
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

class UserCreateResponse(BaseModel):
    uuid: UUID4
    jwt: str
    refresh_token: str

class UserCRUD:
    '''
    CRUD operations for the User model.
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session

    async def create_user(self, create_user: UserCreate) -> Tuple[UserOutPrivate, UserCreateResponse]:
        current_ts = get_timestamp()
        user_uuid = None
        try:
            async with self.session.begin() as session:
                supabase_session = await create_new_user(create_user.address, create_user.password)
                user_uuid = supabase_session["user"]["id"]
                jwt = supabase_session["session"]["access_token"]
                refresh_token = supabase_session["session"]["refresh_token"]
                new_user = User(
                    id=user_uuid,
                    address=create_user.address,
                    role=create_user.role,
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(new_user)
                await session.flush()
                await session.refresh(new_user)
                return UserOutPrivate.model_validate(new_user), UserCreateResponse(
                    uuid=user_uuid,
                    jwt=jwt,
                    refresh_token=refresh_token
                )
        except Exception as e:
            if user_uuid:
                # TODO: implement re-try logic here to make this more robust
                await delete_user(user_uuid)
            raise e

        
    async def update_user(self, update_user: UserUpdate) -> UserOutPrivate:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            user_query = await session.get(User, update_user.id)
            if not user_query:
                raise ValueError("User not found")
            
            user_query.address = update_user.address
            user_query.role = update_user.role
            user_query.updated_at = current_ts
            
            await session.flush()
            await session.refresh(user_query)
            return UserOutPrivate.model_validate(user_query)
        
    async def remove_user(self, remove_user: UserRemove) -> bool:
        async with self.session.begin() as session:
            # first attempt to delete the user from supabase
            await delete_user(remove_user.id)
            stmt = delete(User).where(User.id == remove_user.id)
            result = await session.execute(stmt)
            if not result.rowcount:
                return False
            return result.rowcount > 0
        
    async def get_user(self, get_user: UserGet) -> Optional[UserOutPrivate]:
        async with self.session.begin() as session:
            user_query = await session.get(User, get_user.id)
            if not user_query:
                return None
            return UserOutPrivate.model_validate(user_query)
            
    async def get_user_by_address(self, get_user_by_address: UserGetByAddress) -> Optional[UserOutPrivate]:
        async with self.session.begin() as session:
            user_query = await session.execute(select(User).filter(User.address == get_user_by_address.address))
            user_query = user_query.scalar_one_or_none()
            if not user_query:
                return None
            return UserOutPrivate.model_validate(user_query)

    async def get_user_role(self, get_user_role: UserGetRole) -> Optional[UserRole]:
        async with self.session.begin() as session:
            user_query = await session.execute(select(User).filter(User.id == get_user_role.id))
            user_query = user_query.scalar_one_or_none()
            if not user_query:
                return None
            return user_query.role
        
    async def get_user_address(self, get_user_role: UserGetRole) -> str:
        async with self.session.begin() as session:
            user_query = await session.execute(select(User).filter(User.id == get_user_role.id))
            user_query = user_query.scalar_one_or_none()
            if not user_query:
                return None
            return user_query.address

    async def get_all_users(self) -> List[UserOutPrivate]:
        async with self.session.begin() as session:
            user_query = await session.execute(select(User))
            user_query = user_query.scalars().all()
            return [UserOutPrivate.model_validate(user) for user in user_query]