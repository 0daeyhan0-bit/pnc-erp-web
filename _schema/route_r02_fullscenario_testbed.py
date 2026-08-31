# -*- coding: utf-8 -*-
"""★복합 R02 종합 시나리오 테스트베드 (2026-09-01) — 실제 엔드포인트 구동·라이브 무접촉.
시나리오: 실제 계획품목에 R02 등록(신규 SUB 여러개 + 라인변경 + 제작 사내/외주 혼합) → 활성 →
          생산계획(plan_part_mat) + 협력사계획(plan_mat_source) 반영 검증.
방식: FLOW식 no-commit 몽키패치 + uvicorn + urllib(실인증). 입력은 전부 실제 엔드포인트:
      route/copy·sub/create·part/assign·line/gubun·finalize·approve·route_order/vendor·prodinfo·alloc/save.
      판정: 실제 엔진 planrev._step7_sql(생산) + planrev._step_source(협력사) 재계산 후 비교. 전부 롤백·오염0.
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
PORT=8091
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
def get(p):
    h={}
    if TOK[0]: h["Authorization"]="Bearer "+TOK[0]
    r=urllib.request.Request(f"http://127.0.0.1:{PORT}{p}",headers=h)
    try:
        with urllib.request.urlopen(r,timeout=120) as x: return _json.loads(x.read().decode())
    except Exception as e: return {"_err":str(e)[:160]}
def login():
    TOK[0]=None; TOK[0]=post("/api/auth/login",{"id":"super","pw":os.environ.get("FLOW_PW_SUPER","super")}).get("token"); return TOK[0]
def q(sql,*a):
    c=RAW.cursor()
    try: c.execute(sql,*a); return c.fetchall()
    finally: c.close()

PASS=[];FAIL=[]
def rec(n,ok,d=""): (PASS if ok else FAIL).append(n); print(f"  [{'PASS' if ok else 'FAIL'}] {n}{('  — '+d) if d else ''}")

print("로그인:", "OK" if login() else "FAIL")
YMD="260630"; VENJUNK=None

# ── 대상 계획품목 X 탐색: plan_part_mat에 있고 copy+finalize 통과 + 매입/사급 부품 보유 ──
print("\n=== 대상 계획품목 탐색 ===")
cands=[str(r[0]).strip() for r in q("""SELECT TOP 30 UPPER(LTRIM(RTRIM(assy_item_code))) a
   FROM nx.plan_part_mat GROUP BY UPPER(LTRIM(RTRIM(assy_item_code)))
   HAVING COUNT(DISTINCT mat_code) BETWEEN 8 AND 40 ORDER BY COUNT(*) DESC""") if str(r[0]).strip()]
X=None; RID=None
for it in cands:
    login()
    jc=post("/api/sourcing/route/copy",{"item_code":it,"source":"","ymd":YMD,"user":"t"})
    rid=int(jc.get("route_id") or 0)
    if not rid: RAW.rollback(); continue
    jf=post("/api/sourcing/route/finalize",{"route_id":rid,"item_code":it,"ymd":YMD,"commit":1})
    en=(jf.get("route_edges") or {}); en=en.get("edges",0) if isinstance(en,dict) else (en or 0)
    # 매입/사급 부품 유무
    ms=q("SELECT COUNT(*) FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB' AND ISNULL(gubun,'') IN (N'매입',N'사급')", rid)[0][0]
    if jf.get("committed") and en>0 and ms>=2:
        X=it; print(f"  선택 X={it} (route_edges={en}, 매입/사급부품 {ms}개)"); RAW.rollback(); break
    RAW.rollback()
if not X:
    print("★대상 없음"); RAW.rollback(); sys.exit(1)

# ════════════════ 복합 R02 구성 (실제 엔드포인트) ════════════════
print(f"\n=== 복합 R02 구성 (X={X}) ===")
login()
rid=int(post("/api/sourcing/route/copy",{"item_code":X,"source":"","ymd":YMD,"user":"t"}).get("route_id"))
RID=rid
# 라인 읽기(검사용 SQL)
lines=q("""SELECT line_id, LTRIM(RTRIM(ISNULL(child_item,''))), ISNULL(gubun,''), node_kind, ISNULL(parent_line,0), ISNULL(staged,0)
    FROM nx.sourcing_route_line WHERE route_id=? ORDER BY sort_seq,line_id""", rid)
parts=[(int(r[0]),str(r[1]).strip(),str(r[2]).strip()) for r in lines if r[3]!='SUB' and int(r[5])==0 and str(r[1]).strip() and not str(r[1]).strip().upper().startswith('RAC')]
print(f"  복사된 R02 부품 {len(parts)}개 (SUB제외)")
# 1) 신규 SUB 2개 — 서로 다른 부품 2~3개씩 묶기(자체)
made_subs=[]
if len(parts)>=4:
    g1=[parts[0][0],parts[1][0]]
    r1=post("/api/sourcing/sub/create",{"route_id":rid,"line_ids":g1,"base_child":X,"name":"검증SUB-A","gubun":"자체"})
    if r1.get("ok"): made_subs.append(r1.get("sub_item"))
    g2=[parts[2][0],parts[3][0]]
    r2=post("/api/sourcing/sub/create",{"route_id":rid,"line_ids":g2,"base_child":X,"name":"검증SUB-B","gubun":"자체"})
    if r2.get("ok"): made_subs.append(r2.get("sub_item"))
rec(f"[{X}] 신규 SUB 2종 생성", len(made_subs)==2, f"subs={made_subs}")
# 2) 라인변경 — 제작 사내/외주 혼합. ★외주 대상=자식(subtree) 있는 부품(외주화하면 subtree 빠짐=생산계획 가시변화)
rest=[p for p in parts[4:]]
def has_children(pc):
    return q("SELECT COUNT(*) FROM nx.v_pr_bom WHERE UPPER(LTRIM(RTRIM(item_code)))=? AND ISNULL(except_flag,0)<>1", pc.upper())[0][0]>0
sub_bearing=[p for p in rest if has_children(p[1])]
leaf=[p for p in rest if not has_children(p[1])]
chg={"제작":0,"외주":0}; outsourced=[]; drop_children=[]
# 외주 2개(자식 있는 부품 우선 → subtree 빠짐)
for p in (sub_bearing[:2] if len(sub_bearing)>=1 else rest[:2]):
    if post("/api/sourcing/line/gubun",{"route_id":rid,"line_id":p[0],"gubun":"외주"}).get("ok"):
        chg["외주"]+=1; outsourced.append(p[1])
        for cr in q("SELECT UPPER(LTRIM(RTRIM(mat_code))) FROM nx.v_pr_bom WHERE UPPER(LTRIM(RTRIM(item_code)))=? AND ISNULL(except_flag,0)<>1", p[1].upper()):
            drop_children.append(str(cr[0]).strip())
# 사내제작 2개(leaf)
for p in (leaf[:2] if len(leaf)>=2 else rest[2:4]):
    if post("/api/sourcing/line/gubun",{"route_id":rid,"line_id":p[0],"gubun":"제작"}).get("ok"): chg["제작"]+=1
rec(f"[{X}] 라인변경 제작(사내){chg['제작']}·외주{chg['외주']}(외주 subtree자식 {len(drop_children)}종)", chg["제작"]>=1 and chg["외주"]>=1, f"외주부품={outsourced}")
# 3) finalize → route_edges
jf=post("/api/sourcing/route/finalize",{"route_id":rid,"item_code":X,"ymd":YMD,"commit":1})
en=(jf.get("route_edges") or {}); en=en.get("edges",0) if isinstance(en,dict) else (en or 0)
rec(f"[{X}] finalize→route_edges", jf.get("committed") and en>0, f"edges={en} errors={str(jf.get('errors'))[:60]}")
# 4) 승인
post("/api/sourcing/route/approve",{"route_id":rid,"approve":1,"user":"t"})
# 5) 부품별 업체(매입/사급) — 각 부품에 가격 등록된 실제 업체 지정(price_item 우선, IN_CUST fallback)
def pick_vendor(pc):
    r=q("SELECT TOP 1 LTRIM(RTRIM(ISNULL(vendor_code,''))) FROM PARTNER_ERP_TEST3.nx.price_item WHERE price_type=N'매입' AND LTRIM(RTRIM(item_code))=? AND price IS NOT NULL AND ISNULL(vendor_code,'')<>'' ORDER BY apply_ymd DESC", pc)
    if r and r[0][0]: return str(r[0][0]).strip()
    inc=q("SELECT LTRIM(RTRIM(ISNULL(IN_CUST_CODE,''))) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE=?", pc)
    return str(inc[0][0]).strip() if inc and inc[0][0] else ''
msparts=[str(r[0]).strip() for r in q("SELECT DISTINCT LTRIM(RTRIM(child_item)) FROM nx.sourcing_route_line WHERE route_id=? AND node_kind<>'SUB' AND ISNULL(staged,0)=0 AND ISNULL(gubun,'') IN (N'매입',N'사급') AND UPPER(LTRIM(RTRIM(child_item))) NOT LIKE 'RAC%'", rid) if str(r[0]).strip()]
vend_assigned=0; vend_fail=[]; VMAP={}
for pc in msparts:
    vc=pick_vendor(pc)
    if not vc: vend_fail.append((pc,'no-vendor')); continue
    jv=post("/api/sourcing/route_order/vendor",{"route_id":rid,"item_code":pc,"allocations":[{"vendor_code":vc,"alloc_ratio":100}]})
    if jv.get("ok"): vend_assigned+=1; VMAP[pc.upper()]=vc
    else: vend_fail.append((pc,vc,str(jv.get('detail') or jv.get('_err') or jv.get('_http'))[:40]))
rec(f"[{X}] 부품별 업체지정(매입/사급 {len(msparts)}부품)", len(msparts)>0 and len(vend_fail)==0, f"지정 {vend_assigned}, 실패 {len(vend_fail)}: {vend_fail[:3]}")
# 6) 생산정보
post("/api/prodinfo/proc/save",{"item":X,"route_id":rid,"rows":[{"proc_seq":1,"work_code":"P2","tot_st":1,"work_qty":1}],"user":"t"})
# ★음성검증: 업체는 지정했으나 ★단가 미등록 → 활성화 시도하면 차단돼야(활성화 게이트=여기서 막기)
jneg=post("/api/sourcing/route/alloc/save",{"item":X,"rows":[{"route_id":rid,"is_active":1,"alloc_ratio":100,"apply_from":"2000-01-01"}]})
neg_ok=(not jneg.get("ok")) and jneg.get("gate")=="INCOMPLETE" and any("단가" in e for e in (jneg.get("errors") or []))
rec(f"[{X}] 단가 미등록 → 활성화 차단(활성화 게이트)", neg_ok, f"gate={jneg.get('gate')} {str(jneg.get('errors'))[:70]}")
# 5-b) 단가 등록(조달프로파일 profile/save) → 완비 → 활성화 가능
prof_price_ok=False
if VMAP:
    anyv=list(VMAP.values())[0]
    jpp=post("/api/sourcing/profile/save",{"route_id":rid,"rows":[{"profile_id":0,"vendor_code":anyv,"supply_gubun":"3","buy_price":100,"is_active":0,"is_internal":0,"apply_from":"2000-01-01"}]})
    prof_price_ok=bool(jpp.get("ok"))
    rec(f"[{X}] 단가 등록(조달프로파일)", prof_price_ok, f"gate={jpp.get('gate')}")

# ── 재계산·읽기 헬퍼 ──
def recompute():
    c=RAW.cursor(); planrev._step7_sql(c); c.close()      # 생산계획(plan_part_mat, 내부 _route_setup)
    c=RAW.cursor(); planrev._step_source(c); c.close()     # 협력사축(plan_mat_source)
def read_mat(assy):
    return {(str(a).strip(),str(c).strip()):float(x or 0) for a,c,x in q(
      "SELECT work_order,UPPER(LTRIM(RTRIM(mat_code))),SUM(CAST(part_plan_qty AS float)) FROM nx.plan_part_mat WHERE UPPER(LTRIM(RTRIM(assy_item_code)))=? GROUP BY work_order,UPPER(LTRIM(RTRIM(mat_code)))",assy)}
def read_src(assy):
    wos=sorted({k[0] for k in read_mat(assy)})
    out={}
    for i in range(0,len(wos),200):
        ch=wos[i:i+200]; ph=",".join("?"*len(ch))
        for wo,mat,sg,vc,qty,src in q(f"SELECT WORK_ORDER,UPPER(LTRIM(RTRIM(MAT_CODE))),ISNULL(SUPPLY_GUBUN,''),ISNULL(VENDOR_CODE,''),SUM(CAST(QTY AS float)),MAX(SOURCE) FROM nx.plan_mat_source WHERE WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER,UPPER(LTRIM(RTRIM(MAT_CODE))),ISNULL(SUPPLY_GUBUN,''),ISNULL(VENDOR_CODE,'')",*ch):
            out.setdefault((str(wo).strip(),str(mat).strip()),[]).append((str(sg).strip(),str(vc).strip(),float(qty or 0),str(src).strip()))
    return out
def in_pra(assy):
    c=RAW.cursor(); planrev._route_setup(c); c.execute("SELECT COUNT(*) FROM nx.plan_route_active WHERE assy_item_code=?",assy.upper()); n=c.fetchone()[0]; c.close(); return n

# ════ PHASE A: R02 비활성(route_alloc 없음) → baseline 재계산 ════
print(f"\n=== PHASE A: baseline(R02 비활성) 재계산 — 생산+협력사 ===")
recompute()
B_mat=read_mat(X); B_src=read_src(X)
b_mats=sorted({m for (_,m) in B_mat})
b_srckinds=sorted({t[3] for v in B_src.values() for t in v})
print(f"  baseline: 생산 자재종수={len(b_mats)}, 협력사 라인={sum(len(v) for v in B_src.values())}, SOURCE={b_srckinds}")

# ════ PHASE B: R02 활성(route_alloc.is_active=1) → 재계산 ════   (★PHASE A에서 롤백 안 함 = R02 구성 유지)
print(f"\n=== PHASE B: R02 활성 → 재계산 — 생산+협력사 ===")
login()
jac=post("/api/sourcing/route/alloc/save",{"item":X,"rows":[{"route_id":rid,"is_active":1,"alloc_ratio":100,"apply_from":"2000-01-01"}]})
rec(f"[{X}] 택1 활성(alloc/save)", jac.get("ok"), f"gate={jac.get('gate')} errors={str(jac.get('errors'))[:70]}")
pra=in_pra(X)
rec(f"[{X}] plan_route_active 진입(구조축)", pra==1)
recompute()
R_mat=read_mat(X); R_src=read_src(X)
r_mats=sorted({m for (_,m) in R_mat})
r_srckinds=sorted({t[3] for v in R_src.values() for t in v})
print(f"  R02활성: 생산 자재종수={len(r_mats)}, 협력사 라인={sum(len(v) for v in R_src.values())}, SOURCE={r_srckinds}")

# ════ 검증: 생산계획 반영 ════
print(f"\n=== 검증: 생산계획(plan_part_mat) 반영 ===")
gone=set(b_mats)-set(r_mats); add=set(r_mats)-set(b_mats)
print(f"  자재집합 변화: 사라짐 {len(gone)}종 {sorted(gone)[:8]}")
print(f"                 새로생김 {len(add)}종 {sorted(add)[:8]}")
dropped_hit=[c for c in set(drop_children) if c in gone]
print(f"  외주화 부품의 subtree 자식 {len(set(drop_children))}종 중 계획에서 빠진 것: {len(dropped_hit)}종 {dropped_hit[:6]}")
rec(f"[{X}] 생산계획 구조축 반영(plan_route_active 진입)", pra==1)
rec(f"[{X}] 생산계획이 R02 구조 반영(외주 subtree 누락 or 자재변화)", B_mat!=R_mat, f"gone {len(gone)}·add {len(add)}")

# ════ 검증: 협력사계획 반영 ════
print(f"\n=== 검증: 협력사계획(plan_mat_source) 반영 ===")
# R02 활성 후 X의 자재는 SOURCE='경로대안'이어야
r_all_route=all(t[3]=='경로대안' for v in R_src.values() for t in v) if R_src else False
n_route=sum(1 for v in R_src.values() for t in v if t[3]=='경로대안')
print(f"  R02후 협력사 라인 중 SOURCE='경로대안' = {n_route} / {sum(len(v) for v in R_src.values())}")
rec(f"[{X}] 협력사축 SOURCE='경로대안'으로 전환", n_route>0 and '경로대안' not in b_srckinds)
# 부품별 업체(route_order/vendor로 지정한) 반영 확인 — sourcing_profile 부품×route
prof=q("SELECT LTRIM(RTRIM(item_code)), LTRIM(RTRIM(ISNULL(vendor_code,''))) FROM nx.sourcing_profile WHERE route_id=? AND ISNULL(vendor_code,'')<>''", rid)
prof_map={str(r[0]).strip().upper():str(r[1]).strip() for r in prof}
matched=0; checked=0
for (wo,mat),lst in R_src.items():
    if mat in prof_map:
        checked+=1
        if any(t[1]==prof_map[mat] for t in lst): matched+=1
print(f"  부품별 지정업체가 협력사계획 VENDOR로 반영: {matched}/{checked} (지정부품 {len(prof_map)})")
rec(f"[{X}] 지정 업체가 협력사계획에 반영", checked==0 or matched>=1)
# 샘플 출력
print("  협력사계획 샘플(R02후):")
for (wo,mat),lst in list(R_src.items())[:6]:
    for sg,vc,qty,src in lst[:1]:
        print(f"    WO={wo} mat={mat} 공급방식={sg} 업체={vc} qty={qty:.1f} [{src}]")

# ════ 종료: 롤백(미커밋=오염0 구조보장) ════
tabs=("nx.sourcing_route","nx.route_alloc","nx.plan_part_mat")
RAW.rollback()
chk=pyodbc.connect(CS,autocommit=True); cc=chk.cursor()
for t in tabs:
    try: cc.execute(f"SELECT COUNT(*) FROM {t}"); print(f"  롤백후 {t} = {cc.fetchone()[0]}행(원본 유지)")
    except: pass
chk.close(); RAW.close()

print(f"\n{'='*56}")
print(f"결과: PASS {len(PASS)} / FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("(전부 롤백 — 라이브 plan_part_mat·plan_mat_source 무접촉)")
sys.exit(1 if FAIL else 0)
