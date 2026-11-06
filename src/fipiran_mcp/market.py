"""Market tools: Tehran/Farabourse overview, indices, stocks, industries (the site's symbol and index pages)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from pydantic import Field

from .funds import _bn, _day, _norm
from .http import ApiError, fetch
from .registry import tool

MARKETS = {1: "bourse", 2: "farabourse", 4: "farabourse_base"}  # marketCode, as the symbol page labels them
MAX_POINTS = 60
STOCK_QUERY = {  # what the site's symbol page sends; pageSize 2000 returns every share in one call
    "pageIndex": 1, "pageSize": 2000, "sort": "desc", "column": "transactionValue", "markettype": "",
    "symboltype": "300,303,309", "symbolstatus": "", "industry": "", "subIndustry": "", "symbol": "", "idxCode": "",
    "company": "",
}  # fmt: skip
StockSort = Literal["change_pct", "value", "volume", "trades", "price"]
STOCK_SORTS = {"change_pct": "change_pct", "value": "value", "volume": "volume", "trades": "trades", "price": "close"}


def _pct(a: Any, b: Any) -> float | None:
    return round((a / b - 1) * 100, 2) if a and b else None


def _thin(rows: list[dict]) -> list[dict]:
    """At most MAX_POINTS rows, evenly spaced, always keeping the first and the last."""
    if len(rows) <= MAX_POINTS:
        return rows
    step = (len(rows) - 1) / (MAX_POINTS - 1)
    return [rows[round(i * step)] for i in range(MAX_POINTS)]


async def _industries() -> dict[str, str]:
    """Industry group code (trimmed) -> Persian name."""
    return {x["industryGroupCode"].strip(): x["title"] for x in await fetch("/instrument/getindustry")}


async def _stocks() -> list[dict]:
    """Every listed share with today's trading, joined from the site's instrumentcompare answer."""
    r, names = await asyncio.gather(fetch("/instrument/instrumentcompare", dict(STOCK_QUERY)), _industries())
    r = r.get("items") or [{}]
    deals = {t["insCode"]: t for t in r[0].get("instrumentTransactions", [])}
    last = max((t["transactionDate"] for t in deals.values()), default="")
    out = []
    for i in r[0].get("instruments", []):
        t = deals.get(i["insCode"])
        if not t or t["transactionDate"] != last:  # never traded, or a stale row from an old day
            continue
        out.append({
            "ins_code": i["insCode"],
            "symbol": i["smallSymbolName"],
            "name": i["symbolFullName"],
            "industry_code": i["industryGroupCode"].strip(),
            "industry": names.get(i["industryGroupCode"].strip(), i["industryGroupCode"].strip()),
            "market": MARKETS.get(i["marketCode"], i["marketCode"]),
            "close": t["closingPrice"],
            "last": t["lastTransaction"],
            "yesterday": t["priceYesterday"],
            "change_pct": _pct(t["closingPrice"], t["priceYesterday"]),
            "last_change_pct": _pct(t["lastTransaction"], t["priceYesterday"]),
            "low": t["priceMin"],
            "high": t["priceMax"],
            "volume": t["numberOfVolume"],
            "trades": t["numberOfTransactions"],
            "value_bn_toman": _bn(t["transactionValue"]),
            "date": _day(t["transactionDate"]),
        })  # fmt: skip
    return out


async def _resolve_stock(query: str) -> dict:
    """One listed share by exact ticker, then by name substring; raises with candidates when unclear."""
    q = _norm(query)
    rows = await _stocks()
    exact = [x for x in rows if _norm(x["symbol"]) == q or x["ins_code"] == query.strip()]
    hits = exact or [x for x in rows if q in _norm(x["symbol"]) + _norm(x["name"])]
    if len(hits) == 1 or exact:
        return hits[0]
    if not hits:
        raise ApiError(f"No traded share matches {query!r}. Try the exact ticker or use fp_stocks(query=...).")
    shown = "; ".join(f"{x['symbol']} ({x['name']})" for x in hits[:8])
    raise ApiError(f"{len(hits)} shares match {query!r}: {shown}. Use the exact ticker.")


@tool("Market overview and indices")
async def fp_indices(
    query: Annotated[str | None, Field(description="Part of index name, Persian, e.g. 'شاخص کل', 'بانک'.")] = None,
    sort_by: Annotated[
        Literal["annual", "six_month", "quarterly", "monthly", "weekly", "daily", "value"],
        Field(description="Ranking column; returns in percent."),
    ] = "daily",
    limit: Annotated[int, Field(ge=1, le=70, description="Indices to return.")] = 15,
) -> dict:
    """Show the Tehran and Farabourse market summary and rank the 65 market and industry indices by return.

    Each index has an ins_code for fp_index_history. The first block is the market overview.
    """
    markets, r = await asyncio.gather(fetch("/index/marketlast"), fetch("/index/indexcompare"))
    q = _norm(query)
    key = {"value": "lastValueDay"}.get(sort_by, f"{sort_by}Efficiency")
    rows = [x for x in r.get("items", []) if (not q or q in _norm(x["title"])) and x.get(key) is not None]
    rows.sort(key=lambda x: x[key], reverse=True)
    return {
        "markets": [
            {
                "market": m["typeTitle"],
                "index": m["indexLastValue"] or None,
                "index_change_pct": m["indexChange"],
                "equal_weight_index": m["indexEqualWeightedLastValue"] or None,
                "equal_weight_change_pct": m["indexEqualWeightedChange"] if m["indexEqualWeightedLastValue"] else None,
                "traded_value_bn_toman": _bn(m["marketActivityQTotCap"]),
                "trades": m["marketActivityZTotTran"],
                "market_cap_bn_toman": _bn(m["marketValue"]) or None,
                "open_now": m["isOpen"],
                "data_time": m["lastDataDate"][:16],
            }
            for m in markets
        ],  # fmt: skip
        "matched": len(rows),
        "sorted_by": sort_by,
        "indices": [
            {
                "ins_code": x["insCode"],
                "name": x["title"],
                "date": _day(x["date"]),
                "value": x["lastValueDay"],
                "day_low": x["minimumValueDayIndex"],
                "day_high": x["maximumValueDayIndex"],
                "returns_pct": {
                    p: x.get(f"{p.replace('_m', 'M')}Efficiency")
                    for p in ("daily", "weekly", "monthly", "quarterly", "six_month", "annual")
                },
                "symbols": {
                    "total": x["totalNumberSymbols"],
                    "up": x["numberSymbolsIncreased"],
                    "down": x["reducedNumberSymbols"],
                    "suspended": x["numberSuspendedSymbols"],
                },
            }
            for x in rows[:limit]
        ],  # fmt: skip
    }


@tool("Index history")
async def fp_index_history(
    ins_code: Annotated[str, Field(description="ins_code from fp_indices, e.g. '32097828799138957' (total index).")],
    series: Annotated[
        Literal["value", "returns"],
        Field(description="value: daily close, low, high. returns: six rolling returns (percent)."),
    ] = "value",
    days: Annotated[int, Field(ge=1, le=4000, description="Latest trading days (about 250 per year).")] = 90,
) -> dict:
    """Get the daily history of one market or industry index, oldest first, at most 60 evenly spaced points.

    Use after fp_indices. The value series also has the change over the window.
    """
    params = {"insCodes" if series == "returns" else "insCode": ins_code.strip(), "showAll": str(days > 360).lower()}
    rows = await fetch(f"/chart/index{'efficiency' if series == 'returns' else 'value'}chart", params)
    name = None
    if series == "returns":  # answer is [{insCode, title, items}]
        name, rows = (rows[0]["title"], rows[0]["items"]) if rows else (None, [])
    rows = list(reversed(rows[:days]))
    if not rows:
        raise ApiError(f"No history for index {ins_code!r}. Get a valid ins_code from fp_indices.")
    pts = []
    for r in _thin(rows):
        if series == "value":
            pts.append({"date": _day(r["date"]), "close": r["indexValue"], "low": r["leastIndexTheDayValue"],
                        "high": r["mostIndexTheDayValue"]})  # fmt: skip
        else:
            pts.append({"date": _day(r["date"])} | {
                k: r[f"{f}Efficiency"]
                for k, f in (("daily", "daily"), ("weekly", "weekly"), ("monthly", "monthly"),
                             ("quarterly", "quarterly"), ("six_month", "sixMonth"), ("annual", "annual"))
            })  # fmt: skip
    out: dict[str, Any] = {"ins_code": ins_code, "name": name, "series": series, "from": pts[0]["date"],
                           "to": pts[-1]["date"], "trading_days": len(rows), "points": pts}  # fmt: skip
    if series == "value" and rows[0]["indexValue"]:
        out["change_pct"] = _pct(rows[-1]["indexValue"], rows[0]["indexValue"])
    return out


@tool("Search and rank stocks")
async def fp_stocks(
    query: Annotated[str | None, Field(description="Part of ticker or company name, Persian, e.g. 'فولاد'.")] = None,
    industry: Annotated[
        str | None,
        Field(description="Industry name or code, e.g. 'بانک', '27'. fp_industries lists them."),
    ] = None,
    market: Annotated[
        Literal["bourse", "farabourse", "farabourse_base"] | None,
        Field(description="Tehran Stock Exchange, Iran Farabourse, or Farabourse base market."),
    ] = None,
    sort_by: Annotated[
        StockSort,
        Field(description="change_pct: today's gain. value: traded value."),
    ] = "value",
    ascending: Annotated[bool, Field(description="True lists the lowest first.")] = False,
    limit: Annotated[int, Field(ge=1, le=50, description="Rows to return.")] = 15,
) -> dict:
    """Search and rank listed shares traded on the last trading day: top gainers, losers, most traded, by industry.

    Pass a row's symbol to fp_stock. Prices are rial, value is billion Toman. Untraded shares are left out.
    """
    rows = await _stocks()
    q, ind = _norm(query), _norm(industry)
    out = [
        x for x in rows
        if (not q or q in _norm(x["symbol"]) + _norm(x["name"]))
        and (not ind or ind in _norm(x["industry"]) or ind == _norm(x["industry_code"]))
        and (market is None or x["market"] == market)
    ]  # fmt: skip
    key = {"value": "value_bn_toman", "volume": "volume", "trades": "trades", "price": "close"}.get(sort_by, sort_by)
    out = [x for x in out if x.get(key) is not None]
    out.sort(key=lambda x: x[key], reverse=not ascending)
    slim = ("ins_code", "symbol", "name", "industry", "market", "close", "change_pct", "volume", "value_bn_toman")
    return {
        "as_of": rows[0]["date"] if rows else None,
        "matched": len(out),
        "sorted_by": sort_by,
        "stocks": [{k: x[k] for k in slim} for x in out[:limit]],
    }


@tool("Stock quote")
async def fp_stock(
    symbol: Annotated[str, Field(description="Ticker, Persian (e.g. 'فولاد'), or ins_code.")],
    history_days: Annotated[
        int, Field(ge=0, le=250, description="Latest trading days of OHLC rows to add (0 none).")
    ] = 0,
) -> dict:
    """Get one listed share in full: last trade, range, order book, buyers and sellers, period returns, industry.

    Prices are rial. Order book and retail vs institutional counts are the last published. history_days adds OHLC rows, newest first.
    """
    base = await _resolve_stock(symbol)
    code = base["ins_code"]
    d = (await fetch("/instrument/getinstrument", {"insCode": code})).get("item") or []
    if not d:
        raise ApiError(f"Fipiran has no quote for {symbol!r}.")
    d = d[0]
    tx = d["instrumentTransaction"]
    # Like the site's profile page: adjusted closing price against the adjusted price N days ago. (The chart endpoint
    # disagrees for quarterly and six-month.)
    past = await fetch("/instrument/getefficiency", {"insCode": code, "date": tx["transactionDate"][:10]})
    adj = tx.get("adjPriceBackward")
    ago = {**past, "daily": tx.get("priceYesterdayBackward")}
    ct = (d.get("instrumentClientTypes") or [{}])[0]
    out: dict[str, Any] = {
        **{k: base[k] for k in ("ins_code", "symbol", "name", "industry", "market")},
        "industry_sub": d["instrument"].get("industrySubName"),
        "date": base["date"],
        "close": base["close"], "last": base["last"], "yesterday": base["yesterday"],
        "change_pct": base["change_pct"], "last_change_pct": base["last_change_pct"],
        "low": base["low"], "high": base["high"], "open": d["instrumentTransaction"].get("priceFirst"),
        "volume": base["volume"], "trades": base["trades"], "value_bn_toman": base["value_bn_toman"],
        "returns_pct": {
            k: _pct(adj, ago.get(k if k == "daily" else f"{k.replace('_m', 'M')}Efficiency"))
            for k in ("daily", "weekly", "monthly", "quarterly", "six_month", "annual")
        },
        "order_book": [
            {"bid_price": b["demandPrice"], "bid_volume": b["demandVolume"], "bid_orders": b["numberRequests"],
             "ask_price": b["supplyPrice"], "ask_volume": b["supplyVolume"], "ask_orders": b["numberSupply"]}
            for b in d.get("instrument5BestLimits", [])
        ],
        "retail_vs_institutional": {
            "retail_buyers": ct.get("numberIndividualsBuyers"), "retail_sellers": ct.get("numberIndividualsSellers"),
            "institutional_buyers": ct.get("numberNonIndividualBuyers"),
            "institutional_sellers": ct.get("numberNonIndividualSellers"),
            "retail_buy_volume": ct.get("sumIndividualBuyVolume"), "retail_sell_volume": ct.get("sumIndividualSellVolume"),
            "institutional_buy_volume": ct.get("sumNonIndividualBuyVolume"),
            "institutional_sell_volume": ct.get("sumNonIndividualSellVolume"),
        },
    }  # fmt: skip
    if history_days:
        h = await fetch("/instrument/instrumenthistory", {"insCode": code, "pageSize": history_days, "pageIndex": 0})
        out["history"] = [
            {"date": _day(r["transactionDate"]), "open": r["priceFirst"], "high": r["priceMax"], "low": r["priceMin"],
             "close": r["closingPrice"], "volume": r["numberOfVolume"], "value_bn_toman": _bn(r["transactionValue"])}
            for r in h.get("items", [])[:history_days]
        ]  # fmt: skip
    return out


@tool("Industry trading")
async def fp_industries(
    sort_by: Annotated[
        Literal["value", "volume", "trades"], Field(description="value, volume or trade count.")
    ] = "value",
    limit: Annotated[int, Field(ge=1, le=60, description="Industries to return.")] = 20,
) -> dict:
    """Rank the stock-market industries by trading on the last day: traded value, volume, number of trades.

    Use the name in fp_stocks(industry=...) for its shares, or fp_indices(query=...) for its index.
    """
    rows = await fetch("/chart/industrychart")
    key = {"value": "transactionValue", "volume": "numberOfVolume", "trades": "numberOfTransactions"}[sort_by]
    total = sum(r["transactionValue"] or 0 for r in rows)
    rows.sort(key=lambda r: r[key] or 0, reverse=True)
    return {
        "total_value_bn_toman": _bn(total),
        "industries": [
            {"code": r["industryGroupCode"].strip(), "name": r["title"], "value_bn_toman": _bn(r["transactionValue"]),
             "share_pct": round(100 * r["transactionValue"] / total, 1) if total else None,
             "volume": r["numberOfVolume"], "trades": r["numberOfTransactions"]}
            for r in rows[:limit]
        ],
    }  # fmt: skip
