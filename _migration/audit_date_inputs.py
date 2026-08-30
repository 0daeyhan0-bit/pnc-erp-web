# -*- coding: utf-8 -*-
"""날짜 입력 전수 감사 — "2자리를 치면 1자리만 먹는" 버그 (2026-08-30)

증상
  `<input type="date">` 에서 일/월 세그먼트에 두 자리를 치면 첫 자리만 먹는다.

원인
  Chrome 은 date 입력의 값이 **유효해지는 순간마다** `change` 를 쏜다.
  일 세그먼트에 "1" 을 치면 그 순간 2026-08-01 → 이미 유효 → change 발생.
  이 change 가 조회·재렌더(`load()`/`draw()`)로 이어지면 **입력칸이 다시 그려져**
  포커스와 캐럿이 날아간다. 두 번째 자리는 갈 곳이 없다.
  ★전역 키인 핸들러 문제(2026-08-14 제거)와는 **다른 원인**이다. 그건 이미 없다.

무엇을 찾나
  날짜/월 입력의 change·input 핸들러가 **재렌더 함수로 이어지는가**.
  재렌더 = draw / render / load / go / apply / paint / refresh / show 계열 호출.

쓰는 법
  python _migration/audit_date_inputs.py            요약
  python _migration/audit_date_inputs.py --detail   화면별 상세
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web")
WEB = os.path.abspath(WEB)
DETAIL = "--detail" in sys.argv

# 재렌더로 이어지는 호출(이 이름이 핸들러 몸통에 있으면 화면이 다시 그려진다)
REDRAW = re.compile(r'\b(draw|render|load|go|apply|paint|refresh|reload|search|fetchList|list)\s*\(')
# 날짜/월 입력 태그에서 id 를 뽑는다
INP = re.compile(r'<input[^>]*type=["\'](date|month)["\'][^>]*>', re.I)
IDA = re.compile(r'\bid=["\']?([A-Za-z0-9_\-]+)|\bid=\$\{|\bid="\$\{')


def scan(path):
    src = io.open(path, encoding='utf-8', errors='replace').read()
    lines = src.split("\n")

    # ① 날짜/월 입력 id 수집
    ids = {}
    for m in INP.finditer(src):
        tag = m.group(0)
        ln = src[:m.start()].count("\n") + 1
        idm = re.search(r'id=["\']([A-Za-z0-9_\-]+)["\']', tag)
        key = idm.group(1) if idm else None
        cls = re.search(r'class=["\']([^"\']+)["\']', tag)
        ids.setdefault(key or f"(id없음 L{ln})", []).append((ln, m.group(1), cls.group(1) if cls else ""))

    # ② 각 id 의 change/input 바인딩을 찾아 재렌더 여부 판정
    findings = []
    for key, occ in ids.items():
        if key.startswith("(id없음"):
            findings.append((occ[0][0], key, "?", "id 없음 — 바인딩 추적 불가(수동확인)"))
            continue
        pat = re.compile(r'''["'#\[]%s["'\]]?\s*\)?\s*\.\s*(onchange|oninput)\s*=\s*([^;\n]+)''' % re.escape(key))
        pat2 = re.compile(r'''getElementById\(\s*["']%s["']\s*\)\s*\.\s*(onchange|oninput)\s*=\s*([^;\n]+)''' % re.escape(key))
        pat3 = re.compile(r'''["']#%s["']\s*\)\s*\.\s*addEventListener\(\s*["'](change|input)["']\s*,\s*([^;\n]+)''' % re.escape(key))
        hits = list(pat.finditer(src)) + list(pat2.finditer(src)) + list(pat3.finditer(src))
        if not hits:
            findings.append((occ[0][0], key, "바인딩없음", "change 핸들러 없음 — 버튼 조회형(안전)"))
            continue
        for h in hits:
            ln = src[:h.start()].count("\n") + 1
            body = h.group(2).strip()
            # 화살표 인라인이면 그 자리에서, 이름만이면 그 함수 정의를 찾아 몸통을 본다
            target = body
            nm = re.match(r'^([A-Za-z_$][\w$]*)\s*$', body)
            risky = bool(REDRAW.search(body))
            why = body[:60]
            if nm:
                fn = nm.group(1)
                d = re.search(r'(?:const|let|var|function)\s+%s\s*=?\s*(?:\([^)]*\)|function[^{]*)\s*=?>?\s*\{' % re.escape(fn), src)
                if d:
                    seg = src[d.end():d.end() + 700]
                    risky = bool(REDRAW.search(seg))
                    why = f"{fn}() → " + (", ".join(sorted(set(REDRAW.findall(seg)))) or "재렌더 없음")
            findings.append((ln, key, "★위험" if risky else "안전", why))
    return findings


def main():
    tot = {"★위험": 0, "안전": 0, "바인딩없음": 0, "?": 0}
    rows = []
    for fn in sorted(os.listdir(os.path.join(WEB, "js"))):
        if not fn.endswith(".js"):
            continue
        p = os.path.join(WEB, "js", fn)
        for ln, key, verdict, why in scan(p):
            tot[verdict] = tot.get(verdict, 0) + 1
            rows.append((f"js/{fn}", ln, key, verdict, why))

    print("=" * 88)
    print("  날짜 입력 전수 감사 — change 가 재렌더로 이어지면 두 자리 입력이 깨진다")
    print("=" * 88)
    bad = [r for r in rows if r[3] == "★위험"]
    print(f"  전체 {len(rows)}개 · ★위험 {len(bad)} · 안전 {tot.get('안전',0)} · "
          f"핸들러없음 {tot.get('바인딩없음',0)} · 추적불가 {tot.get('?',0)}\n")

    if bad:
        print("  ── ★위험 (두 자리 입력이 깨진다) ──")
        cur = None
        for f, ln, key, v, why in bad:
            if f != cur:
                print(f"\n  [{f}]")
                cur = f
            print(f"    L{ln:<6} #{key:<14} {why}")

    if DETAIL:
        print("\n  ── 전체 ──")
        for f, ln, key, v, why in rows:
            print(f"    {v:<8} {f}:{ln} #{key}  {why}")


if __name__ == "__main__":
    main()
