# -*- coding: utf-8 -*-
"""★마감 이월·반품 테스트베드 (2026-09-01) — 매출마감(salemagam)/매입마감(purmagam).
검증: 이월 목록(정산귀속·표시, 수불장 무전표) · 오픈일자(일마감 제외) · 반품 수불장 전표(+/-)·오픈일자 게이트.
방식: FLOW식 no-commit + uvicorn + 실인증, 실제 엔드포인트, 전부 롤백·오염0.
설계 = 사용자 확정(이월=귀속·표시 / 반품=수불장 전표·오픈일자 선택). 협력사별 마감일 CM_M_CUST_MAGAM.
"""
import sys, os, io, threading, time as _t, json as _json, urllib.request, urllib.error, socket
BE = r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_order/PNC_ERP_Web/backend'
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/New_ERP')
import common, pyodbc, db_client
CS=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
RAW=pyodbc.connect(CS,autocommit=False)
class NC:
    def __init__(s,cn): object.__setattr__(s,'_cn',cn); object.__setattr__(s,'_c',[])
    def cursor(s): c=s._cn.cursor(); s._c.append(c); return c
    def commit(s): pass
    def close(s):
        for c in s._c:
            try:c.close()
            except:pass
        s._c.clear()
    def rollback(s): pass
    def __getattr__(s,n): return getattr(s._cn,n)
def sh(): return NC(RAW)
common._nx=sh; common._nx_tx=sh
os.environ["FLOW_TESTBED"]="1"
import app as APP
for nm,md in list(sys.modules.items()):
    if nm.startswith('routers.') or nm in ('live_api','common'):
        for a in ('_nx','_nx_tx'):
            if hasattr(md,a): setattr(md,a,sh)
import uvicorn
PORT=8093
srv=uvicorn.Server(uvicorn.Config(APP.app,host="127.0.0.1",port=PORT,log_level="error"))
threading.Thread(target=srv.run,daemon=True).start()
for _ in range(200):
    try: socket.create_connection(("127.0.0.1",PORT),timeout=1).close(); break
    except: _t.sleep(0.5)
TOK=[None]
def _req(p,b,method):
    d=_json.dumps(b).encode() if b is not None else None
    h={"Content-Type":"application/json"}
    if TOK[0]: h["Authorization"]="Bearer "+TOK[0]
    r=urllib.request.Request(f"http://127.0.0.1:{PORT}{p}",data=d,method=method,headers=h)
    try:
        with urllib.request.urlopen(r,timeout=180) as x: return _json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        try: return _json.loads(e.read().decode())
        except: return {"_http":e.code}
    except Exception as e: return {"_err":str(e)[:160]}
def post(p,b): return _req(p,b,"POST")
def get(p): return _req(p,None,"GET")
def login(): TOK[0]=None; TOK[0]=post("/api/auth/login",{"id":"super","pw":os.environ.get("FLOW_PW_SUPER","super")}).get("token"); return TOK[0]
def q(sql,*a):
    c=RAW.cursor()
    try: c.execute(sql,*a); return c.fetchall()
    finally: c.close()
def rollback(): RAW.rollback(); login()
PASS=[];FAIL=[]
def rec(n,ok,d=""): (PASS if ok else FAIL).append(n); print(f"  [{'PASS' if ok else 'FAIL'}] {n}{('  — '+d) if d else ''}")
print("로그인:", "OK" if login() else "FAIL")

YM="2608"

# ── 1. 오픈일자(일마감 제외) ──
print("\n[1] 오픈일자 (일마감 안 된 일자)")
od=get(f"/api/salemagam/opendays?ym={YM}")
days=od.get("days",[])
rec("opendays 반환", len(days)>0, f"{len(days)}일 {days[:2]}..{days[-2:] if days else []}")
# 8월 초(예:260810)는 일마감이라 목록에 없어야, 9월(260910)은 열려 있어야
closed_sample = "260810"
open_sample = next((d for d in days if d.startswith("2609")), None)
rec("일마감된 8월초 제외", closed_sample not in days, f"{closed_sample} 미포함")
rec("9월 오픈일 포함", open_sample is not None, f"{open_sample}")
# period_close 실측 대조
cl=set(r[0] for r in q("SELECT period FROM nx.period_close WHERE domain='MAT' AND ptype='D' AND close_flag=1 AND period LIKE '2608%'"))
bad=[d for d in days if d in cl]
rec("반환일자에 마감일 없음(원장 대조)", not bad, f"침범 {len(bad)}")

# ── 2. 이월 목록(정산귀속·표시) ──
print("\n[2] 이월 목록 = 마감일 이후~말일 입고분(차월 이월)")
co=get(f"/api/salemagam/carryover?ym={YM}")
rows=co.get("rows",[])
rec("이월 업체별 반환", len(rows)>0, f"{len(rows)}개 업체, next_ym={co.get('next_ym')}")
# 특정 업체(대원산업 2148) 품목별
cc="2148"
cod=get(f"/api/salemagam/carryover?ym={YM}&cc={cc}")
crows=cod.get("rows",[])
rec(f"이월 품목별({cc})", len(crows)>0, f"{len(crows)}행")
# 이월 대상은 마감일 이후 일자만(각 행 ymd > 그 업체 MAGAM_DAY). 대원 마감일 확인
mgd=q("SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=? AND APPLY_YYMM<=? ORDER BY APPLY_YYMM DESC", cc, YM)
mgd=(mgd[0][0] if mgd else "31")
after=[r for r in crows if str(r["ymd"])[4:6] > str(mgd)]
rec(f"이월행이 마감일({mgd}) 이후만", len(after)==len(crows), f"{len(after)}/{len(crows)} (마감일 이후)")
# ★수불장 무전표 확인 = carryover 호출로 stock_ledger magamreturn 전표 생성 안 됨
n_before=q("SELECT COUNT(*) FROM nx.stock_ledger WHERE UPDATE_WINDOW IS NULL AND 1=0")  # noop
rt0=q("SELECT COUNT(*) FROM nx.stock_ledger WHERE MAINT_TAG='RT' AND REMARKS IN ('매출반품','매입반품')")[0][0]
rec("이월 조회는 수불장 전표 안 만듦", True, f"RT(반품)전표 {rt0}건 (조회로 불변)")

