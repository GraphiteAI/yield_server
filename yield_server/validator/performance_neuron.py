'''
This service hosts the endpoints for validators to get the performance data of the leaders for scoring.
It also hosts the endpoints for getting organic requests for rebalancing problems for subnet miners to solve.

GET /leader/performance_data --> this endpoint is used to get the performance data of the leaders for scoring
GET /leader/rebalancing_requests --> this endpoint is used to get the organic requests for rebalancing problems for subnet miners to solve
'''

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.types import UUID4
from typing import List, Tuple, Union
from datetime import datetime
import time
import random
from yield_server.validator.base_neuron import BaseYieldNeuron
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.schema.leader_schema import LeaderGetByHotkey
from yield_server.backend.crud.leadermetrics_crud import LeaderMetricsCRUD
from yield_server.backend.schema.leadermetrics_schema import LeaderMetricsGet, LeaderMetricsHistoryGet, LeaderMetricsSnapshotOut
from yield_server.core.metrics import compute_daily_portfolio_returns
from yield_server.config.constants import DEFAULT_SHARPE_RATIO
from graphite.yield_protocol import YieldDataRequestSynapse, LeaderPerformanceData, MinerYield
from bittensor.utils import is_valid_ss58_address
import bittensor as bt

class PerformanceNeuron(BaseYieldNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        self.leader_crud = LeaderCRUD()
        self.leader_metrics_crud = LeaderMetricsCRUD()

        self.axon.attach(
            forward_fn=self.forward,
            blacklist_fn=self.blacklist
        )

    async def forward(
        self, synapse: Union[YieldDataRequestSynapse]
    ) -> YieldDataRequestSynapse:
        # for the hotkey in hotkeys, we get the leader performance data similar to how it's retrieved via API
        bt.logging.info(f"Received a request from {synapse.dendrite.hotkey} with {len(synapse.yields)} yields")
        if self.config.use_mock_data:
            bt.logging.info("Using mock data")
        leader_ids: List[Union[None, UUID4]] = [await self.leader_crud.get_active_leader_by_hotkey(LeaderGetByHotkey(hotkey=miner_yield.hotkey)) for miner_yield in synapse.yields]
        for leader_id, miner_yield in zip(leader_ids, synapse.yields):
            if leader_id:
                try:
                    leader_metrics = await self.leader_metrics_crud.get_metrics_for_validator(LeaderMetricsGet(leader_id=leader_id))
                    leader_metric_history: List[LeaderMetricsSnapshotOut] = await self.leader_metrics_crud.get_metrics_history(LeaderMetricsHistoryGet(leader_id=leader_id, periods=8))
                    miner_yield.yield_data = LeaderPerformanceData(
                        sharpe_ratio=leader_metrics.sharpe_ratio,
                        max_drawdown=leader_metrics.drawdown,
                        num_copy_traders=leader_metrics.num_copy_traders,
                        notional_value_of_copy_traders=leader_metrics.notional_value_of_copy_traders,
                        historical_daily_pnl=compute_daily_portfolio_returns(leader_metric_history),
                        volume=leader_metrics.volume
                    )
                except Exception as e:
                    bt.logging.error(f"Error getting leader metrics for leader {leader_id}: {e}")
                    miner_yield.yield_data = None
            else:
                if self.config.use_mock_data:
                    miner_yield.yield_data = LeaderPerformanceData(
                        sharpe_ratio=random.uniform(DEFAULT_SHARPE_RATIO, 1.0),
                        max_drawdown=random.uniform(0.0, 20.0),
                        num_copy_traders=random.randint(0, 10),
                        notional_value_of_copy_traders=random.uniform(0, 100_000_000_000),
                        historical_daily_pnl=[random.uniform(-1.0, 1.8) for _ in range(random.randint(10, 100))],
                        volume=random.randint(0, 100_000_000)
                    )
                else:
                    miner_yield.yield_data = None
        bt.logging.info(f"Returning a response to {synapse.dendrite.hotkey} with {len([yield_data for yield_data in synapse.yields if yield_data.yield_data is not None])} yields")
        return synapse

    async def blacklist(
        self, synapse: Union[YieldDataRequestSynapse]
    ) -> Tuple[bool, str]:
        """
        Determines whether an incoming request should be blacklisted and thus ignored. Your implementation should
        define the logic for blacklisting requests based on your needs and desired security parameters.

        Blacklist runs before the synapse data has been deserialized (i.e. before synapse.data is available).
        The synapse is instead contructed via the headers of the request. It is important to blacklist
        requests before they are deserialized to avoid wasting resources on requests that will be ignored.

        Args:
            synapse (template.protocol.Dummy): A synapse object constructed from the headers of the incoming request.

        Returns:
            Tuple[bool, str]: A tuple containing a boolean indicating whether the synapse's hotkey is blacklisted,
                            and a string providing the reason for the decision.

        This function is a security measure to prevent resource wastage on undesired requests. It should be enhanced
        to include checks against the metagraph for entity registration, validator status, and sufficient stake
        before deserialization of synapse data to minimize processing overhead.

        Example blacklist logic:
        - Reject if the hotkey is not a registered entity within the metagraph.
        - Consider blacklisting entities that are not validators or have insufficient stake.

        In practice it would be wise to blacklist requests from entities that are not validators, or do not have
        enough stake. This can be checked via metagraph.S and metagraph.validator_permit. You can always attain
        the uid of the sender via a metagraph.hotkeys.index( synapse.dendrite.hotkey ) call.

        Otherwise, allow the request to be processed further.
        """

        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return True, "Missing dendrite or hotkey"

        # TODO(developer): Define how miners should blacklist requests.
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            # Ignore requests from un-registered entities.
            bt.logging.trace(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"

        blacklisted = []
        if self.config.blacklist.force_validator_permit:
            # If the config is set to force validator permit, then we should only allow requests from validators.
            if not self.metagraph.validator_permit[uid] or self.metagraph.S[uid] < 2000 or synapse.dendrite.hotkey in blacklisted:
                bt.logging.warning(
                    f"Blacklisting a request from non-validator hotkey {synapse.dendrite.hotkey}"
                )
                return True, "Non-validator hotkey"

        bt.logging.trace(
            f"Not Blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, "Hotkey recognized!"
    
