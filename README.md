<!-- mcp-name: io.github.sepehr071/fipiran-mcp -->

# fipiran-mcp: Fipiran (فیپیران) Iranian mutual fund and ETF data MCP server for AI agents

**fipiran-mcp is an unofficial, read-only MCP server that gives AI agents the public fund data of Fipiran (مرکز پردازش اطلاعات مالی ایران, fipiran.ir).**<br>
Its 11 tools search and rank Iranian mutual funds and ETFs (صندوق‌های سرمایه‌گذاری) by type, manager, size and return,<br>
show one fund in full, return daily NAV, return, size, flow and investor-mix history, compare funds, rank fund managers, and cover the bourse: market overview, indices, stock quotes and industries.
No API key or account is needed. It works in Claude, Cursor, Copilot and any other MCP client.

[![PyPI](https://img.shields.io/pypi/v/fipiran-mcp?color=2563eb)](https://pypi.org/project/fipiran-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/fipiran-mcp/blob/main/LICENSE)

## For AI agents

- **What:** unofficial MCP server for fipiran.ir fund pages: search and ranking of about 500 Iranian mutual funds and ETFs, fund details, daily NAV / rolling-return / size history, side-by-side comparison, fund types with average returns, fund management companies.
- **Install:** `uvx fipiran-mcp` or `claude mcp add fipiran -- uvx fipiran-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none. Optional `FIPIRAN_MCP_PROXY` (HTTP proxy URL); system proxy settings are ignored.
- **Network:** fipiran.ir answers **Iranian internet lines only**. Outside Iran, set `FIPIRAN_MCP_PROXY` to an Iranian proxy.
- **Access:** read-only, no confirmation needed. Login-only Fipiran features (ranking reports, watchlists, exports) are not included.
- **Tools:** 11, all prefixed `fp_`: `fp_search_funds`, `fp_fund_types`, `fp_fund`, `fp_history`, `fp_compare`, `fp_managers`, `fp_indices`, `fp_index_history`, `fp_stocks`, `fp_stock`, `fp_industries`. Typical sequence: `fp_search_funds` -> `fp_fund` / `fp_history` / `fp_compare`.
- **Use when:** the user asks which Iranian funds returned most, the biggest gold or fixed-income funds, the NAV or price history of a fund, how a fund compares with its type average, or who manages a fund.
- **Output:** compact JSON. Returns are percent per period (not annualised); sizes billion Toman; NAV rial per unit. Names are Persian.

## Tools

| Tool | What it does |
|---|---|
| `fp_search_funds` | Find and rank funds by name, ticker, type, manager, size, age and return (daily to since-start). |
| `fp_fund_types` | Fund types with fund count, total size, average returns and average asset allocation. |
| `fp_fund` | One fund in full: NAV, returns, size, allocation, investors, manager, auditor, custodian, website; optional past date. |
| `fp_history` | Daily NAV, rolling returns, net assets and unit flows, institutional/retail mix or dividends of one fund (up to 60 evenly spaced points). |
| `fp_compare` | 2 to 8 funds side by side. |
| `fp_managers` | Fund management companies by assets under management. |
| `fp_indices` | Tehran and Farabourse market overview plus the 65 market and industry indices ranked by return. |
| `fp_index_history` | Daily value (with low and high) or rolling returns of one index. |
| `fp_stocks` | Search and rank listed shares of the last trading day: gainers, losers, most traded, by industry or market. |
| `fp_stock` | One share in full: quote, range, 5-level order book, retail vs institutional, period returns, optional OHLC history. |
| `fp_industries` | Industries ranked by traded value, volume and trades on the last day. |

## Quick start

```bash
uvx fipiran-mcp
```

Claude Desktop / Cursor config:

```json
{ "mcpServers": { "fipiran": { "command": "uvx", "args": ["fipiran-mcp"] } } }
```

## FAQ

**Is it official?** No. It reads the same public JSON the fipiran.ir fund pages load; it is not affiliated with Fipiran.<br>
**Is this investment advice?** No. It is data. Past returns do not predict future returns; very young funds show distorted annual returns.<br>
**Why does it fail outside Iran?** The site does not answer foreign IPs. Use `FIPIRAN_MCP_PROXY`.

---

*Author: Sepehr Radmard (سپهر رادمرد), [github.com/sepehr071](https://github.com/sepehr071), [linkedin.com/in/sepehr-radmard](https://linkedin.com/in/sepehr-radmard). MIT license.*