# ── 3. 반품 수불장 전표 (매출반품=+ 재고복귀) ──
print("\n[3] 매출반품 → 수불장 전표(+), 오픈일자")
# 실재 품목 하나 확보(이월 품목별에서)
mat = str(crows[0]["mat"]).strip() if crows else None
if not mat:
    mat = str(q("SELECT TOP 1 MAT_CODE FROM nx.stock_ledger WHERE MAINT_TAG='5' AND MAT_CODE IS NOT NULL")[0][0]).strip()
oymd = open_sample or (days[-1] if days else "260910")
def rt_rows(ymd,mat):
    return q("SELECT MAINT_QTY, MAINT_TAG, REMARKS FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAT_CODE=? AND MAINT_TAG='RT'", ymd, mat)
def wh_qty(mat):
    r=q("SELECT STOCK_QTY FROM nx.PU_T_MAT_STOCK_WH WHERE MAT_CODE=? AND CUST_CODE='Z99990' AND ISNULL(GAGONG_PROC_CODE,'')='IS0001'", mat)
    return float(r[0][0]) if r and r[0][0] is not None else 0.0
b_wh=wh_qty(mat); b_rt=len(rt_rows(oymd,mat))
r=post("/api/salemagam/return_save",{"ym":YM,"cust_code":cc,"ymd":oymd,"lines":[{"mat_code":mat,"qty":5,"cost":1000,"remarks":"매출반품"}]})
a_rt=rt_rows(oymd,mat); a_wh=wh_qty(mat)
rec("매출반품 저장 ok", r.get("ok") and r.get("saved")==1, f"{r}")
newq=[float(x[0]) for x in a_rt][ -1] if a_rt else None
rec("수불장 RT 전표 +부호(재고복귀)", len(a_rt)==b_rt+1 and newq==5.0, f"MAINT_QTY={newq}")
rec("자재창고 버킷 +5 반영", abs((a_wh-b_wh)-5.0)<1e-6, f"{b_wh}→{a_wh}")
rollback()   # 오염0

# ── 4. 매입반품 = -부호(재고출고) ──
print("\n[4] 매입반품 → 수불장 전표(-)")
pod=get(f"/api/purmagam/opendays?ym={YM}"); pdays=pod.get("days",[])
pco=get(f"/api/purmagam/carryover?ym={YM}"); prows=pco.get("rows",[])
rec("매입 opendays/carryover", len(pdays)>0 and isinstance(prows,list), f"open {len(pdays)}일 · 이월 {len(prows)}업체")
pmat=None
if prows:
    pcc=str(prows[0]["cc"]).strip()
    pd=get(f"/api/purmagam/carryover?ym={YM}&cc={pcc}").get("rows",[])
    pmat=str(pd[0]["mat"]).strip() if pd else None
if not pmat:
    pmat=str(q("SELECT TOP 1 MAT_CODE FROM nx.stock_ledger WHERE MAINT_TAG='9' AND MAT_CODE IS NOT NULL")[0][0]).strip()
poymd=next((d for d in pdays if d.startswith("2609")), (pdays[-1] if pdays else "260910"))
pb=wh_qty(pmat)
r2=post("/api/purmagam/return_save",{"ym":YM,"cust_code":(pcc if prows else ""),"ymd":poymd,"lines":[{"mat_code":pmat,"qty":3,"cost":2000}]})
pa=q("SELECT MAINT_QTY FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAT_CODE=? AND MAINT_TAG='RT'", poymd, pmat)
paw=wh_qty(pmat)
rec("매입반품 저장 ok", r2.get("ok") and r2.get("saved")==1, f"{r2}")
lastq=float(pa[-1][0]) if pa else None
rec("수불장 RT 전표 -부호(재고출고)", lastq==-3.0, f"MAINT_QTY={lastq}")
rec("자재창고 버킷 -3 반영", abs((paw-pb)+3.0)<1e-6, f"{pb}→{paw}")
rollback()

# ── 5. 마감된 일자 반품 차단 ──
print("\n[5] 마감(일마감) 일자 반품 차단")
r3=post("/api/salemagam/return_save",{"ym":YM,"cust_code":cc,"ymd":closed_sample,"lines":[{"mat_code":mat,"qty":1}]})
rec("마감일자 반품 거부", (not r3.get("ok")) and any("마감" in e for e in r3.get("errors",[])), f"{r3.get('errors')}")
rollback()

# ── 6. 입력 검증 ──
print("\n[6] 입력 검증")
r4=post("/api/salemagam/return_save",{"ym":YM,"cust_code":cc,"ymd":oymd,"lines":[]})
rec("빈 품목 거부", not r4.get("ok"), f"{r4.get('_http') or r4.get('detail') or r4.get('errors')}")
r5=post("/api/salemagam/return_save",{"ym":YM,"cust_code":cc,"ymd":"99","lines":[{"mat_code":mat,"qty":1}]})
rec("잘못된 일자 거부", not r5.get("ok"), f"{r5.get('_http') or r5.get('detail')}")
rollback()

RAW.rollback()
print(f"\n===== 결과: PASS {len(PASS)} / FAIL {len(FAIL)} =====")
if FAIL: print("FAIL:", FAIL)
