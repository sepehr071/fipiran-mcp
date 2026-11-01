import json

import httpx
import pytest
from conftest import fixture

from fipiran_mcp import http
from fipiran_mcp.funds import _norm, _thin

pytestmark = pytest.mark.anyio


@pytest.fixture
def site(api):
    api["/services/fund/fundtype"] = fixture("fundtype.json")
    api["/services/fund/averagereturns"] = fixture("averagereturns.json")
    api["/services/fund/getfund"] = fixture("getfund.json")
    api["/services/chart/getfundchart"] = fixture("chart_nav.json")
    api["/services/chart/fundefficiencychart"] = fixture("chart_returns.json")
    api["/services/chart/getfundnetassetchart"] = fixture("chart_size.json")
    api["/services/chart/possessionchart"] = fixture("possessionchart.json")
    api["/services/chart/fundprofitschart"] = fixture("fundprofitschart.json")
    api["/services/index/marketlast"] = fixture("marketlast.json")
    api["/services/index/indexcompare"] = fixture("indexcompare.json")
    api["/services/chart/indexvaluechart"] = fixture("indexvaluechart.json")
    api["/services/chart/indexefficiencychart"] = fixture("indexefficiencychart.json")
    api["/services/instrument/instrumentcompare"] = fixture("instrumentcompare.json")
    api["/services/instrument/getindustry"] = fixture("getindustry.json")
    api["/services/instrument/getinstrument"] = fixture("getinstrument.json")
    api["/services/instrument/getefficiency"] = fixture("getefficiency.json")
    api["/services/instrument/instrumenthistory"] = fixture("instrumenthistory.json")
    api["/services/chart/industrychart"] = fixture("industrychart.json")

    def compare(request):
        mm = json.loads(request.content)["showMarketMakers"]
        return http.httpx.Response(200, json=fixture("fundcompare_mm.json" if mm else "fundcompare.json"))

    api["/services/fund/fundcompare"] = compare
    return api


async def call(client, name, args=None):
    r = await client.call_tool(name, args or {})
    assert not r.is_error, r
    return r.structured_content


async def test_all_tools_listed(client):
    names = {t.name for t in (await client.list_tools()).tools}
    assert names == {
        "fp_search_funds", "fp_fund_types", "fp_fund", "fp_history", "fp_compare", "fp_managers",
        "fp_indices", "fp_index_history", "fp_stocks", "fp_stock", "fp_industries",
    }  # fmt: skip


async def test_search_filters_and_sorts(client, site):
    r = await call(client, "fp_search_funds", {"fund_type": "equity", "sort_by": "size", "limit": 3})
    assert r["funds"] and all(f["type"] == "در سهام" for f in r["funds"])
    sizes = [f["size_bn_toman"] for f in r["funds"]]
    assert sizes == sorted(sizes, reverse=True)
    r = await call(client, "fp_search_funds", {"query": "اهرمی", "exchange_traded": True, "sort_by": "annual"})
    assert {f["name"] for f in r["funds"]} >= {"سهامی اهرمی نارنج"}
    assert all(f["exchange_traded"] for f in r["funds"])
    assert site.calls[-1].method == "POST"


async def test_search_min_age_and_unknown_type(client, site):
    r = await call(client, "fp_search_funds", {"min_age_years": 10})
    assert r["funds"] and all(f["started"] < "2017" for f in r["funds"])
    bad = await client.call_tool("fp_search_funds", {"fund_type": "nonsense"})
    assert bad.is_error


async def test_fund_types_merges_averages(client, site):
    r = await call(client, "fp_fund_types")
    equity = next(t for t in r["types"] if t["fund_type"] == 6)
    assert equity["funds"] >= 1 and equity["avg_returns_pct"]["annual"] is not None


async def test_fund_detail_uses_listed_group(client, site):
    r = await call(client, "fp_fund", {"reg_no": "12288"})
    assert r["name"] == "سهامی اهرمی نارنج" and r["investors"]["institutional"] == 19
    assert r["symbol"] and r["group_id"] == 1
    q = next(c for c in site.calls if c.url.path.endswith("/getfund")).url.params
    assert q["regno"] == "12288" and q["groupId"] == "1"


async def test_fund_unknown(client, site):
    assert (await client.call_tool("fp_fund", {"reg_no": "1"})).is_error


@pytest.mark.parametrize("series,key", [("nav", "nav"), ("returns", "annual"), ("size", "size_bn_toman")])
async def test_history(client, site, series, key):
    r = await call(client, "fp_history", {"reg_no": "12288", "series": series, "days": 30})
    assert r["series"] == series and r["from"] < r["to"] and key in r["points"][0]
    assert series != "returns" or "six_month" in r["points"][0]
    assert r["trading_days"] == 30 and r["points"][-1]["date"] == r["to"]


