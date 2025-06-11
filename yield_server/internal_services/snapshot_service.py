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

class SnapshotService:
    def __init__(self):
        self.snapshot_interval = SNAPSHOT_INTERVAL
        self.leader_metrics_crud = LeaderMetricsCRUD()
        self.copytrader_metrics_crud = CopyTraderMetricsCRUD()

    async def run_snapshot_service(self):
        return asyncio.create_task(self.snapshot_service())
    
    async def snapshot_service(self):
        '''
        This function takes a snapshot of the leader and copytrader metrics every day.
        '''
        while True:
            print(f"Taking snapshot @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await self.leader_metrics_crud.update_rank()
            await self.copytrader_metrics_crud.take_snapshot_for_all_copytraders()
            await self.leader_metrics_crud.take_snapshot_for_all_leaders()
            await asyncio.sleep(self.snapshot_interval)
    
    async def run_services(self):
        snapshot_task = await self.run_snapshot_service()
        
        await asyncio.gather(
            snapshot_task,
        )

