from yield_server.backend.database.models import CopyTraderMetrics, CopyTrader, CopyTraderMetricsSnapshot, CopyTraderRebalanceTransaction
from yield_server.backend.schema.copytradermetrics_schema import (
    CopyTraderMetricsCreate, 
    CopyTraderMetricsUpdate, 
    CopyTraderMetricsRemove, 
    CopyTraderMetricsOut,
    CopyTraderMetricsGet,
    CopyTraderMetricsHistoryGet,
    CopyTraderMetricsSnapshotGet,
    CopyTraderMetricsSnapshotBase,
    CopyTraderMetricsSnapshotCreate,
    CopyTraderMetricsSnapshotOut,
    CopyTraderPortfolioValueInRao,
    CopyTraderMetricsVolumeUpdate
)

from yield_server.utils.time import get_timestamp
from yield_server.backend.database.db import async_session
from yield_server.core.subtensor_calls import get_wallet_stakes, get_wallet_stakes_in_rao, get_subnets_info

from sqlalchemy import update, delete, select
from pydantic.types import UUID4
from typing import List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

class CopyTraderMetricsCRUD:
    '''
    CRUD operations for CopyTraderMetrics.
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session

    async def create_metrics(self, metrics_create: CopyTraderMetricsCreate) -> CopyTraderMetricsOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            copytrader_record = session.get(CopyTrader, metrics_create.copytrader_id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")

            # check if the copytrader has a metrics record
            metrics_record_results = await session.execute(select(CopyTraderMetrics).filter(CopyTraderMetrics.copytrader_id == metrics_create.copytrader_id))
            metrics_record = metrics_record_results.scalars().one_or_none()
            if metrics_record:
                raise ValueError("CopyTrader metrics already exists")
            
            new_metrics = CopyTraderMetrics(
                copytrader_id=metrics_create.copytrader_id,
                pnl=metrics_create.pnl,
                pnl_percent=metrics_create.pnl_percent,
                volume=metrics_create.volume,
                total_assets=metrics_create.total_assets,
                created_at=current_ts,
                updated_at=current_ts
            )
            session.add(new_metrics)
            await session.flush()
            await session.refresh(new_metrics)
            return CopyTraderMetricsOut.model_validate(new_metrics)
        
    async def update_metrics(self, metrics_update: CopyTraderMetricsUpdate) -> CopyTraderMetricsOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            metrics_record_results = await session.execute(select(CopyTraderMetrics).filter(CopyTraderMetrics.copytrader_id == metrics_update.copytrader_id))
            metrics_record = metrics_record_results.scalars().one_or_none()
            if not metrics_record:
                raise ValueError("CopyTrader metrics not found | verify that you are a valid copytrader or contact support")
            
            update_dict = metrics_update.model_dump(exclude_unset=True)
            update_dict["updated_at"] = current_ts
            for key, value in update_dict.items():
                setattr(metrics_record, key, value)

            await session.flush()
            await session.refresh(metrics_record)
            return CopyTraderMetricsOut.model_validate(metrics_record)
        
    async def get_metrics(self, metrics_get: CopyTraderMetricsGet) -> CopyTraderMetricsOut:
        async with self.session.begin() as session:
            metrics_record_results = await session.execute(select(CopyTraderMetrics).filter(CopyTraderMetrics.copytrader_id == metrics_get.copytrader_id))
            metrics_record = metrics_record_results.scalars().one_or_none()
            if not metrics_record:
                raise ValueError("CopyTrader metrics not found")
            return CopyTraderMetricsOut.model_validate(metrics_record)
    
    async def get_all_copytrader_uuids(self) -> List[CopyTraderMetricsGet]:
        async with self.session.begin() as session:
            copytrader_record_results = await session.execute(select(CopyTraderMetrics))
            copytrader_record = copytrader_record_results.scalars().all()
            if not copytrader_record:
                raise ValueError("CopyTrader metrics not found")
            return [CopyTraderMetricsGet(copytrader_id=copytrader.copytrader_id) for copytrader in copytrader_record]

    # NOTE: the internal service that takes daily portfolio snapshots will invoke this function to update the copytrader_metrics_snapshots table
    async def take_snapshot(self, metrics_get: CopyTraderMetricsGet) -> bool:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            metrics_record_results = await session.execute(select(CopyTraderMetrics).filter(CopyTraderMetrics.copytrader_id == metrics_get.copytrader_id))
            metrics_record = metrics_record_results.scalars().one_or_none()
            if not metrics_record:
                raise ValueError("CopyTrader metrics not found")
            
            # upsert the snapshot data
            snapshot_record_results = await session.execute(select(CopyTraderMetricsSnapshot)
                                                            .filter(CopyTraderMetricsSnapshot.copytrader_id == metrics_get.copytrader_id)
                                                            .filter(CopyTraderMetricsSnapshot.snapshot_date == datetime.today().date()))
            snapshot_record = snapshot_record_results.scalars().one_or_none()
            if snapshot_record:
                # update the snapshot data
                snapshot_record.updated_at = current_ts
                snapshot_record.pnl = metrics_record.pnl
                snapshot_record.pnl_percent = metrics_record.pnl_percent
                snapshot_record.total_assets = metrics_record.total_assets
                snapshot_record.volume = metrics_record.volume
            else:
                snapshot_data = CopyTraderMetricsSnapshotBase.model_validate(metrics_record)
                new_snapshot = CopyTraderMetricsSnapshot(
                    copytrader_id=metrics_get.copytrader_id,
                    snapshot_date=datetime.today().date(),
                    **snapshot_data.model_dump(),
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(new_snapshot)
            await session.flush()
            return True

    async def upsert_snapshot(self, snapshot_create: CopyTraderMetricsSnapshotCreate) -> CopyTraderMetricsSnapshotOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            copytrader_record_results = await session.execute(select(CopyTraderMetrics).filter(CopyTraderMetrics.copytrader_id == snapshot_create.copytrader_id))
            copytrader_record = copytrader_record_results.scalars().one_or_none()
            if not copytrader_record:
                raise ValueError("CopyTrader metrics not found")

            # check if the snapshot already exists
            snapshot_record_results = await session.execute(select(CopyTraderMetricsSnapshot)
                                                            .filter(CopyTraderMetricsSnapshot.copytrader_id == snapshot_create.copytrader_id)
                                                            .filter(CopyTraderMetricsSnapshot.snapshot_date == snapshot_create.snapshot_date))
            snapshot_record: CopyTraderMetricsSnapshot = snapshot_record_results.scalars().one_or_none()
            if snapshot_record:
                snapshot_record.updated_at = current_ts
                snapshot_record.pnl = copytrader_record.pnl
                snapshot_record.pnl_percent = copytrader_record.pnl_percent
                snapshot_record.total_assets = copytrader_record.total_assets
                snapshot_record.volume = copytrader_record.volume
            else:
                snapshot_record = CopyTraderMetricsSnapshot(
                    copytrader_id=snapshot_create.copytrader_id,
                    **snapshot_create.model_dump(exclude={"copytrader_id"}),
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(snapshot_record)
            await session.flush()
            await session.refresh(snapshot_record)
            return CopyTraderMetricsSnapshotOut.model_validate(snapshot_record)
    
    async def get_metrics_history(self, metrics_history_get: CopyTraderMetricsHistoryGet) -> List[CopyTraderMetricsSnapshotOut]:
        async with self.session.begin() as session:
            # check if the copytrader exists
            copytrader_record_results = await session.execute(select(CopyTraderMetrics).filter(CopyTraderMetrics.copytrader_id == metrics_history_get.copytrader_id))
            copytrader_record = copytrader_record_results.scalars().one_or_none()
            if not copytrader_record:
                raise ValueError("CopyTrader metrics not found")
            snapshot_record_results = await session.execute(select(CopyTraderMetricsSnapshot)
            .filter(CopyTraderMetricsSnapshot.copytrader_id == metrics_history_get.copytrader_id)
            .order_by(CopyTraderMetricsSnapshot.snapshot_date.asc())
            .limit(metrics_history_get.periods))
            snapshot_record = snapshot_record_results.scalars().all()
            return [CopyTraderMetricsSnapshotOut.model_validate(snapshot) for snapshot in snapshot_record]

    # Post rebalancing, we need to update the volume of the copytrader
    async def update_volume(self, metrics_update: CopyTraderMetricsVolumeUpdate) -> CopyTraderMetricsOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            metrics_record = await session.get(CopyTraderMetrics, metrics_update.copytrader_id)
            copytrader_rebalance_transaction_results = await session.execute(select(CopyTraderRebalanceTransaction.volume)
                                                                      .filter(CopyTraderRebalanceTransaction.copytrader_id == metrics_update.copytrader_id))
            copytrader_rebalance_transaction_volumes = copytrader_rebalance_transaction_results.scalars().all()
            if len(copytrader_rebalance_transaction_volumes) == 0:
                new_volume = 0
            else:
                new_volume = sum(copytrader_rebalance_transaction_volumes)
            if not metrics_record:
                raise ValueError("CopyTrader metrics not found")
            metrics_record.volume = new_volume
            metrics_record.updated_at = current_ts
            await session.flush()
            await session.refresh(metrics_record)
            return CopyTraderMetricsOut.model_validate(metrics_record)

    async def update_metrics_in_rao(self, metrics_in_rao: CopyTraderPortfolioValueInRao) -> CopyTraderMetricsOut:
        # For copytraders, we do not compute the volume ad-hoc. Rather, we compute it from each rebalancing event.
        '''
        We need to update the following fields:
        1. pnl
        2. pnl_percent
        3. total_assets
        '''
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            metrics_record = await session.get(CopyTraderMetrics, metrics_in_rao.copytrader_id)
            if not metrics_record:
                raise ValueError("CopyTrader metrics not found")
            copytrader_record = await session.get(CopyTrader, metrics_in_rao.copytrader_id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            
            initial_portfolio_value = copytrader_record.account_starting_balance
            if initial_portfolio_value == 0:
                raise ValueError("CopyTrader has no starting account balance")
            metrics_record.pnl = metrics_in_rao.portfolio_value - initial_portfolio_value
            metrics_record.pnl_percent = (metrics_in_rao.portfolio_value - initial_portfolio_value) / initial_portfolio_value
            metrics_record.total_assets = metrics_in_rao.portfolio_value
            metrics_record.updated_at = current_ts
            await session.flush()
            await session.refresh(metrics_record)
            return CopyTraderMetricsOut.model_validate(metrics_record)
        
    async def create_metrics_if_not_exists(self, copytrader_id: UUID4) -> CopyTraderMetricsOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            metrics_record = await session.get(CopyTraderMetrics, copytrader_id)
            # check if the copytrader's starting account balance has been set
            copytrader_record = await session.get(CopyTrader, copytrader_id)
            if copytrader_record.account_starting_balance == 0 or copytrader_record.account_starting_balance is None:
                # we compute the starting account balance from the staked balance
                subnet_info = await get_subnets_info()
                wallet_stakes = await get_wallet_stakes(copytrader_record.address, include_free=False) # Don't include the free balance since we only want to track the staked portfolio
                copytrader_record.account_starting_balance = await get_wallet_stakes_in_rao(subnet_info, wallet_stakes)
                if copytrader_record.account_starting_balance == 0:
                    raise ValueError("CopyTrader has no staked balance")
            if not metrics_record:
                metrics_record = CopyTraderMetrics(
                    copytrader_id=copytrader_id,
                    pnl=0,
                    pnl_percent=0,
                    volume=0,
                    total_assets=copytrader_record.account_starting_balance,
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(metrics_record)
                await session.flush()
                await session.refresh(metrics_record)
                return CopyTraderMetricsOut.model_validate(metrics_record)
            return CopyTraderMetricsOut.model_validate(metrics_record)

    async def take_snapshot_for_all_copytraders(self):
        async with self.session.begin() as session:
            copytrader_ids_results = await session.execute(
                select(CopyTrader.id)
                .where(CopyTrader.leader_id.is_not(None))
                .where(CopyTrader.leader_proxy_id.is_not(None))
            )
            copytrader_ids = copytrader_ids_results.scalars().all()
        # don't nest the sessions | exit the context first
        for copytrader_id in copytrader_ids:
            try:
                await self.take_snapshot(CopyTraderMetricsGet(copytrader_id=copytrader_id))
            except ValueError as e:
                print(f"Error taking snapshot for copytrader {copytrader_id}: {e}")
                continue