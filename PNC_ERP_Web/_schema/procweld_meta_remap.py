# -*- coding: utf-8 -*-
"""proc_weld meta_ok=0 잔여 매핑 정합 — legacy-grounded candidate + 엄격 역검증(재현되는 것만 승격).
근거 정규화:
  - 용접봉(weld_item) suffix: 레거시 CS_T_ITEM_WELD.ITEM_CODE=RAC*-N (변형) → base(RAC*) 동일계열
  - 부모(parent) suffix: nx.sub_variant_map(variant_item→base_item, 레거시 SUB 정본) + 접미사 strip
역검증(필수): 라우팅ST(51+28) × 도출원단위 × loss_factor(1.5) == use_qty(정본, round4). 통과만 meta_ok=1 승격.
★use_qty(정본) 불변 · 임의확정 금지(item_weld 실측 도출값만, 재현 실패시 미승격).
잔여(meta_ok=0)는 유형·사유·후보와 함께 CSV 목록화(사용자 판단용).
멱등: 반복 실행 가능."""
import sys, io, re, csv
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
from collections import defaultdict
CS = (f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
      f"DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
cn = pyodbc.connect(CS, autocommit=True); c = cn.cursor()
LF = 1.5
def baseweld(x):   # RAC 용접봉 base(끝 -N 반복 제거)
    return re.sub(r'(-\d+)+$', '', x)

# item_weld 인덱스
c.execute("SELECT item_code,weld_item,pipe_diam,ISNULL(weld_qty,0),ISNULL(use_qty,0) FROM nx.item_weld")
pair = defaultdict(lambda: {'wq': 0.0, 'use': 0.0, 'diam': (0.0, -1.0)})     # (parent,weld)
pbw  = defaultdict(lambda: {'wq': 0.0, 'use': 0.0, 'diam': (0.0, -1.0)})     # (parent, base(weld))
pall = defaultdict(lambda: {'wq': 0.0, 'use': 0.0, 'diam': (0.0, -1.0)})     # parent 전체
parents_iw = set()
for it, wi, pd, wq, use in c.fetchall():
    it = str(it).strip(); wi = str(wi).strip(); pd = float(pd); wq = float(wq); use = float(use)
    for d, k in ((pair, (it, wi)), (pbw, (it, baseweld(wi))), (pall, it)):
        a = d[k]; a['wq'] += wq; a['use'] += use
        if wq > a['diam'][1]: a['diam'] = (pd, wq)
    parents_iw.add(it)

# sub_variant_map: variant_item → base_item, common_sub
c.execute("SELECT variant_item, base_item, common_sub FROM nx.sub_variant_map")
var2base = {}
for r in c.fetchall():
    v = str(r[0]).strip(); var2base[v] = (str(r[1]).strip(), str(r[2]).strip())

def norm_parents(p):
    """부모 정규화 후보(자기 자신 + sub_variant base + common_sub + 접미사 strip)."""
    out = [p]
    if p in var2base:
        b, cs = var2base[p]
        if b: out.append(b)
        if cs: out.append(cs)
    s = re.sub(r'(-\d+)+$', '', p)
    if s != p: out.append(s)
    seen = set(); res = []
    for x in out:
        if x and x not in seen: seen.add(x); res.append(x)
    return res

# 라우팅ST(51+28)
c.execute("""SELECT p_item,item_code,SUM(work_qty) FROM nx.routing
    WHERE item_code LIKE 'RAC%' AND proc_code IN ('51','28') AND work_qty>0 GROUP BY p_item,item_code""")
rst = {(str(r[0]).strip(), str(r[1]).strip()): float(r[2]) for r in c.fetchall()}
# 품명
c.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item")
NAME = {str(r[0]).strip(): str(r[1]).strip() for r in c.fetchall()}

def match(use, st):
    """use==round4(st*unit*LF) 재현하는 candidate 반환: (unit,diam,rule) 또는 None."""
    if st <= 0: return None
    tgt = round(use, 4)
    return tgt

def try_promote(parent, weld, use):
    """candidate 순회 → 역검증 통과하는 (unit,diam,st,rule) 반환, 없으면 None. cand도 함께(후보표기용)."""
    st = rst.get((parent, weld), 0.0)
    cands = []  # (unit,diam,rule,src_desc)
    bw = baseweld(weld)
    for np in norm_parents(parent):
        rule_p = "self" if np == parent else "subvar/parent-norm"
        if (np, weld) in pair and pair[(np, weld)]['wq'] > 0:
            a = pair[(np, weld)]; cands.append((a['use']/a['wq'], a['diam'][0], f"exact({rule_p})", f"{np}/{weld}"))
        if (np, bw) in pbw and pbw[(np, bw)]['wq'] > 0:
            a = pbw[(np, bw)]; cands.append((a['use']/a['wq'], a['diam'][0], f"weld-variant({rule_p})", f"{np}/{bw}*"))
        if np in pall and pall[np]['wq'] > 0:
            a = pall[np]; cands.append((a['use']/a['wq'], a['diam'][0], f"parent-agg({rule_p})", f"{np}/ALL"))
    if st <= 0:
        return None, cands
    tgt = round(use, 4)
    for unit, diam, rule, src in cands:
        if abs(st*unit*LF - use) < 6e-5 or round(st*unit*LF, 4) == tgt:
            return (unit, diam, st, rule, src), cands
    return None, cands

# 대상: meta_ok=0 & use>0
c.execute("SELECT id,parent_item,weld_item,ISNULL(use_qty,0) FROM nx.proc_weld WHERE ISNULL(meta_ok,0)=0 AND use_qty>0")
targets = [(r[0], str(r[1]).strip(), str(r[2]).strip(), float(r[3])) for r in c.fetchall()]
promo = []      # (id,unit,diam,st) → meta_ok=1
remain = []     # 잔여 목록
for pid, parent, weld, use in targets:
    hit, cands = try_promote(parent, weld, use)
    if hit:
        unit, diam, st, rule, src = hit
        promo.append((pid, diam, unit, st, rule))
    else:
        # 사유 판정
        st = rst.get((parent, weld), 0.0)
        if (parent, weld) in pair:
            reason = "c_수기override(exact쌍 값불일치)"
        elif st <= 0:
            reason = "라우팅ST(51/28)없음→재계산불가"
        elif parent in parents_iw or any(np in parents_iw for np in norm_parents(parent)):
            reason = "부모존재_후보재현실패(관경/용접봉발산)"
        else:
            reason = "e_item_weld에 부모전무"
        best = ""
        if cands:
            u, d, rl, sc = cands[0]
            best = f"{sc} unit={round(u,6)} diam={d} (rule={rl}, exp={round(st*u*LF,5) if st>0 else 'NA'})"
        remain.append({"parent_item": parent, "weld_item": weld, "item_name": NAME.get(parent, ""),
                       "use_qty": round(use, 6), "routing_st": st, "reason": reason, "best_candidate": best})

# 배치 승격(스테이징)
if promo:
    c.execute("IF OBJECT_ID('tempdb..#pm') IS NOT NULL DROP TABLE #pm")
    c.execute("CREATE TABLE #pm(id INT PRIMARY KEY, pipe_diam FLOAT, unit_qty FLOAT, weld_st FLOAT)")
    cur2 = cn.cursor(); cur2.fast_executemany = True
    cur2.executemany("INSERT INTO #pm(id,pipe_diam,unit_qty,weld_st) VALUES(?,?,?,?)",
                     [(pid, diam, unit, st) for pid, diam, unit, st, rule in promo])
    c.execute("""UPDATE p SET p.pipe_diam=m.pipe_diam, p.unit_qty=m.unit_qty, p.weld_st=m.weld_st, p.meta_ok=1, p.loss_factor=ISNULL(p.loss_factor,1.5)
                 FROM nx.proc_weld p JOIN #pm m ON m.id=p.id""")
    c.execute("DROP TABLE #pm")

rule_cnt = defaultdict(int)
for _,_,_,_,rule in promo: rule_cnt[rule] += 1
print(f"승격(역검증 통과): {len(promo)}행")
for k,v in sorted(rule_cnt.items(), key=lambda x:-x[1]): print(f"   rule[{k}]: {v}")
c.execute("SELECT COUNT(*), SUM(CASE WHEN meta_ok=1 THEN 1 ELSE 0 END) FROM nx.proc_weld")
r = c.fetchone()
print(f"최종 meta_ok=1: {r[1]}/{r[0]} ({round(100*r[1]/r[0],1)}%)")

# 잔여 CSV
out = r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\procweld_unmapped.csv"
with io.open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["parent_item","weld_item","item_name","use_qty","routing_st","reason","best_candidate"])
    w.writeheader()
    for row in sorted(remain, key=lambda x:(x["reason"], x["parent_item"])): w.writerow(row)
rc = defaultdict(int)
for row in remain: rc[row["reason"]] += 1
print(f"\n잔여 meta_ok=0(use>0): {len(remain)}행 — 유형별:")
for k,v in sorted(rc.items(), key=lambda x:-x[1]): print(f"   {k}: {v}")
print("CSV:", out)
cn.close()
