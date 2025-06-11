from yield_server.backend.database.models import (
    Leader, 
    UserRole, 
    User, 
    SubnetMinerHotkey, 
    MinerStatus,
    LeaderStatus,
    HotkeyBoundStatus,
    LeaderProxy,
    ProxyBoundStatus,
    LeaderViolation
)

from yield_server.backend.schema.leader_schema import (
    LeaderCreate, 
    LeaderOutPrivate, 
    LeaderSetHotkey,
    LeaderGet,
    LeaderOutPublic,
    LeaderDemote,
    LeaderViolated,
    LeaderUnsetHotkey,
    LeaderSetStartingBalance,
    LeaderActivate,
    LeaderDeactivate,
    LeaderCompleteActivation,
    LeaderGetByHotkey,
    LeaderGetByProxy,
    LeaderAdminViolate,
    LeaderUpdateBlock
)

from yield_server.backend.schema.user_schema import UserOutPrivate
from yield_server.config.constants import MINIMUM_STARTING_BALANCE, MAXIMUM_STARTING_BALANCE

from yield_server.utils.time import get_timestamp
from yield_server.utils.crud_utils import orm_to_dict
from yield_server.backend.database.db import async_session

from sqlalchemy import select, update, insert, text, delete
from pydantic.types import UUID4
from typing import List, Optional
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

