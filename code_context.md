- We use React for the frontend and Python/FastAPI for the backend. 
- Use https://github.com/KailunHong8/quant as github repo.
- Generate Functional Spec based on the product_note.md with the contraints of this code_context.md
- Always update the documentations (markdown files) in the github repo to reflect the latest changes in the codebase and product requirements.

## FMP API Reference

FMP (Financial Modeling Prep) is our primary market data source. All endpoints use the `/stable/` base URL.
- **Base URL**: `https://financialmodelingprep.com/stable`
- **Authentication**: All requests require `apikey` parameter
- **Docs**: https://site.financialmodelingprep.com/developer/docs/

### Available Endpoints

**Company Name Search** - Find stock symbols by company name:
```
GET /stable/search-name?query=apple&apikey=YOUR_API_KEY
```
Use this to look up tradable companies across global exchanges. Returns list of matching symbols.

**Stock Quotes** - Get real-time stock prices:
```
GET /stable/quote?symbol=AAPL&apikey=YOUR_API_KEY
```
Returns latest prices, volume, price changes. Ideal for trading apps and dashboards.

**Company Profile** - Get detailed company information:
```
GET /stable/profile?symbol=AAPL&apikey=YOUR_API_KEY
```
Includes market cap, sector, CEO, description, and current stock price in one call.

**Income Statement** - Fetch financial statements:
```
GET /stable/income-statement?symbol=AAPL&apikey=YOUR_API_KEY
```
Real-time income statements to analyze revenue, net income, and cost trends.

**Historical Prices** - Get OHLCV data:
```
GET /stable/historical-price-eod/full?symbol=AAPL&from=YYYY-MM-DD&to=YYYY-MM-DD&apikey=YOUR_API_KEY
```
Returns historical price data for backtesting and simulations.

### Free Tier Limitations
- Some endpoints may return 402/403 errors on free tier
- Rate limits apply (typically 250 requests/day)
- Consider Yahoo Finance as fallback for restricted endpoints