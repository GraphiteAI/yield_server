'''
This is a neuron that is responsible for receiving organic requests from mainnet validators and generating valid organic portfolio rebalancing problems to be issued to miners.
'''
from yield_server.backend.database.models import UserRole
from yield_server.backend.crud.copytrader_crud import CopyTraderCRUD
from yield_server.backend.crud.leaderportfolio_crud import LeaderPortfolioCRUD
from yield_server.backend.crud.copytradermetrics_crud import CopyTraderMetricsCRUD
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.schema.leaderportfolio_schema import LeaderPortfolioGet, LeaderPortfolioOut
from yield_server.backend.schema.copytrader_schema import (
    CopyTraderRebalanceOut,
    CopyTraderSetRebalanceFailure,
    CopyTraderSetRebalanceSuccess,
    CopyTraderSetRebalanceCooldown
)
from yield_server.backend.schema.leader_schema import LeaderGetByProxy
from yield_server.backend.schema.copytradermetrics_schema import CopyTraderMetricsVolumeUpdate
from yield_server.core.subtensor_calls import get_subnets_info
from yield_server.config.default_config import add_yield_args, add_args, check_config, config
from yield_server.config.constants import (
    MAXIMUM_REBALANCE_RETRIES, 
    DEFAULT_REBALANCE_MODE, 
    DEFAULT_FEE_DESTINATION, 
    DEFAULT_REBALANCE_FEE, 
    DEFAULT_SLIPPAGE_TOLERANCE
)
from yield_server.core.proxy_generator import get_proxy_wallet_name, abs_wallet_path
from yield_server.utils.validator_utils import YieldPool
from yield_server.core.subtensor_calls import get_hotkey_level_portfolio
from yield_server.backend.database.db import create_session_maker

from graphite.base.neuron import BaseNeuron
from graphite import __spec_version__ as spec_version
from graphite.utils.misc import ttl_get_block
from graphite.organic_protocol import OrganicPortfolioRequestSynapse, OrganicPortfolioResponseSynapse
from graphite.protocol import GraphV1PortfolioProblem, GraphV1PortfolioSynapse
from graphite.solvers.greedy_portfolio_solver import GreedyPortfolioSolver
from graphite.utils.graph_utils import get_portfolio_distribution_similarity

import bittensor as bt
from bittensor.core.chain_data import DynamicInfo
from bittensor.utils.balance import Balance
from bittensor.utils import is_valid_ss58_address
from bittensor import Keypair, Wallet
from async_substrate_interface import AsyncSubstrateInterface
from scalecodec.types import GenericExtrinsic

from pydantic import BaseModel, field_validator, model_validator, Field
from pydantic.types import UUID4
from fastapi.encoders import jsonable_encoder
import time
from typing import Optional
import asyncio
import random
import contextlib
import numpy as np
import threading
import os
from collections import deque
import uuid
from typing import Union, List, Tuple, Deque, Set
from dotenv import load_dotenv
from yield_server.validator.base_neuron import BaseYieldNeuron
import traceback

load_dotenv(override=True)

'''
Follow the same design pattern as BaseMiner and Miner Neuron.
'''

class Job(BaseModel):
    copytrader_address: str
    proxy_id: str
    block_number: int # used for prioritization - refers to the next rebalance block of the copytrader
    job_uuid: UUID4 = Field(default_factory=uuid.uuid4) # used to identify the job in the removal task
    
    @field_validator("proxy_id", "copytrader_address")
    def validate_address(cls, v):
        if not is_valid_ss58_address(v):
            raise ValueError("Address is not a valid SS58 address")
        return v

class SentJob(Job):
    # need need to map the hotkey to an index in the 2D list of portfolios
    # to construct the problem, read in the leader portfolio
    leader_id: UUID4
    portfolio_mapping: dict[str, int]
    portfolio_hash: str
    target_portfolio: list[float]
    problem: Optional[GraphV1PortfolioProblem] = None

