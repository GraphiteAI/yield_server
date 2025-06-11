from yield_server.config.constants import LOOKBACK_DAYS

from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import UUID4
from typing import Optional
from datetime import datetime

class LeaderMetricsBase(BaseModel):
    leader_id: UUID4
    total_assets: float
    pnl: float
    pnl_percent: float
    sharpe_ratio: float = Field(default=0)
    drawdown: float = Field(default=0)
    volume: float = Field(default=0)
    num_copy_traders: int # set this on any update based a query of all copytraders
    rank: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class LeaderMetricsCreate(LeaderMetricsBase):
    notional_value_of_copy_traders: float

class LeaderMetricsUpdate(LeaderMetricsBase):
    total_assets: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    drawdown: Optional[float] = None
    volume: Optional[float] = None
    num_copy_traders: Optional[int] = None
    notional_value_of_copy_traders: Optional[float] = None
    rank: Optional[int] = None

class LeaderMetricsRemove(BaseModel):
    leader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class LeaderMetricsOut(LeaderMetricsBase): # NOTE: there is no private version of metrics
    created_at: int
    updated_at: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        )
    
class LeaderMetricsOutForValidator(LeaderMetricsOut): # NOTE: there is no private version of metrics
    notional_value_of_copy_traders: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        )

class LeaderMetricsOutPrivate(LeaderMetricsOut):
    notional_value_of_copy_traders: float

class LeaderMetricsGet(BaseModel):
    leader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class LeaderMetricsHistoryGet(LeaderMetricsGet):
    periods: int = Field(default=LOOKBACK_DAYS)

class LeaderMetricsSnapshotGet(BaseModel):
    leader_id: UUID4
    snapshot_date: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
class LeaderMetricsSnapshotBase(BaseModel):
    total_assets: float
    pnl: float
    pnl_percent: float
    sharpe_ratio: float
    drawdown: float
    volume: float
    num_copy_traders: int
    notional_value_of_copy_traders: float
    rank: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        )

class LeaderMetricsSnapshotCreate(LeaderMetricsSnapshotBase):
    leader_id: UUID4
    snapshot_date: datetime
    notional_value_of_copy_traders: float

class LeaderMetricsSnapshotUpdate(LeaderMetricsSnapshotBase):
    total_assets: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    drawdown: Optional[float] = None
    volume: Optional[float] = None
    num_copy_traders: Optional[int] = None
    notional_value_of_copy_traders: Optional[float] = None
    rank: Optional[int] = None
    snapshot_date: Optional[datetime] = None

class LeaderMetricsSnapshotOut(LeaderMetricsSnapshotBase):
    snapshot_date: datetime
    leader_id: UUID4

    created_at: int
    updated_at: int

class LeaderMetricsSnapshotOutPrivate(LeaderMetricsSnapshotOut):
    notional_value_of_copy_traders: float

class LeaderboardMetricsGet(BaseModel):
    top_n: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class LeaderPortfolioValueInRao(BaseModel):
    leader_id: UUID4
    portfolio_value: float

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )