"""Fund tools: search and rank, one fund, price/return/size history, comparison, fund types, managers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import Field

from .http import ApiError, fetch
from .registry import tool

RIAL_PER_BN_TOMAN = 10**10  # sizes come in rial; 1 billion Toman = 10 billion rial
TYPE_ALIASES = {  # English words an agent is likely to use -> fund type id
    "fixed_income": 4, "fixed income": 4, "gold": 5, "commodity": 5, "equity": 6, "stock": 6, "stocks": 6,
    "mixed": 7, "market_maker": 11, "market maker": 11, "venture": 12, "real_estate": 18, "sector": 21,
    "leveraged": 22, "index": 23, "guaranteed": 24, "pension": 25,
}  # fmt: skip
SORTS = {
    "daily": "dailyEfficiency", "weekly": "weeklyEfficiency", "monthly": "monthlyEfficiency",
    "quarterly": "quarterlyEfficiency", "six_month": "sixMonthEfficiency", "annual": "annualEfficiency",
    "since_start": "efficiency", "size": "netAsset", "units": "investedUnits",
}  # fmt: skip
SortBy = Literal["daily", "weekly", "monthly", "quarterly", "six_month", "annual", "since_start", "size", "units"]
MAX_POINTS = 60


def _norm(s: Any) -> str:
    """Lowercase, Arabic letters to Persian, no spaces or ZWNJ: so 'كارآفرین' matches 'کارآفرین'."""
    t = str(s or "").translate(str.maketrans("يك", "یک"))
    return "".join(t.replace("\u200c", "").split()).lower()


def _bn(rial: Any) -> float | None:
    return round(rial / RIAL_PER_BN_TOMAN, 2) if isinstance(rial, int | float) else None


def _size(x: dict) -> Any:
    return x.get("netAsset", x.get("fundSize"))


def _day(s: str | None) -> str | None:
    return s[:10] if s else None


async def _types() -> dict[int, str]:
    r = await fetch("/fund/fundtype")
    return {t["fundType"]: t["name"] for t in r.get("items", [])}


async def _funds(market_makers: bool = False) -> list[dict]:
    """Every fund row (the site's list). Market makers (type 11) are a separate, larger list."""
    r = await fetch("/fund/fundcompare", body={"regNos": [], "showMarketMakers": market_makers})
    return r.get("items", [])


def _row(x: dict, types: dict[int, str]) -> dict:
    return {
        "reg_no": x["regNo"],
        "group_id": x["groupId"],
        "name": x["name"],
        "symbol": x.get("smallSymbolName"),
        "type": types.get(x.get("fundType"), x.get("fundType")),
        "exchange_traded": x.get("typeOfInvest") == "Negotiable",
        "size_bn_toman": _bn(_size(x)),
        "nav_rial": x.get("statisticalNav"),
        "returns_pct": {
            "daily": x.get("dailyEfficiency"),
            "weekly": x.get("weeklyEfficiency"),
            "monthly": x.get("monthlyEfficiency"),
            "quarterly": x.get("quarterlyEfficiency"),
            "six_month": x.get("sixMonthEfficiency"),
            "annual": x.get("annualEfficiency"),
            "since_start": x.get("efficiency"),
        },
        "manager": x.get("manager"),
        "started": _day(x.get("initiationDate")),
        "data_date": _day(x.get("date")),
    }


async def _resolve_type(value: str | int | None, types: dict[int, str]) -> int | None:
    if value is None or value == "":
        return None
    v = str(value).strip().lower()
    if v.isdigit() and int(v) in types:
        return int(v)
    if v in TYPE_ALIASES:
        return TYPE_ALIASES[v]
    hits = [i for i, n in types.items() if _norm(v) in _norm(n)]
    if len(hits) == 1:
        return hits[0]
    names = "; ".join(f"{i} {n}" for i, n in types.items())
    raise ApiError(f"Unknown or ambiguous fund_type {value!r}. Use an id or a name from: {names}")


async def _find(reg_no: str, group_id: int | None) -> dict:
    """The list row of one fund. Asks the site for just that fund, so the 1.9 MB market-maker list is never loaded."""
    reg = str(reg_no).strip()
    for mm in (False, True):
        for grp in (1, 0) if group_id is None else (group_id,):
            body = {"regNos": [{"regNo": reg, "groupId": grp}], "showMarketMakers": mm}
            rows = [x for x in (await fetch("/fund/fundcompare", body=body)).get("items", []) if x["regNo"] == reg]
            if group_id is not None:
                rows = [x for x in rows if x["groupId"] == group_id]
            if rows:
                return rows[0]
    raise ApiError(f"No fund with reg_no {reg_no!r}. Find it with fp_search_funds first.")


@tool("Search and rank funds")
async def fp_search_funds(
    query: Annotated[
        str | None, Field(description="Part of the fund name, ticker or manager, Persian (e.g. 'کیان', 'طلا', 'آگاه').")
    ] = None,
    fund_type: Annotated[
        str | None,
        Field(
            description="Type id or name: 4 fixed income (درآمد ثابت), 5 gold/commodity, 6 equity (سهام), 7 mixed (مختلط), 21 sector, 22 leveraged, 23 index, 25 pension... English words work too: fixed_income, gold, equity, mixed. fp_fund_types lists all."
        ),
    ] = None,
    exchange_traded: Annotated[
        bool | None,
        Field(
            description="True: only funds traded on the exchange like shares (ETFs, with a ticker). False: only funds you buy and redeem at NAV. Omit for both."
        ),
    ] = None,
    manager: Annotated[str | None, Field(description="Part of the fund manager's name, e.g. 'آگاه'.")] = None,
    min_size_bn_toman: Annotated[
        float | None, Field(description="Only funds at least this big, in billion Toman.")
    ] = None,
    min_age_years: Annotated[
        float | None,
        Field(description="Only funds older than this; use it so 'annual' returns are not from a young fund."),
    ] = None,
    sort_by: Annotated[SortBy, Field(description="Ranking column; returns are percent over that period.")] = "annual",
    ascending: Annotated[bool, Field(description="True lists the lowest first.")] = False,
    include_market_makers: Annotated[
        bool, Field(description="Also list market-maker funds (type 11, over 1000 series, rarely wanted).")
    ] = False,
    limit: Annotated[int, Field(ge=1, le=50, description="Rows to return.")] = 15,
) -> dict:
    """Search Iranian mutual funds and ETFs by name, type or manager, and rank them by return or size.

    Use for "best fixed income funds this year", "biggest gold funds", "funds managed by X". Each row has reg_no and
    group_id: pass them to fp_fund, fp_history or fp_compare. Returns are percent; size is billion Toman.
    """
    types = await _types()
    ftype = await _resolve_type(fund_type, types)
    rows = await _funds(include_market_makers)
    q, m = _norm(query), _norm(manager)
    cutoff = (date.today() - timedelta(days=round(365.25 * min_age_years))).isoformat() if min_age_years else None
    out = []
    for x in rows:
        if ftype is not None and x.get("fundType") != ftype:
            continue
        if exchange_traded is not None and (x.get("typeOfInvest") == "Negotiable") != exchange_traded:
            continue
        if q and q not in _norm(x["name"]) + _norm(x.get("smallSymbolName")) + _norm(x.get("manager")):
            continue
        if m and m not in _norm(x.get("manager")):
            continue
        size = _size(x)
        if min_size_bn_toman and (size or 0) < min_size_bn_toman * RIAL_PER_BN_TOMAN:
            continue
        if cutoff and (_day(x.get("initiationDate")) or "9") > cutoff:
            continue
        out.append(x)
    field = SORTS[sort_by]
    have = [x for x in out if (_size(x) if field == "netAsset" else x.get(field)) is not None]
    have.sort(key=lambda x: _size(x) if field == "netAsset" else x[field], reverse=not ascending)
    return {"matched": len(out), "sorted_by": sort_by, "funds": [_row(x, types) for x in have[:limit]]}


@tool("Fund types and averages")
async def fp_fund_types() -> dict:
    """List fund types (equity, fixed income, gold, mixed...) with fund counts, total size and average returns.

    Use first to learn the type ids for fp_search_funds, or for "how are equity funds doing vs fixed income".
    Returns are the average percent for the type; allocation is the average share of stock/bond/cash/deposit.
    """
    types, avgs, funds = await _types(), await fetch("/fund/averagereturns"), await _funds()
    count: dict[int, int] = {}
    for x in funds:
        count[x["fundType"]] = count.get(x["fundType"], 0) + 1
    by_type = {a["fundTypeId"]: a for a in avgs}
    out = []
    for i, name in types.items():
        a = by_type.get(i, {})
        if not count.get(i) and not a:
            continue
        out.append({
            "fund_type": i,
            "name": name,
            "funds": count.get(i, 0),
            "total_size_bn_toman": _bn(a.get("netAsset")),
            "avg_returns_pct": {
                "daily": a.get("dailyEfficiency"), "weekly": a.get("weeklyEfficiency"),
                "monthly": a.get("monthlyEfficiency"), "quarterly": a.get("quarterlyEfficiency"),
                "six_month": a.get("sixMonthEfficiency"), "annual": a.get("annualEfficiency"),
            },
            "avg_allocation_pct": {k: a.get(k) for k in ("stock", "bond", "cash", "deposit")},
        })  # fmt: skip
    return {"types": out, "note": "Market-maker funds (type 11) are not counted in `funds`."}


@tool("Fund details")
async def fp_fund(
    reg_no: Annotated[str, Field(description="Fund registration number from fp_search_funds, e.g. '12288'.")],
    group_id: Annotated[
        int | None, Field(description="Series number from the search row; leave empty for the fund's first series.")
    ] = None,
    on_date: Annotated[str | None, Field(description="YYYY-MM-DD to see the fund as of an earlier day.")] = None,
) -> dict:
    """Get one fund in full: NAV, returns, size, allocation, investors, manager, auditor, custodian, website.

    Use after fp_search_funds. For a price series use fp_history; to put several side by side use fp_compare.
    """
    base = await _find(reg_no, group_id)
    params: dict[str, Any] = {"regno": base["regNo"], "groupId": base["groupId"]}
    if on_date:
        params["date"] = on_date
    r = await fetch("/fund/getfund", params)
    x = r.get("item")
    if not x:
        raise ApiError(f"Fipiran has no data for fund {reg_no} on {on_date or 'the latest day'}.")
    types = await _types()
    out = _row(x, types)
    out.update({
        "symbol": base.get("smallSymbolName"),  # getfund omits it
        "group_id": base["groupId"],  # getfund with a date answers group 0
        "issue_nav_rial": x.get("issueNav"),
        "redeem_nav_rial": x.get("cancelNav"),
        "units": x.get("investedUnits"),
        "allocation_pct": {k: x.get(k) for k in ("stock", "bond", "cash", "deposit", "other")},
        "top5_holdings_pct": x.get("fiveBest"),
        "investors": {"institutional": x.get("insInvNo"), "retail": x.get("retInvNo")},
        "units_issued_today": x.get("unitsSubDAY"),
        "units_redeemed_today": x.get("unitsRedDAY"),
        "dividend_every_months": x.get("dividendIntervalPeriod") or None,
        "investment_managers": x.get("investmentManager"),
        "auditor": x.get("auditor"),
        "custodian": x.get("custodian"),
        "guarantor": None if x.get("guarantor") == "----" else x.get("guarantor"),
        "websites": x.get("websiteAddress"),
        "registered": _day(x.get("registerDate")),
        "group_name": x.get("groupName"),
    })  # fmt: skip
    return out


def _thin(rows: list[dict]) -> list[dict]:
    """At most MAX_POINTS rows, evenly spaced, always keeping the first and the last."""
    if len(rows) <= MAX_POINTS:
        return rows
    step = (len(rows) - 1) / (MAX_POINTS - 1)
    return [rows[round(i * step)] for i in range(MAX_POINTS)]


@tool("Fund history")
async def fp_history(
    reg_no: Annotated[str, Field(description="Fund registration number from fp_search_funds.")],
    series: Annotated[
        Literal["nav", "returns", "size", "investors", "dividends"],
        Field(
            description="nav: price per unit (issue/redeem/statistical NAV, rial). returns: the six rolling returns (percent). size: net assets (billion Toman) and units issued/redeemed per day (flows). investors: share of units held by institutions and by retail investors (percent). dividends: payouts per unit (rial), all of them."
        ),
    ] = "nav",
    days: Annotated[
        int, Field(ge=1, le=4000, description="How many latest trading days to cover (about 250 per year).")
    ] = 90,
    group_id: Annotated[
        int | None, Field(description="Series number from the search row; leave empty for the first series.")
    ] = None,
) -> dict:
    """Get a fund's daily history: NAV, returns, size and flows, investor mix or dividends, at most 60 points.

    Use for "how did this fund move in the last 6 months" or "are investors putting money in". Oldest first. The
    result also has the NAV change over the window (nav) or the net units issued minus redeemed (size).
    """
    base = await _find(reg_no, group_id)
    path = {
        "nav": "/chart/getfundchart",
        "returns": "/chart/fundefficiencychart",
        "size": "/chart/getfundnetassetchart",
        "investors": "/chart/possessionchart",
        "dividends": "/chart/fundprofitschart",
    }[series]
    rows = await fetch(
        path,
        {
            "regno": base["regNo"],
            "groupId": base["groupId"],
            "showAll": str(days > 360 or series == "dividends").lower(),
        },
    )
    rows = list(reversed(rows if series == "dividends" else rows[:days]))
    if not rows:
        raise ApiError(
            f"Fipiran has no {series} history for fund {reg_no} series {base['groupId']} "
            "(funds with several series, group_id 2 and up, only have fund-level numbers in fp_fund)."
        )
    pts = []
    for r in _thin(rows):
        p: dict[str, Any] = {"date": _day(r.get("date"))}
        if series == "nav":
            p |= {"nav": r["statisticalNav"], "issue": r["issueNav"], "redeem": r["cancelNav"]}
        elif series == "returns":
            p |= {
                k: r[f"{f}Efficiency"]
                for k, f in (
                    ("daily", "daily"),
                    ("weekly", "weekly"),
                    ("monthly", "monthly"),
                    ("quarterly", "quarterly"),
                    ("six_month", "sixMonth"),
                    ("annual", "annual"),
                )
            }
        elif series == "investors":
            p |= {"institutional_pct": r.get("insInvPercent"), "retail_pct": r.get("retInvPercent")}
        elif series == "dividends":
            p = {"date": _day(r["profitDate"]), "per_unit_rial": r["profitValue"]}
        else:
            p |= {
                "size_bn_toman": _bn(r["netAsset"]),
                "units_issued": r["unitsSubDAY"],
                "units_redeemed": r["unitsRedDAY"],
            }
        pts.append(p)
    out: dict[str, Any] = {"reg_no": base["regNo"], "group_id": base["groupId"], "name": base["name"], "series": series,
                           "from": pts[0]["date"], "to": pts[-1]["date"], "trading_days": len(rows), "points": pts}  # fmt: skip
    if series == "nav" and rows[0]["statisticalNav"]:
        out["nav_change_pct"] = round((rows[-1]["statisticalNav"] / rows[0]["statisticalNav"] - 1) * 100, 2)
    if series == "size":
        out["net_units_issued"] = sum((r["unitsSubDAY"] or 0) - (r["unitsRedDAY"] or 0) for r in rows)
    return out


@tool("Compare funds")
async def fp_compare(
    funds: Annotated[
        list[str],
        Field(
            min_length=2,
            max_length=8,
            description="2 to 8 funds as 'regNo' or 'regNo-groupId', e.g. ['12288-1', '11695'].",
        ),
    ],
) -> dict:
    """Put 2 to 8 funds side by side: type, size, NAV, returns for every period, allocation, manager.

    Use after fp_search_funds when the user is choosing between funds. Ids are the reg_no (and group_id) of search rows.
    """
    types = await _types()
    out = []
    for f in funds:
        reg, _, grp = f.strip().partition("-")
        x = await _find(reg, int(grp) if grp.isdigit() else None)
        row = _row(x, types)
        row["allocation_pct"] = {k: x.get(k) for k in ("stock", "bond", "cash", "deposit", "other")}
        row["dividend_every_months"] = x.get("dividendIntervalPeriod") or None
        out.append(row)
    return {"funds": out}


@tool("Fund managers")
async def fp_managers(
    query: Annotated[str | None, Field(description="Part of a manager's name to filter, e.g. 'کارگزاری'.")] = None,
    limit: Annotated[int, Field(ge=1, le=40, description="Managers to return.")] = 15,
) -> dict:
    """Rank fund management companies by total assets under management, with their fund count and typical return.

    Use for "which companies run the most funds". Pass a manager name from here to fp_search_funds(manager=...).
    avg_annual_return_pct only covers that manager's funds older than one year.
    """
    year_ago = (datetime.now() - timedelta(days=365)).date().isoformat()
    groups: dict[str, list[dict]] = {}
    for x in await _funds():
        groups.setdefault(x.get("manager") or "unknown", []).append(x)
    q = _norm(query)
    out = []
    for name, fs in groups.items():
        if q and q not in _norm(name):
            continue
        ann = [
            f["annualEfficiency"]
            for f in fs
            if f.get("annualEfficiency") is not None and (_day(f.get("initiationDate")) or "9") <= year_ago
        ]
        out.append({
            "manager": name,
            "funds": len(fs),
            "total_size_bn_toman": _bn(sum(_size(f) or 0 for f in fs)),
            "avg_annual_return_pct": round(sum(ann) / len(ann), 2) if ann else None,
        })  # fmt: skip
    out.sort(key=lambda m: m["total_size_bn_toman"] or 0, reverse=True)
    return {"matched": len(out), "managers": out[:limit]}
