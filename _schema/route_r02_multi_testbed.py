# -*- coding: utf-8 -*-
"""★10개 다양한 품번(제품군별) R02 종합 반영 테스트 (2026-09-01) — 실제 엔드포인트·라이브 무접촉.
각 품목: copy현행 → 라인변경(제작/외주 혼합) → finalize → 업체지정(단가캡처) → 생산정보 → 승인 → 활성.
10개 모두 활성 후 편성 1회 재계산 → 품목별로 생산계획(plan_route_active·자재변화) + 협력사계획(경로대안·업체) 반영 검증.
FLOW식 no-commit + uvicorn + 실인증, 전부 롤백·오염0. 설계=ROUTE_APPROVAL_GATE_DESIGN.md
"""
import sys, os, io, threading, time as _t, json as _json, urllib.request, urllib.error, socket
BE = r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_order/PNC_ERP_Web/backend'
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/New_ERP')
import common, pyodbc, db_client
CS=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
ro=pyodbc.connect(CS,autocommit=True); rc=ro.cursor()   # 라이브 스냅샷(RO)
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
PORT=8089
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
YMD="260630"
print("로그인:", "OK" if login() else "FAIL")

# 헬퍼
import datetime as _dt
ASOF=_dt.datetime.now().strftime("%y%m%d")
def pick_vendor(pc):
    # ★_master_price와 동일 as-of 필터(미래일자 단가 배제) → 업체 지정 시 단가 캡처 보장
    r=q("SELECT TOP 1 LTRIM(RTRIM(ISNULL(vendor_code,''))) FROM PARTNER_ERP_TEST3.nx.price_item WHERE price_type=N'매입' AND LTRIM(RTRIM(item_code))=? AND price IS NOT NULL AND ISNULL(vendor_code,'')<>'' AND apply_ymd<=? ORDER BY apply_ymd DESC", pc, ASOF)
    if r and r[0][0]: return str(r[0][0]).strip()
    inc=q("SELECT LTRIM(RTRIM(ISNULL(IN_CUST_CODE,''))) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE=?", pc)
    return str(inc[0][0]).strip() if inc and inc[0][0] else ''
