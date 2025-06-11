from fastapi import APIRouter, FastAPI
from bittensor.core.chain_data import AxonInfo

from bittensor.utils import networking

from yield_server.utils.validator_utils import get_ip_address
from yield_server.config.constants import YIELD_VALIDATOR_SERVICE_ADDRESS, YIELD_VALIDATOR_REBALANCING_PORT, YIELD_VALIDATOR_PERFORMANCE_PORT, YIELD_SIGNER_HOTKEY, YIELD_SIGNER_COLDKEY
from bittensor.core.settings import version_as_int

'''
This service is necessary because the validator's can't simply sync with the metagraph to get updates on the axon info of the yield neuron since the yield neuron is not a registered neuron.

The getters defined here are used to pass the appropriate AxonInfo to the validators so that the can communication with our server for organic_forward and yield_forward information
'''

router = APIRouter(prefix="/api/v1/validator", tags=["Validator Information Service"])

@router.get("/rebalancing_info", response_model=AxonInfo)
async def rebalancing_info():
    return AxonInfo(
        version=version_as_int,
        ip=get_ip_address(YIELD_VALIDATOR_SERVICE_ADDRESS),
        port=YIELD_VALIDATOR_REBALANCING_PORT,
        hotkey=YIELD_SIGNER_HOTKEY,
        coldkey=YIELD_SIGNER_COLDKEY,
        protocol=4,
        ip_type=networking.ip_version(get_ip_address(YIELD_VALIDATOR_SERVICE_ADDRESS))
    )

@router.get("/performance_info", response_model=AxonInfo)
async def performance_info():
    return AxonInfo(
        version=version_as_int,
        ip=get_ip_address(YIELD_VALIDATOR_SERVICE_ADDRESS),
        port=YIELD_VALIDATOR_PERFORMANCE_PORT,
        hotkey=YIELD_SIGNER_HOTKEY,
        coldkey=YIELD_SIGNER_COLDKEY,
        protocol=4,
        ip_type=networking.ip_version(get_ip_address(YIELD_VALIDATOR_SERVICE_ADDRESS))
    )

app = FastAPI(
    title="Validator Endpoint",
    description="A service for validating requests from validators",
    version="1.0.0"
)

app.include_router(router)

