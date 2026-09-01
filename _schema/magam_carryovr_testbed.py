# -*- coding: utf-8 -*-
"""★마감 이월 재배정(override) 테스트베드 (2026-09-01).
검증: (A)override 0건이면 현행 _sale_win/_carry_win 과 diff0 (B)daylist carry 표시 (C)재배정 이동(당월↔이월 금액 정확·불변식) (D)매입.
방식: FLOW식 no-commit + uvicorn + 실인증, 실제 엔드포인트, 전부 롤백·오염0.
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
# ★마감 조회 쿼리는 전부 PARTNER_ERP_TEST3.nx.* (3-part) → _conn 도 공유 RAW로 패치해야
#   override 미커밋 쓰기를 조회가 같은 트랜잭션에서 본다(오염0 유지). 실서버는 _conn=live/_nx=nx 정상.
common._nx=sh; common._nx_tx=sh; common._conn=sh
os.environ["FLOW_TESTBED"]="1"
import app as APP
for nm,md in list(sys.modules.items()):
    if nm.startswith('routers.') or nm in ('live_api','common'):
        for a in ('_nx','_nx_tx','_conn'):
            if hasattr(md,a): setattr(md,a,sh)
import uvicorn
PORT=8094
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
YM="2608"; CC="2148"
_yy=int(YM[:2]);_mm=int(YM[2:])-1;_py=_yy
if _mm==0:_mm=12;_py-=1
PREV=f"{_py:02d}{_mm:02d}"

def sumamt(cur_win):
    sql=common._SALE_MAGAM.format(ym=YM)+f"""
      SELECT ISNULL(SUM(-A.MAINT_AMT),0) FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND A.CUST_CODE='{CC}' AND A.MAINT_YMD>='{PREV}00' AND A.MAINT_YMD<='{YM}99' AND {cur_win}"""
    return float(q(sql)[0][0] or 0)
def sumcarry(cw):
    sql=common._SALE_MAGAM.format(ym=YM)+f"""
      SELECT ISNULL(SUM(-A.MAINT_AMT),0) FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT A JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
      WHERE A.MAINT_TAG='5' AND A.CUST_CODE='{CC}' AND A.MAINT_YMD>='{YM}00' AND A.MAINT_YMD<='{YM}99' AND {cw}"""
    return float(q(sql)[0][0] or 0)

# ── A. override 0건 → 현행 diff0 ──
print("\n[A] override 0건 → 현행 _sale_win/_carry_win 과 diff0")
old_cur=sumamt(common._sale_win().format(ym=YM)); new_cur=sumamt(common._sale_win_ovr('SALE').format(ym=YM))
rec("당월 마감 diff0(_sale_win == _sale_win_ovr)", abs(old_cur-new_cur)<0.5, f"old {old_cur:,.0f} == new {new_cur:,.0f}")
old_car=sumcarry(common._carry_win().format(ym=YM)); new_car=sumcarry(common._carry_win_ovr('SALE').format(ym=YM))
rec("이월 diff0(_carry_win == _carry_win_ovr)", abs(old_car-new_car)<0.5, f"old {old_car:,.0f} == new {new_car:,.0f}")

# ── B. daylist = 당월+이월 한 표, carry 표시 ──
print("\n[B] 일자별 조회(daylist) — 당월/이월 한 표 + carry 표시")
dl=get(f"/api/salemagam/daylist?ym={YM}&cc={CC}"); drows=dl.get("rows",[])
c1=[r for r in drows if r["carry"]==1]; c0=[r for r in drows if r["carry"]==0]
rec("daylist 반환", len(drows)>0, f"{len(drows)}행 (이월 {len(c1)} · 당월 {len(c0)})")
rec("이월/당월 둘 다 존재", len(c1)>0 and len(c0)>0, f"carry1 {len(c1)}, carry0 {len(c0)}")

# 당월/이월 합 스냅샷(엔드포인트)
def det_total():
    j=get(f"/api/salemagam/detail?ym={YM}&cc={CC}"); return round(sum(float(i['amt']) for i in j.get('items',[])),0)
def car_total():
    j=get(f"/api/salemagam/carryover?ym={YM}&cc={CC}"); return round(sum(float(r['amt']) for r in j.get('rows',[])),0)
d0=det_total(); k0=car_total(); tot0=d0+k0
rec("초기 당월+이월 스냅샷", True, f"당월 {d0:,.0f} + 이월 {k0:,.0f} = {tot0:,.0f}")

# ── C. 재배정: 이월→당월(당김) ──
print("\n[C] 재배정: 이월 품목을 당월로 당김")
tgt=c1[0]; a=round(float(tgt['amt']),0)
r=post("/api/salemagam/carry_set",{"ym":YM,"cust_code":CC,"mat_code":tgt['mat'],"maint_ymd":tgt['ymd'],"carry":False})
rec("carry_set(당월) ok", r.get("ok") and r.get("assign_ym")==YM, f"{r}")
d1=det_total(); k1=car_total()
rec("당월 +금액 이동", abs((d1-d0)-a)<1.0, f"당월 {d0:,.0f}→{d1:,.0f} (+{a:,.0f})")
rec("이월 -금액 이동", abs((k0-k1)-a)<1.0, f"이월 {k0:,.0f}→{k1:,.0f} (-{a:,.0f})")
rec("총합 불변식", abs((d1+k1)-tot0)<1.0, f"{d1+k1:,.0f} == {tot0:,.0f}")
dl2=get(f"/api/salemagam/daylist?ym={YM}&cc={CC}").get("rows",[])
now=[x for x in dl2 if x['mat']==tgt['mat'] and x['ymd']==tgt['ymd']]
rec("daylist 해당행 carry=0 반영", now and now[0]['carry']==0, f"{now[0]['carry'] if now else '?'}")

# 되돌리기(이월) → 자연상태 = override 삭제
r2=post("/api/salemagam/carry_set",{"ym":YM,"cust_code":CC,"mat_code":tgt['mat'],"maint_ymd":tgt['ymd'],"carry":True})
rec("carry_set(이월 복귀) = 자연상태→override삭제", r2.get("ok") and r2.get("override")==False, f"override={r2.get('override')}")
d2=det_total(); k2=car_total()
rec("복귀 후 초기와 일치(diff0)", abs(d2-d0)<1.0 and abs(k2-k0)<1.0, f"당월 {d2:,.0f}=={d0:,.0f}, 이월 {k2:,.0f}=={k0:,.0f}")

# ── D. 당월→이월(밀기) ──
print("\n[D] 재배정: 당월 품목을 이월로 밀기")
tgt2=c0[0]; b=round(float(tgt2['amt']),0)
post("/api/salemagam/carry_set",{"ym":YM,"cust_code":CC,"mat_code":tgt2['mat'],"maint_ymd":tgt2['ymd'],"carry":True})
d3=det_total(); k3=car_total()
rec("당월 -금액 / 이월 +금액", abs((d0-d3)-b)<1.0 and abs((k3-k0)-b)<1.0, f"당월 -{b:,.0f}, 이월 +{b:,.0f}")

# ── E. 매입 daylist ──
print("\n[E] 매입 daylist")
pl=get("/api/purmagam/list?ym="+YM).get("rows",[])
if pl:
    pcc=str(pl[0]['cc']).strip()
    pdl=get(f"/api/purmagam/daylist?ym={YM}&cc={pcc}").get("rows",[])
    pc1=[r for r in pdl if r['carry']==1]
    rec(f"매입 daylist({pcc})", len(pdl)>0, f"{len(pdl)}행 이월 {len(pc1)}")

RAW.rollback()
print(f"\n===== 결과: PASS {len(PASS)} / FAIL {len(FAIL)} =====")
if FAIL: print("FAIL:", FAIL)
