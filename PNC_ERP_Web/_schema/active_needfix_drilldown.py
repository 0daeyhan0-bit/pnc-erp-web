# -*- coding: utf-8 -*-
"""양산중_조치필요 대표 드릴다운(하나씩 검토용) — 읽기전용. LG용접봉=가정신호(소요량 미사용)."""
import sys, io, re
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
def L(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
def N(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
lv = L().cursor(); nx = N().cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
def basew(x): return re.sub(r'(-\d+)+$', '', x)
def basep(x): return re.sub(r'(-(?:SUB\d*|S\d+|은납\d*|J\d+|\d+))+$', '', x)
nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item"); NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
def bomid(it):
    nx.execute("SELECT bom_id FROM nx.bom_header WHERE item_code=?", it); r=nx.fetchone(); return r[0] if r else None
def kids(it):
    b=bomid(it)
    if b is None: return []
    nx.execute("SELECT child_item FROM nx.bom_line WHERE bom_id=? ORDER BY seq", b)
    return [str(x[0]).strip() for x in nx.fetchall()]
def tree(it,d=0,seen=None):
    if seen is None: seen=set()
    if (it,d) in seen or d>2: return
    seen.add((it,d))
    tag=" ◀용접봉/은납" if it.upper().startswith("RAC") else ""
    print(f"      {'  '*d}└ {it} {('('+NAME.get(it,'')[:22]+')') if NAME.get(it) else ''}{tag}")
    for ch in kids(it): tree(ch,d+1,seen)
def lastprod(it):
    lv.execute("SELECT MAX(PROD_YMD),SUM(CASE WHEN PROD_YMD>='240801' THEN PROD_QTY ELSE 0 END) FROM PR_T_PROD_DTL WHERE ITEM_CODE=?", it)
    r=lv.fetchone(); y=str(r[0]).strip() if r[0] else ''; return (f"20{y[:2]}-{y[2:4]}-{y[4:6]}" if len(y)==6 else '없음', float(r[1] or 0))
def lg_weld(p):
    nx.execute("SELECT child_code,qty FROM nx.lg_bom WHERE parent_code IN (?,?) AND child_code LIKE 'RAC%'", p, basep(p))
    return [(str(r[0]).strip(), float(r[1])) for r in nx.fetchall()]

def drill(p, grp):
    fp, q24 = lastprod(p)
    print(f"\n{'='*70}\n▶[{grp}] {p} | {NAME.get(p,'(품명없음)')} | 최근생산={fp}(24M수량 {q24})")
    nx.execute("SELECT weld_item,use_qty FROM nx.proc_weld WHERE parent_item=? AND use_qty>0", p)
    print("  proc_weld(우리 소요량):", [(str(r[0]).strip(), float(r[1])) for r in nx.fetchall()])
    nx.execute("SELECT item_code,proc_code,work_qty FROM nx.routing WHERE p_item=? AND item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0", p)
    rt=[(str(r[0]).strip(),str(r[1]).strip(),float(r[2])) for r in nx.fetchall()]
    print("  routing 용접ST(51/28):", ", ".join(f"{a[1]}:ST{a[2]}" for a in rt) if rt else "없음")
    lg=lg_weld(p); print("  LG BOM 용접봉:", lg or "없음(가정: 용접공정 없을수도)")
    # CS 원천
    lv.execute("SELECT COUNT(*) FROM CS_T_ITEM_WELD WHERE P_ITEM_CODE=?", p)
    print("  CS_T_ITEM_WELD 원천:", "없음" if nx and lv.fetchone()[0]==0 else "있음")
    print("  BOM 구조:"); tree(p)
    # 점검질문
    if lg: q="실제 용접점 관경/횟수 확인 → CS_T_ITEM_WELD 입력하면 자동재계산 활성"
    elif rt: q="LG엔 없으나 routing 용접ST 있음 → 실제 용접인지/부자재인지 확인, 맞으면 관경입력"
    else: q="LG·routing 모두 용접ST 없음 → 용접공정 실재하나? 부자재(은납링 등)·제외 확인"
    print("  ▶점검질문:", q)

# 최다그룹=② LG無 대표 선두 + ① LG有 대표
REPS = [
  ("②LG無★첫", "AJJ74578314"), ("②LG無", "ADM73210506"), ("②LG無", "AJR74424615"),
  ("②LG無", "AJR71429409"), ("②LG無(ST無)", "5425AP7108C"), ("②LG無(ST無)", "AJR74942632-고압"),
  ("①LG有", "AJR73964602"), ("①LG有", "AJR77224504-S1-3"), ("①LG有", "AJR73327007-은납"),
  ("①LG有", "AJR75463001-SUB2"),
]
for grp, code in REPS:
    drill(code, grp)
