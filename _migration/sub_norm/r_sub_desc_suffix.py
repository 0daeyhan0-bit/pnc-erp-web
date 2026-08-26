# -*- coding: utf-8 -*-
"""r_sub_desc_suffix — SUB(자도번) 품명 앞에 접미사 병기 (멱등·일 마이그 루틴 편입).

목적: 사용자가 기존 서브품번(자도번)에 익숙 → SUB 품명 앞에 접미사 병기해 식별.
      실시간 표시 대신 마스터에 박아넣음(속도부담0·전화면 일관). 컷오버 부담0 원칙
      (CUTOVER_MUST_AND_DAILY_MIGRATION §D) = 매 sync 직후 이 스크립트 재실행(멱등).

★대상 = 품명 마스터 2곳 (화면마다 읽는 원천이 다름):
  ① PARTNER_ERP_TEST3.nx.PR_M_ITEM.ITEM_DESC  — BOM구성·역전개 등(bom.py)
  ② PARTNER_ERP_TEST3.nx.item.item_name       — 실원가/원가엔진(nx_cost_engine silwon_nodes)
  둘 다 안 하면 화면 간 불일치(실원가 탭만 옛 품명). 2026-08-26 실측 발견.

규칙(SUB_MATERIAL_INTEGRATION §18):
  접미사 = 코드 첫 '-' 뒤 전부. 품명 = '[-{접미사}] {원품명}' (자도번 -접미사 모양 그대로 대괄호).
  ★base(원품명) = 현재값에서 '[-{접미사}] ' 프리픽스 제거(self-heal) → 프리픽스 누적 없음·멱등.
    (라이브 재복사든 nx-native든 무관하게 안전. 재실행/옛형식 자동교정.)
  skip: ①접미사없음(clean코드) ②원품명에 코드포함 ③원품명이 접미사시작.

사용: python r_sub_desc_suffix.py        (DRY=미리보기, 쓰기 없음)
      python r_sub_desc_suffix.py --commit  (양쪽 마스터 UPDATE)
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/NEW_ERP_1/PNC_ERP_Web/backend")
import common

COMMIT = "--commit" in sys.argv
# (테이블, 코드컬럼, 품명컬럼)
TARGETS = [
    ("PARTNER_ERP_TEST3.nx.PR_M_ITEM", "ITEM_CODE", "ITEM_DESC"),
    ("PARTNER_ERP_TEST3.nx.item", "item_code", "item_name"),
]
_PREF = re.compile(r"^\[-[^\]]*\]\s+")     # 기존 '[-xxx] ' 프리픽스


def suffix_of(code):
    return code.split("-", 1)[1] if "-" in code else None


def base_of(cur_val, suf):
    """현재 품명에서 '[-{suf}] ' 프리픽스 제거 → 원품명(멱등 base)."""
    p = f"[-{suf}] "
    if cur_val.startswith(p):
        return cur_val[len(p):]
    return _PREF.sub("", cur_val, count=1) if cur_val.startswith("[-") else cur_val


def skip_reason(code, suf, base):
    if code in base:
        return "원품명에 코드포함"
    if base == suf or base.startswith(suf + "/") or base.startswith(suf + "-") or base.startswith(suf + " "):
        return "원품명이 접미사시작"
    return None


def process(cur, subs, tbl, ccol, dcol):
    cur.execute(f"SELECT {ccol}, ISNULL({dcol},'') FROM {tbl}")
    cur_val = {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}
    updates = []; skips = {}
    for c in subs:
        suf = suffix_of(c)
        if suf is None:
            skips["접미사없음"] = skips.get("접미사없음", 0) + 1
            continue
        v = cur_val.get(c)
        if v is None:
            skips["품명없음"] = skips.get("품명없음", 0) + 1
            continue
        base = base_of(v, suf)
        r = skip_reason(c, suf, base)
        if r:
            skips[r] = skips.get(r, 0) + 1
            if v != base:                      # 프리픽스 잔재 → 원품명으로 리셋
                updates.append((c, v, base))
            continue
        new = f"[-{suf}] {base}"
        if v != new:
            updates.append((c, v, new))
    return updates, skips


def main():
    nx = common._nx_tx()
    cur = nx.cursor()
    cur.execute("SELECT DISTINCT LTRIM(RTRIM(raw_item)) FROM PARTNER_ERP_TEST3.nx.sub_code_map WHERE ISNULL(raw_item,'')<>''")
    subs = [r[0] for r in cur.fetchall()]
    total = 0
    for tbl, ccol, dcol in TARGETS:
        try:
            updates, skips = process(cur, subs, tbl, ccol, dcol)
        except Exception as e:
            print(f"[{tbl}] SKIP (오류: {str(e)[:80]})")
            continue
        print(f"[{'COMMIT' if COMMIT else 'DRY'}] {tbl}: SUB={len(subs)} 변경={len(updates)} skip={skips}")
        for c, o, n in updates[:4]:
            print(f"    {c}: '{o}' -> '{n}'")
        if COMMIT and updates:
            cur.fast_executemany = True
            cur.executemany(f"UPDATE {tbl} SET {dcol}=? WHERE {ccol}=?", [(n, c) for c, o, n in updates])
            total += len(updates)
    if COMMIT:
        nx.commit()
        print(f"[COMMIT] 총 {total}건 갱신 완료 (양쪽 마스터·멱등)")
    else:
        nx.rollback()
        print("[DRY] 쓰기 없음 (--commit 로 실제 갱신)")
    nx.close()


if __name__ == "__main__":
    main()