class ReceivedJob(SentJob):
    swaps: list[tuple[int, int, int, int]]
    success: bool = False

    def validate_solution(self):
        # Generate a GraphV1PortfolioSynapse from the swaps and problem
        synapse = GraphV1PortfolioSynapse(problem=self.problem, solution=self.swaps)
        swap_count, objective_score = get_portfolio_distribution_similarity(synapse)
        return swap_count < 1000000 and objective_score != 0

    async def process_rebalance_response(self, substrate_client: AsyncSubstrateInterface, keypair: Keypair)->Optional[Tuple[GenericExtrinsic, int]]:
        assert(keypair.ss58_address == self.proxy_id)
        bt.logging.info(f"Processing rebalance response for {self.proxy_id}")
        # generates the instructions for the rebalance request
        valid_solution = self.validate_solution()
        if not valid_solution:
            return None, None
        
        # refresh the view of the subnet info
        subnets_info: List[DynamicInfo] = await get_subnets_info()
        pools = {subnet_info.netuid: YieldPool(subnet_info.tao_in.rao, subnet_info.alpha_in.rao, netuid=subnet_info.netuid) 
                 for subnet_info in subnets_info}

        # TODO: compute the volume of the rebalance
        volume = 0
        # generate the rebalance call
        swap_calls = []
        # at each step, compute the appropriate price for the limit price 
        bt.logging.debug(f"Swaps: {self.swaps}")
        for portfolio_swap in self.swaps:
            hotkey = [hotkey for hotkey, idx in self.portfolio_mapping.items() if idx == portfolio_swap[0]][0]
            if portfolio_swap[1] == portfolio_swap[2]:
                continue
            origin_pool = pools[portfolio_swap[1]]
            destination_pool = pools[portfolio_swap[2]]
            net_price, rao_moved = origin_pool.compute_alpha_to_alpha_price(destination_pool, portfolio_swap[3])
            volume += rao_moved
            ## Implement your own function to compose swap calls
            swap_call = None
            swap_calls.append(swap_call)

        ## Implement your own function to compose the proxy call
        signed_extrinsic = None
        return signed_extrinsic, volume

class RebalanceJobQueue:
    def __init__(self):
        self.job_queue: List[Job] = [] # initialize with an empty list

    def add_job(self, copy_trader: CopyTraderRebalanceOut, running_jobs: dict[str, Job]) -> Optional[Job]:
        job = Job(
            copytrader_address=copy_trader.address,
            proxy_id=copy_trader.target_proxy,
            block_number=copy_trader.next_rebalance_block
        )
        # O(N) check if the job is already in the queue
        bt.logging.debug(f"Running jobs: {running_jobs.keys()}")
        bt.logging.debug(f"Job queue: {self.job_queue}")
        if not any(job.copytrader_address == job.copytrader_address for job in self.job_queue) and \
            not job.copytrader_address in running_jobs:
            self.job_queue.append(job)
            self.job_queue.sort(key=lambda x: x.block_number, reverse=True)
            return job
        else:
            bt.logging.debug(f"Job {job.copytrader_address} already in the queue or running")
            return None
    
    def replace_job(self, job: Job, running_jobs: dict[str, Job]):
        # replace the job with the new job
        if not job.copytrader_address in running_jobs:
            # prune any existing jobs with the same copytrader address
            self.job_queue = [job for job in self.job_queue if job.copytrader_address != job.copytrader_address]
            self.job_queue.append(job)
            self.job_queue.sort(key=lambda x: x.block_number, reverse=True)
        return job
    
    def get_next_job(self) -> Optional[Job]:
        try:
            return self.job_queue.pop()
        except IndexError:
            return None

