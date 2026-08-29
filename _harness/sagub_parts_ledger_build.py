# -*- coding: utf-8 -*-
"""협력사 사급부품 수불장 재구성 하네스 (2026-01~, 검증용·미커밋).
   모델: (사급부품 자도번 × 협력사)
     입고(+, 보낸것) = PU_T_STOCK_MAINT tag='5'(협력업체판매=사급출고), 부품만(stop_set), abs(qty)
     출고(−, 소진)   = 세트입고(nx.set_input_req 입고완료) 완제품 × sagub_parts_soyo(통일 소요엔진)
     잔량 = Σ입고 − Σ출고  (기초 0 @ 2026-01-01)
   ★소요는 반드시 엔진(§10). ad-hoc BOM 전개 금지.
   실행: python _harness/sagub_parts_ledger_build.py
"""
import sys, io, time
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_sagub/PNC_ERP_Web/backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common  # _harness sys.path 추가
import nx_soyo_engine as soyo
from nx_cost_engine import NxCostEngine
import pyodbc, db_client

def live_cur():
    cs=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    return pyodbc.connect(cs, autocommit=True).cursor()

START = "260101"
eng = NxCostEngine()
cur = eng.cur                       # nx (PARTNER_ERP_TEST3)
lcur = live_cur()                   # live (PU_T_STOCK_MAINT tag5)

def f(x):
    try: return float(x or 0)
    except: return 0.0

