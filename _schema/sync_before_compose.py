# -*- coding: utf-8 -*-
"""★생산계획 편성 전 마스터 동기화 — 5종 일괄 (2026-09-02 신설)

왜 필요한가
  레거시에서 마스터를 고치면 웹 클린본은 따라가지 않는다. 그대로 편성하면
  **계획이 옛 마스터로 짜인다.** 2026-09-02 실측으로 자재소요 −16,645(0.6%) 가
  전부 이 드리프트였고, 5종을 맞추자 **−16(0.0006%)** 까지 줄었다.
  ★편성 로직은 정상이었다 — 마스터만 낡았던 것이다.

돌리는 것 (순서 의미 있음: 계획입력 → BOM → 세트)
  1. 추가계획   nx.prod_plan_input  ← PR_T_PLAN_INPUT     (A/S·긴급 계획)
  2. 모델BOM    nx.PR_M_MODEL_BOM   ← PR_M_MODEL_BOM      (모델 → ASSY 도번)
  3. 전개제외   nx.bom_line.except_flag  ← EXCEPT_FLAG    ★소요를 가장 크게 바꾼다
  4. 소요량     nx.bom_line.qty          ← USE_QTY        + 중복링크 정리
  5. 세트제외   nx.bom_line.set_except   ← SET_EXCEPT_FLAG (세트입고·명세서용)

  ※ **링크 추가/삭제/교체**는 자동에 넣지 않는다 — 계층 구조가 레거시와 달라
    함부로 지우면 파트별계획이 깨진다(실측: 차0 → −18). 개별 판단이 필요하므로
    `sync_clean_item_bom_delta.py --item <상위품목>` 으로 건건이 확인한다.

★안전
  · 라이브는 읽기만(CLAUDE.md §1-1). 쓰기는 nx 뿐.
  · `--apply` 없이는 전부 dry-run(기본).
  · 각 스크립트가 자체 백업 테이블을 만든다.
  · ⚠ 돌린 뒤 **편성(①~⑤)을 다시 실행**해야 계획에 반영된다.
  · 편성 후 검증 = `python _schema/verify_plan_compose.py`

사용
    python _schema/sync_before_compose.py            # 조회만 — 무엇이 바뀌는지
    python _schema/sync_before_compose.py --apply    # 실제 동기화
"""
import sys, os, io, subprocess, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 동기화(없으면 조회만)')
ARG = AP.parse_args()

STEPS = [
    ('추가계획 (A/S·긴급)', 'sync_prod_plan_input_refresh.py'),
    ('모델BOM (모델→ASSY)', 'sync_model_bom.py'),
    ('★전개제외 except_flag', 'sync_except_flag.py'),
    ('★소요량 qty + 중복정리', 'sync_bom_qty.py'),
    ('세트제외 set_except', 'sync_set_except_flag.py'),
]

BAR = '=' * 78
print(BAR)
print(' 편성 전 마스터 동기화 — 5종  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print(BAR)

env = dict(os.environ, PYTHONIOENCODING='utf-8')
fail = []
summary = []

for i, (label, script) in enumerate(STEPS, 1):
    path = os.path.join(_HERE, script)
    if not os.path.exists(path):
        print(f'\n[{i}/5] {label}   ★스크립트 없음 — {script}')
        fail.append(label)
        continue
    print(f'\n[{i}/5] {label}   ({script})')
    print('─' * 78)
    cmd = [sys.executable, path] + (['--apply'] if ARG.apply else [])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=env)
    out = (r.stdout or '') + (r.stderr or '')
    # 핵심 줄만 추린다 — 전체는 개별 스크립트로 볼 것
    keep = [ln for ln in out.splitlines()
            if any(k in ln for k in ('불일치', '할 일', '요약', '검증', '✅', '★',
                                     '반영', '갱신', '신규', '삭제', '백업'))]
    for ln in keep[:14]:
        print('  ' + ln.strip())
    if r.returncode != 0:
        fail.append(label)
        print(f'  ★종료코드 {r.returncode}')
    summary.append((label, '실패' if r.returncode != 0 else 'OK'))

print('\n' + BAR)
print(' 요약')
for label, st in summary:
    print(f'   {"✅" if st == "OK" else "★"} {label}  {st}')
if fail:
    print(f'\n ★실패 {len(fail)}건 — 개별 스크립트로 확인할 것')
if not ARG.apply:
    print('\n ※ DRY-RUN 입니다. 실제로 동기화하려면 --apply 를 붙이세요.')
else:
    print('\n ⚠ ★편성(①~⑤)을 다시 실행해야 계획에 반영됩니다.')
    print('   검증: python _schema/verify_plan_compose.py')
print(BAR)
sys.exit(1 if fail else 0)
