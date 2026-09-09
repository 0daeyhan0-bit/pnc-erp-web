# -*- coding: utf-8 -*-
"""bom_line ↔ 레거시(PR_M_ITEM_BOM) 구조 sync 오케스트레이터 — 매일마이그 2-e 단계.

왜: 매일마이그(delta_sync)는 미러(pr_m_item_bom)만 레거시로 sync하고 nx.bom_line(클린·편성/원가/소요 정본)은
    별도라 안 따라감 → 레거시 BOM 편집이 쌓이면 bom_line 이 다필드 드리프트(gagong·vir·except·엣지·sagub)
    → 생산계획 자재소요가 레거시와 어긋남(2026-09-08 실측·교정). 이 sync를 매일마이그에 넣어 항구 방지.

순서(중요):
  ① soyo_reconcile  = except_flag/엣지 존재를 PR 소요에 정합(엣지 추가/제외)  ← 먼저(엣지 확정)
  ② procmeta_fill   = 빈 공정메타(gagong_proc·s_work·proc_gubun 등) PR에서 채움(추가엣지 포함)
  ③ gagongproc_align= non-empty gagong_proc 차이 PR 정합
  ④ vir_align       = vir_item PR 정합(재귀 영향)
  ⑤ sagub_align     = sagub_default PR 정합
  ⑥ kitting_align   = kitting(KITTING_FLAG) PR 정합(키팅/준비재고체크 분류용·소요/원가 무영향)
전부 멱등·백업 자동. 검증: 후속 mirror_recon + (필요시) 편성 소요 diff0 대조.
★★생산계획 절대정확이 일순위(대표) → 편입 후 편성 소요 diff0 상시 확인.

사용: python _migration/sub_norm/r_bomline_sync.py --commit   (없으면 각 스크립트 DRY)
"""
import sys, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
COMMIT = '--commit' in sys.argv
STEPS = [
    ('① except/엣지 정합', 'r_bomline_soyo_reconcile.py'),
    ('② 공정메타 빈값채움', 'r_bomline_procmeta_fill.py'),
    ('③ gagong_proc 정합', 'r_bomline_gagongproc_align.py'),
    ('④ vir_item 정합', 'r_bomline_vir_align.py'),
    ('⑤ sagub_default 정합', 'r_bomline_sagub_align.py'),
    ('⑥ kitting 정합', 'r_bomline_kitting_align.py'),
]
print("=== bom_line 구조 sync %s ===" % ('(COMMIT)' if COMMIT else '(DRY)'))
for label, script in STEPS:
    print("\n--- %s : %s ---" % (label, script))
    args = [sys.executable, '-u', os.path.join(HERE, script)]
    if COMMIT:
        args.append('--commit')
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    tail = [ln for ln in (r.stdout or '').splitlines() if ln.strip()][-4:]
    print('\n'.join(tail))
    if r.returncode != 0:
        print("  ★오류 exit=%d" % r.returncode)
        print((r.stderr or '')[-300:])
        sys.exit(1)
print("\n=== bom_line sync 완료 ===")
