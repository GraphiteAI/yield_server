from yield_server.backend.database.models import ProxyBoundStatus
from yield_server.config.constants import SS58_ADDRESS_LENGTH

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.types import UUID4
from typing import Optional
from bittensor.utils import is_valid_ss58_address

class LeaderProxyBase(BaseModel):
    proxy_id: str
    leader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
    @field_validator("proxy_id")
    def validate_proxy_id(cls, v):
        if not is_valid_ss58_address(v):
            raise ValueError("Proxy ID must be a valid SS58 address")
        return v

class LeaderProxyCreate(LeaderProxyBase):
    proxy_bound_status: Optional[ProxyBoundStatus] = Field(default=ProxyBoundStatus.UNBOUND)

class LeaderProxyOut(LeaderProxyBase):
    leader_id: Optional[UUID4]
    balance: Optional[int]
    created_at: int
    updated_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        
        )

class LeaderProxyGet(BaseModel):
    proxy_id: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
class LeaderProxyGetByLeader(BaseModel):
    leader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class LeaderProxyUpdateBalance(BaseModel):
    proxy_id: str
    balance: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )