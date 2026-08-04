# -*- coding: utf-8 -*-
"""STEP1 — ①그룹 재현OK 10건 nx.item_weld 입력 + proc_weld.meta_ok 승격. nx만 쓰기(라이브 RO).
안전수칙: ①작업전 백업(_bak, 근거키=10부모) ②멱등(있으면 갱신/재실행안전) ③스코프=10부모만(대량삭제 금지) ④게이트 diff0.
입력 근거: group1_derive_40.csv match=OK. item_weld 행 = (parent, weld_item, pipe_diam, weld_qty, use_qty=std_use×횟수).
proc_weld.use_qty(정본)는 이미 역산으로 동일 → 값 불변, meta_ok만 True 승격 + pipe_diam/unit_qty/weld_st 메타 채움."""
import sys, io, re, csv
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
BAKTAG = "20260804_g1s1"
def N(): return pyodbc.connect(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}", autocommit=True)
cn = N(); c = cn.cursor()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 표준소요량/공수
c.execute("SELECT pipe_diam,MIN(std_use_qty),MIN(std_st) FROM nx.weld_diam GROUP BY pipe_diam")
STDU = {}; STDS = {}
for r in c.fetchall():
    d = round(float(r[0]), 2); STDU[d] = float(r[1]); STDS[d] = float(r[2])

# 재현OK 10건 파싱 (derived: '15.88φ×4' or '12.7φ×2 + 28.0φ×2')
rows = list(csv.DictReader(io.open(r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\_schema\group1_derive_40.csv", encoding="utf-8-sig")))
ok = [r for r in rows if r["match"] == "OK"]
def parse(dv):
    out = []
    for part in dv.split("+"):
        m = re.match(r'\s*([\d.]+)φ×(\d+)\s*', part)
        if m: out.append((round(float(m.group(1)), 2), int(m.group(2))))
    return out
parents = sorted(set(r["item"] for r in ok))
ph = ",".join("?" * len(parents))

# 1) 백업(멱등: 있으면 drop 후 재생성) — 근거키=10부모 스코프
for t, key in [("item_weld", "item_code"), ("proc_weld", "parent_item"), ("routing", "p_item")]:
    bak = f"nx.{t}_bak_{BAKTAG}"
    c.execute(f"IF OBJECT_ID('{bak}','U') IS NOT NULL DROP TABLE {bak}")
    c.execute(f"SELECT * INTO {bak} FROM nx.{t} WHERE {key} IN ({ph})", *parents)
    c.execute(f"SELECT COUNT(*) FROM {bak}")
    print(f"백업 {bak}: {c.fetchone()[0]}행")

# 2) item_weld 입력(멱등) — 스코프: 이 10부모+weld_item, 기존 삭제 후 재삽입
ins = 0
for r in ok:
    p = r["item"]; w = r["weld_item"]
    combo = parse(r["derived"])
    c.execute("DELETE FROM nx.item_weld WHERE item_code=? AND weld_item=?", p, w)  # 스코프 삭제(근거키)
    for d, k in combo:
        su = STDU.get(d, 0.0); uq = round(su * k, 6)
        # nx.item_weld 컬럼: item_code, weld_item, pipe_diam, weld_qty, use_qty
        c.execute("INSERT INTO nx.item_weld(item_code,weld_item,pipe_diam,weld_qty,use_qty) VALUES(?,?,?,?,?)", p, w, d, k, uq)
        ins += 1
print(f"item_weld 입력: {ins}행 ({len(ok)}부모)")

# 3) proc_weld 파생 갱신(멱등): meta_ok=True, pipe_diam/unit_qty/weld_st 채움. use_qty(정본)는 재계산해도 동일해야 함 → 대조
mism = []
for r in ok:
    p = r["item"]; w = r["weld_item"]
    combo = parse(r["derived"])
    sum_use = sum(STDU.get(d, 0) * k for d, k in combo)
    sum_cnt = sum(k for d, k in combo)
    recon = round(sum_use * 1.5, 6)   # loss_factor 1.5
    unit = round(sum_use / sum_cnt, 8) if sum_cnt else 0.0
    diam_rep = max(combo, key=lambda x: x[1])[0] if combo else 0.0
    c.execute("SELECT ISNULL(use_qty,0),ISNULL(loss_factor,1.5) FROM nx.proc_weld WHERE parent_item=? AND weld_item=?", p, w)
    row = c.fetchone(); cur_use = float(row[0]); lf = float(row[1] or 1.5)
    if abs(round(cur_use, 6) - round(recon * (lf / 1.5), 6)) > 6e-5:  # 정본 vs 재계산 대조
        mism.append((p, w, cur_use, recon))
    # meta 채움 (use_qty 정본 불변 — 덮어쓰지 않음)
    c.execute("UPDATE nx.proc_weld SET pipe_diam=?, unit_qty=?, weld_st=?, meta_ok=1 WHERE parent_item=? AND weld_item=?",
              diam_rep, unit, sum_cnt, p, w)
c.execute(f"SELECT COUNT(*) FROM nx.proc_weld WHERE parent_item IN ({ph}) AND meta_ok=1", *parents)
print(f"proc_weld meta_ok=1 승격: {c.fetchone()[0]}행")
print(f"정본 vs 재계산 불일치: {len(mism)} {mism if mism else '(없음 — use_qty 정본 보존 확인)'}")
print("STEP1 입력 완료 — 다음: 게이트 검증")
cn.close()
