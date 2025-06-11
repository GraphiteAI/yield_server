from yield_server.config.constants import SNAPSHOT_INTERVAL, METRIC_UPDATE_INTERVAL
from yield_server.backend.crud.leadermetrics_crud import LeaderMetricsCRUD
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.crud.copytradermetrics_crud import CopyTraderMetricsCRUD
from yield_server.backend.crud.copytrader_crud import CopyTraderCRUD
from yield_server.backend.schema.leadermetrics_schema import LeaderPortfolioValueInRao
from yield_server.core.subtensor_calls import get_portfolios_value_in_rao
from yield_server.backend.schema.copytradermetrics_schema import CopyTraderPortfolioValueInRao
from datetime import datetime

import asyncio

class MetricUpdateService:
    def __init__(self):
        self.snapshot_interval = SNAPSHOT_INTERVAL
        self.metric_update_interval = METRIC_UPDATE_INTERVAL
        self.leader_metrics_crud = LeaderMetricsCRUD()
        self.copytrader_metrics_crud = CopyTraderMetricsCRUD()
        self.copytrader_crud = CopyTraderCRUD()
        self.leader_crud = LeaderCRUD()
        
    async def run_metric_update_service(self):
        return asyncio.create_task(self.metric_update_service())

    async def metric_update_service(self):
        while True:
            print(f"Updating metrics @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await self.update_metrics()
    
    async def update_metrics(self):
        '''
        This function gets all the active leaders and creates a new metric record for each leader that is new.
        It then updates the metric record for all other active leaders.

        Likewise, this function also gets all the copytraders that are following a leader and creates a new metric record for each copytrader that is new.
        It then updates the metric record for all other copytraders that are following a leader.
        '''
        
        copytrader_addresses = await self.copytrader_crud.get_following_copytrader_addresses()
        leader_addresses = await self.leader_metrics_crud.get_active_leader_addresses()

        print(f"leader_addresses: {leader_addresses}")
        print(f"copytrader_addresses: {copytrader_addresses}")

        # for all addresses, we check if there's a metric record for that address, if not, we create a new one
        for leader_address in leader_addresses:
            leader_id = await self.leader_crud.get_leader_id_from_address(leader_address)
            await self.leader_metrics_crud.create_metrics_if_not_exists(leader_id)
        for copytrader_address in copytrader_addresses:
            copytrader_id = await self.copytrader_crud.get_copytrader_id_from_address(copytrader_address)
            try:
                await self.copytrader_metrics_crud.create_metrics_if_not_exists(copytrader_id)
            except ValueError as e:
                print(f"Copytrader {copytrader_address} has no staked assets: {e}")
                # it's likely that the copytrader has no staked balance so we skip it
                continue
        try:
            copytrader_portfolio_value_in_rao = await get_portfolios_value_in_rao(coldkeys=copytrader_addresses, include_free=False)
            leader_portfolio_value_in_rao = await get_portfolios_value_in_rao(coldkeys=leader_addresses, include_free=True)
            print(f"copytrader_portfolio_value_in_rao: {copytrader_portfolio_value_in_rao}")
            print(f"leader_portfolio_value_in_rao: {leader_portfolio_value_in_rao}")
        except Exception as e:
            print(f"Error getting portfolio value in rao: {e}")
            # it's likely that the subtensor is down/congested so we sleep for 5 minutes and try again
            await asyncio.sleep(300)
            return
        
        # now we update the metrics for all the active leaders and copytraders
        # always update the copytrader metrics first because the leader metrics for notional value is computed from the copytrader metrics
        for copytrader_address in copytrader_addresses:
            # get the copytrader's portfolio value
            portfolio_value = copytrader_portfolio_value_in_rao[copytrader_address]
            copytrader_id = await self.copytrader_crud.get_copytrader_id_from_address(copytrader_address)
            copytrader_update = CopyTraderPortfolioValueInRao(copytrader_id=copytrader_id, portfolio_value=portfolio_value)
            await self.copytrader_metrics_crud.update_metrics_in_rao(copytrader_update)
        for leader_address in leader_addresses:
            # get the leader's portfolio value
            portfolio_value = leader_portfolio_value_in_rao[leader_address]
            leader_id = await self.leader_crud.get_leader_id_from_address(leader_address)
            leader_update = LeaderPortfolioValueInRao(leader_id=leader_id, portfolio_value=portfolio_value)
            await self.leader_metrics_crud.update_metrics_in_rao(leader_update)
            
        # reset the leader rank
        await self.leader_metrics_crud.update_rank()

        await asyncio.sleep(self.metric_update_interval)
        
    
    async def run_services(self):
        metric_task = await self.run_metric_update_service()
        
        # do a single run of the metric update first to ensure that the metrics are properly setup
        await self.update_metrics()
        await asyncio.gather(
            metric_task,
        )

