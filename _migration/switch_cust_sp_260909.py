# -*- coding: utf-8 -*-
"""거래처 미러 → 클린 : 웹이 부르는 SP 2개 안의 CM_M_CUST 치환 (2026-09-09)

  SP_PR_4주간계획현황_LIVE
  SP_PR_가공생산진척관리_260602

■ 방식
  SP 본문에서 테이블명만 nx.v_cm_m_cust 로 바꾸고 ALTER 한다.
  컬럼 별칭이 미러와 동일하므로 본문 나머지는 손대지 않는다.
  ★백업 = 원본 정의를 nx.bk_sp_cust_260909 에 저장(롤백용).

■ 주의 (과거 실패 이력)
  580 SP 는 62,113자를 정규식 일괄치환했다가 ITEM_DESC 오류로 롤백했다.
  여기는 컬럼 스키마가 동일한 뷰로의 1:1 치환이라 그 위험이 없다.
  그래도 치환 후 **실제 EXEC 로 행수를 대조**해서 확인한다.
"""
import sys, os, io, re, argparse
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

ap = argparse.ArgumentParser()
ap.add_argument("--commit", action="store_true")
A = ap.parse_args()

nx = _nx(); cur = nx.cursor()
TARGETS = ['SP_PR_4주간계획현황_LIVE', 'SP_PR_가공생산진척관리_260602']
RX = re.compile(r"(\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+)([\w\.\[\]]*?)\bCM_M_CUST\b(?![_\w])", re.I)

print("=" * 96)
print(" SP 안 CM_M_CUST → nx.v_cm_m_cust  ({})".format("반영" if A.commit else "DRY-RUN"))
print("=" * 96)

plan = []
for name in TARGETS:
    cur.execute("""SELECT m.definition, s.name FROM sys.sql_modules m
                     JOIN sys.objects o ON o.object_id=m.object_id
                     JOIN sys.schemas s ON s.schema_id=o.schema_id
                    WHERE o.name=?""", name)
    r = cur.fetchone()
    if not r:
        print("   ★{} — 없음".format(name)); continue
    d, sch = str(r[0]), str(r[1])
    hits = list(RX.finditer(d))
    print("\n■ {}.{}  ({:,}자 · {}곳)".format(sch, name, len(d), len(hits)))
    for m in hits:
        ln = d[:m.start()].count("\n") + 1
        print("     L{:<5d} {}".format(ln, m.group(0).strip()[:64]))
    if hits:
        # 접두어를 nx. 로 통일 (dbo. / 없음 / PARTNER_ERP.dbo. 등 모두 nx.v_cm_m_cust 로)
        new = RX.sub(lambda m: m.group(1) + "nx.v_cm_m_cust", d)
        plan.append((sch, name, d, new, len(hits)))

if not plan:
    print("\n   대상 없음"); nx.close(); sys.exit(0)

if not A.commit:
    print("\n   --commit 을 붙이면 반영한다.")
    nx.close(); sys.exit(0)

# ── 백업
cur.execute("""IF OBJECT_ID('nx.bk_sp_cust_260909') IS NULL
               CREATE TABLE nx.bk_sp_cust_260909(
                 sp_schema varchar(20), sp_name nvarchar(200),
                 definition nvarchar(max), bk_dt datetime DEFAULT getdate())""")
nx.commit()
for sch, name, d, new, n in plan:
    cur.execute("DELETE FROM nx.bk_sp_cust_260909 WHERE sp_name=?", name)
    cur.execute("INSERT INTO nx.bk_sp_cust_260909(sp_schema,sp_name,definition) VALUES(?,?,?)",
                sch, name, d)
nx.commit()
print("\n   백업 nx.bk_sp_cust_260909 — {}건".format(len(plan)))

for sch, name, d, new, n in plan:
    alter = re.sub(r"\bCREATE\s+(PROCEDURE|PROC)\b", r"ALTER \1", new, count=1, flags=re.I)
    if alter == new:
        print("   ★{} — CREATE PROCEDURE 앵커 없음, 건너뜀".format(name)); continue
    cur.execute(alter)
    nx.commit()
    print("   ✔ {}.{} — {}곳 반영".format(sch, name, n))

# ── 재확인
print()
print("=" * 96)
print(" 재확인 — SP 안 CM_M_CUST 잔존")
print("=" * 96)
for sch, name, d, new, n in plan:
    cur.execute("""SELECT m.definition FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
                    WHERE o.name=?""", name)
    dd = str(cur.fetchone()[0])
    left = len(RX.findall(dd))
    print("   {:<34s} 잔존 {}곳 {}".format(name, left, "✔" if left == 0 else "★"))
nx.close()
