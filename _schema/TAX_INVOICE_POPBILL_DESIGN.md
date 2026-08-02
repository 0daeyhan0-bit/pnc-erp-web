# 세금계산서 팝빌(Popbill) 양방향 연계 설계

> 상태: **설계·분석 (구현·DB변경·배포 없음, 승인 후 착수)**. 작성 2026-07-29. 라이브 읽기전용.
> 대표확정: **발행(매출) + 수집(매입) 양방향, 공급자=팝빌(Popbill)**. [[nextgen-erp-6-requirements]] "계산서정합" · [[nextgen-erp-close-settlement]] · 재고엔진 유상사급(SA_T_SALE_DTL=nx.sale_dtl)·매입마감(nx.pur_close) 정합.

---

## 0. 핵심 요약
- **레거시 팝빌 실측**: SP/DB 계산서 발행로직 **없음**. popbill **SDK(PB srs)만 존재** — `popbill.sdk/`에 **httaxinvoicexml.srs(홈택스 세금계산서 XML=수집)·tisearchresult.srs(계산서 조회결과)·chargeinfo.srs(잔액)·messageservice.sru(문자)·faxsearchresult.srs**. → 레거시는 팝빌을 **주로 수집/조회(홈택스 세금계산서)·문자**용으로 붙였고, **발행 로직은 DB/SP에 없음**(수기/외부 추정).
- **계산서 대사 테이블 존재(빈 껍데기)**: `CM_T_TAX_INVOICE_RECON`(recon_yymm·cust_code·**erp_base_amt·erp_adjust_amt·final_tax_invoice_amt·wehago_matched_amt·diff_amt·close_status**) 0행 = 계산서정합 모델 자리만 마련(WEHAGO 매칭 축). → 신규는 이 모델을 **팝빌 수집액**으로 채워 대사.
- **신규 설계**: 발행=유상매출(nx.sale_dtl)→팝빌 정발행 / 수집=팝빌·홈택스 매입계산서→nx.pur_close 대사. nx 계산서 원장(헤더/명세·상태·팝빌키·연계키) 신설.
- **결정필요**: 발행단위(건별 vs 월합계)·사업자/인증키(민감·담당)·정발행vs역발행·수정/취소정책·WEHAGO vs 팝빌 대사축.

---

