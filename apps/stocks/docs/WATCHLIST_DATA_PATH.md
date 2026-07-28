# Watchlist market-data path and field contract

## Routing

`GET /api/watchlist` loads persisted symbols, calls
`hybrid_data_service.get_hybrid_batch_prices`, overlays the in-memory
extended-hours cache, seeds live-price reference closes, validates every item
with `WatchlistItem`, and serializes the list. The frontend receives the same
snake_case names through `fetchWatchlistData` and stores them unchanged in
`useWatchlist`.

| Symbol class | Selected provider | Fallback |
|---|---|---|
| SPY, QQQ, and the other configured ETFs | yfinance | Bounded stale in-process hybrid cache |
| SPCX | Finnhub first | yfinance, then bounded stale in-process cache |
| AAPL, NVDA, and ordinary equities | Finnhub first | yfinance enrichment for missing fundamentals; full yfinance fallback if Finnhub has no usable quote |

SPCX is not synthetic or manually populated anywhere in this repository. The
current yfinance response identifies it as `quoteType=EQUITY`,
`security_type=STOCK`. Its former entry in the static ETF/non-stock routing set
was stale and prevented Finnhub from being attempted.

## Collapsed-row fields

Frontend names match normalized backend names.

| Display | Finnhub source | yfinance source | Normalized/frontend field | Missing fallback |
|---|---|---|---|---|
| Ticker | requested symbol | requested symbol | `ticker` | Uppercase requested symbol |
| Company | profile `shareClassFullName` / `name` | `shortName` / `longName` | `company_name` | Ticker for a partial response; `Error` only when all providers fail |
| Current price | quote `c` | `postMarketPrice`, `currentPrice`, `regularMarketPrice` | `current_price` | `0`; frontend safely formats missing runtime values as `N/A` |
| Change % | quote `d` and `pc` | computed from current and previous close | `change_percent` | Recomputed from price/previous close; `N/A` if no valid previous close |
| After hours | none | post-market service `preMarketPrice` / `postMarketPrice` | `post_market_price` | `null`; frontend em dash |
| Market cap/AUM | profile `marketCapitalization` × 1,000,000 | stock `marketCap` / `nonDilutedMarketCap`; ETF `totalAssets` / `netAssets` | `market_cap` | `0`; frontend `N/A` and `Unknown Cap` |

Live WebSocket `price`, `change_percent`, and `previous_close` override the
collapsed REST values only when present and finite.

## Expanded-row and tooltip fields

| Group | Finnhub source | yfinance source | Normalized/frontend fields | Missing behavior |
|---|---|---|---|---|
| Classification | none on free-tier profile | `quoteType` / `assetType` | `security_type` | `UNKNOWN` |
| Profile | profile `industry`, `finnhubIndustry`, `weburl`, `exchange` | `sector`, `industry`, `longBusinessSummary`, `website`, `fullTimeEmployees`, `exchange` | `sector`, `industry`, `long_business_summary`, `website`, `full_time_employees`, `exchange` | `null`; individual blocks are hidden |
| CEO | unavailable | disabled to avoid a separate slow officers request | `ceo_name` | `null`; hidden |
| Analyst summary | unavailable | `recommendationKey`, `forwardPE` | `average_analyst_rating`, `forward_pe` | `null`; hidden |
| Session prices | quote `o`, `pc`, `l`, `h` | `open` / `regularMarketOpen`, `previousClose` / `regularMarketPreviousClose`, `dayLow`, `dayHigh` | `open_price`, `previous_close`, `day_low`, `day_high` | Required numeric fallback `0` |
| 52-week range | unavailable on free tier | `fiftyTwoWeekLow`, `fiftyTwoWeekHigh` | `fifty_two_week_low`, `fifty_two_week_high` | Required numeric fallback `0` |
| Shares | profile `shareOutstanding` × 1,000,000 and `dilutedSharesOutstanding` | `sharesOutstanding`, `impliedSharesOutstanding`, `floatShares` | `shares_outstanding`, `float_shares` | `null` for ETFs; stock section not rendered for ETFs |
| Ownership | unavailable | `heldPercentInsiders`, `heldPercentInstitutions` | `insider_percent`, `institution_percent` | `null` for ETFs; `0` remains a valid explicit value |
| Short interest | unavailable | `shortPercentOfFloat`, `sharesShort` | `short_percent_of_float`, `shares_short` | `null` for ETFs |
| Analyst targets | unavailable | `targetMeanPrice`, `targetMedianPrice`, `targetHighPrice`, `targetLowPrice`, `numberOfAnalystOpinions`, `recommendationKey` | `target_mean_price`, `target_median_price`, `target_high_price`, `target_low_price`, `number_of_analysts`, `recommendation_key` | Targets `null`; section hidden when no target exists; recommendation `N/A` |
| Risk | profile/yfinance beta plus computed inputs | `beta`, `beta3Year`, short/debt/range inputs | `beta`, `overall_risk` | Required defaults `1.0` and `5.0`; frontend method calls are guarded |
| Volume | free-tier default then yfinance enrichment | `regularMarketVolume` | `volume` | `0`; used for live quote seeding, not currently displayed |
| Source | adapter tag | adapter tag | `data_source` (`fh` or `yf`) | Selected adapter default |
| Enrichment | none | list of fields copied into Finnhub data | `yf_enriched_fields` | Empty list |

