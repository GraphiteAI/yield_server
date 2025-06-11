from yield_server.backend.database.models import (
    LeaderMetrics, 
    Leader, 
    LeaderStatus, 
    LeaderMetricsSnapshot, 
    LeaderTransactions,
    CopyTrader,
    CopyTraderRebalanceTransaction,
    LeaderProxy
)
from yield_server.backend.schema.leadermetrics_schema import (
    LeaderMetricsCreate, 
    LeaderMetricsUpdate, 
    LeaderMetricsRemove,
    LeaderMetricsOut,
    LeaderMetricsGet,
    LeaderMetricsHistoryGet,
    LeaderMetricsSnapshotGet,
    LeaderMetricsSnapshotBase,
    LeaderMetricsSnapshotCreate,
    LeaderMetricsSnapshotUpdate,
    LeaderMetricsSnapshotOut,
    LeaderboardMetricsGet,
    LeaderPortfolioValueInRao,
    LeaderMetricsOutForValidator
)
from yield_server.utils.time import get_timestamp
from yield_server.backend.database.db import async_session
from yield_server.config.constants import LOOKBACK_DAYS, SHARPE_RATIO_LOOKBACK_DAYS
from yield_server.core.metrics import calculate_max_drawdown, compute_sharpe_ratio, compute_daily_portfolio_returns

from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload
from pydantic.types import UUID4
from datetime import datetime
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

