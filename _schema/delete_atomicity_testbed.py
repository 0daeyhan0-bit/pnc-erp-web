# -*- coding: utf-8 -*-
"""★삭제 로직 원자성 전수 검사 테스트베드(사용자 요구 2026-08-31·데이터손실 사고 후속).
   모든 라우터에서 '삭제(DELETE/쓰기 다중)' 함수를 자동 발견해 원자성 위험을 판정.

사고 패턴: 다중 삭제문 + `_nx()`(autocommit) + rollback 없음 → 중간 실패 시 부분삭제가 커밋돼 데이터 소실.
안전 조건: ①단일 삭제문(한 문장=원자) 또는 ②`_nx_tx()`(트랜잭션)+commit/rollback.

이 테스트베드는 **소스 정적검사**(DB 무접촉·오염0)로 전 삭제함수를 분류하고, HIGH 위험(원자화 필요)을 실패로 표시한다.
실행: python _schema/delete_atomicity_testbed.py
"""
import sys, os, io, importlib, inspect, re, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROUTERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend', 'routers')

def classify(src, is_del_fn):
    """함수 소스 → (위험도, 근거). ★진짜 데이터손실 위험 = 여러 '다른 테이블' cascade 삭제 + autocommit + rollback없음(사고패턴).
       is_del_fn=삭제성격 함수(이름 del/remove/cancel 또는 /delete 엔드포인트). replace-save(DELETE+INSERT)는 별도 등급."""
    del_tabs = set(t.lower() for t in re.findall(r'DELETE\s+FROM\s+([\w\.\[\]]+)', src, re.I))
    ndel = len(re.findall(r'DELETE\s+FROM', src, re.I))
    nwrite = len(re.findall(r'\b(DELETE\s+FROM|UPDATE\s+|INSERT\s+INTO)', src, re.I))
    has_insert = bool(re.search(r'INSERT\s+INTO', src, re.I))
    has_update = bool(re.search(r'\bUPDATE\s+', src, re.I))
    uses_tx = '_nx_tx()' in src
    uses_nx = bool(re.search(r'=\s*_nx\(\)', src))
    has_rollback = 'rollback' in src
    has_commit = 'commit' in src
    if ndel == 0 and nwrite == 0:
        return ("N/A", "쓰기 없음")
    if uses_tx and (has_commit or has_rollback):
        return ("SAFE", f"_nx_tx 트랜잭션(commit/rollback)")
    # ★cascade 삭제(다른 테이블 2개+ DELETE) = 부분실패 시 데이터손실(사고패턴)
    if len(del_tabs) >= 2:
        if uses_nx and not has_rollback:
            return ("HIGH", f"cascade 삭제 {len(del_tabs)}테이블({', '.join(sorted(del_tabs))[:60]}) + autocommit + rollback없음 → 부분삭제 데이터손실")
        if not has_rollback:
            return ("MED", f"cascade 삭제 {len(del_tabs)}테이블 · rollback없음")
        return ("MED-확인", f"cascade 삭제 {len(del_tabs)}테이블 · rollback있음")
    # 단일 테이블 DELETE(분기별 여러 DELETE 포함) = 실행당 원자
    if len(del_tabs) <= 1 and not (has_insert and is_del_fn):
        # 삭제+UPDATE 동반(예 승인리셋) 이면서 삭제함수 = 경미한 비원자
        if is_del_fn and has_update and uses_nx and not has_rollback and nwrite >= 2:
            return ("LOW-확인", f"삭제 1테이블 + 동반 UPDATE(autocommit) — 경미한 비원자(부분: UPDATE 누락 가능)")
        return ("LOW", f"삭제 {len(del_tabs)}테이블(실행당 원자)")
    # replace-save(DELETE+INSERT 같은개념) — 삭제프로그램 아님·별도
    if has_insert:
        return ("SAVE", f"replace 저장(DELETE+INSERT) — 삭제 아님. INSERT실패 시 구값소실 위험은 별건")
    return ("MED", f"쓰기 {nwrite} · 확인요")

rows = []
for path in sorted(glob.glob(os.path.join(ROUTERS_DIR, '*.py'))):
    mod = os.path.splitext(os.path.basename(path))[0]
    if mod.startswith('_'): continue
    try:
        m = importlib.import_module(f'routers.{mod}')
    except Exception as e:
        print(f'  (import skip {mod}: {str(e)[:50]})'); continue
    for name, fn in inspect.getmembers(m, inspect.isfunction):
        if getattr(fn, '__module__', '') != f'routers.{mod}': continue
        try: src = inspect.getsource(fn)
        except Exception: continue
        # 삭제 성격 함수만: 이름에 del 또는 소스에 DELETE FROM
        if not (re.search(r'del|remove|cancel|purge', name, re.I) or re.search(r'DELETE\s+FROM', src, re.I)):
            continue
        is_del_fn = bool(re.search(r'del|remove|cancel|purge', name, re.I)) or ('/delete' in src)
        lvl, why = classify(src, is_del_fn)
        if lvl in ("N/A", "SAVE"):
            continue   # replace-save·쓰기없음은 '삭제 프로그램' 범위 밖(별도)
        rows.append((mod, name, lvl, why))

order = {"HIGH": 0, "MED": 1, "MED-확인": 2, "LOW-확인": 3, "LOW": 4, "SAFE": 5}
rows.sort(key=lambda r: (order.get(r[2], 9), r[0], r[1]))

print(f"=== 삭제 함수 원자성 분류 (총 {len(rows)}) ===")
print(f"{'파일':14} {'함수':32} {'위험':6} 근거")
for mod, name, lvl, why in rows:
    print(f"{mod:14} {name:32} {lvl:6} {why}")

highs = [r for r in rows if r[2] == "HIGH"]
meds = [r for r in rows if r[2] == "MED"]
print(f"\n=== 판정 === HIGH {len(highs)} · MED {len(meds)} · LOW {len([r for r in rows if r[2]=='LOW'])} · SAFE {len([r for r in rows if r[2]=='SAFE'])}")
if highs:
    print("\n★★HIGH(원자화 필요·_nx_tx+rollback으로 고칠 것):")
    for mod, name, lvl, why in highs:
        print(f"  · {mod}.{name} — {why}")
if meds:
    print("\n★MED(연결방식·원자성 개별 확인):")
    for mod, name, lvl, why in meds:
        print(f"  · {mod}.{name} — {why}")

# 게이트: HIGH 있으면 FAIL
print(f"\n{'✗ 원자성 FAIL — HIGH 위험 삭제 존재' if highs else '✓ 원자성 PASS — HIGH 위험 삭제 없음'}")
print("✓DB 무접촉(정적 소스검사·오염0)")
