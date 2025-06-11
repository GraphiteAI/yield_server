'''
We abstract the handling of the JWT tokens and the refresh tokens to Supabase to leverage their robust auth system.

The following models are used store the state of the leader and copytrader in the database.

These models are periodically synced with supabase as a remote backup copy to de-risk the loss of local state.
'''

from typing import List, Optional, Annotated, Union
from names_generator import generate_name
from enum import Enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import String, Enum as SQLAlchemyEnum, BigInteger, Boolean, Column, DECIMAL, Float, Integer, CheckConstraint, ForeignKey, event, select, and_, Index, TIMESTAMP, UUID, ForeignKeyConstraint, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, JSONB, INET
from sqlalchemy.schema import Sequence
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session, backref
from sqlalchemy.orm import with_polymorphic

from yield_server.config.constants import SS58_ADDRESS_LENGTH
from yield_server.backend.database.db import Base
from yield_server.utils.time import get_timestamp

class UserRole(Enum):
    GENERIC = "GENERIC"
    LEADER = "LEADER"
    COPYTRADER = "COPYTRADER"

class LeaderStatus(Enum):
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'
    VIOLATED = 'VIOLATED'
    DEREGISTERED = 'DEREGISTERED'

class MinerStatus(Enum):
    REGISTERED = 'REGISTERED'
    DEREGISTERED = 'DEREGISTERED'

class HotkeyBoundStatus(Enum):
    BOUND = 'BOUND'
    UNBOUND = 'UNBOUND'

class ProxyBoundStatus(Enum):
    BOUND = 'BOUND'
    UNBOUND = 'UNBOUND'

class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    address: Mapped[str] = mapped_column(String(SS58_ADDRESS_LENGTH), unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLAlchemyEnum(UserRole), nullable=False, default=UserRole.GENERIC)

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    
    # Add discriminator column for polymorphic inheritance
    __mapper_args__ = {
        "polymorphic_on": "role",
        "polymorphic_identity": UserRole.GENERIC,
    }

    @classmethod
    def get_with_all_columns(cls, session, id):
        # Use with_polymorphic to include all subclass attributes
        poly = with_polymorphic(cls, '*')
        return session.query(poly).filter(poly.id == id).first()

class Leader(User):
    __tablename__ = "leaders"
    
    # Create a primary key that references the parent table
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    # Additional leader-specific columns
    hotkey: Mapped[str] = mapped_column(String(SS58_ADDRESS_LENGTH), ForeignKey("subnet_miner_hotkeys.hotkey", ondelete="SET NULL"), nullable=True, default=None)
    status: Mapped[LeaderStatus] = mapped_column(SQLAlchemyEnum(LeaderStatus), nullable=False, default=LeaderStatus.INACTIVE)

    alias: Mapped[str] = mapped_column(String, nullable=False, default=generate_name, unique=True)
    account_starting_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    start_block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    last_checked_block_number: Mapped[int] = mapped_column(Integer, nullable=True)

    # Relationships
    subnet_miner_hotkey: Mapped["SubnetMinerHotkey"] = relationship("SubnetMinerHotkey", back_populates="leader")
    leader_proxy: Mapped["LeaderProxy"] = relationship("LeaderProxy", back_populates="leader", uselist=False)
    copytraders: Mapped[List["CopyTrader"]] = relationship("CopyTrader", back_populates="leader", foreign_keys="[CopyTrader.leader_id]")
    leader_portfolio: Mapped["LeaderPortfolio"] = relationship("LeaderPortfolio", back_populates="leader", uselist=False)
    leader_metrics: Mapped["LeaderMetrics"] = relationship("LeaderMetrics", back_populates="leader", uselist=False)
    leader_violation: Mapped["LeaderViolation"] = relationship("LeaderViolation", back_populates="leader", uselist=False)

    # Set polymorphic identity for this subclass
    __mapper_args__ = {
        "polymorphic_identity": UserRole.LEADER
    }

