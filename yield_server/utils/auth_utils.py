from bittensor.utils import is_valid_ss58_address
from bittensor_wallet import Keypair
from dotenv import load_dotenv
import jwt
import os

from yield_server.errors.authentication_errors import InvalidSignature, InvalidSS58Address, InvalidMessage, InvalidJWT
from yield_server.config.constants import DEFAULT_EMAIL_TEMPLATE

load_dotenv()

def validate_jwt(jwt_token: str, audience: str = "authenticated", issuer: str = os.getenv("DEVELOPMENT_SUPABASE_JWT_ISSUER")) -> dict:
    '''
    Validates a JWT token.

    Args:
        jwt_token (str): The JWT token to validate
        audience Optional(str): The audience to validate the JWT token against
        issuer Optional(str): The issuer to validate the JWT token against

    Returns:
        dict: The payload of the JWT token
    '''
    secret = os.getenv("DEVELOPMENT_SUPABASE_JWT_SECRET")
    # Decode and verify the token
    options = {
        "verify_signature": True,
        "verify_exp": True
    }

    payload = jwt.decode(
        jwt_token,
        secret,
        algorithms=["HS256"],
        audience=audience,
        issuer=issuer,
        options=options
    )
    return payload
