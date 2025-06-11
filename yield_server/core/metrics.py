'''
This file contains the functions to compute the metrics for the yield server.
'''

from yield_server.config.constants import OTF_DAILY_APY, SHARPE_RATIO_LOOKBACK_DAYS, DEFAULT_SHARPE_RATIO
import numpy as np
def compute_sharpe_ratio(daily_portfolio_returns: list[float]) -> float:
    '''
    Computes the sharpe ratio of the portfolio returns.

    Note that we only compute the sharpe ratio of the portfolio returns when the leader has at least 30 daily returns (Central Limit Theorem).
    '''
    # NOTE: for now we use a naive estimate of risk-free rate as the daily APY of OTF on root
    # A better approach will be developed in the future as the data pipeline is improved
    if len(daily_portfolio_returns) < SHARPE_RATIO_LOOKBACK_DAYS:
        return DEFAULT_SHARPE_RATIO
    
    risk_free_rate = OTF_DAILY_APY / 365
    return (np.array(daily_portfolio_returns) - risk_free_rate).mean() / (np.array(daily_portfolio_returns) - risk_free_rate).std()


def compute_daily_portfolio_returns(historical_pnl_percent: list[float]) -> list[float]:
    '''
    Computes the daily portfolio % returns from the historical pnl % returns.
    '''
    if len(historical_pnl_percent) < 2:
        return []
    daily_portfolio_returns = []
    for i in range(1, len(historical_pnl_percent)):
        daily_portfolio_returns.append(historical_pnl_percent[i] - historical_pnl_percent[i-1])
    return daily_portfolio_returns

def calculate_max_drawdown(portfolio_values: list[int]) -> int:
    '''
    Calculates the maximum drawdown of the portfolio based on the historical % pnl returns of the target portfolio.
    
    Args:
        portfolio_values (list[int]): The historical % pnl returns of the target portfolio.

    Returns:
        int: The maximum % pnl drawdown of the portfolio.

    O(N) time complexity.
    '''
    if len(portfolio_values) == 0:
        return 0
    max_value = portfolio_values[0]
    max_drawdown = 0
    for value in portfolio_values:
        max_drawdown = max(max_drawdown, (max_value - value)) if max_value > 0 else 0
        max_value = max(max_value, value)
    return max_drawdown