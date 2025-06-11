from yield_server.backend.database.models import LeaderProxy, Leader, LeaderStatus, ProxyBoundStatus
from yield_server.backend.schema.leader_schema import LeaderOutPublic
from yield_server.backend.schema.leaderproxy_schema import (
    LeaderProxyCreate, 
    LeaderProxyOut,
    LeaderProxyGet,
    LeaderProxyGetByLeader,
    LeaderProxyUpdateBalance
)

from yield_server.utils.time import get_timestamp
from yield_server.backend.database.db import async_session

from sqlalchemy import update, delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from rich.prompt import Confirm
from typing import List

class LeaderProxyCRUD:
    '''
    CRUD operations for LeaderProxy.
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = async_session

    async def create_proxy(self, create_proxy: LeaderProxyCreate) -> LeaderProxyOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            # check if the leader exists
            leader = await session.get(Leader, create_proxy.leader_id)
            if not leader:
                raise ValueError("Leader not found")
            
            # check if the leader is active
            if leader.status != LeaderStatus.ACTIVE:
                raise ValueError("Leader is not active")

            # check if there's already a proxy bound to the leader
            bounded_proxy_result = await session.execute(select(LeaderProxy).where(LeaderProxy.leader_id == create_proxy.leader_id))
            bounded_proxy = bounded_proxy_result.scalars().one_or_none()
            if bounded_proxy:
                raise ValueError("Proxy already bound to a leader")
            
            new_proxy = LeaderProxy(
                **create_proxy.model_dump(exclude_unset=True),
                created_at=current_ts,
                updated_at=current_ts
            )
            session.add(new_proxy)
            await session.flush()
            await session.refresh(new_proxy)
            return LeaderProxyOut.model_validate(new_proxy)
        
    async def get_proxy(self, get_proxy: LeaderProxyGet) -> LeaderProxyOut:
        async with self.session.begin() as session:
            proxy = await session.get(LeaderProxy, get_proxy.proxy_id)
            if not proxy:
                raise ValueError("Leader proxy not found")
            
            return LeaderProxyOut.model_validate(proxy)
        
    async def get_proxy_by_leader(self, get_leader_proxy: LeaderProxyGetByLeader) -> LeaderProxyOut:
        async with self.session.begin() as session:
            proxy_result = await session.execute(select(LeaderProxy).where(LeaderProxy.leader_id == get_leader_proxy.leader_id))
            proxy = proxy_result.scalars().one_or_none()
            if not proxy:
                raise ValueError("Leader proxy not found")
            return LeaderProxyOut.model_validate(proxy)
        
    async def get_active_leader_by_proxy(self, get_leader_proxy: LeaderProxyGet) -> LeaderOutPublic:
        async with self.session.begin() as session:
            leader_proxy_result = await session.execute(select(LeaderProxy).options(selectinload(LeaderProxy.leader)).where(LeaderProxy.proxy_id == get_leader_proxy.proxy_id))
            leader_proxy = leader_proxy_result.scalars().one_or_none()
            if not leader_proxy:
                raise ValueError("Leader proxy not found")
            if not leader_proxy.leader:
                raise ValueError("Leader not found")
            if leader_proxy.leader.status != LeaderStatus.ACTIVE:
                raise ValueError("Leader is not active")
            return LeaderOutPublic.model_validate(leader_proxy.leader)
        
    async def get_all_active_proxies(self) -> List[LeaderProxyOut]:
        async with self.session.begin() as session:
            stmt = select(LeaderProxy).options(selectinload(LeaderProxy.leader)).where(LeaderProxy.proxy_bound_status == ProxyBoundStatus.BOUND).where(LeaderProxy.leader.status == LeaderStatus.ACTIVE)
            result = await session.execute(stmt)
            return [LeaderProxyOut.model_validate(proxy) for proxy in result.scalars().all()]
        
    async def update_proxy_balance(self, update_proxy_balance: LeaderProxyUpdateBalance) -> LeaderProxyOut:
        async with self.session.begin() as session:
            proxy = await session.get(LeaderProxy, update_proxy_balance.proxy_id)
            if not proxy:
                raise ValueError("Leader proxy not found")
            proxy.balance = update_proxy_balance.balance
            proxy.updated_at = get_timestamp()
            await session.flush()
            return LeaderProxyOut.model_validate(proxy)
