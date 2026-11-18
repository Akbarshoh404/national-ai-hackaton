"""Local model (Ollama) as the first extractor — all mocked, no real Ollama is contacted."""

import json
from datetime import timedelta

import httpx
import pytest

from app.core import db as dbm
from app.core import llm
from app.core.config import settings
from app.core.db import utcnow
from app.core.models import Listing, RawPost
from app.data_pipeline import extractor
from app.data_pipeline.telegram_ingest import save_post

LABEL = "local:qwen2.5:3b"


class FakeOllama:
    """Stands in for `httpx.post` / `httpx.get` inside app.core.llm."""

    def __init__(self, answers):
        self.answers = list(answers)  # dict → JSON reply, str → raw content, Exception → raised
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        assert url.endswith("/api/chat") and json["stream"] is False and json["format"] == "json"
        assert json["options"] == {"temperature": 0, "num_ctx": 2048}
        ans = self.answers.pop(0) if self.answers else {"skip": True, "skip_reason": "test"}
        if isinstance(ans, Exception):
            raise ans
        content = ans if isinstance(ans, str) else _json(ans)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def _json(obj):
    return json.dumps(obj, ensure_ascii=False)


@pytest.fixture()
def ollama(monkeypatch):
    monkeypatch.setattr(settings, "EXTRACT_PROVIDER_ORDER", "local,gemini,rules")
    monkeypatch.setattr(llm, "_local_down_until", 0.0)
    monkeypatch.setattr(llm, "available", lambda: False)  # no Gemini unless a test enables it

    def install(*answers):
        fake = FakeOllama(answers)
        monkeypatch.setattr(llm.httpx, "post", fake.post)
        return fake

    return install


def _posts(*texts, source="localshop", start=1000):
    with dbm.SessionLocal() as db:
        ids = [save_post(db, source, start + i, utcnow() - timedelta(minutes=5), t).id for i, t in enumerate(texts)]
    return ids


def _listing(db, raw_id):
    return db.query(Listing).filter(Listing.raw_post_id == raw_id).one_or_none()


IPHONE = {"skip": False, "category": "phone", "brand": "Apple", "model": "iPhone 13", "condition": "A",
          "price": 5200000, "currency": "UZS", "district": "Chilonzor", "attrs": {"storage_gb": 128}}


def test_local_success_one_post_per_call(client, ollama):
    fake = ollama(IPHONE, {**IPHONE, "model": "iPhone 14", "price": 6300000})
    ids = _posts("iPhone 13 128gb ideal 5.2 mln so'm Chilonzor", "iPhone 14 128gb A holat 6.3 mln so'm", start=1000)
    with dbm.SessionLocal() as db:
        stats = extractor.process_batch(db, [db.get(RawPost, i) for i in ids])
        assert stats["created"] == 2 and len(fake.calls) == 2, "one Ollama call per post"
        first = _listing(db, ids[0])
        assert first.attrs["_extracted_by"] == LABEL and first.price_uzs == 5_200_000
        msgs = fake.calls[0]["messages"]
        assert msgs[0]["role"] == "system" and "ONE post" in msgs[0]["content"]
        assert len(msgs) == 1 + 6 * 2 + 1, "system + 6 few-shot pairs + the post"
        assert "sotib olaman" in msgs[11]["content"].lower() and '"skip":true' in msgs[12]["content"]


def test_invalid_json_falls_through_to_gemini(client, ollama, monkeypatch):
    ollama("this is not json {", {"category": "phone", "price": "five million"})  # bad JSON, then schema failure
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: [dict(IPHONE, i=i) for i in
                                                                    range(prompt.count('"text"'))])
    ids = _posts("iPhone 13 128gb 5.2 mln so'm", "iPhone 13 128gb ideal 5.2 mln so'm", start=1100)
    with dbm.SessionLocal() as db:
        extractor.process_batch(db, [db.get(RawPost, i) for i in ids])
        assert {_listing(db, i).attrs["_extracted_by"] for i in ids} == {"gemini"}


def test_timeout_falls_through_to_rules(client, ollama):
    fake = ollama(httpx.ReadTimeout("slow"))
    ids = _posts("Gentra 2020 probeg 70 000 km, metan, narxi 12 300$", source="localcars", start=1200)
    with dbm.SessionLocal() as db:
        extractor.process_batch(db, [db.get(RawPost, ids[0])])
        lst = _listing(db, ids[0])
        assert lst.attrs["_extracted_by"] == "rules" and lst.model == "Gentra" and len(fake.calls) == 1
    assert not llm.local_suspended(), "a timeout is per-post, not an outage"


def test_ollama_down_skips_local_for_the_batch(client, ollama):
    fake = ollama(httpx.ConnectError("refused"), IPHONE, IPHONE)
    ids = _posts("Redmi Note 12 128gb narxi 1.9 mln so'm", "Redmi Note 12 64gb narxi 1.7 mln so'm",
                 "Redmi Note 12 128gb yangi narxi 2 mln so'm", start=1300)
    with dbm.SessionLocal() as db:
        extractor.process_batch(db, [db.get(RawPost, i) for i in ids])
        assert len(fake.calls) == 1, "after a connection failure the rest of the batch skips Ollama"
        assert all((_listing(db, i) is None) or _listing(db, i).attrs["_extracted_by"] == "rules" for i in ids)
        assert all(db.get(RawPost, i).processed != extractor.FAILED for i in ids)
    assert llm.local_suspended(), "Ollama cools down after a connection failure"


