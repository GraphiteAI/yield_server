from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.types import UUID4
from typing import Optional, Literal
from yield_server.backend.database.models import UserRole, LeaderStatus
from yield_server.utils.signing_utils import UnverifiedSignaturePayload
from names_generator import generate_name
from bittensor.utils import is_valid_ss58_address

class LeaderBase(BaseModel):
    id: UUID4
    role: UserRole
    alias: str = Field(default_factory=generate_name) # setting random name if unset

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True
        )

class LeaderCreate(LeaderBase):
    role: Literal[UserRole.LEADER] = Field(default=UserRole.LEADER, frozen=True)
    account_starting_balance: float
    start_block_number: int

class LeaderSetHotkey(BaseModel):
    id: UUID4
    hotkey: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
class LeaderUnsetHotkey(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
# NOTE: The current implementation does not cover any public information about copytraders (i.e. no data to serve without authentication)
class LeaderOutPrivate(LeaderBase):
    address: str
    hotkey: Optional[str] = None
    status: LeaderStatus
    account_starting_balance: float
    start_block_number: int
    last_checked_block_number: Optional[int] = None
    proxy_address: Optional[str] = None
    
    created_at: int
    updated_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        
        )

class LeaderGetByHotkey(BaseModel):
    hotkey: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True
    )

    @field_validator("hotkey")
    def validate_hotkey(cls, v):
        if not is_valid_ss58_address(v):
            raise ValueError("Invalid hotkey")
        return v
        
class LeaderOutPublic(LeaderBase):
    hotkey: Optional[str] = None
    status: LeaderStatus
    account_starting_balance: float # NOTE: we might not want to expose this information
    start_block_number: int # NOTE: we might not want to expose this information

    created_at: int
    updated_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        
        )
    
class LeaderViolated(BaseModel):
    id: UUID4
    role: Literal[LeaderStatus.VIOLATED] = LeaderStatus.VIOLATED

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class LeaderDeregistered(BaseModel):
    id: UUID4
    role: Literal[LeaderStatus.DEREGISTERED] = LeaderStatus.DEREGISTERED

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class LeaderGet(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class LeaderUpdateBlock(BaseModel):
    id: UUID4
    last_checked_block_number: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class LeaderUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[LeaderStatus] = None
    hotkey: Optional[str] = None
    alias: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class LeaderDemote(BaseModel):
    id: UUID4
    role: Literal[UserRole.GENERIC] = UserRole.GENERIC
    status: Literal[LeaderStatus.INACTIVE] = LeaderStatus.INACTIVE

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
class LeaderSetStartingBalance(BaseModel):
    id: UUID4
    account_starting_balance: float
    start_block_number: int

class LeaderActivate(BaseModel):
    id: UUID4
    status: Literal[LeaderStatus.ACTIVE] = LeaderStatus.ACTIVE
    
class LeaderDeactivate(BaseModel):
    id: UUID4
    status: Literal[LeaderStatus.INACTIVE] = LeaderStatus.INACTIVE

class LeaderCompleteActivation(BaseModel):
    id: UUID4
    hotkey: str
    account_starting_balance: float
    start_block_number: int

class LeaderAdminViolate(BaseModel):
    id: UUID4
    message: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

class LeaderGetByProxy(BaseModel):
    proxy_address: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True)