class LeaderMetricsCRUD:
    '''
    CRUD operations for LeaderMetrics.
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session

    async def create_metrics(self, metrics_create: LeaderMetricsCreate) -> LeaderMetricsOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            # check if the leader exists
            leader = await session.get(Leader, metrics_create.leader_id)
            if not leader:
                raise ValueError("Leader not found")
            
            # check if the leader is active
            if leader.status != LeaderStatus.ACTIVE:
                raise ValueError("Leader is not active | unable to create metrics")
            
            # check if the leader metrics already exists
            existing_metrics = await session.get(LeaderMetrics, metrics_create.leader_id)
            if existing_metrics:
                raise ValueError("Leader metrics already exists")
            
            # overwrite the rank value of the leader
            leader_count = (await session.execute(select(func.count(Leader.id)).filter(Leader.status == LeaderStatus.ACTIVE))).scalar_one()
            metrics_create.rank = leader_count + 1 # +1 because the rank is 1-indexed

            new_metrics = LeaderMetrics(
                **metrics_create.model_dump(),
                created_at=current_ts,
                updated_at=current_ts
            )
            session.add(new_metrics)
            await session.flush()
            await session.refresh(new_metrics)
            return LeaderMetricsOut.model_validate(new_metrics)
        
    async def update_metrics(self, metrics_update: LeaderMetricsUpdate) -> LeaderMetricsOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            metrics_record_results = await session.execute(select(LeaderMetrics).filter(LeaderMetrics.leader_id == metrics_update.leader_id))
            metrics_record = metrics_record_results.scalar_one_or_none()
            if not metrics_record:
                raise ValueError("Leader metrics not found")
            
            update_dict = metrics_update.model_dump(exclude_unset=True)
            update_dict["updated_at"] = current_ts
            for key, value in update_dict.items():
                setattr(metrics_record, key, value)

            await session.flush()
            await session.refresh(metrics_record)
            return LeaderMetricsOut.model_validate(metrics_record)
        
    async def get_metrics(self, leader_get: LeaderMetricsGet) -> LeaderMetricsOut:
        async with self.session.begin() as session:
            metrics_record_results = await session.execute(select(LeaderMetrics).filter(LeaderMetrics.leader_id == leader_get.leader_id))
            metrics_record = metrics_record_results.scalars().one_or_none()
            if not metrics_record:
                raise ValueError("Leader metrics not found")
            return LeaderMetricsOut.model_validate(metrics_record)
        
    async def get_metrics_for_validator(self, leader_get: LeaderMetricsGet) -> LeaderMetricsOutForValidator:
        async with self.session.begin() as session:
            metrics_record_results = await session.execute(select(LeaderMetrics).filter(LeaderMetrics.leader_id == leader_get.leader_id))
            metrics_record = metrics_record_results.scalars().one_or_none()
            if not metrics_record:
                raise ValueError("Leader metrics not found")
            return LeaderMetricsOutForValidator.model_validate(metrics_record)

    # NOTE: the internal service that takes daily portfolio snapshots will invoke this function to update the copytrader_metrics_snapshots table
    async def take_snapshot(self, leader_get: LeaderMetricsGet) -> bool:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            metrics_record_results = await session.execute(select(LeaderMetrics).filter(LeaderMetrics.leader_id == leader_get.leader_id))
            metrics_record = metrics_record_results.scalars().one_or_none()
            if not metrics_record:
                raise ValueError("Leader metrics not found")
            # upsert the snapshot data
            snapshot_record_results = await session.execute(select(LeaderMetricsSnapshot)
                                                            .filter(LeaderMetricsSnapshot.leader_id == leader_get.leader_id)
                                                            .filter(LeaderMetricsSnapshot.snapshot_date == datetime.today().date()))
            snapshot_record = snapshot_record_results.scalars().one_or_none()
            if snapshot_record:
                # update the snapshot data
                snapshot_record.updated_at = current_ts
                snapshot_record.pnl = metrics_record.pnl
                snapshot_record.pnl_percent = metrics_record.pnl_percent
                snapshot_record.total_assets = metrics_record.total_assets
                snapshot_record.volume = metrics_record.volume
                snapshot_record.sharpe_ratio = metrics_record.sharpe_ratio
                snapshot_record.drawdown = metrics_record.drawdown
                snapshot_record.num_copy_traders = metrics_record.num_copy_traders
                snapshot_record.notional_value_of_copy_traders = metrics_record.notional_value_of_copy_traders
            else:
                snapshot_data = LeaderMetricsSnapshotBase.model_validate(metrics_record)
                new_snapshot = LeaderMetricsSnapshot(
                    leader_id=leader_get.leader_id,
                    snapshot_date=datetime.today().date(),
                    **snapshot_data.model_dump(),
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(new_snapshot)
            await session.flush()
            return True

    async def upsert_snapshot(self, snapshot_create: LeaderMetricsSnapshotCreate) -> LeaderMetricsSnapshotOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            leader_record_results = await session.execute(select(LeaderMetrics).filter(LeaderMetrics.leader_id == snapshot_create.leader_id))
            leader_record = leader_record_results.scalars().one_or_none()
            if not leader_record:
                raise ValueError("Leader metrics not found")
            # check if the snapshot already exists
            snapshot_record_results = await session.execute(select(LeaderMetricsSnapshot)
                                                            .filter(LeaderMetricsSnapshot.leader_id == snapshot_create.leader_id)
                                                            .filter(LeaderMetricsSnapshot.snapshot_date == snapshot_create.snapshot_date))
            snapshot_record: LeaderMetricsSnapshot = snapshot_record_results.scalars().one_or_none()
            if snapshot_record:
                snapshot_record.updated_at = current_ts
                snapshot_record.pnl = leader_record.pnl
                snapshot_record.pnl_percent = leader_record.pnl_percent
                snapshot_record.total_assets = leader_record.total_assets
                snapshot_record.volume = leader_record.volume
                snapshot_record.sharpe_ratio = leader_record.sharpe_ratio
                snapshot_record.drawdown = leader_record.drawdown
                snapshot_record.num_copy_traders = leader_record.num_copy_traders
                snapshot_record.notional_value_of_copy_traders = leader_record.notional_value_of_copy_traders
            else:
                snapshot_record = LeaderMetricsSnapshot(
                    leader_id=snapshot_create.leader_id,
                    **snapshot_create.model_dump(exclude={"leader_id"}),
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(snapshot_record)
            await session.flush()
            await session.refresh(snapshot_record)
            return LeaderMetricsSnapshotOut.model_validate(snapshot_record)
    
    async def get_metrics_history(self, metrics_history_get: LeaderMetricsHistoryGet) -> List[LeaderMetricsSnapshotOut]:
        async with self.session.begin() as session:
            # check if the leader exists
            leader_record_results = await session.execute(select(LeaderMetrics).filter(LeaderMetrics.leader_id == metrics_history_get.leader_id))
            leader_record = leader_record_results.scalars().one_or_none()
            if not leader_record:
                raise ValueError("Leader metrics not found")
            snapshot_record_results = await session.execute(select(LeaderMetricsSnapshot)
            .filter(LeaderMetricsSnapshot.leader_id == metrics_history_get.leader_id)
            .order_by(LeaderMetricsSnapshot.snapshot_date.desc())
            .limit(metrics_history_get.periods))
            snapshot_record = snapshot_record_results.scalars().all()
            # sort the snapshot record by snapshot_date in ascending order
            snapshot_record.sort(key=lambda x: x.snapshot_date, reverse=False)
            return [LeaderMetricsSnapshotOut.model_validate(snapshot) for snapshot in snapshot_record]

    # NOTE: for now we only return the top 10 leaders based on rank. However, in the future, we might want to provide more functionality for data filtering
    # In such a case, please extend the LeaderboardMetricsGet model to include a new field for the sorting axis, exclusion criteria, etc.
    async def get_active_leader_uuids(self, leaderboard_metrics_get: LeaderboardMetricsGet) -> List[UUID4]:
        async with self.session.begin() as session:
            if leaderboard_metrics_get.top_n:
                stmt = select(LeaderMetrics).join(LeaderMetrics.leader).where(Leader.status == LeaderStatus.ACTIVE).order_by(LeaderMetrics.rank.asc()).limit(leaderboard_metrics_get.top_n)
            else:
                stmt = select(LeaderMetrics).join(LeaderMetrics.leader).where(Leader.status == LeaderStatus.ACTIVE).order_by(LeaderMetrics.rank.asc())
            snapshot_record_results = await session.execute(stmt)
            snapshot_records = snapshot_record_results.scalars().all()
            return [snapshot.leader_id for snapshot in snapshot_records]

    async def get_active_leader_addresses(self) -> List[str]:
        async with self.session.begin() as session:
            stmt = select(Leader.address).filter(Leader.status == LeaderStatus.ACTIVE)
            leader_addresses = await session.execute(stmt)
            return leader_addresses.scalars().all()
        
    async def create_metrics_if_not_exists(self, leader_id: UUID4) -> LeaderMetricsOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            metrics_record = await session.get(LeaderMetrics, leader_id)
            if not metrics_record:
                # overwrite the rank value of the leader
                leader_count = (await session.execute(select(func.count(Leader.id)).filter(Leader.status == LeaderStatus.ACTIVE))).scalar_one()
                metrics_record = LeaderMetrics(
                    leader_id=leader_id,
                    total_assets=0,
                    pnl=0,
                    pnl_percent=0,
                    sharpe_ratio=0,
                    drawdown=0,
                    volume=0,
                    num_copy_traders=0,
                    notional_value_of_copy_traders=0,
                    rank=leader_count + 1,
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(metrics_record)
                await session.flush()
                await session.refresh(metrics_record)
            return LeaderMetricsOut.model_validate(metrics_record)

    # NOTE: we do not need a volume update CRUD for the leaders as its computed whenever update metrics is called
    async def update_metrics_in_rao(self, metrics_in_rao: LeaderPortfolioValueInRao) -> LeaderMetricsOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            # Get leader with copytraders and their metrics loaded
            stmt = (
                select(LeaderMetrics)
                .join(LeaderMetrics.leader)
                .options(
                    selectinload(LeaderMetrics.leader).options(
                        selectinload(Leader.copytraders).options(
                            selectinload(CopyTrader.metrics)
                        )
                    )
                )
                .filter(Leader.status == LeaderStatus.ACTIVE)
            ).where(Leader.id == metrics_in_rao.leader_id)
            leader_metrics_result = await session.execute(stmt)
            metrics_record = leader_metrics_result.scalar_one_or_none()
            leader_record = metrics_record.leader
            if not metrics_record:
                raise ValueError("Leader not found")

            initial_portfolio_value = leader_record.account_starting_balance
            metrics_record.total_assets = metrics_in_rao.portfolio_value
            metrics_record.pnl = metrics_in_rao.portfolio_value - initial_portfolio_value
            metrics_record.pnl_percent = (metrics_in_rao.portfolio_value - initial_portfolio_value) / initial_portfolio_value
            # compute the volume from the copytrader metrics
            leader_proxy_results = await session.execute(select(LeaderProxy).filter(LeaderProxy.leader_id == metrics_in_rao.leader_id))
            leader_proxy = leader_proxy_results.scalars().one_or_none()
            if leader_proxy:
                leader_transaction_volumes = await session.execute(select(CopyTraderRebalanceTransaction.volume)
                                                                .filter(CopyTraderRebalanceTransaction.leader_proxy_id == leader_proxy.proxy_id))
                leader_transaction_volumes = leader_transaction_volumes.scalars().all()
            else:
                # assign volume to 0 if no leader proxy is found
                leader_transaction_volumes = [0]
            metrics_record.volume = sum(leader_transaction_volumes)
            # compute the sharpe ratio by getting the % returns from the leader metrics and computing the daily returns then the sharpe ratio
            leader_metric_snapshots_results = await session.execute(select(LeaderMetricsSnapshot.pnl_percent)
                                                   .filter(LeaderMetricsSnapshot.leader_id == metrics_in_rao.leader_id)
                                                   .order_by(LeaderMetricsSnapshot.snapshot_date.desc())
                                                   .limit(SHARPE_RATIO_LOOKBACK_DAYS + 1))
            leader_metric_snapshots = leader_metric_snapshots_results.scalars().all()
            daily_returns = compute_daily_portfolio_returns(leader_metric_snapshots)
            metrics_record.sharpe_ratio = compute_sharpe_ratio(daily_returns)
            metrics_record.drawdown = calculate_max_drawdown(leader_metric_snapshots)
            metrics_record.num_copy_traders = len(leader_record.copytraders)
            
            # Calculate total notional value from copytrader metrics
            total_notional = 0

            for copytrader in leader_record.copytraders:
                if copytrader.metrics:  # Check if metrics exist
                    total_notional += copytrader.metrics.total_assets
            metrics_record.notional_value_of_copy_traders = total_notional
            metrics_record.updated_at = current_ts
            await session.flush()
            await session.refresh(metrics_record)
            return LeaderMetricsOut.model_validate(metrics_record)

    async def update_rank(self):
        # sets the rank of all active leaders based on the pnl_percent
        async with self.session.begin() as session:
            stmt = (
                select(LeaderMetrics)
                .join(LeaderMetrics.leader)
                .options(selectinload(LeaderMetrics.leader))
                .filter(Leader.status == LeaderStatus.ACTIVE)
            )
            leader_metrics = await session.execute(stmt)
            leader_metrics = leader_metrics.scalars().all()
            # TODO: change this to sort by sharpe ratio once we have launched for a while
            leader_metrics.sort(key=lambda x: x.pnl_percent, reverse=True)
            for i, leader_metric in enumerate(leader_metrics, start = 1):
                leader_metric.rank = i
                print(f"leader_metric: {leader_metric.rank} for leader: {leader_metric.leader.id}")
            await session.flush()

    async def take_snapshot_for_all_leaders(self):
        # get all active leader ids:
        async with self.session.begin() as session:
            leader_ids_results = await session.execute(select(Leader.id).filter(Leader.status == LeaderStatus.ACTIVE))
            leader_ids = leader_ids_results.scalars().all()
        # don't nest the sessions | exit the context first 
        for leader_id in leader_ids:
            try:
                await self.take_snapshot(LeaderMetricsGet(leader_id=leader_id))
            except Exception as e:
                print(f"Error taking snapshot for leader {leader_id}: {e}")
                continue
