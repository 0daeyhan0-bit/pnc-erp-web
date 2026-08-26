# -*- coding: utf-8 -*-
"""r_sub_desc_suffix — SUB(자도번) 품명 앞에 접미사 병기 (멱등·일 마이그 루틴 편입).

목적: 사용자가 기존 서브품번(자도번)에 익숙 → SUB 품명 앞에 접미사 병기해 식별.
      실시간 표시 대신 마스터에 박아넣음(속도부담0·전화면 일관). 컷오버 부담0 원칙
      (CUTOVER_MUST_AND_DAILY_MIGRATION §D) = 매 sync 직후 이 스크립트 재실행(멱등).

대상: PARTNER_ERP_TEST3.nx.PR_M_ITEM.ITEM_DESC (displays 품명 원천).
      r_delta_sync 마스터=전체재복사라 매 sync가 라이브로 덮음 → sync 직후 실행 필요.

규칙(SUB_MATERIAL_INTEGRATION §18, 검증 scratchpad/suffix_rule_probe.py):
  접미사 = 코드 첫 '-' 뒤 전부. 품명 = '[-{접미사}] {원품명}' (사용자 확정 2026-08-26, 자도번 -접미사 모양 그대로 대괄호).
  ★원품명(base) = 라이브 PR_M_ITEM(무손상 원천) 직독 → 옛형식/재실행 자동교정(멱등, 프리픽스 누적 없음).
  skip: ①접미사없음(clean코드) ②원품명에 코드포함 ③이미 '[-접미사] '로 시작 ④원품명이 접미사로 시작.

사용: python r_sub_desc_suffix.py        (DRY=미리보기, 쓰기 없음)
      python r_sub_desc_suffix.py --commit  (nx.PR_M_ITEM UPDATE)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/NEW_ERP_1/PNC_ERP_Web/backend")
import common

COMMIT = "--commit" in sys.argv
T = "PARTNER_ERP_TEST3.nx.PR_M_ITEM"          # 쓰기 대상(nx 미러)
SRC = "PARTNER_ERP.dbo.PR_M_ITEM"             # 원품명 원천(라이브·무손상·RO)


def suffix_of(code):
    return code.split("-", 1)[1] if "-" in code else None


def pref(suf):
    return f"[-{suf}] "                        # 병기 프리픽스


def skip_reason(code, suf, base):
    if base.startswith(pref(suf)):
        return "이미병기(멱등)"
    if code in base:
        return "원품명에 코드포함"
    if base == suf or base.startswith(suf + "/") or base.startswith(suf + "-") or base.startswith(suf + " "):
        return "원품명이 접미사시작"
    return None


def main():
    nx = common._nx_tx()
    cur = nx.cursor()
    cur.execute("SELECT DISTINCT LTRIM(RTRIM(raw_item)) FROM PARTNER_ERP_TEST3.nx.sub_code_map WHERE ISNULL(raw_item,'')<>''")
    subs = [r[0] for r in cur.fetchall()]
    # 현재 nx 품명(비교용) + 라이브 원품명(base 원천)
    cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM {T}")
    cur_nx = {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}
    ro = common._conn(); rc = ro.cursor()
    rc.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM {SRC}")
    base_of = {str(r[0]).strip(): str(r[1]).strip() for r in rc.fetchall()}
    ro.rollback(); ro.close()

    updates = []           # (code, cur_nx, new)
    skips = {}
    for c in subs:
        suf = suffix_of(c)
        if suf is None:
            skips["접미사없음"] = skips.get("접미사없음", 0) + 1
            continue
        base = base_of.get(c)
        if base is None:
            skips["품명없음"] = skips.get("품명없음", 0) + 1
            continue
        r = skip_reason(c, suf, base)
        if r:
            skips[r] = skips.get(r, 0) + 1
            # 옛 형식 잔재 교정: skip이지만 nx가 base와 다르면 base로 리셋
            if cur_nx.get(c, base) != base:
                updates.append((c, cur_nx.get(c, ""), base))
            continue
        new = pref(suf) + base
        if cur_nx.get(c) != new:               # 이미 정확하면 no-op
            updates.append((c, cur_nx.get(c, ""), new))

    print(f"[{'COMMIT' if COMMIT else 'DRY'}] SUB={len(subs)}  변경대상={len(updates)}  skip={skips}")
    for c, o, n in updates[:8]:
        print(f"  {c}: '{o}' -> '{n}'")

    if COMMIT and updates:
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
