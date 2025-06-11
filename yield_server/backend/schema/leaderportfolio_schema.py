from yield_server.config.constants import LOOKBACK_DAYS

from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import UUID4
from typing import Optional
from datetime import datetime

class LeaderPortfolioBase(BaseModel):
    leader_id: UUID4
    portfolio_distribution: dict[int, float]
    portfolio_hash: str

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        extra="forbid"
    )

class LeaderPortfolioUpsert(LeaderPortfolioBase):
    ...

class LeaderPortfolioOut(LeaderPortfolioBase):
    created_at: int
    updated_at: int

class LeaderPortfolioGet(BaseModel):
    leader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        extra="forbid"
    )

