'''
This module is used to generate a proxy for a leader.

It queries the leader table and filters for leaders that have no proxy.

Then the proxy accounts are created and recorded in the database.
'''

from yield_server.backend.crud.leaderproxy_crud import LeaderProxyCRUD
# from yield_server.backend.schema.leaderproxy_schema import LeaderProxyRemoveStale

import bittensor as bt
from dotenv import load_dotenv
import os
import shutil
from cryptography.fernet import Fernet
import base64
from pydantic.types import UUID4
import shortuuid
import hashlib
from rich.prompt import Confirm

load_dotenv(override=True)

# Get the path from environment variables
home_user = os.path.expanduser('~')
mnemonic_path = os.getenv("TESTENV_MNEMONIC_FILEPATH")
wallet_path = os.getenv("TESTENV_WALLET_PATH")
archive_mnemonic_path = os.getenv("TESTENV_ARCHIVE_MNEMONIC_FILEPATH")
archive_wallet_path = os.getenv("TESTENV_ARCHIVE_WALLET_PATH")
abs_mnemonic_path = os.path.join(home_user, mnemonic_path)
abs_wallet_path = os.path.join(home_user, wallet_path)
abs_archive_mnemonic_path = os.path.join(home_user, archive_mnemonic_path)
abs_archive_wallet_path = os.path.join(home_user, archive_wallet_path)
# Check if the environment variable is set
if not mnemonic_path:
    raise ValueError("SAVED_MNEMONIC_FILEPATH environment variable is not set")
if not wallet_path:
    raise ValueError("TESTENV_WALLET_PATH environment variable is not set")

# Create the directory if it doesn't exist, ignore if it already exists
os.makedirs(abs_mnemonic_path, exist_ok=True)
os.makedirs(abs_wallet_path, exist_ok=True)
os.makedirs(abs_archive_mnemonic_path, exist_ok=True)
os.makedirs(abs_archive_wallet_path, exist_ok=True)

async def generate_and_save_keypair() -> bt.Keypair:
    coldkey_mnemonic = bt.Keypair.generate_mnemonic()
    coldkey = bt.Keypair.create_from_mnemonic(mnemonic=coldkey_mnemonic)
    # save the coldkey pair to local
    admin_hashkey = os.getenv("ADMIN_HASHKEY")
    # hash the admin hashkey using SHA256 to compress it to 32 bytes
    admin_hashkey_32b = hashlib.sha256(admin_hashkey.encode('utf-8')).digest()
    if not admin_hashkey_32b:
        raise ValueError("ADMIN_HASHKEY is not set")
    cipher_suite = Fernet(base64.urlsafe_b64encode(admin_hashkey_32b))
    encrypted_data = cipher_suite.encrypt(coldkey_mnemonic.encode('utf-8'))
    encrypted_mnemonic = base64.urlsafe_b64encode(encrypted_data).decode('utf-8')
    # generate a new text file named after the coldkey address that contains the hashed mnemonic
    with open(f"{abs_mnemonic_path}/{coldkey.ss58_address}.txt", "w") as f:
        f.write(encrypted_mnemonic)
    # hash the mnemonic and store in a separate database
    return coldkey

def get_proxy_wallet_name(leader_id: UUID4) -> str:
    return shortuuid.uuid(str(leader_id))

# NOTE: Only call this function if you have already checked that the leader has no proxy
async def create_proxy_for_leader(leader_id: UUID4) -> str:
    # we will name the proxy wallet after the leader id
    # we use shortuuid to encode the existing uuid to a compact uuid that is url safe
    url_safe_name = get_proxy_wallet_name(leader_id)
    proxy_keypair = await generate_and_save_keypair()
    # set the keypair as the coldkey in a new wallet
    # clean any existing wallet attributed to this leader id
    if os.path.exists(f"{abs_wallet_path}/{url_safe_name}"):
        # get the ss58 address of the existing wallet
        existing_wallet = bt.wallet(name=url_safe_name,path=abs_wallet_path)
        existing_ss58_address = existing_wallet.coldkeypub.ss58_address
        # move the existing wallet to the archive folder
        # we set the original name of the wallet first so that we can use glob to resolve all wallets to easily query all archived wallets of a leader
        shutil.move(f"{abs_wallet_path}/{url_safe_name}", f"{abs_archive_wallet_path}/{url_safe_name}_{existing_ss58_address}")
        # move the existing mnemonic to the archive folder
        shutil.move(f"{abs_mnemonic_path}/{url_safe_name}.txt", f"{abs_archive_mnemonic_path}/{url_safe_name}_{existing_ss58_address}.txt")
    try:
        wallet = bt.wallet(name=url_safe_name,path=abs_wallet_path)
        wallet.set_coldkey(
            proxy_keypair,
            save_coldkey_to_env=False,
            coldkey_password=os.getenv("TESTENV_WALLET_PASSWORD"),
            overwrite=False
            )
        wallet.set_coldkeypub(
            keypair=proxy_keypair, 
            encrypt=False, 
            overwrite=False
            )
        return wallet.coldkeypub.ss58_address
    except KeyboardInterrupt:
        print("KeyboardInterrupt: Exiting the program | Cleaning up the wallet")
    finally:
        # delete the keypair directory from the local path in the event of failure
        if os.path.exists(f"{abs_wallet_path}/{url_safe_name}"):
            shutil.rmtree(f"{abs_wallet_path}/{url_safe_name}")
