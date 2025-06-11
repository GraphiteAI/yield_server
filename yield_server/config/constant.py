DEFAULT_EMAIL_TEMPLATE = "your chosen superbase email template"

SS58_ADDRESS_LENGTH = 48

MINIMUM_STARTING_BALANCE = 500_000_000 # 5 TAO
MAXIMUM_STARTING_BALANCE = 15_000_000_000 # 15 TAO

PROXY_GENERATION_INTERVAL = 60 # 1 minute --> Try 1 minute for testing

LEADER_ACTIVATION_INTERVAL = 3600 # 1 hour

SUBNET_HOTKEY_SYNC_INTERVAL = 3600 # 1 hour

VTRUST_THRESHOLD = 0.01

LOOKBACK_DAYS = 30

TOP_LEADERBOARD_SIZE = 10

SNAPSHOT_INTERVAL = 86400 # 1 day

METRIC_UPDATE_INTERVAL = 3600 # 1 hour

SHARPE_RATIO_LOOKBACK_DAYS = 30

OTF_DAILY_APY = 13.89 # 13.89% daily APY on OTF root (as of 16 May 2025) --> to get the actual daily % returns, we need to divide this value by 365

MINIMUM_SAMPLES_FOR_SHARPE_RATIO = 30 # NOTE: we only compute the sharpe ratio of the portfolio returns when the leader has at least 30 daily returns (Central Limit Theorem)

DEFAULT_SHARPE_RATIO = 0 # default sharpe ratio if the leader has less than 30 daily returns --> To be adjusted based on analysis of sharpe ratio of tao.

YIELD_SIGNER_HOTKEY = "base58_address" # NOTE: this is the hotkey of the yield signer 
YIELD_SIGNER_COLDKEY = "base58_address" # NOTE: this is the coldkey of the yield signer 

YIELD_VALIDATOR_REBALANCING_PORT = 6500

YIELD_VALIDATOR_PERFORMANCE_PORT = 6501

YIELD_VALIDATOR_SERVICE_ADDRESS = "api endpoint for yield validator service"

YIELD_REBALANCE_SLIPPAGE_TOLERANCE = 0.001 # 0.1% slippage tolerance for rebalancing

MAXIMUM_REBALANCE_RETRIES = 3 # maximum number of rebalance retries before we set a cooldown period

REBALANCE_COOLDOWN_PERIOD = 3600 # Number of blocks (12 seconds per block)

DEFAULT_REBALANCE_MODE = "batch_all"

DEFAULT_REBALANCE_FEE = 0.001 # 0.1% of volume of the rebalance transaction

DEFAULT_FEE_DESTINATION = "5HjMs5JDrLH3Hknmfm1gDq7nFYAv6M7t9v3EWMctSRXJS9HC" 

DEFAULT_SLIPPAGE_TOLERANCE = 0.005 # 0.5% slippage tolerance for rebalancing

DEFAULT_MINIMUM_PROXY_BALANCE = 10_000_000 # 0.01 TAO