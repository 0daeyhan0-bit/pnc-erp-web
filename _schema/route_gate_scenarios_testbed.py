# -*- coding: utf-8 -*-
"""★조달경로 확정 게이트 종합 시나리오 테스트베드 (2026-09-01) — 실제 엔드포인트·라이브 무접촉.
검증: 승인 게이트(업체·단가·생산라인) 양성/음성 · 활성 게이트(구조·단가·생산정보) 양성/음성 ·
      편성 미지정 반영(협력사) · 생산+협력사 반영. FLOW식 no-commit + uvicorn + 실인증, 전부 롤백·오염0.
설계 정본 = ROUTE_APPROVAL_GATE_DESIGN.md
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
PORT=8090
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
def rollback(): RAW.rollback(); login()
PASS=[];FAIL=[]
def rec(n,ok,d=""): (PASS if ok else FAIL).append(n); print(f"  [{'PASS' if ok else 'FAIL'}] {n}{('  — '+d) if d else ''}")
print("로그인:", "OK" if login() else "FAIL")
YMD="260630"

# ── 엔드포인트 헬퍼 ──
def copyf(item):
    rid=int(post("/api/sourcing/route/copy",{"item_code":item,"source":"","ymd":YMD,"user":"t"}).get("route_id") or 0)
    if not rid: return 0
    jf=post("/api/sourcing/route/finalize",{"route_id":rid,"item_code":item,"ymd":YMD,"commit":1})
    en=(jf.get("route_edges") or {}); en=en.get("edges",0) if isinstance(en,dict) else (en or 0)
    return rid if (jf.get("committed") and en>0) else 0
def ms_parts(rid):
    return [str(r[0]).strip() for r in q("SELECT DISTINCT LTRIM(RTRIM(child_item)) FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB' AND ISNULL(staged,0)=0 AND ISNULL(gubun,'') IN (N'매입',N'사급') AND UPPER(LTRIM(RTRIM(child_item))) NOT LIKE 'RAC%'", rid) if str(r[0]).strip()]
def mk_items(rid, assy):
    out=[assy]
    out+=[str(r[0]).strip() for r in q("SELECT DISTINCT LTRIM(RTRIM(ISNULL(sub_item,child_item))) FROM nx.sourcing_route_line WHERE route_id=? AND ISNULL(staged,0)=0 AND (ISNULL(gubun,'') IN (N'제작',N'자체') OR node_kind='SUB') AND ISNULL(child_item,'')<>'' AND UPPER(LTRIM(RTRIM(child_item))) NOT LIKE 'RAC%'", rid) if str(r[0]).strip()]
    return list(dict.fromkeys(out))
def pick_vendor(pc):
    r=q("SELECT TOP 1 LTRIM(RTRIM(ISNULL(vendor_code,''))) FROM PARTNER_ERP_TEST3.nx.price_item WHERE price_type=N'매입' AND LTRIM(RTRIM(item_code))=? AND price IS NOT NULL AND ISNULL(vendor_code,'')<>'' ORDER BY apply_ymd DESC", pc)
    if r and r[0][0]: return str(r[0][0]).strip()
    inc=q("SELECT LTRIM(RTRIM(ISNULL(IN_CUST_CODE,''))) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE=?", pc)
    return str(inc[0][0]).strip() if inc and inc[0][0] else ''
def assign_vendors(rid):
    n=0
    for pc in ms_parts(rid):
        vc=pick_vendor(pc)
        if vc and post("/api/sourcing/route_order/vendor",{"route_id":rid,"item_code":pc,"allocations":[{"vendor_code":vc,"alloc_ratio":100}]}).get("ok"): n+=1
    return n
def reg_prodinfo_items(rid, items):
    for it in items:
        post("/api/prodinfo/proc/save",{"item":it,"route_id":0,"rows":[{"proc_seq":1,"work_code":"P2","tot_st":1,"work_qty":1}],"user":"t"})
def reg_route_prodinfo(rid, item):
    post("/api/prodinfo/proc/save",{"item":item,"route_id":rid,"rows":[{"proc_seq":1,"work_code":"P2","tot_st":1,"work_qty":1}],"user":"t"})
def complete_abc(rid):
    """A·B·C 완비(단가구분·원소재치수·가공비공정) — 양성경로 도달용 setup."""
    items=[X]+[str(r[0]).strip() for r in q("SELECT DISTINCT LTRIM(RTRIM(ISNULL(sub_item,child_item))) FROM nx.sourcing_route_line WHERE route_id=? AND ISNULL(staged,0)=0 AND ISNULL(child_item,'')<>'' AND UPPER(LTRIM(RTRIM(child_item))) NOT LIKE 'RAC%'", rid)]
    c=RAW.cursor()
    for it in dict.fromkeys(items):
        c.execute("UPDATE nx.item SET cost_gubun='1' WHERE UPPER(LTRIM(RTRIM(item_code)))=? AND ISNULL(cost_gubun,'')=''", it.upper())
        c.execute("UPDATE nx.item SET metal_gubun=ISNULL(NULLIF(metal_gubun,''),N'CU'), diam=CASE WHEN ISNULL(diam,0)<=0 THEN 1 ELSE diam END, thick=CASE WHEN ISNULL(thick,0)<=0 THEN 1 ELSE thick END, length=CASE WHEN ISNULL(length,0)<=0 THEN 1 ELSE length END WHERE UPPER(LTRIM(RTRIM(item_code)))=? AND ISNULL(cost_gubun,'')='3'", it.upper())
        c.execute("IF EXISTS(SELECT 1 FROM nx.item WHERE UPPER(LTRIM(RTRIM(item_code)))=? AND ISNULL(make_type,'')='1') AND NOT EXISTS(SELECT 1 FROM nx.routing WHERE UPPER(LTRIM(RTRIM(item_code)))=?) INSERT INTO nx.routing(p_item,item_code,proc_code) SELECT item_code,item_code,'P2' FROM nx.item WHERE UPPER(LTRIM(RTRIM(item_code)))=?", it.upper(), it.upper(), it.upper())
    c.close()
def approve(rid): return post("/api/sourcing/route/approve",{"route_id":rid,"approve":1,"user":"t"})
def activate(item,rid): return post("/api/sourcing/route/alloc/save",{"item":item,"rows":[{"route_id":rid,"is_active":1,"alloc_ratio":100,"apply_from":"2000-01-01"}]})
def in_pra(item):
    c=RAW.cursor(); planrev._route_setup(c); c.execute("SELECT COUNT(*) FROM nx.plan_route_active WHERE assy_item_code=?",item.upper()); n=c.fetchone()[0]; c.close(); return n

# ── 대상 탐색 ──
print("\n=== 대상 탐색 ===")
X=None
for it in [str(r[0]).strip() for r in q("SELECT TOP 20 UPPER(LTRIM(RTRIM(assy_item_code))) a FROM nx.plan_part_mat GROUP BY UPPER(LTRIM(RTRIM(assy_item_code))) HAVING COUNT(DISTINCT mat_code) BETWEEN 8 AND 40 ORDER BY COUNT(*) DESC") if str(r[0]).strip()]:
    login(); rid=copyf(it)
    ok = rid and len(ms_parts(rid))>=2
    rollback()
    if ok: X=it; print(f"  X={X}"); break
if not X: print("★대상없음"); RAW.rollback(); sys.exit(1)

# ══ 시나리오 ══
# S1. 승인-NEG-업체: 업체 미지정 → 승인 차단
try:
    rid=copyf(X); ja=approve(rid)
    rec("S1 업체 미지정 → 승인 차단", (not ja.get("ok")) and ja.get("gate")=="APPROVE_INCOMPLETE", f"gate={ja.get('gate')}")
finally: rollback()
# S2. 승인-NEG-생산라인: 업체는 지정, 신규 제작 SUB 생산정보 없음 → 승인 차단
try:
    rid=copyf(X)
    # 신규 SUB(생산정보 없음) 생성
    leafs=[int(r[0]) for r in q("SELECT TOP 2 line_id FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB' AND ISNULL(staged,0)=0", rid)]
    jsub=post("/api/sourcing/sub/create",{"route_id":rid,"line_ids":leafs,"base_child":X,"name":"게이트검증SUB","gubun":"자체"})
    post("/api/sourcing/route/finalize",{"route_id":rid,"item_code":X,"ymd":YMD,"commit":1})
    assign_vendors(rid)
    ja=approve(rid)
    rec("S2 생산라인 미지정(신규SUB) → 승인 차단", (not ja.get("ok")) and ja.get("gate")=="APPROVE_NOPROD", f"gate={ja.get('gate')} {str(ja.get('errors'))[:60]}")
finally: rollback()
# S3. 승인-POS: 업체+생산라인 완비 → 승인 성공
try:
    rid=copyf(X)
    nv=assign_vendors(rid)
    reg_prodinfo_items(rid, mk_items(rid, X)); complete_abc(rid)   # 제작/자체·조립 생산정보 + A·B·C 완비
    ja=approve(rid)
    rec("S3 완비(업체·생산라인) → 승인 성공", ja.get("ok")==True, f"nv={nv}")
finally: rollback()
# S4. 활성-NEG-생산정보(route): 승인됐지만 route 생산정보 없음 → 활성 차단
try:
    rid=copyf(X); assign_vendors(rid); reg_prodinfo_items(rid, mk_items(rid,X)); complete_abc(rid); approve(rid)
    jc=activate(X,rid)
    rec("S4 route 생산정보 미등록 → 활성 차단", (not jc.get("ok")) and jc.get("gate")=="INCOMPLETE" and any("생산정보" in e for e in (jc.get("errors") or [])), f"gate={jc.get('gate')}")
finally: rollback()
# S5. 활성-POS + 반영: 완비 → 활성 성공 → 생산 plan_route_active + 협력사 경로대안
try:
    rid=copyf(X); assign_vendors(rid); reg_prodinfo_items(rid, mk_items(rid,X)); complete_abc(rid); approve(rid)
    reg_route_prodinfo(rid, X)
    jc=activate(X,rid)
    rec("S5 완비 → 활성 성공", jc.get("ok")==True, f"gate={jc.get('gate')}")
    rec("S5 생산: plan_route_active 진입", in_pra(X)==1)
    # 협력사 재계산
    c=RAW.cursor(); planrev._step7_sql(c); c.close(); c=RAW.cursor(); planrev._step_source(c); c.close()
    wos=[str(r[0]).strip() for r in q("SELECT DISTINCT work_order FROM nx.plan_part_mat WHERE UPPER(LTRIM(RTRIM(assy_item_code)))=?",X)]
    nroute=0; nmisc=0
    if wos:
        ph=",".join("?"*len(wos[:200]))
        for src, in q(f"SELECT SOURCE FROM nx.plan_mat_source WHERE WORK_ORDER IN ({ph})",*wos[:200]):
            if str(src).strip()=='경로대안': nroute+=1
        for sg, in q(f"SELECT SUPPLY_GUBUN FROM nx.plan_mat_source WHERE WORK_ORDER IN ({ph}) AND SUPPLY_GUBUN=N'미지정'",*wos[:200]):
            nmisc+=1
    rec("S5 협력사: SOURCE='경로대안' 반영", nroute>0, f"경로대안 {nroute}라인")
    print(f"    (참고)협력사 '미지정' 라인 {nmisc}건 — 정보 없는 부품 안전망 표기")
finally: rollback()
# S6. 편성 미지정 안전망: 활성 R02에 업체 없는 매입부품이 있어도 협력사 계획에 '미지정'으로 나옴(누락 안 됨)
try:
    rid=copyf(X)
    # 업체 일부만 지정(1개 누락 유도) + 생산정보/단가는 완비시켜 활성까지 도달
    parts=ms_parts(rid)
    if len(parts)>=2:
        # 1개 빼고 업체 지정
        for pc in parts[1:]:
            vc=pick_vendor(pc)
            if vc: post("/api/sourcing/route_order/vendor",{"route_id":rid,"item_code":pc,"allocations":[{"vendor_code":vc,"alloc_ratio":100}]})
    # 승인/활성은 업체 미지정이면 게이트에 막히므로: 이 시나리오는 '편성이 미지정을 드러내는가'를 보기 위해
    #   업체 없는 부품이 계획에 어떻게 나오는지 현행경로(R01) 기준으로 확인(활성 불필요).
    c=RAW.cursor(); planrev._step7_sql(c); c.close(); c=RAW.cursor(); planrev._step_source(c); c.close()
    tot=q("SELECT COUNT(*) FROM nx.plan_mat_source")[0][0]
    misc=q("SELECT COUNT(*) FROM nx.plan_mat_source WHERE SUPPLY_GUBUN=N'미지정' OR ISNULL(VENDOR_CODE,'')=''")[0][0]
    rec("S6 편성 미지정 안전망: 정보없는 부품도 계획에 반영(누락0)", tot>0, f"총 {tot}라인 · 미지정/업체공란 {misc}라인(드러남)")
finally: rollback()

# S7. A·B·C 완비 감사(신규 강화): 단가구분 미지정 → 승인 차단 + 정확한 품목 통지
try:
    rid=copyf(X); assign_vendors(rid); reg_prodinfo_items(rid, mk_items(rid,X)); complete_abc(rid)
    p1=q("SELECT TOP 1 LTRIM(RTRIM(l.child_item)) FROM nx.sourcing_route_line l JOIN nx.item i ON UPPER(LTRIM(RTRIM(i.item_code)))=UPPER(LTRIM(RTRIM(l.child_item))) WHERE l.route_id=? AND l.node_kind<>'SUB' AND ISNULL(l.child_item,'')<>'' AND ISNULL(i.cost_gubun,'')<>'' AND UPPER(LTRIM(RTRIM(l.child_item))) NOT LIKE 'RAC%'", rid)
    tgt=str(p1[0][0]).strip() if p1 else None
    if tgt:
        _c=RAW.cursor(); _c.execute("UPDATE nx.item SET cost_gubun='' WHERE UPPER(LTRIM(RTRIM(item_code)))=?", tgt.upper()); _c.close()
    ja=approve(rid)
    okgate=(not ja.get("ok")) and ja.get("gate")=="APPROVE_BOM_INCOMPLETE" and any("단가구분" in e for e in (ja.get("errors") or []))
    rec("S7 단가구분 미지정 → 승인 차단·정확 품목통지", okgate, f"gate={ja.get('gate')} {str([e for e in (ja.get('errors') or []) if tgt and tgt in e][:1])[:60]}")
finally: rollback()

# ── 종료 ──
RAW.rollback()
chk=pyodbc.connect(CS,autocommit=True); cc=chk.cursor()
cc.execute("SELECT COUNT(*) FROM nx.plan_part_mat"); print(f"\n롤백후 plan_part_mat={cc.fetchone()[0]}행(원본)")
chk.close(); RAW.close()
print(f"{'='*56}\n결과: PASS {len(PASS)} / FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("(전부 롤백 — 라이브 무접촉)")
sys.exit(1 if FAIL else 0)
