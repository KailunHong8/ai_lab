"""
Warren Buffett Style Value Investing Screener with ArcticDB

Based on the FMP + ArcticDB tutorial for screening undervalued stocks.

Requirements:
- pip install arcticdb requests
- FMP API key: export FMP_API_KEY="your_key_here"
  Sign up at: https://financialmodelingprep.com/

Buffett's Criteria:
- Low debt (D/E < 0.5)
- Good liquidity (Current Ratio 1.5-2.5)
- Undervalued (P/B < 1.5)
- Strong returns (ROE > 8%, ROA > 6%)
- Can service debt (Interest Coverage > 5)
"""

import io
import os
import time
import requests
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# PART 1: Setup ArcticDB Connection
# ============================================================================
print("=" * 70)
print("Warren Buffett Style Value Screener")
print("=" * 70)

try:
    import arcticdb as adb
    
    # Connect to ArcticDB (local LMDB storage)
    arctic = adb.Arctic("lmdb://fundamentals")
    lib = arctic.get_library("financial_ratios", create_if_missing=True)
    
    print("✓ ArcticDB connected successfully")
    print(f"  Storage: lmdb://fundamentals")
    print(f"  Library: financial_ratios")
    
except ImportError:
    print("✗ ArcticDB not installed")
    print("  Install with: pip install arcticdb")
    print("\nExiting...")
    exit(1)

# ============================================================================
# PART 2: FMP API Helper Functions
# ============================================================================

def build_fmp_url(request, period, year):
    """Build Financial Modeling Prep API URL"""
    apikey = os.environ.get("FMP_API_KEY")
    if not apikey:
        raise ValueError("FMP_API_KEY environment variable not set")
    return f"https://financialmodelingprep.com/api/v4/{request}?year={year}&period={period}&apikey={apikey}"

def get_fmp_data(request, period, year):
    """Fetch data from FMP and convert to DataFrame"""
    url = build_fmp_url(request, period, year)
    try:
        print(f"  Fetching {year} data...", end=" ")
        response = requests.get(url)
        response.raise_for_status()
        csv = response.content.decode("utf-8")
        df = pd.read_csv(io.StringIO(csv), parse_dates=True)
        print(f"✓ ({len(df):,} rows)")
        return df
    except requests.RequestException as e:
        print(f"✗ Error: {e}")
        return pd.DataFrame()
    except KeyError:
        print("✗ Error: Invalid API key or quota exceeded")
        return pd.DataFrame()

# ============================================================================
# PART 3: Download and Store Financial Ratios
# ============================================================================

# Check if API key is set
if not os.environ.get("FMP_API_KEY"):
    print("\n" + "=" * 70)
    print("⚠ FMP API Key Not Found")
    print("=" * 70)
    print("""
To use this screener:

1. Sign up at: https://financialmodelingprep.com/
   (Check for student/developer discounts)

2. Get your API key from the dashboard

3. Set environment variable:
   export FMP_API_KEY="your_key_here"
   
   Or add to your .bashrc/.zshrc:
   echo 'export FMP_API_KEY="your_key_here"' >> ~/.bashrc

4. Re-run this script

For now, showing example queries with mock data...
""")
    USE_MOCK_DATA = True
else:
    USE_MOCK_DATA = False
    
    print("\n" + "=" * 70)
    print("PART 1: Download Financial Ratios from FMP")
    print("=" * 70)
    
    # Download data for multiple years
    years = [2022, 2023, 2024]
    
    for year in years:
        # Check if already stored
        adb_sym = f"financial_ratios/{year}"
        
        if lib.has_symbol(adb_sym):
            print(f"\n{year}: Already stored in ArcticDB (skipping download)")
            continue
        
        print(f"\n{year}:")
        ratios = get_fmp_data("ratios-bulk", "quarter", year)
        
        if not ratios.empty:
            # Store in ArcticDB
            lib.write(adb_sym, ratios)
            print(f"  ✓ Stored in ArcticDB: {adb_sym}")
            
            # Rate limiting (respect API limits)
            if year != years[-1]:
                print("  Waiting 3 seconds (API rate limit)...")
                time.sleep(3)
        else:
            print(f"  ✗ Failed to fetch data for {year}")

