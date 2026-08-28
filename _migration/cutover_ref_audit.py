# -*- coding: utf-8 -*-
"""컷오버 게이트 — 백엔드 SQL 이 참조하는 `nx.<객체>` 가 실제로 존재하는지 전수 감사.

정본 = `_schema/CUTOVER_CHECKLIST.md` 2번 (참조 테이블 nx 존재 감사)

왜 도구로 두나
  컷오버 당일에 이걸 손으로 짜면 그 자리에서 시간을 쓴다. 그리고 손으로 짠 감사는
  오탐이 섞인다 — 단순히 `nx.` 로 뽑으면 `nx.commit`/`nx.cursor`(커넥션 메서드)와
  `nx.item_code` 같은 별칭 컬럼이 25종이나 딸려와 "없는 참조"로 보고된다(2026-08-28 실측).
  ⟹ SQL 문맥(FROM/JOIN/INTO/UPDATE/DELETE FROM/EXEC)에서만 뽑는다.

무엇을 보나
  ① DB 에 없는 참조 = flip 하면 런타임 500 나는 자리
  ② 미러형(대문자) vs 클린형(소문자) = **컷오버 표면**. 미러형은 컷오버 후 죽는다.

사용
  python _migration/cutover_ref_audit.py

기준선 (2026-08-28)
  참조 236종 · DB 에 없는 참조 2종 → 둘 다 `sourcing.py` 의 **스키마 자가 마이그** 코드
  (`nx.sourcing_sagub_price_new` / `nx.sourcing_sub_price_new` — 만들고 곧바로 rename 한다.
   마이그가 이미 끝나서 없는 게 정상) ⟹ **실제 결손 0**
  미러형 64종 · 클린형 172종
"""
import io, sys, os, re, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
BE = r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\_wt_close\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
from common import _nx

PAT = re.compile(r"(?is)\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM|EXEC(?:UTE)?)\s+"
                 r"(?:PARTNER_ERP_TEST3\.)?nx\.([A-Za-z_][A-Za-z0-9_]*)")
refs = {}
for f in sorted(glob.glob("*.py") + glob.glob("routers/*.py")):
    src = io.open(f, encoding='utf-8', errors='replace').read()
    for m in PAT.finditer(src):
        refs.setdefault(m.group(1).upper(), {"name": m.group(1), "files": set()})["files"].add(f)

c = _nx().cursor()
have = {}
c.execute("""SELECT o.name, o.type FROM PARTNER_ERP_TEST3.sys.objects o
             JOIN PARTNER_ERP_TEST3.sys.schemas h ON o.schema_id=h.schema_id WHERE h.name='nx'""")
for n, t in c.fetchall(): have[n.upper()] = t.strip()
c.execute("""SELECT s.name FROM PARTNER_ERP_TEST3.sys.synonyms s
             JOIN PARTNER_ERP_TEST3.sys.schemas h ON s.schema_id=h.schema_id WHERE h.name='nx'""")
for (n,) in c.fetchall(): have[n.upper()] = 'SN'

print(f"=== SQL 이 참조하는 nx.<객체> {len(refs)}종 · DB 의 nx 객체 {len(have)}종 ===")
missing = {k: v for k, v in refs.items() if k not in have}
print(f"\n★DB 에 없는 참조: {len(missing)}종")
for k in sorted(missing):
    v = missing[k]
    print(f"   nx.{v['name']:<34} ← {', '.join(sorted(v['files']))}")
if not missing:
    print("   (없음 — 참조는 전부 실재한다)")

mir = sorted(v['name'] for k, v in refs.items() if v['name'] == v['name'].upper())
cln = sorted(v['name'] for k, v in refs.items() if v['name'] != v['name'].upper())
print(f"\n=== 컷오버 표면 ===")
print(f"   미러형(대문자, 레거시 미러) {len(mir)}종  ← 컷오버 후 죽는다")
print(f"   클린형(소문자)             {len(cln)}종")
print(f"\n   미러형 전체:")
for i in range(0, len(mir), 4):
    print("     " + "  ".join(f"{x:<28}" for x in mir[i:i+4]))
