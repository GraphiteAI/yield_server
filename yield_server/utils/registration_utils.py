from yield_server.utils.auth_utils import validate_jwt
from yield_server.config.constants import DEFAULT_EMAIL_TEMPLATE
from yield_server.backend.database.models import UserRole

from supabase import AsyncClient, acreate_client
from pydantic.types import UUID4
from dotenv import load_dotenv
import os

from gotrue.errors import AuthApiError
from gotrue.types import AdminUserAttributes

load_dotenv(override=True)

# NOTE: in the future if we want to enrich the data contained within the JWT token, we should include the user's role in the metadata
# that would require sync between the user role in the local postgres and with the supabase user metadata which will increase latency
async def create_new_user(coldkey: str, password: str):
    '''
    Creates a new user in the database.

    Args:
        coldkey (str): The coldkey of the user
        password (str): The password of the user
    
    Returns:
        dict: The payload of the JWT token
    '''
    # Given a coldkey, we register an account using a dummy email address and password
    dummy_email = DEFAULT_EMAIL_TEMPLATE.format(address=coldkey)
    dummy_password = password
    user_metadata = {
        "Name": f"Mock User: {coldkey}",
        "email": dummy_email
    }
    credentials = {
        "email": dummy_email,
        "password": dummy_password,
        "options": {
            "data": user_metadata
        }
    }
    # If the coldkey already exists then it means that this account was once used by a leader. 
    # Reset the state associated with this account because it belongs to a re-registered miner.
    supabase_client: AsyncClient = await acreate_client(
        os.getenv("DEVELOPMENT_SUPABASE_URL"),
        os.getenv("DEVELOPMENT_SUPABASE_SERVICE_ROLE_KEY")
    )

    session = await supabase_client.auth.sign_up(
        credentials
    )
    return session.model_dump()
    
async def delete_user(user_id: UUID4):
    '''
    Deletes a user from the system.
    '''
    supabase_client = await acreate_client(
        supabase_url=os.getenv("DEVELOPMENT_SUPABASE_URL"),
        supabase_key=os.getenv("DEVELOPMENT_SUPABASE_SERVICE_ROLE_KEY")
    )
    await supabase_client.auth.admin.delete_user(user_id)
    return

async def reset_password(user_id: UUID4, password: str):
    '''
    Resets the password of a user. The UUID4 user id can be found from the users table by querying the primary key where the address matches the requestor's address.
    '''
    supabase_client = await acreate_client(
        supabase_url=os.getenv("DEVELOPMENT_SUPABASE_URL"),
        supabase_key=os.getenv("DEVELOPMENT_SUPABASE_SERVICE_ROLE_KEY")
    )

    user = await supabase_client.auth.admin.update_user_by_id(
        user_id,
        attributes = AdminUserAttributes(
            password=password
        )
    )
    return user.model_dump()