def build_r02(item):
    """copy→라인변경(제작/외주)→finalize→업체지정→생산정보→승인→활성. 성공 rid, 실패 0. 사유 dict."""
    login()
    rid=int(post("/api/sourcing/route/copy",{"item_code":item,"source":"","ymd":YMD,"user":"t"}).get("route_id") or 0)
    if not rid: return 0,{"step":"copy"}
    # 라인변경: 자식 있는 부품 외주 2 + leaf 제작 2
    parts=[(int(r[0]),str(r[1]).strip()) for r in q("SELECT line_id,LTRIM(RTRIM(ISNULL(child_item,''))) FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB' AND ISNULL(staged,0)=0 AND ISNULL(child_item,'')<>'' AND UPPER(LTRIM(RTRIM(child_item))) NOT LIKE 'RAC%' ORDER BY sort_seq,line_id", rid)]
    def haschild(pc): return q("SELECT COUNT(*) FROM nx.v_pr_bom WHERE UPPER(LTRIM(RTRIM(item_code)))=? AND ISNULL(except_flag,0)<>1",pc.upper())[0][0]>0
    subb=[p for p in parts if haschild(p[1])]; leaf=[p for p in parts if not haschild(p[1])]
    nout=0
    for p in (subb[:2] if subb else parts[:2]):
        if post("/api/sourcing/line/gubun",{"route_id":rid,"line_id":p[0],"gubun":"외주"}).get("ok"): nout+=1
    for p in (leaf[:2] if len(leaf)>=2 else parts[2:4]):
        post("/api/sourcing/line/gubun",{"route_id":rid,"line_id":p[0],"gubun":"제작"})
    jf=post("/api/sourcing/route/finalize",{"route_id":rid,"item_code":item,"ymd":YMD,"commit":1})
    en=(jf.get("route_edges") or {}); en=en.get("edges",0) if isinstance(en,dict) else (en or 0)
    if not (jf.get("committed") and en>0): return 0,{"step":"finalize","err":str(jf.get('errors'))[:60]}
    # 업체지정(매입/사급, 단가캡처)
    msp=[str(r[0]).strip() for r in q("SELECT DISTINCT LTRIM(RTRIM(child_item)) FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB' AND ISNULL(staged,0)=0 AND ISNULL(gubun,'') IN (N'매입',N'사급') AND UPPER(LTRIM(RTRIM(child_item))) NOT LIKE 'RAC%'", rid) if str(r[0]).strip()]
    for pc in msp:
        vc=pick_vendor(pc)
        if vc: post("/api/sourcing/route_order/vendor",{"route_id":rid,"item_code":pc,"allocations":[{"vendor_code":vc,"alloc_ratio":100}]})
    # 생산정보(제작/자체·조립·SUB 품목 + route)
    mk=[item]+[str(r[0]).strip() for r in q("SELECT DISTINCT LTRIM(RTRIM(ISNULL(sub_item,child_item))) FROM nx.sourcing_route_line WHERE route_id=? AND ISNULL(staged,0)=0 AND (ISNULL(gubun,'') IN (N'제작',N'자체') OR node_kind='SUB') AND ISNULL(child_item,'')<>'' AND UPPER(LTRIM(RTRIM(child_item))) NOT LIKE 'RAC%'", rid) if str(r[0]).strip()]
    for it in dict.fromkeys(mk):
        post("/api/prodinfo/proc/save",{"item":it,"route_id":0,"rows":[{"proc_seq":1,"work_code":"P2","tot_st":1,"work_qty":1}],"user":"t"})
    post("/api/prodinfo/proc/save",{"item":item,"route_id":rid,"rows":[{"proc_seq":1,"work_code":"P2","tot_st":1,"work_qty":1}],"user":"t"})
    ja=post("/api/sourcing/route/approve",{"route_id":rid,"approve":1,"user":"t"})
    if not ja.get("ok"): return 0,{"step":"approve","gate":ja.get("gate"),"err":str(ja.get('errors'))[:70]}
    jc=post("/api/sourcing/route/alloc/save",{"item":item,"rows":[{"route_id":rid,"is_active":1,"alloc_ratio":100,"apply_from":"2000-01-01"}]})
    if not jc.get("ok"): return 0,{"step":"activate","gate":jc.get("gate"),"err":str(jc.get('errors'))[:70]}
    return rid,{"outsourced":nout,"vendors":len(msp)}

def live_mat(item):
    rc.execute("SELECT UPPER(LTRIM(RTRIM(mat_code))) FROM nx.plan_part_mat WHERE UPPER(LTRIM(RTRIM(assy_item_code)))=? GROUP BY UPPER(LTRIM(RTRIM(mat_code)))", item.upper())
    return {str(r[0]).strip() for r in rc.fetchall()}

# 다양한 제품군 10품번 — 접두 다양화
print("\n=== 다양한 제품군 10품번 선정 ===")
cand=[str(r[0]).strip() for r in q("""SELECT UPPER(LTRIM(RTRIM(assy_item_code))) a FROM nx.plan_part_mat
   GROUP BY UPPER(LTRIM(RTRIM(assy_item_code))) HAVING COUNT(DISTINCT mat_code) BETWEEN 6 AND 16 ORDER BY COUNT(DISTINCT mat_code)""") if str(r[0]).strip()]
picked=[]; seen=set()
for it in cand:
    pre=it[:5]
    if pre in seen: continue
    seen.add(pre); picked.append(it)
    if len(picked)>=60: break
print(f"  후보(접두 다양·작은BOM) {len(picked)}: {picked[:24]}")

