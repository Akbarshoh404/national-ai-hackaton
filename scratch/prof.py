import os, time, cProfile, pstats
os.environ["DATABASE_URL"]="sqlite:///./_tmp_seed.db"
from app import db, seed
db.drop_all(); db.create_all(); seed.run(reset=False)
from app.services import pricing
with db.SessionLocal() as s:
    pricing.load_frame(s,"phone")
    t=time.time()
    for i in range(50):
        pricing.invalidate()  # force recompute but keep frame? measure raw estimate
        pricing.load_frame(s,"phone")
    print("load ms", (time.time()-t)/50*1000)
    df=pricing.load_frame(s,"phone")
    t=time.time()
    for i in range(50):
        pricing._estimate(s,"phone","iPhone 13","A",None,{"storage_gb":128},brand=None,exclude_id=i,lang="en")
    print("estimate ms", (time.time()-t)/50*1000)
    cProfile.run('for i in range(20): pricing._estimate(s,"phone","iPhone 13","A",None,{"storage_gb":128},brand=None,exclude_id=i,lang="en")','/tmp/p.out')
pstats.Stats('/tmp/p.out').sort_stats('cumtime').print_stats(12)
