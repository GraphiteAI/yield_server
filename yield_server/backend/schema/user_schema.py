from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.types import UUID4
from typing import Literal
from bittensor.utils import is_valid_ss58_address

from yield_server.backend.database.models import UserRole

class UserBase(BaseModel):
    address: str
    role: UserRole

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
    @field_validator("address")
    def validate_address(cls, v):
        if not is_valid_ss58_address(v):
            raise ValueError("Invalid SS58 address")
        return v

class UserCreate(UserBase):
    role: Literal[UserRole.GENERIC] = UserRole.GENERIC
    password: str
    
class UserUpdate(UserBase):
    ...

class UserRemove(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class UserGet(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class UserGetByAddress(BaseModel):
    address: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class UserOutPrivate(UserBase):
    id: UUID4
    created_at: int
    updated_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class UserGetRole(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )