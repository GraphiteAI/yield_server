from yield_server.backend.crud.copytrader_crud import CopyTraderCRUD
from yield_server.core.subtensor_calls import get_subnets_info
from yield_server.config.default_config import add_yield_args, add_args, check_config, config

from graphite.base.neuron import BaseNeuron
from graphite import __spec_version__ as spec_version
from graphite.utils.misc import ttl_get_block
from graphite.base.subnetPool import SubnetPool
from graphite.organic_protocol import OrganicPortfolioRequestSynapse, OrganicPortfolioResponseSynapse
from graphite.protocol import GraphV1PortfolioProblem, GraphV1PortfolioSynapse
from graphite.solvers.greedy_portfolio_solver import GreedyPortfolioSolver
from graphite.utils.graph_utils import get_portfolio_distribution_similarity

import bittensor as bt
from bittensor.core.settings import version_as_int

from fastapi import APIRouter, FastAPI
from abc import ABC, abstractmethod
import uvicorn
from pydantic import BaseModel, Field
from enum import Enum

import time
import copy
import threading
import traceback
import asyncio
import random
import numpy as np
import os
from typing import Union, List, Tuple
from dotenv import load_dotenv
load_dotenv(override=True)

class BaseNeuron(ABC):
    """
    Modified Graphite BaseNeuron to only keep the necessary components.
    """

    neuron_type: str = "BaseNeuron"

    @classmethod
    def check_config(cls, config: "bt.Config"):
        check_config(cls, config)

    @classmethod
    def add_args(cls, parser):
        add_args(cls, parser)

    @classmethod
    def config(cls):
        return config(cls)

    subtensor: "bt.subtensor"
    wallet: "bt.wallet"
    metagraph: "bt.metagraph"
    spec_version: int = spec_version

    @property
    def block(self):
        return ttl_get_block(self)

    def __init__(self, config=None):
        base_config = copy.deepcopy(config or BaseNeuron.config())
        self.config = self.config()
        self.config.merge(base_config)
        self.check_config(self.config)

        # Set up logging with the provided configuration.
        bt.logging.set_config(config=self.config.logging)

        # If a gpu is required, set the device to cuda:N (e.g. cuda:0)
        self.device = self.config.neuron.device

        # Log the configuration for reference.
        bt.logging.info(self.config)

        # Build Bittensor objects
        # These are core Bittensor classes to interact with the network.
        bt.logging.info("Setting up bittensor objects.")

        # The wallet holds the cryptographic key pairs for the neuron.
        self.subtensor = bt.subtensor(config=self.config)
        self.wallet = bt.wallet(config=self.config)
        self.metagraph: bt.Metagraph = bt.metagraph(netuid = self.config.netuid, network = self.config.subtensor.network)

        bt.logging.info(f"Wallet: {self.wallet}")
        bt.logging.info(f"Metagraph: {self.metagraph}")

        # Setting null self.uid
        self.uid = None
        self.last_update = self.block
        bt.logging.info(
            f"Running neuron on data from subnet: {self.config.netuid} with uid {self.uid}"
        )

    @abstractmethod
    async def forward(self, synapse: bt.Synapse) -> bt.Synapse:
        ...

    @abstractmethod
    def run(self):
        ...

    def sync(self):
        """
        Wrapper for synchronizing the state of the network for the given miner or validator.
        """
        try:
            if self.should_sync_metagraph():
                self.resync_metagraph()

            if self.should_set_weights():
                self.set_weights()
        except Exception as e:
            # While the asyncpong build for websocket-client seemingly reduced the crash rate of the validator during syncs, WebSocketBadStatusException raised occasionally  substrate query fails
            bt.logging.info(f"Substrate query failed, continuing with validation: {e}")
            pass

    def instantiate_pools(self, problem: Union[GraphV1PortfolioProblem]):
        current_pools = []
        for netuid, pool in enumerate(problem.pools):
            current_pools.append(SubnetPool(pool[0], pool[1], netuid))
        return current_pools

    def should_sync_metagraph(self):
        """
        Check if enough epoch blocks have elapsed since the last checkpoint to sync.
        """
        return (
            self.block - self.last_update
        ) > self.config.neuron.epoch_length

    def should_set_weights(self) -> bool:
        return False

class BaseYieldNeuron(BaseNeuron):

    neuron_type: str = "YieldNeuron"
    
    @classmethod
    def add_args(cls, parser):
        super().add_args(parser)
        add_yield_args(cls, parser)

    def __init__(self, config=None):
        super().__init__(config=config)

        # Warn if allowing incoming requests from anyone.
        if not self.config.blacklist.force_validator_permit:
            bt.logging.warning(
                "You are allowing non-validators to send requests to your miner. This is a security risk."
            )
        if self.config.blacklist.allow_non_registered:
            bt.logging.warning(
                "You are allowing non-registered entities to send requests to your miner. This is a security risk."
            )
        # The axon handles request processing, allowing validators to send this miner requests.
        self.axon = bt.axon(wallet=self.wallet, config=self.config() if callable(self.config) else self.config)
        # Attach determiners which functions are called when servicing a request.

        bt.logging.info(f"Axon created: {self.axon}")

        # Instantiate runners
        self.should_exit: bool = False
        self.is_running: bool = False
        self.thread: Union[threading.Thread, None] = None
        self.lock = asyncio.Lock()
        self.last_update = self.block

    
    def resync_metagraph(self):
        """Resyncs the metagraph and updates the hotkeys and moving averages based on the new metagraph."""
        bt.logging.info("resync_metagraph()")

        self.metagraph.sync(self.block)

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

        # Serve passes the axon information to the network + netuid we are hosting on.
        # This will auto-update if the axon port of external ip have changed.
        bt.logging.info(
            f"Serving yield axon {self.axon} on local environment"
        )

        # Start the axon, allowing it to receive incoming synapses.
        self.axon.start()

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
        Starts the yield neuron's operations in a separate background thread.
        This is useful for non-blocking operations.
        """
        if not self.is_running:
            bt.logging.debug("Starting yield neuron in background thread.")
            self.should_exit = False
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            self.is_running = True
            bt.logging.debug("Started")

    def stop_run_thread(self):
        """
        Stops the yield neuron's operations that are running in the background thread.
        """
        if self.is_running:
            bt.logging.debug("Stopping yield neuron in background thread.")
            self.should_exit = True
            if self.thread is not None:
                self.thread.join(5)
            self.is_running = False
            bt.logging.debug("Stopped")

    def __enter__(self):
        """
        Starts the miner's operations in a background thread upon entering the context.
        This method facilitates the use of the miner in a 'with' statement.
        """
        self.run_in_background_thread()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Stops the miner's background operations upon exiting the context.
        This method facilitates the use of the miner in a 'with' statement.

        Args:
            exc_type: The type of the exception that caused the context to be exited.
                      None if the context was exited without an exception.
            exc_value: The instance of the exception that caused the context to be exited.
                       None if the context was exited without an exception.
            traceback: A traceback object encoding the stack trace.
                       None if the context was exited without an exception.
        """
        self.stop_run_thread()