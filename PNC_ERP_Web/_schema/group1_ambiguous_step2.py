# -*- coding: utf-8 -*-
"""STEP2 — ①그룹 애매 30건 유형별 목록(하나씩 확인용). 읽기전용, 쓰기 없음.
각 품번: BOM 자식관경 후보 · use_qty · routingST(=총 용접횟수) · 가능한 관경조합(복수해) · 재현실패 사유."""
import sys, io, re, csv
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
lv = pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True).cursor()
nx = pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True).cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
nx.execute("SELECT pipe_diam,MIN(std_use_qty),MIN(std_st) FROM nx.weld_diam GROUP BY pipe_diam")
DIAMS = []; STDU = {}; STDS = {}
for r in nx.fetchall():
    d = round(float(r[0]), 2); DIAMS.append(d); STDU[d] = float(r[1]); STDS[d] = float(r[2])
DIAMS.sort()
nx.execute("SELECT item_code, ISNULL(item_name,'') FROM nx.item"); NAME = {str(r[0]).strip(): str(r[1]).strip() for r in nx.fetchall()}
def child_diams(p):
    nx.execute("SELECT bom_id FROM nx.bom_header WHERE item_code=?", p); r = nx.fetchone(); ds = set()
    if r:
        nx.execute("SELECT child_item FROM nx.bom_line WHERE bom_id=?", r[0])
        for x in nx.fetchall():
            nx.execute("SELECT ISNULL(diam,0) FROM nx.item WHERE item_code=?", str(x[0]).strip()); rr = nx.fetchone()
            if rr and rr[0]:
                near = min(DIAMS, key=lambda z: abs(z - round(float(rr[0]), 2)))
                if abs(near - round(float(rr[0]), 2)) < 0.6: ds.add(near)
    return sorted(ds)
def m4(a, b): return abs(a - b) < 6e-5 or round(a, 4) == round(b, 4)
def all_sols(p, use, rst):
    cand = child_diams(p) or DIAMS[:]
    nu = round(use / 1.5, 6); ri = int(round(rst)) if rst > 0 else 0; sols = []
    for d in cand:
        if STDU[d] <= 0: continue
        k = nu / STDU[d]
        if abs(k - round(k)) < 0.01 and round(k) > 0 and m4(round(k) * STDU[d] * 1.5, use) and (ri == 0 or round(k) == ri):
            sols.append({d: round(k)})
    mx = ri if ri > 0 else 30
    for i in range(len(cand)):
        for j in range(i + 1, len(cand)):
            d1, d2 = cand[i], cand[j]
            if STDU[d2] <= 0: continue
            for k1 in range(0, mx + 1):
                rem = nu - k1 * STDU[d1]
                if rem < -1e-9: break
                k2 = rem / STDU[d2]
                if abs(k2 - round(k2)) < 0.01 and round(k2) >= 0 and (k1 + round(k2)) > 0:
                    k2 = round(k2)
                    if ((ri == 0) or (k1 + k2 == ri)) and m4((k1 * STDU[d1] + k2 * STDU[d2]) * 1.5, use):
                        s = {d: k for d, k in [(d1, k1), (d2, k2)] if k}
                        if s and s not in sols: sols.append(s)
    return cand, sols

rows = list(csv.DictReader(io.open(r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\group1_derive_40.csv", encoding="utf-8-sig")))
amb = [r for r in rows if r["match"] == "애매"]
out = []
for r in amb:
    p = r["item"]; use = float(r["use_qty"]); rst = float(r["routing_weldST"])
    cand, sols = all_sols(p, use, rst)
    kind = "다관경복수해" if len(sols) > 1 else "재현실패"
    combos = " | ".join("+".join(f"{d}φ×{k}" for d, k in sorted(s.items())) for s in sols[:5])
    if kind == "재현실패":
        reason = f"후보관경{cand} routingST(횟수)={rst} → 소요량/횟수 정수해 없음(수기값·rod혼재·관경부족 의심)"
    else:
        reason = f"{len(sols)}개 조합 성립(routingST={rst}{'·횟수제약없어 확정불가' if rst==0 else ''})"
    out.append({"item": p, "item_name": NAME.get(p, ''), "weld_item": r["weld_item"], "use_qty": use,
                "routing_weldST": rst, "child_diams": str(cand), "n_solutions": len(sols),
                "possible_combos": combos, "kind": kind, "reason": reason})

for path in [r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\group1_ambiguous_30.csv",
             r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\group1_ambiguous_30.csv"]:
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["item","item_name","weld_item","use_qty","routing_weldST","child_diams","n_solutions","possible_combos","kind","reason"])
        wr.writeheader()
        for r in sorted(out, key=lambda x: (x["kind"], x["item"])): wr.writerow(r)

mul = [r for r in out if r["kind"] == "다관경복수해"]; fail = [r for r in out if r["kind"] == "재현실패"]
print(f"애매 {len(out)}건: 다관경복수해 {len(mul)} · 재현실패 {len(fail)}")
print("\n=== 다관경복수해 대표(관경조합 후보) ===")
for r in mul[:8]:
    print(f"  {r['item']} | {r['item_name'][:18]} | use={r['use_qty']} ST={r['routing_weldST']} | 조합: {r['possible_combos'][:60]}")
print("\n=== 재현실패 대표(사유) ===")
for r in fail[:9]:
    print(f"  {r['item']} | {r['item_name'][:18]} | use={r['use_qty']} ST={r['routing_weldST']} | 자식관경{r['child_diams']}")
print("\nCSV: _schema/group1_ambiguous_30.csv (+scratchpad)")
