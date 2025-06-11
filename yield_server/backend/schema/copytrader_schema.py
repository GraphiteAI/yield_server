from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import UUID4
from typing import Literal, Optional

from yield_server.backend.database.models import UserRole

class CopyTraderBase(BaseModel):
    id: UUID4
    role: UserRole

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class CopyTraderCreate(CopyTraderBase):
    role: UserRole = Literal[UserRole.COPYTRADER]
    account_starting_balance: int = Field(..., description="The starting balance of the copytrader's account")
    last_proxy_block: int = Field(..., description="The block number of the last proxy")
    next_rebalance_block: int = Field(..., description="The block number of the next rebalance")

class CopyTraderChooseLeader(BaseModel):
    id: UUID4
    leader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

# the information required for the copytrader to begin copying a leader
class CopyTraderProxyBindOut(CopyTraderBase):
    chosen_leader_id: UUID4 = Field(..., description="The id of the leader to bind to for the copytrader")
    chosen_leader_alias: str = Field(..., description="The alias of the leader to bind to for the copytrader")
    target_proxy: str = Field(..., description="The address of the proxy to bind to for the copytrader")

class CopyTraderGet(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
# NOTE: The current implementation does not cover any public information about copytraders (i.e. no data to serve without authentication)
class CopyTraderOut(CopyTraderProxyBindOut):
    chosen_leader_id: Optional[UUID4] = Field(None, description="The id of the leader to bind to for the copytrader")
    chosen_leader_alias: Optional[str] = Field(None, description="The alias of the leader to bind to for the copytrader")
    target_proxy: Optional[str] = Field(None, description="The address of the proxy to bind to for the copytrader")
    address: str

    created_at: int
    updated_at: int
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        
        )
    
class CopyTraderRebalanceOut(CopyTraderBase):
    chosen_leader_id: UUID4
    target_proxy: str
    address: str
    next_rebalance_block: int

class CopyTraderDemote(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class CopyTraderSetProxy(BaseModel):
    id: UUID4
    copytrader_address: str
    target_proxy: str
    extrinsic_hash: str
    block_number: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class CopyTraderRemoveProxy(BaseModel):
    id: UUID4
    copytrader_address: str
    extrinsic_hash: str
    block_number: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class CopyTraderUpdatePortfolioHash(BaseModel):
    id: UUID4
    portfolio_hash: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class CopyTraderSetRebalanceCooldown(BaseModel):
    id: UUID4
    next_rebalance_block: int
    rebalance_attempts: int = 0 # reset rebalance attempts to 0

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class CopyTraderSetRebalanceSuccess(BaseModel):
    id: UUID4
    portfolio_hash: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid", 
        arbitrary_types_allowed=True,
        )

class CopyTraderSetRebalanceFailure(BaseModel):
    id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class CopyTraderSetRebalanceCooldown(BaseModel):
    id: UUID4
    next_rebalance_block: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class CopyTraderSetRebalanceFailure(BaseModel):
    id: UUID4
    block_number: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class CopyTraderSetRebalanceSuccess(CopyTraderSetRebalanceFailure):
    portfolio_hash: str
    extrinsic_hash: str
    leader_proxy_id: str
    volume: int

class SetCopyTraderForRebalancing(BaseModel):
    id: UUID4
    portfolio_hash: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )