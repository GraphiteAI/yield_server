'''
This is the service that generates proxies for active leaders.
'''

from yield_server.backend.database.models import ProxyBoundStatus
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.crud.leaderproxy_crud import LeaderProxyCRUD
from yield_server.backend.schema.leader_schema import LeaderOutPublic
from yield_server.backend.schema.leaderproxy_schema import LeaderProxyCreate, LeaderProxyGetByLeader, LeaderProxyOut, LeaderProxyUpdateBalance
from yield_server.core.proxy_generator import create_proxy_for_leader
from yield_server.config.constants import PROXY_GENERATION_INTERVAL

from pydantic.types import UUID4

import time

import bittensor as bt
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

NETWORK = os.getenv("NETWORK")

class ProxyAssignmentService:
    def __init__(self):
        self.leader_crud = LeaderCRUD()
        self.proxy_crud = LeaderProxyCRUD()

    async def assign_proxy_to_leader(self, leader_id: UUID4):
        proxy_address = await create_proxy_for_leader(leader_id)
        # we are creating a bound proxy here
        proxy_create = LeaderProxyCreate(
            leader_id=leader_id,
            proxy_id=proxy_address,
            proxy_bound_status=ProxyBoundStatus.BOUND
        )
        await self.proxy_crud.create_proxy(proxy_create)
        return proxy_address
    
    async def generate_proxies_for_all_active_leaders(self):
        leaders = await self.leader_crud.get_all_active_leaders()
        print(f"Checking proxies for {len(leaders)} leaders @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        for leader in leaders:
            proxy_address = None
            try:
                # attempt to fetch the proxy from the database
                proxy: LeaderProxyOut = await self.proxy_crud.get_proxy_by_leader(
                    LeaderProxyGetByLeader(leader_id=leader.id)
                    )
                proxy_address = proxy.proxy_id
            except ValueError as e:
                proxy_address = await self.assign_proxy_to_leader(leader.id)
                print(f"Error fetching proxy for leader {leader.id}: {e} | Assigned new proxy {proxy_address}")


            if proxy_address is None:
                raise ValueError(f"Proxy address is None for leader {leader.id}")
            # updating the proxy
            balance = await bt.AsyncSubtensor(NETWORK).get_balance(proxy_address)
            print(f"Proxy {proxy_address} has balance {balance.rao} ")
            await self.proxy_crud.update_proxy_balance(LeaderProxyUpdateBalance(proxy_id=proxy_address, balance=balance.rao))

    async def run(self):
        while True:
            try:
                await self.generate_proxies_for_all_active_leaders()
                await asyncio.sleep(PROXY_GENERATION_INTERVAL)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error generating proxies for all active leaders: {e}")
                await asyncio.sleep(PROXY_GENERATION_INTERVAL)

