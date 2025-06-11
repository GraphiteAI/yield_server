from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from pydantic.types import UUID4
from datetime import datetime
from yield_server.utils.time import get_timestamp

from yield_server.backend.database.db import async_session

from yield_server.backend.database.models import LeaderTransactions, Leader, LeaderStatus
from yield_server.backend.schema.leadertransactions_schema import LeaderTransactionCreate, LeaderTransactionOut
from yield_server.backend.schema.leaderrestrictions_schema import LeaderRestrictionUpdate
from yield_server.backend.schema.leader_schema import LeaderUpdateBlock

from yield_server.backend.crud.leaderrestrictions_crud import LeaderRestrictionCRUD
from yield_server.backend.crud.leader_crud import LeaderCRUD

from sqlalchemy.ext.asyncio import AsyncSession


class LeaderTransactionCRUD:
    '''
    CRUD operations for LeaderTransaction

    GET: Allows retrieving a leader transaction by transaction_id and leader_id
    POST: Allows creating a new leader transaction
    
    NO PUT: Leader transactions are immutable and should not be updated
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session
        self.leader_restriction_crud = LeaderRestrictionCRUD(session=session)
        self.leader_crud = LeaderCRUD(session=session)

    async def create_transaction(self, transaction: LeaderTransactionCreate) -> LeaderTransactionOut:
        '''
        Create a new leader transaction
        '''
        current_ts = get_timestamp()
        async with self.session.begin() as session:

            # check if leader exists
            leader = await session.get(Leader, transaction.leader_id)
            if not leader:
                raise ValueError(f"Leader with id {transaction.leader_id} does not exist")
            
            # check if leader is active
            if leader.status != LeaderStatus.ACTIVE:
                raise ValueError(f"Leader with id {transaction.leader_id} is not active | Unable to create transaction")
            
            new_transaction = LeaderTransactions(
                **transaction.model_dump(),
                created_at=current_ts,
            )

            if (leader.last_checked_block_number == None) or (type(leader.last_checked_block_number) == int and transaction.block_number >= leader.last_checked_block_number):
                session.add(new_transaction)
                await session.flush()
                await session.refresh(new_transaction)
                await self.leader_restriction_crud.update_restriction( 
                    transaction_info=LeaderRestrictionUpdate(
                        leader_id=transaction.leader_id,
                        transaction_block_number=transaction.block_number,
                        extrinsic_hash=transaction.extrinsic_hash
                    )
                )

            if type(leader.last_checked_block_number) == int and leader.last_checked_block_number < transaction.block_number:
                await self.leader_crud.update_leader_last_checked_block_number(LeaderUpdateBlock(
                    id=transaction.leader_id,
                    last_checked_block_number=int(transaction.block_number)
                ))

            return LeaderTransactionOut.model_validate(new_transaction)
        
    async def get_transaction(self, transaction_id: UUID4, leader_id: UUID4) -> LeaderTransactionOut:
        '''
        Get a leader transaction by id
        '''
        async with self.session.begin() as session:
            transaction = await session.get(LeaderTransactions, transaction_id)
            if not transaction:
                raise ValueError(f"Transaction with id {transaction_id} does not exist")
            
            if transaction.leader_id != leader_id:
                raise ValueError(f"Transaction with id {transaction_id} does not belong to leader with id {leader_id}")
            
            return LeaderTransactionOut.model_validate(transaction)

    async def get_transactions_by_leader(self, leader_id: UUID4) -> list[LeaderTransactionOut]:
        '''
        Get all transactions for a leader
        '''
        async with self.session.begin() as session:
            transactions = await session.execute(
                select(LeaderTransactions)
                .where(LeaderTransactions.leader_id == leader_id)
            )
            return [LeaderTransactionOut.model_validate(transaction) for transaction in transactions.scalars().all()]
        
    async def delete_transaction(self, transaction_id: UUID4) -> bool:
        '''
        Delete a leader transaction by transaction_id
        '''
        async with self.session.begin() as session:
            stmt = delete(LeaderTransactions).where(LeaderTransactions.transaction_id == transaction_id)
            result = await session.execute(stmt)
            if not result.rowcount:
                raise ValueError(f"Transaction with id {transaction_id} does not exist")    
            return result.rowcount > 0
        