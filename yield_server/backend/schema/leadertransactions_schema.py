from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import UUID4
from typing import Optional
from datetime import datetime

class LeaderTransactionBase(BaseModel):
    leader_id: UUID4
    call_function: str
    block_number: int
    extrinsic_hash: str

    model_config = ConfigDict(
        from_attributes=True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        )
    
class LeaderTransactionCreate(LeaderTransactionBase):
    pass

class LeaderTransactionOut(LeaderTransactionBase):
    created_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra = "ignore",
        arbitrary_types_allowed = True,
        )