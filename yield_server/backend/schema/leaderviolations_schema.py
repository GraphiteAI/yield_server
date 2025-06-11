from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import UUID4
from typing import Optional
from datetime import datetime

class LeaderViolationBase(BaseModel):
    leader_id: UUID4
    violation_message: str
    created_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        )
    
class LeaderViolationCreate(LeaderViolationBase):
    pass

class LeaderViolationOut(LeaderViolationBase):
    updated_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra = "ignore",
        arbitrary_types_allowed = True,
        )
    