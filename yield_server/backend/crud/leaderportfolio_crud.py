from yield_server.backend.database.models import LeaderProxy, Leader, LeaderStatus, LeaderPortfolio
from yield_server.backend.schema.leaderportfolio_schema import (
    LeaderPortfolioUpsert,
    LeaderPortfolioOut,
    LeaderPortfolioGet,
)
from yield_server.backend.schema.leader_schema import LeaderGet

from yield_server.utils.time import get_timestamp
from yield_server.backend.database.db import async_session

from sqlalchemy import update, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

class LeaderPortfolioCRUD:
    '''
    CRUD operations for LeaderProxy.
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session

    async def upsert_portfolio(self, upsert_portfolio: LeaderPortfolioUpsert) -> LeaderPortfolioOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            # check if the leader exists
            leader = await session.get(Leader, upsert_portfolio.leader_id)
            if not leader:
                raise ValueError("Leader not found")
            
            # check if the leader is active
            if leader.status != LeaderStatus.ACTIVE:
                raise ValueError("Leader is not active")

            # check if there's already a portfolio bound to the leader
            portfolio = await session.get(LeaderPortfolio, upsert_portfolio.leader_id)
            if not portfolio:
                print("Creating new portfolio: ", upsert_portfolio.model_dump(exclude_unset=True))
                portfolio = LeaderPortfolio(
                    **upsert_portfolio.model_dump(exclude_unset=True),
                    created_at=current_ts,
                    updated_at=current_ts
                )
                session.add(portfolio)
            else:
                portfolio.portfolio_distribution = upsert_portfolio.portfolio_distribution
                portfolio.portfolio_hash = upsert_portfolio.portfolio_hash
                portfolio.updated_at = current_ts
            
            await session.flush()
            await session.refresh(portfolio)
            return LeaderPortfolioOut.model_validate(portfolio)
        
    async def get_leader_portfolio(self, get_leader_portfolio: LeaderPortfolioGet) -> LeaderPortfolioOut:
        async with self.session.begin() as session:
            portfolio = await session.get(LeaderPortfolio, get_leader_portfolio.leader_id)
            if not portfolio:
                raise ValueError("Leader portfolio not found")
            return LeaderPortfolioOut.model_validate(portfolio)
