from yield_server.backend.schema.leadertransactions_schema import LeaderTransactionCreate, LeaderTransactionOut
from yield_server.backend.schema.leaderviolations_schema import LeaderViolationCreate
from yield_server.backend.schema.leaderrestrictions_schema import LeaderRestrictionOut
from yield_server.backend.schema.leader_schema import LeaderUpdateBlock, LeaderOutPrivate, LeaderGet
from yield_server.backend.schema.leaderportfolio_schema import LeaderPortfolioUpsert, LeaderPortfolioOut

from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.crud.user_crud import UserCRUD
from yield_server.backend.crud.leadertransactions_crud import LeaderTransactionCRUD
from yield_server.backend.crud.leaderviolations_crud import LeaderViolationCRUD
from yield_server.backend.crud.leaderrestrictions_crud import LeaderRestrictionCRUD
from yield_server.backend.crud.leaderportfolio_crud import LeaderPortfolioCRUD

from yield_server.core.subtensor_calls import coldkey_extrinsic, get_current_block_number, get_block_extrinsics, get_percentage_portfolios

from yield_server.endpoints.rebalancing_service import hash_portfolio

from pprint import pprint
import bittensor as bt
from async_substrate_interface import AsyncSubstrateInterface
from yield_server.utils.time import get_timestamp

from yield_server.backend.database.models import LeaderStatus
from fastapi import HTTPException

import time
import os
from dotenv import load_dotenv

load_dotenv(override=True)