class LeaderMetrics(Base):
    __tablename__ = "leader_metrics"

    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="CASCADE"), primary_key=True)
    # metrics: Mapped[dict] = mapped_column(JSONB, nullable=False) # TODO: determine the exact fields to store and set them as columns instead of using an arbitrary JSONB column

    total_assets: Mapped[int] = mapped_column(BigInteger, comment="This represents the total value of the assets in tao") # this represents the total value of the assets in tao
    pnl: Mapped[int] = mapped_column(BigInteger, comment="The total pnl of the leader's portfolio in rao w.r.t. the initial portfolio value")
    pnl_percent: Mapped[float] = mapped_column(Float, comment="The total pnl of the leader's portfolio in % w.r.t. the initial portfolio value")
    sharpe_ratio: Mapped[float] = mapped_column(Float, comment="Sharpe ratio computed based on daily returns")
    drawdown: Mapped[float] = mapped_column(Float, comment="The maximum % pnl drawdown of the leader's portfolio since the start of the leader's account")
    volume: Mapped[int] = mapped_column(BigInteger, comment="The total volume of the leader's transactions in rao (based on tao value of origin)")
    num_copy_traders: Mapped[int] = mapped_column(Integer, comment="The number of copytraders following the leader")
    notional_value_of_copy_traders: Mapped[int] = mapped_column(BigInteger, comment="The total notional value of the copytraders' portfolios")
    rank: Mapped[int] = mapped_column(Integer, comment="The rank of the leader based on the total assets")
    # status: Mapped[str] = mapped_column(String) # NOTE: remove this column to avoid duplicating data between leader and leader_metrics_snapshots

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

    # Add relationship with Leader
    leader: Mapped["Leader"] = relationship("Leader", back_populates="leader_metrics", uselist=False)

class CopyTrader(User):
    __tablename__ = "copytraders"
    
    # Create a primary key that references the parent table
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    # Additional copytrader-specific columns
    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="SET NULL"), nullable=True)
    leader_proxy_id: Mapped[str] = mapped_column(String(SS58_ADDRESS_LENGTH), ForeignKey("leader_proxies.proxy_id", ondelete="SET NULL"), nullable=True)
    account_starting_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="Starting balance set when the copytrader first begins copytrading") # NOTE: this is the balance of the copytrader's account at the time of following a new leader    
    last_proxy_block: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="block number representing the last time the copytrader's proxy state was updated")
    portfolio_hash: Mapped[str] = mapped_column(String, nullable=True, comment="Version tracking hash of the copytrader's portfolio w.r.t. to the leader's portfolio") # NOTE: this is used to track the version of the portfolio that the copytrader is following
    next_rebalance_block: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="block number representing the last time an attempt to rebalance the copytrader's portfolio was made")
    rebalance_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="number of consecutive attempts to rebalance the copytrader's portfolio without success") # NOTE: once this value exceeds the MAXIMUM_REBALANCE_RETRIES, the copytrader will be set to cooldown with this value being reset upon the next attempt after the cooldown
    
    # Relationship with Leader
    leader: Mapped["Leader"] = relationship("Leader", back_populates="copytraders", foreign_keys=[leader_id])
    leader_proxy: Mapped["LeaderProxy"] = relationship("LeaderProxy", back_populates="copytraders", foreign_keys=[leader_proxy_id])
    # Add relationship with CopyTraderMetrics
    metrics: Mapped["CopyTraderMetrics"] = relationship("CopyTraderMetrics", back_populates="copytrader", uselist=False)

    # Set polymorphic identity for this subclass
    __mapper_args__ = {
        "polymorphic_identity": UserRole.COPYTRADER
    }

class CopyTraderMetrics(Base):
    __tablename__ = "copytrader_metrics"

    copytrader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("copytraders.id", ondelete="CASCADE"), primary_key=True)
    # metrics: Mapped[dict] = mapped_column(JSONB, nullable=False) # TODO: determine the exact fields to store and set them as columns instead of using an arbitrary JSONB column
    
    pnl: Mapped[int] = mapped_column(BigInteger, comment="The total pnl of the copytrader's portfolio in rao w.r.t. the initial portfolio value")
    pnl_percent: Mapped[float] = mapped_column(Float, comment="The total pnl of the copytrader's portfolio in % w.r.t. the initial portfolio value")
    volume: Mapped[int] = mapped_column(BigInteger, comment="The total volume of the copytrader's transactions in rao (based on tao value of origin)")
    total_assets: Mapped[int] = mapped_column(BigInteger, comment="The total asset value of the copytrader's portfolio in rao")
    # status: Mapped[str] = mapped_column(String)

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

    # Add relationship with CopyTrader
    copytrader: Mapped["CopyTrader"] = relationship("CopyTrader", back_populates="metrics")