async def test_history_nav_change(client, site):
    r = await call(client, "fp_history", {"reg_no": "12288", "days": 50})
    assert "nav_change_pct" in r and len(r["points"]) <= 60


async def test_history_investors_dividends_flows(client, site):
    r = await call(client, "fp_history", {"reg_no": "12288", "series": "investors", "days": 5})
    assert r["points"][0].keys() >= {"institutional_pct", "retail_pct"}
    r = await call(client, "fp_history", {"reg_no": "12288", "series": "dividends"})
    assert r["points"][-1]["per_unit_rial"] == 4100.0
    r = await call(client, "fp_history", {"reg_no": "12288", "series": "size", "days": 30})
    assert "net_units_issued" in r


async def test_indices_and_history(client, site):
    r = await call(client, "fp_indices", {"query": "شاخص کل", "sort_by": "annual"})
    assert r["markets"][0]["market"] == "بورس" and r["markets"][0]["traded_value_bn_toman"] > 1000
    assert [i["name"] for i in r["indices"]] == ["شاخص کل"] and r["indices"][0]["symbols"]["total"] > 100
    h = await call(client, "fp_index_history", {"ins_code": "32097828799138957", "days": 5})
    assert h["trading_days"] == 5 and "change_pct" in h and h["points"][-1]["close"] > 0
    h = await call(client, "fp_index_history", {"ins_code": "32097828799138957", "series": "returns", "days": 3})
    assert h["name"] == "شاخص کل" and "six_month" in h["points"][0]


async def test_stocks_rank_and_filter(client, site):
    r = await call(client, "fp_stocks", {"sort_by": "change_pct", "limit": 3})
    ch = [x["change_pct"] for x in r["stocks"]]
    assert ch == sorted(ch, reverse=True) and r["as_of"]
    r = await call(client, "fp_stocks", {"industry": "بانک"})
    assert {x["symbol"] for x in r["stocks"]} == {"وبملت", "وتجارت"}
    assert (await call(client, "fp_stocks", {"market": "farabourse"}))["stocks"][0]["market"] == "farabourse"


async def test_stock_quote(client, site):
    r = await call(client, "fp_stock", {"symbol": "فولاد", "history_days": 3})
    assert r["close"] == 4240 and r["change_pct"] == 0.71 and r["returns_pct"]["quarterly"] == 26.23
    assert len(r["order_book"]) == 5 and len(r["history"]) == 3
    assert (await client.call_tool("fp_stock", {"symbol": "zzzz"})).is_error


async def test_industries(client, site):
    r = await call(client, "fp_industries", {"limit": 3})
    vals = [i["value_bn_toman"] for i in r["industries"]]
    assert vals == sorted(vals, reverse=True) and r["total_value_bn_toman"] >= vals[0]


async def test_compare_by_group(client, site):
    r = await call(client, "fp_compare", {"funds": ["12322-3", "12288"]})
    assert [f["group_id"] for f in r["funds"]] == [3, 1]
    assert (await client.call_tool("fp_compare", {"funds": ["12288"]})).is_error


async def test_managers(client, site):
    r = await call(client, "fp_managers", {"limit": 3})
    assert r["managers"] and r["managers"][0]["total_size_bn_toman"] >= r["managers"][-1]["total_size_bn_toman"]


async def test_http_error_message(client, api):
    api["/services/fund/fundtype"] = lambda request: http.httpx.Response(403, text="forbidden")
    r = await client.call_tool("fp_fund_types", {})
    assert r.is_error and "403" in r.content[0].text


def test_helpers():
    assert _norm("كارآفرين\u200c ") == _norm("کارآفرین")
    pts = _thin([{"i": i} for i in range(500)])
    assert len(pts) == 60 and pts[0]["i"] == 0 and pts[-1]["i"] == 499


async def test_headers_match_the_web_app(api):
    api["/services/x"] = {"ok": 1}
    await http.fetch("/x")
    await http.fetch("/x", body={"a": 1})
    get, post = (c.headers for c in api.calls)
    for h in (get, post):
        assert h["accept"] == "application/json, text/plain, */*" and h["referer"] == "https://fipiran.ir/"
        assert h["sec-fetch-site"] == "same-origin" and h["accept-language"].startswith("fa-IR")
    assert "origin" not in get and post["origin"] == "https://fipiran.ir"


async def test_proxy_list_rotates_after_block(api, monkeypatch):
    monkeypatch.setenv("FIPIRAN_MCP_PROXY", "http://a:1, http://b:2")
    assert http._proxies() == ["http://a:1", "http://b:2"]
    api["/services/x"] = lambda r: httpx.Response(403)
    with pytest.raises(http.ApiError):
        await http.fetch("/x")
    assert http._proxy_index == 1