class KeypairManager:
    def __init__(self):
        self.wallets: dict[str, Wallet] = {}

    def add_keypair(self, proxy_id: str, leader_id: UUID4):
        proxy_wallet_name = get_proxy_wallet_name(leader_id)
        wallet = Wallet(proxy_wallet_name, hotkey=None, path=abs_wallet_path)
        self.wallets[proxy_id] = wallet

    async def get_keypair(self, proxy_id: str, leader_crud: LeaderCRUD = LeaderCRUD()) -> Keypair:
        # retrieves the keypair from the wallet using the appropriate password
        # check if the leader is still active to address race condition between leader violation and copytrader rebalance
        leader_id: Optional[UUID4] = await leader_crud.get_active_leader_by_proxy(LeaderGetByProxy(proxy_address=proxy_id))
        if leader_id is None:
            raise ValueError("Leader not found")
        # only decrypt the wallet if the leader is active
        try:
            keypair =  self.wallets[proxy_id].get_coldkey(password=os.getenv("TESTENV_WALLET_PASSWORD"))
        except Exception as e:
            bt.logging.error(f"Error getting keypair for {proxy_id}: {e}")
            raise e
        return keypair

# TODO: refactor and name this to rebalance neuron
class RebalanceNeuron(BaseYieldNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        self.refresh_subtensor = bt.subtensor(config=self.config) # create a new subtensor object for the refresh job queue to avoid concurrency errors
        # initialize the crud objects
        self.keypair_manager = KeypairManager()
        # initialize the resource managers
        self.job_queue = RebalanceJobQueue()
        
        self.running_jobs: dict[str, Job] = dict() # set to store jobs that are currently being processed: SentJob and ReceivedJob; 

        self.cleanup_tasks: dict[UUID4, asyncio.Task] = dict() # set to store the cleanup tasks for each job

        self.axon.attach(
            forward_fn=self.forward_generate_problem, 
            blacklist_fn=self.blacklist_generate_problem
            ).attach(
            forward_fn=self.forward_receive_solution,
            blacklist_fn=self.blacklist_receive_solution
            )

    def run_refresh_job_queue(self):
        # create new event loop that executes the refresh_job_queue function
        self.refresh_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.refresh_loop)
        try:
            self.refresh_loop.run_until_complete(self.refresh_job_queue())
        finally:
            self.refresh_loop.close()
    
    async def refresh_job_queue(self, copytrader_crud: CopyTraderCRUD = CopyTraderCRUD()):
        # this function is called to fetch the copytraders that should be rebalanced
        # it then adds all the copytraders to the job queue
        while not self.should_exit:
            current_block = self.refresh_subtensor.get_current_block()
            bt.logging.info(f"Refreshing job queue @ {current_block}")
            added_count = 0
            copytraders: List[CopyTraderRebalanceOut] = await copytrader_crud.get_rebalance_copytraders(current_block)
            # bt.logging.info(f"Refreshing job queue with {len(copytraders)} copytraders")
            async with self.lock:
                # lock all resources current being used to prevent race conditions
                for copytrader in copytraders:
                    if copytrader.address in self.running_jobs:
                        continue
                    # test whether the issue is isolated to starlette
                    job = self.job_queue.add_job(copytrader, self.running_jobs)
                    if job is not None:
                        added_count += 1
                # and adds all missing keypairs to the keypair manager
                for copytrader in copytraders:
                    if copytrader.target_proxy not in self.keypair_manager.wallets:
                        self.keypair_manager.add_keypair(copytrader.target_proxy, copytrader.chosen_leader_id)
            bt.logging.info(f"Added {added_count} copytraders to the job queue")
            await asyncio.sleep(60)

    async def remove_stale_job(self, job_to_be_cleaned: Job, stale_timeout: int):
        # remove the job from the running jobs
        await asyncio.sleep(stale_timeout)
        async with self.lock:
            if job_to_be_cleaned.copytrader_address in self.running_jobs:
                bt.logging.info(f"Removing stale job for {job_to_be_cleaned.copytrader_address}")
                self.running_jobs.pop(job_to_be_cleaned.copytrader_address)
            if job_to_be_cleaned.job_uuid in self.cleanup_tasks:
                self.cleanup_tasks.pop(job_to_be_cleaned.job_uuid)

    def cleanup_expired_jobs(self, job_to_be_cleaned: Job, stale_timeout: int = 300):
        # remove all jobs from the running jobs that have expired --> remove jobs that took longer than 1 min
        bt.logging.info(f"Set removal of job for {job_to_be_cleaned.copytrader_address} after {stale_timeout} seconds")
        # Just create the task in the running event loop without trying to run it
        loop = asyncio.get_event_loop()
        self.cleanup_tasks[job_to_be_cleaned.job_uuid] = loop.create_task(self.remove_stale_job(job_to_be_cleaned, stale_timeout))

    # NOTE: we don't actually attach this forward. This is vestigial from the abstractmethod in BaseNeuron.
    def forward(self):
        pass
    
    def convert_portfolio_to_list(self, portfolio: dict[int, Union[float, int]], num_subnets: int, is_percentage: bool = False) -> list[float]:
        '''
        Maps a given portfolio (be it in % or RAO) to a list of length num_subnets
        '''
        # set all values to 0
        portfolio_list = [0] * num_subnets
        for subnet_id, weight in portfolio.items():
            try:
                portfolio_list[subnet_id] = weight
            except IndexError:
                bt.logging.error(f"Subnet ID {subnet_id} is out of range for portfolio list of length {num_subnets}")
        if is_percentage:
            # assert that the sum of the portfolio is 1
            assert np.isclose(sum(portfolio_list), 1, atol=1e-7)
        return portfolio_list
    
    async def formulate_job(self, job: Job, subnets_info: List[DynamicInfo], copytrader_crud: CopyTraderCRUD = CopyTraderCRUD(), leader_portfolio_crud: LeaderPortfolioCRUD = LeaderPortfolioCRUD()) -> Optional[SentJob]:
        # turns the job into a SentJob object
        # get the leader's portfolio
        copy_trader: CopyTraderRebalanceOut = await copytrader_crud.get_rebalance_copytrader_from_address(job.copytrader_address)
        # validate that the proxy_id is the same as the target_proxy
        if copy_trader.target_proxy != job.proxy_id:
            bt.logging.error(f"Proxy ID mismatch for {job.copytrader_address} | expected {job.proxy_id} but got {copy_trader.target_proxy} | proxy has been changed since job was added into the queue")
            return None
        try:
            leader_portfolio: LeaderPortfolioOut = await leader_portfolio_crud.get_leader_portfolio(LeaderPortfolioGet(leader_id=copy_trader.chosen_leader_id))
            leader_portfolio_hash = leader_portfolio.portfolio_hash
            leader_portfolio_distribution = leader_portfolio.portfolio_distribution
        except ValueError as e:
            bt.logging.error(f"Error getting leader portfolio for {job.copytrader_address}: {e}")
            return None
        # get the copytrader's portfolio using the subtensor call
        copytrader_portfolio: dict[str, dict[int, float]] = await get_hotkey_level_portfolio(job.copytrader_address) # nested dict representing the portfolio of the copytrader by the hotkey
        # formulate the problem
        problem_pools = [[subnet_info.tao_in.rao, subnet_info.alpha_in.rao] for subnet_info in subnets_info]
        # generate the 2D list representing the target portfolio
        portfolio_mapping = {hotkey: idx for idx, hotkey in enumerate(copytrader_portfolio.keys())}
        if len(portfolio_mapping) == 0:
            bt.logging.error(f"No portfolio mapping found for {job.copytrader_address} | likely that the copytrader has not yet staked any tao for rebalancing")
            return None
        # generate the initial portfolio
        initial_portfolio = [[] for _ in range(len(portfolio_mapping))]
        for hotkey, portfolios in copytrader_portfolio.items():
            initial_portfolio[portfolio_mapping[hotkey]] = self.convert_portfolio_to_list(portfolios, len(subnets_info))
        target_portfolio = self.convert_portfolio_to_list(leader_portfolio_distribution, len(subnets_info), True)
        problem = GraphV1PortfolioProblem(
            problem_type="PortfolioReallocation",
            n_portfolio=len(initial_portfolio),
            initialPortfolios=initial_portfolio,
            constraintValues=[x * 100 for x in target_portfolio],
            constraintTypes=["eq"] * len(target_portfolio),
            pools=problem_pools
        )
        # NOTE: the SentJob must inherit the job_uuid field from the Job class for the cancel flow to apply as intended.
        sent_job = SentJob(
            job_uuid=job.job_uuid,
            leader_id=copy_trader.chosen_leader_id,
            copytrader_address=job.copytrader_address,
            proxy_id=job.proxy_id,
            block_number=job.block_number,
            portfolio_mapping=portfolio_mapping,
            portfolio_hash=leader_portfolio_hash,
            target_portfolio=target_portfolio,
            problem=problem
        )
        return sent_job

    async def forward_generate_problem(self, synapse: OrganicPortfolioRequestSynapse) -> OrganicPortfolioRequestSynapse:
        bt.logging.info(f"Received a request from validator {synapse.dendrite.hotkey} | Generating a new portfolio problem for copytrader")
        # get target_portfolio from job queue
        # always use the same lock to prevent race conditions
        # create a new session maker for this context
        async_session_maker = await create_session_maker()
        copytrader_crud = CopyTraderCRUD(session=async_session_maker)
        leader_portfolio_crud = LeaderPortfolioCRUD(session=async_session_maker)

        async with self.lock:
            job = self.job_queue.get_next_job()
            if job is None:
                bt.logging.info("No job found in the job queue")
                return synapse # return the original synapse without a problem
            else:
                # add the job to the running jobs
                self.running_jobs[job.copytrader_address] = job
                # add a cleanup task in the background to remove the job from the running jobs if expired
                self.cleanup_expired_jobs(job)

        # yield the resources back once we have popped the job from the JobQueue
        # bt.logging.info(f"Job: {job}")
        subnets_info = await get_subnets_info()
        sent_job: Optional[SentJob] = await self.formulate_job(job, subnets_info, copytrader_crud, leader_portfolio_crud)
        if sent_job is None:
            bt.logging.error(f"Failed to formulate job for copytrader {job.copytrader_address}")
            self.running_jobs.pop(job.copytrader_address) # remove the job from the running jobs
            return synapse
        self.running_jobs[job.copytrader_address] = sent_job # update the running jobs
        synapse.problem = sent_job.problem
        synapse.job_id = sent_job.copytrader_address # use the copytrader address as the job id
        bt.logging.info(f"Sent job: {sent_job.job_uuid}")
        return synapse

    async def blacklist_generate_problem(
        self, synapse: Union[OrganicPortfolioRequestSynapse]
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
    
    async def forward_receive_solution(self, synapse: OrganicPortfolioResponseSynapse) -> OrganicPortfolioResponseSynapse:
        bt.logging.info(f"Received a solution from {synapse.dendrite.hotkey} with {len(synapse.solution)} swaps")
        # process the solution
        async_session_maker = await create_session_maker()
        copytrader_crud = CopyTraderCRUD(session=async_session_maker)
        copytrader_metrics_crud = CopyTraderMetricsCRUD(session=async_session_maker)
        leader_portfolio_crud = LeaderPortfolioCRUD(session=async_session_maker)
        leader_crud = LeaderCRUD(session=async_session_maker)
        sent_job: SentJob = None
        async with self.lock:
            # remove the job from the running jobs by iterating over the set
            if synapse.job_id in self.running_jobs:
                sent_job = self.running_jobs[synapse.job_id]
        
        if sent_job is None:
            bt.logging.error(f"No job found for {synapse.job_id}")
            return synapse
        # process the solution
        received_job = ReceivedJob(
            **sent_job.model_dump(),
            swaps=synapse.solution
        )
        extrinsic_success = False
        swap_volume = 0
        try:
            keypair = await self.keypair_manager.get_keypair(sent_job.proxy_id, leader_crud)
            substrate: AsyncSubstrateInterface = AsyncSubstrateInterface(self.subtensor.substrate.chain_endpoint)
            bt.logging.debug(f"Substrate: {substrate.chain_endpoint}")
            await substrate.initialize()
            signed_extrinsic, swap_volume = await received_job.process_rebalance_response(substrate, keypair)
            bt.logging.info(f"Signed extrinsic: {signed_extrinsic}")
            bt.logging.info(f"Swap volume: {swap_volume}")
            if signed_extrinsic is not None:
                response = await substrate.submit_extrinsic(
                    signed_extrinsic,
                    wait_for_inclusion=True,
                    wait_for_finalization=True
                )
                await response.process_events()
                bt.logging.info(f"Processing event for extrinsic sent on block {await substrate.get_block_number(response.block_hash)}")
                if await response.is_success:
                    # it's not enough that the extrinsic is successful, we need to check that the event actually happened
                    # since we are using a batch all call to wrap the swap_stake_limit call, we need to check that at least one of the swap_stake_limit calls was successful
                    triggered_events: list[dict] = await response.triggered_events
                    for event in triggered_events:
                        bt.logging.info(f"Event: {event}")
                        if event["event"]["module_id"] == "SubtensorModule" and event["event"]["event_id"] == "StakeSwapped":
                            extrinsic_success = True
                            # break
                    if not extrinsic_success:
                        raise ValueError(f"No stake swap event found for {sent_job.copytrader_address}") # NOTE: we trigger the error in the catch block below
                    bt.logging.info(f"Successfully submitted rebalance for {sent_job.copytrader_address} @ block {await substrate.get_block_number(response.block_hash)} with extrinsic hash {response.extrinsic_hash}")
                    copytrader_id = await copytrader_crud.get_copytrader_id_from_address(sent_job.copytrader_address)
                    rebalance_success =  CopyTraderSetRebalanceSuccess(
                        id=copytrader_id,
                        block_number=await substrate.get_block_number(response.block_hash),
                        portfolio_hash=sent_job.portfolio_hash,
                        leader_proxy_id=sent_job.proxy_id,
                        volume=swap_volume,
                        extrinsic_hash=response.extrinsic_hash,
                    )
                    # set the CRUD object
                    await copytrader_crud.set_copytrader_rebalance_success(rebalance_success)
                    await copytrader_metrics_crud.update_volume(CopyTraderMetricsVolumeUpdate(
                        copytrader_id=copytrader_id
                    ))
                    synapse.accepted = True
                    # remove the job from the running jobs
                    async with self.lock:
                        try:
                            if synapse.job_id in self.running_jobs:
                                self.running_jobs.pop(synapse.job_id)
                            # cancel task if it exists
                            if self.cleanup_tasks[sent_job.job_uuid]:
                                self.cleanup_tasks[sent_job.job_uuid].cancel()
                                self.cleanup_tasks.pop(sent_job.job_uuid)
                        except KeyError:
                            bt.logging.warning(f"Job {synapse.job_id} not found in running jobs | likely that the job was already removed due to previous race condition")
                else:
                    bt.logging.error(f"Extrinsic failed with events: {await response.error_message}")
                    bt.logging.error(f"Failed to submit rebalance for {sent_job.copytrader_address}")
                    synapse.accepted = False
                    # increment the rebalance attempts
                    copytrader_id = await copytrader_crud.get_copytrader_id_from_address(sent_job.copytrader_address)
                    rebalance_failure = CopyTraderSetRebalanceFailure(
                        id=copytrader_id,
                        block_number=self.subtensor.get_current_block(),
                    )
                    should_replace: int = await copytrader_crud.set_copytrader_rebalance_failure(rebalance_failure)
                    if should_replace > 0:
                        replace_job = Job(
                            copytrader_address=sent_job.copytrader_address,
                            proxy_id=sent_job.proxy_id,
                            block_number=sent_job.block_number
                        )
                        async with self.lock:
                            self.running_jobs.pop(synapse.job_id)
                            # cancel task if it exists
                            if self.cleanup_tasks[sent_job.job_uuid]:
                                self.cleanup_tasks[sent_job.job_uuid].cancel()
                            self.job_queue.replace_job(replace_job, self.running_jobs)

        except Exception as e:
            bt.logging.error(f"Error submitting rebalance for {sent_job.copytrader_address}: {e}")
            # if the extrinsic failed, we need to regenerate the job and add it back to the job queue
            if not extrinsic_success:
                # increment the rebalance attempts
                copytrader_id = await copytrader_crud.get_copytrader_id_from_address(sent_job.copytrader_address)
                rebalance_failure = CopyTraderSetRebalanceFailure(
                    id=copytrader_id,
                    block_number=self.subtensor.get_current_block(),
                )
                should_replace: int = await copytrader_crud.set_copytrader_rebalance_failure(rebalance_failure)
                if should_replace > 0:
                    # create new job to replace the old job in the job queue
                    replace_job = Job(
                        copytrader_address=sent_job.copytrader_address,
                        proxy_id=sent_job.proxy_id,
                        block_number=sent_job.block_number
                    )
                    async with self.lock:
                        self.running_jobs.pop(synapse.job_id)
                        # cancel task if it exists
                        if self.cleanup_tasks[sent_job.job_uuid]:
                            self.cleanup_tasks[sent_job.job_uuid].cancel()
                        self.job_queue.replace_job(replace_job, self.running_jobs)
                # else let the refresh job queue handle it
            synapse.accepted = False
        return synapse
    
    async def blacklist_receive_solution(
        self, synapse: Union[OrganicPortfolioResponseSynapse]
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
    
    def run(self):
        """
        Initiates and manages the main loop for the miner on the Bittensor network. The main loop handles graceful shutdown on keyboard interrupts and logs unforeseen errors.

        This function performs the following primary tasks:
        1. Check for registration on the Bittensor network.
        2. Starts the miner's axon, making it active on the network.
        3. Periodically resynchronizes with the chain; updating the metagraph with the latest network state and setting weights.

        The miner continues its operations until `should_exit` is set to True or an external interruption occurs.
        During each epoch of its operation, the miner waits for new blocks on the Bittensor network, updates its
        knowledge of the network (metagraph), and sets its weights. This process ensures the miner remains active
        and up-to-date with the network's latest state.

        Note:
            - The function leverages the global configurations set during the initialization of the miner.
            - The miner's axon serves as its interface to the Bittensor network, handling incoming and outgoing requests.

        Raises:
            KeyboardInterrupt: If the miner is stopped by a manual interruption.
            Exception: For unforeseen errors during the miner's operation, which are logged for diagnosis.
        """

        bt.logging.info("Checking for registration and running sync()")

        # Check that miner is registered on the network.
        self.sync()
        self.last_update = self.block
        self.loop = asyncio.new_event_loop()

        # Serve passes the axon information to the network + netuid we are hosting on.
        # This will auto-update if the axon port of external ip have changed.
        bt.logging.info(
            f"Serving yield axon {self.axon} on local environment"
        )

        # create a new event loop for this thread and save the reference to it
        self.refresh_thread = threading.Thread(target=self.run_refresh_job_queue, daemon=True)
        self.refresh_thread.start()

        # Start the axon, allowing it to receive incoming synapses.
        self.axon.start()
        asyncio.set_event_loop(self.loop)

        bt.logging.info(f"Yield Neuron starting at block: {self.block}")

        # This loop maintains the miner's operations until intentionally stopped.
        try:
            while not self.should_exit:
                while (
                    self.block - self.last_update
                    < self.config.neuron.epoch_length
                ):
                    # Wait before checking again.
                    time.sleep(1)

                    # Check if we should exit.
                    if self.should_exit:
                        break

                # Sync metagraph and potentially set weights.
                self.sync()
                self.last_update = self.block

        # If someone intentionally stops the miner, it'll safely terminate operations.
        except KeyboardInterrupt:
            self.axon.stop()

            bt.logging.success("Miner killed by keyboard interrupt.")
            exit()

        # In case of unforeseen errors, the miner will log the error and continue operations.
        except Exception as e:
            bt.logging.error(traceback.format_exc())

    def run_in_background_thread(self):
        """
        Override the base method to use our run method
        """
        if not self.is_running:
            bt.logging.debug("Starting yield neuron in background thread.")
            self.should_exit = False
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            self.is_running = True
            bt.logging.debug("Started")