class LeaderCRUD:
    '''
    CRUD operations for Leaders.
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session

    async def create_new_leader(self, create_leader: LeaderCreate) -> LeaderOutPrivate:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            # Get the existing generic user
            existing_user = await session.get(User, create_leader.id)
            if not existing_user:
                raise ValueError("User not found | Please register as a user first")
            if existing_user.role == UserRole.LEADER:
                raise ValueError("User is already a leader")
            existing_user.role = UserRole.LEADER
            existing_user_dict = orm_to_dict(existing_user, User.__table__)
            existing_user_dict.pop("updated_at")
    
            # Create a new leader entry
            new_leader = Leader(
                **existing_user_dict,
                **create_leader.model_dump(exclude_unset=True, exclude={"id"}),
                status=LeaderStatus.INACTIVE,
                updated_at=current_ts
            )

            await session.execute(
                insert(Leader).values(orm_to_dict(new_leader, Leader.__table__)), 
                execution_options={"postgres_only": True}
                )
                    
            await session.flush()
            session.expunge_all() 
            new_leader = await session.get(Leader, new_leader.id)
            # # Fetch the newly created leader using a select statement
            # result = await session.execute(
            #     select(Leader).where(Leader.id == create_leader.id)
            # )
            # new_leader = result.scalars().one()
            
            if not new_leader:
                raise ValueError("Failed to create leader record")
            
            leader_attributes = orm_to_dict(new_leader, Leader.__table__)
            user_attributes = orm_to_dict(new_leader, User.__table__)
            leader_attributes.update(user_attributes)
                
            return LeaderOutPrivate.model_validate(leader_attributes)

    async def get_leader_by_id_public(self, get_leader: LeaderGet) -> LeaderOutPublic:
        async with self.session.begin() as session:
            leader_record = await session.get(Leader, get_leader.id)
            if not leader_record:
                raise ValueError("Leader not found")
            leader_attributes = orm_to_dict(leader_record, Leader.__table__)
            user_attributes = orm_to_dict(leader_record, User.__table__)
            leader_attributes.update(user_attributes)
            return LeaderOutPublic.model_validate(leader_attributes)

    async def get_leader_by_id_private(self, get_leader: LeaderGet) -> LeaderOutPrivate:
        async with self.session.begin() as session:
            leader_record = await session.get(Leader, get_leader.id)
            if not leader_record:
                raise ValueError("Leader not found")
            leader_attributes = orm_to_dict(leader_record, Leader.__table__)
            user_attributes = orm_to_dict(leader_record, User.__table__)
            leader_attributes.update(user_attributes)
            # get the leader proxy information
            leader_proxy = await session.execute(
                select(LeaderProxy).where(LeaderProxy.leader_id == get_leader.id)
            )
            leader_proxy = leader_proxy.scalars().one_or_none()
            if leader_proxy:
                leader_attributes["proxy_address"] = leader_proxy.proxy_id
            return LeaderOutPrivate.model_validate(leader_attributes)

    async def get_active_leader_by_hotkey(self, get_leader_by_hotkey: LeaderGetByHotkey) -> Optional[UUID4]:
        async with self.session.begin() as session:
            leader_id_results = await session.execute(
                select(Leader.id).where(Leader.hotkey == get_leader_by_hotkey.hotkey).where(Leader.status == LeaderStatus.ACTIVE)
            )
            leader_id = leader_id_results.scalars().one_or_none()
            return leader_id

    async def get_active_leader_by_proxy(self, get_leader_by_proxy: LeaderGetByProxy) -> Optional[UUID4]:
        async with self.session.begin() as session:
            leader_id_results = await session.execute(
                select(Leader.id)
                .join(LeaderProxy, Leader.id == LeaderProxy.leader_id)
                .where(LeaderProxy.proxy_id == get_leader_by_proxy.proxy_address)
                .where(Leader.status == LeaderStatus.ACTIVE)
            )
            leader_id = leader_id_results.scalars().one_or_none()
            return leader_id

    async def get_all_leaders(self) -> List[LeaderOutPublic]:
        async with self.session.begin() as session:
            fetch_leaders = await session.execute(select(Leader))
            leaders = fetch_leaders.scalars().all()

            def get_leader_attributes(leader: Leader) -> LeaderOutPublic:
                leader_attributes = orm_to_dict(leader, Leader.__table__)
                user_attributes = orm_to_dict(leader, User.__table__)
                leader_attributes.update(user_attributes)
                return LeaderOutPublic.model_validate(leader_attributes)

            return [get_leader_attributes(leader) for leader in leaders]
        
    async def get_all_inactive_leaders(self) -> List[LeaderOutPublic]:
        async with self.session.begin() as session:
            fetch_leaders = await session.execute(select(Leader).where(Leader.status == LeaderStatus.INACTIVE))
            leaders = fetch_leaders.scalars().all()
            def get_leader_attributes(leader: Leader) -> LeaderOutPublic:
                leader_attributes = orm_to_dict(leader, Leader.__table__)
                user_attributes = orm_to_dict(leader, User.__table__)
                leader_attributes.update(user_attributes)
                return LeaderOutPublic.model_validate(leader_attributes)
            return [get_leader_attributes(leader) for leader in leaders]

    async def get_all_active_leaders(self) -> List[LeaderOutPublic]:
        async with self.session.begin() as session:
            fetch_leaders = await session.execute(select(Leader).where(Leader.status == LeaderStatus.ACTIVE))
            leaders = fetch_leaders.scalars().all()
            def get_leader_attributes(leader: Leader) -> LeaderOutPublic:
                leader_attributes = orm_to_dict(leader, Leader.__table__)
                user_attributes = orm_to_dict(leader, User.__table__)
                leader_attributes.update(user_attributes)
                return LeaderOutPublic.model_validate(leader_attributes)
            return [get_leader_attributes(leader) for leader in leaders]
        
    async def get_all_active_leaders_private(self) -> List[LeaderOutPrivate]:
        async with self.session.begin() as session:
            fetch_leaders_and_proxies = await session.execute(select(Leader).where(Leader.status == LeaderStatus.ACTIVE).options(selectinload(Leader.leader_proxy)))
            leaders = fetch_leaders_and_proxies.scalars().all()
            def get_leader_attributes(leader: Leader) -> LeaderOutPrivate:
                leader_attributes = orm_to_dict(leader, Leader.__table__)
                user_attributes = orm_to_dict(leader, User.__table__)
                # Add proxy data
                if leader.leader_proxy:
                    leader_attributes['proxy_address'] = leader.leader_proxy.proxy_id
                leader_attributes.update(user_attributes)
                return LeaderOutPrivate.model_validate(leader_attributes)
            return [get_leader_attributes(leader) for leader in leaders]

    async def set_hotkey(self, set_hotkey: LeaderSetHotkey) -> LeaderOutPrivate:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            existing_leader = await session.get(Leader, set_hotkey.id)
            if not existing_leader:
                raise ValueError("Leader not found")
            
            if existing_leader.hotkey:
                raise ValueError("Leader already has a hotkey | Please unbind the hotkey first")
            
            existing_hotkey = await session.get(SubnetMinerHotkey, set_hotkey.hotkey)
            if not existing_hotkey:
                raise ValueError("Hotkey not found")
            
            elif existing_hotkey.status != MinerStatus.REGISTERED:
                raise ValueError("Hotkey not registered")
            
            elif existing_hotkey.bound_status == HotkeyBoundStatus.BOUND:
                raise ValueError("Hotkey already bound to a leader")
            
            existing_hotkey.bound_status = HotkeyBoundStatus.BOUND
            existing_hotkey.updated_at = current_ts

            # Set all values that were set
            for key, value in set_hotkey.model_dump(exclude_unset=True).items():
                setattr(existing_leader, key, value)

            existing_leader.updated_at = current_ts
            await session.flush()
            await session.refresh(existing_leader)
            leader_attributes = orm_to_dict(existing_leader, Leader.__table__)
            user_attributes = orm_to_dict(existing_leader, User.__table__)
            leader_attributes.update(user_attributes)
            return LeaderOutPrivate.model_validate(leader_attributes)

    async def unset_hotkey(self, unset_hotkey: LeaderUnsetHotkey) -> LeaderOutPrivate:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            existing_leader = await session.get(Leader, unset_hotkey.id)
            if not existing_leader:
                raise ValueError("Leader not found")
            
            existing_hotkey = await session.get(SubnetMinerHotkey, existing_leader.hotkey)
            if not existing_hotkey:
                raise ValueError("Hotkey not found")
            
            existing_leader.hotkey = None
            existing_leader.updated_at = current_ts
            existing_hotkey.bound_status = HotkeyBoundStatus.UNBOUND
            # Deactivate any active leader
            if existing_leader.status == LeaderStatus.ACTIVE:
                existing_leader.status = LeaderStatus.INACTIVE
                
            existing_hotkey.updated_at = current_ts
            await session.flush()
            await session.refresh(existing_leader)
            leader_attributes = orm_to_dict(existing_leader, Leader.__table__)
            user_attributes = orm_to_dict(existing_leader, User.__table__)
            leader_attributes.update(user_attributes)
            return LeaderOutPrivate.model_validate(existing_leader)

    async def set_leader_violated(self, leader_violated: LeaderViolated, session=None) -> LeaderOutPrivate:
        current_ts = get_timestamp()

        own_session = False
        if session is None:
            own_session = True
            session_manager = self.session.begin()
            session = await session_manager.__aenter__()
            
        try:
            # Load both the leader's proxy and its copytraders
            stmt = select(Leader).options(
                selectinload(Leader.leader_proxy).selectinload(LeaderProxy.copytraders)
            ).options(selectinload(Leader.subnet_miner_hotkey)).where(Leader.id == leader_violated.id)
            
            result = await session.execute(stmt)
            existing_leader = result.scalar_one_or_none()
            
            if not existing_leader:
                raise ValueError("Leader not found")
            
            if existing_leader.subnet_miner_hotkey:
                existing_leader.subnet_miner_hotkey.bound_status = HotkeyBoundStatus.UNBOUND
                existing_leader.subnet_miner_hotkey.updated_at = current_ts
            
            for key, value in leader_violated.model_dump(exclude_unset=True).items():
                setattr(existing_leader, key, value)

            # cascade the update to the copytraders that are bound to this leader's proxy
            leader_proxy = existing_leader.leader_proxy
            if leader_proxy:
                if leader_proxy.copytraders:
                    for copytrader in leader_proxy.copytraders:
                        copytrader.leader_id = None
                        copytrader.updated_at = current_ts

                leader_proxy.leader_id = None # NOTE: also drop the leader proxy's leader_id
                leader_proxy.updated_at = current_ts

            existing_leader.status = LeaderStatus.VIOLATED
            existing_leader.updated_at = current_ts
            await session.flush()
            await session.refresh(existing_leader)
            leader_attributes = orm_to_dict(existing_leader, Leader.__table__)
            user_attributes = orm_to_dict(existing_leader, User.__table__)
            leader_attributes.update(user_attributes)
            return LeaderOutPrivate.model_validate(leader_attributes)
        except Exception as e:
            raise ValueError(f"Failed to set leader as violated: {str(e)}")
        finally:
            if own_session:
                await session_manager.__aexit__(None, None, None)
        
    async def demote_leader(self, demote_leader: LeaderDemote) -> UserOutPrivate:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            existing_leader = await session.get(Leader, demote_leader.id)
            if not existing_leader:
                raise ValueError("Leader not found")
            
            # check if the leader's role is leader
            if existing_leader.role != UserRole.LEADER:
                raise ValueError("Leader is not a leader")
            
            # unbind the hotkey and proxy
            existing_hotkey = await session.get(SubnetMinerHotkey, existing_leader.hotkey)
            if existing_hotkey:
                existing_hotkey.bound_status = HotkeyBoundStatus.UNBOUND
                existing_hotkey.updated_at = current_ts
            
            existing_proxy = await session.execute(
                select(LeaderProxy).where(LeaderProxy.leader_id == existing_leader.id)
            )
            existing_proxy = existing_proxy.scalars().one_or_none()
            if existing_proxy:
                existing_proxy.proxy_bound_status = ProxyBoundStatus.UNBOUND
                existing_proxy.updated_at = current_ts
                    
            leader_id = existing_leader.id
            existing_leader.role = UserRole.GENERIC
            existing_leader.updated_at = current_ts
            await session.flush()
            await session.execute(
                delete(Leader).where(Leader.id == leader_id)
            )

            # get the new leader
            return UserOutPrivate.model_validate(existing_leader)
    
    # NOTE: this CRUD has been deprecated in favor of merging the bind and activate logic
    async def set_starting_balance(self, set_starting_balance: LeaderSetStartingBalance) -> LeaderOutPrivate:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            existing_leader = await session.get(Leader, set_starting_balance.id)
            if not existing_leader:
                raise ValueError("Leader not found")

            existing_leader.account_starting_balance = set_starting_balance.account_starting_balance
            existing_leader.start_block_number = set_starting_balance.start_block_number
            existing_leader.updated_at = current_ts
            await session.flush()
            await session.refresh(existing_leader)
            return LeaderOutPrivate.model_validate(existing_leader)

    async def complete_leader_activation(self, complete_leader_activation: LeaderCompleteActivation) -> LeaderOutPrivate:
        '''
        This Update operation does an on-site check to ensure that:
        The external checks executed are:
        1. The leader is inactive
        2. The hotkey is unbound and registered
        3. The starting account balance is within the valid range
        '''
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            existing_leader = await session.get(Leader, complete_leader_activation.id)
            if not existing_leader:
                raise ValueError("Leader not found")
            if existing_leader.status != LeaderStatus.INACTIVE:
                raise ValueError("Leader is not inactive")
            # get the existing hotkey
            existing_hotkey = await session.get(SubnetMinerHotkey, complete_leader_activation.hotkey)
            if not existing_hotkey:
                raise ValueError("Hotkey not found")
            if existing_hotkey.status != MinerStatus.REGISTERED:
                raise ValueError("Hotkey is not registered")
            if existing_hotkey.bound_status != HotkeyBoundStatus.UNBOUND:
                raise ValueError("Hotkey is not unbound")
            # check the starting account balance
            if complete_leader_activation.account_starting_balance < MINIMUM_STARTING_BALANCE or complete_leader_activation.account_starting_balance > MAXIMUM_STARTING_BALANCE:
                raise ValueError("Leader starting balance is not within the valid range")
            # set the leader to active
            existing_leader.status = LeaderStatus.ACTIVE
            existing_leader.start_block_number = complete_leader_activation.start_block_number
            existing_leader.hotkey = complete_leader_activation.hotkey
            existing_leader.account_starting_balance = complete_leader_activation.account_starting_balance
            existing_leader.updated_at = current_ts
            existing_hotkey.bound_status = HotkeyBoundStatus.BOUND
            existing_hotkey.updated_at = current_ts
            await session.flush()
            await session.refresh(existing_leader)
            return LeaderOutPrivate.model_validate(existing_leader)
        
            
        
    async def deactivate_leader(self, deactivate_leader: LeaderDeactivate) -> LeaderOutPrivate:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            existing_leader = await session.get(Leader, deactivate_leader.id)
            if not existing_leader:
                raise ValueError("Leader not found")
            existing_leader.status = LeaderStatus.INACTIVE
            existing_leader.updated_at = current_ts
            await session.flush()
            await session.refresh(existing_leader)
            return LeaderOutPrivate.model_validate(existing_leader)

    async def get_leader_id_from_address(self, leader_address: str) -> UUID4:
        async with self.session.begin() as session:
            leader_id = await session.execute(
                select(Leader.id)
                .where(Leader.address == leader_address)
            )
            return leader_id.scalars().one_or_none()
        
    async def admin_violate_leader(self, leader_admin_violate: LeaderAdminViolate) -> LeaderOutPrivate:
        async with self.session.begin() as session:
            existing_leader = await session.execute(
                select(Leader).options(selectinload(Leader.leader_violation)).where(Leader.id == leader_admin_violate.id)
            )
            existing_leader = existing_leader.scalars().one_or_none()
            if not existing_leader:
                raise ValueError("Leader not found")
            # create a new violation message if it doesn't exist
            if not existing_leader.leader_violation:
                new_violation = LeaderViolation(
                    leader_id=leader_admin_violate.id,
                    violation_message=leader_admin_violate.message,
                    updated_at=get_timestamp()
                )
                existing_leader.leader_violation = new_violation
            # pass the session to the set_leader_violated function
            return await self.set_leader_violated(LeaderViolated(id=leader_admin_violate.id), session=session)

    async def update_leader_last_checked_block_number(self, leader_block: LeaderUpdateBlock) -> None:
        async with self.session.begin() as session:
            leader_record = await session.get(Leader, leader_block.id)
            if not leader_record:
                raise ValueError("Leader not found")
            
            if leader_block.last_checked_block_number >= leader_record.start_block_number:
                stmt = (
                    update(Leader)
                    .where(Leader.id == leader_block.id)
                    .values(last_checked_block_number=leader_block.last_checked_block_number)
                )

                await session.execute(stmt)

