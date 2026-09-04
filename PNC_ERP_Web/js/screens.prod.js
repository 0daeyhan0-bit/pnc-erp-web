/* ===== 인쇄창 열기 — ★최상위 공용 함수 (프린터 기억을 위해 실제 URL 사용) =====
   window.open('', ...) 로 열면 주소가 about:blank 가 되는데, 브라우저(특히 Edge)는
   "마지막에 고른 프린터"를 URL 기준으로 저장한다. about:blank 는 저장 키가 못 되어
   매번 기본 프린터(PDF로 저장)로 돌아간다.
   → /print.html?t=<종류> 로 열고, 종류(label/kanban/sheet)를 나눠 출력물별로 따로 기억시킨다.
   호출: openPrintWin('label','pncPrnLabel','width=760,height=1000').then(w=>{...})
   반환: 창이 로드된 뒤의 window (팝업차단이면 null) */
window.openPrintWin=(kind,name,feat)=>new Promise(resolve=>{
  const w=window.open('print.html?t='+encodeURIComponent(kind),name,feat);
  if(!w){resolve(null);return;}
  let done=false;
  const fin=()=>{if(done)return;done=true;
    // ★document.open()/write() 는 문서를 새로 여는 동작이라 URL 이 about:blank 로 돌아가고,
    //   그러면 브라우저가 프린터 선택을 기억하지 못한다(2026-08-21 실측).
    //   → write 대신 print.html 안의 헬퍼(renderPrint)로 DOM 에 주입한다.
    //   호출측은 기존처럼 w.document.write(html); w.document.close(); 를 쓰면 된다.
    const d=w.document;
    let buf='';
    d.write=d.writeln=function(html){buf+=html;};
    d.close=function(){
      const html=buf; buf='';
      if(!html)return;
      try{
        if(typeof w.renderPrint==='function'){w.__pendingHtml=null;w.renderPrint(html);}
        else{                                  // print.html 이 아직 안 떴을 때의 대비책
          //  ※print.html 로드시 __pendingHtml 을 스스로 소비한다(중복인쇄 방지)
          w.__pendingHtml=html;
          setTimeout(()=>{try{
            const h=w.__pendingHtml; if(!h)return;   // 이미 소비됐으면 아무것도 안 함
            w.__pendingHtml=null;
            if(typeof w.renderPrint==='function')w.renderPrint(h);
          }catch(e){}},400);
        }
      }catch(e){
        // 최후수단 — 내용이라도 보이게(URL 은 about:blank 가 되어 프린터 기억은 포기)
        try{d.open();d.write(html);d.close();}catch(_){}
      }
    };
    resolve(w);};
  try{
    if(w.document&&w.document.readyState==='complete')return fin();   // 재사용되는 창
    w.addEventListener('load',fin,{once:true});
  }catch(e){}
  setTimeout(fin,1500);   // 안전장치(로드 이벤트를 놓쳐도 진행)
});

/* ===== 로컬 프린터 에이전트 연동 — ★최상위 공용 =====
   웹은 보안상 "어느 프린터로 보낼지"를 지정할 수 없어 인쇄창에서 매번 골라야 했다.
   가간판(A4)·라벨(40×20)이 서로 다른 USB 프린터에 물린 현장에서는 오출력 위험이 크다.
   → 작업 PC 에 트레이 상주 프로그램(_tools/pnc_print_agent)을 두고, 웹은 kind(가간판/라벨)만
     보낸다. 실제 물리 프린터는 그 PC 의 설정이 정하므로 PC 마다 구성이 달라도 웹 코드는 하나.

   ★에이전트가 없으면 기존 인쇄창 방식으로 자동 폴백한다(현장이 멈추지 않게).
   ★127.0.0.1 로만 통신 — 외부에서 이 PC 프린터를 쓸 수 없다. */
window.PRN_AGENT = (() => {
  const BASE = 'http://127.0.0.1:17650';
  let cache = null, at = 0;
  const ping = async (force) => {
    // 30초 캐시 — 발행 때마다 왕복하면 느리다. 에이전트를 껐다 켠 경우 force 로 갱신.
    if (!force && cache && Date.now() - at < 30000) return cache;
    try {
      const c = new AbortController();
      const t = setTimeout(() => c.abort(), 1200);   // 미설치 PC 에서 오래 기다리지 않게
      const r = await fetch(BASE + '/ping', { signal: c.signal });
      clearTimeout(t);
      cache = r.ok ? await r.json() : null;
    } catch (e) { cache = null; }
    at = Date.now();
    return cache;
  };
  // kind='kanban'|'label'  job={pdf|tspl, doc, copies}
  const send = async (kind, job) => {
    const r = await fetch(BASE + '/print', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ kind }, job))
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) { const e = new Error(j.detail || '출력 실패'); e.need_setup = j.need_setup; throw e; }
    return j;
  };
  return { BASE, ping, send };
})();

/* ===== Spec Sheet(BOM) 출력 — ★최상위 공용 함수 =====
   준비실적처리(키팅) [🖨 BOM출력] → A4 가로 미리보기 → 인쇄.
   레거시 w_pr_input_460 Print미리보기 양식 재현(2026-08-19):
     헤더 : 공정(용접) · 파트명 · Spec Sheet(BOM) · 도번 · 품명 · 시방예정(수기) · 지그보관구역
     본문 : 레벨|품목코드|소분류|체크|대표매입처|재고취처|재고|소요량|품명|규격|지름|두께|길이
            + 자재서명/생산서명/품질서명(수기란)
     푸터 : 페이지 n/tot · DATE. 마지막 페이지에 [n 건] + 서명표(준비수량/자재팀/생산팀/품질팀 초물·OQC/내사경).
   ※페이지 분할 = 행 수 기준(레거시도 넘치면 다음 장). 키팅대상 회색음영은 제외(사용자 지시). */
window.printBomSheet=async(item,gpc)=>{
  const API=API_BASE;
  const nf=(n,d)=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:(d==null?0:d)});
  const esc2=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  let j;
  try{const r=await fetch(`${API}/api/ready/bomsheet?item=${encodeURIComponent(item)}&gpc=${encodeURIComponent(gpc||'')}`);
      j=await r.json();}
  catch(e){alert('BOM 조회 실패: '+e);return;}
  if(!j||!j.rows){alert('BOM 조회 실패: '+((j&&j.detail)||''));return;}
  if(!j.rows.length){alert(`${item} 의 BOM 이 없습니다.`);return;}
  // 1쪽(상단 헤더 영역 큼)·이후쪽 행수. ★마지막 쪽엔 건수박스+서명표가 더 붙으므로
  //   그 쪽만 여유를 둔다(안 그러면 서명표가 다음 장으로 밀리거나 잘림).
  const ROWS_1=28, ROWS_N=32, TAIL_RESERVE=8;
  const pages=[]; let i=0;
  while(i<j.rows.length){
    const cap=pages.length?ROWS_N:ROWS_1;
    const rest=j.rows.length-i;
    // 이번이 마지막 쪽이 되는 경우 = 꼬리(건수박스+서명표) 자리까지 필요.
    //   들어가면 그대로 마감, 모자라면 cap 만큼 채워 다음 쪽으로 넘긴다.
    const n=(rest<=cap-TAIL_RESERVE)?rest:cap;
    pages.push(j.rows.slice(i,i+n)); i+=n;}
  const now=new Date();
  const dt=`${now.getFullYear()}/${String(now.getMonth()+1).padStart(2,'0')}/${String(now.getDate()).padStart(2,'0')}`
          +` ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
  const dim=v=>(+v)?nf(v,2):'';                       // 지름/두께 — 0이면 공백
  const len=v=>(+v)?nf(v,0):'';
  const head=()=>`
    <div class="bh">
      <div class="bh-l">
        <div class="bh-r1"><span class="bh-proc">${esc2(j.proc_nm||'용접')}</span>
             <span class="bh-part">${esc2(j.part_nm||'')}</span></div>
        <div class="bh-r2">도번 : <b>${esc2(j.item)}</b></div>
        <div class="bh-r3">품명 : ${esc2(j.nm||'')}</div>
      </div>
      <div class="bh-c"><div class="bh-title">Spec Sheet(BOM)</div>
        <div class="bh-si"><span>시방예정 :</span><span class="bh-box"></span></div></div>
      <div class="bh-r"><div class="bh-jig">지그보관구역 : ${esc2(j.jig||'')}</div></div>
    </div>`;
  const thead=`<tr>
      <th class="w-lv">레벨</th><th class="w-cd">품목코드</th><th class="w-sg">소분류</th>
      <th class="w-ck">체크</th><th class="w-cs">대표매입처</th><th class="w-rk">재고취처</th>
      <th class="w-st">재고</th><th class="w-uq">소요량</th><th class="w-nm">품명</th>
      <th class="w-sp">규격</th><th class="w-dm">지름</th><th class="w-dm">두께</th><th class="w-dm">길이</th>
      <th class="w-sv">자재<br>서명</th><th class="w-sv">생산<br>서명</th><th class="w-sv">품질<br>서명</th></tr>`;
  // ★레벨 들여쓰기(2026-08-19 요청) — 같은 줄에 붙어 있으면 계층이 안 보여서.
  //   레벨 1=좌측정렬, 2 이상은 레벨당 6mm 들여쓰기(레거시 화면과 동일한 계단 배치).
  const body=rs=>rs.map(x=>`<tr class="${x.lvl===1?'lv1':''}">
      <td class="c">${x.lvl}</td>
      <td class="cd" style="padding-left:${1+(x.lvl-1)*6}mm">${esc2(x.mat)}</td>
      <td class="c">${esc2(x.sgrp)}</td>
      <td></td><td class="c">${esc2(x.cust)}</td><td class="c">${esc2(x.rack)}</td>
      <td class="r">${x.stock?nf(x.stock):''}</td><td class="c">${nf(x.use_qty,4)}</td>
      <td>${esc2(x.nm)}</td><td>${esc2(x.spec)}</td>
      <td class="r">${dim(x.diam)}</td><td class="r">${dim(x.thick)}</td><td class="r">${len(x.length)}</td>
      <td></td><td></td><td></td></tr>`).join('');
  const tail=`
    <table class="btot"><tr><td class="c">${nf(j.cnt)} 건</td></tr></table>
    <table class="bsig">
      <tr><th>준비수량</th><th>자재팀</th><th>생산팀</th><th>품질팀 초물</th><th>품질팀 OQC</th><th>내사경 검사</th></tr>
      <tr><td></td><td></td><td></td><td></td><td></td><td></td></tr></table>`;
  const html=pages.map((rs,pi)=>`
    <div class="pg">
      ${head()}
      <table class="btbl"><thead>${thead}</thead><tbody>${body(rs)}</tbody></table>
      ${pi===pages.length-1?tail:''}
      <div class="pf"><span></span><span>${pi+1} / ${pages.length}</span><span>DATE : ${dt}</span></div>
    </div>`).join('');
  const w=window.open('','_blank','width=1200,height=850');
  if(!w){alert('팝업이 차단되었습니다. 팝업 허용 후 다시 시도하세요.');return;}
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Spec Sheet(BOM) ${esc2(j.item)}</title>
  <style>
    @page{size:A4 landscape;margin:8mm}
    *{box-sizing:border-box}
    body{margin:0;font-family:"맑은 고딕","Malgun Gothic",sans-serif;color:#000;background:#e9edf2}
    .pg{width:281mm;min-height:194mm;background:#fff;margin:6mm auto;padding:4mm 5mm;position:relative;
        box-shadow:0 1px 6px rgba(0,0,0,.25)}
    .bh{display:flex;align-items:flex-start;gap:6mm;margin-bottom:2mm}
    .bh-l{flex:0 0 78mm}
    .bh-r1{display:flex;gap:10mm;font-size:13pt}
    .bh-proc{font-weight:700}.bh-part{font-weight:700}
    .bh-r2{font-size:12pt;margin-top:1mm}.bh-r2 b{font-size:17pt;letter-spacing:.3px}
    .bh-r3{font-size:11pt;margin-top:1mm}
    .bh-c{flex:1;text-align:center}
    .bh-title{font-size:19pt;font-weight:700;text-decoration:underline;letter-spacing:1px;margin-bottom:2mm}
    .bh-si{display:flex;align-items:center;justify-content:center;gap:2mm;font-size:8pt}
    .bh-box{display:inline-block;width:80mm;height:9mm;border:1px solid #000}
    /* 지그보관구역 = 값이 길어도(예 A-6,A-11) 줄바꿈되어 표 위로 넘치지 않게 */
    .bh-r{flex:0 0 40mm;text-align:right;font-size:10pt;padding-top:9mm;
          white-space:normal;word-break:break-all;line-height:1.25}
    .btbl{width:100%;border-collapse:collapse;table-layout:fixed}
    .btbl th,.btbl td{border:1px solid #000;padding:0 1mm;font-size:7.2pt;height:4.6mm;
        overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
    /* 헤더는 2줄(자재/서명)이 들어가므로 높이 확보 + 줄바꿈 허용 — 안 그러면 글자가 잘림 */
    .btbl th{background:#fff;font-weight:700;text-align:center;line-height:1.1;
        height:8mm;white-space:normal;vertical-align:middle}
    .btbl td.c{text-align:center}.btbl td.r{text-align:right}
    .btbl td.cd{text-align:left}                     /* 품목코드 = 레벨 들여쓰기라 좌측정렬 */
    .btbl tr.lv1>td{border-top:1.6px solid #000}      /* 레벨1 시작마다 굵은 구분선 = 계층 그룹 분리 */
    /* ★컬럼폭 합계 = 가용폭(281mm − 좌우패딩 10mm = 271mm) 이내여야 함.
       table-layout:fixed 라 넘치면 오른쪽(품질서명)부터 잘림 — 2026-08-20 재조정.
       7+36+14+9+23+15+13+11+40+34+10+10+10+13+13+13 = 271mm (딱 맞춤) */
    .w-lv{width:7mm}.w-cd{width:36mm}.w-sg{width:14mm}.w-ck{width:9mm}.w-cs{width:23mm}
    .w-rk{width:15mm}.w-st{width:13mm}.w-uq{width:11mm}.w-nm{width:40mm}.w-sp{width:34mm}
    .w-dm{width:10mm}.w-sv{width:13mm}
    .btot{border-collapse:collapse;margin-top:0}
    .btot td{border:1px solid #000;width:42mm;height:5mm;font-size:8pt;text-align:center}
    .bsig{border-collapse:collapse;margin:9mm auto 0}
    .bsig th{border:1px solid #000;width:26mm;height:6mm;font-size:8.5pt;font-weight:700;text-align:center}
    .bsig td{border:1px solid #000;height:17mm}
    .pf{position:absolute;left:5mm;right:5mm;bottom:3mm;display:flex;justify-content:space-between;font-size:7.5pt}
    .tb{position:fixed;top:0;left:0;right:0;background:#1c47a0;color:#fff;padding:6px 12px;z-index:9;
        display:flex;gap:8px;align-items:center;font-size:13px}
    .tb button{padding:4px 14px;font-size:13px;cursor:pointer;border:0;border-radius:4px;background:#fff;color:#1c47a0;font-weight:700}
    .sp{height:38px}
    @media print{.tb,.sp{display:none}body{background:#fff}
      .pg{box-shadow:none;margin:0;page-break-after:always;width:auto;min-height:auto}
      .pg:last-child{page-break-after:auto}}
  </style></head><body>
  <div class="tb"><b>Spec Sheet(BOM)</b>
    <span>${esc2(j.item)} · ${esc2(j.nm||'')} · ${nf(j.cnt)}건 · ${pages.length}쪽</span>
    <span style="flex:1"></span>
    <button onclick="window.print()">🖨 출력</button>
    <button onclick="window.close()">닫기</button></div>
  <div class="sp"></div>${html}</body></html>`);
  w.document.close();
};

/* ===== A4 생산이동전표(용접전표) 출력 — ★최상위 공용 함수 =====
   준비실적처리(키팅)와 생산전표출력관리 두 화면이 공유.
   (2026-08-19: SCREEN.kitting 안에 있어 키팅 화면을 먼저 열지 않으면
    window.printWeldSheet 가 없어 "전표 출력 모듈을 찾을 수 없습니다" 발생 → 최상위로 이동)
   바코드 = J(용접전표)만 8자리 전표번호. G/L은 생산전표출력관리에서 별도 발행. */
window.printWeldSheet=async(sheetNo)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
    let j;
    try{const r=await fetch(`${API}/api/ready/sheet?sheet_no=${encodeURIComponent(sheetNo)}`);j=await r.json();}
    catch(e){alert('전표 조회 실패: '+e);return;}
    if(!j||!j.ok){alert('전표 조회 실패: '+((j&&j.detail)||''));return;}
    const ymd8=s=>{s=(''+(s||'')).trim();return s.length>=6?`${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`:s;};
    const hm4=s=>{s=(''+(s||'')).trim();return /^\d{3,4}$/.test(s)?s.padStart(4,'0').replace(/^(\d\d)(\d\d)$/,'$1:$2'):s;};
    const sn8=j.sheet_no_fmt||String(j.sheet_no||'').padStart(8,'0');
    // ★실제 스캔 가능한 Code128-B 이미지(서버 생성, PIL). 디코딩 검증 완료.
    //   공정별 바코드 = 전표번호(8자리)-SEQ-구분-차수  예: 00266440-1-A-1
    const bcode=(txt,hh)=>`<div style="text-align:center">
        <img src="${API}/api/barcode/code128?text=${encodeURIComponent(txt)}&h=${hh||44}&scale=2"
             style="height:${(hh||44)/2}px;max-width:100%;image-rendering:pixelated" alt="${esc(txt)}">
        <div style="font-size:8px;letter-spacing:.5px">${esc(txt)}</div></div>`;
    // SEQ 10줄 고정(공정 없으면 빈줄).
    // ★컬럼 = 파트 / 공정 / 실적(용접전표·가간판·라벨) / 바코드.
    //   실적 = PR_M_ITEM_PROC_GAGONG.JP_PROC_METHOD (J전표/G간판/L라벨) — 그 공정 실적을 뭘로 잡는지.
    //   ★바코드 규칙(2026-08-19 확인):
    //     · J(용접전표) = 이 전표번호 자체를 스캔 → 8자리 전표번호 바코드를 찍음
    //     · G(가간판)/L(라벨) = 준비등록이 아니라 「생산전표출력관리」에서 별도 발행하며
    //       그때 채번되는 BOX_NO(간판)/QR(라벨)로 실적을 잡음 → 이 전표에는 찍을 값이 없음(발행 안내만)
    const rows10=[];
    for(let i=0;i<10;i++){
      const p=(j.procs||[])[i];
      const mn=p?(p.method_nm||''):'';
      const mbg=p&&p.method==='J'?'#e8f0ff':(p&&p.method==='G'?'#eaf7ec':(p&&p.method==='L'?'#fff5e0':''));
      let bc='';
      if(p){
        if(p.method==='J') bc=bcode(sn8,34);
        else if(p.method==='G'||p.method==='L') bc=`<div style="text-align:center;font-size:9px;color:#666">생산전표출력관리에서 ${esc(mn)} 발행</div>`;
      }
      rows10.push(`<tr style="height:30px">
        <td style="text-align:center;font-weight:700">${i+1}</td>
        <td style="padding-left:4px">${p?esc(p.part_nm||p.gpc):''}</td>
        <td style="padding-left:4px">${p?esc(p.gpc||''):''}${p&&p.mach?`<span style="color:#555;font-size:10px"> (${esc(p.mach)})</span>`:''}</td>
        <td style="text-align:center;font-weight:700${mbg?';background:'+mbg:''}">${esc(mn)}</td>
        <td>${bc}</td></tr>`);
    }
    // ★실제 URL(print.html?t=sheet)로 연다 — about:blank 는 프린터 선택이 기억되지 않는다.
    //   창이름만 전표별로 분리(동시 다건 출력). URL 은 t=sheet 로 같아 프린터 선택을 공유한다.
    const w=await openPrintWin('sheet','pncPrnSheet'+String(sn8||'').replace(/\W/g,''),'width=900,height=1100');
    if(!w){alert('팝업이 차단되었습니다. 브라우저 팝업 허용 후 다시 시도하세요.');return;}
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>생산이동전표 ${esc(sn8)}</title>
    <style>
      @page{size:A4 portrait;margin:8mm}
      *{box-sizing:border-box}
      /* ★A4 세로 전체를 채움 — 시트를 flex 컬럼으로 잡고 메모칸이 남는 높이를 흡수.
         (2026-08-19: 기존엔 내용이 페이지 중간에서 끊겨 아래 절반이 비었음) */
      html,body{height:100%}
      body{margin:0;font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:12px;color:#000}
      .sheet{display:flex;flex-direction:column;min-height:100%}
      .sheet>table{flex:0 0 auto}
      table{border-collapse:collapse;width:100%}
      td,th{border:1.5px solid #000;padding:2px 4px}
      .noborder td{border:none}
      .big{font-size:34px;font-weight:800;text-align:center;line-height:1.1}
      .ttl{font-size:30px;font-weight:800;text-align:center;letter-spacing:6px}
      .lbl{background:#f2f2f2;text-align:center;font-weight:700;white-space:nowrap}
      .memo{height:120px}
      .errtbl td{height:30px}
      @media print{
        .noprint{display:none}
        html,body{height:auto}
        .sheet{min-height:277mm}          /* A4 297mm − 상하 여백 8mm×2 − 여유 */
        .memo{height:auto}
      }
    </style></head><body>
    <div class="noprint" style="margin-bottom:6px">
      <button onclick="window.print()" style="padding:6px 16px;font-size:13px">🖨 인쇄</button>
      <button onclick="window.close()" style="padding:6px 16px;font-size:13px">닫기</button></div>
    <div class="sheet">
    <table>
      <tr>
        <td style="width:26%;height:52px;font-size:15px;font-weight:700;text-align:center">${esc(j.wh_nm||'자재창고')}</td>
        <td style="width:48%" class="ttl">생산 이동 전표</td>
        <td style="width:26%;text-align:center">
          <div style="font-size:22px;font-weight:800">${esc(j.line||'')}</div>
          <div style="font-size:8px">Print : ${esc(j.print_dt||'')}</div></td></tr>
      <tr>
        <td style="height:44px">
          <div style="font-size:8px">완성 후 이동창고</div>
          <div style="font-size:15px;font-weight:700">${esc(j.stock_nm||j.stock_code||'')}</div></td>
        <td>${bcode(sn8)}</td>
        <td style="text-align:center;font-size:20px;font-weight:800">${esc(sn8)}</td></tr>
      <tr>
        <td style="height:56px;font-size:15px;font-weight:700">${esc(j.upper||'')}</td>
        <td style="font-size:19px;font-weight:800;text-align:center">${esc(j.item||'')}</td>
        <td class="big">${nf(j.plan_qty)}</td></tr>
    </table>
    <table style="margin-top:-1.5px">
      <tr>
        <td class="lbl" style="width:8%">품명</td>
        <td style="width:44%">${esc(j.nm||'')}</td>
        <td class="lbl" style="width:12%">생산일자</td>
        <td style="width:12%;text-align:center">${esc(ymd8(j.plan_ymd))}</td>
        <td class="lbl" style="width:10%">투입시간</td>
        <td style="width:14%;text-align:center">${esc(hm4(j.input_hm))}</td></tr>
      <tr><td colspan="3" style="height:26px"></td>
        <td class="lbl">지그보관구역</td><td colspan="2"></td></tr>
    </table>
    <table style="margin-top:-1.5px;flex:1 1 auto">
      <tr><td class="memo"></td></tr>
    </table>
    <table style="margin-top:-1.5px">
      <tr>
        <th style="width:7%">SEQ</th><th style="width:20%">파트</th><th style="width:22%">공정</th>
        <th style="width:13%">실적</th><th style="width:38%">바코드</th></tr>
      ${rows10.join('')}
    </table>
    <table style="margin-top:-1.5px" class="errtbl">
      <tr><td class="lbl" style="width:20%">용접불량이력</td><td></td></tr>
      <tr><td class="lbl">검사불량이력</td><td></td></tr>
      <tr><td class="lbl">조립불량이력</td><td></td></tr>
    </table>
    </div>
    <script>
      // ★인쇄 대화상자 자동 호출 — OS 기본 프린터가 기본 선택됨(브라우저는 프린터 지정 API가 없음).
      //   ★바코드 이미지가 모두 로드된 뒤 인쇄해야 빈칸으로 출력되지 않음.
      (function(){
        var imgs=[].slice.call(document.images), left=imgs.length;
        function go(){setTimeout(function(){window.print();},200);}
        if(!left)return go();
        imgs.forEach(function(im){
          if(im.complete)done();
          else{im.addEventListener('load',done);im.addEventListener('error',done);}
        });
        function done(){if(--left<=0)go();}
      })();
    <\/script>
    </body></html>`);
    w.document.close();
  };

/* ===== PNC ERP screens.prod.js — 생산 SCREEN (app.js 분할, 순수이동) ===== */

/* 생산재고입출고 (생산, dw_pr_stock_460) — 좌:파트재고(수불장 기준) 우:선택품목 입출고이력. 파트차원 추가, 전월이월 2502기준 */
SCREEN.prodinout=(c)=>{
  const API=API_BASE;
  let rows=[], mv={}, pn={}, curYm='', loading=false, msg='';   // rows=[part,mat,desc,spec,sgn,stock,bf]
  const pName=p=>pn[(''+p).trim()]||p;
  const fmtYmd=y=>{y=(''+(y||'')).trim();return (y.length>=6&&y!=='000000')?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'00/00/00';};
  const _pad=n=>(''+n).padStart(2,'0');
  const _tod=(()=>{const d=new Date();return `${(''+d.getFullYear()).slice(2)}${_pad(d.getMonth()+1)}${_pad(d.getDate())}`;})();
  let frm=_tod.slice(0,4)+'01', to=_tod;
  const ymd2d=y=>{y=(''+(y||'')).trim();return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const d2ymd=v=>{v=(''+(v||'')).trim();return v.length>=10?v.slice(2,4)+v.slice(5,7)+v.slice(8,10):'';};
  // ★2026-08-25 기본 소스를 nx(=라이브 미러 + 웹실적)로. 다른 화면(410·키팅)과 의미 통일.
  //   구버전은 기본 live 였고, nx 를 고르면 웹 자체원장(stock_ledger) 파생뷰로 빠졌는데
  //   그 원장에 PRD 이력이 0건이라 늘 빈 화면이었다(웹 실적은 PR_T_PROD_DTL 에 쌓임).
  //   → nx = 일반 그리드(라이브+웹실적) / live = 라이브만. 원장 파생뷰는 source=ledger.
  let sel=null, curL=[], source='nx', incZero=false;   // incZero: 0재고 표시 토글
  const load=async()=>{loading=true;msg='';sel=null;
    const st=c.querySelector('#lbody');if(st)st.innerHTML=spinRow(5);
    const qs=`frm=${encodeURIComponent(frm)}&to=${encodeURIComponent(to)}&inc_zero=${incZero?1:0}`;
    if(source==='ledger'){loading=false;return nxDerivedView(c,`${API}/api/live/prodinout?${qs}&source=ledger`,{title:'생산입출고현황(웹원장)',onBack:()=>{source='nx';load();}});}
    try{const r=await fetch(`${API}/api/live/prodinout?${qs}&source=${encodeURIComponent(source)}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();curYm=j.ym||to.slice(0,4)||'';rows=j.stock||[];mv=j.moves||{};pn=j.partNames||{};}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];mv={};pn={};}
    loading=false;
    const fi=c.querySelector('#frm'),ti=c.querySelector('#to');if(fi)fi.value=ymd2d(frm);if(ti)ti.value=ymd2d(to);
    const ps=[...new Set(rows.map(r=>r[0]))].sort((a,b)=>pName(a).localeCompare(pName(b),'ko'));
    const psel=c.querySelector('#part');if(psel){const v=psel.value;psel.innerHTML='<option value="">전체</option>'+ps.map(p=>`<option value="${esc(p)}">${esc(pName(p))}</option>`).join('');psel.value=v;}
    const sub=c.querySelector('#pio-sub');if(sub)sub.innerHTML=`파트별 생산재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PR_T_STOCK_MAINT_MAT</code> 외 · 🟢 수불기간 ${esc(ymd2d(frm))}~${esc(ymd2d(to))}(이월기준 2502) · ${incZero?'<b style="color:#1c47a0">0재고 포함</b>':'0재고 숨김'}`;
    renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.innerHTML=`
   <div class="page-title">🔁 생산입출고현황</div>
   <div class="page-sub" id="pio-sub">파트별 생산재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PR_T_STOCK_MAINT_MAT</code> 외 · 🟢 nx(이월기준 2502) · 0재고 숨김</div>
   <div class="toolbar">
     <label class="tl">수불기간</label><input type="date" class="inp" id="frm" value="${esc(ymd2d(frm))}" style="min-width:130px"><span style="color:var(--muted);align-self:center">~</span><input type="date" class="inp" id="to" value="${esc(ymd2d(to))}" style="min-width:130px">
     <label class="tl">파트</label><select class="sel" id="part"><option value="">전체</option></select>
     <input class="inp" id="q" placeholder="자도번/품명">
     <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
     <!-- ★0재고 표시 토글(2026-08-28 사용자요청) — 기본은 숨김.
          0 이어도 기간 중 입·출고가 있었으면 이력을 봐야 한다(가공이동으로 0 이 된 품목 등). -->
     <label class="tl" style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;white-space:nowrap"
            title="재고 0 인 품목도 목록에 표시합니다">
       <input type="checkbox" id="zero" ${incZero?'checked':''} style="margin:0"> 0재고 표시</label>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div style="display:flex;gap:10px;align-items:flex-start">
     <div style="flex:0 0 46%;min-width:0">
       <div class="summary-bar" id="lsum"></div>
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr><th>파트</th><th>자도번</th><th>품명</th><th>소분류</th><th class="num">재고</th></tr></thead><tbody id="lbody"></tbody></table></div>
       <div class="rowcount" id="lcnt"></div>
     </div>
     <div style="flex:1;min-width:0">
       <div class="summary-bar" id="rhead"><div class="s-item">← 좌측에서 품목을 클릭하세요</div></div>
       <div class="grid-wrap" style="max-height:548px;overflow:auto"><table class="tbl fit"><thead><tr><th class="center">일자</th><th class="num">전일재고</th><th class="num">입고</th><th class="num">재고조정</th><th class="num">출고</th><th class="num">재고수량</th><th>구분</th><th>사용이력</th></tr></thead><tbody id="rbody"></tbody></table></div>
     </div>
   </div>`;
  const renderRight=(part,mat)=>{
    const row=rows.find(r=>r[0]===part&&r[1]===mat)||[]; const bf=+row[6]||0;
    const lines=(mv[part+'||'+mat]||[]).slice().sort((a,b)=>(''+a[0]).localeCompare(''+b[0],'ko'));
    let bal=bf, html=`<tr><td class="center">00/00/00</td><td class="num">${won(bf)}</td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num qty"><b>${won(bf)}</b></td><td>전월이월</td><td></td></tr>`;
    let si=0,se=0,so=0;
    lines.forEach(r=>{const prev=bal; const i=+r[1]||0,o=+r[2]||0,e=+r[3]||0; bal=prev+i-o+e; si+=i;so+=o;se+=e;
      html+=`<tr><td class="center">${fmtYmd(r[0])}</td><td class="num">${won(prev)}</td><td class="num">${i?won(i):''}</td><td class="num">${e?won(e):''}</td><td class="num">${o?won(o):''}</td><td class="num qty"><b>${won(bal)}</b></td><td>${esc(r[4])||''}</td><td class="cap" title="${esc(r[5]||'')}">${esc(r[5]||'')}</td></tr>`;});
    html+=`<tr class="grandtot"><td class="center">총계</td><td class="num">${won(bf)}</td><td class="num">${won(si)}</td><td class="num">${won(se)}</td><td class="num">${won(so)}</td><td class="num">${won(bal)}</td><td colspan="2"></td></tr>`;
    c.querySelector('#rbody').innerHTML=html;
    c.querySelector('#rhead').innerHTML=`<div class="s-item">${esc(pName(part))} · <b>${esc(mat)}</b></div><div class="s-item">${esc(row[2]||'')}</div><div class="s-item">현재고 <b>${won(bal)}</b></div>`;
    attachResizers(c);
  };
  const renderLeft=()=>{
    const q=c.querySelector('#q').value.trim().toLowerCase(), gb=c.querySelector('#gubun').value, pf=c.querySelector('#part').value;
    curL=rows.filter(r=>(!pf||r[0]===pf)&&(gb==='all'||(gb==='plus'?r[5]>0:r[5]<0))&&(!q||(''+r[1]).toLowerCase().includes(q)||(''+r[2]).toLowerCase().includes(q)))
      .sort((a,b)=>pName(a[0]).localeCompare(pName(b[0]),'ko')||(''+a[1]).localeCompare(''+b[1],'ko'));
    const tot=curL.reduce((a,b)=>a+(+b[5]||0),0);
    let lb=curL.map(r=>`<tr data-part="${esc(r[0])}" data-mat="${esc(r[1])}" class="${sel===r[0]+'||'+r[1]?'sel':''}"><td class="cap" title="${esc(pName(r[0]))}">${esc(pName(r[0]))}</td><td><b>${esc(r[1])}</b></td><td class="cap" title="${esc(r[2])}">${esc(r[2])}</td><td>${esc(r[4])}</td><td class="num qty">${won(r[5])}</td></tr>`).join('');
    if(curL.length)lb+=`<tr class="grandtot"><td colspan="4" class="right">총계 (${won(curL.length)} 품목)</td><td class="num">${won(tot)}</td></tr>`;
    c.querySelector('#lbody').innerHTML=curL.length?lb:`<tr><td colspan="5" class="empty">결과 없음</td></tr>`;
    c.querySelector('#lbody').querySelectorAll('tr[data-mat]').forEach(tr=>tr.onclick=()=>{sel=tr.dataset.part+'||'+tr.dataset.mat;c.querySelectorAll('#lbody tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');renderRight(tr.dataset.part,tr.dataset.mat);});
    c.querySelector('#lsum').innerHTML=`<div class="s-item">품목 <b>${won(curL.length)}</b></div><div class="s-item">재고 합계 <b>${won(tot)}</b></div>`;
    c.querySelector('#lcnt').textContent=`${curL.length}품목 ${incZero?'(0재고 포함)':'(0재고 제외)'}`;
    attachResizers(c);
  };
  // ★검색 = 서버 재조회(load) — renderLeft(캐시 필터)만 하면 화면을 연 뒤 발생한 실적/이동이 반영되지 않음.
  //   (2026-08-19: 준비실적 등록 후 검색해도 "결과 없음" → 탭을 닫았다 열어야 보이던 문제)
  //   드롭다운/구분 변경은 기존대로 캐시 필터(즉시반응) 유지.
  const _reload=()=>{frm=d2ymd(c.querySelector('#frm').value)||frm;to=d2ymd(c.querySelector('#to').value)||to;load();};
  c.querySelector('#go').onclick=_reload;
  c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')renderLeft();};
  c.querySelector('#nxsrc').onclick=()=>{source='nx';load();};   // ★Phase5 nx 파생 보기
  // ★0재고 표시 토글 — 서버 필터라 재조회한다(2026-08-28)
  {const z=c.querySelector('#zero');if(z)z.onchange=e=>{incZero=e.target.checked;load();};}
  c.querySelector('#gubun').onchange=renderLeft;c.querySelector('#part').onchange=renderLeft;
  
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#gubun').value='all';c.querySelector('#part').value='';sel=null;renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 품목을 클릭하세요</div>';};
  c.querySelector('#xls').onclick=()=>downloadCSV('생산재고입출고.csv',['파트','자도번','품명','규격','소분류','재고'],curL.map(r=>[pName(r[0]),r[1],r[2],r[3],r[4],r[5]]));
  load();
};

/* 생산재고조회 — 준비/가공/용접 토글 (+용접 집계/BOM풀기) */
SCREEN.prodstock=(c)=>{
  const API=API_BASE;
  const _pad=n=>(''+n).padStart(2,'0');
  const _tod=(()=>{const d=new Date();return `${(''+d.getFullYear()).slice(2)}${_pad(d.getMonth()+1)}${_pad(d.getDate())}`;})();
  let stage='GAGONG', wmode='agg', livePS=[], curYm='', loading=false, source='live';   // livePS=가공/용접 라이브 · ★Phase5 데이터원(기본 라이브)
  let frm=_tod.slice(0,4)+'01', to=_tod;   // YYMMDD 수불기간
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  const ymd2d=y=>{y=(''+(y||'')).trim();return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const d2ymd=v=>{v=(''+(v||'')).trim();return v.length>=10?v.slice(2,4)+v.slice(5,7)+v.slice(8,10):'';};
  const STAGES=[['GAGONG','가공'],['WELD','용접']];   // 준비(키팅) 탭 제거(중복·별도메뉴 폐지)
  const load=async()=>{loading=true;
    const bd=c.querySelector('#body');if(bd)bd.innerHTML=spinRow(11);
    const qs=`frm=${encodeURIComponent(frm)}&to=${encodeURIComponent(to)}`;
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/prodstock?${qs}&source=nx`,{title:'생산재고조회',onBack:()=>{source='live';load();}});}
    try{const r=await fetch(`${API}/api/live/prodstock?${qs}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();livePS=j.rows||[];curYm=j.ym||to.slice(0,4)||'';}
    catch(e){livePS=[];}
    loading=false;draw();};
  const draw=()=>{
    const isWeld=stage==='WELD', bomMode=isWeld&&wmode==='bom';
    const showLine=(stage==='READY')||(isWeld&&wmode==='agg');
    const hasMove = bomMode || stage==='GAGONG' || (isWeld&&wmode==='agg');   // 기초/입출/조정 표시
    let pool;
    const live=(stage==='GAGONG')||(isWeld&&!bomMode);   // 가공·용접집계=라이브 / 준비·BOM풀기=스냅샷
    if(bomMode) pool=DB.weldBom||[];
    else if(stage==='READY') pool=(DB.stock||[]).filter(r=>r.stage==='READY');
    else pool=livePS.filter(r=>r.stage===stage);
    const lines= showLine ? [...new Set(pool.map(r=>r.loc).filter(Boolean))].sort():[];
    const _per=`${esc(ymd2d(frm))} ~ ${esc(ymd2d(to))}`;
    const sub={READY:'키팅 준비재고(라인별) · 원본 PU_T_READY_STOCK · ⚠️스냅샷(라이브 예정)',
               GAGONG:`가공(P0001) 재공 · 원장 9-union · 🟢 수불기간 ${_per}`,
               WELD: bomMode?'용접 BOM풀기(하위품번 전개) · ⚠️스냅샷(SP, 라이브 예정)':`용접(가공제외) 재공 · 라인별 · 🟢 수불기간 ${_per}`}[stage];
    c.innerHTML=`
     <div class="page-title">🏭 생산재고조회</div><div class="page-sub">${sub}</div>
     <div class="toolbar">
       <div class="toggle-group">${STAGES.map(([k,v])=>`<button data-stage="${k}" class="${stage===k?'on':''}">${v}</button>`).join('')}</div>
       ${isWeld?`<div class="toggle-group" style="margin-left:6px"><button data-w="agg" class="${wmode==='agg'?'on':''}">집계</button><button data-w="bom" class="${wmode==='bom'?'on':''}">BOM풀기</button></div>`:''}
       ${live?`<label style="font-size:12px;color:var(--muted);font-weight:600;margin-left:4px">수불기간</label><input type="date" class="inp" id="frm" value="${esc(ymd2d(frm))}" style="min-width:130px"><span style="color:var(--muted);align-self:center">~</span><input type="date" class="inp" id="to" value="${esc(ymd2d(to))}" style="min-width:130px">`:''}
       <input class="inp" id="q" placeholder="${bomMode?'ASSY/자재품번/품명':'품목코드/품명'}">
       ${!bomMode?`<select class="sel" id="type"><option value="">전체유형</option>${Object.entries(TYPE_NM).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>`:''}
       ${showLine?`<select class="sel" id="line"><option value="">전체라인</option>${lines.map(l=>`<option value="${esc(l)}">${esc(lineName(l))}</option>`).join('')}</select>`:''}
       <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:510px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>
     <div class="summary-bar botsum" id="botsum" style="margin-top:6px;position:sticky;bottom:0"></div>`;
    c.querySelectorAll('[data-stage]').forEach(b=>b.onclick=()=>{stage=b.dataset.stage;wmode='agg';draw();});
    {const _nx=c.querySelector('#nxsrc');if(_nx)_nx.onclick=()=>{source='nx';load();};}   // ★Phase5 nx 파생 보기
    c.querySelectorAll('[data-w]').forEach(b=>b.onclick=()=>{wmode=b.dataset.w;draw();});
    let cur=[];
    const sumbar=rows=>{const qty=rows.reduce((a,b)=>a+(+b.qty||0),0),amt=rows.reduce((a,b)=>a+(+b.amt||0),0);
      const html=`<div class="s-item">건수 <b>${won(rows.length)}</b></div>
        <div class="s-item">재고수량 합계 <b>${won(qty)}</b></div>
        <div class="s-item ${amt<0?'neg':''}">재고금액 합계 <b>${wonI(amt)} 원</b></div>`;
      c.querySelector('#sum').innerHTML=html;
      const bs=c.querySelector('#botsum');if(bs)bs.innerHTML=`<div class="s-item" style="font-weight:700">📊 합계</div>${html}`;};
    function wire(apply){
      c.querySelector('#go').onclick=()=>{ if(live) load(); else apply(); };
      c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
      const fi=c.querySelector('#frm'),ti=c.querySelector('#to');
      if(fi)fi.onchange=e=>{const v=d2ymd(e.target.value);if(v)frm=v;};
      if(ti)ti.onchange=e=>{const v=d2ymd(e.target.value);if(v)to=v;};
      if(c.querySelector('#type'))c.querySelector('#type').onchange=apply;
      if(c.querySelector('#line'))c.querySelector('#line').onchange=apply;
      c.querySelector('#gubun').onchange=apply;
      c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#gubun').value='all';if(c.querySelector('#type'))c.querySelector('#type').value='';if(c.querySelector('#line'))c.querySelector('#line').value='';apply();};}
    const gbf=r=>{const gb=c.querySelector('#gubun').value;return gb==='all'||(gb==='plus'?r.qty>0:r.qty<0);};
    const T=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
    // 영업(제품재고조회) 방식 총계행: 이동컬럼(기초/입고/출고/조정/현재고/금액) 정렬 합계
    const gtMove=(rows,lead)=>`<tr class="grandtot"><td colspan="${lead}" class="right">총계</td><td class="num">${won(T(rows,'basic'))}</td><td class="num">${won(T(rows,'inq'))}</td><td class="num">${won(T(rows,'outq'))}</td><td class="num">${won(T(rows,'adj'))}</td><td class="num">${won(T(rows,'qty'))}</td><td></td><td class="num">${wonI(T(rows,'amt'))}</td></tr>`;
    let render;
    if(bomMode){
      c.querySelector('#th').innerHTML=`<tr><th>ASSY 품번</th><th>자재품번</th><th>품명</th><th>거래처</th><th class="num">기초재고</th><th class="num">입고</th><th class="num">출고</th><th class="num">조정</th><th class="num">현재고</th><th class="num">단가</th><th class="num">금액</th></tr>`;
      render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td>${esc(r.assy)||'-'}</td><td><b>${esc(r.mat)}</b></td><td>${esc(r.nm)}</td><td>${esc(r.cust)||'-'}</td><td class="num">${won(r.basic)}</td><td class="num">${won(r.inq)}</td><td class="num">${won(r.outq)}</td><td class="num">${won(r.adj)}</td><td class="num qty"><b>${won(r.qty)}</b></td><td class="num">${won(r.cost)}</td><td class="num"><b>${wonI(r.amt)}</b></td></tr>`).join('')+gtMove(rows,4):`<tr><td colspan="11" class="empty">결과 없음</td></tr>`;sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      wire(()=>{const q=c.querySelector('#q').value.trim().toLowerCase();render(pool.filter(r=>gbf(r)&&(!q||(r.mat||'').toLowerCase().includes(q)||(r.assy||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));});
      c.querySelector('#xls').onclick=()=>downloadCSV('생산재고_용접_BOM풀기.csv',['ASSY품번','자재품번','품명','거래처','기초재고','입고','출고','조정','현재고','단가','금액'],cur.map(r=>[r.assy,r.mat,r.nm,r.cust,r.basic,r.inq,r.outq,r.adj,r.qty,r.cost,Math.round(r.amt)]));
      render(pool);
      enableSort(c,['assy','mat','nm','cust','basic','inq','outq','adj','qty','cost','amt'],()=>cur,render);
    } else if(hasMove){
      c.querySelector('#th').innerHTML=`<tr><th>품목코드</th><th>품명</th><th>유형</th>${showLine?'<th class="center">라인</th>':''}<th class="num">기초재고</th><th class="num">입고</th><th class="num">출고</th><th class="num">조정</th><th class="num">현재고</th><th class="num">단가</th><th class="num">금액</th></tr>`;
      render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td>${showLine?`<td class="center">${esc(lineName(r.loc))||'-'}</td>`:''}<td class="num">${won(r.basic)}</td><td class="num">${won(r.inq)}</td><td class="num">${won(r.outq)}</td><td class="num">${won(r.adj)}</td><td class="num qty"><b>${won(r.qty)}</b></td><td class="num">${won(r.cost)}</td><td class="num"><b>${wonI(r.amt)}</b></td></tr>`).join('')+gtMove(rows,showLine?4:3):`<tr><td colspan="11" class="empty">결과 없음</td></tr>`;sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      wire(()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value,ln=showLine?c.querySelector('#line').value:'';
        render(pool.filter(r=>gbf(r)&&(!t||r.type===t)&&(!ln||r.loc===ln)&&(!q||(r.cd||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));});
      c.querySelector('#xls').onclick=()=>downloadCSV('생산재고_'+stage+'.csv',['품목코드','품명','유형',...(showLine?['라인']:[]),'기초재고','입고','출고','조정','현재고','단가','금액'],cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,...(showLine?[lineName(r.loc)]:[]),r.basic,r.inq,r.outq,r.adj,r.qty,r.cost,Math.round(r.amt)]));
      render(pool);
      enableSort(c,['cd','nm','type',...(showLine?['loc']:[]),'basic','inq','outq','adj','qty','cost','amt'],()=>cur,render);
    } else {
      c.querySelector('#th').innerHTML=`<tr><th>품목코드</th><th>품명</th><th>유형</th><th class="center">라인</th><th class="num">재고수량</th><th class="center">단위</th><th class="num">단가</th><th class="num">재고금액</th></tr>`;
      render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td><td class="center">${esc(lineName(r.loc))||'-'}</td><td class="num qty">${won(r.qty)}</td><td class="center">${esc(r.uom)}</td><td class="num">${won(r.cost)}</td><td class="num"><b>${wonI(r.amt)}</b></td></tr>`).join('')+`<tr class="grandtot"><td colspan="4" class="right">총계</td><td class="num">${won(T(rows,'qty'))}</td><td></td><td></td><td class="num">${wonI(T(rows,'amt'))}</td></tr>`:`<tr><td colspan="8" class="empty">결과 없음</td></tr>`;sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      wire(()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),t=c.querySelector('#type').value,ln=c.querySelector('#line').value;
        render(pool.filter(r=>gbf(r)&&(!t||r.type===t)&&(!ln||r.loc===ln)&&(!q||(r.cd||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));});
      c.querySelector('#xls').onclick=()=>downloadCSV('생산재고_준비.csv',['품목코드','품명','유형','라인','재고수량','단위','단가','재고금액'],cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,lineName(r.loc),r.qty,r.uom,r.cost,Math.round(r.amt)]));
      render(pool);
      enableSort(c,['cd','nm','type','loc','qty','uom','cost','amt'],()=>cur,render);
    }
  };
  load();
};

/* 용접 재고 — 집계 / BOM풀기 토글 */
SCREEN.stweld=(c)=>{
  let mode='agg';
  const pool=DB.stock.filter(r=>r.stage==='WELD'), bom=DB.weldBom||[];
  const lines=[...new Set(pool.map(r=>r.loc).filter(Boolean))].sort();
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">용접 재고</div>
     <div class="page-sub">용접(가공제외) 재공 · ${mode==='agg'?'ASSY 단위 집계':'BOM풀기(하위품번 전개) — ✔검증 07/15: 142,353 / ₩346.5M'}</div>
     <div class="toolbar">
       <div class="toggle-group"><button id="t-agg" class="${mode==='agg'?'on':''}">집계</button><button id="t-bom" class="${mode==='bom'?'on':''}">BOM풀기</button></div>
       <input class="inp" id="q" placeholder="${mode==='agg'?'품목코드/품명':'ASSY/자재품번/품명'}">
       ${mode==='agg'?`<select class="sel" id="line"><option value="">전체라인</option>${lines.map(l=>`<option value="${esc(l)}">${esc(lineName(l))}</option>`).join('')}</select>`:''}
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:520px"><table class="tbl"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    let cur=[];
    function sumbar(rows){const qty=rows.reduce((a,b)=>a+(+b.qty||0),0),amt=rows.reduce((a,b)=>a+(+b.amt||0),0);
      c.querySelector('#sum').innerHTML=`<div class="s-item">건수 <b>${won(rows.length)}</b></div>
        <div class="s-item">재고수량 합계 <b>${won(qty)}</b></div>
        <div class="s-item ${amt<0?'neg':''}">재고금액 합계 <b>${won(amt)} 원</b></div>`;}
    if(mode==='agg'){
      c.querySelector('#th').innerHTML=`<tr><th>품목코드</th><th>품명</th><th>유형</th><th class="center">라인</th><th class="num">재고수량</th><th class="center">단위</th><th class="num">단가</th><th class="num">재고금액</th></tr>`;
      const render=rows=>{cur=rows;
        c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td><b>${esc(r.cd)}</b></td><td>${esc(r.nm)}</td><td>${tbadge(r.type)}</td><td class="center">${esc(lineName(r.loc))||'-'}</td><td class="num qty">${won(r.qty)}</td><td class="center">${esc(r.uom)}</td><td class="num">${won(r.cost)}</td><td class="num"><b>${won(r.amt)}</b></td></tr>`).join(''):`<tr><td colspan="8" class="empty">결과 없음</td></tr>`;
        sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
      const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),ln=c.querySelector('#line').value;
        render(pool.filter(r=>(!ln||r.loc===ln)&&(!q||r.cd.toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
      c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
      c.querySelector('#line').onchange=apply;
      c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#line').value='';apply();};
      c.querySelector('#xls').onclick=()=>downloadCSV('용접재고_집계.csv',['품목코드','품명','유형','라인','재고수량','단위','단가','재고금액'],cur.map(r=>[r.cd,r.nm,TYPE_NM[r.type]||r.type,r.loc,r.qty,r.uom,r.cost,r.amt]));
      render(pool);
    } else {
      c.querySelector('#th').innerHTML=`<tr><th>ASSY 품번</th><th>자재품번</th><th>품명</th><th>거래처</th><th class="num">재고수량</th><th class="num">단가</th><th class="num">금액</th></tr>`;
      const render=rows=>{cur=rows;
        c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr><td>${esc(r.assy)||'-'}</td><td><b>${esc(r.mat)}</b></td><td>${esc(r.nm)}</td><td>${esc(r.cust)||'-'}</td><td class="num qty">${won(r.qty)}</td><td class="num">${won(r.cost)}</td><td class="num"><b>${won(r.amt)}</b></td></tr>`).join(''):`<tr><td colspan="7" class="empty">결과 없음</td></tr>`;
        sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${bom.length}건`;};
      const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase();
        render(bom.filter(r=>(!q||(r.mat||'').toLowerCase().includes(q)||(r.assy||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
      c.querySelector('#go').onclick=apply;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
      c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';apply();};
      c.querySelector('#xls').onclick=()=>downloadCSV('용접재고_BOM풀기.csv',['ASSY품번','자재품번','품명','거래처','재고수량','단가','금액'],cur.map(r=>[r.assy,r.mat,r.nm,r.cust,r.qty,r.cost,r.amt]));
      render(bom);
    }
    c.querySelector('#t-agg').onclick=()=>{mode='agg';draw();};
    c.querySelector('#t-bom').onclick=()=>{mode='bom';draw();};
  };
  draw();
};

/* ===== 생산: 주문업로드 (w_pr_plan_010) — LG PU-SCS Purchase Order → nx.recv_dtl ===== */
SCREEN.orderupload=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),nfrom:'',nto:'',done:'all',item:'',wo:'',cr:''};
  let data={rows:[],count:0,sum_qty:0,sum_amt:0}, loading=false, msg='', upcr='C', upfile=null;
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,need_from:F.nfrom,need_to:F.nto,done:F.done,item:F.item,wo:F.wo,cr:F.cr});
    try{const r=await fetch(`${API}/api/order/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';data={rows:[],count:0,sum_qty:0,sum_amt:0};}
    loading=false;draw();};
  const doUpload=async()=>{
    if(!upfile){alert('업로드할 엑셀 파일을 선택하세요.');return;}
    msg='업로드 중...';draw();
    const b64=await new Promise(res=>{const fr=new FileReader();fr.onload=()=>res(fr.result);fr.readAsDataURL(upfile);});
    try{const r=await fetch(`${API}/api/order/upload`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cr:upcr,b64})});
      const j=await r.json();
      if(j.ok){alert(`주문 UPLOAD 완료\n신규 ${nf(j.inserted)} · 갱신 ${nf(j.updated)} · 총 ${nf(j.total)}건 (구분 ${j.cr})`);upfile=null;load();return;}
      alert('업로드 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('업로드 실패: '+e);}
    msg='';draw();};
  const draw=()=>{
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('orderupload'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">📥 주문업로드 <span style="font-size:12px;color:var(--muted);font-weight:400">LG PU-SCS Purchase Order → 주문원장</span></div>
     <div class="page-sub">LG Open PO 엑셀(Material·PO No·Delivery Date·Order/Open Qty·P/S Order·Order Date·Unit Price)을 업로드합니다. 저장 <code>nx.recv_dtl</code> · 레거시 <code>SP_LGE_RECV_ORDER</code>/w_pr_plan_010 실검증(품번·단가·워크오더·납기·CR 0불일치)</div>
     <div class="toolbar">
       <label class="tl">주문기간</label><input class="inp" type="date" id="o-from" value="${F.from}"> ~ <input class="inp" type="date" id="o-to" value="${F.to}">
       <label class="tl">납기</label><input class="inp" type="date" id="o-nf" value="${F.nfrom}"> ~ <input class="inp" type="date" id="o-nt" value="${F.nto}">
       <label class="tl">납품</label><select class="inp" id="o-done"><option value="all"${F.done==='all'?' selected':''}>전체</option><option value="undone"${F.done==='undone'?' selected':''}>미완료</option><option value="done"${F.done==='done'?' selected':''}>완료</option></select>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">품번</label><input class="inp" id="o-item" value="${esc(F.item)}" style="width:130px">
       <label class="tl">W/O</label><input class="inp" id="o-wo" value="${esc(F.wo)}" style="width:110px">
       <label class="tl">구분</label><select class="inp" id="o-cr"><option value=""${F.cr===''?' selected':''}>전체</option><option value="C"${F.cr==='C'?' selected':''}>C(SAC)</option><option value="R"${F.cr==='R'?' selected':''}>R(RAC)</option></select>
       <button class="btn" id="o-search">🔍 조회</button>
       <div class="spacer"></div>
       ${canW?`<label class="tl">업로드</label><select class="inp" id="o-upcr"><option value="C"${upcr==='C'?' selected':''}>C(SAC)</option><option value="R"${upcr==='R'?' selected':''}>R(RAC)</option></select>
       <input type="file" id="o-file" accept=".xls,.xlsx" style="width:200px">
       <button class="btn" id="o-upload" style="background:#1c47a0;color:#fff">📥 주문UPLOAD</button>`:`<span style="color:#c0392b;font-size:12px">🔒 업로드 권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">총 <b>${nf(data.count)}</b>건 · 수량 <b>${nf(data.sum_qty)}</b> · 금액 <b>${nf(data.sum_amt)}</b>원${data.count>=5000?' <span style="color:#c0392b">(상위 5,000건)</span>':''}</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:12px"><thead><tr>
       <th>주문번호</th><th>주문일자</th><th>품번</th><th>품명</th><th class="num">주문수량</th><th class="num">잔량</th><th>납기</th><th>시각</th><th>WORK-ORDER</th><th class="num">주문단가</th><th class="num">금액</th><th>구분</th></tr></thead>
      <tbody>${loading?spinRow(12):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td>${esc(r.ORDER_NO)}</td><td class="center">${ymd(r.ORDER_YMD)}</td><td><b>${esc(r.ITEM_CODE)}</b></td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="num">${nf(r.ORDER_QTY)}</td><td class="num">${nf(r.REMAIN_QTY)}</td><td class="center">${ymd(r.NEED_BY_YMD)}</td><td class="center">${esc(r.NEED_BY_HM)}</td>
        <td>${esc(r.WORK_ORDER)}</td><td class="num">${nf(r.ITEM_COST)}</td><td class="num">${nf(r.AMT)}</td><td class="center">${esc(r.CR_FLAG)}</td></tr>`).join(''):`<tr><td colspan="12" class="empty">조회 결과 없음 — 조건을 바꾸거나 엑셀을 업로드하세요.</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#o-search').onclick=()=>{F.from=g('#o-from').value;F.to=g('#o-to').value;F.nfrom=g('#o-nf').value;F.nto=g('#o-nt').value;F.done=g('#o-done').value;F.item=g('#o-item').value;F.wo=g('#o-wo').value;F.cr=g('#o-cr').value;load();};
    if(canW){g('#o-upcr').onchange=e=>upcr=e.target.value;
      g('#o-file').onchange=e=>upfile=e.target.files[0]||null;
      g('#o-upload').onclick=doUpload;}
    ['#o-item','#o-wo'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#o-search').click();});
  };
  load();
};

/* ===== 생산: 생산계획업로드 (w_pr_plan_020) — ★2026-09-03 삭제 =====
   구 SCREEN.planupload 는 제거했다. 정본 = 「생산계획업로드」(js/screens.planrev.js
   SCREEN.planuploadrev, 백엔드 routers/planrev.py).

   왜 지웠나 — 이 화면의 「자재소요·조달 편성」이 부르던 soyo 편성경로는 2026-08-31 에
   은퇴했다(nx.plan_part_dtl 을 19컬럼으로 재생성해 뷰 v_plan_part_copy_new 가 깨지고
   410·키팅·420 조회가 막히는 사고). 그 뒤 화면은 메뉴에서 숨겨진 채 죽은 코드로 남아
   있었고, soyo 에만 있던 route-aware STEP6 도 2026-09-03 에 planrev 로 이식을 마쳐
   더 이상 보존할 이유가 없다.

   ※조회·업로드는 신 화면이 **같은 API**(/api/plan/list · /api/plan/upload)를 쓴다.
   ※권한 키 'planupload' 는 신 화면도 그대로 사용한다(screens.planrev.js:254) — 유지. */

/* ★파트별생산계획 드래그실적 — 확인/취소 버튼은 파일 로드시 문서에 딱 한 번 캡처단계로 건다.
   화면함수(SCREEN.partplan) 안에서 걸면, 이미 열려 있던 탭은 그 함수가 다시 실행되지 않아
   새 코드가 영영 안 걸린다(2026-08-30: 확인 버튼이 안 먹던 진짜 원인 — 040 에서 겪은 것과 동일).
   실제 핸들러는 각 화면 인스턴스가 자기 컨테이너의 _dpFn 에 최신값을 꽂아둔다. */
if(!window._DP_CLICK_BOUND){
  window._DP_CLICK_BOUND=1;
  document.addEventListener('click',ev=>{
    const b=ev.target&&ev.target.closest?ev.target.closest('#pp-dp-ok,#pp-dp-clr'):null;
    if(!b)return;
    ev.preventDefault(); ev.stopPropagation();
    if(b.disabled){alert('처리 중입니다. 잠시 후 다시 눌러주세요.');return;}
    let host=b, fn=null;
    while(host){ if(host._dpFn){fn=host._dpFn;break;} host=host.parentElement; }
    if(!fn){alert('화면이 준비되지 않았습니다.\n[조회]를 눌러 다시 불러온 뒤 시도해 주세요.');return;}
    const f=(b.id==='pp-dp-ok')?fn.ok:fn.no;
    if(!f){alert('처리 함수를 찾지 못했습니다. [조회] 후 다시 시도해 주세요.');return;}
    try{ f(); }
    catch(e){ alert('실적처리 중 오류\n\n'+(e&&e.stack?e.stack:e)); }
  },true);
}

SCREEN.partplan=(c)=>{
  // 파트별 생산계획 — 레거시 w_pr_input_410_new 재현. ★데이터/색상 정본 = 키팅과 동일 SP(GROUP BY gpc·wo·swo·assy·upper·item, 날짜피벗) → /api/kitting/grid 재사용(nx 직독). 값·색상 키팅과 자동일치.
  //
  // ┌─ 2026-08-18 수정내역 (레거시 화면 대조하며 보완) ────────────────────────────────
  // │ 1. 필터 추가: 라인(LINE_NO)·제번(WORK_ORDER) — 레거시엔 있었으나 웹에 누락돼 있던 것.
  // │    · 라인 드롭다운 소스 = /api/plan/part410/lines (PR_T_PLAN_PART_COPY.LINE_NO distinct, CA/CM/GR…).
  // │      ※ /api/planinput/lines(PR003 주문구분: 설치/이지링크/CKD…)는 코드체계가 달라 쓰면 안 됨.
  // │    · 제번은 백엔드 part410에 wo 파라미터를 신규 추가(kitting.py)했으나, 아래 3번으로 현재는 클라 필터 사용.
  // │ 2. 툴바 2줄 배치(레거시 순서): 1줄=기준일자·자도번작업처·파트·생산여부·구분·적용일수·소스,
  // │    2줄=라인·제번·ASSY도번·도번. 생산여부/구분 라디오는 테두리 박스로 그룹 구획(레거시 모양).
  // │    라벨명 변경: 도번→ASSY도번, 자도번→도번. 건수요약은 표 아래 왼쪽으로 이동(계획합·인원은 tfoot과 중복이라 제거).
  // │ 3. ★조회버튼 없이 즉시필터: 한 번 조회한 캐시(st.rows)에서 클라이언트 필터링(레거시 setfilter 방식).
  // │    · 서버 재조회 필요 = 기준일자·자도번작업처·적용일수·소스 4개뿐.
  // │    · 즉시필터 = 파트·라인·ASSY도번·도번·제번·생산여부·구분. 텍스트칸은 지워도 재조회 안 함.
  // │ 4. ★소계행/집계뷰 색상 롤업(aggRank): 하위행 중 관련색이 하나라도 있으면 그 색. 녹3 > 노랑4 > 주황6, 무색('0')은 판정 제외.
  // │    (셀 단위 finRank와는 우선순위가 반대 — 소계는 "진행중인 게 하나라도 있으면 그 상태로 보이게")
  // │ 5. 집계뷰 = 상세뷰 청록 소계행과 1:1 동일하게 재구성. 그룹키를 "연속된 같은 도번 구간"으로(상세 blk 분할과 동일),
  // │    정렬도 백엔드 순서 유지(도번순 재정렬 제거). 집계행 청록배경 + 클릭시 상세 펼침/접힘(▶/▼, 상세는 집계행 위에 표시).
  // │ 6. 컬럼: 품명·Part Plan Ymd Output Hm 삭제 / 재고 7종 추가(자재재고·생산재고·도번고정재고·ASSY재고·출하·생산준비재고·Work Order).
  // │    재고값은 kitting.py part410이 충당계산에 쓰던 풀(midstk/partstk/fixstk/assystk/saled/rstock)을 행에 노출한 것 = 표시전용.
  // │    좌측 코드컬럼(파트·Assy도번·상위도번·도번) 가운데정렬.
  // │ 7. ★후행컬럼(일자컬럼 뒤) = TAILDEF 정의 기반으로 리팩터 + 유저별 순서변경 지원.
  // │    · 기본순서(레거시 배치): LG INPUT · LG INPUT시간 · Work Order · LG OUTPUT시간 · 앞공정 · 현재공정 · 자재재고 · 생산재고 · 도번고정재고 · ASSY재고 · 출하 · 생산준비재고
  // │    · ★앞공정/현재공정 = 레거시 SP(SP_PR_CREATE_PLAN_파트별_생산계획계산_NEW_250826) 1285줄 산식 이식.
  // │      현재공정 = 작업중 전표재고(#TEMP_전표재고)[item·gpc·gagong_proc_seq]
  // │      앞공정   = PROC_SEQ=1 → 0, else 전표재고[item·PRIOR_gpc·PRIOR_seq] − 현재공정
  // │      → 01라인(용접 S5 → 조립 S5-2) 2공정 품목에서 뒷공정 실적이 잡히면 앞공정 잔량이 상계되어 0.
  // │      (SP 본문은 pncind 계정으로 DB에서 직독 — 일반계정은 VIEW DEFINITION 권한 없어 못 읽음)
  // │    · LG OUTPUT시간 = 백엔드 lgh(PR_T_PLAN_DTL의 ORG_PLAN_YMD+ORG_OUTPUT_HM) 신규 표시.
  // │    · ★헤더 드래그앤드롭으로 순서 이동 → localStorage 'pp410_tailorder'에 저장(사람마다 다르게 보기).
  // │      DB 미사용이라 다른 PC에선 기본순서. 신규 컬럼을 TAILDEF에 추가하면 저장된 순서 뒤에 자동 보충되므로 기존 사용자도 안 깨짐.
  // │    · 헤더/행/소계/집계/푸터가 전부 tailTh()·tailTd()·tailBlank()를 쓰므로 컬럼 추가·삭제는 TAILDEF만 고치면 됨.
  // └────────────────────────────────────────────────────────────────────────────
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const f2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const wlab=y=>{if(!y||y.length<6)return dcol(y);const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));const dow='일월화수목금토'[dt.getDay()];return `${y.slice(4,6)}${dow}`;};
  const isWkend=y=>{if(!y||y.length<6)return false;const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return dt.getDay()===0||dt.getDay()===6;};
  // 당김,변경 = CHANGE_DAY + ',' + (LOT_QTY − LAST_LOT_QTY). 전차수 대비 일자·수량 변경(레거시 c_remarks3). 둘다 0이면 공백, 수량변경시 빨강.
  const pulltxt=r=>{const cd=(r.change_day||'').trim(),ld=+r.lot_diff||0;if(!cd&&!ld)return '';return `${cd}${cd&&ld?',':''}${ld?(ld>0?'+':'')+ld:(cd?'':'')}`;};
  const T=new Date();
  // ★색상 정본(레거시 c_color CASE = kitting finBg 이식): 90주황(출하완료)/70노랑(생산완료)/50·10녹(키팅완료)/else 백(미키팅)
  // 색: '6'=출하완료(살구) · '7'=현재공정/작업중전표(진한주황, 출하와 구분) · '4'=생산완료(노랑) · '3'=키팅완료(녹)
  const finBg=f=>f==='6'?'#fac090':(f==='7'?'#ed7d31':(f==='4'?'#ffff00':(f==='3'?'#669900':'')));
  // 드래그 선택 셀 표시
  if(!document.getElementById('dp-style')){
    const stl=document.createElement('style'); stl.id='dp-style';
    // ★선택 표시 = 키팅(준비실적처리)과 동일 — 연파랑 오버레이 + 얇은 파란 테두리.
    //   배경'색'(녹/노랑 완료색)은 살려야 하므로 background-image 로 연한 막만 덧씌운다.
    stl.textContent='.dp-c{cursor:cell;user-select:none}'
      +'.dp-c:hover{outline:2px solid #9dc0e8;outline-offset:-2px}'
      +'.dp-on{outline:2px solid #4a86e8 !important;outline-offset:-2px;font-weight:700;'
      +'background-image:linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72))}'
      // ★일자 헤더·셀 가운데정렬 강제 — .center 가 다른 규칙에 밀리는 경우 대비
      +'.pp-tbl th.center,.pp-tbl td.center{text-align:center !important}'
      /* ★범위선택(복사용) — 일자칸 외 전 컬럼. 실적선택(.dp-on)과 색을 달리해 헷갈리지 않게.
           실적=파랑 / 복사선택=회청색. 배경'색'(완료색)은 살리려고 background-image 막만 덧씌운다.
         ★2026-09-03: 색칠된 셀(녹/노랑/주황)은 인라인 style="background:#..." 로 칠해지는데,
           background 단축속성이 background-image 를 **덮어써서** 선택막이 안 보였다(사용자 지적).
           → outline 을 함께 준다. outline 은 background 와 다른 속성이라 인라인에 안 밀리고,
             테두리라 배경색도 가리지 않는다. !important 는 인라인보다 우선하기 위한 것. */
      +'.pp-sel{background-image:linear-gradient(rgba(148,163,184,.34),rgba(148,163,184,.34));'
      +'outline:2px solid #64748b !important;outline-offset:-2px}'
      // 실적선택이 우선 — 두 클래스가 겹치면 파란 테두리를 보인다(실적이 더 중요한 상태)
      +'.pp-sel.dp-on{outline:2px solid #4a86e8 !important}'
      +'.pp-tbl.pp-copying{cursor:cell}'
      /* ★소계/집계행 = 펼침(더블클릭) 전용. 선택 대상이 아니므로 표시가 붙어도 무시하고,
           더블클릭 시 텍스트가 파랗게 잡히는 것도 막는다(레거시 동일 거동). */
      +'.pp-tbl tr.pp-agg td{user-select:none;-webkit-user-select:none}'
      +'.pp-tbl tr.pp-agg td.pp-sel{background-image:none;outline:none !important}'
      /* 항목보기(컬럼 선택) 모달 */
      +'.ppcol-ov{position:fixed;inset:0;z-index:1250;background:rgba(15,23,42,.38);display:flex;align-items:center;justify-content:center}'
      +'.ppcol-bx{background:#fff;border-radius:10px;box-shadow:0 18px 48px rgba(10,25,55,.4);width:420px;max-width:94vw;display:flex;flex-direction:column;max-height:82vh}'
      +'.ppcol-h{padding:11px 14px;border-bottom:1px solid #dbe3ee;font-weight:700;display:flex;align-items:center;gap:8px}'
      +'.ppcol-b{flex:1;min-height:0;overflow:auto;padding:4px 0}'
      +'.ppcol-f{padding:9px 14px;border-top:1px solid #dbe3ee;display:flex;gap:6px;justify-content:flex-end}'
      // ★user-select:none — 행을 끌 때 텍스트가 파랗게 잡히면 드래그가 안 된다(2026-09-03)
      +'.ppcol-r{display:flex;align-items:center;gap:9px;padding:5px 14px;cursor:grab;'
      +'border-bottom:1px solid #f1f5f9;user-select:none;-webkit-user-select:none}'
      +'.ppcol-r:hover{background:#f5f8fd}'
      +'.ppcol-r.drag{opacity:.45;background:#e8effb}'
      +'.ppcol-r.over{box-shadow:inset 0 3px 0 #2563eb;background:#f0f6ff}'
      +'.ppcol-n{width:26px;color:#94a3b8;font-size:11px;text-align:right}'
      +'.ppcol-t{flex:1}'
      // ▲▼ 순서이동 버튼 — 평소엔 흐리게, 행에 올리면 또렷하게
      +'.ppcol-mv{display:flex;gap:2px;opacity:.25;transition:opacity .12s}'
      +'.ppcol-r:hover .ppcol-mv{opacity:1}'
      +'.ppcol-mv button{width:20px;height:18px;padding:0;line-height:1;font-size:9px;cursor:pointer;'
      +'border:1px solid #cbd5e1;background:#fff;border-radius:3px;color:#475569}'
      +'.ppcol-mv button:hover:not(:disabled){background:#e8effb;border-color:#2563eb;color:#1c47a0}'
      +'.ppcol-mv button:disabled{opacity:.3;cursor:default}'
      /* 일자컬럼 경계 — 표에서 이 자리에 날짜 컬럼들이 들어간다. 위=앞, 아래=뒤 */
      +'.ppcol-sep{display:flex;align-items:center;gap:8px;padding:5px 14px;margin:2px 0;'
      +'background:repeating-linear-gradient(45deg,#eef4fd,#eef4fd 6px,#e3ecfa 6px,#e3ecfa 12px);'
      +'border-top:2px solid #2563eb;border-bottom:2px solid #2563eb;'
      +'color:#1c47a0;font-size:11px;font-weight:700;user-select:none}'
      /* 우클릭 컨텍스트 메뉴 */
      +'.pp-ctx{position:fixed;z-index:1300;background:#fff;border:1px solid #cbd5e1;border-radius:7px;'
      +'box-shadow:0 10px 30px rgba(10,25,55,.3);padding:4px 0;min-width:150px;font-size:13px}'
      +'.pp-ctx div{padding:6px 15px;cursor:pointer;white-space:nowrap}'
      +'.pp-ctx div:hover{background:#eff4fd}';
    document.head.appendChild(stl);
  }
  const finFg=f=>(f==='3'||f==='7')?'#ffffff':'';   // 진한 녹·주황 배경엔 흰 글자(가독)
  // ★기본 소스 = 신규DB(웹편성). 레거시 대조는 소스를 nx/라이브로 바꿔서 본다(2026-08-26).
  // ★기준일 = 마지막 계획업로드의 일자축 첫날(planBaseIso, 2026-08-28 사용자 확정).
  //   당일 기준이면 업로드 전날이 잡혀, 미출하분이 재편성되며 충당된 재고와 어긋난다.
  const st={dates:[],rows:[],cnt:0,plan_sum:0,inwon:0,note:'',base:planBaseIso(),gigan:2,wc:'',part:'',line:'',dono:'',jado:'',wo:'',unfin:'미생산',view:'상세',src:'new',lines:[],loading:false,msg:'',expand:new Set(),dpConf:null,dpSel:new Map(),dpDrag:null,dpBusy:false,dpQov:new Map()};
  // ★라인 드롭다운 = 이 그리드 Line No 컬럼 실사용값(PR_T_PLAN_PART_COPY.LINE_NO distinct, CA/CM/GR 등). PR003 주문구분과는 다른 코드체계.
  const loadLines=async()=>{try{const r=await fetch(`${API}/api/plan/part410/lines?src=${st.src}`);const j=await r.json();st.lines=j.rows||[];}catch(e){st.lines=[];}};
  /* ==== 드래그 실적처리 (레거시 w_pr_input_260 '드래그 → 확인 F12' 이식) ====
     ★실적 단위 = 도번. 조건문에서 파트를 고르고, 그 파트가 파트마스터에
       '생산실적' 방식(R 준비재고 / W 자재창고출고)으로 설정돼 있어야 한다.
       R = 녹색(키팅완료) 셀만 선택 가능 · W = 색 무관 */
  const dpOn=()=>!!(st.dpConf&&st.dpConf.enabled&&st.part);
  const dpKey=(r,ymd)=>[r.gpc||'',r.item||'',r.wo||'',ymd].join('|');
  /* ★잡을 수 있는 수량 = 잔여계획을 재고 상한으로 자른 값.
       R(생산준비재고) = 준비재고(ready_stock)만큼만. 준비재고 3이면 계획이 5라도 3.
       W(자재창고출고) = 자재창고에서 BOM만큼 빼므로 계획 잔여 전량(부족분은 서버가 판정).
     사용자가 더블클릭으로 정한 수량(st.dpQov)이 있으면 그 값이 우선(상한 내에서). */
  const dpCap=r=>{
    if(!st.dpConf)return Infinity;
    if(st.dpConf.type==='R')return Math.max(+r.ready_stock||0,0);
    return Infinity;
  };
  const dpRem=(r,planRem,key)=>{
    const cap=dpCap(r);
    let v=Math.min(planRem,cap===Infinity?planRem:cap);
    if(key&&st.dpQov.has(key))v=Math.min(v,Math.max(+st.dpQov.get(key)||0,0));
    return Math.max(Math.floor(v),0);
  };
  const dpLoadConf=async()=>{
    if(!st.part){st.dpConf=null;return;}
    try{ st.dpConf=await fetch(`${API}/api/dragprod/conf?part=${encodeURIComponent(st.part)}`).then(x=>x.json()); }
    catch(e){ st.dpConf=null; }
  };
  const dpClear=()=>{st.dpSel.clear();st.dpQov.clear();render();};
  const dpConfirm=async()=>{
    if(st.dpBusy)return;
    if(!st.dpSel.size)return alert('실적을 잡을 셀을 드래그로 선택하세요.');
    // ★key(gpc|item|wo|ymd)를 함께 실어 보낸다 — 처리 후 그 셀만 부분갱신하기 위함
    const rows=[...st.dpSel.entries()].map(([k,v])=>Object.assign({key:k},v));
    const tot=rows.reduce((a,x)=>a+(+x.qty||0),0);
    // 사전점검
    let chk=null;
    try{ chk=await fetch(`${API}/api/dragprod/check`,{method:'POST',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({rows})}).then(x=>x.json()); }
    catch(e){ return alert('점검 실패: '+e); }
    const bad=(chk.rows||[]).filter(x=>!x.ok);
    let warn='';
    if(bad.length){
      warn='\n\n⚠ 실적 불가 '+bad.length+'건\n'
          +bad.slice(0,5).map(x=>'  · '+x.item+' — '
            +(x.lack&&x.lack.length?x.lack.slice(0,2).map(l=>l.mat+' 부족 '+nf(l.lack)).join(', '):x.reason)).join('\n');
    }
    // ★실적일자 = 오늘(작업일). 기준일자(st.base)는 계획을 보는 축일 뿐이라
    //   그걸 보내면 지난 일자로 실적이 잡히고, 마감된 일자면 서버가 거부한다
    //   (2026-08-30 실측: 기준일 260828 로 보내 "일마감된 일자" 실패). 바코드실적(520)도 오늘 기준.
    const today6=(()=>{const t=new Date();
      return String(t.getFullYear()).slice(2)+String(t.getMonth()+1).padStart(2,'0')+String(t.getDate()).padStart(2,'0');})();
    if(!window.confirm(`${st.dpConf.part_nm||st.part} · ${st.dpConf.type_nm}\n`
                      +`실적일자 ${today6.slice(0,2)}/${today6.slice(2,4)}/${today6.slice(4,6)} (오늘)\n`
                      +`${rows.length}건 / 합계 ${nf(tot)}\n`
                      +`\n생산실적 + BOM자재 차감 + 세트재고 차감이 함께 처리됩니다.${warn}`
                      +`\n\n진행할까요?`))return;
    st.dpBusy=true;render();
    try{
      const r=await fetch(`${API}/api/dragprod/save`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ymd:today6,rows,
          user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})}).then(x=>x.json());
      if(!r.ok)throw new Error(r.detail||'실패');
      let m='실적처리 완료 — '+r.done+'건';
      if(r.skipped)m+='\n\n제외 '+r.skipped+'건\n'
        +(r.skips||[]).slice(0,5).map(x=>'  · '+x.item+' — '+x.reason).join('\n');
      st.dpSel.clear(); st.dpQov.clear();   // 처리 끝난 셀의 수량조정은 소멸(040 동일)
      /* ★전체 재조회(load) 금지 — 8,500행을 다시 받아 화면을 통째로 다시 그리면
           스크롤·툴바가 리셋돼 "계속 새로고침되는" 것처럼 보인다(2026-08-30 지적).
         처리된 만큼을 캐시(st.rows)에 직접 반영하고 표만 부분갱신한다.
         반영 규칙 = 화면 표기(완료/계획)와 동일 — 잡은 수량을 '완료(cover)'에 더한다.
           일자칸 → r.dcov[ymd] += qty · 당일이전 → r.prior_cover += qty
         셀 색(dfin/prior_fin)은 계획을 다 채웠을 때만 '생산완료(4)'로 올린다. */
      const bump=(key,qty)=>{
        const p=String(key).split('|');            // gpc|item|wo|ymd
        const [gpc,item,wo,ymd]=[p[0]||'',p[1]||'',p[2]||'',p[3]||''];
        (st.rows||[]).forEach(r=>{
          if((r.gpc||'')!==gpc||(r.item||'')!==item||(r.wo||'')!==wo)return;
          if(ymd==='PRIOR'){
            const pl=+r.prior_plan||0;
            r.prior_cover=Math.min((+r.prior_cover||0)+qty,pl);
            if(r.prior_cover>=pl&&pl>0&&(r.prior_fin||'0')==='3')r.prior_fin='4';
          }else{
            const pl=(r.days&&r.days[ymd])||0; if(!pl)return;
            r.dcov=r.dcov||{}; r.dfin=r.dfin||{};
            r.dcov[ymd]=Math.min((+r.dcov[ymd]||0)+qty,pl);
            if(r.dcov[ymd]>=pl&&(r.dfin[ymd]||'0')==='3')r.dfin[ymd]='4';
          }
          r.finish=(+r.finish||0)+qty;
        });
      };
      // 서버가 실제 처리한 수량(준비재고 상한으로 잘렸을 수 있음)만 반영
      (r.rows||[]).forEach(x=>{ if(x.key)bump(x.key,+x.qty||0); });
      redrawBody();
      alert(m);
    }catch(e){ alert('실적처리 실패: '+e.message); }
    st.dpBusy=false;
    // 배지(선택 건수·처리중 표시)만 갱신 — 표는 위에서 이미 부분갱신했다
    const bd=c.querySelector('#pp-dp-cnt'); if(bd)bd.textContent=st.dpSel.size+'건';
    const bk=c.querySelector('#pp-dp-ok');  if(bk){bk.disabled=false;bk.textContent='✅ 확인';}
  };

  const load=async()=>{st.loading=true;render();
    // ★전체를 한 번만 조회해 캐시 → 파트·라인·ASSY도번·도번·제번·미생산·구분은 재조회 없이 클라이언트에서 즉시 필터(레거시 동일).
    //   재조회(=조회버튼)는 기준일·자도번작업처·적용일수·소스 변경 시만.
    const qs=new URLSearchParams({from_ymd:st.base,gigan:st.gigan,wc:st.wc,view:'상세',unfin:'전체',src:st.src,limit:40000});
    try{const r=await fetch(`${API}/api/plan/part410?${qs}`);const j=await r.json();st.dates=j.dates||[];st.rows=j.rows||[];st.cnt=j.cnt||0;st.plan_sum=j.plan_sum||0;st.inwon=j.inwon||0;st.inwonBy=j.inwon_by||{};st.note=j.note||'';st.msg='';}
    catch(e){st.msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';st.rows=[];st.dates=[];}
    st.loading=false;render();};
  const shiftDay=n=>{const d=new Date(st.base);d.setDate(d.getDate()+n);st.base=iso(d);load();};
  // 생산ST(행) = (생산계획 − 완료) × item_st(초) / 3600  [레거시 c_item_st]
  const rowST=r=>Math.max((+r.plan_qty||0)-(+r.finish||0),0)*(+r.item_st||0)/3600;
  // PART INPUT 시간(output_hm) "1126"→"11:26" 표기(레거시 동일)
  const hhmm=s=>{s=(''+(s||'')).trim();if(!s||!/^\d{1,4}$/.test(s))return esc(s);s=s.padStart(4,'0');return s.slice(0,2)+':'+s.slice(2);};
  const ymd6=s=>{s=(''+(s||'')).trim();return s.length>=6?s.slice(0,2)+'/'+s.slice(2,4)+'/'+s.slice(4,6):esc(s);};  // 260816→26/08/16 (LG INPUT)
  // ★render(bodyOnly=true) = 표(tbody/tfoot)와 건수만 갱신(툴바·헤더 유지). 필터 변경시 사용해 버벅임 제거.
  //   redrawBody()는 스크롤 위치까지 보존하는 래퍼.
  let _typeT=null;
  const redrawBody=()=>{const w=c.querySelector('.grid-wrap');const sy=w?w.scrollTop:0,sx=w?w.scrollLeft:0;
    render(true);
    const n=c.querySelector('.grid-wrap');if(n){n.scrollTop=sy;n.scrollLeft=sx;}};
  // ★집계행 클릭 = 상세 펼침/접힘 토글. tbody만 교체해도 다시 연결돼야 하므로 분리.
  /* ★펼침/접힘 = 더블클릭(2026-09-03 사용자 요청).
       종전엔 한 번 클릭이었는데, 같은 행을 복사용으로 긁거나 셀을 짚기만 해도
       접혔다 펴져 화면이 튀었다. 더블클릭이면 의도적으로만 열린다. */
  const wireRows=()=>{c.querySelectorAll('tr.pp-agg').forEach(tr=>tr.ondblclick=()=>{
    const k=tr.getAttribute('data-gk');if(!k)return;
    if(st.expand.has(k))st.expand.delete(k);else st.expand.add(k);
    redrawBody();});};
  // ── 점진 렌더(대용량) ────────────────────────────────────────────────
  //   처음 PP_PAGE 행만 DOM 에 올리고, 스크롤 끝에서 이어붙인다.
  const PP_PAGE=400;
  let ppRest=null;                 // 아직 안 붙인 <tr> 조각들
  /* ★표 본문 '세대'(2026-09-03) — tbody 가 새로 만들어질 때마다 +1.
       드래그 실적선택이 캐시한 셀 목록(_cells)이 아직 유효한지 이걸로 판정한다.
       세대 비교 없이 캐시하면 재렌더 뒤 죽은 DOM 을 잡고 있어 선택이 안 먹는다. */
  let _bodyGen=0;
  /* ★사용자별 화면설정(2026-09-03) — 정본 = 서버 nx.user_pref, 로그인 계정에 붙는다.
       왜 서버인가 — localStorage 만 쓰면 ①다른 PC 로 가면 기본값 ②캐시를 지우면 사라짐
       ③한 PC 를 여러 명이 쓰면 설정이 섞인다. 계정 설정이므로 계정을 따라다녀야 한다.
       localStorage 는 '서버응답 도착 전 임시표시'용으로만 남긴다(깜빡임 방지). */
  const PREF_SCOPE='pp410';
  let PREF=null;                    // null=아직 서버에서 안 옴 → localStorage 임시값 사용
  const prefLoad=async()=>{
    try{const r=await fetch(`${API}/api/pref?scope=${PREF_SCOPE}`);
      if(!r.ok)return false; const j=await r.json();
      if(j&&j.prefs){PREF=j.prefs; return true;}
    }catch(e){}
    return false;};
  const prefSave=async(obj)=>{
    // 화면은 즉시 반영하고(낙관적), 서버 저장은 뒤따른다. 실패해도 화면이 멈추지 않는다.
    PREF=Object.assign({},PREF||{},obj);
    try{Object.keys(obj).forEach(k=>{
      if(obj[k]==null)localStorage.removeItem('pp410_'+k);
      else localStorage.setItem('pp410_'+k,JSON.stringify(obj[k]));});}catch(_){}
    try{const r=await fetch(`${API}/api/pref`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({scope:PREF_SCOPE,prefs:obj})});
      return r.ok;}catch(e){return false;}};
  const ppAppend=()=>{
    if(!ppRest||!ppRest.length)return;
    const tb=c.querySelector('tbody'); if(!tb){ppRest=null;return;}
    const take=ppRest.slice(0,PP_PAGE); ppRest=ppRest.slice(PP_PAGE);
    tb.insertAdjacentHTML('beforeend',take.join(''));
    _bodyGen++;                    // ★행이 늘었다 → 실적선택 셀 캐시 무효화(안 하면 새 행이 선택 안 됨)
    wireRows();                    // 새로 붙은 집계행에도 클릭 연결
    const cnt=c.querySelector('#pp-cnt');
    if(cnt&&ppRest.length)cnt.textContent=cnt.textContent.replace(/^\S+건/,
      nf(tb.rows.length)+'행 표시');
  };
  const ppWireLazy=()=>{
    const w=c.querySelector('.grid-wrap');
    if(!w||w.dataset.lazy)return;
    w.dataset.lazy='1';
    w.addEventListener('scroll',()=>{
      if(ppRest&&ppRest.length&&w.scrollTop+w.clientHeight>=w.scrollHeight-400)ppAppend();
    },{passive:true});
  };
  const render=(bodyOnly)=>{
    const d=st.dates;
    const wcM=new Map([['P1','용접'],['P2','가공']]);
    const PART_FIX=[['S5','01라인(용접)'],['S5-2','01라인(조립)'],['S1','02라인'],['S6','03라인'],['S4','04라인'],['S11','05라인'],['RAC','06라인'],['S10','자동은납 10'],['S13','서브/고주파'],['S12','설치'],['S8','서포터 08'],['S9','용접 09'],['S7','다관절 로봇 용접'],['-','-'],['Q1000','용접봉창고']];
    const partOpts='<option value=""'+(st.part?'':' selected')+'>전체</option>'+PART_FIX.map(([v,n])=>v==='-'?'<option disabled>─────────</option>':`<option value="${esc(v)}"${st.part===v?' selected':''}>${esc(n)}</option>`).join('');
    // ★레거시처럼 라디오그룹 전체를 테두리 박스로 구획(어디까지 한 그룹인지 시각적으로 구분)
    const seg=(name,val,opts)=>`<span style="border:1px solid var(--line-2,#c9d3e0);border-radius:4px;padding:2px 6px;background:#fff;display:inline-flex;align-items:center">${opts.map(v=>`<label style="font-weight:400;margin:0 5px 0 1px;white-space:nowrap"><input type="radio" name="${name}" value="${v}" ${val===v?'checked':''}> ${v}</label>`).join('')}</span>`;
    // ★미생산·파트·라인·도번·제번 = 전부 클라이언트 즉시필터(전체 캐시에서). 레거시 setfilter처럼 재조회 없음.
    let base = st.unfin==='미생산' ? st.rows.filter(r=>!r.done) : st.rows;
    if(st.part) base = base.filter(r=>r.gpc===st.part);
    if(st.line) base = base.filter(r=>(r.line||'')===st.line);
    const inc=(v,q)=>String(v||'').toUpperCase().includes(q);
    if(st.dono){const q=st.dono.toUpperCase();base = base.filter(r=>inc(r.assy,q));}
    if(st.jado){const q=st.jado.toUpperCase();base = base.filter(r=>inc(r.item,q));}
    if(st.wo){const q=st.wo.toUpperCase();base = base.filter(r=>inc(r.wo,q));}
    // ★소계/집계 색상 롤업: 관련 색상이 하나라도 있으면 그 색(aggRank 녹3>노랑4>주황6).
    //   무색('0'=미키팅/전표)은 판정 대상에서 제외. 색이 하나도 없으면 무색. (소계행·집계뷰 공통)
    const rollFin=(fs)=>{const v=fs.filter(f=>f&&f!=='0');if(!v.length)return '0';
      return v.slice().sort((a,b)=>aggRank(a)-aggRank(b))[0];};
    // ★2026-09-02 소계 색상 = 레거시 규칙으로 환원(= rollFin 과 동일 판정).
    //   레거시 원본: g1_plan_qty_NN.Background = c_color( min(if(plan>0, fin)) )
    //     (_legacy_analysis/GAGONG_4PROGRAMS_ANALYSIS.md:309 · w_pr_input_420_new.srw:444)
    //   = "계획 있는 행들의 fin 중 **가장 진행이 덜 된 것**" 이지 "전부 같을 때만"이 아니다.
    //
    //   ※종전(2026-08-25)은 "하위행이 전부 같은 색일 때만" 이었는데, 실제 데이터가
    //     한 도번 안에서 파트(S5 용접 / S5-2 조립)로 갈리고 제번마다 진행도가 달라
    //     **색이 거의 항상 섞인다** → 소계가 사실상 늘 무색이었다.
    //     실측 2026-09-02 AJR73965505(96행): fin = 6×10 · 7×4 · 0×4 → 종전 무색,
    //     레거시는 진주황('7'). 사용자 확인 = 진주황이 맞다.
    //
    //   무색('0')은 판정에서 제외한다 — 계획만 있고 아직 아무 진행이 없는 행까지
    //   min 에 넣으면 한 건만 미착수여도 전체가 무색이 되어 같은 문제가 재발한다.
    //   색이 하나도 없으면 그때만 무색. 우선순위 = aggRank(녹3>노랑4>주황7>살구6>자재2).
    const rollFinQ=rollFin;
    // ── 구분(view): 집계=도번(item)단위 롤업 / 전체·제번=제번(WO)단위 상세 ──
    let disp=base;
    if(st.view==='집계'){
      // ★집계 = 상세뷰의 청록 소계행(도번 item "연속블록")과 1:1 동일해야 함.
      //   → Map(전역 도번키)로 묶으면 떨어져 등장하는 같은 도번이 하나로 합쳐져 상세와 어긋남.
      //     bodyHtml의 블록분할(연속 item)과 똑같이 구간별로 집계.
      // ★블록키 = 파트(gpc)+도번(item). 도번만 쓰면 같은 도번의 S5(용접)/S5-2(조립)가 한 집계행으로 합쳐져
      //   파트명·앞공정·현재공정이 대표행(첫 공정) 값만 표시됨. bodyHtml 블록분할과 동일 규칙. 2026-08-19 수정.
      const bkey0=r=>(r.gpc||'')+''+(r.item||'')+''+(r.line||'');
      const out=[];
      for(let i=0;i<base.length;){
        const it=bkey0(base[i]); let j=i; const blk=[];
        while(j<base.length&&bkey0(base[j])===it){blk.push(base[j]);j++;}
        const r0=blk[0];
        const g={gpcnm:r0.gpcnm,gpc:r0.gpc,assy:r0.assy,upper:r0.upper,item:r0.item,nm:r0.nm,line:r0.line,inhm:r0.inhm,
                 part_ymd:r0.part_ymd,plan_ymd:r0.plan_ymd,output_hm:r0.output_hm,item_st:r0.item_st,
                 change_day:r0.change_day,lot_diff:0,wo:'',swo:'',
                 // 재고류는 도번(item) 기준 값이라 블록 대표행 값 그대로(합산 아님)
                 mat_stock:r0.mat_stock,prod_stock:r0.prod_stock,sagub_stock:r0.sagub_stock,fix_stock:r0.fix_stock,
                 assy_stock:r0.assy_stock,sale_qty:r0.sale_qty,ready_stock:r0.ready_stock,
                 prev_proc:r0.prev_proc,cur_proc:r0.cur_proc,
                 plan_qty:0,finish:0,prior_plan:0,prior_cover:0,prior_fin:'0',days:{},dcov:{},dfin:{},_st:0,
                 _blk:blk,_gkey:it+'@'+i};   // ★펼침 토글용: 이 집계행이 대표하는 상세행들 + 블록 고유키(같은 도번 반복 대비 인덱스 포함)
        blk.forEach(r=>{
          g.plan_qty+=+r.plan_qty||0;g.finish+=+r.finish||0;g.prior_plan+=+r.prior_plan||0;g.prior_cover+=+r.prior_cover||0;
          g.lot_diff+=+r.lot_diff||0;if(!g.change_day)g.change_day=r.change_day;
          g._st+=Math.round(rowST(r)*100)/100;            // 소계행과 동일: 셀별 round(,2) 후 합산
          if((r.part_ymd||'')<(g.part_ymd||'zz'))g.part_ymd=r.part_ymd;
          d.forEach(x=>{if(r.days&&r.days[x]){g.days[x]=(g.days[x]||0)+r.days[x];g.dcov[x]=(g.dcov[x]||0)+((r.dcov&&r.dcov[x])||0);}});
        });
        // 색상 = 소계행과 동일(계획>0인 행만 대상, aggRank: 녹3 > 노랑4 > 주황6).
        //   ★부분충당이면 무색(rollFinQ) — 합계가 계획을 다 채웠을 때만 칠한다.
        g.prior_fin=rollFinQ(blk.filter(r=>(+r.prior_plan||0)>0).map(r=>r.prior_fin||'0'));
        d.forEach(x=>{g.dfin[x]=rollFinQ(blk.filter(r=>((r.days&&r.days[x])||0)>0).map(r=>(r.dfin&&r.dfin[x])||'0'));});
        out.push(g); i=j;
      }
      disp=out;
    }
    // 정렬: ★전 뷰 공통 = 백엔드(레거시 setsort: part_group→part_plan_ymd_hm→item→plan_ymd→output_hm→lg→wo→swo) 순서 유지.
    //   ★집계도 상세와 동일 순서(레거시 확인) — 도번순 재정렬하면 상세와 어긋남. Map은 삽입순 유지라 그대로 두면 됨.
    if(st.view==='제번') disp=disp.slice().sort((a,b)=>(a.item||'').localeCompare(b.item||'')||((a.part_ymd||'')+(a.inhm||'')).localeCompare((b.part_ymd||'')+(b.inhm||''))||(a.wo||'').localeCompare(b.wo||''));
    const numTd=(v,bg,strong,fg)=>`<td class="center"${bg?` style="background:${bg}${strong?';font-weight:700':''}${fg?';color:'+fg:''}"`:''}>${v}</td>`;   // ★가운데정렬
    // 완료수량=생산실적(finish)만. 생산분 있으면 "생산/계획", 없으면 계획만(바 없이=키팅/미키팅은 색으로만 구분)
    // ★값 없는 셀은 공백(기존 '·' 표시 제거 — 빈칸이 많아 지저분해서)
    const pcell=r=>r.prior_plan>0?(r.prior_cover>0?`${nf(r.prior_cover)}/${nf(r.prior_plan)}`:`${nf(r.prior_plan)}`):'';
    const stkc=v=>(+v||0)?nf(v):'';   // 재고컬럼: 0은 공백(레거시 동일 — 값 있는 것만 눈에 띄게)
    // ★후행(일자컬럼 뒤) 컬럼 정의 — 순서변경/드래그 대상. key로 localStorage에 유저별 순서 저장.
    //   기본순서 = 레거시 배치: LG INPUT · LG INPUT시간 · Work Order · LG OUTPUT시간 · 재고6종
    const TAILDEF={
      // ★전 컬럼 가운데정렬(center) — 숫자도 우측정렬 대신 가운데(사용자 요청)
      plan_ymd:  {t:'LG INPUT',      cls:'center', v:r=>ymd6(r.plan_ymd)},
      output_hm: {t:'LG INPUT시간',  cls:'center', v:r=>hhmm(r.output_hm)},
      wo:        {t:'Work Order',    cls:'center', v:r=>esc(r.wo||''), st:'font-size:10px'},
      lgh:       {t:'LG OUTPUT시간', cls:'center', v:r=>{const s=(''+(r.lgh||'')).trim();return s.length>=10?ymd6(s.slice(0,6))+' '+hhmm(s.slice(6,10)):esc(s);}, st:'font-size:10px'},
      // ★앞공정/현재공정(레거시 SP_..._NEW_250826): 작업중 전표재고 기준.
      //   현재공정=자기 공정 잔량 / 앞공정=PROC_SEQ 1이면 0, else 앞공정잔량−현재공정잔량
      //   01라인(용접S5→조립S5-2)처럼 2공정인 품목에서 뒷공정 실적이 잡히면 앞공정이 상계돼 0이 됨.
      prev_proc: {t:'앞공정',        cls:'center mut', v:r=>stkc(r.prev_proc)},
      cur_proc:  {t:'현재공정',      cls:'center mut', v:r=>stkc(r.cur_proc)},
      mat_stock: {t:'자재재고',      cls:'center mut', v:r=>stkc(r.mat_stock)},
      prod_stock:{t:'생산재고',      cls:'center mut', v:r=>stkc(r.prod_stock)},
      // ★2026-08-25 사급(업체)재고 분리 — 업체 보유분을 따로 봐야 해서 생산재고에서 뺐다.
      sagub_stock:{t:'사급재고',     cls:'center mut', v:r=>stkc(r.sagub_stock)},
      fix_stock: {t:'도번고정재고',  cls:'center mut', v:r=>stkc(r.fix_stock)},
      assy_stock:{t:'ASSY재고',      cls:'center mut', v:r=>stkc(r.assy_stock)},
      sale_qty:  {t:'출하',          cls:'center mut', v:r=>stkc(r.sale_qty)},
      ready_stock:{t:'생산준비재고', cls:'center mut', v:r=>stkc(r.ready_stock)},
    };
    // ★앞쪽(SEQ 뒤 ~ 일자컬럼 앞) 컬럼도 동일하게 정의 → 전 컬럼 드래그 이동 대상.
    //   firstInGrp(그룹 첫행만 코드 표시) 규칙이 있는 컬럼은 v(r,fg)의 2번째 인자로 처리.
    const HEADDEF={
      gpc:      {t:'파트',        cls:'center', v:(r,fg)=>fg?esc(r.gpcnm||r.gpc):''},
      assy:     {t:'Assy도번',    cls:'center', v:(r,fg)=>fg?`<b>${esc(r.assy)}</b>`:''},
      upper:    {t:'상위도번',    cls:'center', v:(r,fg)=>fg?esc(r.upper||''):''},
      item:     {t:'도번',        cls:'center', v:(r,fg)=>`<b>${fg?esc(r.item):''}</b>`},
      line:     {t:'Line No',     cls:'center', v:r=>esc(r.line||'')},
      part_ymd: {t:'PART일자',    cls:'center', v:r=>esc(dcol(r.part_ymd||''))},
      inhm:     {t:'PART INPUT',  cls:'center', v:r=>hhmm(r.inhm)},
      pull:     {t:'당김',        cls:'center', v:r=>esc(pulltxt(r)), sf:r=>`color:${(+r.lot_diff||0)?'#c0392b':'#b8791f'};font-weight:${(+r.lot_diff||0)?'700':'400'}`},
      st:       {t:'생산ST',      cls:'center', v:r=>f2(r._st!==undefined?r._st:rowST(r))},
      plan_qty: {t:'생산계획',    cls:'center', v:r=>`<b>${nf(r.plan_qty)}</b>`},
      prior:    {t:'당일이전계획',cls:'center', v:r=>r.prior_plan>0?pcell(r):'',
                 bg:r=>r.prior_plan>0&&(r.prior_fin||'0')!=='0'?{b:finBg(r.prior_fin),f:finFg(r.prior_fin)}:null,
                 // ★당일이전계획도 드래그 실적 대상(2026-08-30). 일자칸과 동일 규칙.
                 dp:r=>{
                   if(!dpOn())return null;
                   // ★집계·소계행 제외 — 그 행들은 wo='' 로 만들어지고(blk 합산행), 상세행과
                   //   같이 선택되면 같은 실적이 두 번 잡힌다. 실적 단위는 도번×제번.
                   if(!r.wo||r._blk)return null;
                   const planRem=Math.max((+r.prior_plan||0)-(+r.prior_cover||0),0);
                   if(planRem<=0)return null;
                   const cf=r.prior_fin||'0';
                   if(st.dpConf.type==='R'&&cf!=='3')return null;   // 준비재고=녹색만
                   const k=dpKey(r,'PRIOR');
                   const rem=dpRem(r,planRem,k);   // ★준비재고 상한
                   if(rem<=0)return null;
                   return {k,part:r.gpc||'',item:r.item||'',
                           wo:r.wo||'',line:r.line||'',rem};
                 }},
    };
    const ALLDEF=Object.assign({},HEADDEF,TAILDEF);
    const HEAD_DEFAULT=['gpc','assy','upper','item','line','part_ymd','inhm','pull','st','plan_qty','prior'];
    const TAIL_DEFAULT=['plan_ymd','output_hm','wo','lgh','prev_proc','cur_proc','mat_stock','prod_stock','sagub_stock','fix_stock','assy_stock','sale_qty','ready_stock'];
    const HEAD_LSKEY='headorder', TAIL_LSKEY='tailorder';
    // 유저별 저장순서 로드(없거나 깨졌으면 기본). 신규 컬럼을 정의에 추가하면 저장순서 뒤에 자동 보충 → 기존 사용자도 안 깨짐.
    const loadOrder=(lskey,def,defs)=>{
      // ★정본 = 서버(nx.user_pref, 로그인 계정별). localStorage 는 서버응답 도착 전 임시표시용.
      //   서버가 응답하면 PREF 가 채워지고 재렌더된다(prefLoad).
      try{const s=(PREF&&PREF[lskey]!==undefined)?PREF[lskey]
                 :JSON.parse(localStorage.getItem('pp410_'+lskey)||'null');
        if(Array.isArray(s)&&s.length){const v=s.filter(k=>defs[k]);def.forEach(k=>{if(!v.includes(k))v.push(k);});return v;}
      }catch(e){}
      return def.slice();};
    // ★defs=ALLDEF — 앞↔뒤 그룹 이동을 허용하므로 저장된 키가 반대 그룹 것일 수 있다.
    //   그룹별 정의로 거르면 옮긴 컬럼이 저장에서 탈락해 원위치로 돌아간다.
    const headOrderAll=loadOrder(HEAD_LSKEY,HEAD_DEFAULT,ALLDEF);
    let tailOrderAll=loadOrder(TAIL_LSKEY,TAIL_DEFAULT,ALLDEF);
    /* ★한 컬럼이 양쪽 그룹에 동시에 있으면 표에 두 번 나온다.
         loadOrder 는 "저장에 없는 기본컬럼을 뒤에 보충"하는데, 앞으로 옮긴 컬럼은
         tail 저장목록에서 빠졌으므로 TAIL_DEFAULT 보충 때 되살아난다.
         → head 가 이미 가진 키는 tail 에서 뺀다(head 우선). */
    tailOrderAll=tailOrderAll.filter(k=>!headOrderAll.includes(k));
    /* ★항목보기(2026-09-03) — 레거시 '항목보기'와 동일: 체크 해제한 컬럼은 표에서 사라진다.
         숨김목록만 저장한다(표시목록이 아니라). 그래야 나중에 컬럼을 추가해도
         기존 사용자에게 자동으로 보인다(저장목록에 없다고 사라지지 않는다).
         일자컬럼은 대상 아님 — 조회조건(적용일수)이 정하므로 여기서 숨기면 설정이 어긋난다. */
    const HIDE_LSKEY='hidecols';
    const loadHide=()=>{try{const s=(PREF&&PREF[HIDE_LSKEY]!==undefined)?PREF[HIDE_LSKEY]
                            :JSON.parse(localStorage.getItem('pp410_'+HIDE_LSKEY)||'null');
      return new Set(Array.isArray(s)?s.filter(k=>ALLDEF[k]):[]);}catch(e){return new Set();}};
    const hideSet=loadHide();
    const headOrder=headOrderAll.filter(k=>!hideSet.has(k));
    const tailOrder=tailOrderAll.filter(k=>!hideSet.has(k));
    // th/td 생성 공통 — data-tk(컬럼키)·data-grp(head|tail)로 드래그 그룹 구분(그룹 내에서만 이동).
    /* ★헤더 드래그 이동은 은퇴(2026-09-03 사용자 요청).
         8,500행이 붙은 표에서 열을 통째로 옮기면 저사양 PC 가 눈에 띄게 버벅였다.
         순서 변경은 '항목보기'(우클릭) 목록에서 한다 — 표를 안 건드리므로 즉각 반응하고,
         숨김·순서를 한 자리에서 정리한 뒤 [확인] 한 번에 반영된다.
         data-tk 는 남긴다(컬럼 식별에 계속 쓰인다). */
    const mkTh=(ks,defs,grp)=>ks.map(k=>`<th class="center" data-tk="${k}" data-grp="${grp}" title="우클릭 = 항목보기(순서·숨김)">${defs[k].t}</th>`).join('');
    const mkTd=(ks,defs,r,fg)=>ks.map(k=>{const c=defs[k];   // data-tk = 컬럼이동시 열 식별용
      const b=c.bg?c.bg(r):null;
      const stl=(c.st||'')+(c.sf?c.sf(r):'')+(b?`background:${b.b};font-weight:700${b.f?';color:'+b.f:''}`:'');
      // ★드래그 실적 대상 컬럼(당일이전계획 등)
      const dp=c.dp?c.dp(r):null;
      const dpa=dp?` class="${c.cls} dp-c${st.dpSel.has(dp.k)?' dp-on':''}" data-dp="${esc(dp.k)}"`
                  +` data-part="${esc(dp.part)}" data-item="${esc(dp.item)}"`
                  +` data-wo="${esc(dp.wo)}" data-line="${esc(dp.line)}" data-rem="${dp.rem}"`
                 :` class="${c.cls}"`;
      return `<td${dpa}${stl?` style="${stl}"`:''}>${c.v(r,fg)}</td>`;}).join('');
    // ★ALLDEF 로 조회한다 — 항목보기에서 컬럼을 앞↔뒤 그룹으로 옮길 수 있으므로
    //   headOrder 에 원래 tail 이던 키가 들어올 수 있다(HEADDEF 만 보면 undefined 로 깨진다).
    const headTh=()=>mkTh(headOrder,ALLDEF,'head');
    const tailTh=()=>mkTh(tailOrder,ALLDEF,'tail');
    const headTd=(r,fg)=>mkTd(headOrder,ALLDEF,r,fg);
    const tailTd=(r)=>mkTd(tailOrder,ALLDEF,r,true);
    const tailBlank=()=>tailOrder.map(()=>'<td></td>').join('');
    const rowHtml=(r,seq,firstInGrp,gkey,open,childOf)=>{const pf=r.prior_fin||'0';
      // ★집계행(gkey) = 청록 배경 + 클릭시 펼침/접힘. 펼쳐진 상세행(childOf) = 흰 배경이지만 클릭시 같이 접힘.
      const isAgg = gkey!==undefined;
      const tog = isAgg ? gkey : childOf;                       // 클릭 토글 대상 키
      const aggBg = isAgg ? 'background:#cdeef7;font-weight:600;cursor:pointer;' : (childOf?'cursor:pointer;':'');
      return `<tr${tog!==undefined?` class="pp-agg" data-gk="${esc(tog)}"`:''}${(aggBg||(firstInGrp&&seq>1))?` style="${aggBg}${firstInGrp&&seq>1?'border-top:2px solid #9fb3c8':''}"`:''}>
        <td class="center mut">${isAgg?`<span style="color:#456">${open?'▼':'▶'}</span> `:''}${seq}</td>${headTd(r,firstInGrp)}
        ${d.map(x=>{const pl=(r.days&&r.days[x])||0,cv=(r.dcov&&r.dcov[x])||0,cf=(r.dfin&&r.dfin[x])||'0';
          if(!pl)return numTd('','',false);
          const td=numTd(cv>0?`${nf(cv)}/${nf(pl)}`:`${nf(pl)}`,finBg(cf),cf!=='0',finFg(cf));
          // ★드래그 실적 대상 셀 — 조건문에서 파트를 고르고 그 파트가 생산실적 설정돼 있을 때만
          if(!dpOn()||isAgg)return td;
          const planRem=Math.max(pl-cv,0); if(planRem<=0)return td;
          // 준비재고(R) = 녹색(키팅완료 '3')만 / 자재창고출고(W) = 색 무관
          if(st.dpConf.type==='R'&&cf!=='3')return td;
          const key=dpKey(r,x);
          // ★준비재고 상한 — 준비 3개면 계획이 5라도 3개만 잡힌다
          const rem=dpRem(r,planRem,key); if(rem<=0)return td;
          const on=st.dpSel.has(key);
          // ★class 를 새로 덧붙이면 안 된다 — numTd 가 이미 class="center" 를 달고 나오므로
          //   class 속성이 두 개가 되고, HTML 은 첫 번째만 채택해 가운데정렬이 통째로 날아간다
          //   (그리고 classList 로 dp-on 을 토글해도 화면에 반영되지 않는다). 기존 class 에 병합한다.
          return td.replace(/class="([^"]*)"/, (mm,cls)=>
                   `class="${cls} dp-c${on?' dp-on':''}" data-dp="${esc(key)}"`
                  +` data-part="${esc(r.gpc||'')}" data-item="${esc(r.item||'')}"`
                  +` data-wo="${esc(r.wo||'')}" data-line="${esc(r.line||'')}" data-rem="${rem}"`);
        }).join('')}${tailTd(r)}</tr>`;};
    // ★레거시 DW 도번(item) 그룹 소계행(청록, group trailer) — 완료합/계획합. 상세뷰만.
    // gkey/folded = 상세뷰 블록 접기 토글용(클릭시 그 블록 상세행 숨김). 미전달이면 기존처럼 단순 소계행.
    const subHtml=(blk,gkey,folded)=>{const r0=blk[0];
      const sPl=blk.reduce((s,r)=>s+(+r.plan_qty||0),0), sST=blk.reduce((s,r)=>s+Math.round(rowST(r)*100)/100,0);
      const sPrP=blk.reduce((s,r)=>s+(+r.prior_plan||0),0), sPrC=blk.reduce((s,r)=>s+(+r.prior_cover||0),0);
      const sPrF=rollFinQ(blk.filter(r=>(+r.prior_plan||0)>0).map(r=>r.prior_fin||'0'));
      const subTd=(v,f)=>`<td class="center"${f&&f!=='0'?` style="background:${finBg(f)};font-weight:700${finFg(f)?';color:'+finFg(f):''}"`:''}>${v}</td>`;   // ★가운데정렬
      // ★소계행도 headOrder(유저 컬럼순서)를 따라야 하므로, 합계값을 담은 가상행을 만들어 headTd에 넘김.
      //   소계에 표시 안 하는 컬럼(상위도번·LineNo·PART일자·PART INPUT·당김)은 빈값 처리.
      const sub={gpcnm:r0.gpcnm,gpc:r0.gpc,assy:r0.assy,upper:'',item:r0.item,line:'',part_ymd:'',inhm:'',
                 lot_diff:0,change_day:'',_st:sST,plan_qty:sPl,prior_plan:sPrP,prior_cover:sPrC,prior_fin:sPrF,
                 plan_ymd:r0.plan_ymd,output_hm:r0.output_hm,wo:'',lgh:r0.lgh,
                 mat_stock:r0.mat_stock,prod_stock:r0.prod_stock,sagub_stock:r0.sagub_stock,fix_stock:r0.fix_stock,
                 assy_stock:r0.assy_stock,sale_qty:r0.sale_qty,ready_stock:r0.ready_stock,
                 prev_proc:r0.prev_proc,cur_proc:r0.cur_proc};
      return `<tr${gkey!==undefined?` class="pp-agg" data-gk="${esc(gkey)}" title="더블클릭 = 상세 펼침/접힘"`:''} style="background:#cdeef7;font-weight:600;border-bottom:1px solid #9fb3c8${gkey!==undefined?';cursor:pointer':''}">
        <td class="center mut">${gkey!==undefined?`<span style="color:#456">${folded?'▶':'▼'}</span>`:''}</td>${headTd(sub,true)}
        ${d.map(x=>{const pl=blk.reduce((s,r)=>s+((r.days&&r.days[x])||0),0),cv=blk.reduce((s,r)=>s+((r.dcov&&r.dcov[x])||0),0);
          const cf=rollFinQ(blk.filter(r=>((r.days&&r.days[x])||0)>0).map(r=>(r.dfin&&r.dfin[x])||'0'));
          return pl>0?subTd(nf(cv)+'/'+nf(pl),cf):`<td class="center"></td>`;}).join('')}${tailTd(sub)}</tr>`;};
    // tbody: 상세=도번블록별 상세행+청록소계, 집계=집계행(클릭시 상세 펼침), 제번=집계행만
    // 전체 컬럼수 = SEQ(1) + 앞쪽컬럼(headOrder) + 일자컬럼(d) + 후행컬럼(tailOrder). colspan/스피너 계산용.
    const NCOL=1+headOrder.length+tailOrder.length;
    const bodyHtml=()=>{if(!disp.length)return `<tr><td colspan="${NCOL+d.length}" class="empty">조회 결과 없음 — 기준일자/작업처/파트/도번을 조정하세요</td></tr>`;
      // ★집계: 행 클릭 = 그 블록 상세행 펼침/접힘 토글(레거시 드릴다운).
      //   상세는 집계행 "위"에 표시(상세뷰와 동일한 배치: 상세행들 → 소계행 순).
      //   펼쳐진 상세행도 같은 gkey를 달아 클릭시 닫히게 함.
      if(st.view==='집계')return disp.map((r,i)=>{
        const open=st.expand.has(r._gkey);
        const kids=(open&&r._blk)?r._blk.map((cr,ci)=>rowHtml(cr,ci+1,ci===0,undefined,undefined,r._gkey)).join(''):'';
        return kids+rowHtml(r,i+1,true,r._gkey,open);}).join('');
      // ★그룹키 = 파트(gpc)+도번(item). 도번만 쓰면 같은 도번의 S5(용접)/S5-2(조립)가 한 블록으로 묶여
      //   파트명이 첫 행에만 찍히고 아래 조립행이 용접행처럼 보임(앞공정 6이 용접에 붙은 것으로 오독). 2026-08-19 수정.
      const bkey=r=>(r.gpc||'')+''+(r.item||'')+''+(r.line||'');
      if(st.view!=='상세')return disp.map((r,i)=>rowHtml(r,i+1,i===0||bkey(disp[i-1])!==bkey(r))).join('');
      // ★상세: 블록(연속 파트+도번) 단위 접기/펼치기. 상세행·소계행 아무 데나 클릭하면 그 블록이 접힘(집계처럼 소계만 보임).
      //   st.expand에 담긴 키 = "접힌" 블록(집계뷰에선 "펼친" 의미라 반대지만, 각 뷰 전환시 clear하므로 충돌 없음)
      let h='',i=0,seq=0;
      while(i<disp.length){const it=bkey(disp[i]);let j=i;const blk=[];while(j<disp.length&&bkey(disp[j])===it){blk.push(disp[j]);j++;}
        const gk=it+'@'+i, folded=st.expand.has(gk);
        // 상세행은 클릭 대상 아님(childOf 미전달) — 접기/펼치기는 소계행 클릭으로만
        if(!folded) blk.forEach((r,bi)=>{seq++;h+=rowHtml(r,seq,bi===0);});
        h+=subHtml(blk,gk,folded); i=j;}
      return h;};
    // footer: 당일이전·일자별 (완료/계획) + 생산ST행
    const planSum=disp.reduce((s,r)=>s+(+r.plan_qty||0),0);   // ★표시중(필터적용) 계획합 — 캐시 클라이언트필터 기준
    const fPrP=disp.reduce((s,r)=>s+(+r.prior_plan||0),0), fPrC=disp.reduce((s,r)=>s+(+r.prior_cover||0),0);
    const fPl=x=>disp.reduce((s,r)=>s+((r.days&&r.days[x])||0),0), fCv=x=>disp.reduce((s,r)=>s+((r.dcov&&r.dcov[x])||0),0);
    const fST=disp.reduce((s,r)=>s+rowST(r),0);
    const r2=v=>Math.round(v*100)/100;   // ★레거시 dw c_item_st=round(...,2) 셀별 반올림 후 합산(누적 반올림차 방지)
    const fSTd=x=>disp.reduce((s,r)=>s+r2(Math.max(((r.days&&r.days[x])||0)-((r.dcov&&r.dcov[x])||0),0)*(+r.item_st||0)/3600),0);
    const fSTprior=disp.reduce((s,r)=>s+r2(Math.max((+r.prior_plan||0)-(+r.prior_cover||0),0)*(+r.item_st||0)/3600),0);
    // ★성능: bodyOnly=true면 표(tbody/tfoot)와 건수줄만 교체하고 툴바·헤더는 그대로 둠.
    //   필터 변경마다 c.innerHTML 전체를 갈아엎으면 2,900행 기준 눈에 띄게 버벅여서 분리함.
    //   (툴바를 유지하므로 입력칸 포커스·커서위치도 자연히 보존됨)
    // ★대용량 대응(2026-08-21): 4,782행 × 30컬럼 = 약 14만 셀을 한 번에 DOM 에 올리면
    //   저사양 PC에서 최초렌더·컬럼이동·스크롤이 모두 멈춘다("응답 없음").
    //   → 완성된 tbody HTML 을 <tr> 단위로 잘라 처음 PP_PAGE 개만 붙이고,
    //     스크롤이 끝에 가까워지면 이어붙인다. 행 생성 로직(집계/상세/블록접기)은 그대로.
    _bodyGen++;                    // ★표가 새로 만들어진다 → 실적선택 셀 캐시 무효화(_cellsGen 비교)
    const _fullBody=st.loading?spinRow(NCOL+d.length):bodyHtml();
    const _chunks=(()=>{if(st.loading)return null;
      const parts=_fullBody.split(/(?=<tr)/);          // <tr 앞에서 분할(행 경계 보존)
      return parts.length>PP_PAGE?parts:null;})();     // 적으면 통째로
    ppRest=_chunks?_chunks.slice(PP_PAGE):null;
    const tbodyHtml=_chunks?_chunks.slice(0,PP_PAGE).join(''):_fullBody;
    const tfootHtml=(()=>{if(!disp.length)return '';
      // ★2026-08-25 인원 = 선택한 파트의 인원. 파트 미선택(전체)일 때만 전체합.
      //   서버는 전체를 한 번만 주므로(클라이언트 필터 구조) 파트별 맵에서 골라 쓴다.
      //   예) 01라인(용접)=S5 9명 / 05라인=S11 8명 / 전체 111명.
      const iw=(st.part&&st.inwonBy)?(+st.inwonBy[st.part]||0):(st.inwon||0);
      const fSTtot=fSTprior+d.reduce((s,x)=>s+fSTd(x),0);
      const footRow=(label,vals)=>{let put=false;
        return headOrder.map(k=>{
          if(vals[k]!==undefined)return `<td class="center">${vals[k]}</td>`;
          if(!put){put=true;return `<td class="center" style="font-weight:600">${label}</td>`;}
          return '<td></td>';}).join('');};
      return `<tr class="grandtot" style="position:sticky;bottom:44px;background:#eef2f7;font-weight:700;border-top:2px solid #b8c4d4">
        <td></td>${footRow('합계',{st:f2(fSTtot),plan_qty:nf(planSum),prior:fPrP>0?nf(fPrC)+'/'+nf(fPrP):''})}${d.map(x=>{const pl=fPl(x);return `<td class="center">${pl>0?nf(fCv(x))+'/'+nf(pl):''}</td>`;}).join('')}${tailBlank()}</tr>
       <tr class="grandtot" style="position:sticky;bottom:22px;background:#f4f7fc;color:#456;border-top:1px solid #d3ddea">
        <td></td>${footRow('생산ST',{st:f2(fSTtot),prior:f2(fSTprior)})}${d.map(x=>`<td class="center">${f2(fSTd(x))}</td>`).join('')}${tailBlank()}</tr>
       <tr class="grandtot" style="position:sticky;bottom:0;background:#f4f7fc;color:#666;border-top:1px solid #d3ddea">
        <td></td>${footRow(`계상근무공수 (÷인원 ${nf(iw)})`,{st:iw?f2(fSTtot/iw):'—'})}${d.map((x,xi)=>`<td class="center">${iw?f2(((xi===0?fSTprior:0)+fSTd(x))/iw):'—'}</td>`).join('')}${tailBlank()}</tr>`;})();
    const srcLbl=st.src==='live'?'🔴 라이브':(st.src==='new'?'🟣 신규DB(웹계획)':'🟢 nx');
    const cntHtml=`${nf(disp.length)}건 · ${srcLbl} · 일자 ${d.length}개`;
    if(bodyOnly){
      const tb=c.querySelector('tbody'), tf=c.querySelector('tfoot'), cnt=c.querySelector('#pp-cnt');
      if(tb){tb.innerHTML=tbodyHtml;}
      if(tf){tf.innerHTML=tfootHtml;}
      if(cnt){cnt.textContent=cntHtml;}
      wireRows();          // 새로 그린 행에 클릭(집계 펼침) 핸들러만 다시 연결
      ppWireLazy();        // 스크롤 이어붙이기(점진 렌더)
      return;
    }
    c.innerHTML=`
     <div class="page-title">🧩 파트별 생산계획 <span style="font-size:12px;color:var(--muted);font-weight:400">w_pr_input_410_new · nx 직독(키팅과 동일 SP·색상)</span></div>
     <div class="page-sub">사내 생산품(용접/가공) 파트별 일자계획. 당일이전계획=기준일 이전 계획 누적(완료/계획). 셀=완료/계획.
       <span style="background:#669900;color:#fff;padding:0 5px">녹=키팅완료</span> <span style="background:#ffff00;padding:0 5px">노랑=생산완료</span> <span style="background:#ed7d31;color:#fff;padding:0 5px">진주황=현재공정(작업중전표)</span> <span style="background:#fac090;padding:0 5px">살구=출하완료</span> 백=미키팅</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px;row-gap:2px">
       <label class="tl">기준일자</label><button class="btn ghost" id="pp-prev" title="전일" style="padding:2px 6px">◀</button>
       <!-- ★날짜칸 폭: type=date는 브라우저 기본 패딩/캘린더아이콘 여백이 커서 width만 줄이면 값이 잘림.
            → 패딩 제거 + 폰트 살짝 축소 + width:auto(내용폭)로 두어 빈공백 최소화. 네이티브 세그먼트 편집은 유지(CLAUDE.md §3). -->
       <input class="inp" type="date" id="pp-base" value="${st.base}" style="width:auto;min-width:0;padding:2px 0 2px 3px;font-size:12px">
       <button class="btn ghost" id="pp-next" title="익일" style="padding:2px 6px">▶</button>
       <label class="tl">자도번작업처</label><select class="inp" id="pp-wc" style="width:80px"><option value="">전체</option>${[...wcM].map(([v,n])=>`<option value="${esc(v)}"${st.wc===v?' selected':''}>${esc(n)}</option>`).join('')}</select>
       <label class="tl">파트</label><select class="inp" id="pp-part" style="width:130px">${partOpts}</select>
       <label class="tl">생산여부</label>${seg('pp-uf',st.unfin,['전체','미생산'])}
       <label class="tl">구분</label>${seg('pp-vw',st.view,['상세','집계','제번'])}
       <label class="tl">적용일수</label><select class="inp" id="pp-gigan" style="width:62px">${[1,2,3,4,5,6,7,8,9,10].map(n=>`<option value="${n}"${st.gigan===n?' selected':''}>${n}일</option>`).join('')}</select>
       <label class="tl">소스</label><select class="inp src-new" id="pp-src" data-src="${esc(st.src)}" style="width:auto;min-width:150px" title="신규DB(웹계획)=웹이 자체 편성한 계획(nx.plan_part_dtl) / 우리(nx)=레거시 편성 미러 / 라이브 대사=레거시 그대로"><option value="new"${st.src==='new'?' selected':''}>🟣 신규DB(웹계획)</option><option value="nx"${st.src==='nx'?' selected':''}>🟢 우리(nx)</option><option value="live"${st.src==='live'?' selected':''}>🔴 라이브 대사</option></select>
       <button class="btn" id="pp-go">🔍 조회</button>
       ${dpOn()?`<span style="display:inline-flex;gap:6px;align-items:center;margin-left:10px;padding:2px 10px;
            border:1px solid ${st.dpConf.type==='R'?'#7cc499':'#9dc0e8'};border-radius:6px;
            background:${st.dpConf.type==='R'?'#eafaef':'#eaf3ff'}">
          <b style="font-size:12px;color:${st.dpConf.type==='R'?'#1c7c3a':'#1c47a0'}">🖱 드래그 실적 · ${esc(st.dpConf.type_nm)}</b>
          <span style="font-size:11px;color:#5a6b82">선택 <b id="pp-dp-cnt">${st.dpSel.size}건</b></span>
          <button class="btn" id="pp-dp-ok" ${st.dpBusy?'disabled':''}
            style="background:#1c7c3a;color:#fff;padding:1px 9px;font-size:12px">${st.dpBusy?'처리중…':'✅ 확인'}</button>
          <button class="btn ghost" id="pp-dp-clr" style="padding:1px 7px;font-size:12px">취소</button>
          <span style="font-size:10px;color:#8aa0bd">드래그 후 <b>우클릭</b>/<b>F12</b> · <b>더블클릭</b>=수량조정</span>
        </span>`:(st.part&&st.dpConf&&!st.dpConf.enabled
          ?`<span style="margin-left:10px;font-size:11px;color:#c0392b">🔒 ${esc(st.dpConf.msg||'')}</span>`:'')}
       <div style="flex-basis:100%;height:0"></div>
       <label class="tl">라인</label><select class="inp" id="pp-line" style="width:90px"><option value="">전체</option>${st.lines.map(l=>`<option value="${esc(l.code)}"${st.line===String(l.code)?' selected':''}>${esc(l.nm||l.code)}</option>`).join('')}</select>
       <label class="tl">제번</label><input class="inp" id="pp-wo" value="${esc(st.wo)}" style="width:90px" placeholder="제번" autocomplete="off">
       <label class="tl">ASSY도번</label><input class="inp" id="pp-dono" value="${esc(st.dono)}" style="width:100px" placeholder="ASSY도번" autocomplete="off">
       <label class="tl">도번</label><input class="inp" id="pp-jado" value="${esc(st.jado)}" style="width:100px" placeholder="도번(item)" autocomplete="off">
       <div class="spacer"></div>
       <button class="btn xls" id="pp-xls" title="화면에 보이는 그대로(색상 포함) 엑셀로 내려받습니다">엑셀</button>
     </div>
     ${st.msg?(st.msg.includes('실패')||st.msg.includes('오류')
        ?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`
        :`<div class="page-sub" style="color:#5a6b82">${esc(st.msg)}</div>`):''}
     ${st.note?`<div class="page-sub" style="color:#b8860b">${esc(st.note)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit pp-tbl" style="font-size:11px"><thead><tr>
       <th class="center">SEQ</th>${headTh()}${d.map(x=>`<th class="center"${isWkend(x)?' style="color:#c0392b"':''}>${esc(wlab(x))}</th>`).join('')}${tailTh()}</tr></thead>
      <tbody>${tbodyHtml}</tbody>
      <tfoot>${tfootHtml}</tfoot>
      </table></div>
     <div class="page-sub" style="text-align:left;margin-top:2px" id="pp-cnt">${cntHtml}</div>`;
    const g=id=>c.querySelector(id);
    // 조회(서버 재조회) = 기준일·자도번작업처·적용일수·소스만. 나머지 필터는 캐시에서 즉시필터라 재조회 불필요.
    g('#pp-go').onclick=()=>{st.base=g('#pp-base').value;st.wc=g('#pp-wc').value;st.gigan=+g('#pp-gigan').value;st.src=g('#pp-src').value;
      load();};
    // 소스는 고르는 즉시 색을 바꾼다(조회 전에도 무엇을 볼지 보이게). 실제 반영은 [조회].
    g('#pp-src').onchange=e=>{e.target.dataset.src=e.target.value;};
    // ★생산여부·구분·파트·라인·ASSY도번·도번·제번 = 캐시에서 즉시 재렌더(재조회 없음, 레거시 동일)
    // ★전부 redrawBody() = 표만 갱신(툴바 유지) → 2,900행에서도 즉각 반응
    c.querySelectorAll('input[name=pp-uf]').forEach(el=>el.onchange=()=>{const x=c.querySelector('input[name=pp-uf]:checked');if(x){st.unfin=x.value;redrawBody();}});
    c.querySelectorAll('input[name=pp-vw]').forEach(el=>el.onchange=()=>{const x=c.querySelector('input[name=pp-vw]:checked');if(x){st.view=x.value;st.expand.clear();redrawBody();}});
    // ★파트 변경 = 드래그 실적 가능 여부 재판정(파트마스터 설정 조회). 선택은 초기화.
    g('#pp-part').onchange=async()=>{st.part=g('#pp-part').value;st.dpSel.clear();st.dpQov.clear();
      await dpLoadConf(); render();};

    /* ==== 드래그 선택 — 키팅(준비실적처리)과 동일한 '사각범위' 방식 ====
       ★단순 mousemove 로 '지나간 셀'만 담으면 빠르게 끌 때 이벤트가 유실돼 중간이 빠진다.
         시작셀~현재셀의 (행,열) 사각범위를 매 move 마다 통째로 계산한다(엑셀 감각). */
    const gw=c.querySelector('.grid-wrap');
    if(gw&&dpOn()){
      /* ★userSelect 는 일자칸(.dp-c)에만 건다(2026-09-03).
           종전엔 grid-wrap 전체에 걸어 **표 어디서도 텍스트를 못 긁었다** — 복사 불가의 원인.
           일자칸만 막으면 실적 드래그 중 파란 텍스트선택이 끼는 것만 없어지고,
           나머지 컬럼은 우리 범위선택(.pp-sel)이 담당한다. (CSS .dp-c 에 이미 user-select:none) */
      gw.style.userSelect=''; gw.style.webkitUserSelect='';
      gw.onselectstart=e=>{const t=e.target;
        return !(t&&t.closest&&t.closest('.dp-c'));};
      const rcOf=td=>{const tr=td.parentElement;return {r:tr?tr.rowIndex:-1,c:td.cellIndex};};
      /* ★성능(2026-09-03): 종전엔 커서가 일자칸 밖일 때 그 행의 모든 .dp-c 에
           getBoundingClientRect() 를 돌려 '가장 가까운 칸'을 찾았다. rect 읽기는 강제 리플로우라
           mousemove 마다 열 개수만큼 발생 → 드래그가 무거웠다.
           → 열 위치는 드래그 중 변하지 않으므로 **헤더에서 한 번만 재서** 캐시한다(_colX).
             그 다음부터는 산술 비교만 한다. */
      let _colX=null,_colXGen=-1,_colXsx=-1;
      const colXCache=()=>{
        // 가로스크롤하면 화면좌표가 통째로 밀린다 → 스크롤 위치도 캐시키에 넣는다
        const sx=gw.scrollLeft;
        if(_colX&&_colXGen===_bodyGen&&_colXsx===sx)return _colX;
        _colXsx=sx;
        const row=gw.querySelector('tr.pp-agg,tbody tr'); _colX=[];
        if(row)for(const td of row.cells){
          if(td.classList.contains('dp-c')){const b=td.getBoundingClientRect();
            _colX.push({i:td.cellIndex,l:b.left,r:b.right});}}
        _colXGen=_bodyGen; return _colX;};
      const cellAt=(x,y)=>{
        const e=document.elementFromPoint(x,y); if(!e)return null;
        const td=e.closest('.dp-c'); if(td)return td;
        const tr=e.closest('tr');
        if(tr){
          const cols=colXCache(); let best=-1,bd=1e9;
          for(const cx of cols){                       // rect 읽기 없음 — 캐시된 좌표로 비교만
            const d=(x<cx.l)?(cx.l-x):((x>cx.r)?(x-cx.r):0);
            if(d<bd){bd=d;best=cx.i;}}
          if(best>=0&&best<tr.cells.length){const q=tr.cells[best];
            if(q&&q.classList.contains('dp-c'))return q;}}
        return e.closest('td');};
      const paintCnt=()=>{const el=c.querySelector('#pp-dp-cnt');
        if(el)el.textContent=st.dpSel.size+'건';};
      let _a=null,_cells=null,_own=null,_on=false,_cellsGen=-1;
      const applyRect=td=>{
        if(!_a||!_cells)return;
        const b=rcOf(td);
        const r1=Math.min(_a.r,b.r),r2=Math.max(_a.r,b.r);
        const c1=Math.min(_a.c,b.c),c2=Math.max(_a.c,b.c);
        for(const it of _cells){
          const inR=it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2;
          const has=st.dpSel.has(it.k);
          if(inR&&!has){st.dpSel.set(it.k,it.v);it.td.classList.add('dp-on');_own.add(it.k);}
          else if(!inR&&has&&_own.has(it.k)){st.dpSel.delete(it.k);it.td.classList.remove('dp-on');}
        }
        paintCnt();};
      gw.onmousedown=ev=>{
        if(ev.button!==0)return;
        // ★실적선택은 **일자칸(.dp-c)에서 시작할 때만**(2026-09-03 사용자 확정).
        //   그 외 셀의 드래그는 '복사용 범위선택'이 가져간다 — 종전엔 아무 td 에서나
        //   시작돼 도번·품명을 끌어도 실적이 잡혔고, 텍스트 복사가 아예 불가능했다.
        const any=ev.target.closest('td.dp-c'); if(!any||!any.closest('tr'))return;
        ev.preventDefault();
        if(!ev.ctrlKey&&!ev.metaKey){
          st.dpSel.clear();
          c.querySelectorAll('.dp-on').forEach(x=>x.classList.remove('dp-on'));
        }
        _on=true; _own=new Set();
        // ★성능(2026-09-03): mousedown 마다 전 셀을 훑고 rcOf() 를 부르면
        //   8,500행 × 일자컬럼에서 수만 번 DOM 접근이 일어나 클릭이 눈에 띄게 늦었다.
        //   → 캐시하고, 표가 다시 그려질 때만 무효화한다(_cellsGen 으로 세대 비교).
        if(!_cells||_cellsGen!==_bodyGen){
          _cells=[...c.querySelectorAll('.dp-c')].map(x=>{const p=rcOf(x);
            return {td:x,r:p.r,c:p.c,k:x.dataset.dp,
                    v:{part:x.dataset.part,item:x.dataset.item,wo:x.dataset.wo,
                       line:x.dataset.line,qty:+x.dataset.rem||0}};});
          _cellsGen=_bodyGen;
        }
        _a=rcOf(any);
        applyRect(any);
      };
      gw.onmousemove=ev=>{ if(!_on)return; const td=cellAt(ev.clientX,ev.clientY);
        if(td)applyRect(td); };
      if(!gw._dpUp){ gw._dpUp=1;
        document.addEventListener('mouseup',()=>{_on=false;}); }
    }
    // ★문서 캡처 리스너(파일 상단)가 찾아 쓰는 최신 핸들러. 이미 열린 탭에서도 확인이 먹는 이유.
    c._dpFn={ok:dpConfirm,no:dpClear};
    const dok=g('#pp-dp-ok'); if(dok)dok.onclick=dpConfirm;   // 직접배선도 유지(이중안전)
    const dcl=g('#pp-dp-clr'); if(dcl)dcl.onclick=dpClear;

    /* ==== 더블클릭 = 수량조정 (040 출하실적등록과 동일 패턴) ====
       계획 5개인데 3개만 실적을 잡는 경우가 있어 셀 단위로 수량을 정한다.
       모달은 body 에 렌더(§3 — .content 안에 fixed 를 넣으면 잘린다). */
    const dpQtyDlg=(td)=>{
      const key=td.dataset.dp, rem=+td.dataset.rem||0;
      if(rem<=0){alert('실적을 잡을 잔여계획이 없는 칸입니다.');return;}
      const old=document.getElementById('pp-qov'); if(old)old.remove();
      const cur0=st.dpQov.has(key)?Math.max(0,Math.min(rem,+st.dpQov.get(key)||0)):rem;
      const capNm=st.dpConf.type==='R'?'준비재고':'계획잔여';
      const ov=document.createElement('div'); ov.id='pp-qov';
      ov.style.cssText='position:fixed;inset:0;z-index:1200;background:rgba(0,0,0,.28);display:flex;align-items:center;justify-content:center';
      ov.innerHTML=`<div style="background:#fff;border:1px solid #90a4bd;border-radius:6px;min-width:340px;box-shadow:0 6px 22px rgba(0,0,0,.3);font-size:13px">
        <div style="background:#2f6fb3;color:#fff;padding:6px 10px;font-weight:600;display:flex;justify-content:space-between">
          <span>수량조정 (범위 0 ~ ${nf(rem)})</span><span id="ppq-x" style="cursor:pointer">✕</span></div>
        <div style="padding:8px 22px 0;color:#5a6b82;font-size:11.5px">
          ${esc(td.dataset.item||'')} · ${esc(st.dpConf.type_nm||'')} · 상한 ${capNm} ${nf(rem)}</div>
        <div style="padding:14px 22px;display:flex;align-items:center;gap:12px;justify-content:center">
          <label style="background:#dbe6f2;border:1px solid #b8c8dc;padding:4px 14px;font-weight:600">수량</label>
          <input id="ppq-v" type="number" min="0" max="${rem}" step="1" value="${cur0}"
                 style="width:120px;padding:5px 8px;border:1px solid #90a4bd;text-align:right;font-size:15px">
          <span style="color:#7a8aa0">/ ${nf(rem)}</span></div>
        <div style="padding:0 22px 16px;display:flex;gap:8px;justify-content:flex-end">
          <button id="ppq-no" class="btn">닫기</button>
          <button id="ppq-ok" class="btn" style="background:#1c7c3a;color:#fff">✔ 이 수량으로 실적처리</button></div></div>`;
      document.body.appendChild(ov);
      const inp=ov.querySelector('#ppq-v');
      inp.focus(); inp.select();
      const close=()=>ov.remove();
      const save=()=>{
        let v=Math.floor(+inp.value||0);
        if(!(v>=0)){alert('수량은 0 이상 숫자여야 합니다.');return;}
        if(v>rem){alert(`상한(${nf(rem)})보다 많이 잡을 수 없습니다.`);return;}
        if(v>=rem)st.dpQov.delete(key); else st.dpQov.set(key,v);
        // ★수량조정한 셀은 반드시 '선택' 상태로 만든다.
        //   더블클릭은 mousedown 을 2번 발생시키는데 2번째가 선택초기화 분기에 걸려
        //   선택이 풀린다. 그대로 두면 조정만 하고 [확인]을 눌러도 아무것도 안 잡힌다
        //   (040 에서 2026-08-25 실측된 함정 — 같은 구조라 여기도 동일하게 막는다).
        if(v>0){ st.dpSel.set(key,{part:td.dataset.part,item:td.dataset.item,
                   wo:td.dataset.wo,line:td.dataset.line,qty:v}); }
        else st.dpSel.delete(key);
        close();
        if(v<=0){ render(); return; }
        // ★여기서 곧바로 실적처리까지 끝낸다(040 동일). 조정만 해두고 따로 [확인]을
        //   누르게 하면 그 사이 선택이 풀려 "조정했는데 실적이 안 잡힌다"가 반복된다.
        dpConfirm();
      };
      ov.querySelector('#ppq-ok').onclick=save;
      ov.querySelector('#ppq-no').onclick=close;
      ov.querySelector('#ppq-x').onclick=close;
      ov.onclick=e=>{if(e.target===ov)close();};
      inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();save();}
                        else if(e.key==='Escape'){e.preventDefault();close();}};};
    // ★dpQtyDlg 정의 뒤에 바인딩(TDZ 회피 — core.js/이 화면에서 반복된 함정)
    if(gw&&dpOn()){
      gw.ondblclick=ev=>{
        const td=ev.target.closest?ev.target.closest('td.dp-c[data-dp]'):null;
        if(!td)return;
        ev.preventDefault(); ev.stopPropagation();
        dpQtyDlg(td);};
    }

    /* ==== 우클릭 컨텍스트 메뉴 (레거시 260 동일 — 확인 F12 / 취소 F11) ==== */
    const dpMenuClose=()=>{const m=document.getElementById('dp-menu'); if(m)m.remove();};
    if(gw&&dpOn()){
      gw.oncontextmenu=ev=>{
        ev.preventDefault(); dpMenuClose();
        // ★선택 안 된 셀에서 우클릭하면 그 셀을 잡아준다(040 동일).
        //   안 그러면 "메뉴는 뜨는데 전부 회색"이라 아무것도 못 한다.
        const td0=ev.target&&ev.target.closest?ev.target.closest('td.dp-c[data-dp]'):null;
        if(td0&&!st.dpSel.has(td0.dataset.dp)){
          st.dpSel.clear();
          c.querySelectorAll('.dp-on').forEach(x=>x.classList.remove('dp-on'));
          st.dpSel.set(td0.dataset.dp,{part:td0.dataset.part,item:td0.dataset.item,
            wo:td0.dataset.wo,line:td0.dataset.line,qty:+td0.dataset.rem||0});
          td0.classList.add('dp-on');
          const el=c.querySelector('#pp-dp-cnt'); if(el)el.textContent=st.dpSel.size+'건';
        }
        const n=st.dpSel.size;
        const m=document.createElement('div'); m.id='dp-menu';
        m.style.cssText='position:fixed;z-index:2000;background:#fff;border:1px solid #9fb3c8;'
          +'border-radius:6px;box-shadow:0 8px 24px rgba(10,25,55,.28);padding:4px 0;min-width:190px;font-size:13px';
        m.style.left=Math.min(ev.clientX,window.innerWidth-210)+'px';
        m.style.top =Math.min(ev.clientY,window.innerHeight-140)+'px';
        const row=(label,key,fn,dis)=>{
          const d=document.createElement('div');
          d.style.cssText='padding:6px 14px;display:flex;justify-content:space-between;gap:20px;'
            +(dis?'color:#b8c4d4;cursor:default':'cursor:pointer');
          d.innerHTML=`<span>${label}</span><span style="color:#8aa0bd;font-size:11px">${key}</span>`;
          if(!dis){ d.onmouseenter=()=>d.style.background='#eaf3ff';
                    d.onmouseleave=()=>d.style.background='';
                    d.onclick=()=>{dpMenuClose();fn();}; }
          m.appendChild(d);
        };
        row(`<b>확 인</b> <span style="color:#1c7c3a">${n}건</span>`,'F12',dpConfirm,!n);
        row('취 소','F11',dpClear,!n);
        const hr=document.createElement('div');
        hr.style.cssText='height:1px;background:#e3e9f0;margin:4px 0'; m.appendChild(hr);
        row('전체 해제','',()=>{st.dpSel.clear();render();},!n);
        /* ★항목보기·복사를 이 메뉴에도 넣는다(2026-09-03).
             드래그 실적모드(dpOn)에서는 .grid-wrap 의 이 핸들러가 표의 우클릭을 먼저 가져가
             **항목보기 메뉴가 아예 안 떴다**(사용자 보고). 메뉴를 하나로 합쳐 어느 모드에서도
             같은 자리에서 쓰게 한다. */
        const hr2=document.createElement('div');
        hr2.style.cssText='height:1px;background:#e3e9f0;margin:4px 0'; m.appendChild(hr2);
        row('항목보기','',()=>openColPick(),false);
        row('선택영역 복사','',()=>copySel(),false);
        row('전체 복사','',()=>copyAll(),false);
        document.body.appendChild(m);
        // ★바깥 클릭으로 닫기는 반드시 'click' 으로 건다(040 동일).
        //   'mousedown' 으로 걸면 메뉴 항목을 누르는 순간 mousedown 이 먼저 떠서
        //   메뉴가 제거되고, 이어질 click 이 사라진 요소에서 발생해 onclick 이
        //   영영 안 불린다 — "메뉴는 뜨는데 확인이 안 먹는" 증상의 원인(2026-08-30).
        setTimeout(()=>{document.addEventListener('click',dpMenuClose,{once:true});},0);
      };
    }
    // 단축키 — F12 확인 / F11 취소 (레거시 동일)
    if(!window._dpKey){ window._dpKey=1;
      document.addEventListener('keydown',e=>{
        const s2=(typeof st!=='undefined')?st:null;
        if(!s2||!s2.dpSel||!s2.dpSel.size)return;
        if(e.key==='F12'){e.preventDefault();dpConfirm();}
        else if(e.key==='F11'){e.preventDefault();dpClear();}
      });
    }
    g('#pp-line').onchange=()=>{st.line=g('#pp-line').value;redrawBody();};
    /* ★컬럼 헤더 드래그 이동은 제거했다(2026-09-03 사용자 요청).
         왜 — 8,500행이 붙은 표에서 열을 옮기면 헤더+전 행의 셀을 하나씩 insertBefore 해야 해서
         표를 DOM 에서 떼었다 붙이는 최적화를 넣고도 저사양 PC 에서 버벅였다("탭이동은 버벅").
         순서 변경은 **항목보기**(헤더 우클릭)에서 한다 — 목록 행만 움직이므로 표를 전혀
         건드리지 않아 즉각 반응하고, 숨김·순서를 한 자리에서 정리해 [확인] 한 번에 반영된다. */
    wireRows();   // 집계행 클릭(펼침/접힘) — 표만 다시 그릴 때도 재연결 필요해서 별도 함수로 분리
    ppWireLazy(); // 스크롤 이어붙이기(점진 렌더) — 전체 렌더 경로
    g('#pp-prev').onclick=()=>shiftDay(-1);g('#pp-next').onclick=()=>shiftDay(1);
    // 텍스트 필터 3종 = 입력 즉시 클라이언트 필터(재조회 없음).
    // ★성능: 타이핑마다 전체 재렌더하면 2,900행 기준 버벅임 → 180ms 디바운스 + 표(tbody/tfoot)만 교체(툴바 유지=포커스/커서 보존).
    [['#pp-dono','dono'],['#pp-jado','jado'],['#pp-wo','wo']].forEach(([id,key])=>{const e=g(id);if(!e)return;
      e.oninput=()=>{clearTimeout(_typeT);const v=e.value.trim();
        _typeT=setTimeout(()=>{st[key]=v;redrawBody();},180);};});

    /* ══ 항목보기 (레거시 '항목보기' 이식, 2026-09-03) ══════════════════════
       헤더 우클릭 → 컬럼 체크박스 목록. 해제하면 표에서 숨김. 순번대로 나오고
       목록 자체를 드래그해 순서도 바꾼다(헤더 드래그와 같은 저장소를 쓴다).
       일자컬럼은 조회조건(적용일수)이 정하므로 대상에서 뺀다. */
    const openColPick=()=>{
      const old=document.getElementById('pp-colpick'); if(old)old.remove();
      // 표시순서 = 저장된 전체순서(head 그룹 → tail 그룹). 숨긴 것도 목록엔 나온다(체크만 해제).
      const list=[...headOrderAll.map(k=>[k,'head']),...tailOrderAll.map(k=>[k,'tail'])];
      const ov=document.createElement('div'); ov.className='ppcol-ov'; ov.id='pp-colpick';
      ov.innerHTML=`<div class="ppcol-bx">
        <div class="ppcol-h">항목보기<span style="font-weight:400;font-size:11px;color:#7b8aa0">체크 해제 = 숨김 · 행을 끌거나 ▲▼ 로 순서 변경</span></div>
        <div class="ppcol-b" id="ppcol-list"></div>
        <div class="ppcol-f">
          <button class="btn ghost" id="ppcol-reset">초기화</button>
          <div style="flex:1"></div>
          <button class="btn ghost" id="ppcol-no">취소</button>
          <button class="btn" id="ppcol-ok" style="background:#1c47a0;color:#fff">확인</button>
        </div></div>`;
      document.body.appendChild(ov);           // ★§3 — .content 안에 fixed 를 넣으면 잘린다
      let work=list.slice(), hide=new Set(hideSet);
      /* ★순서 변경 = 마우스 이벤트로 직접 구현(2026-09-03 재작업).
           HTML5 draggable 은 여기서 신뢰할 수 없었다 — 텍스트 선택이 먼저 잡혀
           파란 블록만 생기고 드래그가 시작되지 않았다(사용자 보고).
           mousedown/mousemove/mouseup 으로 직접 처리하면 브라우저 기본동작에
           의존하지 않아 확실하다. 5px 이상 움직여야 드래그로 보므로 '클릭=체크토글'과
           충돌하지 않는다(그냥 누르면 체크, 끌면 이동). */
      let dragK=null, dragFrom=0, moved=false;
      const paint=()=>{
        /* ★일자컬럼 경계선(2026-09-03) — '앞/뒤' 글자만으로는 어디가 경계인지 애매했다.
             표는 [앞그룹][일자컬럼][뒷그룹] 이므로, 목록에서도 그 자리에 일자컬럼을
             한 줄로 그려 넣는다. 이 줄 위로 옮기면 일자 앞, 아래면 일자 뒤가 된다. */
        const firstTail=work.findIndex(x=>x[1]==='tail');
        ov.querySelector('#ppcol-list').innerHTML=work.map(([k,grp],i)=>
          (i===firstTail?`<div class="ppcol-sep">일자 컬럼 (조회조건 '적용일수'로 결정)</div>`:'')
          +`<div class="ppcol-r" data-k="${k}" data-grp="${grp}" data-i="${i}">
             <span class="ppcol-n">${i+1}</span>
             <input type="checkbox" ${hide.has(k)?'':'checked'}>
             <span class="ppcol-t">${esc(ALLDEF[k].t)}</span>
             <span class="ppcol-g" style="color:#c3cbd6;font-size:10px">${grp==='head'?'앞':'뒤'}</span>
             <span class="ppcol-mv">
               <button data-mv="up"   title="위로"   ${i===0?'disabled':''}>▲</button>
               <button data-mv="down" title="아래로" ${i===work.length-1?'disabled':''}>▼</button>
             </span>
           </div>`).join('')
          +(firstTail<0?`<div class="ppcol-sep">일자 컬럼 (조회조건 '적용일수'로 결정)</div>`:'');
        ov.querySelectorAll('.ppcol-r').forEach(row=>{
          const k=row.dataset.k;
          const cb=row.querySelector('input');
          cb.onchange=()=>{if(cb.checked)hide.delete(k);else hide.add(k);};
          /* ★▲▼ 버튼 — 드래그가 어려운 환경(터치패드 등)을 위한 확실한 수단.
               한 칸 옮기고, 그룹 경계를 넘으면 그 자리의 그룹을 물려받는다. */
          row.querySelectorAll('[data-mv]').forEach(b=>b.onclick=ev=>{
            ev.stopPropagation();
            const i=work.findIndex(x=>x[0]===k);
            const j=(b.dataset.mv==='up')?i-1:i+1;
            if(j<0||j>=work.length)return;
            const item=work[i];
            item[1]=work[j][1];                 // 지나간 자리의 그룹을 따른다
            work[i]=work[j]; work[j]=item;
            paint();});
        });
      };
      const listEl=ov.querySelector('#ppcol-list');
      const rowAtY=(y)=>{                      // 커서 아래 행 찾기(경계 밖이면 맨위/맨아래)
        const rows=[...listEl.querySelectorAll('.ppcol-r')];
        if(!rows.length)return null;
        for(const r of rows){const b=r.getBoundingClientRect();
          if(y>=b.top&&y<=b.bottom)return r;}
        // ★일자 구분선 위에 놓은 경우 — 가장 가까운 행으로 붙인다(그 줄 자체는 행이 아니다).
        //   이러면 "경계에 걸쳐 놓기"가 자연스럽게 앞/뒤 중 가까운 쪽으로 정해진다.
        let best=rows[0],bd=1e9;
        for(const r of rows){const b=r.getBoundingClientRect();
          const dist=(y<b.top)?(b.top-y):((y>b.bottom)?(y-b.bottom):0);
          if(dist<bd){bd=dist;best=r;}}
        return best;
      };
      listEl.addEventListener('mousedown',ev=>{
        const row=ev.target.closest&&ev.target.closest('.ppcol-r'); if(!row)return;
        if(ev.target.tagName==='INPUT')return;    // 체크박스는 브라우저가 처리
        if(ev.target.closest('.ppcol-mv'))return; // ▲▼ 버튼은 클릭으로 처리(드래그 아님)
        ev.preventDefault();                     // ★텍스트 선택 차단 — 파란 블록의 원인
        dragK=row.dataset.k; dragFrom=+row.dataset.i; moved=false;
        row.classList.add('drag');
      });
      document.addEventListener('mousemove',function ppcolMove(ev){
        if(!dragK)return;
        if(!ov.isConnected){dragK=null;document.removeEventListener('mousemove',ppcolMove);return;}
        moved=true;
        const over=rowAtY(ev.clientY);
        listEl.querySelectorAll('.ppcol-r.over').forEach(x=>{if(x!==over)x.classList.remove('over');});
        if(over&&over.dataset.k!==dragK)over.classList.add('over');
      });
      document.addEventListener('mouseup',function ppcolUp(ev){
        if(!dragK){return;}
        if(!ov.isConnected){dragK=null;document.removeEventListener('mouseup',ppcolUp);return;}
        const k=dragK; dragK=null;
        listEl.querySelectorAll('.ppcol-r.drag,.ppcol-r.over')
              .forEach(x=>x.classList.remove('drag','over'));
        const srcRow=[...listEl.querySelectorAll('.ppcol-r')].find(r=>r.dataset.k===k);
        if(!moved){                              // 안 움직였으면 = 클릭 → 체크 토글
          if(srcRow){const cb=srcRow.querySelector('input');
            cb.checked=!cb.checked; if(cb.checked)hide.delete(k);else hide.add(k);}
          return;
        }
        const over=rowAtY(ev.clientY);
        if(!over||over.dataset.k===k)return;
        /* ★그룹(앞/뒤) 경계를 넘는 이동 허용(사용자 요청).
             표는 [SEQ][앞그룹][일자컬럼][뒷그룹] 구조라 일자컬럼이 사이에 끼어 있다.
             놓은 자리의 그룹을 물려받는다 = 일자컬럼 기준 어느 편에 설지가 정해진다. */
        const fi=work.findIndex(x=>x[0]===k); const item=work[fi];
        work.splice(fi,1);
        const ti=work.findIndex(x=>x[0]===over.dataset.k);
        item[1]=over.dataset.grp;
        work.splice(ti<0?work.length:ti,0,item);
        paint();
      });
      paint();
      const close=()=>ov.remove();
      ov.onclick=e=>{if(e.target===ov)close();};
      ov.querySelector('#ppcol-no').onclick=close;
      ov.querySelector('#ppcol-reset').onclick=()=>{
        work=[...HEAD_DEFAULT.map(k=>[k,'head']),...TAIL_DEFAULT.map(k=>[k,'tail'])];
        hide=new Set(); paint();};
      ov.querySelector('#ppcol-ok').onclick=()=>{
        const h=work.filter(x=>x[1]==='head').map(x=>x[0]);
        const t=work.filter(x=>x[1]==='tail').map(x=>x[0]);
        prefSave({[HEAD_LSKEY]:h,[TAIL_LSKEY]:t,[HIDE_LSKEY]:[...hide]});   // ★계정별 서버 저장
        close();
        /* ★redrawBody() 는 tbody/tfoot 만 교체하고 <thead> 는 그대로 둔다 →
             컬럼 구성이 바뀌어도 헤더가 안 바뀌어 "확인을 눌러도 그대로"였다(2026-09-03).
             컬럼 구성 변경은 헤더까지 다시 그려야 하므로 전체 렌더로 간다(스크롤은 직접 보존). */
        const w=c.querySelector('.grid-wrap'); const sy=w?w.scrollTop:0, sx=w?w.scrollLeft:0;
        render();
        const n=c.querySelector('.grid-wrap'); if(n){n.scrollTop=sy;n.scrollLeft=sx;}};
    };
    // 헤더 우클릭 = 항목보기 (레거시와 동일 진입). 표 어디서 눌러도 뜨게 tbody 도 받는다.
    const tblEl=c.querySelector('table.pp-tbl')||c.querySelector('table');
    if(tblEl)tblEl.oncontextmenu=ev=>{
      ev.preventDefault();
      const old=document.querySelector('.pp-ctx'); if(old)old.remove();
      const m=document.createElement('div'); m.className='pp-ctx';
      m.innerHTML='<div data-a="col">항목보기</div><div data-a="copy">선택영역 복사</div><div data-a="all">전체 복사</div>';
      m.style.left=Math.min(ev.clientX,innerWidth-170)+'px';
      m.style.top=Math.min(ev.clientY,innerHeight-110)+'px';
      document.body.appendChild(m);
      /* ★바깥클릭 닫기와 항목실행의 순서 문제(2026-09-03 수정).
           종전엔 document 의 mousedown 으로 닫고 메뉴는 click 으로 실행했다.
           mousedown 이 click 보다 **먼저** 오므로 메뉴가 이미 remove 된 뒤라
           click 이 죽은 노드에서 발생 → **항목보기를 눌러도 아무 일도 안 일어났다**.
           → 메뉴 실행도 mousedown 에서 처리하고, 바깥클릭 닫기는 메뉴 안을 제외한다. */
      const kill=()=>{m.remove();document.removeEventListener('mousedown',outside,true);};
      const outside=e=>{if(!m.contains(e.target))kill();};
      setTimeout(()=>document.addEventListener('mousedown',outside,true),0);
      m.addEventListener('mousedown',e=>{
        e.preventDefault(); e.stopPropagation();          // 표의 범위선택 mousedown 으로 새지 않게
        const t=e.target.closest&&e.target.closest('[data-a]'); if(!t)return;
        const a=t.getAttribute('data-a'); kill();
        if(a==='col')openColPick(); else if(a==='copy')copySel(); else if(a==='all')copyAll();
      });
    };

    /* ══ 범위선택 + Ctrl+C 복사 (2026-09-03) ══════════════════════════════
       일자칸(.dp-c)은 드래그=실적선택으로 이미 쓰이므로 건드리지 않는다.
       그 외 셀에서 끌면 엑셀식 사각범위가 잡히고 Ctrl+C 로 탭구분 텍스트가 복사된다
       (엑셀에 그대로 붙는다). 선택색은 실적선택(파랑)과 구분되게 회청색. */
    const gw2=c.querySelector('.grid-wrap');
    if(gw2&&!gw2.dataset.cpsel){
      gw2.dataset.cpsel='1';
      let a0=null,on=false;
      const rc=td=>({r:td.parentElement?td.parentElement.rowIndex:-1,c:td.cellIndex});
      /* ★칠한 셀을 직접 들고 있는다(2026-09-03) — clearSel 이 매번 querySelectorAll('.pp-sel')로
           문서를 훑으면 드래그 중 프레임마다 전체 스캔이 된다. 배열로 기억하면 지울 것만 지운다.
           (표가 재렌더되면 죽은 노드가 남을 수 있으나 classList 조작은 무해하고, 새 표에는 안 붙는다) */
      let painted=[];
      const clearSel=()=>{for(const x of painted)x.classList.remove('pp-sel'); painted=[];};
      const paintRange=(b)=>{
        if(!a0)return;
        const r1=Math.min(a0.r,b.r),r2=Math.max(a0.r,b.r);
        const c1=Math.min(a0.c,b.c),c2=Math.max(a0.c,b.c);
        clearSel();
        const tbl=gw2.querySelector('table'); if(!tbl)return;
        // ★행 전체를 훑되 rows/cells 직접 인덱싱 — querySelectorAll 반복보다 훨씬 싸다
        const bodies=[...tbl.tBodies];
        bodies.forEach(tb=>{const rs=tb.rows;
          for(let i=0;i<rs.length;i++){const row=rs[i]; const ri=row.rowIndex;
            if(ri<r1||ri>r2)continue;
            // ★소계/집계행(청록 .pp-agg)은 선택 대상이 아니다 — 레거시도 그렇다(2026-09-03).
            //   이 행은 '펼침/접힘'만 하는 자리다. 선택모양이 뜨면 그 행도 복사되는 줄 알게 된다.
            if(row.classList.contains('pp-agg'))continue;
            const cs=row.cells;
            // ★실적칸(.dp-c)은 복사선택에서 제외 — 두 선택이 겹쳐 "표시가 2개" 로 보였다(2026-09-03).
            //   일자칸은 실적선택(파랑) 전용, 나머지는 복사선택(회청) 전용으로 완전히 가른다.
            for(let j=c1;j<=c2&&j<cs.length;j++){
              const cell=cs[j];
              if(!cell.classList.contains('dp-c')){cell.classList.add('pp-sel');painted.push(cell);}}}});
      };
      gw2.addEventListener('mousedown',ev=>{
        if(ev.button!==0)return;
        const td=ev.target.closest&&ev.target.closest('td');
        if(!td||!td.parentElement)return;
        if(td.classList.contains('dp-c'))return;      // ★일자칸=실적선택 영역, 건드리지 않음
        // ★소계/집계행에서는 선택을 시작하지도 않는다 — 그 자리는 더블클릭(펼침) 전용.
        if(td.parentElement.classList.contains('pp-agg')){clearSel();return;}
        // ★실적선택이 남아 있으면 지운다 — 한 화면에 선택이 두 종류 보이면 헷갈린다.
        if(st.dpSel&&st.dpSel.size){st.dpSel.clear();
          c.querySelectorAll('.dp-on').forEach(x=>x.classList.remove('dp-on'));
          const el=c.querySelector('#pp-dp-cnt'); if(el)el.textContent='0건';}
        clearSel(); a0=rc(td); on=true; paintRange(a0);
        ev.preventDefault();                          // 브라우저 기본 텍스트선택과 겹치지 않게
      });
      /* ★성능(2026-09-03): mousemove 는 초당 수십~수백 회 온다.
           매번 paintRange 를 돌리면 clearSel(전체 훑기)+전 행 재칠하기가 반복돼
           대각선으로 길게 끌 때 눈에 띄게 끊겼다.
           ①같은 셀 위에서 움직이면 무시(대부분의 이벤트가 여기서 걸러진다)
           ②실제 칠하기는 rAF 로 프레임당 1회 — 화면 갱신 주기보다 자주 칠할 이유가 없다. */
      let lastB=null,rafId=0;
      gw2.addEventListener('mousemove',ev=>{
        if(!on)return;
        const td=ev.target.closest&&ev.target.closest('td');
        if(!td||!td.parentElement)return;
        const b=rc(td);
        if(lastB&&lastB.r===b.r&&lastB.c===b.c)return;    // ① 같은 칸 → 할 일 없음
        lastB=b;
        if(rafId)return;
        rafId=requestAnimationFrame(()=>{rafId=0; if(on&&lastB)paintRange(lastB);});  // ② 프레임당 1회
      });
      document.addEventListener('mouseup',()=>{
        if(rafId){cancelAnimationFrame(rafId);rafId=0;}
        if(on&&lastB)paintRange(lastB);                   // 마지막 위치는 확실히 반영
        on=false; lastB=null;});
    }
    // 선택영역 → 탭구분 텍스트(엑셀 붙여넣기 호환)
    const selText=()=>{
      const cells=[...c.querySelectorAll('.pp-sel')];
      if(!cells.length)return '';
      const map=new Map();
      cells.forEach(td=>{const r=td.parentElement.rowIndex;
        if(!map.has(r))map.set(r,[]);
        map.get(r).push([td.cellIndex,(td.innerText||'').trim()]);});
      return [...map.keys()].sort((x,y)=>x-y)
        .map(r=>map.get(r).sort((x,y)=>x[0]-y[0]).map(x=>x[1]).join('\t')).join('\n');
    };
    const toClip=(txt,what)=>{
      if(!txt){alert('복사할 영역을 먼저 끌어서 선택하세요.');return;}
      const done=()=>{const el=c.querySelector('#pp-cnt');
        if(el){const o=el.textContent;el.textContent=what+' 복사됨';setTimeout(()=>{el.textContent=o;},1400);}};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(txt).then(done,()=>fallback());
      }else fallback();
      function fallback(){   // 비보안 컨텍스트(http)에서는 clipboard API 가 막힌다
        const ta=document.createElement('textarea'); ta.value=txt;
        ta.style.cssText='position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta); ta.select();
        try{document.execCommand('copy');done();}catch(_){alert('복사에 실패했습니다.');}
        ta.remove();}
    };
    const copySel=()=>toClip(selText(),'선택영역');
    const copyAll=()=>{
      const tbl=c.querySelector('.grid-wrap table'); if(!tbl)return;
      const out=[];
      const hr=tbl.tHead&&tbl.tHead.rows[0];
      if(hr)out.push([...hr.cells].map(th=>(th.innerText||'').trim()).join('\t'));
      [...tbl.tBodies].forEach(tb=>{const rs=tb.rows;
        for(let i=0;i<rs.length;i++)out.push([...rs[i].cells].map(td=>(td.innerText||'').trim()).join('\t'));});
      toClip(out.join('\n'),`전체 ${nf(out.length-1)}행`);
    };
    // Ctrl+C — 이 화면이 열려 있을 때만. 표 안에 선택영역이 있으면 그걸 가로챈다.
    if(!c.dataset.cpkey){
      c.dataset.cpkey='1';
      c.addEventListener('keydown',ev=>{
        if((ev.ctrlKey||ev.metaKey)&&(ev.key==='c'||ev.key==='C')){
          if(!c.querySelector('.pp-sel'))return;      // 선택 없으면 브라우저 기본 동작
          ev.preventDefault(); copySel();}
      });
      c.setAttribute('tabindex','-1');                // keydown 을 받으려면 포커스 가능해야 한다
      c.style.outline='none';
    }
    /* ══ 엑셀 다운로드 — 화면 그대로(색상 포함) ══════════════════════════
       ★DOM 에서 읽는다. 데이터에서 다시 만들면 항목보기(숨김·순서)·집계/상세 뷰·
         펼침상태를 전부 재현해야 하고, 그러면 화면과 어긋날 여지가 생긴다.
         "보이는 대로 받는다"가 사용자가 기대하는 동작이다.
       ★점진 렌더 때문에 화면에는 일부 행만 붙어 있으므로, **전 행을 임시로 붙였다가**
         뽑고 되돌린다(안 그러면 400행만 받는다).
       ★색상은 셀의 실제 배경색(computed)을 그대로 쓴다 = 레거시 색규칙을 재구현할 필요 없음. */
    const g2=id=>c.querySelector(id);
    const xlsBtn=g2('#pp-xls');
    if(xlsBtn)xlsBtn.onclick=()=>{
      const tbl=c.querySelector('.grid-wrap table'); if(!tbl)return;
      if(!disp.length){alert('조회 결과가 없습니다.');return;}
      const restore=ppRest;                       // 점진렌더 잔여분 백업
      const tb=tbl.tBodies[0];
      const added=[];
      if(ppRest&&ppRest.length){                  // 전 행을 임시로 붙인다
        const before=tb.rows.length;
        tb.insertAdjacentHTML('beforeend',ppRest.join(''));
        for(let i=before;i<tb.rows.length;i++)added.push(tb.rows[i]);
      }
      try{
        /* ★alpha=0(투명)을 반드시 걸러야 한다 — 색이 안 칠해진 셀의 backgroundColor 는
             'rgba(0, 0, 0, 0)' 이라 그냥 파싱하면 **#000000(검정)** 이 되어
             표 전체가 새까맣게 나온다. 흰색도 서식 없음으로 보내 파일을 가볍게 한다. */
        const rgb2hex=s=>{const m=/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/.exec(s||'');
          if(!m)return '';
          if(m[4]!==undefined&&parseFloat(m[4])===0)return '';    // 투명 = 색 없음
          const h=(+m[1]<<16|+m[2]<<8|+m[3]).toString(16).padStart(6,'0').toUpperCase();
          return (h==='FFFFFF')?'':'#'+h;};
        const hr=tbl.tHead.rows[0];
        const cols=[...hr.cells].map(th=>({h:(th.innerText||'').trim(),
                                           w:Math.max(60,Math.round(th.getBoundingClientRect().width))}));
        const cellOf=td=>{
          const cs=getComputedStyle(td);
          const t=(td.innerText||'').trim().replace(/^[▼▶]\s*/,'');   // 펼침 마커는 뺀다
          const bg=rgb2hex(cs.backgroundColor), fg=rgb2hex(cs.color);
          const num=(t!==''&&/^-?[\d,]+(\.\d+)?$/.test(t))?Number(t.replace(/,/g,'')):null;
          return {v:(num===null||isNaN(num))?t:num,
                  bg:bg||'', fg:(fg&&fg!=='#000000')?fg:'',
                  b:(+cs.fontWeight>=600)?1:0, al:'center'};
        };
        const rows=[];
        for(const tr of tb.rows){
          if(tr.querySelector('td.empty'))continue;
          rows.push([...tr.cells].map(cellOf));
        }
        const foot=tbl.tFoot?[...tbl.tFoot.rows].map(tr=>[...tr.cells].map(cellOf)):[];
        const T=new Date(),p=n=>String(n).padStart(2,'0');
        const stamp=`${String(T.getFullYear()).slice(2)}${p(T.getMonth()+1)}${p(T.getDate())}`
                   +`${p(T.getHours())}${p(T.getMinutes())}`;
        const partNm=st.part?(PART_FIX.find(x=>x[0]===st.part)||['',''])[1]:'전체';
        downloadXLS(`파트별생산계획_${stamp}`,cols,rows,
          {sheet:'파트별 생산계획',
           title:`파트별 생산계획 — 기준일자 ${st.base} · 파트 ${partNm} · ${st.view}`,
           sub:`${nf(disp.length)}건 · 적용일수 ${st.gigan}일 · ${st.unfin}`,
           foot});
      }finally{
        added.forEach(tr=>tr.remove());           // ★임시로 붙인 행은 반드시 되돌린다
        ppRest=restore;
      }
    };
    if(typeof attachResizers==='function')attachResizers(c);
  };
  // ★계획 기준일(마지막 업로드 일자축 첫날)만 잡고 화면을 그린다 — 2026-08-28
  //   ★자동조회 안 함(2026-08-30 사용자 요청): 8,500행 조회가 진입할 때마다 걸려
  //     느리고, 조건을 바꾸기도 전에 먼저 도는 게 불편하다. [조회] 를 눌러야 조회.
  (async()=>{try{const b=await planBase();if(b&&b.iso)st.base=b.iso;}catch(_){}
             await loadLines();
             await prefLoad();          // ★내 항목보기 설정(계정별) — 표를 그리기 전에 받아둔다
             st.msg='조건을 고르고 [🔍 조회] 를 누르세요.';
             render();})();
};
// 색 우선순위(낮을수록 완료단계 높음): 출하6 < 생산4 < 키팅3 < 자재2 < 미키팅0
function finRank(f){return {'6':1,'4':2,'3':3,'2':4,'0':9}[f]||9;}
// ★소계/집계행 색 롤업 우선순위(파트별 생산계획): 관련색 하나라도 있으면 그 색 — 녹3 > 노랑4 > 주황6 > 자재2 > 무색0.
//   (셀 단위 finRank와 반대 방향: 소계는 "진행 중인 게 하나라도 있으면 그 상태로 보이게" = 현장 판단 기준)
function aggRank(f){return {'3':1,'4':2,'7':3,'6':4,'2':5,'0':9}[f]||9;}   // '7'=현재공정(전표) — 출하'6'보다 앞

/* ===== 생산 ③: 생산실적현황 (w_pr_list_010) — 작업장별집계/도번별상세(실측확정) ===== */
SCREEN.prodresult=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf1=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:1,maximumFractionDigits:1});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),swork:'',line:'',item:'',tag:'',gubun:'1'};
  let works=[], lines=[], filtLoaded=false, acT=null;
  let data={mode:'1',rows:[],cnt:0,sum_lot:0,sum_qty:0,sum_st:0}, loading=false, msg='';
  const tagCell=g=>g==='양산'?'<span style="color:#1c47a0;font-weight:700">양산</span>':(g==='셀'?'<span style="color:#8a5a1a;font-weight:700">셀</span>':'');
  const acItem=(val)=>{clearTimeout(acT);const t=(val||'').trim();if(!t)return;acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);const rows=(await r.json()).rows||[];const dl=c.querySelector('#pr-itemdl');if(dl)dl.innerHTML=rows.slice(0,40).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');}catch(e){}},180);};
  const loadFilters=async()=>{try{const r=await fetch(`${API}/api/prodresult/filters`);const j=await r.json();works=j.works||[];lines=j.lines||[];}catch(e){}filtLoaded=true;};
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,swork:F.swork,line:F.line,item:F.item,tag:F.tag,gubun:F.gubun});
    try{const r=await fetch(`${API}/api/prodresult/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패';data={mode:F.gubun,rows:[],cnt:0,sum_lot:0,sum_qty:0,sum_st:0};}
    loading=false;draw();};
  const draw=()=>{
    const detail=(data.mode==='2');
    const workOpts=`<option value="">전체</option>`+works.map(o=>`<option value="${esc(o.code)}"${F.swork===o.code?' selected':''}>${esc(o.code)} ${esc(o.name)}</option>`).join('');
    const lineOpts=`<option value="">전체</option>`+lines.map(l=>`<option value="${esc(l)}"${F.line===l?' selected':''}>${esc(l)}</option>`).join('');
    const head=detail
      ? `<tr><th style="text-align:left">도번</th><th style="text-align:left">품명</th><th class="center">생산일자</th><th class="center">라인</th><th class="num">생산수량</th><th class="num">필요ST</th><th class="center">구분</th></tr>`
      : `<tr><th style="text-align:left">작업장명</th><th class="center">생산일자</th><th class="num">LOT수량</th><th class="num">생산수량</th><th class="num">필요ST</th><th class="center">구분</th></tr>`;
    const ncol=detail?7:6;
    const body=loading?spinRow(ncol):(data.rows.length?data.rows.map(r=>detail
      ? `<tr><td style="text-align:left"><b>${esc(r.item)}</b></td><td style="text-align:left">${esc(r.inm)}</td><td class="center">${ymd(r.ymd)}</td><td class="center">${esc(r.line)}</td><td class="num"><b>${nf(r.qty)}</b></td><td class="num">${nf1(r.st)}</td><td class="center">${tagCell(r.gubun)}</td></tr>`
      : `<tr><td style="text-align:left">${esc((r.wc?r.wc+' ':'')+r.wcnm)||''}</td><td class="center">${ymd(r.ymd)}</td><td class="num">${nf(r.lot)}</td><td class="num"><b>${nf(r.qty)}</b></td><td class="num">${nf1(r.st)}</td><td class="center">${tagCell(r.gubun)}</td></tr>`
    ).join(''):`<tr><td colspan="${ncol}" class="empty">조회 결과 없음</td></tr>`);
    const foot=data.rows.length?(detail
      ? `<tfoot><tr class="grandtot"><td colspan="4" class="center">합계 ${nf(data.cnt)}건</td><td class="num">${nf(data.sum_qty)}</td><td class="num">${nf1(data.sum_st)}</td><td></td></tr></tfoot>`
      : `<tfoot><tr class="grandtot"><td colspan="2" class="center">합계 ${nf(data.cnt)}건</td><td class="num">${nf(data.sum_lot)}</td><td class="num">${nf(data.sum_qty)}</td><td class="num">${nf1(data.sum_st)}</td><td></td></tr></tfoot>`):'';
    c.innerHTML=`
     <div class="page-title">📊 생산실적현황 <span style="font-size:12px;color:var(--muted);font-weight:400">${detail?'도번별 상세':'작업장별 일별 집계'} · 레거시 w_pr_list_010</span></div>
     <div class="page-sub">필요ST=Σ(품목ST×생산수량)/60${detail?'':' · LOT수량=품목종수'}. 🟢 nx · 원본 <code>PR_T_PROD_DTL</code></div>
     <div class="toolbar">
       <label class="tl">생산기간</label><input class="inp" type="date" id="pr-from" value="${F.from}" style="width:130px"> ~ <input class="inp" type="date" id="pr-to" value="${F.to}" style="width:130px">
       <label class="tl">작업장</label><select class="inp" id="pr-sw" style="width:96px">${workOpts}</select>
       <label class="tl">라인</label><select class="inp" id="pr-line" style="width:74px">${lineOpts}</select>
       <label class="tl">양산/셀</label><select class="inp" id="pr-tag" style="width:70px"><option value=""${F.tag===''?' selected':''}>전체</option><option value="1"${F.tag==='1'?' selected':''}>양산</option><option value="2"${F.tag==='2'?' selected':''}>셀</option></select>
       <label class="tl">도번</label><input class="inp" id="pr-item" list="pr-itemdl" autocomplete="off" value="${esc(F.item)}" style="width:104px;text-transform:uppercase"><datalist id="pr-itemdl"></datalist>
       <label class="tl">조회종류</label><select class="inp" id="pr-gubun" style="width:132px"><option value="1"${F.gubun==='1'?' selected':''}>작업장별 집계</option><option value="2"${F.gubun==='2'?' selected':''}>도번별 상세</option></select>
       <button class="btn" id="pr-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건${detail?'':` · LOT <b>${nf(data.sum_lot)}</b>`} · 생산수량 <b>${nf(data.sum_qty)}</b> · 필요ST <b>${nf1(data.sum_st)}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:12px"><thead>${head}</thead><tbody>${body}</tbody>${foot}</table></div>`;
    const g=id=>c.querySelector(id);
    g('#pr-search').onclick=()=>{F.from=g('#pr-from').value;F.to=g('#pr-to').value;F.swork=g('#pr-sw').value;F.line=g('#pr-line').value;F.item=g('#pr-item').value;F.tag=g('#pr-tag').value;F.gubun=g('#pr-gubun').value;load();};
    g('#pr-item').oninput=e=>acItem(e.target.value);
    g('#pr-item').onkeyup=e=>{if(e.key==='Enter')g('#pr-search').click();};
    ['#pr-sw','#pr-line','#pr-tag','#pr-gubun'].forEach(id=>g(id).onchange=()=>g('#pr-search').click());
  };
  (async()=>{await loadFilters();load();})();
};

/* ===== 생산 ④: 파트별 생산실적현황 (w_pr_list_090) — 집계/도번/바코드/가간판/스티커(실측확정) ===== */
SCREEN.partresult=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf1=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:1,maximumFractionDigits:1});
  const nf2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const ymd=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // 레거시 w_pr_list_090 조회종류(list_gubun). 4(용접전표)는 제외.
  const GUBUNS=[['1','파트별 생산실적(집계)'],['2','파트별 생산실적(도번)'],['7','바코드실적처리'],['5','가간판'],['6','스티커']];
  let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),part:'',item:'',worker:'',gubun:'1'};
  let parts=[], acT=null;
  let data={mode:'1',rows:[],cnt:0,sum_qty:0,sum_st:0}, loading=false, msg='';
  const tagCell=g=>g==='양산'?'<span style="color:#1c47a0;font-weight:700">양산</span>':(g==='셀'?'<span style="color:#8a5a1a;font-weight:700">셀</span>':'');
  const pcell=r=>`<b>${esc(r.part)}</b>${r.partnm||r.pnm?' '+esc(r.partnm||r.pnm):''}`;
  // 모드별 컬럼정의 [header, align(l/c/n), render, footKey(qty/st1/st2)]
  const COLS={
    '1':[['파트','l',pcell],['생산일자','c',r=>ymd(r.ymd)],['생산수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['필요ST','n',r=>nf1(r.st),'st1'],['품목수','n',r=>nf(r.items)]],
    '2':[['파트','l',pcell],['도번','l',r=>`<b>${esc(r.item)}</b>`],['품명','l',r=>esc(r.inm)],['생산일자','c',r=>ymd(r.ymd)],['생산수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['필요ST','n',r=>nf1(r.st),'st1'],['구분','c',r=>tagCell(r.gubun)]],
    '7':[['파트코드','l',r=>esc(r.partnm||r.part)],['작업공정','l',r=>esc(((r.swork||'')+' '+(r.partnm||'')).trim())],['품번','l',r=>`<b>${esc(r.item)}</b>`],['수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['공정ST','n',r=>nf2(r.st),'st2'],['작업자','l',r=>esc(r.worker)],['설비','l',r=>esc(r.machnm||r.mach)],['작업시작시각','c',r=>esc(r.sta)],['작업완료시각','c',r=>esc(r.fin)],['바코드번호','c',r=>esc(r.barcode)],['전표번호','c',r=>esc(r.sheet)],['공정SEQ','c',r=>esc(r.proc_seq)],['최종처리자','l',r=>esc(r.u_user)],['최종처리일시','c',r=>esc(r.u_dt)]],
    '5':[['파트','l',pcell],['품번','l',r=>`<b>${esc(r.item)}</b>`],['양산/셀','c',r=>tagCell(r.gubun_tag)],['수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['공정ST','n',r=>nf2(r.st),'st2'],['설비','l',r=>esc(r.machnm||r.mach)],['작업자','l',r=>esc(r.worker)],['작업시작시각','c',r=>esc(r.sta)],['작업완료시각','c',r=>esc(r.fin)],['바코드번호','c',r=>esc(r.barcode)],['Update User','l',r=>esc(r.u_user)],['Update Datetime','c',r=>esc(r.u_dt)],['Update Ip','c',r=>esc(r.u_ip)],['Update Computer','c',r=>esc(r.u_comp)],['Update Window','c',r=>esc(r.u_win)]],
    '6':[['파트','l',pcell],['품번','l',r=>`<b>${esc(r.item)}</b>`],['수량','n',r=>`<b>${nf(r.qty)}</b>`,'qty'],['공정ST','n',r=>nf2(r.st),'st2'],['설비','l',r=>esc(r.machnm||r.mach)],['작업자','l',r=>esc(r.worker)],['작업완료시각','c',r=>esc(r.fin)],['바코드번호','c',r=>esc(r.barcode)],['Update User','l',r=>esc(r.u_user)],['Update Datetime','c',r=>esc(r.u_dt)],['Update Ip','c',r=>esc(r.u_ip)],['Update Computer','c',r=>esc(r.u_comp)],['Update Window','c',r=>esc(r.u_win)]]
  };
  const acItem=(val)=>{clearTimeout(acT);const t=(val||'').trim();if(!t)return;acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);const rows=(await r.json()).rows||[];const dl=c.querySelector('#pt-itemdl');if(dl)dl.innerHTML=rows.slice(0,40).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');}catch(e){}},180);};
  const loadFilters=async()=>{try{const r=await fetch(`${API}/api/partresult/filters`);parts=(await r.json()).parts||[];}catch(e){}};
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,part:F.part,item:F.item,worker:F.worker,gubun:F.gubun});
    try{const r=await fetch(`${API}/api/partresult/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패';data={mode:F.gubun,rows:[],cnt:0,sum_qty:0,sum_st:0};}
    loading=false;draw();};
  const alnCls=a=>a==='n'?'num':(a==='c'?'center':'');
  const alnSty=a=>a==='l'?' style="text-align:left"':'';
  const footVal=k=>k==='qty'?nf(data.sum_qty):(k==='st1'?nf1(data.sum_st):(k==='st2'?nf2(data.sum_st):''));
  const draw=()=>{
    const m=data.mode||F.gubun, cols=COLS[m]||COLS['1'], wide=(m==='7'||m==='5'||m==='6');
    const stLbl=wide?'공정ST':'필요ST', stVal=wide?nf2(data.sum_st):nf1(data.sum_st);
    const partOpts=`<option value="">전체</option>`+parts.map(o=>`<option value="${esc(o.code)}"${F.part===o.code?' selected':''}>${esc(o.name)} (${esc(o.code)})</option>`).join('');
    const gubunOpts=GUBUNS.map(([v,l])=>`<option value="${v}"${F.gubun===v?' selected':''}>${v}:${l}</option>`).join('');
    const head=`<tr>${cols.map(cd=>`<th class="${alnCls(cd[1])}"${alnSty(cd[1])}${wide?' style="white-space:nowrap"':''}>${cd[0]}</th>`).join('')}</tr>`;
    const body=loading?spinRow(cols.length):(data.rows.length?data.rows.map(r=>`<tr>${cols.map(cd=>`<td class="${alnCls(cd[1])}"${alnSty(cd[1])}${wide?' style="white-space:nowrap"':''}>${cd[2](r)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${cols.length}" class="empty">조회 결과 없음</td></tr>`);
    const foot=data.rows.length?`<tfoot><tr class="grandtot">${cols.map((cd,i)=>i===0?`<td class="center" style="white-space:nowrap">합계 ${nf(data.cnt)}건</td>`:(cd[3]?`<td class="num">${footVal(cd[3])}</td>`:`<td></td>`)).join('')}</tr></tfoot>`:'';
    const grid=`<table class="tbl${wide?'':' fit'}" style="font-size:12px"><thead>${head}</thead><tbody>${body}</tbody>${foot}</table>`;
    const desc={'1':'파트별 일별 집계','2':'파트·도번별 상세','7':'바코드실적처리(공정단위)','5':'가간판(가상설비 GP)','6':'스티커(실설비 00)'}[m]||'';
    const src=wide?'PR_T_PROD_DTL_STICKER + WELD_SHEET_DTL(공정ST)':'PROC(조립) ∪ STICKER(용접) ∪ CUTTING(가공)';
    c.innerHTML=`
     <div class="page-title">📈 파트별 생산실적현황 <span style="font-size:12px;color:var(--muted);font-weight:400">${desc} · 레거시 w_pr_list_090</span></div>
     <div class="page-sub">${wide?'공정ST'+(m==='7'?'=TOT_ST×수량':'=TOT_ST×수량/60')+' · 바코드단위 공정실적':'생산수량=Σ·필요ST=Σ(파트별 공정ST×수량)/60'+(m==='2'?'':'·품목수=품목종수')+' · 필요ST 합계=시간(Σ분/60)'}. 🟢 nx · 원본 <code>${src}</code></div>
     <div class="toolbar">
       <label class="tl">생산기간</label><input class="inp" type="date" id="pt-from" value="${F.from}" style="width:130px"> ~ <input class="inp" type="date" id="pt-to" value="${F.to}" style="width:130px">
       <label class="tl">도번</label><input class="inp" id="pt-item" list="pt-itemdl" autocomplete="off" value="${esc(F.item)}" style="width:110px;text-transform:uppercase"><datalist id="pt-itemdl"></datalist>
       <label class="tl">파트</label><select class="inp" id="pt-part" style="width:140px">${partOpts}</select>
       <label class="tl">작업자</label><input class="inp" id="pt-worker" value="${esc(F.worker)}" style="width:72px">
       <label class="tl">조회종류</label><select class="inp" id="pt-gubun" style="width:172px">${gubunOpts}</select>
       <button class="btn" id="pt-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${nf(data.cnt)}건 · 생산수량 <b>${nf(data.sum_qty)}</b> · ${stLbl} <b>${stVal}</b></span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${grid}</div>`;
    const g=id=>c.querySelector(id);
    g('#pt-search').onclick=()=>{F.from=g('#pt-from').value;F.to=g('#pt-to').value;F.part=g('#pt-part').value;F.item=g('#pt-item').value;F.worker=g('#pt-worker').value;F.gubun=g('#pt-gubun').value;load();};
    g('#pt-item').oninput=e=>acItem(e.target.value);
    ['#pt-item','#pt-worker'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#pt-search').click();});
    ['#pt-part','#pt-gubun'].forEach(id=>g(id).onchange=()=>g('#pt-search').click());
  };
  (async()=>{await loadFilters();load();})();
};

/* ===== 생산 ⑦: 생산파트재고조정 (w_pr_stock_470) — PR_T_STOCK_MAINT_MAT tag2 ===== */
/* ===== 생산 쓰기화면 공용 CRUD 패널 (nx 미러: 등록/수정/삭제) =====
   cfg: {listEp,saveEp,delEp,days,dateLabel,filters[],buildQS,cols[],form[],newRow,fromRow,toBody,sum} */

/* ★파트 드롭다운 옵션 — 쓰기화면의 파트칸은 자유입력 금지(§3 코드 직접입력칸 금지).
   자유입력으로 두면 파트명('04라인')이 PART_CODE 에 저장돼 실제 파트(S4)에 재고가
   안 쌓인다(2026-08-25 실사고: SUB6 조정 500개가 유실 → 520 차감이 재고 0 판정).
   배열 객체를 그대로 form 설정에 넘기고 로드 후 내용을 채운다(fld()가 렌더시점에 읽음). */
const _WR_PARTS=[{v:'',t:'(없음)'}];
let _wrPartsLoaded=false;
const wrLoadParts=async()=>{if(_wrPartsLoaded)return;_wrPartsLoaded=true;
  try{const r=await fetch(`${API_BASE}/api/wr/parts`);const j=await r.json();
    (j.rows||[]).forEach(p=>_WR_PARTS.push({v:p.code,t:p.nm?`${p.nm} (${p.code})`:p.code}));}
  catch(e){_wrPartsLoaded=false;}};

/* ===== 생산 ⑦: 생산파트재고조정 (w_pr_stock_470) — 라이브 조회 + nx.stock_maint 등록/수정/삭제 ===== */
SCREEN.partstockadj=(c)=>{
  wrLoadParts();
  wrShell(c,{sid:'partstockadj', nxOnly:true,
    title:`🛠️ 생산파트재고조정 <span style="font-size:12px;color:var(--muted);font-weight:400">자재개별재고조정(등록·수정·삭제)</span>`,
    sub:`파트재고 장부수정(조정, ±). 조회=📁미러이력(<code>PR_T_STOCK_MAINT_MAT</code> 재고조정)∪웹편집(<code>nx.stock_ledger</code> PRD). 레거시 라이브 없음(컷오버).`,
    cfg:{
      listEp:'/api/stockmaint/list', saveEp:'/api/stockmaint/save', delEp:'/api/stockmaint/delete',
      dateLabel:'수정기간', filters:[{k:'tag',label:'구분',width:50},{k:'mat',label:'자재',width:120},{k:'wc',label:'작업처',width:60}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,tag:F.tag||'',mat:F.mat||'',wc:F.wc||''}),
      sum:d=>`조정수량합 <b>${_wnf(d.sum_qty)}</b>`,
      cols:[
        {h:'조정일자',cls:'center',fmt:r=>_wymd(r.MAINT_YMD)},
        {h:'구분',k:'tag_nm',cls:'center'},
        {h:'작업처',k:'work_code',cls:'center'},
        {h:'파트',cls:'center',fmt:r=>{const p=(r.part_code||'').trim();if(!p)return '';
          const o=_WR_PARTS.find(x=>x.v===p);return o?esc(o.t):`<span style="color:#c0392b" title="파트마스터에 없는 코드">${esc(p)} ⚠</span>`;}},
        {h:'자재',fmt:r=>`<b>${esc(r.mat_code)}</b>`},
        {h:'품명',k:'mat_nm',cap:1,title:'mat_nm'},
        {h:'도번',k:'item_code'},
        {h:'조정수량',cls:'num',fmt:r=>`<span style="color:${r.MAINT_QTY<0?'#c0392b':'#1c7c3a'}">${_wnf(r.MAINT_QTY)}</span>`},
        {h:'단가',cls:'num',fmt:r=>_wnf(r.MAINT_COST)},
        {h:'금액',cls:'num',fmt:r=>_wnf(r.MAINT_AMT)},
        {h:'비고',k:'remarks',cap:1,title:'remarks'},
        {h:'작업자',k:'usr'},
        {h:'작업일시',k:'INSERT_DATETIME',cls:'center'},
      ],
      form:[
        {k:'maint_ymd',label:'조정일자',type:'date',required:1,width:140},
        {k:'maint_tag',label:'구분',type:'select',opts:[{v:'2',t:'재고조정'},{v:'1',t:'불량'},{v:'4',t:'기타'}],width:100},
        {k:'work_code',label:'작업처',width:60},
        {k:'part_code',label:'파트',type:'select',opts:_WR_PARTS,width:120},
        {k:'mat_code',label:'자재',required:1,search:1,width:160},{k:'item_code',label:'도번',search:1,width:140},
        {k:'maint_qty',label:'조정수량',type:'num',width:90},{k:'maint_cost',label:'단가',type:'num',width:90},
        {k:'prod_work_code',label:'생산작업장',width:70},{k:'remarks',label:'비고',width:200},
      ],
      newRow:F=>({id:null,maint_ymd:F.to,maint_tag:'2',work_code:'',part_code:'',mat_code:'',item_code:'',maint_qty:'',maint_cost:'',prod_work_code:'',remarks:''}),
      fromRow:r=>({id:r.ID,maint_ymd:_y6(r.MAINT_YMD),maint_tag:r.tag,work_code:r.work_code,part_code:r.part_code,mat_code:r.mat_code,item_code:r.item_code,maint_qty:r.MAINT_QTY,maint_cost:r.MAINT_COST,prod_work_code:r.prod_work_code,remarks:r.remarks}),
      toBody:f=>({id:f.id,maint_ymd:f.maint_ymd,maint_tag:f.maint_tag,work_code:f.work_code,part_code:f.part_code,mat_code:f.mat_code,item_code:f.item_code,maint_qty:f.maint_qty,maint_cost:f.maint_cost,prod_work_code:f.prod_work_code,remarks:f.remarks,user:'웹사용자'}),
    }
  });
};

/* ===== 생산 ⑧: 생산자재출고관리 (w_pr_stock_150) — PR_T_STOCK_MAINT_MAT 창고이동/출고 ===== */
SCREEN.partissue=(c)=>{
  wrShell(c,{sid:'partissue', nxOnly:true,
    title:`📤 생산자재출고관리 <span style="font-size:12px;color:var(--muted);font-weight:400">자재출고(창고간 이동, 등록·수정·삭제)</span>`,
    sub:`파트 창고간 이동(FROM파트→TO파트, net-0). 조회=📁미러이력(<code>PR_T_STOCK_MAINT_MAT</code> 창고이동)∪웹편집(<code>nx.stock_ledger</code> MV). 레거시 라이브 없음(컷오버).`,
    default:'edit',
    live:(body)=>wrLiveLedger(body,'issue'),
    cfg:{
      listEp:'/api/matissue/list', saveEp:'/api/matissue/save', delEp:'/api/matissue/delete',
      dateLabel:'출고기간', filters:[{k:'mat',label:'자재',width:120},{k:'frompart',label:'FROM파트',width:70},{k:'topart',label:'TO파트',width:70}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,mat:F.mat||'',frompart:F.frompart||'',topart:F.topart||''}),
      sum:d=>`출고수량합 <b>${_wnf(d.sum_qty)}</b>`,
      cols:[
        {h:'출고일자',cls:'center',fmt:r=>_wymd(r.ISSUE_YMD)},
        {h:'FROM파트',k:'frompart',cls:'center'},
        {h:'TO파트',k:'topart',cls:'center'},
        {h:'작업처',k:'work_code',cls:'center'},
        {h:'자재',fmt:r=>`<b>${esc(r.mat_code)}</b>`},
        {h:'품명',k:'mat_nm',cap:1,title:'mat_nm'},
        {h:'도번',k:'item_code'},
        {h:'출고수량',cls:'num',fmt:r=>`<b>${_wnf(r.ISSUE_QTY)}</b>`},
        {h:'비고',k:'remarks',cap:1,title:'remarks'},
        {h:'작업자',k:'usr'},
        {h:'작업일시',k:'INSERT_DATETIME',cls:'center'},
      ],
      form:[
        {k:'issue_ymd',label:'출고일자',type:'date',required:1,width:140},
        {k:'from_part_code',label:'FROM파트',width:70},{k:'part_code',label:'TO파트',width:70},{k:'work_code',label:'작업처',width:60},
        {k:'mat_code',label:'자재',required:1,search:1,width:160},{k:'item_code',label:'도번',search:1,width:140},
        {k:'issue_qty',label:'출고수량',type:'num',width:100},{k:'remarks',label:'비고',width:220},
      ],
      newRow:F=>({id:null,issue_ymd:F.to,from_part_code:'',part_code:'',work_code:'',mat_code:'',item_code:'',issue_qty:'',remarks:''}),
      fromRow:r=>({id:r.ID,issue_ymd:_y6(r.ISSUE_YMD),from_part_code:r.frompart,part_code:r.topart,work_code:r.work_code,mat_code:r.mat_code,item_code:r.item_code,issue_qty:r.ISSUE_QTY,remarks:r.remarks}),
      toBody:f=>({id:f.id,issue_ymd:f.issue_ymd,from_part_code:f.from_part_code,part_code:f.part_code,work_code:f.work_code,mat_code:f.mat_code,item_code:f.item_code,issue_qty:f.issue_qty,remarks:f.remarks,user:'웹사용자'}),
    }
  });
};

/* ===== 생산계획추가입력 CRUD (nx.prod_plan_input ← PR_T_PLAN_INPUT) — 수동 추가 생산계획 ===== */
SCREEN.planinput=(host)=>{
  const API=API_BASE;
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const ymd6=d=>{ if(!d) return ''; const p=d.split('-'); return p[0].slice(2)+p[1]+p[2]; };  // yyyy-mm-dd → YYMMDD
  const shift=(d,n)=>{ const t=new Date(d+'T00:00:00'); t.setDate(t.getDate()+n); return iso(t); };
  const hmfmt=v=>{ const s=String(v||'').trim(); return /^\d{4}$/.test(s)?s.slice(0,2)+':'+s.slice(2):s; };  // HHMM→HH:MM
  // 엑셀 날짜 → YYMMDD(6). "2026-08-05","26/8/5","260805","20260805" 모두 흡수. 미인식시 원문 유지.
  const ymdNorm=v=>{ let s=String(v==null?'':v).replace(/[^\d]/g,''); if(s.length===8)s=s.slice(2); return /^\d{6}$/.test(s)?s:String(v==null?'':v).trim(); };
  const st={mx:{dates:[],rows:[],grandtot:{},total:0,cnt:0,note:''},q:'',line:'',base:iso(new Date()),
            prevDay:false,lines:[],form:null,bulk:null,sel:new Set(),msg:''};
  /* ★수정 팝업 필드(2026-09-02 사용자 확정)
       · 계획일자 = 달력(date) — 날짜 이동이 잦다(UI표준 §3)
       · 제번 = **읽기전용** — 저장 시 자동채번된 값이라 고치면 안 된다
       · 공정·생산구분 = 제거(기본값 고정)
       · 비고 = 넓게(wide) */
  const F=[['plan_ymd','계획일자','date'],['line_no','라인','req'],['item_code','품번','req'],
    ['output_hm','산출시각','time'],['plan_qty','계획수량','num'],['work_order','제번','ro'],
    ['remarks','비고','wide']];
  // HHMM ↔ HH:MM (time input 왕복용). 내부 저장은 계속 HHMM 4자리.
  const hm2t=s=>/^\d{4}$/.test(String(s||''))?`${s.slice(0,2)}:${s.slice(2)}`:'';
  const t2hm=s=>String(s||'').replace(/[^\d]/g,'').slice(0,4);
  // 라인 표기 = "코드 명칭"(레거시 dddw 형식). 명칭 없거나 코드=명칭이면 코드만.
  const lineLabel=l=>{ const c=String(l.code),n=String(l.nm||'').trim(); return (n&&n!==c)?`${c} ${n}`:c; };
  const lineNm=code=>{ const l=st.lines.find(x=>String(x.code)===String(code)); return l?lineLabel(l):(code||''); };
  // 라인 select 폭 = 표기 글자폭(UI규칙, 한글 폭 보정 1.7ch)
  const lineW=()=>{ const w=Math.max(6,...st.lines.map(l=>{const s=lineLabel(l);return [...s].reduce((a,ch)=>a+(ch.charCodeAt(0)>0x2000?1.7:1),0);})); return (w+3).toFixed(0)+'ch'; };
  const lineOpts=(sel,all)=>(all?`<option value=""${sel?'':' selected'}>전체</option>`:'')+
    st.lines.map(l=>`<option value="${esc(l.code)}"${String(sel)===String(l.code)?' selected':''}>${esc(lineLabel(l))}</option>`).join('');
  const loadLines=async()=>{ try{const r=await fetch(`${API}/api/planinput/lines`);const j=await r.json();st.lines=j.rows||[];}catch(e){st.lines=[];} };
  const load=async()=>{
    // 전일기준(prevDay): 시작일=OFF 기준일 / ON 전일(기준일−1). 기준일부터 forward 4주 매트릭스.
    const qs=new URLSearchParams({base:ymd6(st.base),prevday:st.prevDay?1:0,days:28,q:st.q,line:st.line});
    try{const r=await fetch(`${API}/api/planinput/matrix?${qs}`);const j=await r.json();
      st.mx=(j&&j.dates)?j:{dates:[],rows:[],grandtot:{},total:0,cnt:0,note:''};st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.mx={dates:[],rows:[],grandtot:{},total:0,cnt:0,note:''};}
    st.sel.clear();render();
  };
  // ── 수정 모달(기존 레코드 단건) ──
  const editHtml=(f)=>`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
     <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:600px;max-width:96vw">
       <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
         <b>생산계획 수정</b><span id="pi-x" style="cursor:pointer;font-size:17px">✕</span></div>
       <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
         <table style="border-collapse:collapse;width:100%"><tbody>${F.map(fd=>`<tr>
           <td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:110px">${fd[1]}${(fd[2]==='req'||fd[2]==='date')?'<span style="color:#c0392b">*</span>':''}</td>
           <td style="padding:4px 0">${
              fd[0]==='line_no'
              ?`<select class="inp pf" data-k="line_no" style="width:${lineW()}">${lineOpts(f.line_no,false)}</select>`
              :fd[2]==='date'
              ?`<input class="inp pf" data-k="plan_ymd" type="date" value="${esc(ymd2iso(f.plan_ymd))}" style="width:150px">`
              :fd[2]==='time'
              /* ★2100 → 21:00 로 보이게(네이티브 시계 피커). 저장값은 HHMM 유지 */
              ?`<input class="inp pf" data-k="output_hm" type="time" value="${esc(hm2t(f.output_hm))}" style="width:120px">`
              :fd[2]==='ro'
              /* ★제번은 자동채번 값 — 읽기전용(고치면 계획 추적이 끊긴다) */
              ?`<input class="inp" value="${esc(f[fd[0]]||'')}" readonly style="width:200px;background:#f2f5f9;color:#5b6b80" title="저장 시 자동채번된 값이라 수정할 수 없습니다">`
              :`<input class="inp pf" data-k="${fd[0]}" value="${esc(f[fd[0]]||'')}" ${fd[2]==='num'?'type="number"':''} style="width:${fd[2]==='num'?100:(fd[2]==='wide'?420:200)}px;max-width:100%" autocomplete="off">`}</td></tr>`).join('')}
           ${(f.ins_user||f.upd_user)?`<tr><td style="padding:5px 8px 5px 0;text-align:right;color:#8aa0bd;font-size:11px">기록</td>
             <td style="padding:4px 0;color:#8aa0bd;font-size:11px">${f.ins_user?`등록 ${esc(f.ins_user)}${f.ins_dt?` (${esc(String(f.ins_dt).slice(0,16))})`:''}`:''}${(f.ins_user&&f.upd_user)?' · ':''}${f.upd_user?`수정 ${esc(f.upd_user)}${f.upd_dt?` (${esc(String(f.upd_dt).slice(0,16))})`:''}`:''}</td></tr>`:''}
         </tbody></table>
       </div>
       <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
         <span style="color:#c0392b;font-size:11px">* 계획일자·라인·품번·수량 필수. 시각은 HHMM. 제번은 자동채번(수정 불가).</span>
         <span><button class="btn" id="pi-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="pi-cancel">닫기</button></span></div>
     </div></div>`;
  const render=()=>{
    const editing=st.form!==null, f=st.form||{}, bulking=st.bulk!==null;
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('planinput'):true;
    const D=st.mx.dates||[], R=st.mx.rows||[], G=st.mx.grandtot||{};
    const wke=wd=>wd===5?'color:#1b6ec2':(wd===6?'color:#c0392b':'');  // 토 파랑 / 일 빨강
    const dhead=D.map(d=>`<th class="num" style="min-width:36px;${wke(d.wd)}" title="${esc(d.ymd)}">${esc(d.mmdd)}<br><span style="font-size:9px">${esc(d.dow)}</span></th>`).join('');
    host.innerHTML=`
     <div class="page-title">➕ 생산계획추가입력 <span style="font-size:12px;color:var(--muted);font-weight:400">일자별 계획 매트릭스 · nx.prod_plan_input(레거시 PR_T_PLAN_INPUT 이관본)</span></div>
     <div class="page-sub">레거시 <code>w_pr_plan_060 / dw_pr_plan_060_1</code> 재현. 좌측 고정컬럼 + <b>기준일부터 4주</b> 일자매트릭스(기준일=첫 일자컬럼, 셀=계획수량, 하단 일자합계). 추가는 <b>엑셀 붙여넣기</b>. <span style="color:#c0392b">대체·출하수량은 원천 미보유(공란)</span>.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">기준일자</label>
       <button class="btn" id="pi-prevd" title="전일" style="padding:1px 8px">◀</button>
       <input class="inp" type="date" id="pi-base" value="${st.base}">
       <button class="btn" id="pi-nextd" title="익일" style="padding:1px 8px">▶</button>
       <label class="tl" style="margin-left:6px"><input type="checkbox" id="pi-prev" ${st.prevDay?'checked':''}> 전일기준</label>
       <label class="tl">라인</label><select class="inp" id="pi-line" style="width:${lineW()}">${lineOpts(st.line,true)}</select>
       <label class="tl">검색</label><input class="inp" id="pi-q" value="${esc(st.q)}" placeholder="품번/제번" style="width:140px" autocomplete="off">
       <button class="btn" id="pi-search">🔍 조회</button>
       ${ed?`<button class="btn" id="pi-add" style="background:#1c7c3a;color:#fff">➕ 추가(엑셀붙여넣기)</button>
       <button class="btn" id="pi-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.mx.cnt||0)}행 · 합계 ${won(st.mx.total||0)}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?editHtml(f):''}
     ${bulking?bulkHtml():''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th style="width:24px"></th>
        <th>WORK-ORDER</th><th>작업처</th><th>양산/셀</th><th>라인</th><th>품번</th><th>품명</th><th>품목구분</th>
        <th class="num">생산수량</th><th class="num" title="원천 미보유(가정 공란)">대체수량</th><th class="num" title="원천 미보유(가정 공란)">출하수량</th><th class="num">시간</th>
        ${dhead}</tr></thead>
      <tbody>${R.length?R.map((r,i)=>{
        const cells=D.map(d=>{const c=r.cells[d.ymd];const q=c?c.qty:0;
          return `<td class="num" style="${wke(d.wd)}${q>0?';cursor:pointer;background:#eef5ff':''}" ${(q>0&&ed)?`data-edit="${c.recs[0].ppi_id}" title="클릭:수정"`:''}>${q>0?won(q):''}</td>`;}).join('');
        return `<tr>
        <td class="center">${ed?`<input type="checkbox" class="pi-chk" data-idx="${i}" ${st.sel.has(i)?'checked':''}>`:''}</td>
        <td>${esc(r.work_order)}</td><td>${esc(r.work_nm)}</td><td class="center">${esc(r.prod_nm)}</td>
        <td class="center" title="${esc(lineNm(r.line_no))}">${esc(lineNm(r.line_no))}</td><td><b>${esc(r.item_code)}</b></td>
        <td class="cap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td>${esc(r.item_type)}</td>
        <td class="num"><b>${won(r.total||0)}</b></td><td class="num" style="color:#b8c2cf"></td><td class="num" style="color:#b8c2cf"></td>
        <td class="num">${esc(hmfmt(r.output_hm))}</td>
        ${cells}</tr>`;}).join(''):`<tr><td colspan="${12+D.length}" class="empty">조회 결과 없음${ed?' (➕추가로 등록)':''}</td></tr>`}</tbody>
      ${R.length?`<tfoot><tr style="position:sticky;bottom:0;background:#f0f4fa;font-weight:700">
        <td></td><td colspan="7" style="text-align:right">일자별 합계 ▶</td>
        <td class="num">${won(st.mx.total||0)}</td><td></td><td></td><td></td>
        ${D.map(d=>`<td class="num" style="${wke(d.wd)}">${G[d.ymd]?won(G[d.ymd]):''}</td>`).join('')}</tr></tfoot>`:''}
      </table></div>`;
    const g=id=>host.querySelector(id);
    g('#pi-prevd').onclick=()=>{st.base=shift(st.base,-1);load();};
    g('#pi-nextd').onclick=()=>{st.base=shift(st.base,1);load();};
    g('#pi-base').onchange=()=>{st.base=g('#pi-base').value||st.base;load();};
    g('#pi-prev').onchange=()=>{st.prevDay=g('#pi-prev').checked;load();};
    g('#pi-search').onclick=()=>{st.q=g('#pi-q').value;st.line=g('#pi-line').value;load();};
    g('#pi-line').onchange=()=>{st.line=g('#pi-line').value;load();};
    g('#pi-q').onkeyup=e=>{if(e.key==='Enter')g('#pi-search').click();};
    if(ed){
      g('#pi-add').onclick=async()=>{ if(!st.lines.length)await loadLines();   // 라인 드롭다운 보장(로드 실패/레이스 방어)
        const _y0=ymd6(st.base);
        // 행의 일자는 비워 둔다 — 상단 계획일자를 바꾸면 그 값이 그대로 반영된다(2026-09-03)
        st.bulk={plan_ymd:_y0,line_no:st.line||(st.lines[0]&&st.lines[0].code)||'',output_hm:'2100',prod_tag:'1',work_code:'',rows:blankRows(10)};render();};
      g('#pi-del').onclick=()=>del();
      host.querySelectorAll('.pi-chk').forEach(ch=>ch.onclick=()=>{const i=+ch.dataset.idx;ch.checked?st.sel.add(i):st.sel.delete(i);});
      host.querySelectorAll('[data-edit]').forEach(td=>td.onclick=()=>editCell(+td.dataset.edit));
    }
    attachResizers(host);
    if(editing){
      g('#pi-cancel').onclick=g('#pi-x').onclick=()=>{st.form=null;render();};
      g('#pi-save').onclick=save;
      // ★date/time 입력은 내부포맷(YYMMDD·HHMM)으로 되돌려 저장한다
      host.querySelectorAll('.pf').forEach(el=>{
        const k=el.dataset.k, t=el.type;
        const h=()=>{ st.form[k] = t==='date'?ymd6(el.value) : (t==='time'?t2hm(el.value) : el.value); };
        el.oninput=h; el.onchange=h;
      });
    }
    if(bulking) wireBulk();
  };
  // ── 셀 클릭 수정(단건 레코드 프리필) ──
  const editCell=async(ppi_id)=>{
    try{const r=await fetch(`${API}/api/planinput/get?ppi_id=${ppi_id}`);const j=await r.json();
      if(j&&j.ppi_id){st.form=j;render();}else alert('행 조회 실패');}
    catch(e){alert('행 조회 오류: '+e);}
  };
  // ── 엑셀 붙여넣기 일괄추가 ──
  /* ★신규행 기본값(2026-08-31 사용자 확정)
       · 계획일자 = **기본 계획일자로 미리 채운다**(빈칸 아님). 그 자리에서 고칠 수도 있고
         엑셀 날짜열을 붙여넣으면 덮어쓴다. 종전엔 전부 빈칸이라 매번 입력해야 했다.
       · 제번(work_order) = **입력칸 없음** — 저장할 때 백엔드가 자동채번한다
         (레거시 w_pr_plan_060 도 신규행 WORK-ORDER 칸이 비어 있고 저장 시 채워진다). */
  /* ★새 행의 계획일자는 **비워 둔다**(2026-09-03 교정).
       종전엔 만들 때의 기본일자를 박아 넣었다. 그러면 사용자가 나중에 상단 계획일자를 바꿔도
       이미 만들어진 행은 **옛 날짜를 그대로 들고 있어** 그 값으로 저장된다
       (실제 증상: 9/5 로 고쳤는데 모달을 열 때의 당일 9/3 으로 저장됨).
       비워 두면 저장 시 eff() 가 상단 기본일자를 쓰므로 늘 최신 값이 반영된다.
       행마다 다른 날짜가 필요하면 그 행의 달력에서 직접 고르면 된다(그 값이 우선). */
  const blankRows=(n)=>Array.from({length:n},()=>({plan_ymd:'',item_code:'',plan_qty:'',remarks:''}));
  // YYMMDD ↔ yyyy-mm-dd (달력 input 왕복용)
  const ymd2iso=s=>/^\d{6}$/.test(String(s||''))?`20${s.slice(0,2)}-${s.slice(2,4)}-${s.slice(4,6)}`:'';
  /* ★품번 오토컴플리트(2026-09-02) — 입력한 글자로 서버검색해 datalist 를 채운다.
       전 품목을 미리 받지 않는다(수만 건). 200ms 디바운스 + 같은 질의 재요청 안 함. */
  let _bsT=null, _bsQ='';
  const bulkSearch=(q)=>{
    q=String(q||'').trim(); if(q.length<2||q===_bsQ)return;
    clearTimeout(_bsT);
    _bsT=setTimeout(async()=>{ _bsQ=q;
      try{const r=await fetch(`${API}/api/itemmaster/list?q=${encodeURIComponent(q)}&limit=50`);
        const j=await r.json();
        st.bulkItems=(j.rows||[]).map(x=>({code:String(x.item_code||'').trim(),
                                           name:String(x.item_name||'').trim()})).filter(x=>x.code);
        const dl=host.querySelector('#pb-itemdl');
        if(dl)dl.innerHTML=st.bulkItems.map(x=>`<option value="${esc(x.code)}">${esc(x.name)}</option>`).join('');
      }catch(e){}
    },200);
  };
  // 붙여넣기 직후: 화면의 품번들 품명을 한 번에 조회해 채운다
  const fillNames=async()=>{ const b=st.bulk; if(!b)return;
    const codes=[...new Set(b.rows.map(r=>String(r.item_code||'').trim().toUpperCase()).filter(Boolean))];
    if(!codes.length)return;
    try{const r=await fetch(`${API}/api/planinput/itemnames`,{method:'POST',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({codes})});
      const j=await r.json(); const m=j.names||{};
      b.rows.forEach(x=>{x.item_name=m[String(x.item_code||'').trim().toUpperCase()]||'';});
      render();
    }catch(e){}
  };
  const bulkHtml=()=>{ const b=st.bulk;
    return `<div class="wr-modal" style="position:fixed;inset:0;z-index:120;background:rgba(20,30,50,.42);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:18px 10px">
     <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.34);width:1060px;max-width:94vw">
       <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c7c3a;color:#fff;border-radius:10px 10px 0 0">
         <b>➕ 생산계획 추가 — 엑셀 붙여넣기(날짜·품번·수량)</b><span id="pb-x" style="cursor:pointer;font-size:17px">✕</span></div>
       <div style="padding:12px 16px">
         <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:8px;font-size:12px">
           <!-- ★계획일자 = 네이티브 달력(UI표준 §3 "모든 일자 입력은 type=date").
                내부포맷 YYMMDD 는 ymd6/iso 헬퍼로 왕복한다. 전 행이 이 일자로 편성된다. -->
           <label class="tl">계획일자</label><input class="inp" type="date" id="pb-ymd" value="${esc(ymd2iso(b.plan_ymd))}" style="width:150px" title="기본 계획일자 — 행에 일자가 비어 있으면 이 값으로 저장됩니다(행별 일자가 우선)">
           <label class="tl">라인</label><select class="inp" id="pb-line" style="width:${lineW()}">${lineOpts(b.line_no,false)}</select>
           <!-- ★산출시각 5ch 는 '2100'이 잘렸다 → 7ch (2026-09-02) -->
           <label class="tl">산출시각</label><input class="inp" id="pb-hm" value="${esc(b.output_hm)}" placeholder="HHMM" style="width:7ch;min-width:0;flex:none;text-align:center" autocomplete="off">
           <!-- ★생산구분(1양산)·공정은 기본값 고정이라 화면에서 뺐다(2026-09-02 사용자 요청).
                값은 st.bulk 에 그대로 남아 저장 시 함께 전송된다. -->
         </div>
         <div style="font-size:11px;color:#1c7c3a;margin-bottom:6px">💡 엑셀에서 <b>계획일자⇥품번⇥수량⇥비고</b> 열을 복사해 <b>계획일자 칸</b>에 붙여넣으면 여러 행에 자동 분배됩니다. (품번만 / 품번⇥수량 도 가능 — 그 경우 품번 칸에 붙여넣기)<br>
           행별 <b>계획일자</b>는 달력으로 골라도 되고, <b>비우면 위의 기본 계획일자</b>로 저장됩니다. <b>제번(WORK-ORDER)은 저장 시 자동 생성</b>됩니다.</div>
         <div style="max-height:calc(100vh - 330px);overflow-y:auto;overflow-x:hidden;border:1px solid #d7dfea;border-radius:6px">
           <!-- ★행별 계획일자 열 **복원**(2026-09-03 사용자 요청 — "계획일자도 선택 또는 붙여넣을 수 있게").
                경위: 2026-09-02 에 열만 지웠는데 저장 로직(eff/base6)은 그대로 남아 있었다.
                      그래서 행마다 다른 날짜로 편성할 방법이 없었다.
                · 날짜칸은 UI표준 §3 대로 <input type="date">(달력 피커)
                · 엑셀에서 「날짜⇥품번⇥수량」을 붙여넣으면 이 칸부터 자동 분배된다(pbPaste 의 fields 순서)
                정렬·폭: 헤더 가운데(UI표준) · 품번 오토컴플리트 -->
           <table class="tbl" style="font-size:11px;width:100%;table-layout:fixed"><thead><tr>
             <!-- ★제번 열 제거(2026-08-31) — 저장 시 자동채번(WO+7자리연번+라인). 레거시 동일. -->
             <th style="width:34px;text-align:center">#</th>
             <th style="width:132px;text-align:center">계획일자 <span style="color:#1c7c3a">(비우면 상단일자)</span></th>
             <th style="text-align:center">품번 <span style="color:#1c7c3a">(붙여넣기·검색)</span></th>
             <th style="width:180px;text-align:center">품명</th>
             <th style="width:100px;text-align:center">계획수량</th>
             <th style="text-align:center">비고</th>
             <th style="width:30px"></th></tr></thead>
           <tbody>${b.rows.map((r,i)=>`<tr>
             <td class="center" style="color:#8aa0bd">${i+1}</td>
             <td><input class="inp pb-ymd" data-i="${i}" type="date" value="${esc(ymd2iso(r.plan_ymd))}" style="width:100%;min-width:0" title="비우면 상단 계획일자로 저장됩니다"></td>
             <td><input class="inp pb-item" data-i="${i}" value="${esc(r.item_code)}" list="pb-itemdl" style="width:100%;min-width:0" autocomplete="off" placeholder="품번 입력·검색"></td>
             <td class="pb-nm" data-i="${i}" style="color:#5b6b80;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.item_name||'')}">${esc(r.item_name||'')}</td>
             <td><input class="inp pb-qty" data-i="${i}" value="${esc(r.plan_qty)}" type="number" style="width:100%;min-width:0;text-align:right" autocomplete="off"></td>
             <td><input class="inp pb-rm" data-i="${i}" value="${esc(r.remarks)}" style="width:100%;min-width:0" autocomplete="off"></td>
             <td class="center"><span class="pb-rmrow" data-i="${i}" style="cursor:pointer;color:#c0392b" title="행삭제">✕</span></td></tr>`).join('')}</tbody></table>
           <datalist id="pb-itemdl">${(st.bulkItems||[]).map(x=>`<option value="${esc(x.code)}">${esc(x.name)}</option>`).join('')}</datalist>
         </div>
         <div style="margin-top:6px"><button class="btn" id="pb-addrow">＋ 행추가(5)</button>
           <span style="color:#8aa0bd;font-size:11px;margin-left:8px">품번·수량(>0)·계획일자 있는 행만 저장됩니다.</span></div>
       </div>
       <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
         <span style="color:#c0392b;font-size:11px">* 라인·시각 공통 적용. 각 행 품번·수량 필수. 계획일자=행별 우선(비면 기본일자). 제번은 자동채번(WO+연번+라인).</span>
         <span><button class="btn" id="pb-save" style="background:#1c7c3a;color:#fff">💾 일괄저장</button> <button class="btn" id="pb-cancel">닫기</button></span></div>
     </div></div>`;
  };
  // 다열 붙여넣기 자동분배: start행부터 fields 순서대로 셀 매핑(부족 행은 추가). 날짜=정규화·수량=숫자만.
  const applyPaste=(b,start,txt,fields)=>{
    const lines=txt.replace(/\r/g,'').split('\n');
    while(lines.length&&lines[lines.length-1]==='')lines.pop();  // 꼬리 빈줄 제거
    lines.forEach((ln,k)=>{
      const cells=ln.split('\t'), ri=start+k;
      // 일자는 비워 둔다 — 붙여넣기 값이 있으면 아래에서 채워지고, 없으면 상단 기본일자가 쓰인다
      while(b.rows.length<=ri)b.rows.push({plan_ymd:'',item_code:'',plan_qty:'',remarks:''});
      fields.forEach((f,ci)=>{
        if(ci>=cells.length)return;
        let v=(cells[ci]||'').trim(); if(v==='')return;
        if(f==='plan_ymd')v=ymdNorm(v); else if(f==='plan_qty')v=v.replace(/[^\d.\-]/g,'').trim();
        b.rows[ri][f]=v;
      });
    });
  };
  const wireBulk=()=>{ const g=id=>host.querySelector(id), b=st.bulk;
    g('#pb-x').onclick=g('#pb-cancel').onclick=()=>{st.bulk=null;render();};
    g('#pb-save').onclick=bulkSave;
    /* ★달력(type=date) → 내부포맷 YYMMDD 로 저장.
       ⚠oninput 도 함께 건다 — onchange 만 있으면 키보드로 직접 입력한 뒤
         포커스를 잃지 않고 바로 [일괄저장]을 누를 때 값이 반영되지 않는다
         (실제 증상: 9/5 로 고쳤는데 당일 9/3 으로 저장). */
    { const e0=g('#pb-ymd');
      if(e0){ e0.onchange=e0.oninput=e=>{b.plan_ymd=ymd6(e.target.value);}; } }
    g('#pb-line').onchange=e=>b.line_no=e.target.value;
    g('#pb-hm').oninput=e=>b.output_hm=e.target.value;
    /* ★행별 계획일자 칸(2026-09-03 복원) — 달력 선택 + 엑셀 붙여넣기 둘 다 지원.
         붙여넣기는 이 칸부터 [날짜⇥품번⇥수량⇥비고] 순으로 자동 분배된다. */
    host.querySelectorAll('.pb-ymd').forEach(el=>{
      el.onchange=el.oninput=e=>{
        const i=+e.target.dataset.i;
        b.rows[i].plan_ymd=ymd6(e.target.value);      // 빈 값이면 '' → 저장 시 상단일자 사용
      };
      el.onpaste=e=>{
        const txt=(e.clipboardData||window.clipboardData).getData('text');
        if(!/[\n\t]/.test(txt))return;                // 단일값이면 브라우저 기본 처리
        e.preventDefault();
        applyPaste(b, +e.target.dataset.i, txt, ['plan_ymd','item_code','plan_qty','remarks']);
        render(); fillNames();
      };
    });
    // ★생산구분·공정 입력칸은 제거됨(기본값 고정) — 없는 노드에 핸들러를 걸면 죽는다.
    //   값은 st.bulk 에 남아 저장 시 그대로 전송된다.
    g('#pb-addrow').onclick=()=>{b.rows=b.rows.concat(blankRows(5));render();};   // 일자는 비움(=상단일자 사용)
    // 품번 열: 단일=품번(수기·검색), 다열=품번⇥수량⇥비고
    host.querySelectorAll('.pb-item').forEach(el=>{
      el.oninput=e=>{
        const i=+e.target.dataset.i, v=e.target.value;
        b.rows[i].item_code=v;
        bulkSearch(v);                      // 입력할수록 후보 좁힘(디바운스)
        // 이미 아는 품번이면 품명을 즉시 채운다(재렌더 없이 셀만 — 포커스 유지)
        const hit=(st.bulkItems||[]).find(x=>x.code===v.trim().toUpperCase());
        b.rows[i].item_name=hit?hit.name:'';
        const nm=host.querySelector(`.pb-nm[data-i="${i}"]`);
        if(nm){nm.textContent=b.rows[i].item_name;nm.title=b.rows[i].item_name;}
      };
      el.onpaste=e=>{
        const txt=(e.clipboardData||window.clipboardData).getData('text');
        if(!/[\n\t]/.test(txt))return;               // 단일값이면 기본 붙여넣기
        e.preventDefault();
        applyPaste(b,+e.target.dataset.i,txt,['item_code','plan_qty','remarks']);
        render(); fillNames();                       // 붙여넣은 품번들의 품명 조회
      };
    });
    // ★계획수량·비고 열도 붙여넣기 지원(2026-09-02). 종전엔 onpaste 가 없어
    //   엑셀 한 열을 복사하면 **한 칸에 전부 들어갔다**(값이 위로 몰림).
    //   계획수량 칸에서 붙여넣으면 수량⇥비고, 비고 칸에서는 비고만 채운다.
    host.querySelectorAll('.pb-qty').forEach(el=>{
      el.oninput=e=>{b.rows[+e.target.dataset.i].plan_qty=e.target.value;};
      el.onpaste=e=>{
        const txt=(e.clipboardData||window.clipboardData).getData('text');
        if(!/[\n\t]/.test(txt))return;               // 단일값이면 기본 붙여넣기
        e.preventDefault();
        applyPaste(b,+e.target.dataset.i,txt,['plan_qty','remarks']);render();
      };
    });
    host.querySelectorAll('.pb-rm').forEach(el=>{
      el.oninput=e=>{b.rows[+e.target.dataset.i].remarks=e.target.value;};
      el.onpaste=e=>{
        const txt=(e.clipboardData||window.clipboardData).getData('text');
        if(!/[\n\t]/.test(txt))return;
        e.preventDefault();
        applyPaste(b,+e.target.dataset.i,txt,['remarks']);render();
      };
    });
    host.querySelectorAll('.pb-rmrow').forEach(el=>el.onclick=()=>{b.rows.splice(+el.dataset.i,1);if(!b.rows.length)b.rows=blankRows(3);render();});
  };
  const bulkSave=async()=>{ const b=st.bulk;
    if(!String(b.line_no||'').trim()){alert('라인을 선택하세요');return;}
    const hm=String(b.output_hm||'').trim(); if(hm&&!/^\d{4}$/.test(hm)){alert('산출시각은 HHMM(4자리)');return;}
    const base6=/^\d{6}$/.test(String(b.plan_ymd||'').trim())?String(b.plan_ymd).trim():'';   // 기본일자(선택)
    const eff=r=>{const d=ymdNorm(r.plan_ymd);return /^\d{6}$/.test(d)?d:base6;};                // 행별 우선, 없으면 기본
    const withItem=b.rows.filter(r=>String(r.item_code||'').trim()&&Number(r.plan_qty)>0);
    const valid=withItem.filter(r=>/^\d{6}$/.test(eff(r)));
    if(!valid.length){alert(withItem.length?'계획일자가 없습니다(행별 또는 기본 계획일자 입력)':'품번·수량(>0)이 있는 행이 없습니다');return;}
    const noDate=withItem.length-valid.length;
    if(noDate&&!confirm(`계획일자 없는 ${noDate}행은 제외됩니다. ${valid.length}행을 등록할까요? (라인 ${b.line_no})`))return;
    if(!noDate&&!confirm(`${valid.length}개 행을 일괄 등록할까요? (라인 ${b.line_no}${base6?` · 기본일자 ${base6}`:''})`))return;
    try{const r=await fetch(`${API}/api/planinput/bulk`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({plan_ymd:b.plan_ymd,line_no:b.line_no,output_hm:b.output_hm,prod_tag:b.prod_tag,work_code:b.work_code,rows:b.rows})});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=`✅ ${j.inserted}건 일괄등록${j.skipped?` (제외 ${j.skipped})`:''}`;st.bulk=null;
        // ★forward 창이므로 **가장 이른** 등록일자를 기준일(첫 컬럼)로 → 등록분이 전부 보인다.
        //   (종전엔 backward 창이라 가장 늦은 일자를 우측 끝으로 잡았다)
        const mn=valid.map(eff).sort().shift()||base6;
        if(/^\d{6}$/.test(mn))st.base=`20${mn.slice(0,2)}-${mn.slice(2,4)}-${mn.slice(4,6)}`;
        st.line=b.line_no;await load();}
      else alert('일괄저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('일괄저장 오류: '+e);}
  };
  const save=async()=>{
    const f=st.form;
    if(!/^\d{6}$/.test(String(f.plan_ymd||'').trim())){alert('계획일자는 YYMMDD(6자리 숫자)여야 합니다');return;}
    if(!String(f.line_no||'').trim()||!String(f.item_code||'').trim()){alert('라인·품번은 필수입니다');return;}
    if(!(Number(f.plan_qty)>0)){alert('계획수량은 0보다 커야 합니다');return;}
    const hm=String(f.output_hm||'').trim();
    if(hm&&!/^\d{4}$/.test(hm)){alert('산출시각은 HHMM(4자리)여야 합니다');return;}
    try{const r=await fetch(`${API}/api/planinput/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.mode==='insert'?'✅ 등록완료':'✅ 수정완료');st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async()=>{
    const ids=[];st.sel.forEach(i=>{const row=st.mx.rows[i];if(row&&row.ppids)ids.push(...row.ppids);});
    if(!ids.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(`선택 ${st.sel.size}행(${ids.length}건)을 삭제하시겠습니까?`))return;
    try{const r=await fetch(`${API}/api/planinput/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
      const j=await r.json();st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
    catch(e){alert('삭제 오류: '+e);}
  };
  // 초기: 라인목록 로드 후 기준일 조회
  (async()=>{ await loadLines(); await load(); })();
};

/* ===== 준비실적처리(키팅) — 460_new 레이아웃. 라이브 자재소요+회수율+fin색상. 확인=nx flag-only(자재무차감) ===== */
SCREEN.kitting=(host)=>{
  // 준비실적처리(키팅) — 레거시 w_pr_input_460_new(≈dw_pr_input_410_t1_new2) 전 컬럼·2행·필터·버튼 재현. 라이브 PARTNER_ERP(RO).
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const f2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const y2iso=y=>y&&y.length===6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';
  const wlab=y=>{if(!y||y.length<6)return dcol(y);const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));const dow='일월화수목금토'[dt.getDay()];return `${y.slice(4,6)}${dow}`;};   // 레거시 라벨: 일자+요일 (예 19월)
  const isWkend=y=>{if(!y||y.length<6)return false;const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return dt.getDay()===0||dt.getDay()===6;};
  const T=new Date();
  /* ★복사용 범위선택 스타일(2026-09-03, 410 과 동일 규칙).
       실적선택(.kt-sel, 파랑)과 색을 달리해 회청색으로. 색칠된 셀은 인라인 background 가
       background-image 를 덮으므로 표시는 outline 으로 준다(인라인에 안 밀리게 !important). */
  if(!document.getElementById('kt-cpsel-style')){
    const s=document.createElement('style'); s.id='kt-cpsel-style';
    s.textContent='.kt-cp{background-image:linear-gradient(rgba(148,163,184,.34),rgba(148,163,184,.34));'
      +'outline:2px solid #64748b !important;outline-offset:-2px}'
      // 소계/집계행은 선택 대상이 아니다 — 표시가 붙어도 무시(펼침 전용 자리)
      +'tr.kt-subtot td.kt-cp,tr.kt-agg td.kt-cp{background-image:none;outline:none !important}'
      +'tr.kt-subtot td,tr.kt-agg td{user-select:none;-webkit-user-select:none}'
      // ★소계/집계행의 도번칸 = BOM 선택 대상 아님. 어떤 선택표시도 내지 않는다(2026-09-03)
      +'tr.kt-subtot .kt-item,tr.kt-agg .kt-item{outline:none !important;box-shadow:none !important}'
      /* ★항목보기 모달·컨텍스트메뉴 CSS(2026-09-03).
           종전엔 이 스타일이 SCREEN.partplan(410) 안에서만 주입돼, 키팅만 열면
           클래스가 없어 **모달이 화면에 안 보였다**(팝업이 안 뜨는 것처럼). 여기에도 정의한다.
           같은 이름이라 410 을 먼저 열었든 아니든 동작이 같다. */
      +'.ppcol-ov{position:fixed;inset:0;z-index:1250;background:rgba(15,23,42,.38);display:flex;align-items:center;justify-content:center}'
      +'.ppcol-bx{background:#fff;border-radius:10px;box-shadow:0 18px 48px rgba(10,25,55,.4);width:420px;max-width:94vw;display:flex;flex-direction:column;max-height:82vh}'
      +'.ppcol-h{padding:11px 14px;border-bottom:1px solid #dbe3ee;font-weight:700;display:flex;align-items:center;gap:8px}'
      +'.ppcol-b{flex:1;min-height:0;overflow:auto;padding:4px 0}'
      +'.ppcol-f{padding:9px 14px;border-top:1px solid #dbe3ee;display:flex;gap:6px;justify-content:flex-end}'
      +'.ppcol-r{display:flex;align-items:center;gap:9px;padding:5px 14px;cursor:pointer;'
      +'border-bottom:1px solid #f1f5f9;user-select:none;-webkit-user-select:none}'
      +'.ppcol-r:hover{background:#f5f8fd}'
      +'.ppcol-n{width:26px;color:#94a3b8;font-size:11px;text-align:right}'
      +'.ppcol-t{flex:1}'
      +'.ppcol-sep{display:flex;align-items:center;gap:8px;padding:5px 14px;margin:2px 0;'
      +'background:repeating-linear-gradient(45deg,#eef4fd,#eef4fd 6px,#e3ecfa 6px,#e3ecfa 12px);'
      +'border-top:2px solid #2563eb;border-bottom:2px solid #2563eb;'
      +'color:#1c47a0;font-size:11px;font-weight:700;user-select:none}'
      +'.pp-ctx{position:fixed;z-index:1300;background:#fff;border:1px solid #cbd5e1;border-radius:7px;'
      +'box-shadow:0 10px 30px rgba(10,25,55,.3);padding:4px 0;min-width:150px;font-size:13px}'
      +'.pp-ctx div{padding:6px 15px;cursor:pointer;white-space:nowrap}'
      +'.pp-ctx div:hover{background:#eff4fd}';
    document.head.appendChild(s);
  }
  /* ★항목보기(2026-09-03) — 컬럼 숨김/순서.
       이 화면은 헤더·본행·소계행·집계행·합계행 5곳이 각자 <td> 를 직접 쓰기 때문에
       410 처럼 정의배열로 갈아엎으면 손댈 곳이 많고 실적등록 로직까지 흔들린다.
       → **열 번호(고정컬럼)만 정의**해 두고, 숨김은 CSS(nth-child)로, 순서는 DOM 열 이동으로 한다.
         렌더 코드를 건드리지 않으므로 실적 등록·취소 경로가 그대로 유지된다.
       일자컬럼(가변)은 대상 아님 — 조회조건 '기간'이 정한다. */
  const KT_FIXED=[   // {i:열인덱스(0=체크박스), t:이름}  ※일자컬럼 앞 8개 + 뒤 11개
    {i:1,t:'SEQ'},{i:2,t:'파트'},{i:3,t:'도번'},{i:4,t:'PART일자'},
    {i:5,t:'PART INPUT'},{i:6,t:'Line No'},{i:7,t:'당일이전'},
  ];
  const KT_TAIL=[    // 일자컬럼 뒤(오프셋은 일자 개수에 따라 계산)
    {o:0,t:'준비재고'},{o:1,t:'완료수량'},{o:2,t:'준비수량'},{o:3,t:'생산재고'},
    {o:4,t:'ASSY재고'},{o:5,t:'출하'},{o:6,t:'자재사용량'},{o:7,t:'Work Order'},
    {o:8,t:'Split Work Order'},{o:9,t:'ASSY도번'},
  ];
  const KT_SCOPE='kt460';
  let KTPREF=null;                       // 서버(nx.user_pref)에서 온 설정
  const ktPrefLoad=async()=>{try{const r=await fetch(`${API}/api/pref?scope=${KT_SCOPE}`);
      if(!r.ok)return false; const j=await r.json();
      if(j&&j.prefs){KTPREF=j.prefs;return true;}}catch(e){}
    return false;};
  const ktPrefSave=async(obj)=>{
    KTPREF=Object.assign({},KTPREF||{},obj);
    try{Object.keys(obj).forEach(k=>{if(obj[k]==null)localStorage.removeItem('kt460_'+k);
      else localStorage.setItem('kt460_'+k,JSON.stringify(obj[k]));});}catch(_){}
    try{const r=await fetch(`${API}/api/pref`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({scope:KT_SCOPE,prefs:obj})});return r.ok;}catch(e){return false;}};
  const ktHidden=()=>{try{const s=(KTPREF&&KTPREF.hide!==undefined)?KTPREF.hide
                         :JSON.parse(localStorage.getItem('kt460_hide')||'null');
      return new Set(Array.isArray(s)?s:[]);}catch(e){return new Set();}};
  // ★기본 소스 = 신규DB(웹편성). 레거시 대조는 소스를 nx/라이브로 바꿔서 본다(2026-08-26).
  const st={dates:[],rows:[],cnt:0,plan_sum:0,ready_sum:0,note:'',base:iso(T),gigan:2,src:'new',wc:'',wh:'',part:'',pgroup:'',line:'',dono:'',jado:'',wo:'',unfin:'미생산',view:'상세',sel:new Set(),fold:new Set(),cellSel:new Set(),itemSel:null,loading:false,msg:''};
  /* load(quiet) — quiet=true 면 **표만 조용히 갱신**한다(2026-09-03).
       왜 — 실적 등록/취소 뒤 매번 render() 전체를 돌려 화면이 통째로 새로 그려졌다.
       스크롤이 맨 위로 튀고 펼쳐둔 블록이 접히고, 8천행에서는 눈에 띄게 멈췄다
       ("실적 잡을 때·취소할 때 새로고침" 증상). 데이터는 다시 받아야 정확하지만
       **그리는 건 tbody/tfoot 만** 바꾸면 된다 — 스크롤·펼침·조건이 그대로 유지된다. */
  let ktQueried=false;   // ★[조회] 를 눌렀는가 — 빈 표 안내문구 구분(자동조회 안 하므로 필요)
  const load=async(quiet)=>{
    ktQueried=true;                      // 이후 빈 결과는 '조회 결과 없음'으로 안내
    const gw0=host.querySelector('.grid-wrap');
    const sy=gw0?gw0.scrollTop:0, sx=gw0?gw0.scrollLeft:0;
    if(!quiet){st.loading=true;render();}
    // ★항상 전체로 1회 fetch → 캐시. 파트·제번·도번·미생산·구분은 클라에서 즉시 필터(재조회 없음).
    //   서버 재조회 = 기준일자·자도번작업처·기간 변경시만. (파트별 생산계획과 동일 정책)
    const qs=new URLSearchParams({from_ymd:st.base,gigan:st.gigan,wc:st.wc,pgroup:st.pgroup,line:st.line,view:'상세',unfin:'전체',src:(st.src||'nx'),limit:6000});
    try{const r=await fetch(`${API}/api/kitting/grid?${qs}`);const j=await r.json();st.dates=j.dates||[];st.rows=j.rows||[];st.cnt=j.cnt||0;st.plan_sum=j.plan_sum||0;st.ready_sum=j.ready_sum||0;st.note=j.note||'';if(!quiet)st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];st.dates=[];}
    st.loading=false;st.sel.clear();
    if(quiet){
      st.cellSel.clear();                 // 처리된 셀 선택은 해제(값이 바뀌었다)
      render(true);                       // 표(tbody/tfoot)만 교체 — 툴바·스크롤·펼침 유지
      const gw1=host.querySelector('.grid-wrap');
      if(gw1){gw1.scrollTop=sy;gw1.scrollLeft=sx;}
      const mb=host.querySelector('#kt-msg'); if(mb)mb.textContent=st.msg||'';
    }else render();
  };
  const shiftDay=n=>{const d=new Date(st.base);d.setDate(d.getDate()+n);st.base=iso(d);load();};
  const act=async(mode)=>{
    const rows=st.rows.filter((r,i)=>st.sel.has(i)).map(r=>({item_code:r.item,work_order:r.wo,gpc:r.gpc,plan_ymd:r.part_ymd,work_center:r.wc,qty:(mode==='cancel'?r.ready_qty:r.need_qty)})).filter(r=>r.qty>0);
    if(!rows.length){alert(mode==='cancel'?'취소할(준비수량>0) 행 선택':'준비필요(>0) 행 선택');return;}
    const knm=mode==='cancel'?'준비취소':'확인(준비등록)';
    if(!confirm(`${rows.length}건 ${knm}?\n(자재 무차감 · 준비재고+READY 마킹, 자재차감은 생산실적)`))return;
    try{const r=await fetch(`${API}/api/ready/register`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,rows,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})});
      const j=await r.json();if(j.ok){st.msg=`✅ ${knm} ${j.count}건 완료${j.skipped?` (제외 ${j.skipped})`:''}`;await load(true);}else alert(knm+' 실패');}
    catch(e){alert(knm+' 오류: '+e);}};
  // ★셀단위 확인/취소(우클릭) — flag-only(자재무차감). 확인=그 셀 잔량 준비등록, 취소=되돌림.
  const cellAct=async(mode,m)=>{
    // ★취소 = 등록의 완전 원복(준비재고−, 자재창고 되돌림, 파트창고−, 용접전표 삭제) → /api/ready/commit mode=cancel
    if(mode==='cancel'){
      // ★취소수량 = 이미 등록된 수량(done). 잔량(qty)이 아님 — 셀 2/16이면 2를 취소.
      const q=+m.done||0;
      if(q<=0){alert('취소할 준비수량이 없습니다.');return;}
      if(!confirm(`${esc(m.item)} · ${nf(q)}세트 준비취소할까요?\n`
                 +`· 준비재고 감소\n· ${esc(m.gpc)} 파트창고 → 자재창고 재고 원복\n· 용접전표 삭제`))return;
      try{
        const r=await fetch(`${API}/api/ready/commit`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({mode:'cancel',item:m.item,gpc:m.gpc,qty:q,
                               ymd:(m.ymd==='P'?'':m.ymd),wo:m.wo,
                               user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})});
        const j=await r.json();
        if(j.ok){st.msg=`⏪ 준비취소 완료 — ${esc(m.item)} ${nf(q)}세트 원복`;await load(true);}
        else alert('취소 불가: '+(j.detail||''));
      }catch(e){alert('취소 오류: '+e);}
      return;
    }
    const body={item:m.item,wo:m.wo,swo:m.swo,gpc:m.gpc,ymd:m.ymd,qty:+m.qty,assy:m.assy,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')};
    try{const r=await fetch(`${API}/api/kitting/cell-confirm`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();
      if(j.ok){st.msg=`✅ 준비확인 ${nf(j.qty||0)} (${esc(m.item)} · ${dcol(m.ymd)})`;await load(true);}
      else alert('확인 불가: '+(j.detail||''));}
    catch(e){alert('셀 확인 오류: '+e);}};
  // fin 우선순위. ★파트별 생산계획(SCREEN.partplan)과 동일 색체계로 통일(2026-08-18):
  //   '6'=출하완료(살구) · '7'=현재공정/작업중전표(진주황) · '4'=생산완료(노랑) · '3'=키팅완료(녹) · '0'=미키팅(백)
  const finBg=f=>f==='6'?'#fac090':(f==='7'?'#ed7d31':(f==='4'?'#ffff00':(f==='3'?'#669900':'')));
  const finFg=f=>(f==='3'||f==='7')?'#ffffff':'';   // 진한 녹·주황 배경엔 흰 글자(가독)
  // ★파트별 생산계획과 동일한 UX 이식(2026-08-18): 소계행 접기/펼치기 + 표만 재그리기(성능)
  let _typeT=null;
  const redrawBody=()=>{const w=host.querySelector('.grid-wrap');const sy=w?w.scrollTop:0,sx=w?w.scrollLeft:0;
    render(true);
    const n=host.querySelector('.grid-wrap');if(n){n.scrollTop=sy;n.scrollLeft=sx;}};
  // ★셀 드래그선택 → [확인] → 세트가능수량 팝업(레거시 w_pr_input_466)
  //   레거시 제약: 선택 셀이 여러 파트면 "한가지 파트씩", 여러 도번이면 "한가지 도번씩" 경고 후 중단.
  //   팝업 = /api/ready/setcheck (조회전용): 자도번별 사용수량·재고·세트가능수량·협력사.
  let _ktDrag=false;   // 좌클릭 드래그 중 여부(셀 선택). mouseup에서 해제.
  let _rectOwn=new Set();   // 이번 드래그 사각범위가 만든 선택키(범위 축소시 이것만 해제 — Ctrl 추가선택분 보존)
  document.addEventListener('mouseup',()=>{_ktDrag=false;});
  const cellKey=td=>[td.dataset.item,td.dataset.wo,td.dataset.swo,td.dataset.gpc,td.dataset.ymd].join('');
  // ★선택 표시 — 완료(녹)·생산완료(노랑) 셀 위에서도 확실히 구분되게(2026-08-19).
  //   기존 outline 2px 파랑은 진한 녹색 배경에 묻혀 "선택됐는지" 알 수 없었음.
  //   → 두꺼운 파란 테두리 + 안쪽 흰 링 + 좌상단 ✔ 배지로 배경색과 무관하게 보이도록.
  //
  //   ★성능 주의(2026-08-19 재수정): 드래그 중 매 셀마다 전 셀(수천 개)을 순회하며
  //     DOM 을 만들고 지우면 프레임이 밀려 mouseenter 가 유실 → "드래그했는데 중간 셀이 빠짐".
  //     → paintOne(단일 셀)만 갱신하고, 전체 순회 paintSel 은 재렌더 직후에만 호출.
  //   ★DOM 을 건드리지 않는다(2026-08-19 재재수정): 배지 span 을 append/remove 하면
  //     드래그 중 커서 아래 요소가 매번 바뀌어 mouseover 판정이 흔들리고 선택이 빠졌음.
  //     → 스타일 3개만 갈아끼움. 좌상단 삼각 표식도 background-image(그라디언트)로 처리.
  // ★2026-08-20 선택표시 완화(사용자 요청) — 도번칸(paintItem)과 같은 톤.
  //   진한 파랑 삼각+두꺼운 흰 테두리 → 연파랑 오버레이 + 얇은 파란 테두리.
  //   배경'색'(완료 녹/노랑)은 유지해야 하므로 backgroundImage 로 연한 막만 덧씌움.
  const _SELBG='linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72))';
  const paintOne=(td,on)=>{
    const s=td.style;
    s.outline       = on?'2px solid #4a86e8':'';
    s.outlineOffset = on?'-2px':'';
    s.boxShadow     = '';
    s.backgroundImage = on?_SELBG:'';      // 배경'색'(완료 녹/노랑)은 그대로 두고 이미지만 덧씌움
    s.fontWeight    = on?'700':'';
    td.classList.toggle('kt-sel',on);};
  // 선택 뱃지 = 칸수 + 잔량합(준비등록 대상) + 등록분합(취소 대상)
  const paintCnt=()=>{const b=host.querySelector('#kt-cellcnt');
    if(!b)return;
    const n=st.cellSel.size;
    if(!n){b.textContent='';b.style.display='none';return;}
    let jan=0,don=0;
    host.querySelectorAll('.kt-cell.kt-sel').forEach(td=>{
      jan+=(+td.dataset.qty||0); don+=(+td.dataset.done||0);});
    const r2=v=>Math.round(v*100)/100;
    b.textContent=`선택 ${n}칸`
      +(jan>0?` · 잔량 ${nf(r2(jan))}`:'')
      +(don>0?` · 준비 ${nf(r2(don))}`:'');
    b.style.display='inline-block';};
  // 전체 재도색 — 재렌더/선택해제 등 "한 번만" 도는 경로에서 사용
  const paintSel=()=>{host.querySelectorAll('.kt-cell').forEach(td=>
    paintOne(td,st.cellSel.has(cellKey(td))));paintCnt();};
  // 드래그 중 = 이 셀 하나만 켜기(전체 순회 없음)
  const selAdd=(td)=>{const k=cellKey(td);
    if(st.cellSel.has(k)){paintCnt();return;}
    st.cellSel.add(k);paintOne(td,true);paintCnt();};
  const selClear=()=>{if(!st.cellSel.size)return;
    host.querySelectorAll('.kt-cell.kt-sel').forEach(td=>paintOne(td,false));
    st.cellSel.clear();paintCnt();};
  // ★도번 칸 선택(2026-08-19) — 레거시처럼 도번 셀 자체가 반전(검정바탕/흰글씨)되고,
  //   그 상태로 [🖨 BOM출력] 을 누르면 그 도번의 Spec Sheet(BOM) 이 나옴.
  //   일자셀 드래그선택(st.cellSel)과는 별개 상태(st.itemSel). 서로 지우지 않음.
  //   ★2026-08-20 두 가지 개선(사용자 요청):
  //   (1) 같은 도번이 집계행+상세행에 여러 번 나와도 "클릭한 그 칸 하나"만 표시.
  //       → item·gpc 뿐 아니라 행 고유키(uid)까지 비교. 펼친 상세행을 클릭하면 그 행만 반전.
  //   (2) 검정(#111) 반전이 너무 진해 → 연한 파랑 + 파란 테두리로 완화.
  const itemUid=(td)=>{const tr=td.closest('tr');if(!tr)return '';
    const rows=[...host.querySelectorAll('tr')];
    return String(rows.indexOf(tr));};
  const paintItem=()=>{host.querySelectorAll('.kt-item').forEach(td=>{
    const on=st.itemSel && td.dataset.item===st.itemSel.item
             && td.dataset.gpc===st.itemSel.gpc && itemUid(td)===st.itemSel.uid;
    td.style.background = on?'#dbeafe':'';
    td.style.color      = on?'#123a6b':'';
    td.style.fontWeight = on?'700':'';
    td.style.outline    = on?'2px solid #4a86e8':'';
    td.style.outlineOffset = on?'-2px':'';});};
  const itemPick=(td)=>{
    const k={item:td.dataset.item,gpc:td.dataset.gpc,uid:itemUid(td)};
    st.itemSel=(st.itemSel&&st.itemSel.item===k.item&&st.itemSel.gpc===k.gpc
                &&st.itemSel.uid===k.uid)?null:k;  // 재클릭=해제
    selClear();          // ★도번 클릭 = 수량셀 선택 해제(둘이 동시에 남지 않게, 2026-08-20)
    paintItem();};
  const selectedCells=()=>[...host.querySelectorAll('.kt-cell')].filter(td=>st.cellSel.has(cellKey(td)));
  // viewOnly=true : [🔎 세트가능 확인] 에서 호출 — 조회 전용(등록 버튼·세트수량 입력·전표출력 숨김)
  //                 false: [✅ 확인(준비등록)] / 우클릭 확인 — 등록까지 진행
  const openSetPopup=async(viewOnly)=>{
    const tds=selectedCells();
    if(!tds.length){alert('셀을 드래그해서 선택하세요.');return;}
    const parts=[...new Set(tds.map(t=>t.dataset.gpc))];
    if(parts.length>1){alert('한가지 파트씩 생산준비처리를 진행해 주십시오.');return;}
    const items=[...new Set(tds.map(t=>t.dataset.item))];
    if(items.length>1){alert('한가지 도번씩 생산준비처리를 진행해 주십시오.');return;}
    // ★충당 순서 = 선택 범위 안에서 "이른 날짜부터" 순차(레거시 동일).
    //   계획 변동이 잦아 특정 셀을 콕 집어 채우지 않고, 재고 소진처럼 앞 날짜부터 흘려보냄.
    //   ('P'=당일이전 백로그가 가장 앞. 그 다음 일자 오름차순)
    const ordKey=t=>(t.dataset.ymd==='P'?'000000':(t.dataset.ymd||'999999'));
    tds.sort((a,b)=>ordKey(a).localeCompare(ordKey(b)));
    const item=items[0], ymd=tds[0].dataset.ymd;
    const qty=tds.reduce((s,t)=>s+(+t.dataset.qty||0),0);   // 선택 셀 잔량 합 = 생산준비 세트수량
    // ★잔량0 셀(=이미 준비완료, 녹색)만 골라 [확인]을 누른 경우 — 등록할 게 없음.
    //   취소 목적이면 우클릭 → ⏪ 준비취소 로 안내(2026-08-19: 완료셀도 선택 가능해지며 추가).
    if(qty<=0&&!viewOnly){alert('선택한 셀은 이미 준비가 완료되어 등록할 잔량이 없습니다.\n\n'
                    +'취소하려면 해당 셀에서 우클릭 → ⏪ 준비취소 를 사용하세요.');return;}
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;z-index:1200;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center';
    // ★레거시 w_pr_input_466: 세트수량은 편집 가능(파란칸), 용접전표 출력여부 체크박스 제공.
    const partNm=(tds[0].closest('tr')?.querySelectorAll('td')[2]?.textContent||'').trim();
    ov.innerHTML=`<div style="background:#fff;border-radius:8px;min-width:660px;max-width:90vw;max-height:80vh;overflow:auto;box-shadow:0 8px 30px rgba(0,0,0,.3)">
      <div style="padding:10px 14px;border-bottom:1px solid #e3e9f0;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span style="font-size:20px;font-weight:700;background:#eceff3;padding:4px 14px;border-radius:4px">${esc(partNm)}</span>
        <span class="tl">도번</span><span style="background:#eceff3;padding:4px 10px;border-radius:4px;font-weight:600">${esc(item)}</span>
        <span class="tl">${viewOnly?'확인 수량':'생산준비 세트수량'}</span>
        <input class="inp" id="sp-qty" type="number" min="1" step="1" value="${qty}" ${viewOnly?'readonly':''}
               style="width:90px;min-width:0;text-align:right;background:${viewOnly?'#eceff3':'#e8f0fe'};font-weight:700">
        ${viewOnly
          ?`<span style="color:#1c47a0;font-size:12px;font-weight:600">🔎 조회 전용 — 재고·세트가능수량만 확인합니다</span>`
          :`<label style="display:inline-flex;align-items:center;gap:5px;font-weight:400">
          <input type="checkbox" id="sp-weld" checked> 용접전표 A4 출력<span style="color:#8a93a0;font-weight:400">(해제해도 전표는 발행됨)</span></label>`}
        <span style="flex:1"></span><button class="btn ghost" id="sp-x" style="padding:2px 10px">✕</button></div>
      <div id="sp-body" style="padding:12px 14px"><div style="color:#789">조회 중…</div></div></div>`;
    document.body.appendChild(ov);
    const close=()=>ov.remove();
    ov.onclick=e=>{if(e.target===ov)close();};
    ov.querySelector('#sp-x').onclick=close;
    try{
      const r=await fetch(`${API}/api/ready/setcheck?item=${encodeURIComponent(item)}&ymd=${encodeURIComponent(ymd)}&qty=${qty}`);
      const j=await r.json();
      const able=j.set_able||0;
      // ★키팅제외분 참고표시 — 기본은 닫힘(기존 모습 유지), 펼치면 목록이 보인다.
      //   투입파트 미지정 / 키팅제외(BOM관리 '키팅' 미체크) 를 사유별로 나눠 두 블록으로 보여준다.
      const exclBlock=(title,list)=>list.length?`<details style="margin-top:8px;border:1px solid #e3e9f0;border-radius:6px;background:#fafbfc">
        <summary style="padding:6px 10px;cursor:pointer;color:#6b7684;font-size:11px">
          ${esc(title)} (${nf(list.length)}건)<span style="color:#9aa3ad"> — 참고용, 세트가능 계산에서 제외됨</span></summary>
        <table class="tbl" style="font-size:11px;width:100%;margin:0">
          <thead><tr><th class="center">자도번</th><th class="center">품명</th><th class="center">사용수량</th><th class="center">협력사</th><th class="center">제외사유</th></tr></thead>
          <tbody>${list.map(x=>`<tr style="color:#8a93a0">
            <td class="center">${esc(x.mat)}</td><td class="center">${esc(x.nm||'')}</td>
            <td class="center">${x.use_qty}</td><td class="center">${esc(x.cust||'')}</td>
            <td class="center">${esc(x.why||'')}</td></tr>`).join('')}</tbody>
        </table></details>`:'';
      // ★세트수량은 사용자가 수정 가능 → 입력값(want) 기준으로 판정·표시·등록. 변경시 즉시 재판정.
      const paint=()=>{
        const want=Math.max(0,+ov.querySelector('#sp-qty').value||0);
        const ok=able>=want&&want>0;
        ov.querySelector('#sp-body').innerHTML=`
        <table class="tbl" style="font-size:12px;width:100%">
          <thead><tr><th class="center">자도번</th><th class="center">사용수량</th><th class="center">재고수량</th><th class="center">세트가능수량</th><th class="center">협력사</th></tr></thead>
          <tbody>${(j.rows||[]).length?(j.rows||[]).map(x=>`<tr${x.set_able<want?' style="background:#fff1f0"':''}>
            <td class="center">${esc(x.mat)}</td><td class="center">${x.use_qty}</td>
            <td class="center"${x.stock_qty<0?' style="color:#c0392b;font-weight:700"':''}>${nf(x.stock_qty)}</td>
            <td class="center"${x.set_able<want?' style="color:#c0392b;font-weight:700"':''}>${nf(x.set_able)}</td>
            <td class="center">${esc(x.cust||'')}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">키팅 대상 자재 없음(투입파트·키팅체크 있는 자재 없음)</td></tr>'}</tbody>
          <tfoot><tr style="background:#eef2f7;font-weight:700">
            <td class="center">${nf((j.rows||[]).length)}건</td><td class="center"></td><td class="center"></td>
            <td class="center"${able<0?' style="color:#c0392b"':''}>${nf(able)}</td><td class="center"></td></tr></tfoot>
        </table>
        <div style="margin-top:10px;padding:8px 10px;border-radius:6px;background:${ok?'#e8f6ec':'#fdecea'};color:${ok?'#1c7c3a':'#c0392b'};font-weight:600">
          ${ok?`✅ 세트가능 ${nf(able)} — 요청 ${nf(want)} 처리 가능`
              :`⚠ 세트가능 ${nf(able)} — 요청 ${nf(want)} 에 미달(자재부족). 실적이 잡히지 않습니다.`}
        </div>
        ${exclBlock('투입파트 정보없음', (j.excluded||[]).filter(x=>(x.why||'').includes('투입파트')))}
        ${exclBlock('키팅제외품', (j.excluded||[]).filter(x=>!(x.why||'').includes('투입파트')))}
        ${viewOnly?'':`<div style="margin-top:6px;color:#789;font-size:11px">
          ※ 충당 순서: 선택 범위 안에서 <b>이른 날짜부터</b> 순차로 채웁니다(계획 변동 대비, 재고 소진 방식).
          완료 시 준비재고가 증가하고 화면의 준비수량은 준비재고 기준으로 갱신됩니다.</div>`}
        <div style="margin-top:10px;display:flex;gap:6px;justify-content:flex-end">
          <button class="btn ghost" id="sp-cancel">닫기</button>
          ${viewOnly?'':`<button class="btn" id="sp-ok" ${ok?'':'disabled'} style="background:${ok?'#1c7c3a':'#c8cdd4'};color:#fff">✅ 완료(준비등록)</button>`}
        </div>`;
        ov.querySelector('#sp-cancel').onclick=close;
        const okBtn=ov.querySelector('#sp-ok');
        if(okBtn&&ok)okBtn.onclick=async()=>{
          // ★전체 프로세스 API(/api/ready/commit) 호출:
          //   ①준비재고+ ②자재창고출고(tag B, 소요×세트) ③파트창고재고+ ④용접전표 발행 — 원자적 처리.
          const weld=ov.querySelector('#sp-weld').checked;
          const t0=tds[0];
          if(!confirm(`${esc(item)} · ${nf(want)}세트 생산준비 등록할까요?\n`
                     +`· 준비재고 증가\n· 자재창고 → ${esc(t0.dataset.gpc)} 파트창고 재고이동(소요량×${nf(want)})\n`
                     +`· 용접전표 발행${weld?' + A4 출력':' (출력 안 함)'}\n`))return;
          okBtn.disabled=true;okBtn.textContent='등록 중…';
          try{
            const rr=await fetch(`${API}/api/ready/commit`,{method:'POST',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({mode:'register',item:item,gpc:t0.dataset.gpc,qty:want,
                                   ymd:(t0.dataset.ymd==='P'?'':t0.dataset.ymd),wo:t0.dataset.wo,
                                   weld_print:weld,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})});
            const jj=await rr.json();
            if(jj.ok){close();selClear();
              st.msg=`✅ 생산준비 등록 완료 — ${esc(item)} ${nf(want)}세트`
                    +(jj.sheet_no?` · 용접전표 ${esc(jj.sheet_no)} 발행`:'')
                    +(jj.moved&&jj.moved.length?` · 자재 ${jj.moved.length}종 파트창고 이동`:'');
              // ★용접전표 출력여부 체크시 발행된 전표를 즉시 A4로 열어줌(레거시 자동출력 동작)
              if(weld&&jj.sheet_no)window.printWeldSheet(jj.sheet_no);   // ★최상위 공용 함수
              await load();}
            else{alert('준비등록 실패: '+(jj.detail||''));okBtn.disabled=false;okBtn.textContent='✅ 완료(준비등록)';}
          }catch(e){alert('준비등록 오류: '+e);okBtn.disabled=false;okBtn.textContent='✅ 완료(준비등록)';}
        };
      };
      paint();
      const qi=ov.querySelector('#sp-qty');
      if(qi){qi.oninput=paint;qi.onchange=paint;}   // 세트수량 수정 → 즉시 재판정
    }catch(e){ov.querySelector('#sp-body').innerHTML=`<div style="color:#c0392b">조회 실패: ${esc(String(e))}</div>`;}
  };
  // ★생산 이동 전표(용접전표) A4 출력 — 레거시 dw 양식 재현.
  //   필드매핑: wh_part_desc(자재창고) · line_no(우상단) · 전표번호 8자리+바코드 · upper_item_code
  //             · item_code · plan_qty(대형) · item_desc · plan_ymd · schedule(투입시간) · jig_keep_area
  //             · SEQ 10줄(part_desc/sub_desc/sub_barcode) · err_remarks1~3(용접·검사·조립 불량이력)
  //   바코드 = J(용접전표)만 8자리 전표번호. G/L은 생산전표출력관리에서 별도 발행.
  // ★window 전역으로 노출 — 준비실적처리(키팅)와 생산전표출력관리 두 화면이 같은 A4 양식을 공유.
  // ★행 이벤트(체크박스·소계행 접기) — tbody만 교체해도 다시 연결돼야 하므로 분리
  const wireKtRows=()=>{
    const upd=()=>{const c=host.querySelector('#kt-selcnt');if(c)c.textContent=st.sel.size;};   // #kt-selcnt 표시는 제거됨(가드로 무해)
    const idsOf=ch=>(ch.dataset.idxs||'').split(',').filter(Boolean).map(Number);
    // 체크박스는 재렌더 없이 상태·DOM만 갱신(대량행 렉 방지)
    host.querySelectorAll('.kt-chk').forEach(ch=>ch.onclick=()=>{idsOf(ch).forEach(x=>ch.checked?st.sel.add(x):st.sel.delete(x));
      const a=host.querySelector('#kt-all');if(a)a.checked=false;upd();});
    // 청록 소계행(상세뷰)·집계행(집계뷰) 클릭 = 그 도번 블록 접기/펼치기
    //   ※ 체크박스 클릭은 토글되면 안 되므로 이벤트 전파 차단
    /* ★펼침/접힘 = 더블클릭(2026-09-03, 410 과 동일).
         한 번 클릭이면 그 행을 스치거나 복사용으로 긁기만 해도 접혔다 펴져 화면이 튄다. */
    host.querySelectorAll('tr.kt-subtot, tr.kt-agg').forEach(tr=>{
      tr.title='더블클릭 = 상세 펼침/접힘';
      tr.ondblclick=(ev)=>{
        if(ev.target && ev.target.classList && ev.target.classList.contains('kt-chk'))return;
        const k=tr.getAttribute('data-gk');if(!k)return;
        if(st.fold.has(k))st.fold.delete(k);else st.fold.add(k);
        redrawBody();};});
    // ★셀 드래그선택(레거시 방식): 좌클릭을 "누르고 있는 동안"만 드래그 확장.
    //   ev.buttons(비트마스크)로 실제 버튼 눌림 여부를 매 이동마다 확인 → 그냥 마우스만 지나가면 선택 안 됨.
    //   Ctrl/⌘ 누르고 시작하면 기존 선택 유지(추가선택).
    //   ★잔량(data-qty)이 0인 셀 = 실적 다 잡힌 것 → 선택 대상 아님(레거시 동일). 부족분만 드래그됨.
    //   ★2026-08-19 보완: 잔량 0이라도 "이미 등록된 수량(data-done)>0" 이면 선택 가능하게.
    //     녹색(준비완료) 셀은 잔량0이라 클릭이 아예 안 먹어 "선택된 건지" 알 수 없었음.
    //     취소는 등록분을 되돌리는 동작이므로 그 셀도 잡혀야 함. 확인(준비등록)은 잔량>0 셀만 대상(기존 유지).
    const selectable=td=>((+td.dataset.qty||0)>0)||((+td.dataset.done||0)>0&&td.dataset.fin!=='6');
    // ★이벤트 위임(2026-08-19) — 셀마다 핸들러를 다는 대신 grid-wrap 한 곳에서 처리.
    //   셀이 수천 개라 개별 부착은 렌더가 무거워지고, 드래그 중 프레임이 밀려 선택이 빠졌음.
    //   mouseenter(셀별) → mouseover(위임, 버블링) 로 교체.
    //   ★사각영역 선택(2026-08-19 재재수정): mouseover 로 "지나간 셀"만 담으면
    //     빠르게 끌 때 이벤트가 유실돼 중간 셀이 빠짐(실측: 85행 누락).
    //     → 시작셀~현재셀의 (행,열) 사각범위를 매 move 마다 계산해 통째로 선택.
    //       엑셀과 동일한 감각이고, 커서가 셀 사이를 건너뛰어도 절대 빠지지 않음.
    const gwSel=host.querySelector('.grid-wrap');
    if(gwSel){
      // ★브라우저 기본 텍스트선택 차단(2026-08-20) — 빈칸 드래그시 파란 하이라이트가
      //   그리드를 덮던 문제. 선택표시는 우리가 그리는 연파랑만 남는다.
      gwSel.style.userSelect='none'; gwSel.style.webkitUserSelect='none';
      gwSel.onselectstart=()=>false;
      //   ※행 구조가 달라도(소계/집계행) 안전하도록 (행=rowIndex, 열=cellIndex)로 좌표화.
      //     kt-cell 은 일자컬럼에만 붙으므로 열 인덱스는 같은 컬럼끼리 일치.
      const rcOf=td=>{const tr=td.parentElement;
        return {r:tr?tr.rowIndex:-1, c:td.cellIndex};};
      // 커서 아래 kt-cell. 셀이 아니면(빈칸·고정컬럼·행간격) 같은 y 에서 가로로 훑어
      // 가장 가까운 kt-cell 을 찾아 좌표만 얻는다 → 드래그가 중간에 끊기지 않음.
      /* ★성능(2026-09-03): 종전엔 행마다 모든 .kt-cell 에 getBoundingClientRect() 를 돌려
           '가장 가까운 칸'을 찾았다. rect 읽기는 강제 리플로우라 mousemove 마다 열 수만큼
           발생 → 드래그가 무거웠다. 열의 가로위치는 드래그 중 변하지 않으므로 한 번만 재서
           캐시한다(가로스크롤·표 재렌더 시에만 갱신). */
      let _kcolX=null,_kcolXsx=-1,_kcolXn=-1;
      const kcolX=()=>{
        const sx=gwSel.scrollLeft, n=host.querySelectorAll('.kt-cell').length;
        if(_kcolX&&_kcolXsx===sx&&_kcolXn===n)return _kcolX;
        _kcolXsx=sx; _kcolXn=n; _kcolX=[];
        const row=host.querySelector('tr.kt-main'); // 한 행만 재면 전 열 위치를 안다
        if(row)for(const td of row.cells){
          if(td.classList.contains('kt-cell')){const b=td.getBoundingClientRect();
            _kcolX.push({i:td.cellIndex,l:b.left,r:b.right});}}
        return _kcolX;};
      const cellAt=(x,y)=>{
        let e=document.elementFromPoint(x,y);
        let td=e?e.closest('.kt-cell'):null;
        if(td)return td;
        const tr=e?e.closest('tr'):null;               // 같은 행에서 x 에 가장 가까운 셀
        if(tr){
          const cols=kcolX(); let best=-1,bd=1e9;
          for(const cx of cols){                       // rect 읽기 없음 — 캐시 좌표로 비교만
            const d=(x<cx.l)?(cx.l-x):((x>cx.r)?(x-cx.r):0);
            if(d<bd){bd=d;best=cx.i;}}
          if(best>=0&&best<tr.cells.length){const q=tr.cells[best];
            if(q&&q.classList.contains('kt-cell'))return q;}}
        // ★빈칸 위를 지날 때도 좌표를 잃지 않도록 일반 td 로 폴백(2026-08-20).
        //   선택은 _cells(=숫자칸)만 대상이라 빈칸이 켜지지는 않는다.
        return e?e.closest('td'):null;};
      let _a=null, _cells=null, _lastTd=null;   // 시작 (행,열) / 셀 스냅샷 / 직전 커서 셀
      const applyRect=(td)=>{
        if(!_a||!_cells)return;
        const b=rcOf(td);
        const r1=Math.min(_a.r,b.r), r2=Math.max(_a.r,b.r);
        const c1=Math.min(_a.c,b.c), c2=Math.max(_a.c,b.c);
        for(const it of _cells){
          const inRect = it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2;
          const has=st.cellSel.has(it.k);
          if(inRect&&!has){st.cellSel.add(it.k);paintOne(it.td,true);_rectOwn.add(it.k);}
          else if(!inRect&&has&&_rectOwn.has(it.k)){st.cellSel.delete(it.k);paintOne(it.td,false);}
        }
        paintCnt();};
      gwSel.onmousedown=(ev)=>{
        if(ev.button!==0)return;                       // 좌클릭만(우클릭=컨텍스트메뉴)
        /* ★실적선택을 시작하면 복사선택(회청)을 지운다(2026-09-03).
             둘이 동시에 켜져 있으면 "클릭표시가 양쪽 다" 보여 무엇이 선택된 건지 알 수 없다.
             한 화면에 선택은 한 종류만 — 반대 방향(복사→실적 해제)도 아래 gwCp 에서 처리한다. */
        if(host._ktClearCp)host._ktClearCp();
        const it=ev.target.closest('.kt-item');        // 도번 칸 클릭 = 도번 선택(BOM출력 대상)
        // ★소계/집계행에서는 선택표시를 내지 않는다(2026-09-03, 410 과 동일 · 레거시도 그렇다).
        //   그 행은 '펼침(더블클릭)' 전용 자리다 — 파란 테두리가 뜨면 선택된 줄 알게 된다.
        if(it&&it.closest('tr.kt-subtot,tr.kt-agg')){ev.preventDefault();return;}
        if(it){ev.preventDefault();itemPick(it);return;}
        // ★빈칸(수량 없는 셀)에서 시작한 드래그도 사각범위 선택으로(2026-08-20 사용자요청).
        //   선택 자체는 숫자칸만 — 빈칸은 기준점 역할만 하고 켜지지 않는다.
        //   (기존: .kt-cell 아니면 return → 브라우저 기본 텍스트선택이 파랗게 잡히던 문제)
        const any=ev.target.closest('td');
        if(any&&!ev.target.closest('.kt-cell')&&any.closest('tr')&&rcOf(any)){
          ev.preventDefault();
          if(st.itemSel){st.itemSel=null;paintItem();}
          if(!ev.ctrlKey&&!ev.metaKey)selClear();
          _ktDrag=true;_rectOwn=new Set();
          _cells=[...host.querySelectorAll('.kt-cell')].filter(selectable)
                   .map(x=>{const p=rcOf(x);return {td:x,r:p.r,c:p.c,k:cellKey(x)};});
          _a=rcOf(any);_lastTd=any;return;
        }
        const td=ev.target.closest('.kt-cell'); if(!td||!selectable(td))return;
        ev.preventDefault();
        if(st.itemSel){st.itemSel=null;paintItem();}   // ★수량셀 선택 = 도번 선택 해제(2026-08-20)
        // ★재클릭=해제(도번칸과 동일). Ctrl 없이 이미 선택된 칸을 다시 누르면 그 칸만 끈다.
        const _k=cellKey(td);
        if(!ev.ctrlKey&&!ev.metaKey&&st.cellSel.has(_k)){
          if(st.cellSel.size===1){st.cellSel.delete(_k);paintOne(td,false);paintCnt();return;}
          selClear();                       // 여러 칸 선택 상태 → 한 번에 정리
          st.cellSel.add(_k);paintOne(td,true);paintCnt();
          _ktDrag=true;_rectOwn=new Set([_k]);
          _cells=[...host.querySelectorAll('.kt-cell')].filter(selectable)
                   .map(x=>{const p=rcOf(x);return {td:x,r:p.r,c:p.c,k:cellKey(x)};});
          _a=rcOf(td);_lastTd=td;return;
        }
        if(ev.ctrlKey||ev.metaKey){         // Ctrl+클릭 = 개별 토글
          if(st.cellSel.has(_k)){st.cellSel.delete(_k);paintOne(td,false);paintCnt();return;}
        }
        _ktDrag=true;
        if(!ev.ctrlKey&&!ev.metaKey)selClear();
        _rectOwn=new Set();                            // 이번 드래그가 만든 선택분(되돌릴 대상)
        // 선택가능 셀 좌표를 드래그 시작시 1회만 스냅샷 → move 마다 DOM 질의 없음
        _cells=[...host.querySelectorAll('.kt-cell')].filter(selectable)
                 .map(x=>{const p=rcOf(x);return {td:x,r:p.r,c:p.c,k:cellKey(x)};});
        _a=rcOf(td);_lastTd=td;selAdd(td);_rectOwn.add(cellKey(td));};
      /* ★성능(2026-09-03): mousemove 는 초당 수십~수백 회 온다. 매번 applyRect 로
           전 셀(_cells)을 훑으면 대각선으로 길게 끌 때 프레임이 밀린다.
           ①같은 칸 위 이동은 무시 ②실제 칠하기는 rAF 로 프레임당 1회. */
      let _kRaf=0,_kLastRC=null;
      gwSel.onmousemove=(ev)=>{
        if(!_ktDrag)return;
        if(!(ev.buttons&1)){                                    // 손 뗐으면 종료
          _ktDrag=false;_a=null;_cells=null;_lastTd=null;
          if(_kRaf){cancelAnimationFrame(_kRaf);_kRaf=0;} _kLastRC=null; return;}
        const td=cellAt(ev.clientX,ev.clientY)||_lastTd;        // 셀을 못 찾으면 직전 위치 유지
        if(!td)return;
        _lastTd=td;
        const p=rcOf(td);
        if(_kLastRC&&_kLastRC.r===p.r&&_kLastRC.c===p.c)return; // ① 같은 칸 → 할 일 없음
        _kLastRC=p;
        if(_kRaf)return;
        _kRaf=requestAnimationFrame(()=>{_kRaf=0; if(_ktDrag&&_lastTd)applyRect(_lastTd);});  // ②
      };
      gwSel.onmouseup=()=>{
        if(_kRaf){cancelAnimationFrame(_kRaf);_kRaf=0;}
        if(_ktDrag&&_lastTd)applyRect(_lastTd);                 // 마지막 위치는 확실히 반영
        _ktDrag=false;_a=null;_cells=null;_lastTd=null;_kLastRC=null;};
    }
    /* ══ 복사용 범위선택 + Ctrl+C (2026-09-03, 410 과 동일) ══════════════════
         .kt-cell(일자·당일이전)=실적선택 전용이므로 건드리지 않는다.
         그 외 셀(도번·파트·재고·WorkOrder…)을 끌면 회청색 사각범위가 잡히고
         Ctrl+C 로 탭구분 텍스트가 복사된다(엑셀 붙여넣기 호환). 소계/집계행은 제외. */
    const gwCp=host.querySelector('.grid-wrap');
    if(gwCp&&!gwCp.dataset.cpsel){
      gwCp.dataset.cpsel='1';
      let cpA=null,cpOn=false,cpPainted=[],cpRaf=0,cpLast=null;
      const cpRc=td=>({r:td.parentElement?td.parentElement.rowIndex:-1,c:td.cellIndex});
      const cpClear=()=>{for(const x of cpPainted)x.classList.remove('kt-cp'); cpPainted=[];};
      host._ktClearCp=cpClear;        // ★실적선택 시작 시 호출 — 두 선택이 겹쳐 보이지 않게
      const cpPaint=(b)=>{
        if(!cpA)return;
        const r1=Math.min(cpA.r,b.r),r2=Math.max(cpA.r,b.r);
        const c1=Math.min(cpA.c,b.c),c2=Math.max(cpA.c,b.c);
        cpClear();
        const tbl=gwCp.querySelector('table'); if(!tbl)return;
        for(const tb of tbl.tBodies){const rs=tb.rows;
          for(let i=0;i<rs.length;i++){const row=rs[i]; const ri=row.rowIndex;
            if(ri<r1||ri>r2)continue;
            if(row.classList.contains('kt-subtot')||row.classList.contains('kt-agg'))continue;  // 소계 제외
            const cs=row.cells;
            for(let j=c1;j<=c2&&j<cs.length;j++){
              const cell=cs[j];
              if(cell.classList.contains('kt-cell'))continue;      // 실적칸 제외(두 선택 겹침 방지)
              cell.classList.add('kt-cp'); cpPainted.push(cell);}}}
      };
      gwCp.addEventListener('mousedown',ev=>{
        if(ev.button!==0)return;
        const td=ev.target.closest&&ev.target.closest('td');
        if(!td||!td.parentElement)return;
        if(td.classList.contains('kt-cell'))return;                // 실적선택 영역
        if(ev.target.closest('.kt-item'))return;                   // 도번칸=BOM 대상 선택
        if(ev.target.tagName==='INPUT')return;                     // 체크박스
        const tr=td.parentElement;
        if(tr.classList.contains('kt-subtot')||tr.classList.contains('kt-agg')){cpClear();return;}
        // ★반대 방향 — 복사선택을 시작하면 실적선택(파랑)을 지운다. 한 화면에 선택은 한 종류만.
        if(st.cellSel&&st.cellSel.size){selClear();paintCnt();}
        if(st.itemSel){st.itemSel=null;paintItem();}
        cpClear(); cpA=cpRc(td); cpOn=true; cpPaint(cpA);
        ev.preventDefault();
      });
      gwCp.addEventListener('mousemove',ev=>{
        if(!cpOn)return;
        const td=ev.target.closest&&ev.target.closest('td');
        if(!td||!td.parentElement)return;
        const b=cpRc(td);
        if(cpLast&&cpLast.r===b.r&&cpLast.c===b.c)return;          // 같은 칸 → 무시
        cpLast=b;
        if(cpRaf)return;
        cpRaf=requestAnimationFrame(()=>{cpRaf=0; if(cpOn&&cpLast)cpPaint(cpLast);});
      });
      document.addEventListener('mouseup',()=>{
        if(cpRaf){cancelAnimationFrame(cpRaf);cpRaf=0;}
        if(cpOn&&cpLast)cpPaint(cpLast);
        cpOn=false; cpLast=null;});
      // 선택영역 → 탭구분 텍스트
      host._ktCopySel=()=>{
        if(!cpPainted.length){alert('복사할 영역을 먼저 끌어서 선택하세요.');return;}
        const map=new Map();
        cpPainted.forEach(td=>{const r=td.parentElement.rowIndex;
          if(!map.has(r))map.set(r,[]);
          map.get(r).push([td.cellIndex,(td.innerText||'').trim()]);});
        const txt=[...map.keys()].sort((x,y)=>x-y)
          .map(r=>map.get(r).sort((x,y)=>x[0]-y[0]).map(x=>x[1]).join('\t')).join('\n');
        ktToClip(txt,'선택영역');
      };
      host._ktCopyAll=()=>{
        const tbl=gwCp.querySelector('table'); if(!tbl)return;
        const out=[];
        const hr=tbl.tHead&&tbl.tHead.rows[0];
        if(hr)out.push([...hr.cells].map(th=>(th.innerText||'').trim()).join('\t'));
        for(const tb of tbl.tBodies){const rs=tb.rows;
          for(let i=0;i<rs.length;i++)out.push([...rs[i].cells].map(td=>(td.innerText||'').trim()).join('\t'));}
        ktToClip(out.join('\n'),`전체 ${nf(out.length-1)}행`);
      };
    }
    const ktToClip=(txt,what)=>{
      if(!txt)return;
      const done=()=>{const el=host.querySelector('#kt-cnt');
        if(el){const o=el.textContent;el.textContent=what+' 복사됨';setTimeout(()=>{el.textContent=o;},1400);}};
      const fb=()=>{const ta=document.createElement('textarea'); ta.value=txt;
        ta.style.cssText='position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta); ta.select();
        try{document.execCommand('copy');done();}catch(_){alert('복사에 실패했습니다.');}
        ta.remove();};
      if(navigator.clipboard&&navigator.clipboard.writeText)
        navigator.clipboard.writeText(txt).then(done,fb);
      else fb();
    };
    // Ctrl+C — 표 안에 복사선택이 있을 때만 가로챈다
    if(!host.dataset.cpkey){
      host.dataset.cpkey='1';
      host.setAttribute('tabindex','-1'); host.style.outline='none';
      host.addEventListener('keydown',ev=>{
        if((ev.ctrlKey||ev.metaKey)&&(ev.key==='c'||ev.key==='C')){
          if(!host.querySelector('.kt-cp'))return;
          ev.preventDefault(); if(host._ktCopySel)host._ktCopySel();}
      });
    }
    ktApplyHide();      // ★항목보기 숨김 반영(표를 다시 그릴 때마다)
    ktWireLazy();       // ★점진 렌더 — 스크롤 끝에서 이어붙이기
    // 커서/툴팁만 셀별로(1회, 이벤트 부착 아님)
    host.querySelectorAll('.kt-cell').forEach(td=>{
      if(!selectable(td)){td.style.cursor='default';return;}
      td.style.cursor='pointer';
      td.title=((+td.dataset.qty||0)>0)
        ?'클릭/드래그: 선택 · 우클릭: 확인/취소'
        :`준비완료 ${td.dataset.done} — 클릭: 선택 · 우클릭: 준비취소`;});
    // ★소계/집계행의 도번칸은 클릭 대상이 아니다 — 커서도 기본으로(2026-09-03)
    host.querySelectorAll('.kt-item').forEach(td=>{
      td.style.cursor=td.closest('tr.kt-subtot,tr.kt-agg')?'pointer':'pointer';
      if(td.closest('tr.kt-subtot,tr.kt-agg'))td.title='더블클릭 = 상세 펼침/접힘';});
    paintSel();paintItem();};
  /* ══ 항목보기 — 숨김 적용 · 목록 모달 · 일반 우클릭메뉴 (2026-09-03) ══════════
       숨김은 열 인덱스로 지운다. 렌더 코드를 안 건드리므로 실적등록 경로가 그대로다.
       ★열 인덱스는 '일자 개수'에 따라 뒤쪽이 밀리므로 st.dates.length 로 계산한다. */
  const ktColList=()=>{
    const nd=(st.dates||[]).length;
    return KT_FIXED.map(x=>({key:'f'+x.i,idx:x.i,t:x.t}))
      .concat(KT_TAIL.map(x=>({key:'t'+x.o,idx:8+nd+x.o,t:x.t})));
  };
  const ktApplyHide=()=>{
    const hide=ktHidden(), cols=ktColList();
    const tbl=host.querySelector('.grid-wrap table'); if(!tbl)return;
    const hideIdx=new Set(cols.filter(c=>hide.has(c.key)).map(c=>c.idx));
    // 모든 행에서 해당 열의 셀을 숨긴다(colspan 쓰는 '결과없음' 행은 건드리지 않는다)
    const doRow=row=>{const cs=row.cells;
      if(cs.length<=2)return;                       // colspan 안내행
      for(let i=0;i<cs.length;i++)cs[i].style.display=hideIdx.has(i)?'none':'';};
    if(tbl.tHead)[...tbl.tHead.rows].forEach(doRow);
    for(const tb of tbl.tBodies)for(const r of tb.rows)doRow(r);
    if(tbl.tFoot)[...tbl.tFoot.rows].forEach(doRow);
  };
  const ktColPick=()=>{
    const old=document.getElementById('kt-colpick'); if(old)old.remove();
    const cols=ktColList(); let hide=new Set(ktHidden());
    const ov=document.createElement('div'); ov.className='ppcol-ov'; ov.id='kt-colpick';
    ov.innerHTML=`<div class="ppcol-bx">
      <div class="ppcol-h">항목보기<span style="font-weight:400;font-size:11px;color:#7b8aa0">체크 해제 = 숨김 · 일자컬럼은 조회조건 '기간'이 정합니다</span></div>
      <div class="ppcol-b" id="ktcol-list"></div>
      <div class="ppcol-f">
        <button class="btn ghost" id="ktcol-reset">초기화</button><div style="flex:1"></div>
        <button class="btn ghost" id="ktcol-no">취소</button>
        <button class="btn" id="ktcol-ok" style="background:#1c47a0;color:#fff">확인</button>
      </div></div>`;
    document.body.appendChild(ov);                  // ★§3 — .content 안 fixed 는 잘린다
    const nd=(st.dates||[]).length;
    const paint=()=>{
      ov.querySelector('#ktcol-list').innerHTML=cols.map((c,i)=>
        (i===KT_FIXED.length?`<div class="ppcol-sep">일자 컬럼 ${nd}개 (조회조건 '기간')</div>`:'')
        +`<div class="ppcol-r" data-k="${c.key}">
            <span class="ppcol-n">${i+1}</span>
            <input type="checkbox" ${hide.has(c.key)?'':'checked'}>
            <span class="ppcol-t">${esc(c.t)}</span>
          </div>`).join('');
      ov.querySelectorAll('.ppcol-r').forEach(row=>{
        const k=row.dataset.k, cb=row.querySelector('input');
        cb.onchange=()=>{if(cb.checked)hide.delete(k);else hide.add(k);};
        row.onclick=e=>{if(e.target===cb)return;
          cb.checked=!cb.checked; if(cb.checked)hide.delete(k);else hide.add(k);};
      });
    };
    paint();
    const close=()=>ov.remove();
    ov.onclick=e=>{if(e.target===ov)close();};
    ov.querySelector('#ktcol-no').onclick=close;
    ov.querySelector('#ktcol-reset').onclick=()=>{hide=new Set();paint();};
    ov.querySelector('#ktcol-ok').onclick=()=>{
      ktPrefSave({hide:[...hide]}); close(); ktApplyHide();};
  };
  // 실적칸이 아닌 곳의 우클릭 = 항목보기 · 복사
  const ktPlainMenu=(ev)=>{
    ev.preventDefault();
    const old=document.querySelector('.pp-ctx'); if(old)old.remove();
    const m=document.createElement('div'); m.className='pp-ctx';
    m.innerHTML='<div data-a="col">항목보기</div><div data-a="copy">선택영역 복사</div><div data-a="all">전체 복사</div>';
    m.style.left=Math.min(ev.clientX,innerWidth-170)+'px';
    m.style.top=Math.min(ev.clientY,innerHeight-110)+'px';
    document.body.appendChild(m);
    // ★mousedown 에서 실행 — click 으로 하면 바깥클릭 닫기가 먼저 떠 메뉴가 사라진다(410 동일 이슈)
    const kill=()=>{m.remove();document.removeEventListener('mousedown',outside,true);};
    const outside=e=>{if(!m.contains(e.target))kill();};
    setTimeout(()=>document.addEventListener('mousedown',outside,true),0);
    m.addEventListener('mousedown',e=>{
      e.preventDefault(); e.stopPropagation();
      const t=e.target.closest&&e.target.closest('[data-a]'); if(!t)return;
      const a=t.getAttribute('data-a'); kill();
      if(a==='col')ktColPick();
      else if(a==='copy'){if(host._ktCopySel)host._ktCopySel();}
      else if(a==='all'){if(host._ktCopyAll)host._ktCopyAll();}
    });
  };
  /* 고정컬럼수(체크박스+SEQ..ASSY도번) — colspan/스피너 계산용.
     ★2026-08-19: 회수율·Item St(회수율반영) 삭제로 21→19
     ★2026-09-03: 실측 재확인 = 체크1 + 앞7(SEQ·파트·도번·PART일자·PART INPUT·Line No·당일이전)
       + 뒤10(준비재고~ASSY도번) = **18**. 19 는 1 초과였다(빈결과 안내행 colspan 이 한 칸
       넘쳐도 화면상 티가 안 나 남아 있었다). 헤더 실측 대조로 교정. */
  const NCOL=18;
  /* ══ 점진 렌더(2026-09-03 신설) ═══════════════════════════════════════════
       왜 — 이 화면은 최대 6,000행 × 20컬럼 = 12만 셀을 **한 번에** DOM 에 올렸다.
       저사양 PC 에서 최초 렌더·스크롤·드래그가 모두 멈춘다("엄청 버벅거린다").
       → 처음 KT_PAGE 행만 붙이고 스크롤이 끝에 가까워지면 이어붙인다.
         행 생성 로직(mainRow/aggRow/subTotalRow)은 그대로 — 완성된 HTML 을 <tr> 단위로 자를 뿐.
       ※합계(tfoot)·건수는 전체 기준 그대로라 숫자가 달라지지 않는다. (410 과 동일 방식) */
  const KT_PAGE=300;
  let ktRest=null;                       // 아직 안 붙인 <tr> 조각들
  /* ★행 생성기(mainRow/aggRow/subTotalRow)는 render() 안에 있으므로
       ktBody 는 그것들을 인자(mk)로 받는다 — 스코프를 넘겨 쓰지 않는다. */
  const ktBody=(flat,d,mk)=>{
    if(!flat.length)return `<tr><td colspan="${NCOL+d.length}" class="empty">`
      +(ktQueried?'조회 결과 없음 — 기준일자/작업처/파트/도번을 조정하세요'
                 :'조건을 고르고 [조회] 를 누르세요.')+`</td></tr>`;
    const full=flat.map(mk).join('');
    const parts=full.split(/(?=<tr)/);
    if(parts.length<=KT_PAGE){ktRest=null;return full;}
    ktRest=parts.slice(KT_PAGE);
    return parts.slice(0,KT_PAGE).join('');
  };
  const ktAppend=()=>{
    if(!ktRest||!ktRest.length)return;
    const tb=host.querySelector('.grid-wrap tbody'); if(!tb){ktRest=null;return;}
    const take=ktRest.slice(0,KT_PAGE); ktRest=ktRest.slice(KT_PAGE);
    tb.insertAdjacentHTML('beforeend',take.join(''));
    wireKtRows();                        // 새로 붙은 행에도 핸들러·숨김 반영
  };
  const ktWireLazy=()=>{
    const w=host.querySelector('.grid-wrap');
    if(!w||w.dataset.ktlazy)return;
    w.dataset.ktlazy='1';
    w.addEventListener('scroll',()=>{
      if(ktRest&&ktRest.length&&w.scrollTop+w.clientHeight>=w.scrollHeight-400)ktAppend();
    },{passive:true});
  };
  const render=(bodyOnly)=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('kitting'):true;
    const d=st.dates;
    // ★파트·자도번작업처 드롭다운 = 고정 전체목록 항상 렌더(필터결과 rows에서 뽑지 않음 → 선택해도 목록 안 줄어듦).
    const wcM=new Map([['P1','용접'],['P2','가공']]);   // 자도번작업처 고정(PR_M_WORK)
    // 파트 고정 code↔name(PR_M_PROC_GAGONG 실측), 대표 지정순서. '-'=구분선. rows 무관.
    const PART_FIX=[['S5','01라인(용접)'],['S5-2','01라인(조립)'],['S1','02라인'],['S6','03라인'],['S4','04라인'],['S11','05라인'],['RAC','06라인'],['S10','자동은납 10'],['S13','서브/고주파'],['S12','설치'],['S8','서포터 08'],['S9','용접 09'],['S7','다관절 로봇 용접'],['-','-'],['Q1000','용접봉창고']];
    const partOpts='<option value=""'+(st.part?'':' selected')+'>전체</option>'+PART_FIX.map(([v,n])=>v==='-'?'<option disabled>─────────</option>':`<option value="${esc(v)}"${st.part===v?' selected':''}>${esc(n)}</option>`).join('');
    // ★파트별 생산계획과 동일: 라디오그룹 전체를 테두리 박스로 구획
    const seg=(name,val,opts)=>`<span style="border:1px solid var(--line-2,#c9d3e0);border-radius:4px;padding:2px 6px;background:#fff;display:inline-flex;align-items:center">${opts.map(v=>`<label style="font-weight:400;margin:0 5px 0 1px;white-space:nowrap"><input type="radio" name="${name}" value="${v}" ${val===v?'checked':''}> ${v}</label>`).join('')}</span>`;
    // ── 미생산/미키팅 클라 즉시필터 + 평탄화(상세=본행+제번 / 집계=도번합침 1행 / 제번=제번행) ──
    // ★파트·제번·도번은 클라이언트 즉시필터(캐시에서) — 조회버튼 없이 반응. 파트별 생산계획과 동일 방식.
    const inc=(v,q)=>String(v||'').toUpperCase().includes(q);
    const qPart=st.part, qWo=st.wo.toUpperCase(), qDono=st.dono.toUpperCase(), qJado=st.jado.toUpperCase();
    const passed=[];st.rows.forEach((r,i)=>{
      if(!(st.unfin==='미생산'?r.done:(st.unfin==='미키팅'?r.unkit:true)))return;
      if(qPart&&r.gpc!==qPart)return;
      if(qWo&&!inc(r.wo,qWo))return;
      if(qDono&&!inc(r.assy,qDono))return;
      if(qJado&&!inc(r.item,qJado))return;
      passed.push({r,i});});
    const flat=[];let seq=0;
    // ★소계/집계 색상 롤업(파트별 생산계획 aggRank와 동일): 관련색이 하나라도 있으면 그 색. 녹3>노랑4>진주황7>살구6.
    const aggRk=f=>({'3':1,'4':2,'7':3,'6':4,'2':5,'0':9})[f]||9;
    const rollF=(fs)=>{const v=fs.filter(f=>f&&f!=='0');if(!v.length)return '0';
      return v.slice().sort((a,b)=>aggRk(a)-aggRk(b))[0];};
    // ★2026-08-23 부분충당 소계는 무색. 하위행 중 하나라도 색이 있으면 롤업되던 탓에
    //   48/129 처럼 미충족인데도 완전충당 색이 칠해졌다 → 합계가 계획을 다 채웠을 때만 색.
    const rollFq=(fs,cv,pl)=>((+cv||0) >= (+pl||0)-1e-6) ? rollF(fs) : '0';
    if(st.view==='집계'){
      // ★파트별 생산계획과 동일: "연속된 같은 도번" 블록 단위로 집계행 생성(전역 Map이면 상세와 순서가 어긋남).
      //   집계행 = 청록 배경 + 클릭시 상세 드릴다운(상세는 집계행 "위"에 표시). 색상은 rollF(관련색 우선) 사용.
      for(let i=0;i<passed.length;){
        // ★2026-09-01 블록키를 파트별생산계획(410)과 동일하게 — gpc+도번+라인+PART일자.
        //   종전 (도번+라인) 만 쓰면 같은 라인이라도 PART일자가 다르면 한 행으로 합쳐지고,
        //   반대로 정렬상 SVC 가 사이에 끼면 같은 라인이 두 블록으로 갈렸다.
        //   410 은 (gpc,item,line) 블록 + 일자별 행이라 08/24 C1 316 · 08/25 C1 102 처럼 나온다.
        //   대표 확정: "준비등록을 파트별생산계획처럼" · "추가계획(SVC) 라인만 분리".
        const bk=x=>(x.r.gpc||'')+'\x01'+(x.r.item||'')+'\x01'+(x.r.line||'')+'\x01'+(x.r.part_ymd||'');
        const it=bk(passed[i]); let j=i; const blk=[];
        while(j<passed.length&&bk(passed[j])===it){blk.push(passed[j]);j++;}
        const r0=blk[0].r, gk=it.replace(/\x01/g,'|')+'@'+i, open=st.fold.has(gk);
        const g={item:r0.item,gpc:r0.gpc,gpcnm:r0.gpcnm,line:r0.line,inhm:r0.inhm,part_ymd:r0.part_ymd,wo:'',swo:'',assy:r0.assy,
                 use_qty:r0.use_qty,days:{},dcov:{},dfin:{},drdy:{},
                 prior_plan:0,prior_cover:0,prior_ready:0,prior_fin:'0',plan_qty:0,finish:0,ready_qty:0,
                 ready_stock:0,prod_stock:0,assy_stock:0,sale:0,fin:'0',idxs:[]};
        blk.forEach(({r,i:ri})=>{
          g.idxs.push(ri);
          g.plan_qty+=r.plan_qty||0;g.finish+=r.finish||0;g.ready_qty+=r.ready_qty||0;
          g.prior_plan+=r.prior_plan||0;g.prior_cover+=r.prior_cover||0;g.prior_ready+=r.prior_ready||0;g.sale+=r.sale||0;
          g.ready_stock=Math.max(g.ready_stock,r.ready_stock||0);g.prod_stock=Math.max(g.prod_stock,r.prod_stock||0);g.assy_stock=Math.max(g.assy_stock,r.assy_stock||0);
          (st.dates||[]).forEach(x=>{const pl=(r.days&&r.days[x])||0;if(pl){g.days[x]=(g.days[x]||0)+pl;g.dcov[x]=(g.dcov[x]||0)+((r.dcov&&r.dcov[x])||0);g.drdy[x]=(g.drdy[x]||0)+((r.drdy&&r.drdy[x])||0);}});
        });
        // 색상 = 소계행과 동일 롤업(계획>0 행만 대상, 녹>노랑>진주황>살구)
        g.prior_fin=rollF(blk.filter(o=>(+o.r.prior_plan||0)>0).map(o=>o.r.prior_fin||'0'));
        (st.dates||[]).forEach(x=>{g.dfin[x]=rollF(blk.filter(o=>((o.r.days&&o.r.days[x])||0)>0).map(o=>(o.r.dfin&&o.r.dfin[x])||'0'));});
        // 펼침시 상세행을 집계행 "위"에 배치(파트별 생산계획과 동일)
        if(open) blk.forEach(({r,i:ri})=>{seq++;flat.push({t:'m',r,idxs:[ri],seq,childOf:gk});});
        seq++;flat.push({t:'g',r:g,idxs:g.idxs,seq,gk,open});
        i=j;
      }
    }else{
      // 상세·제번 = WO(제번)행. ★기존 하위행(splits=본행 자기복제, 레거시에 없는 중복)은 제거.
      // ★상세뷰: 파트별 생산계획처럼 "연속된 같은 도번" 블록마다 청록 소계행(t:'s') 추가 + 블록 접기 지원.
      if(st.view==='상세'){
        for(let i=0;i<passed.length;){
          // ★집계뷰와 같은 블록키(410 동일) — 소계행도 같은 단위로 묶여야 두 뷰가 어긋나지 않는다.
          const bk=x=>(x.r.gpc||'')+'\x01'+(x.r.item||'')+'\x01'+(x.r.line||'')+'\x01'+(x.r.part_ymd||'');
        const it=bk(passed[i]); let j=i; const blk=[];
          while(j<passed.length&&bk(passed[j])===it){blk.push(passed[j]);j++;}
          const gk=it.replace(/\x01/g,'|')+'@'+i, folded=st.fold.has(gk);
          if(!folded) blk.forEach(({r,i:ri})=>{seq++;flat.push({t:'m',r,idxs:[ri],seq});});
          flat.push({t:'s',blk:blk.map(o=>o.r),gk,folded});
          i=j;
        }
      }else{
        passed.forEach(({r,i})=>{seq++;flat.push({t:'m',r,idxs:[i],seq});});
      }
    }
    const fcnt=flat.filter(o=>o.t==='m').length;
    const fplan=passed.reduce((s,o)=>s+(o.r.plan_qty||0),0);
    const fready=passed.reduce((s,o)=>s+(o.r.ready_qty||0),0);
    const fpass=passed.map(o=>o.r);   // 필터통과 원행(합계행용)
    // ★파트별 생산계획과 동일: 전 셀 가운데정렬(center), 값 없는 셀은 '·' 대신 공백
    const numTd=(v,bg,strong,fg)=>`<td class="center"${bg?` style="background:${bg}${strong?';font-weight:700':''}${fg?';color:'+fg:''}"`:''}>${v}</td>`;
    // 우클릭 확인/취소 대상 셀(당일이전·일자) — data-*에 셀키(item·wo·gpc·ymd·잔량·assy·fin) 실어 컨텍스트메뉴에서 사용
    // ★data-qty=미준비 잔량(확인용) / data-done=이미 등록된 수량(취소용). 둘을 섞으면 취소수량이 틀어짐
    //   (2026-08-18 버그: 셀 2/16 취소 시 잔량 14가 취소수량으로 넘어감 → 등록분 2만 취소되어야 함)
    const ktCell=(v,bg,strong,fg,m)=>`<td class="center kt-cell" title="우클릭: 확인/취소" data-item="${esc(m.item)}" data-wo="${esc(m.wo)}" data-swo="${esc(m.swo)}" data-gpc="${esc(m.gpc)}" data-ymd="${esc(m.ymd)}" data-qty="${m.qty}" data-done="${m.done||0}" data-assy="${esc(m.assy)}" data-fin="${esc(m.fin)}"${(bg||fg)?` style="${bg?`background:${bg}${strong?';font-weight:700':''}`:''}${fg?';color:'+fg:''};cursor:context-menu"`:' style="cursor:context-menu"'}>${v}</td>`;
    const mainRow=(o)=>{const r=o.r,idxs=o.idxs||[];   // 셀별 색(당일이전=prior_fin, 일자=dfin), 전체행 배경 없음(레거시=셀별). idxs=하위 st.rows 인덱스(집계=여러WO)
      const pfin=r.prior_fin||'0';
      const pcell=r.prior_plan>0?`${nf(r.prior_cover||0)}/${nf(r.prior_plan)}`:'';
      return `<tr class="kt-main">
        <td class="center"><input type="checkbox" class="kt-chk" data-idxs="${idxs.join(',')}" ${idxs.length&&idxs.every(x=>st.sel.has(x))?'checked':''}></td>
        <td class="center">${o.seq}</td><td class="center">${esc(r.gpcnm||r.gpc)}</td>
        <td class="center kt-item" data-item="${esc(r.item)}" data-gpc="${esc(r.gpc)}" title="클릭: 도번 선택 → BOM출력"><b>${esc(r.item)}</b></td>
        <td class="center">${esc(dcol(r.part_ymd||''))}</td><td class="center">${esc(r.inhm)}</td><td class="center">${esc(r.line)}</td>
        ${r.prior_plan>0?ktCell(pcell,finBg(pfin),pfin!=='0',finFg(pfin),{item:r.item,wo:r.wo,swo:r.swo,gpc:r.gpc,ymd:r.part_ymd,qty:Math.max((r.prior_plan||0)-(r.prior_cover||0),0),done:(r.prior_ready||0),assy:r.assy,fin:pfin}):numTd('','',false)}
        ${d.map(x=>{const pl=(r.days&&r.days[x])||0,cv=(r.dcov&&r.dcov[x])||0,rd=(r.drdy&&r.drdy[x])||0,cf=(r.dfin&&r.dfin[x])||'0';return pl?ktCell(`${nf(cv)}/${nf(pl)}`,finBg(cf),cf!=='0',finFg(cf),{item:r.item,wo:r.wo,swo:r.swo,gpc:r.gpc,ymd:x,qty:Math.max(pl-cv,0),done:rd,assy:r.assy,fin:cf}):numTd('','',false);}).join('')}
        ${numTd(nf(r.ready_stock))}${numTd(nf(r.finish))}<td class="center" style="color:#1c7c3a"><b>${nf(r.ready_qty)}</b></td>
        ${numTd(nf(r.prod_stock))}${numTd(nf(r.assy_stock))}${numTd(nf(r.sale))}${numTd(nf(r.use_qty))}
        <td class="center">${esc(r.wo)}</td><td class="center">${esc(r.swo)}</td><td class="center">${esc(r.assy)}</td></tr>`;};
    // ★청록 소계행(파트별 생산계획 subHtml과 동일 개념) — 도번 블록 합계 + 색상 롤업.
    //   클릭시 그 블록 상세행 접기/펼치기(▼/▶). 색 롤업 = 관련색 하나라도 있으면 그 색(녹>노랑>진주황>살구).
    // ★집계행 = 청록 배경 + ▶/▼ 클릭 드릴다운. mainRow와 같은 컬럼구조지만 행 전체가 청록.
    const aggRow=(o)=>{const r=o.r,idxs=o.idxs||[];
      // ★부분충당은 무색(소계행과 동일 규칙) — 병합행도 합계가 계획을 채웠을 때만 색.
      const pfin=rollFq([r.prior_fin||'0'], r.prior_cover||0, r.prior_plan||0);
      const cTd=(v,f)=>`<td class="center"${f&&f!=='0'?` style="background:${finBg(f)};font-weight:700${finFg(f)?';color:'+finFg(f):''}"`:''}>${v}</td>`;
      return `<tr class="kt-agg" data-gk="${esc(o.gk)}" style="background:#cdeef7;font-weight:600;border-bottom:1px solid #9fb3c8;cursor:pointer">
        <td class="center"><input type="checkbox" class="kt-chk" data-idxs="${idxs.join(',')}" ${idxs.length&&idxs.every(x=>st.sel.has(x))?'checked':''}></td>
        <td class="center mut"><span style="color:#456">${o.open?'▼':'▶'}</span> ${o.seq}</td>
        <td class="center">${esc(r.gpcnm||r.gpc)}</td>
        <td class="center kt-item" data-item="${esc(r.item)}" data-gpc="${esc(r.gpc)}" title="클릭: 도번 선택 → BOM출력"><b>${esc(r.item)}</b></td>
        <td class="center">${esc(dcol(r.part_ymd||''))}</td><td class="center">${esc(r.inhm)}</td><td class="center">${esc(r.line)}</td>
        ${r.prior_plan>0?cTd(nf(r.prior_cover||0)+'/'+nf(r.prior_plan),pfin):'<td class="center"></td>'}
        ${d.map(x=>{const pl=(r.days&&r.days[x])||0,cv=(r.dcov&&r.dcov[x])||0;
          const cf=rollFq([(r.dfin&&r.dfin[x])||'0'], cv, pl);
          return pl?cTd(nf(cv)+'/'+nf(pl),cf):'<td class="center"></td>';}).join('')}
        <td class="center">${nf(r.ready_stock)}</td><td class="center">${nf(r.finish)}</td>
        <td class="center" style="color:#1c7c3a"><b>${nf(r.ready_qty)}</b></td>
        <td class="center">${nf(r.prod_stock)}</td><td class="center">${nf(r.assy_stock)}</td>
        <td class="center">${nf(r.sale)}</td><td class="center">${nf(r.use_qty)}</td>
        <td class="center"></td><td class="center"></td><td class="center">${esc(r.assy)}</td></tr>`;};
    /* ★점진 렌더에 넘길 행 생성기 — 세 종류(본행·집계·소계)를 하나로 묶는다.
         function 선언이라 호이스팅된다 = 아래 tbody 렌더보다 뒤에 써도 안전하다
         (const 로 두면 TDZ 로 "Cannot access before initialization" 이 난다). */
    function ktMk(o){return o.t==='m'?mainRow(o):(o.t==='g'?aggRow(o):subTotalRow(o));}
    const subTotalRow=(o)=>{const blk=o.blk,r0=blk[0];
      const sum=k=>blk.reduce((s,r)=>s+(+r[k]||0),0);
      const sPrP=sum('prior_plan'), sPrC=sum('prior_cover');
      const sPrF=rollFq(blk.filter(r=>(+r.prior_plan||0)>0).map(r=>r.prior_fin||'0'), sPrC, sPrP);
      const sTd=(v,f)=>`<td class="center"${f&&f!=='0'?` style="background:${finBg(f)};font-weight:700${finFg(f)?';color:'+finFg(f):''}"`:''}>${v}</td>`;
      return `<tr class="kt-subtot" data-gk="${esc(o.gk)}" style="background:#cdeef7;font-weight:600;border-bottom:1px solid #9fb3c8;cursor:pointer">
        <td class="center"></td><td class="center mut"><span style="color:#456">${o.folded?'▶':'▼'}</span></td>
        <td class="center">${esc(r0.gpcnm||r0.gpc)}</td><td class="center"><b>${esc(r0.item)}</b></td>
        <td class="center">${esc(dcol(r0.part_ymd||''))}</td><td class="center">${esc(r0.inhm)}</td><td class="center">${esc(r0.line)}</td>
        ${sPrP>0?sTd(nf(sPrC)+'/'+nf(sPrP),sPrF):'<td class="center"></td>'}
        ${d.map(x=>{const pl=blk.reduce((s,r)=>s+((r.days&&r.days[x])||0),0),cv=blk.reduce((s,r)=>s+((r.dcov&&r.dcov[x])||0),0);
          const cf=rollFq(blk.filter(r=>((r.days&&r.days[x])||0)>0).map(r=>(r.dfin&&r.dfin[x])||'0'), cv, pl);
          return pl>0?sTd(nf(cv)+'/'+nf(pl),cf):'<td class="center"></td>';}).join('')}
        <td class="center">${nf(Math.max(...blk.map(r=>+r.ready_stock||0)))}</td><td class="center">${nf(sum('finish'))}</td>
        <td class="center" style="color:#1c7c3a"><b>${nf(sum('ready_qty'))}</b></td>
        <td class="center">${nf(Math.max(...blk.map(r=>+r.prod_stock||0)))}</td><td class="center">${nf(Math.max(...blk.map(r=>+r.assy_stock||0)))}</td>
        <td class="center">${nf(sum('sale'))}</td><td class="center"></td>
        <td class="center"></td><td class="center"></td><td class="center">${esc(r0.assy)}</td></tr>`;};
    // ★bodyOnly=true면 표(tbody/tfoot)·건수만 교체(툴바 유지) — 필터 조작시 버벅임 제거. 파트별 생산계획과 동일 패턴.
    if(bodyOnly){
      const tb=host.querySelector('tbody'), tf=host.querySelector('tfoot'), cnt=host.querySelector('#kt-cnt');
      if(tb)tb.innerHTML=st.loading?spinRow(NCOL+d.length):ktBody(flat,d,ktMk);
      if(tf)tf.innerHTML=flat.length?`<tr class="grandtot" style="position:sticky;bottom:0;background:#eef2f7;font-weight:700;border-top:2px solid #b8c4d4">
        <td></td><td class="center">합계</td><td></td><td></td><td></td><td></td><td></td><td class="center"></td>${d.map(x=>`<td class="center">${nf(fpass.reduce((s,r)=>s+((r.days&&r.days[x])||0),0))}</td>`).join('')}
        <td class="center">${nf(fpass.reduce((s,r)=>s+(r.ready_stock||0),0))}</td><td class="center">${nf(fpass.reduce((s,r)=>s+(r.finish||0),0))}</td><td class="center">${nf(fready)}</td>
        <td></td><td></td><td class="center">${nf(fpass.reduce((s,r)=>s+(r.sale||0),0))}</td><td></td><td></td><td></td><td></td><td class="center">${f2(fpass.reduce((s,r)=>s+(r.item_st||0),0))}</td><td></td></tr>`:'';
      if(cnt)cnt.textContent=`${st.view==='집계'?'도번':'본행'} ${nf(fcnt)}건 · 계획 ${nf(fplan)} · 준비 ${nf(fready)}`;
      wireKtRows();
      return;
    }
    host.innerHTML=`
     <div class="page-title">🧰 준비실적처리(키팅) <span style="font-size:12px;color:var(--muted);font-weight:400">w_pr_input_460_new · 라이브 PR_T_PLAN_PART_DTL(읽기전용)</span></div>
     <div class="page-sub">본행=도번×제번(Work Order) · <span style="background:#e3f0fb;padding:0 5px">하늘색 하위행=파트(GAGONG_PROC 예 S11/S4) split</span>. 셀=재고충당/계획. 당일이전=지평이전 백로그(단일누적).
       <span style="background:#669900;color:#fff;padding:0 5px">녹=키팅완료(준비충당)</span> <span style="background:#ffff00;padding:0 5px">노랑=생산완료(ASSY재고)</span> <span style="background:#fac090;padding:0 5px">주황=출하완료</span> 백=미키팅</div>
     <!-- ★기능버튼은 맨 위 별도 줄(레거시 배치). 아래 필터 툴바는 파트별 생산계획과 동일 2줄 구성.
          (3종 중 [생산창고 재고과부족 확인]은 미구현이라 2026-08-19 숨김) -->
     <div class="toolbar" style="flex-wrap:wrap;gap:4px;margin-bottom:4px">
       <button class="btn ghost" id="kt-bom">🖨 BOM출력</button>
       <button class="btn ghost" id="kt-move">🚚 생산이동표 강제발행</button>
       <!-- ★[⚠ 생산창고 재고과부족 확인] 숨김(2026-08-19) — 기능 미구현(레거시 연동 예정).
            나중에 되살릴 때 아래 주석만 풀면 됨. 핸들러(#kt-short)는 가드로 남겨둠.
       <button class="btn ghost" id="kt-short">⚠ 생산창고 재고과부족 확인</button> -->
     </div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px;row-gap:2px">
       <!-- 2줄: 기준일자 · 자도번작업처 · 파트 · 기간 · 조회/등록 버튼 -->
       <label class="tl">기준일자</label><button class="btn ghost" id="kt-prev" title="전일" style="padding:2px 6px">◀</button>
       <input class="inp" type="date" id="kt-base" value="${st.base}" style="width:auto;min-width:0;padding:2px 0 2px 3px;font-size:12px">
       <button class="btn ghost" id="kt-next" title="익일" style="padding:2px 6px">▶</button>
       <label class="tl">자도번작업처</label><select class="inp" id="kt-wc" style="width:88px"><option value="">전체</option>${[...wcM].map(([v,n])=>`<option value="${esc(v)}"${st.wc===v?' selected':''}>${esc(n)}</option>`).join('')}</select>
       <label class="tl">파트</label><select class="inp" id="kt-part" style="width:130px">${partOpts}</select>
       <label class="tl">기간</label><select class="inp" id="kt-gigan" style="width:62px">${[1,2,3,4,5,6,7,8].map(n=>`<option value="${n}"${st.gigan===n?' selected':''}>${n}일</option>`).join('')}</select>
       <label class="tl">소스</label><select class="inp src-new" id="kt-src" data-src="${esc(st.src)}" style="width:auto;min-width:150px" title="신규DB(웹계획)=웹이 자체 편성한 계획(nx.plan_part_dtl) / 우리(nx)=레거시 편성 미러 / 라이브 대사=레거시 그대로"><option value="new"${st.src==='new'?' selected':''}>🟣 신규DB(웹계획)</option><option value="nx"${st.src==='nx'?' selected':''}>🟢 우리(nx)</option><option value="live"${st.src==='live'?' selected':''}>🔴 라이브 대사</option></select>
       <button class="btn" id="kt-go">🔍 조회</button>
       <button class="btn ghost" id="kt-setchk" title="셀을 드래그 선택한 뒤 클릭 — 자도번별 재고/세트가능수량 확인(조회전용)">🔎 세트가능 확인</button>
       ${ed?`<button class="btn" id="kt-reg" style="background:#1c7c3a;color:#fff">✅ 확인(준비등록)</button><button class="btn ghost" id="kt-can">⏪ 준비취소</button>`:`<span style="color:#c0392b;font-size:12px">🔒 권한 없음</span>`}
       <div style="flex-basis:100%;height:0"></div>
       <!-- 3줄: 제번 · ASSY도번 · 도번 · 미생산 · 구분 (레거시 3단 배치) -->
       <label class="tl">제번</label><input class="inp" id="kt-wo" value="${esc(st.wo)}" style="width:90px" placeholder="제번" autocomplete="off">
       <label class="tl">ASSY도번</label><input class="inp" id="kt-dono" value="${esc(st.dono)}" style="width:100px" placeholder="ASSY도번" autocomplete="off">
       <label class="tl">도번</label><input class="inp" id="kt-jado" value="${esc(st.jado)}" style="width:100px" placeholder="도번(item)" autocomplete="off">
       <label class="tl">미생산</label>${seg('kt-uf',st.unfin,['전체','미생산','미키팅'])}
       <label class="tl">구분</label>${seg('kt-vw',st.view,['상세','집계','제번'])}
       <!-- ★행 체크박스 개수 표시(#kt-selcnt) 제거 — 셀선택 뱃지(#kt-cellcnt)와 중복·혼동(2026-08-19).
            체크박스 기능(BOM출력 등 대상 선택)은 그대로. -->
       <span id="kt-cellcnt" style="display:none;margin-left:6px;padding:1px 8px;
             border-radius:10px;background:#1d4ed8;color:#fff;font-size:11px;font-weight:700"></span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${st.note?`<div class="page-sub" style="color:#b8860b">${esc(st.note)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr><th style="width:22px"><input type="checkbox" id="kt-all"></th>
        <th class="center">SEQ</th><th class="center">파트</th><th class="center">도번</th><th class="center">PART일자</th><th class="center">PART INPUT</th><th class="center">Line No</th><th class="center">당일이전</th>${d.map(x=>`<th class="center"${isWkend(x)?' style="color:#c0392b"':''}>${esc(wlab(x))}</th>`).join('')}<th class="center">준비재고</th><th class="center">완료수량</th><th class="center">준비수량</th><th class="center">생산재고</th><th class="center">ASSY재고</th><th class="center">출하</th><th class="center">자재사용량</th><th class="center">Work Order</th><th class="center">Split Work Order</th><th class="center">ASSY도번</th></tr></thead>
      <tbody>${st.loading?spinRow(NCOL+d.length):ktBody(flat,d,ktMk)}</tbody>
      <tfoot>${flat.length?`<tr class="grandtot" style="position:sticky;bottom:0;background:#eef2f7;font-weight:700;border-top:2px solid #b8c4d4">
        <td></td><td class="center">합계</td><td></td><td></td><td></td><td></td><td></td><td class="center"></td>${d.map(x=>`<td class="center">${nf(fpass.reduce((s,r)=>s+((r.days&&r.days[x])||0),0))}</td>`).join('')}
        <td class="center">${nf(fpass.reduce((s,r)=>s+(r.ready_stock||0),0))}</td><td class="center">${nf(fpass.reduce((s,r)=>s+(r.finish||0),0))}</td><td class="center">${nf(fready)}</td>
        <td></td><td></td><td class="center">${nf(fpass.reduce((s,r)=>s+(r.sale||0),0))}</td><td></td><td></td><td></td><td></td></tr>`:''}</tfoot>
      </table></div>
     <div class="page-sub" style="text-align:left;margin-top:2px" id="kt-cnt">${st.view==='집계'?'도번':'본행'} ${nf(fcnt)}건 · 계획 ${nf(fplan)} · 준비 ${nf(fready)} · ${st.src==='live'?'🔴 라이브 대사':(st.src==='new'?'🟣 신규DB(웹계획)':'🟢 우리(nx)')}</div>`;
    const g=id=>host.querySelector(id);
    // ★조회(서버 재조회) = 기준일자·자도번작업처·기간만. 나머지 필터는 캐시에서 즉시필터라 재조회 불필요.
    g('#kt-go').onclick=()=>{st.base=g('#kt-base').value;st.wc=g('#kt-wc').value;st.gigan=+g('#kt-gigan').value;
      const sv=g('#kt-src');if(sv)st.src=sv.value;
      load();};
    // 소스는 고르는 즉시 색을 바꾼다(조회 전에도 무엇을 볼지 보이게). 실제 반영은 [조회].
    {const sv=g('#kt-src');if(sv)sv.onchange=e=>{e.target.dataset.src=e.target.value;};}
    g('#kt-prev').onclick=()=>shiftDay(-1);g('#kt-next').onclick=()=>shiftDay(1);   // ◀▶만 즉시조회(예외)
    // ★BOM출력 = 선택 셀의 도번 → Spec Sheet(BOM) A4 가로 미리보기 → 인쇄(레거시 w_pr_input_460 동일).
    //   셀 미선택이면 레거시와 같은 문구로 안내.
    //   대상 = ①도번 칸을 클릭해 선택한 도번(레거시 방식) ②없으면 드래그선택한 셀의 도번.
    g('#kt-bom').onclick=()=>{
      if(st.itemSel){window.printBomSheet(st.itemSel.item, st.itemSel.gpc);return;}
      const tds=selectedCells();
      if(!tds.length){alert('미완료분 수량이 존재하는 도번을 선택해 주십시오.');return;}
      const items=[...new Set(tds.map(t=>t.dataset.item))];
      if(items.length>1){alert('한가지 도번씩 BOM 출력해 주십시오.');return;}
      window.printBomSheet(items[0], tds[0].dataset.gpc);};
    // ★생산이동전표 강제발행 = 재고이동 없이 전표 데이터만 등록(준비실적 없이 생산실적을 잡기 위한 우회).
    //   준비재고·자재창고·파트창고 일절 무변경. 체크박스로 선택한 행이 대상.
    g('#kt-move').onclick=async()=>{
      const sel=st.rows.filter((r,i)=>st.sel.has(i));
      if(!sel.length){alert('강제발행할 행을 선택하세요(체크박스).');return;}
      const rows=sel.map(r=>({item:r.item,gpc:r.gpc,ymd:r.part_ymd,qty:(+r.plan_qty||0)})).filter(r=>r.qty>0);
      if(!rows.length){alert('계획수량이 있는 행이 없습니다.');return;}
      const tot=rows.reduce((s,r)=>s+r.qty,0);
      if(!confirm(`생산이동전표 강제발행 — ${rows.length}건 (합계 ${nf(tot)})\n\n`
                 +`· 전표 데이터만 등록됩니다\n`
                 +`· 준비재고/자재창고/파트창고는 변동 없음\n`
                 +`· 준비실적 없이 생산실적을 잡기 위한 용도입니다`))return;
      try{
        const r=await fetch(`${API}/api/ready/force-sheet`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({rows,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹')})});
        const j=await r.json();
        if(j.ok){
          const ns=(j.issued||[]).map(x=>x.sheet_no);
          st.msg=`🚚 생산이동전표 강제발행 ${j.cnt}건 — 전표번호 ${ns.slice(0,5).join(', ')}${ns.length>5?` 외 ${ns.length-5}건`:''}`
                +(j.skipped&&j.skipped.length?` (제외 ${j.skipped.length})`:'');
          st.sel.clear();await load();
        }else alert('강제발행 실패: '+(j.detail||''));
      }catch(e){alert('강제발행 오류: '+e);}
    };
    {const sh=g('#kt-short');   // 버튼은 현재 숨김 — 되살리면 이 핸들러가 다시 붙음
     if(sh)sh.onclick=()=>alert('생산창고 재고과부족 확인: 준비재고 대비 소요 과부족 점검(레거시 연동 예정).');}
    const ka=g('#kt-all');if(ka)ka.onclick=e=>{const on=e.target.checked;st.sel.clear();
      host.querySelectorAll('.kt-chk').forEach(ch=>{ch.checked=on;if(on)(ch.dataset.idxs||'').split(',').filter(Boolean).map(Number).forEach(x=>st.sel.add(x));});
      const c=g('#kt-selcnt');if(c)c.textContent=st.sel.size;};
    wireKtRows();   // 체크박스·소계행 클릭(표만 다시 그릴 때도 재연결 필요)
    // ★미생산/구분/파트 = 재조회 없이 표만 즉시 갱신(캐시된 전체행에서 클라 필터/집계). 날짜·작업처·기간 변경만 [조회] 재fetch.
    host.querySelectorAll('input[name=kt-uf]').forEach(rb=>rb.onchange=()=>{st.unfin=rb.value;st.sel.clear();st.fold.clear();redrawBody();});
    host.querySelectorAll('input[name=kt-vw]').forEach(rb=>rb.onchange=()=>{st.view=rb.value;st.sel.clear();st.fold.clear();redrawBody();});
    g('#kt-part').onchange=()=>{st.part=g('#kt-part').value;st.sel.clear();st.fold.clear();redrawBody();};
    // 텍스트 필터(제번·ASSY도번·도번) = 180ms 디바운스 후 표만 갱신
    [['#kt-wo','wo'],['#kt-dono','dono'],['#kt-jado','jado']].forEach(([id,key])=>{const e=g(id);if(!e)return;
      e.oninput=()=>{clearTimeout(_typeT);const v=e.value.trim();
        _typeT=setTimeout(()=>{st[key]=v;st.sel.clear();st.fold.clear();redrawBody();},180);};});
    const sc=g('#kt-setchk');if(sc)sc.onclick=()=>openSetPopup(true);   // 조회전용(등록버튼 없음)
    // ★[확인(준비등록)]도 팝업 경유로 통일 — 자재 세트가능수량 확인 없이 바로 등록되면 안 됨.
    //   드래그선택이 있으면 그걸, 없으면 체크박스 선택행의 셀을 대상으로 팝업.
    if(ed){g('#kt-reg').onclick=()=>{
        if(!st.cellSel.size){alert('셀을 드래그해서 선택한 뒤 [확인(준비등록)]을 누르세요.');return;}
        openSetPopup();};
      g('#kt-can').onclick=()=>act('cancel');}
    // ★셀 우클릭 컨텍스트 메뉴(확인/취소) — canEdit 게이트. 마감/출고(fin 6)·완료(fin 4)·잔량0 은 확인 비활성.
    if(ed){
      const gw=host.querySelector('.grid-wrap');
      if(gw)gw.oncontextmenu=(ev)=>{
        const td=ev.target.closest('.kt-cell');
        if(!td){ktPlainMenu(ev);return;}                 // ★실적칸 밖 = 항목보기·복사 메뉴
        ev.preventDefault();
        // ★우클릭한 셀을 즉시 선택표시(2026-08-19) — 어느 칸에 메뉴를 띄웠는지 보이지 않아
        //   녹색(완료) 셀에서 특히 헷갈렸음. 이미 드래그선택에 포함된 셀이면 그 선택은 유지.
        if(!st.cellSel.has(cellKey(td))){selClear();selAdd(td);}
        const m={item:td.dataset.item,wo:td.dataset.wo,swo:td.dataset.swo,gpc:td.dataset.gpc,ymd:td.dataset.ymd,qty:+td.dataset.qty,done:+td.dataset.done||0,assy:td.dataset.assy,fin:td.dataset.fin};
        const canC=m.qty>0 && m.fin!=='4' && m.fin!=='6';   // 확인: 잔량>0·미완료(생산/출하완료 아님)
        const canX=m.done>0 && m.fin!=='6';                  // 취소: 등록수량>0·출하완료 셀 불가
        const old=document.getElementById('kt-ctxmenu'); if(old)old.remove();
        const mn=document.createElement('div'); mn.id='kt-ctxmenu';
        mn.style.cssText=`position:fixed;left:${ev.clientX}px;top:${ev.clientY}px;z-index:99999;background:#fff;border:1px solid #b8c4d4;border-radius:6px;box-shadow:0 3px 10px rgba(0,0,0,.25);font-size:12px;min-width:150px;overflow:hidden`;
        mn.innerHTML=`<div style="padding:5px 12px;background:#f2f6fb;color:#456;border-bottom:1px solid #e3e9f0">${esc(m.item)} · ${esc(dcol(m.ymd))} · 취소가능 ${nf(m.done)} / 잔량 ${nf(m.qty)}</div>`+
          `<div class="ktm" data-a="confirm" style="padding:7px 12px;cursor:${canC?'pointer':'not-allowed'};color:${canC?'#1c7c3a':'#c0c8d2'};font-weight:600">✅ 확인(준비등록) ${m.qty>0?nf(m.qty):''}</div>`+
          `<div class="ktm" data-a="cancel" style="padding:7px 12px;cursor:${canX?'pointer':'not-allowed'};color:${canX?'#c0392b':'#c0c8d2'};border-top:1px solid #eee">⏪ 준비취소 ${m.done>0?nf(m.done):''}</div>`+
          // ★항목보기·복사도 같은 메뉴에(2026-09-03) — 실적칸 위에서 우클릭해도 쓸 수 있게
          `<div class="ktm" data-a="col" style="padding:7px 12px;cursor:pointer;border-top:1px solid #ddd">항목보기</div>`+
          `<div class="ktm" data-a="copyall" style="padding:7px 12px;cursor:pointer">전체 복사</div>`;
        document.body.appendChild(mn);
        mn.querySelectorAll('.ktm').forEach(el=>el.onclick=()=>{const a=el.dataset.a;
          if(a==='col'){mn.remove();ktColPick();return;}
          if(a==='copyall'){mn.remove();if(host._ktCopyAll)host._ktCopyAll();return;}
          if((a==='confirm'&&!canC)||(a==='cancel'&&!canX))return; mn.remove();
          // ★확인 = 세트가능수량 팝업을 반드시 경유(자재 부족이면 실적 안 잡힘 + 이른날짜부터 순차충당).
          //   우클릭한 셀이 드래그선택에 포함돼 있으면 그 선택 전체를, 아니면 그 셀 하나만 대상으로 팝업.
          if(a==='confirm'){
            if(!st.cellSel.has(cellKey(td))){selClear();selAdd(td);}
            openSetPopup(); return;
          }
          cellAct(a,m);});   // 취소는 기존 셀단위 처리 유지
        setTimeout(()=>document.addEventListener('click',()=>{const x=document.getElementById('kt-ctxmenu');if(x)x.remove();},{once:true}),0);
      };
    }
    attachResizers(host);
  };
  /* ★자동조회 안 함(2026-09-03 사용자 요청, 410 과 동일).
       왜 — 진입할 때마다 6,000행 조회가 먼저 걸려 느리고, 조건(기준일자·파트·기간)을
       바꾸기도 전에 한 번 돌아 버린다. [조회] 를 눌러야 조회한다.
     ★항목보기 설정(계정별)은 먼저 받아둔다 — 늦게 오면 컬럼이 깜빡인다. */
  (async()=>{ await ktPrefLoad();
              st.msg='조건을 고르고 [조회] 를 누르세요.';
              render(); })();
};

/* ===== 생산전표출력관리 — 전표(J)/간판(G)/라벨(L) 조회·발행(nx.sheet_issue)·인쇄 ===== */
/* ★2026-08-19 전면 재구성 — 레거시 w_pr_input_490 구조(마스터-디테일).
   [이전] 계획 기준 단일 그리드 · 계획일자 조회
   [현재] 발행된 전표 기준 · ★출력기간(PRINT_DATETIME) 조회 · 생산완료(미완료 기본) 필터
     좌측    : 전표목록(전표번호·투입파트·계획일자·계획수량·도번·전표완료여부)
     우상단  : 공정상세 — 전표처리방법 J:전표 / G:가간판 (그 공정 실적을 뭘로 잡는지)
     우하단좌: 간판(PR_T_INDI_SHEET2)   우하단우: 라벨(PR_T_PRINT_STICKER)
   ※행 클릭 시 우측만 부분갱신(CLAUDE.md §3 마스터-디테일 스크롤 리셋 방지). */
SCREEN.prodsheet=(host)=>{
  const API=API_BASE;
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const T=new Date(), today=iso(T);
  const st={rows:[],cnt:0,sumQty:0,from:today,to:today,part:'',item:'',sheetNo:'',boxNo:'',labelNo:'',
            fin:'N',parts:[],agent:null,sel:new Set(),cur:null,det:null,loading:false,detLoading:false,msg:''};
  // ★프린터 2대 운용(레거시 w_pr_input_490 동일) — 제품스티커=라벨프린터 / 가간판·전표=A4프린터.
  //   웹은 보안상 프린터를 코드로 지정할 수 없다 → 작업 PC 에 트레이 에이전트를 두고
  //   웹은 kind(가간판/라벨)만 보낸다. 실제 프린터는 **그 PC 의 에이전트 설정**이 정한다.
  //   (종전엔 여기서 ERP서버 프린터 목록을 골랐지만, 현장 프린터는 각 PC 에 USB 로 물려 있어
  //    서버 목록은 애초에 대상이 아니었다 — 게다가 '메모용'이라 실제 출력엔 영향이 없었다.)
  //   에이전트 미설치 PC 는 기존 인쇄창 방식으로 자동 폴백된다.
  const agentChip=()=>{
    const a=st.agent;
    if(a===null||a===undefined)
      return `<span style="font-size:11px;color:#8a94a6">프린터 에이전트 확인 중…</span>`;
    if(a===false)
      // ★미설치 PC — 여기서 바로 받게 한다(USB 로 돌리면 반드시 빠지는 PC 가 생긴다).
      return `<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 9px;
                    background:#fff3f0;border:1px solid #ffbfae;border-radius:14px">
          <b style="font-size:11px;color:#c0392b">자동출력 꺼짐</b>
          <span style="font-size:11px;color:#8a5b52">이 PC 에 프린터 에이전트가 없어 <b>인쇄창</b>으로 출력합니다.</span>
        </span>
        <button class="btn" id="ps-agent-dl" style="height:24px;padding:0 10px;font-size:11px;
                background:#1c7c3a;color:#fff;border-color:#1c7c3a"
                title="설치파일을 받아 더블클릭하면 자동으로 설치됩니다">설치파일 받기</button>
        <span id="ps-agent-dlmsg" style="font-size:11px;color:#8a94a6"></span>`;
    const one=(tit,sz,nm,bg,bd,c1)=>`<span style="display:inline-flex;align-items:center;gap:5px;
          padding:3px 9px;background:${bg};border:1px solid ${bd};border-radius:14px">
        <b style="font-size:11px;color:${c1}">${tit}</b>
        <span style="font-size:10px;color:#7b8794">${sz}</span>
        <span style="font-size:11px;font-weight:700;color:${nm?'#1c7c3a':'#c0392b'}">
          ${nm?esc(nm):'미지정'}</span></span>`;
    return one('제품스티커','40×20',a.label_printer,'#fff7e6','#ffd591','#a06a00')
         + one('가간판·전표','210×110 / A4',a.kanban_printer,'#e6f7ff','#91d5ff','#0d6b9a')
         + `<span style="font-size:11px;color:#8a94a6">발행하면 <b>인쇄창 없이</b> 위 프린터로 바로 나갑니다
              — 변경은 작업표시줄의 <b>PNC 프린터 에이전트 → 설정</b>.</span>
            <a href="#" id="ps-agent-dl" style="font-size:11px;color:#5b7fa6"
               title="다른 PC 에 설치하거나 새 버전으로 갱신할 때">설치파일</a>
            <span id="ps-agent-dlmsg" style="font-size:11px;color:#8a94a6"></span>`;};
  const loadAgent=async(force)=>{
    const a=await PRN_AGENT.ping(force); st.agent=a||false;};
  const qsv=o=>new URLSearchParams(Object.entries(o).filter(([,v])=>v!==''&&v!=null)).toString();
  // ★자동출력 시도 — 성공하면 true(호출측은 즉시 return, 인쇄창 안 뜸).
  //   에이전트가 없거나 실패하면 false → 호출측이 기존 인쇄창 방식으로 계속 진행한다.
  //   urlFn(agent) = 서버에서 인쇄물(PDF/TSPL)을 받아올 URL.
  const tryAgent=async(kind,urlFn)=>{
    const ag=await PRN_AGENT.ping();
    if(!ag)return false;                       // 미설치 PC = 조용히 기존 방식
    const ready=kind==='label'?ag.ready_label:ag.ready_kanban;
    if(!ready){
      // 설치는 됐는데 프린터를 안 골랐다 — 알려주고 기존 방식으로 진행.
      st.msg=`${kind==='label'?'라벨':'가간판'} 프린터가 지정되지 않아 인쇄창으로 출력합니다 `
            +`(트레이의 "PNC 프린터 에이전트 → 설정"에서 지정).`;
      render();return false;
    }
    try{
      const r=await fetch(urlFn(ag));
      const j=await r.json();
      if(!j||!j.ok)throw new Error((j&&j.detail)||'인쇄물 생성 실패');
      const res=await PRN_AGENT.send(kind,{pdf:j.pdf,tspl:j.tspl,doc:j.doc});
      st.msg=`${j.doc} → ${res.printer} 로 출력했습니다.`;render();
      return true;
    }catch(e){
      // 실패해도 현장이 멈추면 안 된다 — 기존 인쇄창으로 넘긴다.
      st.msg=`자동출력 실패(${e.message}) — 인쇄창으로 출력합니다.`;render();
      return false;
    }
  };
  const loadParts=async()=>{try{const r=await fetch(`${API}/api/prodsheet/parts`);const j=await r.json();st.parts=j.rows||[];}catch(e){st.parts=[];}};
  const load=async()=>{st.loading=true;st.cur=null;st.det=null;render();
    const qs=qsv({from_ymd:st.from,to_ymd:st.to,part:st.part,item:st.item,
                  sheet_no:st.sheetNo,box_no:st.boxNo,label_no:st.labelNo,fin:st.fin,limit:2000});
    try{const r=await fetch(`${API}/api/prodsheet/list?${qs}`);const j=await r.json();
      st.rows=j.rows||[];st.cnt=j.cnt||0;st.sumQty=j.sum_qty||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];st.cnt=0;st.sumQty=0;}
    st.loading=false;st.sel.clear();render();};
  // ★행 클릭 = 우측 디테일만 교체(좌측 재렌더 X → 스크롤 유지)
  const loadDetail=async(sheetNo,tr)=>{
    if(tr){host.querySelectorAll('#ps-lbody tr').forEach(x=>x.classList.remove('ps-on'));tr.classList.add('ps-on');}
    st.cur=sheetNo;st.detLoading=true;paintDetail();
    try{const r=await fetch(`${API}/api/prodsheet/detail?sheet_no=${encodeURIComponent(sheetNo)}`);
      const j=await r.json();st.det=j.ok?j:null;}
    catch(e){st.det=null;}
    st.detLoading=false;paintDetail();};
  // ★nf/dcol 은 화면별 로컬 헬퍼(core.js의 것은 함수 내부 스코프라 밖에서 못 씀).
  //   (2026-08-19: 누락으로 가간판 팝업에서 "nf is not defined" 발생)
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const finBadge=f=>f==='1'?'<span class="bdg ok">완료</span>':'';
  // ── 우측 디테일(공정/간판/라벨) 부분갱신 ──────────────────────────────
  const paintDetail=()=>{
    const box=host.querySelector('#ps-det'); if(!box)return;
    if(!st.cur){box.innerHTML='<div class="s-item" style="padding:14px;color:var(--muted)">← 좌측에서 전표를 선택하세요</div>';return;}
    if(st.detLoading){box.innerHTML='<div class="s-item" style="padding:14px">불러오는 중…</div>';return;}
    const d=st.det||{procs:[],kanbans:[],labels:[]};
    const hdr=st.rows.find(r=>r.sheet_no===st.cur)||{};
    // 공정상세 — 전표처리방법(J:전표/G:가간판)이 그 공정 실적을 잡는 방법
    const pr=(d.procs||[]).map(p=>`<tr>
        <td class="center">${esc(p.part_nm||p.gpc)}</td>
        <td class="center">${esc(p.gpc)}</td>
        <td class="center">${p.seq}</td>
        <td class="center"><span class="bdg ${p.method==='J'?'ok':(p.method==='G'?'':'off')}">${esc(p.method_nm||'')}</span></td>
        <td class="center">${p.fin_flag==='1'?'완료':''}</td>
        <td class="num">${won(p.work_qty)}</td>
        <td class="num">${won(p.prod_qty)}</td>
        <td class="center" style="font-size:10px">${esc((p.sta_dt||'').slice(5,16).replace('T',' '))}</td>
        <td class="center" style="font-size:10px">${esc((p.fin_dt||'').slice(5,16).replace('T',' '))}</td>
        <td class="center">${esc(p.mach)}</td></tr>`).join('')
      ||`<tr><td colspan="10" class="empty">공정 정보 없음</td></tr>`;
    // 간판 — 분할본은 parent 표시
    // 간판 그리드 — 레거시 전 컬럼(재발행·간판번호·도번·계획수량·최초출력·분할·실적처리자
    //                ·생산처리일시·Line No·전표번호·삭제여부·분할전간판번호)
    const kb=(d.kanbans||[]).map(k=>{const del=k.del_flag==='1';
      return `<tr${del?' style="color:#aaa;text-decoration:line-through"':''}>
        <td class="center">${del?'':`<button class="btn ghost xs ps-kre" data-box="${k.box_no}" style="padding:1px 6px;font-size:10px">재발행</button>`}</td>
        <td class="center"><b>${k.box_no}</b></td>
        <td>${esc(k.item_code)}</td>
        <td class="num">${won(k.plan_qty)}</td>
        <td class="num">${won(k.org_qty)}</td>
        <td class="center">${del?'':`<button class="btn ghost xs ps-ksp" data-box="${k.box_no}" data-qty="${k.plan_qty}" style="padding:1px 6px;font-size:10px">분할</button>`}</td>
        <td class="center">${esc(k.prod_user||'')}</td>
        <td class="center" style="font-size:10px">${esc((k.prod_dt||'').replace('T',' '))}</td>
        <td class="center">${esc(k.line||'')}</td>
        <td class="center">${esc(k.sheet_no||'')}</td>
        <td class="center">${del?'<b style="color:#c0392b">삭제</b>':''}</td>
        <td class="center">${k.parent?k.parent:''}</td></tr>`;}).join('')
      ||`<tr><td colspan="12" class="empty">간판 없음</td></tr>`;
    // 라벨 그리드 — 레거시 전 컬럼(재발행·출력일자·라벨시작번호·도번·출력수량·출력담당자
    //                ·라벨출력일시·전표번호·작업처·작업자·시작번호·QR From/To)
    const lb=(d.labels||[]).map(l=>`<tr>
        <td class="center"><button class="btn ghost xs ps-lre" data-seq="${l.print_seq}" style="padding:1px 6px;font-size:10px">재발행</button></td>
        <td class="center">${esc(dcol(l.print_ymd))}</td>
        <td class="center"><b>${l.print_seq}</b></td>
        <td>${esc(l.item_code)}</td>
        <td class="num">${won(l.qty)}</td>
        <td class="center">${esc(l.print_user||'')}</td>
        <td class="center" style="font-size:10px">${esc((l.print_dt||'').replace('T',' '))}</td>
        <td class="center">${esc(l.sheet_no||'')}</td>
        <td class="center">${esc(l.work_code||'')}</td>
        <td class="center">${esc(l.worker_code||'')}</td>
        <td class="center">${l.start_no||''}</td>
        <td class="cap" style="font-size:10px;max-width:170px;overflow:hidden;text-overflow:ellipsis" title="${esc(l.qr_from)}">${esc(l.qr_from)}</td>
        <td class="cap" style="font-size:10px;max-width:170px;overflow:hidden;text-overflow:ellipsis" title="${esc(l.qr_to)}">${esc(l.qr_to)}</td></tr>`).join('')
      ||`<tr><td colspan="13" class="empty">라벨 없음</td></tr>`;
    box.innerHTML=`
      <div class="grid-wrap" style="flex:0 0 auto;max-height:190px;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:6px">
        <table class="tbl fit" style="font-size:11px"><thead><tr>
          <th class="center">파트명</th><th class="center">공정코드</th><th class="center">SEQ</th>
          <th class="center">전표처리방법</th><th class="center">작업완료</th><th class="num">작업수량</th>
          <th class="num">생산실적</th><th class="center">시작</th><th class="center">종료</th><th class="center">설비</th>
        </tr></thead><tbody>${pr}</tbody></table></div>
      <div style="display:flex;gap:8px;flex:1 1 auto;min-height:0;margin-top:6px">
        <div style="flex:1 1 48%;min-width:0;display:flex;flex-direction:column">
          <div style="font-size:11px;font-weight:700;color:#456;margin-bottom:2px">가간판 <span style="font-weight:400;color:var(--muted)">${(d.kanbans||[]).length}건</span></div>
          <div class="grid-wrap" style="flex:1 1 auto;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:6px">
            <table class="tbl" style="font-size:11px;min-width:920px"><thead><tr>
              <th class="center" style="width:48px">재발행</th><th class="center">간판번호</th><th>도번</th>
              <th class="num">계획수량</th><th class="num">최초출력</th><th class="center" style="width:44px">분할</th>
              <th class="center">실적처리자</th><th class="center">생산처리일시</th><th class="center">Line No</th>
              <th class="center">전표번호</th><th class="center">삭제여부</th><th class="center">분할전간판</th>
              </tr></thead><tbody>${kb}</tbody></table></div>
        </div>
        <div style="flex:1 1 52%;min-width:0;display:flex;flex-direction:column">
          <div style="font-size:11px;font-weight:700;color:#456;margin-bottom:2px">제품스티커(라벨) <span style="font-weight:400;color:var(--muted)">${(d.labels||[]).length}건</span></div>
          <div class="grid-wrap" style="flex:1 1 auto;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:6px">
            <table class="tbl" style="font-size:11px;min-width:1100px"><thead><tr>
              <th class="center" style="width:48px">재발행</th><th class="center">출력일자</th><th class="center">라벨시작번호</th>
              <th>도번</th><th class="num">출력수량</th><th class="center">출력담당자</th>
              <th class="center">라벨출력일시</th><th class="center">전표번호</th><th class="center">작업처</th>
              <th class="center">작업자</th><th class="center">시작번호</th>
              <th class="center">QR From</th><th class="center">QR To</th></tr></thead><tbody>${lb}</tbody></table></div>
        </div>
      </div>`;
    // 재발행/분할 버튼 — 2단계에서 연결
    // 재발행 = 새 채번 없이 그 간판을 다시 인쇄(바코드 동일 → 실적 연결 유지)
    box.querySelectorAll('.ps-kre').forEach(b=>b.onclick=()=>printKanban([b.dataset.box]));
    // 재발행 = 시작/종료번호 지정 팝업 → 새 채번 없이 같은 QR로 재인쇄(실적 연결 유지)
    box.querySelectorAll('.ps-lre').forEach(b=>b.onclick=()=>openLabelReprint(b.dataset.seq));
    box.querySelectorAll('.ps-ksp').forEach(b=>b.onclick=()=>openSplit(+b.dataset.box,+b.dataset.qty));
  };
  // ── 좌측 전표목록 본문만 그리기 ───────────────────────────────────────
  const leftBody=()=>st.loading?spinRow(8)
    :(st.rows.length?st.rows.map((r,i)=>`<tr data-sn="${esc(r.sheet_no)}" data-i="${i}" class="${st.cur===r.sheet_no?'ps-on':''}" style="cursor:pointer">
        <td class="center"><input type="checkbox" class="ps-chk" data-i="${i}" ${st.sel.has(i)?'checked':''}></td>
        <td class="center"><b>${esc(r.sheet_no)}</b></td>
        <td class="center">${esc(r.gpc_nm||r.gpc||'')}</td>
        <td class="center">${esc(dcol(r.plan_ymd))}</td>
        <td class="num">${won(r.plan_qty)}</td>
        <td><b>${esc(r.item_code)}</b></td>
        <td class="cap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="center">${finBadge(r.fin_flag)}</td>
        <td class="center">${r.gcnt?`<b style="color:#1c7c3a">${r.gcnt}</b>`:'-'}</td>
        <td class="center">${r.lcnt?`<b style="color:#b8860b">${r.lcnt}</b>`:'-'}</td></tr>`).join('')
      :`<tr><td colspan="10" class="empty">조회 결과 없음 — 출력기간/생산완료 조건을 조정하세요</td></tr>`);
  const wireLeft=()=>{
    host.querySelectorAll('#ps-lbody tr[data-sn]').forEach(tr=>{
      tr.onclick=(e)=>{if(e.target.closest('input,button'))return;loadDetail(tr.dataset.sn,tr);};});
    host.querySelectorAll('.ps-chk').forEach(ch=>ch.onclick=(e)=>{
      e.stopPropagation();const i=+ch.dataset.i;ch.checked?st.sel.add(i):st.sel.delete(i);
      const a=host.querySelector('#ps-all');if(a)a.checked=false;
      const c=host.querySelector('#ps-selcnt');if(c)c.textContent=st.sel.size;});
  };
  const selRows=()=>st.rows.filter((r,i)=>st.sel.has(i));
  // ── 발행 버튼(2·3단계에서 팝업 연결) ─────────────────────────────────
  // ★가간판 발행 팝업(레거시 w_pr_input_468) — 포장수량 입력 → 자동분할 → 인쇄 시 저장+출력
  //   포장수량 기본값 = PR_M_ITEM_SUB.PACK_QTY. 변경 후 [다시 작성]하면 새 단위로 재분할.
  const openKanban=async()=>{const rows=selRows();
    if(!rows.length){alert('가간판을 발행할 전표를 선택하세요(체크박스).');return;}
    if(rows.length>1){alert('가간판은 전표 1건씩 발행합니다.');return;}
    const sn=rows[0].sheet_no;
    let pv;
    try{const r=await fetch(`${API}/api/prodsheet/kanban-preview?sheet_no=${encodeURIComponent(sn)}`);pv=await r.json();}
    catch(e){alert('조회 실패: '+e);return;}
    if(!pv||!pv.ok){alert('조회 실패: '+((pv&&pv.detail)||''));return;}
    // ★모달은 document.body에 렌더(CLAUDE.md §3 — .content 안에 넣으면 잘림)
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1200;display:flex;align-items:center;justify-content:center';
    const close=()=>ov.remove();
    const draw=()=>{
      const parts=pv.parts||[];
      ov.innerHTML=`<div style="background:#fff;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.3);width:660px;max-width:94vw;max-height:90vh;display:flex;flex-direction:column">
        <div style="padding:10px 14px;border-bottom:1px solid #e3e9f0;font-weight:700;display:flex;align-items:center;gap:8px">
          🏷 가간판 출력 <span style="font-size:12px;color:var(--muted);font-weight:400">전표 ${esc(pv.sheet_no)} · ${esc(pv.item)}</span>
          <div style="flex:1"></div><button class="btn ghost" id="kb-x" style="padding:2px 10px">✕</button></div>
        <div style="padding:12px 14px;overflow:auto">
          <table class="tbl" style="width:100%;font-size:12px;margin-bottom:10px">
            <tr><th class="lbl" style="width:80px;background:#f2f6fb">품번</th><td><b>${esc(pv.item)}</b></td>
                <th class="lbl" style="width:80px;background:#f2f6fb">품명</th><td colspan="3">${esc(pv.nm)}</td></tr>
            <tr><th class="lbl" style="background:#f2f6fb">포장BOX</th>
                <td><input class="inp" id="kb-kind" value="${esc(pv.pack_kind)}" style="width:96%;min-width:0;height:26px"></td>
                <th class="lbl" style="background:#f2f6fb">포장수량</th>
                <td><input class="inp" id="kb-pack" type="number" min="0" value="${pv.pack_qty}" style="width:80px;min-width:0;height:26px;background:#ffffcc;font-weight:700"></td>
                <th class="lbl" style="background:#f2f6fb;width:60px">계획</th><td><b>${nf(pv.plan_qty)}</b></td></tr>
            <tr><th class="lbl" style="background:#f2f6fb">생산자</th><td>${esc(pv.prod_worker)}</td>
                <th class="lbl" style="background:#f2f6fb">검사자</th><td>${esc(pv.insp_worker)}</td>
                <th class="lbl" style="background:#f2f6fb">잔여</th><td><b style="color:${pv.remain>0?'#1c7c3a':'#c0392b'}">${nf(pv.remain)}</b>${pv.issued_qty>0?`<span style="color:#888;font-size:11px"> (기발행 ${nf(pv.issued_qty)})</span>`:''}</td></tr>
            <tr><th class="lbl" style="background:#f2f6fb">대상공정</th><td colspan="5">${(pv.procs||[]).map(p=>`${esc(p.gpc)} ${esc(p.nm)}`).join(' · ')||'<span style="color:#c0392b">없음</span>'}</td></tr>
          </table>
          ${pv.warn?`<div style="background:#fff6e5;border:1px solid #f0d9a8;border-radius:6px;padding:6px 10px;font-size:12px;color:#8a6d1f;margin-bottom:8px">⚠ ${esc(pv.warn)}</div>`:''}
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <b style="font-size:12px">발행 예정 ${parts.length}장</b>
            <button class="btn ghost" id="kb-redo" style="padding:2px 10px;font-size:11px">🔄 가간판 다시 작성</button>
            <div style="flex:1"></div>
            <span style="font-size:11px;color:var(--muted)">합계 ${nf(parts.reduce((s,x)=>s+x,0))}</span></div>
          <div class="grid-wrap" style="max-height:230px;overflow:auto;border:1px solid var(--line-2,#c9d3e0);border-radius:6px">
            <table class="tbl fit" style="font-size:12px"><thead><tr>
              <th class="center" style="width:44px">SEQ</th><th>품번</th><th class="num" style="width:110px">간판수량</th></tr></thead>
            <tbody>${parts.length?parts.map((q,i)=>`<tr>
                <td class="center">${i+1}</td><td>${esc(pv.item)}</td>
                <td class="num"><b>${nf(q)}</b></td></tr>`).join('')
              :`<tr><td colspan="3" class="empty">발행할 수량이 없습니다</td></tr>`}</tbody></table></div>
        </div>
        <div style="padding:10px 14px;border-top:1px solid #e3e9f0;display:flex;gap:6px;justify-content:flex-end">
          <button class="btn ghost" id="kb-close">닫기</button>
          <button class="btn" id="kb-print" ${parts.length?'':'disabled'} style="background:${parts.length?'#1c7c3a':'#c0c8d2'};color:#fff">🖨 인쇄(저장+출력)</button></div>
      </div>`;
      const q=id=>ov.querySelector(id);
      q('#kb-x').onclick=close;q('#kb-close').onclick=close;
      // 포장수량 변경 → 재분할(서버 재계산)
      const redo=async()=>{const p=+q('#kb-pack').value||0;
        try{const r=await fetch(`${API}/api/prodsheet/kanban-preview?sheet_no=${encodeURIComponent(sn)}&pack_qty=${p}`);
          const j=await r.json();if(j&&j.ok){const kind=q('#kb-kind').value;pv=j;pv.pack_kind=kind;draw();}}
        catch(e){alert('재계산 실패: '+e);}};
      q('#kb-redo').onclick=redo;
      q('#kb-pack').onkeyup=e=>{if(e.key==='Enter')redo();};
      if(parts.length)q('#kb-print').onclick=async()=>{
        if(!confirm(`가간판 ${parts.length}장 발행할까요?\n\n· 간판번호(BOX_NO) 채번 후 저장\n· 재고/실적 변동 없음\n· 저장 후 A4 1/3 양식으로 출력`))return;
        const btn=q('#kb-print');btn.disabled=true;btn.textContent='발행 중…';
        try{
          const r=await fetch(`${API}/api/prodsheet/kanban-issue`,{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({sheet_no:sn,pack_qty:+q('#kb-pack').value||0,qtys:parts,
                                 user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})});
          const j=await r.json();
          if(j.ok){close();
            st.msg=`🏷 가간판 ${j.cnt}장 발행 — 간판번호 ${j.issued.map(x=>x.box_no).slice(0,4).join(', ')}${j.cnt>4?` 외 ${j.cnt-4}장`:''}`;
            printKanban(j.issued.map(x=>x.box_no));
            await load();
          }else{alert('발행 실패: '+(j.detail||''));btn.disabled=false;btn.textContent='🖨 인쇄(저장+출력)';}
        }catch(e){alert('발행 오류: '+e);btn.disabled=false;btn.textContent='🖨 인쇄(저장+출력)';}
      };
    };
    draw();document.body.appendChild(ov);
    ov.onclick=e=>{if(e.target===ov)close();};
  };
  // ★제품스티커(라벨) 발행 팝업(레거시 w_pr_input_469) — 출력수량·용접사·검사자 입력 → 저장+인쇄
  //   QR = 도번+KPI+연월일+일련4 (도번×출력일자 단위 누적). 바코드종류는 QR3만 구현.
  const openLabel=async()=>{const rows=selRows();
    if(!rows.length){alert('제품스티커를 발행할 전표를 선택하세요(체크박스).');return;}
    if(rows.length>1){alert('제품스티커는 전표 1건씩 발행합니다.');return;}
    const sn=rows[0].sheet_no;
    let pv;
    try{const r=await fetch(`${API}/api/prodsheet/label-preview?sheet_no=${encodeURIComponent(sn)}`);pv=await r.json();}
    catch(e){alert('조회 실패: '+e);return;}
    if(!pv||!pv.ok){alert('조회 실패: '+((pv&&pv.detail)||''));return;}
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1200;display:flex;align-items:center;justify-content:center';
    const close=()=>ov.remove();
    const draw=()=>{
      const q=+((ov.querySelector('#lb-qty')||{}).value)||pv.qty||0;
      ov.innerHTML=`<div style="background:#fff;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.3);width:1000px;max-width:97vw">
        <div style="padding:10px 14px;border-bottom:1px solid #e3e9f0;font-weight:700;display:flex;align-items:center;gap:8px">
          🔖 라벨출력 <span style="font-size:12px;color:var(--muted);font-weight:400">전표 ${esc(pv.sheet_no)} · ${esc(pv.item)}</span>
          <div style="flex:1"></div><button class="btn ghost" id="lb-x" style="padding:2px 10px">✕</button></div>
        <div style="padding:12px 14px">
          <div class="grid-wrap" style="border:1px solid var(--line-2,#c9d3e0);border-radius:6px;margin-bottom:8px;overflow:visible">
            <table class="tbl" style="font-size:12px;width:100%;table-layout:fixed"><thead><tr>
              <th class="center" style="width:40px">SEQ</th><th style="width:130px">품번</th><th>품명</th>
              <th class="num" style="width:76px">계획수량</th><th class="num" style="width:96px">출력수량</th>
              <th style="width:120px">용접사</th><th style="width:120px">검사자</th>
              <th class="center" style="width:96px">바코드종류</th></tr></thead>
            <tbody><tr>
              <td class="center">1</td><td><b>${esc(pv.item)}</b></td>
              <td class="cap" style="max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${esc(pv.nm)}">${esc(pv.nm)}</td>
              <td class="num">${nf(pv.plan_qty)}</td>
              <td class="num"><input class="inp" id="lb-qty" type="number" min="1" value="${q}"
                   style="width:78px;min-width:0;height:26px;text-align:right;background:#ffffcc;font-weight:700"></td>
              <td><input class="inp" id="lb-w" value="${esc(pv.prod_worker)}" style="width:112px;min-width:0;height:26px"></td>
              <td><input class="inp" id="lb-i" value="${esc(pv.insp_worker)}" style="width:112px;min-width:0;height:26px"></td>
              <td class="center"><select class="sel" id="lb-kind" style="width:80px;min-width:0;height:26px;padding:0 4px">
                <option value="QR3" selected>QR3</option></select></td></tr></tbody></table></div>
          <table class="tbl" style="width:100%;font-size:12px">
            <tr><th class="lbl" style="width:90px;background:#f2f6fb">출력일자</th><td>${esc(dcol(pv.print_ymd))} <span style="color:#888">(${esc(pv.datecode)})</span></td>
                <th class="lbl" style="width:70px;background:#f2f6fb">잔여</th>
                <td><b style="color:${pv.remain>0?'#1c7c3a':'#c0392b'}">${nf(pv.remain)}</b>${pv.issued_qty>0?`<span style="color:#888;font-size:11px"> (기발행 ${nf(pv.issued_qty)})</span>`:''}</td></tr>
            <tr><th class="lbl" style="background:#f2f6fb">QR 범위</th><td colspan="3" id="lb-qr" style="font-family:monospace;font-size:11px">${esc(pv.qr_from)} ~ ${esc(pv.qr_to)}</td></tr>
          </table>
          <div style="font-size:11px;color:#888;margin-top:6px">※일련번호는 <b>도번×출력일자</b> 단위로 누적됩니다(같은 날 추가 발행 시 이어짐).</div>
        </div>
        <div style="padding:10px 14px;border-top:1px solid #e3e9f0;display:flex;gap:6px;justify-content:flex-end">
          <button class="btn ghost" id="lb-close">닫기</button>
          <button class="btn" id="lb-save" style="background:#b8860b;color:#fff">🖨 저장+인쇄</button></div>
      </div>`;
      const g=id=>ov.querySelector(id);
      g('#lb-x').onclick=close;g('#lb-close').onclick=close;
      // 수량 변경 → QR 범위 재계산
      g('#lb-qty').oninput=async()=>{const v=+g('#lb-qty').value||0;
        if(v<=0)return;
        try{const r=await fetch(`${API}/api/prodsheet/label-preview?sheet_no=${encodeURIComponent(sn)}&qty=${v}`);
          const j=await r.json();
          if(j&&j.ok){const e=g('#lb-qr');if(e)e.textContent=`${j.qr_from} ~ ${j.qr_to}`;}}catch(e){}};
      g('#lb-save').onclick=async()=>{
        const qty=+g('#lb-qty').value||0;
        if(qty<=0){alert('출력수량을 입력하세요.');return;}
        if(!confirm(`제품스티커 ${nf(qty)}장 발행할까요?\n\n· 라벨번호 채번 후 저장\n· 재고/실적 변동 없음\n· 저장 후 낱장 QR 라벨 인쇄`))return;
        const btn=g('#lb-save');btn.disabled=true;btn.textContent='발행 중…';
        try{
          const r=await fetch(`${API}/api/prodsheet/label-issue`,{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({sheet_no:sn,qty,worker:g('#lb-w').value.trim(),inspector:g('#lb-i').value.trim(),
                                 user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})});
          const j=await r.json();
          if(j.ok){close();
            st.msg=`🔖 제품스티커 ${nf(j.qty)}장 발행 — 라벨번호 ${j.print_seq} (${j.qr_from} ~ ${j.qr_to})`;
            printLabel(j.print_seq);
            await load();
          }else{alert('발행 실패: '+(j.detail||''));btn.disabled=false;btn.textContent='🖨 저장+인쇄';}
        }catch(e){alert('발행 오류: '+e);btn.disabled=false;btn.textContent='🖨 저장+인쇄';}
      };
    };
    draw();document.body.appendChild(ov);
    ov.onclick=e=>{if(e.target===ov)close();};
  };
  // ★라벨 재발행 팝업(레거시 w_pr_input_469 "수정") — 시작/종료번호로 범위 지정해 재출력.
  //   새 채번 없음(QR 동일 → 실적 연결 유지). 용접사·검사자는 이번 출력분에만 반영.
  const openLabelReprint=async(printSeq)=>{
    let j;
    try{const r=await fetch(`${API}/api/prodsheet/label-print?print_seq=${encodeURIComponent(printSeq)}`);j=await r.json();}
    catch(e){alert('라벨 조회 실패: '+e);return;}
    if(!j||!j.ok){alert('라벨 조회 실패: '+((j&&j.detail)||''));return;}
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1200;display:flex;align-items:center;justify-content:center';
    const close=()=>ov.remove();
    ov.innerHTML=`<div style="background:#fff;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.3);width:1060px;max-width:97vw">
      <div style="padding:10px 14px;border-bottom:1px solid #e3e9f0;font-weight:700;display:flex;align-items:center;gap:8px">
        🔖 라벨출력 <span style="font-size:12px;color:#c0392b;font-weight:700">— 재발행</span>
        <span style="font-size:12px;color:var(--muted);font-weight:400">라벨번호 ${j.print_seq} · ${esc(j.item)}</span>
        <div style="flex:1"></div><button class="btn ghost" id="rp-x" style="padding:2px 10px">✕</button></div>
      <div style="padding:12px 14px">
        <div class="grid-wrap" style="border:1px solid var(--line-2,#c9d3e0);border-radius:6px;margin-bottom:8px;overflow:visible">
          <table class="tbl" style="font-size:12px;width:100%;table-layout:fixed"><thead><tr>
            <th class="center" style="width:40px">SEQ</th><th style="width:130px">품번</th><th>품명</th>
            <th class="num" style="width:76px">출력수량</th>
            <th class="num" style="width:96px">시작번호</th><th class="num" style="width:96px">종료번호</th>
            <th style="width:120px">용접사</th><th style="width:120px">검사자</th>
            <th class="center" style="width:96px">바코드종류</th></tr></thead>
          <tbody><tr>
            <td class="center">1</td><td><b>${esc(j.item)}</b></td>
            <td class="cap" style="max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${esc(j.nm)}">${esc(j.nm)}</td>
            <td class="num"><b id="rp-cnt">${nf(j.qty)}</b></td>
            <!-- ★시작/종료 = 순번(1부터). 1~50 이면 50장, 30~50 이면 21장(2026-08-28) -->
            <td class="num"><input class="inp" id="rp-s" type="number" min="1" max="${j.org_qty}" value="${j.start_no}"
                 title="몇 번째 라벨부터 (1 ~ ${j.org_qty})"
                 style="width:78px;min-width:0;height:26px;text-align:right;background:#ffffcc;font-weight:700"></td>
            <td class="num"><input class="inp" id="rp-e" type="number" min="1" max="${j.org_qty}" value="${j.end_no}"
                 title="몇 번째 라벨까지 (1 ~ ${j.org_qty})"
                 style="width:78px;min-width:0;height:26px;text-align:right"></td>
            <td><input class="inp" id="rp-w" value="${esc(j.worker||'')}" style="width:112px;min-width:0;height:26px"></td>
            <td><input class="inp" id="rp-i" value="${esc(j.inspector||'')}" style="width:112px;min-width:0;height:26px"></td>
            <td class="center"><select class="sel" id="rp-kind" style="width:80px;min-width:0;height:26px;padding:0 4px">
              <option value="QR3" selected>QR3</option></select></td></tr></tbody></table></div>
        <table class="tbl" style="width:100%;font-size:12px">
          <tr><th class="lbl" style="width:90px;background:#f2f6fb">출력일자</th><td>${esc(dcol(j.print_ymd))}</td>
              <th class="lbl" style="width:90px;background:#f2f6fb">발행범위</th><td id="rp-rng">1 ~ ${nf(j.org_qty)} (총 ${nf(j.org_qty)}장) <span style="color:#888">· QR ${esc(j.abs_org_start)}~${esc(j.abs_org_end)}</span></td></tr>
          <tr><th class="lbl" style="background:#f2f6fb">QR 범위</th><td colspan="3" id="rp-qr" style="font-family:monospace;font-size:11px">${esc(j.qr_from)} ~ ${esc(j.qr_to)}</td></tr>
        </table>
        <div style="font-size:11px;color:#888;margin-top:6px">※재발행은 <b>새 채번 없이</b> 같은 QR로 다시 인쇄합니다(실적 연결 유지).</div>
      </div>
      <div style="padding:10px 14px;border-top:1px solid #e3e9f0;display:flex;gap:6px;justify-content:flex-end">
        <button class="btn ghost" id="rp-close">닫기</button>
        <button class="btn" id="rp-print" style="background:#b8860b;color:#fff">🖨 재출력</button></div>
    </div>`;
    const g=id=>ov.querySelector(id);
    g('#rp-x').onclick=close;g('#rp-close').onclick=close;
    const sync=async()=>{
      // ★순번 기준(1 ~ 총장수). 서버도 같은 규칙으로 클램프한다.
      let s=+g('#rp-s').value||1, e=+g('#rp-e').value||j.org_qty;
      s=Math.max(1,Math.min(s,j.org_qty));
      e=Math.max(s,Math.min(e,j.org_qty));
      try{const r=await fetch(`${API}/api/prodsheet/label-print?print_seq=${encodeURIComponent(printSeq)}&start_no=${s}&end_no=${e}`);
        const k=await r.json();
        if(k&&k.ok){g('#rp-cnt').textContent=nf(k.qty);g('#rp-qr').textContent=`${k.qr_from} ~ ${k.qr_to}`;}}catch(e2){}};
    g('#rp-s').oninput=sync;g('#rp-e').oninput=sync;
    g('#rp-print').onclick=()=>{
      const s=+g('#rp-s').value||1, e=+g('#rp-e').value||j.org_qty;   // 순번 기준
      close();
      printLabel(printSeq,{start:s,end:e,worker:g('#rp-w').value.trim(),inspector:g('#rp-i').value.trim()});
    };
    document.body.appendChild(ov);
    ov.onclick=e=>{if(e.target===ov)close();};
  };
  // ★제품스티커(QR3) 인쇄 — 낱장 연속. 레거시 양식 실측:
  //   좌상단 QR / PNC Industry / {출력일자} {라벨번호}-{일련4} / n / 전체 / 도번 / 용접사/검사자
  const printLabel=async(printSeq,opt)=>{
    let j;
    const o=opt||{};
    const qs=new URLSearchParams({print_seq:printSeq});
    if(o.start)qs.set('start_no',o.start);
    if(o.end)qs.set('end_no',o.end);
    if(o.worker)qs.set('worker',o.worker);
    if(o.inspector)qs.set('inspector',o.inspector);
    // ★에이전트가 살아있으면 인쇄창 없이 라벨프린터로 바로 출력.
    //   출력방식(TSPL 직송/PDF)은 그 PC 의 에이전트 설정을 따른다.
    if(await tryAgent('label',ag=>{
        const q=new URLSearchParams(qs);
        q.set('mode',(ag&&ag.label_mode)==='tspl'?'tspl':'pdf');
        return `${API}/api/print/label?${q}`;}))return;
    try{const r=await fetch(`${API}/api/prodsheet/label-print?${qs}`);j=await r.json();}
    catch(e){alert('라벨 조회 실패: '+e);return;}
    if(!j||!j.ok){alert('라벨 조회 실패: '+((j&&j.detail)||''));return;}
    const one=L=>`<div class="lb">
      <img class="qr" src="${API}/api/barcode/qr?text=${encodeURIComponent(L.qr)}&scale=3&border=1" alt="${esc(L.qr)}">
      <div class="tx">
        <div class="t1">PNC Industry</div>
        <div class="t2">${esc(L.disp)}</div>
        <div class="t3">${L.n} / ${j.org_qty||j.qty}</div>
        <div class="t4">${esc(j.item)}</div>
        <div class="t5">${esc(j.worker||'')}/${esc(j.inspector||'')}</div>
      </div></div>`;
    // ★실제 URL(print.html?t=label)로 연다 — about:blank 는 프린터 선택이 기억되지 않는다.
    const w=await openPrintWin('label','pncPrnLabel','width=760,height=1000');
    if(!w){alert('팝업이 차단되었습니다. 브라우저 팝업 허용 후 다시 시도하세요.');return;}
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>제품스티커 ${esc(j.item)} (${j.qty}장)</title>
    <style>
      /* ★QR3 라벨 규격 = 40mm × 20mm (라벨프린터 낱장). */
      @page{size:40mm 20mm;margin:0}
      *{box-sizing:border-box}
      body{margin:0;font-family:'맑은 고딕',Malgun Gothic,sans-serif;color:#000}
      /* 낱장 라벨 — 좌측 QR + 우측 텍스트. 1장=1페이지 */
      .lb{display:flex;align-items:center;gap:1mm;width:40mm;height:20mm;padding:1mm;
          page-break-after:always;page-break-inside:avoid;overflow:hidden}
      .lb:last-child{page-break-after:auto}
      .lb .qr{width:17mm;height:17mm;image-rendering:pixelated;flex:0 0 auto}
      .lb .tx{flex:1 1 auto;min-width:0;text-align:center;line-height:1.15}
      .t1{font-size:7pt;letter-spacing:1px}
      .t2{font-size:5.5pt;letter-spacing:.2px}
      .t3{font-size:7pt;font-weight:700;text-align:right;padding-right:1mm}
      .t4{font-size:8pt;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .t5{font-size:6.5pt;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      /* 화면 미리보기에서는 낱장 경계를 보이게(인쇄 시 테두리 없음) */
      @media screen{ .lb{border:1px dashed #bbb;margin:0 0 2mm 0} }
      @media print{.noprint{display:none}}
    </style></head><body>
    <div class="noprint" style="margin-bottom:6px">
      <button onclick="window.print()" style="padding:6px 16px;font-size:13px">🖨 인쇄</button>
      <button onclick="window.close()" style="padding:6px 16px;font-size:13px">닫기</button>
      <span style="font-size:12px;color:#555;margin-left:8px">제품스티커 ${j.qty}장 · 라벨번호 ${j.print_seq} · QR3 · 40×20mm</span>
      <div style="margin-top:6px;padding:6px 10px;background:#fff7e6;border:1px solid #ffd591;border-radius:4px;font-size:12px">
        <b>라벨프린터(40×20)를 인쇄창에서 고르세요.</b>
        <span style="color:#8c6d1f">— 한 번 고르면 다음부터 자동 선택됩니다.
          이 PC 에 <b>PNC 프린터 에이전트</b>를 설치하면 인쇄창 없이 바로 출력됩니다.</span>
      </div></div>
    ${(j.labels||[]).map(one).join('')}
    <script>
      (function(){var imgs=[].slice.call(document.images),left=imgs.length;
        function go(){setTimeout(function(){window.print();},300);}
        if(!left)return go();
        imgs.forEach(function(im){if(im.complete)done();else{im.addEventListener('load',done);im.addEventListener('error',done);}});
        function done(){if(--left<=0)go();}})();
    <\/script></body></html>`);
    w.document.close();
  };
  // ★간판 분할 팝업(레거시 w_pr_input_495) — 대차/박스에 나눠 담기 위해 간판 1장을 여러 장으로.
  //   [동작] 원본을 삭제표시(DELETE_FLAG='1') + 분할본을 새 BOX_NO로 생성(PARENT_BOX_NO=원본)
  //   [제약] 분할수량 합계 = 원본수량. 실적 잡힌 간판은 분할 불가.
  const openSplit=(boxNo,orgQty)=>{
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1200;display:flex;align-items:center;justify-content:center';
    const close=()=>ov.remove();
    let rows=[{q:''},{q:''},{q:''},{q:''},{q:''}];   // 레거시처럼 5줄 기본
    const draw=()=>{
      const sum=rows.reduce((s,r)=>s+(+r.q||0),0);
      const left=Math.round((orgQty-sum)*10000)/10000;
      const okAll=Math.abs(left)<0.0001 && rows.filter(r=>+r.q>0).length>=2;
      ov.innerHTML=`<div style="background:#fff;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.3);width:520px;max-width:94vw">
        <div style="padding:10px 14px;border-bottom:1px solid #e3e9f0;font-weight:700;display:flex;align-items:center;gap:8px">
          ✂ 간판분할 <span style="font-size:12px;color:var(--muted);font-weight:400">간판 ${boxNo} · 원본수량 ${nf(orgQty)}</span>
          <div style="flex:1"></div><button class="btn ghost" id="sp-x" style="padding:2px 10px">✕</button></div>
        <div style="padding:12px 14px">
          <div style="font-size:12px;color:#666;margin-bottom:6px">분할수량을 입력하세요. <b>합계가 원본수량(${nf(orgQty)})과 같아야</b> 저장됩니다.</div>
          <div class="grid-wrap" style="max-height:260px;overflow:auto;border:1px solid var(--line-2,#c9d3e0);border-radius:6px">
            <table class="tbl fit" style="font-size:12px"><thead><tr>
              <th class="center" style="width:44px">SEQ</th><th class="center">간판번호</th><th>품번</th>
              <th class="num" style="width:90px">간판수량</th><th class="num" style="width:110px">분할수량</th></tr></thead>
            <tbody>${rows.map((r,i)=>`<tr>
                <td class="center">${i+1}</td>
                <td class="center">${i===0?String(boxNo).padStart(8,'0'):''}</td>
                <td>${i===0?esc(st.det&&st.det.kanbans?(st.det.kanbans.find(k=>k.box_no===boxNo)||{}).item_code||'':''):''}</td>
                <td class="num">${i===0?nf(orgQty):''}</td>
                <td class="num"><input class="inp sp-q" data-i="${i}" type="number" min="0" value="${r.q}"
                     style="width:92px;min-width:0;height:24px;text-align:right;background:#ffffcc"></td></tr>`).join('')}
            </tbody></table></div>
          <div style="display:flex;gap:10px;margin-top:8px;font-size:12px;align-items:center">
            <button class="btn ghost" id="sp-add" style="padding:2px 10px;font-size:11px">＋ 줄 추가</button>
            <div style="flex:1"></div>
            <span>합계 <b>${nf(sum)}</b></span>
            <span>잔여 <b style="color:${Math.abs(left)<0.0001?'#1c7c3a':'#c0392b'}">${nf(left)}</b></span></div>
        </div>
        <div style="padding:10px 14px;border-top:1px solid #e3e9f0;display:flex;gap:6px;justify-content:flex-end">
          <button class="btn ghost" id="sp-close">닫기</button>
          <button class="btn" id="sp-save" ${okAll?'':'disabled'} style="background:${okAll?'#1c47a0':'#c0c8d2'};color:#fff">✔ 저장</button></div>
      </div>`;
      const q=id=>ov.querySelector(id);
      q('#sp-x').onclick=close;q('#sp-close').onclick=close;
      q('#sp-add').onclick=()=>{rows.push({q:''});draw();};
      // ★레거시 동작: 한 줄에 수량을 넣으면 바로 다음 줄에 잔여수량이 자동으로 채워짐
      //   (예 원본 5 · SEQ1=3 입력 → SEQ2=2 자동). 사용자가 SEQ2를 고치면 그 다음 줄로 이어짐.
      const recalc=()=>{
        const s=rows.reduce((a,r)=>a+(+r.q||0),0), lf=Math.round((orgQty-s)*10000)/10000;
        const ok=Math.abs(lf)<0.0001 && rows.filter(r=>+r.q>0).length>=2;
        const sv=q('#sp-save');
        if(sv){sv.disabled=!ok;sv.style.background=ok?'#1c47a0':'#c0c8d2';
          sv.onclick=ok?doSave:null;}
        const info=ov.querySelectorAll('span > b');
        if(info[0])info[0].textContent=nf(s);
        if(info[1]){info[1].textContent=nf(lf);info[1].style.color=Math.abs(lf)<0.0001?'#1c7c3a':'#c0392b';}
      };
      ov.querySelectorAll('.sp-q').forEach(el=>{
        el.oninput=()=>{
          const i=+el.dataset.i;
          rows[i].q=el.value;
          // 자동 잔여: 지금 줄까지의 합을 뺀 나머지를 다음 줄에 채움(다음 줄이 비어있거나 자동값일 때만)
          const upto=rows.slice(0,i+1).reduce((a,r)=>a+(+r.q||0),0);
          const rest=Math.round((orgQty-upto)*10000)/10000;
          if(i+1<rows.length){
            const nx=ov.querySelector(`.sp-q[data-i="${i+1}"]`);
            if(nx&&(rest>0||nx.dataset.auto==='1')){
              rows[i+1].q=rest>0?String(rest):'';
              nx.value=rows[i+1].q;
              nx.dataset.auto='1';
              // 그 뒤 줄은 자동값이면 비움
              for(let k=i+2;k<rows.length;k++){
                const e2=ov.querySelector(`.sp-q[data-i="${k}"]`);
                if(e2&&e2.dataset.auto==='1'){rows[k].q='';e2.value='';}
              }
            }
          }
          el.dataset.auto='0';   // 직접 입력한 칸은 자동값 아님
          recalc();};
      });
      recalc();
      async function doSave(){
        const qtys=rows.map(r=>+r.q||0).filter(x=>x>0);
        if(!confirm(`간판 ${boxNo}(${nf(orgQty)})를 ${qtys.length}장으로 분할할까요?\n\n`
                   +`· ${qtys.map(x=>nf(x)).join(' + ')} = ${nf(orgQty)}\n`
                   +`· 원본 간판은 삭제 표시되고 새 간판번호가 채번됩니다\n`
                   +`· 재고/실적 변동 없음`))return;
        const btn=q('#sp-save');btn.disabled=true;btn.textContent='저장 중…';
        try{
          const r=await fetch(`${API}/api/prodsheet/kanban-split`,{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({box_no:boxNo,qtys,user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})});
          const j=await r.json();
          if(j.ok){close();
            st.msg=`✂ 간판 ${boxNo} → ${j.cnt}장 분할 (${j.issued.map(x=>x.box_no).join(', ')})`;
            printKanban(j.issued.map(x=>x.box_no));
            if(st.cur)await loadDetail(st.cur);
            render(true);
          }else{alert('분할 실패: '+(j.detail||''));btn.disabled=false;btn.textContent='✔ 저장';}
        }catch(e){alert('분할 오류: '+e);btn.disabled=false;btn.textContent='✔ 저장';}
      }
    };
    draw();document.body.appendChild(ov);
    ov.onclick=e=>{if(e.target===ov)close();};
  };
  // ★가간판 인쇄 — 용지 210×110mm(A4 3등분, 2026-08-20 실측). 레거시 양식 재현:
  //   [라인 | 도번(대) | ★간판수량(대)] / [박스종류·표준포장수 | 바코드 GP+BOX_NO 8자리]
  //   ※우상단 대형숫자 = 순번이 아니라 그 간판의 수량.
  //     (실측: box=2618985 표시4 = 수량4, 순번은 1/7 → 수량 확정. 2026-08-19 수정)
  //   [생산날짜 · 엘지날짜 · 품명] / [공정순서] / [불량이력 · 시방이력 | 검수란]
  //   [용접자 · 검사자] / 하단: 출력일시·발행자 | 용접전표번호
  //   ★바코드 GP+BOX_NO = 이 간판으로 실적을 잡는 값(공정별 바코드생산실적에서 스캔).
  const printKanban=async(boxNos)=>{
    const list=(boxNos||[]).filter(Boolean);
    if(!list.length)return;
    // ★에이전트가 살아있으면 인쇄창 없이 지정 프린터로 바로 출력한다.
    if(await tryAgent('kanban',()=>`${API}/api/print/kanban?box_no=${encodeURIComponent(list.join(','))}`))return;
    const cards=[];
    for(const bn of list){
      try{const r=await fetch(`${API}/api/prodsheet/kanban-print?box_no=${encodeURIComponent(bn)}`);
        const j=await r.json();if(j&&j.ok)cards.push(j);}catch(e){}
    }
    if(!cards.length){alert('간판 출력 데이터를 가져오지 못했습니다.');return;}
    const WD=['일','월','화','수','목','금','토'];
    const ymdw=s=>{s=(''+(s||'')).trim();if(s.length<6)return s;
      const y=2000+ +s.slice(0,2),m=+s.slice(2,4),d=+s.slice(4,6);
      const dt=new Date(y,m-1,d);
      return `${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}(${WD[dt.getDay()]||''})`;};
    const bc=(txt)=>`<div style="text-align:center;line-height:1">
        <img src="${API}/api/barcode/code128?text=${encodeURIComponent(txt)}&h=40&scale=2"
             style="height:20px;max-width:100%;image-rendering:pixelated" alt="${esc(txt)}">
        <div style="font-size:7px;letter-spacing:.3px">${esc(txt)}</div></div>`;
    const card=c=>`<div class="kb">
      <table>
        <tr>
          <td class="c" style="width:12%;font-size:21px;font-weight:700;height:22mm">${esc(c.line||'')}</td>
          <td class="c" style="width:58%;font-size:40px;font-weight:800;letter-spacing:1px">${esc(c.item)}</td>
          <td class="c" style="width:30%;font-size:40px;font-weight:800">${nf(c.qty)}</td></tr>
      </table>
      <table>
        <tr>
          <td style="width:12%"></td>
          <td class="c lb" style="width:14%;font-size:13px">박스종류</td><td class="c" style="width:18%;font-size:14px">${esc(c.pack_kind||'')}</td>
          <td class="c lb" style="width:16%;font-size:13px">표준포장수</td><td class="c" style="width:10%;font-weight:700;font-size:14px">${c.pack_qty||''}</td>
          <td style="width:30%">${bc(c.barcode)}</td></tr>
      </table>
      <table>
        <tr><td class="c lb" style="width:12%;font-size:13px">생산날짜</td><td class="c" style="width:20%;font-weight:700;font-size:14px">${esc(ymdw(c.plan_ymd))}</td>
            <td class="c lb" style="width:14%;font-size:13px">엘지날짜</td><td class="c" style="width:20%;font-weight:700;font-size:14px">${esc(ymdw(c.plan_ymd))}</td>
            <td class="c lb" style="width:8%;font-size:13px">품명</td><td style="width:26%;font-size:11px;padding-left:3px">${esc(c.nm||'')}</td></tr>
        <tr><td class="c lb" style="font-size:13px">공정순서</td><td colspan="5" style="font-weight:700;padding-left:4px;font-size:14px">${esc(c.proc_nm||'')}</td></tr>
      </table>
      <table>
        <colgroup><col style="width:12%"><col style="width:62%"><col style="width:26%"></colgroup>
        <tr><td class="c lb" style="height:14mm;font-size:16px">불량이력</td><td></td>
            <td class="c lb">검수란</td></tr>
        <tr><td class="c lb" style="height:14mm;font-size:16px">시방이력</td><td></td>
            <td></td></tr>
      </table>
      <table>
        <tr><td class="c lb" style="width:12%">용접자</td><td class="c" style="width:26%;font-weight:700">${esc(c.prod_worker||'')}</td>
            <td class="c lb" style="width:14%">검사자</td><td class="c" style="width:22%;font-weight:700">${esc(c.insp_worker||'')}</td>
            <td style="width:26%"></td></tr>
      </table>
      <div class="ft"><span>출력일시 : ${esc((c.print_dt||'').slice(2,16).replace('T',' ').replace(/-/g,'/'))} ${esc(c.print_user||'')}</span>
        <span>용접전표번호 : ${esc(c.sheet_no_fmt)}</span></div>
    </div>`;
    // ★실제 URL(print.html?t=kanban)로 연다 — about:blank 는 프린터 선택이 기억되지 않는다.
    const w=await openPrintWin('kanban','pncPrnKanban','width=980,height=680');
    if(!w){alert('팝업이 차단되었습니다. 브라우저 팝업 허용 후 다시 시도하세요.');return;}
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>가간판 ${esc(cards[0].item)} (${cards.length}장)</title>
    <style>
      /* ★용지 = 210 × 110mm (A4 가로폭 그대로, 세로 3등분) — 2026-08-28 교정.
         이전엔 180mm 였는데 실물 용지는 A4 폭(210mm)이라 좌우가 남았다.
         ★상단 잘림 재수정(2026-08-31 실물 확인): 08-28 에 여백을 4mm→상하 2mm 로 줄였는데
           **2mm 는 프린터의 물리적 인쇄불가 영역(보통 3~5mm)보다 작다.** 그래서 첫 행
           테두리가 다시 잘려 나왔다(그 전에는 정상 출력됐다는 사용자 확인).
           → 상단은 6mm 로 넉넉히, 하단은 3mm. 좌우 3mm 유지.
           표 합계 83mm + 상하여백 9mm = 92mm < 110mm 이라 한 장에 여유 있게 들어간다.
         간판 1장 = 1페이지. */
      @page{size:210mm 110mm;margin:6mm 3mm 3mm 3mm}
      *{box-sizing:border-box}
      body{margin:0;font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:10px;color:#000}
      /* 간판 1장 = 1페이지. 레거시 실물처럼 표는 위쪽에 모으고 아래는 비운다
         (표를 억지로 늘려 채우지 않음 — 2026-08-20 레거시 대조). */
      .kb{border:2px solid #000;page-break-inside:avoid;overflow:hidden;display:flex;flex-direction:column}
      .kb+.kb{page-break-before:always}
      .kb table{border-collapse:collapse;width:100%}
      /* 레거시 실물 대조: 글자·행높이를 키우고 라벨칸 음영은 없앤다(전부 흰 바탕) */
      .kb td{border:1px solid #000;padding:2px 3px;font-size:12px;height:7mm}
      .kb .c{text-align:center}
      .kb .lb{font-weight:700;white-space:nowrap}
      .kb .ft{display:flex;justify-content:space-between;padding:2px 4px;font-size:9px;
              font-weight:700;border-top:1px solid #000;margin-top:auto}
      /* ★인쇄 시 화면용 안내(.noprint)를 완전히 들어낸다 — display:none 만으로는
         일부 브라우저가 첫 페이지 상단에 여백을 남겨 간판 첫 행이 잘렸다(2026-08-28). */
      @media print{
        .noprint{display:none !important;height:0 !important;margin:0 !important;padding:0 !important}
        html,body{margin:0 !important;padding:0 !important}
        .kb{margin:0 !important}
      }
    </style></head><body>
    <div class="noprint" style="margin-bottom:6px">
      <button onclick="window.print()" style="padding:6px 16px;font-size:13px">🖨 인쇄</button>
      <button onclick="window.close()" style="padding:6px 16px;font-size:13px">닫기</button>
      <span style="font-size:12px;color:#555;margin-left:8px">가간판 ${cards.length}장 · 210×110mm (A4 3등분) — 인쇄창에서 <b>여백 없음</b>·<b>배율 100%</b> 확인</span>
      <div style="margin-top:6px;padding:6px 10px;background:#e6f7ff;border:1px solid #91d5ff;border-radius:4px;font-size:12px">
        <b>가간판 프린터(210×110 / A4)를 인쇄창에서 고르세요.</b>
        <span style="color:#1a6a99">— 한 번 고르면 다음부터 자동 선택됩니다.
          이 PC 에 <b>PNC 프린터 에이전트</b>를 설치하면 인쇄창 없이 바로 출력됩니다.</span>
      </div></div>
    ${cards.map(card).join('')}
    <script>
      (function(){var imgs=[].slice.call(document.images),left=imgs.length;
        function go(){setTimeout(function(){window.print();},250);}
        if(!left)return go();
        imgs.forEach(function(im){if(im.complete)done();else{im.addEventListener('load',done);im.addEventListener('error',done);}});
        function done(){if(--left<=0)go();}})();
    <\/script></body></html>`);
    w.document.close();
  };
  // A4 생산이동전표 = 준비실적처리와 동일 양식(window.printWeldSheet 공유)
  const printSheets=()=>{const rows=selRows();
    if(!rows.length){alert('출력할 전표를 선택하세요(체크박스).');return;}
    rows.forEach((r,i)=>setTimeout(()=>window.printWeldSheet(r.sheet_no),i*400));};   // 다건=순차 팝업
  // ── 전체 렌더 ────────────────────────────────────────────────────────
  const render=(bodyOnly)=>{
    if(bodyOnly){
      const tb=host.querySelector('#ps-lbody');
      if(tb){tb.innerHTML=leftBody();wireLeft();}
      const c=host.querySelector('#ps-cnt');
      if(c)c.textContent=`${won(st.cnt)}건 · 계획수량 ${won(st.sumQty)}`;
      return;
    }
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('prodsheet'):true;
    host.innerHTML=`
     <style>#ps-lbody tr.ps-on{background:#cdeef7 !important;font-weight:600}
            #ps-lbody tr:hover{background:#f2f8fd}</style>
     <div style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="flex:0 0 auto">🖨️ 생산전표출력관리 <span style="font-size:12px;color:var(--muted);font-weight:400">w_pr_input_490 · 전표 기준 가간판/제품스티커 발행</span></div>
     <!-- ★프린터 2대 지정(레거시 490 상단과 동일 위치) — 이름은 내 브라우저에 저장 -->
     <div style="flex:0 0 auto;display:flex;align-items:center;flex-wrap:wrap;gap:8px;
                 margin:0 0 6px;padding:7px 10px;border:1px solid #d6dee8;border-left:4px solid #5b7fa6;
                 border-radius:6px;background:linear-gradient(180deg,#fbfdff,#f1f5fa)">
       <span style="font-size:12px;font-weight:700;color:#41546b">프린터 설정</span>
       ${agentChip()}
       <button class="btn" id="ps-prn-r" style="height:24px;padding:0 8px;font-size:11px"
               title="이 PC 의 프린터 에이전트 상태를 다시 확인합니다">상태 새로고침</button>
     </div>
     <div class="page-sub" style="flex:0 0 auto">출력기간=전표 <code>PRINT_DATETIME</code> · 전표처리방법 <b>J:전표</b>(용접전표 바코드로 실적) / <b>G:가간판</b>(간판 바코드로 실적) · 포장정보=<code>PR_M_ITEM_SUB</code>.</div>
     <div class="toolbar" style="flex:0 0 auto;flex-wrap:wrap;gap:4px">
       <label class="tl">출력기간</label>
       <input class="inp" type="date" id="ps-from" value="${st.from}" style="min-width:0;width:132px"> ~
       <input class="inp" type="date" id="ps-to" value="${st.to}" style="min-width:0;width:132px">
       <label class="tl">파트</label>
       <select class="sel" id="ps-part" style="min-width:0;width:120px"><option value="">전체</option>
         ${st.parts.map(p=>`<option value="${esc(p.code)}" ${st.part===p.code?'selected':''}>${esc(p.nm)}</option>`).join('')}</select>
       <label class="tl">도번</label><input class="inp" id="ps-item" value="${esc(st.item)}" style="min-width:0;width:110px" autocomplete="off">
       <label class="tl">생산완료</label>
       <label class="tl" style="font-weight:400"><input type="radio" name="ps-fin" value="" ${st.fin===''?'checked':''}> 전체</label>
       <label class="tl" style="font-weight:400"><input type="radio" name="ps-fin" value="N" ${st.fin==='N'?'checked':''}> 미완료</label>
       <label class="tl" style="font-weight:400"><input type="radio" name="ps-fin" value="Y" ${st.fin==='Y'?'checked':''}> 완료</label>
       <button class="btn" id="ps-go">🔍 조회</button>
     </div>
     <div class="toolbar" style="flex:0 0 auto;margin-top:2px;gap:4px;flex-wrap:wrap">
       <label class="tl">전표번호</label><input class="inp" id="ps-sn" value="${esc(st.sheetNo)}" style="min-width:0;width:90px" autocomplete="off">
       <label class="tl">간판번호</label><input class="inp" id="ps-box" value="${esc(st.boxNo)}" style="min-width:0;width:90px" autocomplete="off">
       <label class="tl">라벨번호</label><input class="inp" id="ps-lbl" value="${esc(st.labelNo)}" style="min-width:0;width:90px" autocomplete="off">
       <span style="width:10px"></span>
       ${ed?`<button class="btn" id="ps-pj" style="background:#1c47a0;color:#fff">📄 생산이동전표 출력</button>
             <button class="btn" id="ps-ig" style="background:#1c7c3a;color:#fff">🏷 가간판 발행</button>
             <button class="btn" id="ps-il" style="background:#b8860b;color:#fff">🔖 제품스티커 발행</button>`
            :`<span style="color:#c0392b;font-size:12px">🔒 발행권한 없음</span>`}
       <div class="spacer"></div><span class="rowcount">선택 <b id="ps-selcnt">${st.sel.size}</b></span>
     </div>
     ${st.msg?`<div class="page-sub" style="flex:0 0 auto;color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div style="display:flex;gap:8px;flex:1 1 auto;min-height:0;margin-top:2px">
       <div style="flex:0 0 46%;min-width:0;display:flex;flex-direction:column">
         <div class="grid-wrap" style="flex:1 1 auto;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
          <table class="tbl fit" style="font-size:11px"><thead><tr>
            <th style="width:24px"><input type="checkbox" id="ps-all"></th>
            <th class="center">전표번호</th><th class="center">투입파트</th><th class="center">계획일자</th>
            <th class="num">계획수량</th><th>도번</th><th>품명</th><th class="center">완료</th>
            <th class="center">간판</th><th class="center">라벨</th></tr></thead>
          <tbody id="ps-lbody">${leftBody()}</tbody></table></div>
         <div class="rowcount" id="ps-cnt" style="flex:0 0 auto">${won(st.cnt)}건 · 계획수량 ${won(st.sumQty)}</div>
       </div>
       <div id="ps-det" style="flex:1 1 54%;min-width:0;display:flex;flex-direction:column"></div>
     </div>
     </div>`;
    const g=id=>host.querySelector(id);
    const syncF=()=>{st.from=g('#ps-from').value;st.to=g('#ps-to').value;st.part=g('#ps-part').value;
      st.item=g('#ps-item').value.trim();st.sheetNo=g('#ps-sn').value.trim();
      st.boxNo=g('#ps-box').value.trim();st.labelNo=g('#ps-lbl').value.trim();
      const f=host.querySelector('input[name="ps-fin"]:checked');st.fin=f?f.value:'';};
    g('#ps-go').onclick=()=>{syncF();load();};
    host.querySelectorAll('input[name="ps-fin"]').forEach(r=>r.onchange=()=>{syncF();load();});
    g('#ps-part').onchange=()=>{syncF();load();};
    ['#ps-item','#ps-sn','#ps-box','#ps-lbl'].forEach(id=>{const e=g(id);if(e)e.onkeyup=ev=>{if(ev.key==='Enter'){syncF();load();}};});
    g('#ps-all').onclick=e=>{st.sel.clear();if(e.target.checked)st.rows.forEach((r,i)=>st.sel.add(i));
      host.querySelectorAll('.ps-chk').forEach(ch=>ch.checked=e.target.checked);
      const c=g('#ps-selcnt');if(c)c.textContent=st.sel.size;};
    // 프린터 에이전트 상태 새로고침 — 에이전트를 켜거나 프린터를 바꾼 뒤 누른다.
    {const pr=g('#ps-prn-r');
     if(pr)pr.onclick=async()=>{pr.disabled=true;pr.textContent='확인 중…';
       await loadAgent(true);render();};}
    // 설치파일 받기 — 받아서 더블클릭하면 자가설치된다(관리자권한 불필요).
    {const dl=g('#ps-agent-dl'),dm=g('#ps-agent-dlmsg');
     if(dl)dl.onclick=async(ev)=>{
       ev.preventDefault();
       if(dm)dm.textContent='설치파일 확인 중…';
       let inf=null;
       try{const r=await fetch(`${API}/api/print/agent-info`);inf=await r.json();}catch(e){}
       if(!inf||!inf.available){
         if(dm)dm.textContent='';
         alert('설치파일이 서버에 없습니다.\n관리자에게 문의하세요.');return;}
       if(dm)dm.textContent=`내려받는 중… (${inf.size_mb}MB)`;
       // ★그냥 location 이동을 쓰면 로그인 토큰이 안 실려 401 이 난다 → fetch 로 받아 저장.
       try{
         const r=await fetch(`${API}/api/print/agent-download`);
         if(!r.ok)throw new Error('HTTP '+r.status);
         const blob=await r.blob();
         const u=URL.createObjectURL(blob);
         const a2=document.createElement('a');
         a2.href=u;a2.download='PNC프린터에이전트.exe';
         document.body.appendChild(a2);a2.click();a2.remove();
         setTimeout(()=>URL.revokeObjectURL(u),10000);
         if(dm)dm.textContent=`받았습니다 (${inf.size_mb}MB) — 더블클릭하면 설치됩니다.`;
       }catch(e){
         if(dm)dm.textContent='';
         alert('설치파일 다운로드 실패: '+e.message);}
     };}
    if(ed){g('#ps-pj').onclick=printSheets;g('#ps-ig').onclick=openKanban;g('#ps-il').onclick=openLabel;}
    wireLeft();paintDetail();attachResizers(host);
  };
  Promise.all([loadParts(),loadAgent(false)]).then(()=>{render();load();});
};

/* ===== 공정별 바코드생산실적 (w_pr_input_520) — 스캔→자동채움→등록/취소(nx.proc_barcode) ===== */
/* ===== 공정별 바코드생산실적 (w_pr_input_520 / _pop / 526) =====
   ★2026-08-19 레거시 구조로 재구성.
     [흐름] 상단에서 기준일자·파트·공정·작업자·설비를 먼저 고정
            → 그 공정의 바코드만 스캔 → 팝업에서 처리수량 확인/수정 → 등록
     [오등록 방지] 공정을 미리 고정하므로 "용접전표로 조립 실적" 같은 실수가 원천 차단.
            그래도 바코드 종류가 그 공정의 실적수단(J전표/G가간판/L라벨)과 다르면 경고.
     [실적 원장] nx.PR_T_PROD_DTL (레거시 미러) — 레거시 등록분과 같은 곳에 쌓임.
     [부분처리] 총수량 200 중 50만 처리 가능. 재스캔하면 잔여 기준으로 이어짐(50/200 → …).
     ※작업지도서 PDF 표시는 경로 확인 후 추가 예정. */
/* ===== 공정별 바코드생산실적 (w_pr_input_520) =====
   ★2026-08-19 레거시 구조 + 팝업 제거(한 화면에 전부).
     [흐름] 상단에서 기준일자·파트·공정·작업자·설비 고정
            → 바코드 스캔 → ★같은 화면의 처리부에 자동 채움 → 처리수량 확인/수정 → Enter로 등록
     [팝업 없앤 이유] 스캔이 반복 작업이라 매번 팝업이 뜨면 흐름이 끊김. 레거시 520 본화면도 붙박이 처리부.
     [오등록 방지] 파트·공정을 미리 고정 + 바코드 종류가 그 공정의 실적수단(J/G/L)과 다르면 경고.
     [실적 원장] nx.PR_T_PROD_DTL (레거시 미러) — 레거시 등록분과 같은 곳.
     [부분처리] 총 200 중 50만 처리 가능. 재스캔하면 잔여 기준으로 이어짐(50/200 → …).
     ※작업지도서 PDF 표시는 경로 확인 후 추가 예정. */
SCREEN.procbarcode=(host)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  // 생산시작~종료 소요시간(초 → 사람이 읽는 형태). 음수(취소행)는 표시 안 함.
  const dur=s=>{s=+s||0;if(s<0)return '';
    if(s<60)return s+'초';
    const m=Math.floor(s/60),ss=s%60;
    if(m<60)return ss?`${m}분 ${ss}초`:`${m}분`;
    const h=Math.floor(m/60),mm=m%60;return mm?`${h}시간 ${mm}분`:`${h}시간`;};
  // ★PC별 설정 기억(localStorage) — 현장 PC는 파트·공정·작업자·설비가 고정이라
  //   프로그램을 다시 열어도 마지막 선택이 그대로 복원되어야 함(2026-08-19 요청).
  //   기준일자는 저장하지 않음(항상 오늘) — 날짜까지 기억하면 다음날 어제 것으로 조회됨.
  const PBK='pnc.procbc.sel';
  const loadSel=()=>{try{return JSON.parse(localStorage.getItem(PBK)||'{}')||{};}catch(e){return {};}};
  const saveSel=()=>{try{localStorage.setItem(PBK,JSON.stringify(
      {part:st.part,swork:st.swork,worker:st.worker,mach:st.mach}));}catch(e){}};
  // ★★생산 시작시각 보관(localStorage) — 2026-08-19 요청.
  //   한 PC에서 여러 바코드를 동시에 걸어두고 끝나는 순서대로 부분등록하므로,
  //   (바코드+파트)별로 "작업을 시작한 시각"을 각각 들고 있어야 함.
  //     · 최초 스캔        → 그 시각 보관
  //     · 재인식(미등록)   → 보관된 최초 시각 복원 (화면 닫았다 열어도, 다른 바코드 처리해도 유지)
  //     · 부분등록         → 그 구간은 [보관시각 ~ 등록시각]으로 확정,
  //                          잔여가 있으면 "등록시각"을 새 시작으로 갈아끼움(분할=시작 리셋)
  //     · 전량등록/취소    → 보관분 삭제
  //   폐기 정책: 없음(사용자 지정) — 등록될 때까지 계속 보관.
  const PBS='pnc.procbc.sta';
  const staAll=()=>{try{return JSON.parse(localStorage.getItem(PBS)||'{}')||{};}catch(e){return {};}};
  const staPut=(m)=>{try{localStorage.setItem(PBS,JSON.stringify(m));}catch(e){}};
  const staKey=(bc,part)=>`${bc}@${part}`;
  const staGet=(bc,part)=>staAll()[staKey(bc,part)]||'';
  const staSet=(bc,part,v)=>{const m=staAll();m[staKey(bc,part)]=v;staPut(m);};
  const staDel=(bc,part)=>{const m=staAll();delete m[staKey(bc,part)];staPut(m);};
  const nowStr=()=>{const d=new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} `
          +`${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`;};
  const _sv=loadSel();
  const st={ymd:iso(new Date()),part:_sv.part||'',swork:_sv.swork||'',worker:_sv.worker||'',mach:_sv.mach||'',
            parts:[],procs:[],machs:[],workers:[],
            cur:null,      // 스캔된 바코드 정보(처리부에 표시)
            netOnly:true,  // 실적이력: 등록/취소 상쇄분 숨김(실제 생산분만)
            rows:[],cnt:0,sumQty:0,last:null,loading:false};
  const qsv=o=>new URLSearchParams(Object.entries(o).filter(([,v])=>v!==''&&v!=null)).toString();
  const loadMasters=async(keepSel)=>{
    try{const r=await fetch(`${API}/api/procbc/masters?${qsv({part:st.part})}`);const j=await r.json();
      st.parts=j.parts||[];st.procs=j.procs||[];st.machs=j.machs||[];st.workers=j.workers||[];
      if(!keepSel){
        st.swork=(st.procs[0]||{}).code||'';
        st.mach=(st.machs[0]||{}).code||'';
        if(!st.workers.some(w=>w.code===st.worker))st.worker='';
      }else{
        // ★복원값 검증 — 저장된 코드가 현재 마스터에 없으면(마스터 변경/파트 변경) 버리고 기본값으로.
        if(st.part&&!st.parts.some(p=>p.code===st.part))st.part='';
        if(!st.procs.some(p=>p.code===st.swork))st.swork=(st.procs[0]||{}).code||'';
        if(!st.machs.some(m=>m.code===st.mach))st.mach=(st.machs[0]||{}).code||'';
        if(!st.workers.some(w=>w.code===st.worker))st.worker='';
      }}catch(e){}
  };
  // ★실적이력 = 선택한 파트의 것만. 파트 미선택이면 조회하지 않음(전체가 쏟아지지 않게).
  const load=async()=>{
    if(!st.part){st.rows=[];st.cnt=0;st.sumQty=0;st.loading=false;render();return;}
    st.loading=true;render();
    try{const r=await fetch(`${API}/api/procbc/list?${qsv({ymd:st.ymd,part:st.part,swork:st.swork,limit:300})}`);
      const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.sumQty=j.sum_qty||0;}
    catch(e){st.rows=[];st.cnt=0;st.sumQty=0;}
    st.loading=false;render();};
  const focusBc=()=>setTimeout(()=>{const b=host.querySelector('#pb-bc');if(b){b.value='';b.focus();}},60);
  const focusQty=()=>setTimeout(()=>{const q=host.querySelector('#pb-qty');if(q){q.focus();q.select();}},60);
  // ── 스캔 → 처리부 채움(팝업 없음) ────────────────────────────────────
  const scan=async(bc)=>{bc=(bc||'').trim();if(!bc)return;
    if(!st.part){alert('파트코드를 먼저 선택하세요.');return;}
    if(!st.worker){alert('작업자를 선택하세요.');const w=host.querySelector('#pb-worker');if(w)w.focus();return;}
    // ★2회 스캔 = 실적등록(2026-08-19 요청) — 현장에서 스캐너만으로 처리.
    //   1회차: 생산시작(빨강 표시) · 포커스는 바코드칸에 그대로 유지
    //   2회차: 같은 바코드를 다시 찍으면 그 자리에서 실적등록(레거시 520 "2번 읽어야 실적" 동작)
    //   처리수량은 그 사이 수기로 고칠 수 있음(기본=잔여 전량).
    if(st.cur && st.cur.bc===bc){doSave();return;}
    let lk;
    try{lk=await(await fetch(`${API}/api/procbc/lookup?${qsv({barcode:bc,proc_code:st.part})}`)).json();}
    catch(e){st.cur=null;st.last={err:'조회 오류: '+e,bc};render();focusBc();return;}
    // ★파트 불일치 = 즉시 차단 팝업(2026-08-19). 예: S5-2 가간판을 S5(01라인 용접)에서 스캔.
    //   경고가 아니라 차단 — 실제로 계획6 전표에 9가 잡히는 오염이 발생했음.
    if(lk.mismatch){
      st.cur=null;
      alert(lk.msg||`이 바코드는 [${st.part}] 공정의 것이 아닙니다.`);
      st.last={err:`파트 불일치 — [${st.part}]에서 처리할 수 없는 바코드`
                  +(lk.procs&&lk.procs.length?` (해당 공정: ${lk.procs.join(', ')})`:''),bc};
      render();focusBc();return;}
    if(!lk.found){st.cur=null;st.last={err:lk.msg||'미발견',bc};render();focusBc();return;}
    const remain=Math.max(+lk.remain||0,0);
    // ★완료된 바코드를 다시 찍으면 → 취소 확인. 확인하면 실적·재고 전부 원복(레거시 220: 수량 음수 등록)
    if(remain<=0){
      const done=+lk.done_qty||0;
      if(done>0){
        if(confirm(`이미 전량 처리된 바코드입니다.\n\n`
                  +`· ${lk.item_code} ${lk.item_name||''}\n`
                  +`· 실적 ${nf(done)} / 총계 ${nf(lk.qty)}\n\n`
                  +`실적을 취소할까요?\n`
                  +`· 완제품(ASSY) 재고 ${nf(done)} 감소\n`
                  +`· BOM 자재 재고 원복`)){
          doCancel(bc,lk,done);return;
        }
      }
      st.cur=null;
      st.last={err:`잔여 0 — 이미 전량 처리됨(총 ${nf(lk.qty)} · 처리 ${nf(done)})`,bc};
      render();focusBc();return;}
    // ★생산 시작시각 = 이 (바코드+파트)를 '처음 스캔한' 시각. 등록 시각이 '종료'가 됨.
    //   보관분이 있으면 복원(= 여러 바코드를 동시에 걸어두고 나중에 재인식해도 최초 시각 유지),
    //   없으면 지금을 시작으로 보관. 등록될 때까지 남아 있음(폐기 없음).
    let sta=staGet(bc,st.part), resumed=false;
    if(sta) resumed=true; else {sta=nowStr();staSet(bc,st.part,sta);}
    st.cur={bc,lk,qty:remain,sta,resumed};st.last=null;render();focusBc();   // ★포커스는 바코드칸 유지(연속 스캔)
  };
  // ★실적 취소 = 수량을 음수로 등록(레거시 220 동일) → 실적·ASSY·BOM자재 모두 원복
  const doCancel=async(bc,lk,qty)=>{
    const sta=new Date();
    const s=`${sta.getFullYear()}-${String(sta.getMonth()+1).padStart(2,'0')}-${String(sta.getDate()).padStart(2,'0')} `
           +`${String(sta.getHours()).padStart(2,'0')}:${String(sta.getMinutes()).padStart(2,'0')}:${String(sta.getSeconds()).padStart(2,'0')}`;
    try{
      const r=await fetch(`${API}/api/procbc/save`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({barcode:bc,proc_code:st.part,s_work_code:st.swork,item_code:lk.item_code,
                             qty:-qty,total_qty:lk.qty,worker_code:st.worker,mach_code:st.mach,
                             sheet_no:lk.sheet_no,proc_seq:lk.proc_seq,sta_at:s,
                             line_user:(typeof PERM!=='undefined'?PERM.currentUser().nm:''),
                             window:'w_pr_input_520',
                             user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})});
      const j=await r.json();
      if(j.ok){
        const sk=j.stock||{};
        st.cur=null;
        staDel(bc,st.part);   // 취소 = 처음으로 되돌림 → 보관 시작시각도 폐기(다음 스캔이 새 시작)
        st.last={cancel:1,item:lk.item_code,nm:lk.item_name,qty,kind:lk.kind,bc,
                 assy:sk.assy,mats:(sk.mats||[]).length};
        await load();focusBc();
      }else{alert('취소 실패: '+((j.errors||[]).join(' ')||j.detail||''));focusBc();}
    }catch(e){alert('취소 오류: '+e);focusBc();}
  };
  const doSave=async()=>{
    const c=st.cur; if(!c)return;
    const el=host.querySelector('#pb-qty');
    const q=+((el&&el.value)||0);
    if(q<=0){alert('처리수량을 입력하세요.');focusQty();return;}
    if(q>c.qty){alert(`잔여(${nf(c.qty)})를 초과할 수 없습니다.`);focusQty();return;}
    // ★앞공정 실적 확인 — 부족하면 경고 후 사용자가 확인해야 진행(B안).
    //   전표 단위로 공정 진행이 관리되므로 원칙은 앞공정부터. 다만 실무 예외가 있어 강제차단은 안 함.
    const pr=c.lk.prior;
    if(pr && pr.qty < q){
      if(!confirm(`앞공정 실적이 부족합니다.\n\n`
                 +`· 앞공정 ${pr.nm||pr.gpc} : 실적 ${nf(pr.qty)}\n`
                 +`· 현재공정 처리요청 : ${nf(q)}\n\n`
                 +`앞공정 실적이 먼저 잡혀야 합니다.\n`
                 +`그래도 실적을 잡을까요?`)){focusQty();return;}
    }
    const btn=host.querySelector('#pb-ok'); if(btn){btn.disabled=true;btn.textContent='등록 중…';}
    try{
      const r=await fetch(`${API}/api/procbc/save`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({barcode:c.bc,proc_code:st.part,s_work_code:st.swork,item_code:c.lk.item_code,
                             qty:q,total_qty:c.lk.qty,worker_code:st.worker,mach_code:st.mach,
                             sheet_no:c.lk.sheet_no,proc_seq:c.lk.proc_seq,sta_at:c.sta,
                             line_user:(typeof PERM!=='undefined'?PERM.currentUser().nm:''),
                             window:'w_pr_input_520',
                             user:(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자')})});
      const j=await r.json();
      if(j.ok){
        // ★재고처리가 통째로 건너뛴 경우는 조용히 넘기지 않는다(공정정보 누락 등).
        //   백엔드가 warn 을 실어 보낸다 — 2026-08-30.
        if(j.warn) alert('⚠ 실적은 등록됐으나 재고처리가 생략됐습니다.\n\n'+j.warn);
        const sk=j.stock||{};
        // ★보관 시작시각 갱신 — 이 구간은 [c.sta ~ 지금]으로 확정됐으므로,
        //   잔여가 남으면 "지금"을 새 시작으로 갈아끼우고(분할=시작 리셋), 전량 끝났으면 삭제.
        const left=Math.max((+c.qty||0)-q,0);
        if(left>0) staSet(c.bc,st.part,nowStr()); else staDel(c.bc,st.part);
        st.last={ok:1,item:c.lk.item_code,nm:c.lk.item_name,qty:q,kind:c.lk.kind,bc:c.bc,
                 done:(+c.lk.done_qty||0)+q,tot:c.lk.qty,sta:c.sta,left,
                 assy:sk.assy,mats:(sk.mats||[]).length};
        st.cur=null;await load();focusBc();
      }else if(j.shortage){
        // ★자재 재고부족 = 실적 미등록(음수재고 금지). 부족 품번·수량을 그대로 보여줌.
        alert((j.errors||[]).join('\n'));
        st.last={err:`자재 재고부족 — ${j.shortage.length}개 품번`,bc:c.bc};
        render();focusBc();
      }else{alert('등록 실패: '+((j.errors||[]).join(' ')||j.detail||''));
        if(btn){btn.disabled=false;btn.textContent='✅ 실적등록 (Enter)';}}
    }catch(e){alert('등록 오류: '+e);
      if(btn){btn.disabled=false;btn.textContent='✅ 실적등록 (Enter)';}}
  };
  const clearCur=()=>{st.cur=null;render();focusBc();};
  // ★"실제 생산분만" 필터 — 등록(+)/취소(−)가 상쇄된 쌍을 숨긴다.
  //   같은 (바코드+공정+수량절대값) 안에서 + 와 − 를 짝지어 제거하고, 남는 것만 표시.
  //   예: 54, -54, 54, -54, 54  → 마지막 54 한 건만 남음(순합계 54와 일치).
  //   체크 해제하면 취소내역까지 전부 보인다.
  const netRows=()=>{
    if(!st.netOnly) return st.rows;
    const neg=new Map();                       // key → 남은 취소 건수
    st.rows.forEach(r=>{if((+r.qty||0)<0){
      const k=`${r.barcode}|${r.swork}|${Math.abs(+r.qty||0)}`;
      neg.set(k,(neg.get(k)||0)+1);}});
    const out=[];
    // 최신순 배열이므로 뒤(오래된 것)부터 훑어 +를 취소분과 짝지음
    for(let i=st.rows.length-1;i>=0;i--){
      const r=st.rows[i], q=+r.qty||0;
      if(q<0) continue;                        // 취소행 자체는 표시 안 함
      const k=`${r.barcode}|${r.swork}|${Math.abs(q)}`;
      const n=neg.get(k)||0;
      if(n>0){neg.set(k,n-1);continue;}        // 짝이 있는 등록 = 상쇄 → 숨김
      out.unshift(r);
    }
    return out;
  };
  const render=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('procbarcode'):true;
    const L=st.last, C=st.cur;
    const warn=C&&C.lk.warn?C.lk.warn:'';
    const hrows=netRows();
    const hcnt=hrows.length;
    const hsum=Math.round(hrows.reduce((s,r)=>s+(+r.qty||0),0)*100)/100;
    host.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="flex:0 0 auto">🔫 공정별 바코드생산실적 <span style="font-size:12px;color:var(--muted);font-weight:400">w_pr_input_520 · 전표/간판/라벨 스캔 → 실적</span></div>
     <div class="page-sub" style="flex:0 0 auto">파트·공정을 고정한 뒤 그 공정의 바코드를 스캔합니다 · 실적원장=<code>PR_T_PROD_DTL</code>(레거시 공통) · 부분처리 가능.</div>
     <div class="toolbar" style="flex:0 0 auto;flex-wrap:wrap;gap:6px;background:#f4f7fc;border-radius:8px;padding:8px">
       <label class="tl">기준일자</label><input class="inp" type="date" id="pb-ymd" value="${st.ymd}" style="min-width:0;width:132px">
       <label class="tl">파트코드<span style="color:#c0392b">*</span></label>
       <select class="sel" id="pb-part" style="min-width:0;width:150px"><option value="">선택</option>
         ${st.parts.map(p=>`<option value="${esc(p.code)}" ${st.part===p.code?'selected':''}>${esc(p.code)} ${esc(p.nm)}</option>`).join('')}</select>
       <label class="tl">공정코드</label>
       <select class="sel" id="pb-swork" style="min-width:0;width:150px">
         ${st.procs.length?st.procs.map(p=>`<option value="${esc(p.code)}" ${st.swork===p.code?'selected':''}>${esc(p.nm)}</option>`).join(''):'<option value="">-</option>'}</select>
       <label class="tl">작업자<span style="color:#c0392b">*</span></label>
       <select class="sel" id="pb-worker" style="min-width:0;width:120px"><option value="">선택</option>
         ${st.workers.map(w=>`<option value="${esc(w.code)}" ${st.worker===w.code?'selected':''}>${esc(w.nm)}</option>`).join('')}</select>
       <label class="tl">설비코드</label>
       <select class="sel" id="pb-mach" style="min-width:0;width:110px"><option value="">-</option>
         ${st.machs.map(m=>`<option value="${esc(m.code)}" ${st.mach===m.code?'selected':''}>${esc(m.code)}</option>`).join('')}</select>
       <button class="btn" id="pb-go">🔍 조회</button>
     </div>
     <!-- ★스캔 + 처리부 (팝업 없이 한 화면) -->
     <!-- ★대기중(1회 스캔 완료)이면 빨간 테두리 — 한 번 더 찍으면 등록 -->
     <div style="flex:0 0 auto;margin-top:10px;border:2px solid ${C?'#c0392b':'#1c47a0'};border-radius:8px;background:#fff;overflow:hidden">
       <div style="display:flex;gap:10px;align-items:center;padding:10px 14px;background:${C?'#fff5f5':'#f7f9fd'}">
         <label class="tl" style="font-size:15px;font-weight:700">🔫 바코드</label>
         <input class="inp" id="pb-bc" placeholder="${C?'같은 바코드를 한 번 더 스캔하면 실적등록':'전표(8자리) / 간판(GP…) / 라벨 QR 스캔 후 Enter'}"
                style="flex:1;min-width:0;font-size:16px;padding:10px${C?';border-color:#c0392b;background:#fff8f8':''}" ${ed&&st.part?'':'disabled'}>
         ${!ed?'<span style="color:#c0392b;font-size:12px">🔒 실적등록 권한 없음</span>'
              :(!st.part?'<span style="color:#c0392b;font-size:12px">← 파트코드를 먼저 선택하세요</span>'
                        :(C?`<span style="color:#c0392b;font-size:13px;font-weight:700;white-space:nowrap">● 생산시작 — 한 번 더 스캔</span>`:''))}
       </div>
       ${(()=>{ // ★작업중(시작만 찍히고 아직 미등록) 목록 — 한 PC에서 여러 건 동시 진행용
          if(!st.part)return '';
          const m=staAll(),ks=Object.keys(m).filter(k=>k.endsWith('@'+st.part));
          if(!ks.length)return '';
          return `<div style="padding:6px 14px 10px;border-top:1px dashed #cfd8e3;background:#fffdf5">
            <span style="font-size:12px;color:#b86a00;font-weight:700">⏱ 작업중 ${ks.length}건</span>
            ${ks.map(k=>{const bc=k.slice(0,k.lastIndexOf('@'));
              return `<span class="pb-run" data-bc="${esc(bc)}" title="클릭하면 이어서 처리"
                        style="display:inline-block;margin-left:8px;padding:2px 8px;border:1px solid #f0cf9a;border-radius:10px;
                               background:#fff7e8;font-size:12px;cursor:pointer">
                        ${esc(bc)} <b style="color:#b86a00">${esc((m[k]||'').slice(11,16))}~</b></span>`;}).join('')}
            <span style="font-size:11px;color:#888;margin-left:8px">시작만 기록된 건 · 등록하면 사라집니다</span></div>`;})()}
       ${C?`
       <div style="padding:0 14px 12px">
         ${warn?`<div style="background:#fdecec;border:1px solid #f3c9c9;border-radius:6px;padding:7px 10px;font-size:12px;color:#c0392b;margin-bottom:8px;font-weight:600">⚠ ${esc(warn)}</div>`:''}
         <table class="tbl" style="width:100%;font-size:13px">
           <tr><th class="lbl" style="width:80px;background:#f2f6fb">작업자</th>
               <td style="width:130px"><b>${esc(st.worker)}</b></td>
               <th class="lbl" style="width:60px;background:#f2f6fb">품번</th>
               <td><b style="font-size:15px">${esc(C.lk.item_code)}</b>
                   <span style="color:#666;margin-left:8px">${esc(C.lk.item_name||'')}</span></td>
               <td style="width:110px;text-align:center;background:#eef2f7;font-weight:700">${esc((C.lk.method||'')+':'+(C.lk.kind||''))}</td></tr>
           <tr><th class="lbl" style="background:#f2f6fb">처리수량</th>
               <td><input class="inp" id="pb-qty" type="number" min="1" max="${C.qty}" value="${C.qty}"
                    style="width:120px;min-width:0;height:32px;text-align:right;font-size:17px;font-weight:700;background:#ffffcc"></td>
               <th class="lbl" style="background:#f2f6fb">실적/총계</th>
               <td colspan="2" style="font-size:15px"><b>${nf(C.lk.done_qty)}</b> / <b>${nf(C.lk.qty)}</b>
                   <span style="color:#1c7c3a;font-size:12px;margin-left:8px">잔여 ${nf(C.qty)}</span>
                   <span style="color:#888;font-size:12px;margin-left:10px">바코드 ${esc(C.bc)}${C.lk.sheet_no?` · 전표 ${esc(C.lk.sheet_no)}`:''}</span></td></tr>
           <tr><th class="lbl" style="background:#fdecec;color:#c0392b">생산시작</th>
               <td colspan="4" style="font-size:13px;background:#fff8f8">
                 <b style="font-size:17px;color:#c0392b">● 생산시작</b>
                 <b style="font-size:15px;color:#c0392b;margin-left:8px">${esc((C.sta||'').slice(11))}</b>
                 <span style="color:#888;font-size:12px;margin-left:6px">${esc((C.sta||'').slice(0,10))}</span>
                 ${C.resumed
                    ?`<span style="color:#b86a00;font-size:12px;margin-left:10px;font-weight:700">⏱ 이어서 작업중 — 최초 스캔시각 유지</span>`
                    :''}
                 <span style="color:#c0392b;font-size:13px;margin-left:12px;font-weight:700">
                   → 같은 바코드를 한 번 더 스캔하면 실적등록</span></td></tr>
           ${C.lk.prior?`<tr><th class="lbl" style="background:#f2f6fb">앞공정</th>
               <td colspan="4" style="font-size:13px">
                 ${esc(C.lk.prior.nm||C.lk.prior.gpc)} <span style="color:#888">(SEQ ${C.lk.prior.proc_seq})</span>
                 · 실적 <b style="color:${C.lk.prior.qty>=C.qty?'#1c7c3a':'#c0392b'}">${nf(C.lk.prior.qty)}</b>
                 ${C.lk.prior.qty>=C.qty
                    ?'<span style="color:#1c7c3a;font-size:12px;margin-left:6px">✔ 충족</span>'
                    :'<span style="color:#c0392b;font-size:12px;margin-left:6px;font-weight:700">⚠ 부족 — 등록 시 확인 필요</span>'}</td></tr>`:''}
         </table>
         <div style="display:flex;gap:6px;justify-content:flex-end;margin-top:8px">
           <button class="btn ghost" id="pb-cancel">취소 (Esc)</button>
           <button class="btn" id="pb-ok" style="background:#1c7c3a;color:#fff">✅ 실적등록 (바코드 재스캔)</button></div>
       </div>`:''}
     </div>
     ${L?`<div style="flex:0 0 auto;margin-top:8px;padding:10px 14px;border-radius:8px;font-size:14px;${L.ok?'background:#e5f3e8;border:1px solid #a8d5b5':(L.cancel?'background:#fff3e0;border:1px solid #f0cf9a':'background:#fdecec;border:1px solid #f3c9c9')}">
       ${L.ok?`<b style="color:#1c7c3a">✅ 등록</b> · ${esc(L.kind||'')} · <b>${esc(L.item)}</b> ${esc(L.nm||'')} · 처리 <b>${nf(L.qty)}</b>
              <span style="color:#456;margin-left:10px">실적/총계 <b>${nf(L.done)}</b> / <b>${nf(L.tot)}</b></span>
              ${L.sta?`<span style="color:#456;margin-left:10px;font-size:12px">구간 ${esc((L.sta||'').slice(11))} ~ 방금</span>`:''}
              ${L.left>0?`<span style="color:#b86a00;margin-left:10px;font-size:12px;font-weight:700">잔여 ${nf(L.left)} — 다시 스캔하면 지금부터 새로 시작</span>`:''}
              ${L.assy!=null?`<span style="color:#888;margin-left:10px;font-size:12px">ASSY재고 ${nf(L.assy)>0?'+':''}${nf(L.assy)} · BOM자재 ${nf(L.mats)}종 차감</span>`:''}`
        :(L.cancel?`<b style="color:#b86a00">⏪ 취소</b> · ${esc(L.kind||'')} · <b>${esc(L.item)}</b> ${esc(L.nm||'')} · 취소 <b>${nf(L.qty)}</b>
              <span style="color:#888;margin-left:10px;font-size:12px">ASSY재고 ${nf(L.assy)} · BOM자재 ${nf(L.mats)}종 원복</span>`
             :`<b style="color:#c0392b">✖ ${esc(L.err)}</b> <span style="color:#888">(${esc(L.bc)})</span>`)}
     </div>`:''}
     <!-- ★좌: 실적이력 / 우: 작업지도서 -->
     <div style="display:flex;gap:8px;flex:1 1 auto;min-height:0;margin-top:12px">
       <div style="flex:1 1 50%;min-width:0;display:flex;flex-direction:column">
         <div class="page-sub" style="flex:0 0 auto;font-weight:600;margin:0 0 4px;display:flex;align-items:center;gap:8px">
           <span>실적 이력</span>
           <span style="color:var(--muted);font-weight:400">${st.part
             ?`${esc(st.part)}${(st.parts.find(p=>p.code===st.part)||{}).nm?' '+esc((st.parts.find(p=>p.code===st.part)||{}).nm):''} · ${nf(hcnt)}건 · 합계 ${nf(hsum)}`
             :'파트 선택 시 표시'}</span>
           <span style="flex:1"></span>
           <!-- ★등록/취소가 상쇄된 쌍은 숨김 = 실제 생산분만. 해제하면 취소내역까지 전부 표시. -->
           <label style="font-weight:400;font-size:12px;display:inline-flex;align-items:center;gap:4px;cursor:pointer"
                  title="등록 후 취소해서 실적이 0이 된 건을 숨깁니다">
             <input type="checkbox" id="pb-netonly" ${st.netOnly?'checked':''}> 실제 생산분만</label>
         </div>
         <div class="grid-wrap" style="flex:1 1 auto;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
          <table class="tbl fit" style="font-size:11px"><thead><tr>
            <th class="center">생산시작</th><th class="center">생산종료</th><th class="center">소요</th>
            <th>도번</th><th>품명</th>
            <th class="num">수량</th><th class="center">작업자</th><th class="center">파트</th><th class="center">공정</th>
            <th class="center">바코드</th>
            </tr></thead>
          <tbody>${st.loading?spinRow(10):(hrows.length?hrows.map(r=>`<tr${r.qty<0?' style="background:#fff3e0"':''}>
            <td class="center mut">${esc(r.sta||'')}</td>
            <td class="center mut">${esc(r.fin||'')}</td>
            <td class="center mut">${r.secs!=null?esc(dur(r.secs)):''}</td>
            <td><b>${esc(r.item_code)}</b></td>
            <td class="cap" title="${esc(r.nm)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
            <td class="num"><b${r.qty<0?' style="color:#c0392b"':''}>${nf(r.qty)}</b></td>
            <td class="center">${esc(r.worker)}</td><td class="center">${esc(r.part)}</td><td class="center">${esc(r.swork)}</td>
            <td class="center mut" title="${esc(r.barcode)}${r.sheet_no?' · 전표 '+esc(r.sheet_no):''}"
                style="max-width:110px;overflow:hidden;text-overflow:ellipsis">${esc(r.barcode||'')}</td>
            </tr>`).join('')
            :`<tr><td colspan="10" class="empty">${!st.part?'파트코드를 선택하면 해당 파트의 실적이 표시됩니다':(st.rows.length?'표시할 실적 없음 — 등록·취소가 모두 상쇄되었습니다(체크 해제 시 전체 표시)':'실적 이력 없음')}</td></tr>`)}</tbody></table></div>
       </div>
       <div style="flex:1 1 50%;min-width:0;display:flex;flex-direction:column">
         <div class="page-sub" style="flex:0 0 auto;font-weight:600;margin:0 0 4px">📄 작업지도서
           ${C?`<span style="color:var(--muted);font-weight:400">${esc(C.lk.item_code)}</span>`:''}</div>
         <div style="flex:1 1 auto;min-height:0;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;overflow:hidden;display:flex;align-items:center;justify-content:center">
           ${C?`<div style="text-align:center;color:var(--muted);font-size:13px;padding:20px">
                  <div style="font-size:34px;margin-bottom:8px">📄</div>
                  <div><b style="color:#456">${esc(C.lk.item_code)}</b> 작업지도서</div>
                  <div style="margin-top:6px;font-size:12px">PDF 저장 경로 확인 후 연결 예정</div></div>`
               :`<div style="color:var(--muted);font-size:13px">바코드를 스캔하면 작업지도서가 표시됩니다</div>`}
         </div>
       </div>
     </div>
     </div>`;
    const g=id=>host.querySelector(id);
    g('#pb-ymd').onchange=e=>{st.ymd=e.target.value;load();};   // 일자는 저장 안 함(항상 오늘로 시작)
    g('#pb-part').onchange=async e=>{st.part=e.target.value;st.cur=null;await loadMasters(false);saveSel();render();load();};
    g('#pb-swork').onchange=e=>{st.swork=e.target.value;saveSel();load();};
    g('#pb-worker').onchange=e=>{st.worker=e.target.value;saveSel();};
    g('#pb-mach').onchange=e=>{st.mach=e.target.value;saveSel();};
    g('#pb-go').onclick=load;
    {const nb=g('#pb-netonly'); if(nb)nb.onchange=e=>{st.netOnly=e.target.checked;render();};}
    // 작업중 칩 클릭 = 그 바코드를 다시 인식(최초 시작시각 복원됨)
    host.querySelectorAll('.pb-run').forEach(el=>{el.onclick=()=>scan(el.getAttribute('data-bc'));});
    // ★포커스는 항상 바코드칸(대기중이어도) — 스캐너만으로 연속 처리.
    //   Esc = 대기 취소. 처리수량은 필요할 때만 마우스/Tab 으로 가서 수기 입력.
    if(ed&&st.part){const bi=g('#pb-bc');
      if(bi){bi.onkeydown=e=>{
          if(e.key==='Enter'){e.preventDefault();scan(bi.value);}
          else if(e.key==='Escape'&&C){e.preventDefault();clearCur();}};
        bi.focus();}}
    if(C){
      const qi=g('#pb-qty');
      if(qi)qi.onkeydown=e=>{
        if(e.key==='Enter'){e.preventDefault();doSave();}
        else if(e.key==='Escape'){e.preventDefault();clearCur();}};
      const ok=g('#pb-ok'); if(ok)ok.onclick=doSave;
      const cc=g('#pb-cancel'); if(cc)cc.onclick=clearCur;
    }
    attachResizers(host);
  };
  loadMasters(true).then(()=>{render();load();});
};
/* ===== 생산준비재고관리 — 준비(키팅) 재고 조회 (읽기전용) ===== */
SCREEN.readystock=(host)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,total:0,procs:[],q:'',proc:'',loading:false,msg:''};
  const load=async()=>{
    st.loading=true;render();
    const qs=new URLSearchParams({q:st.q,proc:st.proc,limit:1500});
    try{const r=await fetch(`${API}/api/readystock/list?${qs}`);const j=await r.json();
      st.rows=j.rows||[];st.cnt=j.cnt||0;st.total=j.total_qty||0;if(j.procs)st.procs=j.procs;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    st.loading=false;render();
  };
  const render=()=>{
    host.innerHTML=`
     <div class="page-title">🧷 생산준비재고관리 <span style="font-size:12px;color:var(--muted);font-weight:400">준비(키팅) 재고 잔량 · 조회</span></div>
     <div class="page-sub">생산준비(키팅) 재고 잔량. 원천 <code>PU_T_READY_STOCK</code>. <b style="color:#b8860b">강제수정(자재복원)은 준비원장 설계 후 제공 예정 — 현재 조회만</b>.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">공정</label><select class="inp" id="rs-proc" style="width:auto"><option value="">전체</option>${st.procs.map(o=>`<option value="${esc(o.code)}" ${st.proc===o.code?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">검색</label><input class="inp" id="rs-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:170px">
       <button class="btn" id="rs-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건 · 재고합 <b>${won(Math.round(st.total))}</b></span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b;font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th>품번</th><th>품명</th><th>규격</th><th>공정</th><th>거래처</th><th class="num">준비재고</th><th class="center">최종수정</th></tr></thead>
      <tbody>${st.loading?spinRow(7):(st.rows.length?st.rows.map(r=>`<tr>
        <td><b>${esc(r.item_code)}</b></td>
        <td class="cap" title="${esc(r.nm)}" style="max-width:170px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="cap" title="${esc(r.spec)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(r.spec)}</td>
        <td>${esc(r.proc_nm)}</td><td class="cap" title="${esc(r.cust_nm)}" style="max-width:110px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm)}</td>
        <td class="num ${r.stock_qty<0?'neg':''}">${won(r.stock_qty)}</td>
        <td class="center mut">${esc((r.upd_dt||'').slice(0,10))}</td></tr>`).join(''):`<tr><td colspan="7" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#rs-search').onclick=()=>{st.q=g('#rs-q').value;st.proc=g('#rs-proc').value;load();};
    g('#rs-q').onkeyup=e=>{if(e.key==='Enter')g('#rs-search').click();};
    g('#rs-proc').onchange=()=>{st.proc=g('#rs-proc').value;load();};
    attachResizers(host);
  };
  load();
};

/* ===== 생산: 생산계획현황 (라이브 SA_T_PLAN_DTL, 제번×일자 피벗) — 생산팀 요청 ===== */
SCREEN.prodplanstatus=(c)=>{
  const API=API_BASE;
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:(s||'');
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(new Date(T.getTime()-3*864e5)),to:iso(new Date(T.getTime()+14*864e5)),line:'',wo:'',model:'',cr:''};
  let data={dates:[],rows:[],wo_count:0,sum_qty:0}, loading=false, msg='';
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,line:F.line,wo:F.wo,model:F.model,cr:F.cr});
    try{const r=await fetch(`${API}/api/prodplan/status?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={dates:[],rows:[],wo_count:0,sum_qty:0};}
    loading=false;draw();};
  const draw=()=>{
    const dates=data.dates||[];
    // 규칙17: 로드된 rows에서 라인·제번·모델 datalist (모델=값→이름 그대로)
    const psLine=new Set(),psWo=new Set(),psModel=new Set();
    (data.rows||[]).forEach(r=>{if(r.line)psLine.add(r.line);if(r.wo)psWo.add(r.wo);if(r.model)psModel.add(r.model);});
    const psLineOpts=[...psLine].map(v=>`<option value="${esc(v)}"></option>`).join('');
    const psWoOpts=[...psWo].map(v=>`<option value="${esc(v)}"></option>`).join('');
    const psModelOpts=[...psModel].map(v=>`<option value="${esc(v)}"></option>`).join('');
    c.innerHTML=`
     <div class="page-title">📋 생산계획현황 <span style="font-size:12px;color:var(--muted);font-weight:400">현행 LG 생산계획(제번×일자)</span></div>
     <div class="page-sub">현행 생산계획을 <b>제번(WO)×일자</b>로 조회(라이브·읽기전용). 원본 <code>SA_T_PLAN_DTL</code> · 업로드본(nx)은 생산계획업로드에서 대조 · C=확정/R=변경</div>
     <div class="toolbar">
       <label class="tl">계획기간</label><input class="inp" type="date" id="pp-from" value="${F.from}"> ~ <input class="inp" type="date" id="pp-to" value="${F.to}">
       <label class="tl">라인</label><input class="inp" id="pp-line" list="ppst-line" value="${esc(F.line)}" style="width:70px" placeholder="라인" autocomplete="off"><datalist id="ppst-line">${psLineOpts}</datalist>
       <label class="tl">제번</label><input class="inp" id="pp-wo" list="ppst-wo" value="${esc(F.wo)}" style="width:110px" placeholder="제번 입력" autocomplete="off"><datalist id="ppst-wo">${psWoOpts}</datalist>
       <label class="tl">모델</label><input class="inp" id="pp-model" list="ppst-model" value="${esc(F.model)}" style="width:120px" placeholder="모델명 입력" autocomplete="off"><datalist id="ppst-model">${psModelOpts}</datalist>
       <label class="tl">구분</label><select class="inp" id="pp-cr"><option value="">전체</option><option value="C"${F.cr==='C'?' selected':''}>확정(C)</option><option value="R"${F.cr==='R'?' selected':''}>변경(R)</option></select>
       <button class="btn" id="pp-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">제번 ${won(data.wo_count)} · 계획합 <b>${won(data.sum_qty)}</b> · 일자 ${dates.length}</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>
        <th>라인</th><th>제번</th><th>모델</th><th class="center">구분</th><th class="center">치공구</th><th class="num">계</th>${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${loading?spinRow(6+dates.length):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${esc(r.line)}</td><td><b>${esc(r.wo)}</b></td>
        <td class="bcap" title="${esc(r.model)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.model)}</td>
        <td class="center">${r.cr==='R'?'<span class="bdg" style="background:#f4d3d3;color:#a33">변경</span>':(r.cr==='C'?'<span class="bdg ok">확정</span>':esc(r.cr))}</td>
        <td class="center">${esc(r.tool)}</td><td class="num"><b>${won(r.total)}</b></td>
        ${dates.map(d=>`<td class="num">${r.days[d]?won(r.days[d]):''}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${6+dates.length}" class="empty">조회 결과 없음 (기간/조건 조정)</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#pp-search').onclick=()=>{F.from=g('#pp-from').value;F.to=g('#pp-to').value;F.line=g('#pp-line').value;F.wo=g('#pp-wo').value;F.model=g('#pp-model').value;F.cr=g('#pp-cr').value;load();};
    ['#pp-line','#pp-wo','#pp-model'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#pp-search').click();});
  };
  load();
};

/* ===== 일반업무: 공수등록(근무/지원) — nx.hr_work_info(웹) ∪ HR_M_WORK_INFO 미러(읽기전용). 레거시 라이브 없음(컷오버) ===== */
/*   인원정보호출: 파트별 등록작업자(PR_M_PROC_GAGONG_WORKER)를 공수 그리드에 자동채움(레거시 w_pr_worktime_010) */
SCREEN.gongsu=(c)=>{
  const API=API_BASE;
  const canEd=()=>(typeof PERM!=='undefined')?PERM.canEdit('gongsu'):true;
  const uname=()=>(typeof PERM!=='undefined'?PERM.currentUser().nm:'웹사용자');
  // ★2026-08-23 근태 확장 — 반차를 오전/오후로 분리.
  //   ※코드 선정 주의: 레거시 HR_M_WORK_INFO.HR_CHECK_POINT 는 4(38,374건)·5(3,948건)·6·7·10~14 를
  //     이미 다른 의미로 쓰고 있다. 반면 '2'(반차)는 레거시 0건이라 안전 →
  //     오전반차='2'(기존 '반차' 라벨 재사용), 오후반차='8'(레거시 미사용).
  //   근태를 고르면 시작·종료·근무h가 규칙대로 자동세팅되고, 시작/종료를 직접 고치면 근무h 재계산.
  //   잔업 = 정규(8h) + N시간. 저녁휴게 17:00~17:30 뒤부터 시작하므로 종료 = 17:30 + N.
  //   레거시 미사용 코드 20~25 배정(4~7·10~14 는 레거시 사용중이라 회피).
  const HRCHK=[['0','정상'],['1','연차'],['2','오전반차'],['8','오후반차'],['3','조퇴'],
               ['20','잔업1'],['21','잔업1.5'],['22','잔업2'],['23','잔업2.5'],['24','잔업3'],['25','잔업3.5']];
  const HRPRE={'0':['0800','1700'],'1':['0000','0000'],'2':['0800','1200'],'8':['1300','1700'],
               '20':['0800','1830'],'21':['0800','1900'],'22':['0800','1930'],
               '23':['0800','2000'],'24':['0800','2030'],'25':['0800','2100']};   // 조퇴는 수기
  // 시작~종료 → 근무h. 정규 08:00~17:00, 휴게 = 점심 12:00~13:00 + 저녁 17:00~17:30.
  //   근무구간에 걸친 휴게만 공제하고 30분 단위로 정리. 종료<=시작이면 0.
  //   (08:00~17:00 → 9h−1h = 8h / 08:00~12:00 → 4h / 13:00~17:00 → 4h / 08:00~18:00 → 10−1−0.5 = 8.5h)
  const _hm=s=>{s=String(s||'').replace(/\D/g,'').padStart(4,'0');const h=+s.slice(0,2),m=+s.slice(2,4);
    return (h>=0&&h<48&&m>=0&&m<60)?h*60+m:null;};
  const BRK=[[12*60,13*60],[17*60,17*60+30]];        // 점심 · 저녁
  const calcHr=(st,et)=>{const a=_hm(st),b=_hm(et);if(a==null||b==null||b<=a)return 0;
    let mi=b-a;
    BRK.forEach(([p,q])=>{mi-=Math.max(0,Math.min(b,q)-Math.max(a,p));});
    return Math.max(0,Math.round(mi/15)/4);};      // 15분(0.25h) 단위
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let body=null;
  // ★2026-08-23 근무일 기본 = 당일(기존 당월1일~오늘). 기간을 넓히면 백엔드가
  //   WORK_YMD DESC, DEPT_CODE 순으로 주므로 최근 날짜부터 부서별로 묶여 보인다.
  let F={from:iso(T),to:iso(T),gubun:'',dept:'',user:''};
  let data={rows:[],cnt:0,sum_hr:0}, loading=false, msg='';
  let editId=null;                                // ★인라인 수정 중인 행 ID
  let parts=[];                                   // 투입파트 드롭다운
  let entry={open:false,ymd:iso(T),part:'',gubun:'근무',rows:[],loading:false};   // 인원정보호출 입력
  const loadParts=async()=>{try{const r=await fetch(`${API}/api/partmaster/list`);parts=(await r.json()).rows||[];}catch(e){parts=[];}};
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,gubun:F.gubun,dept:F.dept,user:F.user});
    try{const r=await fetch(`${API}/api/gongsu/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={rows:[],cnt:0,sum_hr:0};}
    loading=false;draw();};
  const callPersons=async()=>{   // 투입파트 빈값=전체(backend persons가 전체 지원) → 항상 전체로 시작 가능
    entry.loading=true;draw();
    try{const qs=new URLSearchParams({part:entry.part,ymd:entry.ymd,gubun:entry.gubun});
      const r=await fetch(`${API}/api/gongsu/persons?${qs}`);const j=await r.json();
      entry.rows=(j.rows||[]).map(x=>({...x,_sel:!x.exists}));}   // 이미 등록된 사람은 기본 미선택
    catch(e){alert('인원정보호출 실패: '+e);entry.rows=[];}
    entry.loading=false;draw();};
  const saveBulk=async()=>{const sel=entry.rows.filter(r=>r._sel);
    if(!sel.length){alert('저장할 인원을 선택하세요');return;}
    const rows=sel.map(r=>({gubun:entry.gubun,work_ymd:entry.ymd,dept_code:r.dept_code,user_id:r.user_id,line:r.line,
      start_time:r.start_time,end_time:r.end_time,work_hr:r.work_hr,hr_check:r.hr_check,remarks:r.remarks||''}));
    try{const r=await fetch(`${API}/api/gongsu/save_bulk`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows,uuser:uname()})});
      const j=await r.json();if(j.ok){entry.open=false;entry.rows=[];msg=`✅ 공수 ${j.ins}건 등록`;F.from=entry.ymd;F.to=entry.ymd;await load();}else alert('저장 실패: '+(j.detail||''));}
    catch(e){alert('저장 오류: '+e);}};
  const delRow=async(id)=>{if(!confirm('이 공수 기록을 삭제할까요?'))return;
    try{const r=await fetch(`${API}/api/gongsu/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[id]})});
      const j=await r.json();if(j.ok){msg='🗑 삭제 완료';await load();}else alert('삭제 실패');}
    catch(e){alert('삭제 오류: '+e);}};
  const entryPanel=()=>{const ed=canEd();
    return `<div style="background:#f4f8ff;border:1px solid #cddcf3;border-radius:8px;padding:10px;margin:6px 0">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <b style="color:#1c47a0">👥 인원정보호출</b>
        <label class="tl">기준일</label><input class="inp" type="date" id="gs-eymd" value="${entry.ymd}">
        <label class="tl">구분</label><select class="inp" id="gs-egubun" style="width:80px">${['근무','지원'].map(g=>`<option${entry.gubun===g?' selected':''}>${g}</option>`).join('')}</select>
        <label class="tl">투입파트</label>
        <select class="inp" id="gs-epart" style="min-width:200px"><option value=""${entry.part===''?' selected':''}>전체</option>${parts.map(p=>`<option value="${esc(p.code)}"${entry.part===p.code?' selected':''}>${esc(p.code)}${p.nm?' · '+esc(p.nm):''}</option>`).join('')}</select>
        <button class="btn" id="gs-call" style="background:#1c47a0;color:#fff">📥 인원정보호출</button>
        ${entry.rows.length?`<div style="flex:1"></div><span style="color:#5a6b82">선택 ${entry.rows.filter(r=>r._sel).length}/${entry.rows.length}명</span>
        ${ed?`<button class="btn" id="gs-bulksave" style="background:#1c7c3a;color:#fff">💾 선택 일괄저장</button>`:''}`:''}
        <button class="btn ghost" id="gs-eclose">닫기</button>
      </div>
      ${entry.loading?'<div class="page-sub">불러오는 중…</div>':(entry.rows.length?`
      <div class="grid-wrap" style="max-height:340px;overflow:auto;margin-top:8px;background:#fff;border:1px solid #d3ddeb;border-radius:6px">
       <table class="tbl fit" style="font-size:12px"><thead><tr>
        <th class="center" style="width:34px"><input type="checkbox" id="gs-all" ${entry.rows.every(r=>r._sel)?'checked':''}></th>
        <th style="text-align:left">작업자</th><th class="center">시작</th><th class="center">종료</th><th class="num">근무h</th><th class="center">근태</th><th style="text-align:left">비고</th><th class="center">상태</th></tr></thead>
       <tbody>${entry.rows.map((r,i)=>`<tr style="${r.exists?'background:#fff7f2':''}">
        <td class="center"><input type="checkbox" class="gs-sel" data-i="${i}" ${r._sel?'checked':''}></td>
        <td style="text-align:left"><b>${esc(r.user_id)}</b>${r.real?'':' <span style="color:#c8a15a;font-size:11px">비실작업</span>'}</td>
        <td class="center"><input class="inp gs-f" data-i="${i}" data-k="start_time" value="${esc(r.start_time)}" style="width:50px;text-align:center;font-size:12px;padding:1px 3px"></td>
        <td class="center"><input class="inp gs-f" data-i="${i}" data-k="end_time" value="${esc(r.end_time)}" style="width:50px;text-align:center;font-size:12px;padding:1px 3px"></td>
        <td class="num"><input class="inp gs-f" data-i="${i}" data-k="work_hr" value="${r.work_hr}" style="width:44px;text-align:right;font-size:12px;padding:1px 3px"></td>
        <td class="center"><select class="inp gs-f" data-i="${i}" data-k="hr_check" style="font-size:12px;padding:1px">${HRCHK.map(([v,t])=>`<option value="${v}"${r.hr_check===v?' selected':''}>${t}</option>`).join('')}</select></td>
        <td style="text-align:left"><input class="inp gs-f" data-i="${i}" data-k="remarks" value="${esc(r.remarks||'')}" style="width:100%;font-size:12px;padding:1px 3px"></td>
        <td class="center">${r.exists?'<span style="color:#c0392b;font-size:11px">이미등록</span>':'<span style="color:#1c7c3a;font-size:11px">신규</span>'}</td></tr>`).join('')}</tbody></table></div>`:'<div class="page-sub" style="margin-top:6px;color:#8aa0bd">파트를 선택하고 📥 인원정보호출을 누르면 등록 작업자가 채워집니다.</div>')}
    </div>`;};
  const draw=()=>{if(!body)return;const ed=canEd();
    body.innerHTML=`
     <div class="toolbar">
       <label class="tl">근무일</label><input class="inp" type="date" id="gs-from" value="${F.from}"> ~ <input class="inp" type="date" id="gs-to" value="${F.to}">
       <label class="tl">구분</label><input class="inp" id="gs-gubun" value="${esc(F.gubun)}" style="width:60px">
       <label class="tl">부서</label><input class="inp" id="gs-dept" value="${esc(F.dept)}" style="width:70px">
       <label class="tl">작업자</label><input class="inp" id="gs-user" value="${esc(F.user)}" style="width:90px">
       <button class="btn" id="gs-search">🔍 조회</button>
       ${ed?`<button class="btn" id="gs-newentry" style="background:#1c7c3a;color:#fff">👥 근무공수등록</button>`:''}
       <div class="spacer"></div><span class="rowcount">${won(data.cnt)}건 · 공수합 <b>${_wnf(data.sum_hr)}</b>h</span>
     </div>
     ${msg?`<div class="page-sub" style="color:${msg.includes('실패')||msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(msg)}</div>`:''}
     ${entry.open?entryPanel():''}
     <div class="grid-wrap" style="max-height:calc(100vh - ${entry.open?'560':'320'}px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:12px"><thead><tr>
       <th class="center">구분</th><th class="center">근무일</th><th>부서</th><th>작업자</th><th class="center">라인</th>
       <th class="center">시작</th><th class="center">종료</th><th class="num">근무h</th><th class="center">지원h</th><th class="center">근태</th><th>비고</th><th class="center">출처</th>${ed?'<th></th>':''}</tr></thead>
      <tbody>${loading?spinRow(ed?13:12):((data.rows&&data.rows.length)?data.rows.map(r=>(editId&&r.ID===editId)?`<tr style="background:#fffbea">
        <td class="center"><select class="inp ge-gubun" style="width:64px;padding:1px 2px"><option value="근무"${r.gubun!=='지원'?' selected':''}>근무</option><option value="지원"${r.gubun==='지원'?' selected':''}>지원</option></select></td>
        <td class="center"><input class="inp ge-ymd" type="date" value="${esc(_wiso(r.work_ymd))}" style="width:130px;padding:1px 2px"></td>
        <td>${esc(r.dept_nm||r.dept_code)}</td><td>${esc(r.user_id)}</td>
        <td class="center"><input class="inp ge-line" value="${esc(r.line||'')}" style="width:52px;padding:1px 2px"></td>
        <td class="center"><input class="inp ge-st" value="${esc(r.start_time||'')}" style="width:48px;padding:1px 2px" placeholder="0800"></td>
        <td class="center"><input class="inp ge-et" value="${esc(r.end_time||'')}" style="width:48px;padding:1px 2px" placeholder="1700"></td>
        <td class="num"><input class="inp ge-hr" type="number" step="any" value="${r.work_hr??''}" style="width:56px;padding:1px 2px;text-align:right"></td>
        <td class="center"><input class="inp ge-shr" type="number" step="any" value="${r.support_hr??''}" style="width:52px;padding:1px 2px;text-align:right"></td>
        <td class="center"><select class="inp ge-chk" style="width:64px;padding:1px 2px">${HRCHK.map(([v,n])=>`<option value="${v}"${String(r.hr_check||'0')===v?' selected':''}>${n}</option>`).join('')}</select></td>
        <td><input class="inp ge-rmk" value="${esc(r.remarks||'')}" style="width:100%;padding:1px 2px"></td>
        <td class="center"><span style="color:#1c7c3a;font-size:11px">웹</span></td>
        <td class="center" style="white-space:nowrap"><button class="btn ge-save" data-id="${r.ID}" style="padding:1px 6px;background:#1c7c3a;color:#fff">저장</button> <button class="btn ghost ge-cancel" style="padding:1px 5px">✖</button></td></tr>`:`<tr>
        <td class="center">${r.gubun==='지원'?'<span class="bdg" style="background:#e7f0ff;color:#1c47a0">지원</span>':'<span class="bdg ok">근무</span>'}</td>
        <td class="center">${esc(_wymd(r.work_ymd))}</td><td>${esc(r.dept_nm||r.dept_code)}</td><td>${esc(r.user_id)}</td><td class="center">${esc(r.line)}</td>
        <td class="center">${esc(r.start_time)}</td><td class="center">${esc(r.end_time)}</td><td class="num">${_wnf(r.work_hr)}</td>
        <td class="center">${r.support_hr?_wnf(r.support_hr):''}</td>
        <td class="center">${r.hr_check_nm==='정상'?'':`<span style="color:#c0392b">${esc(r.hr_check_nm)}</span>`}</td>
        <td class="bcap" title="${esc(r.remarks)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.remarks)}</td>
        <td class="center">${r.editable?'<span style="color:#1c7c3a;font-size:11px">웹</span>':'<span style="color:#8aa0bd;font-size:11px">📁이력</span>'}</td>
        ${ed?`<td class="center" style="white-space:nowrap">${r.editable&&r.ID?`<button class="btn ghost gs-edit" data-id="${r.ID}" style="padding:1px 6px;color:#2f6db3">✎</button> <button class="btn ghost gs-del" data-id="${r.ID}" style="padding:1px 6px;color:#c0392b">🗑</button>`:''}</td>`:''}</tr>`).join(''):`<tr><td colspan="${ed?13:12}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>body.querySelector(id);
    g('#gs-search').onclick=()=>{F.from=g('#gs-from').value;F.to=g('#gs-to').value;F.gubun=g('#gs-gubun').value;F.dept=g('#gs-dept').value;F.user=g('#gs-user').value;load();};
    ['#gs-gubun','#gs-dept','#gs-user'].forEach(id=>{const el=g(id);if(el)el.onkeyup=e=>{if(e.key==='Enter')g('#gs-search').click();};});
    const nb=g('#gs-newentry');if(nb)nb.onclick=()=>{if(!entry.open){entry.part='';entry.rows=[];}entry.open=!entry.open;draw();};   // 열 때마다 투입파트=전체로 초기화
    body.querySelectorAll('.gs-del').forEach(b=>b.onclick=()=>delRow(+b.dataset.id));
    // ★행 수정(인라인) — ✎ 클릭 시 편집모드. 근태선택=시간·근무h 자동, 시간수정=근무h 재계산.
    body.querySelectorAll('.gs-edit').forEach(b=>b.onclick=()=>{editId=+b.dataset.id;draw();});
    const ec=body.querySelector('.ge-cancel');if(ec)ec.onclick=()=>{editId=null;draw();};
    if(editId){
      const q=s=>body.querySelector(s);
      const chk=q('.ge-chk'), st=q('.ge-st'), et=q('.ge-et'), hr=q('.ge-hr');
      const sync=()=>{if(hr)hr.value=calcHr(st&&st.value,et&&et.value);};
      if(chk)chk.onchange=()=>{const p=HRPRE[chk.value];
        if(p){if(st)st.value=p[0];if(et)et.value=p[1];if(hr)hr.value=(chk.value==='1')?0:calcHr(p[0],p[1]);}};
      [st,et].forEach(el=>{if(el)el.onchange=sync;});
      const sv=q('.ge-save');
      if(sv)sv.onclick=async()=>{
        const row=(data.rows||[]).find(x=>x.ID===editId)||{};
        const body2={id:editId, gubun:q('.ge-gubun').value, work_ymd:(q('.ge-ymd').value||'').replace(/-/g,'').slice(2),
          dept_code:row.dept_code||'', user_id:row.user_id||'', line:q('.ge-line').value,
          start_time:q('.ge-st').value, end_time:q('.ge-et').value, work_hr:+q('.ge-hr').value||0,
          support_line:row.support_line||'', support_start:row.support_start||'', support_end:row.support_end||'',
          support_hr:+q('.ge-shr').value||0, hr_check:q('.ge-chk').value, remarks:q('.ge-rmk').value, uuser:uname()};
        sv.disabled=true;sv.textContent='저장중…';
        try{const r=await fetch(`${API}/api/gongsu/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body2)});
          const j=await r.json();
          if(j.ok){editId=null;load();}else{alert('수정 실패: '+(j.detail||JSON.stringify(j)));sv.disabled=false;sv.textContent='저장';}}
        catch(e){alert('수정 실패: '+e);sv.disabled=false;sv.textContent='저장';}};
    }
    // 인원정보호출 패널 와이어
    if(entry.open){
      const ey=g('#gs-eymd');if(ey)ey.onchange=()=>{entry.ymd=ey.value;};
      const eg=g('#gs-egubun');if(eg)eg.onchange=()=>{entry.gubun=eg.value;};
      const ep=g('#gs-epart');if(ep)ep.onchange=()=>{entry.part=ep.value;};
      const cb=g('#gs-call');if(cb)cb.onclick=callPersons;
      const cl=g('#gs-eclose');if(cl)cl.onclick=()=>{entry.open=false;draw();};
      const bs=g('#gs-bulksave');if(bs)bs.onclick=saveBulk;
      const all=g('#gs-all');if(all)all.onchange=()=>{entry.rows.forEach(r=>r._sel=all.checked);draw();};
      body.querySelectorAll('.gs-sel').forEach(x=>x.onchange=()=>{entry.rows[+x.dataset.i]._sel=x.checked;draw();});
      // ★2026-08-23 근태·시간 연동(수정행과 동일 규칙)
      //   근태 선택 → 시작/종료/근무h 자동세팅, 시작·종료 직접수정 → 근무h 재계산.
      const _rowEls=i=>({st:body.querySelector(`.gs-f[data-i="${i}"][data-k="start_time"]`),
                         et:body.querySelector(`.gs-f[data-i="${i}"][data-k="end_time"]`),
                         hr:body.querySelector(`.gs-f[data-i="${i}"][data-k="work_hr"]`)});
      body.querySelectorAll('.gs-f').forEach(inp=>{
        const i=+inp.dataset.i, k=inp.dataset.k;
        const apply=()=>{entry.rows[i][k]=inp.value;
          const e=_rowEls(i);
          if(k==='hr_check'){const p=HRPRE[inp.value];
            if(p){if(e.st){e.st.value=p[0];entry.rows[i].start_time=p[0];}
                  if(e.et){e.et.value=p[1];entry.rows[i].end_time=p[1];}
                  const h=(inp.value==='1')?0:calcHr(p[0],p[1]);
                  if(e.hr){e.hr.value=h;}entry.rows[i].work_hr=h;}}
          else if(k==='start_time'||k==='end_time'){
            const h=calcHr(e.st&&e.st.value, e.et&&e.et.value);
            if(e.hr){e.hr.value=h;}entry.rows[i].work_hr=h;}};
        inp.oninput=apply; if(inp.tagName==='SELECT')inp.onchange=apply;
      });
    }
  };
  wrShell(c,{sid:'gongsu', nxOnly:true,
    title:`⏱️ 공수등록 <span style="font-size:12px;color:var(--muted);font-weight:400">근무/지원 공수(등록·수정·삭제)</span>`,
    sub:`부서·작업자별 근무/지원 공수. 조회=<code>nx.hr_work_info</code>(웹) ∪ <code>HR_M_WORK_INFO</code> 미러(📁읽기전용 이력). 👥 인원정보호출=파트별 등록작업자 자동채움.`,
    cfg:{sid:'gongsu', _custom:(bd)=>{body=bd;(async()=>{await loadParts();await load();})();}}
  });
};

/* ===== 일반업무: 일일체크리스트 (DAY_CHECK_LIST 라이브 조회, 과거이력 안내) ===== */
SCREEN.daycheck=(c)=>{
  const API=API_BASE;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  let F={from:nowMS(),to:nowCD(),dept:''}, data={rows:[],cnt:0,note:''}, loading=false, msg='';
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,dept:F.dept});
    try{const r=await fetch(`${API}/api/daycheck/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';data={rows:[],cnt:0};}
    loading=false;draw();};
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">📋 일일체크리스트 <span style="font-size:12px;color:var(--muted);font-weight:400">부서간 일일 이슈/체크</span></div>
     <div class="page-sub">부서간 일일 이슈·체크 공유(라이브·읽기전용). 원본 <code>DAY_CHECK_LIST</code>.</div>
     ${data.note?`<div class="page-sub" style="color:#b8860b">ℹ ${esc(data.note)} (최신 ${esc(_wymd(data.max_ymd))})</div>`:''}
     <div class="toolbar">
       <label class="tl">일자</label><input class="inp" type="date" id="dc-from" value="${F.from}"> ~ <input class="inp" type="date" id="dc-to" value="${F.to}">
       <label class="tl">부서</label><input class="inp" id="dc-dept" value="${esc(F.dept)}" style="width:120px">
       <button class="btn" id="dc-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(data.cnt)}건</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr><th>일자</th><th>부서</th><th>요청자</th><th>이슈항목</th><th>이슈내용</th><th>내용/조치</th><th class="center">결과</th><th>결과자</th><th class="center">중요</th></tr></thead>
      <tbody>${loading?spinRow(9):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td class="center">${esc(_wymd(r.ymd))}</td><td>${esc(r.dept)}</td><td>${esc(r.req)}</td>
        <td>${esc(r.item)}</td><td class="bcap" title="${esc(r.note)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.note)}</td>
        <td class="bcap" title="${esc(r.contents)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.contents)}</td>
        <td class="center">${esc(r.result)}</td><td>${esc(r.rmember)}</td><td class="center">${r.imp?'⭐':''}</td></tr>`).join(''):`<tr><td colspan="9" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#dc-search').onclick=()=>{F.from=g('#dc-from').value;F.to=g('#dc-to').value;F.dept=g('#dc-dept').value;load();};
    g('#dc-dept').onkeyup=e=>{if(e.key==='Enter')g('#dc-search').click();};
  };
  load();
};

/* ===== 생산 ⑨: 공정별 생산실적등록 (w_pr_input_260) — PR_T_PROD_DTL 실적 이력 ===== */
SCREEN.procresult=(c)=>{
  const wrLiveProc=(body)=>{
    const API=API_BASE;
    const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
    const T=new Date();
    let F={from:iso(new Date(T.getFullYear(),T.getMonth(),1)),to:iso(T),swork:'',line:'',item:''};
    let data={rows:[],cnt:0,sum_qty:0}, loading=false, msg='';
    const load=async()=>{loading=true;draw();
      const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,swork:F.swork,line:F.line,item:F.item});
      try{const r=await fetch(`${API}/api/procresult/dtl?${qs}`);data=await r.json();msg='';}
      catch(e){msg='백엔드 연결 실패';data={rows:[],cnt:0,sum_qty:0};}
      loading=false;draw();};
    const draw=()=>{
      body.innerHTML=`
       <div class="toolbar">
         <label class="tl">생산기간</label><input class="inp" type="date" id="pc-from" value="${F.from}"> ~ <input class="inp" type="date" id="pc-to" value="${F.to}">
         <label class="tl">공정</label><input class="inp" id="pc-sw" value="${esc(F.swork)}" style="width:70px">
         <label class="tl">라인</label><input class="inp" id="pc-line" value="${esc(F.line)}" style="width:60px">
         <label class="tl">품번</label><input class="inp" id="pc-item" value="${esc(F.item)}" style="width:120px">
         <button class="btn" id="pc-search">🔍 조회</button>
         <div class="spacer"></div><span class="rowcount">${_wnf(data.cnt)}건 · 생산수량합 <b>${_wnf(data.sum_qty)}</b></span>
       </div>
       ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
       <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" style="font-size:11px"><thead><tr><th>생산일자</th><th>시각</th><th>WORK-ORDER</th><th>도번</th><th>품명</th><th>파트</th><th>공정</th><th>라인</th><th class="num">생산수량</th><th>작업자</th></tr></thead>
        <tbody>${loading?spinRow(10):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
          <td class="center">${_wymd(r.PROD_YMD)}</td><td class="center">${_whms(r.PROD_HMS)}</td><td>${esc(r.wo)}</td><td><b>${esc(r.item)}</b></td>
          <td class="bcap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
          <td class="center">${esc(r.part)}</td><td class="center">${esc(r.sw)}</td><td class="center">${esc(r.line)}</td>
          <td class="num"><b>${_wnf(r.PROD_QTY)}</b></td><td>${esc(r.usr)}</td></tr>`).join(''):`<tr><td colspan="10" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
      const g=id=>body.querySelector(id);
      g('#pc-search').onclick=()=>{F.from=g('#pc-from').value;F.to=g('#pc-to').value;F.swork=g('#pc-sw').value;F.line=g('#pc-line').value;F.item=g('#pc-item').value;load();};
      ['#pc-sw','#pc-line','#pc-item'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#pc-search').click();});
    };
    load();
  };
  wrShell(c,{sid:'procresult', nxOnly:true,
    title:`✅ 공정별 생산실적등록 <span style="font-size:12px;color:var(--muted);font-weight:400">공정별 생산실적(등록·수정·삭제)</span>`,
    sub:`공정별 생산실적(제번·품목·공정·수량). 조회=📁미러이력(<code>PR_T_PROD_DTL</code>)∪웹편집(<code>nx.proc_result</code>). 레거시 라이브 없음(컷오버).`,
    default:'edit',
    live:wrLiveProc,
    cfg:{
      listEp:'/api/procreg/list', saveEp:'/api/procreg/save', delEp:'/api/procreg/delete', days:3,
      dateLabel:'생산기간', filters:[{k:'swork',label:'공정',width:60},{k:'line',label:'라인',width:50},{k:'item',label:'품번',width:120},{k:'wo',label:'WO',width:100}],
      buildQS:F=>({from_ymd:F.from,to_ymd:F.to,swork:F.swork||'',line:F.line||'',item:F.item||'',wo:F.wo||''}),
      sum:d=>`생산수량합 <b>${_wnf(d.sum_qty)}</b>`,
      cols:[
        {h:'생산일자',cls:'center',fmt:r=>_wymd(r.PROD_YMD)},
        {h:'시각',cls:'center',fmt:r=>_whms(r.PROD_HMS)},
        {h:'WORK-ORDER',k:'wo'},
        {h:'도번',fmt:r=>`<b>${esc(r.item)}</b>`},
        {h:'품명',k:'nm',cap:1,title:'nm'},
        {h:'파트',k:'part',cls:'center'},
        {h:'공정',k:'sw',cls:'center'},
        {h:'라인',k:'line',cls:'center'},
        {h:'생산수량',cls:'num',fmt:r=>`<b>${_wnf(r.PROD_QTY)}</b>`},
        {h:'완료',cls:'center',fmt:r=>r.fin==='5'?'✔':''},
        {h:'작업자',k:'usr'},
      ],
      form:[
        {k:'prod_ymd',label:'생산일자',type:'date',required:1,width:140},
        {k:'work_order',label:'WO',width:110},{k:'split_work_order',label:'분할WO',width:110},
        {k:'item_code',label:'도번',required:1,search:1,width:150},
        {k:'part_code',label:'파트',width:60},{k:'s_work_code',label:'공정',type:'num',width:70},{k:'line_no',label:'라인',width:60},
        {k:'prod_qty',label:'생산수량',type:'num',width:90},{k:'work_code',label:'작업처',width:60},
        {k:'finish_flag',label:'완료',type:'select',opts:[{v:'0',t:'진행'},{v:'5',t:'완료'}],width:90},
      ],
      newRow:F=>({id:null,prod_ymd:F.to,work_order:'',split_work_order:'',item_code:'',part_code:'',s_work_code:'',line_no:'',prod_qty:'',work_code:'',finish_flag:'0'}),
      fromRow:r=>({id:r.ID,prod_ymd:_y6(r.PROD_YMD),prod_hms:r.PROD_HMS,work_order:r.wo,split_work_order:r.swo,item_code:r.item,part_code:r.part,s_work_code:r.sw,line_no:r.line,prod_qty:r.PROD_QTY,work_code:r.work_code,finish_flag:r.fin||'0'}),
      toBody:f=>({id:f.id,prod_ymd:f.prod_ymd,prod_hms:f.prod_hms||'',work_order:f.work_order,split_work_order:f.split_work_order,item_code:f.item_code,part_code:f.part_code,s_work_code:f.s_work_code,line_no:f.line_no,prod_qty:f.prod_qty,work_code:f.work_code,finish_flag:f.finish_flag,user:'웹사용자'}),
    }
  });
};
