"""Research validation for accessories: category matching and no clothing size."""

from datetime import datetime, timezone

from app.contracts import Preferences, SizePref
from app.research.urlsafety import UrlCheck
from app.research.verify import verify_submission


def ok_url(u):
    host = u.split("/")[2]
    return UrlCheck(True, "", u, host)


def test_watch_job_rejects_watch_bands_and_ignores_clothing_size():
    now = datetime.now(timezone.utc)
    raw = [
        {"retailer": "Shop", "productUrl": "https://shop.example/w", "title": "Silver-tone automatic watch",
         "matchType": "similar", "availability": "in_stock", "sizesAvailable": ["One size"], "observedAt": now.isoformat()},
        {"retailer": "Shop", "productUrl": "https://shop.example/b", "title": "Apple Watch Band 41mm",
         "matchType": "similar", "observedAt": now.isoformat()},
    ]
    products, rejected, _ = verify_submission(raw, job_id="rsj_x", prefs=Preferences(size=SizePref(raw="M")), mode="fixture",
                                              job_created_at=now, url_checker=ok_url, category="watch")
    assert [p.title for p in products] == ["Silver-tone automatic watch"]
    assert any("not a watch" in r.reason for r in rejected)
    assert all(c.constraint != "size" for c in products[0].constraint_checks)