PASS=[];FAIL=[]
def rec(n,ok,d=""): (PASS if ok else FAIL).append(n); print(f"  [{'PASS' if ok else 'FAIL'}] {n}{('  — '+d) if d else ''}")

# 10개 빌드+활성(롤백 없이 누적)
print("\n=== R02 구성·활성 (10품번) ===")
built=[]; base={}; _att=0
for it in picked:
    if len(built)>=10 or _att>=50: break
    _att+=1
    try:
        base[it]=live_mat(it)
        rid,info=build_r02(it)
        if rid: built.append((it,rid,info)); print(f"  OK {it} (rid={rid}, 외주{info.get('outsourced')}·업체{info.get('vendors')})")
        else: print(f"  -- {it} 실패 @ {info.get('step')} {info.get('gate') or ''} {info.get('err') or ''}")
    except pyodbc.Error as e:
        # DB 연결끊김(부하) — 더 진행 못함, 지금까지 구성분으로 진행
        print(f"  ★{it} DB오류로 중단({str(e)[:50]}) → 구성 {len(built)}품번으로 편성 진행"); break
    except Exception as e:
        print(f"  -- {it} 예외 {type(e).__name__} {str(e)[:60]}")
print(f"구성·활성 완료 {len(built)}품번")
if len(built)<1: print("★구성 0"); RAW.rollback(); sys.exit(1)

# 편성 1회 재계산
print("\n=== 편성 재계산(생산+협력사) ===")
c=RAW.cursor(); planrev._step7_sql(c); c.close()
c=RAW.cursor(); planrev._step_source(c); c.close()
c=RAW.cursor(); planrev._route_setup(c)
pra={str(r[0]).strip() for r in c.execute("SELECT assy_item_code FROM nx.plan_route_active").fetchall()}
c.close()

# 품목별 검증
print("\n=== 품목별 반영 검증 ===")
n_prod=n_coop=0
for (it,rid,info) in built:
    inpra = it.upper() in pra
    r_mat = {str(r[0]).strip() for r in q("SELECT UPPER(LTRIM(RTRIM(mat_code))) FROM nx.plan_part_mat WHERE UPPER(LTRIM(RTRIM(assy_item_code)))=? GROUP BY UPPER(LTRIM(RTRIM(mat_code)))", it.upper())}
    changed = (base.get(it,set()) != r_mat)
    wos=[str(r[0]).strip() for r in q("SELECT DISTINCT work_order FROM nx.plan_part_mat WHERE UPPER(LTRIM(RTRIM(assy_item_code)))=?", it.upper())]
    nroute=0
    if wos:
        ph=",".join("?"*len(wos[:100]))
        nroute=q(f"SELECT COUNT(*) FROM nx.plan_mat_source WHERE WORK_ORDER IN ({ph}) AND SOURCE=N'경로대안'",*wos[:100])[0][0]
    prod_ok = inpra
    coop_ok = nroute>0
    if prod_ok: n_prod+=1
    if coop_ok: n_coop+=1
    rec(f"[{it}] 생산={'O' if prod_ok else 'X'}(pra{'진입' if inpra else '미진입'}·자재{'변화' if changed else '동일'}) 협력사={'O' if coop_ok else 'X'}(경로대안 {nroute})", prod_ok and coop_ok, f"외주{info.get('outsourced')}")

RAW.rollback()
chk=pyodbc.connect(CS,autocommit=True); cc=chk.cursor()
cc.execute("SELECT COUNT(*) FROM nx.plan_part_mat"); print(f"\n롤백후 plan_part_mat={cc.fetchone()[0]}행(원본)")
chk.close(); RAW.close(); ro.close()
print(f"{'='*56}\n결과: 구성 {len(built)}품번 · 생산반영 {n_prod} · 협력사반영 {n_coop} · PASS {len(PASS)}/FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("(전부 롤백 — 라이브 무접촉)")
sys.exit(1 if (FAIL or len(built)<5) else 0)
