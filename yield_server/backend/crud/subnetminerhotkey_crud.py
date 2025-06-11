from yield_server.backend.database.models import (
    SubnetMinerHotkey, 
    MinerStatus,
    Leader,
    LeaderViolation,
    LeaderStatus,
    LeaderProxy
)
from yield_server.backend.schema.subnetminerhotkey_schema import (
    SubnetMinerHotkeyCreate, 
    SubnetMinerHotkeyUpdate, 
    SubnetMinerHotkeyRemove,
    SubnetMinerHotkeyOut,
    SubnetMinerHotkeyGet,
    SubnetMinerHotkeyDeregister
)
from yield_server.utils.time import get_timestamp
from yield_server.backend.database.db import async_session
from yield_server.errors.leader_violation_exceptions import BoundHotkeyDeregistrationException

from sqlalchemy import update, delete, select
from sqlalchemy.orm import selectinload
from pydantic.types import UUID4
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

class SubnetMinerHotkeyCRUD:
    def __init__(self, session: AsyncSession = async_session):
        self.session = session
    
    async def register_hotkey(self, hotkey: SubnetMinerHotkeyCreate) -> SubnetMinerHotkeyOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            # check if hotkey already exists
            existing_hotkey = await session.get(SubnetMinerHotkey, hotkey.hotkey)
            if existing_hotkey:
                # if the hotkey is already registered, we update the status
                existing_hotkey.status = hotkey.status
                existing_hotkey.updated_at = current_ts
                return SubnetMinerHotkeyOut.model_validate(existing_hotkey)
            else:
                new_hotkey = SubnetMinerHotkey(
                    hotkey=hotkey.hotkey,
                    status=hotkey.status,
                    created_at=current_ts,
                    updated_at=current_ts
                    )
                
                session.add(new_hotkey)
                await session.flush()
                await session.refresh(new_hotkey)
                return SubnetMinerHotkeyOut.model_validate(new_hotkey)
        
    async def update_hotkey(self, hotkey: SubnetMinerHotkeyUpdate) -> SubnetMinerHotkeyOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            stmt = update(SubnetMinerHotkey).where(SubnetMinerHotkey.hotkey == hotkey.hotkey)
            stmt = stmt.values(status=hotkey.status, updated_at=current_ts)
            await session.execute(stmt)
            updated_hotkey = await session.get(SubnetMinerHotkey, hotkey.hotkey)
            if not updated_hotkey:
                raise ValueError("Hotkey not found")
            return SubnetMinerHotkeyOut.model_validate(updated_hotkey)
        
    async def get_hotkey(self, hotkey: SubnetMinerHotkeyGet) -> SubnetMinerHotkeyOut:
        async with self.session.begin() as session:
            hotkey = await session.get(SubnetMinerHotkey, hotkey.hotkey)
            if not hotkey:
                raise ValueError("Hotkey not found")
            return SubnetMinerHotkeyOut.model_validate(hotkey)
        
    async def remove_hotkey(self, hotkey: SubnetMinerHotkeyRemove) -> bool:
        async with self.session.begin() as session:
            stmt = delete(SubnetMinerHotkey).where(SubnetMinerHotkey.hotkey == hotkey.hotkey)
            result = await session.execute(stmt)
            if not result.rowcount:
                raise ValueError("Hotkey not found")
            return result.rowcount > 0
        
    async def get_all_hotkeys(self) -> List[SubnetMinerHotkeyOut]:
        async with self.session.begin() as session:
            get_hotkeys_result = await session.execute(select(SubnetMinerHotkey))
            hotkeys = get_hotkeys_result.scalars().all()
            return [SubnetMinerHotkeyOut.model_validate(hotkey) for hotkey in hotkeys]
        
    async def get_all_active_hotkeys(self) -> List[SubnetMinerHotkeyOut]:
        async with self.session.begin() as session:
            get_hotkeys_result = await session.execute(select(SubnetMinerHotkey).where(SubnetMinerHotkey.status == MinerStatus.REGISTERED))
            hotkeys = get_hotkeys_result.scalars().all()
            return [SubnetMinerHotkeyOut.model_validate(hotkey) for hotkey in hotkeys]
        
    async def deregister_hotkey(self, deregister_hotkey: SubnetMinerHotkeyDeregister) -> SubnetMinerHotkeyOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            hotkey = await session.get(SubnetMinerHotkey, deregister_hotkey.hotkey)
            if not hotkey:
                raise ValueError("Hotkey not found")
            bound_leader_result = await session.execute(select(Leader)
                                                        .options(selectinload(Leader.leader_proxy)
                                                                 .selectinload(LeaderProxy.copytraders)
                                                                 )
                                                        .where(Leader.hotkey == deregister_hotkey.hotkey))
            bound_leader = bound_leader_result.scalars().one_or_none()
            hotkey.status = MinerStatus.DEREGISTERED
            hotkey.updated_at = current_ts
            if bound_leader:
                for copytrader in bound_leader.leader_proxy.copytraders:
                    copytrader.leader_id = None
                    copytrader.updated_at = current_ts
                bound_leader.leader_proxy.leader_id = None
                bound_leader.leader_proxy.updated_at = current_ts
                bound_leader.status = LeaderStatus.VIOLATED
                bound_leader.updated_at = current_ts
                violation_message = BoundHotkeyDeregistrationException(
                    hotkey=deregister_hotkey.hotkey,
                    leader_id=bound_leader.id,
                    timestamp=current_ts
                ).violation_message
                await session.add(LeaderViolation(
                    leader_id=bound_leader.id,
                    violation_message=violation_message,
                    created_at=current_ts,
                    updated_at=current_ts
                ))
            await session.flush()
            await session.refresh(hotkey)
            return SubnetMinerHotkeyOut.model_validate(hotkey)