import socket
from typing import List, Union, Tuple
from async_substrate_interface import AsyncSubstrateInterface
from scalecodec.types import GenericCall
from bittensor import Keypair
from bittensor.utils import is_valid_ss58_address
from pydantic import BaseModel, Field, field_validator
from graphite.base.subnetPool import SubnetPool

def get_ip_address(domain):
    try:
        ip_address = socket.gethostbyname(domain)
        return ip_address
    except socket.gaierror:
        return "Error: Could not resolve the domain name."

class YieldPool(SubnetPool):
    def __init__(self, tao_in: int, alpha_in: int, netuid: int):
        super().__init__(tao_in, alpha_in, netuid)

    def compute_alpha_to_alpha_price(self, destination_pool: 'YieldPool', unstaked_alpha: int)->Tuple[int, int]:
        tao_out = self.swap_alpha_to_tao(unstaked_alpha)
        moved_alpha = destination_pool.swap_tao_to_alpha(tao_out)
        return int(moved_alpha * 1e9 / unstaked_alpha), int(tao_out) # division makes the value unitless | multiplication to map back to RAO units