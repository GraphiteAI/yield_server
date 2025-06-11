'''
This file contains the core logic for verifying the proxy of a copytrader.
'''

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from yield_server.core.subtensor_calls import get_block_extrinsics
import bittensor as bt
from bittensor.utils import is_valid_ss58_address
from scalecodec.utils.ss58 import ss58_encode
from scalecodec.types import GenericExtrinsic

# from typing import Literal, TypedDict # NOTE: if using python version < 3.12, import TypedDict from typing_extensions
import sys
from typing import Literal, List
if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

from async_substrate_interface import AsyncSubstrateInterface
# ARCHIVE_ENDPOINT = "wss://archive.chain.opentensor.ai:443"

class AddProxyCallArgs(TypedDict):
    delegate: str
    delay: Literal[0]
    proxy_type: Literal["Staking"]

class ProxyVerification(BaseModel):
    extrinsic_hash: str
    block_number: int
    copytrader_address: str

    @field_validator("extrinsic_hash")
    def validate_extrinsic_hash(cls, v):
        # check if the string starts with 0x if not append it
        if not v.startswith("0x"):
            v = "0x" + v
        # check if the hash matches the expected format
        if len(v) != 66:
            raise ValueError("Extrinsic hash must be 66 characters long (including the 0x prefix)")
        return v
    
    model_config = ConfigDict(extra="ignore")

class ProxyAddVerification(ProxyVerification):
    target_proxy: str

    call_function: Literal["add_proxy"] = "add_proxy"
    call_args: AddProxyCallArgs = {
        "delegate": "some_address",
        "delay": 0,
        "proxy_type": "Staking"
    }

    @model_validator(mode="after")
    def set_delegate(self):
        self.call_args["delegate"] = self.target_proxy
        return self

class ProxyRemoveVerification(ProxyVerification):
    call_function: Literal["remove_proxies"] = "remove_proxies"

async def verify_add_proxy(verify_add: ProxyAddVerification):
    ## Implement your own on-chain function to add proxy
    return False

async def verify_remove_proxies(verify_remove: ProxyRemoveVerification):
    ## Implement your own on-chain function to remove proxies
    return False
