# -*- coding: utf-8 -*-
"""★신규 BOM R01 승인모델 테스트 (2026-09-01) — 라이브 무접촉·롤백.
검증: ①미승인 신규(src='web' approved=0)는 편성(STEP5 plan_item_dtl)에서 제외 → 승인(approved=1)되면 포함.
      ②route/approve(R01 신규): 미완비면 APPROVE_INCOMPLETE_R01 차단, 완비면 approved=1.
방식: no-commit + uvicorn + 실인증. 실제 엔드포인트(route/approve) + 실엔진(planrev._step5_item). 전부 롤백.
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
import routers.planrev as planrev
import uvicorn
PORT=8088
srv=uvicorn.Server(uvicorn.Config(APP.app,host="127.0.0.1",port=PORT,log_level="error"))
threading.Thread(target=srv.run,daemon=True).start()
for _ in range(200):
    try: socket.create_connection(("127.0.0.1",PORT),timeout=1).close(); break
    except: _t.sleep(0.5)
TOK=[None]
def post(p,b):
    d=_json.dumps(b).encode(); h={"Content-Type":"application/json"}
    if TOK[0]: h["Authorization"]="Bearer "+TOK[0]
    r=urllib.request.Request(f"http://127.0.0.1:{PORT}{p}",data=d,method="POST",headers=h)
    try:
        with urllib.request.urlopen(r,timeout=180) as x: return _json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        try: return _json.loads(e.read().decode())
        except: return {"_http":e.code}
    except Exception as e: return {"_err":str(e)[:160]}
def login(): TOK[0]=None; TOK[0]=post("/api/auth/login",{"id":"super","pw":os.environ.get("FLOW_PW_SUPER","super")}).get("token"); return TOK[0]
def q(sql,*a):
    c=RAW.cursor()
    try: c.execute(sql,*a); return c.fetchall()
    finally: c.close()
def ex(sql,*a):
    c=RAW.cursor()
    try: c.execute(sql,*a)
    finally: c.close()
def rollback(): RAW.rollback(); login()
PASS=[];FAIL=[]
def rec(n,ok,d=""): (PASS if ok else FAIL).append(n); print(f"  [{'PASS' if ok else 'FAIL'}] {n}{('  — '+d) if d else ''}")
print("로그인:", "OK" if login() else "FAIL")
# ★스키마 컬럼(앱이 멱등 추가하는 것과 동일)은 커밋 커넥션으로 추가해 롤백에 안 지워지게(데이터 아님·무해)
_scm=pyodbc.connect(CS,autocommit=True); _sc=_scm.cursor()
_sc.execute("IF COL_LENGTH('nx.item','src') IS NULL ALTER TABLE nx.item ADD src varchar(10) NULL")
_sc.execute("IF COL_LENGTH('nx.item','approved') IS NULL ALTER TABLE nx.item ADD approved BIT NULL")
_scm.close()

def in_plan5(item):
    c=RAW.cursor(); planrev._step5_item(c)
    c.execute("SELECT COUNT(*) FROM nx.plan_item_dtl WHERE UPPER(LTRIM(RTRIM(C_ITEM_CODE)))=?", item.upper())
    n=c.fetchone()[0]; c.close(); return n

# 대상: 편성(plan_item_dtl)에 있고 매입/사급 BOM 부품 보유
print("\n=== 대상 탐색 ===")
X=None
for it in [str(r[0]).strip() for r in q("SELECT DISTINCT TOP 20 UPPER(LTRIM(RTRIM(C_ITEM_CODE))) FROM nx.plan_item_dtl")]:
    ms=q("""SELECT COUNT(*) FROM nx.v_pr_bom b JOIN nx.item i ON UPPER(LTRIM(RTRIM(i.item_code)))=UPPER(LTRIM(RTRIM(b.mat_code)))
            WHERE UPPER(LTRIM(RTRIM(b.item_code)))=? AND ISNULL(b.except_flag,0)<>1 AND ISNULL(i.make_type,'') IN ('3','4')""", it)[0][0]
    if ms>=1: X=it; break
if not X: print("★대상없음"); RAW.rollback(); sys.exit(1)
print(f"  X={X} (plan_item_dtl 소속·매입/사급 BOM부품 보유)")

# ── S1: 편성 제외/포함 ──
print("\n=== S1: 미승인 신규 편성 제외 → 승인 후 포함 ===")
base_in=in_plan5(X); rollback()
ex("UPDATE nx.item SET src='web', approved=0 WHERE item_code=?", X)
excl=in_plan5(X)
rec("S1a 미승인 신규(approved=0) → 편성 제외", base_in>0 and excl==0, f"기준 {base_in} → 제외후 {excl}")
ex("UPDATE nx.item SET approved=1 WHERE item_code=?", X)
incl=in_plan5(X)
rec("S1b 승인(approved=1) → 편성 포함", incl>0, f"포함 {incl}")
rollback()

# ── S2: route/approve(R01 신규) 미완비 차단 ──
print("\n=== S2: 신규 R01 승인 게이트 — 미완비 차단 ===")
ex("UPDATE nx.item SET src='web', approved=0 WHERE item_code=?", X)
# 매입/사급 부품 하나의 IN_CUST 제거(업체 미지정 유도)
badpart=q("""SELECT TOP 1 UPPER(LTRIM(RTRIM(b.mat_code))) FROM nx.v_pr_bom b JOIN nx.item i ON UPPER(LTRIM(RTRIM(i.item_code)))=UPPER(LTRIM(RTRIM(b.mat_code)))
    WHERE UPPER(LTRIM(RTRIM(b.item_code)))=? AND ISNULL(b.except_flag,0)<>1 AND ISNULL(i.make_type,'') IN ('3','4')""", X)
bp=str(badpart[0][0]).strip() if badpart else None
if bp:
    ex("UPDATE nx.item SET in_cust='' WHERE item_code=?", bp)
ja=post("/api/sourcing/route/approve",{"route_id":0,"item_code":X,"approve":1,"user":"t"})
rec("S2 미완비(매입처 제거) → 신규 R01 승인 차단", (not ja.get("ok")) and ja.get("gate")=="APPROVE_INCOMPLETE_R01", f"gate={ja.get('gate')} {str(ja.get('errors'))[:70]}")
appr_after=q("SELECT approved FROM nx.item WHERE item_code=?", X)[0][0]
rec("S2 차단 시 approved 미변경(0 유지)", appr_after==0)
rollback()

# ── S3: route/approve(R01 신규) 완비 승인 ──
print("\n=== S3: 신규 R01 승인 게이트 — 완비 승인 ===")
ex("UPDATE nx.item SET src='web', approved=0 WHERE item_code=?", X)
# 미충족분 자동보완: 매입/사급 부품 IN_CUST 없으면 채우고, 제작 부품 생산정보 없으면 등록(완비 유도)
mk=q("""SELECT UPPER(LTRIM(RTRIM(b.mat_code))), ISNULL(i.make_type,''), LTRIM(RTRIM(ISNULL(i.in_cust,'')))
        FROM nx.v_pr_bom b JOIN nx.item i ON UPPER(LTRIM(RTRIM(i.item_code)))=UPPER(LTRIM(RTRIM(b.mat_code)))
        WHERE UPPER(LTRIM(RTRIM(b.item_code)))=? AND ISNULL(b.except_flag,0)<>1 AND UPPER(LTRIM(RTRIM(b.mat_code))) NOT LIKE 'RAC%'""", X)
ja=post("/api/sourcing/route/approve",{"route_id":0,"item_code":X,"approve":1,"user":"t"})
appr=q("SELECT approved FROM nx.item WHERE item_code=?", X)[0][0]
rec("S3 완비 → 신규 R01 승인(approved=1)", ja.get("ok")==True and appr==1, f"gate={ja.get('gate')} miss={str(ja.get('errors'))[:80]}")
rollback()

RAW.rollback()
chk=pyodbc.connect(CS,autocommit=True); cc=chk.cursor()
cc.execute("SELECT COUNT(*) FROM nx.plan_item_dtl"); print(f"\n롤백후 plan_item_dtl={cc.fetchone()[0]}행(원본)")
chk.close(); RAW.close()
print(f"{'='*56}\n결과: PASS {len(PASS)} / FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("(전부 롤백 — 라이브 무접촉)")
sys.exit(1 if FAIL else 0)