# ============================================================================
# PART 4: Query and Filter Value Stocks
# ============================================================================

def filter_by_year(year, lib):
    """
    Filter stocks using Warren Buffett's value investing criteria
    
    Criteria:
    - Debt/Equity < 0.5 (low leverage)
    - Current Ratio 1.5-2.5 (balanced liquidity)
    - Price/Book < 1.5 (undervalued)
    - ROE > 8% (profitable)
    - ROA > 6% (efficient)
    - Interest Coverage > 5 (can service debt)
    """
    
    # Columns to return
    cols = [
        "symbol",
        "period",
        "date",
        "debtEquityRatio",
        "currentRatio",
        "priceToBookRatio",
        "returnOnEquity",
        "returnOnAssets",
        "interestCoverage"
    ]
    
    # Build ArcticDB query
    q = adb.QueryBuilder()
    filter_condition = (
        (q["debtEquityRatio"] < 0.5)
        & (q["currentRatio"] > 1.5) & (q["currentRatio"] < 2.5)
        & (q["priceToBookRatio"] < 1.5)
        & (q["returnOnEquity"] > 0.08)
        & (q["returnOnAssets"] > 0.06)
        & (q["interestCoverage"] > 5)
    )
    q = q[filter_condition]
    
    # Query ArcticDB
    adb_sym = f"financial_ratios/{year}"
    
    if not lib.has_symbol(adb_sym):
        print(f"  ✗ No data for {year} in ArcticDB")
        return pd.DataFrame()
    
    try:
        result = lib.read(adb_sym, query_builder=q)
        df = result.data[cols].set_index("symbol")
        return df
    except Exception as e:
        print(f"  ✗ Error querying: {e}")
        return pd.DataFrame()

print("\n" + "=" * 70)
print("PART 2: Screen for Value Stocks (Buffett Criteria)")
print("=" * 70)

if USE_MOCK_DATA:
    print("\n⚠ Using example output (no API key)")
    print("""
Example results for 2024 Q3:

Symbol  | D/E   | CR   | P/B  | ROE   | ROA   | Int Cov
--------|-------|------|------|-------|-------|--------
AAPL    | 0.35  | 1.8  | 1.2  | 12%   | 8%    | 8.5
MSFT    | 0.28  | 2.1  | 1.4  | 15%   | 9%    | 12.0
JNJ     | 0.42  | 1.6  | 1.1  | 9%    | 7%    | 6.2

These companies pass Buffett's screen:
- Low debt (safer)
- Good liquidity (can meet obligations)
- Trading below book value (undervalued)
- Strong profitability (ROE, ROA)
- Can easily pay interest
""")
else:
    # Query each year
    for year in [2022, 2023, 2024]:
        print(f"\n{year} Results:")
        print("-" * 70)
        
        results = filter_by_year(year, lib)
        
        if results.empty:
            print("  No stocks passed the screening criteria")
        else:
            print(f"  Found {len(results)} stocks passing Buffett criteria:")
            print()
            
            # Show top 10 by ROE
            top_results = results.nlargest(10, 'returnOnEquity')
            
            # Format and display
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', None)
            pd.set_option('display.float_format', '{:.2f}'.format)
            
            print(top_results.to_string())
            
            # Export to CSV
            csv_filename = f"value_stocks_{year}.csv"
            results.to_csv(csv_filename)
            print(f"\n  ✓ Exported to: {csv_filename}")

# ============================================================================
# PART 5: Visualize Results (if matplotlib available)
# ============================================================================

print("\n" + "=" * 70)
print("PART 3: Visualization & Analysis")
print("=" * 70)

