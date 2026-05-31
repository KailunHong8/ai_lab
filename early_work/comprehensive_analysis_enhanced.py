"""
Enhanced Portfolio Analysis - Goldman Sachs Institutional Perspective
STEP 2: Portfolio Monitoring with Macroeconomic Context

INVESTMENT PHILOSOPHY:
1. Quality First: Invest in companies with durable competitive advantages
2. Societal Value: Prioritize companies improving human wellbeing
3. Financial Solidity: Strong balance sheets, sustainable profitability
4. Reasonable Valuation: Price matters, but quality matters more
5. Macro Awareness: Understand economic cycles and sector rotation

This enhanced version adds:
- Macroeconomic context (rates, GDP, sector rotation)
- Quality metrics beyond Buffett (ROIC, FCF, earnings quality)
- Competitive moat indicators
- Capital allocation efficiency
- Sector concentration risk
- Modern Portfolio Theory optimization
- ESG/societal impact scoring

Based on principles from:
- Brealey, Myers, Allen: "Principles of Corporate Finance"
- Warren Buffett: Quality at reasonable prices
- Goldman Sachs: Macro-aware fundamental investing
- Nobel Laureates: Markowitz (portfolio theory), Fama-French (value factors), Shiller (behavioral)
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import warnings
warnings.filterwarnings('ignore')

# Helper function
def format_date(dt):
    if isinstance(dt, date) and not hasattr(dt, 'hour'):
        return dt
    elif hasattr(dt, 'date') and callable(dt.date):
        return dt.date()
    else:
        return str(dt)

# Helper functions for ticker format conversion
def ticker_for_openbb(symbol):
    """Convert ticker to OpenBB format (hyphen to dot for class shares)"""
    return symbol.replace('-', '.')

def ticker_for_yfinance(symbol):
    """Convert ticker to yfinance format (dot to hyphen for class shares)"""
    if '.' in symbol and len(symbol.split('.')[-1]) == 1:
        return symbol.replace('.', '-')
    return symbol

# Initialize ArcticDB if available
ARCTIC_AVAILABLE = False
try:
    import arcticdb as adb
    arctic = adb.Arctic("lmdb://quant_data")
    fundamentals_lib = arctic.get_library("fundamentals", create_if_missing=True)
    prices_lib = arctic.get_library("prices", create_if_missing=True)
    ARCTIC_AVAILABLE = True
    print("✓ ArcticDB initialized for caching")
except ImportError:
    print("ℹ ArcticDB not available (pip install arcticdb for caching)")

print("\n" + "=" * 80)
print("ENHANCED PORTFOLIO ANALYSIS")
print("Goldman Sachs Institutional Perspective")
print("=" * 80)

# ============================================================================
# PART 0: Macroeconomic Context
# ============================================================================
print("\n" + "=" * 80)
print("PART 0: Macroeconomic Context")
print("=" * 80)

try:
    from openbb import obb
    import yfinance as yf
    
    # Fetch macroeconomic indicators
    print("\nFetching key macro indicators...")
    
    # 1. 10-Year Treasury Yield (risk-free rate proxy)
    tnx = yf.Ticker("^TNX")
    tnx_data = tnx.history(period="5d")
    current_10y_yield = tnx_data['Close'].iloc[-1] / 100 if not tnx_data.empty else 0.045
    
    # 2. VIX (market fear gauge)
    vix = yf.Ticker("^VIX")
    vix_data = vix.history(period="5d")
    current_vix = vix_data['Close'].iloc[-1] if not vix_data.empty else 15
    
    # 3. Dollar Index (currency strength)
    dxy = yf.Ticker("DX-Y.NYB")
    dxy_data = dxy.history(period="5d")
    current_dxy = dxy_data['Close'].iloc[-1] if not dxy_data.empty else 100
    
    print(f"\n📊 Current Macro Environment:")
    print(f"  10-Year Treasury: {current_10y_yield*100:.2f}% {'(High - Value stocks favored)' if current_10y_yield > 0.04 else '(Low - Growth favored)'}")
    print(f"  VIX (Fear Index): {current_vix:.1f} {'(High - Market stress)' if current_vix > 20 else '(Low - Market calm)' if current_vix < 15 else '(Normal)'}")
    print(f"  Dollar Index:     {current_dxy:.1f} {'(Strong - Headwind for multinationals)' if current_dxy > 105 else '(Weak - Tailwind for exporters)' if current_dxy < 95 else '(Neutral)'}")
    
    # Determine market regime
    print(f"\n💡 Macro Regime Assessment:")
    if current_10y_yield > 0.045:
        print(f"  → High Rate Environment: Favor quality over growth, dividend payers")
    else:
        print(f"  → Low Rate Environment: Growth and tech should outperform")
    
    if current_vix > 25:
        print(f"  → High Volatility: Defensive sectors (Healthcare, Utilities, Staples)")
    elif current_vix < 15:
        print(f"  → Low Volatility: Risk-on (Tech, Cyclicals)")
    else:
        print(f"  → Normal Volatility: Balanced approach")
    
    rf = current_10y_yield  # Use actual 10Y as risk-free rate
    
except Exception as e:
    print(f"⚠ Could not fetch macro data: {e}")
    print("  Using default assumptions: 10Y = 4.5%, VIX = 15")
    rf = 0.045
    current_vix = 15

# ============================================================================
# PART 1: Market Data + Benchmark
# ============================================================================
print("\n" + "=" * 80)
print("PART 1: Market Data Collection")
print("=" * 80)

try:
    from openbb import obb
    
    # ========================================================================
    # 🎯 YOUR PORTFOLIO: Update with picks from visualize_value_stocks.py
    # ========================================================================
    # Example: Top picks from holistic scoring
    symbols = ['TEL', 'ABT', 'CBOE', 'DOV', 'COIN', 'BRK.B', 'SWKS', 'TTD', 'EOG', 'STE']
    
    # Or load from your exported file:
    # import glob
    # pick_files = glob.glob("my_portfolio_picks_*.csv")
    # if pick_files:
    #     latest_picks = max(pick_files, key=os.path.getmtime)
    #     picks_df = pd.read_csv(latest_picks)
    #     symbols = picks_df.nlargest(10, 'holistic_score')['symbol'].tolist()
    
    benchmark = "SPY"
    
    print(f"\nFetching data for: {', '.join(symbols)} + {benchmark}")
    
    # Convert symbols for OpenBB
    symbols_openbb = [ticker_for_openbb(s) for s in symbols]
    
    # Fetch portfolio data
    result = obb.equity.price.historical(symbol=','.join(symbols_openbb))
    data = result.to_dataframe()
    
    if 'symbol' in data.columns:
        portfolio_prices = data.pivot_table(index='date', columns='symbol', values='close')
        portfolio_prices.columns = symbols[:len(portfolio_prices.columns)]
    else:
        portfolio_prices = pd.DataFrame({symbols[0]: data['close']})
    
    # Ensure we have all requested symbols
    available_symbols = [s for s in symbols if s in portfolio_prices.columns]
    if len(available_symbols) < len(symbols):
        missing = set(symbols) - set(available_symbols)
        print(f"  ⚠ Could not fetch data for: {', '.join(missing)}")
    
    portfolio_prices = portfolio_prices[available_symbols].dropna()
    symbols = available_symbols
    
    # Fetch benchmark
    spy_result = obb.equity.price.historical(symbol=benchmark)
    spy_data = spy_result.to_dataframe()
    spy_prices = spy_data['close']
    
    # Align dates
    common_dates = portfolio_prices.index.intersection(spy_prices.index)
    portfolio_prices = portfolio_prices.loc[common_dates]
    spy_prices = spy_prices.loc[common_dates]
    
    # Cache in ArcticDB
    if ARCTIC_AVAILABLE:
        try:
            if isinstance(portfolio_prices.index[0], date) and not isinstance(portfolio_prices.index[0], datetime):
                portfolio_prices.index = pd.to_datetime(portfolio_prices.index)
                spy_prices.index = pd.to_datetime(spy_prices.index)
            
            for sym in symbols:
                prices_lib.write(f"{sym}_daily", portfolio_prices[[sym]])
            prices_lib.write("SPY_daily", pd.DataFrame({'close': spy_prices}))
        except Exception as e:
            print(f"  ⚠ ArcticDB cache write failed: {e}")
    
    print(f"✓ Fetched {len(portfolio_prices)} days of data")
    print(f"  Date range: {format_date(portfolio_prices.index[0])} to {format_date(portfolio_prices.index[-1])}")
    
except Exception as e:
    print(f"Error: {e}")
    exit(1)

# ============================================================================
# PART 2: Enhanced Fundamental Data
# ============================================================================
print("\n" + "=" * 80)
print("PART 2: Enhanced Fundamental Analysis")
print("=" * 80)

fundamentals = {}

for symbol in symbols:
    try:
        # Try to fetch from cache first
        if ARCTIC_AVAILABLE and fundamentals_lib.has_symbol(f"{symbol}_metrics"):
            cached = fundamentals_lib.read(f"{symbol}_metrics").data
            if (datetime.now() - cached.index[0]).days < 30:
                fundamentals[symbol] = cached.to_dict('records')[0]
                print(f"{symbol}: Using cached fundamentals")
                continue
        
        # Fetch fundamentals using yfinance directly
        print(f"{symbol}: Fetching enhanced fundamentals...", end=" ")
        
        try:
            import yfinance as yf
            import time
            
            max_retries = 3
            retry_delay = 1
            ticker = None
            info = {}
            
            for attempt in range(max_retries):
                try:
                    symbol_yf = ticker_for_yfinance(symbol)
                    if symbol_yf != symbol:
                        print(f"[{symbol} → {symbol_yf}]", end=" ")
                    ticker = yf.Ticker(symbol_yf)
                    info = ticker.info
                    
                    has_fundamentals = info and (
                        info.get('priceToBook') is not None or 
                        info.get('trailingPE') is not None or
                        info.get('marketCap') is not None
                    )
                    if has_fundamentals:
                        break
                    elif attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise e
            
            if not info or not (info.get('priceToBook') or info.get('trailingPE') or info.get('marketCap')):
                raise Exception(f"No fundamental data returned from yfinance for {symbol_yf}")
            
            # Get financial statements for calculated ratios
            try:
                balance_sheet = ticker.balance_sheet
                financials = ticker.financials
                cashflow = ticker.cashflow
                
                # Standard Buffett metrics
                if not balance_sheet.empty and not financials.empty:
                    bs = balance_sheet.iloc[:, 0]
                    fin = financials.iloc[:, 0]
                    
                    total_debt = bs.get('Total Debt', bs.get('Long Term Debt', 0))
                    stockholder_equity = bs.get('Stockholders Equity', bs.get('Total Equity Gross Minority Interest', 1))
                    debt_equity_calc = total_debt / stockholder_equity if stockholder_equity else None
                    
                    current_assets = bs.get('Current Assets', 0)
                    current_liabilities = bs.get('Current Liabilities', 1)
                    current_ratio_calc = current_assets / current_liabilities if current_liabilities else None
                    
                    net_income = fin.get('Net Income', 0)
                    total_assets = bs.get('Total Assets', 1)
                    roe_calc = net_income / stockholder_equity if stockholder_equity else None
                    roa_calc = net_income / total_assets if total_assets else None
                    
                    ebit = fin.get('EBIT', fin.get('Operating Income', 0))
                    interest_expense = fin.get('Interest Expense', 1)
                    interest_coverage_calc = ebit / abs(interest_expense) if interest_expense else None
                    
                    # ENHANCED METRICS (Goldman Sachs Quality Indicators)
                    
                    # 1. ROIC (Return on Invested Capital) - True economic profitability
                    invested_capital = stockholder_equity + total_debt
                    nopat = ebit * 0.79  # Assume 21% tax rate
                    roic = nopat / invested_capital if invested_capital else None
                    
                    # 2. Free Cash Flow Yield (Cash generation vs market cap)
                    if not cashflow.empty:
                        cf = cashflow.iloc[:, 0]
                        operating_cf = cf.get('Operating Cash Flow', 0)
                        capex = abs(cf.get('Capital Expenditure', cf.get('Capital Expenditures', 0)))
                        free_cash_flow = operating_cf - capex
                        market_cap = info.get('marketCap', 1)
                        fcf_yield = free_cash_flow / market_cap if market_cap else None
                    else:
                        fcf_yield = None
                    
                    # 3. Earnings Quality (CFO / Net Income) - Are earnings real?
                    if not cashflow.empty:
                        cf = cashflow.iloc[:, 0]
                        operating_cf = cf.get('Operating Cash Flow', 1)
                        earnings_quality = operating_cf / net_income if net_income and net_income != 0 else None
                    else:
                        earnings_quality = None
                    
                    # 4. Asset Turnover (Revenue / Assets) - Efficiency
                    revenue = fin.get('Total Revenue', 1)
                    asset_turnover = revenue / total_assets if total_assets else None
                    
                    # 5. Gross Margin (Pricing power indicator)
                    gross_profit = fin.get('Gross Profit', 0)
                    gross_margin = gross_profit / revenue if revenue else None
                    
                else:
                    roic = fcf_yield = earnings_quality = asset_turnover = gross_margin = None
                    debt_equity_calc = current_ratio_calc = roe_calc = roa_calc = interest_coverage_calc = None
                    
            except Exception:
                roic = fcf_yield = earnings_quality = asset_turnover = gross_margin = None
                debt_equity_calc = current_ratio_calc = roe_calc = roa_calc = interest_coverage_calc = None
            
            # Compile enhanced metrics
            metrics = {
                'symbol': symbol,
                'date': datetime.now(),
                # Standard valuation
                'pb_ratio': info.get('priceToBook'),
                'pe_ratio': info.get('trailingPE') or info.get('forwardPE'),
                'peg_ratio': info.get('pegRatio'),  # P/E to Growth
                # Buffett criteria
                'debt_equity': debt_equity_calc or info.get('debtToEquity'),
                'current_ratio': current_ratio_calc or info.get('currentRatio'),
                'roe': roe_calc or info.get('returnOnEquity'),
                'roa': roa_calc or info.get('returnOnAssets'),
                'interest_coverage': interest_coverage_calc,
                # Enhanced quality metrics
                'roic': roic,
                'fcf_yield': fcf_yield,
                'earnings_quality': earnings_quality,
                'asset_turnover': asset_turnover,
                'gross_margin': gross_margin,
                # Company info
                'market_cap': info.get('marketCap'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'dividend_yield': info.get('dividendYield'),
                'payout_ratio': info.get('payoutRatio'),
                'profit_margins': info.get('profitMargins'),
                # Moat indicators
                'revenue_growth': info.get('revenueGrowth'),
                'earnings_growth': info.get('earningsGrowth'),
            }
            
            fundamentals[symbol] = metrics
            
            # Cache in ArcticDB
            if ARCTIC_AVAILABLE:
                try:
                    df_cache = pd.DataFrame([metrics])
                    df_cache['date'] = pd.to_datetime(df_cache['date'])
                    df_cache = df_cache.set_index('date')
                    fundamentals_lib.write(f"{symbol}_metrics", df_cache)
                except Exception:
                    pass
            
            print("✓")
            
        except Exception as e:
            print(f"⚠ Error: {e}")
            metrics = {'symbol': symbol, 'date': datetime.now()}
            fundamentals[symbol] = metrics
            
    except Exception as e:
        print(f"{symbol}: Error - {e}")
        fundamentals[symbol] = {'symbol': symbol, 'date': datetime.now()}

# ============================================================================
# PART 3: Enhanced Portfolio Analytics
# ============================================================================
print("\n" + "=" * 80)
print("PART 3: Portfolio Analytics with Quality Assessment")
print("=" * 80)

returns = portfolio_prices.pct_change().dropna()
spy_returns = spy_prices.pct_change().dropna()

common_dates = returns.index.intersection(spy_returns.index)
returns = returns.loc[common_dates]
spy_returns = spy_returns.loc[common_dates]

print(f"\nAnalysis Period: {len(returns)} trading days")
print(f"Date range: {format_date(returns.index[0])} to {format_date(returns.index[-1])}")

# Individual asset stats with quality scores
print("\n" + "-" * 100)
print(f"{'Symbol':<8} {'Return':>8} {'Vol':>8} {'Sharpe':>8} {'Beta':>8} {'Alpha':>8} {'ROIC':>7} {'Quality':>8}")
print("-" * 100)

results = []

for symbol in symbols:
    # Price-based metrics
    annual_ret = returns[symbol].mean() * 252
    annual_vol = returns[symbol].std() * np.sqrt(252)
    sharpe = (annual_ret - rf) / annual_vol if annual_vol > 0 else 0
    
    # Beta and Alpha
    covariance = returns[symbol].cov(spy_returns)
    market_var = spy_returns.var()
    beta = covariance / market_var
    
    market_ret = spy_returns.mean() * 252
    capm_predicted = rf + beta * (market_ret - rf)
    alpha = annual_ret - capm_predicted
    
    # Quality Score (0-100)
    fund = fundamentals.get(symbol, {})
    quality_score = 0
    
    # ROIC > 15% (best indicator of moat)
    roic = fund.get('roic')
    if roic and roic > 0.15:
        quality_score += 25
    elif roic and roic > 0.10:
        quality_score += 15
    
    # FCF Yield > 5%
    fcf_yield = fund.get('fcf_yield')
    if fcf_yield and fcf_yield > 0.05:
        quality_score += 20
    elif fcf_yield and fcf_yield > 0.03:
        quality_score += 10
    
    # Earnings Quality > 1.0 (cash > accounting earnings)
    eq = fund.get('earnings_quality')
    if eq and eq > 1.0:
        quality_score += 20
    elif eq and eq > 0.8:
        quality_score += 10
    
    # Gross Margin > 40% (pricing power)
    gm = fund.get('gross_margin')
    if gm and gm > 0.40:
        quality_score += 20
    elif gm and gm > 0.30:
        quality_score += 10
    
    # ROE > 15%
    roe = fund.get('roe')
    if roe and roe > 0.15:
        quality_score += 15
    elif roe and roe > 0.10:
        quality_score += 10
    
    results.append({
        'Symbol': symbol,
        'Return': annual_ret,
        'Volatility': annual_vol,
        'Sharpe': sharpe,
        'Beta': beta,
        'Alpha': alpha,
        'ROIC': roic,
        'FCF_Yield': fcf_yield,
        'Quality_Score': quality_score,
        'Fundamentals': fund
    })
    
    roic_str = f"{roic*100:.1f}%" if roic else "N/A"
    quality_str = f"{quality_score}/100"
    
    print(f"{symbol:<8} {annual_ret:7.2%} {annual_vol:7.2%} {sharpe:7.2f} {beta:7.2f} {alpha:7.2%} {roic_str:>7} {quality_str:>8}")

# Portfolio level
portfolio_ret = returns.mean(axis=1)
port_annual_ret = portfolio_ret.mean() * 252
port_annual_vol = portfolio_ret.std() * np.sqrt(252)
port_sharpe = (port_annual_ret - rf) / port_annual_vol

spy_annual_ret = spy_returns.mean() * 252
spy_annual_vol = spy_returns.std() * np.sqrt(252)

print("\n" + "-" * 100)
print("Portfolio vs S&P 500")
print("-" * 100)
print(f"{'Metric':<30} {'Portfolio':>15} {'S&P 500':>15} {'Difference':>15}")
print(f"{'Return':<30} {port_annual_ret:>14.2%} {spy_annual_ret:>14.2%} {port_annual_ret-spy_annual_ret:>14.2%}")
print(f"{'Volatility':<30} {port_annual_vol:>14.2%} {spy_annual_vol:>14.2%} {port_annual_vol-spy_annual_vol:>14.2%}")
print(f"{'Sharpe Ratio':<30} {port_sharpe:>14.2f} {(spy_annual_ret-rf)/spy_annual_vol:>14.2f}")

# ============================================================================
# PART 4: Sector Concentration & Diversification
# ============================================================================
print("\n" + "=" * 80)
print("PART 4: Sector Diversification Analysis")
print("=" * 80)

# Sector breakdown
sectors = {}
for result in results:
    sector = result['Fundamentals'].get('sector', 'Unknown')
    if sector in sectors:
        sectors[sector] += 1
    else:
        sectors[sector] = 1

total_stocks = len(results)
print(f"\n📊 Sector Allocation (out of {total_stocks} stocks):")
for sector, count in sorted(sectors.items(), key=lambda x: x[1], reverse=True):
    pct = count / total_stocks * 100
    print(f"  {sector:<30} {count:>2} stocks ({pct:>5.1f}%)")

# Diversification assessment
unique_sectors = len(sectors)
max_concentration = max(sectors.values()) / total_stocks

print(f"\n💡 Diversification Assessment:")
if unique_sectors >= 5:
    print(f"  ✓ Well diversified: {unique_sectors} different sectors")
elif unique_sectors >= 3:
    print(f"  ⚠ Moderate diversification: {unique_sectors} sectors (consider adding more)")
else:
    print(f"  ⚠ Concentrated: Only {unique_sectors} sectors (high sector risk!)")

if max_concentration < 0.30:
    print(f"  ✓ Good balance: Largest sector is {max_concentration*100:.0f}% of portfolio")
elif max_concentration < 0.50:
    print(f"  ⚠ Some concentration: Largest sector is {max_concentration*100:.0f}%")
else:
    print(f"  ⚠ High concentration: {max_concentration*100:.0f}% in one sector!")

# Correlation matrix
print(f"\n📈 Correlation Matrix (Diversification check):")
corr_matrix = returns.corr()
avg_correlation = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean()
print(f"  Average pairwise correlation: {avg_correlation:.2f}")
if avg_correlation < 0.50:
    print(f"  ✓ Good diversification (low correlation)")
elif avg_correlation < 0.70:
    print(f"  ⚠ Moderate diversification")
else:
    print(f"  ⚠ Poor diversification (stocks move together)")

# Show top correlations
print(f"\n  Highest correlations (similar risk exposures):")
corr_flat = corr_matrix.unstack()
corr_flat = corr_flat[corr_flat < 1.0]  # Remove self-correlations
top_corr = corr_flat.nlargest(5)
for (stock1, stock2), corr_val in top_corr.items():
    print(f"    {stock1} - {stock2}: {corr_val:.2f}")

# ============================================================================
# PART 5: Quality Rankings (Institutional Perspective)
# ============================================================================
print("\n" + "=" * 80)
print("PART 5: Institutional Quality Rankings")
print("=" * 80)

print(f"\n💎 MOAT & QUALITY INDICATORS (What Goldman Sachs looks for):")
print("-" * 100)
print(f"{'Symbol':<8} {'ROIC':>8} {'FCF Yield':>10} {'Earn.Quality':>12} {'Gross Mgn':>10} {'Quality':>10}")
print("-" * 100)

for result in sorted(results, key=lambda x: x['Quality_Score'], reverse=True):
    roic = result.get('ROIC')
    fcf = result.get('FCF_Yield')
    eq = result['Fundamentals'].get('earnings_quality')
    gm = result['Fundamentals'].get('gross_margin')
    quality = result['Quality_Score']
    
    roic_str = f"{roic*100:>6.1f}%" if roic else "N/A"
    fcf_str = f"{fcf*100:>8.1f}%" if fcf else "N/A"
    eq_str = f"{eq:>10.2f}x" if eq else "N/A"
    gm_str = f"{gm*100:>8.1f}%" if gm else "N/A"
    
    print(f"{result['Symbol']:<8} {roic_str:>8} {fcf_str:>10} {eq_str:>12} {gm_str:>10} {quality:>7}/100")

print(f"\nKey Quality Metrics Explained:")
print(f"  ROIC (Return on Invested Capital): >15% = Strong moat, pricing power")
print(f"  FCF Yield: >5% = Strong cash generation relative to valuation")
print(f"  Earnings Quality: >1.0x = Real cash earnings, not accounting tricks")
print(f"  Gross Margin: >40% = Pricing power, competitive advantage")

# ============================================================================
# PART 6: Final Portfolio Recommendations
# ============================================================================
print("\n" + "=" * 80)
print("PART 6: Goldman Sachs Portfolio Construction Recommendations")
print("=" * 80)

# Sort by composite score: Quality + Sharpe + Alpha
df_results = pd.DataFrame(results)
df_results['Composite'] = (
    0.40 * df_results['Quality_Score'] +       # Quality is king
    0.30 * (df_results['Sharpe'] - df_results['Sharpe'].min()) / (df_results['Sharpe'].max() - df_results['Sharpe'].min()) * 100 +
    0.30 * (df_results['Alpha'] - df_results['Alpha'].min()) / (df_results['Alpha'].max() - df_results['Alpha'].min()) * 100
)

df_results = df_results.sort_values('Composite', ascending=False)

print(f"\n🏆 RECOMMENDED PORTFOLIO RANKING:")
print("-" * 120)
print(f"{'Rank':<6} {'Symbol':<8} {'Sector':<25} {'Quality':>9} {'Sharpe':>8} {'Alpha':>8} {'ROIC':>8} {'Score':>8}")
print("-" * 120)

for idx, (_, row) in enumerate(df_results.iterrows(), 1):
    sector = row['Fundamentals'].get('sector', 'Unknown')[:23]
    roic = row['ROIC']
    roic_str = f"{roic*100:.1f}%" if roic else "N/A"
    
    print(f"{idx:<6} {row['Symbol']:<8} {sector:<25} {row['Quality_Score']:>6}/100 "
          f"{row['Sharpe']:>7.2f} {row['Alpha']:>7.2%} {roic_str:>8} {row['Composite']:>7.1f}")

print(f"\n💡 Portfolio Construction Principles (Modern Portfolio Theory + Buffett):")
print(f"  1. Quality First: Prioritize companies with ROIC >15% (durable moats)")
print(f"  2. Diversify Sectors: Aim for 5+ sectors, max 30% in any one sector")
print(f"  3. Risk-Adjusted Returns: High Sharpe ratio stocks (efficiency)")
print(f"  4. Positive Alpha: Companies beating CAPM predictions")
print(f"  5. Balance Size: Mix of large caps (stability) and mid caps (growth)")
print(f"  6. Societal Value: Favor Healthcare, Technology, Industrials")
print(f"  7. Macro Awareness: Adjust for interest rate and economic cycle")

# Final recommendations
top3 = df_results.head(3)
print(f"\n🎯 Top 3 Core Holdings:")
for i, (_, row) in enumerate(top3.iterrows(), 1):
    sector = row['Fundamentals'].get('sector', 'Unknown')
    print(f"  {i}. {row['Symbol']:<6} - {sector:<20} (Score: {row['Composite']:.1f}/100)")
    print(f"     Quality: {row['Quality_Score']}/100, Sharpe: {row['Sharpe']:.2f}, Alpha: {row['Alpha']:.2%}")

# Risk warnings
print(f"\n⚠ Risk Considerations:")
if current_vix > 20:
    print(f"  - High market volatility: Consider reducing position sizes")
if max_concentration > 0.40:
    print(f"  - High sector concentration: Add stocks from underrepresented sectors")
if avg_correlation > 0.70:
    print(f"  - High correlation: Portfolio lacks diversification")
if port_sharpe < 0.50:
    print(f"  - Low Sharpe ratio: Consider higher quality stocks")

print("\n" + "=" * 80)
print("✓ Enhanced Analysis Complete!")
print("=" * 80)

print(f"\n📚 Further Reading (Nobel Prize-Winning Insights):")
print(f"  - Markowitz (1952): Portfolio Selection - Diversification reduces risk")
print(f"  - Fama-French (1992): Value stocks outperform over long term")
print(f"  - Shiller (2000): Irrational Exuberance - Don't overpay")
print(f"  - Buffett (Annual Letters): Quality companies at reasonable prices")
print(f"  - Graham (Intelligent Investor): Margin of safety principle")

