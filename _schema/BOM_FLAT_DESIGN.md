# nx.bom_flat — 레거시 평면전개 정본 BOM

> 대표 지시(2026-08-24): LG는 참고용, **우리 레거시 BOM을 평면전개**해서 쓰자(빠르고 품번 구성상 정확). 이론적 정본 BOM = 품번+수량+역할+치수+중량+원소재소요량+공정+용접, "누가/어떻게(라우팅)"에 종속.

## 1. 엔진 = _bom_tree_nx(real=1, expandbuy=1) 배치 재현
- 소스 = `nx.bom_line`(미러=우리 BOM, 화면 "품목 BOM관리" 소스). bom_header(제품→bom_id)·bom_line(bom_id→child).
- 규칙: **cs_calc_except=0**(현행)만 + bom_header 보유 자식은 전개(매입 SUB도)·**비현행 -F&T/변형 제외**. 재귀 최하위=재료 leaf. 수량=경로 롤업.
- 용접봉(RAC)=별도축(nx.proc_weld) → 재료 평면전개서 제외.
- ★검증: AJR75563402 = 화면 10 재료 leaf **정확 재현**(누락0·초과0·5006AR4091**H**).

## 2. 축(각 재료 leaf에 부착)
| 컬럼 | 내용 | 소스 |
|---|---|---|
| item_code / leaf_code | 제품 / 재료 우리품번 | bom_line 평면전개 |
| qty | 소요량(개수, 롤업) | bom_line.qty |
| role | 완성부품/제작동관/원소재/반제품/체결/단열/용접봉 | bom_dim.role∪nx.bom.role |
| fin_diam/thick/length | 치수 | bom_dim |
| **weight_actual** | **우리 실측 중량=원소재소요량** = weight_calc(치수) | bom_dim.fin_weight |
| **raw_lg_kg** | **LG 인증 원소재 kg**(정산 LME차액용) | nx.bom 원소재 edge |
| gagong_proc | 공정코드 | bom_line.gagong_proc |
| dim_src | 치수출처 | bom_dim |

- **중량=원소재소요량=1축**(동관kg), 값 2개: 우리실측(weight_calc=fin_weight) / LG인증(edge). 차이=사급정산 근거. [[newerp-weight-source-lg-vs-actual]]

## 3. 실측 결과 (2026-08-24)
- **31,746행 · 사용중 제품 3,689** (use_flag=1 ∩ bom_header).
- 검증: 미해결SUB **0**(완전평면) · 제작동관 13,556중 중량실측누락 **34**(99.75%) · 종류 AJR2745·MJU384·AJJ242·521·ADM·AET… 다양.
- 축커버리지: 역할88%·공정66%·중량실측/LG인증 ~45%(원소재계열).
- 이상 2건 모두 정당: 접미사leaf 170=외주107·구매62(매입 완제 terminal) · 빈전개39=전부 cs_except=1(비현행).

## 3-1. 용접포인트 축 = nx.bom_flat_weld (companion, 2026-08-24 완료)
- 소스 = `nx.proc_weld`(현행 cs_calc_except=0, 5,508행). grain=접합점별(재료와 다름) → 별도 companion.
- 제품별 **트리 전개 모든 노드**의 용접점 롤업(용접이 SUB노드=은납/-19-1에 걸림 → 롤업 필수).
- 컬럼: item_code(제품)·weld_parent(용접노드)·weld_item(용접봉)·weld_base·pipe_diam(관경)·weld_st(용접ST)·use_qty.
- **6,619행·용접보유 3,090제품**. ★AJR75563402=은납/19-1노드서 RAC30599301+RAC30599327 둘다(화면"용접봉 2" 재현, ST·Ø·uq 포함).
- 데이터품질: 일부 ST/Ø/use_qty 미입력(원 proc_weld 성김) → 개선여지.

## 4. 남음
- 라우팅·공급처(R01~Rnn) 종속 반영(누가/어떻게→원소재소요량·공정·용접 변동).
- nx.bom_flat 승격/프로그램 연결(원가·소요·backflush가 이 정본 참조).
- 용접 proc_weld 데이터품질 보강(ST/Ø 미입력).

## 5. 롤백/재생성
- 멱등 재빌드(DROP+CREATE). 원 nx.bom 백업 = nx.bom_bak_260824_lg2our.
