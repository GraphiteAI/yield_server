import bittensor as bt
import asyncio
from pprint import pprint
from bittensor.core.chain_data import (
    DynamicInfo,
    StakeInfo,
)
from bittensor.core.chain_data.utils import decode_account_id
from async_substrate_interface import AsyncSubstrateInterface
from typing import Optional, List
import copy
import os
from dotenv import load_dotenv

load_dotenv(override=True)

current_mode = os.getenv("NETWORK")
if current_mode == "test":
    specified_netuid = 65
else:
    specified_netuid = 43

async def get_wallet_stakes(coldkey_ss58:str, hotkey_ss58:Optional[str]=None, async_subtensor:Optional[bt.AsyncSubtensor]=None, include_free:bool=True):
    ## Implement your own method of getting the wallet stakes on-chain
    return {}

async def check_leader_wallet_start_valid(coldkey_ss58:str, hotkey_ss58:str, min_stake:int=5*1e9, max_stake:int=15*1e9, async_subtensor:bt.AsyncSubtensor=None):
    wallet_stake = await get_wallet_stakes(coldkey_ss58, hotkey_ss58, async_subtensor)
    netuid = 0
    # a valid leader wallet has a starting balance of 5-15 staked tao, nothing else.
    if len(wallet_stake) == 1 and netuid in wallet_stake:
        if wallet_stake[netuid] >= min_stake and wallet_stake[netuid] <= max_stake:
            return True
    return False

async def get_subnets_info(async_subtensor:bt.AsyncSubtensor=None):
    async_subtensor = bt.AsyncSubtensor(current_mode) 
    await async_subtensor.initialize()
    subnets = await async_subtensor.all_subnets()
    subnets.sort(key=lambda x: x.netuid)
    return subnets

async def get_wallet_stakes_in_rao(subnets_info: list[DynamicInfo], stakes: dict[int, int]):
    ## Implement your own method of getting the sum of wallet stakes on-chain
    return 0

# Helper function to get the stakes for a list of coldkeys
async def get_coldkeys_stakes(coldkeys: List[str], async_subtensor:bt.AsyncSubtensor=None) -> dict[str, List[StakeInfo]]:
    ## Implement your own method of getting the stakes for a list of coldkeys on-chain
    return {}

async def get_hotkey_level_portfolio(coldkey: str, async_subtensor:Optional[bt.AsyncSubtensor]=None) -> dict[str, dict[int, float]]:
    ## Implement your own method of getting the hotkey level portfolio on-chain
    return {}

async def get_portfolios_value_in_rao(
        converted_portfolio_distributions: Optional[dict[str, dict[int, float]]] = None, 
        subnet_infos: Optional[list[DynamicInfo]] = None, 
        async_subtensor:Optional[bt.AsyncSubtensor]=None,
        coldkeys: Optional[List[str]] = None,
        include_free: bool = True
        ) -> dict[str, float]:
    ## Implement your own method of getting the portfolio values in rao on-chain
    return {}

async def get_percentage_portfolios(
        converted_portfolio_distributions: Optional[dict[str, dict[int, float]]] = None, 
        subnet_infos: Optional[list[DynamicInfo]] = None, 
        async_subtensor:Optional[bt.AsyncSubtensor]=None,
        coldkeys: Optional[List[str]] = None
        ) -> dict[str, dict[int, float]]:
    ## Implement your own method of getting the percentage portfolios on-chain
    return {}

async def get_current_block_number(async_subtensor:bt.AsyncSubtensor=None):
    async_subtensor = bt.AsyncSubtensor(current_mode)
    await async_subtensor.initialize()
    block = await async_subtensor.get_current_block()
    return block

async def get_registered_miner_hotkeys(async_subtensor:bt.AsyncSubtensor=None):
    async_subtensor = bt.AsyncSubtensor(current_mode)
    await async_subtensor.initialize()
    metagraph = await async_subtensor.metagraph(netuid=specified_netuid, network=current_mode)
    miner_hotkeys = []
    for hotkey, vtrust in zip(metagraph.hotkeys, metagraph.validator_trust):
        if vtrust < 0.01:
            miner_hotkeys.append(hotkey)
    return miner_hotkeys


async def coldkey_extrinsic(coldkeys: list[str], extrinsics) -> list:
    ## Implement your own method of processing on-chain extrinsics
    return []