def test_price_mismatch_uses_rule_price(client, ollama, caplog):
    ollama({**IPHONE, "price": 5800000})  # text says 5.2 mln → >1% apart
    ids = _posts("iPhone 13 128gb ideal holatda narxi 5.2 mln so'm", start=1400)
    with caplog.at_level("WARNING", logger="raft.extractor"), dbm.SessionLocal() as db:
        extractor.process_batch(db, [db.get(RawPost, ids[0])])
        assert _listing(db, ids[0]).price_uzs == 5_200_000
    assert "price mismatch" in caplog.text


def test_price_within_one_percent_keeps_model_price():
    item = {**IPHONE, "price": 5_230_000}
    assert extractor.check_price(item, "iPhone 13 narxi 5.2 mln so'm", "local")["price"] == 5_230_000
    usd = {**IPHONE, "price": 410, "currency": "USD"}
    assert extractor.check_price(usd, "iPhone 13 narxi 450$", "local")["price"] == 450
    assert extractor.check_price({"skip": True}, "narxi 5 mln", "local") == {"skip": True}


def test_input_parse_uses_provider_order(client, chilonzor, ollama):
    ollama({"skip": False, "category": "car", "brand": "Chevrolet", "model": "Cobalt", "condition": "used",
            "price": 11800, "currency": "USD", "attrs": {"year": 2021, "mileage_km": 45000, "trim": 4}})
    r = client.post("/api/v1/input/parse", headers=chilonzor, json={"text": "cobalt 2021 45 ming probeg pozitsiya 4"})
    out = r.json()
    assert r.status_code == 200 and out["source"] == "llm" and out["brand"] == "Chevrolet"
    assert out["price"] is None, "no price in the text → none from the model either"


def test_copilot_never_calls_local(client, chilonzor, ollama):
    fake = ollama()
    client.post("/api/v1/advisor/chat", headers=chilonzor, json={"question": "100 mln kredit 24 oyga"})
    client.get("/api/v1/books/audit", headers=chilonzor)
    assert fake.calls == []


def test_health_and_model_card(client, monkeypatch):
    monkeypatch.setattr(settings, "EXTRACT_PROVIDER_ORDER", "local,gemini,rules")
    monkeypatch.setattr(llm, "local_status", lambda cache_s=30.0: (False, "Ollama not reachable (test)"))
    h = client.get("/api/v1/health").json()
    assert h["local_model"]["status"] == "error" and "not reachable" in h["local_model"]["detail"]
    assert h["status"] in ("ok", "degraded")
    m = client.get("/api/v1/model").json()
    assert m["model"] == "qwen2.5:3b" and m["provider"] == LABEL
    assert m["provider_order"] == ["local", "gemini", "rules"] and m["local_reachable"] is False
    if m["listings"]:
        assert abs(sum(m["share"].values()) - 1) < 0.01 and sum(m["counts"].values()) == m["listings"]
    monkeypatch.setattr(settings, "EXTRACT_PROVIDER_ORDER", "gemini,rules")
    assert client.get("/api/v1/health").json()["local_model"]["status"] == "disabled"


def test_reextract_reports_changes(client, ollama):
    ollama({**IPHONE, "condition": "B"})
    ids = _posts("iPhone 13 128gb ideal 5.2 mln so'm Chilonzor", start=1500)
    with dbm.SessionLocal() as db:
        extractor.process_batch(db, [db.get(RawPost, ids[0])])  # stored with condition B
    ollama({**IPHONE, "condition": "C", "district": None})
    with dbm.SessionLocal() as db:
        r = extractor.reextract(db, "local", 1)
    assert r["compared"] == 1 and r["posts"][0]["raw_post_id"] == ids[0]
    assert {"condition", "district"} <= set(r["posts"][0]["changed"])
    with dbm.SessionLocal() as db:
        assert _listing(db, ids[0]).condition == "B", "reextract never writes"


@pytest.mark.parametrize("text,category,expected", [
    # patterns from real shop posts that the first regex parser got wrong
    ("📱 12 Pro 💾 128GB 🔋 70% 💰 225$ 📦 ❌ Bosh tolov 79$ 6 oyga 35$", "phone", (225, "USD")),  # installments
    ("#Pro13 128GB Narxi: 420$ Nasiya: Bosh tolov: 147$ 3 oy: 112$ dan", "phone", (420, "USD")),
    ("Депозит: 2000 у.е. • Цена: 3500 у.е", "rent", (3500, "USD")),  # deposit listed before the price
    ("💵 Narxi: 4 mln 600 ming so'm", "laptop", (4_600_000, "UZS")),  # compound amount
    ("💵 Нархи: 5 mln 600 ming so'm", "laptop", (5_600_000, "UZS")),
    ("Galaxy A54 $260 ideal", "phone", (260, "USD")),  # "A54" is part of the model name
    ("Ijara 2 xona 450$ oyiga", "rent", (450, "USD")),  # "oyiga" after a currency is still a price
    ("Tanishingizdan arzon! 8GB 512GB", "laptop", None),
])
def test_price_parser_real_world_patterns(text, category, expected):
    assert extractor.parse_price(text, category) == expected


def test_long_posts_keep_head_and_tail():
    post = "MacBook Air M2 8/256 " + "zo'r holatda, " * 80 + "💵 Narxi: 9 mln 500 ming so'm"
    clipped = extractor.clip_post(post)
    assert len(clipped) <= extractor.LOCAL_MAX_POST_CHARS and clipped.startswith("MacBook Air M2")
    assert clipped.endswith("Narxi: 9 mln 500 ming so'm") and " … " in clipped