t0=time.time()
# ── 용접 소재(용접봉 RAC · 용접링/은납 BCUP · 이름 '용접') = 별도 트랙 → 제외 ──
cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.item
    WHERE item_code LIKE 'RAC%' OR item_code LIKE 'BCUP%' OR item_name LIKE '%용접%'""")
weld_excl = set(r[0].strip() for r in cur.fetchall())
print(f"[제외] 용접 소재(용접봉·용접링·은납) {len(weld_excl)}종")

# ── stop_set = 사급부품 universe (v_pr_bom SAGUB_FLAG='1' distinct child) ──
cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(MAT_CODE))) FROM nx.v_pr_bom WHERE SAGUB_FLAG='1' AND ISNULL(MAT_CODE,'')<>''")
stop_set = set(r[0].strip() for r in cur.fetchall())
print(f"[stop_set] 사급부품 {len(stop_set)}종(용접 포함) → 소진에서 용접 제외")

# ── 입고(+) = 사급출고 tag5 (부품만, Jan~) per (cust, part) ──
lcur.execute("""SELECT UPPER(LTRIM(RTRIM(CUST_CODE))), UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(CAST(MAINT_QTY AS float))
    FROM PU_T_STOCK_MAINT WITH(NOLOCK)
    WHERE MAINT_TAG='5' AND MAINT_YMD>=? GROUP BY CUST_CODE, MAT_CODE""", START)
inp = {}    # (cust,part) -> +qty(보낸것)
in_all=0; in_part=0
for c,m,q in lcur.fetchall():
    if not c or not m: continue
    in_all += 1
    if m in stop_set and m not in weld_excl:
        inp[(c,m)] = inp.get((c,m),0.0) + abs(f(q))   # 불출 음수 → 보유 +
        in_part += 1
print(f"[입고] tag5 (cust,part) {in_all}쌍 중 부품 {in_part}쌍 · Σ보낸 {sum(inp.values()):,.0f}")

# ── 출고(−) = 세트입고 완제품 × sagub_parts_soyo (레거시 live 실소스, nx 세트입고는 시드=미사용) ──
soyo.warm_vpr(eng)
lcur.execute("""SELECT UPPER(LTRIM(RTRIM(CUST_CODE))), UPPER(LTRIM(RTRIM(ITEM_CODE))), SUM(CAST(MAINT_QTY AS float))
    FROM PU_T_SET_STOCK_MAINT WITH(NOLOCK) WHERE MAINT_YMD>=? AND ISNULL(ITEM_CODE,'')<>''
    GROUP BY CUST_CODE, ITEM_CODE""", START)
setrows = [(r[0].strip(), r[1].strip(), f(r[2])) for r in lcur.fetchall() if r[0] and r[1]]
print(f"[세트입고] (협력사,완제품) {len(setrows)}쌍 · Σ완성 {sum(x[2] for x in setrows):,.0f}")
memo={}
out = {}    # (cust,part) -> 소진
miss_soyo=0
for c, it, qty in setrows:
    pmap = soyo.sagub_parts_soyo(eng, it, stop_set, memo)
    if not pmap: miss_soyo += 1
    for part, per in pmap.items():
        if part in weld_excl: continue          # 용접 소재는 별도 트랙
        out[(c,part)] = out.get((c,part),0.0) + per*qty
print(f"[출고] 소진 (cust,part) {len(out)}쌍 · Σ소진 {sum(out.values()):,.0f} · 소요0완제품 {miss_soyo}")

# ── 넷팅 per (cust, part) ──
keys = set(inp)|set(out)
led = []
for k in keys:
    i=inp.get(k,0.0); o=out.get(k,0.0); led.append((k[0],k[1],i,o,i-o))
neg = [x for x in led if x[4] < -0.5]
print(f"\n[전체 수불장] (협력사×사급부품) {len(led)}행 · 잔량<0 {len(neg)}행")
print(f"  Σ보낸 {sum(x[2] for x in led):,.0f} · Σ소진 {sum(x[3] for x in led):,.0f} · Σ잔량 {sum(x[4] for x in led):,.0f}")

# ── 스코프 A: 우리가 실제 보낸 부품만(tag5 자도번 universe) ──
our_parts = {m for (c,m) in inp}
ledA = [x for x in led if x[1] in our_parts]
negA = [x for x in ledA if x[4] < -0.5]
print(f"\n[스코프A: 우리가 보낸 부품({len(our_parts)}종)으로 한정] {len(ledA)}행 · 잔량<0 {len(negA)}행")
print(f"  Σ보낸 {sum(x[2] for x in ledA):,.0f} · Σ소진 {sum(x[3] for x in ledA):,.0f} · Σ잔량 {sum(x[4] for x in ledA):,.0f}")

# ── 스코프 B: 우리가 보낸 (협력사,부품) 조합만 ──
ledB = [x for x in led if (x[0],x[1]) in inp]
negB = [x for x in ledB if x[4] < -0.5]
print(f"[스코프B: 우리가 보낸 (협력사,부품) 조합만] {len(ledB)}행 · 잔량<0 {len(negB)}행")
print(f"  Σ보낸 {sum(x[2] for x in ledB):,.0f} · Σ소진 {sum(x[3] for x in ledB):,.0f} · Σ잔량 {sum(x[4] for x in ledB):,.0f}")

# 협력사별 요약 TOP
from collections import defaultdict
by=defaultdict(lambda:[0.0,0.0,0.0])
for c,m,i,o,b in led:
    by[c][0]+=i; by[c][1]+=o; by[c][2]+=b
cur.execute("SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM nx.CM_M_CUST")
nm={r[0].strip():str(r[1]).strip() for r in cur.fetchall() if r[0]}
print("\n[협력사별] 보낸 / 소진 / 잔량 (Σ보낸 상위 12)")
for c in sorted(by, key=lambda k:-by[k][0])[:12]:
    i,o,b=by[c]; print(f"  {c:6s} {nm.get(c,'')[:14]:14s} 보낸{i:12,.0f} 소진{o:12,.0f} 잔량{b:12,.0f}")

print("\n[음수 잔량 샘플 8] (보낸<소진 = 소스 갭 후보)")
for c,m,i,o,b in sorted(neg,key=lambda x:x[4])[:8]:
    print(f"  {c:6s} {m:16s} 보낸{i:10,.0f} 소진{o:10,.0f} 잔량{b:10,.0f}")
print(f"\n(경과 {time.time()-t0:.0f}s)")
