# -*- coding: utf-8 -*-
"""엔진 진짜 diff0 재베이스라인: NxCostEngine(nx.bom_line) vs 라이브 레거시 SP 오라클(pncind).
성분 [jae,gagong,ilban,unban,profit,silwon,lg] 대조(won/bu=엔진 미분할이라 제외). PASS=전성분 tol이내.
사용: python engine_rebaseline.py [N] [ymd]   기본 N=100 ymd=260630. 결과 rebaseline_<ymd>.json + 실패성분 분포."""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
import cost_oracle as CO
from nx_cost_engine import NxCostEngine
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
YMD = sys.argv[2] if len(sys.argv) > 2 else '260630'
KEYS = ['jae', 'gagong', 'ilban', 'unban', 'profit', 'silwon', 'lg']
TOL = 1.5
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
ro = RO().cursor()
# 표본: 완제품(make_type=1, '-'없음, BOM보유) 랜덤 + 앵커
ro.execute(f"""SELECT TOP {N} m.ITEM_CODE FROM PR_M_ITEM m
   WHERE ISNULL(m.MAKE_TYPE,'')='1' AND m.ITEM_CODE NOT LIKE '%-%'
     AND EXISTS(SELECT 1 FROM CS_M_ITEM_BOM b WHERE b.ITEM_CODE=m.ITEM_CODE)
   ORDER BY NEWID()""")
items = [ (r[0] or '').strip() for r in ro.fetchall() ]
for a in ['AJR75563402','AJR75563503','AJR30077403']:
    if a not in items: items.append(a)
print(f"재베이스라인 N={len(items)} ymd={YMD} (성분 {KEYS}, tol={TOL})")
ocn = CO._conn(); ocur = ocn.cursor()
eng = NxCostEngine()
res = {}; npass=nfail=nerr=njae_ok=0
from collections import Counter
failkey = Counter(); jae_gap=[]
for i, it in enumerate(items):
    try:
        o = CO.get_oracle(it, YMD, ocur); osil = o['sil']
    except Exception as e:
        nerr+=1; res[it]={"err":"ORA "+str(e)[:40]}; continue
    try:
        s = eng.silwon(it, YMD)
    except Exception as e:
        try:                              # 커넥션 끊김 → 엔진 재생성 1회 재시도
            try: eng.close()
            except Exception: pass
            eng = NxCostEngine(); s = eng.silwon(it, YMD)
        except Exception as e2:
            nerr+=1; res[it]={"err":"ENG "+str(e2)[:40]}; continue
    diffs = {}
    for k in KEYS:
        ov=float(osil.get(k,0) or 0); cv=float(s.get(k,0) or 0)
        if abs(ov-cv) > TOL: diffs[k]={"sp":round(ov,1),"eng":round(cv,1),"d":round(cv-ov,1)}
    res[it]={"ok":not diffs,"diffs":diffs,"sp_silwon":round(float(osil.get('silwon',0)),1),"eng_silwon":round(float(s.get('silwon',0)),1)}
    if 'jae' not in diffs: njae_ok+=1   # ★재료비만(설계차=용접 가공비 무관) 정합
    if diffs:
        nfail+=1
        for k in diffs: failkey[k]+=1
        if 'jae' in diffs: jae_gap.append((it, diffs['jae']['d']))
    else: npass+=1
    if (i+1)%25==0: print(f"  ...{i+1}/{len(items)} (pass {npass} fail {nfail} err {nerr})")
eng.close(); ocn.close()
json.dump(res, open(os.path.join(os.path.dirname(__file__), f'rebaseline_{YMD}.json'),'w',encoding='utf-8'), ensure_ascii=False, indent=1)
tot=len(items)
print(f"\n=== 엔진 vs 라이브 레거시 SP ({YMD}) ===")
print(f"  PASS(전성분 diff0) {npass} / FAIL {nfail} / ERR {nerr}  = {tot}")
ncomp=tot-nerr
print(f"  ★재료비(jae) diff0: {njae_ok}/{ncomp} = {round(100*njae_ok/ncomp,1) if ncomp else 0}% (용접 등 설계차 무관 = 진짜 재료비 정합률)")
print(f"  실패 성분 분포: {dict(failkey)}")
if jae_gap:
    import statistics
    gaps=[g for _,g in jae_gap]
    print(f"  재료비 갭 {len(jae_gap)}건: 평균Δ{round(statistics.mean(gaps),1)} 중앙Δ{round(statistics.median(gaps),1)} 최대|Δ|{max(abs(g) for g in gaps)}")
    print("   재료비 갭 상위:", sorted(jae_gap,key=lambda x:-abs(x[1]))[:8])
print("  저장:", f'rebaseline_{YMD}.json')
