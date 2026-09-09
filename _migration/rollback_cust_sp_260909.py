# -*- coding: utf-8 -*-
"""SP 2개 거래처 치환 롤백 (2026-09-09)

■ 왜 롤백하나 — 실측으로 결과가 달라졌다
     SP_PR_4주간계획현황_LIVE   ['260901','260930','1','%','%','%','2148']
        행수는 1,055 로 같으나 값이 다르다 — 예: 0750 → 1352
     SP_PR_가공생산진척관리_260602 ['260908','260909','P2']
        606행 → 770행 (+164)

  치환 자체는 1:1 뷰인데 결과가 달라졌다 = **원래 읽던 대상이 달랐다**.
  가공생산진척관리는 무접두(from cm_m_cust) 였다 → TEST3.dbo(356행) 를 읽고 있었고,
  nx(361행) 로 바꾸니 조인 대상이 늘었다.

  ★어느 쪽이 옳은지는 별도 판단이 필요하다(레거시 화면과 대조).
    그 판단 전에는 **현행 동작을 유지**한다 — 오늘 컷오버 확인 중이라 값이 흔들리면 안 된다.
    코드 149곳 전환은 값 동일이 확인됐으므로 그대로 둔다(SP만 되돌린다).
"""
import sys, os, io, re
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

nx = _nx(); cur = nx.cursor()
cur.execute("SELECT sp_schema, sp_name, definition FROM nx.bk_sp_cust_260909")
rows = cur.fetchall()

print("=" * 90)
print(" SP 롤백 — nx.bk_sp_cust_260909 원본으로 복원")
print("=" * 90)
for sch, name, d in rows:
    d = str(d)
    alter = re.sub(r"\bCREATE\s+(PROCEDURE|PROC)\b", r"ALTER \1", d, count=1, flags=re.I)
    cur.execute(alter); nx.commit()
    print("   ✔ {}.{} 복원".format(sch, name))

print()
print(" 확인 — CM_M_CUST 참조가 돌아왔나")
RX = re.compile(r"\b(?:FROM|JOIN)\s+[\w\.\[\]]*\bCM_M_CUST\b(?![_\w])", re.I)
for sch, name, d in rows:
    cur.execute("""SELECT m.definition FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
                    WHERE o.name=?""", str(name))
    dd = str(cur.fetchone()[0])
    print("   {:<34s} {}곳".format(str(name), len(RX.findall(dd))))
nx.close()
