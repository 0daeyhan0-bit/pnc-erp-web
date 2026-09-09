# bom_line ↔ 레거시 구조 sync (옵션 A) — 실행·검증 로그 (2026-09-08)

> 배경: 신규 ERP 존재이유 = 신규 BOM 방식(소요엔진·클린 bom_line). "신규 BOM 방식 안 쓰는 코드"를 엔진으로 이관하려면 **bom_line이 레거시(현행)와 일치**해야 하는데, 재감사 결과 **bom_line이 레거시 대비 다필드 드리프트**(매일마이그가 미러만 sync·bom_line 미sync)였다. 대표 지시 = **A(bom_line↔레거시 구조 sync)·검증(원가/편성/소요 diff0) 필수·단계별.**
> 정본연계: `SOYO_ENGINE_RULE.md`(§1-10) · `MIRROR_CLEAN_DUAL_TABLE_AUDIT §6` · `BOMLINE_PROCMETA_GAP_260829.md`.

## 근본 진단
매일마이그(2026-09-08 재개)는 **미러(pr_m_item_bom)만** 레거시로 sync하고 **bom_line(클린)은 안 함** → 레거시 BOM 편집(9월분)이 bom_line에 미반영 → **다필드 드리프트**: gagong_proc·vir_item·except_flag·엣지존재·sagub_default·s_work·proc_gubun. 편성 소요(v_pr_bom)·prodsheet 재고차감이 이 드리프트만큼 레거시와 어긋남.
- 영향 규모(실측): reconcile+vir 영향 부모 **11개**(유효범위 3). 매우 국소적.
- **★차기 항구화**: 이 bom_line sync를 **매일마이그에 편입**해야 재발 방지(현재 누락 단계).

## 실행 (선행조건 = 매일마이그로 미러 최신화 완료 07:18~21)
| 단계 | 스크립트 | 결과 | 백업 |
|---|---|---|---|
| gagong_proc 빈값채움 | `r_bomline_procmeta_fill.py --commit` | gagong 42·s_work 139·proc_gubun 117 채움(빈값만) | nx.bom_line_procmeta_bak |
| gagong_proc 정합 | `r_bomline_gagongproc_align.py --commit` | 19행 PR 정합 | (동상) |
| except/엣지 정합 | `r_bomline_soyo_reconcile.py --commit` | except0→1 **42** · 엣지추가 **31** · qty_pr 7 | nx.bom_line_bak_soyorec / bom_header_bak_soyorec |
| vir_item 정합(신규) | `r_bomline_vir_align.py --commit` | 3행 PR 정합·잔여0 | nx.bom_line_vir_bak |
| (reconcile 후 재실행) procmeta_fill | 재실행 | s_work 31·proc_gubun 31(추가엣지 채움) | (동상) |

## 검증 (게이트 — 전부 통과 or 진행중)
| 검증 | 방법 | 결과 |
|---|---|---|
| **원가 diff0** | 영향 11부모 `NxCostEngine.silwon` before/after | ✅ **변동 0** (reconcile 후·vir 후 각각) — cost는 cs_calc_except만 필터라 무영향 확인 |
| **생산계획 무영향(gagong)** | planrev _step7 gagong_proc 소스 코드확인 | ✅ 편성=PR_M_ITEM_PROC_GAGONG+PR_M_WORK_SINGLE 사용(bom_line.gagong_proc 미참조) |
| **prodsheet 소요 diff0** | `_bom_expand`(미러) vs `prod_input_soyo`(bom_line) 300표본 비-Q1000 | 97.3%→**99.7%**(299/300). AJR73364008·AEG74589808 해소 |
| 잔여 1(AGF30058404) | 근인 | **sagub_default 드리프트**(AGF30058504→MAF: 미러0/클린1). 다필드 드리프트의 다음 필드 |

## sagub_default 단계 (2026-09-08 적용, `r_bomline_sagub_align.py` 신규·백업 nx.bom_line_sagub_bak)
- 적용: 76엣지 PR 정합(잔여0). 방향=PR_M_ITEM_BOM.SAGUB_FLAG(§3 정본).
- 검증: ✅**원가 diff0**(67부모 변동0·sagub는 원가 무영향) · ✅**prodsheet 완전 diff0**(AGF30058404 해소=마지막 잔차) · ✅**PR vs CS SAGUB 99.91% 동일**(42,246중 39만 상이).
- ⚠**중량정산 46부모 변동**: weight_explode(sagub≠1 동중량)가 sagub 교정으로 재산출. 대부분 **유효범위 밖**(유효범위 2~3). bom_line.sagub 드리프트 교정이라 **레거시로 수렴(정확)** 방향이나, `_explode_legacy`(5인자) standalone 호출 불가로 **중량==레거시 독립 자동검증은 미완**. → 협력사 정산금액 영향이라 **대표 판단 대기**(keep=sync정확 / rollback=중량 별도검증 후).

## ★생산계획 소요 diff0 검증 (일순위·대표 확정 "절대 맞아야") — 2026-09-08 PASS
sync 완료(gagong+except+vir+sagub) 후, 편성이 타는 **v_pr_bom(=bom_line) soyo == 미러 pr_m_item_bom soyo** 대조(유효범위 Assy·except≠1):
- **엣지 구조**: 미러만 **0** · 클린만 **0** (sync 전 32/184 → 완전 일치)
- **편성수량(USE_QTY_PR·dedup)**: 동일 **12,503** · 수량다름 **6**
- 그 6건 = **전부 RAC(용접봉)** → §1-10대로 BOM 자재소요 제외·공정(proc_weld/CS_T_ITEM_WELD ITEM_USE_QTY×1.5)으로 별도산출 → **편성 자재소요·용접원가 모두 무관**(값도 0.001~0.01 미세).
- ⟹ **생산계획 자재소요 = 레거시 완전 diff0**(용접봉 엔진별도 제외). 일순위 충족.
- 대표 지시: **사급정산(중량)은 협력사 견적 프로그램 재구축 기준으로 재설정** → sagub의 중량 46부모 변동은 그때 재기준(현 시점 무관). **sagub align 유지 확정.**

## 남은 단계 (단계별)
1. **[대표판단] sagub 중량영향 46부모 keep/rollback** — 중량정산 레거시 대사(compute_quote/CS 재계산)로 확정.
2. 잔여 필드(kitting 등) 있으면 동일 방식.
3. **매일마이그에 bom_line sync 편입**(항구화) — gagong/vir/except/sagub align 순서 포함.
4. 전부 diff0 도달 후 → prodsheet 등 BOM 소비자 엔진 스왑(#2~). **prodsheet는 이미 diff0 도달**(sagub 유지 전제).

## 롤백
백업: nx.bom_line_bak_soyorec·bom_header_bak_soyorec / nx.bom_line_procmeta_bak / nx.bom_line_vir_bak. 각 스크립트 역적용 또는 bak에서 복원.
