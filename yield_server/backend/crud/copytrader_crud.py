from yield_server.backend.database.models import CopyTrader, UserRole, User, LeaderProxy, Leader, LeaderStatus, LeaderPortfolio, CopyTraderRebalanceTransaction
from yield_server.backend.schema.copytrader_schema import (
    CopyTraderCreate, 
    CopyTraderOut, 
    CopyTraderDemote, 
    CopyTraderSetProxy,
    CopyTraderRemoveProxy,
    CopyTraderProxyBindOut,
    CopyTraderChooseLeader,
    CopyTraderGet,
    CopyTraderUpdatePortfolioHash,
    CopyTraderSetRebalanceSuccess,
    CopyTraderSetRebalanceFailure,
    CopyTraderRebalanceOut,
    SetCopyTraderForRebalancing
)
from yield_server.backend.schema.user_schema import UserOutPrivate
from yield_server.core.subtensor_calls import get_wallet_stakes, get_wallet_stakes_in_rao, get_subnets_info
from yield_server.backend.database.db import async_session
from yield_server.core.proxy_verification import ProxyAddVerification, ProxyRemoveVerification, verify_add_proxy, verify_remove_proxies
from yield_server.utils.time import get_timestamp
from yield_server.utils.crud_utils import orm_to_dict
from yield_server.config.constants import MAXIMUM_REBALANCE_RETRIES, REBALANCE_COOLDOWN_PERIOD, DEFAULT_MINIMUM_PROXY_BALANCE

from pydantic.types import UUID4
from sqlalchemy import delete, select, insert
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

