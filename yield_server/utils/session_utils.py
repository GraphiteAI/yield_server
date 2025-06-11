from supabase import AsyncClient, acreate_client
from gotrue.errors import AuthApiError

from dotenv import load_dotenv
import os

from pydantic.types import UUID4
from typing import Optional
from yield_server.config.constants import DEFAULT_EMAIL_TEMPLATE

load_dotenv()

def match_user(user_id: UUID4, valid_jwt: str) -> Optional[UUID4]:
    '''
    Matches a user ID to a JWT token. Determines if the user ID associated with the resource matches the requester's user ID as implied by the JWT token.

    NOTE: only use this function if the resource has a public/private interaction and after the JWT has been validated.
    
    Args:
        user_id (UUID4): The user ID of the resource
        valid_jwt (str): The decoded JWT token of the requester
    
    Returns:
        Optional[UUID4]: The user ID of the requester if the user ID matches the JWT token, otherwise None
    '''
    # extract the user ID from the JWT token
    if not isinstance(valid_jwt, dict):
        raise ValueError("Invalid JWT token")
    
    try:
        requester_id = valid_jwt["sub"]
    except KeyError:
        raise ValueError("Invalid JWT token")
    # compare the user ID but make sure to cast both to strings
    return requester_id == str(user_id)


async def user_login(address: str, password: str):
    '''
    Logs a user in to the system.

    Args:
        coldkey (SS58_ADDRESS): The coldkey of the user
        password (str): The password of the user
    
    Returns:
        dict: The payload of the JWT token
    '''
    supabase_client = await acreate_client(
        supabase_url=os.getenv("DEVELOPMENT_SUPABASE_URL"),
        supabase_key=os.getenv("DEVELOPMENT_SUPABASE_SERVICE_ROLE_KEY")
    )

    credentials = {
        "email": DEFAULT_EMAIL_TEMPLATE.format(address=address),
        "password": password
    }

    response = await supabase_client.auth.sign_in_with_password(
        credentials
    )
    return response.model_dump()

async def refresh_session(refresh_token: str) -> dict:
    '''
    Refreshes the session token and returns the new JWT token and refresh token.
    
    In the future, as we change the structure of the yield problem (allowing for multiple windows), 
    then this will be useful to reduce the need to re-authenticate.

    Returns:
        dict: The payload of the JWT token
    '''
    # NOTE
    supabase_client = await acreate_client(
        supabase_url=os.getenv("DEVELOPMENT_SUPABASE_URL"),
        supabase_key=os.getenv("DEVELOPMENT_SUPABASE_SERVICE_ROLE_KEY")
    )
    response = await supabase_client.auth.refresh_session(refresh_token)
    return response.model_dump()

async def user_logout(jwt: str) -> bool:
    '''
    Logs a user out of the system.

    returns True or raises errors associated with Supabase Auth API
    '''
    supabase_client = await acreate_client(
        supabase_url=os.getenv("DEVELOPMENT_SUPABASE_URL"),
        supabase_key=os.getenv("DEVELOPMENT_SUPABASE_SERVICE_ROLE_KEY")
    )
    try:
        await supabase_client.auth.admin.sign_out(jwt)
    except Exception as e:
        pass
    return True

