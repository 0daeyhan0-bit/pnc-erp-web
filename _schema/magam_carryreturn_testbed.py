# -*- coding: utf-8 -*-
"""★마감 이월 테스트베드 (2026-09-01) — 매출마감(salemagam)/매입마감(purmagam).
검증: 이월 목록(정산 귀속·표시, 수불장 무전표) · 업체별/품목별 · 입고일자 다일자(일자별 토글용).
방식: FLOW식 no-commit + uvicorn + 실인증, 실제 엔드포인트, 전부 롤백·오염0.
설계: 이월=정산 귀속·표시만(수불장 전표 없음). 반품 기능은 사용자 요청으로 제거(2026-09-01).
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
PASS=[];FAIL=[]
def rec(n,ok,d=""): (PASS if ok else FAIL).append(n); print(f"  [{'PASS' if ok else 'FAIL'}] {n}{('  — '+d) if d else ''}")
print("로그인:", "OK" if login() else "FAIL")
YM="2608"

# ── 1. 이월 업체별 ──
print("\n[1] 이월 업체별 집계")
co=get(f"/api/salemagam/carryover?ym={YM}")
rows=co.get("rows",[])
rec("이월 업체별 반환", len(rows)>0, f"{len(rows)}개 업체 · next_ym={co.get('next_ym')}")
rec("next_ym = 차월", co.get("next_ym")=="2609", f"{co.get('next_ym')}")

# ── 2. 이월 품목·일자별(2148 대원산업) ──
print("\n[2] 이월 품목별/입고일자별 (2148)")
cc="2148"
cod=get(f"/api/salemagam/carryover?ym={YM}&cc={cc}")
crows=cod.get("rows",[])
rec("품목×입고일 행 반환", len(crows)>0, f"{len(crows)}행")
# 마감일 이후만
mgd=q("SELECT TOP 1 MAGAM_DAY FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM WHERE CUST_CODE=? AND APPLY_YYMM<=? ORDER BY APPLY_YYMM DESC", cc, YM)
mgd=(mgd[0][0] if mgd else "31")
after=[r for r in crows if str(r["ymd"])[4:6] > str(mgd)]
rec(f"전 행이 마감일({mgd}) 이후", len(after)==len(crows), f"{len(after)}/{len(crows)}")
# 일자별 토글 = 여러 입고일 존재
udays=sorted(set(str(r["ymd"]) for r in crows))
rec("입고일 다일자(일자별 토글용)", len(udays)>=2, f"입고일 {len(udays)}종 {udays[:5]}")
# 품목별 집계 = 품번 유니크수
umat=set(str(r["mat"]) for r in crows)
rec("품목별 집계 가능", len(umat)>0, f"품번 {len(umat)}종")
# 금액 합 일치(업체별 총액 vs 품목별 합)
tot_cc=next((r["amt"] for r in rows if str(r["cc"])==cc), None)
tot_it=round(sum(+r["amt"] for r in crows),0)
rec("업체총액 ≈ 품목합", tot_cc is not None and abs(round(tot_cc,0)-tot_it)<1.0, f"업체 {round(tot_cc or 0):,} vs 품목합 {int(tot_it):,}")

# ── 3. 수불장 무전표(조회는 원장 불변) ──
print("\n[3] 이월 조회는 수불장 전표 안 만듦")
b=q("SELECT COUNT(*) FROM nx.stock_ledger WHERE UPDATE_WINDOW='magamreturn'")[0][0]
get(f"/api/salemagam/carryover?ym={YM}&cc={cc}"); get(f"/api/purmagam/carryover?ym={YM}")
a=q("SELECT COUNT(*) FROM nx.stock_ledger WHERE UPDATE_WINDOW='magamreturn'")[0][0]
rec("magamreturn 전표 불변(0)", a==b==0, f"before {b} after {a}")

# ── 4. 매입마감 이월 ──
print("\n[4] 매입마감 이월")
pco=get(f"/api/purmagam/carryover?ym={YM}"); prows=pco.get("rows",[])
rec("매입 업체별 이월", isinstance(prows,list) and len(prows)>0, f"{len(prows)}업체 next_ym={pco.get('next_ym')}")
if prows:
    pcc=str(prows[0]["cc"]).strip()
    pd=get(f"/api/purmagam/carryover?ym={YM}&cc={pcc}").get("rows",[])
    pud=sorted(set(str(r["ymd"]) for r in pd))
    rec(f"매입 품목×입고일({pcc})", len(pd)>0, f"{len(pd)}행 · 입고일 {len(pud)}종")

RAW.rollback()
print(f"\n===== 결과: PASS {len(PASS)} / FAIL {len(FAIL)} =====")
if FAIL: print("FAIL:", FAIL)