class CopyTraderCRUD:
    '''
    CRUD operations for CopyTraders.
    '''
    def __init__(self, session: AsyncSession = async_session):
        self.session = session

    async def create_new_copytrader(self, copytrader: CopyTraderCreate) -> CopyTraderOut:
        current_ts = get_timestamp()

        async with self.session.begin() as session:
            # get the user record that represents the copytrader
            existing_user = await session.get(User, copytrader.id)
            if not existing_user:
                raise ValueError("User not found")
            if existing_user.role != UserRole.GENERIC:
                raise ValueError("User is not a generic user | Please revert back to a generic user before trying to create a copytrader")
            # create a new copytrader record
            existing_user.role = UserRole.COPYTRADER
            existing_user_dict = orm_to_dict(existing_user, User.__table__)
            existing_user_dict.pop("updated_at")
            # NOTE: on creation of a copytrader, the leader_id and leader_proxy_id (proxy_account) are not set
            new_copytrader = CopyTrader(
                **existing_user_dict,
                account_starting_balance=copytrader.account_starting_balance,
                last_proxy_block = copytrader.last_proxy_block,
                next_rebalance_block=copytrader.next_rebalance_block,
                rebalance_attempts=0,
                updated_at=current_ts,
            )
            
            await session.execute(
                insert(CopyTrader).values(orm_to_dict(new_copytrader, CopyTrader.__table__)), 
                execution_options={"postgres_only": True}
                )
            
            await session.flush()
            session.expunge_all()
            new_copytrader = await session.get(CopyTrader, new_copytrader.id)
            
            if not new_copytrader:
                raise ValueError("Failed to create copytrader record")
            
            copytrader_attributes = orm_to_dict(new_copytrader, CopyTrader.__table__)
            user_attributes = orm_to_dict(new_copytrader, User.__table__)
            copytrader_attributes.update(user_attributes)
            copytrader_attributes["chosen_leader_id"] = None
            copytrader_attributes["chosen_leader_alias"] = None
            copytrader_attributes["target_proxy"] = None
            
            return CopyTraderOut.model_validate(copytrader_attributes)
    
    async def get_proxy_data(self, choose_leader: CopyTraderChooseLeader) -> CopyTraderProxyBindOut:
        async with self.session.begin() as session:
            copytrader_record: Optional[CopyTrader] = await session.get(CopyTrader, choose_leader.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            # check if the chosen leader exists
            chosen_leader: Optional[Leader] = await session.get(Leader, choose_leader.leader_id)
            if not chosen_leader:
                raise ValueError("Leader not found")
            if chosen_leader.status != LeaderStatus.ACTIVE:
                raise ValueError("Leader is not active")
            # check if the chosen leader proxy exists
            leader_proxy_result = await session.execute(select(LeaderProxy).filter(LeaderProxy.leader_id == chosen_leader.id))
            chosen_leader_proxy: Optional[LeaderProxy] = leader_proxy_result.scalars().one_or_none()
            if not chosen_leader_proxy:
                raise ValueError("Leader proxy not found | Generator service has yet to set a proxy for this leader")
            if chosen_leader_proxy.balance < DEFAULT_MINIMUM_PROXY_BALANCE:
                raise ValueError("Leader proxy balance is less than the minimum proxy balance | Try following a different leader")

            copytrader_id = copytrader_record.id
            role = copytrader_record.role
            leader_id = chosen_leader.id
            alias = chosen_leader.alias
            leader_proxy_id = chosen_leader_proxy.proxy_id
            data_dict = {
                "id": copytrader_id,
                "role": role,
                "chosen_leader_id": leader_id,
                "chosen_leader_alias": alias,
                "target_proxy": leader_proxy_id
            }
            return CopyTraderProxyBindOut.model_validate(data_dict)

    async def set_proxy(self, set_proxy: CopyTraderSetProxy) -> CopyTraderOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            copytrader_record: Optional[CopyTrader] = await session.get(CopyTrader, set_proxy.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            # check that the update is more recent than the last block
            if set_proxy.block_number <= copytrader_record.last_proxy_block:
                raise ValueError("Update is not more recent than the last update to the CopyTrader's proxy")
            is_valid_proxy = await verify_add_proxy(ProxyAddVerification(**set_proxy.model_dump()))
            if not is_valid_proxy:
                raise ValueError("Invalid proxy extrinsic")
            # check if the leader proxy exists
            leader_proxy_record: Optional[LeaderProxy] = await session.get(LeaderProxy, set_proxy.target_proxy)
            if not leader_proxy_record:
                raise ValueError("Leader proxy not found")
            if not leader_proxy_record.leader_id:
                raise ValueError("Leader proxy not associated with a leader | Likely due to leader being demoted")
            
            # get the current account value of the copytrader and set it as the account starting balance
            if copytrader_record.account_starting_balance is None or copytrader_record.account_starting_balance == 0:
                subnet_info = await get_subnets_info()
                wallet_stakes = await get_wallet_stakes(copytrader_record.address, include_free=False) # Don't include the free balance since we only want to track the staked portfolio
                copytrader_record.account_starting_balance = await get_wallet_stakes_in_rao(subnet_info, wallet_stakes)

            copytrader_record.leader_id = leader_proxy_record.leader_id
            copytrader_record.leader_proxy_id = set_proxy.target_proxy
            copytrader_record.updated_at = current_ts
            copytrader_record.last_proxy_block = set_proxy.block_number
            
            await session.flush()
            await session.refresh(copytrader_record)

            target_proxy = copytrader_record.leader_proxy_id
            chosen_leader_id = copytrader_record.leader_id
            chosen_leader: Optional[Leader] = await session.get(Leader, chosen_leader_id)
            if not chosen_leader:
                # NOTE: This will happen in the unlikely event of a race condition where the leader demotes themselves and the associated leader of the proxy is removed
                raise ValueError("Leader not found | Proxied leader might have been removed")
            chosen_leader_alias = chosen_leader.alias
            data_dict = {
                "id": copytrader_record.id,
                "role": copytrader_record.role,
                "chosen_leader_id": chosen_leader_id,
                "chosen_leader_alias": chosen_leader_alias,
                "target_proxy": target_proxy,
                "address": copytrader_record.address,
                "created_at": copytrader_record.created_at,
                "updated_at": copytrader_record.updated_at
            }
            return CopyTraderOut.model_validate(data_dict)

    async def remove_proxy(self, remove_proxy: CopyTraderRemoveProxy) -> CopyTraderOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            copytrader_record = await session.get(CopyTrader, remove_proxy.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            # check that the update is more recent than the last block
            if remove_proxy.block_number <= copytrader_record.last_proxy_block:
                raise ValueError("Update is not more recent than the last update to the CopyTrader's proxy")
            is_valid_proxy = await verify_remove_proxies(ProxyRemoveVerification.model_validate(remove_proxy.model_dump()))
            if not is_valid_proxy:
                raise ValueError("Invalid proxy extrinsic")
            copytrader_record.leader_proxy_id = None
            copytrader_record.leader_id = None
            copytrader_record.last_proxy_block = remove_proxy.block_number
            copytrader_record.updated_at = current_ts
            await session.flush()
            await session.refresh(copytrader_record)
            target_proxy = copytrader_record.leader_proxy_id
            chosen_leader_id = copytrader_record.leader_id
            if chosen_leader_id or target_proxy:
                raise ValueError(f"Failed to remove proxy | Leader {chosen_leader_id} still found with proxy {target_proxy}")
            data_dict = {
                "id": copytrader_record.id,
                "role": copytrader_record.role,
                "chosen_leader_id": copytrader_record.leader_id,
                "chosen_leader_alias": None,
                "target_proxy": copytrader_record.leader_proxy_id,
                "address": copytrader_record.address,
                "created_at": copytrader_record.created_at,
                "updated_at": copytrader_record.updated_at
            }
            return CopyTraderOut.model_validate(data_dict)
        
    async def get_copytrader(self, copytrader_id: CopyTraderGet) -> CopyTraderOut:
        async with self.session.begin() as session:
            copytrader_record = await session.get(CopyTrader, copytrader_id.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            leader_record = await session.get(Leader, copytrader_record.leader_id)
            if leader_record:
                leader_alias = leader_record.alias
            else:
                leader_alias = None
            data_dict = {
                "id": copytrader_record.id,
                "role": copytrader_record.role,
                "chosen_leader_id": copytrader_record.leader_id,
                "chosen_leader_alias": leader_alias,
                "target_proxy": copytrader_record.leader_proxy_id,
                "address": copytrader_record.address,
                "created_at": copytrader_record.created_at,
                "updated_at": copytrader_record.updated_at
            }
            return CopyTraderOut.model_validate(data_dict)
        
    async def demote_copytrader(self, copytrader: CopyTraderDemote) -> UserOutPrivate:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            existing_copytrader = await session.get(CopyTrader, copytrader.id)
            if not existing_copytrader:
                raise ValueError("CopyTrader not found")
            if existing_copytrader.role != UserRole.COPYTRADER:
                raise ValueError("CopyTrader is not a copytrader")
            existing_copytrader.role = UserRole.GENERIC
            existing_copytrader.updated_at = current_ts
            await session.flush()
            await session.execute(
                delete(CopyTrader).where(CopyTrader.id == copytrader.id)
            )
            return UserOutPrivate.model_validate(existing_copytrader)

    # NOTE: consider adding a check to ensure that the portfolio hash matches the leader's portfolio hash in the leader_portfolio_distributions table
    # This Update transaction should only be invoked by our internal rebalancing service that manages the copytraders
    async def update_portfolio_hash(self, update_portfolio_hash: CopyTraderUpdatePortfolioHash) -> CopyTraderOut:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            copytrader_record = await session.get(CopyTrader, update_portfolio_hash.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            copytrader_record.portfolio_hash = update_portfolio_hash.portfolio_hash
            copytrader_record.updated_at = current_ts
            await session.flush()
            await session.refresh(copytrader_record)
            return CopyTraderOut.model_validate(copytrader_record)
        
    async def get_following_copytrader_addresses(self) -> List[str]:
        async with self.session.begin() as session:
            copytrader_addresses = await session.execute(
                select(CopyTrader.address)
                .where(CopyTrader.leader_id.is_not(None))
                .where(CopyTrader.leader_proxy_id.is_not(None))
            )
            return copytrader_addresses.scalars().all()
        
    async def get_rebalance_copytrader_from_address(self, copytrader_address: str) -> CopyTraderRebalanceOut:
        async with self.session.begin() as session:
            copytrader_result = await session.execute(
                select(CopyTrader)
                .where(CopyTrader.address == copytrader_address)
            )
            copytrader_record = copytrader_result.scalars().one_or_none()
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            return CopyTraderRebalanceOut(
                id=copytrader_record.id,
                role=copytrader_record.role,
                address=copytrader_record.address,
                chosen_leader_id=copytrader_record.leader_id,
                target_proxy=copytrader_record.leader_proxy_id,
                next_rebalance_block=copytrader_record.next_rebalance_block
            )
        
    async def get_copytrader_id_from_address(self, copytrader_address: str) -> UUID4:
        async with self.session.begin() as session:
            copytrader_id = await session.execute(
                select(CopyTrader.id)
                .where(CopyTrader.address == copytrader_address)
            )
            return copytrader_id.scalars().one_or_none()
        
    async def get_rebalance_copytraders(self, current_block: int) -> List[CopyTraderRebalanceOut]:
        async with self.session.begin() as session:
            copytraders_and_portfolios = await session.execute(
                select(CopyTrader)
                .where(CopyTrader.leader_id.is_not(None))
                .where(CopyTrader.leader_proxy_id.is_not(None))
                .join(LeaderPortfolio, LeaderPortfolio.leader_id == CopyTrader.leader_id)
                .where(LeaderPortfolio.portfolio_hash.is_distinct_from(CopyTrader.portfolio_hash))
                .where(CopyTrader.next_rebalance_block < current_block)
            )
            results = copytraders_and_portfolios.scalars().all()
            return [CopyTraderRebalanceOut(
                id=copytrader.id,
                role=copytrader.role,
                address=copytrader.address,
                chosen_leader_id=copytrader.leader_id,
                target_proxy=copytrader.leader_proxy_id,
                next_rebalance_block=copytrader.next_rebalance_block
            ) for copytrader in results]

    async def set_copytrader_rebalance_success(self, set_rebalance_success: CopyTraderSetRebalanceSuccess) -> None:
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            copytrader_record = await session.get(CopyTrader, set_rebalance_success.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            copytrader_record.portfolio_hash = set_rebalance_success.portfolio_hash
            copytrader_record.next_rebalance_block = set_rebalance_success.block_number
            copytrader_record.rebalance_attempts = 0
            copytrader_record.updated_at = current_ts
            # create a new copytrader_rebalance_transaction record
            copytrader_rebalance_transaction = CopyTraderRebalanceTransaction(
                copytrader_id=copytrader_record.id,
                leader_proxy_id=set_rebalance_success.leader_proxy_id,
                block_number=set_rebalance_success.block_number,
                extrinsic_hash=set_rebalance_success.extrinsic_hash,
                volume=set_rebalance_success.volume,
                created_at=current_ts
            )
            session.add(copytrader_rebalance_transaction)
            await session.flush()
            await session.refresh(copytrader_record)
            return None

    async def set_copytrader_rebalance_failure(self, set_rebalance_failure: CopyTraderSetRebalanceFailure) -> int:
        '''
        Attempts to increment the rebalance attempts for a copytrader.
        If the copytrader has reached the maximum number of rebalance attempts, it will be placed on cooldown for the duration of the cooldown period.
        
        Returns the number of rebalance attempts for the copytrader or 0 if the copytrader has been placed on cooldown.
        '''
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            copytrader_record = await session.get(CopyTrader, set_rebalance_failure.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            copytrader_record.rebalance_attempts += 1
            copytrader_record.updated_at = current_ts
            await session.flush()
            await session.refresh(copytrader_record)
            if copytrader_record.rebalance_attempts >= MAXIMUM_REBALANCE_RETRIES:
                copytrader_record.next_rebalance_block = set_rebalance_failure.block_number + REBALANCE_COOLDOWN_PERIOD
                copytrader_record.rebalance_attempts = 0
                await session.flush()
                await session.refresh(copytrader_record)
            return copytrader_record.rebalance_attempts
        
    async def set_copytrader_for_rebalancing(self, set_copytrader_for_rebalancing: SetCopyTraderForRebalancing) -> None:
        '''
        To trigger a rebalance, we need to set unset the copytrader's referenced portfolio hash

        To preserve the type of the column data, we will set the portfolio hash to the current portfolio hash of the copytrader's portfolio
        '''
        current_ts = get_timestamp()
        async with self.session.begin() as session:
            copytrader_record: Optional[CopyTrader] = await session.get(CopyTrader, set_copytrader_for_rebalancing.id)
            if not copytrader_record:
                raise ValueError("CopyTrader not found")
            copytrader_record.portfolio_hash = set_copytrader_for_rebalancing.portfolio_hash
            copytrader_record.updated_at = current_ts
            await session.flush()
            await session.refresh(copytrader_record)
            return None
        