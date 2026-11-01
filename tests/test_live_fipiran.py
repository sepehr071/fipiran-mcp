import pytest

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def call(client, name, args=None):
    r = await client.call_tool(name, args or {})
    assert not r.is_error, r
    return r.structured_content


async def test_live_search_and_fund(client):
    r = await call(client, "fp_search_funds", {"fund_type": "equity", "sort_by": "size", "limit": 5})
    assert r["matched"] > 50 and len(r["funds"]) == 5
    top = r["funds"][0]
    f = await call(client, "fp_fund", {"reg_no": top["reg_no"], "group_id": top["group_id"]})
    assert f["name"] == top["name"] and f["nav_rial"] > 0


async def test_live_types_and_managers(client):
    t = await call(client, "fp_fund_types")
    assert any(x["fund_type"] == 4 and x["funds"] > 50 for x in t["types"])
    m = await call(client, "fp_managers", {"limit": 3})
    assert len(m["managers"]) == 3


async def test_live_history_and_compare(client):
    hits = (await call(client, "fp_search_funds", {"fund_type": "gold", "min_age_years": 2, "limit": 2}))["funds"]
    h = await call(client, "fp_history", {"reg_no": hits[0]["reg_no"], "group_id": hits[0]["group_id"], "days": 120})
    assert h["trading_days"] == 120 and len(h["points"]) <= 60
    c = await call(client, "fp_compare", {"funds": [f"{x['reg_no']}-{x['group_id']}" for x in hits]})
    assert len(c["funds"]) == 2


async def test_live_market(client):
    r = await call(client, "fp_indices", {"query": "شاخص کل", "limit": 3})
    assert r["markets"][0]["index"] > 100000 and r["indices"]
    h = await call(client, "fp_index_history", {"ins_code": r["indices"][0]["ins_code"], "days": 20})
    assert h["trading_days"] == 20
    s = await call(client, "fp_stocks", {"sort_by": "value", "limit": 3})
    assert s["matched"] > 300
    q = await call(client, "fp_stock", {"symbol": s["stocks"][0]["symbol"]})
    assert q["close"] > 0 and len(q["order_book"]) == 5
    assert (await call(client, "fp_industries", {"limit": 3}))["industries"]
    assert (await call(client, "fp_history", {"reg_no": "10851", "series": "investors", "days": 5}))["points"]
