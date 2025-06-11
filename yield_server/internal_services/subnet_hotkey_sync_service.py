'''
This is the service that syncs the hotkeys of the miners registered on Subnet 43 allowing miners to bind to them using their leader accounts.
'''
from yield_server.config.constants import SUBNET_HOTKEY_SYNC_INTERVAL, VTRUST_THRESHOLD
from yield_server.backend.crud.subnetminerhotkey_crud import SubnetMinerHotkeyCRUD
from yield_server.backend.schema.subnetminerhotkey_schema import SubnetMinerHotkeyCreate, SubnetMinerHotkeyDeregister
from yield_server.backend.database.models import MinerStatus
from yield_server.utils.time import get_timestamp

import bittensor as bt

import os
from dotenv import load_dotenv

load_dotenv(override=True)

NETWORK = os.getenv("NETWORK")

class SubnetHotkeySyncService:
    def __init__(self):
        self.subnet_miner_hotkey_crud = SubnetMinerHotkeyCRUD()

    async def sync_hotkeys(self):
        # get all the hotkeys from the subnet
        print(f"Syncing hotkeys at timestamp: {get_timestamp()}")
        if NETWORK == "test":
            metagraph = bt.metagraph(netuid=65, network="test")
        else:
            metagraph = bt.metagraph(netuid=43, network="finney")
        new_hotkeys = []
        for hotkey, vtrust in zip(metagraph.hotkeys, metagraph.validator_trust):
            if vtrust < VTRUST_THRESHOLD:
                new_hotkeys.append(hotkey)

        # get all the active hotkeys from the database
        subnet_miner_hotkeys = await self.subnet_miner_hotkey_crud.get_all_active_hotkeys()
        subnet_miner_hotkey_addresses = [hotkey.hotkey for hotkey in subnet_miner_hotkeys]
        # compare the actual subnet hotkeys with the ones in the database
        deregistered_hotkeys = []
        for hotkey in subnet_miner_hotkey_addresses:
            if hotkey not in new_hotkeys:
                deregistered_hotkeys.append(hotkey)
        print(f"Deregistered hotkeys: {deregistered_hotkeys}")

        # deregister the hotkeys
        for hotkey in deregistered_hotkeys:
            await self.subnet_miner_hotkey_crud.deregister_hotkey(SubnetMinerHotkeyDeregister(hotkey=hotkey))

        new_unseen_hotkeys = []
        for hotkey in new_hotkeys:
            if hotkey not in subnet_miner_hotkey_addresses:
                new_unseen_hotkeys.append(hotkey)
        
        print(f"New unseen hotkeys: {new_unseen_hotkeys}")
        # create the hotkeys
        for hotkey in new_unseen_hotkeys:
            await self.subnet_miner_hotkey_crud.register_hotkey(SubnetMinerHotkeyCreate(hotkey=hotkey, status=MinerStatus.REGISTERED))

    async def run(self):
        while True:
            try:
                await self.sync_hotkeys()
                await asyncio.sleep(SUBNET_HOTKEY_SYNC_INTERVAL)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error in subnet hotkey sync service: {e}")
                await asyncio.sleep(SUBNET_HOTKEY_SYNC_INTERVAL)

