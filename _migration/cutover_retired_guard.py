# -*- coding: utf-8 -*-
"""컷오버 게이트 — **은퇴한 미러를 새 코드가 다시 읽는지** 검사한다.

정본 = `_schema/DO_NOT_USE_FIELDS.md` §14 (미러 은퇴 등록부)

왜 필요한가 (2026-08-28 실측으로 드러난 구멍)
  `nx.PR_M_ITEM` → `nx.item` 리더 이관은 PR#66~75 로 **코드 잔여 0** 을 달성했다.
  그런데 이틀 뒤 감사해 보니 **7곳이 되살아나 있었다.** 전부 이관 완료 *이후* 에 쓴 새 코드다.
      close.py:127(2026-08-27) · lgsagub.py:761(08-27) · planrev.py 5곳(08-26)
  규칙은 문서에만 있었고 **강제하는 장치가 없었다.**
  ⟹ 잔여를 0 으로 만드는 것보다, 0 을 **유지**하는 장치가 필요하다.
     안 그러면 컷오버 표면이 계속 자라고, 그만큼 컷오버 당일 할 일이 늘어난다.

사용
  python _migration/cutover_retired_guard.py          # 보고
  python _migration/cutover_retired_guard.py --strict # 잔여가 있으면 exit 1 (CI/훅용)

★검사 방법: SQL 문맥(FROM|JOIN|INTO|UPDATE|DELETE FROM|EXEC)에서만 뽑는다.
  그냥 이름으로 grep 하면 주석·문서 문자열이 걸려 오탐이 난다.
"""
import io, sys, os, re, glob

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend')

# 은퇴 등록부 — DO_NOT_USE_FIELDS §14. 정본이 생겨 미러를 읽으면 안 되는 것들.
RETIRED = {
    "PR_M_ITEM": ("nx.item", "품목 마스터. sgroup 소유권도 nx.item(PR#84) — 미러는 재분류 미반영"),
}

PAT_T = r"(?is)\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM|EXEC(?:UTE)?)\s+(?:PARTNER_ERP_TEST3\.)?nx\.{}\b"


def main():
    strict = '--strict' in sys.argv
    files = sorted(glob.glob(os.path.join(BE, "*.py")) + glob.glob(os.path.join(BE, "routers", "*.py")))
    total = 0
    print(f"=== 은퇴 미러 회귀 검사 · 대상 {len(RETIRED)}종 · 파일 {len(files)}개 ===\n")
    for name, (canon, why) in RETIRED.items():
        rx = re.compile(PAT_T.format(name))
        hits = []
        for f in files:
            src = io.open(f, encoding='utf-8', errors='replace').read()
            for m in rx.finditer(src):
                line = src[:m.start()].count("\n") + 1
                hits.append((os.path.relpath(f, BE).replace("\\", "/"), line))
        total += len(hits)
        mark = "★잔여" if hits else "✅ 0"
        print(f"  {mark}  nx.{name}  →  정본 {canon}")
        print(f"        {why}")
        for f, ln in hits:
            print(f"        · {f}:{ln}")
        print()
    print(f"=== 합계 잔여 {total}곳 ===")
    if total:
        print("  ⟹ 컷오버 표면이다. 정본으로 옮기고, 값이 달라지면 **왜 다른지 실측해 기록**할 것.")
        print("     (미러가 낡아 클린이 맞는 경우가 있다 — 예: sgroup 재분류 84건)")
    if strict and total:
        sys.exit(1)


if __name__ == "__main__":
    main()