class TransactionService:
    '''
    Transaction service to keep track of all leader on-chain transactions
    '''
    def __init__(self):
        self.leader_crud = LeaderCRUD()
        self.user_crud = UserCRUD()
        self.leader_transaction_crud = LeaderTransactionCRUD()
        self.leader_violation_crud = LeaderViolationCRUD()
        self.leader_restriction_crud = LeaderRestrictionCRUD()
        self.leader_portfolio_crud = LeaderPortfolioCRUD()

        NETWORK = os.getenv("NETWORK")
        self.network = NETWORK
    
    async def update_new_transactions(self):
        '''
        This function will check for new transactions and update the database
        '''

        async def get_current_active_leaders():
            active_leaders = await self.leader_crud.get_all_active_leaders_private()

            all_last_checked_block_number = []
            leader_coldkeys = []
            leader_coldkeys_dict = {}
                
            leader_restrictions = await self.leader_restriction_crud.get_all_restrictions()
            leader_res = {}
            for leader_restriction in leader_restrictions:
                leader_res[leader_restriction.leader_id] = leader_restriction.first_no_trade_block_number

            for active_leader in active_leaders:
                start_block_number = active_leader.start_block_number
                last_checked_block_number = getattr(active_leader, "last_checked_block_number", start_block_number)
                if last_checked_block_number is None:
                    last_checked_block_number = start_block_number
                coldkey = active_leader.address # leader coldkey
                leader_coldkeys.append(coldkey)
                leader_coldkeys_dict[coldkey] = {"id": active_leader.id, "start_block_number": start_block_number, "rebalance_block_number": leader_res.get(active_leader.id, 99999999999)}
                all_last_checked_block_number.append(last_checked_block_number)
                # print("start block", start_block_number, "last checked", last_checked_block_number, "coldkey", coldkey)
        
            starting_check_block_number = min(all_last_checked_block_number)+1
            return active_leaders, leader_coldkeys, leader_coldkeys_dict, starting_check_block_number
        
        try:
            async_subtensor = bt.AsyncSubtensor(self.network)
            await async_subtensor.initialize()
            
            if self.network == "test" :
                async_substrate = AsyncSubstrateInterface(
                    url="wss://test.finney.opentensor.ai:443",
                    ss58_format=42,)
            else:
                async_substrate = AsyncSubstrateInterface(
                    url="wss://archive.chain.opentensor.ai:443",
                    ss58_format=42,)
            await async_substrate.initialize()
        except Exception as e:
            print(f"Error occurred: {e}")
            try:
                await async_subtensor.close()
            except Exception:
                pass
            try:
                await async_substrate.close()
            except Exception:
                pass
            
            # Recreate and reinitialize connections
            
            if "429" in str(e):
                print("Received 429 Too Many Requests. Waiting 1 hour before retrying...")
                await asyncio.sleep(3600)  # 1 hour
            else:
                await asyncio.sleep(60)  # 1 minute for other errors

            async_subtensor = bt.AsyncSubtensor(self.network)
            await async_subtensor.initialize()
            if self.network == "test":
                async_substrate = AsyncSubstrateInterface(
                    url="wss://test.finney.opentensor.ai:443",
                    ss58_format=42,
                )
            else:
                async_substrate = AsyncSubstrateInterface(
                    url="wss://archive.chain.opentensor.ai:443",
                    ss58_format=42,
                )
            await async_substrate.initialize()

        while True:
            try:
                time1 = time.time()
                active_leaders, leader_coldkeys, leader_coldkeys_dict, starting_check_block_number = await get_current_active_leaders()
                print("[Get Current Active Leaders] Time taken:", time.time() - time1)

                current_block_number = await get_current_block_number(async_subtensor)
                print("[Current block number]", current_block_number)
                print("[Checking blocks]", starting_check_block_number, "->", current_block_number)

                while starting_check_block_number <= current_block_number:
                    active_leaders = await self.leader_crud.get_all_active_leaders_private()
                    latest_leader_coldkeys = [active_leader.address for active_leader in active_leaders]
                    leader_coldkeys = [coldkey for coldkey in leader_coldkeys if coldkey in latest_leader_coldkeys]

                    print("[Block Number]", starting_check_block_number, "| [LEADERS]", [active_leader.id for active_leader in active_leaders])
                    extrinsics = await get_block_extrinsics(async_substrate, starting_check_block_number, self.network)

                    assert extrinsics['header']['number'] == starting_check_block_number, "Block number mismatch"

                    for coldkey, leader_info in leader_coldkeys_dict.items():
                        if leader_info['rebalance_block_number'] == starting_check_block_number:
                            leader: LeaderOutPrivate = await self.leader_crud.get_leader_by_id_private(LeaderGet(id=leader_info['id']))
                            if not leader:
                                raise HTTPException(status_code=404, detail="Leader not found")
                            elif leader.status != LeaderStatus.ACTIVE:
                                raise HTTPException(status_code=400, detail="Leader is not active")
                            leader_ss58_address = leader.address
                            portfolio_distributions: dict[str, dict[int, float]] = await get_percentage_portfolios(coldkeys=[leader_ss58_address]) # dict of dict representing the portfolio distributions
                            portfolio_distribution = portfolio_distributions[leader_ss58_address]
                            portfolio_hash = hash_portfolio(portfolio_distribution)

                            await self.leader_portfolio_crud.upsert_portfolio(LeaderPortfolioUpsert(
                                leader_id=leader_info['id'],
                                portfolio_distribution=portfolio_distribution,
                                portfolio_hash=portfolio_hash
                            ))

                    extrinsics_to_process = await coldkey_extrinsic(leader_coldkeys, extrinsics)
                    for process_extrinsic in extrinsics_to_process:
                        if process_extrinsic['block_number'] >= leader_coldkeys_dict[process_extrinsic['address']]['start_block_number']:
                            if process_extrinsic['function_type'] == "Bounded" or process_extrinsic['function_type'] == "Violated":
                                await self.leader_transaction_crud.create_transaction(LeaderTransactionCreate(
                                    leader_id=leader_coldkeys_dict[process_extrinsic['address']]['id'],
                                    call_function=process_extrinsic['extrinsic_call'],
                                    block_number=process_extrinsic['block_number'],
                                    extrinsic_hash=process_extrinsic['extrinsic_hash'],
                                ))
                            if process_extrinsic['function_type'] == "Violated":
                                target_id = leader_coldkeys_dict[process_extrinsic['address']].get("id")
                                if not target_id:
                                    continue 
                                try: # leader could have already violated on the block trade
                                    await self.leader_violation_crud.create_violation(violation=LeaderViolationCreate(
                                            leader_id=target_id,
                                            violation_message=f"Transaction hash {process_extrinsic['extrinsic_hash']} in block number {process_extrinsic['block_number']} violates the restriction",
                                            created_at=get_timestamp(),
                                        ))
                                except:
                                    pass

                    if starting_check_block_number % 300 == 0:
                        for active_leader in active_leaders:
                            if active_leader.last_checked_block_number is None or (type(active_leader.last_checked_block_number) == int and active_leader.last_checked_block_number < starting_check_block_number):
                                await self.leader_crud.update_leader_last_checked_block_number(LeaderUpdateBlock(
                                    id=active_leader.id,
                                    last_checked_block_number=int(starting_check_block_number)
                                ))
                        # resync every 300 blocks, ie 1hr
                        active_leaders, leader_coldkeys, leader_coldkeys_dict, starting_check_block_number = await get_current_active_leaders()
                    
                    starting_check_block_number += 1

                for active_leader in active_leaders:
                    if active_leader.last_checked_block_number is None or (type(active_leader.last_checked_block_number) == int and active_leader.last_checked_block_number < starting_check_block_number):
                        await self.leader_crud.update_leader_last_checked_block_number(LeaderUpdateBlock(
                            id=active_leader.id,
                            last_checked_block_number=int(starting_check_block_number-1)
                        ))

                await asyncio.sleep(5)

            except Exception as e:
                print(f"Error occurred: {e}")
                try:
                    await async_subtensor.close()
                except Exception:
                    pass
                try:
                    await async_substrate.close()
                except Exception:
                    pass
                
                # Recreate and reinitialize connections
                
                if "429" in str(e):
                    print("Received 429 Too Many Requests. Waiting 1 hour before retrying...")
                    await asyncio.sleep(3600)  # 1 hour
                else:
                    await asyncio.sleep(60)  # 1 minute for other errors

                async_subtensor = bt.AsyncSubtensor(self.network)
                await async_subtensor.initialize()
                if self.network == "test":
                    async_substrate = AsyncSubstrateInterface(
                        url="wss://test.finney.opentensor.ai:443",
                        ss58_format=42,
                    )
                else:
                    async_substrate = AsyncSubstrateInterface(
                        url="wss://archive.chain.opentensor.ai:443",
                        ss58_format=42,
                    )
                await async_substrate.initialize()


