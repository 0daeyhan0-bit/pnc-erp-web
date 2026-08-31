# -*- coding: utf-8 -*-
"""원가 100%(원소재 중량): SP는 원소재(cg='3') 중량을 **항상 기하계산**(외경>0), 저장 ITEM_WEIGHT 무시.
  ITEM_WEIGHT = π(외경−T)·T·길이·비중 ÷ 1e6  (비중=CM_M_MASTER_DETAIL PR019 금속별).
엔진은 nx.item.net_weight를 사용 → 저장값이 기하와 다르면 재료비 갭(MJU63669741 저장0.9393 vs 기하0.784 → 18049 vs SP 15057).
★ver2(2026-08-13): net_weight=0뿐 아니라 **cg='3' 전체**를 금속별 기하중량으로 덮어씀(SP 완전정합).
백업 nx.item_geomwt_bak(전 cg3 net_weight). --commit 없으면 규모만. 컷오버 재적용 대상."""
import sys, io, math
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
DENS = {'고강도':8.94, 'CU':8.94, 'AL':2.7, 'FE':7.85, 'STS':7.93}  # PR019 비중
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
rows = c.execute("""SELECT item_code, metal_gubun, diam, thick, length, net_weight FROM nx.item
  WHERE cost_gubun='3' AND diam>0 AND thick>0 AND length>0""").fetchall()
upd = []; skip_metal = {}
for r in rows:
    metal = (r[1] or '').strip()
    dens = DENS.get(metal)
    if not dens:
        skip_metal[metal] = skip_metal.get(metal, 0) + 1; continue
    d, t, L = float(r[2]), float(r[3]), float(r[4])
    geo = round(math.pi * (d - t) * t * L * dens / 1e6, 6)
    old = float(r[5] or 0)
    if abs(geo - old) > 0.0001:
        upd.append((geo, (r[0] or '').strip()))
print(f"cg='3' 치수有 {len(rows)}건 중 기하중량과 상이(갱신대상): {len(upd)}건. 비중없는금속 스킵: {skip_metal}")
if DRY:
    for g, code in upd[:8]: print(f"  {code:<16} → {g}")
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
# 전 cg3 net_weight 백업(직전상태). 이전 불완전 백업은 별칭 보존.
if c.execute("SELECT OBJECT_ID('nx.item_geomwt_bak','U')").fetchone()[0] is not None:
    c.execute("IF OBJECT_ID('nx.item_geomwt_bak0','U') IS NULL SELECT item_code, net_weight INTO nx.item_geomwt_bak0 FROM nx.item_geomwt_bak")
    c.execute("DROP TABLE nx.item_geomwt_bak")
c.execute("SELECT item_code, net_weight INTO nx.item_geomwt_bak FROM nx.item WHERE cost_gubun='3'")
print("백업 nx.item_geomwt_bak(전 cg3):", c.execute("SELECT COUNT(*) FROM nx.item_geomwt_bak").fetchone()[0])
# ★갱신대상 0건이면 executemany 가 터진다(pyodbc: "second parameter must not be empty").
#   2026-09-01 매일 마이그에서 실제로 걸렸다 — 어제는 11건이라 안 걸렸고 오늘은 0건이라 exit=1.
#   갱신할 게 없다는 건 정상(멱등 도구가 수렴한 상태)인데 루틴이 실패로 보이면 안 된다.
if upd:
    c.executemany("UPDATE nx.item SET net_weight=? WHERE item_code=?", upd)
print(f"기하중량 갱신 완료 {len(upd)}건. 되돌리기: nx.item_geomwt_bak")
n.close()
