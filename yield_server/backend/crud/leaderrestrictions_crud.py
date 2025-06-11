# leader transaction hears all the leaders' transactions
# leader transactions appends to leader restrictions
# leader transactions also pushes for organic portfolio reallocation if block number >= any leader first_no_trade_block_number
# update leader transaction volume

from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from pydantic.types import UUID4
from datetime import datetime
from yield_server.utils.time import get_timestamp   

from yield_server.backend.database.db import async_session

from yield_server.backend.database.models import LeaderRestrictions, Leader, LeaderStatus, LeaderViolation
from yield_server.backend.schema.leaderrestrictions_schema import LeaderRestrictionCreate, LeaderRestrictionOut, LeaderRestrictionUpdate

from yield_server.backend.crud.leaderviolations_crud import LeaderViolationCRUD
from yield_server.backend.schema.leaderviolations_schema import LeaderViolationCreate
from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.schema.leader_schema import LeaderOutPrivate
from sqlalchemy.ext.asyncio import AsyncSession

leader_crud = LeaderCRUD()

class LeaderRestrictionCRUD:
    '''
    CRUD operations for LeaderRestriction
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session
        self.leader_violation_crud = LeaderViolationCRUD(session=session) # ensure the nested crud has the same session maker as the parent

    async def create_restriction(self, restriction: LeaderRestrictionCreate) -> LeaderRestrictionOut:
        '''
        Create a new leader restriction
        '''
        async with self.session.begin() as session:

            # check if leader exists
            leader = await session.get(Leader, restriction.leader_id)
            if not leader:
                raise ValueError(f"Leader with id {restriction.leader_id} does not exist")
            
            # check if leader is active
            if leader.status != LeaderStatus.ACTIVE:
                raise ValueError(f"Leader with id {restriction.leader_id} is not active | Unable to create restriction")
            
            new_restriction = LeaderRestrictions(
                **restriction.model_dump(),
            )

            session.add(new_restriction)
            await session.flush()
            await session.refresh(new_restriction)
            return LeaderRestrictionOut.model_validate(new_restriction)
        
    async def get_restriction(self, leader_id: UUID4) -> LeaderRestrictionOut:
        '''
        Get a leader restriction by leader_id
        '''
        async with self.session.begin() as session:
            restriction = await session.get(LeaderRestrictions, leader_id)
            if not restriction:
                raise ValueError(f"Restriction with leader_id {leader_id} does not exist")
            
            return LeaderRestrictionOut.model_validate(restriction)
        
    async def get_all_restrictions(self) -> list[LeaderRestrictionOut]:
        '''
        Get all leader restrictions for active leaders
        '''
        async with self.session.begin() as session:
            # load all active leaders
            active_leaders = await leader_crud.get_all_active_leaders_private()
            stmt = select(LeaderRestrictions).where(LeaderRestrictions.leader_id.in_([leader.id for leader in active_leaders]))
            result = await session.execute(stmt)
            restrictions = result.scalars().all()
            return [LeaderRestrictionOut.model_validate(restriction) for restriction in restrictions]
        
    async def update_restriction(self, transaction_info: LeaderRestrictionUpdate) -> LeaderRestrictionOut:
        '''
        Update a leader restriction
        '''
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            leader = await session.get(Leader, transaction_info.leader_id)
            if not leader:
                raise ValueError(f"Leader with id {transaction_info.leader_id} does not exist")
            if leader.status != LeaderStatus.ACTIVE:
                raise ValueError(f"Leader with id {transaction_info.leader_id} is not active | Unable to update restriction")
            
            # create leader restriction if it does not exist
            existing_restriction = await session.get(LeaderRestrictions, transaction_info.leader_id)
            if not existing_restriction:
                new_restriction = LeaderRestrictionCreate(
                    leader_id=transaction_info.leader_id,
                    first_non_violated_trading_block_number=transaction_info.transaction_block_number,
                    first_no_trade_block_number=transaction_info.transaction_block_number+300,
                    last_no_trade_block_number=transaction_info.transaction_block_number+7200,
                )
                await self.create_restriction(new_restriction)
                return LeaderRestrictionOut.model_validate(new_restriction)
            else:
                validated_existing_restriction = LeaderRestrictionOut.model_validate(existing_restriction)
            
            # check if the transaction block violated anything 
            if transaction_info.transaction_block_number >= existing_restriction.first_no_trade_block_number and transaction_info.transaction_block_number <= existing_restriction.last_no_trade_block_number:
                # update the violation
                try: # we could be revising this block due to saved state and leader could already be violated
                    await self.leader_violation_crud.create_violation(violation=LeaderViolationCreate(
                        leader_id=transaction_info.leader_id,
                        violation_message=f"Transaction hash {transaction_info.extrinsic_hash} in block number {transaction_info.transaction_block_number} violates the restriction",
                        created_at=current_ts,
                    ), session=session)
                except:
                    pass
                return validated_existing_restriction
            elif transaction_info.transaction_block_number > existing_restriction.last_no_trade_block_number:
                # update the restriction
                first_non_violated_trading_block_number = transaction_info.transaction_block_number
                stmt = (
                    update(LeaderRestrictions)
                    .where(LeaderRestrictions.leader_id == transaction_info.leader_id)
                    .values(
                        first_non_violated_trading_block_number=first_non_violated_trading_block_number,
                        first_no_trade_block_number=first_non_violated_trading_block_number+300,
                        last_no_trade_block_number=first_non_violated_trading_block_number+7200,
                    )
                )

                await session.execute(stmt)
                updated_restriction = await session.get(LeaderRestrictions, transaction_info.leader_id)
                return LeaderRestrictionOut.model_validate(updated_restriction)
            else:
                return validated_existing_restriction
                
