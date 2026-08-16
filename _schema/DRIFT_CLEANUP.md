# 드리프트 손상 정리 — 매핑·계획·기록 (2026-08-16)

> 목적: `드리프트복원`/소요툴이 nx.bom_line에 만든 손상(스퓨리어스 엣지 + 진짜자식 오배제)을 CS 정본에 맞춰 정리. LME 잔여5품목 + 가공 과교정/은납의 **공통 뿌리**.
> 원칙: 다축 플래그(원가 cs_calc_except / 소요 except_flag / 세트 set_except / 키팅 kitting) 독립 → **원가축만 CS정합**(다른 축 보존). 제자리 개별삭제 위험(BOM_MIRROR_DEBT §2). 배포 보류.
> 관련: [[BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE]] · LME_OVERCOUNT_ROOTCAUSE.md · GAGONG_ROUTING_MIGRATION.md

## 손상 전체 매핑 (실측)
### A. 드리프트복원 스퓨리어스 엣지 = 22 (CS_M_ITEM_BOM에 없음)
nx.bom_line remarks='드리프트복원' 중 CS에 없는 엣지. 부모: AJR30133707-SUB-1/-2·A-S-1/-2·AJR74482401-1(→4-1·MJU63706901-01)·AJR71429443·MJU63706901.
- 플래그 대부분: **cs_calc_except=0(원가 계상=이중계상 유발)·except_flag=1(소요 제외)·set_except=0·kitting=0**.
- **예외 A-S-2 그룹 6엣지**: kitting=1(키팅 대상)·일부 except_flag=0(소요 포함) → 다축 사용, 삭제 주의.

### B. 진짜자식 cs_calc_except=1 오배제 = 14 (nx=1, CS=0)
소요툴('[qtyfix 소요PR'·'[soyorec')이 원가축까지 잘못 배제. **AJR74482401-1→AJR74482401([soyorec])** = LME 잔여5품목 핵심. 그외 AJR30157801·AJR30012012·AET73831401-13-1 등 '[qtyfix 소요PR'.

## 정리 방침 (원가축만 CS정합, 다른 축 보존)
- **B(14)**: cs_calc_except 1→0 (진짜자식 원가 복원). except_flag 등 다른축 불변 → 소요 무영향.
- **A(22)**: cs_calc_except 0→1 (스퓨리어스 원가 제외=이중계상 해소). **행 삭제 아님**(except_flag/kitting 보존, 소요/키팅 무영향). = 원가만 CS정합, 다축 안전.
→ 이러면 제자리 삭제 위험 없이 **원가(LME+가공) diff0**, 소요/세트/키팅 불변.

## 검증 (진행중)
- 시뮬: 위 방침 적용 후 영향제품(AJR30133707·AJR30012101/102/103·AJR74462301·AJR74985204 등) LME+가공 diff0 확인 예정.

## 도구 (scratchpad)
- driftmap.py(손상 매핑)