# NOTE: consider including column for leader_id for more efficient querying
class SubnetMinerHotkey(Base):
    __tablename__ = "subnet_miner_hotkeys"
    
    hotkey: Mapped[str] = mapped_column(String(SS58_ADDRESS_LENGTH), nullable=False, primary_key=True)
    status: Mapped[MinerStatus] = mapped_column(SQLAlchemyEnum(MinerStatus), nullable=False, default=MinerStatus.REGISTERED)
    bound_status: Mapped[HotkeyBoundStatus] = mapped_column(SQLAlchemyEnum(HotkeyBoundStatus), nullable=False, default=HotkeyBoundStatus.UNBOUND)
    
    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    
    # One-to-one relationship with Leader
    leader: Mapped["Leader"] = relationship("Leader", back_populates="subnet_miner_hotkey", uselist=False)

class LeaderProxy(Base):
    __tablename__ = "leader_proxies"
    
    proxy_id: Mapped[str] = mapped_column(String(SS58_ADDRESS_LENGTH), primary_key=True, comment="The proxy address (ss58) of the leader")
    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="SET NULL"), unique=True, nullable=True)
    proxy_bound_status: Mapped[ProxyBoundStatus] = mapped_column(SQLAlchemyEnum(ProxyBoundStatus), nullable=False, default=ProxyBoundStatus.UNBOUND)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    
    # One-to-one relationship with Leader
    leader: Mapped["Leader"] = relationship("Leader", back_populates="leader_proxy", foreign_keys=[leader_id])
    
    # One-to-many relationship with CopyTraders
    copytraders: Mapped[List["CopyTrader"]] = relationship("CopyTrader", back_populates="leader_proxy", foreign_keys="[CopyTrader.leader_proxy_id]")

class LeaderMetricsSnapshot(Base):
    __tablename__ = "leader_metrics_snapshots"

    snapshot_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid.uuid4())
    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="CASCADE"))
    
    total_assets: Mapped[int] = mapped_column(BigInteger, comment="The total asset value of the leader's portfolio in rao")
    pnl: Mapped[int] = mapped_column(BigInteger, comment="The total pnl of the leader's portfolio in rao w.r.t. the initial portfolio value")
    pnl_percent: Mapped[float] = mapped_column(Float, comment="The total pnl of the leader's portfolio in % w.r.t. the initial portfolio value")
    sharpe_ratio: Mapped[float] = mapped_column(Float, comment="Sharpe ratio computed based on daily returns")
    drawdown: Mapped[float] = mapped_column(Float, comment="The maximum % pnl drawdown of the leader's portfolio since the start of the leader's account")
    volume: Mapped[int] = mapped_column(BigInteger, comment="The total volume of the leader's transactions in rao (based on tao value of origin)")
    num_copy_traders: Mapped[int] = mapped_column(Integer, comment="The number of copytraders following the leader")
    notional_value_of_copy_traders: Mapped[int] = mapped_column(BigInteger, comment="The total notional value of the copytraders' portfolios")
    rank: Mapped[int] = mapped_column(Integer, comment="The rank of the leader based on the total assets")
    snapshot_date: Mapped[datetime] = mapped_column(Date)

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

    # Create indexes and constraints
    __table_args__ = (
        Index('idx_leader_metrics_date', 'leader_id', 'snapshot_date'),
        UniqueConstraint('leader_id', 'snapshot_date', name='uq_leader_snapshot_date'),
    )

