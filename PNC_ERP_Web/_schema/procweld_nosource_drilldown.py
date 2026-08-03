# -*- coding: utf-8 -*-
"""원천갭 형태별 대표 품번 드릴다운(하나씩 검토용) — 읽기전용.
품번·품명·생산구분 / BOM 트리(용접봉·은납 노드 표시) / proc_weld.use_qty / item_weld 원천유무(정규화·변형포함) / routing 용접ST / 원천부재 추정 / 점검포인트."""
import sys, io, re
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict
def L(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
def N(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
nx = N().cursor(); lv = L().cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item"); NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
lv.execute("SELECT ITEM_CODE, ISNULL(ITEM_STATUS,'') FROM PR_M_ITEM"); STAT = {str(r[0]).strip(): str(r[1]).strip() for r in lv.fetchall()}
nx.execute("SELECT DISTINCT item_code FROM nx.item_weld"); IWP = set(str(r[0]).strip() for r in nx.fetchall())
nx.execute("SELECT variant_item,base_item,common_sub FROM nx.sub_variant_map"); V2B = {str(r[0]).strip(): (str(r[1]).strip(), str(r[2]).strip()) for r in nx.fetchall()}
def norms(p):
    out=[p]
    if p in V2B:
        b,cs=V2B[p]
        if b: out.append(b)
        if cs: out.append(cs)
    for pat in [r'(-\d+)+$', r'(-(?:SUB\d*|S\d+|은납|J\d+|\d+))+$']:
        s=re.sub(pat,'',p)
        if s!=p: out.append(s)
    return list(dict.fromkeys(out))
def bomid(it):
    nx.execute("SELECT bom_id FROM nx.bom_header WHERE item_code=?", it); r=nx.fetchone(); return r[0] if r else None
def kids(it):
    b=bomid(it)
    if b is None: return []
    nx.execute("SELECT child_item,qty FROM nx.bom_line WHERE bom_id=? ORDER BY seq", b)
    return [(str(x[0]).strip(), float(x[1])) for x in nx.fetchall()]
def tree(it, d=0, seen=None):
    if seen is None: seen=set()
    if (it,d) in seen or d>3: return
    seen.add((it,d))
    tag=""
    if it.upper().startswith("RAC"): tag=" ◀용접봉/은납"
    nm=NAME.get(it,"")[:24]
    print(f"      {'  '*d}└ {it} {('('+nm+')') if nm else ''} {tag}")
    for ch,q in kids(it):
        tree(ch, d+1, seen)

def drill(p):
    print(f"\n{'='*70}\n▶ {p}  |  {NAME.get(p,'(품명없음)')}  |  상태={STAT.get(p,'?')}")
    # proc_weld
    nx.execute("SELECT weld_item,use_qty,pipe_diam,unit_qty,weld_st,ISNULL(meta_ok,0) FROM nx.proc_weld WHERE parent_item=? AND use_qty>0", p)
    pw=nx.fetchall()
    print("  [proc_weld 정본 소요량]:")
    for r in pw: print(f"     용접봉 {str(r[0]).strip()} ({NAME.get(str(r[0]).strip(),'')[:20]}) use_qty={r[1]} diam={r[2]} meta_ok={r[5]}")
    # item_weld 원천
    nx.execute("SELECT pipe_diam,weld_qty,use_qty FROM nx.item_weld WHERE item_code=?", p)
    ex=nx.fetchall()
    normhit=[x for x in norms(p) if x in IWP]
    print(f"  [item_weld 원천]: EXACT {len(ex)}행" + (f" {[(float(a[0]),int(a[1])) for a in ex]}" if ex else " (없음)"))
    print(f"     정규화/변형 후보 중 item_weld 보유: {normhit or '없음'}")
    # routing 용접
    nx.execute("SELECT item_code,proc_code,work_qty,prod_uph FROM nx.routing WHERE p_item=? AND item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0", p)
    rt=nx.fetchall()
    nx.execute("SELECT COUNT(*) FROM nx.routing WHERE p_item=? AND item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 AND ISNULL(prod_uph,0)=0", p)
    broken=nx.fetchone()[0]
    print(f"  [routing 용접ST(51/28)]: " + (", ".join(f"{str(r[1]).strip()}:ST{r[2]}/uph{r[3]}" for r in rt) if rt else "없음") + (f"  ★uph=0 파손 {broken}건" if broken else ""))
    # BOM 트리
    print("  [BOM 구조]:"); tree(p)

# 대표: (a)최다 선두 → 각 형태 3~5
REPS = [
  ("a★첫검토", "AJR34909302"), ("a", "AJJ73799402"), ("a", "AJR73972012"), ("a", "AJR76543201"),
  ("e", "AJR74984305-S3-1"), ("e", "AJR36852201-은납"), ("e", "AJR74364920-1-1(링)"),
  ("d", "AEG74589804(신창)"), ("d", "AJR77224009"), ("d", "AJR30125601-A-S-3"),
  ("b", "AJR75462809"), ("b", "AJR73964602"),
  ("f", "3A00280E"), ("f", "AJR30028405"),
  ("c", "AJR75023606"),
]
for form, code in REPS:
    print(f"\n\n########## 형태({form}) ##########", end="")
    drill(code)
