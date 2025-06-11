from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal
from yield_server.backend.database.models import MinerStatus, HotkeyBoundStatus
from bittensor.utils import is_valid_ss58_address

class SubnetMinerHotkeyBase(BaseModel):
    hotkey: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
    @field_validator("hotkey")
    def validate_hotkey(cls, v):
        if not is_valid_ss58_address(v):
            raise ValueError("Invalid SS58 address")
        return v

class SubnetMinerHotkeyCreate(SubnetMinerHotkeyBase):
    status: Literal[MinerStatus.REGISTERED] = MinerStatus.REGISTERED
    bound_status: Literal[HotkeyBoundStatus.UNBOUND] = HotkeyBoundStatus.UNBOUND

class SubnetMinerHotkeyUpdate(SubnetMinerHotkeyBase):
    status: MinerStatus

class SubnetMinerHotkeyRemove(BaseModel):
    hotkey: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )

class SubnetMinerHotkeyOut(SubnetMinerHotkeyBase):
    status: MinerStatus
    bound_status: HotkeyBoundStatus
    created_at: int
    updated_at: int

class SubnetMinerHotkeyGet(BaseModel):
    hotkey: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )
    
class SubnetMinerHotkeyDeregister(BaseModel):
    hotkey: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        
        )