## 1. 레거시 팝빌/계산서 실측 (읽기전용)
### 1.1 DB
- **테이블**: `CM_T_TAX_INVOICE_RECON`(계산서 대사, 0행·준비만) · `HR_T_MEMBER_TAX`(직원세금, 무관). 그 외 *_TAX_*/*_INVOICE_* **없음**.
- **SP/함수**: 계산서/팝빌 관련 SP **0건**. 정의에 popbill/세금계산서 포함 SP **0건**. → **DB측 발행/수집 로직 부재**.
- **CM_T_TAX_INVOICE_RECON 컬럼**(계산서정합 모델): recon_id·recon_yymm·cust_code·**erp_base_amt**(ERP 매출/매입 기준액)·**erp_adjust_amt**(조정)·**final_tax_invoice_amt**(최종 계산서액)·**wehago_matched_amt**(WEHAGO 매칭액)·**diff_amt**(차이)·close_status·감사. → **월×거래처 단위 대사**(ERP액 vs 실계산서액 diff).
### 1.2 소스(src_extracted) — popbill.sdk (PB 구조체)
| 파일 | 용도 |
|--|--|
| **httaxinvoicexml.srs** | 홈택스 세금계산서 XML 구조 → **매입 계산서 수집** |
| **tisearchresult.srs** | TaxInvoice 조회결과 → 계산서 목록 수집 |
| chargeinfo.srs | 팝빌 **잔액/과금** 조회 |
| messageservice.sru | 문자(SMS/알림톡) |
| faxsearchresult.srs | 팩스 |
- ★**발행 서비스 오브젝트(taxinvoiceService 발행부) 미추출/미사용** — 레거시는 계산서 **수집·조회·문자** 중심. 발행은 외부(홈택스 직접/세무대리) 추정. dw_ac_master_300(계정마스터)·f_get_master_name_cnv_code에 세금계산서 문자열 참조(코드성).
- **∴ 레거시 = 팝빌 수집형(부분)**. 신규 "양방향(발행+수집)"은 **발행 신규구축** 필요.

## 2. 신규 ERP 팝빌 양방향 흐름
### 2.1 발행(매출) — 정발행
```
유상매출 확정(nx.sale_dtl = SA_T_SALE_DTL, 유상사급/판매/출하) 
  → 매출마감(nx.sale_close, 월×거래처 확정)
  → 계산서 발행대상 집계(§결정 A: 건별 or 월합계)
  → nx.tax_invoice(헤더 status='임시') + nx.tax_invoice_dtl(명세)
  → 팝빌 RegistIssue(정발행) API → 팝빌 응답(ntsConfirmNum·ic_key)
  → status: 임시 → 발행 → (국세청)승인/실패
  → 취소/수정발행 시 역발행·수정 API + status 갱신
```
- 공급가액=SALE_AMT(사급단가·판매가 합), 세액=공급가×10%(면세=0), 합계. 유상사급 LME 소급분은 매출조정→계산서 수정발행 or 별도.
### 2.2 수집(매입)
```
팝빌 MgtKeyType/홈택스 세금계산서 조회(httaxinvoice/tisearchresult) 정기수집
  → nx.tax_invoice_in(매입계산서 헤더·명세, 공급자·공급가·세액·ntsConfirmNum)
  → 매입마감(nx.pur_close) 대사: 계산서액 vs ERP 매입내역(매입입고·구매)
  → CM_T_TAX_INVOICE_RECON 모델(erp_base_amt vs final_tax_invoice_amt·diff_amt) 채움
  → 불일치 리포트(diff≠0), close_status 관리
```
- 6대요구 "계산서정합" = 이 대사(매입계산서↔매입내역, 매출계산서↔매출마감).

## 3. nx 스키마 설계(초안)
- **nx.tax_invoice**(발행 헤더): tax_id·issue_type(정발행'1'/역발행'2')·**cust_code**·write_date·supply_amt·tax_amt·total_amt·tax_type(과세/면세)·**mgt_key**(우리관리번호)·**pb_state**(임시/발행/승인/실패/취소)·**nts_confirm_num**(국세청승인번호)·pb_response(원문)·**link_gubun**(매출/유상사급)·close_yymm·ins/upd 감사.
- **nx.tax_invoice_dtl**(명세): tax_id·seq·item_name·spec·qty·unit_cost·supply_amt·tax_amt·remarks. 연계키=nx.sale_dtl(work_order·item·sale_ymd).
- **nx.tax_invoice_in**(수집 매입): in_id·**supplier_biz_no**·supplier_name·write_date·supply_amt·tax_amt·nts_confirm_num·pb_mgtkey·**match_state**(대사)·link_pur_key(매입전표)·collected_dt.
- **nx.tax_recon**(= CM_T_TAX_INVOICE_RECON 승격): recon_yymm·cust_code·erp_base_amt·erp_adjust_amt·final_tax_invoice_amt·**pb_matched_amt**(팝빌수집액, WEHAGO 대체/병행)·diff_amt·close_status.
- **nx.pb_config**(사업자·인증, ★민감·담당입력): biz_no·corp_name·**linkID·secretKey**(팝빌)·ceo·addr·업태종목·test_flag(연동테스트/운영)·발행자이메일. → **암호화 저장·화면 마스킹**, 코드에 하드코딩 금지.

## 4. 팝빌 인터페이스 설계 (실호출=구현단계)
| 기능 | 팝빌 API(개념) | nx 트리거 | 응답저장 |
|--|--|--|--|
| 발행(정) | TaxinvoiceService.RegistIssue | 매출확정/마감 후 | nts_confirm_num·pb_state·ic_key |
| 발행취소 | CancelIssue/Delete | 취소 | pb_state=취소 |
| 수정발행 | 역발행 or 수정 | 금액정정(LME) | 신 tax_id 링크 |
| 상태조회 | GetDetailInfo/GetInfos | 배치 폴링 | pb_state 갱신(승인/실패) |
| 매입수집 | Search/MgtKey·홈택스 | 정기배치 | nx.tax_invoice_in |
| 잔액 | getBalance(chargeinfo) | 발행 전 체크 | 표시 |
- 인증: linkID+secretKey(pb_config). 테스트베드→운영 전환 플래그. 실 SDK(파이썬 popbill) 연동은 구현단계(키·인증 담당필요).

## 5. 재고엔진·마감 정합
- **유상사급(재고엔진 §11.2)**: 사급출고=SA_T_SALE_DTL(매출)→**계산서 발행 대상**(정발행). 무상사급(문영·경성정밀)=창고이동→**계산서 없음**. → 발행대상 필터 = link_gubun 매출 AND 유상(무상거래처 nx.sagub_free_vendor 제외).
- **매출마감(nx.sale_close)**: 월×거래처 확정 → 계산서 발행/대사 기준. **매입마감(nx.pur_close)**: 수집 매입계산서와 대사.
- LME 소급정산 차액 → 매출조정(erp_adjust_amt) → 계산서 수정발행 or 익월 반영(§결정).

## 6. 결정 필요 포인트
- **A. 발행단위**: 건별(출하/사급 전표별) vs **월합계(거래처×월)**. 관행·거래처 요구 확인(대개 월합계 세금계산서).
- **B. 정발행 vs 역발행**: 매출=우리 정발행 / 매입=공급자 발행분 수집(역발행 사용 여부).
- **C. 대사축(WEHAGO vs 팝빌)**: CM_T_TAX_INVOICE_RECON은 wehago_matched_amt. 팝빌 수집으로 대체할지 병행할지(WEHAGO=더존 플랫폼, 팝빌=계산서API — 둘 다 쓰는지 담당확인).
- **D. LME 소급 계산서 처리**: 수정발행 vs 익월 조정 vs 별도 정산계산서.
- **E. 상태머신**: 임시→발행→국세청승인/실패→(취소/수정). 실패 재시도·역발행 정책.

## 7. 담당확인 (민감·정책)
- **사업자정보·팝빌 인증키(linkID/secretKey)**: 담당 직접입력(암호화). 코드/문서에 미기재.
- 발행 정책: 월합계/건별, 발행일(마감후 N일), 발행자, 이메일/문자 통지.
- 세무대리/홈택스 직접발행 병행 여부, WEHAGO(더존) 사용 현황(대사축 확정).
- 면세/과세 구분 기준(품목·거래처), 영세율(수출) 유무.
- 무상사급(문영·경성정밀)=계산서 없음 재확인(무상=매출아님).

## 8. 미확보 · 상태
- 레거시 발행로직 부재(수집 SDK만) → **발행은 신규구축**(대조원본 없음). 팝빌 발행 서비스 오브젝트(taxinvoiceService.sru) 미추출 → 필요시 .pbl 재추출(수집구조 srs는 확보).
- CM_T_TAX_INVOICE_RECON 실사용 이력 0 → 대사 실운영 방식 담당확인.
- **구현·DB변경·배포 없음.** 인증키·발행정책 담당확정 + 위 스키마 승인 후 구현.

---
## 부록: 실측
- popbill.sdk 파일 5종(httaxinvoicexml·tisearchresult·chargeinfo·messageservice·faxsearchresult). 계산서 SP 0건. CM_T_TAX_INVOICE_RECON 8지표 컬럼·0행. nx 기존=sale_close·pur_close(마감), 계산서 원장 없음(신설 대상).
- 무상사급 거래처(재고엔진 연계) = 문영산업(2014,260226) + 경성정밀 주식회사 주촌지점(2350, 적용일 담당확인). 계산서 발행대상서 제외.
</content>
</invoke>
