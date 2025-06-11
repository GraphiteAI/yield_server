from yield_server.config.constants import LOOKBACK_DAYS
from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import UUID4
from datetime import datetime, date
from typing import Optional

class CopyTraderMetricsBase(BaseModel):
    copytrader_id: UUID4
    pnl: float
    pnl_percent: float
    volume: float
    total_assets: float

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )
    
class CopyTraderMetricsCreate(CopyTraderMetricsBase):
    ...

class CopyTraderPortfolioValueInRao(BaseModel):
    copytrader_id: UUID4
    portfolio_value: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class CopyTraderMetricsVolumeUpdate(BaseModel):
    copytrader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class CopyTraderMetricsUpdate(CopyTraderMetricsBase):
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    volume: Optional[float] = None
    total_assets: Optional[float] = None

# NOTE: this is not used anywhere because our current implementation cascades the deletion of the copytrader_metrics record when the copytrader record is deleted
class CopyTraderMetricsRemove(BaseModel):
    copytrader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

# NOTE: there is no public version of this schema unlike for the leader_metrics
class CopyTraderMetricsOut(CopyTraderMetricsBase):
    created_at: int
    updated_at: int

class CopyTraderMetricsGet(BaseModel):
    copytrader_id: UUID4

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class CopyTraderMetricsHistoryGet(CopyTraderMetricsGet):
    periods: int = Field(default=LOOKBACK_DAYS)

class CopyTraderMetricsSnapshotGet(BaseModel):
    copytrader_id: UUID4
    snapshot_date: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        )

class CopyTraderMetricsSnapshotBase(BaseModel):
    pnl: float
    pnl_percent: float
    volume: float
    total_assets: float

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        )

class CopyTraderMetricsSnapshotCreate(CopyTraderMetricsBase):
    copytrader_id: UUID4
    snapshot_date: datetime

class CopyTraderMetricsSnapshotUpdate(CopyTraderMetricsSnapshotCreate):
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    volume: Optional[float] = None
    total_assets: Optional[float] = None
    snapshot_date: Optional[datetime] = None

class CopyTraderMetricsSnapshotOut(CopyTraderMetricsSnapshotBase):
    snapshot_date: datetime
    copytrader_id: UUID4
    
    created_at: int
    updated_at: int