### ETF nested fields

The ETF response uses the same `WatchlistItem` envelope and adds `etf_data`.
Stock-only fields serialize as `null`.

| yfinance field | Nested backend/frontend field | Missing behavior |
|---|---|---|
| `fundFamily` | `fund_family` | Hidden |
| `expenseRatio` | `expense_ratio` | `null`; hidden |
| `totalAssets` / `netAssets` | `net_assets` | `null`; hidden |
| `fundInceptionDate` | `inception_date` | `null`; hidden |
| `dividendYield` | `dividend_yield` | `null`; hidden |
| `distributionFrequency` | `distribution_frequency` | `null`; hidden |
| `indexType` | `index_tracked` | `null`; hidden |
| `category` | `category` | `null`; hidden |
| `holdingsCount` | `holdings_count` | `null`; hidden |
| `Ticker.holdings` | `top_holdings` | `null`; subsection hidden |
| `sectorWeightings` | `sector_allocation` | `null`; subsection hidden |

yfinance 1.x percentage-point metadata is normalized to decimal fractions before
the frontend applies percentage formatting.

## Null, zero, undefined, and empty strings

- Backend normalization treats absent keys, `None`, empty strings, and
  non-finite numbers as missing.
- Optional fields remain `null`; required numeric fields use documented numeric
  defaults so one sparse symbol cannot invalidate the complete list response.
- Explicit numeric zero remains zero and is listed separately in structured
  diagnostics.
- Frontend `undefined`, `null`, and `NaN` render as `N/A` through shared
  presentation helpers. Explicit zero remains formattable as `$0.00` or `0.00`.
- Empty optional strings hide their associated expanded blocks.

## Cache behavior

The hybrid fundamentals cache is in-process memory. Fresh entries avoid a
provider call; expired entries can be used for up to
`HYBRID_STALE_CACHE_TTL_S` only after provider failure.

The yfinance SQLite cache location is separate from both PostgreSQL and the
hybrid fundamentals cache. Upstream yfinance 1.5.1 uses
`platformdirs.user_cache_dir()/py-yfinance` for `tkr-tz.db` and `cookies.db`,
creates the directory on first use, and rejects a directory that is not both
readable and writable. These SQLite files contain timezone and cookie state;
they do not persist watchlist quotes, company metadata, or market cap.

The defensive application setup now selects `YFINANCE_CACHE_DIR` when set, or
the OS temporary directory otherwise. It creates and write-tests that directory
before yfinance initialization. Setup failure is logged and does not itself
short-circuit the provider request.

Render filesystems are ephemeral by default, so a successful local cache is
rebuilt after a restart or deploy. Ephemerality alone does not imply that the
directory is unwritable or cause `unable to open database file`; that error
would additionally require a path, permission, or SQLite problem. Persistence
is not required for these caches. If a Render persistent disk is attached, a
directory under its mount path can be selected with `YFINANCE_CACHE_DIR`. See
[Render persistent disks](https://render.com/docs/disks).


## Frontend refresh preservation

Live WebSocket quotes remain in a separate `livePrices` map and affect only the
rendered price and change. The 15-second extended-hours refresh merges only the
three `post_market_*` fields. Neither path mutates `company_name`, `market_cap`,
or expanded fundamentals.

The full REST refresh previously replaced each complete `WatchlistItem`. A
sparse provider response or per-symbol error shell could therefore make prior
fundamentals disappear until another complete REST response arrived. Full
refreshes now preserve last-known metadata and positive fundamentals when the
incoming value is absent, null, an empty placeholder, or an unusable zero.
Explicit zero remains valid for percentage fields and ETF expense ratios.

## Incident status

The production watchlist recovered before this local cache change was deployed.
No supplied log excerpt contains `unable to open database file` or
`YF-Fallback`, and the excerpts do not include a full `/api/watchlist` request
for the affected window. The production incident is therefore transient and
currently non-reproducible; the root cause is not confirmed.
