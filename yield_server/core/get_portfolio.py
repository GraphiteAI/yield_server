import asyncio
import json
from typing import List, Dict, Any, Optional, Union
from fastapi import FastAPI, Query, Body, HTTPException, Depends, Header
from pydantic import BaseModel
from async_substrate_interface import AsyncSubstrateInterface
from substrateinterface import Keypair
from collections import defaultdict
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv(override=True)

NETWORK = os.getenv("NETWORK")

# Initialize FastAPI app
app = FastAPI()

if NETWORK == "test":
    URL = "wss://test.finney.opentensor.ai:443"
else:
    URL = "wss://entrypoint-finney.opentensor.ai:443"

async def get_coldkey_balance(substrate: AsyncSubstrateInterface, coldkey_ss58: str, block_hash: str):
    ## Implement your own function to get the coldkey balance on-chain
    return 0

def bytes_to_ss58_address(bytes_tuple, ss58_format=42):
    """
    Convert byte tuple to SS58 address format used by Substrate
    SS58 format 42 is specific to Substrate/Polkadot networks
    """
    bytes_data = bytes(bytes_tuple[0])
    keypair = Keypair(public_key=bytes_data, ss58_format=ss58_format)
    return keypair.ss58_address

def calculate_tao_stake(alpha_stake: float, netuid: int, subnets_info:dict) -> float:
    """
    - TaoInPool and AlphaInPool are from the subnet's info
    - alpha is the stake in the specific subnet
    """
    netuid_int = int(netuid)
    if netuid_int >= len(subnets_info):
        # If subnet not found, return original stake
        return 0
    if netuid_int == 0:
        return alpha_stake
    
    tao_in_pool = int(subnets_info[netuid_int].get('tao_in', 0))
    alpha_in_pool = int(subnets_info[netuid_int].get('alpha_in', 0))

    # Calculate k (constant product)
    k = tao_in_pool * alpha_in_pool
    
    if alpha_in_pool == 0 or k == 0:
        return 0
    
    # Calculate TAO stake based on AMM formula
    tau = tao_in_pool - (k / (alpha_in_pool + alpha_stake))
    return max(tau, 0)


async def get_personal_portfolio_info(coldkey, substrate=None) -> Dict:
    ## Implement your own function to get the personal portfolio info
    return {}

async def get_protected_portfolio_info(coldkey, substrate=None) -> Dict:

    portfolio_data = await get_personal_portfolio_info(coldkey, substrate)
    # filter out information that is not needed for the protected portfolio
    protected_portfolio = portfolio_data.copy()    
    return protected_portfolio

async def get_protected_portfolio_info_leader(coldkey, substrate=None) -> Dict:

    portfolio_data = await get_personal_portfolio_info(coldkey, substrate)
    # filter out information that is not needed for the protected portfolio leader
    protected_portfolio = portfolio_data.copy()     
    return protected_portfolio

