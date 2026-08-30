# 컷오버 FLIP 워크리스트 (현행 main 기준·2026-08-30 확정)

> RUNBOOK Step7(일괄 flip)의 실제 대상. 브랜치 `feat/cutover-live-to-mirror`는 main보다 622커밋 stale → **현행 main에 재적용**해야 함.
> 백엔드 `PARTNER_ERP.dbo.<T>` 직독 96개를 전수판정: **FLIP 74 · KEEP 15 · CLEAN(마스터) 5 · 주석 2**.
> 판정기준: FLIP=신규데이터 계속 쌓이는 트랜잭션/재고/계획(동결 시 "얼어붙은 옛 값" 사고)→nx 미러. KEEP=대조/DEPRECATED/총평균 레거시재현/legacy토글/불변 월스냅샷 시드. CLEAN=마스터(§9-1)→nx.item / nx.price_*.

---

## FLIP 74개 — 컷오버 시 `PARTNER_ERP.dbo.X` → `PARTNER_ERP_TEST3.nx.X`
```
common.py       365, 521, 522, 533, 534, 604            (6·라이브∪nx 브리지·CUT)
live_api.py     440, 507, 564, 750, 766, 877, 878,       (12·리시빙/CUT/유니버스 브리지)
                894, 915, 927, 1014, 1273
close.py        525, 538, 550, 557, 564, 620,            (11·활성 이동평균 _mv_*·생산마감 _prd_*)
                873, 875, 981, 1295, 1902
cost.py         683                                       (1·실손익 판가=리시빙 가중평균)
gagong.py       586, 590, 597, 607, 608, 609, 610,       (10·가공 현재재고/현재실적 전량)
                681, 685, 731
gagongmove.py   445                                       (1·가공이동 전표)
kitting.py      148, 154, 183, 187, 204, 229, 269, 272,  (23·키팅 준비/충당 현재재고·출하)
                275, 278, 307, 663, 676, 696, 702, 718,
                749, 752, 758, 792, 1041, 1049
matexpect.py    227, 233, 240, 290, 295                  (5·실적소요 드라이버·매입실적)
salesplan.py    235                                       (1·판매계획 LINE_NO)
sales.py        1522                                      (1·제품재고 FULL JOIN)
soyo.py         59, 93, 434                               (3·주문/AS계획/사급원가계획)
```
집중지점: **kitting/gagong/matexpect**(재고·출하·계획 현재값), **live_api·common**(라이브∪nx 브리지), **close `_mv_*`/`_prd_*`**(활성 평가법).

## CLEAN(마스터, §9-1) 5개 — ★보류(아침 사용자 논의 필요)
```
lgsagub.py  104, 105        CS_M_METERIAL_COST → nx.price_*  (절삭재료비 사급가·price 엔진 매핑 필요)
soyo.py     632, 633, 639   PR_M_ITEM         → nx.item      (routing_edge STEP7)
```
**보류 사유(2026-08-30 밤)**: ①soyo는 컬럼명 재매핑 필요(dbo.PR_M_ITEM.in_cust_code/make_type/work_code ↔ nx.item 컬럼명 상이) ②정본 충돌 — 메모리 [[newerp-nxitem-reader-migration]] "**soyo dbo STEP7만 보존**"(리더이관 시 의도적 잔존) + nx.PR_M_ITEM 미러는 **물리drop 컷오버대기**라 미러로도 못 감 ③lgsagub는 price 엔진 매핑. → 성급한 전환 금지, **컷오버 전 사용자와 방향 확정**(nx.item 클린으로 정합 vs STEP7 예외 유지). 현재 dbo 직독이라 병행운영 중엔 정상 동작. **컷오버 차단요인 여부도 함께 판단**(마스터는 신규 품목 드물어 프로즌 영향 작음).

## KEEP 15개 — 일부러 레거시에 둠(바꾸면 안 됨)
```
close.py    150, 162        _snap_mat_movavg_old ("★★사용금지·교정 전후 대조")
close.py    213, 386, 440, 692  총평균 _ta_*/시드 (레거시 재현·불변 월마감. 386=PR_M_ITEM_COST 마스터지만 재현목적 KEEP)
close.py    332, 344, 356, 363, 369  _ta_build 총평균법 "레거시 정본/대조용 보존"
coopplan.py 24, 376         legacy 토글 / _planstatus_legacy 재현(읽기전용)
live_api.py 875             _U src=live 순수 대조모드
common.py   541             PR_T_MONTH_STOCK_WH '2502' 고정 스냅샷(불변 시드)
```

## 주석/독스트링(대상 아님) 2개
```
cost.py 650 · kitting.py 582
```

---

## 적용 방법(flip 브랜치와 동일)
1. 각 FLIP 참조를 `PARTNER_ERP.dbo.<T>` → `PARTNER_ERP_TEST3.nx.<T>` (대소문자 nx 미러명 확인 — 27종 전부 존재 검증됨)
2. CLEAN 5개는 `nx.item` / `nx.price_*`로(§9-1·엔진경유 우선)
3. KEEP 15개·주석 2개는 **손대지 않음**
4. 검증: `mirror_recon.py` GREEN · flow testbed(flow_server 8099 + scenarios) PASS·오염0 · 원가 diff0 게이트 · 재고 게이트 차단확인
5. dev(8013) 실화면 확인 후 PR → 컷오버 당일 배포

## 상태
- [ ] FLIP 74 적용   - [ ] CLEAN 5 적용   - [ ] 검증(recon/flow/cost/gate)   - [ ] PR
