# -*- coding: utf-8 -*-
"""r_sub_desc_suffix — SUB(자도번) 품명 앞에 접미사 병기 (멱등·일 마이그 루틴 편입).

목적: 사용자가 기존 서브품번(자도번)에 익숙 → SUB 품명 앞에 접미사 병기해 식별.
      실시간 표시 대신 마스터에 박아넣음(속도부담0·전화면 일관). 컷오버 부담0 원칙
      (CUTOVER_MUST_AND_DAILY_MIGRATION §D) = 매 sync 직후 이 스크립트 재실행(멱등).

대상: PARTNER_ERP_TEST3.nx.PR_M_ITEM.ITEM_DESC (displays 품명 원천).
      r_delta_sync 마스터=전체재복사라 매 sync가 라이브로 덮음 → sync 직후 실행 필요.

규칙(SUB_MATERIAL_INTEGRATION §18, 검증 scratchpad/suffix_rule_probe.py):
  접미사 = 코드 첫 '-' 뒤 전부. '{접미사} {품명}' prepend.
  skip: ①접미사없음(clean코드) ②품명에 코드포함 ③이미 '접미사 '로 시작(멱등) ④품명=접미사시작.
  실측: prepend 1,975 / skip 나머지. 재실행 멱등.

사용: python r_sub_desc_suffix.py        (DRY=미리보기, 쓰기 없음)
      python r_sub_desc_suffix.py --commit  (nx.PR_M_ITEM UPDATE)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/NEW_ERP_1/PNC_ERP_Web/backend")
import common

COMMIT = "--commit" in sys.argv
T = "PARTNER_ERP_TEST3.nx.PR_M_ITEM"


def suffix_of(code):
    return code.split("-", 1)[1] if "-" in code else None


def skip_reason(code, suf, nm):
    if nm.startswith(suf + " "):
        return "이미병기(멱등)"
    if code in nm:
        return "품명에 코드포함"
    if nm == suf or nm.startswith(suf + "/") or nm.startswith(suf + "-"):
        return "품명=접미사시작"
    return None


def main():
    nx = common._nx_tx()
    cur = nx.cursor()
    # SUB 스코프 = sub_code_map raw_item (등록 SUB 자도번)
    cur.execute("SELECT DISTINCT LTRIM(RTRIM(raw_item)) FROM PARTNER_ERP_TEST3.nx.sub_code_map WHERE ISNULL(raw_item,'')<>''")
    subs = [r[0] for r in cur.fetchall()]
    cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM {T}")
    desc = {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}

    updates = []           # (code, old, new)
    skips = {}
    for c in subs:
        suf = suffix_of(c)
        if suf is None:
            skips["접미사없음"] = skips.get("접미사없음", 0) + 1
            continue
        nm = desc.get(c)
        if nm is None:
            skips["품명없음"] = skips.get("품명없음", 0) + 1
            continue
        r = skip_reason(c, suf, nm)
        if r:
            skips[r] = skips.get(r, 0) + 1
            continue
        updates.append((c, nm, f"{suf} {nm}"))

    print(f"[{'COMMIT' if COMMIT else 'DRY'}] SUB={len(subs)}  prepend대상={len(updates)}  skip={skips}")
    for c, o, n in updates[:8]:
        print(f"  {c}: '{o}' -> '{n}'")

    if COMMIT and updates:
        # 멱등 UPDATE (근거키=item_code 스코프, 대량삭제 아님)
        cur.fast_executemany = True
        cur.executemany(f"UPDATE {T} SET ITEM_DESC=? WHERE ITEM_CODE=?", [(n, c) for c, o, n in updates])
        nx.commit()
        print(f"[COMMIT] {len(updates)}건 ITEM_DESC 갱신 완료 (멱등·재실행 안전)")
    else:
        nx.rollback()
        print("[DRY] 쓰기 없음 (--commit 로 실제 갱신)")
    nx.close()


if __name__ == "__main__":
    main()
