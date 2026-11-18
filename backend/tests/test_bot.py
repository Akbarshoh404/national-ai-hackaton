"""Phase 7: bot command handlers and alert fan-out (no network)."""

from app.channels import bot
from app.core import alerts
from app.core import db as dbm
from app.core.models import Alert


def test_bot_link_and_commands(client):
    assert "/link" in bot.handle_text(111, "/start")
    assert "API" in bot.handle_text(111, "/link wrong-key")
    assert "ulang" in bot.handle_text(111, "/budget")
    assert "Sergeli Avto" in bot.handle_text(111, "/link demo-sergeli-avto")
    assert "Byudjet" in bot.handle_text(111, "/budget")
    assert "AI Auditor" in bot.handle_text(111, "/audit")
    assert bot.handle_text(111, "/deals")
    assert bot.handle_text(111, "/rfqs")
    assert "ulang" in bot.handle_invoice(222, b"x")
    assert "GEMINI" in bot.handle_invoice(111, b"x")


def test_alert_push_fanout(client):
    bot.handle_text(333, "/link demo-chilonzor-phone")
    with dbm.SessionLocal() as db:
        db.query(Alert).update({Alert.sent_telegram: True})
        alerts.create(db, company_id=None, category="car", type="sourcing_deal",
                      i18n=alerts.texts("alert.deal.title", "alert.deal.title", title="Cobalt 2021", pct=20))
        alerts.create(db, company_id=None, category="phone", type="system",
                      i18n={lg: {"title": "Test", "message": "phone broadcast"} for lg in ("uz", "ru", "en")})
    pushes = bot.pending_pushes()
    chats = {(chat, text.split("\n")[0]) for _, chat, text in pushes}
    assert (111, "🔥 Cobalt 2021: bozordan 20% arzon") in chats  # sergeli trades cars
    assert (333, "Test") in chats and (111, "Test") not in chats
    assert bot.pending_pushes() == []
