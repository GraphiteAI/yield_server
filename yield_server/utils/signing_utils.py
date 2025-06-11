from pydantic import BaseModel, Field, model_validator, ConfigDict, field_validator
from yield_server.config.constants import SS58_ADDRESS_LENGTH
from bittensor.utils import is_valid_ss58_address
from fastapi import HTTPException
from bittensor_wallet import Keypair
from typing import Optional

class UnverifiedSignaturePayload(BaseModel):
    message: str = Field(..., description="The message that was signed.")
    signature: str = Field(..., description="The signature of the message.")
    address: str = Field(..., min_length=SS58_ADDRESS_LENGTH, max_length=SS58_ADDRESS_LENGTH, description="The hotkey that was used to sign the message.")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid" # forbid any extra fields to limit the risk of malicious payloads
        )

    @field_validator("address", mode="before")
    def validate_ss58_address(cls, v):
        if not is_valid_ss58_address(v):
            raise HTTPException(status_code=400, detail="Hotkey is not a valid SS58 address")
        return v
    
    @field_validator("signature", mode="before")
    def append_0x(cls, v):
        if not v.startswith("0x"):
            return f"0x{v}"
        return v

def verify_signature(signature_payload: UnverifiedSignaturePayload) -> bool:
    """
    Verifies the cryptographic signature of the nonce using Bittensor's Keypair.
    
    Args:
        message (str): The message that was signed.
        signature (str): The provided signature.
        address (str): The address that was used to sign the message.
    
    Returns:
        bool: True if the signature is valid; False otherwise.
    """
    try:
        keypair = Keypair(ss58_address=signature_payload.address)
        return keypair.verify(signature_payload.message, signature_payload.signature)
    except Exception as e:
        print(f"Error verifying signature: {e}")
        return False
    
