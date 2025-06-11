from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import UUID4
from typing import Optional
from datetime import datetime

class LeaderRestrictionBase(BaseModel):
    leader_id: UUID4
    first_non_violated_trading_block_number: int
    first_no_trade_block_number: int
    last_no_trade_block_number: int

    model_config = ConfigDict(
        from_attributes=True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        )
    
class LeaderRestrictionCreate(LeaderRestrictionBase):
    pass

class LeaderRestrictionOut(LeaderRestrictionBase):
    pass

class LeaderRestrictionUpdate(BaseModel):
    leader_id: UUID4
    transaction_block_number: int
    extrinsic_hash: str

    model_config = ConfigDict(
        from_attributes=True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        )