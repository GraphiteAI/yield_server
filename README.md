# Validator decentralized backend server
If you would like to run a Validator on Subnet 43 with your own site and backend, this open-sourced code provides you with most of the code needed to get your backend set up!
The backend automates proxy wallet creation, monitors validator performance, and ensures rebalancing actions are executed with precision. Designed for scalability and reliability, this service orchestrates the secure, transparent, and efficient operation of validators within a dynamic ecosystem. 


This guide explains how to set up and run the validator system, including proxy generation, configuration, and database schema. The base template is opensourced and can be found at the repository **yield_server**.

For database setup, refer to the [PostgreSQL 17 Documentation](https://www.postgresql.org/files/documentation/pdf/17/postgresql-17-A4.pdf).

For supabase database, refer to [Supabase Documentation](https://supabase.com/docs).

For logging, refer to [Logging Documentation](https://docs.python.org/3/library/logging.html).

Note that we will need to use both PostgreSQL and Supabase for the setup so do spend some time reading the above documents to get a gist of how to set them up.

---

## 🧠 Proxy Generation

Proxies are generated per activated leader (UUID-based), using `proxy_assignment_service.py`.  
Wallet names are derived from the shortuuid hash of the UUID.

---

## ⚙️ Environment Configuration (`.env.py`)

Ensure the following **12 environment variables** are set:

### Supabase
```env
SUPABASE_SERVICE_ROLE_KEY=<<from supabase>>
SUPABASE_URL=<<from supabase>>
SUPABASE_JWT_SECRET=<<from supabase>>
SUPABASE_JWT_ISSUER=<<from supabase>>
```

### Admin & Database
```env
ASYNC_DB_URL=<<PostgreSQL URL>>
ADMIN_KEY=<<Supabase admin user key>>
ADMIN_HASHKEY=<<128-byte unique key>>
```

### Wallet Paths
```env
LIVE_WALLET_PATH=<<wallets storage path>>
LIVE_MNEMONIC_FILEPATH=<<mnemonic archive path>>
LIVE_ARCHIVE_WALLET_PATH=<<archived wallets path>>
LIVE_ARCHIVE_MNEMONIC_FILEPATH=<<archived mnemonic text file path>>
LIVE_WALLET_PASSWORD=<<64-byte password>>
```

---

## 🧾 Constants

Refer to `yield_server/config/constant.py` for constants setup.

### Wallet & Email
```python
DEFAULT_EMAIL_TEMPLATE = "<<your superbase template>>"
SS58_ADDRESS_LENGTH = 48
```

### Balances
```python
MINIMUM_STARTING_BALANCE = 500_000_000       # 5 TAO
MAXIMUM_STARTING_BALANCE = 15_000_000_000    # 15 TAO
```

### Timing Intervals (in seconds)
```python
PROXY_GENERATION_INTERVAL = 60               # 1 min
LEADER_ACTIVATION_INTERVAL = 3600            # 1 hour
SUBNET_HOTKEY_SYNC_INTERVAL = 3600
SNAPSHOT_INTERVAL = 86400                    # 1 day
METRIC_UPDATE_INTERVAL = 3600
```

### Metrics
```python
VTRUST_THRESHOLD = 0.01
LOOKBACK_DAYS = 30
TOP_LEADERBOARD_SIZE = 10
SHARPE_RATIO_LOOKBACK_DAYS = 30
OTF_DAILY_APY = 13.89                        # Divide by 365 for daily %
MINIMUM_SAMPLES_FOR_SHARPE_RATIO = 30
DEFAULT_SHARPE_RATIO = 0
```

### Yield Signer Keys
```python
YIELD_SIGNER_HOTKEY = "<<base58 address>>"
YIELD_SIGNER_COLDKEY = "<<base58 address>>"
```

### Ports
```python
YIELD_VALIDATOR_REBALANCING_PORT = 6500
YIELD_VALIDATOR_PERFORMANCE_PORT = 6501
```

### Service Address
```python
YIELD_VALIDATOR_SERVICE_ADDRESS = "<<API endpoint>>"
```

### Rebalancing Params
```python
YIELD_REBALANCE_SLIPPAGE_TOLERANCE = 0.001
MAXIMUM_REBALANCE_RETRIES = 3
REBALANCE_COOLDOWN_PERIOD = 3600
DEFAULT_REBALANCE_MODE = "batch_all"
DEFAULT_REBALANCE_FEE = 0.001
DEFAULT_FEE_DESTINATION = "5HjMs5JDrLH3Hknmfm1gDq7nFYAv6M7t9v3EWMctSRXJS9HC"
DEFAULT_SLIPPAGE_TOLERANCE = 0.005
DEFAULT_MINIMUM_PROXY_BALANCE = 10_000_000   # 0.01 TAO
```

---

## 🗃️ Database Setup

Refer to `yield_server/backend/database/models.py` to define your database schema.

Initialize with:
```python
Base.metadata.create_all()
```

---

## Logging

Refer to `yield_server/config/logging.py` for logging setup.
This is the default logging configuraton offered by the bittensor subnet template. 
The levels are defined with a scoping logic. In other words, if you enable “info” level logging, then higher levels are also included (“warning”, “error”...).

✅ That’s it! Your validator and proxy setup should now be good to go.

