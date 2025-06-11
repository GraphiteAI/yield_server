from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from pydantic.types import UUID4
from datetime import datetime
from yield_server.utils.time import get_timestamp

from yield_server.backend.database.db import async_session

from yield_server.backend.database.models import LeaderViolation, Leader, LeaderStatus
from yield_server.backend.schema.leaderviolations_schema import LeaderViolationCreate, LeaderViolationOut
from yield_server.backend.schema.leader_schema import LeaderViolated
from yield_server.backend.crud.leader_crud import LeaderCRUD

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException

class LeaderViolationCRUD:
    '''
    CRUD operations for LeaderViolation

    CREATE: Allows creating a new leader violation
    GET: Allows retrieving a leader violation by id
    NO PUT/DELETE: Leader violations are immutable and should not be updated or deleted
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session
        self.leader_crud = LeaderCRUD(session=session)

    async def create_violation(self, violation: LeaderViolationCreate, session=None) -> LeaderViolationOut:
        '''
        Create a new leader violation
        '''
        current_ts = get_timestamp()

        own_session = False
        if session is None:
            own_session = True
            session_manager = self.session.begin()
            session = await session_manager.__aenter__()

        try:
            # check if leader exists
            leader = await session.get(Leader, violation.leader_id)
            if not leader:
                raise ValueError(f"Leader with id {violation.leader_id} does not exist")
            
            # check if leader is active
            if leader.status != LeaderStatus.ACTIVE:
                raise ValueError(f"Leader with id {violation.leader_id} is not active | Unable to create violation")
            
            new_violation = LeaderViolation(
                **violation.model_dump(),
                updated_at=current_ts, 
            )

            try:
                session.add(new_violation) 
                await self.leader_crud.set_leader_violated(LeaderViolated(id=violation.leader_id), session=session)
                await session.flush()
                await session.refresh(new_violation)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Leader is already violated: {str(e)}"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to set leader as violated: {str(e)}"
                )
            
            return LeaderViolationOut.model_validate(new_violation)
        finally:
            if own_session:
                await session_manager.__aexit__(None, None, None)

    async def get_violation(self, leader_id: UUID4) -> LeaderViolationOut:
        '''
        Get a leader violation by leader_id
        '''
        async with self.session.begin() as session:
            violation = await session.get(LeaderViolation, leader_id)
            if not violation:
                raise ValueError(f"Violation with id {leader_id} does not exist")
            return LeaderViolationOut.model_validate(violation)
        