# NOTE: this table stores a dict with key value representing the % of the leader's portfolio in each subnet's alpha token
# While the portfolio distribution is subject to change based on the value the underlying assets, the records are only updated upon change in portfolio state via leader transactions
# This will avoid rebalancing operations when the leader's approach remains the same
class LeaderPortfolio(Base):
    __tablename__ = "leader_portfolio"

    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="CASCADE"), primary_key=True)
    portfolio_distribution: Mapped[dict] = mapped_column(JSONB, comment="A dict with key value representing the % of the leader's portfolio in each subnet's alpha token")
    portfolio_hash: Mapped[str] = mapped_column(String, nullable=True, comment="A hash of the portfolio distribution to track changes in the portfolio")

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

    # One-to-one relationship with Leader
    leader: Mapped["Leader"] = relationship("Leader", back_populates="leader_portfolio", foreign_keys=[leader_id])

class CopyTraderMetricsSnapshot(Base):
    __tablename__ = "copytrader_metrics_snapshots"

    snapshot_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    copytrader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("copytraders.id", ondelete="CASCADE"))

    pnl: Mapped[int] = mapped_column(BigInteger, comment="The total pnl of the copytrader's portfolio in rao w.r.t. the initial portfolio value")
    pnl_percent: Mapped[float] = mapped_column(Float, comment="The total pnl of the copytrader's portfolio in % w.r.t. the initial portfolio value")
    volume: Mapped[int] = mapped_column(BigInteger, comment="The total volume of the copytrader's transactions in rao (based on tao value of origin)")
    total_assets: Mapped[int] = mapped_column(BigInteger, comment="The total asset value of the copytrader's portfolio in rao")
    snapshot_date: Mapped[datetime] = mapped_column(Date)

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

    # Create index and constraints
    __table_args__ = (
        Index('idx_copytrader_metrics_date', 'copytrader_id', 'snapshot_date'),
        UniqueConstraint('copytrader_id', 'snapshot_date', name='uq_copytrader_snapshot_date'),
    )

# NOTE: this table stores the violation to be displayed on the UI for the leader's acknowledgement
class LeaderViolation(Base):
    __tablename__ = "leader_violations"

    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="CASCADE"), primary_key=True)
    violation_message: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

    # Add relationship with Leader
    leader: Mapped["Leader"] = relationship("Leader", back_populates="leader_violation", foreign_keys=[leader_id])

# NOTE: this table stores all transactions that occurred on leader's coldkey and/or hotkey
class LeaderTransactions(Base):
    __tablename__ = "leader_transactions"

    transaction_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="CASCADE"))
    call_function: Mapped[str] = mapped_column(String, nullable=False)
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extrinsic_hash: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

# NOTE: this table stores all the rebalance transactions that have been made for the copytraders
class CopyTraderRebalanceTransaction(Base):
    __tablename__ = "copytrader_rebalance_transactions"

    transaction_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    copytrader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("copytraders.id", ondelete="CASCADE"))
    leader_proxy_id: Mapped[str] = mapped_column(String(SS58_ADDRESS_LENGTH), ForeignKey("leader_proxies.proxy_id", ondelete="CASCADE"))
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extrinsic_hash: Mapped[str] = mapped_column(String, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger) # NOTE: this is the volume of the rebalance transaction

    created_at: Mapped[int] = mapped_column(BigInteger, default=get_timestamp)

    __table_args__ = (
        Index('idx_copytrader_rebalance_transactions_copytrader_id', 'copytrader_id'),
        Index('idx_copytrader_rebalance_transactions_leader_proxy_id', 'leader_proxy_id'),
    )

# NOTE: each leader is given 300 blocks to perform transactions before a 6900 block cooldown period
class LeaderRestrictions(Base):
    __tablename__ = "leader_restrictions"

    leader_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("leaders.id", ondelete="CASCADE"), primary_key=True)
    first_non_violated_trading_block_number: Mapped[int] = mapped_column(Integer, nullable=False) # triggered when a bounded function is called
    first_no_trade_block_number: Mapped[int] = mapped_column(Integer, nullable=False) # first_non_violated_trading_block_number + 300, this is the block copytraders starts rebalancing
    last_no_trade_block_number: Mapped[int] = mapped_column(Integer, nullable=False) # last_non_violated_trading_block_number + 300 + 6900

