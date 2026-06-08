"""
Full Market Scanner - Buffett Value Criteria

Efficiently scans entire stock universe:
- S&P 500 (500 stocks)
- Russell 1000 (1000 stocks)
- All US stocks (5000+ stocks)

Uses parallel processing and ArcticDB caching for speed.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
warnings.filterwarnings('ignore')

# Helper function for ticker format conversion
def ticker_for_yfinance(symbol):
    """Convert ticker to yfinance format (dot to hyphen for class shares)"""
    # BRK.B → BRK-B, BF.A → BF-A, etc.
    if '.' in symbol and len(symbol.split('.')[-1]) == 1:
        return symbol.replace('.', '-')
    return symbol

# ============================================================================
# Configuration
# ============================================================================

# Choose your universe (set to True for the one you want)
SCAN_SP500 = True          # ~500 stocks, ~10-15 minutes
SCAN_RUSSELL_1000 = False  # ~1000 stocks, ~30 minutes
SCAN_ALL_US = False        # ~5000 stocks, ~2-3 hours

# Parallel processing settings
MAX_WORKERS = 10           # Number of parallel threads (adjust based on your CPU)
CACHE_DAYS = 7             # Use cached data if fresher than this
RATE_LIMIT_DELAY = 0.1     # Seconds between batches (respect yfinance rate limits)

print("=" * 70)
print("Full Market Scanner - Buffett Value Criteria")
print("=" * 70)

# ============================================================================
# Setup ArcticDB
# ============================================================================

try:
    import arcticdb as adb
    arctic = adb.Arctic("lmdb://quant_data")
    fundamentals_lib = arctic.get_library("fundamentals", create_if_missing=True)
    print("\n✓ ArcticDB connected")
except ImportError:
    print("\n✗ ArcticDB required: pip install arcticdb")
    exit(1)

# ============================================================================
# Get Stock Universe
# ============================================================================

def get_sp500_tickers():
    """Get S&P 500 tickers from multiple sources"""
    
    # Method 1: Try Wikipedia with headers to avoid 403
    try:
        import requests
        from io import StringIO
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        df = tables[0]
        tickers = df['Symbol'].str.replace('.', '-').tolist()
        print(f"✓ Fetched {len(tickers)} tickers from Wikipedia")
        return tickers
    except Exception as e:
        print(f"  Wikipedia failed: {e}")
    
    # Method 2: Use yfinance screener
    try:
        import yfinance as yf
        # Get tickers from yfinance screener (S&P 500)
        sp500 = yf.Ticker("^GSPC")  # S&P 500 index
        # This doesn't give constituents, try another method
    except Exception:
        pass
    
    # Method 3: Use pre-defined list (backup)
    print("  Using pre-defined S&P 500 list (may be slightly outdated)")
    # Major S&P 500 components as of 2024-2025
    return [
        # Tech (Magnificent 7 + others)
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
        "AVGO", "ORCL", "CSCO", "ADBE", "CRM", "ACN", "AMD", "INTC", "IBM", "QCOM",
        "TXN", "INTU", "NOW", "AMAT", "LRCX", "KLAC", "SNPS", "CDNS", "PANW",
        
        # Finance
        "BRK.B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SCHW", "AXP",
        "BLK", "C", "USB", "PNC", "TFC", "COF", "BK", "AIG", "MET", "PRU",
        "ALL", "TRV", "PGR", "CB", "AFL", "HIG", "CME", "ICE", "SPGI", "MCO",
        
        # Healthcare
        "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
        "AMGN", "GILD", "CVS", "CI", "ELV", "HCA", "BSX", "MDT", "ISRG", "SYK",
        "VRTX", "ZTS", "REGN", "IQV", "BDX", "HUM", "CNC", "CAH", "MCK", "COO",
        
        # Consumer Discretionary
        "TSLA", "AMZN", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "CMG",
        "MAR", "ABNB", "GM", "F", "ORLY", "AZO", "YUM", "ROST", "DHI", "LEN",
        "DG", "DLTR", "EBAY", "DECK", "TPR", "BBY", "ULTA", "RCL", "CCL", "LVS",
        
        # Consumer Staples  
        "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL", "KMB",
        "GIS", "K", "HSY", "STZ", "TAP", "CAG", "CPB", "SJM", "CHD", "CLX",
        "TSN", "HRL", "MKC", "KHC", "MNST", "KDP", "EL", "ADM", "BG",
        
        # Energy
        "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HES",
        "HAL", "BKR", "WMB", "KMI", "OKE", "LNG", "FANG", "DVN", "MRO", "APA",
        
        # Industrials
        "GE", "CAT", "RTX", "HON", "UPS", "BA", "LMT", "DE", "UNP", "MMM",
        "GD", "NOC", "ITW", "EMR", "ETN", "PH", "CARR", "OTIS", "JCI", "WM",
        "RSG", "NSC", "CSX", "FDX", "PCAR", "URI", "IR", "FAST", "PAYX", "ROK",
        
        # Materials
        "LIN", "APD", "SHW", "FCX", "NEM", "DOW", "DD", "ECL", "NUE", "VMC",
        "MLM", "PPG", "CTVA", "IFF", "EMN", "ALB", "CE", "FMC", "MOS", "CF",
        
        # Real Estate
        "AMT", "PLD", "CCI", "EQIX", "PSA", "WELL", "DLR", "O", "SBAC", "AVB",
        "EQR", "VTR", "VICI", "SPG", "ARE", "MAA", "PEAK", "ESS", "IRM", "CBRE",
        
        # Utilities
        "NEE", "SO", "DUK", "CEG", "D", "AEP", "SRE", "EXC", "XEL", "PCG",
        "ED", "WEC", "ES", "PEG", "AWK", "DTE", "FE", "EIX", "ETR", "PPL",
        
        # Communication Services
        "GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR",
        "EA", "TTWO", "MTCH", "NWSA", "PARA", "WBD", "OMC", "IPG", "FOXA",
    ]

def get_russell_1000_tickers():
    """Get Russell 1000 tickers (approximation using major exchanges)"""
    print("Note: Using expanded list (S&P 500 + Mid/Small caps)")
    
    sp500 = get_sp500_tickers()
    
    # Add additional mid/small caps
    additional = [
        # Mid-cap growth  
        "CRWD", "ZS", "DDOG", "NET", "OKTA", "SNOW", "MDB", "TEAM", "HUBS",
        "FTNT", "WDAY", "VEEV", "ANSS", "RBLX", "U", "DASH", "DOCU",
        
        # Mid-cap value
        "PINS", "LYFT", "UBER", "ABNB", "COIN", "HOOD", "SOFI", "AFRM",
        
        # Small-cap tech
        "DOCN", "GTLB", "S", "BILL", "ZI", "CFLT", "ESTC", "DBX",
        
        # Clean energy
        "PLUG", "FSLR", "ENPH", "SEDG", "RUN", "BE", "BLNK", "CHPT",
    ]
    
    return list(set(sp500 + additional))

def get_all_us_tickers():
    """Get comprehensive US stock list"""
    print("Note: Using Russell 1000 proxy (full universe requires data subscription)")
    # For truly comprehensive scanning, users can provide their own CSV of tickers
    # or use paid data services (Bloomberg, Refinitiv, etc.)
    return get_russell_1000_tickers()

print("\n" + "=" * 70)
print("Loading Stock Universe")
print("=" * 70)

if SCAN_SP500:
    print("\nFetching S&P 500 constituents...")
    stock_universe = get_sp500_tickers()
    universe_name = "S&P 500"
elif SCAN_RUSSELL_1000:
    print("\nFetching Russell 1000 constituents...")
    stock_universe = get_russell_1000_tickers()
    universe_name = "Russell 1000"
elif SCAN_ALL_US:
    print("\nFetching all US stocks...")
    stock_universe = get_all_us_tickers()
    universe_name = "All US Stocks"
else:
    print("\n✗ No universe selected! Set one to True in configuration.")
    exit(1)

print(f"✓ Loaded {len(stock_universe)} tickers from {universe_name}")

# ============================================================================
# Parallel Data Fetching
# ============================================================================

def fetch_stock_fundamentals(symbol):
    """Fetch fundamentals for a single stock with caching"""
    
    # Check cache first
    cache_key = f"{symbol}_fundamentals_scan"
    if fundamentals_lib.has_symbol(cache_key):
        try:
            cached = fundamentals_lib.read(cache_key).data
            cache_age = (datetime.now() - pd.to_datetime(cached.index[0])).days
            if cache_age < CACHE_DAYS:
                return {'status': 'cached', 'data': cached.to_dict('records')[0]}
        except Exception:
            pass
    
    # Fetch from yfinance
    try:
        import yfinance as yf
        
        # Convert ticker format for yfinance (BRK.B → BRK-B)
        symbol_yf = ticker_for_yfinance(symbol)
        ticker = yf.Ticker(symbol_yf)
        info = ticker.info
        
        # Quick validation - skip if critical data missing
        if not info or len(info) < 5:
            return {'status': 'error', 'symbol': symbol, 'error': 'No data returned'}
        
        # Get balance sheet and financials
        try:
            bs = ticker.balance_sheet.iloc[:, 0] if not ticker.balance_sheet.empty else pd.Series()
            fin = ticker.financials.iloc[:, 0] if not ticker.financials.empty else pd.Series()
            
            # Calculate ratios
            total_debt = bs.get('Total Debt', bs.get('Long Term Debt', 0))
            equity = bs.get('Stockholders Equity', bs.get('Total Equity Gross Minority Interest', 1))
            debt_equity = total_debt / equity if equity and equity != 0 else None
            
            current_assets = bs.get('Current Assets', 0)
            current_liabilities = bs.get('Current Liabilities', 1)
            current_ratio = current_assets / current_liabilities if current_liabilities else None
            
            net_income = fin.get('Net Income', 0)
            total_assets = bs.get('Total Assets', 1)
            roe = net_income / equity if equity and equity != 0 else None
            roa = net_income / total_assets if total_assets else None
            
            ebit = fin.get('EBIT', fin.get('Operating Income', 0))
            interest_expense = fin.get('Interest Expense', 1)
            interest_coverage = ebit / abs(interest_expense) if interest_expense else None
        except Exception:
            debt_equity = None
            current_ratio = None
            roe = None
            roa = None
            interest_coverage = None
        
        # Compile metrics
        metrics = {
            'symbol': symbol,
            'fetch_date': datetime.now(),
            'company_name': info.get('longName', symbol),
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'market_cap': info.get('marketCap', 0),
            'pb_ratio': info.get('priceToBook'),
            'pe_ratio': info.get('trailingPE') or info.get('forwardPE'),
            'debt_equity': debt_equity or info.get('debtToEquity'),
            'current_ratio': current_ratio or info.get('currentRatio'),
            'roe': roe or info.get('returnOnEquity'),
            'roa': roa or info.get('returnOnAssets'),
            'interest_coverage': interest_coverage,
            'dividend_yield': info.get('dividendYield'),
            'beta': info.get('beta'),
        }
        
        # Cache in ArcticDB
        try:
            df_cache = pd.DataFrame([metrics])
            df_cache['fetch_date'] = pd.to_datetime(df_cache['fetch_date'])
            df_cache = df_cache.set_index('fetch_date')
            fundamentals_lib.write(cache_key, df_cache)
        except Exception:
            pass
        
        return {'status': 'success', 'data': metrics}
        
    except Exception as e:
        return {'status': 'error', 'symbol': symbol, 'error': str(e)[:100]}

# ============================================================================
# Main Scanning Loop with Progress Tracking
# ============================================================================

print("\n" + "=" * 70)
print("Scanning Market (Parallel Processing)")
print("=" * 70)
print(f"\nConfiguration:")
print(f"  Universe: {universe_name} ({len(stock_universe)} stocks)")
print(f"  Workers: {MAX_WORKERS} parallel threads")
print(f"  Cache: {CACHE_DAYS} days")
print(f"\nThis will take approximately {len(stock_universe) * 0.5 / MAX_WORKERS / 60:.0f}-{len(stock_universe) * 1.0 / MAX_WORKERS / 60:.0f} minutes")
print("\nStarting scan...\n")

all_fundamentals = []
errors = []
cached_count = 0
success_count = 0
error_count = 0

start_time = time.time()

# Process in parallel
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    # Submit all tasks
    future_to_symbol = {executor.submit(fetch_stock_fundamentals, symbol): symbol 
                        for symbol in stock_universe}
    
    # Process completed tasks
    for i, future in enumerate(as_completed(future_to_symbol), 1):
        symbol = future_to_symbol[future]
        
        try:
            result = future.result()
            
            if result['status'] == 'cached':
                all_fundamentals.append(result['data'])
                cached_count += 1
                status = "✓ (cached)"
            elif result['status'] == 'success':
                all_fundamentals.append(result['data'])
                success_count += 1
                status = "✓"
            else:
                errors.append(result)
                error_count += 1
                status = f"✗ ({result['error'][:30]})"
            
            # Progress indicator every 10 stocks
            if i % 10 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed
                remaining = (len(stock_universe) - i) / rate if rate > 0 else 0
                print(f"  [{i}/{len(stock_universe)}] {symbol:<8} {status} | "
                      f"Rate: {rate:.1f}/s | ETA: {remaining/60:.1f}min")
        
        except Exception as e:
            error_count += 1
            errors.append({'symbol': symbol, 'error': str(e)[:100]})
            if i % 10 == 0:
                print(f"  [{i}/{len(stock_universe)}] {symbol:<8} ✗ Exception")
        
        # Rate limiting between batches
        if i % 50 == 0:
            time.sleep(RATE_LIMIT_DELAY)

elapsed_time = time.time() - start_time

print(f"\n{'='*70}")
print(f"Scan Complete!")
print(f"{'='*70}")
print(f"  Total time: {elapsed_time/60:.1f} minutes")
print(f"  Success: {success_count} fetched + {cached_count} cached = {success_count + cached_count} total")
print(f"  Errors: {error_count}")
print(f"  Rate: {len(stock_universe)/elapsed_time:.1f} stocks/second")

# ============================================================================
# Apply Buffett Criteria
# ============================================================================

print("\n" + "=" * 70)
print("Applying Buffett Value Criteria")
print("=" * 70)

df = pd.DataFrame(all_fundamentals)

if len(df) == 0:
    print("\n✗ No data collected. Check errors above.")
    exit(1)

# Apply filters
df['buffett_pb'] = df['pb_ratio'].apply(lambda x: 1 if x and 0 < x < 1.5 else 0)
df['buffett_de'] = df['debt_equity'].apply(lambda x: 1 if x and 0 < x < 0.5 else 0)
df['buffett_cr'] = df['current_ratio'].apply(lambda x: 1 if x and 1.5 < x < 2.5 else 0)
df['buffett_roe'] = df['roe'].apply(lambda x: 1 if x and x > 0.08 else 0)
df['buffett_roa'] = df['roa'].apply(lambda x: 1 if x and x > 0.06 else 0)
df['buffett_ic'] = df['interest_coverage'].apply(lambda x: 1 if x and x > 5 else 0)

df['buffett_score'] = (
    df['buffett_pb'] + df['buffett_de'] + df['buffett_cr'] +
    df['buffett_roe'] + df['buffett_roa'] + df['buffett_ic']
)

# Filter for value stocks (≥4/6 criteria)
value_stocks = df[df['buffett_score'] >= 4].copy()
value_stocks = value_stocks.sort_values('buffett_score', ascending=False)

print(f"\nResults:")
print(f"  Scanned: {len(df)} stocks")
print(f"  Passed ≥4/6 criteria: {len(value_stocks)} stocks ({len(value_stocks)/len(df)*100:.1f}%)")
print(f"  Perfect 6/6 score: {len(value_stocks[value_stocks['buffett_score']==6])} stocks")

# ============================================================================
# Display Top Results
# ============================================================================

print("\n" + "=" * 70)
print("Top 30 Value Stocks")
print("=" * 70)

if len(value_stocks) > 0:
    print("\n" + "-" * 100)
    print(f"{'Rank':<5} {'Symbol':<8} {'Company':<30} {'Sector':<20} {'Score':<7} {'P/B':<8}")
    print("-" * 100)
    
    for idx, row in value_stocks.head(30).iterrows():
        rank = value_stocks.index.get_loc(idx) + 1
        symbol = row['symbol']
        company = row['company_name'][:28]
        sector = row['sector'][:18]
        score = f"{row['buffett_score']:.0f}/6"
        pb = f"{row['pb_ratio']:.2f}" if row['pb_ratio'] and row['pb_ratio'] > 0 else "N/A"
        
        print(f"{rank:<5} {symbol:<8} {company:<30} {sector:<20} {score:<7} {pb:<8}")

# ============================================================================
# Export Results
# ============================================================================

print("\n" + "=" * 70)
print("Export Results")
print("=" * 70)

# Export all scanned data
df.to_csv(f'market_scan_{universe_name.replace(" ", "_").lower()}_{datetime.now().strftime("%Y%m%d")}.csv', index=False)
print(f"\n✓ Full scan exported: market_scan_{universe_name.replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d')}.csv")

# Export value stocks
if len(value_stocks) > 0:
    value_stocks.to_csv(f'value_stocks_{universe_name.replace(" ", "_").lower()}_{datetime.now().strftime("%Y%m%d")}.csv', index=False)
    print(f"✓ Value stocks exported: value_stocks_{universe_name.replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d')}.csv")
    
    # Show sector distribution
    print("\n" + "-" * 70)
    print("Sector Distribution (Value Stocks)")
    print("-" * 70)
    sector_counts = value_stocks['sector'].value_counts()
    for sector, count in sector_counts.head(10).items():
        pct = count / len(value_stocks) * 100
        print(f"  {sector:<30} {count:>3} stocks ({pct:>5.1f}%)")
    
    # Top picks
    print("\n" + "-" * 70)
    print("Suggested Portfolio (Top 10)")
    print("-" * 70)
    top_symbols = value_stocks.head(10)['symbol'].tolist()
    print(f"\nsymbols = {top_symbols}")

# Export errors for review
if errors:
    pd.DataFrame(errors).to_csv(f'scan_errors_{datetime.now().strftime("%Y%m%d")}.csv', index=False)
    print(f"\n⚠ {len(errors)} errors logged to: scan_errors_{datetime.now().strftime('%Y%m%d')}.csv")

# ============================================================================
# Summary Statistics
# ============================================================================

print("\n" + "=" * 70)
print("SUMMARY STATISTICS")
print("=" * 70)

print(f"""
Scan Performance:
  Universe: {universe_name}
  Total stocks: {len(stock_universe)}
  Successfully scanned: {len(df)} ({len(df)/len(stock_universe)*100:.1f}%)
  From cache: {cached_count} ({cached_count/len(df)*100:.1f}%)
  Fresh fetched: {success_count} ({success_count/len(df)*100:.1f}%)
  Errors: {error_count}
  Time: {elapsed_time/60:.1f} minutes
  
Buffett Criteria Results:
  6/6 (perfect):   {len(df[df['buffett_score']==6]):>4} stocks
  5/6 (excellent): {len(df[df['buffett_score']==5]):>4} stocks
  4/6 (good):      {len(df[df['buffett_score']==4]):>4} stocks
  3/6 or less:     {len(df[df['buffett_score']<=3]):>4} stocks
  
Next Steps:
1. Review the exported CSV files
2. Research top value stocks manually
3. Select 5-10 for your portfolio
4. Update comprehensive_analysis.py with your picks
5. Monitor performance over time
""")

print("\n" + "=" * 70)
print("✓ Full market scan completed!")
print("=" * 70)

