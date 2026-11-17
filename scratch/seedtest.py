import os, time
os.environ["DATABASE_URL"]="sqlite:///./_tmp_seed.db"
os.environ["AUTO_MIGRATE"]="false"
from app import db, seed
db.drop_all(); db.create_all()
t=time.time(); print(seed.run(reset=False)); print("seed s", time.time()-t)
from app.services import pricing
with db.SessionLocal() as s:
    for kw in [dict(category="phone", model="iPhone 13", condition="A", attrs={"storage_gb":128}),
               dict(category="laptop", model="MacBook Air M1", condition="A", attrs={"ram_gb":8,"ssd_gb":256}),
               dict(category="car", model="Cobalt", attrs={"year":2021,"mileage_km":50000,"fuel":"benzin"}),
               dict(category="house", district="Yunusobod", attrs={"rooms":3,"area_m2":85,"building":"novostroyka"}),
               dict(category="rent", district="Chilonzor", attrs={"rooms":2,"furnished":True})]:
        t=time.time(); e=pricing.estimate(s, **kw)
        print(kw["category"], e.fair_price_usd, e.range_uzs, e.comparables, e.confidence, e.basis, round((time.time()-t)*1000,1),"ms", e.price_by_seller_type)