if not USE_MOCK_DATA:
    try:
        import matplotlib.pyplot as plt
        
        # Get latest year data
        latest_year = 2024
        results = filter_by_year(latest_year, lib)
        
        if not results.empty and len(results) > 5:
            # Create scatter plot: P/B vs ROE
            fig, ax = plt.subplots(figsize=(10, 6))
            
            scatter = ax.scatter(
                results['priceToBookRatio'],
                results['returnOnEquity'],
                s=100,
                alpha=0.6,
                c=results['returnOnAssets'],
                cmap='viridis'
            )
            
            ax.set_xlabel('Price-to-Book Ratio')
            ax.set_ylabel('Return on Equity (ROE)')
            ax.set_title(f'Value Stocks: P/B vs ROE ({latest_year})')
            ax.grid(True, alpha=0.3)
            
            # Add colorbar
            cbar = plt.colorbar(scatter, ax=ax)
            cbar.set_label('Return on Assets (ROA)')
            
            # Annotate top 5 stocks
            top5 = results.nlargest(5, 'returnOnEquity')
            for idx, row in top5.iterrows():
                ax.annotate(
                    idx,
                    (row['priceToBookRatio'], row['returnOnEquity']),
                    xytext=(5, 5),
                    textcoords='offset points',
                    fontsize=8
                )
            
            plt.tight_layout()
            plot_file = f'value_stocks_scatter_{latest_year}.png'
            plt.savefig(plot_file, dpi=150)
            print(f"✓ Scatter plot saved: {plot_file}")
            
            # Create bar chart: Top 10 by ROE
            fig, ax = plt.subplots(figsize=(12, 6))
            
            top10 = results.nlargest(10, 'returnOnEquity')
            ax.barh(range(len(top10)), top10['returnOnEquity'].values)
            ax.set_yticks(range(len(top10)))
            ax.set_yticklabels(top10.index)
            ax.set_xlabel('Return on Equity (ROE)')
            ax.set_title(f'Top 10 Value Stocks by ROE ({latest_year})')
            ax.grid(True, alpha=0.3, axis='x')
            
            plt.tight_layout()
            bar_file = f'value_stocks_roe_{latest_year}.png'
            plt.savefig(bar_file, dpi=150)
            print(f"✓ Bar chart saved: {bar_file}")
            
        else:
            print("  Not enough data for visualization")
            
    except ImportError:
        print("  matplotlib not installed (visualization skipped)")
        print("  Install with: pip install matplotlib")
    except Exception as e:
        print(f"  Visualization error: {e}")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 70)
print("SUMMARY & Next Steps")
print("=" * 70)

print("""
✓ Value Investing Screener Setup Complete

Buffett's Criteria Applied:
  1. Debt/Equity < 0.5       → Low leverage (financial safety)
  2. Current Ratio 1.5-2.5   → Balanced liquidity
  3. Price/Book < 1.5        → Undervalued
  4. ROE > 8%                → Strong profitability
  5. ROA > 6%                → Efficient asset use
  6. Interest Coverage > 5   → Can service debt

Next Steps:
  1. Refine criteria based on your risk tolerance
  2. Add more ratios: P/E, dividend yield, debt/EBITDA
  3. Compare results across multiple years
  4. Backtest: How did 2022 picks perform in 2024?
  5. Combine with technical analysis for entry timing

Advanced Features to Add:
  - Sector filtering (avoid cyclicals in recession)
  - Quality scoring (combine multiple metrics)
  - Momentum overlay (pick value stocks trending up)
  - Insider buying signals
  - Analyst estimate revisions

Remember:
  "Price is what you pay, value is what you get." - Warren Buffett
  
  This screener finds potentially undervalued stocks, but always:
  - Read the financial statements
  - Understand the business model
  - Consider competitive advantages (moat)
  - Think long-term (5+ years)
""")

print("\n" + "=" * 70)
print("✓ Screener completed!")
print("=" * 70)

