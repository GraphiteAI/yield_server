import asyncio
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
import bittensor as bt

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from yield_server.backend.database.db import async_session
from yield_server.backend.database.models import (
    CopyTrader,
    CopyTraderMetrics,
    CopyTraderMetricsSnapshot,
    Leader,
    LeaderProxy
)
from yield_server.core.subtensor_calls import (
    get_wallet_stakes, 
    get_subnets_info, 
    get_wallet_stakes_in_rao
)
from yield_server.utils.time import get_timestamp

import os
from dotenv import load_dotenv

load_dotenv(override=True)

NETWORK = os.getenv("NETWORK")

async def calculate_leader_metrics():
    """
    Calculates and updates metrics for all copytraders.
    """
    print(f"[{datetime.now()}] Starting copytrader metrics update...")
    
    # First create the session object by calling the factory
    session_factory = async_session()
    # Then use it as an async context manager
    async with session_factory() as session:
        try:
            # Initialize bittensor connection (reused across calls)
            async_subtensor = bt.AsyncSubtensor(NETWORK)
            await async_subtensor.initialize()
            
            # Get subnet info for stake calculation
            subnets_info = await get_subnets_info(async_subtensor=async_subtensor)
            
            # Get all copytraders with their related data
            query = (
                select(CopyTrader, Leader.account_starting_balance)
                .join(LeaderProxy, CopyTrader.leader_proxy_id == LeaderProxy.proxy_id)
                .join(Leader, Leader.id == LeaderProxy.leader_id)
            )
            
            result = await session.execute(query)
            copytraders_data = result.all()
            
            timestamp = get_timestamp()
            metrics_updated = 0
            
            for copytrader, account_starting_balance in copytraders_data:
                # Get wallet stakes using user's address as coldkey
                try:
                    # Get wallet stakes and calculate total assets
                    total_assets = await get_wallet_stakes(
                        coldkey_ss58=copytrader.address,
                        hotkey_ss58=None,  # Not needed for copytraders
                        async_subtensor=async_subtensor
                    )
                    
                    total_assets_in_tao = await get_wallet_stakes_in_rao(
                        subnets_info=subnets_info,
                        stakes=total_assets,
                    )
                    
                    # Calculate PNL metrics
                    pnl = total_assets_in_tao - account_starting_balance
                    pnl_percent = (pnl / account_starting_balance) * 100 if account_starting_balance else 0
                    
                    # Get previous metric for volume (keeping the previous value)
                    prev_metrics_query = select(CopyTraderMetrics).where(
                        CopyTraderMetrics.copytrader_id == copytrader.id
                    )
                    prev_result = await session.execute(prev_metrics_query)
                    prev_metrics = prev_result.scalar_one_or_none()
                    
                    # Use previous volume or default to 0
                    volume = prev_metrics.volume if prev_metrics else 0
                    status = "ACTIVE"  # Status will be managed by another service as mentioned
                    
                    # Update metrics
                    metrics_data = {
                        "total_assets": total_assets,
                        "total_assets_in_tao": total_assets_in_tao,
                        "pnl": pnl,
                        "pnl_percent": pnl_percent,
                        "volume": volume,
                        "status": status,
                        "updated_at": timestamp
                    }
                    
                    # UPSERT CopyTraderMetrics
                    if prev_metrics:
                        await session.execute(
                            update(CopyTraderMetrics)
                            .where(CopyTraderMetrics.copytrader_id == copytrader.id)
                            .values(**metrics_data)
                        )
                    else:
                        # Create new record if doesn't exist
                        metrics_record = CopyTraderMetrics(
                            copytrader_id=copytrader.id,
                            created_at=timestamp,
                            **metrics_data
                        )
                        session.add(metrics_record)
                    
                    # Create snapshot
                    snapshot = CopyTraderMetricsSnapshot(
                        copytrader_id=copytrader.id,
                        pnl=pnl,
                        pnl_percent=pnl_percent,
                        volume=volume,
                        total_assets=total_assets,
                        total_assets_in_tao=total_assets_in_tao,
                        status=status,
                        snapshot_timestamp=timestamp
                    )
                    session.add(snapshot)
                    
                    metrics_updated += 1
                    
                except Exception as e:
                    print(f"Error updating metrics for copytrader {copytrader.id}: {str(e)}")
            
            await session.flush()
            print(f"[{datetime.now()}] ✅ Metrics updated for {metrics_updated} copytraders.")
        
        except Exception as e:
            await session.rollback()
            print(f"[{datetime.now()}] ❌ Error updating copytrader metrics: {str(e)}")


async def scheduled_task():
    """Run metrics calculation on a schedule."""
    await calculate_leader_metrics()


