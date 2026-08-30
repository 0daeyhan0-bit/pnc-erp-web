/* ===== PNC ERP screens.pur.js — 구매/자재 SCREEN (app.js 분할, 순수이동) ===== */
SCREEN.mat=(c)=>itemLiveView(c,true);

/* 자재재고입출고현황 (구매/자재, dw_pu_stock_060) — 마스터-디테일. 좌: 자재창고(IS0001) 재고, 우: 선택품목 입출고이력(누적재고). 수불장 정본 기준 */
SCREEN.matinout=(c)=>{
  const API=API_BASE;
  let stockAll=[], stock=[], moves=[], bfMap={}, byMat={}, curYm='', loading=false, msg='';
  const fmtYmd=y=>{y=(''+(y||'')).trim();return (y.length>=6&&y!=='000000')?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'00/00/00';};
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  const WHN={Z99990:'피앤씨창고'}, PWN={IS0001:'자재창고',IS0002:'부자재창고(미키팅)'};
  const pwName=p=>PWN[(''+(p||'')).trim()]||(''+(p||'')).trim();
  const iso2ymd=v=>{v=(''+(v||'')).trim();return v.length>=10?v.slice(2).replace(/-/g,''):'';};   // 2026-07-01 → 260701
  const ymd2iso=y=>{y=(''+(y||'')).trim();return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const todayIso=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const m1Iso=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-01`;};
  // ★2026-08-25 기본 소스 nx(=라이브 미러 + 웹실적). 생산·제품 입출고와 통일.
  let sel=null, curL=[], curFrom='', curTo='', source='nx';
  const load=async()=>{loading=true;msg='';sel=null;
    const st=c.querySelector('#lbody');if(st)st.innerHTML=spinRow(5);
    const sc=(c.querySelector('#whcust')?c.querySelector('#whcust').value:'Z99990')||'Z99990';
    const pw=(c.querySelector('#partwh')?c.querySelector('#partwh').value:'IS0001')||'IS0001';
    const f6=iso2ymd(c.querySelector('#dfrom')?c.querySelector('#dfrom').value:'')||iso2ymd(m1Iso());
    const t6=iso2ymd(c.querySelector('#dto')?c.querySelector('#dto').value:'')||iso2ymd(todayIso());
    const qv=(c.querySelector('#q')?c.querySelector('#q').value:'').trim();   // ★품번(자도번/품명): 입력 시 서버 스코프
    curFrom=f6;curTo=t6;   // ★요청 기간을 먼저 반영 → 조회 실패(타임아웃)해도 날짜 안 되돌아감
    // ★2026-08-25 source 의미 통일: nx=라이브+웹실적(일반그리드) / live=라이브만 / ledger=웹원장 파생
    if(source==='ledger'){loading=false;return nxDerivedView(c,`${API}/api/live/matinout?from_ymd=${f6}&to_ymd=${t6}&source=ledger`,{title:'자재입출고현황(웹원장)',onBack:()=>{source='nx';load();}});}
    try{const r=await fetch(`${API}/api/live/matinout?from_ymd=${f6}&to_ymd=${t6}&stock_cust=${encodeURIComponent(sc)}&part_wh=${encodeURIComponent(pw)}&source=${encodeURIComponent(source)}`+(qv?`&q=${encodeURIComponent(qv)}`:''));if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();curFrom=j.from_ymd||f6;curTo=j.to_ymd||t6;stockAll=j.stock||[];moves=j.moves||[];
      stock=stockAll.filter(s=>Math.abs(+s.stock||0)>0.0001);
      bfMap={};stockAll.forEach(s=>bfMap[s.mat]=+s.bf||0);
      byMat={};moves.forEach(x=>{(byMat[x.mat]=byMat[x.mat]||[]).push(x);});
      const buys=[...new Set(stockAll.map(x=>(''+(x.cust||'')).trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));
      const bdl=c.querySelector('#mio-buydl');if(bdl)bdl.innerHTML=buys.map(x=>`<option value="${esc(x)}">`).join('');
      const sells=[...new Set(moves.filter(x=>(+x.o||0)>0).map(x=>(''+(x.cust||'')).trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ko'));
      const sdl=c.querySelector('#mio-selldl');if(sdl)sdl.innerHTML=sells.map(x=>`<option value="${esc(x)}">`).join('');}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';stockAll=[];stock=[];moves=[];}
    loading=false;
    const df=c.querySelector('#dfrom');if(df)df.value=ymd2iso(curFrom);
    const dt=c.querySelector('#dto');if(dt)dt.value=ymd2iso(curTo);
    const sub=c.querySelector('#mio-sub');if(sub)sub.innerHTML=`${esc(WHN[sc]||sc)} · ${esc(pwName(pw))} 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PU_T_STOCK_MAINT</code> 외 · 🟢 nx ${esc(fmtYmd(curFrom))}~${esc(fmtYmd(curTo))} · 0재고 숨김`;
    renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 자도번을 클릭하세요</div>';};
  c.innerHTML=`
   <style>
     /* 사용이력 = "업체명 : OO, 세트품번 : AJR…" 라 길다. 전역 .cap(86px) 대신 넉넉히(2026-08-23) */
     .tbl th.mio-uh,.tbl td.mio-uh{min-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
   </style>
   <div class="page-title">🔁 자재 입출고현황</div>
   <div class="page-sub" id="mio-sub">재고창고·파트창고 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PU_T_STOCK_MAINT</code> 외 · 🟢 nx · 0재고 숨김</div>
   <div class="toolbar">
     <label class="tl">조회기간</label><input type="date" class="inp" id="dfrom" value="${m1Iso()}" style="min-width:130px"> ~ <input type="date" class="inp" id="dto" value="${todayIso()}" style="min-width:130px">
     <label class="tl">재고창고</label><select class="sel" id="whcust"><option value="Z99990">피앤씨창고</option></select>
     <label class="tl">파트창고</label><select class="sel" id="partwh"><option value="IS0001">자재창고</option><option value="IS0002">부자재창고(미키팅)</option></select>
     <input class="inp" id="q" placeholder="자도번/품명" style="width:120px"><input class="inp" id="qbuy" list="mio-buydl" autocomplete="off" placeholder="매입처" style="width:100px"><datalist id="mio-buydl"></datalist><input class="inp" id="qsell" list="mio-selldl" autocomplete="off" placeholder="매출처" style="width:100px"><datalist id="mio-selldl"></datalist><select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div style="display:flex;gap:10px;align-items:flex-start">
     <div style="flex:0 0 42%;min-width:0">
       <div class="summary-bar" id="lsum"></div>
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr><th>자도번</th><th>품명</th><th>매입처</th><th>파트창고</th><th class="num">재고</th><th class="center">최종입고일</th><th class="center">최종출고일</th></tr></thead><tbody id="lbody"></tbody></table></div>
       <div class="rowcount" id="lcnt"></div>
     </div>
     <div style="flex:1;min-width:0">
       <div class="summary-bar" id="rhead"><div class="s-item">← 좌측에서 자도번을 클릭하세요</div></div>
       <div class="grid-wrap" style="max-height:548px;overflow:auto"><table class="tbl fit"><thead><tr><th class="center">일자</th><th class="num">전일재고</th><th class="num">입고</th><th class="num">출고</th><th class="num">재고조정</th><th class="num">재고이동</th><th class="num">재고수량</th><th>구분</th><th class="mio-uh">사용이력</th><th class="center">작업시간</th></tr></thead><tbody id="rbody"></tbody></table></div>
     </div>
   </div>`;
  const renderRight=mat=>{
    const s=stockAll.find(x=>x.mat===mat)||{}; const bf=bfMap[mat]||0;
    // 같은 날짜 안에서는 작업시간(INSERT_DATETIME) 순 — 레거시와 행 순서를 맞춘다
    const lines=(byMat[mat]||[]).slice().sort((a,b)=>
      (''+a.ymd).localeCompare(''+b.ymd,'ko') || (''+(a.wt||'')).localeCompare(''+(b.wt||''),'ko'));
    // ★사용이력(레거시 w_pu_stock_060_wh) — 입고: "업체명 : OO, 세트품번 : AJR…" / 출고: "세트품번 : AJR…"
    //   원천 PU_T_STOCK_MAINT.ITEM_CODE(상위·세트품번) + INSERT_DATETIME(작업시간). 2026-08-23 추가.
    const useHist=r=>{
      const p=[];
      if(r.cust)p.push(`업체명 : ${r.cust}`);
      if(r.itm) p.push(`세트품번 : ${r.itm}`);
      if(!p.length&&r.wo)p.push(`제번 : ${r.wo}`);
      return p.join(', ');
    };
    let bal=bf, html=`<tr><td class="center">00/00/00</td><td class="num">${won(bf)}</td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num qty"><b>${won(bf)}</b></td><td>전월이월</td><td></td><td></td></tr>`;
    let si=0,so=0,se=0,sm=0;
    lines.forEach(r=>{const prev=bal; const i=+r.i||0,o=+r.o||0,e=+r.e||0,mv=+r.mv||0; bal=prev+i-o+e+mv; si+=i;so+=o;se+=e;sm+=mv;
      const uh=useHist(r);
      html+=`<tr><td class="center">${fmtYmd(r.ymd)}</td><td class="num">${won(prev)}</td><td class="num">${i?won(i):''}</td><td class="num">${o?won(o):''}</td><td class="num">${e?won(e):''}</td><td class="num">${mv?won(mv):''}</td><td class="num qty"><b>${won(bal)}</b></td><td>${esc(r.div)||''}</td><td class="mio-uh" title="${esc(uh)}">${esc(uh)}</td><td class="center" style="white-space:nowrap;font-size:10px;color:#667">${esc(r.wt||'')}</td></tr>`;});
    html+=`<tr class="grandtot"><td class="center">총계</td><td class="num">${won(bf)}</td><td class="num">${won(si)}</td><td class="num">${won(so)}</td><td class="num">${won(se)}</td><td class="num">${won(sm)}</td><td class="num">${won(bal)}</td><td colspan="3"></td></tr>`;
    c.querySelector('#rbody').innerHTML=html;
    c.querySelector('#rhead').innerHTML=`<div class="s-item">자도번 <b>${esc(mat)}</b></div><div class="s-item">${esc(s.nm||'')}</div><div class="s-item">현재고 <b>${won(bal)}</b></div>`;
    attachResizers(c);
  };
  const renderLeft=()=>{
    const q=c.querySelector('#q').value.trim().toLowerCase(), gb=c.querySelector('#gubun').value;
    const qb=c.querySelector('#qbuy').value.trim().toLowerCase();
    const qs=c.querySelector('#qsell').value.trim().toLowerCase();
    const sellMats=qs?new Set(moves.filter(x=>(+x.o||0)>0&&(''+(x.cust||'')).toLowerCase().includes(qs)).map(x=>x.mat)):null;
    curL=stock.filter(s=>(gb==='all'||(gb==='plus'?s.stock>0:s.stock<0))&&(!q||(''+s.mat).toLowerCase().includes(q)||(''+s.nm).toLowerCase().includes(q))&&(!qb||(''+(s.cust||'')).toLowerCase().includes(qb))&&(!sellMats||sellMats.has(s.mat)))
      .sort((a,b)=>(''+a.mat).localeCompare(''+b.mat,'ko'));
    const tot=curL.reduce((a,b)=>a+(+b.stock||0),0);
    let lb=curL.map(s=>`<tr data-mat="${esc(s.mat)}" class="${sel===s.mat?'sel':''}"><td><b>${esc(s.mat)}</b></td><td class="cap" title="${esc(s.nm)}">${esc(s.nm)}</td><td class="cap" title="${esc(s.cust||'')}">${esc(s.cust||'')}</td><td>${esc(pwName(s.part))}</td><td class="num qty">${won(s.stock)}</td><td class="center">${fmtYmd(s.lastin)!=='00/00/00'?fmtYmd(s.lastin):'-'}</td><td class="center">${fmtYmd(s.lastout)!=='00/00/00'?fmtYmd(s.lastout):'-'}</td></tr>`).join('');
    if(curL.length)lb+=`<tr class="grandtot"><td colspan="4" class="right">총계 (${won(curL.length)} 품목)</td><td class="num">${won(tot)}</td><td></td><td></td></tr>`;
    c.querySelector('#lbody').innerHTML=curL.length?lb:`<tr><td colspan="7" class="empty">결과 없음</td></tr>`;
    c.querySelector('#lbody').querySelectorAll('tr[data-mat]').forEach(tr=>tr.onclick=()=>{sel=tr.dataset.mat;c.querySelectorAll('#lbody tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');renderRight(sel);});
    c.querySelector('#lsum').innerHTML=`<div class="s-item">품목 <b>${won(curL.length)}</b></div><div class="s-item">재고 합계 <b>${won(tot)}</b></div>`;
    c.querySelector('#lcnt').textContent=`${curL.length}품목 (0재고 제외)`;
    attachResizers(c);
  };
  c.querySelector('#go').onclick=()=>load();
  c.querySelector('#nxsrc').onclick=()=>{source='nx';load();};   // ★Phase5 nx 파생 보기
  c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')load();else renderLeft();};   // ★Enter=서버 스코프 조회(기간 무관 빠름), 그외=로드된 데이터 클라 필터
  c.querySelector('#qbuy').onkeyup=()=>renderLeft();
  c.querySelector('#qsell').onkeyup=()=>renderLeft();
  c.querySelector('#gubun').onchange=renderLeft;
  bindDate(c.querySelector('#dfrom'),()=>load());
  bindDate(c.querySelector('#dto'),()=>load());
  c.querySelector('#whcust').onchange=()=>load();
  c.querySelector('#partwh').onchange=()=>load();
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#qbuy').value='';c.querySelector('#qsell').value='';c.querySelector('#gubun').value='all';c.querySelector('#partwh').value='IS0001';c.querySelector('#whcust').value='Z99990';c.querySelector('#dfrom').value=m1Iso();c.querySelector('#dto').value=todayIso();sel=null;load();};
  c.querySelector('#xls').onclick=()=>downloadCSV('자재입출고현황.csv',['자도번','품명','매입처','파트창고','재고','최종입고일','최종출고일'],curL.map(s=>[s.mat,s.nm,s.cust||'',pwName(s.part),s.stock,fmtYmd(s.lastin)!=='00/00/00'?fmtYmd(s.lastin):'',fmtYmd(s.lastout)!=='00/00/00'?fmtYmd(s.lastout):'']));
  load();
};

/* 확정입고집계표 (구매/자재, dw_pu_input_120) — 확정입고(검사통과)+수입. 조회기준 마감/입고 × 출력방식 거래처별/품목별/업체별 */
SCREEN.receipt=(c)=>{
  const SG=DB.sgroupNames||{}, CT=DB.custTypeNames||{}, LG=DB.lgroupNames||{}, CHG=DB.chargeMap||{};
  const CURN={KRW:'원',USD:'달러',JPY:'엔',EUR:'유로',CNY:'위안'};
  const sgN=s=>SG[(''+s).trim()]||(''+s).trim()||'', ctN=t=>CT[(''+t).trim()]||(''+t).trim()||'',
        lgN=l=>LG[(''+l).trim()]||(''+l).trim()||'', chg=cc=>CHG[(''+cc).trim()]||'', curN=x=>CURN[(''+x).trim()]||(''+x).trim()||'';
  const rateD=r=>(''+r.cur).trim()==='KRW'?'':won(r.rate);
  const fVat=a=>Math.floor((+a||0)*0.1), S=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
  const API=API_BASE;
  let gijun='close', mode='cust', vat=false, cur=[], pool=[], loading=false, msg='', curYm='', curFrom='', curTo='';   // 빈값 → 백엔드가 당월1일~오늘(실행일자) 기본값 적용
  let F={lg:'',sg:'',ct:'',cq:'',mq:''};   // 필터 상태(draw 재그림에도 유지)
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const dToInput=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-',''), inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const load=async()=>{loading=true;msg='';draw();
    try{const u=gijun==='close'?`${API}/api/live/receipt?gijun=close`+(curYm?`&ym=${curYm}`:'')
        :`${API}/api/live/receipt?gijun=issue&dfrom=${curFrom}&dto=${curTo}`;
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();
      pool=j.rows||[];if(gijun==='close')curYm=j.ym||curYm;else{curFrom=j.dfrom||curFrom;curTo=j.dto||curTo;}}
    catch(e){pool=[];msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';}
    loading=false;draw();};
  const draw=()=>{
    // pool = 라이브 조회결과(load에서 세팅)
    const lgs=[...new Set(pool.map(r=>(''+r.lg).trim()).filter(Boolean))].sort();
    const sgs=[...new Set(pool.map(r=>(''+r.sg).trim()).filter(Boolean))].sort();
    const cts=[...new Set(pool.map(r=>(''+r.ct).trim()).filter(Boolean))].sort();
    c.innerHTML=`
     <div class="page-title">📥 확정입고집계표</div>
     <div class="page-sub">확정입고(검사통과)+수입 · 원본 <code>PU_T_STOCK_MAINT</code>(9/S/C/G/H)+<code>PU_T_STOCK_MAINT_C</code>(P) · 🟢 nx ${gijun==='close'?`마감기준 ${esc(ymToInput(curYm)||'-')}`:`입고기준 ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="close" class="${gijun==='close'?'on':''}">마감기준</button><button data-g="issue" class="${gijun==='issue'?'on':''}">입고기준</button></div>
       <label class="tl">${gijun==='close'?'마감년월':'입고일자'}</label>
       ${gijun==='close'?`<input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||nowCM())}" style="min-width:120px">`:`<input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:130px">`}
       <label class="tl">출력방식</label>
       <select class="sel" id="mode"><option value="cust" ${mode==='cust'?'selected':''}>거래처별</option><option value="item" ${mode==='item'?'selected':''}>품목별</option><option value="agg" ${mode==='agg'?'selected':''}>업체별</option></select>
       <button class="btn ${vat?'':'ghost'}" id="vat">부가세조정</button>
     </div>
     <div class="toolbar">
       <select class="sel" id="lg"><option value="">전체 대분류</option>${lgs.map(x=>`<option value="${esc(x)}" ${F.lg===x?'selected':''}>${esc(lgN(x))}</option>`).join('')}</select>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgs.map(x=>`<option value="${esc(x)}" ${F.sg===x?'selected':''}>${esc(sgN(x))}</option>`).join('')}</select>
       <select class="sel" id="ct"><option value="">전체 매입유형</option>${cts.map(x=>`<option value="${esc(x)}" ${F.ct===x?'selected':''}>${esc(ctN(x))}</option>`).join('')}</select>
       <input class="inp" id="cq" value="${esc(F.cq)}" placeholder="거래처코드/명">
       <input class="inp" id="mq" value="${esc(F.mq)}" placeholder="품번/품명/PART NO">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <span id="derr" style="color:#c0392b;font-size:12px;font-weight:600"></span>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{gijun=b.dataset.g;load();});
    c.querySelector('#mode').onchange=e=>{mode=e.target.value;draw();};
    c.querySelector('#vat').onclick=()=>{vat=!vat;draw();};
    const filt=()=>{const lg=F.lg,sg=F.sg,ct=F.ct,cq=(F.cq||'').trim().toLowerCase(),mq=(F.mq||'').trim().toLowerCase();
      return pool.filter(r=>(!lg||(''+r.lg).trim()===lg)&&(!sg||(''+r.sg).trim()===sg)&&(!ct||(''+r.ct).trim()===ct)
        &&(!cq||(''+r.cc).toLowerCase().includes(cq)||(''+r.cnm).toLowerCase().includes(cq))
        &&(!mq||(''+r.mat).toLowerCase().includes(mq)||(''+r.nm).toLowerCase().includes(mq)||(''+r.ic).toLowerCase().includes(mq)));};
    const money=a=>`<td class="num">${wonI(a)}</td>`;
    // ★금액 기준=KRW(kamt) — 수입 외화도 KRW환산 합산(통화혼합 방지). 부가세/합계도 KRW. 화폐/환율/단가는 참조로 유지.
    const amtHdr=`<th class="num">금액</th>`+(vat?`<th class="num">부가세</th><th class="num">합계</th>`:'');
    const amtCells=r=>`<td class="num gstock">${wonI(r.kamt)}</td>`+(vat?`${money(fVat(r.kamt))}${money(r.kamt+fVat(r.kamt))}`:'');
    const amtSub=g=>`<td class="num gstock">${wonI(g.kamt)}</td>`+(vat?`${money(fVat(g.kamt))}${money(g.kamt+fVat(g.kamt))}`:'');
    const VC=vat?2:0;
    let lines=filt(), tbody='', thead='', ncols=0;
    // 아이템 라인 셀 (거래처별/품목별 공통 우측)
    const itemMid=r=>`<td>${esc(lgN(r.lg))}</td><td>${esc(sgN(r.sg))}</td><td class="center">${esc(r.unit)||''}</td><td class="num">${won(r.qty)}</td><td class="num">${won(r.wt)}</td><td class="center">${esc(curN(r.cur))}</td><td class="num">${rateD(r)}</td><td class="num">${won(r.cost)}</td><td class="num">${won(r.kcost)}</td>${amtCells(r)}`;
    const midHdr=`<th>대분류</th><th>소분류</th><th class="center">단위</th><th class="num">수량</th><th class="num">중량</th><th class="center">화폐</th><th class="num">환율</th><th class="num">단가</th><th class="num">단가(KRW)</th>${amtHdr}`;
    const midK=['lg','sg','unit','qty','wt','cur','rate','cost','kcost','kamt'];
    // 행 템플릿(모드별)+정렬키 — 헤더 더블클릭 정렬(소계무시 평면 렌더)에 재사용. ASY PART NO(ic) 컬럼 제거
    const TPL={
      cust:r=>`<tr><td><b>${esc(r.cc)}</b></td><td class="cap" style="max-width:170px" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap" title="${esc(ctN(r.ct))}">${esc(ctN(r.ct))}</td><td>${esc(r.mat)}</td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td>${itemMid(r)}</tr>`,
      item:r=>`<tr><td><b>${esc(r.mat)}</b></td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td><td class="cap" style="max-width:170px" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap">${esc(ctN(r.ct))}</td>${itemMid(r)}</tr>`,
      agg:r=>{const v6=(''+r.ct).trim()==='6'?'vat6':'';return `<tr><td><b>${esc(r.cc)}</b></td><td class="cap" style="max-width:170px" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td>${esc(chg(r.cc))||'-'}</td><td class="cap">${esc(ctN(r.ct))}</td><td class="num">${won(r.qty)}</td><td class="num gstock">${wonI(r.kamt)}</td><td class="num ${v6}">${wonI(r.kvat)}</td><td class="num">${wonI(r.kamt+r.kvat)}</td></tr>`;},
    };
    const KEYS={cust:['cc','cnm','ct','mat','nm','spec'].concat(midK), item:['mat','nm','spec','cnm','ct'].concat(midK), agg:['cc','cnm','chg','ct','qty','kamt','kvat','kamt']};
    const gsty=' style="position:sticky;bottom:0;background:#e8f0fb;box-shadow:0 -1px 0 #b9cbe6;z-index:3"';
    const grandRow=()=>{const gq=S(cur,'qty'),ga=S(cur,'amt'),gk=S(cur,'kamt');
      if(mode==='agg'){const gkv=S(cur,'kvat');
        return `<tr class="grandtot"${gsty}><td colspan="4" class="right">총계 (${won(cur.length)} 업체)</td><td class="num">${won(gq)}</td><td class="num">${wonI(gk)}</td><td class="num">${wonI(gkv)}</td><td class="num">${wonI(gk+gkv)}</td></tr>`;}
      const lead=mode==='cust'?9:8;
      return `<tr class="grandtot"${gsty}><td colspan="${lead}" class="right">총계</td><td class="num">${won(gq)}</td><td colspan="5"></td>${amtSub({amt:ga,kamt:gk})}</tr>`;};
    if(mode==='cust'){
      cur=lines.slice().sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko')||(''+a.mat).localeCompare(''+b.mat,'ko'));
      thead=`<tr><th>거래처코드</th><th>거래처명</th><th style="min-width:100px">매입유형</th><th>PART NO</th><th>품명</th><th>PART SPEC</th>${midHdr}</tr>`;
      ncols=16+VC;
      const groups=[]; let ck=null;
      cur.forEach(r=>{if(r.cc!==ck){groups.push({cc:r.cc,cnm:r.cnm,rows:[]});ck=r.cc;}groups[groups.length-1].rows.push(r);});
      groups.forEach(g=>{g.rows.forEach(r=>{tbody+=TPL.cust(r);});
        const gs={qty:S(g.rows,'qty'),amt:S(g.rows,'amt'),kamt:S(g.rows,'kamt')};
        tbody+=`<tr class="subtot"><td colspan="9" class="right">(업체계) ${esc(g.cnm)}</td><td class="num">${won(gs.qty)}</td><td colspan="5"></td>${amtSub(gs)}</tr>`;});
    } else if(mode==='item'){
      const map=new Map();
      lines.forEach(r=>{const k=r.ic+'|'+r.mat; if(!map.has(k))map.set(k,{...r,qty:0,amt:0,kamt:0,vat:0,kvat:0}); const o=map.get(k);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.kamt+=+r.kamt||0;o.vat+=+r.vat||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.mat).localeCompare(''+b.mat,'ko'));
      thead=`<tr><th>PART NO</th><th>품명</th><th>PART SPEC</th><th>거래처명</th><th style="min-width:100px">매입유형</th>${midHdr}</tr>`;
      ncols=15+VC;
      cur.forEach(r=>{tbody+=TPL.item(r);});
    } else { // 업체별
      const map=new Map();
      lines.forEach(r=>{if(!map.has(r.cc))map.set(r.cc,{cc:r.cc,cnm:r.cnm,ct:r.ct,qty:0,amt:0,kamt:0,vat:0,kvat:0}); const o=map.get(r.cc);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.kamt+=+r.kamt||0;o.vat+=+r.vat||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko'));
      thead=`<tr><th>거래처코드</th><th>거래처명</th><th>담당자</th><th style="min-width:100px">매입유형</th><th class="num">수량</th><th class="num">금액</th><th class="num">부가세</th><th class="num">합계</th></tr>`;
      ncols=8;
      cur.forEach(r=>{tbody+=TPL.agg(r);});
    }
    tbody+=grandRow();
    c.querySelector('#th').innerHTML=thead;
    c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${ncols}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
      :(msg?`<tr><td colspan="${ncols}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
      :(cur.length?tbody:`<tr><td colspan="${ncols}" class="empty">결과 없음</td></tr>`));
    c.querySelector('#cnt').textContent=`${cur.length}${mode==='agg'?'업체':'라인'} / 대상 ${lines.length}라인`;
    attachResizers(c);
    enableSort(c, KEYS[mode].concat(mode!=='agg'&&vat?['','','','','']:[]), ()=>cur, ()=>{
      let b=''; cur.forEach(r=>b+=TPL[mode](r)); b+=grandRow(); c.querySelector('#body').innerHTML=b;});
    const go=()=>{const de=c.querySelector('#derr');if(de)de.textContent='';
      if(gijun==='close'){const v=c.querySelector('#dto').value;if(!/^\d{4}-\d{2}$/.test(v)){if(de)de.textContent='⚠ 마감년월을 올바르게 입력하세요';return;}curYm=inYm(v);}
      else{const f=c.querySelector('#dfrom').value,t=c.querySelector('#dto').value;
        if(!/^\d{4}-\d{2}-\d{2}$/.test(f)||!/^\d{4}-\d{2}-\d{2}$/.test(t)){if(de)de.textContent='⚠ 입고일자를 올바르게 입력하세요';return;}
        if(f>t){if(de)de.textContent='⚠ 시작일이 종료일보다 늦습니다';return;}curFrom=inD(f);curTo=inD(t);}
      load();};
    const syncF=()=>{F.lg=c.querySelector('#lg').value;F.sg=c.querySelector('#sg').value;F.ct=c.querySelector('#ct').value;F.cq=c.querySelector('#cq').value;F.mq=c.querySelector('#mq').value;};
    c.querySelector('#go').onclick=()=>{syncF();draw();};   // ★검색=필터적용(검색어 유지)
    const _dto=c.querySelector('#dto');if(_dto)_dto.onchange=go;   // 날짜 변경 시만 재조회
    const _dfr=c.querySelector('#dfrom');if(_dfr)_dfr.onchange=go;
    ['#lg','#sg','#ct'].forEach(s=>c.querySelector(s).onchange=()=>{syncF();draw();});
    c.querySelector('#cq').onkeyup=e=>{if(e.key==='Enter'){syncF();draw();}};c.querySelector('#mq').onkeyup=e=>{if(e.key==='Enter'){syncF();draw();}};
    c.querySelector('#reset').onclick=()=>{gijun='close';mode='cust';vat=false;curYm='';F={lg:'',sg:'',ct:'',cq:'',mq:''};load();};
    c.querySelector('#xls').onclick=()=>{let hd,rows;
      if(mode==='agg'){hd=['거래처코드','거래처명','담당자','매입유형','수량','금액','부가세','합계'];
        rows=cur.map(r=>[r.cc,r.cnm,chg(r.cc),ctN(r.ct),r.qty,Math.round(r.kamt),Math.round(r.kvat),Math.round(r.kamt+r.kvat)]);}
      else{const base=['PART NO','품명','PART SPEC','거래처코드','거래처명','매입유형','대분류','소분류','단위','수량','중량','화폐','환율','단가','단가(KRW)','금액'].concat(vat?['부가세','합계']:[]);hd=base;
        rows=cur.map(r=>[r.mat,r.nm,r.spec,r.cc,r.cnm,ctN(r.ct),lgN(r.lg),sgN(r.sg),r.unit,r.qty,r.wt,curN(r.cur),(''+r.cur).trim()==='KRW'?'':r.rate,r.cost,r.kcost,Math.round(r.kamt)].concat(vat?[fVat(r.kamt),Math.round(r.kamt+fVat(r.kamt))]:[]));}
      downloadCSV('확정입고집계표_'+gijun+'_'+mode+'.csv',hd,rows);};
  };
  load();
};

/* 확정입고명세서 (구매/자재, dw_pu_input_110) — 라인단위. 조회기준 마감/입고 × 출력방식 6종 */
SCREEN.receiptdetail=(c)=>{
  const SG=DB.sgroupNames||{}, CT=DB.custTypeNames||{}, LG=DB.lgroupNames||{}, CHG=DB.chargeMap||{};
  const CURN={KRW:'원',USD:'달러',JPY:'엔',EUR:'유로',CNY:'위안'};
  const sgN=s=>SG[(''+s).trim()]||(''+s).trim()||'', ctN=t=>CT[(''+t).trim()]||(''+t).trim()||'',
        lgN=l=>LG[(''+l).trim()]||(''+l).trim()||'', chg=cc=>CHG[(''+cc).trim()]||'', curN=x=>CURN[(''+x).trim()]||(''+x).trim()||'';
  const fmtYmd=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;};
  const fmtYm=y=>{y=(''+(y||'')).trim();return y.length>=4?`${y.slice(0,2)}/${y.slice(2,4)}`:y;};
  const rateD=r=>(''+r.cur).trim()==='KRW'?'':won(r.rate);
  const CD={
    ymd:{h:'입고일자',cls:'center',get:r=>fmtYmd(r.ymd)},
    seq:{h:'입고순번',cls:'center',get:r=>esc(r.seq)},
    ym:{h:'입고년월',cls:'center',get:r=>fmtYm(r.ym)},
    cnm:{h:'거래처',cls:'cap',get:r=>esc(r.cnm)},
    ct:{h:'매입유형',cls:'cap',w:100,get:r=>esc(ctN(r.ct))},
    chg:{h:'담당자',cls:'',get:r=>esc(chg(r.cc))||'-'},
    mat:{h:'입고품번',cls:'',w:96,get:r=>`<b style="display:inline-block;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom" title="${esc(r.mat)}">${esc(r.mat)}</b>`},
    nm:{h:'품명',cls:'cap',get:r=>esc(r.nm)},
    spec:{h:'PART SPEC',cls:'cap',get:r=>esc(r.spec)||''},
    diam:{h:'Φ',cls:'num',get:r=>won(r.diam)},
    thick:{h:'T',cls:'num',get:r=>won(r.thick)},
    length:{h:'L',cls:'num',get:r=>won(r.length)},
    lg:{h:'대분류',cls:'',get:r=>esc(lgN(r.lg))},
    sg:{h:'소분류',cls:'',get:r=>esc(sgN(r.sg))},
    unit:{h:'단위',cls:'center',get:r=>esc(r.unit)||''},
    qty:{h:'입고수량',cls:'num',get:r=>won(r.qty)},
    wt:{h:'중량',cls:'num',get:r=>won(r.wt)},
    cur:{h:'화폐',cls:'center',get:r=>esc(curN(r.cur))},
    rate:{h:'환율',cls:'num',get:r=>rateD(r)},
    cost:{h:'단가',cls:'num',get:r=>won(r.cost)},
    amt:{h:'금액',cls:'num gstock',get:r=>wonI(r.kamt)},   // ★금액 기준=KRW(kamt)
    kamt:{h:'금액(KRW)',cls:'num',get:r=>wonI(r.kamt)},   // (미사용·TAIL서 제외)
  };
  const TAIL=['unit','qty','wt','cur','rate','cost','amt'];   // ★금액(=KRW)만 · 금액(KRW) 중복컬럼 제외
  const ITEM=['mat','nm','spec','diam','thick','length','lg','sg'];
  const MODES={
    day:      {label:'일자별',      lead:['ymd','seq','cnm','ct','chg','ym'].concat(ITEM), sort:['ymd','seq']},
    month:    {label:'월별',        lead:['ym','ymd','seq','cnm','ct','chg'].concat(ITEM), sort:['ym','ymd','seq'], g1:'ym',l1:'월계'},
    cust:     {label:'업체별',      lead:['cnm','ct','chg','ymd','seq','ym'].concat(ITEM), sort:['cc','ymd','seq'], g1:'cc',l1:'업체계'},
    item:     {label:'품목별',      lead:ITEM.concat(['ymd','seq','cnm','ct','chg','ym']), sort:['mat','ymd','seq'], g1:'mat',l1:'품목계'},
    custitem: {label:'업체/품목별',  lead:['cnm','ct','chg'].concat(ITEM,['ymd','seq','ym']), sort:['cc','mat','ymd','seq'], g1:'cc',g2:'mat',l1:'업체계',l2:'품목계'},
    itemcust: {label:'품목/업체별',  lead:ITEM.concat(['cnm','ct','chg','ymd','seq','ym']), sort:['mat','cc','ymd','seq'], g1:'mat',g2:'cc',l1:'품목계',l2:'업체계'},
  };
  const API=API_BASE;
  let gijun='close', mode='day', cur=[], pool=[], loading=false, msg='', curYm='', curFrom='', curTo='', source='live', curMq='';   // ★Phase5 데이터원(기본 라이브 무변경) + curMq=품번 검색어(조회 후 유지·서버 스코프)
  let curCq='', curLg='', curSg='', curCt='';   // ★거래처·대분류·소분류·거래처분류 검색어 유지(재조회·기간변경 시 안없어지게)
  const RENDER_CAP=1500;   // ★초기속도: 비그룹(일자별) 렌더 상한(총계는 전체 기준·엑셀은 전체)
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const dToInput=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-',''), inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const load=async()=>{loading=true;msg='';draw();
    try{const qs=curMq?`&q=${encodeURIComponent(curMq)}`:'';   // ★품번 서버 스코프(미입력=전체·무변경)
      const u=(gijun==='close'?`${API}/api/live/receiptdetail?gijun=close`+(curYm?`&ym=${curYm}`:'')
        :`${API}/api/live/receiptdetail?gijun=issue&dfrom=${curFrom}&dto=${curTo}`)+qs;
      if(source==='nx'){loading=false;return nxDerivedView(c,u+'&source=nx',{title:'자재입고명세서',onBack:()=>{source='live';load();}});}
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();
      pool=j.rows||[];if(gijun==='close')curYm=j.ym||curYm;else{curFrom=j.dfrom||curFrom;curTo=j.dto||curTo;}}
    catch(e){pool=[];msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';}
    loading=false;draw();};
  const draw=()=>{
    // pool = 라이브 조회결과(load에서 세팅)
    pool.forEach(r=>{if(r.ym===undefined)r.ym=(''+r.ymd).slice(0,4);});
    const cfg=MODES[mode], order=cfg.lead.concat(TAIL), qi=order.indexOf('qty');
    const lgs=[...new Set(pool.map(r=>(''+r.lg).trim()).filter(Boolean))].sort();
    const sgs=[...new Set(pool.map(r=>(''+r.sg).trim()).filter(Boolean))].sort();
    const cts=[...new Set(pool.map(r=>(''+r.ct).trim()).filter(Boolean))].sort();
    c.innerHTML=`
     <div class="page-title">🧾 확정입고명세서</div>
     <div class="page-sub">확정입고(검사통과)+수입 라인 명세 · 원본 <code>PU_T_STOCK_MAINT</code>+<code>PU_T_STOCK_MAINT_C</code> · 🟢 nx ${gijun==='close'?`마감기준 ${esc(ymToInput(curYm)||'-')}`:`입고기준 ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="close" class="${gijun==='close'?'on':''}">마감기준</button><button data-g="issue" class="${gijun==='issue'?'on':''}">입고기준</button></div>
       <label class="tl">${gijun==='close'?'마감년월':'입고일자'}</label>
       ${gijun==='close'?`<input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||nowCM())}" style="min-width:120px">`:`<input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:130px">`}
       <label class="tl">출력방식</label>
       <select class="sel" id="mode">${Object.entries(MODES).map(([k,v])=>`<option value="${k}" ${mode===k?'selected':''}>${v.label}</option>`).join('')}</select>
     </div>
     <div class="toolbar">
       <select class="sel" id="lg"><option value="">전체 대분류</option>${lgs.map(x=>`<option value="${esc(x)}" ${curLg===x?'selected':''}>${esc(lgN(x))}</option>`).join('')}</select>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgs.map(x=>`<option value="${esc(x)}" ${curSg===x?'selected':''}>${esc(sgN(x))}</option>`).join('')}</select>
       <select class="sel" id="ct"><option value="">전체 매입유형</option>${cts.map(x=>`<option value="${esc(x)}" ${curCt===x?'selected':''}>${esc(ctN(x))}</option>`).join('')}</select>
       <input class="inp" id="cq" placeholder="거래처코드/명" value="${esc(curCq)}">
       <input class="inp" id="mq" placeholder="품번/품명/PART NO (검색=서버조회)" value="${esc(curMq)}">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
       <span id="derr" style="color:#c0392b;font-size:12px;font-weight:600"></span>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{gijun=b.dataset.g;load();});
    c.querySelector('#mode').onchange=e=>{mode=e.target.value;draw();};
    const filt=()=>{const lg=c.querySelector('#lg').value,sg=c.querySelector('#sg').value,ct=c.querySelector('#ct').value,
        cq=c.querySelector('#cq').value.trim().toLowerCase(),mq=c.querySelector('#mq').value.trim().toLowerCase();
      return pool.filter(r=>(!lg||(''+r.lg).trim()===lg)&&(!sg||(''+r.sg).trim()===sg)&&(!ct||(''+r.ct).trim()===ct)
        &&(!cq||(''+r.cc).toLowerCase().includes(cq)||(''+r.cnm).toLowerCase().includes(cq))
        &&(!mq||(''+r.mat).toLowerCase().includes(mq)||(''+r.nm).toLowerCase().includes(mq)));};
    const rowHtml=r=>`<tr>${order.map(k=>{const cd=CD[k],cap=cd.cls.indexOf('cap')>=0,v=cd.get(r);return `<td class="${cd.cls}"${cap?` title="${esc((''+(k==='cnm'?r.cnm:k==='nm'?r.nm:k==='spec'?r.spec:k==='ct'?ctN(r.ct):'')))}"`:''}>${v}</td>`;}).join('')}</tr>`;
    /* receiptdetail-live */
    const subRow=(label,q,a,k,g)=>`<tr class="${g||'subtot'}"${g==='grandtot'?' style="position:sticky;bottom:0;background:#e8f0fb;box-shadow:0 -1px 0 #b9cbe6;z-index:3"':''}><td colspan="${qi}" class="right">${esc(label)}</td><td class="num">${won(q)}</td><td colspan="4"></td><td class="num">${wonI(k)}</td></tr>`;
    const render=()=>{
      let lines=filt();
      lines.sort((a,b)=>{for(const k of cfg.sort){const c2=(''+(a[k]??'')).localeCompare(''+(b[k]??''),'ko',{numeric:true});if(c2)return c2;}return 0;});
      cur=lines; let html='';
      if(!cfg.g1){ lines.slice(0,RENDER_CAP).forEach(r=>html+=rowHtml(r)); if(lines.length>RENDER_CAP)html+=`<tr><td colspan="${order.length}" class="empty" style="color:#8a6d1c">상위 ${won(RENDER_CAP)}행만 표시 · 전체 ${won(lines.length)}행은 검색어로 좁히거나 엑셀 다운로드</td></tr>`; }
      else { let g1v=null,g2v=null,s1q=0,s1a=0,s1k=0,s2q=0,s2a=0,s2k=0;
        lines.forEach(r=>{const v1=r[cfg.g1], v2=cfg.g2?r[cfg.g2]:null;
          if(g1v!==null && v1!==g1v){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a,s2k); html+=subRow(cfg.l1,s1q,s1a,s1k); s1q=s1a=s1k=s2q=s2a=s2k=0; g2v=null; }
          else if(cfg.g2 && g2v!==null && v2!==g2v){ html+=subRow(cfg.l2,s2q,s2a,s2k); s2q=s2a=s2k=0; }
          html+=rowHtml(r); s1q+=+r.qty||0; s1a+=+r.amt||0; s1k+=+r.kamt||0; s2q+=+r.qty||0; s2a+=+r.amt||0; s2k+=+r.kamt||0; g1v=v1; g2v=v2; });
        if(g1v!==null){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a,s2k); html+=subRow(cfg.l1,s1q,s1a,s1k); }
      }
      const tq=lines.reduce((a,b)=>a+(+b.qty||0),0), ta=lines.reduce((a,b)=>a+(+b.amt||0),0), tk=lines.reduce((a,b)=>a+(+b.kamt||0),0);
      html+=subRow('총계',tq,ta,tk,'grandtot');
      c.querySelector('#th').innerHTML=`<tr>${order.map(k=>`<th class="${CD[k].cls}" data-base="${esc(CD[k].h)}"${CD[k].w?` style="min-width:${CD[k].w}px"`:''}>${CD[k].h}</th>`).join('')}</tr>`;
      c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${order.length}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
        :(msg?`<tr><td colspan="${order.length}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
        :(lines.length?html:`<tr><td colspan="${order.length}" class="empty">결과 없음</td></tr>`));
      c.querySelector('#cnt').textContent=`${lines.length}라인 / 대상 ${pool.length}라인`;
      attachResizers(c);
      enableSort(c, order, ()=>cur, ()=>{
        let h=''; cur.slice(0,RENDER_CAP).forEach(r=>h+=rowHtml(r));
        const gq=cur.reduce((a,b)=>a+(+b.qty||0),0),ga=cur.reduce((a,b)=>a+(+b.amt||0),0),gk=cur.reduce((a,b)=>a+(+b.kamt||0),0);
        h+=subRow('총계',gq,ga,gk,'grandtot');
        c.querySelector('#body').innerHTML=h;
      });
    };
    const go=()=>{const de=c.querySelector('#derr');if(de)de.textContent='';
      if(gijun==='close'){const v=c.querySelector('#dto').value;if(!/^\d{4}-\d{2}$/.test(v)){if(de)de.textContent='⚠ 마감년월을 올바르게 입력하세요';return;}curYm=inYm(v);}
      else{const f=c.querySelector('#dfrom').value,t=c.querySelector('#dto').value;
        if(!/^\d{4}-\d{2}-\d{2}$/.test(f)||!/^\d{4}-\d{2}-\d{2}$/.test(t)){if(de)de.textContent='⚠ 입고일자를 올바르게 입력하세요';return;}
        if(f>t){if(de)de.textContent='⚠ 시작일이 종료일보다 늦습니다';return;}curFrom=inD(f);curTo=inD(t);}
      load();};
    const capF=()=>{curCq=c.querySelector('#cq').value.trim();curLg=c.querySelector('#lg').value;curSg=c.querySelector('#sg').value;curCt=c.querySelector('#ct').value;curMq=c.querySelector('#mq').value.trim();};
    const doSearch=()=>{capF();load();};   // ★검색버튼=Enter 동일(서버 재조회, 필터 유지)
    c.querySelector('#go').onclick=doSearch;
    c.querySelector('#nxsrc').onclick=()=>{capF();source='nx';load();};   // ★Phase5 nx 파생 보기
    const _dto=c.querySelector('#dto');if(_dto)_dto.onchange=()=>{capF();go();};   // 날짜 변경(검색어 유지)
    const _dfr=c.querySelector('#dfrom');if(_dfr)_dfr.onchange=()=>{capF();go();};
    ['#lg','#sg','#ct'].forEach(s=>c.querySelector(s).onchange=()=>{capF();render();});   // 분류=클라 필터(유지)
    c.querySelector('#cq').onkeyup=e=>{curCq=e.target.value.trim();if(e.key==='Enter')doSearch();else render();};   // 거래처=클라 필터, Enter=검색버튼과 동일
    c.querySelector('#mq').onkeyup=e=>{curMq=e.target.value.trim();if(e.key==='Enter')doSearch();else render();};   // 품번=Enter=검색(서버조회), 그외 클라 필터
    c.querySelector('#reset').onclick=()=>{mode='day';gijun='close';curYm='';curMq='';curCq='';curLg='';curSg='';curCt='';load();};
    c.querySelector('#xls').onclick=()=>{
      const hd=order.map(k=>CD[k].h);
      const raw={ymd:r=>fmtYmd(r.ymd),seq:r=>r.seq,ym:r=>fmtYm(r.ym),cnm:r=>r.cnm,ct:r=>ctN(r.ct),chg:r=>chg(r.cc),mat:r=>r.mat,nm:r=>r.nm,spec:r=>r.spec,diam:r=>r.diam,thick:r=>r.thick,length:r=>r.length,lg:r=>lgN(r.lg),sg:r=>sgN(r.sg),unit:r=>r.unit,qty:r=>r.qty,wt:r=>r.wt,cur:r=>curN(r.cur),rate:r=>(''+r.cur).trim()==='KRW'?'':r.rate,cost:r=>r.cost,amt:r=>Math.round(r.kamt),kamt:r=>Math.round(r.kamt)};
      downloadCSV('확정입고명세서_'+gijun+'_'+mode+'.csv',hd,cur.map(r=>order.map(k=>raw[k](r))));
    };
    render();
  };
  load();
};

/* 자재불출명세서 (구매/자재, dw_pu_input_130) — 라인(일자·순번)단위. 조회기준 마감/불출 × 출력방식 5종 */
SCREEN.dispatchdetail=(c)=>{
  const SG=DB.sgroupNames||{}, CT=DB.custTypeNames||{}, LG=DB.lgroupNames||{}, CHG=DB.chargeMap||{};
  const CURN={KRW:'원',USD:'달러',JPY:'엔',EUR:'유로',CNY:'위안'};
  const sgN=s=>SG[(''+s).trim()]||(''+s).trim()||'', ctN=t=>CT[(''+t).trim()]||(''+t).trim()||'',
        lgN=l=>LG[(''+l).trim()]||(''+l).trim()||'', chg=cc=>CHG[(''+cc).trim()]||'', curN=x=>CURN[(''+x).trim()]||(''+x).trim()||'';
  const fmtYmd=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;};
  const rateD=r=>(''+r.cur).trim()==='KRW'?'':won(r.rate);
  const CD={
    ymd:{h:'일자',cls:'center',get:r=>fmtYmd(r.ymd)},
    seq:{h:'순번',cls:'center',get:r=>esc(r.seq)},
    cc:{h:'불출처',cls:'cap',w:120,get:r=>esc(r.cnm)},
    ct:{h:'매입유형',cls:'cap',w:100,get:r=>esc(ctN(r.ct))},
    chg:{h:'담당자',cls:'',get:r=>esc(chg(r.cc))||'-'},
    mat:{h:'PART_NO',cls:'',get:r=>`<b>${esc(r.mat)}</b>`},
    nm:{h:'품명',cls:'cap',get:r=>esc(r.nm)},
    spec:{h:'PART SPEC',cls:'cap',get:r=>esc(r.spec)||''},
    lg:{h:'대분류',cls:'',get:r=>esc(lgN(r.lg))},
    sg:{h:'소분류',cls:'',get:r=>esc(sgN(r.sg))},
    incust:{h:'입고처',cls:'cap',w:120,get:r=>esc(r.incust)||''},
    unit:{h:'단위',cls:'center',get:r=>esc(r.unit)||''},
    qty:{h:'수량',cls:'num',get:r=>won(r.qty)},
    wt:{h:'중량',cls:'num',get:r=>won(r.wt)},
    cur:{h:'화폐',cls:'center',get:r=>esc(curN(r.cur))},
    rate:{h:'환율',cls:'num',get:r=>rateD(r)},
    cost:{h:'단가',cls:'num',get:r=>won(r.cost)},
    amt:{h:'금액',cls:'num gstock',get:r=>wonI(r.kamt)},   // ★금액 기준=KRW(kamt)
    kamt:{h:'금액(KRW)',cls:'num',get:r=>wonI(r.kamt)},   // (미사용·TAIL서 제외)
  };
  const TAIL=['unit','qty','wt','cur','rate','cost','amt'];   // ★금액(=KRW)만 · 금액(KRW) 중복컬럼 제외
  const MODES={
    day:      {label:'일자별',       lead:['ymd','seq','cc','ct','chg','mat','nm','spec','lg','sg','incust'], sort:['ymd','seq']},
    cust:     {label:'불출처별',      lead:['cc','ct','chg','ymd','seq','mat','nm','spec','lg','sg','incust'], sort:['cc','ymd','seq'], g1:'cc',g2:'ymd',l1:'불출처소계',l2:'일계'},
    item:     {label:'품목별',        lead:['mat','nm','spec','lg','sg','incust','ymd','seq','cc','ct','chg'], sort:['mat','ymd','seq'], g1:'mat',g2:'ymd',l1:'품목계',l2:'일계'},
    custitem: {label:'불출처/품목별',  lead:['cc','ct','chg','mat','nm','spec','lg','sg','incust','ymd','seq'], sort:['cc','mat','ymd','seq'], g1:'cc',g2:'mat',l1:'불출처소계',l2:'품목계'},
    itemcust: {label:'품목/불출처별',  lead:['mat','nm','spec','lg','sg','incust','cc','ct','chg','ymd','seq'], sort:['mat','cc','ymd','seq'], g1:'mat',g2:'cc',l1:'품목계',l2:'불출처소계'},
  };
  const API=API_BASE;
  let gijun='close', mode='day', cur=[], pool=[], loading=false, msg='', curYm='', curFrom='', curTo='', source='live';   // ★Phase5 데이터원(기본 라이브 무변경)
  let curCq='', curLg='', curSg='', curCt='', curMq='';   // ★검색어 유지(재조회·기간변경 시)
  const RENDER_CAP=1500;   // ★초기속도: 비그룹 렌더 상한
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const dToInput=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-',''), inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const load=async()=>{loading=true;msg='';draw();
    try{const u=gijun==='close'?`${API}/api/live/dispatchdetail?gijun=close`+(curYm?`&ym=${curYm}`:'')
        :`${API}/api/live/dispatchdetail?gijun=issue&dfrom=${curFrom}&dto=${curTo}`;
      if(source==='nx'){loading=false;return nxDerivedView(c,u+'&source=nx',{title:'자재불출명세서',onBack:()=>{source='live';load();}});}
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();
      pool=j.rows||[];if(gijun==='close')curYm=j.ym||curYm;else{curFrom=j.dfrom||curFrom;curTo=j.dto||curTo;}}
    catch(e){pool=[];msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';}
    loading=false;draw();};
  const draw=()=>{
    // pool = 라이브 조회결과(load에서 세팅)
    const cfg=MODES[mode], order=cfg.lead.concat(TAIL), qi=order.indexOf('qty');
    const lgs=[...new Set(pool.map(r=>(''+r.lg).trim()).filter(Boolean))].sort();
    const sgs=[...new Set(pool.map(r=>(''+r.sg).trim()).filter(Boolean))].sort();
    const cts=[...new Set(pool.map(r=>(''+r.ct).trim()).filter(Boolean))].sort();
    c.innerHTML=`
     <div class="page-title">📋 자재불출명세서</div>
     <div class="page-sub">LG外 전 매출(유상사급 포함) 라인 명세 · 원본 <code>PU/SA_T_STOCK_MAINT</code>+<code>PU_T_STOCK_MAINT_C</code> · 🟢 nx ${gijun==='close'?`마감기준 ${esc(ymToInput(curYm)||'-')}`:`불출기준 ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="close" class="${gijun==='close'?'on':''}">마감기준</button><button data-g="issue" class="${gijun==='issue'?'on':''}">불출기준</button></div>
       <label class="tl">${gijun==='close'?'마감년월':'불출일자'}</label>
       ${gijun==='close'?`<input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||nowCM())}" style="min-width:120px">`:`<input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:130px">`}
       <label class="tl">출력방식</label>
       <select class="sel" id="mode">${Object.entries(MODES).map(([k,v])=>`<option value="${k}" ${mode===k?'selected':''}>${v.label}</option>`).join('')}</select>
     </div>
     <div class="toolbar">
       <select class="sel" id="lg"><option value="">전체 대분류</option>${lgs.map(x=>`<option value="${esc(x)}" ${curLg===x?'selected':''}>${esc(lgN(x))}</option>`).join('')}</select>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgs.map(x=>`<option value="${esc(x)}" ${curSg===x?'selected':''}>${esc(sgN(x))}</option>`).join('')}</select>
       <select class="sel" id="ct"><option value="">전체 매입유형</option>${cts.map(x=>`<option value="${esc(x)}" ${curCt===x?'selected':''}>${esc(ctN(x))}</option>`).join('')}</select>
       <input class="inp" id="cq" placeholder="불출처코드/명" value="${esc(curCq)}">
       <input class="inp" id="mq" placeholder="품번/품명/PART NO" value="${esc(curMq)}">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
       <span id="derr" style="color:#c0392b;font-size:12px;font-weight:600"></span>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{gijun=b.dataset.g;load();});
    c.querySelector('#mode').onchange=e=>{mode=e.target.value;draw();};
    const filt=()=>{const lg=c.querySelector('#lg').value,sg=c.querySelector('#sg').value,ct=c.querySelector('#ct').value,
        cq=c.querySelector('#cq').value.trim().toLowerCase(),mq=c.querySelector('#mq').value.trim().toLowerCase();
      return pool.filter(r=>(!lg||(''+r.lg).trim()===lg)&&(!sg||(''+r.sg).trim()===sg)&&(!ct||(''+r.ct).trim()===ct)
        &&(!cq||(''+r.cc).toLowerCase().includes(cq)||(''+r.cnm).toLowerCase().includes(cq))
        &&(!mq||(''+r.mat).toLowerCase().includes(mq)||(''+r.nm).toLowerCase().includes(mq)));};
    const rowHtml=r=>`<tr>${order.map(k=>{const cd=CD[k],cap=cd.cls.indexOf('cap')>=0,v=cd.get(r);return `<td class="${cd.cls}"${cap?` title="${esc((''+(k==='cc'?r.cnm:k==='nm'?r.nm:k==='spec'?r.spec:k==='incust'?r.incust:k==='ct'?ctN(r.ct):'')))}"`:''}>${v}</td>`;}).join('')}</tr>`;
    /* dispatchdetail-live */
    const subRow=(label,q,a,k,g)=>`<tr class="${g||'subtot'}"${g==='grandtot'?' style="position:sticky;bottom:0;background:#e8f0fb;box-shadow:0 -1px 0 #b9cbe6;z-index:3"':''}><td colspan="${qi}" class="right">${esc(label)}</td><td class="num">${won(q)}</td><td colspan="4"></td><td class="num">${wonI(k)}</td></tr>`;
    const render=()=>{
      let lines=filt();
      lines.sort((a,b)=>{for(const k of cfg.sort){const c2=(''+(a[k]??'')).localeCompare(''+(b[k]??''),'ko',{numeric:true});if(c2)return c2;}return 0;});
      cur=lines;
      let html='';
      if(!cfg.g1){ lines.slice(0,RENDER_CAP).forEach(r=>html+=rowHtml(r)); if(lines.length>RENDER_CAP)html+=`<tr><td colspan="${order.length}" class="empty" style="color:#8a6d1c">상위 ${won(RENDER_CAP)}행만 표시 · 전체 ${won(lines.length)}행은 검색어로 좁히거나 엑셀 다운로드</td></tr>`; }
      else {
        let g1v=null,g2v=null,s1q=0,s1a=0,s1k=0,s2q=0,s2a=0,s2k=0;
        lines.forEach(r=>{const v1=r[cfg.g1], v2=cfg.g2?r[cfg.g2]:null;
          if(g1v!==null && v1!==g1v){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a,s2k); html+=subRow(cfg.l1,s1q,s1a,s1k); s1q=s1a=s1k=s2q=s2a=s2k=0; g2v=null; }
          else if(cfg.g2 && g2v!==null && v2!==g2v){ html+=subRow(cfg.l2,s2q,s2a,s2k); s2q=s2a=s2k=0; }
          html+=rowHtml(r);
          s1q+=+r.qty||0; s1a+=+r.amt||0; s1k+=+r.kamt||0; s2q+=+r.qty||0; s2a+=+r.amt||0; s2k+=+r.kamt||0; g1v=v1; g2v=v2; });
        if(g1v!==null){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a,s2k); html+=subRow(cfg.l1,s1q,s1a,s1k); }
      }
      const tq=lines.reduce((a,b)=>a+(+b.qty||0),0), ta=lines.reduce((a,b)=>a+(+b.amt||0),0), tk=lines.reduce((a,b)=>a+(+b.kamt||0),0);
      html+=subRow('총계',tq,ta,tk,'grandtot');
      c.querySelector('#th').innerHTML=`<tr>${order.map(k=>`<th class="${CD[k].cls}" data-base="${esc(CD[k].h)}"${CD[k].w?` style="min-width:${CD[k].w}px"`:''}>${CD[k].h}</th>`).join('')}</tr>`;
      c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${order.length}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
        :(msg?`<tr><td colspan="${order.length}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
        :(lines.length?html:`<tr><td colspan="${order.length}" class="empty">결과 없음</td></tr>`));
      c.querySelector('#cnt').textContent=`${lines.length}라인 / 대상 ${pool.length}라인`;
      attachResizers(c);
      // 헤더 더블클릭 정렬(소계 무시=잎행 평면 렌더)
      enableSort(c, order, ()=>cur, ()=>{
        let h=''; cur.slice(0,RENDER_CAP).forEach(r=>h+=rowHtml(r));
        const gq=cur.reduce((a,b)=>a+(+b.qty||0),0),ga=cur.reduce((a,b)=>a+(+b.amt||0),0),gk=cur.reduce((a,b)=>a+(+b.kamt||0),0);
        h+=subRow('총계',gq,ga,gk,'grandtot');
        c.querySelector('#body').innerHTML=h;
      });
    };
    const go=()=>{const de=c.querySelector('#derr');if(de)de.textContent='';
      if(gijun==='close'){const v=c.querySelector('#dto').value;if(!/^\d{4}-\d{2}$/.test(v)){if(de)de.textContent='⚠ 마감년월을 올바르게 입력하세요';return;}curYm=inYm(v);}
      else{const f=c.querySelector('#dfrom').value,t=c.querySelector('#dto').value;
        if(!/^\d{4}-\d{2}-\d{2}$/.test(f)||!/^\d{4}-\d{2}-\d{2}$/.test(t)){if(de)de.textContent='⚠ 불출일자를 올바르게 입력하세요';return;}
        if(f>t){if(de)de.textContent='⚠ 시작일이 종료일보다 늦습니다';return;}curFrom=inD(f);curTo=inD(t);}
      load();};
    const capF=()=>{curCq=c.querySelector('#cq').value.trim();curLg=c.querySelector('#lg').value;curSg=c.querySelector('#sg').value;curCt=c.querySelector('#ct').value;curMq=c.querySelector('#mq').value.trim();};
    c.querySelector('#go').onclick=()=>{capF();render();};   // ★검색=필터적용(검색어 유지·버튼=Enter 동일)
    const _dto=c.querySelector('#dto');if(_dto)_dto.onchange=()=>{capF();go();};   // 날짜 변경(검색어 유지)
    const _dfr=c.querySelector('#dfrom');if(_dfr)_dfr.onchange=()=>{capF();go();};
    ['#lg','#sg','#ct'].forEach(s=>c.querySelector(s).onchange=()=>{capF();render();});
    c.querySelector('#cq').onkeyup=e=>{curCq=e.target.value.trim();render();};
    c.querySelector('#mq').onkeyup=e=>{curMq=e.target.value.trim();render();};
    c.querySelector('#reset').onclick=()=>{mode='day';gijun='close';curYm='';curCq='';curLg='';curSg='';curCt='';curMq='';load();};
    c.querySelector('#xls').onclick=()=>{
      const hd=order.map(k=>CD[k].h.replace(/<[^>]+>/g,''));
      const raw={ymd:r=>fmtYmd(r.ymd),seq:r=>r.seq,cc:r=>r.cnm,ct:r=>ctN(r.ct),chg:r=>chg(r.cc),ic:r=>r.ic,mat:r=>r.mat,nm:r=>r.nm,spec:r=>r.spec,lg:r=>lgN(r.lg),sg:r=>sgN(r.sg),incust:r=>r.incust,unit:r=>r.unit,qty:r=>r.qty,wt:r=>r.wt,cur:r=>curN(r.cur),rate:r=>(''+r.cur).trim()==='KRW'?'':r.rate,cost:r=>r.cost,amt:r=>Math.round(r.kamt),kamt:r=>Math.round(r.kamt)};
      downloadCSV('자재불출명세서_'+gijun+'_'+mode+'.csv',hd,cur.map(r=>order.map(k=>raw[k](r))));
    };
    render();
  };
  load();
};

/* 자재불출집계표 (영업, dw_pu_input_140) — LG外 전 매출(유상사급 포함). 조회기준 마감/불출 × 출력방식 창고별/품목별/업체별 */
SCREEN.dispatch=(c)=>{
  const SG=DB.sgroupNames||{}, CT=DB.custTypeNames||{}, LG=DB.lgroupNames||{}, CHG=DB.chargeMap||{}, CI=DB.custInfo||{};
  const CURN={KRW:'원',USD:'달러',JPY:'엔',EUR:'유로',CNY:'위안'};
  const sgN=s=>SG[(''+s).trim()]||(''+s).trim()||'', ctN=t=>CT[(''+t).trim()]||(''+t).trim()||'',
        lgN=l=>LG[(''+l).trim()]||(''+l).trim()||'', chg=cc=>CHG[(''+cc).trim()]||'', ci=cc=>CI[cc]||{biz:'',tel:'',fax:''},
        curN=x=>CURN[(''+x).trim()]||(''+x).trim()||'', rateD=r=>(''+r.cur).trim()==='KRW'?'':won(r.rate);
  const fVat=a=>Math.floor((+a||0)*0.1), S=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
  const API=API_BASE;
  let gijun='close', mode='wh', vat=false, cur=[], pool=[], loading=false, msg='', curYm='', curFrom='', curTo='';   // 빈값 → 백엔드가 당월1일~오늘(실행일자) 기본값 적용
  let F={lg:'',sg:'',ct:'',cq:'',mq:''};   // 필터 상태(draw 재그림에도 유지)
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const dToInput=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-',''), inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const load=async()=>{loading=true;msg='';draw();
    try{const u=gijun==='close'?`${API}/api/live/dispatch?gijun=close`+(curYm?`&ym=${curYm}`:'')
        :`${API}/api/live/dispatch?gijun=issue&dfrom=${curFrom}&dto=${curTo}`;
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();
      pool=j.rows||[];if(gijun==='close')curYm=j.ym||curYm;else{curFrom=j.dfrom||curFrom;curTo=j.dto||curTo;}}
    catch(e){pool=[];msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';}
    loading=false;draw();};
  const draw=()=>{
    // pool = 라이브 조회결과(load에서 세팅)
    const lgs=[...new Set(pool.map(r=>(''+r.lg).trim()).filter(Boolean))].sort();
    const sgs=[...new Set(pool.map(r=>(''+r.sg).trim()).filter(Boolean))].sort();
    const cts=[...new Set(pool.map(r=>(''+r.ct).trim()).filter(Boolean))].sort();
    const dateInput = gijun==='close'
      ? `<label class="tl">마감년월</label><input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||nowCM())}" style="min-width:120px">`
      : `<label class="tl">불출일자</label><input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom)||nowMS())}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo)||nowCD())}" style="min-width:130px">`;
    c.innerHTML=`
     <div class="page-title">📤 자재불출집계표</div>
     <div class="page-sub">LG外 전 매출(유상사급 포함) · 원본 <code>PU/SA_T_STOCK_MAINT</code>+<code>PU_T_STOCK_MAINT_C</code> · 🟢 nx ${gijun==='close'?`마감기준(업체별 마감일) ${esc(ymToInput(curYm)||'-')}`:`불출기준(실제 이동일) ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="close" class="${gijun==='close'?'on':''}">마감기준</button><button data-g="issue" class="${gijun==='issue'?'on':''}">불출기준</button></div>
       ${dateInput}
       <label class="tl">출력방식</label>
       <select class="sel" id="mode"><option value="wh" ${mode==='wh'?'selected':''}>창고별</option><option value="item" ${mode==='item'?'selected':''}>품목별</option><option value="cust" ${mode==='cust'?'selected':''}>업체별</option></select>
       <button class="btn ${vat?'':'ghost'}" id="vat">부가세조정</button>
     </div>
     <div class="toolbar">
       <select class="sel" id="lg"><option value="">전체 대분류</option>${lgs.map(x=>`<option value="${esc(x)}" ${F.lg===x?'selected':''}>${esc(lgN(x))}</option>`).join('')}</select>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgs.map(x=>`<option value="${esc(x)}" ${F.sg===x?'selected':''}>${esc(sgN(x))}</option>`).join('')}</select>
       <select class="sel" id="ct"><option value="">전체 매입유형</option>${cts.map(x=>`<option value="${esc(x)}" ${F.ct===x?'selected':''}>${esc(ctN(x))}</option>`).join('')}</select>
       <input class="inp" id="cq" value="${esc(F.cq)}" placeholder="거래처코드/명">
       <input class="inp" id="mq" value="${esc(F.mq)}" placeholder="품번/품명/PART NO">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <span id="derr" style="color:#c0392b;font-size:12px;font-weight:600"></span>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="grid-wrap" style="max-height:500px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{gijun=b.dataset.g;load();});
    c.querySelector('#mode').onchange=e=>{mode=e.target.value;draw();};
    c.querySelector('#vat').onclick=()=>{vat=!vat;draw();};
    const filt=()=>{const lg=F.lg,sg=F.sg,ct=F.ct,cq=(F.cq||'').trim().toLowerCase(),mq=(F.mq||'').trim().toLowerCase();
      return pool.filter(r=>(!lg||(''+r.lg).trim()===lg)&&(!sg||(''+r.sg).trim()===sg)&&(!ct||(''+r.ct).trim()===ct)
        &&(!cq||(''+r.cc).toLowerCase().includes(cq)||(''+r.cnm).toLowerCase().includes(cq))
        &&(!mq||(''+r.mat).toLowerCase().includes(mq)||(''+r.nm).toLowerCase().includes(mq)));};
    /* dispatch-live */
    const sumbar=(n,qty,amt)=>{c.querySelector('#sum').innerHTML=`<div class="s-item">라인 <b>${won(n)}</b></div>
        <div class="s-item">수량 합계 <b>${won(qty)}</b></div>
        <div class="s-item ${amt<0?'neg':''}">금액 합계 <b>${wonI(amt)} 원</b>${vat?` · 부가세포함 <b>${wonI(amt+fVat(amt))} 원</b>`:''}</div>`;};
    const money=(a,cls='')=>`<td class="num ${cls}">${wonI(a)}</td>`;
    // 창고별/품목별 공통 라인 셀(금액/부가세)
    // ★금액 기준=KRW(kamt) — 수입 외화도 KRW환산 합산(통화혼합 방지). 부가세/합계도 KRW. 화폐/환율/단가는 참조 유지.
    const amtCells=r=>`<td class="num gstock">${wonI(r.kamt)}</td>`+(vat?`${money(fVat(r.kamt))}${money(r.kamt+fVat(r.kamt))}`:'');
    const amtSub=g=>`<td class="num gstock">${wonI(g.kamt)}</td>`+(vat?`${money(fVat(g.kamt))}${money(g.kamt+fVat(g.kamt))}`:'');
    const amtHdr=`<th class="num">금액</th>`+(vat?`<th class="num">부가세</th><th class="num">합계</th>`:'');
    const VC=vat?2:0;  // 추가 컬럼 수(KRW: 부가세/합계)

    // 행 템플릿(모드별)+정렬키 — 헤더 더블클릭 정렬(소계무시 평면 렌더)에 재사용. vat 추가컬럼은 계산값이라 정렬 no-op
    const midCells=r=>`<td class="center">${esc(r.unit)||''}</td><td class="num">${won(r.qty)}</td><td class="num">${won(r.wt)}</td><td class="center">${esc(curN(r.cur))}</td><td class="num">${rateD(r)}</td><td class="num">${won(r.cost)}</td><td class="num">${won(r.kcost)}</td>${amtCells(r)}`;
    const TPL={
      wh:  r=>`<tr><td><b>${esc(r.cc)}</b></td><td class="cap" style="max-width:170px" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap" title="${esc(ctN(r.ct))}">${esc(ctN(r.ct))}</td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td>${esc(r.mat)}</td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td><td>${esc(lgN(r.lg))}</td><td>${esc(sgN(r.sg))}</td><td class="cap" title="${esc(r.incust)||''}">${esc(r.incust)||''}</td>${midCells(r)}</tr>`,
      item:r=>`<tr><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td><b>${esc(r.mat)}</b></td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td><td>${esc(lgN(r.lg))}</td><td>${esc(sgN(r.sg))}</td><td class="cap" title="${esc(r.incust)||''}">${esc(r.incust)||''}</td><td>${esc(r.cc)}</td><td class="cap" style="max-width:170px" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap">${esc(ctN(r.ct))}</td>${midCells(r)}</tr>`,
      cust:r=>{const info=ci(r.cc), v6=(''+r.ct).trim()==='6'?'vat6':'';return `<tr><td><b>${esc(r.cc)}</b></td><td>${esc(r.cnm)}</td><td>${esc(chg(r.cc))||'-'}</td><td>${esc(ctN(r.ct))}</td><td>${esc(info.biz)}</td><td>${esc(info.tel)}</td><td>${esc(info.fax)}</td><td class="num">${won(r.qty)}</td><td class="num gstock">${wonI(r.kamt)}</td><td class="num ${v6}">${wonI(r.kvat)}</td><td class="num">${wonI(r.kamt+r.kvat)}</td></tr>`;},
    };
    const baseKEYS={wh:['cc','cnm','ct','nm','mat','spec','lg','sg','incust','unit','qty','wt','cur','rate','cost','kcost','kamt'],
      item:['nm','mat','spec','lg','sg','incust','cc','cnm','ct','unit','qty','wt','cur','rate','cost','kcost','kamt'],
      cust:['cc','cnm','chg','ct','biz','tel','fax','qty','kamt','kvat','kamt']};
    let lines=filt(), tbody='', thead='', grand={qty:0,amt:0,kamt:0}, ncols=0;
    const grandRow=()=>{grand.qty=S(cur,'qty'); grand.amt=S(cur,'amt'); grand.kamt=S(cur,'kamt');
      const sty=' style="position:sticky;bottom:0;background:#e8f0fb;box-shadow:0 -1px 0 #b9cbe6;z-index:3"';
      if(mode==='cust'){const gkv=S(cur,'kvat');
        return `<tr class="grandtot"${sty}><td colspan="7" class="right">총계 (${won(cur.length)} 업체)</td><td class="num">${won(grand.qty)}</td><td class="num">${wonI(grand.kamt)}</td><td class="num">${wonI(gkv)}</td><td class="num">${wonI(grand.kamt+gkv)}</td></tr>`;}
      return `<tr class="grandtot"${sty}><td colspan="10" class="right">총계</td><td class="num">${won(grand.qty)}</td><td colspan="5"></td>${amtSub({amt:grand.amt,kamt:grand.kamt})}</tr>`;};
    if(mode==='wh'){
      // 창고별: item_code 무시하고 (cc,mat,cost,cur,lg,sg) 재집계
      const map=new Map();
      lines.forEach(r=>{const k=[r.cc,r.mat,r.cost,r.cur,r.lg,r.sg].join('|');
        if(!map.has(k))map.set(k,{...r,qty:0,amt:0,vat:0,kamt:0,kvat:0});
        const o=map.get(k);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.vat+=+r.vat||0;o.kamt+=+r.kamt||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko')||(''+a.mat).localeCompare(''+b.mat,'ko'));
      thead=`<tr><th>창고</th><th>창고명</th><th style="min-width:100px">매입유형</th><th>품명</th><th>PART NO</th><th>PART SPEC</th><th>대분류</th><th>소분류</th><th style="min-width:120px">입고처</th><th class="center">단위</th><th class="num">수량</th><th class="num">중량</th><th class="center">화폐</th><th class="num">환율</th><th class="num">단가</th><th class="num">단가(KRW)</th>${amtHdr}</tr>`;
      ncols=16+1+VC;
      const groups=[]; let ck=null;
      cur.forEach(r=>{if(r.cc!==ck){groups.push({cc:r.cc,cnm:r.cnm,ct:r.ct,rows:[]});ck=r.cc;}groups[groups.length-1].rows.push(r);});
      groups.forEach(g=>{g.rows.forEach(r=>{tbody+=TPL.wh(r);});
        const gs={qty:S(g.rows,'qty'),amt:S(g.rows,'amt'),kamt:S(g.rows,'kamt')};
        tbody+=`<tr class="subtot"><td colspan="10" class="right">(창고계) ${esc(g.cnm)}</td><td class="num">${won(gs.qty)}</td><td colspan="5"></td>${amtSub(gs)}</tr>`;});
    } else if(mode==='item'){
      cur=lines.slice().sort((a,b)=>(''+a.mat).localeCompare(''+b.mat,'ko')||(''+a.cc).localeCompare(''+b.cc,'ko'));
      thead=`<tr><th>품명</th><th>PART NO</th><th>PART SPEC</th><th>대분류</th><th>소분류</th><th style="min-width:120px">입고처</th><th>창고</th><th>창고명</th><th style="min-width:100px">매입유형</th><th class="center">단위</th><th class="num">수량</th><th class="num">중량</th><th class="center">화폐</th><th class="num">환율</th><th class="num">단가</th><th class="num">단가(KRW)</th>${amtHdr}</tr>`;
      ncols=16+1+VC;
      const groups=[]; let mk=null;
      cur.forEach(r=>{if(r.mat!==mk){groups.push({mat:r.mat,nm:r.nm,rows:[]});mk=r.mat;}groups[groups.length-1].rows.push(r);});
      groups.forEach(g=>{g.rows.forEach(r=>{tbody+=TPL.item(r);});
        const gs={qty:S(g.rows,'qty'),amt:S(g.rows,'amt'),kamt:S(g.rows,'kamt')};
        tbody+=`<tr class="subtot"><td colspan="10" class="right">(품목계) ${esc(g.nm)}</td><td class="num">${won(gs.qty)}</td><td colspan="5"></td>${amtSub(gs)}</tr>`;});
    } else { // 업체별 집계
      const map=new Map();
      lines.forEach(r=>{if(!map.has(r.cc))map.set(r.cc,{cc:r.cc,cnm:r.cnm,ct:r.ct,qty:0,amt:0,vat:0,kamt:0,kvat:0});
        const o=map.get(r.cc);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.vat+=+r.vat||0;o.kamt+=+r.kamt||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko'));
      thead=`<tr><th>거래처코드</th><th>거래처명</th><th>담당자</th><th style="min-width:100px">매입유형</th><th>사업자번호</th><th>전화번호</th><th>팩스번호</th><th class="num">수량</th><th class="num">금액</th><th class="num">부가세</th><th class="num">합계</th></tr>`;
      ncols=11;
      cur.forEach(r=>{tbody+=TPL.cust(r);});
    }
    tbody+=grandRow();
    c.querySelector('#th').innerHTML=thead;
    c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${ncols}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
      :(msg?`<tr><td colspan="${ncols}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
      :(cur.length?tbody:`<tr><td colspan="${ncols}" class="empty">결과 없음</td></tr>`));
    c.querySelector('#cnt').textContent=`${cur.length}${mode==='cust'?'업체':'라인'} / 대상 ${lines.length}라인`;
    attachResizers(c);
    enableSort(c, baseKEYS[mode].concat(vat?['','','','','']:[]), ()=>cur, ()=>{
      let b=''; cur.forEach(r=>b+=TPL[mode](r)); b+=grandRow(); c.querySelector('#body').innerHTML=b;});
    // 이벤트
    // 조회 = 선택 기간으로 라이브 재조회
    const go=()=>{const de=c.querySelector('#derr');if(de)de.textContent='';
      if(gijun==='close'){const v=c.querySelector('#dto').value;if(!/^\d{4}-\d{2}$/.test(v)){if(de)de.textContent='⚠ 마감년월을 올바르게 입력하세요';return;}curYm=inYm(v);}
      else{const f=c.querySelector('#dfrom').value,t=c.querySelector('#dto').value;
        if(!/^\d{4}-\d{2}-\d{2}$/.test(f)||!/^\d{4}-\d{2}-\d{2}$/.test(t)){if(de)de.textContent='⚠ 불출일자를 올바르게 입력하세요';return;}
        if(f>t){if(de)de.textContent='⚠ 시작일이 종료일보다 늦습니다';return;}curFrom=inD(f);curTo=inD(t);}
      load();};
    const syncF=()=>{F.lg=c.querySelector('#lg').value;F.sg=c.querySelector('#sg').value;F.ct=c.querySelector('#ct').value;F.cq=c.querySelector('#cq').value;F.mq=c.querySelector('#mq').value;};
    c.querySelector('#go').onclick=()=>{syncF();draw();};   // ★검색=필터적용(검색어 유지)
    const _dto=c.querySelector('#dto');if(_dto)_dto.onchange=go;
    const _dfr=c.querySelector('#dfrom');if(_dfr)_dfr.onchange=go;
    ['#lg','#sg','#ct'].forEach(s=>c.querySelector(s).onchange=()=>{syncF();draw();});
    c.querySelector('#cq').onkeyup=e=>{if(e.key==='Enter'){syncF();draw();}};
    c.querySelector('#mq').onkeyup=e=>{if(e.key==='Enter'){syncF();draw();}};
    c.querySelector('#reset').onclick=()=>{gijun='close';mode='wh';vat=false;curYm='';F={lg:'',sg:'',ct:'',cq:'',mq:''};load();};
    c.querySelector('#xls').onclick=()=>{
      let hd, rows;
      if(mode==='cust'){hd=['거래처코드','거래처명','담당자','매입유형','사업자번호','전화번호','팩스번호','수량','금액','부가세','합계'];
        rows=cur.map(r=>{const i=ci(r.cc);return [r.cc,r.cnm,chg(r.cc),ctN(r.ct),i.biz,i.tel,i.fax,r.qty,Math.round(r.kamt),Math.round(r.kvat),Math.round(r.kamt+r.kvat)];});}
      else{const base=['품명','PART NO','PART SPEC','대분류','소분류','입고처','창고','창고명','매입유형','단위','수량','중량','화폐','환율','단가','단가(KRW)','금액'].concat(vat?['부가세','합계']:[]);
        hd=base;
        rows=cur.map(r=>[r.nm,r.mat,r.spec,lgN(r.lg),sgN(r.sg),r.incust,r.cc,r.cnm,ctN(r.ct),r.unit,r.qty,r.wt,curN(r.cur),(''+r.cur).trim()==='KRW'?'':r.rate,r.cost,r.kcost,Math.round(r.kamt)].concat(vat?[fVat(r.kamt),Math.round(r.kamt+fVat(r.kamt))]:[]));}
      downloadCSV('자재불출집계표_'+gijun+'_'+mode+'.csv',hd,rows);
    };
  };
  load();
};

/* 자재 수불장 (구매/자재, 일=dw_pu_stock_260 / 월=dw_pu_stock_160) — 기초/입고/출고/기타/재고 × 수량·단가·금액 */
SCREEN.matledger=(c)=>{
  // ★C7 전환(2026-08-28): 레거시 임시테이블 → 확정 스냅샷 파생.
  //   이전엔 일수불이 PU_T_MONTH_STOCK_WH_DAILY(레거시 w_pu_stock_260 이 조회할 때마다 TRUNCATE)
  //   를 읽어 "누가 언제 조회했느냐"로 내용이 바뀌었다. 이제 마감과 **같은 엔진**을 호출한다.
  //   정본 = _schema/CLOSE_MGMT_CANON.md §20~21 · STOCK_CLOSE_HANDOFF.md §7
  const API=API_BASE;
  let pool=[], loading=false, msg='', meta=null, cur=[], dom='MAT';   // dom=MAT 자재 / PRD 생산
  const SG=DB.sgroupNames||{}, CT=DB.custTypeNames||{}, CHG=DB.chargeMap||{};
  const sgName=s=>{const k=(''+s).trim();return SG[k]||k||'';};
  const ctName=t=>{const k=(''+t).trim();return CT[k]||k||'';};
  const chg=cc=>CHG[(''+cc).trim()]||'';
  const fmtYmd=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'';};
  const upr=(a,q)=>q?Math.round(a/q):0;
  const pad=n=>String(n).padStart(2,'0');
  const date2ymd=v=>{v=(''+(v||'')).trim();return v?v.slice(2).replace(/-/g,''):'';};
  // 기본 기간 = 당월 1일 ~ 오늘
  const _t=new Date();
  let dTo=`${_t.getFullYear()}-${pad(_t.getMonth()+1)}-${pad(_t.getDate())}`;
  let dFrom=`${_t.getFullYear()}-${pad(_t.getMonth()+1)}-01`;
  const load=async()=>{
    loading=true;msg='';draw();
    try{const u=`${API}/api/close/ledger?domain=${dom}&d_from=${date2ymd(dFrom)}&d_to=${date2ymd(dTo)}`;
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();
      pool=j.rows||[];meta=j;}
    catch(e){pool=[];meta=null;msg='조회 실패 — '+e.message;}
    loading=false;draw();};
  const draw=()=>{
    const brk=(meta&&meta.invariant_breaks)||[], va=(meta&&meta.valuation_adjust)||{count:0,amount:0,why:''};
    const sub=`기초(확정 스냅샷) + 입고 − 출고 ± 조정 = 기말 · 단가=이동평균${dom==='PRD'?'(매입가 기반)':(dom==='SAL'?'(판가 기반)':'')} · <b>저장하지 않고 매번 계산</b>${dom==='PRD'?' · 축=품목×재고위치':''}`
      +(meta?` · ${esc(meta.basis||'')}`:'');
    const sgroups=[...new Set(pool.map(r=>(''+r.sg).trim()).filter(Boolean))].sort();
    const custs=[...new Set(pool.map(r=>r.cust).filter(Boolean))].sort();
    c.innerHTML=`
     <div class="page-title">📒 ${({MAT:'자재',PRD:'생산',SAL:'영업'})[dom]} 수불장</div>
     <div class="page-sub">${sub}</div>
     <div class="toolbar">
       <div class="toggle-group"><button data-dom="MAT" class="${dom==='MAT'?'on':''}">자재</button><button data-dom="PRD" class="${dom==='PRD'?'on':''}">생산</button><button data-dom="SAL" class="${dom==='SAL'?'on':''}">영업</button></div>
       <label style="font-size:12px;color:var(--muted);font-weight:600">기간</label>
       <input type="date" class="inp" id="dfrom" value="${esc(dFrom)}" style="min-width:135px">
       <span style="color:var(--muted)">~</span>
       <input type="date" class="inp" id="dto" value="${esc(dTo)}" style="min-width:135px">
       <input class="inp" id="q" placeholder="품목코드/품명">
       <input class="inp" id="cust" list="ml-custl" placeholder="전체 매입처 (입력)" autocomplete="off" style="width:150px"><datalist id="ml-custl">${custs.map(w=>`<option value="${esc(w)}"></option>`).join('')}</datalist>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgroups.map(s=>`<option value="${esc(s)}">${esc(sgName(s))}</option>`).join('')}</select>
       <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
       <label style="display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#c0392b;font-weight:700"><input type="checkbox" id="longstk"> 장기재고(3개월↑)</label>
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     ${brk.length?`<div class="summary-bar" style="background:#fdecea;border-color:#e74c3c"><div class="s-item" style="color:#c0392b"><b>★불변식 위반 ${brk.length}건</b> — 기초+입−출±조정 ≠ 기말. 즉시 확인 필요: ${esc(brk.slice(0,5).map(b=>b.item).join(', '))}</div></div>`:''}
     ${va.count?`<div class="summary-bar" style="background:#fef9e7"><div class="s-item">평가조정 <b>${won(va.count)}</b>건 · <b>${wonI(va.amount)}</b>원 <span style="color:var(--muted)">— ${esc(va.why||'')}</span></div></div>`:''}
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:510px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    pool.forEach(r=>{r._su=upr(r.sa,r.sq);r._bu=upr(r.ba,r.bq);r._iu=upr(r.ia,r.iq);r._ou=upr(r.oa,r.oq);r._tu=upr(r.ta,r.tq);
      r._sgn=sgName(r.sg);r._ctn=ctName(r.ctype);r._chg=chg(r.custcd);r._lin=fmtYmd(r.lastin);});
    c.querySelector('#th').innerHTML=`<tr>
      <th>품목코드</th><th class="cap">품명</th>${dom==='PRD'?'<th>재고위치</th>':''}
      <th class="num gstock">재고수량</th><th class="num gstock">재고단가</th><th class="num gstock">재고금액</th>
      <th>소분류</th><th>매입유형</th><th class="center">단위</th>
      <th class="num">기초재고</th><th class="num">기초단가</th><th class="num">기초금액</th>
      <th class="num">입고수량</th><th class="num">입고단가</th><th class="num">입고금액</th>
      <th class="num">출고수량</th><th class="num">출고단가</th><th class="num">출고금액</th>
      <th class="num">기타수량</th><th class="num">기타단가</th><th class="num">기타금액</th>
      <th class="num">평가조정</th>
      <th>담당자</th><th class="cap">매입처명</th><th class="center">최종입고일</th></tr>`;
    const T=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
    const sumbar=rows=>{c.querySelector('#sum').innerHTML=`<div class="s-item">건수 <b>${won(rows.length)}</b></div>
        <div class="s-item">기초금액 <b>${wonI(T(rows,'ba'))}</b></div>
        <div class="s-item">입고금액 <b>${wonI(T(rows,'ia'))}</b></div>
        <div class="s-item">출고금액 <b>${wonI(T(rows,'oa'))}</b></div>
        <div class="s-item">재고수량 <b>${won(T(rows,'sq'))}</b></div>
        <div class="s-item ${T(rows,'sa')<0?'neg':''}">재고금액 <b>${wonI(T(rows,'sa'))} 원</b></div>`;};
    const gbf=r=>{const gb=c.querySelector('#gubun').value;return gb==='all'||(gb==='plus'?r.sq>0:r.sq<0);};
    const gtRow=rows=>rows.length?`<tr class="grandtot">
      <td colspan="${dom==='PRD'?3:2}" class="right">총계 (${won(rows.length)}건)</td>
      <td class="num">${won(T(rows,'sq'))}</td><td></td><td class="num">${wonI(T(rows,'sa'))}</td>
      <td></td><td></td><td></td>
      <td class="num">${won(T(rows,'bq'))}</td><td></td><td class="num">${wonI(T(rows,'ba'))}</td>
      <td class="num">${won(T(rows,'iq'))}</td><td></td><td class="num">${wonI(T(rows,'ia'))}</td>
      <td class="num">${won(T(rows,'oq'))}</td><td></td><td class="num">${wonI(T(rows,'oa'))}</td>
      <td class="num">${won(T(rows,'tq'))}</td><td></td><td class="num">${wonI(T(rows,'ta'))}</td>
      <td class="num">${wonI(T(rows,'va'))}</td>
      <td></td><td></td><td></td></tr>`:'';
    const render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr>
      <td><b>${esc(r.cd)}</b></td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td>${dom==='PRD'?`<td>${esc(r.loc)||'가공창고'}</td>`:''}
      <td class="num gstock qty"><b>${won(r.sq)}</b></td><td class="num gstock">${won(r._su)}</td><td class="num gstock amt"><b>${wonI(r.sa)}</b></td>
      <td>${esc(r._sgn)}</td><td>${esc(r._ctn)}</td><td class="center">${esc(r.unit)||''}</td>
      <td class="num">${won(r.bq)}</td><td class="num">${won(r._bu)}</td><td class="num">${wonI(r.ba)}</td>
      <td class="num">${won(r.iq)}</td><td class="num">${won(r._iu)}</td><td class="num">${wonI(r.ia)}</td>
      <td class="num">${won(r.oq)}</td><td class="num">${won(r._ou)}</td><td class="num">${wonI(r.oa)}</td>
      <td class="num">${won(r.tq)}</td><td class="num">${won(r._tu)}</td><td class="num">${wonI(r.ta)}</td>
      <td class="num" ${Math.abs(+r.va||0)>1?'style="color:#c0392b;font-weight:700"':''} title="단가0 보정·마이너스재고 단가리셋 분">${(+r.va||0)?wonI(r.va):''}</td>
      <td>${esc(r._chg)||'-'}</td><td class="cap" title="${esc(r.cust)||''}">${esc(r.cust)||'-'}</td><td class="center">${esc(r._lin)||'-'}</td></tr>`).join('')+gtRow(rows)
      :`<tr><td colspan="${dom==='PRD'?25:24}" class="empty">${pool.length===0?'해당 기간 자료 없음':'검색 결과 없음(필터 조건 확인)'}</td></tr>`;
      sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
    const cutoffYmd=()=>{const v=c.querySelector('#dto').value; if(!v)return null;
      const d=new Date(v); if(isNaN(d))return null; d.setMonth(d.getMonth()-3);
      return pad(d.getFullYear()%100)+pad(d.getMonth()+1)+pad(d.getDate());};
    const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),sg=c.querySelector('#sg').value,cu=c.querySelector('#cust').value;
      const lng=c.querySelector('#longstk').checked, cut=cutoffYmd();
      render(pool.filter(r=>gbf(r)&&(!sg||(''+r.sg).trim()===sg)&&(!cu||r.cust===cu)
        &&(!lng||(r.sq>0 && (''+(r.lastin||'')).trim()!=='' && (''+r.lastin).trim()<cut))
        &&(!q||(r.cd||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
    const go=()=>{const f=c.querySelector('#dfrom').value, t2=c.querySelector('#dto').value;
      if(f!==dFrom||t2!==dTo){dFrom=f;dTo=t2;load();}else apply();};
    c.querySelectorAll('[data-dom]').forEach(b=>b.onclick=()=>{if(dom!==b.dataset.dom){dom=b.dataset.dom;load();}});
    c.querySelector('#go').onclick=go;
    c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
    // ★날짜칸은 디바운스로 받는다 — 즉시 조회·재렌더하면 입력칸이 갈아치워져
    //   28일을 치려고 '2' 를 누른 순간 2일로 굳는다(core.js bindDate).
    bindDate(c.querySelector('#dfrom'),go);bindDate(c.querySelector('#dto'),go);
    c.querySelector('#sg').onchange=apply;c.querySelector('#cust').onchange=apply;c.querySelector('#gubun').onchange=apply;
    c.querySelector('#longstk').onchange=apply;
    c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#sg').value='';c.querySelector('#cust').value='';c.querySelector('#gubun').value='all';c.querySelector('#longstk').checked=false;apply();};
    c.querySelector('#xls').onclick=()=>downloadCSV(`${({MAT:'자재',PRD:'생산',SAL:'영업'})[dom]}수불장_${date2ymd(dFrom)}_${date2ymd(dTo)}.csv`,
      ['품목코드','품명','재고수량','재고단가','재고금액','소분류','매입유형','단위','기초재고','기초단가','기초금액','입고수량','입고단가','입고금액','출고수량','출고단가','출고금액','기타수량','기타단가','기타금액','평가조정','담당자','매입처명','최종입고일'],
      cur.map(r=>[r.cd,r.nm,r.sq,r._su,Math.round(r.sa),r._sgn,r._ctn,r.unit,r.bq,r._bu,Math.round(r.ba),r.iq,r._iu,Math.round(r.ia),r.oq,r._ou,Math.round(r.oa),r.tq,r._tu,Math.round(r.ta),Math.round(r.va||0),r._chg,r.cust,r._lin]));
    if(loading){c.querySelector('#body').innerHTML=spinRow(dom==='PRD'?25:24);c.querySelector('#cnt').textContent='';}
    else if(msg){c.querySelector('#body').innerHTML=`<tr><td colspan="${dom==='PRD'?25:24}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`;c.querySelector('#cnt').textContent='';}
    else{render(pool);
      enableSort(c,['cd','nm','sq','_su','sa','_sgn','_ctn','unit','bq','_bu','ba','iq','_iu','ia','oq','_ou','oa','tq','_tu','ta','va','_chg','cust','lastin'],()=>cur,render);}
  };
  load();
};

/* 구매/자재 > 사급출고관리 — 사급출고품(자재불출=매출, PU_T_STOCK_MAINT tag='5') 조회·관리. 자재불출명세서와 동일소스(live)+웹등록분(nx). 단가=마감때만변경(읽기전용). */
SCREEN.saguboutput=(c)=>{
  const API=API_BASE;
  const pad=n=>String(n).padStart(2,"0");
  const iso=d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const yy=s=>s?s.slice(2).replace(/-/g,""):"";
  const now=new Date();
  const won=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const wonI=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const d8=s=>{s=(''+(s||'')).trim();return s.length>=6?`${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`:s;};
  let st={rows:[],cust:"",item:"",fr:iso(new Date(now.getFullYear(),now.getMonth(),1)),to:iso(now),gijun:"issue",sortKey:"",sortDir:1,loading:false,edit:null};
  const load=async()=>{st.loading=true;draw();let live=[],nx=[];
    try{const u=st.gijun==='close'?`${API}/api/live/dispatchdetail?gijun=close&ym=${yy(st.to).slice(0,4)}`
        :`${API}/api/live/dispatchdetail?gijun=issue&dfrom=${yy(st.fr)}&dto=${yy(st.to)}`;
      const j=await (await fetch(u)).json();
      live=(j.rows||[]).map(r=>({ymd:r.ymd,custnm:r.cnm,cust:r.cc,code:r.mat,nm:r.nm,spec:r.spec,qty:+r.qty||0,cost:+r.cost||0,amt:+r.amt||0,vat:+r.vat||0,incust:r.incust,src:'L'}));}catch(e){}
    try{const j=await (await fetch(`${API}/api/saleout/list?fr=${yy(st.fr)}&to=${yy(st.to)}`)).json();
      nx=(j.rows||[]).map(r=>({id:r.id,ymd:r.out_ymd,custnm:r.custnm,cust:r.out_cust,code:r.item_code,nm:r.itemnm,spec:'',qty:+r.out_qty||0,cost:+r.cost||0,amt:+r.amt||0,vat:+r.vat||0,incust:'',src:'N',closed:+r.closed||0,sheet:r.sheet_no||'',wo:r.work_order||'',split:r.split_work_order||''}));}catch(e){}
    st.rows=nx.concat(live);st.loading=false;draw();};
  const del=async(id)=>{if(!window.confirm("이 출고건(웹 등록분)을 삭제할까요?"))return;
    try{const r=await fetch(`${API}/api/saleout/delete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id})});
      const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||r.status);await load();}catch(x){alert("삭제 실패: "+(x.message||x));}};
  const save=async()=>{const e=st.edit;const q=parseFloat(e.qty);if(isNaN(q)||q<=0)return alert("수량(양수)을 입력하세요.");
    try{const r=await fetch(`${API}/api/saleout/save`,{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:e.id,out_cust:e.cust,item_code:e.code,out_qty:q,out_ymd:e.ymd,sheet_no:e.sheet||"",work_order:e.wo||"",split_work_order:e.split||"",cost:e.cost})});
      const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||r.status);st.edit=null;await load();}catch(x){alert("수정 실패: "+(x.message||x));}};
  const draw=()=>{
    const cq=st.cust.trim().toLowerCase(),mq=st.item.trim().toLowerCase();
    let rows=st.rows.filter(r=>(!cq||(''+r.custnm).toLowerCase().includes(cq)||(''+r.cust).toLowerCase().includes(cq))&&(!mq||(''+r.code).toLowerCase().includes(mq)||(''+r.nm).toLowerCase().includes(mq)));
    if(st.sortKey){const k=st.sortKey,d=st.sortDir||1;rows.sort((a,b)=>{const x=a[k],y=b[k];if(typeof x==='number'&&typeof y==='number')return(x-y)*d;return String(x==null?"":x).localeCompare(String(y==null?"":y),"ko",{numeric:true})*d;});}
    const tq=rows.reduce((a,r)=>a+r.qty,0),ta=rows.reduce((a,r)=>a+r.amt,0),tv=rows.reduce((a,r)=>a+r.vat,0);
    c.innerHTML=`
     <div class="page-title">📤 사급출고관리</div>
     <div class="page-sub">사급 출고품(<b>자재불출=매출</b>, PU_T_STOCK_MAINT tag='5') 조회·관리 · <b>웹등록분(nx)만 수정(수량조정)·삭제</b>·레거시분은 조회전용 · <b>매출마감된 자료는 잠금</b>(🔒) · 단가 읽기전용(마감때만 변경)</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="issue" class="${st.gijun==='issue'?'on':''}">불출기준</button><button data-g="close" class="${st.gijun==='close'?'on':''}">마감기준</button></div>
       <label class="tl">기간</label><input class="inp" type="date" id="o-fr" value="${esc(st.fr)}"> ~ <input class="inp" type="date" id="o-to" value="${esc(st.to)}">
       <label class="tl" style="margin-left:8px">불출처</label><input class="inp" id="o-cust" value="${esc(st.cust)}" placeholder="불출처(코드/명)" style="width:130px">
       <label class="tl" style="margin-left:8px">품번</label><input class="inp" id="o-item" value="${esc(st.item)}" placeholder="품번/품명" style="width:120px">
       <button class="btn" id="o-go">🔍 조회</button>
     </div>
     ${st.edit?`<div class="panel" style="border:2px solid #2e86de"><div class="panel-h">출고 수량조정 (웹등록분)</div><div class="panel-b">
       <div class="toolbar" style="flex-wrap:wrap;gap:8px">
         <label class="tl">불출처</label><input class="inp" value="${esc(st.edit.custnm||st.edit.cust)}" style="width:140px" disabled>
         <label class="tl">품번</label><input class="inp" value="${esc(st.edit.code)}" style="width:120px" disabled>
         <label class="tl">일자</label><input class="inp" value="${esc(d8(st.edit.ymd))}" style="width:90px" disabled>
         <label class="tl">단가🔒</label><input class="inp" value="${won(st.edit.cost)}" style="width:90px;text-align:right" disabled>
         <label class="tl">수량<span style="color:red">*</span></label><input class="inp" id="oe-qty" value="${esc(st.edit.qty)}" style="width:100px;text-align:right">
         <button class="btn" id="oe-save" style="background:#27ae60;color:#fff">💾 저장</button>
         <button class="btn" id="oe-cancel">취소</button>
       </div><div style="font-size:11px;color:var(--muted);margin-top:4px">단가는 읽기전용(하드룰) — 수량만 조정. 금액·부가세는 저장 시 단가×수량으로 재계산.</div></div></div>`:""}
     <div class="panel"><div class="panel-h">사급출고 ${st.loading?"(조회중…)":`(${rows.length}건)`}</div><div class="panel-b" style="padding:0">
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl" style="white-space:nowrap"><thead><tr>
         <th data-key="ymd">일자</th><th data-key="custnm">불출처</th><th data-key="code">품번</th><th data-key="nm">품명</th><th data-key="spec">규격</th>
         <th class="num" data-key="qty">수량</th><th class="num" data-key="cost">단가🔒</th><th class="num" data-key="amt">금액(매출)</th><th class="num" data-key="vat">부가세</th>
         <th data-key="incust">입고처</th><th class="center" data-key="src">구분</th><th class="center">관리</th></tr></thead>
       <tbody>${rows.map(r=>`<tr>
         <td>${d8(r.ymd)}</td><td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.custnm||r.cust)}">${esc(r.custnm||r.cust)}</td>
         <td><b>${esc(r.code)}</b></td><td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.nm||"")}">${esc(r.nm||"")}</td>
         <td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.spec||"")}">${esc(r.spec||"")}</td>
         <td class="num qty">${won(r.qty)}</td><td class="num" style="color:#888">${won(r.cost)}</td><td class="num" style="color:#c0392b">${wonI(r.amt)}</td><td class="num">${wonI(r.vat)}</td>
         <td class="cap" style="max-width:110px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.incust||"")}">${esc(r.incust||"")}</td>
         <td class="center">${r.src==='N'?(r.closed?'<span style="color:#c0392b" title="매출마감됨">웹등록🔒</span>':'<span style="color:#2e86de">웹등록</span>'):'<span style="color:#888">레거시</span>'}</td>
         <td class="center">${r.src!=='N'?'<span style="color:#888">조회</span>':(r.closed?'<span style="color:#c0392b" title="매출마감된 자료는 수정/삭제 불가">🔒마감</span>':`<button class="btn xs o-ed" data-id="${r.id}">수정</button> <button class="btn xs o-del" data-id="${r.id}">삭제</button>`)}</td></tr>`).join("")||`<tr><td colspan="12" style="padding:16px;color:var(--muted)">${st.loading?"":"해당 기간 출고 없음"}</td></tr>`}
       <tr class="grandtot"><td colspan="5" class="center">합계 ${rows.length}건</td><td class="num">${won(tq)}</td><td></td><td class="num">${wonI(ta)}</td><td class="num">${wonI(tv)}</td><td colspan="3"></td></tr>
       </tbody></table></div></div></div>`;
    const g=id=>c.querySelector(id);
    c.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{st.gijun=b.dataset.g;load();});
    g("#o-fr").onchange=x=>st.fr=x.target.value;g("#o-to").onchange=x=>st.to=x.target.value;
    g("#o-cust").oninput=x=>st.cust=x.target.value;g("#o-item").oninput=x=>st.item=x.target.value;
    g("#o-go").onclick=load;
    c.querySelectorAll(".o-del").forEach(x=>x.onclick=()=>del(+x.dataset.id));
    c.querySelectorAll(".o-ed").forEach(x=>x.onclick=()=>{const r=st.rows.find(v=>v.src==='N'&&v.id==x.dataset.id);if(r)st.edit={id:r.id,cust:r.cust,custnm:r.custnm,code:r.code,nm:r.nm,ymd:r.ymd,qty:r.qty,cost:r.cost,sheet:r.sheet,wo:r.wo,split:r.split};draw();});
    if(st.edit){const q=c.querySelector("#oe-qty");if(q)q.oninput=x=>st.edit.qty=x.target.value;
      const sv=c.querySelector("#oe-save");if(sv)sv.onclick=save;
      const cn=c.querySelector("#oe-cancel");if(cn)cn.onclick=()=>{st.edit=null;draw();};}
    c.querySelectorAll("thead th").forEach(th=>{addResizer(th);const k=th.dataset.key;if(k){th.style.cursor="pointer";th.title="더블클릭 정렬·경계드래그 너비조절";th.ondblclick=()=>{st.sortDir=(st.sortKey===k&&st.sortDir===1)?-1:1;st.sortKey=k;draw();};}});
  };
  load();
};

/* 구매/자재 > 사급재고입출고현황(SCREEN.sagubstock) — ★작업2로 메뉴·화면 제거됨. 역할은 협력사>협력사사급재고관리(SCREEN.sagubadjust)로 흡수. */

/* 협력사 > 협력사사급재고관리 (★작업3 재구축) — 메인=협력사 보유 사급재고 현황(정본 레거시 PU_T_SAGUB_STOCK RO), 부가=재고조정(nx.sagub_maint TAG='B' CRUD, 실사±).
   보유잔량 = Σ사급출고(원자재) − Σ(완성/세트입고 × 상위품 BOM소요량) − 조정. 레거시 트리거가 net유지한 STOCK_QTY를 정본으로 표시. */
/* ══ 자재개별일괄출고 팝업 (레거시 w_pu_stock_156) ═══════════════════════════
   ★자재창고의 **단품을 다른 창고로 내보내는** 화면이다(2026-08-28 사용자 확정).
     BOM 전개가 아니다 — 자도번을 직접 입력해서 출고한다.
   상단: 출고일자 ◀▶ · FROM파트창고 · TO창고구분(생산/영업) · TO파트 · TO작업처
   그리드: SEQ · 자도번 · 품명 · 규격 · 단위 · 재고수량 · 출고수량 · 비고
   ·행추가 50행씩, 입력된 행만 저장. 엑셀 붙여넣기 지원.
   ·저장 = nx.stock_ledger MAINT_TAG='B'(자재개별출고) · 재고 차감.                */
function openMatIssuePopup(opt){
  const API=API_BASE, onSaved=opt.onSaved||(()=>{});
  const ROWSTEP=50;
  const pad=n=>String(n).padStart(2,'0');
  const isoT=(d=>`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`)(new Date());
  const nf=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const yy=s=>s?s.slice(2).replace(/-/g,''):'';
  let ymd=opt.ymd||isoT, fromWh='IS0001', outGubun='1', toWh='';
  let rows=[], busy=false, info={};
  let whs=opt.whs||[];
  const blank=()=>({mat:'',nm:'',spec:'',unit:'',stock:'',qty:'',rmk:'',bad:0});
  const addRows=n=>{for(let i=0;i<n;i++)rows.push(blank());};
  addRows(ROWSTEP);
  const filled=()=>rows.filter(r=>(r.mat||'').trim()&&Number(r.qty)>0);

  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;z-index:1300;background:rgba(20,30,48,.45);display:flex;align-items:center;justify-content:center';
  document.body.appendChild(ov);
  const close=()=>ov.remove();
  ov.onclick=e=>{if(e.target===ov&&!busy&&!filled().length)close();};

  const bodyHtml=()=>rows.map((r,i)=>`<tr data-i="${i}" class="${(r.mat||'').trim()?'on':''} ${r.bad?'bad':''}">
      <td class="center mut">${i+1}</td>
      <td><input class="mi-mat" data-i="${i}" value="${esc(r.mat)}" autocomplete="off" list="mi-mdl"></td>
      <td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td>
      <td class="cap mut" title="${esc(r.spec||'')}">${esc(r.spec||'')}</td>
      <td class="center mut">${esc(r.unit||'')}</td>
      <td class="num ${(r.mat&&r.stock!==''&&!(Number(r.stock)>0))?'mi-ng':'mut'}">${r.stock===''?'':nf(r.stock)}</td>
      <td><input class="mi-qty" data-i="${i}" type="number" step="any" min="0" value="${esc(r.qty)}" style="text-align:right"></td>
      <td><input class="mi-rmk" data-i="${i}" value="${esc(r.rmk)}"></td>
      <td class="center"><span class="mi-del" data-i="${i}" title="행 비우기">✖</span></td>
    </tr>`).join('')+`<datalist id="mi-mdl"></datalist>`;

  const foot=()=>{const f=filled();
    return `입력 <b>${f.length}</b>건 · 출고수량 <b>${nf(f.reduce((s,r)=>s+Number(r.qty||0),0))}</b>`
         +` <span class="mut">/ ${rows.length}행</span>`;};

  const redrawBody=()=>{
    const ae=document.activeElement;
    const keep=(ae&&ov.contains(ae)&&ae.dataset&&ae.dataset.i!==undefined)
      ?{cls:[...ae.classList].find(x=>x.startsWith('mi-')),i:ae.dataset.i,s:ae.selectionStart,e:ae.selectionEnd}:null;
    const tb=ov.querySelector('#mi-tb');if(tb){tb.innerHTML=bodyHtml();wireRows();}
    const ft=ov.querySelector('#mi-foot');if(ft)ft.innerHTML=foot();
    if(keep&&keep.cls){const el=ov.querySelector(`.${keep.cls}[data-i="${keep.i}"]`);
      if(el){el.focus();try{el.setSelectionRange(keep.s,keep.e);}catch(x){}}}};

  const draw=()=>{
    ov.innerHTML=`
     <div class="mip">
       <div class="mip-h"><span>📤 자재개별일괄출고 — 등 록</span><span class="mip-x" id="mi-x">✕</span></div>
       <div class="mip-tb">
         <label class="tl">출고일자</label>
         <button class="btn ghost mip-nav" id="mi-prev" title="전일">◀</button>
         <input type="date" class="inp mip-w" id="mi-ymd" value="${ymd}" style="width:140px">
         <button class="btn ghost mip-nav" id="mi-next" title="익일">▶</button>
         <label class="tl">FROM파트창고</label>
         <select class="inp mip-w" id="mi-fw" style="width:150px">
           ${(whs.length?whs:[{code:'IS0001',nm:'자재창고'}]).map(w=>`<option value="${esc(w.code)}" ${w.code===fromWh?'selected':''}>${esc(w.code)} ${esc(w.nm||'')}</option>`).join('')}
         </select>
         <label class="tl">TO창고구분</label>
         <select class="inp mip-w" id="mi-og" style="width:110px">
           <option value="1" ${outGubun==='1'?'selected':''}>생산창고</option>
           <option value="2" ${outGubun==='2'?'selected':''}>영업창고</option>
         </select>
         <!-- ★PBL w_pu_stock_156 ue_save_after 원문 기준(2026-08-28 실측 확정)
              구분1 생산창고 → TO파트(to_gagong_proc_code) **필수**, 헤더값 1개를 전 행 일괄저장
                              + 받는 파트에 입고(f_pr_set_mat_stock_wh → nx.PR_T_MAT_STOCK_WH)
              구분2 영업창고 → TO파트 미사용(라이브 8,120건 중 채움 0)
                              + 영업창고 입고(f_sa_set_item_stock → nx.item_stock_maint)
              ※거래처 컬럼은 두지 않는다 — 이 화면은 **제품 이동만** 한다(2026-08-28 사용자 확정) -->
         <label class="tl" ${outGubun==='2'?'style="opacity:.42"':''}>TO파트</label>
         <select class="inp mip-w" id="mi-tw" style="width:170px" ${outGubun==='2'?'disabled':''}>
           <option value="">(선택)</option>
           ${(opt.wcs||[]).map(w=>`<option value="${esc(w.code)}" ${w.code===toWh?'selected':''}>${esc(w.nm||w.code)}</option>`).join('')}
         </select>
         ${outGubun==='2'
            ?'<span class="mip-note">영업창고 = 파트창고 없음</span>'
            :'<span class="mip-note">생산창고 = TO파트 필수(전 행 일괄)</span>'}
       </div>
       <div class="mip-tb">
         <span class="mip-hint">💡 <b>자도번</b>칸에 엑셀 셀을 <b>Ctrl+V</b> 하면 여러 행이 채워집니다(자도번↹수량↹비고).</span>
         <div class="spacer"></div>
         <span class="rowcount" id="mi-foot">${foot()}</span>
       </div>
       <div class="mip-grid"><table class="tbl mip-tbl"><thead><tr>
         <th style="width:44px">SEQ</th><th style="width:170px">자도번</th><th style="width:230px">품명</th>
         <th style="width:150px">규격</th><th style="width:50px">단위</th>
         <th style="width:90px">재고수량</th><th style="width:90px">출고수량</th>
         <th>비고</th><th style="width:32px"></th></tr></thead>
         <tbody id="mi-tb">${bodyHtml()}</tbody></table></div>
       <div class="mip-f">
         <button class="btn" id="mi-add">☰＋ 행추가 (${ROWSTEP})</button>
         <button class="btn ghost" id="mi-clr">☰− 빈행정리</button>
         <div class="spacer"></div>
         <span class="mut" style="font-size:12px">가드: 마감월 잠금 · 재고부족 차단</span>
         <button class="btn" id="mi-save" style="background:#1c7c3a;color:#fff" ${busy?'disabled':''}>✔ 저장</button>
         <button class="btn ghost" id="mi-close">✖ 닫기</button>
       </div>
     </div>
     <style>
      .mip{background:#fff;border-radius:10px;box-shadow:0 12px 40px rgba(20,30,48,.35);
           width:min(1280px,97vw);height:min(88vh,900px);display:flex;flex-direction:column;overflow:hidden}
      .mip-h{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;
             padding:9px 14px;background:#1c47a0;color:#fff;font-weight:700;font-size:14px}
      .mip-x{cursor:pointer;opacity:.85}.mip-x:hover{opacity:1}
      .mip-tb{flex:0 0 auto;display:flex;align-items:center;gap:6px;padding:7px 12px;flex-wrap:wrap}
      .mip-tb:first-of-type{border-bottom:1px solid #e6ecf5}
      .mip-tb:nth-of-type(2){border-bottom:1px solid #c9d3e0;background:#f7f9fd}
      .mip-w{min-width:0}
      .mip-nav{padding:2px 7px;min-width:0}
      .mip-ci{background:#fff8dc;border-color:#e0c97a}
      .mip-ci:focus{background:#fffdf2;border-color:#c9a227;outline:none}
      .mip-cbtn{padding:3px 8px;min-width:0;background:#2f6db3;color:#fff;border-color:#2f6db3}
      .mip-hint{color:#2f5aa8;background:#eef4ff;border-radius:6px;padding:3px 9px;font-size:11.5px}
      .mip-note{color:#8a6d1f;background:#fdf6e3;border:1px solid #ecd9a0;border-radius:6px;padding:2px 8px;font-size:11.5px}
      .mip-grid{flex:1 1 auto;min-height:0;overflow:auto;margin:0 12px;border:1px solid #c9d3e0;border-radius:6px}
      .mip-tbl{font-size:12px;table-layout:fixed;width:100%}
      .mip-tbl th,.mip-tbl td{padding:2px 5px;white-space:nowrap;border-bottom:1px solid #eef1f6}
      .mip-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2;text-align:center;border-bottom:1px solid #c9d3e0}
      .mip-tbl input{border:1px solid transparent;border-radius:3px;padding:2px 4px;font-size:12px;width:100%;background:transparent}
      .mip-tbl input:focus{border-color:#2f6db3;background:#fff;outline:none}
      .mip-tbl tr.on{background:#f4fbf6}.mip-tbl tr.bad input.mi-mat{background:#ffecec;border-color:#c0392b;color:#c0392b}
      .mip-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
      .mip-tbl td.mi-ng{text-align:right;color:#c0392b;font-weight:700;background:#fff2f2}
      .mip-tbl td.mut{color:var(--muted)}.mip-tbl td.cap{overflow:hidden;text-overflow:ellipsis}
      .mip-f{flex:0 0 auto;display:flex;align-items:center;gap:6px;padding:9px 12px;border-top:1px solid #c9d3e0;background:#f7f9fd}
      .mi-del{cursor:pointer;color:#c0392b;opacity:.55}.mi-del:hover{opacity:1}
     </style>`;
    wire();};

  const trace=async(codes)=>{
    codes=[...new Set(codes.map(x=>(x||'').trim().toUpperCase()).filter(Boolean))].filter(x=>info[x]===undefined);
    if(!codes.length)return;
    try{const r=await fetch(`${API}/api/stock/matinfo`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({codes})});
      ((await r.json()).rows||[]).forEach(x=>{info[(x.mat||'').toUpperCase()]=x;});}catch(e){}};
  const applyInfo=()=>{rows.forEach(r=>{const k=(r.mat||'').trim().toUpperCase();if(!k)return;
    const v=info[k];if(!v)return;
    r.nm=v.nm||'';r.spec=v.spec||'';r.unit=v.unit||'';r.stock=v.stock;r.bad=v.unknown?1:0;});};

  function wireRows(){
    const g=s=>ov.querySelectorAll(s);
    g('.mi-mat').forEach(el=>{
      el.onchange=async()=>{const i=+el.dataset.i;rows[i].mat=el.value.trim().toUpperCase();
        await trace([rows[i].mat]);applyInfo();redrawBody();};
      el.onpaste=async ev=>{
        const t=(ev.clipboardData||window.clipboardData).getData('text');
        if(!t||!/[\t\r\n]/.test(t))return;
        ev.preventDefault();
        const start=+el.dataset.i;
        const lines=t.replace(/\r/g,'').split('\n').filter(x=>x.trim()!=='');
        while(rows.length<start+lines.length)addRows(ROWSTEP);
        // 열 순서: 자도번 ↹ 수량 ↹ 비고
        lines.forEach((ln,k)=>{const cl=ln.split('\t'),r=rows[start+k];
          r.mat=(cl[0]||'').trim().toUpperCase();
          if(cl.length>1){const q=parseFloat(String(cl[1]).replace(/,/g,''));if(!isNaN(q))r.qty=q;}
          if(cl.length>2)r.rmk=(cl[2]||'').trim();});
        await trace(lines.map(l=>l.split('\t')[0]));applyInfo();redrawBody();};
      let t=null;
      el.oninput=()=>{const v=el.value.trim();clearTimeout(t);if(v.length<2)return;
        t=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(v)}&all_active=1`);
          const dl=ov.querySelector('#mi-mdl');
          if(dl)dl.innerHTML=((await r.json()).rows||[]).map(x=>`<option value="${esc(x.item)}">${esc(x.name||'')}</option>`).join('');
        }catch(e){}},220);};});
    // 수량 입력은 재렌더 없이 합계만(커서 튐 방지)
    g('.mi-qty').forEach(el=>el.oninput=()=>{const i=+el.dataset.i;rows[i].qty=el.value;
      const ft=ov.querySelector('#mi-foot');if(ft)ft.innerHTML=foot();});
    g('.mi-rmk').forEach(el=>el.oninput=()=>{rows[+el.dataset.i].rmk=el.value;});
    g('.mi-del').forEach(el=>el.onclick=()=>{rows[+el.dataset.i]=blank();redrawBody();});
  }

  function wire(){
    const g=id=>ov.querySelector(id);
    g('#mi-x').onclick=g('#mi-close').onclick=()=>{
      if(filled().length&&!confirm(`입력한 ${filled().length}건이 저장되지 않았습니다. 닫을까요?`))return;close();};
    g('#mi-ymd').onchange=e=>{ymd=e.target.value;};
    const shift=d=>{const t=new Date(ymd);t.setDate(t.getDate()+d);
      ymd=`${t.getFullYear()}-${pad(t.getMonth()+1)}-${pad(t.getDate())}`;draw();};
    g('#mi-prev').onclick=()=>shift(-1);g('#mi-next').onclick=()=>shift(1);
    g('#mi-fw').onchange=e=>{fromWh=e.target.value;};
    // ★영업창고는 파트창고가 없어 TO파트를 쓰지 않는다(2026-08-28 사용자 확정)
    g('#mi-og').onchange=e=>{outGubun=e.target.value;
      if(outGubun==='2') toWh='';
      draw();};
    g('#mi-tw').onchange=e=>{toWh=e.target.value;};
    g('#mi-add').onclick=()=>{addRows(ROWSTEP);redrawBody();};
    g('#mi-clr').onclick=()=>{rows=rows.filter(r=>(r.mat||'').trim());if(rows.length<ROWSTEP)addRows(ROWSTEP-rows.length);redrawBody();};
    g('#mi-save').onclick=save;
    wireRows();
  }

  async function save(){
    if(busy)return;
    const sel=filled();
    if(!sel.length){alert('입력된 행이 없습니다. 자도번과 출고수량을 입력하세요.');return;}
    const bad=sel.filter(r=>r.bad);
    if(bad.length){alert(`미등록 품목 ${bad.length}건:\n`+bad.slice(0,10).map(r=>r.mat).join(', '));return;}
    const short=sel.filter(r=>{const s=Number(r.stock);return !(s>0)||Number(r.qty)>s;});
    if(short.length&&!confirm(
        `재고가 부족한 품목이 ${short.length}건 있습니다:\n\n`
        +short.slice(0,8).map(r=>`  ${r.mat}  재고 ${nf(r.stock||0)} < 출고 ${nf(r.qty)}`).join('\n')
        +`\n\n그래도 저장할까요? (백엔드 재고 가드에서 막힐 수 있습니다)`))return;
    // ★레거시 가드 원문(ue_save_after): 생산파트출고면 TO파트 필수
    if(outGubun==='1'&&!toWh){
      alert('생산파트출고일 경우 출고할 생산파트를 선택해 주십시오.');
      const el=ov.querySelector('#mi-tw');if(el)el.focus();return;}
    const _to=(outGubun==='1')
      ?('생산창고 '+((((opt.wcs||[]).find(w=>w.code===toWh)||{}).nm)||toWh))
      :'영업창고';
    if(!confirm(`${sel.length}건 · 출고수량 ${nf(sel.reduce((s,r)=>s+Number(r.qty||0),0))}\n`
      +`출고일 ${ymd} · ${fromWh} → ${_to}\n\n저장할까요? (재고 차감)`))return;
    busy=true;draw();
    try{
      // 구분1=TO파트 전 행 일괄·거래처 공백 / 구분2=TO파트 공백·거래처 행별 (PBL 원문)
      const _tw=(outGubun==='1')?(toWh||null):null;
      const body={screen:'issue', user:_curUserNm(), rows:sel.map(r=>({
        MAINT_YMD:yy(ymd), MAT_CODE:r.mat, MAINT_TAG:'B', qty:Number(r.qty),
        GAGONG_PROC_CODE:fromWh||null, TO_GAGONG_PROC_CODE:_tw,
        OUT_WH_GUBUN:outGubun||null,
        CUST_CODE:null,                    // 제품 이동만 — 거래처 개념 없음(2026-08-28 사용자 확정)
        REMARKS:(r.rmk||'').trim()||null}))};
      const rr=await fetch(`${API}/api/stock/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await rr.json();
      if(!j.ok){alert('저장 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));busy=false;draw();return;}
      alert(`✅ 저장 완료 — ${j.count}건 출고 (재고 차감)`);
      close();onSaved();
    }catch(e){alert('저장 실패: '+e.message);busy=false;draw();}
  }
  draw();
  setTimeout(()=>{const f=ov.querySelector('.mi-mat');if(f)f.focus();},60);
}

SCREEN.stockissue=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const nfq=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const fmtY=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;};
  const fmtDt=s=>{s=(''+(s||'')).trim();return s?s.replace('T',' ').slice(0,19):'';};
  const iso2ymd=v=>{v=(''+(v||'')).trim();return v.length>=10?v.slice(2).replace(/-/g,''):'';};
  const ymd2iso=y=>{y=(''+(y||'')).trim();return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const todayIso=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const m1Iso=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-01`;};
  let rows=[], tot={cnt:0,qty:0,pages:1}, fw=[], tw=[], page=1, loading=false, msg='', F={out:'',fromwh:'',towh:''};
  const load=async()=>{loading=true;msg='';draw();
    const g=id=>{const e=c.querySelector(id);return e?e.value:'';};
    const f6=iso2ymd(g('#si-from'))||iso2ymd(m1Iso()), t6=iso2ymd(g('#si-to'))||iso2ymd(todayIso());
    const qs=new URLSearchParams({from_ymd:f6,to_ymd:t6,pn:g('#si-pn'),mat:g('#si-mat'),out_wh:F.out,from_wh:F.fromwh,to_wh:F.towh,page:page,size:2000});
    try{const r=await fetch(`${API}/api/live/stockissue?${qs}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();rows=j.rows||[];tot={cnt:j.total_cnt||0,qty:j.total_qty||0,pages:j.pages||1};fw=j.from_whs||[];tw=j.to_whs||[];}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];tot={cnt:0,qty:0,pages:1};}
    loading=false;draw();};
  const draw=()=>{
    const opt=(list,sel)=>['<option value="">%% 전체</option>'].concat(list.map(x=>`<option value="${esc(x.code)}" ${sel===x.code?'selected':''}>${esc(x.nm||x.code)}</option>`)).join('');
    // ★표 아래 여백 제거 확정구조(커밋 4787a13) + 조건문 2줄(자재입고관리·판매출고와 동일 형식)
    c.innerHTML=`
     <div class="si-root" style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="flex:0 0 auto">📤 자재출고관리 <span style="font-size:12px;color:var(--muted);font-weight:400">자재개별출고 (레거시 w_pu_stock_150)</span></div>
     <div class="page-sub" style="flex:0 0 auto">자재창고 → 생산/영업창고 개별출고(파트출고) 조회. 🟢 nx <code>PU_T_STOCK_MAINT</code> (MAINT_TAG in '4'축관·'B'개별출고) · 건수·수량합은 전체 집계.</div>
     <div class="si-cond" style="flex:0 0 auto">
       <div class="si-row">
         <label class="tl">출고기간</label>
         <input type="date" class="inp si-w" id="si-from" value="${esc(ymd2iso(tot._f)||m1Iso())}" style="width:140px">
         <span class="mut">~</span>
         <input type="date" class="inp si-w" id="si-to" value="${esc(ymd2iso(tot._t)||todayIso())}" style="width:140px">
         <label class="tl">P/N</label>
         <input class="inp si-ci si-w" id="si-pn" value="${esc(F._pn||'')}" placeholder="P/N" style="width:130px">
         <label class="tl">자도번</label>
         <input class="inp si-ci si-w" id="si-mat" value="${esc(F._mat||'')}" placeholder="자도번" style="width:130px">
       </div>
       <div class="si-row">
         <label class="tl">FROM파트창고</label><select class="sel" id="si-fw">${opt(fw,F.fromwh)}</select>
         <label class="tl">TO창고구분</label>
         <select class="sel" id="si-out"><option value="">전체</option><option value="1" ${F.out==='1'?'selected':''}>생산창고</option><option value="2" ${F.out==='2'?'selected':''}>영업창고</option></select>
         <label class="tl">TO작업장</label><select class="sel" id="si-tw">${opt(tw,F.towh)}</select>
         <button class="btn" id="si-go">🔍 조회</button>
         <span class="si-act">
           <button class="btn" id="si-add" style="background:#1c47a0;color:#fff" title="레거시 w_pu_stock_156 — ASSY도번 BOM 전개 일괄출고">➕ 등록(출고)</button>
           <button class="btn" id="si-xls">⬇ 엑셀</button>
         </span>
         <div class="spacer"></div>
         <span class="rowcount">총 <b>${nfq(tot.cnt)}</b>건 · 출고수량합 <b>${nf(tot.qty)}</b>${tot.pages>1?` · ${page}/${tot.pages}페이지(2000건씩)`:''}</span>
         ${tot.pages>1?`<button class="btn ghost" id="si-prev" ${page<=1?'disabled':''}>◀ 이전</button><button class="btn ghost" id="si-next" ${page>=tot.pages?'disabled':''}>다음 ▶</button>`:''}
       </div>
     </div>
     ${msg?`<div class="page-sub" style="flex:0 0 auto;color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
     <table class="tbl fit" style="font-size:12px"><thead><tr>
       <th class="center">출고일자</th><th class="num">출고SEQ</th><th>FROM파트창고</th><th>P/N</th><th>TO창고구분</th><th>TO파트창고</th><th>자도번</th>
       <th class="num">출고수량</th><th class="num">출고단가</th><th class="num">출고금액</th><th>비고</th><th>작업자</th><th class="center">작업일시</th></tr></thead>
     <tbody>${loading?spinRow(13):(rows.length?rows.map(r=>`<tr>
       <td class="center">${esc(fmtY(r.ymd))}</td><td class="num">${esc(r.seq)}</td><td>${esc(r.from_wh||'')}</td>
       <td class="cap" title="${esc(r.pn_nm||'')}"><b>${esc(r.pn||'')}</b></td><td>${esc(r.out_wh_nm||'')}</td><td>${esc(r.to_wh||'')}</td><td><b>${esc(r.mat||'')}</b></td>
       <td class="num qty">${nf(r.qty)}</td><td class="num">${nf(r.cost)}</td><td class="num">${nfq(r.amt)}</td><td class="cap" title="${esc(r.remarks||'')}">${esc(r.remarks||'')}</td><td>${esc(r.usr||'')}</td><td class="center">${esc(fmtDt(r.dt))}</td></tr>`).join('')
       :`<tr><td colspan="13" class="empty">${loading?'':'결과 없음'}</td></tr>`)}
       ${rows.length?`<tr class="grandtot"><td colspan="7" class="right">총계 (전체 ${nfq(tot.cnt)}건, 현재페이지 ${rows.length}건)</td><td class="num">${nf(tot.qty)}</td><td colspan="5"></td></tr>`:''}</tbody></table></div>
     <style>
       .si-cond{background:#f7f9fd;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;
                padding:7px 10px;margin:6px 0 8px}
       .si-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
       .si-row+.si-row{margin-top:6px}
       .si-w{min-width:0}                                  /* app.css .inp{min-width:200px} 해제 */
       .si-ci{background:#fff8dc;border-color:#e0c97a}
       .si-ci:focus{background:#fffdf2;border-color:#c9a227;outline:none}
       .si-act{display:inline-flex;align-items:center;gap:6px;margin-left:12px;
               padding-left:12px;border-left:1px solid #cfdcf2}
       .si-root .grid-wrap thead th{text-align:center}     /* 헤더 가운데정렬(공통 규칙) */
       .si-root tr.grandtot td{position:sticky;bottom:0;background:#eaf1fb;font-weight:700;
                               z-index:2;border-top:2px solid #cdd9ef}
     </style>
     </div>`;
    const gv=id=>{const e=c.querySelector(id);return e?e.value.trim():'';};
    const doGo=()=>{F.out=gv('#si-out');F.fromwh=gv('#si-fw');F.towh=gv('#si-tw');F._pn=gv('#si-pn');F._mat=gv('#si-mat');tot._f=iso2ymd(gv('#si-from'));tot._t=iso2ymd(gv('#si-to'));page=1;load();};
    c.querySelector('#si-go').onclick=doGo;
    // ★등록 팝업(레거시 w_pu_stock_156) = **수동출고 전용**.
    //   평소 출고(생산 준비실적·판매 등)는 각 업무화면에서 자동 생성되고 여기엔 조회만 된다.
    {const ad=c.querySelector('#si-add');
     if(ad)ad.onclick=async()=>{
       let whs=[], wcs=[];
       try{const j=await (await fetch(`${API}/api/stock/warehouses`)).json();
         whs=(j.rows||[]).map(x=>({code:x.wh,nm:x.nm})); wcs=j.wcs||[];}catch(e){}
       openMatIssuePopup({ymd:(gv('#si-to')||todayIso()),
         whs:(whs.length?whs:fw), wcs:(wcs.length?wcs:tw), onSaved:load});};}
    ['#si-pn','#si-mat'].forEach(id=>{const e=c.querySelector(id);if(e)e.onkeyup=ev=>{if(ev.key==='Enter')doGo();};});
    ['#si-out','#si-fw','#si-tw','#si-from','#si-to'].forEach(id=>{const e=c.querySelector(id);if(e)e.onchange=doGo;});
    const pv=c.querySelector('#si-prev');if(pv)pv.onclick=()=>{if(page>1){page--;load();}};
    const nx=c.querySelector('#si-next');if(nx)nx.onclick=()=>{if(page<tot.pages){page++;load();}};
    c.querySelector('#si-xls').onclick=()=>downloadCSV('자재출고관리.csv',
      ['출고일자','출고SEQ','FROM파트창고','P/N','품명','TO창고구분','TO파트창고','자도번','출고수량','출고단가','출고금액','비고','작업자','작업일시'],
      rows.map(r=>[fmtY(r.ymd),r.seq,r.from_wh,r.pn,r.pn_nm,r.out_wh_nm,r.to_wh,r.mat,r.qty,r.cost,r.amt,r.remarks,r.usr,fmtDt(r.dt)]));
    attachResizers&&attachResizers(c);enableSort&&enableSort(c);
  };
  load();
};

/* ==== 자재 일마감/수불장(이동평균) — 우리 교정 nx.mat_stock_daily 조회 ====
   기초(직전잔량)+입고−출고+평가조정=기말. 매입=평균갱신·이동/출고=현재평균 불변(수입환율·마이너스가드·tagP 반영). 소모품 제외. */
SCREEN.matclose=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nq=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const iso2ymd=v=>{v=(''+(v||'')).trim();return v.length>=10?v.slice(2).replace(/-/g,''):'';};
  const ymd2iso=y=>{y=(''+(y||'')).trim();return y.length>=6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';};
  const fmtY=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;};
  const m1=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-01`;};
  const tdy=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  let all=[], rows=[], loading=false, msg='', q='', dfrom='', dto='';
  const load=async()=>{
    const gf=c.querySelector('#mc-from'),gt=c.querySelector('#mc-to');   // ★재렌더 前 입력 먼저 읽어 상태갱신(날짜 직접 키인 값 보존 — 안 그러면 draw가 옛값으로 되돌림)
    const f=(gf&&iso2ymd(gf.value))||dfrom, t=(gt&&iso2ymd(gt.value))||dto;
    dfrom=f; dto=t; loading=true; msg=''; draw();
    try{const r=await fetch(`${API}/api/live/matclose?dfrom=${f}&dto=${t}`);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();all=j.rows||[];dfrom=j.dfrom||f;dto=j.dto||t;}
    catch(e){all=[];msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';}
    loading=false;applyF();};
  const adjOf=r=>Number(r.sa||0)-(Number(r.ba||0)+Number(r.ia||0)-Number(r.oa||0));
  const applyF=()=>{const s=q.trim().toLowerCase();
    rows=s?all.filter(r=>(''+(r.cd||'')).toLowerCase().includes(s)||(''+(r.nm||'')).toLowerCase().includes(s)||(''+(r.sgnm||'')).toLowerCase().includes(s)):all;draw();};
  // 품목 일별 수불추이 팝업
  const openLedger=async(cd,nm)=>{
    let el=document.createElement('div');
    el.innerHTML=`<div style="position:fixed;inset:0;z-index:1250;background:rgba(20,30,50,.44);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:44px 12px">
      <div style="background:#fff;border-radius:12px;padding:18px 20px;width:820px;max-width:96vw;box-shadow:0 14px 50px rgba(0,0,0,.34)">
       <div style="font-weight:700;font-size:15px;margin-bottom:10px">📒 ${esc(cd)} <span style="font-size:12px;color:#888;font-weight:400">${esc(nm||'')} · 일별 수불추이(이동평균)</span></div>
       <div id="mcl-body" style="max-height:60vh;overflow:auto"><div class="empty" style="padding:20px">${typeof SPIN!=='undefined'?SPIN:''}조회 중…</div></div>
       <div style="margin-top:14px;text-align:right"><button class="btn" id="mcl-close">닫기</button></div>
      </div></div>`;
    document.body.appendChild(el);
    el.querySelector('#mcl-close').onclick=()=>el.remove();
    el.firstElementChild.onclick=e=>{if(e.target===el.firstElementChild)el.remove();};
    try{const r=await fetch(`${API}/api/live/matclose/ledger?mat=${encodeURIComponent(cd)}&dfrom=${dfrom}&dto=${dto}`);
      const j=await r.json();const L=j.rows||[];
      el.querySelector('#mcl-body').innerHTML=`<table class="tbl" style="font-size:12px;width:100%"><thead><tr style="position:sticky;top:0;background:#eef3fb">
        <th>일자</th><th class="num">입고수량</th><th class="num">입고금액</th><th class="num">출고수량</th><th class="num">출고금액</th><th class="num">재고수량</th><th class="num">평균단가</th><th class="num">재고금액</th></tr></thead>
        <tbody>${L.length?L.map(r=>`<tr><td class="center">${fmtY(r.ymd)}</td><td class="num">${r.iq?nq(r.iq):''}</td><td class="num">${r.ia?nf(r.ia):''}</td><td class="num">${r.oq?nq(r.oq):''}</td><td class="num">${r.oa?nf(r.oa):''}</td><td class="num"><b>${nq(r.sq)}</b></td><td class="num">${nf(r.avg)}</td><td class="num"><b>${nf(r.sa)}</b></td></tr>`).join(''):`<tr><td colspan="8" class="empty">이동 없음</td></tr>`}</tbody></table>`;
    }catch(e){el.querySelector('#mcl-body').innerHTML=`<div class="empty" style="color:#c0392b;padding:20px">조회 실패</div>`;}
  };
  const draw=()=>{
    const T={ba:0,ia:0,oa:0,adj:0,sa:0,bq:0,iq:0,oq:0,sq:0};
    rows.forEach(r=>{T.ba+=+r.ba||0;T.ia+=+r.ia||0;T.oa+=+r.oa||0;T.adj+=adjOf(r);T.sa+=+r.sa||0;T.bq+=+r.bq||0;T.iq+=+r.iq||0;T.oq+=+r.oq||0;T.sq+=+r.sq||0;});
    c.innerHTML=`<div style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="margin-bottom:2px">📗 자재 일마감/수불장 <span style="font-size:12px;color:var(--muted);font-weight:400">이동평균 · nx.mat_stock_daily (교정본)</span></div>
     <div class="page-sub" style="margin-bottom:6px">기초(직전잔량)+입고−출고+평가조정=기말. 매입=평균갱신·이동/출고=현재평균 불변(수입 환율·마이너스재고 가드·tagP 반영). 소모품 제외. 행 클릭=일별추이.</div>
     <div class="toolbar" style="gap:6px;flex:0 0 auto">
       <label class="tl">기간</label><input type="date" class="inp" id="mc-from" value="${esc(ymd2iso(dfrom)||m1())}" style="width:140px"> ~ <input type="date" class="inp" id="mc-to" value="${esc(ymd2iso(dto)||tdy())}" style="width:140px">
       <input class="inp" id="mc-q" placeholder="품번/품명/제품군" value="${esc(q)}" style="width:170px">
       <button class="btn" id="mc-go">🔍 조회</button>
       <div class="spacer"></div><button class="btn xls" id="mc-xls">📥 엑셀</button>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b;flex:0 0 auto">⚠ ${esc(msg)}</div>`:''}
     <div class="summary-bar" style="flex:0 0 auto"><div class="s-item">품목 <b>${nf(rows.length)}</b></div><div class="s-item">기초 <b>${nf(T.ba)}</b></div><div class="s-item">입고 <b>${nf(T.ia)}</b></div><div class="s-item">출고 <b>${nf(T.oa)}</b></div><div class="s-item">기말 <b>${nf(T.sa)} 원</b></div></div>
     <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
     <table class="tbl fit" style="font-size:12px"><thead><tr>
       <th>품번</th><th>품명</th><th>제품군</th>
       <th class="num">기초수량</th><th class="num">기초금액</th><th class="num">입고수량</th><th class="num">입고금액</th>
       <th class="num">출고수량</th><th class="num">출고금액</th><th class="num" title="기말−(기초+입고−출고). 이동평균 평가조정">평가조정</th>
       <th class="num">기말수량</th><th class="num">평균단가</th><th class="num">기말금액</th></tr></thead>
     <tbody id="mc-body"></tbody>
     <tfoot><tr class="grandtot" style="position:sticky;bottom:0;background:#eaf1fb;font-weight:700"><td colspan="3" class="right">총계 ${nf(rows.length)}품목</td>
       <td class="num">${nq(T.bq)}</td><td class="num">${nf(T.ba)}</td><td class="num">${nq(T.iq)}</td><td class="num">${nf(T.ia)}</td>
       <td class="num">${nq(T.oq)}</td><td class="num">${nf(T.oa)}</td><td class="num">${nf(T.adj)}</td><td class="num">${nq(T.sq)}</td><td></td><td class="num">${nf(T.sa)}</td></tr></tfoot></table></div>
     <div class="rowcount" style="flex:0 0 auto">${dfrom?`${fmtY(dfrom)} ~ ${fmtY(dto)}`:''}</div></div>`;
    const b=c.querySelector('#mc-body');
    b.innerHTML=loading?`<tr><td colspan="13" class="empty">${typeof SPIN!=='undefined'?SPIN:''}조회 중…</td></tr>`
      :(rows.length?rows.map(r=>{const adj=adjOf(r);return `<tr class="mc-row" data-cd="${esc(r.cd)}" style="cursor:pointer">
        <td><b>${esc(r.cd)}</b></td><td class="cap" title="${esc(r.nm||'')}">${esc(r.nm||'')}</td><td class="center">${esc(r.sgnm||r.sg||'')}</td>
        <td class="num">${nq(r.bq)}</td><td class="num">${nf(r.ba)}</td><td class="num">${nq(r.iq)}</td><td class="num">${nf(r.ia)}</td>
        <td class="num">${nq(r.oq)}</td><td class="num">${nf(r.oa)}</td><td class="num" style="${Math.abs(adj)>1?'color:#a03d2c':''}">${adj?nf(adj):''}</td>
        <td class="num"><b>${nq(r.sq)}</b></td><td class="num">${nf(r.avg)}</td><td class="num"><b>${nf(r.sa)}</b></td></tr>`;}).join('')
      :`<tr><td colspan="13" class="empty">결과 없음</td></tr>`);
    const go=()=>{q=(c.querySelector('#mc-q').value||'').trim();
      const f=iso2ymd(c.querySelector('#mc-from').value),t=iso2ymd(c.querySelector('#mc-to').value);
      if(f!==dfrom||t!==dto)load();else applyF();};
    c.querySelector('#mc-go').onclick=go;
    c.querySelector('#mc-q').onkeyup=e=>{if(e.key==='Enter')go();};
    // 날짜는 자동조회 안 함(타이핑 중 change로 재렌더→포커스 뺏김 방지). 자유 키인 후 조회버튼/Enter로 적용. (UI규칙: 직접 키인 보장)
    ['#mc-from','#mc-to'].forEach(id=>{const e=c.querySelector(id);if(e)e.onkeyup=ev=>{if(ev.key==='Enter')go();};});
    c.querySelectorAll('.mc-row').forEach(tr=>tr.onclick=()=>{const cd=tr.dataset.cd,r=rows.find(x=>x.cd===cd);openLedger(cd,r?r.nm:'');});
    c.querySelector('#mc-xls').onclick=()=>downloadCSV('자재일마감_'+(dfrom||'')+'_'+(dto||'')+'.csv',
      ['품번','품명','제품군','기초수량','기초금액','입고수량','입고금액','출고수량','출고금액','평가조정','기말수량','평균단가','기말금액'],
      rows.map(r=>[r.cd,r.nm,r.sgnm||r.sg,r.bq,r.ba,r.iq,r.ia,r.oq,r.oa,adjOf(r),r.sq,r.avg,r.sa]));
    if(typeof attachResizers!=='undefined')attachResizers(c);if(typeof enableSort!=='undefined')enableSort(c);
  };
  load();
};

/* ==== 자재입고진행현황(읽기전용 집계): 품목별 현재고=원장 SUM ==== */
SCREEN.matkanban=(c)=>{
  let q='', rows=[], loading=false, msg='';
  const load=async()=>{loading=true;msg='';draw();
    try{const r=await fetch(`${STOCK_API}/api/stock/kanban?q=${encodeURIComponent(q)}`);if(!r.ok)throw new Error('HTTP '+r.status);rows=(await r.json()).rows||[];}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];}
    loading=false;draw();};
  const draw=()=>{
    const tStock=rows.reduce((s,r)=>s+Number(r.stock_qty||0),0);
    const tIn=rows.reduce((s,r)=>s+Number(r.in_qty||0),0);
    const tOut=rows.reduce((s,r)=>s+Number(r.out_qty||0),0);
    c.innerHTML=`
     <div class="page-title">📊 자재입고진행현황 <span style="font-size:12px;color:var(--muted);font-weight:400">nx · 품목별 재고집계(읽기전용)</span></div>
     <div class="page-sub">품목별 현재고 = 원장 누적 SUM. 입고계·출고계와 함께 재고 잔량을 한눈에 확인합니다. (상위 300품목)</div>
     <div class="toolbar">
       <label class="tl">자도번/품명</label><input class="inp" id="kb-q" value="${esc(q)}" placeholder="코드·품명 일부" style="width:180px">
       <button class="btn" id="kb-go">🔍 조회</button>
       <button class="btn" id="kb-xls">⬇ 엑셀</button>
       <div class="spacer"></div>
       <span class="rowcount">${rows.length}품목 · 현재고 <b>${_nf(tStock)}</b> · 입고 ${_nf(tIn)} · 출고 ${_nf(tOut)}</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     ${loading?`<div class="empty">조회 중…</div>`:`
     <div class="grid-wrap kb-wrap"><table class="tbl kb-tbl"><thead><tr>
       <th>자도번</th><th>품명</th><th>규격</th><th>파트</th><th>현재고</th><th>입고계</th><th>출고계</th></tr></thead>
     <tbody>${rows.map(r=>`<tr>
       <td><b>${esc(r.MAT_CODE||'')}</b></td>
       <td class="bcap" title="${esc(r.item_name||'')}">${esc(r.item_name||'')}</td>
       <td class="bcap" title="${esc(r.item_spec||'')}">${esc(r.item_spec||'')}</td>
       <td class="center mut">${esc(r.part||'')}</td>
       <td class="num stk-stock ${Number(r.stock_qty)<0?'neg':''}">${_nf(r.stock_qty)}</td>
       <td class="num" style="color:#2f7d3a">${_nf(r.in_qty)}</td>
       <td class="num" style="color:#c0392b">${_nf(r.out_qty)}</td></tr>`).join('')||`<tr><td colspan="7" class="empty">조회 결과 없음</td></tr>`}</tbody></table></div>`}
     <style>
       .kb-wrap{max-height:calc(100vh - 260px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
       .kb-tbl{font-size:12px}.kb-tbl th,.kb-tbl td{padding:3px 8px;white-space:nowrap}
       .kb-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2}
       .kb-tbl td.bcap{max-width:200px;overflow:hidden;text-overflow:ellipsis}.kb-tbl .mut{color:var(--muted)}
       .kb-tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
       .kb-tbl td.stk-stock{font-weight:700;background:#f2f7ff}.kb-tbl td.neg{color:#c0392b}
     </style>`;
    const qi=c.querySelector('#kb-q');qi.oninput=e=>q=e.target.value;qi.onkeyup=e=>{if(e.key==='Enter')load();};
    c.querySelector('#kb-go').onclick=load;
    c.querySelector('#kb-xls').onclick=()=>dlCSV('자재입고진행현황.csv',['자도번','품명','규격','파트','현재고','입고계','출고계'],
      rows.map(r=>[r.MAT_CODE,r.item_name,r.item_spec,r.part,r.stock_qty,r.in_qty,r.out_qty]));
  };
  load();
};
SCREEN.salemagam=_mkMagam({base:'salemagam',weight:true,title:'🧾 매출마감처리',sub:'협력사 매출(tag5)',src:'PU_T_STOCK_MAINT(5)',verb:'매출',amtlbl:'매출금액',recalc:true});
SCREEN.purmagam=_mkMagam({base:'purmagam',weight:false,title:'📥 매입마감처리',sub:'확정입고 매입(9/S/C/G/H)',src:'PU_T_STOCK_MAINT 확정입고',verb:'매입',amtlbl:'매입금액',recalc:true});   // recalc=매입단가 재계산(레거시 cost_calc) 노출

/* ==== 수동발주 (구매/자재) — 매입처 선택→품목별 계획/재고/추가발주→발주서→메일(UI) ==== */
SCREEN.manorder=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  let vendor=null, items=[], loading=false, msg='', vq='', vlist=[], vsearching=false, buf=20, ordered=false, lead=14;   // lead=발주리드타임(일), 기본 2주. 업체 리드타임테이블(CM_ITEM_SUPPLIER) 있으면 그 값
  let editQty={}, planDates=[];   // editQty: 추가발주 사용자조정값, planDates: 우측 일자별 계획 컬럼(좌측과 동일 items 사용)
  const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const d6=d=>`${String(d.getFullYear()).slice(2)}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
  const cutoffD6=()=>{const d=new Date();d.setDate(d.getDate()+(+lead||0));return d6(d);};                       // 오늘+반영일수 마감일
  const winSum=it=>{if(!it.days)return null;const co=cutoffD6();let s=0,any=false;for(const dd in it.days){any=true;if((''+dd)<=co)s+=(+it.days[dd]||0);}return any?Math.round(s):null;};  // 오늘~오늘+N일 이내 일자별 계획합(=N일치)
  const adjPlan=it=>{const w=winSum(it);return w==null?(+it.plan_qty||0):w;};                                    // ★반영일수(N)만큼의 계획수량. 30일=전체. days없으면 월 전체계획
  const bufQty=it=>Math.round(adjPlan(it)*(buf/100));                                                           // 여유분(조정계획 기준)
  const defAdd=it=>Math.max(0,Math.round(adjPlan(it)+bufQty(it)-(+it.stock_qty||0)-(+it.po_qty||0)));           // 기본 추가발주(리드타임 반영)
  const ord=it=>{const e=editQty[it.ic];return (e!==undefined&&e!=='')?Math.max(0,+e||0):defAdd(it);};         // 사용자 조정 우선
  const searchV=async()=>{vsearching=true;msg='';draw();
    try{const r=await fetch(`${API}/api/manorder/vendors?q=${encodeURIComponent(vq)}`);vlist=(await r.json()).rows||[];}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';vlist=[];}
    vsearching=false;draw();};
  const selV=async(v)=>{vendor=v;vlist=[];ordered=false;editQty={};planDates=[];await loadItems();};
  const loadItems=async()=>{loading=true;msg='';draw();
    // 좌/우 동일 소스: items(각 행에 days=부모 도번 일자별 계획) + dates. 우측 계 = 좌측 계획수량.
    try{const r=await fetch(`${API}/api/manorder/items?cc=${encodeURIComponent(vendor.cc)}`);const j=await r.json();items=j.rows||[];vendor.ym=j.ym;vendor.stock_ym=j.stock_ym;planDates=j.dates||[];}
    catch(e){msg='백엔드 연결 실패';items=[];planDates=[];}
    loading=false;draw();};
  const jsstr=s=>String(s==null?'':s).replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/\r?\n/g,' ');
  // 발주서 본문(스탠드얼론용) — 버튼/스크립트 없는 순수 발주서
  const sheetBody=(list,tot)=>`
     <div class="po">
       <h1>발 주 서</h1>
       <div class="hd"><div>수신: <b>${esc(vendor.nm)}</b> (${esc(vendor.cc)})<br>계획월 ${esc(vendor.ym||'-')} · 여유분 ${buf}%</div>
         <div style="text-align:right">발주일자 <b>${today()}</b><br>(주)피앤씨인더스트리<br>사업자 726-86-02934</div></div>
       <table><thead><tr><th>No</th><th>품목</th><th>품명</th><th class="r">발주수량</th><th>단위</th></tr></thead>
         <tbody>${list.map((it,i)=>`<tr><td class="c">${i+1}</td><td><b>${esc(it.ic)}</b></td><td>${esc(it.nm)}</td><td class="r"><b>${nf(ord(it))}</b></td><td class="c">${esc(it.unit||'EA')}</td></tr>`).join('')}</tbody>
         <tfoot><tr><td colspan="3" class="r">합계 (${list.length}품목)</td><td class="r">${nf(tot)}</td><td></td></tr></tfoot></table>
     </div>`;
  const POCSS=`body{font-family:'맑은 고딕','Malgun Gothic',sans-serif;margin:28px;color:#222;background:#fff}
     .po{max-width:760px;margin:0 auto;border:2px solid #1c47a0;border-radius:10px;padding:22px 26px}
     h1{color:#1c47a0;text-align:center;letter-spacing:8px;margin:0 0 10px;font-size:26px}
     .hd{display:flex;justify-content:space-between;border-bottom:2px solid #1c47a0;padding-bottom:10px;margin-bottom:14px;font-size:13px;line-height:1.5}
     table{width:100%;border-collapse:collapse;font-size:13px} th,td{border:1px solid #b9c4d6;padding:6px 9px} th{background:#eef4ff}
     .r{text-align:right} .c{text-align:center} tfoot td{font-weight:700;background:#f5f8ff}
     .tb{max-width:760px;margin:0 auto 16px;display:flex;gap:10px;align-items:center}
     .pbtn{padding:8px 15px;border:1px solid #1c47a0;background:#1c47a0;color:#fff;border-radius:6px;cursor:pointer;font-size:13px}
     .pbtn.g{background:#fff;color:#1c47a0} .note{color:#c0392b;font-size:12px} @media print{.tb{display:none}}`;
  // 발주 진행 → 선택품목만 새 발주서 팝업창
  const openPO=(list)=>{
    const tot=list.reduce((a,b)=>a+ord(b),0);
    const cleanDoc=`<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>발주서_${esc(vendor.nm)}_${today()}</title><style>${POCSS}</style></head><body>${sheetBody(list,tot)}</body></html>`;
    const w=window.open('','_blank','width=900,height=760,scrollbars=yes');
    if(!w){alert('팝업이 차단되었습니다. 브라우저 팝업 허용 후 다시 시도하세요.');return;}
    const doc=`<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>발주서_${esc(vendor.nm)}_${today()}</title><style>${POCSS}</style></head><body>
      <div class="tb"><button class="pbtn" id="po-mail">📧 이메일 발송</button><button class="pbtn g" id="po-dl">⬇ 발주서 다운로드</button><button class="pbtn g" id="po-print">🖨 인쇄</button><span class="note">※ 이메일 발송은 추후 연결계획입니다</span></div>
      ${sheetBody(list,tot)}
      <script>
        var DOC=${JSON.stringify(cleanDoc)};
        document.getElementById('po-mail').onclick=function(){alert('${jsstr(vendor.nm)} 에게 발주서를 이메일로 발송합니다.\\n\\n추후 연결계획입니다.');};
        document.getElementById('po-print').onclick=function(){window.print();};
        document.getElementById('po-dl').onclick=function(){var b=new Blob([DOC],{type:'text/html;charset=utf-8'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='발주서_${jsstr(vendor.nm)}_${today()}.html';document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},1500);};
      <\/script></body></html>`;
    w.document.open();w.document.write(doc);w.document.close();
  };
  // 우측 협력사 일자별 계획 매트릭스 — ★좌측과 동일 items·동일 순서(순번 1:1 매칭). 계 = 계획수량.
  const dpanel=()=>{
    if(loading)return `<table class="tbl"><tbody>${spinRow(5)}</tbody></table>`;
    const dates=planDates||[];
    if(!items.length)return `<div style="padding:18px;color:#8aa0bd;font-size:13px">품목 없음</div>`;
    if(!dates.length)return `<div style="padding:18px;color:#8aa0bd;font-size:13px">이 매입처의 일자별 계획이 없습니다(계획월 <b>${esc(vendor.ym||'-')}</b> 기준).</div>`;
    const dh=dates.map(d=>`<th class="num" title="${esc(d)}">${esc((''+d).slice(2,4))}/${esc((''+d).slice(4,6))}</th>`).join('');
    const body=items.map((it,i)=>`<tr><td class="center mut">${i+1}</td><td><b>${esc(it.ic)}</b></td><td class="cap" title="${esc(it.nm||'')}">${esc(it.nm||'')}</td><td class="num qty">${nf(it.plan_qty||0)}</td>${dates.map(d=>{const q=(it.days&&it.days[d])||0;return `<td class="num">${q?nf(q):''}</td>`;}).join('')}</tr>`).join('');
    return `<table class="tbl" id="mo-rtbl" style="font-size:12px"><thead><tr><th class="center" style="width:34px">No</th><th>도번</th><th>품명</th><th class="num">계</th>${dh}</tr></thead>
      <tbody>${body}</tbody></table>`;
  };
  const upSum=()=>{let n=0,t=0;items.forEach(it=>{const a=ord(it);if(a>0){n++;t+=a;}});
    const el=c.querySelector('#mo-sum');if(el)el.innerHTML=`계획월 <b>${esc(vendor.ym||'-')}</b> · 재고 <b>${esc(vendor.stock_ym||'-')}</b> · 발주대상 <b>${nf(n)}</b>품목 · 추가발주 총 <b>${nf(t)}</b>`;};
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">🛒 수동발주 <span style="font-size:12px;color:var(--muted);font-weight:400">매입처 선택 → 발주계산(추가발주 조정) + 협력사 일자별 계획 → 발주서</span></div>
     <div class="page-sub">좌: 생산계획(월) 대비 현재고·기발주 반영 추가발주(직접 조정 가능) · 우: 그 매입처 협력사 일자별 계획(한달). 조달 프로파일 배분(<code>nx.sourcing_profile</code>)·발주업체지정(<code>nx.order_vendor</code>)이 설정된 품목은 <b>이 매입처 몫</b>만 계상(미설정=현행 100%). 🟢 nx (계획 <code>PR_T_PLAN_ITEM_DTL</code>·재고 <code>PU_T_MONTH_STOCK_WH</code>)</div>
     <div class="toolbar">
       <label class="tl">매입처</label><input class="inp" id="mo-vq" value="${esc(vq)}" placeholder="업체명/코드 입력" style="width:200px"><button class="btn" id="mo-vsearch">🔍 검색</button>
       ${vendor?`<span style="margin-left:8px;font-weight:700;color:#1c47a0">✔ ${esc(vendor.nm)} (${esc(vendor.cc)})</span> <button class="btn ghost" id="mo-clear">✖ 변경</button>`:''}
       <div class="spacer"></div>
       ${vendor?`<button class="btn" id="mo-order">📋 발주 진행 (선택품목 발주서)</button>`:''}
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     ${!vendor?`
       <div class="grid-wrap" style="max-width:640px;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;margin-top:8px">
         <table class="tbl"><thead><tr><th>코드</th><th>매입처</th><th class="num">품목수</th></tr></thead>
         <tbody>${vsearching?spinRow(3):(vlist.length?vlist.map(v=>`<tr class="mo-vrow" data-cc="${esc(v.cc)}" style="cursor:pointer"><td><b>${esc(v.cc)}</b></td><td>${esc(v.nm)}</td><td class="num">${v.items}</td></tr>`).join(''):`<tr><td colspan="3" class="empty">매입처를 검색하세요 (예: AUDY)</td></tr>`)}</tbody></table>
       </div>`
     :`
       <div class="toolbar" style="margin-top:2px"><span class="rowcount" id="mo-sum"></span><span style="margin-left:12px;color:#8aa0bd;font-size:12px">☑ 발주할 품목 체크 · 추가발주 수량 직접 조정 가능</span></div>
       <div style="display:flex;gap:10px;align-items:flex-start">
         <div style="flex:0 0 47%;min-width:0">
           <div style="font-weight:700;margin:2px 0 4px;color:#1c47a0">발주 계산</div>
           <div class="grid-wrap" id="mo-lwrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
           <table class="tbl fit" id="mo-ltbl" style="font-size:12px"><thead><tr><th class="center" style="width:34px">No</th><th class="center" style="width:32px"><input type="checkbox" id="mo-all" checked title="전체선택"></th><th>품목</th><th>품명</th><th class="num" style="white-space:nowrap">계획수량<br><span style="color:#c0392b;font-size:10px" title="발주 리드타임 — 이 일수 이내 계획분은 발주로 못 바꾸므로 차감(기본 2주)">반영 <input class="inp" id="mo-lead" type="number" min="0" max="365" value="${lead}" style="width:36px;min-width:36px;text-align:right;padding:1px 3px;border-color:#c0392b;color:#c0392b">일</span></th><th class="num">기발주</th><th class="num">현재고</th><th class="num" style="white-space:nowrap">여유분<br><input class="inp" id="mo-buf" type="number" min="0" max="999" value="${buf}" style="width:40px;min-width:40px;text-align:right;padding:2px 4px">%</th><th class="num">추가발주</th></tr></thead>
           <tbody>${loading?spinRow(9):(items.length?items.map((it,i)=>{const a=ord(it);return `<tr><td class="center mut">${i+1}</td><td class="center"><input type="checkbox" class="mo-ck" data-ic="${esc(it.ic)}" ${a>0?'checked':''}></td><td><b>${esc(it.ic)}</b></td><td class="bcap" title="${esc(it.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(it.nm)}</td>
             <td class="num" title="반영 ${lead}일치 계획 ${nf(adjPlan(it))} (월 전체계획 ${nf(it.plan_qty)})${it.alloc_note?' · '+it.alloc_note:''}">${nf(adjPlan(it))}${adjPlan(it)!==(+it.plan_qty||0)?`<br><span style="color:#8aa0bd;font-size:10px">/${nf(it.plan_qty)}</span>`:''}${it.alloc_note?`<br><span style="color:#7a4ca0;font-size:10px" title="조달 프로파일 배분/발주업체지정 적용 — 이 매입처 몫만 계상">${esc(it.alloc_note)}</span>`:''}</td><td class="num">${nf(it.po_qty)}</td><td class="num">${nf(it.stock_qty)}</td><td class="num" style="color:#8aa0bd">${nf(bufQty(it))}</td>
             <td class="num"><input class="mo-add" data-ic="${esc(it.ic)}" type="number" min="0" value="${a}" style="width:74px;text-align:right;font-weight:700;color:#1c7c3a"></td></tr>`;}).join(''):`<tr><td colspan="9" class="empty">품목 없음</td></tr>`)}</tbody></table></div>
         </div>
         <div style="flex:1;min-width:0">
           <div style="font-weight:700;margin:2px 0 4px;color:#1c47a0">협력사 일자별 계획 <span style="font-weight:400;color:#8aa0bd;font-size:12px">${esc(vendor.nm)} · ${esc(vendor.ym||'-')} (좌측과 순번 1:1)</span></div>
           <div class="grid-wrap" id="mo-rwrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">${dpanel()}</div>
         </div>
       </div>`}
     <style>.mo-vrow:hover{background:#eef4ff}#mo-buf::-webkit-outer-spin-button,#mo-buf::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}#mo-buf{-moz-appearance:textfield;appearance:textfield}
       #mo-ltbl tbody tr,#mo-rtbl tbody tr{height:30px}#mo-ltbl td,#mo-rtbl td{padding-top:2px;padding-bottom:2px}#mo-ltbl .mo-add{height:22px;box-sizing:border-box}#mo-ltbl .mo-ck{margin:0}
       #mo-ltbl thead th,#mo-rtbl thead th{height:46px;box-sizing:border-box;vertical-align:middle}</style>`;
    const vs=c.querySelector('#mo-vsearch');if(vs)vs.onclick=()=>{vq=c.querySelector('#mo-vq').value;searchV();};
    const vqi=c.querySelector('#mo-vq');if(vqi)vqi.onkeyup=e=>{if(e.key==='Enter'){vq=e.target.value;searchV();}};
    c.querySelectorAll('.mo-vrow').forEach(r=>r.onclick=()=>{const v=vlist.find(x=>x.cc===r.dataset.cc);if(v)selV(v);});
    const cl=c.querySelector('#mo-clear');if(cl)cl.onclick=()=>{vendor=null;items=[];planDates=[];ordered=false;editQty={};draw();};
    const bf=c.querySelector('#mo-buf');if(bf)bf.onchange=e=>{buf=Math.max(0,+e.target.value||0);editQty={};draw();};
    const ld=c.querySelector('#mo-lead');if(ld)ld.onchange=e=>{lead=Math.max(0,+e.target.value||0);editQty={};draw();};   // 리드타임 변경→계획수량·추가발주 재계산
    const all=c.querySelector('#mo-all');if(all)all.onchange=e=>{c.querySelectorAll('.mo-ck').forEach(x=>x.checked=e.target.checked);};
    c.querySelectorAll('.mo-add').forEach(inp=>inp.oninput=()=>{editQty[inp.dataset.ic]=inp.value;const ck=c.querySelector(`.mo-ck[data-ic="${inp.dataset.ic.replace(/"/g,'\\"')}"]`);if(ck&&(+inp.value||0)>0)ck.checked=true;upSum();});
    const od=c.querySelector('#mo-order');if(od)od.onclick=()=>{
      const ck=new Set([...c.querySelectorAll('.mo-ck:checked')].map(x=>x.dataset.ic));
      const list=items.filter(it=>ck.has(''+it.ic)&&ord(it)>0);
      if(!list.length){alert('발주할 품목을 하나 이상 선택하고, 추가발주 수량이 0보다 커야 합니다.');return;}
      openPO(list);
    };
    if(vendor&&!loading){upSum();attachResizers&&attachResizers(c);
      // 좌우 세로 스크롤 동기화(순번 1:1 정렬 유지)
      const L=c.querySelector('#mo-lwrap'), R=c.querySelector('#mo-rwrap');
      if(L&&R){let sync=false;
        const link=(a,b)=>a.addEventListener('scroll',()=>{if(sync)return;sync=true;b.scrollTop=a.scrollTop;sync=false;});
        link(L,R);link(R,L);}
    }
  };
  draw();
};

/* ==== 원소재/용접봉 월별 시세 (구매/자재) — 무게정산 단가 ==== */
SCREEN.matprice=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ymToInput=y=>{y=(''+(y||'')).trim();return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const inYm=v=>(''+(v||'')).slice(2).replace('-','');
  let ym='', rows=[], loading=false, msg='', edit={};
  const cur=(cat,f,def)=>{const e=edit[cat+'|'+f];if(e!==undefined&&e!=='')return e;const r=rows.find(x=>x.category===cat);const v=r?r[f]:null;return (v!=null&&v!=='')?v:def;};
  const load=async(y)=>{loading=true;msg='';draw();
    try{const r=await fetch(`${API}/api/matprice/list?ym=${encodeURIComponent(y||'')}`);const j=await r.json();rows=j.rows||[];ym=j.ym;edit={};}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';rows=[];}
    loading=false;draw();};
  const save=async()=>{
    const body={ym,rows:['원소재','용접봉'].map(cat=>({category:cat,real_price:cur(cat,'real_price',''),sagub_price:cur(cat,'sagub_price','')}))};
    try{const r=await fetch(`${API}/api/matprice/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();if(!j.ok)throw new Error('save');alert('시세 저장 완료 — 매출마감 무게정산에 반영됩니다.');load(ym);}
    catch(e){alert('저장 실패: '+e.message);}};
  const upDiff=(cat)=>{const sg=+cur(cat,'sagub_price',cat==='원소재'?20000:21100)||0;const si=cur(cat,'real_price','');const el=c.querySelector(`.mp-diff[data-cat="${cat}"]`);
    if(!el)return;if(si===''||si==null){el.textContent='-';el.style.color='#aaa';}else{const d=+si-sg;el.textContent=nf(d);el.style.color=d<0?'#c0392b':'#1c7c3a';}};
  const draw=()=>{
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('matprice'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">💲 원소재/용접봉 월별 시세 <span style="font-size:12px;color:var(--muted);font-weight:400">무게정산 단가</span></div>
     <div class="page-sub">월별 시세·사급가 입력. 매출마감 무게정산 = 차액중량 × (시세 − 사급가). 원소재·용접봉 각각.</div>
     <div class="toolbar"><label class="tl">적용월</label><input type="month" class="inp" id="mp-ym" value="${esc(ymToInput(ym))}" style="min-width:120px">${ed?'<button class="btn" id="mp-save">💾 저장</button>':`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`}</div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-width:660px;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
     <table class="tbl" style="width:100%"><thead><tr><th>구분</th><th class="num">사급가(원/kg)</th><th class="num">시세(원/kg)</th><th class="num">차액단가(시세−사급)</th></tr></thead>
     <tbody>${loading?spinRow(4):['원소재','용접봉'].map(cat=>{const sg=cur(cat,'sagub_price',cat==='원소재'?20000:21100);const si=cur(cat,'real_price','');const df=(si!==''&&si!=null)?(+si-+sg):null;
       return `<tr><td><b>${cat}</b></td>
         <td class="num"><input class="mp-in" data-cat="${cat}" data-f="sagub_price" type="number" step="any" value="${sg}" style="width:120px;text-align:right" ${ed?'':'disabled'}></td>
         <td class="num"><input class="mp-in" data-cat="${cat}" data-f="real_price" type="number" step="any" value="${si}" placeholder="시세 입력" style="width:120px;text-align:right" ${ed?'':'disabled'}></td>
         <td class="num mp-diff" data-cat="${cat}" style="font-weight:700;color:${df==null?'#aaa':(df<0?'#c0392b':'#1c7c3a')}">${df==null?'-':nf(df)}</td></tr>`;}).join('')}</tbody></table></div>
     <div class="page-sub" style="margin-top:8px;color:#8aa0bd">※ 원소재 사급가는 관경별(CU 20,000/고강도 22,000)이나 정산은 대표값. 용접봉 사급가 기본 21,100. 시세 미입력 시 정산금액 0.</div>`;
    bindDate(c.querySelector('#mp-ym'),e=>load(inYm(e.target.value)));
    if(ed){const sb=c.querySelector('#mp-save');if(sb)sb.onclick=save;
      c.querySelectorAll('.mp-in').forEach(el=>el.oninput=()=>{edit[el.dataset.cat+'|'+el.dataset.f]=el.value;upDiff(el.dataset.cat);});}
  };
  load('');
};

/* ===== 자재소요·조달 조회 (정본 nx.plan_mat_source) — BOM전개 소요 + 조달프로파일 공급방식 ===== */
SCREEN.matsource=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const GB={'매입':'#1c47a0','유상사급':'#7a4ca0','외주가공':'#b8860b','외주완성':'#8a6d00','자체':'#1c7c3a','미지정':'#c0392b'};
  let mode='gubun', F={gubun:'',vendor:'',mat:'',wo:''}, rows=[], loading=false, msg='';
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({mode,gubun:F.gubun,vendor:F.vendor,mat:F.mat,wo:F.wo});
    try{const r=await fetch(`${API}/api/plan/sourcing?${qs}`);const j=await r.json();rows=j.rows||[];msg=j.ok?'':(j.error||'조회 실패');}
    catch(e){msg='백엔드 연결 실패';rows=[];}
    loading=false;draw();};
  const draw=()=>{
    const tot=rows.reduce((s,r)=>s+Number(r.qty||0),0);
    // 규칙17: 로드된 rows에서 공급처/자재(코드값→이름표시)·제번 datalist 생성
    const vMap=new Map(),matMap=new Map(),woMap=new Map();
    rows.forEach(r=>{
      if(r.VENDOR_CODE&&!vMap.has(r.VENDOR_CODE))vMap.set(r.VENDOR_CODE,r.vname||'');
      if(r.MAT_CODE&&!matMap.has(r.MAT_CODE))matMap.set(r.MAT_CODE,r.mname||'');
      if(r.WORK_ORDER&&!woMap.has(r.WORK_ORDER))woMap.set(r.WORK_ORDER,'');});
    const vOpts=[...vMap].map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const matOpts=[...matMap].map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const woOpts=[...woMap.keys()].map(v=>`<option value="${esc(v)}"></option>`).join('');
    const head=mode==='gubun'?`<tr><th>공급방식</th><th class="num">자재종수</th><th class="num">조달소요</th><th class="num">프로파일유래</th><th class="num">BOM기본유래</th><th class="num">비중</th></tr>`
      :mode==='vendor'?`<tr><th>공급방식</th><th>공급처코드</th><th>공급처명</th><th class="num">자재종수</th><th class="num">조달소요</th><th class="num">비중</th></tr>`
      :`<tr><th>제번</th><th>자재</th><th>자재명</th><th>공급방식</th><th>공급처</th><th>공급처명</th><th class="num">소요</th><th>출처</th></tr>`;
    const body=loading?`<tr><td colspan="8" class="empty">조회 중…</td></tr>`:(rows.length?rows.map(r=>{
      if(mode==='gubun')return `<tr><td><span style="color:${GB[r.SUPPLY_GUBUN]||'#333'};font-weight:600">${esc(r.SUPPLY_GUBUN)}</span></td><td class="num">${nf(r.mats)}</td><td class="num"><b>${nf(r.qty)}</b></td><td class="num" style="color:#7a4ca0">${nf(r.prof_qty)}</td><td class="num" style="color:#8899aa">${nf(r.qty-r.prof_qty)}</td><td class="num">${tot?(100*r.qty/tot).toFixed(1):0}%</td></tr>`;
      if(mode==='vendor')return `<tr><td><span style="color:${GB[r.SUPPLY_GUBUN]||'#333'}">${esc(r.SUPPLY_GUBUN)}</span></td><td>${esc(r.VENDOR_CODE)}</td><td>${esc(r.vname)}</td><td class="num">${nf(r.mats)}</td><td class="num"><b>${nf(r.qty)}</b></td><td class="num">${tot?(100*r.qty/tot).toFixed(1):0}%</td></tr>`;
      return `<tr><td><b>${esc(r.WORK_ORDER)}</b></td><td>${esc(r.MAT_CODE)}</td><td class="bcap" title="${esc(r.mname)}" style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${esc(r.mname)}</td><td><span style="color:${GB[r.SUPPLY_GUBUN]||'#333'}">${esc(r.SUPPLY_GUBUN)}</span></td><td>${esc(r.VENDOR_CODE)}</td><td>${esc(r.vname)}</td><td class="num">${nf(r.QTY)}</td><td class="center">${r.SOURCE==='프로파일'?'<span style="color:#7a4ca0">프로파일</span>':'<span style="color:#8899aa">BOM기본</span>'}</td></tr>`;
    }).join(''):`<tr><td colspan="8" class="empty">${msg||'데이터 없음 — 생산계획업로드 화면에서 🧾자재소요·조달 편성을 먼저 실행하세요.'}</td></tr>`);
    c.innerHTML=`
     <div class="page-title">🧾 자재소요·조달 조회 <span style="font-size:12px;color:var(--muted);font-weight:400">정본 자재소요(BOM전개) + 조달 프로파일 공급방식</span></div>
     <div class="page-sub">레거시 STEP5→6→7 충실이식 정본 자재소요(<code>nx.plan_part_mat</code>, 수량100%검증)에 조달 프로파일을 오버레이. 프로파일 없는 자재는 BOM기본(MAKE_TYPE·가공처)으로 분류. 용접봉(그룹910)·자체생산 중간품은 규칙상 제외.</div>
     <div class="toolbar">
       <label class="tl">보기</label><select class="inp" id="m-mode"><option value="gubun"${mode==='gubun'?' selected':''}>공급방식별</option><option value="vendor"${mode==='vendor'?' selected':''}>공급처별</option><option value="detail"${mode==='detail'?' selected':''}>명세(제번×자재)</option></select>
       <label class="tl">공급방식</label><select class="inp" id="m-gubun"><option value="">전체</option>${['매입','유상사급','외주가공','외주완성','자체','미지정'].map(g=>`<option value="${g}"${F.gubun===g?' selected':''}>${g}</option>`).join('')}</select>
       <label class="tl">공급처</label><input class="inp" id="m-vendor" list="ms-vendorl" value="${esc(F.vendor)}" style="width:110px" placeholder="공급처코드/명" autocomplete="off"><datalist id="ms-vendorl">${vOpts}</datalist>
       <label class="tl">자재</label><input class="inp" id="m-mat" list="ms-matl" value="${esc(F.mat)}" style="width:120px" placeholder="자재코드/명" autocomplete="off"><datalist id="ms-matl">${matOpts}</datalist>
       <label class="tl">제번</label><input class="inp" id="m-wo" list="ms-wol" value="${esc(F.wo)}" style="width:100px" placeholder="제번 입력" autocomplete="off"><datalist id="ms-wol">${woOpts}</datalist>
       <button class="btn" id="m-search">🔍 조회</button>
     </div>
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">행 <b>${nf(rows.length)}</b> · 조달소요합 <b>${nf(tot)}</b></span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:12px"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#m-mode').onchange=e=>{mode=e.target.value;load();};
    g('#m-search').onclick=()=>{F.gubun=g('#m-gubun').value;F.vendor=g('#m-vendor').value;F.mat=g('#m-mat').value;F.wo=g('#m-wo').value;load();};
    ['#m-vendor','#m-mat','#m-wo'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#m-search').click();});
  };
  load();
};

/* ===== 생산 ②: 파트별 생산계획 (w_pr_input_410) — PR_T_PLAN_PART_MAT 라이브 ===== */
/* ===== 자재입고(발주분 입고: 개별일괄 057 / PO바코드 057_1) — nx.stock_ledger, 발주잔량 차감 ===== */
SCREEN.matreceive=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const y6=s=>{s=(''+(s||'')).replace(/-/g,'');return s.length>=8?s.slice(2):s;};
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  let tab='batch', F={cust:'',item:'',sheet:'',ymd:iso(new Date()),wh:'IS0001'}, rows=[], loading=false, msg='';
  const isG=()=>tab==='gagong';
  const load=async()=>{loading=true;draw();
    try{
      if(isG()){
        const qs=new URLSearchParams({sheet:F.sheet,item:F.item});
        const r=await fetch(`${API}/api/matrecv/gagong_pending?${qs}`);const j=await r.json();
        rows=(j.rows||[]).map(x=>({ITEM_CODE:x.MAT_CODE,nm:x.nm,spec:x.spec,cust_nm:'',CUST_CODE:'',PUR_YMD:x.MAINT_YMD,DLVY_YMD:'',
          remain:x.remain,inq:x.remain,nx_in:x.nx_in,move_qty:x.MAINT_QTY,pur_cost:0,insp:'',
          group_seq:x.MAINT_GROUP_SEQ,upper:x.upper_code,gagong:x.GAGONG_PROC_CODE,to_gagong:x.TO_GAGONG_PROC_CODE}));msg=j._err||'';
      }else{
        const qs=new URLSearchParams({cust:F.cust,item:F.item,sheet:(tab==='barcode'?F.sheet:'')});
        const r=await fetch(`${API}/api/matrecv/po_pending?${qs}`);const j=await r.json();rows=(j.rows||[]).map(x=>({...x,inq:x.remain}));msg=j._err||'';
      }
    }catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';rows=[];}
    loading=false;draw();};
  const receive=async()=>{
    const sel=rows.filter(r=>Number(r.inq)>0);
    if(!sel.length){alert('입고수량(잔량 이내)을 입력한 행이 없습니다.');return;}
    if(!confirm(`${sel.length}건 입고 확정합니다. ${isG()?'가공이동전표가 입고 처리':'발주잔량이 차감'}되고 재고가 증가합니다.\n(입고일 ${F.ymd}${isG()?'':', 창고 '+F.wh})`))return;
    let ep,body;
    if(isG()){ep='/api/matrecv/gagong_receive';body={ymd:y6(F.ymd),rows:sel.map(r=>({item:r.ITEM_CODE,qty:Number(r.inq),group_seq:r.group_seq,upper:r.upper,gagong:r.gagong,to_gagong:r.to_gagong}))};}
    else{ep='/api/matrecv/receive';body={ymd:y6(F.ymd),wh:F.wh,rows:sel.map(r=>({item:r.ITEM_CODE,qty:Number(r.inq),cost:r.pur_cost,cust:r.CUST_CODE,pur_ymd:r.PUR_YMD,pur_seq:r.PUR_SEQ,pur_seq_row:r.PUR_SEQ_ROW,insp:r.insp}))};}
    try{const r=await fetch(`${API}${ep}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();
      if(j.ok){alert(`✅ 입고 확정 ${j.count}건 완료 (재고 반영)`);load();}
      else alert('입고 실패:\n'+((j.errors||[j.error||JSON.stringify(j)]).join('\n')));}
    catch(e){alert('입고 오류: '+e);}
  };
  const draw=()=>{
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('matreceive'):true;
    const TAB=[['batch','📋 개별일괄입고(발주분)'],['barcode','🔫 PO바코드입고'],['gagong','🔧 가공이동바코드']];
    const bc=(tab==='barcode'||isG());
    const hdr=isG()?`<th>그룹SEQ</th><th>자도번</th><th>품명</th><th>상위품번</th><th>가공처</th><th>입고창고</th><th class="num">이동수량</th><th class="num">웹입고</th><th class="num">잔량</th><th class="num">입고수량</th>`
      :`<th>거래처</th><th>자도번</th><th>품명</th><th>규격</th><th>발주일</th><th>납기</th><th class="num">발주</th><th class="num">기입고</th><th class="num">취소</th><th class="num">웹입고</th><th class="num">잔량</th><th class="num">입고수량</th><th class="num">단가</th>`;
    const ncol=isG()?10:13;
    const rowHtml=(r,i)=>isG()
      ?`<tr><td>${esc(r.group_seq)}</td><td><b>${esc(r.ITEM_CODE)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td>${esc(r.upper)}</td><td class="center">${esc(r.gagong)}</td><td class="center">${esc(r.to_gagong)}</td><td class="num">${nf(r.move_qty)}</td><td class="num">${nf(r.nx_in)}</td><td class="num"><b style="color:#1c47a0">${nf(r.remain)}</b></td><td class="num"><input class="inp mr-inq" data-i="${i}" type="number" min="0" max="${r.remain}" value="${r.inq}" style="width:70px;text-align:right"></td></tr>`
      :`<tr><td class="bcap" title="${esc(r.cust_nm)}" style="max-width:90px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm||r.CUST_CODE)}</td><td><b>${esc(r.ITEM_CODE)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td>${esc(r.spec)}</td><td class="center">${dcol(r.PUR_YMD)}</td><td class="center">${dcol(r.DLVY_YMD)}</td><td class="num">${nf(r.PUR_QTY)}</td><td class="num">${nf(r.in_qty)}</td><td class="num">${nf(r.cancel_qty)}</td><td class="num">${nf(r.nx_in)}</td><td class="num"><b style="color:#1c47a0">${nf(r.remain)}</b></td><td class="num"><input class="inp mr-inq" data-i="${i}" type="number" min="0" max="${r.remain}" value="${r.inq}" style="width:70px;text-align:right"></td><td class="num">${nf(r.pur_cost)}</td></tr>`;
    c.innerHTML=`
     <div class="page-title">📦 자재입고 <span style="font-size:12px;color:var(--muted);font-weight:400">${isG()?'가공이동전표 입고':'발주분 입고'} · 재고반영</span></div>
     <div class="page-sub">${isG()?'가공이동전표(<code>PU_T_STOCK_MAINT_GAGONG_MOVE</code>) 미입고분을 바코드/자도번으로 조회→입고. 입고구분 <b>C(가공입고)</b>':'발주(<code>PU_T_PURCHASE_DTL</code>) 잔량분 입고. <b>발주잔량=발주−기입고−취소−웹입고</b>'} · 입고확정 시 <code>nx.stock_ledger</code> 기록(재고↑, 삭제=역진행) · 일/월 마감월 입고 차단</div>
     <div id="mr-tabs" style="display:flex;gap:4px;padding:4px 0 0;border-bottom:2px solid #dce3ee;margin-bottom:8px">
       ${TAB.map(t=>`<button class="btn ${tab===t[0]?'':'ghost'}" data-tab="${t[0]}" style="border-radius:8px 8px 0 0;${tab===t[0]?'background:#1c47a0;color:#fff':''}">${t[1]}</button>`).join('')}</div>
     <div class="toolbar">
       ${bc?`<label class="tl">바코드${isG()?'(MV)':'(PO)'}</label><input class="inp" id="mr-sheet" value="${esc(F.sheet)}" placeholder="${isG()?'MV 바코드 스캔':'PO 바코드 스캔'}/입력" style="width:150px">`:`<label class="tl">거래처</label><input class="inp" id="mr-cust" list="mrl-cust" value="${esc(F.cust)}" placeholder="거래처코드/명" autocomplete="off" style="width:110px"><datalist id="mrl-cust">${[...new Map((rows||[]).map(r=>[r.CUST_CODE,r.cust_nm])).entries()].filter(([v])=>v).map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('')}</datalist>`}
       <label class="tl">자도번</label><input class="inp" id="mr-item" list="mrl-item" value="${esc(F.item)}" placeholder="자도번/품명" autocomplete="off" style="width:120px"><datalist id="mrl-item">${[...new Map((rows||[]).map(r=>[r.ITEM_CODE,r.nm])).entries()].map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('')}</datalist>
       <button class="btn" id="mr-go">🔍 조회</button>
       <div class="spacer"></div>
       <label class="tl">입고일자</label><input type="date" class="inp" id="mr-ymd" value="${F.ymd}" style="width:135px">
       ${isG()?'':`<label class="tl">입고창고</label><input class="inp" id="mr-wh" value="${esc(F.wh)}" style="width:80px">`}
       ${canW?`<button class="btn" id="mr-recv" style="background:#1c7c3a;color:#fff">⬇ 입고확정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 입고 권한 없음</span>`}
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="toolbar" style="margin-top:2px"><span class="rowcount">${isG()?'미입고 이동전표':'발주잔량분'} <b>${nf(rows.length)}</b>건 · 입고예정합 <b>${nf(rows.reduce((s,r)=>s+(Number(r.inq)||0),0))}</b></span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>${hdr}</tr></thead>
      <tbody>${loading?spinRow(ncol):(rows.length?rows.map(rowHtml).join(''):`<tr><td colspan="${ncol}" class="empty">${bc?'바코드를 스캔/입력하고 조회하세요':'발주잔량분 없음 — 조회 조건을 바꾸세요'}</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    c.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{if(tab!==b.dataset.tab){tab=b.dataset.tab;rows=[];draw();}});
    g('#mr-go').onclick=()=>{if(g('#mr-cust'))F.cust=g('#mr-cust').value;F.item=g('#mr-item').value;if(g('#mr-sheet'))F.sheet=g('#mr-sheet').value;load();};
    g('#mr-ymd').onchange=e=>F.ymd=e.target.value;
    if(g('#mr-wh'))g('#mr-wh').oninput=e=>F.wh=e.target.value;
    const rc=g('#mr-recv');if(rc)rc.onclick=()=>{F.ymd=g('#mr-ymd').value;if(g('#mr-wh'))F.wh=g('#mr-wh').value;receive();};
    c.querySelectorAll('.mr-inq').forEach(el=>el.oninput=()=>{const i=+el.dataset.i;let v=Number(el.value)||0;if(v>rows[i].remain){v=rows[i].remain;el.value=v;}rows[i].inq=v;});
    const sh=g('#mr-sheet');if(sh)sh.onkeyup=e=>{if(e.key==='Enter'){F.sheet=sh.value;load();}};
    ['#mr-cust','#mr-item'].forEach(id=>{if(g(id))g(id).onkeyup=e=>{if(e.key==='Enter')g('#mr-go').click();};});
  };
  load();
};

/* ★조달 프로파일 재구성 — 개발(조달경로 통합검토)과 동일 레이아웃(실제BOM+후보,현행=실입고,공정) + 유효기간·배분% 편집. */
SCREEN.sourceprofile=(c)=>{
  const API=API_BASE;
  const MKC={'자체':'#1c7c3a','외주(유상사급)':'#b8860b','매입':'#1c47a0','미지정':'#888'};
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('sourceprofile'):true;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const today=iso(new Date()), CLOSE='2026-06-30', OPEN='2030-12-31', FROM0='2026-07-01';
  const baseOf=x=>{x=(x||'').trim().toUpperCase();const m=x.match(/^([A-Z]{2,4}\d+)/);return m?m[1]:x;};
  const nfq=v=>{v=Number(v||0);return v%1===0?v.toLocaleString('ko-KR'):v.toFixed(4).replace(/0+$/,'').replace(/\.$/,'');};
  let q='', slist=[], sel=null, selNm='', tree=null, tload=false, searching=false, msg='', acT=null, edit={}, ref=today;
  let showUnappr=false, routes=[], allocErrs=[], activeRid=null;   // 조달경로 후보(nx.sourcing_route) + 저장된 활성경로(nx.route_alloc). ★택1: activeRid=운영 활성 경로 route_id(항상 1개=100%, 배분% 폐지)
  let selRid=null, rtree={}, rvmap={};   // ★선택 경로(null=현행 R01)·경로별 BOM트리 캐시·경로별 부품→업체배분 캐시(R01=current_order·R02=route/detail)
  const loadAlloc=async()=>{try{const r=await fetch(`${API}/api/sourcing/route/alloc?item=${encodeURIComponent(sel)}&show_unapproved=${showUnappr?1:0}`);const j=await r.json();routes=j.routes||[];allocErrs=j.alloc_errs||[];}catch(e){routes=[];allocErrs=[];}};
  const search=async(auto)=>{searching=true;draw();
    try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(q)}`);slist=(await r.json()).rows||[];}
    catch(e){slist=[];msg='검색 실패';}
    searching=false;draw();if(auto&&slist.length&&!sel)open(slist[0].item);};
  const fillDL=()=>{const dl=c.querySelector('#sp-dl');if(dl)dl.innerHTML=slist.slice(0,60).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');};
  const ac=t=>{clearTimeout(acT);acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);slist=(await r.json()).rows||[];fillDL();}catch(e){}},180);};
  const loadCurVend=async(item)=>{try{const j=await(await fetch(`${API}/api/sourcing/current_order?item=${encodeURIComponent(item)}`)).json();
    const m={};(j.rows||[]).forEach(x=>{m[String(x.item_code).trim()]=(x.vendors||[]).map(v=>({name:v.vendor_name||v.vendor_code,ratio:v.alloc_ratio}));});return m;}catch(e){return {};}};
  const open=async(item)=>{sel=item;selNm='';tree=null;tload=true;edit={};selRid=null;rtree={};rvmap={};draw();
    try{const r=await fetch(`${API}/api/bom/tree?item=${encodeURIComponent(item)}`);const j=await r.json();tree=j.rows||[];selNm=j.name||'';}catch(e){tree=[];}
    await loadAlloc();
    const av=routes.find(r=>r.is_active)||routes.find(r=>_isCur(r))||routes[0];   // ★택1 활성경로 초기화(저장된 활성>현행R01>첫행)
    activeRid=av?av.route_id:null;
    rvmap['_cur']=await loadCurVend(item);   // ★현행(R01) 부품별 다중업체·비율(order_vendor)
    tload=false;draw();};
  const curE=(rid,f,dflt)=>{const k=rid+'|'+f;return edit[k]!==undefined?edit[k]:dflt;};
  const setE=(rid,f,v)=>{edit[rid+'|'+f]=v;};
  const _isCur=r=>!!(r.current_flag||r.route_no===1);   // R01(현행)
  const ract=r=>r.route_id===activeRid;   // ★택1 — 활성경로(activeRid)만 true. 배분% 폐지(항상 100%)
  const setActive=rid=>{activeRid=+rid;draw();};   // ★라디오: 하나 선택 시 나머지 자동 비활성
  const save=async()=>{
    const chosen=routes.find(r=>r.route_id===activeRid);
    if(!chosen){alert('활성 경로를 선택하세요.');return;}
    if(chosen.readonly||(!_isCur(chosen)&&!chosen.approve_flag)){alert('저장 불가 — 미승인/배정불가 후보는 활성 경로로 지정할 수 없습니다(개발 › 조달경로 통합검토에서 승인 필요).');return;}
    const rows=routes.filter(r=>!r.readonly).map(r=>({route_id:r.route_id,apply_from:null,apply_to:null,
      is_active:(r.route_id===activeRid)?1:0,alloc_ratio:(r.route_id===activeRid)?100:null}));   // ★택1=활성 100%·나머지 null
    try{const r=await fetch(`${API}/api/sourcing/route/alloc/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item:sel,rows})});
      const j=await r.json();if(j.ok){alert('저장 완료 — 활성 경로 확정');open(sel);return;}
      const hint=j.gate==='VENDOR'?'활성 경로의 매입처 미지정 부품이 있습니다 — [✎ 매입처 수정]에서 지정하세요(R01 매입처가 자동 채워짐)':(j.gate==='APPROVE'?'미승인 후보는 활성 배정 불가(개발 승인 필요)':(j.gate==='ALLOC'?'배분 검증 실패':'저장 거부'));
      alert('저장 실패 — '+hint+':\n\n'+(j.errors?j.errors.join('\n'):JSON.stringify(j)));}
    catch(e){alert('저장 실패: '+e);}};
  // ===== 업체·단가 모달 — ★ASSY 매입단가=업체별(공통 없음), 업체=배분%(정수). 사급 부품가 UI 없음(이 모달 스코프 밖) =====
  // ASSY 매입단가=외주 SUB×업체별(nx.item_price gubun=매입, vendor=지정 항상). 단품 매입=매입 마스터 자동(입력X). 사급 부품가=품목단가 관리에서(여기 아님).
  // ★후보/계획 단가(정산 아님): nx만 저장. 정산 마스터 불변(마감때만).
  const isoToday=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  let pm=null, pmAcT=null;   // pm={route,hdr,rows[](업체),subs[],assyV{}(업체×SUB ASSY),direct[],msg,loading}
  const SG_OPTS=[['2','외주(유상사급)'],['1','자체'],['3','매입']];
  const OK=(vc,key)=>`${vc}||${key}`;   // 맵 키(업체||SUB)
  const blankVRow=()=>({profile_id:0,vendor_code:'',vendor_name:'',supply_gubun:'2',alloc_ratio:null,apply_from:isoToday(),apply_to:'',is_active:1,lme_flag:0,_delete:false});
  const pmOpen=async(r)=>{pm={route:r,hdr:null,rows:[],subs:[],assyV:{},direct:[],msg:'',loading:true};draw();
    try{const res=await fetch(`${API}/api/sourcing/profile/list?route_id=${r.route_id}`);const j=await res.json();
      pm.hdr=j.header||null;
      pm.rows=(j.rows||[]).map(x=>({profile_id:x.profile_id,vendor_code:x.vendor_code||'',vendor_name:x.vendor_name||'',
        supply_gubun:x.supply_gubun||'2',alloc_ratio:(x.alloc_ratio!=null?Math.round(x.alloc_ratio):null),
        apply_from:x.apply_from||'',apply_to:x.apply_to||'',is_active:x.is_active?1:0,lme_flag:x.lme_flag?1:0,_delete:false}));
      if(!pm.rows.length)pm.rows=[blankVRow()];
    }catch(e){pm.msg='업체 목록 로드 실패';}
    try{const sr=await fetch(`${API}/api/sourcing/sub_price?route_id=${r.route_id}`);const sj=await sr.json();
      pm.subs=sj.subs||[];pm.direct=sj.direct_items||[];
      // ★ASSY=업체별만(공통 무시). override 배열 = 업체별 값.
      (sj.prices||[]).forEach(p=>{(p.overrides||[]).forEach(o=>{pm.assyV[OK(o.vendor_code,p.sub_item)]=(o.assy_price!=null?o.assy_price:null);});});
    }catch(e){}
    pm.loading=false;draw();};
  const pmClose=()=>{pm=null;draw();};
  const pmAddRow=()=>{pm.rows.push(blankVRow());draw();};
  const pmDelRow=i=>{const r=pm.rows[i];if(!r)return;if(r.profile_id>0){r._delete=true;}else{pm.rows.splice(i,1);}draw();};
  const pmActive=()=>pm.rows.filter(r=>!r._delete&&r.is_active&&r.vendor_code);
  const pmStat=()=>{const act=pmActive();const withAl=act.filter(r=>r.alloc_ratio!==''&&r.alloc_ratio!=null);
    const sum=Math.round(withAl.reduce((a,r)=>a+(parseFloat(r.alloc_ratio)||0),0)*100)/100;
    return {n:act.length,sum,single:act.length<=1,withAl:withAl.length};};
  const pmVendorAC=(t)=>{clearTimeout(pmAcT);pmAcT=setTimeout(async()=>{
    try{const r=await fetch(`${API}/api/sourcing/vendors?q=${encodeURIComponent(t)}`);const vs=(await r.json()).rows||[];
      pm._vlist=vs;const dl=c.querySelector('#pm-vdl');if(dl)dl.innerHTML=vs.map(v=>`<option value="${esc(v.name)}">${esc(v.name)} (${esc(v.code)})${v.role?' · '+esc(v.role):''}</option>`).join('');}catch(e){}},180);};
  const pmResolveVendor=(idx,val)=>{const v=val.trim();const list=pm._vlist||[];
    const hit=list.find(x=>x.name===v)||list.find(x=>x.code===v)||list.find(x=>(x.name||'').indexOf(v)>=0);
    if(hit){pm.rows[idx].vendor_code=hit.code;pm.rows[idx].vendor_name=hit.name;}else{pm.rows[idx].vendor_name=v;}};
  const pmSave=async()=>{
    // ① 업체·배분(가격 없음)
    const rows=pm.rows.map(r=>({profile_id:r.profile_id||0,vendor_code:r.vendor_code||'',supply_gubun:r.supply_gubun||'2',
      lme_flag:r.lme_flag?1:0,apply_from:r.apply_from||null,apply_to:r.apply_to||null,is_active:r.is_active?1:0,is_internal:0,
      alloc_ratio:(r.is_active&&r.alloc_ratio!==''&&r.alloc_ratio!=null)?Math.round(parseFloat(r.alloc_ratio)):null,   // ★배분%=정수
      buy_price:null,sagub_price:null,_delete:!!r._delete}));
    const pf=v=>(v!==''&&v!=null)?parseFloat(v):null;
    const activeVc=pm.rows.filter(r=>!r._delete&&r.vendor_code).map(r=>r.vendor_code);
    // ② ASSY 매입단가 = 업체별만(공통행 없음). vendor=지정 항상.  (★사급 부품가는 이 모달에서 제거 — 품목단가 관리에서)
    const arows=[];pm.subs.forEach(s=>activeVc.forEach(vc=>{const k=OK(vc,s.sub_item);if(k in pm.assyV)arows.push({vendor_code:vc,sub_item:s.sub_item,assy_price:pf(pm.assyV[k])});}));
    try{const res=await fetch(`${API}/api/sourcing/profile/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:pm.route.route_id,rows})});
      const j=await res.json();
      if(!j.ok){const hint=j.gate==='ALLOC'?'유효기간 겹치는 활성 업체 배분합=100% 확인':(j.gate==='NOT_APPROVED'?'미승인 후보는 업체 지정 불가(개발 승인 필요)':'저장 거부');
        pm.msg='❌ 저장 실패 — '+hint+(j.errors?': '+j.errors.join(' / '):(j.msg?': '+j.msg:''));draw();return;}
      let amsg='';
      if(pm.subs.length){const ar=await fetch(`${API}/api/sourcing/sub_price/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:pm.route.route_id,rows:arows})});
        const aj=await ar.json();if(aj&&aj.ok)amsg+=` · ASSY ${aj.upsert||0}반영/${aj.del||0}삭제`;}
      pm.msg=`✅ 저장 완료 (업체 추가 ${j.ins||0} · 수정 ${j.upd||0} · 삭제 ${j.del||0}${amsg})`;await pmOpen(pm.route);return;}
    catch(e){pm.msg='❌ 저장 실패: '+e;draw();}};
  const vendorModal=()=>{if(!pm)return '';const S=pmStat(),ok=S.single||Math.abs(S.sum-100)<0.01;
    // 업체 grid 행(SUB별): 업체·공급구분·배분%(정수)·유효시작·유효종료·ASSY 매입단가(업체별)·활성·삭제  (★사급 없음)
    const vrow=(r,i,s)=>r._delete?'':`
      <tr>
        <td><input class="inp pm-e" list="pm-vdl" autocomplete="off" data-i="${i}" data-f="vendor" value="${esc(r.vendor_name||r.vendor_code||'')}" placeholder="업체명/코드" style="width:150px;min-width:0">${r.vendor_code?`<div style="font-size:10px;color:#8aa0bd">${esc(r.vendor_code)}</div>`:''}</td>
        <td><select class="pm-e" data-i="${i}" data-f="supply_gubun">${SG_OPTS.map(([v,l])=>`<option value="${v}"${r.supply_gubun===v?' selected':''}>${l}</option>`).join('')}</select></td>
        <td class="num"><input class="inp pm-e num" type="number" step="1" min="0" max="100" data-i="${i}" data-f="alloc_ratio" value="${r.alloc_ratio==null?'':r.alloc_ratio}" placeholder="—" style="width:72px;min-width:0" title="공급능력 기준 배분%(정수)"></td>
        <td><input class="inp pm-e" type="date" data-i="${i}" data-f="apply_from" value="${esc(r.apply_from||'')}" style="width:154px;min-width:150px"></td>
        <td><input class="inp pm-e" type="date" data-i="${i}" data-f="apply_to" value="${esc(r.apply_to||'')}" title="비우면 무기한" style="width:154px;min-width:150px"></td>
        <td class="num" style="background:#eef5ff">${r.vendor_code?`<input class="inp pm-assyv num" data-vc="${esc(r.vendor_code)}" data-si="${esc(s.sub_item)}" type="number" step="1" value="${pm.assyV[OK(r.vendor_code,s.sub_item)]==null?'':pm.assyV[OK(r.vendor_code,s.sub_item)]}" placeholder="업체별" style="width:110px;min-width:0" ${canW?'':'disabled'} title="이 업체의 ASSY 조립 매입단가">`:`<span style="font-size:10px;color:#aab">업체지정후</span>`}</td>
        <td class="center"><input type="checkbox" class="pm-e" data-i="${i}" data-f="is_active"${r.is_active?' checked':''}></td>
        <td class="center"><button class="btn ghost pm-del" data-i="${i}" title="삭제" style="padding:0 6px;color:#c0392b">✖</button></td>
      </tr>`;
    // 외주 SUB 블록: [업체 grid: 업체·배분%·유효·ASSY(업체별)·활성·삭제]  (★사급 부품가 없음)
    const subBlocks=pm.subs.map(s=>{
      const gridHead=`<th>업체</th><th>공급구분</th><th class="num">배분%<br><span style="font-weight:400;font-size:10px">(정수)</span></th><th>유효시작</th><th>유효종료</th><th class="num" style="background:#eef5ff">ASSY 매입단가<br><span style="font-weight:400;font-size:10px">(업체별)</span></th><th class="center">활성</th><th class="center">삭제</th>`;
      const gridBody=pm.loading?`<tr><td colspan="8">${spinRow(1)}</td></tr>`:pm.rows.map((r,i)=>vrow(r,i,s)).join('');
      return `<div style="margin-top:10px;border:1px solid #e6d29a;border-radius:8px;overflow:hidden">
        <div style="padding:6px 10px;background:#fdf7e6;font-size:12px;font-weight:700;color:#8a6d1c">🧩 외주 SUB · <b>${esc(s.sub_item)}</b> <span style="font-weight:400;color:#556">${esc(s.sub_name||'')}</span> <span style="font-size:10px;color:#b8860b">${esc(s.gubun||'')}</span></div>
        <div style="padding:6px 10px">
          <div style="font-size:11px;font-weight:600;color:#334;margin:0 0 2px">업체 · 배분%(정수) · ASSY 매입단가(업체별)</div>
          <div style="overflow-x:auto"><table class="tbl" style="font-size:12px;margin:0"><thead><tr>${gridHead}</tr></thead><tbody>${gridBody}</tbody></table></div>
          <div style="text-align:right;margin-top:4px">${canW?`<button class="btn ghost pm-add" style="font-size:11px;padding:1px 10px">➕ 업체추가</button>`:''}</div>
        </div></div>`;}).join('');
    // 외주 SUB 없으면: 업체·배분만(가격 대상 없음)
    const noSubTable=!pm.subs.length?`<div style="margin-top:10px;border:1px solid #e6d29a;border-radius:8px;padding:8px 10px">
        <div style="font-size:12px;color:#5a6b82;margin-bottom:4px">외주 SUB 없음(단품·제작만) — ASSY 대상 없음. 단품 매입=매입 마스터 자동. 업체·배분만 지정.</div>
        <div style="overflow-x:auto"><table class="tbl" style="font-size:12px;margin:0"><thead><tr><th>업체</th><th>공급구분</th><th class="num">배분%<br><span style="font-weight:400;font-size:10px">(정수)</span></th><th>유효시작</th><th>유효종료</th><th class="center">활성</th><th class="center">삭제</th></tr></thead>
        <tbody>${pm.rows.map((r,i)=>r._delete?'':`<tr>
          <td><input class="inp pm-e" list="pm-vdl" autocomplete="off" data-i="${i}" data-f="vendor" value="${esc(r.vendor_name||r.vendor_code||'')}" placeholder="업체명/코드" style="width:150px;min-width:0"></td>
          <td><select class="pm-e" data-i="${i}" data-f="supply_gubun">${SG_OPTS.map(([v,l])=>`<option value="${v}"${r.supply_gubun===v?' selected':''}>${l}</option>`).join('')}</select></td>
          <td class="num"><input class="inp pm-e num" type="number" step="1" min="0" max="100" data-i="${i}" data-f="alloc_ratio" value="${r.alloc_ratio==null?'':r.alloc_ratio}" placeholder="—" style="width:72px;min-width:0"></td>
          <td><input class="inp pm-e" type="date" data-i="${i}" data-f="apply_from" value="${esc(r.apply_from||'')}" style="width:154px;min-width:150px"></td>
          <td><input class="inp pm-e" type="date" data-i="${i}" data-f="apply_to" value="${esc(r.apply_to||'')}" style="width:154px;min-width:150px"></td>
          <td class="center"><input type="checkbox" class="pm-e" data-i="${i}" data-f="is_active"${r.is_active?' checked':''}></td>
          <td class="center"><button class="btn ghost pm-del" data-i="${i}" style="padding:0 6px;color:#c0392b">✖</button></td></tr>`).join('')}</tbody></table></div>
        <div style="text-align:right;margin-top:4px">${canW?`<button class="btn ghost pm-add" style="font-size:11px;padding:1px 10px">➕ 업체추가</button>`:''}</div></div>`:'';
    // 단품 매입품(레벨1 직속 매입) = 입력 없음·읽기전용
    const directBlock=pm.direct.length?`<div style="margin-top:12px">
        <div style="font-size:12px;font-weight:700;color:#334;margin-bottom:3px">📦 단품 매입품 <span style="font-weight:400;font-size:11px;color:#8aa0bd">(레벨1 직속 매입 · 입력 없음 · 매입 마스터 자동조회·읽기전용)</span></div>
        <table class="tbl" style="font-size:12px"><thead><tr><th>품번</th><th>품명</th><th>구분</th></tr></thead>
        <tbody>${pm.direct.map(d=>`<tr><td><b>${esc(d.item_code)}</b></td><td class="bcap" style="max-width:300px;overflow:hidden;text-overflow:ellipsis" title="${esc(d.item_name)}">${esc(d.item_name)}</td><td style="color:#1c47a0">${esc(d.gubun||'매입')}</td></tr>`).join('')}</tbody></table></div>`:'';
    return `<div class="wr-modal" style="position:fixed;inset:0;z-index:120;background:rgba(20,30,50,.42);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
      <div style="background:#fff;border-radius:10px;min-width:820px;max-width:96vw;box-shadow:0 8px 40px rgba(0,0,0,.25)">
       <div style="padding:12px 16px;border-bottom:1px solid #e2e8f2;display:flex;align-items:center;gap:10px">
         <span style="font-weight:700;font-size:15px;color:#1c3a6e">🏭 업체·단가 지정 <span style="font-size:11px;font-weight:400;color:#8aa0bd">(ASSY=업체별 · 업체=배분%)</span></span>
         ${badge(pm.route)} <b style="color:#1c3a6e">${esc(pm.route.route_name||'')}</b>
         <span style="color:var(--muted);font-size:12px">${esc(sel)} ${esc(selNm)}</span>
         <div class="spacer" style="flex:1"></div>
         <button class="btn ghost" id="pm-x" style="font-size:16px">✖</button></div>
       <div style="padding:8px 16px 4px;font-size:12px;color:#8a6d1c;background:#fdf7e6;border-bottom:1px solid #f0e6c8">
         ⚠️ <b>후보/계획 단가(정산 아님)</b>: ① <b>ASSY 매입단가</b>=외주 SUB×<b>업체별</b>(각 업체 조립가, 공통 없음) ② <b>단품 매입품</b>=매입 마스터 자동(읽기전용). 업체는 <b>배분%(공급능력·정수)</b>. 사급 부품가는 <b>[품목단가 관리]</b>에서(이 모달에 없음). 정산 매입/판매 단가(마감때만 수정)는 변경되지 않습니다.</div>
       <div style="padding:6px 16px;font-size:12px;color:${ok?'#1c7c3a':'#c0392b'};font-weight:600">배분: ${S.single?`활성 ${S.n}개(단일 → 100% 자동)`:`활성 ${S.n}개 배분합 ${S.sum}% ${ok?'✓':'(=100 필요)'}`}</div>
       <div style="padding:0 16px 12px;overflow:auto;max-height:66vh">
         ${subBlocks}${noSubTable}
         ${directBlock}
         <datalist id="pm-vdl"></datalist>
       </div>
       <div style="padding:10px 16px;border-top:1px solid #e2e8f2;display:flex;align-items:center;gap:8px">
         ${pm.msg?`<span style="font-size:12px;font-weight:600;color:${pm.msg.startsWith('✅')?'#1c7c3a':'#c0392b'}">${esc(pm.msg)}</span>`:''}
         <div class="spacer" style="flex:1"></div>
         <button class="btn ghost" id="pm-cancel">닫기</button>
         ${canW?`<button class="btn" id="pm-save" style="background:#1c47a0;color:#fff">💾 저장</button>`:''}</div>
      </div></div>`;};
  const wireModal=()=>{if(!pm)return;const g=id=>c.querySelector(id);
    const x=g('#pm-x'),cn=g('#pm-cancel');if(x)x.onclick=pmClose;if(cn)cn.onclick=pmClose;
    c.querySelectorAll('.pm-add').forEach(el=>el.onclick=pmAddRow);   // ★업체추가(SUB별 버튼, 클래스 바인딩)
    const sv=g('#pm-save');if(sv)sv.onclick=pmSave;
    c.querySelectorAll('.pm-del').forEach(el=>el.onclick=()=>pmDelRow(+el.dataset.i));
    c.querySelectorAll('.pm-assyv').forEach(el=>el.onchange=()=>{pm.assyV[OK(el.dataset.vc,el.dataset.si)]=(el.value===''?null:el.value);});   // ASSY 업체별 (★사급 핸들러 제거)
    c.querySelectorAll('.pm-e').forEach(el=>{const i=+el.dataset.i,f=el.dataset.f;
      if(f==='vendor'){el.oninput=e=>pmVendorAC(e.target.value);el.onchange=e=>{pmResolveVendor(i,e.target.value);draw();};}
      else if(f==='is_active'){el.onchange=()=>{pm.rows[i].is_active=el.checked?1:0;draw();};}
      else if(f==='supply_gubun'){el.onchange=()=>{pm.rows[i].supply_gubun=el.value;};}
      else if(f==='alloc_ratio'){el.onchange=()=>{pm.rows[i].alloc_ratio=(el.value===''?null:Math.round(parseFloat(el.value)||0));draw();};}   // ★정수만
      else{el.onchange=()=>{pm.rows[i][f]=(el.value===''?'':el.value);};}});};
  // ===== R01(현행) 발주업체·단가 모달 (자동발주 근거) — ★품목당 다중업체+배분%(합100). 현행 매입처 자동시드 + 업체별 마스터단가(읽기전용) =====
  let om=null, omAcT=null;   // om={item,asof,rows[],msg,loading,saving}
  const omOpen=async(it,rid)=>{rid=+rid||0;om={item:it,route_id:rid,asof:'',rows:[],msg:'',loading:true,saving:false};draw();
    try{const url=rid>0?`${API}/api/sourcing/route_order?item=${encodeURIComponent(it)}&route_id=${rid}`:`${API}/api/sourcing/current_order?item=${encodeURIComponent(it)}`;
      const r=await fetch(url);const j=await r.json();
      om.asof=j.asof||'';om.rows=(j.rows||[]).map(x=>({item_code:x.item_code,item_name:x.item_name||'',spec:x.spec||'',qty:x.qty,
        make_label:x.make_label||'',sagub:!!x.sagub,cur_vendor_code:x.cur_vendor_code||'',cur_vendor_name:x.cur_vendor_name||'',
        item_master_price:x.master_price,has_override:!!x.has_override,
        vendors:(x.vendors||[{vendor_code:x.cur_vendor_code,vendor_name:x.cur_vendor_name,alloc_ratio:100,master_price:x.master_price}])
          .map(v=>({code:v.vendor_code||'',name:v.vendor_name||'',ratio:(v.alloc_ratio==null?null:+v.alloc_ratio),price:v.master_price,price_reg:(v.price_reg!==false)}))}));
    }catch(e){om.msg='발주 근거 로드 실패: '+e;}
    om.loading=false;draw();};
  const omClose=()=>{om=null;draw();};
  const omVendorAC=(t)=>{clearTimeout(omAcT);omAcT=setTimeout(async()=>{
    try{const r=await fetch(`${API}/api/sourcing/vendors?q=${encodeURIComponent(t)}`);const vs=(await r.json()).rows||[];
      om._vlist=vs;const dl=c.querySelector('#om-vdl');if(dl)dl.innerHTML=vs.map(v=>`<option value="${esc(v.name)}">${esc(v.name)} (${esc(v.code)})${v.role?' · '+esc(v.role):''}</option>`).join('');}catch(e){}},180);};
  const omPrice=async(i,vi)=>{const vd=om.rows[i].vendors[vi];if(!vd.code){vd.price=null;vd.price_reg=undefined;return;}
    vd.price=undefined;vd.price_reg=undefined;draw();   // 조회중
    try{const r=await fetch(`${API}/api/sourcing/item_vendor_price?item=${encodeURIComponent(om.rows[i].item_code)}&vendor=${encodeURIComponent(vd.code)}`);const pj=await r.json();
      vd.price=pj.reg?pj.cost:null;vd.price_reg=!!pj.reg;}catch(e){vd.price=null;vd.price_reg=false;}draw();};
  const omResolve=(i,vi,val)=>{const v=val.trim();const list=om._vlist||[];const hit=list.find(x=>x.name===v)||list.find(x=>x.code===v)||list.find(x=>(x.name||'').indexOf(v)>=0);
    const vd=om.rows[i].vendors[vi];
    if(hit){vd.code=hit.code;vd.name=hit.name;}
    else if(!v){vd.code='';vd.name='';vd.price=null;vd.price_reg=undefined;draw();return;}
    else{vd.name=v;vd.code='';vd.price=null;vd.price_reg=undefined;draw();return;}
    omPrice(i,vi);};   // ★선택 업체의 단가 등록여부 조회(미등록=단가미등록·저장차단)
  const omRatio=(i,vi,val)=>{om.rows[i].vendors[vi].ratio=(val===''?null:Math.round(parseFloat(val)||0));draw();};
  const omAdd=(i)=>{om.rows[i].vendors.push({code:'',name:'',ratio:null,price:undefined});draw();};
  const omDelV=(i,vi)=>{const vs=om.rows[i].vendors;vs.splice(vi,1);
    if(!vs.length)vs.push({code:om.rows[i].cur_vendor_code,name:om.rows[i].cur_vendor_name,ratio:100,price:om.rows[i].item_master_price});
    if(vs.length===1)vs[0].ratio=100;draw();};
  const omSave=async()=>{
    // ★R01=current_order/vendor(order_vendor) · R02+=route_order/vendor(sourcing_profile route스코프). R02는 시드포함 전 지정행 확정(사용자 지정=고정).
    const isR02=(+om.route_id>0);
    om.saving=true;om.msg='⏳ 단가 확인 중…';draw();
    const targets=[];
    for(let i=0;i<om.rows.length;i++){const r=om.rows[i];const vs=r.vendors.filter(v=>v.code);
      if(isR02){if(!vs.length && !r.has_override)continue;}   // R02: 업체 있으면(R01시드 포함) 확정 저장 / 빈칸이면서 기지정만(=지정해제) 저장
      else{const isDefault=(vs.length===1 && vs[0].code===r.cur_vendor_code);if(isDefault && !r.has_override)continue;}
      targets.push(i);
      for(let vi=0;vi<r.vendors.length;vi++){const v=r.vendors[vi];if(v.code && v.price_reg===undefined){await omPrice(i,vi);}}}
    // 검증: ★단가미등록 차단(경고) + 다중업체 배분%합100
    for(const i of targets){const r=om.rows[i];const vs=r.vendors.filter(v=>v.code);
      const unreg=vs.filter(v=>v.price_reg===false);
      if(unreg.length){om.saving=false;om.msg=`⚠ 저장 불가 — [${r.item_code} ${r.item_name}]의 업체 「${unreg.map(v=>v.name||v.code).join(', ')}」는 매입단가가 등록되지 않았습니다. 단가 등록 후 배정하세요.`;draw();return;}
      if(vs.length>=2){if(vs.some(v=>v.ratio==null)){om.saving=false;om.msg=`⚠ 저장 불가 — [${r.item_code}] 다중업체는 모든 업체에 배분% 입력 필요`;draw();return;}
        const s=vs.reduce((a,v)=>a+(+v.ratio||0),0);if(Math.abs(s-100)>0.01){om.saving=false;om.msg=`⚠ 저장 불가 — [${r.item_code}] 배분% 합이 ${s}% (100% 필요)`;draw();return;}}}
    if(!targets.length){om.saving=false;om.msg='변경사항 없음';draw();return;}
    om.msg='';draw();let cnt=0;
    try{for(const i of targets){const r=om.rows[i];const vs=r.vendors.filter(v=>v.code);
        let allocations;
        if(isR02){allocations=vs.map(v=>({vendor_code:v.code,alloc_ratio:v.ratio}));}                       // R02: 지정행(시드포함) 확정 · 빈칸=지정해제
        else{const isDefault=(vs.length===1 && vs[0].code===r.cur_vendor_code);allocations=isDefault?[]:vs.map(v=>({vendor_code:v.code,alloc_ratio:v.ratio}));}   // R01: default=override 해제
        const url=isR02?`${API}/api/sourcing/route_order/vendor`:`${API}/api/sourcing/current_order/vendor`;
        const body=isR02?{route_id:+om.route_id,item_code:r.item_code,allocations}:{item_code:r.item_code,allocations};
        const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const jj=await res.json();if(!res.ok||!jj.ok){om.saving=false;om.msg=`⚠ 저장 불가 — [${r.item_code}] ${jj.detail||'저장실패'}`;draw();return;}cnt++;}
      await omOpen(om.item,om.route_id);om.msg=`✅ 발주업체·배분 저장 (${cnt}건)`;draw();
    }catch(e){om.saving=false;om.msg='❌ 저장 실패: '+e;draw();}};
  const orderModal=()=>{if(!om)return '';
    const isR02=(+om.route_id>0);   // ★R02+ = 대안 조달경로(route_order/sourcing_profile) · R01 = 현행(current_order/order_vendor)
    const _rr=routes.find(x=>x.route_id==om.route_id);
    const rlab=isR02?('R'+String(_rr?_rr.route_no:'').toString().padStart(2,'0')+(_rr&&_rr.route_name?' · '+_rr.route_name:'')):'현행 R01';
    const rowsHtml=om.loading?`<tr><td colspan="4">${spinRow(1)}</td></tr>`:(om.rows.length?om.rows.map((r,i)=>{
      const multi=r.vendors.length>1, sum=r.vendors.reduce((a,v)=>a+(+v.ratio||0),0), bad=multi&&Math.abs(sum-100)>0.01;
      const vhtml=r.vendors.map((v,vi)=>{
        const pcell=(v.price!=null)?`<span style="color:#556">${nfq(v.price)}</span>`
          :(v.code?(v.price_reg===undefined?'<span style="color:#c9d1dc">…</span>':'<span style="color:#c0392b;font-weight:600" title="이 업체의 매입단가가 마스터에 없음 — 단가 등록 후 배정 가능">단가미등록</span>')
                  :'<span style="color:#c9d1dc">-</span>');
        return `<div style="display:flex;align-items:center;gap:5px;margin:1px 0">
          <input class="inp om-e" list="om-vdl" autocomplete="off" data-i="${i}" data-vi="${vi}" value="${esc(v.name||v.code||'')}" placeholder="발주업체" style="width:150px" ${canW?'':'disabled'}>
          ${multi?`<input class="inp om-r" type="number" min="0" max="100" data-i="${i}" data-vi="${vi}" value="${v.ratio==null?'':v.ratio}" placeholder="%" style="width:50px;text-align:right" ${canW?'':'disabled'}><span style="color:#8aa0bd;font-size:11px">%</span>`:''}
          <span style="min-width:78px;text-align:right;background:#f4f6fb;border-radius:3px;padding:0 5px" title="업체별 마스터 매입단가(읽기전용)">${pcell}</span>
          ${(canW&&multi)?`<span class="om-del" data-i="${i}" data-vi="${vi}" style="cursor:pointer;color:#c0392b;font-weight:700" title="업체 삭제">×</span>`:''}</div>`;}).join('');
      return `<tr>
        <td style="white-space:nowrap;vertical-align:top"><b>${esc(r.item_code)}</b> <span style="font-size:10px;color:#8aa0bd">${esc(r.make_label||'')}</span>${r.sagub?' <span style="font-size:10px;color:#7a3ea8;background:#f3ecfb;border-radius:3px;padding:0 4px;font-weight:700" title="사급(우리가 자재 공급)">사급</span>':''}</td>
        <td class="bcap" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;vertical-align:top" title="${esc(r.item_name)}">${esc(r.item_name)}</td>
        <td class="num" style="vertical-align:top">${nfq(r.qty)}</td>
        <td style="vertical-align:top">${vhtml}
          <div style="margin-top:2px;display:flex;align-items:center;gap:8px">
            ${canW?`<button class="btn ghost om-add" data-i="${i}" style="padding:1px 7px;font-size:11px">＋ 업체추가</button>`:''}
            ${multi?`<span style="font-size:11px;font-weight:600;color:${bad?'#c0392b':'#1c7c3a'}">합 ${sum}%${bad?' ⚠':' ✓'}</span>`:(isR02?(r.seeded?'<span style="font-size:10px;color:#b8791f;font-weight:600" title="R01(현행) 매입처에서 자동으로 끌어온 제안값 — 저장하면 이 경로 값으로 확정(고정)">R01 시드(제안·저장 시 확정)</span>':(r.vendors.some(v=>v.code)?'':'<span style="font-size:10px;color:#c0392b;font-weight:600" title="R01에 없는 R02 고유 부품 — 업체를 직접 지정하세요">미지정 — 업체 지정 필요</span>')):(r.has_override?'':`<span style="font-size:10px;color:#8aa0bd">현행 매입처 100%</span>`))}
          </div></td>
      </tr>`;}).join(''):`<tr><td colspan="4" class="empty">현행 발주 대상 품목 없음</td></tr>`);
    return `<div class="wr-modal" style="position:fixed;inset:0;z-index:120;background:rgba(20,30,50,.42);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
      <div style="background:#fff;border-radius:10px;min-width:720px;max-width:96vw;box-shadow:0 8px 40px rgba(0,0,0,.25)">
       <div style="padding:12px 16px;border-bottom:1px solid #e2e8f2;display:flex;align-items:center;gap:10px">
         <span style="font-weight:700;font-size:15px;color:${isR02?'#1c47a0':'#1c7c3a'}">📦 발주업체·배분 <span style="font-size:11px;font-weight:400;color:#8aa0bd">(${esc(rlab)} · ${isR02?'대안 조달경로':'자동발주 근거'})</span></span>
         <b style="color:#1c3a6e">${esc(om.item)}</b><span style="color:var(--muted);font-size:12px">${esc(selNm)} · 기준일 ${esc(om.asof||'')}</span>
         <div class="spacer" style="flex:1"></div>
         <button class="btn ghost" id="om-x" style="font-size:16px">✖</button></div>
       <div style="padding:8px 16px 4px;font-size:12px;color:#1c5b2e;background:#eefaf0;border-bottom:1px solid #cfe9d5">
         ${isR02?`✅ <b>${esc(rlab)} 발주업체·배분</b> — 이 경로의 <b>자기 구조 부품</b>입니다. 매입처는 <b>R01(현행)에서 채울 수 있는 것만 자동 시드(제안·주황)</b>, R01에 없는 R02 고유 부품(새 SUB 등)은 <b>직접 지정</b>하세요. <b>저장하면 이 경로 값으로 확정(고정)</b> — 이후 R01이 바뀌어도 덮어쓰지 않습니다. [＋업체추가]로 분할발주(배분% 합 100). (단가=마스터 읽기전용)`:`✅ <b>자동발주 근거(품목→발주업체→배분%→단가)</b> — 현행 <b>매입처 자동시드</b> + <b>업체별 마스터 매입단가</b>(읽기전용). ★<b>한 부품을 여러 업체로 분할발주</b>: [＋업체추가]로 업체 넣고 <b>배분%</b> 입력(합 100). 자동발주가 소요를 <b>비율대로 업체별 PO 분할</b>합니다. (단가는 마감때만 수정)`}</div>
       <div style="padding:0 16px 12px;overflow:auto;max-height:66vh">
         <table class="tbl" style="font-size:12px;margin-top:8px"><thead><tr><th>품번</th><th>품명</th><th class="num">소요량</th><th>발주업체 · 배분% · 마스터단가<span style="font-weight:400;font-size:10px;color:#8aa0bd">(읽기전용)</span></th></tr></thead>
         <tbody>${rowsHtml}</tbody></table>
         <datalist id="om-vdl"></datalist>
         <div style="font-size:11px;color:#8aa0bd;margin-top:4px">※ 단일업체면 100% 자동. 단가=마스터(PR_M_ITEM_COST) 자동조회·읽기전용.${isR02?' <b style="color:#b8791f">주황=R01 시드(제안)</b> · <b style="color:#c0392b">미지정=직접 지정</b>. 저장 시 이 경로에 확정(고정).':' 안 바꾸면 현행 매입처 그대로.'}</div>
       </div>
       <div style="padding:10px 16px;border-top:1px solid #e2e8f2;display:flex;align-items:center;gap:8px">
         ${om.msg?(om.msg.startsWith('✅')||om.msg.startsWith('⏳')||om.msg==='변경사항 없음'
            ?`<span style="font-size:12px;font-weight:600;color:${om.msg.startsWith('✅')?'#1c7c3a':'#8a94a6'}">${esc(om.msg)}</span>`
            :`<span style="flex:1;font-size:13px;font-weight:700;color:#9a1b1b;background:#fdeaea;border:1px solid #f0c2c2;border-radius:6px;padding:6px 10px">${esc(om.msg)}</span>`):''}
         <div class="spacer" style="flex:1"></div>
         <button class="btn ghost" id="om-cancel">닫기</button>
         ${canW?`<button class="btn" id="om-save" style="background:#1c7c3a;color:#fff" ${om.saving?'disabled':''}>💾 발주업체·배분 저장</button>`:''}</div>
      </div></div>`;};
  const wireOrder=()=>{if(!om)return;const g=id=>c.querySelector(id);
    const x=g('#om-x'),cn=g('#om-cancel');if(x)x.onclick=omClose;if(cn)cn.onclick=omClose;
    const sv=g('#om-save');if(sv)sv.onclick=omSave;
    c.querySelectorAll('.om-e').forEach(el=>{el.oninput=e=>omVendorAC(e.target.value);el.onchange=e=>omResolve(+el.dataset.i,+el.dataset.vi,e.target.value);});
    c.querySelectorAll('.om-r').forEach(el=>{el.onchange=e=>omRatio(+el.dataset.i,+el.dataset.vi,e.target.value);});
    c.querySelectorAll('.om-add').forEach(el=>el.onclick=()=>omAdd(+el.dataset.i));
    c.querySelectorAll('.om-del').forEach(el=>el.onclick=()=>omDelV(+el.dataset.i,+el.dataset.vi));};
  const kindOf=n=>{if((n.nm||'').indexOf('용접봉')>=0)return{t:'용접봉',c:'#8e44ad'};if(n.haskids)return{t:'제작(SUB)',c:'#1c7c3a'};if(String(n.sag)==='1')return{t:'사급',c:'#b8860b'};return{t:'매입/구매',c:'#1c47a0'};};
  // ★선택 경로(R01/R02) 기준 BOM 트리 전환 + 매입처 다중업체·비율
  const gubunKind=g=>{g=(g||'').trim();return g==='제작'?{t:'제작',c:'#1c7c3a'}:(g==='사급'?{t:'사급',c:'#b8860b'}:{t:'매입/구매',c:'#1c47a0'});};
  const buildRouteTree=(item,itemNm,lines)=>{const live=(lines||[]).filter(l=>!l.staged);
    const byP={};live.forEach(l=>{const p=(l.parent_line==null?'root':l.parent_line);(byP[p]=byP[p]||[]).push(l);});
    const rows=[{level:0,code:item,nm:itemNm||'',haskids:true,qty:1}];
    const walk=(key,lvl)=>{(byP[key]||[]).forEach(l=>{const isSub=l.node_kind==='SUB';
      rows.push({level:lvl,code:isSub?(l.sub_item||l.child_item):l.child_item,nm:l.child_name||'',qty:l.qty,haskids:isSub,kind:isSub?null:gubunKind(l.gubun),custnm:l.vendor_name||''});
      if(isSub)walk(l.line_id,lvl+1);});};
    walk('root',1);return rows;};
  const selectRoute=async(r)=>{const rid=r.route_id,isCur=_isCur(r);selRid=isCur?null:rid;
    if(!isCur&&!rtree[rid]){try{const j=await(await fetch(`${API}/api/sourcing/route/detail?route_id=${rid}`)).json();
      rtree[rid]=buildRouteTree(sel,selNm,j.lines||[]);
      const m={};(j.lines||[]).forEach(l=>{if(l.node_kind!=='SUB'&&l.vendor_name)m[String(l.child_item).trim()]=[{name:l.vendor_name,ratio:null}];});rvmap[rid]=m;
      }catch(e){rtree[rid]=[];rvmap[rid]={};}}
    draw();};
  const curTree=()=>selRid==null?tree:(rtree[selRid]||[]);
  const curVmap=()=>selRid==null?(rvmap['_cur']||{}):(rvmap[selRid]||{});
  const selRouteLabel=()=>{if(selRid==null)return 'R01 · 현행';const r=routes.find(x=>x.route_id==selRid);return r?('R'+String(r.route_no).padStart(2,'0')+(r.route_name?' · '+r.route_name:'')):'선택 경로';};
  const vcell=(code,fallback)=>{const vs=curVmap()[String(code).trim()];
    if(vs&&vs.length)return vs.map(v=>`${esc(v.name)}${v.ratio!=null?` <span style="color:#1c47a0;font-size:10px;font-weight:600">${nfq(v.ratio)}%</span>`:''}`).join(' <span style="color:#c9d1dc">/</span> ');
    return esc(fallback||'');};
  const treeTbl=()=>{const T=curTree();if(!T)return '';if(!T.length)return `<div class="empty" style="margin-top:16px">설정된 BOM 구성 없음</div>`;
    return `<table class="tbl" style="font-size:12px"><thead><tr><th style="min-width:280px">레벨·품번</th><th>품명</th><th class="num">수량</th><th>구분</th><th>매입처</th></tr></thead><tbody>${T.map(n=>{const k=n.kind||kindOf(n),root=n.level===0;return `<tr style="${root?'background:#eef5ff;font-weight:700':''}"><td style="white-space:nowrap"><span style="display:inline-block;width:${n.level*18}px"></span>${n.level?'└ ':''}<b>${esc(n.code)}</b></td><td class="bcap" style="max-width:210px;overflow:hidden;text-overflow:ellipsis" title="${esc(n.nm)}">${esc(n.nm)}</td><td class="num">${root?'':nfq(n.qty)}</td><td>${root?'':`<span style="color:${k.c};font-weight:600">${k.t}</span>`}</td><td>${root||n.haskids?'':vcell(n.code,n.custnm)}</td></tr>`;}).join('')}</tbody></table>`;};
  const badge=r=>{const on=r.current_flag;return `<span style="background:${on?'#1c7c3a':'#1c47a0'};color:#fff;border-radius:8px;padding:1px 8px;font-size:11px;font-weight:700">R${String(r.route_no).padStart(2,'0')}${on?' · 현행':''}</span>`;};
  const routeRow=r=>{const ro=r.readonly;
    const isCur=_isCur(r);   // R01(현행)
    const canVend=isCur||(r.approve_flag&&r.route_id>0);   // R01 항상 · R02는 승인+실저장 후보만 매입처 지정
    const canPick=canW&&!ro&&(isCur||r.approve_flag);      // ★택1 활성 지정 가능(승인 후보만)
    const on=ract(r);
    return `<tr style="${r.current_flag?'background:#f0f7f0;':''}${ro?'background:#f4f4f4;opacity:.6;':(!on?'opacity:.6;':'')}">
      <td style="white-space:nowrap">${badge(r)} <b style="color:#1c3a6e">${esc(r.route_name||'')}</b></td>
      <td>${esc(r.gubun||'-')}</td>
      <td style="font-weight:600">${r.vendor_code?esc(r.vendor_name||r.vendor_code):'<span style="color:#aab">-</span>'}</td>
      <td class="center">${r.approve_flag?'<span style="background:#1c7c3a;color:#fff;border-radius:8px;padding:0 7px;font-size:10px">승인</span>':'<span style="background:#999;color:#fff;border-radius:8px;padding:0 7px;font-size:10px" title="개발 승인 전 — 활성 불가">미승인</span>'}</td>
      <td class="center">${canPick?`<label style="cursor:pointer;font-size:11px;color:${on?'#1c47a0':'#8aa0bd'};font-weight:${on?'700':'400'}"><input type="radio" name="sp-active" class="sp-act" data-ri="${r.route_id}"${on?' checked':''} style="vertical-align:middle"> ${on?'활성':'선택'}</label>`:(on?'<span style="color:#1c47a0;font-weight:700">✔ 활성</span>':(ro?'<span style="color:#c0392b;font-size:10px">활성불가</span>':'<span style="color:#c9d1dc">비활성</span>'))}</td>
      <td class="center">${canVend?`<button class="btn ghost sp-editvend" data-ri="${isCur?0:r.route_id}" title="${isCur?'현행 R01 발주업체·배분 수정':'이 경로(R02) 발주업체 지정 — R01 매입처 자동 시드(채울 수 있는 것만)'}" style="padding:1px 8px;font-size:11px;color:${isCur?'#1c7c3a':'#1c47a0'};border-color:${isCur?'#9fd0ac':'#9fc0e0'}">✎ 매입처 수정</button>`:'<span style="color:#c9d1dc;font-size:10px">승인 후 지정</span>'}</td>
    </tr>`;};
  const routePanel=()=>{const appr=routes.filter(r=>r.approve_flag).length,un=routes.length-appr;
    const act=routes.find(r=>ract(r));
    const actLab=act?('R'+String(act.route_no).padStart(2,'0')+(act.route_name?' · '+act.route_name:'')+(_isCur(act)?' (현행)':'')):'미지정';
    return `<div style="font-weight:700;color:#334;margin:2px 0 4px">🧬 조달경로 후보 <span style="font-size:11px;color:#8aa0bd;font-weight:400">(★운영 경로 택1 — 활성 1개=항상 100% · 승인 후보만 · 저장 <code>nx.route_alloc</code>)</span>
      <label style="float:right;font-size:12px;font-weight:400;color:#5a6b82"><input type="checkbox" id="sp-unappr" ${showUnappr?'checked':''}> 미승인 보기</label></div>
      <div style="margin:0 0 6px;font-size:12px;color:#1c47a0;font-weight:600">운영 활성 경로: <b>${esc(actLab)}</b> <span style="font-weight:400;color:#8aa0bd">— 하나만 활성(항상 100%). [저장]으로 확정 후 [✎ 매입처 수정]에서 부품별 매입처 지정.</span>${allocErrs.length?` · <span style="color:#c0392b">검증: ${esc(allocErrs.join(' / '))}</span>`:''}</div>
      <table class="tbl" style="font-size:12px;margin:0"><thead><tr><th>경로</th><th>구분</th><th>공급처</th><th class="center">승인</th><th class="center">활성(택1)</th><th class="center">매입처</th></tr></thead>
      <tbody>${routes.length?routes.map(routeRow).join(''):`<tr><td colspan="6" class="empty">조달경로 후보 없음${!showUnappr?' — [미승인 보기]로 개발 진행중 후보 확인':' (개발 › 조달경로 통합검토에서 생성·승인)'}</td></tr>`}</tbody></table>
      <div class="page-sub" style="color:#8aa0bd;margin-top:3px">승인 ${appr}건${un?` · 미승인 ${un}건(회색·활성 불가)`:''}. R01=현행(실사용 BOM 기준선·자동승인). R02+는 [개발 › 조달경로 통합검토]에서 승인해야 활성 지정 가능. 매입처: R02는 R01에서 <b>채울 수 있는 것만 시드(제안)</b> + 고유 부품 직접 지정.</div>`;};
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">🧭 조달 프로파일 <span style="font-size:12px;color:var(--muted);font-weight:400">승인 조달경로 후보(R01 현행·R02…)에 활성·배분% 배정</span></div>
     <div class="page-sub">품번 검색 → <b>실제 설정된 BOM</b>(참고) + <b>조달경로 후보 배정</b>. 후보(R01 vs R02…)마다 <b>활성·배분%</b>(활성 후보 합 100%) 지정. 저장 <code>nx.route_alloc</code></div>
     <div style="display:flex;gap:14px;align-items:flex-start">
      <div style="flex:0 0 290px">
       <div class="toolbar"><input class="inp" id="sp-q" list="sp-dl" autocomplete="off" value="${esc(q)}" placeholder="품번/품명 (예: 3402)" style="width:180px;min-width:0"><datalist id="sp-dl"></datalist><button class="btn" id="sp-search">🔍</button></div>
       <div class="grid-wrap" style="max-height:calc(100vh - 240px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" style="font-size:12px"><thead><tr><th>품번</th><th>품명</th></tr></thead>
        <tbody>${searching?spinRow(2):(slist.length?slist.map(s=>`<tr class="sp-row${sel===s.item?' sel':''}" data-i="${esc(s.item)}" style="cursor:pointer"><td><b>${esc(s.item)}</b></td><td class="bcap" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(s.name||'')}</td></tr>`).join(''):`<tr><td colspan="2" class="empty">품번 검색</td></tr>`)}</tbody></table>
       </div>
      </div>
      <div style="flex:1;min-width:0">
       ${sel?`
        <div class="toolbar"><span style="font-weight:700;color:#1c47a0;font-size:16px">${esc(sel)}</span> <span style="color:var(--muted)">${esc(selNm)}</span>
          <label class="tl" style="margin-left:10px">기준일</label><input class="inp" type="date" id="sp-ref" value="${ref}" style="width:130px">
          <div class="spacer"></div>
          ${canW?`<button class="btn" id="sp-save" style="background:#1c47a0;color:#fff">💾 저장</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>`}</div>
        ${tload?`<div class="grid-wrap" style="padding:20px">${spinRow(1)}</div>`:`<div style="overflow:auto;max-height:calc(100vh - 205px)">
          <div style="font-weight:700;color:#334;margin:2px 0 4px">📦 실제 설정된 BOM 구성 <span style="font-size:12px;font-weight:600;color:#1c47a0">— ${esc(selRouteLabel())}</span> <span style="font-size:11px;color:#8aa0bd;font-weight:400">(아래 경로 R01/R02 행을 클릭하면 그 경로 구성으로 전환 · 매입처=업체·비율)</span></div>
          <div style="overflow-x:auto">${treeTbl()}</div>
          <div style="height:12px"></div>
          ${routePanel()}
          <div class="page-sub" style="margin-top:4px;color:#8aa0bd">※ 유효기간 안+활성인 후보만 배분(겹치면 합 100%, 단일이면 100% 자동). 이 배정은 후보(R01 vs R02…) 간 계층 — 후보 내부 업체분배는 [개발 › 조달경로 통합검토]에서.</div></div>`}`
       :`<div class="empty" style="margin-top:40px">좌측에서 품번을 선택하세요. (예: 3402)</div>`}
      </div>
     </div>
     ${msg?`<div class="page-sub" style="color:#1c7c3a">${esc(msg)}</div>`:''}
     ${vendorModal()}
     ${orderModal()}
     <style>.sp-row.sel{background:#e8f0ff}.sp-row:hover{background:#eef4ff}</style>`;
    const g=id=>c.querySelector(id);
    g('#sp-search').onclick=()=>{q=g('#sp-q').value;search();};
    g('#sp-q').oninput=e=>ac(e.target.value);
    g('#sp-q').onkeyup=e=>{if(e.key==='Enter'){q=e.target.value;search(true);}};
    g('#sp-q').onchange=e=>{const v=e.target.value.trim();if(v&&slist.some(s=>s.item===v))open(v);};
    c.querySelectorAll('.sp-row').forEach(el=>el.onclick=()=>open(el.dataset.i));
    const sv=g('#sp-save');if(sv)sv.onclick=save;
    const rf=g('#sp-ref');if(rf)rf.onchange=()=>{ref=rf.value;draw();};
    const un=g('#sp-unappr');if(un)un.onchange=async()=>{showUnappr=un.checked;await loadAlloc();draw();};
    c.querySelectorAll('.sp-act').forEach(el=>el.onchange=()=>setActive(el.dataset.ri));   // ★택1 라디오
    c.querySelectorAll('.sp-editvend').forEach(el=>el.onclick=()=>{if(sel)omOpen(sel,+el.dataset.ri||0);});   // R01=0(current_order)·R02=route_id(route_order)
    wireModal();
    wireOrder();
    fillDL();
  };
  const init=async()=>{q='';await search();if(slist.length)open(slist[0].item);};
  init();
};

/* ===== 협력사견적: 견적(원소재비/가공비 분리) vs 현재 입고가 · 사급가 변경 시 판가 재계산 ===== */
SCREEN.coopquote=(host)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,vendor:'',q:'',vendors:[],loading:false,form:null,sel:new Set(),recalc:null,msg:'',filterMode:'active',detail:null,bomedit:null,workMode:false,worklist:[],workBy:{},workDone:0,workLoading:false,workType:''};
  const loadParts=async(idx)=>{const r=st.rows[idx];if(!r)return;
    st.detail={assy:r.assy_code,vendor:r.vendor,rows:[],loading:true};render();
    try{const res=await fetch(`${API}/api/coopquote/parts?assy=${encodeURIComponent(r.assy_code)}&vendor=${encodeURIComponent(r.vendor)}`);
      const j=await res.json();st.detail.rows=j.rows||[];}catch(e){st.detail.rows=[];}
    st.detail.loading=false;render();};
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const won2=v=>(v==null||v==='')?'-':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const nf=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ed=()=>(typeof PERM!=='undefined')?PERM.canEdit('coopquote'):true;
  const loadVendors=async()=>{try{const r=await fetch(`${API}/api/coopquote/vendors`);const j=await r.json();st.vendors=j.rows||[];}catch(e){}};
  const load=async()=>{st.loading=true;if(!st.ym)st.ym=new Date().toISOString().slice(0,7);render();
    try{const r=await fetch(`${API}/api/coopquote/list?vendor=${encodeURIComponent(st.vendor)}&q=${encodeURIComponent(st.q)}&active_only=${st.filterMode==='active'?1:0}&newonly=${st.filterMode==='new'?1:0}&ym=${encodeURIComponent(st.ym||'')}`);
      const j=await r.json();st.rows=j.rows||[];st.cnt=j.count||0;}
    catch(e){st.rows=[];st.cnt=0;}
    st.loading=false;render();};
  // 모달(신규/수정) 실시간 미리보기
  const matOf=f=>Math.round((+f.total_weight||0)*(+f.sagub_price||0));
  const saleOf=f=>matOf(f)+Math.round(+f.proc_cost||0);
  const save=async()=>{
    const f=st.form;if(!f.vendor||!f.assy_code){alert('협력사·품번은 필수입니다.');return;}
    try{const r=await fetch(`${API}/api/coopquote/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'save');st.form=null;st.msg='✔ 견적 저장 완료';await load();}
    catch(e){alert('저장 실패: '+e.message);}};
  const doRecalc=async()=>{
    const rc=st.recalc;const pn=+rc.price_normal||0, ph=+rc.price_high||0;
    if(pn<=0&&ph<=0){alert('일반CU 또는 고강도CU 사급가를 입력하세요.');return;}
    const body={price_normal:pn,price_high:ph,scope:rc.scope};
    if(rc.scope==='vendor')body.vendor=st.vendor;
    if(rc.scope==='ids')body.ids=[...st.sel];
    try{const r=await fetch(`${API}/api/coopquote/recalc`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'recalc');
      const dt=j.detail||{};st.recalc=null;st.sel.clear();
      st.msg=`✔ 재계산 완료 (가공비 유지) → 일반CU ${dt['일반CU']||0}건${pn?'('+nf(pn)+'원/kg)':''} · 고강도CU ${dt['고강도CU']||0}건${ph?'('+nf(ph)+'원/kg)':''}`;await load();}
    catch(e){alert('재계산 실패: '+e.message);}};
  // ===== BOM 견적 편집 모달 (하위부품 전체 한 번에) =====
  const geom=(d,t,L)=>(d&&t&&L)?Math.PI*(d-t)*t*L*8.94/1e6:0;
  const nf4=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const beUw=(r)=>{const be=st.bomedit;if(r.role==='반제품'||r.role==='용접봉')return 0;const e=be.edits[r.code];
    if(e&&(e.diam||e.thick||e.length)){const d=+e.diam||r.coop_diam||r.lg_diam,t=+e.thick||r.coop_thick||r.lg_thick,L=+e.length||r.coop_length||r.lg_length;return geom(d,t,L);}
    return r.unit_weight||0;};
  const beSoyo=()=>{const be=st.bomedit;return (!be||!be.data)?0:be.data.rows.filter(r=>r.role==='제작동관').reduce((s,r)=>s+beUw(r)*r.cum_qty,0);};
  // ★관경별 사급가: 행 입력값 → 저장된 관경별 → 헤더 기본 사급가 순
  const beRowSagub=(r)=>{const be=st.bomedit;const e=be.sagubEdits&&be.sagubEdits[r.code];
    if(e!=null&&e!=='')return +e||0;
    if(r.coop_sagub&&+r.coop_sagub>0)return +r.coop_sagub;
    return +be.sagub||0;};
  const beRowQty=(r)=>{const be=st.bomedit;const e=be.qtyEdits&&be.qtyEdits[r.code];return (e!=null&&e!=='')?(+e||0):(r.cum_qty||0);};
  // 행 재료비: 제작동관=소요중량×사급가(파생) · 그외=직접입력(matEdits) 또는 백엔드 mat_now
  const beRowMat=(r)=>{const be=st.bomedit;
    if(r.role==='제작동관')return Math.round(beUw(r)*beRowQty(r)*beRowSagub(r));
    const e=be.matEdits&&be.matEdits[r.code];return (e!=null&&e!=='')?Math.round(+e||0):Math.round(r.mat_now||0);};
  const beRowGag=(r)=>(r.role==='제작동관'?beRowGagong(r):0);   // 사급/용접봉=가공 없음
  const beRowTot=(r)=>beRowMat(r)+beRowGag(r);                  // 합계=재료비+가공비 (사급=재료비)
  const beRaw=()=>{const be=st.bomedit;return (!be||!be.data)?0:be.data.rows.filter(r=>r.role==='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowMat(r),0);};
  const beWeld=()=>{const be=st.bomedit;return (!be||!be.data)?0:Math.round(be.data.total_weld_cost||0);};
  const beProcCnt=(r,op)=>{const pe=st.bomedit.procEdits[r.code];if(pe&&pe[op]!=null&&pe[op]!=='')return +pe[op]||0;return (r.procs&&r.procs[op])||0;};
  const beRowGagong=(r)=>{const be=st.bomedit;if(r.role!=='제작동관'||!be.data)return 0;const rate=be.data.rate||{};const lab=be.data.labor_rate||6300;let t=0;
    (be.data.proc_ops||[]).forEach(op=>{const c=beProcCnt(r,op);const dv=rate[op];if(c&&dv)t+=(lab/dv)*c;});return Math.round(t*(r.cum_qty||0));};
  const newBomEdit=()=>{st.bomedit={isNew:true,loading:false,vendor:st.vendor||'',grade:'일반CU',sagub:20000,proc:0,ym:new Date().toISOString().slice(0,7),edits:{},procEdits:{},sagubEdits:{},matEdits:{},qtyEdits:{},data:null,assy:''};render();};
  const loadBomInto=async(item,salePrefill)=>{const be=st.bomedit;if(!be||!item.trim())return;
    be.assy=item.trim();be.loading=true;be.edits={};render();
    try{const res=await fetch(`${API}/api/coopquote/bom-form?item=${encodeURIComponent(item.trim())}&vendor=${encodeURIComponent(be.vendor||'')}&ym=${encodeURIComponent(st.ym||'')}`);const j=await res.json();be.data=j;
      if(j.cur_sagub)be.sagub=j.cur_sagub;   // 기본사급가=최신 원소재 사급가(종전 견적사급가 아님)
      be.asm=j.assembly?JSON.parse(JSON.stringify(j.assembly)):null;   // 서브조립 편집용
      if(be.asm){be.asm.gagong=Math.round((be.asm.total||0)-(be.asm.mgmt||0)-(be.asm.transport||0)-(be.asm.profit||0));}  // 합계=가공+관리+운반+이윤 정합(용접봉재료 포함)
      // 신규(기존행 없음)만 공정기반 가공비로 프리필. 기존 견적은 저장 가공비 유지(조회창 일치)
      if(!be.rowvals){const procAuto=Math.round(j.total_proc_cost||0)+Math.round(j.total_weld_cost||0);
        be.proc=procAuto>0?procAuto:0;}
    }catch(e){be.data=null;}
    be.loading=false;render();};
  const openBomEdit=async(idx)=>{const r=st.rows[idx];if(!r)return;
    st.bomedit={isNew:false,viewMode:true,loading:true,vendor:r.vendor,grade:r.grade||'일반CU',sagub:r.sagub_price||20000,proc:Math.round(r.proc_cost||0),ym:new Date().toISOString().slice(0,7),edits:{},procEdits:{},sagubEdits:{},matEdits:{},qtyEdits:{},data:null,assy:r.assy_code,
      rowvals:{mat_cost:r.mat_cost||0,mat_raw:r.mat_raw||0,mat_weld:r.mat_weld||0,mat_part:r.mat_part||0,proc_cost:r.proc_cost||0,sale:r.sale_price||0}};render();
    await loadBomInto(r.assy_code, r.sale_price||0);};
  // 작업목록(직원입력)
  const loadWork=async()=>{st.workLoading=true;render();
    try{const r=await fetch(`${API}/api/coopquote/worklist?wtype=${encodeURIComponent(st.workType)}`);const j=await r.json();st.worklist=j.rows||[];st.workBy=j.by_type||{};st.workDone=j.resolved||0;}
    catch(e){st.worklist=[];}
    st.workLoading=false;render();};
  const openWork=async(assy,vendor)=>{if(!assy)return;
    st.bomedit={isNew:false,loading:true,vendor:(vendor||st.vendor||'').trim(),grade:'일반CU',sagub:20000,proc:0,ym:new Date().toISOString().slice(0,7),edits:{},procEdits:{},sagubEdits:{},matEdits:{},qtyEdits:{},data:null,assy:assy,rowvals:null,fromWork:true};render();
    await loadBomInto(assy,null);};
  const saveBomEdit=async()=>{const be=st.bomedit;if(!be||!be.data)return;
    const specs=be.data.rows.filter(r=>r.role==='제작동관').map(r=>{const e=be.edits[r.code]||{};
      return {code:r.code,diam:(+e.diam||r.coop_diam||r.lg_diam),thick:(+e.thick||r.coop_thick||r.lg_thick),length:(+e.length||r.coop_length||r.lg_length),sagub:beRowSagub(r)};})
      .filter(s=>s.diam&&s.thick&&s.length);
    const baseMat=be.rowvals?Math.max(0,(be.rowvals.mat_cost||0)-(be.rowvals.mat_raw||0)):(be.data.rows.filter(r=>r.role!=='제작동관'&&r.role!=='반제품'&&r.pur_price).reduce((s,r)=>s+Math.round(r.pur_price*r.cum_qty),0));
    // 공정 ST(제작동관, 편집반영) + 서브조립 공정/관리/운반/이윤
    const procs=be.data.rows.filter(r=>r.role==='제작동관').map(r=>{const eff={};(be.data.proc_ops||[]).forEach(op=>{const c=beProcCnt(r,op);if(c>0)eff[op]=c;});return {code:r.code,ops:eff};});
    const assembly=be.asm?{procs:be.asm.procs||{},gagong:Math.round(+be.asm.gagong||0),mgmt:Math.round(+be.asm.mgmt||0),transport:Math.round(+be.asm.transport||0),profit:Math.round(+be.asm.profit||0)}:null;
    const body={item:be.data.item,vendor:be.vendor.trim(),grade:be.grade,sagub_price:+be.sagub||0,proc_cost:Math.round(+be.proc||0),base_mat:baseMat,item_name:be.data.name,specs,procs,assembly};
    try{const r=await fetch(`${API}/api/coopquote/bom-save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'save');
      const wasWork=be.fromWork;st.bomedit=null;st.msg=`✔ 견적 저장 · 소요중량 ${nf4(j.total_soyo_weight)}kg · 원소재비 ${nf(j.mat_cost)} · 판가 ${nf(j.sale_price)}`;
      if(wasWork){await loadWork();}else{await load();}}
    catch(e){alert('저장 실패: '+e.message);}};
  const beBadge=(role)=>{const M={'제작동관':['#e8f3ec','#1c7c3a'],'사급':['#eef2f7','#5a6a80'],'용접봉':['#fff3e0','#b8791f'],'매입부품':['#f0ecfa','#6a3fb0'],'반제품':['#e8eef7','#1c47a0']};
    const key=(role&&role.indexOf('제작(')===0)?'제작동관':role;const c=M[key]||['#eee','#555'];return `<span style="font-size:10px;padding:1px 5px;border-radius:8px;background:${c[0]};color:${c[1]};white-space:nowrap">${role}</span>`;};
  const render=()=>{
    const canEd=ed();
    const modal=st.form, rc=st.recalc, f=st.form||{}, be=st.bomedit;
    const diffCol=r=>{if(r.diff==null)return '<span style="color:#c9d1dc">-</span>';
      const c=r.diff>0?'#c0392b':(r.diff<0?'#1c6ec2':'#5a6a80');const s=r.diff>0?'▲':(r.diff<0?'▼':'');
      return `<b style="color:${c}">${s}${nf(Math.abs(r.diff))}</b>`;};
    {const _pg=host.querySelector('#cq-grid'); if(_pg) st._scroll=_pg.scrollTop;}  // 재렌더 전 리스트 스크롤 보존
    host.innerHTML=`
     <div class="page-title">💱 협력사견적관리 <span style="font-size:12px;color:var(--muted);font-weight:400">하위부품 bottom-up 견적 vs 실입고가 · nx.coop_quote</span></div>
     <div class="page-sub">「협력 업체 견적 정리」 기반 <b>bottom-up</b>. <b style="color:#1c6ec2">재료비 = Σ하위부품(원소재·용접봉·부속품)</b>, <b style="color:#1c7c3a">가공비 = 판가−재료비</b>, <b>재료비율 = 재료비/판가</b>.
       품번 행을 <b>클릭</b>하면 하위부품 3분류 상세가 열립니다. 입고가 = <b>실제 납품 거래가</b>(<code>PU_T_STOCK_MAINT</code>, 라이브) 종전(작년12월)·현재(최근). 🚚 토글=현재 납품품목만.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">협력사</label><select class="sel" id="cq-vendor"><option value="">전체</option>${st.vendors.map(v=>`<option value="${esc(v.vendor)}" ${st.vendor===v.vendor?'selected':''}>${esc(v.vendor)} (${v.n})</option>`).join('')}</select>
       <input class="inp" id="cq-q" value="${esc(st.q)}" placeholder="품번/품명 검색" style="width:170px">
       <span style="display:inline-flex;align-items:center;gap:5px;background:#fff3d6;border:1px solid #e8c877;border-radius:6px;padding:2px 8px"><label style="color:#8a5a00;font-weight:700;font-size:12px" title="인상후 사급부품 판매단가·원소재 사급가 기준월 — 리스트 전체에 적용">📅 적용월(전체)</label><input class="inp" id="cq-ym" type="month" value="${esc(st.ym||'')}" style="width:130px;font-weight:600"></span>
       <button class="btn" id="cq-go">🔍 조회</button>
       <select class="btn" id="cq-filter" title="목록 필터: 전체 / 최근4개월 납품실적 / 미승인(BOM 자동생성)" style="background:#eef2f7;color:#33507d;font-weight:600">
         <option value="all"${st.filterMode==='all'?' selected':''}>📋 전체</option>
         <option value="active"${st.filterMode==='active'?' selected':''}>🚚 현재 납품품목</option>
         <option value="new"${st.filterMode==='new'?' selected':''}>🆕 미승인 견적</option>
         <option value="fix"${st.filterMode==='fix'?' selected':''}>⚠️ 보완/확인 필요</option>
       </select>
       ${canEd?`<button class="btn" id="cq-new" style="background:#1c7c3a;color:#fff">➕ 신규견적</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>`}
       <button class="btn xls" id="cq-xls">📥 엑셀 다운로드</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${st.workMode?`<div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid #d8cbee;border-radius:8px">
       <div style="padding:9px 14px;background:#f4f0fb;font-size:13px;color:#4a3a6a;position:sticky;top:0;z-index:2">📋 <b>직원 입력 작업목록</b> — 데이터문제 <b style="color:#c0392b">${st.workBy['데이터문제']||0}</b> · 신규 <b style="color:#b8791f">${st.workBy['신규']||0}</b> · 완료 <b style="color:#1c7c3a">${st.workDone}</b> <span style="color:#8a7aa5">· 입고수량 큰 순 · 행 클릭 → 입력폼 → 저장 시 완료</span></div>
       <table class="tbl fit" style="font-size:12.5px"><thead><tr><th>품번</th><th>협력사</th><th>유형</th><th>사유</th><th class="num">입고수량</th></tr></thead>
       <tbody>${st.workLoading?spinRow(5):(st.worklist.length?st.worklist.map((r,i)=>`<tr class="cq-wrow" data-idx="${i}" style="cursor:pointer">
         <td style="font-family:monospace;font-size:12px">${esc(r.assy_code)}</td><td>${r.vendor?esc(r.vendor):'<span style="color:#c9d1dc">-</span>'}</td>
         <td><span style="font-size:11px;padding:1px 6px;border-radius:8px;background:${r.wtype==='신규'?'#fbe9d0':'#fdecec'};color:${r.wtype==='신규'?'#b8791f':'#c0392b'}">${esc(r.wtype)}</span></td>
         <td style="font-size:11px;color:#6a6a6a">${esc(r.reason)}</td><td class="num">${won(r.in_qty)}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">작업목록 없음 (전부 완료)</td></tr>')}</tbody></table></div>`:''}
     <style>
       #cq-tbl{width:max-content!important;table-layout:auto!important;border-collapse:separate!important;border-spacing:0}
       #cq-tbl th,#cq-tbl td{padding:1px 6px!important;white-space:nowrap;line-height:1.35}
       #cq-tbl td.cap{white-space:normal}
       /* 2줄 헤더 계단식 고정: 그룹행 top:0, 세부행 top=그룹행높이 (데이터 배어나옴 방지) */
       #cq-tbl thead th{position:sticky;z-index:5}
       #cq-tbl thead tr:first-child th{top:0;height:18px}
       #cq-tbl thead tr:nth-child(2) th{top:18px}
     </style>
     <div class="grid-wrap" id="cq-grid" style="${st.workMode?'display:none;':''}max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" id="cq-tbl" style="font-size:11px"><thead>
        <tr>
        ${canEd?'<th rowspan="2" style="width:24px"></th>':''}
        <th rowspan="2" data-sort="vendor" style="cursor:pointer" title="더블클릭 정렬">협력사</th><th rowspan="2" data-sort="assy_code" style="cursor:pointer" title="더블클릭 정렬">품번(Assy)</th><th rowspan="2" data-sort="item_name" style="cursor:pointer" title="더블클릭 정렬">품명</th><th rowspan="2" data-sort="spec" style="cursor:pointer" title="더블클릭 정렬">규격</th><th rowspan="2" data-sort="grade" style="cursor:pointer" title="더블클릭 정렬">등급</th>
        <th colspan="4" class="center" style="background:#f0efe9;color:#8a6d3b;border-left:2px solid #d9d3c4">인상전 <span style="font-weight:400;font-size:9px">(종전·작년12월)</span></th>
        <th colspan="4" class="center" style="background:#eaf1fc;color:#1c47a0;border-left:2px solid #b9cdec">인상후 <span style="font-weight:400;font-size:9px">(적용월 기준)</span></th>
        <th rowspan="2" class="num" data-sort="diff_new" style="cursor:pointer" title="더블클릭 정렬 — 손익 이상치 찾기 · 인상후 총가공비 − 인상전 총가공비">가공비<br>차이</th>
        <th rowspan="2" data-sort="last_in_ymd" style="cursor:pointer" title="더블클릭 정렬">최근납품</th><th rowspan="2" data-sort="status" style="cursor:pointer" title="더블클릭 정렬">상태</th>${canEd?'<th rowspan="2" style="width:40px">작업</th>':''}</tr>
        <tr>
        <th class="num" data-sort="mat_before" style="background:#f7f6f1;color:#1c6ec2;border-left:2px solid #d9d3c4;cursor:pointer" title="더블클릭 정렬">재료비</th><th class="num" data-sort="ratio_before" style="background:#f7f6f1;cursor:pointer">재료비율</th><th class="num" data-sort="proc_before" style="background:#f7f6f1;color:#1c7c3a;cursor:pointer">총가공비</th><th class="num" data-sort="incost_before" style="background:#f7f6f1;color:#8a6d3b;cursor:pointer">입고가</th>
        <th class="num" data-sort="mat_after" style="background:#f4f8ff;color:#1c6ec2;border-left:2px solid #b9cdec;cursor:pointer" title="더블클릭 정렬">재료비</th><th class="num" data-sort="ratio_after" style="background:#f4f8ff;cursor:pointer">재료비율</th><th class="num" data-sort="proc_after" style="background:#f4f8ff;color:#1c7c3a;cursor:pointer">총가공비</th><th class="num" data-sort="incost_after" style="background:#f4f8ff;color:#8a6d3b;cursor:pointer">입고가</th></tr></thead>
      <tbody>${st.loading?spinRow(canEd?18:16):(st.rows.length?st.rows.map((r,i)=>`<tr class="cq-row" data-idx="${i}">
        ${canEd?`<td class="center"><input type="checkbox" class="cq-chk" data-id="${r.quote_id}" ${st.sel.has(r.quote_id)?'checked':''} onclick="event.stopPropagation()"></td>`:''}
        <td style="font-weight:600;color:#1c47a0">${esc(r.vendor)}</td>
        <td style="font-family:monospace;font-size:13px">${esc(r.assy_code)}${r.switched?' <span title="과거 사급 → 현재 제작동관 전환" style="font-size:9px;padding:1px 4px;border-radius:8px;background:#f3e8ff;color:#7c3aed;font-family:sans-serif">🔄전환</span>':''}</td>
        <td class="cap" title="${esc(r.item_name)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.item_name)}</td>
        <td style="font-size:10px">${esc(r.spec)}</td>
        <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:${r.grade==='고강도CU'?'#fbe9d0':'#e8eef7'};color:${r.grade==='고강도CU'?'#b8791f':'#1c47a0'};white-space:nowrap">${esc(r.grade||'일반CU')}</span></td>
        <td class="num" style="color:#1c6ec2;background:#faf9f4;border-left:2px solid #e6e0d0" title="인상전 재료비 = 견적동 + 용접봉 + 사급부품(판매단가 작년12월)"><b>${r.mat_before!=null?won(r.mat_before):'-'}</b></td>
        <td class="num" style="background:#faf9f4">${r.ratio_before!=null?r.ratio_before+'%':'-'}</td>
        <td class="num" style="color:#1c7c3a;background:#faf9f4" title="인상전 총가공비 = 종전입고가 − 인상전 재료비">${r.proc_before!=null?won(r.proc_before):'-'}</td>
        <td class="num" style="color:#8a6d3b;background:#faf9f4">${r.incost_before!=null?won(r.incost_before):'-'}</td>
        <td class="num" style="color:#1c6ec2;background:#f7fbff;border-left:2px solid #cadcf3" title="인상후 재료비 = 인상후동(현재사급가) + 용접봉 + 사급부품(판매단가 적용월)"><b>${r.mat_after!=null?won(r.mat_after):'-'}</b></td>
        <td class="num" style="background:#f7fbff">${r.ratio_after!=null?r.ratio_after+'%':'-'}</td>
        <td class="num" style="color:#1c7c3a;background:#f7fbff" title="인상후 총가공비 = 현재입고가 − 인상후 재료비">${r.proc_after!=null?won(r.proc_after):'-'}</td>
        <td class="num" style="color:#8a6d3b;background:#f7fbff">${r.incost_after!=null?won(r.incost_after):'-'}</td>
        <td class="num" title="인상후 총가공비 − 인상전 총가공비 · ≈0=가공비 유지(정상, 재료인상만 반영) · 값이 크면 가공비 변동=검토">${r.diff_new!=null?('<b style="color:'+(Math.abs(r.diff_new)<Math.max(50,(r.incost_before||0)*0.03)?'#1c7c3a':'#c0392b')+'">'+won(r.diff_new)+'</b>'):'-'}</td>
        <td class="center" style="font-size:10px;${r.last_in_ymd?'':'color:#c9d1dc'}">${r.last_in_ymd?('20'+r.last_in_ymd.slice(0,2)+'-'+r.last_in_ymd.slice(2,4)+'-'+r.last_in_ymd.slice(4,6)):'미납품'}</td>
        <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:${r.status==='확정'?'#e3f5e9':'#eef2f7'};color:${r.status==='확정'?'#1c7c3a':'#5a6a80'}">${esc(r.status)}</span></td>
        ${canEd?`<td class="center"><button class="btn cq-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px;background:#eef2fb;color:#1c47a0" onclick="event.stopPropagation()">상세</button></td>`:''}</tr>`).join(''):`<tr><td colspan="${canEd?18:16}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
     ${modal?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:560px;max-width:97vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>협력사견적 ${f.quote_id?'수정':'신규'}</b><span id="cq-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:14px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px 8px;align-items:center;font-size:12px">
             <label style="color:#33507d;font-weight:600;text-align:right">협력사<span style="color:#c0392b">*</span></label><input class="inp cf" data-k="vendor" value="${esc(f.vendor||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">품번<span style="color:#c0392b">*</span></label><input class="inp cf" data-k="assy_code" value="${esc(f.assy_code||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">품명</label><input class="inp cf" data-k="item_name" value="${esc(f.item_name||'')}" style="grid-column:span 3">
             <label style="color:#33507d;font-weight:600;text-align:right">규격</label><input class="inp cf" data-k="spec" value="${esc(f.spec||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">등급</label><select class="inp cf" data-k="grade"><option value="일반CU" ${f.grade!=='고강도CU'?'selected':''}>일반CU</option><option value="고강도CU" ${f.grade==='고강도CU'?'selected':''}>고강도CU</option></select>
             <label style="color:#33507d;font-weight:600;text-align:right">총중량(kg)</label><input class="inp cf" type="number" step="any" data-k="total_weight" value="${esc(f.total_weight||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">사급가(원/kg)</label><input class="inp cf" type="number" step="any" data-k="sagub_price" value="${esc(f.sagub_price||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">가공비(고정)</label><input class="inp cf" type="number" step="any" data-k="proc_cost" value="${esc(f.proc_cost||'')}">
           </div>
           <div style="margin-top:10px;background:#f4f8ff;border:1px solid #dbe6f7;border-radius:8px;padding:8px 12px;font-size:12px;display:flex;gap:18px;justify-content:center">
             <span>원소재비 <b id="cq-pv-mat" style="color:#1c6ec2">${nf(matOf(f))}</b></span>
             <span style="color:#8aa0bd">+</span>
             <span>가공비 <b style="color:#1c7c3a">${nf(Math.round(+f.proc_cost||0))}</b></span>
             <span style="color:#8aa0bd">=</span>
             <span>판가 <b id="cq-pv-sale" style="font-size:14px">${nf(saleOf(f))}</b></span>
           </div>
           <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px;align-items:center;font-size:12px;margin-top:10px">
             <label style="color:#33507d;font-weight:600;text-align:right">견적가</label><input class="inp cf" type="number" step="any" data-k="quote_price" value="${esc(f.quote_price!=null?f.quote_price:'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">확정가</label><input class="inp cf" type="number" step="any" data-k="final_price" value="${esc(f.final_price!=null?f.final_price:'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">LG단가</label><input class="inp cf" type="number" step="any" data-k="lg_price" value="${esc(f.lg_price!=null?f.lg_price:'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">비고</label><input class="inp cf" data-k="remark" value="${esc(f.remark||'')}">
           </div>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="color:#8aa0bd;font-size:11px">확정가 입력 시 상태=확정. 원소재비=총중량×사급가 자동.</span>
           <span><button class="btn" id="cq-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="cq-cancel">닫기</button></span></div>
       </div></div>`:''}
     ${rc?`<div class="wr-modal" style="position:fixed;inset:0;z-index:111;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;padding:50px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:480px;max-width:96vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#b8791f;color:#fff;border-radius:10px 10px 0 0">
           <b>🔄 사급가 변경 → 판가 재계산</b><span id="cq-rx" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:16px">
           <div style="font-size:12px;color:#5a6a80;margin-bottom:12px">새 사급가(원/kg)를 적용하면 각 견적의 <b style="color:#1c6ec2">원소재비 = 총중량 × 새 사급가</b>로 재계산되고 <b style="color:#1c7c3a">가공비는 그대로 유지</b>됩니다. 판가 = 새 원소재비 + 가공비. <b>등급별로 각각 입력</b>하며, 비우면 해당 등급은 건드리지 않습니다.</div>
           <div style="display:grid;grid-template-columns:auto 1fr auto;gap:8px 10px;align-items:center;margin-bottom:12px">
             <span style="font-size:12px;padding:2px 7px;border-radius:8px;background:#e8eef7;color:#1c47a0;font-weight:600">일반CU</span>
             <input class="inp" id="cq-rc-pn" type="number" step="any" value="${esc(rc.price_normal!=null?rc.price_normal:20000)}" placeholder="일반CU 사급가" style="text-align:right;font-weight:700">
             <span style="color:#8aa0bd;font-size:11px">원/kg</span>
             <span style="font-size:12px;padding:2px 7px;border-radius:8px;background:#fbe9d0;color:#b8791f;font-weight:600">고강도CU</span>
             <input class="inp" id="cq-rc-ph" type="number" step="any" value="${esc(rc.price_high!=null?rc.price_high:22000)}" placeholder="고강도CU 사급가" style="text-align:right;font-weight:700">
             <span style="color:#8aa0bd;font-size:11px">원/kg</span>
           </div>
           <div style="font-size:12px;color:#33507d;font-weight:600;margin-bottom:6px">적용 범위 <span style="font-weight:400;color:#8aa0bd">(현재 화면: 일반 ${st.rows.filter(x=>x.grade!=='고강도CU').length} · 고강도 ${st.rows.filter(x=>x.grade==='고강도CU').length})</span></div>
           <div style="display:flex;flex-direction:column;gap:6px;font-size:12px">
             <label><input type="radio" name="cq-scope" value="all" ${rc.scope==='all'?'checked':''}> 전체 견적 (${won(st.cnt)}건 기준)</label>
             <label><input type="radio" name="cq-scope" value="vendor" ${rc.scope==='vendor'?'checked':''} ${st.vendor?'':'disabled'}> 현재 협력사만 ${st.vendor?`(${esc(st.vendor)})`:'<span style="color:#c9d1dc">— 협력사 선택 필요</span>'}</label>
             <label><input type="radio" name="cq-scope" value="ids" ${rc.scope==='ids'?'checked':''} ${st.sel.size?'':'disabled'}> 선택한 ${st.sel.size}건만</label>
           </div>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;text-align:right">
           <button class="btn" id="cq-rc-run" style="background:#b8791f;color:#fff">적용</button> <button class="btn" id="cq-rc-cancel">취소</button></div>
       </div></div>`:''}
     ${st.detail?(()=>{const d=st.detail;const T={'동관':{c:'#1c6ec2',n:'원소재(동관)'},'사급부품':{c:'#5a6a80',n:'부속품(사급)'},'용접봉':{c:'#b8791f',n:'용접봉'}};
       const sub=(t)=>d.rows.filter(x=>x.ptype===t);const sum=(a,k)=>a.reduce((s,x)=>s+(+x[k]||0),0);
       const tm=sum(d.rows,'mat_cost'),tp=sum(d.rows,'proc_cost'),tt=sum(d.rows,'part_total');
       return `<div class="wr-modal" style="position:fixed;inset:0;z-index:112;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:820px;max-width:98vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>🧩 하위부품 구성 — ${esc(d.assy)} <span style="font-weight:400;font-size:12px">${esc(d.vendor)}</span></b><span id="cq-dx" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           ${d.loading?'<div style="padding:20px;color:#8aa0bd">불러오는 중…</div>':(d.rows.length?
           ['동관','사급부품','용접봉'].filter(t=>sub(t).length).map(t=>`
             <div style="font-weight:700;color:${T[t].c};margin:8px 0 4px">${T[t].n} <span style="font-weight:400;color:#8aa0bd;font-size:12px">${sub(t).length}개</span></div>
             <table class="tbl" style="width:100%;font-size:11px;margin-bottom:6px"><thead><tr style="background:#f4f7fb">
               <th style="text-align:left">단품</th><th style="text-align:left">품명</th><th>규격</th><th class="num">재료비</th><th class="num">가공비</th><th class="num">합계</th></tr></thead>
             <tbody>${sub(t).map(x=>`<tr><td style="font-family:monospace;font-size:10px">${esc(x.part_code)}</td>
               <td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(x.part_name)}</td>
               <td style="font-size:10px">${esc(x.spec)}</td><td class="num" style="color:#1c6ec2">${won(x.mat_cost)}</td>
               <td class="num" style="color:#1c7c3a">${won(x.proc_cost)}</td><td class="num"><b>${won(x.part_total)}</b></td></tr>`).join('')}</tbody></table>`).join('')
           :'<div style="padding:20px;color:#8aa0bd">하위부품 데이터 없음</div>')}
           ${d.rows.length?`<div style="margin-top:10px;background:#f4f8ff;border:1px solid #dbe6f7;border-radius:8px;padding:8px 14px;font-size:13px;display:flex;gap:22px;justify-content:flex-end">
             <span>재료비 <b style="color:#1c6ec2">${nf(tm)}</b></span><span>가공비 <b style="color:#1c7c3a">${nf(tp)}</b></span>
             <span>합계 <b>${nf(tt)}</b></span></div>`:''}
         </div>
         <div style="padding:10px 16px;border-top:1px solid #e2e8f2;text-align:right"><button class="btn" id="cq-dc">닫기</button></div>
       </div></div>`;})():''}
     ${be?(()=>{const d=be.data;const soyo=beSoyo();const raw=beRaw();const weld=beWeld();
       const baseMat=d?d.rows.filter(r=>r.role!=='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowMat(r),0):0;   // 부속품/용접봉/반제품lump(편집 재료비 반영)
       const A0=be.asm||{gagong:(d&&d.assembly_proc)||0,mgmt:0,transport:0,profit:0};const asmTot=Math.round((+A0.gagong||0)+(+A0.mgmt||0)+(+A0.transport||0)+(+A0.profit||0));
       const procTube=d?d.rows.filter(r=>r.role==='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowGag(r),0):0;
       const mat=raw+baseMat;const gagong=procTube+asmTot;const curIn=(d&&d.cur_incost!=null)?d.cur_incost:null;const prevIn=(d&&d.prev_incost!=null)?d.prev_incost:null;
       // ★완제품 합계 = 백엔드 v3 총합. 총가공비 = 입고가 − 재료비 (리스트와 동일). 조정도 v3 재료비(totMat) 기준.
       const totMat=d?Math.round(d.total_mat||0):0;const totMatB=d?Math.round(d.total_mat_before||0):0;
       const sale=(curIn!=null?curIn:(totMat+gagong));const adjust=(curIn!=null?Math.round(curIn-totMat-gagong):0);const proc=gagong;
       const totGag=(curIn!=null?Math.round(curIn-totMat):gagong);const totSale=(curIn!=null?Math.round(curIn):(totMat+gagong));
       const totGagB=(prevIn!=null?Math.round(prevIn-totMatB):totGag);const totSaleB=(prevIn!=null?Math.round(prevIn):(totMatB+(totGagB||0)));const adjustB=(prevIn!=null?Math.round(prevIn-totMatB-gagong):adjust);
       const grand=sale;
       return `<div class="wr-modal" style="position:fixed;inset:0;z-index:112;background:rgba(20,30,50,.42);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:18px 8px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.34);width:1340px;max-width:98vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>📝 ${be.isNew&&!d?'신규 견적':(be.viewMode?'견적 상세 — ':'견적 편집 — ')+esc(be.assy)} <span style="font-weight:400;font-size:12px">${esc(d?d.name:'')}</span>${(d&&be.viewMode)?'<span style="font-size:11px;margin-left:8px;background:#eef2fb;color:#1c47a0;padding:2px 8px;border-radius:8px">읽기전용</span>':''}</b><span id="be-x" style="cursor:pointer;font-size:18px">✕</span></div>
         <div class="${be.viewMode?'be-view':''}" style="padding:12px 16px;max-height:calc(100vh - 150px);overflow:auto">
         ${be.loading?'<div style="padding:40px;text-align:center;color:#8aa0bd">불러오는 중…</div>':(!d?(be.isNew?`<div style="padding:34px;text-align:center"><div style="margin-bottom:12px;color:#33507d;font-size:13px">품번을 입력하면 <b>현 BOM 구성</b>이 자동으로 펼쳐집니다.</div><input class="inp" id="be-newitem" placeholder="Assy 품번" style="width:230px;font-family:monospace" value="${esc(be.assy||'')}"> <button class="btn" id="be-load" style="background:#1c7c3a;color:#fff">🔍 BOM 불러오기</button></div>`:'<div style="padding:40px;text-align:center;color:#c0392b">BOM 조회 실패</div>'):`
           <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:8px;font-size:12px;background:#f4f8ff;border:1px solid #dbe6f7;border-radius:8px;padding:7px 12px">
             <label style="color:#33507d;font-weight:600">협력사</label><input class="inp" id="be-vendor" value="${esc(be.vendor)}" style="width:120px">
             <span style="color:#8aa0bd;font-size:11px">임율 ${nf(d.labor_rate)}</span>
             <span style="display:inline-flex;align-items:center;gap:5px;background:#fff3d6;border:1px solid #e8c877;border-radius:6px;padding:3px 8px" title="적용월은 리스트 상단에서 전체 설정합니다(개별 변경 불가)"><label style="color:#8a5a00;font-weight:700">📅 적용월(전체)</label><b style="color:#8a5a00">${esc(st.ym||'-')}</b></span>
             <span style="color:#c0392b;font-weight:700" title="현재 재료비 합계(적용월 기준)">재료비(현재) ${nf(d.total_mat||0)}</span>
             ${d.need_input?`<span style="color:#c0392b;font-weight:600">⚠ 스펙 입력필요 ${d.need_input}건</span>`:'<span style="color:#1c7c3a">스펙 완비</span>'}
           </div>
           <div style="overflow-x:auto">
           <table class="tbl fit" style="font-size:13px"><thead><tr>
             <th>품번</th><th>품명</th><th>역할</th><th class="num">소요량</th><th class="num" style="color:#8aa0bd">BOM규격</th>
             <th class="num" style="color:#1c7c3a">Φ</th><th class="num" style="color:#1c7c3a">T</th><th class="num" style="color:#1c7c3a">L</th>
             <th class="num">개당중량</th><th class="num" style="color:#1c6ec2">소요중량</th><th class="num" style="color:#b8791f" title="사급가(원/kg)">사급가</th>
             <th class="num" style="color:#c0392b" title="재료비(현재·적용월): 사급=판매단가·제작동관=소요중량×사급가·용접봉=소요×단가">재료비</th><th class="num" style="color:#c0392b" title="재료비/합계">재료비율</th><th class="num" style="color:#1c7c3a" title="가공비 = 제작동관 가공 + 조립공정 + 조정">가공비</th><th class="num" style="color:#c0392b">합계</th>
             ${(d.proc_ops||[]).map(op=>`<th style="font-size:12px;color:#6a3fb0;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom" title="${esc(op)} 공정 횟수">${esc(op==='교/체'?'교체':op)}</th>`).join('')}
             <th style="color:#1c7c3a;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">가공비</th><th style="color:#8a6d3b;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">관리비</th><th style="color:#8a6d3b;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">운반비</th><th style="color:#8a6d3b;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">이윤</th></tr></thead>
           <tbody><tr style="background:#eaf1fc;font-weight:700">
               <td style="font-family:monospace;font-size:13px;padding-left:6px">${esc(d.item)}</td>
               <td class="cap" style="max-width:120px;overflow:hidden;text-overflow:ellipsis" title="${esc(d.name)}">${esc(d.name)}</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#1c47a0;color:#fff">완제품</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num be-tsoyo2" style="color:#1c6ec2">${nf4(soyo)}</td><td class="num">-</td>
               <td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tmat-root">${nf(totMat)}</td><td class="num" style="color:#5a6a80;font-weight:700" id="be-tratio-root">${totSale>0?Math.round(totMat/totSale*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" id="be-tgag-root" title="총가공비 = 현재입고가 − 재료비">${nf(totGag)}</td><td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tsale-root" title="판가(현재입고가)">${nf(totSale)}${d.asof_cur_label?'<div style="font-size:8px;color:#8aa0bd;font-weight:400" title="현재입고가 실제 납품월(실납품 실거래일)">납품:'+esc(d.asof_cur_label)+'</div>':''}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>
             ${d.rows.map(r=>{const isTube=r.role==='제작동관';const isWeld=r.role==='용접봉';const isPipe=(r.role!=='반제품'&&!isWeld&&(r.coop_diam||r.unit_weight||isTube));const e=be.edits[r.code]||{};
             const dd=(e.diam!=null&&e.diam!=='')?e.diam:(r.coop_diam||'');const tt=(e.thick!=null&&e.thick!=='')?e.thick:(r.coop_thick||'');const ll=(e.length!=null&&e.length!=='')?e.length:(r.coop_length||'');
             const uw=beUw(r);const need=isTube&&!(dd&&tt&&ll);const ind=6+r.level*12;const pr=r.procs||{};
             const rq=beRowQty(r);const rmat=beRowMat(r);const rgag=beRowGag(r);const rtot=rmat+rgag;const rratio=rtot>0?Math.round(rmat/rtot*100):(rmat?100:0);
             const grey=r.in_quote===false;const matEd=be.matEdits&&be.matEdits[r.code];const qtyEd=be.qtyEdits&&be.qtyEdits[r.code];
             return `<tr style="${need?'background:#fdf0f0':''}">
               <td style="font-family:monospace;font-size:12px;padding-left:${ind}px">${r.haskids?'▸':''}${esc(r.code)}</td>
               <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td>
               <td>${(be.viewMode||r.haskids||r.role==='반제품')?beBadge(r.role_disp||r.role):(()=>{const cur=(r.role_v3==='동관고강도')?'동관고강도':(r.role==='제작동관'?'제작동관':(r.role==='용접봉'?'용접봉':'사급'));return `<select class="be-role" data-code="${esc(r.code)}" data-uw="${beUw(r)||r.unit_weight||''}" style="font-size:10px;padding:1px 2px;border:1px solid #cbd5e6;border-radius:6px;background:#fffbe8">${['제작동관','동관고강도','사급','용접봉'].map(o=>`<option${cur===o?' selected':''}>${o}</option>`).join('')}</select>`;})()}</td>
               <td class="num"><input class="be-qty inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(qtyEd!=null&&qtyEd!==''?qtyEd:(r.cum_qty||''))}" style="width:46px;min-width:0;text-align:right;padding:1px 2px"></td>
               <td class="num" style="color:#8aa0bd;font-size:11px">${r.lg_diam?('Φ'+r.lg_diam+'×'+r.lg_thick+'×'+r.lg_length):'-'}</td>
               ${isPipe?`<td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="diam" value="${esc(dd)}" style="width:38px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_diam||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="thick" value="${esc(tt)}" style="width:32px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_thick||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="length" value="${esc(ll)}" style="width:40px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_length||''}"></td>`
                 :`<td class="num" style="font-size:9px">${dd||'-'}</td><td class="num" style="font-size:9px">${tt||'-'}</td><td class="num" style="font-size:9px">${ll||'-'}</td>`}
               <td class="num be-uw" data-code="${esc(r.code)}">${(uw||r.unit_weight)?nf4(uw||r.unit_weight):(isWeld?'<span style="color:#b8791f;font-size:9px">공정</span>':'-')}</td>
               <td class="num be-sw" data-code="${esc(r.code)}" style="color:#1c6ec2">${(uw||r.unit_weight)?nf4((uw||r.unit_weight)*rq):'-'}</td>
               <td class="num">${isTube?`<input class="be-sg inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc((be.sagubEdits&&be.sagubEdits[r.code]!=null&&be.sagubEdits[r.code]!=='')?be.sagubEdits[r.code]:(r.coop_sagub>0?r.coop_sagub:''))}" style="width:60px;min-width:0;text-align:right;padding:1px 2px;color:#b8791f;font-weight:600" title="사급가(원/kg)">`:(isWeld&&r.coop_sagub>0?`<span style="color:#b8791f;font-size:11px" title="용접봉 사급가">${nf(r.coop_sagub)}</span>`:'<span style="color:#c9d1dc">-</span>')}</td>
               <td class="num" style="${grey?'color:#c9d1dc':'color:#c0392b;font-weight:700'}" title="현재(인상후) 재료비 (사급=판매단가·동관=소요중량×사급가·용접봉=소요×단가)">${grey?('('+nf(rmat)+')'):(isTube?`<span class="be-rm" data-code="${esc(r.code)}">${nf(rmat)}</span>`:`<input class="be-mat inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(matEd!=null&&matEd!==''?matEd:(r.mat_now||0))}" style="width:64px;min-width:0;text-align:right;padding:1px 2px;color:#c0392b;font-weight:700">`)}${r.sale_note?'<div style="font-size:8px;color:#8aa0bd" title="현재 판매단가 적용일(해당 업체)">'+esc(r.sale_note)+'</div>':''}</td>
               <td class="num" style="color:#c0392b"><span class="be-ratio" data-code="${esc(r.code)}">${grey?'-':rratio+'%'}</span></td>
               <td class="num" style="color:#1c7c3a"><span class="be-rg2" data-code="${esc(r.code)}">${isTube?nf(rgag):'-'}</span></td>
               <td class="num" style="color:#c0392b;font-weight:700"><span class="be-tot" data-code="${esc(r.code)}">${grey?'-':nf(rtot)}</span></td>
               ${(d.proc_ops||[]).map(op=>`<td class="num">${isTube?`<input class="be-pc" data-code="${esc(r.code)}" data-op="${esc(op)}" value="${(be.procEdits[r.code]&&be.procEdits[r.code][op]!=null&&be.procEdits[r.code][op]!=='')?be.procEdits[r.code][op]:(pr[op]||'')}" style="width:26px;min-width:0;text-align:center;padding:1px 1px;font-size:11px;color:#6a3fb0;border:1px solid #e2e8f2;border-radius:3px">`:''}</td>`).join('')}
               <td class="num" style="color:#1c7c3a">${isTube?`<span class="be-rg" data-code="${esc(r.code)}">${nf(beRowGagong(r))}</span>`:'-'}</td>
               <td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td></tr>`;}).join('')}
             ${(be.asm||d.assembly_proc>0)?(()=>{const A=be.asm||{procs:{},gagong:d.assembly_proc,mgmt:0,transport:0,profit:0,total:d.assembly_proc};
               const atot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
               return `<tr style="background:#fff8ec">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#8a6d3b">(서브조립)</td>
               <td class="cap" style="color:#8a6d3b" title="견적서엔 칸이 없어 용접봉 줄에 넣었던 실제 조립작업 공정">서브ASSY 조립공정</td>
               <td><span style="font-size:11px;padding:1px 6px;border-radius:8px;background:#fff3e0;color:#b8791f">조립공정</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#1c7c3a;font-weight:700" id="be-asmgag">${nf(atot)}</td><td class="num" style="color:#c0392b;font-weight:700" id="be-asmtot">${nf(atot)}</td>
               ${(d.proc_ops||[]).map(op=>`<td class="num"><input class="be-asmpc" data-op="${esc(op)}" value="${A.procs&&A.procs[op]?A.procs[op]:''}" style="width:26px;min-width:0;text-align:center;padding:1px 1px;font-size:11px;color:#b8791f;border:1px solid #f0e0c0;border-radius:3px"></td>`).join('')}
               <td class="num"><input class="be-asm" data-f="gagong" value="${esc(A.gagong)}" style="width:50px;min-width:0;text-align:right;padding:1px 2px;font-size:12px;color:#1c7c3a;font-weight:700"></td>
               <td class="num"><input class="be-asm" data-f="mgmt" value="${esc(A.mgmt)}" style="width:50px;min-width:0;text-align:right;padding:1px 2px;font-size:12px"></td>
               <td class="num"><input class="be-asm" data-f="transport" value="${esc(A.transport)}" style="width:44px;min-width:0;text-align:right;padding:1px 2px;font-size:12px"></td>
               <td class="num"><input class="be-asm" data-f="profit" value="${esc(A.profit)}" style="width:44px;min-width:0;text-align:right;padding:1px 2px;font-size:12px"></td></tr>`;})():''}
             ${curIn!=null?`<tr style="background:#fef6e9">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#a06010">(가격조정)</td>
               <td class="cap" style="color:#a06010" title="판가(현재입고가) − 재료비 − 가공비">현재입고가 정합 조정</td>
               <td><span style="font-size:11px;padding:1px 6px;border-radius:8px;background:#fbe4cc;color:#a06010">조정</span></td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#a06010;font-weight:700" id="be-adjgag">${nf(adjust)}</td><td class="num" style="color:#a06010;font-weight:700" id="be-adjust">${nf(adjust)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>`:''}
             <tr><td colspan="${19+(d.proc_ops||[]).length}" style="height:0;border-top:3px solid #8a6d3b;padding:0"></td></tr>
             <tr style="background:#f0efe9"><td colspan="${19+(d.proc_ops||[]).length}" style="text-align:left;padding:5px 10px;color:#8a6d3b;font-size:12px;font-weight:700">📋 종전 견적 (인상전 · 종전사급가/작년12월 판매단가 · 읽기전용)</td></tr>
             <tr style="background:#faf9f4;font-weight:700">
               <td style="font-family:monospace;font-size:13px;padding-left:6px">${esc(d.item)}</td>
               <td class="cap" style="max-width:120px;overflow:hidden;text-overflow:ellipsis" title="${esc(d.name)}">${esc(d.name)}</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#8a6d3b;color:#fff">완제품</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num" style="color:#1c6ec2">${nf4(soyo)}</td><td class="num">-</td>
               <td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px">${nf(totMatB)}</td><td class="num" style="color:#5a6a80;font-weight:700">${totSaleB>0?Math.round(totMatB/totSaleB*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" title="종전 총가공비 = 종전입고가 − 종전재료비">${totGagB!=null?nf(totGagB):'-'}</td><td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px" title="종전 판가(종전입고가)">${totSaleB!=null?nf(totSaleB):'-'}${d.asof_prev_label?'<div style="font-size:8px;color:#8aa0bd;font-weight:400" title="종전입고가 실제 납품월(25/11 이하 최근 실거래일)">납품:'+esc(d.asof_prev_label)+'</div>':''}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>
             ${d.rows.map(r=>{const isTube=r.role==='제작동관';const isWeld=r.role==='용접봉';const uw=beUw(r);const ind=6+r.level*12;const pr=r.procs||{};
               const rq=(r.cum_qty||0);const rmatB=(r.mat_before!=null?r.mat_before:0);const rgag=isTube?beRowGagong(r):0;const rtotB=rmatB+rgag;
               const rratioB=rtotB>0?Math.round(rmatB/rtotB*100):(rmatB?100:0);const sagubPrev=(isTube&&uw&&rq)?Math.round(rmatB/(uw*rq)):(isWeld&&r.coop_sagub?+r.coop_sagub:null);const grey=r.in_quote===false;
               return `<tr>
                 <td style="font-family:monospace;font-size:12px;padding-left:${ind}px">${r.haskids?'▸':''}${esc(r.code)}</td>
                 <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td>
                 <td>${beBadge(r.role)}</td>
                 <td class="num">${nf4(rq)}</td>
                 <td class="num" style="color:#8aa0bd;font-size:11px">${r.lg_diam?('Φ'+r.lg_diam+'×'+r.lg_thick+'×'+r.lg_length):'-'}</td>
                 <td class="num" style="font-size:9px">${r.coop_diam||'-'}</td><td class="num" style="font-size:9px">${r.coop_thick||'-'}</td><td class="num" style="font-size:9px">${r.coop_length||'-'}</td>
                 <td class="num">${uw?nf4(uw):(isWeld?'<span style="color:#b8791f;font-size:9px">공정</span>':'-')}</td>
                 <td class="num" style="color:#1c6ec2">${(isTube&&uw)?nf4(uw*rq):'-'}</td>
                 <td class="num" style="color:#b8791f;font-weight:600">${(!be.viewMode&&isTube)?`<span class="be-prevsg" data-code="${esc(r.code)}" data-high="${(r.role_disp||'').indexOf('고강')>=0?1:0}" style="cursor:pointer;border-bottom:1px dashed #b8791f" title="클릭: 종전(인상전) 사급가 수정 · 일반CU 7550">${sagubPrev!=null?nf(sagubPrev):'입력'} ✎</span>`:(sagubPrev!=null?nf(sagubPrev):'-')}</td>
                 <td class="num" style="color:#8a6d3b;font-weight:700">${grey?('('+nf(rmatB)+')'):nf(rmatB)}${r.sale_note_prev?'<div style="font-size:8px;color:#8aa0bd" title="종전 판매단가 적용일(해당 업체)">'+esc(r.sale_note_prev)+'</div>':''}</td>
                 <td class="num" style="color:#8a6d3b">${grey?'-':rratioB+'%'}</td>
                 <td class="num" style="color:#1c7c3a">${isTube?nf(rgag):'-'}</td>
                 <td class="num" style="color:#8a6d3b;font-weight:700">${grey?'-':nf(rtotB)}</td>
                 ${(d.proc_ops||[]).map(op=>`<td class="num" style="font-size:11px;color:#6a3fb0">${(isTube&&pr[op])?pr[op]:''}</td>`).join('')}
                 <td class="num" style="color:#1c7c3a">${isTube?nf(rgag):'-'}</td>
                 <td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td></tr>`;}).join('')}
             ${(be.asm||d.assembly_proc>0)?(()=>{const A=be.asm||{gagong:d.assembly_proc,mgmt:0,transport:0,profit:0};const atot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
               return `<tr style="background:#fff8ec">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#8a6d3b">(서브조립)</td>
               <td class="cap" style="color:#8a6d3b">서브ASSY 조립공정</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#fff3e0;color:#b8791f">조립공정</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#1c7c3a;font-weight:700">${nf(atot)}</td><td class="num" style="color:#8a6d3b;font-weight:700">${nf(atot)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>`;})():''}
             ${prevIn!=null?`<tr style="background:#fef6e9">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#a06010">(가격조정)</td>
               <td class="cap" style="color:#a06010">종전입고가 정합 조정</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#fbe4cc;color:#a06010">조정</span></td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#a06010;font-weight:700">${nf(adjustB)}</td><td class="num" style="color:#a06010;font-weight:700">${nf(adjustB)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>`:''}
             </tbody></table></div>
           `)}
         </div>
         <div style="padding:10px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="color:#8aa0bd;font-size:11px">구성=현 BOM(고정) · 제작동관 협력사 스펙만 입력 · 용접봉=공정(재료비 제외)</span>
           <span>${canEd?(be.viewMode?'<button class="btn" id="be-editmode" style="background:#1c7c3a;color:#fff">✏ 수정 (현재 견적)</button> ':'<button class="btn" id="be-save" style="background:#1b6ec2;color:#fff">💾 저장</button> '):''}<button class="btn" id="be-cancel">닫기</button></span></div>
       </div></div>`;})():''}
     <style>#cq-tbl tbody tr:hover{background:#eef4ff}.cq-row.sel{background:#dbe9ff}
       .be-view input,.be-view select{border:none!important;background:transparent!important;box-shadow:none!important;pointer-events:none;padding:0!important;margin:0!important;text-align:inherit;font:inherit;color:inherit;width:auto!important;min-width:0;height:auto!important;line-height:1.2!important;vertical-align:middle}
       .be-view input.inp,.be-view .be-qty,.be-view .be-sp,.be-view .be-sg,.be-view .be-mat,.be-view .be-pc,.be-view .be-asm,.be-view .be-asmpc{cursor:default}
       .be-view table.fit{width:max-content!important;min-width:0!important;table-layout:auto!important;font-size:11px}
       .be-view td,.be-view th{padding:0 6px!important;white-space:nowrap;line-height:1.6;height:auto!important;width:auto!important;min-width:0!important}
       .be-view tr{height:auto!important}
       .be-view input{max-width:56px!important}</style>`;
    const g=id=>host.querySelector(id);
    g('#cq-go').onclick=()=>{st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};
    {const cf=g('#cq-filter');if(cf)cf.onchange=e=>{st.filterMode=e.target.value;st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};}
    {const gw=g('#cq-work');if(gw)gw.onclick=()=>{st.workMode=!st.workMode;st.msg='';if(st.workMode)loadWork();else render();};}
    host.querySelectorAll('.cq-wrow').forEach(tr=>tr.onclick=()=>{const r=st.worklist[+tr.dataset.idx];if(r)openWork(r.assy_code,r.vendor);});
    g('#cq-xls').onclick=()=>{
      if(!st.rows.length){alert('다운로드할 데이터가 없습니다.');return;}
      const hd=['협력사','품번(Assy)','품명','규격','등급',
        '인상전_재료비','인상전_재료비율(%)','인상전_총가공비','인상전_입고가',
        '인상후_재료비','인상후_재료비율(%)','인상후_총가공비','인상후_입고가',
        '차이(신)=인상후−인상전 총가공비','최근납품','상태'];
      const fy=y=>y?('20'+y.slice(0,2)+'-'+y.slice(2,4)+'-'+y.slice(4,6)):'';
      const bl=v=>(v==null?'':v);
      const rows=st.rows.map(r=>[r.vendor,r.assy_code,r.item_name,r.spec,r.grade||'일반CU',
        bl(r.mat_before),bl(r.ratio_before),bl(r.proc_before),bl(r.incost_before),
        bl(r.mat_after),bl(r.ratio_after),bl(r.proc_after),bl(r.incost_after),
        bl(r.diff_new),fy(r.last_in_ymd),r.status]);
      const tag=(st.vendor||'전체')+(st.ym?'_'+st.ym:'')+(st.filterMode==='active'?'_현재납품':(st.filterMode==='new'?'_미승인':''));
      dlCSV('협력사견적_'+tag+'.csv',hd,rows);};
    g('#cq-vendor').onchange=()=>{st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};
    {const _g=host.querySelector('#cq-grid'); if(_g){ if(st._scroll!=null)_g.scrollTop=st._scroll; _g.onscroll=()=>{st._scroll=_g.scrollTop;}; }}  // 상세 열고닫아도 리스트 스크롤 유지
    {const cy=g('#cq-ym');if(cy)cy.onchange=()=>{st.ym=cy.value;st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};}
    g('#cq-q').onkeyup=e=>{if(e.key==='Enter')g('#cq-go').click();};
    // 메인 컬럼 더블클릭 정렬 (토글 asc/desc). 차이(신) 정렬=손익 이상치 찾기
    host.querySelectorAll('#cq-tbl thead th[data-sort]').forEach(th=>th.ondblclick=()=>{
      const k=th.dataset.sort;
      st.sortDir=(st.sortKey===k&&st.sortDir==='asc')?'desc':'asc';
      st.sortKey=k; const dir=st.sortDir==='asc'?1:-1;
      const isNum=st.rows.some(r=>typeof r[k]==='number');
      st.rows.sort((a,b)=>{
        let x=a[k],y=b[k];
        if(isNum){ x=(x==null?-Infinity:+x); y=(y==null?-Infinity:+y); return (x-y)*dir; }
        return String(x==null?'':x).localeCompare(String(y==null?'':y))*dir;
      });
      render();
    });
    if(st.sortKey){const sth=host.querySelector(`#cq-tbl thead th[data-sort="${st.sortKey}"]`);if(sth)sth.insertAdjacentHTML('beforeend',`<span style="color:#c0392b">${st.sortDir==='asc'?' ▲':' ▼'}</span>`);}
    if(canEd){
      g('#cq-new').onclick=()=>newBomEdit();
      host.querySelectorAll('.cq-chk').forEach(ch=>ch.onclick=(ev)=>{ev.stopPropagation();const id=+ch.dataset.id;ch.checked?st.sel.add(id):st.sel.delete(id);});
      host.querySelectorAll('.cq-edit').forEach(b=>b.onclick=(ev)=>{ev.stopPropagation();openBomEdit(+b.dataset.idx);});
    }
    if(modal){
      g('#cq-cancel').onclick=g('#cq-x').onclick=()=>{st.form=null;render();};
      g('#cq-save').onclick=save;
      host.querySelectorAll('.cf').forEach(el=>el.oninput=()=>{st.form[el.dataset.k]=el.value;
        const pm=g('#cq-pv-mat'),ps=g('#cq-pv-sale');if(pm)pm.textContent=nf(matOf(st.form));if(ps)ps.textContent=nf(saleOf(st.form));});
    }
    if(rc){
      g('#cq-rc-cancel').onclick=g('#cq-rx').onclick=()=>{st.recalc=null;render();};
      g('#cq-rc-pn').oninput=e=>st.recalc.price_normal=e.target.value;
      g('#cq-rc-ph').oninput=e=>st.recalc.price_high=e.target.value;
      host.querySelectorAll('input[name=cq-scope]').forEach(r=>r.onchange=()=>{st.recalc.scope=r.value;});
      g('#cq-rc-run').onclick=doRecalc;
    }
    if(be){
      const close=()=>{st.bomedit=null;render();};
      const bx=g('#be-x'),bc=g('#be-cancel');if(bx)bx.onclick=close;if(bc)bc.onclick=close;
      const nl=g('#be-load'),ni=g('#be-newitem');
      if(nl)nl.onclick=()=>{be.vendor=(g('#be-vendor')?g('#be-vendor').value:be.vendor);loadBomInto(ni.value,null);};
      if(ni)ni.onkeyup=e=>{if(e.key==='Enter')loadBomInto(ni.value,null);};
      const bs=g('#be-save');if(bs)bs.onclick=saveBomEdit;
      const bem=g('#be-editmode');if(bem)bem.onclick=()=>{st.bomedit.viewMode=false;render();};
      host.querySelectorAll('.be-role').forEach(sel=>sel.onchange=async()=>{const code=sel.dataset.code,role=sel.value;sel.disabled=true;
        try{await fetch(`${API}/api/coopquote/set-role`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assy:be.assy,part:code,role})});}catch(e){}
        loadBomInto(be.assy,(be.rowvals?be.rowvals.sale:(be.data&&be.data.cur_incost!=null?be.data.cur_incost:null)));});
      const upd=()=>{const soyo=beSoyo();const raw=beRaw();
        const baseMat=be.data.rows.filter(r=>r.role!=='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowMat(r),0);
        const procTube=be.data.rows.filter(r=>r.role==='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowGag(r),0);
        const A=be.asm||{gagong:be.data.assembly_proc||0,mgmt:0,transport:0,profit:0};const asmTot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
        const mat=raw+baseMat;const gagong=procTube+asmTot;const curIn=(be.data.cur_incost!=null)?be.data.cur_incost:null;
        const sale=(curIn!=null?curIn:(mat+gagong));const adjust=(curIn!=null?Math.round(curIn-mat-gagong):0);
        const set=(id,v)=>{const el=g(id);if(el)el.textContent=v;};
        set('#be-tsoyo',nf4(soyo));set('#be-tsoyo2',nf4(soyo));set('#be-traw',nf(raw));set('#be-tbase',nf(baseMat));set('#be-tmat',nf(mat));set('#be-tmat-root',nf(mat));
        set('#be-tgag',nf(gagong));set('#be-tadj',nf(adjust));set('#be-adjust',nf(adjust));set('#be-adjgag',nf(adjust));set('#be-tsale',nf(sale));set('#be-grandtot',nf(sale));set('#be-grandtot-l',nf(sale));
        set('#be-grandmat',nf(mat));set('#be-grandgag',nf(gagong+adjust));set('#be-tgag-root',nf(gagong+adjust));
        set('#be-tratio-root',(sale>0?Math.round(mat/sale*100):0)+'%');set('#be-tsale-root',nf(sale));};
      const beRefreshRow=(inp)=>{const code=inp.dataset.code;const r=be.data.rows.find(x=>x.code===code);if(!r)return;
        const tr=inp.closest('tr');const uw=beUw(r);const rq=beRowQty(r);const rmat=beRowMat(r);const rgag=beRowGag(r);const rtot=rmat+rgag;const rratio=rtot>0?Math.round(rmat/rtot*100):(rmat?100:0);
        const s=(cls,v)=>{const el=tr.querySelector('.'+cls);if(el)el.textContent=v;};
        s('be-uw',uw?nf4(uw):(r.role==='용접봉'?'공정':'-'));s('be-sw',uw?nf4(uw*rq):'-');
        s('be-rm',nf(rmat));s('be-ratio',rratio+'%');s('be-tot',nf(rtot));s('be-rg',nf(rgag));
        tr.style.background=(r.role==='제작동관'&&!uw)?'#fdf0f0':'';upd();};
      const bv=g('#be-vendor');if(bv){bv.oninput=e=>be.vendor=e.target.value;bv.onchange=e=>{be.vendor=e.target.value;if(be.data&&be.assy)loadBomInto(be.assy,null);};}
      host.querySelectorAll('.be-sg').forEach(inp=>inp.oninput=()=>{be.sagubEdits=be.sagubEdits||{};be.sagubEdits[inp.dataset.code]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-sp').forEach(inp=>inp.oninput=()=>{const code=inp.dataset.code,fld=inp.dataset.f;be.edits[code]=be.edits[code]||{};be.edits[code][fld]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-qty').forEach(inp=>inp.oninput=()=>{be.qtyEdits=be.qtyEdits||{};be.qtyEdits[inp.dataset.code]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-mat').forEach(inp=>inp.oninput=()=>{be.matEdits=be.matEdits||{};be.matEdits[inp.dataset.code]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-pc').forEach(inp=>inp.oninput=()=>{const code=inp.dataset.code,op=inp.dataset.op;be.procEdits[code]=be.procEdits[code]||{};be.procEdits[code][op]=inp.value;beRefreshRow(inp);});
      const asmUpd=()=>{if(!be.asm)return;const A=be.asm;const atot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
        const t=g('#be-asmtot');if(t)t.textContent=nf(atot);upd();};
      host.querySelectorAll('.be-asm').forEach(inp=>inp.oninput=()=>{be.asm=be.asm||{procs:{},gagong:0,mgmt:0,transport:0,profit:0};be.asm[inp.dataset.f]=inp.value;asmUpd();});
      host.querySelectorAll('.be-asmpc').forEach(inp=>inp.oninput=()=>{be.asm=be.asm||{procs:{},gagong:0,mgmt:0,transport:0,profit:0};be.asm.procs=be.asm.procs||{};be.asm.procs[inp.dataset.op]=inp.value;
        const rate=be.data.rate||{};const lab=be.data.labor_rate||6300;let gg=0;
        Object.keys(be.asm.procs).forEach(op=>{const c=+be.asm.procs[op]||0;const dv=rate[op];if(c&&dv)gg+=(lab/dv)*c;});
        be.asm.gagong=Math.round(gg);const gi=host.querySelector('.be-asm[data-f="gagong"]');if(gi)gi.value=be.asm.gagong;asmUpd();});
    }
    attachResizers(host);
  };
  (async()=>{await loadVendors();load();})();
};

/* ===== 협력사견적관리2 (v2 테이블 · 단가구분/불출검증 분류) ===== */
SCREEN.coopquote2=(host)=>{
  const API=API_BASE;
  const st={rows:[],cnt:0,vendor:'',q:'',vendors:[],loading:false,form:null,sel:new Set(),recalc:null,msg:'',filterMode:'active',detail:null,bomedit:null,workMode:false,worklist:[],workBy:{},workDone:0,workLoading:false,workType:''};
  const loadParts=async(idx)=>{const r=st.rows[idx];if(!r)return;
    st.detail={assy:r.assy_code,vendor:r.vendor,rows:[],loading:true};render();
    try{const res=await fetch(`${API}/api/coopquote2/parts?assy=${encodeURIComponent(r.assy_code)}&vendor=${encodeURIComponent(r.vendor)}`);
      const j=await res.json();st.detail.rows=j.rows||[];}catch(e){st.detail.rows=[];}
    st.detail.loading=false;render();};
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const won2=v=>(v==null||v==='')?'-':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const nf=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const ed=()=>(typeof PERM!=='undefined')?PERM.canEdit('coopquote'):true;
  const loadVendors=async()=>{try{const r=await fetch(`${API}/api/coopquote2/vendors`);const j=await r.json();st.vendors=j.rows||[];}catch(e){}};
  const load=async()=>{st.loading=true;if(!st.ym)st.ym=new Date().toISOString().slice(0,7);render();
    try{const r=await fetch(`${API}/api/coopquote2/list?vendor=${encodeURIComponent(st.vendor)}&q=${encodeURIComponent(st.q)}&active_only=${st.filterMode==='active'?1:0}&newonly=${st.filterMode==='new'?1:0}&fixonly=${st.filterMode==='fix'?1:0}&ym=${encodeURIComponent(st.ym||'')}`);
      const j=await r.json();st.rows=j.rows||[];st.cnt=j.count||0;}
    catch(e){st.rows=[];st.cnt=0;}
    st.loading=false;render();};
  // 모달(신규/수정) 실시간 미리보기
  const matOf=f=>Math.round((+f.total_weight||0)*(+f.sagub_price||0));
  const saleOf=f=>matOf(f)+Math.round(+f.proc_cost||0);
  const save=async()=>{
    const f=st.form;if(!f.vendor||!f.assy_code){alert('협력사·품번은 필수입니다.');return;}
    try{const r=await fetch(`${API}/api/coopquote2/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'save');st.form=null;st.msg='✔ 견적 저장 완료';await load();}
    catch(e){alert('저장 실패: '+e.message);}};
  const doRecalc=async()=>{
    const rc=st.recalc;const pn=+rc.price_normal||0, ph=+rc.price_high||0;
    if(pn<=0&&ph<=0){alert('일반CU 또는 고강도CU 사급가를 입력하세요.');return;}
    const body={price_normal:pn,price_high:ph,scope:rc.scope};
    if(rc.scope==='vendor')body.vendor=st.vendor;
    if(rc.scope==='ids')body.ids=[...st.sel];
    try{const r=await fetch(`${API}/api/coopquote2/recalc`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'recalc');
      const dt=j.detail||{};st.recalc=null;st.sel.clear();
      st.msg=`✔ 재계산 완료 (가공비 유지) → 일반CU ${dt['일반CU']||0}건${pn?'('+nf(pn)+'원/kg)':''} · 고강도CU ${dt['고강도CU']||0}건${ph?'('+nf(ph)+'원/kg)':''}`;await load();}
    catch(e){alert('재계산 실패: '+e.message);}};
  // ===== BOM 견적 편집 모달 (하위부품 전체 한 번에) =====
  const geom=(d,t,L)=>(d&&t&&L)?Math.PI*(d-t)*t*L*8.94/1e6:0;
  const nf4=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const beUw=(r)=>{const be=st.bomedit;if(r.role==='반제품'||r.role==='용접봉')return 0;const e=be.edits[r.code];
    if(e&&(e.diam||e.thick||e.length)){const d=+e.diam||r.coop_diam||r.lg_diam,t=+e.thick||r.coop_thick||r.lg_thick,L=+e.length||r.coop_length||r.lg_length;return geom(d,t,L);}
    return r.unit_weight||0;};
  const beSoyo=()=>{const be=st.bomedit;return (!be||!be.data)?0:be.data.rows.filter(r=>r.role==='제작동관').reduce((s,r)=>s+beUw(r)*r.cum_qty,0);};
  // ★관경별 사급가: 행 입력값 → 저장된 관경별 → 헤더 기본 사급가 순
  const beRowSagub=(r)=>{const be=st.bomedit;const e=be.sagubEdits&&be.sagubEdits[r.code];
    if(e!=null&&e!=='')return +e||0;
    if(r.coop_sagub&&+r.coop_sagub>0)return +r.coop_sagub;
    return +be.sagub||0;};
  const beRowQty=(r)=>{const be=st.bomedit;const e=be.qtyEdits&&be.qtyEdits[r.code];return (e!=null&&e!=='')?(+e||0):(r.cum_qty||0);};
  // 행 재료비: 제작동관=소요중량×사급가(파생) · 그외=직접입력(matEdits) 또는 백엔드 mat_now
  const beRowMat=(r)=>{const be=st.bomedit;
    if(r.role==='제작동관')return Math.round(beUw(r)*beRowQty(r)*beRowSagub(r));
    const e=be.matEdits&&be.matEdits[r.code];return (e!=null&&e!=='')?Math.round(+e||0):Math.round(r.mat_now||0);};
  const beRowGag=(r)=>(r.role==='제작동관'?beRowGagong(r):0);   // 사급/용접봉=가공 없음
  const beRowTot=(r)=>beRowMat(r)+beRowGag(r);                  // 합계=재료비+가공비 (사급=재료비)
  const beRaw=()=>{const be=st.bomedit;return (!be||!be.data)?0:be.data.rows.filter(r=>r.role==='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowMat(r),0);};
  const beWeld=()=>{const be=st.bomedit;return (!be||!be.data)?0:Math.round(be.data.total_weld_cost||0);};
  const beProcCnt=(r,op)=>{const pe=st.bomedit.procEdits[r.code];if(pe&&pe[op]!=null&&pe[op]!=='')return +pe[op]||0;return (r.procs&&r.procs[op])||0;};
  const beRowGagong=(r)=>{const be=st.bomedit;if(r.role!=='제작동관'||!be.data)return 0;const rate=be.data.rate||{};const lab=be.data.labor_rate||6300;let t=0;
    (be.data.proc_ops||[]).forEach(op=>{const c=beProcCnt(r,op);const dv=rate[op];if(c&&dv)t+=(lab/dv)*c;});return Math.round(t*(r.cum_qty||0));};
  const newBomEdit=()=>{st.bomedit={isNew:true,loading:false,vendor:st.vendor||'',grade:'일반CU',sagub:20000,proc:0,ym:new Date().toISOString().slice(0,7),edits:{},procEdits:{},sagubEdits:{},matEdits:{},qtyEdits:{},data:null,assy:''};render();};
  const loadBomInto=async(item,salePrefill)=>{const be=st.bomedit;if(!be||!item.trim())return;
    be.assy=item.trim();be.loading=true;be.edits={};render();
    try{const res=await fetch(`${API}/api/coopquote2/bom-form?item=${encodeURIComponent(item.trim())}&vendor=${encodeURIComponent(be.vendor||'')}&ym=${encodeURIComponent(st.ym||'')}`);const j=await res.json();be.data=j;
      if(j.cur_sagub)be.sagub=j.cur_sagub;   // 기본사급가=최신 원소재 사급가(종전 견적사급가 아님)
      be.asm=j.assembly?JSON.parse(JSON.stringify(j.assembly)):null;   // 서브조립 편집용
      if(be.asm){be.asm.gagong=Math.round((be.asm.total||0)-(be.asm.mgmt||0)-(be.asm.transport||0)-(be.asm.profit||0));}  // 합계=가공+관리+운반+이윤 정합(용접봉재료 포함)
      // 신규(기존행 없음)만 공정기반 가공비로 프리필. 기존 견적은 저장 가공비 유지(조회창 일치)
      if(!be.rowvals){const procAuto=Math.round(j.total_proc_cost||0)+Math.round(j.total_weld_cost||0);
        be.proc=procAuto>0?procAuto:0;}
    }catch(e){be.data=null;}
    be.loading=false;render();};
  const openBomEdit=async(idx)=>{const r=st.rows[idx];if(!r)return;
    st.bomedit={isNew:false,viewMode:true,loading:true,vendor:r.vendor,grade:r.grade||'일반CU',sagub:r.sagub_price||20000,proc:Math.round(r.proc_cost||0),ym:new Date().toISOString().slice(0,7),edits:{},procEdits:{},sagubEdits:{},matEdits:{},qtyEdits:{},data:null,assy:r.assy_code,
      rowvals:{mat_cost:r.mat_cost||0,mat_raw:r.mat_raw||0,mat_weld:r.mat_weld||0,mat_part:r.mat_part||0,proc_cost:r.proc_cost||0,sale:r.sale_price||0}};render();
    await loadBomInto(r.assy_code, r.sale_price||0);};
  // 작업목록(직원입력)
  const loadWork=async()=>{st.workLoading=true;render();
    try{const r=await fetch(`${API}/api/coopquote2/worklist?wtype=${encodeURIComponent(st.workType)}`);const j=await r.json();st.worklist=j.rows||[];st.workBy=j.by_type||{};st.workDone=j.resolved||0;}
    catch(e){st.worklist=[];}
    st.workLoading=false;render();};
  const openWork=async(assy,vendor)=>{if(!assy)return;
    st.bomedit={isNew:false,loading:true,vendor:(vendor||st.vendor||'').trim(),grade:'일반CU',sagub:20000,proc:0,ym:new Date().toISOString().slice(0,7),edits:{},procEdits:{},sagubEdits:{},matEdits:{},qtyEdits:{},data:null,assy:assy,rowvals:null,fromWork:true};render();
    await loadBomInto(assy,null);};
  const saveBomEdit=async()=>{const be=st.bomedit;if(!be||!be.data)return;
    const specs=be.data.rows.filter(r=>r.role==='제작동관').map(r=>{const e=be.edits[r.code]||{};
      return {code:r.code,diam:(+e.diam||r.coop_diam||r.lg_diam),thick:(+e.thick||r.coop_thick||r.lg_thick),length:(+e.length||r.coop_length||r.lg_length),sagub:beRowSagub(r)};})
      .filter(s=>s.diam&&s.thick&&s.length);
    const baseMat=be.rowvals?Math.max(0,(be.rowvals.mat_cost||0)-(be.rowvals.mat_raw||0)):(be.data.rows.filter(r=>r.role!=='제작동관'&&r.role!=='반제품'&&r.pur_price).reduce((s,r)=>s+Math.round(r.pur_price*r.cum_qty),0));
    // 공정 ST(제작동관, 편집반영) + 서브조립 공정/관리/운반/이윤
    const procs=be.data.rows.filter(r=>r.role==='제작동관').map(r=>{const eff={};(be.data.proc_ops||[]).forEach(op=>{const c=beProcCnt(r,op);if(c>0)eff[op]=c;});return {code:r.code,ops:eff};});
    const assembly=be.asm?{procs:be.asm.procs||{},gagong:Math.round(+be.asm.gagong||0),mgmt:Math.round(+be.asm.mgmt||0),transport:Math.round(+be.asm.transport||0),profit:Math.round(+be.asm.profit||0)}:null;
    const body={item:be.data.item,vendor:be.vendor.trim(),grade:be.grade,sagub_price:+be.sagub||0,proc_cost:Math.round(+be.proc||0),base_mat:baseMat,item_name:be.data.name,specs,procs,assembly};
    try{const r=await fetch(`${API}/api/coopquote2/bom-save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'save');
      const wasWork=be.fromWork;st.bomedit=null;st.msg=`✔ 견적 저장 · 소요중량 ${nf4(j.total_soyo_weight)}kg · 원소재비 ${nf(j.mat_cost)} · 판가 ${nf(j.sale_price)}`;
      if(wasWork){await loadWork();}else{await load();}}
    catch(e){alert('저장 실패: '+e.message);}};
  const beBadge=(role)=>{const M={'제작동관':['#e8f3ec','#1c7c3a'],'사급':['#eef2f7','#5a6a80'],'용접봉':['#fff3e0','#b8791f'],'매입부품':['#f0ecfa','#6a3fb0'],'반제품':['#e8eef7','#1c47a0']};
    const key=(role&&role.indexOf('제작(')===0)?'제작동관':role;const c=M[key]||['#eee','#555'];return `<span style="font-size:10px;padding:1px 5px;border-radius:8px;background:${c[0]};color:${c[1]};white-space:nowrap">${role}</span>`;};
  const render=()=>{
    const canEd=ed();
    const modal=st.form, rc=st.recalc, f=st.form||{}, be=st.bomedit;
    const diffCol=r=>{if(r.diff==null)return '<span style="color:#c9d1dc">-</span>';
      const c=r.diff>0?'#c0392b':(r.diff<0?'#1c6ec2':'#5a6a80');const s=r.diff>0?'▲':(r.diff<0?'▼':'');
      return `<b style="color:${c}">${s}${nf(Math.abs(r.diff))}</b>`;};
    {const _pg=host.querySelector('#cq-grid'); if(_pg) st._scroll=_pg.scrollTop;}  // 재렌더 전 리스트 스크롤 보존
    host.innerHTML=`
     <div class="page-title">💱 협력사견적관리 <span style="font-size:12px;color:var(--muted);font-weight:400">하위부품 bottom-up 견적 vs 실입고가 · nx.coop_quote</span></div>
     <div class="page-sub">「협력 업체 견적 정리」 기반 <b>bottom-up</b>. <b style="color:#1c6ec2">재료비 = Σ하위부품(원소재·용접봉·부속품)</b>, <b style="color:#1c7c3a">가공비 = 판가−재료비</b>, <b>재료비율 = 재료비/판가</b>.
       품번 행을 <b>클릭</b>하면 하위부품 3분류 상세가 열립니다. 입고가 = <b>실제 납품 거래가</b>(<code>PU_T_STOCK_MAINT</code>, 라이브) 종전(작년12월)·현재(최근). 🚚 토글=현재 납품품목만.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">협력사</label><select class="sel" id="cq-vendor"><option value="">전체</option>${st.vendors.map(v=>`<option value="${esc(v.vendor)}" ${st.vendor===v.vendor?'selected':''}>${esc(v.vendor)} (${v.n})</option>`).join('')}</select>
       <input class="inp" id="cq-q" value="${esc(st.q)}" placeholder="품번/품명 검색" style="width:170px">
       <span style="display:inline-flex;align-items:center;gap:5px;background:#fff3d6;border:1px solid #e8c877;border-radius:6px;padding:2px 8px"><label style="color:#8a5a00;font-weight:700;font-size:12px" title="인상후 사급부품 판매단가·원소재 사급가 기준월 — 리스트 전체에 적용">📅 적용월(전체)</label><input class="inp" id="cq-ym" type="month" value="${esc(st.ym||'')}" style="width:130px;font-weight:600"></span>
       <button class="btn" id="cq-go">🔍 조회</button>
       <select class="btn" id="cq-filter" title="목록 필터: 전체 / 최근4개월 납품실적 / 미승인(BOM 자동생성)" style="background:#eef2f7;color:#33507d;font-weight:600">
         <option value="all"${st.filterMode==='all'?' selected':''}>📋 전체</option>
         <option value="active"${st.filterMode==='active'?' selected':''}>🚚 현재 납품품목</option>
         <option value="new"${st.filterMode==='new'?' selected':''}>🆕 미승인 견적</option>
         <option value="fix"${st.filterMode==='fix'?' selected':''}>⚠️ 보완/확인 필요</option>
       </select>
       ${canEd?`<button class="btn" id="cq-new" style="background:#1c7c3a;color:#fff">➕ 신규견적</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>`}
       <button class="btn xls" id="cq-xls">📥 엑셀 다운로드</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${st.workMode?`<div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid #d8cbee;border-radius:8px">
       <div style="padding:9px 14px;background:#f4f0fb;font-size:13px;color:#4a3a6a;position:sticky;top:0;z-index:2">📋 <b>직원 입력 작업목록</b> — 데이터문제 <b style="color:#c0392b">${st.workBy['데이터문제']||0}</b> · 신규 <b style="color:#b8791f">${st.workBy['신규']||0}</b> · 완료 <b style="color:#1c7c3a">${st.workDone}</b> <span style="color:#8a7aa5">· 입고수량 큰 순 · 행 클릭 → 입력폼 → 저장 시 완료</span></div>
       <table class="tbl fit" style="font-size:12.5px"><thead><tr><th>품번</th><th>협력사</th><th>유형</th><th>사유</th><th class="num">입고수량</th></tr></thead>
       <tbody>${st.workLoading?spinRow(5):(st.worklist.length?st.worklist.map((r,i)=>`<tr class="cq-wrow" data-idx="${i}" style="cursor:pointer">
         <td style="font-family:monospace;font-size:12px">${esc(r.assy_code)}</td><td>${r.vendor?esc(r.vendor):'<span style="color:#c9d1dc">-</span>'}</td>
         <td><span style="font-size:11px;padding:1px 6px;border-radius:8px;background:${r.wtype==='신규'?'#fbe9d0':'#fdecec'};color:${r.wtype==='신규'?'#b8791f':'#c0392b'}">${esc(r.wtype)}</span></td>
         <td style="font-size:11px;color:#6a6a6a">${esc(r.reason)}</td><td class="num">${won(r.in_qty)}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">작업목록 없음 (전부 완료)</td></tr>')}</tbody></table></div>`:''}
     <style>
       #cq-tbl{width:max-content!important;table-layout:auto!important;border-collapse:separate!important;border-spacing:0}
       #cq-tbl th,#cq-tbl td{padding:1px 6px!important;white-space:nowrap;line-height:1.35}
       #cq-tbl td.cap{white-space:normal}
       /* 2줄 헤더 계단식 고정: 그룹행 top:0, 세부행 top=그룹행높이 (데이터 배어나옴 방지) */
       #cq-tbl thead th{position:sticky;z-index:5}
       #cq-tbl thead tr:first-child th{top:0;height:18px}
       #cq-tbl thead tr:nth-child(2) th{top:18px}
     </style>
     <div class="grid-wrap" id="cq-grid" style="${st.workMode?'display:none;':''}max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" id="cq-tbl" style="font-size:11px"><thead>
        <tr>
        ${canEd?'<th rowspan="2" style="width:24px"></th>':''}
        <th rowspan="2" data-sort="vendor" style="cursor:pointer" title="더블클릭 정렬">협력사</th><th rowspan="2" data-sort="assy_code" style="cursor:pointer" title="더블클릭 정렬">품번(Assy)</th><th rowspan="2" data-sort="item_name" style="cursor:pointer" title="더블클릭 정렬">품명</th><th rowspan="2" data-sort="spec" style="cursor:pointer" title="더블클릭 정렬">규격</th><th rowspan="2" data-sort="grade" style="cursor:pointer" title="더블클릭 정렬">등급</th>
        <th colspan="4" class="center" style="background:#f0efe9;color:#8a6d3b;border-left:2px solid #d9d3c4">인상전 <span style="font-weight:400;font-size:9px">(종전·작년12월)</span></th>
        <th colspan="4" class="center" style="background:#eaf1fc;color:#1c47a0;border-left:2px solid #b9cdec">인상후 <span style="font-weight:400;font-size:9px">(적용월 기준)</span></th>
        <th rowspan="2" class="num" data-sort="diff_new" style="cursor:pointer" title="더블클릭 정렬 — 손익 이상치 찾기 · 인상후 총가공비 − 인상전 총가공비">가공비<br>차이</th>
        <th rowspan="2" data-sort="last_in_ymd" style="cursor:pointer" title="더블클릭 정렬">최근납품</th><th rowspan="2" data-sort="status" style="cursor:pointer" title="더블클릭 정렬">상태</th>${canEd?'<th rowspan="2" style="width:40px">작업</th>':''}</tr>
        <tr>
        <th class="num" data-sort="mat_before" style="background:#f7f6f1;color:#1c6ec2;border-left:2px solid #d9d3c4;cursor:pointer" title="더블클릭 정렬">재료비</th><th class="num" data-sort="ratio_before" style="background:#f7f6f1;cursor:pointer">재료비율</th><th class="num" data-sort="proc_before" style="background:#f7f6f1;color:#1c7c3a;cursor:pointer">총가공비</th><th class="num" data-sort="incost_before" style="background:#f7f6f1;color:#8a6d3b;cursor:pointer">입고가</th>
        <th class="num" data-sort="mat_after" style="background:#f4f8ff;color:#1c6ec2;border-left:2px solid #b9cdec;cursor:pointer" title="더블클릭 정렬">재료비</th><th class="num" data-sort="ratio_after" style="background:#f4f8ff;cursor:pointer">재료비율</th><th class="num" data-sort="proc_after" style="background:#f4f8ff;color:#1c7c3a;cursor:pointer">총가공비</th><th class="num" data-sort="incost_after" style="background:#f4f8ff;color:#8a6d3b;cursor:pointer">입고가</th></tr></thead>
      <tbody>${st.loading?spinRow(canEd?18:16):(st.rows.length?st.rows.map((r,i)=>`<tr class="cq-row" data-idx="${i}">
        ${canEd?`<td class="center"><input type="checkbox" class="cq-chk" data-id="${r.quote_id}" ${st.sel.has(r.quote_id)?'checked':''} onclick="event.stopPropagation()"></td>`:''}
        <td style="font-weight:600;color:#1c47a0">${esc(r.vendor)}</td>
        <td style="font-family:monospace;font-size:13px">${esc(r.assy_code)}${r.switched?' <span title="과거 사급 → 현재 제작동관 전환" style="font-size:9px;padding:1px 4px;border-radius:8px;background:#f3e8ff;color:#7c3aed;font-family:sans-serif">🔄전환</span>':''}</td>
        <td class="cap" title="${esc(r.item_name)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.item_name)}</td>
        <td style="font-size:10px">${esc(r.spec)}</td>
        <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:${r.grade==='고강도CU'?'#fbe9d0':'#e8eef7'};color:${r.grade==='고강도CU'?'#b8791f':'#1c47a0'};white-space:nowrap">${esc(r.grade||'일반CU')}</span></td>
        <td class="num" style="color:#1c6ec2;background:#faf9f4;border-left:2px solid #e6e0d0" title="인상전 재료비 = 견적동 + 용접봉 + 사급부품(판매단가 작년12월)"><b>${r.mat_before!=null?won(r.mat_before):'-'}</b></td>
        <td class="num" style="background:#faf9f4">${r.ratio_before!=null?r.ratio_before+'%':'-'}</td>
        <td class="num" style="color:#1c7c3a;background:#faf9f4" title="인상전 총가공비 = 종전입고가 − 인상전 재료비">${r.proc_before!=null?won(r.proc_before):'-'}</td>
        <td class="num" style="color:#8a6d3b;background:#faf9f4">${r.incost_before!=null?won(r.incost_before):'-'}</td>
        <td class="num" style="color:#1c6ec2;background:#f7fbff;border-left:2px solid #cadcf3" title="인상후 재료비 = 인상후동(현재사급가) + 용접봉 + 사급부품(판매단가 적용월)"><b>${r.mat_after!=null?won(r.mat_after):'-'}</b></td>
        <td class="num" style="background:#f7fbff">${r.ratio_after!=null?r.ratio_after+'%':'-'}</td>
        <td class="num" style="color:#1c7c3a;background:#f7fbff" title="인상후 총가공비 = 현재입고가 − 인상후 재료비">${r.proc_after!=null?won(r.proc_after):'-'}</td>
        <td class="num" style="color:#8a6d3b;background:#f7fbff">${r.incost_after!=null?won(r.incost_after):'-'}</td>
        <td class="num" title="인상후 총가공비 − 인상전 총가공비 · ≈0=가공비 유지(정상, 재료인상만 반영) · 값이 크면 가공비 변동=검토">${r.diff_new!=null?('<b style="color:'+(Math.abs(r.diff_new)<Math.max(50,(r.incost_before||0)*0.03)?'#1c7c3a':'#c0392b')+'">'+won(r.diff_new)+'</b>'):'-'}</td>
        <td class="center" style="font-size:10px;${r.last_in_ymd?'':'color:#c9d1dc'}">${r.last_in_ymd?('20'+r.last_in_ymd.slice(0,2)+'-'+r.last_in_ymd.slice(2,4)+'-'+r.last_in_ymd.slice(4,6)):'미납품'}</td>
        <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:${r.status==='확정'?'#e3f5e9':'#eef2f7'};color:${r.status==='확정'?'#1c7c3a':'#5a6a80'}">${esc(r.status)}</span></td>
        ${canEd?`<td class="center"><button class="btn cq-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px;background:#eef2fb;color:#1c47a0" onclick="event.stopPropagation()">상세</button></td>`:''}</tr>`).join(''):`<tr><td colspan="${canEd?18:16}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
     ${modal?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:560px;max-width:97vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>협력사견적 ${f.quote_id?'수정':'신규'}</b><span id="cq-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:14px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px 8px;align-items:center;font-size:12px">
             <label style="color:#33507d;font-weight:600;text-align:right">협력사<span style="color:#c0392b">*</span></label><input class="inp cf" data-k="vendor" value="${esc(f.vendor||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">품번<span style="color:#c0392b">*</span></label><input class="inp cf" data-k="assy_code" value="${esc(f.assy_code||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">품명</label><input class="inp cf" data-k="item_name" value="${esc(f.item_name||'')}" style="grid-column:span 3">
             <label style="color:#33507d;font-weight:600;text-align:right">규격</label><input class="inp cf" data-k="spec" value="${esc(f.spec||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">등급</label><select class="inp cf" data-k="grade"><option value="일반CU" ${f.grade!=='고강도CU'?'selected':''}>일반CU</option><option value="고강도CU" ${f.grade==='고강도CU'?'selected':''}>고강도CU</option></select>
             <label style="color:#33507d;font-weight:600;text-align:right">총중량(kg)</label><input class="inp cf" type="number" step="any" data-k="total_weight" value="${esc(f.total_weight||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">사급가(원/kg)</label><input class="inp cf" type="number" step="any" data-k="sagub_price" value="${esc(f.sagub_price||'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">가공비(고정)</label><input class="inp cf" type="number" step="any" data-k="proc_cost" value="${esc(f.proc_cost||'')}">
           </div>
           <div style="margin-top:10px;background:#f4f8ff;border:1px solid #dbe6f7;border-radius:8px;padding:8px 12px;font-size:12px;display:flex;gap:18px;justify-content:center">
             <span>원소재비 <b id="cq-pv-mat" style="color:#1c6ec2">${nf(matOf(f))}</b></span>
             <span style="color:#8aa0bd">+</span>
             <span>가공비 <b style="color:#1c7c3a">${nf(Math.round(+f.proc_cost||0))}</b></span>
             <span style="color:#8aa0bd">=</span>
             <span>판가 <b id="cq-pv-sale" style="font-size:14px">${nf(saleOf(f))}</b></span>
           </div>
           <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px;align-items:center;font-size:12px;margin-top:10px">
             <label style="color:#33507d;font-weight:600;text-align:right">견적가</label><input class="inp cf" type="number" step="any" data-k="quote_price" value="${esc(f.quote_price!=null?f.quote_price:'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">확정가</label><input class="inp cf" type="number" step="any" data-k="final_price" value="${esc(f.final_price!=null?f.final_price:'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">LG단가</label><input class="inp cf" type="number" step="any" data-k="lg_price" value="${esc(f.lg_price!=null?f.lg_price:'')}">
             <label style="color:#33507d;font-weight:600;text-align:right">비고</label><input class="inp cf" data-k="remark" value="${esc(f.remark||'')}">
           </div>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="color:#8aa0bd;font-size:11px">확정가 입력 시 상태=확정. 원소재비=총중량×사급가 자동.</span>
           <span><button class="btn" id="cq-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="cq-cancel">닫기</button></span></div>
       </div></div>`:''}
     ${rc?`<div class="wr-modal" style="position:fixed;inset:0;z-index:111;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;padding:50px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:480px;max-width:96vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#b8791f;color:#fff;border-radius:10px 10px 0 0">
           <b>🔄 사급가 변경 → 판가 재계산</b><span id="cq-rx" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:16px">
           <div style="font-size:12px;color:#5a6a80;margin-bottom:12px">새 사급가(원/kg)를 적용하면 각 견적의 <b style="color:#1c6ec2">원소재비 = 총중량 × 새 사급가</b>로 재계산되고 <b style="color:#1c7c3a">가공비는 그대로 유지</b>됩니다. 판가 = 새 원소재비 + 가공비. <b>등급별로 각각 입력</b>하며, 비우면 해당 등급은 건드리지 않습니다.</div>
           <div style="display:grid;grid-template-columns:auto 1fr auto;gap:8px 10px;align-items:center;margin-bottom:12px">
             <span style="font-size:12px;padding:2px 7px;border-radius:8px;background:#e8eef7;color:#1c47a0;font-weight:600">일반CU</span>
             <input class="inp" id="cq-rc-pn" type="number" step="any" value="${esc(rc.price_normal!=null?rc.price_normal:20000)}" placeholder="일반CU 사급가" style="text-align:right;font-weight:700">
             <span style="color:#8aa0bd;font-size:11px">원/kg</span>
             <span style="font-size:12px;padding:2px 7px;border-radius:8px;background:#fbe9d0;color:#b8791f;font-weight:600">고강도CU</span>
             <input class="inp" id="cq-rc-ph" type="number" step="any" value="${esc(rc.price_high!=null?rc.price_high:22000)}" placeholder="고강도CU 사급가" style="text-align:right;font-weight:700">
             <span style="color:#8aa0bd;font-size:11px">원/kg</span>
           </div>
           <div style="font-size:12px;color:#33507d;font-weight:600;margin-bottom:6px">적용 범위 <span style="font-weight:400;color:#8aa0bd">(현재 화면: 일반 ${st.rows.filter(x=>x.grade!=='고강도CU').length} · 고강도 ${st.rows.filter(x=>x.grade==='고강도CU').length})</span></div>
           <div style="display:flex;flex-direction:column;gap:6px;font-size:12px">
             <label><input type="radio" name="cq-scope" value="all" ${rc.scope==='all'?'checked':''}> 전체 견적 (${won(st.cnt)}건 기준)</label>
             <label><input type="radio" name="cq-scope" value="vendor" ${rc.scope==='vendor'?'checked':''} ${st.vendor?'':'disabled'}> 현재 협력사만 ${st.vendor?`(${esc(st.vendor)})`:'<span style="color:#c9d1dc">— 협력사 선택 필요</span>'}</label>
             <label><input type="radio" name="cq-scope" value="ids" ${rc.scope==='ids'?'checked':''} ${st.sel.size?'':'disabled'}> 선택한 ${st.sel.size}건만</label>
           </div>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;text-align:right">
           <button class="btn" id="cq-rc-run" style="background:#b8791f;color:#fff">적용</button> <button class="btn" id="cq-rc-cancel">취소</button></div>
       </div></div>`:''}
     ${st.detail?(()=>{const d=st.detail;const T={'동관':{c:'#1c6ec2',n:'원소재(동관)'},'사급부품':{c:'#5a6a80',n:'부속품(사급)'},'용접봉':{c:'#b8791f',n:'용접봉'}};
       const sub=(t)=>d.rows.filter(x=>x.ptype===t);const sum=(a,k)=>a.reduce((s,x)=>s+(+x[k]||0),0);
       const tm=sum(d.rows,'mat_cost'),tp=sum(d.rows,'proc_cost'),tt=sum(d.rows,'part_total');
       return `<div class="wr-modal" style="position:fixed;inset:0;z-index:112;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:820px;max-width:98vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>🧩 하위부품 구성 — ${esc(d.assy)} <span style="font-weight:400;font-size:12px">${esc(d.vendor)}</span></b><span id="cq-dx" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           ${d.loading?'<div style="padding:20px;color:#8aa0bd">불러오는 중…</div>':(d.rows.length?
           ['동관','사급부품','용접봉'].filter(t=>sub(t).length).map(t=>`
             <div style="font-weight:700;color:${T[t].c};margin:8px 0 4px">${T[t].n} <span style="font-weight:400;color:#8aa0bd;font-size:12px">${sub(t).length}개</span></div>
             <table class="tbl" style="width:100%;font-size:11px;margin-bottom:6px"><thead><tr style="background:#f4f7fb">
               <th style="text-align:left">단품</th><th style="text-align:left">품명</th><th>규격</th><th class="num">재료비</th><th class="num">가공비</th><th class="num">합계</th></tr></thead>
             <tbody>${sub(t).map(x=>`<tr><td style="font-family:monospace;font-size:10px">${esc(x.part_code)}</td>
               <td class="cap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(x.part_name)}</td>
               <td style="font-size:10px">${esc(x.spec)}</td><td class="num" style="color:#1c6ec2">${won(x.mat_cost)}</td>
               <td class="num" style="color:#1c7c3a">${won(x.proc_cost)}</td><td class="num"><b>${won(x.part_total)}</b></td></tr>`).join('')}</tbody></table>`).join('')
           :'<div style="padding:20px;color:#8aa0bd">하위부품 데이터 없음</div>')}
           ${d.rows.length?`<div style="margin-top:10px;background:#f4f8ff;border:1px solid #dbe6f7;border-radius:8px;padding:8px 14px;font-size:13px;display:flex;gap:22px;justify-content:flex-end">
             <span>재료비 <b style="color:#1c6ec2">${nf(tm)}</b></span><span>가공비 <b style="color:#1c7c3a">${nf(tp)}</b></span>
             <span>합계 <b>${nf(tt)}</b></span></div>`:''}
         </div>
         <div style="padding:10px 16px;border-top:1px solid #e2e8f2;text-align:right"><button class="btn" id="cq-dc">닫기</button></div>
       </div></div>`;})():''}
     ${be?(()=>{const d=be.data;const soyo=beSoyo();const raw=beRaw();const weld=beWeld();
       const baseMat=d?d.rows.filter(r=>r.role!=='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowMat(r),0):0;   // 부속품/용접봉/반제품lump(편집 재료비 반영)
       const A0=be.asm||{gagong:(d&&d.assembly_proc)||0,mgmt:0,transport:0,profit:0};const asmTot=Math.round((+A0.gagong||0)+(+A0.mgmt||0)+(+A0.transport||0)+(+A0.profit||0));
       const procTube=d?d.rows.filter(r=>r.role==='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowGag(r),0):0;
       const mat=raw+baseMat;const gagong=procTube+asmTot;const curIn=(d&&d.cur_incost!=null)?d.cur_incost:null;const prevIn=(d&&d.prev_incost!=null)?d.prev_incost:null;
       // ★완제품 합계 = 백엔드 v3 총합. 총가공비 = 입고가 − 재료비 (리스트와 동일). 조정도 v3 재료비(totMat) 기준.
       const totMat=d?Math.round(d.total_mat||0):0;const totMatB=d?Math.round(d.total_mat_before||0):0;
       const sale=(curIn!=null?curIn:(totMat+gagong));const adjust=(curIn!=null?Math.round(curIn-totMat-gagong):0);const proc=gagong;
       const totGag=(curIn!=null?Math.round(curIn-totMat):gagong);const totSale=(curIn!=null?Math.round(curIn):(totMat+gagong));
       const totGagB=(prevIn!=null?Math.round(prevIn-totMatB):totGag);const totSaleB=(prevIn!=null?Math.round(prevIn):(totMatB+(totGagB||0)));const adjustB=(prevIn!=null?Math.round(prevIn-totMatB-gagong):adjust);
       const grand=sale;
       return `<div class="wr-modal" style="position:fixed;inset:0;z-index:112;background:rgba(20,30,50,.42);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:18px 8px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.34);width:1340px;max-width:98vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>📝 ${be.isNew&&!d?'신규 견적':(be.viewMode?'견적 상세 — ':'견적 편집 — ')+esc(be.assy)} <span style="font-weight:400;font-size:12px">${esc(d?d.name:'')}</span>${(d&&be.viewMode)?'<span style="font-size:11px;margin-left:8px;background:#eef2fb;color:#1c47a0;padding:2px 8px;border-radius:8px">읽기전용</span>':''}</b><span id="be-x" style="cursor:pointer;font-size:18px">✕</span></div>
         <div class="${be.viewMode?'be-view':''}" style="padding:12px 16px;max-height:calc(100vh - 150px);overflow:auto">
         ${be.loading?'<div style="padding:40px;text-align:center;color:#8aa0bd">불러오는 중…</div>':(!d?(be.isNew?`<div style="padding:34px;text-align:center"><div style="margin-bottom:12px;color:#33507d;font-size:13px">품번을 입력하면 <b>현 BOM 구성</b>이 자동으로 펼쳐집니다.</div><input class="inp" id="be-newitem" placeholder="Assy 품번" style="width:230px;font-family:monospace" value="${esc(be.assy||'')}"> <button class="btn" id="be-load" style="background:#1c7c3a;color:#fff">🔍 BOM 불러오기</button></div>`:'<div style="padding:40px;text-align:center;color:#c0392b">BOM 조회 실패</div>'):`
           <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:8px;font-size:12px;background:#f4f8ff;border:1px solid #dbe6f7;border-radius:8px;padding:7px 12px">
             <label style="color:#33507d;font-weight:600">협력사</label><input class="inp" id="be-vendor" value="${esc(be.vendor)}" style="width:120px">
             <span style="color:#8aa0bd;font-size:11px">임율 ${nf(d.labor_rate)}</span>
             <span style="display:inline-flex;align-items:center;gap:5px;background:#fff3d6;border:1px solid #e8c877;border-radius:6px;padding:3px 8px" title="적용월은 리스트 상단에서 전체 설정합니다(개별 변경 불가)"><label style="color:#8a5a00;font-weight:700">📅 적용월(전체)</label><b style="color:#8a5a00">${esc(st.ym||'-')}</b></span>
             <span style="color:#c0392b;font-weight:700" title="현재 재료비 합계(적용월 기준)">재료비(현재) ${nf(d.total_mat||0)}</span>
             ${d.need_input?`<span style="color:#c0392b;font-weight:600">⚠ 스펙 입력필요 ${d.need_input}건</span>`:'<span style="color:#1c7c3a">스펙 완비</span>'}
           </div>
           <div style="overflow-x:auto">
           <table class="tbl fit" style="font-size:13px"><thead><tr>
             <th>품번</th><th>품명</th><th>역할</th><th class="num">소요량</th><th class="num" style="color:#8aa0bd">BOM규격</th>
             <th class="num" style="color:#1c7c3a">Φ</th><th class="num" style="color:#1c7c3a">T</th><th class="num" style="color:#1c7c3a">L</th>
             <th class="num">개당중량</th><th class="num" style="color:#1c6ec2">소요중량</th><th class="num" style="color:#b8791f" title="사급가(원/kg)">사급가</th>
             <th class="num" style="color:#c0392b" title="재료비(현재·적용월): 사급=판매단가·제작동관=소요중량×사급가·용접봉=소요×단가">재료비</th><th class="num" style="color:#c0392b" title="재료비/합계">재료비율</th><th class="num" style="color:#1c7c3a" title="가공비 = 제작동관 가공 + 조립공정 + 조정">가공비</th><th class="num" style="color:#c0392b">합계</th>
             ${(d.proc_ops||[]).map(op=>`<th style="font-size:12px;color:#6a3fb0;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom" title="${esc(op)} 공정 횟수">${esc(op==='교/체'?'교체':op)}</th>`).join('')}
             <th style="color:#1c7c3a;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">가공비</th><th style="color:#8a6d3b;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">관리비</th><th style="color:#8a6d3b;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">운반비</th><th style="color:#8a6d3b;writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;padding:6px 2px;letter-spacing:-1px;vertical-align:bottom">이윤</th></tr></thead>
           <tbody><tr style="background:#eaf1fc;font-weight:700">
               <td style="font-family:monospace;font-size:13px;padding-left:6px">${esc(d.item)}</td>
               <td class="cap" style="max-width:120px;overflow:hidden;text-overflow:ellipsis" title="${esc(d.name)}">${esc(d.name)}</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#1c47a0;color:#fff">완제품</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num be-tsoyo2" style="color:#1c6ec2">${nf4(soyo)}</td><td class="num">-</td>
               <td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tmat-root">${nf(totMat)}</td><td class="num" style="color:#5a6a80;font-weight:700" id="be-tratio-root">${totSale>0?Math.round(totMat/totSale*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" id="be-tgag-root" title="총가공비 = 현재입고가 − 재료비">${nf(totGag)}</td><td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tsale-root" title="판가(현재입고가)">${nf(totSale)}${d.asof_cur_label?'<div style="font-size:8px;color:#8aa0bd;font-weight:400" title="현재입고가 실제 납품월(실납품 실거래일)">납품:'+esc(d.asof_cur_label)+'</div>':''}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>
             ${d.rows.map(r=>{const isTube=r.role==='제작동관';const isWeld=r.role==='용접봉';const isPipe=(r.role!=='반제품'&&!isWeld&&(r.coop_diam||r.unit_weight||isTube));const e=be.edits[r.code]||{};
             const dd=(e.diam!=null&&e.diam!=='')?e.diam:(r.coop_diam||'');const tt=(e.thick!=null&&e.thick!=='')?e.thick:(r.coop_thick||'');const ll=(e.length!=null&&e.length!=='')?e.length:(r.coop_length||'');
             const uw=beUw(r);const need=isTube&&!(dd&&tt&&ll);const ind=6+r.level*12;const pr=r.procs||{};
             const rq=beRowQty(r);const rmat=beRowMat(r);const rgag=beRowGag(r);const rtot=rmat+rgag;const rratio=rtot>0?Math.round(rmat/rtot*100):(rmat?100:0);
             const grey=r.in_quote===false;const matEd=be.matEdits&&be.matEdits[r.code];const qtyEd=be.qtyEdits&&be.qtyEdits[r.code];
             return `<tr style="${need?'background:#fdf0f0':''}">
               <td style="font-family:monospace;font-size:12px;padding-left:${ind}px">${r.haskids?'▸':''}${esc(r.code)}</td>
               <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td>
               <td>${(be.viewMode||r.haskids||r.role==='반제품')?beBadge(r.role_disp||r.role):(()=>{const cur=(r.role_v3==='동관고강도')?'동관고강도':(r.role==='제작동관'?'제작동관':(r.role==='용접봉'?'용접봉':'사급'));return `<select class="be-role" data-code="${esc(r.code)}" data-uw="${beUw(r)||r.unit_weight||''}" style="font-size:10px;padding:1px 2px;border:1px solid #cbd5e6;border-radius:6px;background:#fffbe8">${['제작동관','동관고강도','사급','용접봉'].map(o=>`<option${cur===o?' selected':''}>${o}</option>`).join('')}</select>`;})()}</td>
               <td class="num"><input class="be-qty inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(qtyEd!=null&&qtyEd!==''?qtyEd:(r.cum_qty||''))}" style="width:46px;min-width:0;text-align:right;padding:1px 2px"></td>
               <td class="num" style="color:#8aa0bd;font-size:11px">${r.lg_diam?('Φ'+r.lg_diam+'×'+r.lg_thick+'×'+r.lg_length):'-'}</td>
               ${isPipe?`<td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="diam" value="${esc(dd)}" style="width:38px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_diam||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="thick" value="${esc(tt)}" style="width:32px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_thick||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="length" value="${esc(ll)}" style="width:40px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_length||''}"></td>`
                 :`<td class="num" style="font-size:9px">${dd||'-'}</td><td class="num" style="font-size:9px">${tt||'-'}</td><td class="num" style="font-size:9px">${ll||'-'}</td>`}
               <td class="num be-uw" data-code="${esc(r.code)}">${(uw||r.unit_weight)?nf4(uw||r.unit_weight):(isWeld?'<span style="color:#b8791f;font-size:9px">공정</span>':'-')}</td>
               <td class="num be-sw" data-code="${esc(r.code)}" style="color:#1c6ec2">${(uw||r.unit_weight)?nf4((uw||r.unit_weight)*rq):'-'}</td>
               <td class="num">${isTube?`<input class="be-sg inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc((be.sagubEdits&&be.sagubEdits[r.code]!=null&&be.sagubEdits[r.code]!=='')?be.sagubEdits[r.code]:(r.coop_sagub>0?r.coop_sagub:''))}" style="width:60px;min-width:0;text-align:right;padding:1px 2px;color:#b8791f;font-weight:600" title="사급가(원/kg)">`:(isWeld&&r.coop_sagub>0?`<span style="color:#b8791f;font-size:11px" title="용접봉 사급가">${nf(r.coop_sagub)}</span>`:'<span style="color:#c9d1dc">-</span>')}</td>
               <td class="num" style="${grey?'color:#c9d1dc':'color:#c0392b;font-weight:700'}" title="현재(인상후) 재료비 (사급=판매단가·동관=소요중량×사급가·용접봉=소요×단가)">${grey?('('+nf(rmat)+')'):(isTube?`<span class="be-rm" data-code="${esc(r.code)}">${nf(rmat)}</span>`:`<input class="be-mat inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(matEd!=null&&matEd!==''?matEd:(r.mat_now||0))}" style="width:64px;min-width:0;text-align:right;padding:1px 2px;color:#c0392b;font-weight:700">`)}${r.sale_note?'<div style="font-size:8px;color:#8aa0bd" title="현재 판매단가 적용일(해당 업체)">'+esc(r.sale_note)+'</div>':''}</td>
               <td class="num" style="color:#c0392b"><span class="be-ratio" data-code="${esc(r.code)}">${grey?'-':rratio+'%'}</span></td>
               <td class="num" style="color:#1c7c3a"><span class="be-rg2" data-code="${esc(r.code)}">${isTube?nf(rgag):'-'}</span></td>
               <td class="num" style="color:#c0392b;font-weight:700"><span class="be-tot" data-code="${esc(r.code)}">${grey?'-':nf(rtot)}</span></td>
               ${(d.proc_ops||[]).map(op=>`<td class="num">${isTube?`<input class="be-pc" data-code="${esc(r.code)}" data-op="${esc(op)}" value="${(be.procEdits[r.code]&&be.procEdits[r.code][op]!=null&&be.procEdits[r.code][op]!=='')?be.procEdits[r.code][op]:(pr[op]||'')}" style="width:26px;min-width:0;text-align:center;padding:1px 1px;font-size:11px;color:#6a3fb0;border:1px solid #e2e8f2;border-radius:3px">`:''}</td>`).join('')}
               <td class="num" style="color:#1c7c3a">${isTube?`<span class="be-rg" data-code="${esc(r.code)}">${nf(beRowGagong(r))}</span>`:'-'}</td>
               <td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td></tr>`;}).join('')}
             ${(be.asm||d.assembly_proc>0)?(()=>{const A=be.asm||{procs:{},gagong:d.assembly_proc,mgmt:0,transport:0,profit:0,total:d.assembly_proc};
               const atot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
               return `<tr style="background:#fff8ec">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#8a6d3b">(서브조립)</td>
               <td class="cap" style="color:#8a6d3b" title="견적서엔 칸이 없어 용접봉 줄에 넣었던 실제 조립작업 공정">서브ASSY 조립공정</td>
               <td><span style="font-size:11px;padding:1px 6px;border-radius:8px;background:#fff3e0;color:#b8791f">조립공정</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#1c7c3a;font-weight:700" id="be-asmgag">${nf(atot)}</td><td class="num" style="color:#c0392b;font-weight:700" id="be-asmtot">${nf(atot)}</td>
               ${(d.proc_ops||[]).map(op=>`<td class="num"><input class="be-asmpc" data-op="${esc(op)}" value="${A.procs&&A.procs[op]?A.procs[op]:''}" style="width:26px;min-width:0;text-align:center;padding:1px 1px;font-size:11px;color:#b8791f;border:1px solid #f0e0c0;border-radius:3px"></td>`).join('')}
               <td class="num"><input class="be-asm" data-f="gagong" value="${esc(A.gagong)}" style="width:50px;min-width:0;text-align:right;padding:1px 2px;font-size:12px;color:#1c7c3a;font-weight:700"></td>
               <td class="num"><input class="be-asm" data-f="mgmt" value="${esc(A.mgmt)}" style="width:50px;min-width:0;text-align:right;padding:1px 2px;font-size:12px"></td>
               <td class="num"><input class="be-asm" data-f="transport" value="${esc(A.transport)}" style="width:44px;min-width:0;text-align:right;padding:1px 2px;font-size:12px"></td>
               <td class="num"><input class="be-asm" data-f="profit" value="${esc(A.profit)}" style="width:44px;min-width:0;text-align:right;padding:1px 2px;font-size:12px"></td></tr>`;})():''}
             ${curIn!=null?`<tr style="background:#fef6e9">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#a06010">(가격조정)</td>
               <td class="cap" style="color:#a06010" title="판가(현재입고가) − 재료비 − 가공비">현재입고가 정합 조정</td>
               <td><span style="font-size:11px;padding:1px 6px;border-radius:8px;background:#fbe4cc;color:#a06010">조정</span></td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#a06010;font-weight:700" id="be-adjgag">${nf(adjust)}</td><td class="num" style="color:#a06010;font-weight:700" id="be-adjust">${nf(adjust)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>`:''}
             <tr><td colspan="${19+(d.proc_ops||[]).length}" style="height:0;border-top:3px solid #8a6d3b;padding:0"></td></tr>
             <tr style="background:#f0efe9"><td colspan="${19+(d.proc_ops||[]).length}" style="text-align:left;padding:5px 10px;color:#8a6d3b;font-size:12px;font-weight:700">📋 종전 견적 (인상전 · 종전사급가/작년12월 판매단가 · 읽기전용)</td></tr>
             <tr style="background:#faf9f4;font-weight:700">
               <td style="font-family:monospace;font-size:13px;padding-left:6px">${esc(d.item)}</td>
               <td class="cap" style="max-width:120px;overflow:hidden;text-overflow:ellipsis" title="${esc(d.name)}">${esc(d.name)}</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#8a6d3b;color:#fff">완제품</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num" style="color:#1c6ec2">${nf4(soyo)}</td><td class="num">-</td>
               <td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px">${nf(totMatB)}</td><td class="num" style="color:#5a6a80;font-weight:700">${totSaleB>0?Math.round(totMatB/totSaleB*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" title="종전 총가공비 = 종전입고가 − 종전재료비">${totGagB!=null?nf(totGagB):'-'}</td><td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px" title="종전 판가(종전입고가)">${totSaleB!=null?nf(totSaleB):'-'}${d.asof_prev_label?'<div style="font-size:8px;color:#8aa0bd;font-weight:400" title="종전입고가 실제 납품월(25/11 이하 최근 실거래일)">납품:'+esc(d.asof_prev_label)+'</div>':''}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>
             ${d.rows.map(r=>{const isTube=r.role==='제작동관';const isWeld=r.role==='용접봉';const uw=beUw(r);const ind=6+r.level*12;const pr=r.procs||{};
               const rq=(r.cum_qty||0);const rmatB=(r.mat_before!=null?r.mat_before:0);const rgag=isTube?beRowGagong(r):0;const rtotB=rmatB+rgag;
               const rratioB=rtotB>0?Math.round(rmatB/rtotB*100):(rmatB?100:0);const sagubPrev=(isTube&&uw&&rq)?Math.round(rmatB/(uw*rq)):(isWeld&&r.coop_sagub?+r.coop_sagub:null);const grey=r.in_quote===false;
               return `<tr>
                 <td style="font-family:monospace;font-size:12px;padding-left:${ind}px">${r.haskids?'▸':''}${esc(r.code)}</td>
                 <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td>
                 <td>${beBadge(r.role)}</td>
                 <td class="num">${nf4(rq)}</td>
                 <td class="num" style="color:#8aa0bd;font-size:11px">${r.lg_diam?('Φ'+r.lg_diam+'×'+r.lg_thick+'×'+r.lg_length):'-'}</td>
                 <td class="num" style="font-size:9px">${r.coop_diam||'-'}</td><td class="num" style="font-size:9px">${r.coop_thick||'-'}</td><td class="num" style="font-size:9px">${r.coop_length||'-'}</td>
                 <td class="num">${uw?nf4(uw):(isWeld?'<span style="color:#b8791f;font-size:9px">공정</span>':'-')}</td>
                 <td class="num" style="color:#1c6ec2">${(isTube&&uw)?nf4(uw*rq):'-'}</td>
                 <td class="num" style="color:#b8791f;font-weight:600">${(!be.viewMode&&isTube)?`<span class="be-prevsg" data-code="${esc(r.code)}" data-high="${(r.role_disp||'').indexOf('고강')>=0?1:0}" style="cursor:pointer;border-bottom:1px dashed #b8791f" title="클릭: 종전(인상전) 사급가 수정 · 일반CU 7550">${sagubPrev!=null?nf(sagubPrev):'입력'} ✎</span>`:(sagubPrev!=null?nf(sagubPrev):'-')}</td>
                 <td class="num" style="color:#8a6d3b;font-weight:700">${grey?('('+nf(rmatB)+')'):nf(rmatB)}${r.sale_note_prev?'<div style="font-size:8px;color:#8aa0bd" title="종전 판매단가 적용일(해당 업체)">'+esc(r.sale_note_prev)+'</div>':''}</td>
                 <td class="num" style="color:#8a6d3b">${grey?'-':rratioB+'%'}</td>
                 <td class="num" style="color:#1c7c3a">${isTube?nf(rgag):'-'}</td>
                 <td class="num" style="color:#8a6d3b;font-weight:700">${grey?'-':nf(rtotB)}</td>
                 ${(d.proc_ops||[]).map(op=>`<td class="num" style="font-size:11px;color:#6a3fb0">${(isTube&&pr[op])?pr[op]:''}</td>`).join('')}
                 <td class="num" style="color:#1c7c3a">${isTube?nf(rgag):'-'}</td>
                 <td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td><td class="num" style="color:#c9d1dc">-</td></tr>`;}).join('')}
             ${(be.asm||d.assembly_proc>0)?(()=>{const A=be.asm||{gagong:d.assembly_proc,mgmt:0,transport:0,profit:0};const atot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
               return `<tr style="background:#fff8ec">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#8a6d3b">(서브조립)</td>
               <td class="cap" style="color:#8a6d3b">서브ASSY 조립공정</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#fff3e0;color:#b8791f">조립공정</span></td>
               <td class="num">×1</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#1c7c3a;font-weight:700">${nf(atot)}</td><td class="num" style="color:#8a6d3b;font-weight:700">${nf(atot)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>`;})():''}
             ${prevIn!=null?`<tr style="background:#fef6e9">
               <td style="font-family:monospace;font-size:12px;padding-left:18px;color:#a06010">(가격조정)</td>
               <td class="cap" style="color:#a06010">종전입고가 정합 조정</td>
               <td><span style="font-size:10px;padding:1px 5px;border-radius:8px;background:#fbe4cc;color:#a06010">조정</span></td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num">-</td>
               <td class="num">-</td><td class="num">-</td><td class="num" style="color:#a06010;font-weight:700">${nf(adjustB)}</td><td class="num" style="color:#a06010;font-weight:700">${nf(adjustB)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>`:''}
             </tbody></table></div>
           `)}
         </div>
         <div style="padding:10px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="color:#8aa0bd;font-size:11px">구성=현 BOM(고정) · 제작동관 협력사 스펙만 입력 · 용접봉=공정(재료비 제외)</span>
           <span>${canEd?(be.viewMode?'<button class="btn" id="be-editmode" style="background:#1c7c3a;color:#fff">✏ 수정 (현재 견적)</button> ':'<button class="btn" id="be-save" style="background:#1b6ec2;color:#fff">💾 저장</button> '):''}<button class="btn" id="be-cancel">닫기</button></span></div>
       </div></div>`;})():''}
     <style>#cq-tbl tbody tr:hover{background:#eef4ff}.cq-row.sel{background:#dbe9ff}
       .be-view input,.be-view select{border:none!important;background:transparent!important;box-shadow:none!important;pointer-events:none;padding:0!important;margin:0!important;text-align:inherit;font:inherit;color:inherit;width:auto!important;min-width:0;height:auto!important;line-height:1.2!important;vertical-align:middle}
       .be-view input.inp,.be-view .be-qty,.be-view .be-sp,.be-view .be-sg,.be-view .be-mat,.be-view .be-pc,.be-view .be-asm,.be-view .be-asmpc{cursor:default}
       .be-view table.fit{width:max-content!important;min-width:0!important;table-layout:auto!important;font-size:11px}
       .be-view td,.be-view th{padding:0 6px!important;white-space:nowrap;line-height:1.6;height:auto!important;width:auto!important;min-width:0!important}
       .be-view tr{height:auto!important}
       .be-view input{max-width:56px!important}</style>`;
    const g=id=>host.querySelector(id);
    g('#cq-go').onclick=()=>{st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};
    {const cf=g('#cq-filter');if(cf)cf.onchange=e=>{st.filterMode=e.target.value;st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};}
    {const gw=g('#cq-work');if(gw)gw.onclick=()=>{st.workMode=!st.workMode;st.msg='';if(st.workMode)loadWork();else render();};}
    host.querySelectorAll('.cq-wrow').forEach(tr=>tr.onclick=()=>{const r=st.worklist[+tr.dataset.idx];if(r)openWork(r.assy_code,r.vendor);});
    g('#cq-xls').onclick=()=>{
      if(!st.rows.length){alert('다운로드할 데이터가 없습니다.');return;}
      const hd=['협력사','품번(Assy)','품명','규격','등급',
        '인상전_재료비','인상전_재료비율(%)','인상전_총가공비','인상전_입고가',
        '인상후_재료비','인상후_재료비율(%)','인상후_총가공비','인상후_입고가',
        '차이(신)=인상후−인상전 총가공비','최근납품','상태'];
      const fy=y=>y?('20'+y.slice(0,2)+'-'+y.slice(2,4)+'-'+y.slice(4,6)):'';
      const bl=v=>(v==null?'':v);
      const rows=st.rows.map(r=>[r.vendor,r.assy_code,r.item_name,r.spec,r.grade||'일반CU',
        bl(r.mat_before),bl(r.ratio_before),bl(r.proc_before),bl(r.incost_before),
        bl(r.mat_after),bl(r.ratio_after),bl(r.proc_after),bl(r.incost_after),
        bl(r.diff_new),fy(r.last_in_ymd),r.status]);
      const tag=(st.vendor||'전체')+(st.ym?'_'+st.ym:'')+(st.filterMode==='active'?'_현재납품':(st.filterMode==='new'?'_미승인':''));
      dlCSV('협력사견적_'+tag+'.csv',hd,rows);};
    g('#cq-vendor').onchange=()=>{st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};
    {const _g=host.querySelector('#cq-grid'); if(_g){ if(st._scroll!=null)_g.scrollTop=st._scroll; _g.onscroll=()=>{st._scroll=_g.scrollTop;}; }}  // 상세 열고닫아도 리스트 스크롤 유지
    {const cy=g('#cq-ym');if(cy)cy.onchange=()=>{st.ym=cy.value;st.vendor=g('#cq-vendor').value;st.q=g('#cq-q').value;st.msg='';load();};}
    g('#cq-q').onkeyup=e=>{if(e.key==='Enter')g('#cq-go').click();};
    // 메인 컬럼 더블클릭 정렬 (토글 asc/desc). 차이(신) 정렬=손익 이상치 찾기
    host.querySelectorAll('#cq-tbl thead th[data-sort]').forEach(th=>th.ondblclick=()=>{
      const k=th.dataset.sort;
      st.sortDir=(st.sortKey===k&&st.sortDir==='asc')?'desc':'asc';
      st.sortKey=k; const dir=st.sortDir==='asc'?1:-1;
      const isNum=st.rows.some(r=>typeof r[k]==='number');
      st.rows.sort((a,b)=>{
        let x=a[k],y=b[k];
        if(isNum){ x=(x==null?-Infinity:+x); y=(y==null?-Infinity:+y); return (x-y)*dir; }
        return String(x==null?'':x).localeCompare(String(y==null?'':y))*dir;
      });
      render();
    });
    if(st.sortKey){const sth=host.querySelector(`#cq-tbl thead th[data-sort="${st.sortKey}"]`);if(sth)sth.insertAdjacentHTML('beforeend',`<span style="color:#c0392b">${st.sortDir==='asc'?' ▲':' ▼'}</span>`);}
    if(canEd){
      g('#cq-new').onclick=()=>newBomEdit();
      host.querySelectorAll('.cq-chk').forEach(ch=>ch.onclick=(ev)=>{ev.stopPropagation();const id=+ch.dataset.id;ch.checked?st.sel.add(id):st.sel.delete(id);});
      host.querySelectorAll('.cq-edit').forEach(b=>b.onclick=(ev)=>{ev.stopPropagation();openBomEdit(+b.dataset.idx);});
    }
    if(modal){
      g('#cq-cancel').onclick=g('#cq-x').onclick=()=>{st.form=null;render();};
      g('#cq-save').onclick=save;
      host.querySelectorAll('.cf').forEach(el=>el.oninput=()=>{st.form[el.dataset.k]=el.value;
        const pm=g('#cq-pv-mat'),ps=g('#cq-pv-sale');if(pm)pm.textContent=nf(matOf(st.form));if(ps)ps.textContent=nf(saleOf(st.form));});
    }
    if(rc){
      g('#cq-rc-cancel').onclick=g('#cq-rx').onclick=()=>{st.recalc=null;render();};
      g('#cq-rc-pn').oninput=e=>st.recalc.price_normal=e.target.value;
      g('#cq-rc-ph').oninput=e=>st.recalc.price_high=e.target.value;
      host.querySelectorAll('input[name=cq-scope]').forEach(r=>r.onchange=()=>{st.recalc.scope=r.value;});
      g('#cq-rc-run').onclick=doRecalc;
    }
    if(be){
      const close=()=>{st.bomedit=null;render();};
      const bx=g('#be-x'),bc=g('#be-cancel');if(bx)bx.onclick=close;if(bc)bc.onclick=close;
      const nl=g('#be-load'),ni=g('#be-newitem');
      if(nl)nl.onclick=()=>{be.vendor=(g('#be-vendor')?g('#be-vendor').value:be.vendor);loadBomInto(ni.value,null);};
      if(ni)ni.onkeyup=e=>{if(e.key==='Enter')loadBomInto(ni.value,null);};
      const bs=g('#be-save');if(bs)bs.onclick=saveBomEdit;
      const bem=g('#be-editmode');if(bem)bem.onclick=()=>{st.bomedit.viewMode=false;render();};
      host.querySelectorAll('.be-role').forEach(sel=>sel.onchange=async()=>{const code=sel.dataset.code,role=sel.value;
        let prev_sagub=null;
        if(role==='제작동관'||role==='동관고강도'){   // ★제작동관 전환 시 종전(인상전) 사급가 직접 입력(일반CU 7550)
          const d=prompt('종전(인상전) 사급가 입력\n· 일반 CU: 7550\n· 고강도 등은 해당 종전 사급가\n(취소 시 7550 적용)', '7550');
          prev_sagub=(d===null?7550:(d.trim()||7550));
        }
        sel.disabled=true;
        try{await fetch(`${API}/api/coopquote2/set-role`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assy:be.assy,part:code,role,prev_sagub,unit_weight:sel.dataset.uw})});}catch(e){}
        loadBomInto(be.assy,(be.rowvals?be.rowvals.sale:(be.data&&be.data.cur_incost!=null?be.data.cur_incost:null)));});
      // ★종전사급가 클릭 편집(이미 제작동관인 건의 인상전 사급가 개별 수정 · 일반CU 7550)
      host.querySelectorAll('.be-prevsg').forEach(sp=>sp.onclick=async()=>{const code=sp.dataset.code;
        const cur0=(sp.textContent||'').replace(/[^\d]/g,'')||'7550';
        const d=prompt('종전(인상전) 사급가 입력 · 일반 CU = 7550\n(제작동관 인상전 재료비 = 소요중량 × 종전사급가)', cur0);
        if(d===null)return;const prev_sagub=(String(d).trim()||7550);const role=(sp.dataset.high==='1')?'동관고강도':'제작동관';
        try{await fetch(`${API}/api/coopquote2/set-role`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assy:be.assy,part:code,role,prev_sagub})});}catch(e){}
        loadBomInto(be.assy,(be.rowvals?be.rowvals.sale:(be.data&&be.data.cur_incost!=null?be.data.cur_incost:null)));});
      const upd=()=>{const soyo=beSoyo();const raw=beRaw();
        const baseMat=be.data.rows.filter(r=>r.role!=='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowMat(r),0);
        const procTube=be.data.rows.filter(r=>r.role==='제작동관'&&r.in_quote!==false).reduce((s,r)=>s+beRowGag(r),0);
        const A=be.asm||{gagong:be.data.assembly_proc||0,mgmt:0,transport:0,profit:0};const asmTot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
        const mat=raw+baseMat;const gagong=procTube+asmTot;const curIn=(be.data.cur_incost!=null)?be.data.cur_incost:null;
        const sale=(curIn!=null?curIn:(mat+gagong));const adjust=(curIn!=null?Math.round(curIn-mat-gagong):0);
        const set=(id,v)=>{const el=g(id);if(el)el.textContent=v;};
        set('#be-tsoyo',nf4(soyo));set('#be-tsoyo2',nf4(soyo));set('#be-traw',nf(raw));set('#be-tbase',nf(baseMat));set('#be-tmat',nf(mat));set('#be-tmat-root',nf(mat));
        set('#be-tgag',nf(gagong));set('#be-tadj',nf(adjust));set('#be-adjust',nf(adjust));set('#be-adjgag',nf(adjust));set('#be-tsale',nf(sale));set('#be-grandtot',nf(sale));set('#be-grandtot-l',nf(sale));
        set('#be-grandmat',nf(mat));set('#be-grandgag',nf(gagong+adjust));set('#be-tgag-root',nf(gagong+adjust));
        set('#be-tratio-root',(sale>0?Math.round(mat/sale*100):0)+'%');set('#be-tsale-root',nf(sale));};
      const beRefreshRow=(inp)=>{const code=inp.dataset.code;const r=be.data.rows.find(x=>x.code===code);if(!r)return;
        const tr=inp.closest('tr');const uw=beUw(r);const rq=beRowQty(r);const rmat=beRowMat(r);const rgag=beRowGag(r);const rtot=rmat+rgag;const rratio=rtot>0?Math.round(rmat/rtot*100):(rmat?100:0);
        const s=(cls,v)=>{const el=tr.querySelector('.'+cls);if(el)el.textContent=v;};
        s('be-uw',uw?nf4(uw):(r.role==='용접봉'?'공정':'-'));s('be-sw',uw?nf4(uw*rq):'-');
        s('be-rm',nf(rmat));s('be-ratio',rratio+'%');s('be-tot',nf(rtot));s('be-rg',nf(rgag));
        tr.style.background=(r.role==='제작동관'&&!uw)?'#fdf0f0':'';upd();};
      const bv=g('#be-vendor');if(bv){bv.oninput=e=>be.vendor=e.target.value;bv.onchange=e=>{be.vendor=e.target.value;if(be.data&&be.assy)loadBomInto(be.assy,null);};}
      host.querySelectorAll('.be-sg').forEach(inp=>inp.oninput=()=>{be.sagubEdits=be.sagubEdits||{};be.sagubEdits[inp.dataset.code]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-sp').forEach(inp=>inp.oninput=()=>{const code=inp.dataset.code,fld=inp.dataset.f;be.edits[code]=be.edits[code]||{};be.edits[code][fld]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-qty').forEach(inp=>inp.oninput=()=>{be.qtyEdits=be.qtyEdits||{};be.qtyEdits[inp.dataset.code]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-mat').forEach(inp=>inp.oninput=()=>{be.matEdits=be.matEdits||{};be.matEdits[inp.dataset.code]=inp.value;beRefreshRow(inp);});
      host.querySelectorAll('.be-pc').forEach(inp=>inp.oninput=()=>{const code=inp.dataset.code,op=inp.dataset.op;be.procEdits[code]=be.procEdits[code]||{};be.procEdits[code][op]=inp.value;beRefreshRow(inp);});
      const asmUpd=()=>{if(!be.asm)return;const A=be.asm;const atot=Math.round((+A.gagong||0)+(+A.mgmt||0)+(+A.transport||0)+(+A.profit||0));
        const t=g('#be-asmtot');if(t)t.textContent=nf(atot);upd();};
      host.querySelectorAll('.be-asm').forEach(inp=>inp.oninput=()=>{be.asm=be.asm||{procs:{},gagong:0,mgmt:0,transport:0,profit:0};be.asm[inp.dataset.f]=inp.value;asmUpd();});
      host.querySelectorAll('.be-asmpc').forEach(inp=>inp.oninput=()=>{be.asm=be.asm||{procs:{},gagong:0,mgmt:0,transport:0,profit:0};be.asm.procs=be.asm.procs||{};be.asm.procs[inp.dataset.op]=inp.value;
        const rate=be.data.rate||{};const lab=be.data.labor_rate||6300;let gg=0;
        Object.keys(be.asm.procs).forEach(op=>{const c=+be.asm.procs[op]||0;const dv=rate[op];if(c&&dv)gg+=(lab/dv)*c;});
        be.asm.gagong=Math.round(gg);const gi=host.querySelector('.be-asm[data-f="gagong"]');if(gi)gi.value=be.asm.gagong;asmUpd();});
    }
    attachResizers(host);
  };
  (async()=>{await loadVendors();load();})();
};

/* ===== 견적입력 (BOM 구성 자동 + 협력사 스펙만 채움) — /api/coopquote/bom-form·bom-save ===== */
SCREEN.coopquoteinput=(host)=>{
  const API=API_BASE;
  const st={item:'',data:null,loading:false,msg:'',vendor:'',grade:'일반CU',sagub:20000,proc:0,vendors:[],edits:{},sagubEdits:{}};
  const nf=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf4=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const ed=()=>(typeof PERM!=='undefined')?PERM.canEdit('coopquote'):true;
  const geom=(d,t,L)=>(d&&t&&L)?Math.PI*(d-t)*t*L*8.94/1e6:0;
  const loadVendors=async()=>{try{const r=await fetch(`${API}/api/coopquote/vendors`);const j=await r.json();st.vendors=j.rows||[];}catch(e){}};
  const load=async()=>{const it=st.item.trim();if(!it)return;st.loading=true;st.edits={};st.msg='';render();
    try{const r=await fetch(`${API}/api/coopquote/bom-form?item=${encodeURIComponent(it)}`);const j=await r.json();st.data=j;}
    catch(e){st.data=null;st.msg='조회 실패: '+e.message;}
    st.loading=false;render();};
  // 현재 편집 반영 개당중량
  const uwOf=(r)=>{const e=st.edits[r.code];
    if(r.role!=='제작동관')return 0;
    if(e&&(e.diam||e.thick||e.length)){const d=+e.diam||r.coop_diam||r.lg_diam,t=+e.thick||r.coop_thick||r.lg_thick,L=+e.length||r.coop_length||r.lg_length;return geom(d,t,L);}
    return r.unit_weight||0;};
  const totalSoyo=()=>!st.data?0:st.data.rows.filter(r=>r.role==='제작동관').reduce((s,r)=>s+uwOf(r)*r.cum_qty,0);
  // ★관경별 사급가: 행 입력 → 저장된 관경별 → 헤더 기본 순
  const rowSagub=(r)=>{const e=st.sagubEdits&&st.sagubEdits[r.code];
    if(e!=null&&e!=='')return +e||0;
    if(r.coop_sagub&&+r.coop_sagub>0)return +r.coop_sagub;
    return +st.sagub||0;};
  const matRaw=()=>!st.data?0:Math.round(st.data.rows.filter(r=>r.role==='제작동관').reduce((s,r)=>s+uwOf(r)*r.cum_qty*rowSagub(r),0));
  const save=async()=>{
    if(!st.data)return;if(!st.vendor.trim()){alert('협력사를 입력/선택하세요.');return;}
    const specs=st.data.rows.filter(r=>r.role==='제작동관').map(r=>{const e=st.edits[r.code]||{};
      return {code:r.code,diam:(+e.diam||r.coop_diam||r.lg_diam),thick:(+e.thick||r.coop_thick||r.lg_thick),length:(+e.length||r.coop_length||r.lg_length),sagub:rowSagub(r)};})
      .filter(s=>s.diam&&s.thick&&s.length);
    const body={item:st.data.item,vendor:st.vendor.trim(),grade:st.grade,sagub_price:+st.sagub||0,proc_cost:(Math.round(+st.proc||0)+weldCost()),item_name:st.data.name,specs};
    try{const r=await fetch(`${API}/api/coopquote/bom-save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'save');
      st.msg=`✔ 저장 완료 · 스펙갱신 ${j.spec_updated}건 · 소요중량 ${nf4(j.total_soyo_weight)}kg · 원소재비 ${nf(j.mat_cost)} · 판가 ${nf(j.sale_price)}`;
      await load();}
    catch(e){alert('저장 실패: '+e.message);}};
  const roleBadge=(role)=>{const M={'제작동관':['#e8f3ec','#1c7c3a'],'사급':['#eef2f7','#5a6a80'],'용접봉':['#fff3e0','#b8791f'],'매입부품':['#f0ecfa','#6a3fb0'],'반제품':['#e8eef7','#1c47a0']};
    const c=M[role]||['#eee','#555'];return `<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:${c[0]};color:${c[1]};white-space:nowrap">${role}</span>`;};
  const weldCost=()=>!st.data?0:Math.round(st.data.total_weld_cost||0);
  const render=()=>{
    const canEd=ed();const d=st.data;const soyo=totalSoyo();const mat=matRaw();
    const weld=weldCost();const sale=mat+Math.round(+st.proc||0)+weld;
    host.innerHTML=`
     <div class="page-title">📝 견적입력 <span style="font-size:12px;color:var(--muted);font-weight:400">현 BOM 자동구성 · 협력사 원소재 스펙만 입력 → 소요중량·판가 자동</span></div>
     <div class="page-sub">품번을 조회하면 <b>현 BOM(CS_M_ITEM_BOM)</b> 구성이 그대로 펼쳐집니다. <b style="color:#1c7c3a">제작동관</b> 행의 <b>협력사 외경·두께·길이</b>만 채우면 개당중량·소요중량이 자동 계산됩니다. (사급/용접봉/매입부품은 매입가 자동)</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:6px">
       <label class="tl">품번</label><input class="inp" id="qi-item" value="${esc(st.item)}" placeholder="Assy 품번" style="width:190px;font-family:monospace">
       <button class="btn" id="qi-go">🔍 BOM 불러오기</button>
       ${d?`<span style="margin-left:8px;font-weight:600">${esc(d.name||'')}</span>
         ${d.already_quoted?'<span style="font-size:11px;color:#1c7c3a;background:#e3f5e9;padding:1px 7px;border-radius:8px">기존견적 있음</span>':'<span style="font-size:11px;color:#b8791f;background:#fbe9d0;padding:1px 7px;border-radius:8px">신규</span>'}
         ${d.need_input?`<span style="font-size:11px;color:#c0392b;background:#fdecec;padding:1px 7px;border-radius:8px">스펙 입력필요 ${d.need_input}건</span>`:'<span style="font-size:11px;color:#1c7c3a">스펙 완비</span>'}`:''}
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${!d?`<div class="empty" style="padding:40px;text-align:center;color:#8aa0bd">품번을 입력하고 BOM을 불러오세요.</div>`:`
     <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:6px 0;font-size:12px;background:#f4f8ff;border:1px solid #dbe6f7;border-radius:8px;padding:8px 12px">
       <label style="color:#33507d;font-weight:600">협력사</label>
       <input class="inp" id="qi-vendor" list="qi-vlist" value="${esc(st.vendor)}" placeholder="협력사" style="width:130px">
       <datalist id="qi-vlist">${st.vendors.map(v=>`<option value="${esc(v.vendor)}">`).join('')}</datalist>
       <label style="color:#33507d;font-weight:600">등급</label>
       <select class="inp" id="qi-grade" style="width:100px"><option value="일반CU" ${st.grade!=='고강도CU'?'selected':''}>일반CU</option><option value="고강도CU" ${st.grade==='고강도CU'?'selected':''}>고강도CU</option></select>
       <label style="color:#33507d;font-weight:600" title="관경별 사급가 미입력 행에 적용되는 기본값(일괄)">기본사급가(원/kg)</label><input class="inp" id="qi-sagub" type="number" step="any" value="${esc(st.sagub)}" style="width:90px;text-align:right">
       <label style="color:#33507d;font-weight:600">가공비(고정)</label><input class="inp" id="qi-proc" type="number" step="any" value="${esc(st.proc)}" style="width:90px;text-align:right">
     </div>
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th>품번</th><th>품명</th><th>역할</th><th class="num">소요량</th>
        <th class="num" style="color:#8aa0bd">LG(Φ×T×L)</th>
        <th class="num" style="color:#1c7c3a">협력사 Φ</th><th class="num" style="color:#1c7c3a">T</th><th class="num" style="color:#1c7c3a">L</th>
        <th class="num">개당중량</th><th class="num" style="color:#1c6ec2">소요중량</th><th class="num">매입가</th><th class="num" style="color:#b8791f" title="관경별 사급가(원/kg) — 직원 직접입력">사급가</th></tr></thead>
      <tbody>${st.loading?spinRow(12):d.rows.map(r=>{
        const isTube=r.role==='제작동관';const e=st.edits[r.code]||{};
        const dd=(e.diam!=null&&e.diam!=='')?e.diam:(r.coop_diam||'');
        const tt=(e.thick!=null&&e.thick!=='')?e.thick:(r.coop_thick||'');
        const ll=(e.length!=null&&e.length!=='')?e.length:(r.coop_length||'');
        const uw=uwOf(r);const need=isTube&&!(dd&&tt&&ll);
        const ind=8+(r.level-1)*14;
        return `<tr style="${need?'background:#fdf0f0':''}">
          <td style="font-family:monospace;font-size:10px;padding-left:${ind}px">${r.haskids?'▸ ':''}${esc(r.code)}</td>
          <td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td>
          <td>${roleBadge(r.role)}</td>
          <td class="num">×${nf4(r.cum_qty)}</td>
          <td class="num" style="color:#8aa0bd;font-size:10px">${r.lg_diam?('Φ'+r.lg_diam+'×'+r.lg_thick+'×'+r.lg_length):'-'}</td>
          ${isTube&&canEd?`<td class="num"><input class="qi-sp inp" data-code="${esc(r.code)}" data-f="diam" value="${esc(dd)}" style="width:52px;text-align:right;padding:1px 3px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_diam||''}"></td>
            <td class="num"><input class="qi-sp inp" data-code="${esc(r.code)}" data-f="thick" value="${esc(tt)}" style="width:44px;text-align:right;padding:1px 3px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_thick||''}"></td>
            <td class="num"><input class="qi-sp inp" data-code="${esc(r.code)}" data-f="length" value="${esc(ll)}" style="width:52px;text-align:right;padding:1px 3px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_length||''}"></td>`
            :`<td class="num" style="font-size:10px">${dd||'-'}</td><td class="num" style="font-size:10px">${tt||'-'}</td><td class="num" style="font-size:10px">${ll||'-'}</td>`}
          <td class="num qi-uw">${uw?nf4(uw):(r.role==='용접봉'?'<span style="color:#b8791f;font-size:9px">공정</span>':'-')}</td>
          <td class="num qi-sw" style="color:#1c6ec2">${(isTube&&uw)?nf4(uw*r.cum_qty):(r.role==='용접봉'?'<span style="color:#b8791f" title="용접봉=공정 부자재비(재료비 제외)">↳가공비 ${nf(r.weld_cost)}</span>':'-')}</td>
          <td class="num">${r.pur_price!=null?nf(r.pur_price):'-'}</td>
          <td class="num">${isTube&&canEd?`<input class="qi-sg inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc((st.sagubEdits&&st.sagubEdits[r.code]!=null&&st.sagubEdits[r.code]!=='')?st.sagubEdits[r.code]:(r.coop_sagub>0?r.coop_sagub:''))}" placeholder="${esc(st.sagub||'')}" style="width:58px;text-align:right;padding:1px 3px;color:#b8791f;font-weight:600" title="관경별 사급가(원/kg). 비우면 기본사급가 적용">`:(isTube?(r.coop_sagub>0?nf(r.coop_sagub):'<span style="color:#c9d1dc">-</span>'):'<span style="color:#c9d1dc">-</span>')}</td></tr>`;}).join('')}</tbody></table></div>
     <div style="margin-top:8px;background:#eef4ff;border:1px solid #cdddf5;border-radius:8px;padding:10px 16px;font-size:13px;display:flex;gap:16px;justify-content:flex-end;align-items:center;flex-wrap:wrap">
       <span>총 소요중량 <b id="qi-tsoyo" style="color:#1c6ec2">${nf4(soyo)}</b> kg</span>
       <span style="color:#8aa0bd">× 관경별 사급가 =</span>
       <span>원소재비 <b id="qi-tmat" style="color:#1c6ec2">${nf(mat)}</b></span>
       <span style="color:#8aa0bd">+ 가공비 ${nf(st.proc)}</span>
       <span style="color:#b8791f">+ 용접봉(공정) <b id="qi-tweld">${nf(weld)}</b></span>
       <span style="color:#8aa0bd">=</span>
       <span>판가 <b id="qi-tsale" style="font-size:15px">${nf(sale)}</b></span>
       ${canEd?`<button class="btn" id="qi-save" style="background:#1b6ec2;color:#fff">💾 견적 저장</button>`:'<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>'}
     </div>`}`;
    const g=id=>host.querySelector(id);
    g('#qi-go').onclick=()=>{st.item=g('#qi-item').value;load();};
    g('#qi-item').onkeyup=e=>{if(e.key==='Enter'){st.item=e.target.value;load();}};
    if(d){
      const upd=()=>{const soyo=totalSoyo();const mat=matRaw();const sale=mat+Math.round(+st.proc||0)+weldCost();
        const a=g('#qi-tsoyo'),b=g('#qi-tmat'),c=g('#qi-tsale');if(a)a.textContent=nf4(soyo);if(b)b.textContent=nf(mat);if(c)c.textContent=nf(sale);};
      const gv=g('#qi-vendor');if(gv)gv.oninput=e=>st.vendor=e.target.value;
      const gg=g('#qi-grade');if(gg)gg.onchange=e=>st.grade=e.target.value;
      const gs=g('#qi-sagub');if(gs)gs.oninput=e=>{st.sagub=e.target.value;host.querySelectorAll('.qi-sg').forEach(i=>i.placeholder=e.target.value);upd();};
      host.querySelectorAll('.qi-sg').forEach(inp=>inp.oninput=()=>{st.sagubEdits=st.sagubEdits||{};st.sagubEdits[inp.dataset.code]=inp.value;upd();});
      const gp=g('#qi-proc');if(gp)gp.oninput=e=>{st.proc=e.target.value;upd();};
      host.querySelectorAll('.qi-sp').forEach(inp=>inp.oninput=()=>{
        const code=inp.dataset.code,f=inp.dataset.f;st.edits[code]=st.edits[code]||{};st.edits[code][f]=inp.value;
        // 해당 행 개당/소요중량 갱신
        const tr=inp.closest('tr');const r=d.rows.find(x=>x.code===code);const uw=uwOf(r);
        const uwc=tr.querySelector('.qi-uw'),swc=tr.querySelector('.qi-sw');
        if(uwc)uwc.textContent=uw?nf4(uw):'-';if(swc)swc.textContent=uw?nf4(uw*r.cum_qty):'-';
        tr.style.background=(uw)?'':'#fdf0f0';upd();});
      const sv=g('#qi-save');if(sv)sv.onclick=save;
    }
    attachResizers(host);
  };
  (async()=>{await loadVendors();render();})();
};

/* ===== 기준정보: 업체별 재고금액 (월재고 스냅샷 → 매입처 집계, 라이브) ===== */
SCREEN.stockval=(c)=>{
  const API=API_BASE;
  let ym='', months=[], sum={rows:[],sum_amt:0,cnt:0}, sel=null, det=null, loading=false, dloading=false, msg='';
  const ymd=s=>(s&&(''+s).length===4)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}`:(s||'');
  const load=async()=>{loading=true;sel=null;det=null;draw();
    try{const r=await fetch(`${API}/api/stockval/list?ym=${encodeURIComponent(ym)}`);sum=await r.json();ym=sum.ym;months=sum.months||[];msg='';}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010';sum={rows:[],sum_amt:0,cnt:0};}
    loading=false;draw();};
  const loadDet=async(incust)=>{sel=incust;dloading=true;draw();
    try{const r=await fetch(`${API}/api/stockval/list?ym=${encodeURIComponent(ym)}&incust=${encodeURIComponent(incust)}`);det=await r.json();}
    catch(e){det={rows:[],sum_amt:0};}
    dloading=false;draw();};
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">🏷️ 업체별 재고금액 <span style="font-size:12px;color:var(--muted);font-weight:400">매입처별 월말 재고자산</span></div>
     <div class="page-sub">월재고 스냅샷을 <b>매입처(IN_CUST)</b> 기준으로 집계. 원본 <code>PU_T_MONTH_STOCK_WH</code>(라이브·읽기전용) · MAT→<code>PR_M_ITEM.IN_CUST_CODE</code> 매핑 · 좌측 업체 클릭 → 자재명세</div>
     <div class="toolbar">
       <label class="tl">기준월</label><select class="inp" id="sv-ym">${months.map(m=>`<option value="${m}"${m===ym?' selected':''}>${ymd(m)}</option>`).join('')}</select>
       <button class="btn" id="sv-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">업체 ${won(sum.cnt)}개 · 재고자산 총 <b>${won(sum.sum_amt)}</b>원</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div style="display:flex;gap:14px;align-items:flex-start">
      <div style="flex:0 0 460px;min-width:0">
       <div class="summary-bar"><div class="s-item"><b>매입처별 재고금액</b> (${ymd(ym)})</div></div>
       <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" style="font-size:11px"><thead><tr><th>매입처</th><th class="num">품목수</th><th class="num">재고수량</th><th class="num">재고금액</th></tr></thead>
        <tbody>${loading?spinRow(4):((sum.rows&&sum.rows.length)?sum.rows.map(r=>`<tr class="sv-row${sel===r.incust?' sel':''}" data-cc="${esc(r.incust)}" style="cursor:pointer">
          <td><b>${esc(r.nm||r.incust||'(미지정)')}</b></td><td class="num">${won(r.items)}</td><td class="num">${won(r.qty)}</td><td class="num"><b>${won(r.amt)}</b></td></tr>`).join(''):`<tr><td colspan="4" class="empty">데이터 없음</td></tr>`)}</tbody></table>
       </div>
      </div>
      <div style="flex:1;min-width:0">
       ${sel!=null?`<div class="summary-bar"><div class="s-item"><b>${esc((sum.rows.find(x=>x.incust===sel)||{}).nm||sel||'(미지정)')}</b> 자재명세 ${det?`· ${won(det.cnt)}건 · ${won(det.sum_amt)}원`:''}</div></div>
        <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
         <table class="tbl" style="font-size:11px"><thead><tr><th>자재코드</th><th>품명</th><th>규격</th><th class="center">단위</th><th class="num">재고수량</th><th class="num">단가</th><th class="num">재고금액</th></tr></thead>
         <tbody>${dloading?spinRow(7):((det&&det.rows&&det.rows.length)?det.rows.map(r=>`<tr>
           <td><b>${esc(r.mat)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
           <td>${esc(r.spec)}</td><td class="center">${esc(r.unit)}</td><td class="num">${won(r.qty)}</td><td class="num">${won(r.cost)}</td><td class="num"><b>${won(r.amt)}</b></td></tr>`).join(''):`<tr><td colspan="7" class="empty">자재 없음</td></tr>`)}</tbody></table>
        </div>`
       :`<div class="empty" style="margin-top:40px">← 좌측에서 매입처를 선택하면 자재명세가 표시됩니다.</div>`}
      </div>
     </div>
     <style>.sv-row.sel{background:#e8f0ff}.sv-row:hover{background:#eef4ff}</style>`;
    const g=id=>c.querySelector(id);
    g('#sv-ym').onchange=e=>{ym=e.target.value;};
    g('#sv-go').onclick=load;
    c.querySelectorAll('.sv-row').forEach(el=>el.onclick=()=>loadDet(el.dataset.cc));
  };
  load();
};

/* ===== 자동발주 (생산계획+주문 → MRP → 조달배분 → 업체별 PO 자동생성) — nx.auto_po ===== */
/* 소요원천=정본 자재소요(nx.plan_part_mat 100%검증)+조달프로파일 오버레이(nx.plan_mat_source). 미리보기+확정 분리. 단가=마스터 매입단가(읽기전용). */
SCREEN.autoorder=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const won=n=>'₩'+nf(n);
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('autoorder'):true;
  const GB={'매입':'#1c47a0','유상사급':'#7a4ca0','외주가공':'#b8860b','외주완성':'#8a6d00','미지정':'#c0392b'};
  let tab='preview', F={line:'',cr:'',vendor:'',item:'',gubun:'',ymd:''};
  let pos=[], summary=null, loading=false, msg='', sel=new Set(), open=new Set();
  let heads=[], detail=null, dpo='';
  const loadPrev=async()=>{loading=true;msg='';draw();
    const qs=new URLSearchParams({line:F.line,cr:F.cr,vendor:F.vendor,item:F.item,gubun:F.gubun,ymd:F.ymd});
    try{const r=await fetch(`${API}/api/autoorder/preview?${qs}`);const j=await r.json();
      pos=j.pos||[];summary=j.summary||null;sel=new Set(pos.filter(p=>!p.no_vendor).map(p=>p.vendor_code));}
    catch(e){msg='백엔드 연결 실패';pos=[];summary=null;}
    loading=false;draw();};
  const loadList=async()=>{loading=true;msg='';draw();
    try{const r=await fetch(`${API}/api/autoorder/list`);const j=await r.json();heads=j.rows||[];}
    catch(e){msg='조회 실패';heads=[];}
    loading=false;draw();};
  const loadDetail=async(po)=>{dpo=po;detail=null;draw();
    try{const r=await fetch(`${API}/api/autoorder/list?po_no=${encodeURIComponent(po)}`);const j=await r.json();detail=j.lines||[];}
    catch(e){detail=[];}
    draw();};
  const confirm_=async()=>{
    const vlist=[...sel];
    if(!vlist.length){alert('확정할 발주업체를 선택하세요(미지정 업체는 확정 불가).');return;}
    const totAmt=pos.filter(p=>sel.has(p.vendor_code)).reduce((s,p)=>s+p.total_amt,0);
    const totLn=pos.filter(p=>sel.has(p.vendor_code)).reduce((s,p)=>s+p.line_count,0);
    if(!confirm(`선택 업체 ${vlist.length}곳 · 라인 ${nf(totLn)} · 금액 ${won(totAmt)}\n자동발주(PO)를 생성합니다. (nx 저장 · 실제 외부발송 아님)\n순소요 = 소요 − 이미 확정된 발주. 진행할까요?`))return;
    try{const r=await fetch(`${API}/api/autoorder/confirm`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({line:F.line,cr:F.cr,vendor:F.vendor,item:F.item,gubun:F.gubun,ymd:F.ymd,vendors:vlist,user:(typeof ME!=='undefined'?ME:'')})});
      const j=await r.json();
      if(j.ok){alert(`✅ 자동발주 생성 완료\n배치 ${j.batch}\nPO ${nf(j.po_count)}건 · 라인 ${nf(j.line_count)} · 금액 ${won(j.total_amt)}${j.skipped_novendor?('\n(발주업체 미지정 '+nf(j.skipped_novendor)+'라인 제외)'):''}`);loadPrev();}
      else alert('확정 실패: '+(j.error||JSON.stringify(j)));}
    catch(e){alert('확정 오류: '+e);}
  };
  const cancelPo=async(po)=>{if(!confirm(`${po} 발주를 취소(status=취소)합니다. 취소분은 재발주 가능.`))return;
    try{const r=await fetch(`${API}/api/autoorder/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({po_no:po})});
      const j=await r.json();if(j.ok){alert('취소 완료');loadList();}else alert('취소 실패');}catch(e){alert('오류 '+e);}};
  const draw=()=>{
    const gubOpts=['','매입','유상사급','외주가공','외주완성','미지정'].map(g=>`<option value="${g}"${F.gubun===g?' selected':''}>${g||'전체'}</option>`).join('');
    const crOpts=[['','전체'],['C','C(SAC)'],['R','R(RAC)']].map(o=>`<option value="${o[0]}"${F.cr===o[0]?' selected':''}>${o[1]}</option>`).join('');
    const bar=summary?`<span class="rowcount">업체 <b>${nf(summary.vendor_count)}</b> · 발주라인 <b>${nf(summary.line_count)}</b> · 수량 <b>${nf(summary.total_qty)}</b> · 금액 <b style="color:#1c7c3a">${won(summary.total_amt)}</b>${summary.novendor_lines?` · <span style="color:#c0392b">미지정 ${nf(summary.novendor_lines)}라인</span>`:''}</span>`:'';
    const selAmt=pos.filter(p=>sel.has(p.vendor_code)).reduce((s,p)=>s+p.total_amt,0);
    const cards=pos.map((p,pi)=>{
      const isOpen=open.has(p.vendor_code||('__nv'+pi));
      const ok=p.no_vendor?'':`<input type="checkbox" class="ao-sel" data-vc="${esc(p.vendor_code)}" ${sel.has(p.vendor_code)?'checked':''} style="transform:scale(1.15)">`;
      const head=`<tr class="ao-head${p.no_vendor?' nv':''}" data-k="${esc(p.vendor_code||('__nv'+pi))}" style="cursor:pointer;background:${p.no_vendor?'#fdecec':'#eef4ff'};font-weight:600">
        <td style="width:26px" onclick="event.stopPropagation()">${ok}</td>
        <td>${isOpen?'▼':'▶'} <b>${esc(p.vendor_name)}</b> ${p.no_vendor?'':`<span style="color:#8aa0bd;font-size:11px">${esc(p.vendor_code)}</span>`}</td>
        <td class="num">${nf(p.line_count)}</td><td class="num">${nf(p.total_qty)}</td><td class="num"><b>${won(p.total_amt)}</b></td></tr>`;
      const body=isOpen?p.lines.map(l=>`<tr>
        <td></td><td style="padding-left:18px"><b>${esc(l.item_code)}</b> <span class="bcap" title="${esc(l.item_name)}" style="color:#5a6a80">${esc(l.item_name)}</span>
          <span style="color:${GB[l.supply_gubun]||'#333'};font-size:11px">·${esc(l.supply_gubun)}</span>${l.overridden?' <span style="color:#b8860b;font-size:10px" title="발주업체 override(R01)">◆override</span>':''}${l.no_price?' <span style="color:#c0392b;font-size:10px">단가없음</span>':''}</td>
        <td class="num">${nf(l.order_qty)}${l.already_qty?`<span style="color:#8aa0bd;font-size:10px" title="이미 발주 차감">(−${nf(l.already_qty)})</span>`:''}</td>
        <td class="num">${l.unit_price==null?'-':nf(l.unit_price)}</td><td class="num">${won(l.amt)}</td></tr>`).join(''):'';
      return head+body;
    }).join('');
    const listBody=loading?`<tr><td colspan="8" class="empty">조회 중…</td></tr>`:(heads.length?heads.map(h=>`<tr class="ao-lrow" data-po="${esc(h.po_no)}" style="cursor:pointer">
        <td><b>${esc(h.po_no)}</b></td><td>${esc(h.vendor_name)}</td><td><span style="color:${GB[h.supply_gubun]||'#333'}">${esc(h.supply_gubun)}</span></td>
        <td class="center">${esc(h.po_ymd)}</td><td class="num">${nf(h.line_count)}</td><td class="num">${nf(h.total_qty)}</td><td class="num"><b>${won(h.total_amt)}</b></td>
        <td class="center">${h.status==='취소'?'<span style="color:#c0392b">취소</span>':'<span style="color:#1c7c3a">확정</span>'}${(canW&&h.status!=='취소')?` <button class="btn ghost ao-cancel" data-po="${esc(h.po_no)}" style="font-size:10px;padding:1px 5px" onclick="event.stopPropagation()">취소</button>`:''}</td></tr>`).join(''):`<tr><td colspan="8" class="empty">${msg||'확정된 자동발주 없음 — [미리보기·확정] 탭에서 생성하세요.'}</td></tr>`);
    c.innerHTML=`
     <div class="page-title">🛒 자동발주 <span style="font-size:12px;color:var(--muted);font-weight:400">생산계획+주문 → 자재소요(MRP) → 조달배분 → 업체별 PO</span></div>
     <div class="page-sub">정본 자재소요(<code>nx.plan_part_mat</code>, STEP5→6→7 100%검증) + 조달프로파일 오버레이(<code>nx.plan_mat_source</code>) → 업체별 순소요·단가·금액. 단가=마스터 매입단가(<code>PR_M_ITEM_COST</code> as-of·읽기전용). 순소요=소요−확정발주. 자체·용접봉 제외. PO=<code>nx.auto_po</code>(dev·외부발송 아님).</div>
     <div id="ao-tabs" style="display:flex;gap:4px;padding:4px 0 0;border-bottom:2px solid #dce3ee;margin-bottom:8px">
       ${[['preview','🧮 미리보기·확정'],['list','📋 발주조회']].map(t=>`<button class="btn ${tab===t[0]?'':'ghost'}" data-tab="${t[0]}" style="border-radius:8px 8px 0 0;${tab===t[0]?'background:#1c47a0;color:#fff':''}">${t[1]}</button>`).join('')}</div>
     ${tab==='preview'?`
     <div class="toolbar">
       <label class="tl">라인</label><input class="inp" id="ao-line" value="${esc(F.line)}" placeholder="예 CG" style="width:70px" autocomplete="off">
       <label class="tl">구분</label><select class="inp" id="ao-cr">${crOpts}</select>
       <label class="tl">공급방식</label><select class="inp" id="ao-gubun">${gubOpts}</select>
       <label class="tl">공급처</label><input class="inp" id="ao-vendor" value="${esc(F.vendor)}" placeholder="업체코드" style="width:80px" autocomplete="off">
       <label class="tl">자재</label><input class="inp" id="ao-item" value="${esc(F.item)}" placeholder="자재코드/명" style="width:120px" autocomplete="off">
       <label class="tl">기준일</label><input class="inp" id="ao-ymd" value="${esc(F.ymd)}" placeholder="YYMMDD(단가)" style="width:90px" autocomplete="off">
       <button class="btn" id="ao-prev" style="background:#1c47a0;color:#fff">🧮 미리보기</button>
       ${canW?`<button class="btn" id="ao-conf" style="background:#1c7c3a;color:#fff">✅ 선택 발주 확정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 발주 권한 없음</span>`}
     </div>
     <div class="toolbar" style="margin-top:2px">${bar}${sel.size?` · <span style="color:#1c7c3a">선택 ${nf(sel.size)}업체 ${won(selAmt)}</span>`:''}</div>
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:12px"><thead><tr><th style="width:26px"></th><th>발주업체 / 자재</th><th class="num">발주수량</th><th class="num">단가</th><th class="num">금액</th></tr></thead>
      <tbody>${loading?`<tr><td colspan="5" class="empty">산출 중…</td></tr>`:(pos.length?cards:`<tr><td colspan="5" class="empty">${msg||'미리보기를 실행하세요. (생산계획업로드 → 🧾자재소요·조달 편성이 선행되어야 함)'}</td></tr>`)}</tbody></table></div>`
     :`
     <div class="toolbar"><button class="btn" id="ao-lgo">🔄 새로고침</button>${detail!==null?`<button class="btn ghost" id="ao-back">◀ 목록</button> <span class="rowcount">PO <b>${esc(dpo)}</b> 명세</span>`:''}</div>
     <div class="grid-wrap" style="max-height:calc(100vh - 260px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${detail!==null?`<table class="tbl" style="font-size:12px"><thead><tr><th>자재</th><th>품명</th><th>공급방식</th><th class="num">소요</th><th class="num">기발주</th><th class="num">발주수량</th><th class="num">단가</th><th class="num">금액</th></tr></thead>
       <tbody>${detail.length?detail.map(l=>`<tr><td><b>${esc(l.item_code)}</b></td><td class="bcap" title="${esc(l.item_name)}">${esc(l.item_name)}</td><td><span style="color:${GB[l.supply_gubun]||'#333'}">${esc(l.supply_gubun)}</span></td><td class="num">${nf(l.req_qty)}</td><td class="num">${nf(l.already_qty)}</td><td class="num"><b>${nf(l.order_qty)}</b></td><td class="num">${l.unit_price==null?'-':nf(l.unit_price)}</td><td class="num">${won(l.amt)}</td></tr>`).join(''):`<tr><td colspan="8" class="empty">라인 없음</td></tr>`}</tbody></table>`
      :`<table class="tbl" style="font-size:12px"><thead><tr><th>PO번호</th><th>발주업체</th><th>공급방식</th><th>발주일</th><th class="num">라인</th><th class="num">수량</th><th class="num">금액</th><th>상태</th></tr></thead><tbody>${listBody}</tbody></table>`}</div>`}`;
    const g=id=>c.querySelector(id);
    c.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{if(tab!==b.dataset.tab){tab=b.dataset.tab;detail=null;if(tab==='list')loadList();else draw();}});
    if(tab==='preview'){
      const rd=()=>{F.line=g('#ao-line').value.trim();F.cr=g('#ao-cr').value;F.gubun=g('#ao-gubun').value;F.vendor=g('#ao-vendor').value.trim();F.item=g('#ao-item').value.trim();F.ymd=g('#ao-ymd').value.trim();};
      g('#ao-prev').onclick=()=>{rd();loadPrev();};
      if(g('#ao-conf'))g('#ao-conf').onclick=()=>{rd();confirm_();};
      ['#ao-line','#ao-vendor','#ao-item','#ao-ymd'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter'){rd();loadPrev();}});
      c.querySelectorAll('.ao-head').forEach(el=>el.onclick=()=>{const k=el.dataset.k;if(open.has(k))open.delete(k);else open.add(k);draw();});
      c.querySelectorAll('.ao-sel').forEach(el=>el.onclick=e=>{e.stopPropagation();const vc=el.dataset.vc;if(el.checked)sel.add(vc);else sel.delete(vc);draw();});
    }else{
      if(g('#ao-lgo'))g('#ao-lgo').onclick=loadList;
      if(g('#ao-back'))g('#ao-back').onclick=()=>{detail=null;draw();};
      c.querySelectorAll('.ao-lrow').forEach(el=>el.onclick=()=>loadDetail(el.dataset.po));
      c.querySelectorAll('.ao-cancel').forEach(el=>el.onclick=()=>cancelPo(el.dataset.po));
    }
  };
  draw();
};
/* LG사급현황 (구매/자재) — LG 사급 실적(유상사급 입고) 엑셀 업로드 + 조회. nx.lg_sagub_actual.
   ★업로드시 사업부(RAC/SAC) 선택 · 일자(Transaction Date) 저장 · 품번 클릭시 일자·단가별 개별기록(가격변동 확인). */
SCREEN.lgsagub=(c)=>{
  const API=API_BASE;
  const _now=new Date(),_yy=String(_now.getFullYear()%100).padStart(2,'0'),_mm=String(_now.getMonth()+1).padStart(2,'0');
  const _M1=_yy+_mm+'01',_TD=_yy+_mm+String(_now.getDate()).padStart(2,'0');
  let st={tab:'status',by_ym:[],by_biz:[],files:[],rows:[],sel:'',selName:'',detail:[],dloading:false,
          df:'',dt:'',ymdMin:'',ymdMax:'',biz:'',cls:'',q:'',upBiz:'',sort:{k:'amt',dir:-1},loading:false,msg:'',
          c_from:_M1,c_to:_TD,c_sy:'',cmp:null,c_msg:'',c_loading:false,c_only:'',c_sort:{k:'',dir:-1},
          p_from:_M1,p_to:_TD,pcmp:null,p_loading:false,p_only:'',p_sort:{k:'',dir:-1},pledger:null,
          s_ym:'',slist:null,s_loading:false,s_q:'',s_msg:'',
          cv_status:'supplier',cv_mt:'1,2,5',cv_werks:'',cv_scope:'all',cv_cutg:'절삭',cv_q:'',cvdata:null,cv_loading:false,cv_sort:{k:'',dir:-1}};
  const sortItems=(arr,sort)=>{if(!sort.k||!arr.length)return arr;const {k,dir}=sort;const num=typeof arr[0][k]==='number';
    return arr.slice().sort((a,b)=>num?(((a[k]||0)-(b[k]||0))*dir):((''+(a[k]||'')).localeCompare(''+(b[k]||''))*dir));};
  const ymd2date=s=>{s=''+(s||'');return s.length>=6?`20${s.slice(0,2)}-${s.slice(2,4)}-${s.slice(4,6)}`:'';};  // 260703→2026-07-03
  const date2ymd=v=>v?(''+v).slice(2).replace(/-/g,''):'';                                                       // 2026-07-03→260703
  const ymdF=s=>{s=''+(s||'');return s.length>=6?`${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`:'-';};        // 260703→26/07/03
  const ym2m=y=>{y=(''+(y||'')).replace(/\D/g,'');return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};   // 2607→2026-07 (type=month value)
  const m2ym=v=>{const s=(''+(v||'')).replace(/\D/g,'');return s.length>=6?s.slice(2,6):(s.length>=4?s.slice(0,4):'');}; // 2026-07→2607
  const rng=()=>{const q=[];if(st.df)q.push('ymd_from='+st.df);if(st.dt)q.push('ymd_to='+st.dt);if(st.biz)q.push('biz='+encodeURIComponent(st.biz));return q;};
  const loadSum=async()=>{try{const j=await(await fetch(`${API}/api/lgsagub/summary`)).json();st.by_ym=j.by_ym||[];st.by_biz=j.by_biz||[];st.files=j.files||[];st.ymdMin=j.ymd_min||'';st.ymdMax=j.ymd_max||'';
      if(!st.df){const _d=new Date();const _y=String(_d.getFullYear()%100).padStart(2,'0'),_m=String(_d.getMonth()+1).padStart(2,'0');st.df=_y+_m+'01';st.dt=_y+_m+String(_d.getDate()).padStart(2,'0');}}catch(e){st.by_ym=[];st.by_biz=[];st.files=[];}};
  const NUMK=['qty','pmax','amt','cnt'];
  const applySort=()=>{const {k,dir}=st.sort;if(!k)return;const num=NUMK.includes(k);
    st.rows.sort((a,b)=>{let va=a[k],vb=b[k];if(num){return ((+va||0)-(+vb||0))*dir;}return (''+(va||'')).localeCompare(''+(vb||''))*dir;});};
  const loadList=async()=>{try{const qs=rng().slice();if(st.cls)qs.push('cls='+encodeURIComponent(st.cls));if(st.q)qs.push('q='+encodeURIComponent(st.q));
      const j=await(await fetch(`${API}/api/lgsagub/list${qs.length?('?'+qs.join('&')):''}`)).json();st.rows=j.rows||[];applySort();}catch(e){st.rows=[];}};
  const loadDetail=async(item)=>{st.sel=item;st.dloading=true;paintDetail();
    try{const qs=['item='+encodeURIComponent(item)].concat(rng());
      const j=await(await fetch(`${API}/api/lgsagub/detail?${qs.join('&')}`)).json();st.detail=j.rows||[];}catch(e){st.detail=[];}
    st.dloading=false;paintDetail();};
  const reload=async()=>{st.loading=true;draw();await loadSum();await loadList();st.loading=false;draw();};
  const upload=async(file)=>{if(!file)return;
    if(!st.upBiz){st.msg='⚠ 먼저 사업부(RAC/SAC)를 선택하세요.';draw();return;}
    // #7 업로드 전 사업부 확인 경고(실수 방지)
    if(!confirm(`이 파일을 [ ${st.upBiz} ] 사업부 실적으로 업로드합니다.\n\n파일: ${file.name}\n\n사업부가 맞습니까?`)){return;}
    st.msg='업로드 중… '+file.name+' ('+st.upBiz+')';draw();
    const usedBiz=st.upBiz;
    try{const fd=new FormData();fd.append('file',file);
      const r=await fetch(`${API}/api/lgsagub/upload?biz=${encodeURIComponent(st.upBiz)}`,{method:'POST',body:fd});const j=await r.json();
      if(!j.ok){st.msg='❌ '+(j.error||'실패')+(j.header_row?(' · 감지헤더: '+j.header_row.join(' | ')):'');}
      else{const det=Object.entries(j.detected||{}).map(([k,v])=>`${k}=${v}`).join(', ');
        const ym=(j.by_ym||[]).map(x=>`${x.ym}:${wonI(x.amt)}원(${x.rows})`).join('  ');
        st.msg=`✅ [${usedBiz}] ${file.name} · ${j.rows}행 · 감지[${det}] · ${ym}`;}
    }catch(e){st.msg='❌ 업로드 오류: '+e.message;}
    st.upBiz='';   // #7 업로드 후 사업부 토글 해제(다음 파일에 실수로 같은 사업부 넣기 방지)
    st.sel='';st.detail=[];await loadSum();await loadList();draw();};
  // ── 우측 상세(일자·단가별) 부분갱신 ──
  const detailHtml=()=>{
    if(!st.sel)return `<div class="empty" style="padding:24px;text-align:center;color:var(--muted)">← 왼쪽에서 품번을 클릭하면<br>일자·단가별 개별 기록이 표시됩니다</div>`;
    if(st.dloading)return `<table class="tbl fit"><tbody>${spinRow(5)}</tbody></table>`;
    const d=st.detail; let prevP=null;
    const body=d.length?d.map(r=>{const chg=(prevP!==null&&Math.abs(r.price-prevP)>1e-6);prevP=r.price;
        return `<tr${chg?' style="background:#fff6e0"':''}><td>${ymdF(r.ymd)}</td><td class="center">${esc(r.biz||'-')}</td>
          <td class="num"${chg?' style="color:#c0392b;font-weight:700"':''}>${wonI(r.price)}${chg?' ▲':''}</td>
          <td class="num">${wonI(r.qty)}</td><td class="num">${wonI(r.amt)}</td></tr>`;}).join('')
      :`<tr><td colspan="5" class="empty">기록 없음</td></tr>`;
    const tq=d.reduce((a,b)=>a+(b.qty||0),0),ta=d.reduce((a,b)=>a+(b.amt||0),0);
    const prices=[...new Set(d.map(r=>r.price))];
    return `<div style="font-weight:600;margin:2px 0 6px">📄 ${esc(st.sel)} <span style="color:var(--muted);font-weight:400;font-size:12px">${esc(st.selName)}</span>
        ${prices.length>1?`<span style="color:#c0392b;font-size:12px">· 단가 ${prices.length}종 (변동 有)</span>`:`<span style="color:#1c7c3a;font-size:12px">· 단가 단일</span>`}</div>
      <div class="grid-wrap" style="max-height:430px;overflow:auto"><table class="tbl fit"><thead><tr><th>일자</th><th>사업부</th><th class="num">단가</th><th class="num">수량</th><th class="num">금액</th></tr></thead>
        <tbody>${body}</tbody>
        <tfoot><tr class="lg-foot"><td colspan="3" class="right">합계</td><td class="num">${wonI(tq)}</td><td class="num">${wonI(ta)}</td></tr></tfoot></table></div>`;
  };
  const paintDetail=()=>{const el=c.querySelector('#lg-detail');if(el)el.innerHTML=detailHtml();
    c.querySelectorAll('.it-row').forEach(tr=>tr.style.background=(tr.dataset.item===st.sel?'#e3f0ff':''));};
  // #6 정렬가능 헤더(더블클릭)
  const sh=(k,label,cls)=>`<th data-sk="${k}"${cls?' class="'+cls+'"':''} style="cursor:pointer" title="더블클릭 정렬">${label}${st.sort.k===k?(st.sort.dir<0?' ▼':' ▲'):''}</th>`;

  // ═══════════ 리시빙 비교 탭 ═══════════
  const TABS=[['status','📊 사급입고 현황'],['compare','⚖ 리시빙비교(원소재)'],['parts','🔩 리시빙비교(부품)'],['convert','원소재사급전환율']];
  const tabBar=()=>`<div style="display:flex;gap:3px;margin:4px 0 10px;border-bottom:2px solid #dbe5f2;flex-wrap:wrap">
    ${TABS.map(([k,l])=>`<div class="lg-tab" data-tab="${k}" style="padding:7px 15px;cursor:pointer;font-weight:600;font-size:13px;border:1px solid #dbe5f2;border-bottom:none;border-radius:7px 7px 0 0;margin-bottom:-2px;${st.tab===k?'background:#fff;color:#1c47a0;border-bottom:2px solid #fff':'background:#eef3fa;color:#5a7597'}">${l}</div>`).join('')}
   </div>`;
  const routeTab=()=>{
    if(st.tab==='compare')return st.cmp?drawCompare():loadCompare();
    if(st.tab==='parts')return st.pcmp?drawParts():loadParts();
    if(st.tab==='settle')return st.slist?drawSettle():loadSettle();
    if(st.tab==='convert')return st.cvdata?drawConvert():loadConvert();
    return draw();
  };
  const wireTabs=()=>c.querySelectorAll('.lg-tab').forEach(t=>t.onclick=()=>{if(st.tab!==t.dataset.tab){st.tab=t.dataset.tab;routeTab();}});
  const loadCompare=async()=>{st.c_loading=true;drawCompare();if(!st.ledger)loadLedger();
    try{const qs=[];if(st.c_from)qs.push('ymd_from='+st.c_from);if(st.c_to)qs.push('ymd_to='+st.c_to);
      const j=await(await fetch(`${API}/api/lgsagub/recvcompare?${qs.join('&')}`)).json();st.cmp=j;st.c_msg='';}
    catch(e){st.cmp=null;st.c_msg='❌ 조회 실패: '+e.message;}
    st.c_loading=false;drawCompare();};
  // 월별 동 원소재 수불(기초+입고−소요=기말, 첫 OSP월 기초0). "매월 차이=재고 잔량"을 증명.
  const loadLedger=async()=>{
    try{const j=await(await fetch(`${API}/api/lgsagub/recvcompare_ledger`)).json();st.ledger=j;}
    catch(e){st.ledger=null;}
    if(st.tab==='compare')drawCompare();};
  const ledgerHtml=()=>{
    const L=st.ledger;
    if(!L) return `<div style="font-size:12px;color:#8aa0bd">월별 수불 로딩…</div>`;
    const rs=L.rows||[];
    const yl=y=>y?`${y.slice(0,2)}.${y.slice(2)}`:y;
    // 소요/기말 키만 달리해 LG인증·BOM기준 두 표 생성 (기초·입고는 공통 입고)
    const tbl=(title,ok,sk,ck,ak,color)=>`
      <div style="font-weight:700;color:${color};font-size:12px;margin:4px 0 3px;flex:0 0 auto">${title}</div>
      <table class="tbl fit lg-tbl" style="font-size:11.5px"><thead><tr>
        <th>월</th><th class="num">기초</th><th class="num">입고</th><th class="num">소요</th><th class="num">기말</th><th class="num">기말금액</th>
      </tr></thead><tbody>${rs.map(r=>`<tr>
        <td><b>${yl(r.ym)}</b></td>
        <td class="num">${wonI(Math.round(r[ok]||0))}</td>
        <td class="num" style="color:#1c7c3a">${wonI(Math.round(r.in_kg))}</td>
        <td class="num" style="color:#1c47a0">${wonI(Math.round(r[sk]||0))}</td>
        <td class="num" style="font-weight:700;color:${(r[ck]||0)<0?'#a03d2c':'#16324f'}">${wonI(Math.round(r[ck]||0))}</td>
        <td class="num" style="color:#5a7597">${wonI(Math.round(r[ak]||0))}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">데이터 없음</td></tr>'}</tbody></table>`;
    return `<div style="flex:1;min-height:0;overflow:auto">
      ${tbl('월별 동 수불 · LG BOM 기준 (LG 정산 소요)','open_bom_kg','soyo_bom_kg','close_bom_kg','close_bom_amt','#1c7c3a')}
      ${tbl('월별 동 수불 · 우리 BOM 기준 (협력사 포함)','open_our_kg','soyo_our_kg','close_our_kg','close_our_amt','#a06a1c')}
      <div style="font-size:11px;color:#8aa0bd;margin-top:4px">입고=OSP(LG 사급 raw 동) · 소요=우리 동소요(협력사 사급분 포함). 두 기준 차이 = 우리절삭 동의 LG인증중량 vs 우리 실측중량 = 정산차액</div>
    </div>`;
  };
  // ── 원단위 관리(업로드·적용월·목록) ──
  const loadSettle=async()=>{st.s_loading=true;drawSettle();
    try{const qs=[];if(st.s_ym)qs.push('ym='+encodeURIComponent(st.s_ym));if(st.s_q)qs.push('q='+encodeURIComponent(st.s_q));
      const j=await(await fetch(`${API}/api/lgsagub/settle_list${qs.length?('?'+qs.join('&')):''}`)).json();st.slist=j;st.s_ym=j.ym||st.s_ym;}
    catch(e){st.slist=null;st.s_msg='❌ 조회실패: '+e.message;}
    st.s_loading=false;drawSettle();};
  const settleUpload=async(file)=>{if(!file)return;
    if(!/^\d{4}$/.test(st.s_ym)){st.s_msg='⚠ 적용월을 먼저 선택/입력하세요.';drawSettle();return;}
    if(!confirm(`동정산 원단위 파일을 [ ${st.s_ym} ] 적용월로 업로드합니다.\n(피앤씨 탭만 적재, 같은 월 기존데이터 덮어씀)\n\n파일: ${file.name}\n계속?`))return;
    st.s_msg='업로드 중… '+file.name;drawSettle();
    try{const fd=new FormData();fd.append('file',file);
      const j=await(await fetch(`${API}/api/lgsagub/settle_upload?ym=${encodeURIComponent(st.s_ym)}`,{method:'POST',body:fd})).json();
      if(!j.ok)st.s_msg='❌ '+(j.error||'실패')+(j.header?(' · 헤더:'+j.header.slice(0,8).join('|')):'');
      else st.s_msg=`✅ [${st.s_ym}] ${j.sheet} · ${wonI(j.rows)}행 · `+(j.by_gubun1||[]).map(g=>`${g.gubun1} ${wonI(g.rows)}행`).join('  ');
    }catch(e){st.s_msg='❌ '+e.message;}
    st.cmp=null;await loadSettle();};
  const settleCopy=async()=>{
    if(!st.s_ym){st.s_msg='⚠ 복사 원본 적용월을 먼저 선택하세요.';drawSettle();return;}
    const to=prompt(`[${st.s_ym}] 원단위를 복사할 신규 적용월(YYMM 4자리):`,'');
    if(!to||!/^\d{4}$/.test(to.trim()))return;
    st.s_msg='복사 중…';drawSettle();
    try{const j=await(await fetch(`${API}/api/lgsagub/settle_copy?from_ym=${encodeURIComponent(st.s_ym)}&to_ym=${encodeURIComponent(to.trim())}`,{method:'POST'})).json();
      st.s_msg=j.ok?`✅ ${st.s_ym}→${to.trim()} ${wonI(j.rows)}행 복사(수정 후 재업로드 가능)`:'❌ 복사실패';st.s_ym=to.trim();st.cmp=null;}
    catch(e){st.s_msg='❌ '+e.message;}
    await loadSettle();};
  const drawSettle=()=>{
    const m=st.slist, rows=(m&&m.rows)||[], yms=(m&&m.yms)||[];
    const ymOpts=`<option value="">(선택)</option>`+yms.map(y=>`<option value="${y.ym}"${st.s_ym===y.ym?' selected':''}>${y.ym} (${wonI(y.rows)}행)</option>`).join('');
    const body=st.s_loading?spinRow(12):(rows.length?rows.map(r=>`<tr>
        <td><b>${esc(r.assy_pn)}</b></td><td class="cap" style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.assy_desc)}">${esc(r.assy_desc)}</td>
        <td class="cap" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.coop)}</td>
        <td>${esc(r.sub_pn)}</td><td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.sub_desc)}">${esc(r.sub_desc)}</td>
        <td class="num">${wonI(r.qty)}</td><td class="center"><span style="font-size:11px;padding:1px 6px;border-radius:8px;${r.gubun1==='사급'?'background:#e6f0ff;color:#1c47a0':'background:#fbe9e4;color:#a03d2c'}">${esc(r.gubun1)}</span></td>
        <td class="center" style="font-size:11px">${esc(r.gubun2)}</td><td class="num">${r.od||'-'}</td><td class="num">${r.thk||'-'}</td><td class="num">${r.leng||'-'}</td><td class="num">${r.weight?r.weight.toFixed(4):'-'}</td></tr>`).join('')
      :`<tr><td colspan="12" class="empty">데이터 없음 — 적용월 선택 후 엑셀 업로드</td></tr>`);
    const sg=rows.filter(r=>r.gubun1==='사급').length, jk=rows.filter(r=>r.gubun1==='직거래').length;
    c.innerHTML=`
     <div class="page-title">📊 LG사급현황 <span style="font-size:12px;color:var(--muted);font-weight:400">동정산 원단위 관리</span></div>
     ${tabBar()}
     <div class="page-sub">LG와 소통하는 <b>동정산 원단위</b>(Assy별 동부자재 소요·규격·사급/직거래 구분). 월별 큰 변경 없음 → 전월복사 후 부분수정 가능. <code>nx.lg_settle_unit</code>. ★중량=수량반영값.</div>
     <div style="display:flex;gap:8px;align-items:stretch;margin-bottom:8px;flex-wrap:wrap">
       <div style="flex:0 0 auto;border:1px solid #cfe0f5;border-radius:8px;padding:8px 14px;background:#fbfdff;display:flex;flex-direction:column;justify-content:center">
         <div style="font-size:11px;color:#5a7597;margin-bottom:4px">적용월 <span style="color:#c0392b">*</span></div>
         <div style="display:flex;gap:6px;align-items:center"><select class="sel" id="s-ym-sel" style="width:130px">${ymOpts}</select>
           <input type="month" class="inp" id="s-ym-new" value="${ym2m(st.s_ym)}" style="width:140px" title="신규월 직접입력"></div></div>
       <div id="s-dz" title="동정산 원단위 엑셀(피앤씨 탭)" style="flex:1;min-width:280px;border:2px dashed #8fb4d6;border-radius:8px;padding:8px;background:#f4f9fe;color:#5a7597;text-align:center;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:12px">
         📥 동정산 <b style="margin:0 4px">원단위 엑셀</b> 드래그&드롭/클릭 <span style="color:#8aa0bd;margin-left:6px">(적용월 선택 후 · 피앤씨 탭)</span>
         <input type="file" id="s-f" accept=".xlsx,.xls" style="display:none"></div>
       <button class="btn" id="s-copy" style="flex:0 0 auto" title="선택 적용월을 신규월로 복사">📋 전월 복사로 신규월</button>
     </div>
     ${st.s_msg?`<div style="padding:6px 10px;background:#eef6ff;border:1px solid #cfe0f5;border-radius:6px;margin-bottom:8px;font-size:12px">${esc(st.s_msg)}</div>`:''}
     <div class="toolbar" style="margin-bottom:6px">
       <input class="inp" id="s-q" value="${esc(st.s_q)}" placeholder="Assy/하위 품번·품명" style="width:200px"><button class="btn" id="s-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${m?`적용월 ${esc(m.ym||'-')} · ${wonI(rows.length)}행 (사급 ${wonI(sg)}·직거래 ${wonI(jk)})`:'조회 전'}</span>
     </div>
     <div class="grid-wrap" style="max-height:480px;overflow:auto"><table class="tbl fit lg-tbl"><thead><tr>
        <th>Assy P/N</th><th class="cap">Desc</th><th class="cap">협력사</th><th>P/N(하위1)</th><th class="cap">Desc</th>
        <th class="num">수량</th><th class="center">구분1</th><th class="center">구분2</th><th class="num">외경</th><th class="num">T</th><th class="num">길이</th><th class="num">중량</th></tr></thead>
       <tbody>${body}</tbody></table></div>`;
    wireTabs();
    const dz=c.querySelector('#s-dz'),fi=c.querySelector('#s-f');
    dz.onclick=()=>fi.click();
    dz.ondragover=e=>{e.preventDefault();dz.style.background='#e3f0ff';};dz.ondragleave=()=>{dz.style.background='#f4f9fe';};
    dz.ondrop=e=>{e.preventDefault();dz.style.background='#f4f9fe';if(e.dataTransfer.files[0])settleUpload(e.dataTransfer.files[0]);};
    fi.onchange=()=>{if(fi.files[0]){settleUpload(fi.files[0]);fi.value='';}};
    c.querySelector('#s-ym-sel').onchange=e=>{st.s_ym=e.target.value;loadSettle();};
    c.querySelector('#s-ym-new').oninput=e=>{st.s_ym=m2ym(e.target.value);};
    c.querySelector('#s-copy').onclick=settleCopy;
    c.querySelector('#s-go').onclick=()=>{st.s_q=c.querySelector('#s-q').value.trim();loadSettle();};
    c.querySelector('#s-q').onkeyup=e=>{if(e.key==='Enter'){st.s_q=e.target.value.trim();loadSettle();}};
    attachResizers(c);
  };
  // ═══════════ 원소재 사급전환율 탭 (LG BOM Assembly Pull 대조) ═══════════
  const WLAB={DGZ:'RAC',DMZ:'SAC'};                       // 공장→사업부
  const MTLAB={'1':'자체','2':'외주','3':'매입','4':'사급','5':'외주완성'};
  const loadConvert=async()=>{st.cv_loading=true;drawConvert();
    try{const qs=[`status=${st.cv_status}`,`mt=${encodeURIComponent(st.cv_mt)}`,`scope=${st.cv_scope}`,`cutg=${encodeURIComponent(st.cv_cutg)}`];
      if(st.cv_werks)qs.push('werks='+st.cv_werks);
      if(st.cv_q)qs.push('q='+encodeURIComponent(st.cv_q));
      const j=await(await fetch(`${API}/api/lgsagub/sagub_convert?${qs.join('&')}`)).json();st.cvdata=j;}
    catch(e){st.cvdata={rows:[],_err:e.message};}
    st.cv_loading=false;drawConvert();};
  const drawConvert=()=>{
    const m=st.cvdata||{};
    let rows=(m.rows||[]).slice();
    rows=sortItems(rows,st.cv_sort);
    const n2=v=>(v==null||v==='')?'-':(+v).toFixed(2);
    const n4=v=>(v==null||v==='')?'-':(+v).toFixed(4);
    const wI=v=>(v==null||v==='')?'-':Math.round(+v);
    const cvh=(k,label,cls)=>`<th${cls?' class="'+cls+'"':''} data-cvk="${k}" style="cursor:pointer" title="더블클릭 정렬">${label}${st.cv_sort.k===k?(st.cv_sort.dir<0?' ▼':' ▲'):''}</th>`;
    const mtChk=['1','2','5','3','4'].map(x=>{const on=st.cv_mt.split(',').includes(x);
      return `<label style="font-size:12px;margin-right:8px;cursor:pointer"><input type="checkbox" class="cv-mt" value="${x}"${on?' checked':''}> ${x}·${MTLAB[x]}</label>`;}).join('');
    const badge=(txt,bg,fg)=>`<span style="font-size:11px;padding:1px 7px;border-radius:8px;background:${bg};color:${fg};white-space:nowrap">${txt}</span>`;
    const body=st.cv_loading?spinRow(12):(rows.length?rows.map(r=>`<tr${r.status==='미전환'?' style="background:#fff4f0"':''}>
        <td><b>${esc(r.model)}</b><div style="font-size:11px;color:#8aa0bd;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.model_name)}</div></td>
        <td class="num">${r.recv_prev?`<b>${wonI(r.recv_prev)}</b>`:'<span style="color:#c9d3df">0</span>'}</td>
        <td>${esc(r.parent)}<div style="font-size:11px;color:#8aa0bd;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.parent_name)}">${esc(r.parent_name)}</div></td>
        <td class="center" style="font-size:11px">${esc(r.make_type)}·${esc(MTLAB[r.make_type]||'')}</td>
        <td>${esc(r.child)}</td>
        <td class="num">${n2(r.od)}</td><td class="num">${n2(r.thk)}</td><td class="num">${wI(r.length)}</td>
        <td class="num">${n4(r.weight)}</td><td class="center" style="font-size:11px">${esc(r.metal)}${r.form?(' '+esc(r.form)):''}</td>
        <td class="center">${r.dim_src==='우리'?badge('우리','#e6f7ea','#1c7c3a'):(r.dim_src==='LG'?badge('LG','#fdf0e3','#b5651d'):'-')}</td>
        <td class="num">${n4(r.qty)}</td><td class="center" style="font-size:11px">${esc(WLAB[r.werks]||r.werks||'')}</td>
        <td class="center">${r.status==='미전환'?badge('미전환','#fbe0da','#c0392b'):badge('전환','#e0ecfb','#1c47a0')}</td></tr>`).join('')
      :`<tr><td colspan="14" class="empty">${m._err?('오류: '+esc(m._err)):'대상 없음 — 필터를 조정하세요'}</td></tr>`);
    const statusOpt=[['supplier','미전환'],['pull','전환'],['all','전체']]
      .map(([k,l])=>`<option value="${k}"${st.cv_status===k?' selected':''}>${l}</option>`).join('');
    const werksOpt=[['','전체'],['DMZ','SAC'],['DGZ','RAC']]
      .map(([k,l])=>`<option value="${k}"${st.cv_werks===k?' selected':''}>${l}</option>`).join('');
    const scopeOpt=[['all','전체'],['active','사용중']]
      .map(([k,l])=>`<option value="${k}"${st.cv_scope===k?' selected':''}>${l}</option>`).join('');
    const cutgOpt=[['절삭','절삭'],['설치','설치'],['분지관','분지관'],['이지링크','이지링크'],['(없음)','(미분류)'],['all','전체']]
      .map(([k,l])=>`<option value="${k}"${st.cv_cutg===k?' selected':''}>${l}</option>`).join('');
    const pym='전월 리시빙';   // 전월은 서버가 매월 자동계산(오늘 기준 직전월)
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%">
     <div class="page-title" style="flex:0 0 auto">📊 LG사급현황 <span style="font-size:12px;color:var(--muted);font-weight:400">원소재 사급전환율</span></div>
     <div style="flex:0 0 auto">${tabBar()}</div>
     <div class="page-sub" style="flex:0 0 auto">LG BOM(<code>nx.lg_bom</code>)의 동 원소재(Tube,Raw)가 <b>사급(Assembly Pull)</b>으로 전환됐는지 우리 BOM과 대조. <b style="color:#c0392b">Supplier=미전환</b>(아직 우리가 구매)·Assembly Pull=전환(LG 사급). 치수·재질은 우리 정본 <code>nx.item</code> 우선(없으면 LG spec).</div>
     <div style="flex:0 0 auto;display:flex;gap:10px;margin-bottom:8px;flex-wrap:wrap">
       ${card('전환율(전체 동원소재)',(m.rate!=null?m.rate:'-')+'%',`사급 ${wonI(m.pull||0)} / 미전환 ${wonI(m.supplier||0)} edge`,'#1c47a0')}
       ${card('대상 완제품(ASSY)',wonI(m.models||0),`제작품 ${wonI(m.parents||0)}종`,'#5a7597')}
       ${card('표시 행',`${wonI(m.shown||0)}${(m.total>m.shown)?(' / '+wonI(m.total)):''}`,'필터 반영','#b5651d')}
     </div>
     <div class="toolbar" style="flex:0 0 auto;flex-wrap:nowrap;overflow-x:auto">
       <label class="tl">범위</label><select class="sel" id="cv-scope" style="width:74px">${scopeOpt}</select>
       <label class="tl" style="margin-left:5px">제품군</label><select class="sel" id="cv-cutg" style="width:76px">${cutgOpt}</select>
       <label class="tl" style="margin-left:5px">상태</label><select class="sel" id="cv-status" style="width:72px">${statusOpt}</select>
       <label class="tl" style="margin-left:5px">사업부</label><select class="sel" id="cv-werks" style="width:64px">${werksOpt}</select>
       <label class="tl" style="margin-left:6px">제작유형</label><span style="white-space:nowrap">${mtChk}</span>
       <input class="inp" id="cv-q" value="${esc(st.cv_q)}" placeholder="품번/품명 검색" style="width:150px;margin-left:5px">
       <button class="btn" id="cv-go">조회</button>
       <button class="btn xls" id="cv-xls" style="margin-left:4px">엑셀 다운로드</button>
       <div class="spacer"></div><span class="rowcount">${st.cv_loading?'조회 중…':`${wonI(rows.length)}행`}</span>
     </div>
     <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl fit lg-tbl"><thead><tr>
        ${cvh('model','ASSY 품번')}${cvh('recv_prev',pym,'num')}${cvh('parent','제작품(하위)')}${cvh('make_type','제작유형','center')}${cvh('child','동원소재')}
        ${cvh('od','외경','num')}${cvh('thk','두께','num')}${cvh('length','길이','num')}${cvh('weight','단위중량','num')}
        <th class="center">재질</th><th class="center">치수출처</th>${cvh('qty','소요중량(KG)','num')}<th class="center">사업부</th>${cvh('status','사급전환','center')}</tr></thead>
       <tbody>${body}</tbody></table></div>
     </div>`;
    wireTabs();
    c.querySelector('#cv-scope').onchange=e=>{st.cv_scope=e.target.value;loadConvert();};
    c.querySelector('#cv-cutg').onchange=e=>{st.cv_cutg=e.target.value;loadConvert();};
    c.querySelector('#cv-status').onchange=e=>{st.cv_status=e.target.value;loadConvert();};
    c.querySelector('#cv-werks').onchange=e=>{st.cv_werks=e.target.value;loadConvert();};
    c.querySelectorAll('.cv-mt').forEach(cb=>cb.onchange=()=>{
      st.cv_mt=[...c.querySelectorAll('.cv-mt:checked')].map(x=>x.value).join(',');loadConvert();});
    c.querySelector('#cv-go').onclick=()=>{st.cv_q=c.querySelector('#cv-q').value.trim();loadConvert();};
    c.querySelector('#cv-q').onkeyup=e=>{if(e.key==='Enter'){st.cv_q=e.target.value.trim();loadConvert();}};
    c.querySelectorAll('[data-cvk]').forEach(th=>th.ondblclick=()=>{const k=th.dataset.cvk;
      st.cv_sort=(st.cv_sort.k===k)?{k,dir:-st.cv_sort.dir}:{k,dir:1};drawConvert();});
    const xb=c.querySelector('#cv-xls');if(xb)xb.onclick=()=>{
      const H=['ASSY품번','ASSY품명',pym,'제작품','제작품명','제작유형','동원소재','외경','두께','길이','단위중량','재질','형태','치수출처','소요중량(KG)','사업부','사급전환'];
      const R=rows.map(r=>[r.model,r.model_name,r.recv_prev,r.parent,r.parent_name,r.make_type+'·'+(MTLAB[r.make_type]||''),r.child,r.od,r.thk,r.length,r.weight,r.metal,r.form,r.dim_src,r.qty,WLAB[r.werks]||r.werks||'',r.status]);
      downloadCSV(`원소재사급전환율_${st.cv_status}_${st.cv_scope}.csv`,H,R);};
    attachResizers(c);
  };
  const card=(title,val,sub,color)=>`<div style="flex:1;min-width:150px;border:1px solid #dbe5f2;border-left:4px solid ${color};border-radius:8px;padding:10px 14px;background:#fff">
      <div style="font-size:11px;color:#5a7597">${title}</div><div style="font-size:20px;font-weight:700;color:${color};margin:3px 0">${val}</div>
      <div style="font-size:11px;color:#8aa0bd">${sub||''}</div></div>`;
  const drawCompare=()=>{
    const m=st.cmp, cop=m&&m.copper;
    const its=(m&&m.items)||[];
    const showOnly=st.c_only;
    let filt=showOnly==='unmatched'?its.filter(x=>!x.matched):its;
    filt=sortItems(filt,st.c_sort);
    // ★B: 우리 직접절삭(우리 실측) + 협력사 사급분 = 우리 BOM 기준. LG BOM 기준 = LG 정산 소요(우리절삭 LG인증 + 협력사). 차이=정산차액. 2중계상 없음.
    filt.forEach(r=>{r.ourbom_kg=(r.actual_kg||0)+(r.coop_kg||0);});   // 우리 BOM 기준 = 우리 실측절삭 + 협력사
    const isCoop=r=>((r.coop_kg||0)>0.001);
    const T={rc:0,rr:0,actual_kg:0,coop_kg:0,ourbom_kg:0,total_kg:0,total_amt:0};
    filt.forEach(r=>{T.rc+=r.recv_c;T.rr+=r.recv_r;T.actual_kg+=(r.actual_kg||0);T.coop_kg+=(r.coop_kg||0);T.ourbom_kg+=(r.ourbom_kg||0);T.total_kg+=(r.total_kg||0);T.total_amt+=(r.total_amt||0);});
    const csh=(k,label,cls)=>`<th${cls?' class="'+cls+'"':''} data-sk="${k}" style="cursor:pointer" title="더블클릭 정렬">${label}${st.c_sort.k===k?(st.c_sort.dir<0?' ▼':' ▲'):''}</th>`;
    const rowsH=st.c_loading?spinRow(9):(filt.length?filt.map(r=>{const cp=isCoop(r);return `<tr${cp?' style="background:#fff7e8"':(!r.matched?' style="background:#fff4f0"':'')}>
        <td><b>${esc(r.item)}</b>${cp?' <span style="color:#a06a1c;font-size:10px">협력사사급</span>':(!r.matched?' <span style="color:#a03d2c;font-size:10px">LG미인증</span>':'')}</td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.name)}">${esc(r.name)}</td>
        <td class="num">${wonI(r.recv_c)}</td><td class="num" style="color:#a03d2c">${r.recv_r?wonI(r.recv_r):''}</td>
        <td class="num" style="color:#1c7c3a;font-weight:600">${r.actual_kg?wonI(r.actual_kg):'-'}</td>
        <td class="num" style="color:#a06a1c;font-weight:600">${r.coop_kg?wonI(r.coop_kg):'-'}</td>
        <td class="num" style="color:#16324f;font-weight:700">${r.ourbom_kg?wonI(r.ourbom_kg):'-'}</td>
        <td class="num" style="color:#5a7597">${r.total_kg?wonI(r.total_kg):'-'}</td>
        <td class="num" style="color:#8aa0bd">${r.total_amt?wonI(r.total_amt):'-'}</td></tr>`;}).join('')
      :`<tr><td colspan="9" class="empty">데이터 없음 — 대사조회를 눌러주세요</td></tr>`);
    const foot=filt.length?`<tfoot><tr class="lg-foot"><td colspan="2" class="right">합계 ${wonI(filt.length)}종</td>
        <td class="num">${wonI(T.rc)}</td><td class="num" style="color:#a03d2c">${wonI(T.rr)}</td>
        <td class="num" style="color:#1c7c3a">${wonI(T.actual_kg)}</td><td class="num" style="color:#a06a1c">${wonI(T.coop_kg)}</td>
        <td class="num" style="color:#16324f">${wonI(T.ourbom_kg)}</td><td class="num" style="color:#5a7597">${wonI(T.total_kg)}</td>
        <td class="num" style="color:#8aa0bd">${wonI(T.total_amt)}</td></tr></tfoot>`:'';
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%">
      <div class="page-title" style="flex:0 0 auto">📊 LG사급현황 <span style="font-size:12px;color:var(--muted);font-weight:400">리시빙 비교 · 원소재(동 kg)</span></div>
      <div style="flex:0 0 auto">${tabBar()}</div>
      ${st.c_msg?`<div style="padding:6px 10px;background:#eef6ff;border:1px solid #cfe0f5;border-radius:6px;margin-bottom:8px;font-size:12px;flex:0 0 auto">${esc(st.c_msg)}</div>`:''}
      <div class="toolbar" style="margin-bottom:8px;flex:0 0 auto;flex-wrap:nowrap;overflow-x:auto">
        <label class="tl">리시빙 기간</label><input type="date" class="inp" id="c-df" value="${ymd2date(st.c_from)}" style="width:150px"> ~ <input type="date" class="inp" id="c-dt" value="${ymd2date(st.c_to)}" style="width:150px">
        <button class="btn" id="c-go">대사조회</button>
        <label class="rl" style="margin-left:10px"><input type="checkbox" id="c-unm"${st.c_only==='unmatched'?' checked':''}> 미매칭만</label>
        <div class="spacer"></div>
        ${cop?`<span class="rowcount">우리 BOM 기준 <b style="color:#16324f">${wonI((cop.actual_net||0)+(cop.coop_net||0))}</b>kg (우리절삭 <b style="color:#1c7c3a">${wonI(cop.actual_net)}</b> + 협력사 <b style="color:#a06a1c">${wonI(cop.coop_net)}</b>) · LG BOM 기준 ${wonI(cop.total_net)}kg · OSP 입고 ${wonI(cop.in_osp_kg)}kg</span>`:'<span class="rowcount">조회 전</span>'}
      </div>
      <div style="display:flex;gap:10px;flex:1;min-height:0">
        <div style="flex:0 0 340px;display:flex;flex-direction:column;min-height:0;border:1px solid #dbe5f2;border-radius:8px;padding:8px;background:#fbfdff">
          ${ledgerHtml()}
        </div>
        <div style="flex:1;display:flex;flex-direction:column;min-height:0">
          <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl fit lg-tbl"><thead><tr>
            ${csh('item','품번(완제품)')}${csh('name','품명','cap')}${csh('recv_c','출고(리시빙)','num')}${csh('recv_r','반품(리시빙)','num')}
            ${csh('actual_kg','우리 직접절삭(kg)','num')}${csh('coop_kg','협력사 사급분(kg)','num')}${csh('ourbom_kg','우리 BOM 기준(kg)','num')}${csh('total_kg','LG BOM 기준(kg)','num')}${csh('total_amt','금액','num')}</tr></thead>
           <tbody>${rowsH}</tbody>${foot}</table></div>
        </div>
      </div>
     </div>
     <style>.lg-tbl thead th{position:sticky;top:0;background:#f1f5fb;z-index:4}.lg-tbl tfoot .lg-foot td{position:sticky;bottom:0;background:#eaf1fb;font-weight:700;border-top:2px solid #b9cbe6;z-index:3}</style>`;
    wireTabs();
    c.querySelector('#c-go').onclick=()=>{st.c_from=date2ymd(c.querySelector('#c-df').value);st.c_to=date2ymd(c.querySelector('#c-dt').value);loadCompare();};
    c.querySelector('#c-unm').onchange=e=>{st.c_only=e.target.checked?'unmatched':'';drawCompare();};
    c.querySelectorAll('th[data-sk]').forEach(th=>th.ondblclick=()=>{const k=th.dataset.sk;if(st.c_sort.k===k)st.c_sort.dir*=-1;else st.c_sort={k,dir:-1};drawCompare();});
    attachResizers(c);
  };

  // ── 리시빙비교(부품) ──
  const loadParts=async()=>{st.p_loading=true;drawParts();if(!st.pledger)loadPartsLedger();
    try{const qs=[];if(st.p_from)qs.push('ymd_from='+st.p_from);if(st.p_to)qs.push('ymd_to='+st.p_to);
      const j=await(await fetch(`${API}/api/lgsagub/recvcompare_parts${qs.length?('?'+qs.join('&')):''}`)).json();st.pcmp=j;}
    catch(e){st.pcmp=null;}
    st.p_loading=false;drawParts();};
  // 월별 사급부품 수불(원소재와 동일 형태·1월부터): 기초+입고(OSP)−소요(리시빙×BOM)=기말
  const loadPartsLedger=async()=>{
    try{const j=await(await fetch(`${API}/api/lgsagub/recvcompare_parts_ledger`)).json();st.pledger=j;}
    catch(e){st.pledger=null;}
    if(st.tab==='parts')drawParts();};
  const partsLedgerHtml=()=>{
    const L=st.pledger;
    if(!L)return `<div style="font-size:12px;color:#8aa0bd">월별 수불 로딩…</div>`;
    const rs=L.rows||[]; const yl=y=>y?`${y.slice(0,2)}.${y.slice(2)}`:y;
    return `<div style="flex:1;min-height:0;overflow:auto">
      <div style="font-weight:700;color:#1c7c3a;font-size:12px;margin:4px 0 3px">월별 사급부품 수불 (개수·2월부터)</div>
      <table class="tbl fit lg-tbl" style="font-size:11.5px"><thead><tr>
        <th>월</th><th class="num">기초</th><th class="num">입고</th><th class="num">소요</th><th class="num">기말</th><th class="num">기말금액</th>
      </tr></thead><tbody>${rs.map(r=>`<tr>
        <td><b>${yl(r.ym)}</b></td>
        <td class="num">${wonI(Math.round(r.open_bom_kg||0))}</td>
        <td class="num" style="color:#1c7c3a">${wonI(Math.round(r.in_kg))}</td>
        <td class="num" style="color:#8a5a1a">${wonI(Math.round(r.soyo_bom_kg||0))}</td>
        <td class="num" style="font-weight:700;color:${(r.close_bom_kg||0)<0?'#a03d2c':'#16324f'}">${wonI(Math.round(r.close_bom_kg||0))}</td>
        <td class="num" style="color:#5a7597">${wonI(Math.round(r.close_bom_amt||0))}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">데이터 없음</td></tr>'}</tbody></table>
      <div style="font-size:11px;color:#8aa0bd;margin-top:4px">입고=LG OSP 사급부품 · 소요=리시빙×BOM. 2월(첫 OSP월) 기초0</div>
    </div>`;};
  const psh=(k,label,cls)=>`<th${cls?' class="'+cls+'"':''} data-sk="${k}" style="cursor:pointer" title="더블클릭 정렬">${label}${st.p_sort.k===k?(st.p_sort.dir<0?' ▼':' ▲'):''}</th>`;
  const drawParts=()=>{
    const m=st.pcmp, s=m&&m.summary;
    let its=(m&&m.items)||[];
    its.forEach(r=>{r.avgprice=r.in_qty?Math.round(r.in_amt/r.in_qty):(r.price||0);r.amtdiff=Math.round(r.diff*r.avgprice);});
    let filt=st.p_only==='diff'?its.filter(x=>Math.abs(x.diff_erp||0)>0.5):its;   // ★①↔②(우리ERP↔OSP) 불일치만
    filt=sortItems(filt,st.p_sort);
    const T={erp_in:0,in_qty:0,out_net:0,diff_erp:0,diff:0};
    filt.forEach(r=>{T.erp_in+=(r.erp_in||0);T.in_qty+=r.in_qty;T.out_net+=r.out_net;T.diff_erp+=(r.diff_erp||0);T.diff+=r.diff;});
    const foot=filt.length?`<tfoot><tr class="lg-foot"><td colspan="2" class="right">합계 ${wonI(filt.length)}종</td>
        <td class="num" style="color:#1c47a0">${wonI(T.erp_in)}</td><td class="num" style="color:#1c7c3a">${wonI(T.in_qty)}</td>
        <td class="num" style="color:#8a5a1a">${wonI(T.out_net)}</td>
        <td class="num" style="color:${Math.abs(T.diff_erp)<0.5?'#1c7c3a':'#a03d2c'}">${wonI(T.diff_erp)}</td>
        <td class="num" style="color:#8aa0bd">${wonI(T.diff)}</td><td class="num">-</td></tr></tfoot>`:'';
    const body=st.p_loading?spinRow(8):(filt.length?filt.map(r=>`<tr>
        <td><b>${esc(r.item)}</b></td><td class="cap" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.name)}">${esc(r.name)}</td>
        <td class="num" style="color:#1c47a0;font-weight:600">${r.erp_in?wonI(r.erp_in):'-'}</td>
        <td class="num" style="color:#1c7c3a;font-weight:600">${r.in_qty?wonI(r.in_qty):'-'}</td>
        <td class="num" style="color:#8a5a1a">${r.out_net?wonI(r.out_net):'-'}</td>
        <td class="num" style="font-weight:600;color:${Math.abs(r.diff_erp||0)<0.5?'#8aa0bd':'#a03d2c'}" title="우리ERP↔LG OSP 불일치(둘 다 공급이라 0이어야 정상)">${(r.diff_erp||0)?wonI(r.diff_erp):'0'}</td>
        <td class="num" style="color:#8aa0bd" title="②공급−③소비 = 선입고(양수 정상)">${wonI(r.diff)}</td>
        <td class="num" style="font-size:11px;color:#8aa0bd">${r.avgprice?wonI(r.avgprice):'-'}</td></tr>`).join('')
      :`<tr><td colspan="8" class="empty">데이터 없음 — 리시빙 기간 선택 후 조회</td></tr>`);
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%">
      <div class="page-title" style="flex:0 0 auto">📊 LG사급현황 <span style="font-size:12px;color:var(--muted);font-weight:400">리시빙 비교 · 사급부품(개수)</span></div>
      <div style="flex:0 0 auto">${tabBar()}</div>
      <div class="page-sub" style="flex:0 0 auto">사급부품 3-way 대사: <b style="color:#1c47a0">①우리ERP 확정입고</b>(PU_T_STOCK_MAINT) vs <b style="color:#1c7c3a">②LG OSP</b>(전산) vs <b style="color:#8a5a1a">③리시빙소비</b>(리시빙×BOM). 좌측=월별 수불(1월부터). 헤더 더블클릭 정렬.</div>
      <div class="toolbar" style="margin-bottom:8px;flex:0 0 auto;flex-wrap:nowrap;overflow-x:auto">
        <label class="tl">리시빙 기간</label><input type="date" class="inp" id="p-df" value="${ymd2date(st.p_from)}" style="width:150px"> ~ <input type="date" class="inp" id="p-dt" value="${ymd2date(st.p_to)}" style="width:150px">
        <button class="btn" id="p-go">대사조회</button>
        <label class="rl" style="margin-left:10px"><input type="checkbox" id="p-diff"${st.p_only==='diff'?' checked':''}> 차이있는것만</label>
        <div class="spacer"></div><span class="rowcount">${s?`사급부품 ${wonI(s.parts)}종`:'조회 전'}</span>
      </div>
      <div style="display:flex;gap:10px;flex:1;min-height:0">
        <div style="flex:0 0 320px;display:flex;flex-direction:column;min-height:0;border:1px solid #dbe5f2;border-radius:8px;padding:8px;background:#fbfdff">
          ${partsLedgerHtml()}
        </div>
        <div style="flex:1;display:flex;flex-direction:column;min-height:0">
          <div class="grid-wrap" style="flex:1;min-height:0;overflow:auto"><table class="tbl fit lg-tbl"><thead><tr>
            ${psh('item','사급부품 품번')}${psh('name','품명','cap')}${psh('erp_in','①우리ERP입고','num')}${psh('in_qty','②LG OSP','num')}
            ${psh('out_net','③리시빙소비','num')}${psh('diff_erp','①↔②차이','num')}${psh('diff','선입고(②−③)','num')}${psh('avgprice','평균단가','num')}</tr></thead>
           <tbody>${body}</tbody>${foot}</table></div>
        </div>
      </div>
     </div>
     <style>.lg-tbl thead th{position:sticky;top:0;background:#f1f5fb;z-index:4}.lg-tbl tfoot .lg-foot td{position:sticky;bottom:0;background:#eaf1fb;font-weight:700;border-top:2px solid #b9cbe6;z-index:3}</style>`;
    wireTabs();
    c.querySelector('#p-go').onclick=()=>{st.p_from=date2ymd(c.querySelector('#p-df').value);st.p_to=date2ymd(c.querySelector('#p-dt').value);loadParts();};
    c.querySelector('#p-diff').onchange=e=>{st.p_only=e.target.checked?'diff':'';drawParts();};
    c.querySelectorAll('th[data-sk]').forEach(th=>th.ondblclick=()=>{const k=th.dataset.sk;if(st.p_sort.k===k)st.p_sort.dir*=-1;else st.p_sort={k,dir:-1};drawParts();});
    attachResizers(c);
  };

  const draw=()=>{
    if(st.tab==='compare'){drawCompare();return;}
    if(st.tab==='parts'){drawParts();return;}
    if(st.tab==='settle'){drawSettle();return;}
    const tot=st.rows.reduce((a,b)=>a+(b.amt||0),0), totq=st.rows.reduce((a,b)=>a+(b.qty||0),0), totc=st.rows.reduce((a,b)=>a+(b.cnt||0),0);
    const dataRange=(st.ymdMin&&st.ymdMax)?`${ymdF(st.ymdMin)}~${ymdF(st.ymdMax)}`:'없음';
    const bizOpts=`<option value="">전체</option>`+(st.by_biz.filter(b=>b.biz).map(b=>`<option value="${esc(b.biz)}"${st.biz===b.biz?' selected':''}>${esc(b.biz)}</option>`).join(''));
    c.innerHTML=`
     <div class="page-title">📊 LG사급현황 <span style="font-size:12px;color:var(--muted);font-weight:400">LG 사급 실적(유상사급 입고) · 사업부·일자·단가</span></div>
     ${tabBar()}
     <div class="page-sub">엑셀 업로드 → <code>nx.lg_sagub_actual</code>. 컬럼 자동감지(품번·수량·금액·단가·<b>일자</b>). <b>업로드 시 사업부(RAC/SAC) 선택</b> 필수. 보유 데이터: <b>${dataRange}</b>.</div>
     <div style="display:flex;gap:8px;align-items:stretch;margin-bottom:8px">
       <div style="flex:0 0 auto;border:1px solid #cfe0f5;border-radius:8px;padding:8px 14px;background:#fbfdff;display:flex;flex-direction:column;justify-content:center;white-space:nowrap">
          <div style="font-size:11px;color:#5a7597;margin-bottom:5px">업로드 사업부 <span style="color:#c0392b">*</span></div>
          <div style="display:flex;gap:14px"><label class="rl"><input type="radio" name="lg-upbiz" value="RAC"${st.upBiz==='RAC'?' checked':''}> RAC(DGZ)</label><label class="rl"><input type="radio" name="lg-upbiz" value="SAC"${st.upBiz==='SAC'?' checked':''}> SAC(DMZ)</label></div></div>
       <div id="dz" title="엑셀을 여기로 끌어다 놓거나 클릭" style="flex:1;border:2px dashed #8fb4d6;border-radius:8px;padding:8px;background:#f4f9fe;color:#5a7597;text-align:center;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:12px">
          📥 LG 사급 실적 엑셀 <b style="margin:0 4px">드래그&드롭</b> 또는 클릭 <span style="color:#8aa0bd;margin-left:6px">(사업부 선택 후)</span>
          <input type="file" id="dz-f" accept=".xlsx,.xls" style="display:none"></div>
     </div>
     ${st.msg?`<div style="padding:6px 10px;background:#eef6ff;border:1px solid #cfe0f5;border-radius:6px;margin-bottom:8px;font-size:12px">${esc(st.msg)}</div>`:''}
     <div class="toolbar" style="margin-bottom:4px">
       <label class="tl">기간</label>
       <input class="inp" type="date" id="lg-df" value="${ymd2date(st.df)}" style="width:150px"> ~
       <input class="inp" type="date" id="lg-dt" value="${ymd2date(st.dt)}" style="width:150px">
       <label class="tl">사업부</label><select class="sel" id="lg-biz">${bizOpts}</select>
       <label class="tl">분류</label><select class="sel" id="lg-cls"><option value="">전체</option><option value="원소재"${st.cls==='원소재'?' selected':''}>원소재</option><option value="사급부품"${st.cls==='사급부품'?' selected':''}>사급부품</option></select>
       <input class="inp" id="lg-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:150px">
       <button class="btn" id="lg-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">품목 ${won(st.rows.length)} · 수량 ${wonI(totq)} · 금액 ${wonI(tot)}원</span>
     </div>
     <div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap">
       <div style="flex:1;min-width:520px">
         <div style="font-weight:600;margin:2px 0 6px">📦 품목별 요약 <span style="font-size:11px;color:var(--muted)">(품번 클릭 → 오른쪽 일자·단가별 기록 · 헤더 더블클릭 정렬)</span></div>
         <div class="grid-wrap" style="max-height:460px;overflow:auto"><table class="tbl fit lg-tbl"><thead><tr>${sh('item','품번')}${sh('name','품명','cap')}${sh('biz','사업부','center')}${sh('cls','분류','center')}${sh('qty','수량','num')}${sh('pmax','단가','num')}${sh('amt','금액','num')}${sh('cnt','건','num')}</tr></thead>
         <tbody>${st.loading?spinRow(8):(st.rows.length?st.rows.map(r=>`<tr class="it-row" data-item="${esc(r.item)}" data-name="${esc(r.name)}" style="cursor:pointer;${r.item===st.sel?'background:#e3f0ff':''}"><td><b>${esc(r.item)}</b></td><td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.name)}">${esc(r.name)}</td><td class="center" style="font-size:11px;color:#33507d">${esc(r.biz||'-')}</td><td class="center"><span style="font-size:11px;padding:1px 6px;border-radius:8px;${r.cls==='원소재'?'background:#e6f0ff;color:#1c47a0':'background:#eef7ea;color:#1c7c3a'}">${esc(r.cls)}</span></td><td class="num">${wonI(r.qty)}</td><td class="num">${r.pchg?`<span style="color:#c0392b" title="단가 변동(${wonI(r.pmin)}~${wonI(r.pmax)})">${wonI(r.pmax)} ▲</span>`:wonI(r.pmax)}</td><td class="num">${wonI(r.amt)}</td><td class="num">${won(r.cnt)}</td></tr>`).join(''):`<tr><td colspan="8" class="empty">데이터 없음</td></tr>`)}</tbody>
         ${st.rows.length?`<tfoot><tr class="lg-foot"><td colspan="4" class="right">합계 ${won(st.rows.length)}품목</td><td class="num">${wonI(totq)}</td><td></td><td class="num">${wonI(tot)}</td><td class="num">${won(totc)}</td></tr></tfoot>`:''}
         </table></div>
       </div>
       <div style="flex:1;min-width:380px" id="lg-detail">${detailHtml()}</div>
     </div>
     <style>.lg-tbl tfoot .lg-foot td,.grid-wrap tfoot .lg-foot td{position:sticky;bottom:0;background:#eaf1fb;font-weight:700;border-top:2px solid #b9cbe6;z-index:3}</style>`;
    const dz=c.querySelector('#dz'),fi=c.querySelector('#dz-f');
    dz.onclick=()=>fi.click();
    dz.ondragover=e=>{e.preventDefault();dz.style.background='#e3f0ff';dz.style.borderColor='#1c7c3a';};
    dz.ondragleave=()=>{dz.style.background='#f4f9fe';dz.style.borderColor='#8fb4d6';};
    dz.ondrop=e=>{e.preventDefault();dz.style.background='#f4f9fe';dz.style.borderColor='#8fb4d6';if(e.dataTransfer.files[0])upload(e.dataTransfer.files[0]);};
    fi.onchange=()=>{if(fi.files[0]){upload(fi.files[0]);fi.value='';}};
    c.querySelectorAll('input[name=lg-upbiz]').forEach(rd=>rd.onchange=()=>{st.upBiz=rd.value;});
    const go=()=>{st.df=date2ymd(c.querySelector('#lg-df').value);st.dt=date2ymd(c.querySelector('#lg-dt').value);
      st.biz=c.querySelector('#lg-biz').value;st.cls=c.querySelector('#lg-cls').value;st.q=c.querySelector('#lg-q').value;st.sel='';st.detail=[];loadList().then(draw);};
    c.querySelector('#lg-go').onclick=go;
    c.querySelector('#lg-q').onkeyup=e=>{if(e.key==='Enter')go();};
    // #6 헤더 더블클릭 정렬(로컬)
    c.querySelectorAll('th[data-sk]').forEach(th=>th.ondblclick=()=>{const k=th.dataset.sk;
      if(st.sort.k===k)st.sort.dir*=-1;else st.sort={k,dir:(NUMK.includes(k)?-1:1)};applySort();draw();});
    // ★품번 클릭 = 우측 상세만 부분갱신(전체 재렌더 X → 스크롤 유지)
    c.querySelectorAll('.it-row').forEach(tr=>tr.onclick=()=>{st.selName=tr.dataset.name;loadDetail(tr.dataset.item);});
    wireTabs();
    attachResizers(c);
  };
  reload();
};

/* ===== 동정산 원단위 관리 — 원소재 마스터의 탭으로 호출됨(SCREEN.dongunit(host)). nx.lg_settle_unit ===== */
SCREEN.dongunit=(host)=>{
  const API=API_BASE;
  const ym2m=y=>{y=(''+(y||'')).replace(/\D/g,'');return y.length>=4?`20${y.slice(0,2)}-${y.slice(2,4)}`:'';};
  const m2ym=v=>{const s=(''+(v||'')).replace(/\D/g,'');return s.length>=6?s.slice(2,6):(s.length>=4?s.slice(0,4):'');};
  let st={s_ym:'',slist:null,s_loading:false,s_q:'',s_msg:''};
  const load=async()=>{st.s_loading=true;draw();
    try{const qs=[];if(st.s_ym)qs.push('ym='+encodeURIComponent(st.s_ym));if(st.s_q)qs.push('q='+encodeURIComponent(st.s_q));
      const j=await(await fetch(`${API}/api/lgsagub/settle_list${qs.length?('?'+qs.join('&')):''}`)).json();st.slist=j;st.s_ym=j.ym||st.s_ym;}
    catch(e){st.slist=null;st.s_msg='❌ 조회실패: '+e.message;}
    st.s_loading=false;draw();};
  const upload=async(file)=>{if(!file)return;
    if(!/^\d{4}$/.test(st.s_ym)){st.s_msg='⚠ 적용월을 먼저 선택/입력하세요.';draw();return;}
    if(!confirm(`동정산 원단위 파일을 [ ${st.s_ym} ] 적용월로 업로드합니다.\n(피앤씨 탭만, 같은 월 덮어씀)\n\n${file.name}\n계속?`))return;
    st.s_msg='업로드 중… '+file.name;draw();
    try{const fd=new FormData();fd.append('file',file);
      const j=await(await fetch(`${API}/api/lgsagub/settle_upload?ym=${encodeURIComponent(st.s_ym)}`,{method:'POST',body:fd})).json();
      if(!j.ok)st.s_msg='❌ '+(j.error||'실패');
      else st.s_msg=`✅ [${st.s_ym}] ${j.sheet} · ${wonI(j.rows)}행 · `+(j.by_gubun1||[]).map(g=>`${g.gubun1} ${wonI(g.rows)}행`).join('  ');
    }catch(e){st.s_msg='❌ '+e.message;}
    await load();};
  const copy=async()=>{
    if(!st.s_ym){st.s_msg='⚠ 복사 원본 적용월을 먼저 선택하세요.';draw();return;}
    const to=prompt(`[${st.s_ym}] 원단위를 복사할 신규 적용월(YYMM 4자리):`,'');
    if(!to||!/^\d{4}$/.test(to.trim()))return;
    st.s_msg='복사 중…';draw();
    try{const j=await(await fetch(`${API}/api/lgsagub/settle_copy?from_ym=${encodeURIComponent(st.s_ym)}&to_ym=${encodeURIComponent(to.trim())}`,{method:'POST'})).json();
      st.s_msg=j.ok?`✅ ${st.s_ym}→${to.trim()} ${wonI(j.rows)}행 복사`:'❌ 복사실패';st.s_ym=to.trim();}
    catch(e){st.s_msg='❌ '+e.message;}
    await load();};
  const draw=()=>{
    const m=st.slist, rows=(m&&m.rows)||[], yms=(m&&m.yms)||[];
    const ymOpts=`<option value="">(선택)</option>`+yms.map(y=>`<option value="${y.ym}"${st.s_ym===y.ym?' selected':''}>${y.ym} (${wonI(y.rows)}행)</option>`).join('');
    const body=st.s_loading?spinRow(12):(rows.length?rows.map(r=>`<tr>
        <td><b>${esc(r.assy_pn)}</b></td><td class="cap" style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.assy_desc)}">${esc(r.assy_desc)}</td>
        <td class="cap" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.coop)}</td>
        <td>${esc(r.sub_pn)}</td><td class="cap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.sub_desc)}">${esc(r.sub_desc)}</td>
        <td class="num">${wonI(r.qty)}</td><td class="center"><span style="font-size:11px;padding:1px 6px;border-radius:8px;${r.gubun1==='사급'?'background:#e6f0ff;color:#1c47a0':'background:#fbe9e4;color:#a03d2c'}">${esc(r.gubun1)}</span></td>
        <td class="center" style="font-size:11px">${esc(r.gubun2)}</td><td class="num">${r.od||'-'}</td><td class="num">${r.thk||'-'}</td><td class="num">${r.leng||'-'}</td><td class="num">${r.weight?r.weight.toFixed(4):'-'}</td></tr>`).join('')
      :`<tr><td colspan="12" class="empty">데이터 없음 — 적용월 선택 후 엑셀 업로드</td></tr>`);
    const sg=rows.filter(r=>r.gubun1==='사급').length, jk=rows.filter(r=>r.gubun1==='직거래').length;
    host.innerHTML=`
     <div class="page-sub" style="margin-top:2px">LG와 소통하는 <b>동정산 원단위</b>(Assy별 동부자재 소요·규격·사급/직거래 구분). 월별 큰 변경 없음 → 전월복사 후 부분수정. <code>nx.lg_settle_unit</code>. ★중량=수량반영값.</div>
     <div style="display:flex;gap:8px;align-items:stretch;margin-bottom:8px;flex-wrap:wrap">
       <div style="flex:0 0 auto;border:1px solid #cfe0f5;border-radius:8px;padding:8px 14px;background:#fbfdff;display:flex;flex-direction:column;justify-content:center">
         <div style="font-size:11px;color:#5a7597;margin-bottom:4px">적용월 <span style="color:#c0392b">*</span></div>
         <div style="display:flex;gap:6px;align-items:center"><select class="sel" id="du-sel" style="width:130px">${ymOpts}</select>
           <input type="month" class="inp" id="du-new" value="${ym2m(st.s_ym)}" style="width:140px" title="신규월 직접입력"></div></div>
       <div id="du-dz" title="동정산 원단위 엑셀(피앤씨 탭)" style="flex:1;min-width:280px;border:2px dashed #8fb4d6;border-radius:8px;padding:8px;background:#f4f9fe;color:#5a7597;text-align:center;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:12px">
         📥 동정산 <b style="margin:0 4px">원단위 엑셀</b> 드래그&드롭/클릭 <span style="color:#8aa0bd;margin-left:6px">(적용월 선택 후 · 피앤씨 탭)</span>
         <input type="file" id="du-f" accept=".xlsx,.xls" style="display:none"></div>
       <button class="btn" id="du-copy" style="flex:0 0 auto" title="선택 적용월을 신규월로 복사">📋 전월 복사로 신규월</button>
     </div>
     ${st.s_msg?`<div style="padding:6px 10px;background:#eef6ff;border:1px solid #cfe0f5;border-radius:6px;margin-bottom:8px;font-size:12px">${esc(st.s_msg)}</div>`:''}
     <div class="toolbar" style="margin-bottom:6px">
       <input class="inp" id="du-q" value="${esc(st.s_q)}" placeholder="Assy/하위 품번·품명" style="width:200px"><button class="btn" id="du-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${m?`적용월 ${esc(m.ym||'-')} · ${wonI(rows.length)}행 (사급 ${wonI(sg)}·직거래 ${wonI(jk)})`:'조회 전'}</span>
     </div>
     <div class="grid-wrap" style="max-height:calc(100vh - 360px);overflow:auto"><table class="tbl fit du-tbl"><thead><tr>
        <th>Assy P/N</th><th class="cap">Desc</th><th class="cap">협력사</th><th>P/N(하위1)</th><th class="cap">Desc</th>
        <th class="num">수량</th><th class="center">구분1</th><th class="center">구분2</th><th class="num">외경</th><th class="num">T</th><th class="num">길이</th><th class="num">중량</th></tr></thead>
       <tbody>${body}</tbody></table></div>
     <style>.du-tbl thead th{position:sticky;top:0;background:#f1f5fb;z-index:4}</style>`;
    const dz=host.querySelector('#du-dz'),fi=host.querySelector('#du-f');
    dz.onclick=()=>fi.click();
    dz.ondragover=e=>{e.preventDefault();dz.style.background='#e3f0ff';};dz.ondragleave=()=>{dz.style.background='#f4f9fe';};
    dz.ondrop=e=>{e.preventDefault();dz.style.background='#f4f9fe';if(e.dataTransfer.files[0])upload(e.dataTransfer.files[0]);};
    fi.onchange=()=>{if(fi.files[0]){upload(fi.files[0]);fi.value='';}};
    host.querySelector('#du-sel').onchange=e=>{st.s_ym=e.target.value;load();};
    host.querySelector('#du-new').oninput=e=>{st.s_ym=m2ym(e.target.value);};
    host.querySelector('#du-copy').onclick=copy;
    host.querySelector('#du-go').onclick=()=>{st.s_q=host.querySelector('#du-q').value.trim();load();};
    host.querySelector('#du-q').onkeyup=e=>{if(e.key==='Enter'){st.s_q=e.target.value.trim();load();}};
    attachResizers(host);
  };
  load();
};

/* ===== 도입-수입입력(w_pu_stock_c_040, tag=P) · 도입-수출입력(w_pu_stock_c_050, tag=Q) — PU_T_STOCK_MAINT_C 라이브 조회 ===== */
/* 금액(KRW)=금액×환율 버림(레거시 검증). 거래처별 그룹 소계 + 총계. */
(function(){
  const CURN={KRW:'원',USD:'달러',JPY:'엔',EUR:'유로',CNY:'위안',RMB:'위안'};
  const fmtY=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;};
  const dIn=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const nD=(v,n)=>{const x=+v||0;return x.toLocaleString('en-US',{minimumFractionDigits:n,maximumFractionDigits:n});};
  const wonI=v=>Math.round(+v||0).toLocaleString('en-US');
  const curN=x=>CURN[(''+x).trim()]||(''+x).trim()||'';
  const _def=(days)=>{const t=new Date(),f=new Date();f.setDate(1);if(days)f.setDate(t.getDate()-days);
    const g=d=>`20${String(d.getFullYear()).slice(2)}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;return[g(f),g(t)];};

  // 커스텀 오토컴플리트 드롭다운(datalist 브라우저 재필터 문제 회피 — 서버결과 그대로 표시·클릭선택)
  function acAttach(inp, fetchFn, onPick){
    let box=null, t=null, items=[], idx=-1;
    const close=()=>{if(box){box.remove();box=null;}idx=-1;};
    const open=(list)=>{close();items=list;if(!list||!list.length)return;
      box=document.createElement('div');const r=inp.getBoundingClientRect();
      box.style.cssText='position:fixed;left:'+r.left+'px;top:'+(r.bottom+2)+'px;width:'+Math.max(r.width,240)+'px;max-height:250px;overflow:auto;background:#fff;border:1px solid #b9c6dd;border-radius:6px;box-shadow:0 10px 28px rgba(0,0,0,.2);z-index:1300;font-size:13px';
      list.forEach((it,i)=>{const o=document.createElement('div');o.className='ac-op';
        o.style.cssText='padding:6px 10px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';o.innerHTML=it.label;
        o.onmousedown=e=>{e.preventDefault();onPick(it);close();};box.appendChild(o);});
      document.body.appendChild(box);};
    inp.addEventListener('input',()=>{const q=inp.value.trim();clearTimeout(t);if(q.length<1){close();return;}
      t=setTimeout(async()=>{try{open(await fetchFn(q));}catch(e){close();}},200);});
    inp.addEventListener('blur',()=>setTimeout(close,150));
    inp.addEventListener('keydown',e=>{if(!box)return;const ops=box.querySelectorAll('.ac-op');
      if(e.key==='ArrowDown'){e.preventDefault();idx=Math.min(idx+1,ops.length-1);}
      else if(e.key==='ArrowUp'){e.preventDefault();idx=Math.max(idx-1,0);}
      else if(e.key==='Enter'&&idx>=0){e.preventDefault();onPick(items[idx]);close();return;}
      else if(e.key==='Escape'){close();return;} else return;
      ops.forEach((o,i)=>o.style.background=i===idx?'#eaf2fd':'');if(ops[idx])ops[idx].scrollIntoView({block:'nearest'});});
  }
  function dopipView(c, kind){
    const wide = kind==='pur';
    const ep = wide ? 'purchase' : 'sale';
    const dateLbl = wide ? '입고일자' : '출고일자';
    // 컬럼정의
    const COLS = wide ? [
      ['ymd',dateLbl,'center',r=>fmtY(r.ymd)],['cust_nm','거래처','cap',r=>esc(r.cust_nm)],
      ['mat','품목번호','',r=>`<b>${esc(r.mat)}</b>`],['qty','수량','num',r=>nD(r.qty,0)],
      ['cur','통화','center',r=>esc(r.cur)],['cost','단가(외환)','num',r=>nD(r.cost,r.cost%1?4:2)],
      ['amt','금액','num',r=>nD(r.amt,4)],['krw','금액(KRW)','num',r=>wonI(r.krw)],
      ['rate','환율','num',r=>r.cur==='KRW'?'':nD(r.rate,2)],['remarks','비고','cap',r=>esc(r.remarks)],
      ['duty','관세','num',r=>r.duty?wonI(r.duty):''],['fare','운임','num',r=>r.fare?wonI(r.fare):''],
      ['tax','부과세과표','num',r=>r.tax?wonI(r.tax):''],['insp','신고번호','',r=>esc(r.insp)],
      ['bl','B/L 번호','',r=>esc(r.bl)],['hs','HS CODE','',r=>esc(r.hs)],
    ] : [
      ['ymd',dateLbl,'center',r=>fmtY(r.ymd)],['cust_nm','거래처','cap',r=>esc(r.cust_nm)],
      ['mat','품목번호','',r=>`<b>${esc(r.mat)}</b>`],['qty','수량','num',r=>nD(r.qty,0)],
      ['cur','통화','center',r=>esc(r.cur)],['cost','단가(외화)','num',r=>nD(r.cost,r.cost%1?4:2)],
      ['amt','금액','num',r=>nD(r.amt,4)],['krw','금액(KRW)','num',r=>wonI(r.krw)],
      ['rate','환율','num',r=>r.cur==='KRW'?'':nD(r.rate,2)],['remarks','비고','cap',r=>esc(r.remarks)],
    ];
    const qi = COLS.findIndex(x=>x[0]==='qty');
    const API=API_BASE;
    const [df,dt]=_def(wide?0:45);   // 수입=당월1일~오늘, 수출=45일
    const sid = wide?'dopippur':'dopipsale';
    const canEdit = (typeof PERM!=='undefined' && PERM.canEdit)?PERM.canEdit(sid):true;
    let from=df, to=dt, cq='', cqNm='', mq='', iq='', bq='', rows=[], tot={}, loading=false, msg='', sel=null, form=null;
    const load=async()=>{loading=true;msg='';draw();
      try{let u=`${API}/api/dopip/${ep}?from_ymd=${inD(from)}&to_ymd=${inD(to)}`;
        if(cq)u+=`&cust=${encodeURIComponent(cq)}`; if(mq)u+=`&mat=${encodeURIComponent(mq)}`;
        if(wide){if(iq)u+=`&insp=${encodeURIComponent(iq)}`; if(bq)u+=`&bl=${encodeURIComponent(bq)}`;}
        const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();
        rows=j.rows||[];tot=j.tot||{};}
      catch(e){rows=[];tot={};msg='백엔드 연결 실패';}
      loading=false;draw();};
    const rowHtml=r=>{const on=sel&&sel.ymd===r.ymd&&sel.seq===r.seq;
      return `<tr class="dp-row${on?' sel':''}" data-y="${r.ymd}" data-s="${r.seq}" style="cursor:${canEdit?'pointer':'default'}${on?';background:#dce9ff':''}">${COLS.map(cd=>{const cap=cd[2].indexOf('cap')>=0;return `<td class="${cd[2]}"${cap?` title="${esc(cd[3](r).replace(/<[^>]+>/g,''))}"`:''}>${cd[3](r)}</td>`;}).join('')}</tr>`;};
    const sub=(label,q,a,k,cls)=>`<tr class="${cls||'subtot'}"><td colspan="${qi}" class="right">${esc(label)}</td><td class="num">${nD(q,0)}</td><td></td><td></td><td class="num">${nD(a,4)}</td><td class="num">${wonI(k)}</td><td colspan="${COLS.length-qi-4}"></td></tr>`;
    // ===== 편집 모달 (document.body 렌더 = 조상 클리핑 방지) =====
    const CUROPT=['USD','RMB','CNY','JPY','EUR','KRW'];
    let modalEl=null, acT=null, acCust={};
    if(!document.getElementById('dp-style')){const st=document.createElement('style');st.id='dp-style';
      st.textContent='.dp-grid thead th{position:sticky;top:0;z-index:3;background:#f4f7fc}'
        +'.dp-grid tr.grandtot td{position:sticky;bottom:0;background:#eaf1fb;z-index:2;font-weight:700;border-top:2px solid #cdd9ef}'
        +'.dp-row.sel td{background:#dce9ff !important}'
        +'.dp-modal .fl{text-align:right;white-space:nowrap;color:#4a5563;font-size:13px}'
        +'.dp-modal input,.dp-modal select{border:1px solid #cbd5e6;border-radius:5px;padding:5px 8px;font-size:13px;box-sizing:border-box}';
      document.head.appendChild(st);}
    const removeModal=()=>{ if(modalEl){modalEl.remove();modalEl=null;} };
    const modalHtml=()=>{const f=form.data, amt=(+f.qty||0)*(+f.cost||0), krw=Math.trunc(amt*(+f.rate||0));
      const L=(t)=>`<label class="fl">${t}</label>`;
      const N=(k,w)=>`<input class="dpf" data-k="${k}" value="${esc(f[k]!=null&&f[k]!==''?f[k]:'')}" style="width:${w||'130px'};text-align:right">`;
      const T=(k,w)=>`<input class="dpf" data-k="${k}" value="${esc(f[k]!=null&&f[k]!==''?f[k]:'')}" style="width:${w||'100%'}">`;
      const R=[];
      R.push(L(wide?'입고일자':'출고일자')+`<input class="dpf" data-k="ymd" type="date" value="${esc(dIn(f.ymd))}" ${form.mode==='edit'?'readonly':''} style="width:150px">`
           + L('거래처')+`<input class="dpf" data-k="cust_nm" autocomplete="off" value="${esc(f.cust_nm||'')}" placeholder="거래처명/코드 입력" style="width:100%">`);
      R.push(L('품목번호')+`<input class="dpf" data-k="mat" autocomplete="off" value="${esc(f.mat||'')}" placeholder="자도번/품명 입력" style="width:100%">`
           + L('수량')+N('qty'));
      R.push(L('통화')+`<select class="dpf" data-k="cur" style="width:120px">${CUROPT.map(x=>`<option value="${x}" ${(''+f.cur)===x?'selected':''}>${x}</option>`).join('')}</select>`
           + L('단가(외환)')+N('cost'));
      R.push(L('환율')+N('rate')+L('비고')+T('remarks'));
      if(wide){ R.push(L('관세')+N('duty')+L('운임')+N('fare'));
        R.push(L('부가세과표')+N('tax')+L('신고번호')+T('insp'));
        R.push(L('B/L번호')+T('bl')+L('HS CODE')+T('hs')); }
      return `<div class="wr-modal dp-modal" style="position:fixed;inset:0;z-index:1200;background:rgba(20,30,50,.44);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:48px 12px">
       <div style="background:#fff;border-radius:12px;padding:20px 24px;width:660px;max-width:94vw;box-shadow:0 14px 50px rgba(0,0,0,.34)">
        <div style="font-weight:700;font-size:15px;margin-bottom:16px">${form.mode==='new'?('➕ 도입-'+(wide?'수입':'수출')+' 추가'):'✏️ 수정 ('+esc(f.ymd)+'-'+f.seq+')'}</div>
        <div style="display:grid;grid-template-columns:80px 1fr 80px 1fr;gap:11px 12px;align-items:center">${R.join('')}</div>
        <div style="margin-top:14px;padding:9px 12px;background:#f4f7fc;border-radius:7px;font-size:13px">금액(외환) <b id="dp-amt">${nD(amt,4)}</b> · 금액(KRW) <b id="dp-krw">${wonI(krw)}</b> <span style="color:#888">(=수량×단가, ×환율 버림 자동)</span></div>
        <div style="margin-top:18px;text-align:right"><button class="btn ghost" id="dp-cancel">취소</button> <button class="btn" id="dp-save" style="background:#1c47a0;color:#fff">💾 저장</button></div>
       </div></div>`;};
    const mq2=k=>{const x=modalEl&&modalEl.querySelector('.dpf[data-k="'+k+'"]');return x?x.value.trim():'';};
    const recalc=()=>{const amt=(+mq2('qty')||0)*(+mq2('cost')||0), krw=Math.trunc(amt*(+mq2('rate')||0));
      const ae=modalEl.querySelector('#dp-amt'),ke=modalEl.querySelector('#dp-krw');if(ae)ae.textContent=nD(amt,4);if(ke)ke.textContent=wonI(krw);};
    const wireModal=()=>{
      modalEl.querySelectorAll('.dpf').forEach(el=>el.oninput=recalc);
      modalEl.querySelector('#dp-cancel').onclick=()=>{removeModal();form=null;};
      modalEl.querySelector('#dp-save').onclick=doSave;
      const cel=modalEl.querySelector('.dpf[data-k="cust_nm"]');
      if(cel)acAttach(cel, async q=>{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(q)}`);
          return ((await r.json()).rows||[]).map(x=>({name:x.name,code:x.code,label:`${esc(x.name)} <span style="color:#8896ab">${esc(x.code)}</span>`}));},
        it=>{cel.value=it.name;acCust[it.name]=it.code;recalc();});
      const mel=modalEl.querySelector('.dpf[data-k="mat"]');
      if(mel)acAttach(mel, async q=>{const r=await fetch(`${API}/api/item/list?q=${encodeURIComponent(q)}&limit=25`);
          return ((await r.json()).rows||[]).map(x=>({name:x.item_code,label:`<b>${esc(x.item_code)}</b> <span style="color:#8896ab">${esc(x.nm||'')}</span>`}));},
        it=>{mel.value=it.name;recalc();});
      const fi=modalEl.querySelector('.dpf');if(fi)fi.focus();
    };
    const showModal=()=>{removeModal();modalEl=document.createElement('div');modalEl.innerHTML=modalHtml();document.body.appendChild(modalEl);wireModal();};
    const openAdd=()=>{form={mode:'new',data:{ymd:inD(to),cust:'',cust_nm:'',mat:'',qty:0,cur:'USD',cost:0,rate:0,remarks:''}};showModal();};
    // ===== 다건 그리드 입력(레거시 w_pu_stock_c_045): 거래처 먼저 → 그 거래처 품번 오토컴플리트, 여러 행 한번에 =====
    const openAddGrid=()=>{
      const G={ymd:inD(to),cust:'',cust_nm:'',cur:'USD',rate:'',rows:[]};
      const blank=()=>({mat:'',nm:'',qty:'',cost:'',duty:'',fare:'',tax:'',insp:'',bl:'',hs:'',remarks:''});
      for(let i=0;i<6;i++)G.rows.push(blank());
      const COLD = wide
        ? [['mat','품번','ac',150],['nm','품명','ro',150],['qty','수량','n',72],['cost','단가(외환)','n',88],['amt','금액','calc',90],['krw','금액(KRW)','calc',100],['duty','관세','n',72],['fare','운임','n',72],['tax','부가세과표','n',84],['insp','신고번호','t',106],['bl','B/L번호','t',106],['hs','HS','t',68],['remarks','비고','t',96]]
        : [['mat','품번','ac',160],['nm','품명','ro',170],['qty','수량','n',80],['cost','단가(외환)','n',90],['amt','금액','calc',90],['krw','금액(KRW)','calc',100],['remarks','비고','t',150]];
      let gEl=null; const trunc=v=>Math.trunc(+v||0);
      const cellVal=(r,k)=>{const a=(+r.qty||0)*(+r.cost||0); if(k==='amt')return nD(a,4); if(k==='krw')return wonI(trunc(a*(+G.rate||0))); return r[k]!=null?r[k]:'';};
      const rowTr=(r,i)=>`<tr data-i="${i}">`+COLD.map(cd=>{const k=cd[0],ty=cd[2],w=cd[3];
          if(ty==='calc')return `<td class="num" style="text-align:right;padding:2px 6px"><span class="g-${k}" data-i="${i}">${cellVal(r,k)}</span></td>`;
          if(ty==='ro')return `<td style="padding:2px 4px"><input class="ge" data-i="${i}" data-k="${k}" value="${esc(r[k]||'')}" readonly style="width:${w}px;background:#f3f6fb;border:0;font-size:12px"></td>`;
          const al=(ty==='n')?'text-align:right':'';
          return `<td style="padding:2px 4px"><input class="ge${ty==='ac'?' gac':''}" data-i="${i}" data-k="${k}" value="${esc(r[k]||'')}" ${ty==='ac'?'autocomplete="off" placeholder="자도번"':''} style="width:${w}px;${al};font-size:12px;border:1px solid #d3dcea;border-radius:4px;padding:3px 5px"></td>`;
        }).join('')+`<td class="center"><button class="grx" data-i="${i}" title="행삭제" style="border:0;background:none;color:#c0392b;cursor:pointer;font-size:14px">✕</button></td></tr>`;
      const gridHtml=()=>`<div class="wr-modal dp-modal" style="position:fixed;inset:0;z-index:1200;background:rgba(20,30,50,.44);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:38px 10px">
        <div style="background:#fff;border-radius:12px;padding:18px 20px;width:${wide?1500:720}px;max-width:98vw;box-shadow:0 14px 50px rgba(0,0,0,.34)">
         <div style="font-weight:700;font-size:15px;margin-bottom:12px">➕ 도입-${wide?'수입':'수출'} 다건 입력 <span style="font-size:12px;color:#888;font-weight:400">· 거래처 먼저 선택 → 그 거래처 품번 검색</span></div>
         <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px;padding:10px 12px;background:#f4f7fc;border-radius:8px">
           <label class="fl">${wide?'입고일자':'출고일자'}</label><input class="gh" data-k="ymd" type="date" value="${esc(dIn(G.ymd))}" style="width:145px">
           <label class="fl">거래처</label><input class="gh gac-cust" data-k="cust_nm" autocomplete="off" value="${esc(G.cust_nm)}" placeholder="거래처명/코드" style="width:180px"><span id="g-custcode" style="font-size:11px;color:#1c47a0;min-width:34px">${esc(G.cust||'')}</span>
           <label class="fl">통화</label><select class="gh" data-k="cur" style="width:88px">${CUROPT.map(x=>`<option value="${x}" ${G.cur===x?'selected':''}>${x}</option>`).join('')}</select>
           <label class="fl">환율</label><input class="gh" data-k="rate" value="${esc(G.rate)}" style="width:88px;text-align:right" placeholder="0">
         </div>
         <div style="max-height:52vh;overflow:auto;border:1px solid #d3dcea;border-radius:8px">
           <table class="tbl" style="font-size:12px;min-width:100%"><thead><tr style="position:sticky;top:0;background:#eef3fb;z-index:2">${COLD.map(cd=>`<th style="padding:5px 6px;white-space:nowrap">${cd[1]}</th>`).join('')}<th></th></tr></thead>
           <tbody id="g-body">${G.rows.map((r,i)=>rowTr(r,i)).join('')}</tbody></table>
         </div>
         <div style="display:flex;align-items:center;gap:12px;margin-top:10px">
           <button class="btn ghost" id="g-addrow">＋ 행추가</button><div style="flex:1"></div>
           <span style="font-size:13px">합계 금액 <b id="g-tamt">0</b> · KRW <b id="g-tkrw">0</b> 원</span>
         </div>
         <div style="margin-top:14px;text-align:right"><button class="btn ghost" id="g-cancel">취소</button> <button class="btn" id="g-save" style="background:#1c47a0;color:#fff">💾 저장(다건)</button></div>
        </div></div>`;
      const recalc=()=>{let ta=0,tk=0;G.rows.forEach((r,i)=>{const a=(+r.qty||0)*(+r.cost||0),k=trunc(a*(+G.rate||0));ta+=a;tk+=k;
          const ae=gEl.querySelector(`.g-amt[data-i="${i}"]`),ke=gEl.querySelector(`.g-krw[data-i="${i}"]`);if(ae)ae.textContent=nD(a,4);if(ke)ke.textContent=wonI(k);});
        const te=gEl.querySelector('#g-tamt'),tke=gEl.querySelector('#g-tkrw');if(te)te.textContent=nD(ta,4);if(tke)tke.textContent=wonI(tk);};
      const wireRow=tr=>{const i=+tr.dataset.i;
        tr.querySelectorAll('.ge').forEach(el=>{if(el.readOnly)return;const k=el.dataset.k;el.oninput=()=>{G.rows[i][k]=el.value;if(k==='qty'||k==='cost')recalc();};});
        const rx=tr.querySelector('.grx');if(rx)rx.onclick=()=>{if(G.rows.length<=1)G.rows[0]=blank();else G.rows.splice(i,1);renderBody();};
        const ac=tr.querySelector('.gac');
        if(ac)acAttach(ac, async q=>{ if(!G.cust)return [{label:'⚠ 거래처를 먼저 선택하세요',_none:1}];
            const r=await fetch(`${API}/api/dopip/items?kind=${wide?'pur':'sale'}&cust=${encodeURIComponent(G.cust)}&q=${encodeURIComponent(q)}`);
            return ((await r.json()).rows||[]).map(x=>({mat:x.mat,nm:x.nm,cost:x.cost,cur:x.cur,label:`<b>${esc(x.mat)}</b> <span style="color:#8896ab">${esc(x.nm||'')}</span> <span style="color:#1c7c3a">${x.cost||''} ${esc(x.cur||'')}</span>`}));},
          it=>{if(it._none)return;G.rows[i].mat=it.mat;G.rows[i].nm=it.nm||'';if(!G.rows[i].cost&&it.cost)G.rows[i].cost=it.cost;
            if(it.cur&&it.cur!==G.cur){G.cur=it.cur;const cs=gEl.querySelector('.gh[data-k="cur"]');if(cs)cs.value=it.cur;}
            renderBody();});};
      const renderBody=()=>{const tb=gEl.querySelector('#g-body');tb.innerHTML=G.rows.map((r,i)=>rowTr(r,i)).join('');tb.querySelectorAll('tr').forEach(wireRow);recalc();};
      const doSaveBatch=async()=>{
        if(!G.cust){alert('거래처를 먼저 선택하세요 (목록에서 클릭)');return;}
        const ymd=inD(gEl.querySelector('.gh[data-k="ymd"]').value);if(!ymd){alert('일자 필요');return;}
        const valid=G.rows.filter(r=>(''+r.mat).trim()&&(+r.qty||0)!==0);
        if(!valid.length){alert('품번·수량이 있는 행이 1개 이상 필요합니다');return;}
        const body={kind:wide?'pur':'sale',ymd:ymd,cust:G.cust,cur:G.cur,rate:+G.rate||0,
          rows:valid.map(r=>({mat:(''+r.mat).trim(),qty:+r.qty||0,cost:+r.cost||0,duty:+r.duty||0,fare:+r.fare||0,tax:+r.tax||0,insp:(''+(r.insp||'')).trim(),bl:(''+(r.bl||'')).trim(),hs:(''+(r.hs||'')).trim(),remarks:(''+(r.remarks||'')).trim()}))};
        try{const r=await fetch(`${API}/api/dopip/save_batch`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
          const j=await r.json();if(!r.ok){alert('저장 실패: '+(j.detail||r.status));return;}
          gEl.remove();gEl=null;sel={ymd:ymd,seq:(j.seqs&&j.seqs[0])||0};alert(`${j.inserted}건 저장되었습니다 (전표 ${j.sheet})`);load();
          }catch(e){alert('저장 오류: '+e.message);}};
      const wireHeader=()=>{
        gEl.querySelectorAll('.gh').forEach(el=>{const k=el.dataset.k;el.onchange=()=>{G[k]=el.value;if(k==='rate')recalc();};if(k==='rate')el.oninput=()=>{G.rate=el.value;recalc();};});
        const ce=gEl.querySelector('.gac-cust');
        if(ce)acAttach(ce, async q=>{const r=await fetch(`${API}/api/dopip/vendors?kind=${wide?'pur':'sale'}&q=${encodeURIComponent(q)}`);
            return ((await r.json()).rows||[]).map(x=>({code:x.code,name:x.name,label:`${esc(x.name)} <span style="color:#8896ab">${esc(x.code)}</span>`}));},
          it=>{G.cust=it.code;G.cust_nm=it.name;ce.value=it.name;const cc=gEl.querySelector('#g-custcode');if(cc)cc.textContent=it.code;});
        gEl.querySelector('#g-addrow').onclick=()=>{G.rows.push(blank());renderBody();};
        gEl.querySelector('#g-cancel').onclick=()=>{gEl.remove();gEl=null;};
        gEl.querySelector('#g-save').onclick=doSaveBatch;};
      gEl=document.createElement('div');gEl.innerHTML=gridHtml();document.body.appendChild(gEl);
      wireHeader();renderBody();const f=gEl.querySelector('.gac-cust');if(f)f.focus();
    };
    const openEdit=()=>{if(!sel){alert('행을 선택하세요');return;}const r=rows.find(x=>x.ymd===sel.ymd&&x.seq===sel.seq);if(r){form={mode:'edit',data:Object.assign({},r)};showModal();}};
    const doSave=async()=>{const f=form.data;
      const custNm=mq2('cust_nm'); let cust=acCust[custNm]||'';
      if(!cust){ if(custNm===(f.cust_nm||'')) cust=f.cust||''; else if(/^\d+$/.test(custNm)) cust=custNm; }
      const body={kind:wide?'pur':'sale',seq:form.mode==='edit'?f.seq:0,ymd:inD(mq2('ymd')),cust:cust,mat:mq2('mat'),
        qty:mq2('qty'),cur:mq2('cur'),cost:mq2('cost'),rate:mq2('rate'),remarks:mq2('remarks')};
      if(wide){body.duty=mq2('duty');body.fare=mq2('fare');body.tax=mq2('tax');body.insp=mq2('insp');body.bl=mq2('bl');body.hs=mq2('hs');}
      if(!body.ymd||!cust||!body.mat){alert('일자·거래처·품목번호 필수 (거래처는 목록에서 선택)');return;}
      try{const r=await fetch(`${API}/api/dopip/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await r.json();if(!r.ok){alert('저장 실패: '+(j.detail||r.status));return;}
        removeModal();form=null;sel={ymd:body.ymd,seq:j.seq};load();}
      catch(e){alert('저장 오류: '+e.message);}};
    const doDelete=async()=>{if(!sel){alert('삭제할 행을 선택하세요');return;}
      if(!confirm(`${sel.ymd}-${sel.seq} 행을 삭제할까요?`))return;
      try{const r=await fetch(`${API}/api/dopip/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:wide?'pur':'sale',ymd:sel.ymd,seq:sel.seq})});
        const j=await r.json();if(!r.ok){alert('삭제 실패: '+(j.detail||r.status));return;}
        sel=null;load();}
      catch(e){alert('삭제 오류: '+e.message);}};
    const draw=()=>{
      c.innerHTML=`<div style="display:flex;flex-direction:column;height:100%">
       <div class="page-title" style="margin-bottom:2px">${wide?'🚢 도입-수입입력':'✈️ 도입-수출입력'} <span style="font-size:12px;color:var(--muted);font-weight:400">${wide?'해외 수입(구매)':'해외 수출(판매)'} · nx</span></div>
       <div class="page-sub" style="margin-bottom:6px">원본 <code>w_pu_stock_c_0${wide?'40':'50'}</code> · <code>nx.PU_T_STOCK_MAINT_C</code> (MAINT_TAG='${wide?'P':'Q'}') · 금액(KRW)=금액×환율(버림) · 행 클릭=선택·더블클릭=수정</div>
       <div class="toolbar" style="gap:5px">
         <label class="tl" style="margin:0">${wide?'입고':'출고'}</label>
         <input type="date" class="inp" id="df" value="${esc(from)}" style="width:118px"><span style="color:var(--muted);margin:0 -3px">~</span><input type="date" class="inp" id="dt" value="${esc(to)}" style="width:118px">
         <input class="inp" id="cqn" placeholder="거래처명" value="${esc(cqNm)}" autocomplete="off" style="width:118px">
         <input class="inp" id="mq" placeholder="자도번" value="${esc(mq)}" style="width:100px">
         ${wide?`<input class="inp" id="iq" placeholder="신고번호" value="${esc(iq)}" style="width:100px"><input class="inp" id="bq" placeholder="B/L번호" value="${esc(bq)}" style="width:95px">`:''}
         <button class="btn" id="go">🔍조회</button>
         ${canEdit?`<button class="btn" id="add" style="background:#1c7c3a;color:#fff">➕추가</button><button class="btn" id="edit">✏️수정</button><button class="btn" id="del" style="color:#c0392b">🗑삭제</button>`:''}
         <div class="spacer"></div><button class="btn xls" id="xls">📥엑셀</button>
       </div>
       <div class="summary-bar" id="sum" style="flex:0 0 auto"></div>
       <div class="grid-wrap dp-grid" style="flex:1;min-height:0;overflow:auto"><table class="tbl fit"><thead><tr>${COLS.map(cd=>`<th class="${cd[2]}">${cd[1]}</th>`).join('')}</tr></thead><tbody id="body"></tbody></table></div>
       <div class="rowcount" id="cnt" style="flex:0 0 auto"></div></div>`;
      const g=id=>c.querySelector(id);
      let html='';
      if(loading) html=`<tr><td colspan="${COLS.length}" class="empty">${typeof SPIN!=='undefined'?SPIN:''}조회 중…</td></tr>`;
      else if(msg) html=`<tr><td colspan="${COLS.length}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`;
      else if(!rows.length) html=`<tr><td colspan="${COLS.length}" class="empty">결과 없음</td></tr>`;
      else{ let gv=null,sq=0,sa=0,sk=0;
        rows.forEach(r=>{ const gk=r.cust+'|'+r.ymd; if(gv!==null && gk!==gv){ html+=sub('소계',sq,sa,sk); sq=sa=sk=0; }
          html+=rowHtml(r); sq+=+r.qty||0; sa+=+r.amt||0; sk+=+r.krw||0; gv=gk; });
        if(gv!==null) html+=sub('소계',sq,sa,sk);
        html+=sub('총계',tot.qty||0,tot.amt||0,tot.krw||0,'grandtot');
      }
      g('#body').innerHTML=html;
      g('#sum').innerHTML=`<div class="s-item">건수 <b>${won(tot.cnt||0)}</b></div><div class="s-item">수량 <b>${nD(tot.qty||0,0)}</b></div><div class="s-item">금액 <b>${nD(tot.amt||0,3)}</b></div><div class="s-item">금액(KRW) <b>${wonI(tot.krw||0)} 원</b></div>`;
      g('#cnt').textContent=`${tot.cnt||0}건${sel?` · 선택 ${sel.ymd}-${sel.seq}`:''}`;
      const go=()=>{from=g('#df').value;to=g('#dt').value;
        const nm=g('#cqn')?g('#cqn').value.trim():'';
        if(!nm){cq='';cqNm='';} else if(nm===cqNm){} else if(/^\d+$/.test(nm)){cq=nm;cqNm=nm;} else {cq='';cqNm=nm;}
        mq=g('#mq').value.trim();if(wide){iq=g('#iq').value.trim();bq=g('#bq').value.trim();}sel=null;load();};
      g('#go').onclick=go;
      c.querySelectorAll('.toolbar .inp').forEach(el=>el.onkeyup=e=>{if(e.key==='Enter')go();});
      const cqnEl=g('#cqn'); if(cqnEl)acAttach(cqnEl, async q=>{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(q)}`);
        return ((await r.json()).rows||[]).map(x=>({name:x.name,code:x.code,label:`${esc(x.name)} <span style="color:#8896ab">${esc(x.code)}</span>`}));},
        it=>{cq=it.code;cqNm=it.name;cqnEl.value=it.name;go();});
      g('#xls').onclick=()=>{const hd=COLS.map(cd=>cd[1]);
        downloadCSV((wide?'도입수입입력':'도입수출입력')+'_'+inD(from)+'_'+inD(to)+'.csv',hd,rows.map(r=>COLS.map(cd=>(''+cd[3](r)).replace(/<[^>]+>/g,''))));};
      c.querySelectorAll('.dp-row').forEach(tr=>{tr.onclick=()=>{sel={ymd:tr.dataset.y,seq:+tr.dataset.s};draw();};
        if(canEdit)tr.ondblclick=()=>{sel={ymd:tr.dataset.y,seq:+tr.dataset.s};openEdit();};});
      if(canEdit){const a=g('#add'),e=g('#edit'),d=g('#del');
        if(a)a.onclick=openAddGrid; if(e)e.onclick=openEdit; if(d)d.onclick=doDelete;}
      if(typeof attachResizers!=='undefined')attachResizers(c);
    };
    load();
  }
  SCREEN.dopippur=(c)=>dopipView(c,'pur');
  SCREEN.dopipsale=(c)=>dopipView(c,'sale');
})();


/* ==== 자재입고진행현황 (구매/자재) — 레거시 w_pr_input_010_part 이식 ====
   기준일부터 N근무일 동안 자재(자도번)별 소요계획·진행상태.
   ★구분 4종 = 전체(자도번 집계 + 클릭하면 제번 펼침) / 집계 / 제번 / 도번별
   ★IN/OUT 은 INPUT 만(사용자 지정 — OUTPUT 은 계획DB 차이라 2차)
   ★일자축 = 기준일부터 달력일, 근무일이 N일 찰 때까지(휴무일도 칸으로 나오되 0)
     레거시 실측: 기준일 260828(휴무) → 28금·29토·30일·31월·01화·02수 */
SCREEN.matinput=(c)=>{
  const API=API_BASE;
  // ★num 은 전역이 아니다(core.js:2070 은 _mkMagam 지역) — 여기서 선언해야 한다
  const num=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const _t=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const y6=(s)=>{const d=(''+(s||'')).replace(/\D/g,'');return d.length>=8?d.slice(2,8):d;};
  const DOW=['일','월','화','수','목','금','토'];
  const dlab=(ymd)=>{const s=''+(ymd||'');if(s.length!==6)return s;
    const d=new Date(2000+ +s.slice(0,2), +s.slice(2,4)-1, +s.slice(4,6));
    return `${s.slice(4,6)}${DOW[d.getDay()]}`;};
  // LG INPUT — 0942 → 09:42 (사용자 요청)
  const hm4=(s)=>{s=(''+(s||'')).replace(/\D/g,'');
    return s.length>=4?`${s.slice(0,2)}:${s.slice(2,4)}`:s;};
  // ★헤더 주황 = 주말(토·일)만. 레거시가 그렇다.
  //   회사달력상 휴무(work=0)로 칠하면 평일인 기준일(8/28 금)까지 주황이 된다.
  const dowOff=(ymd)=>{const s=''+(ymd||'');if(s.length!==6)return false;
    const w=new Date(2000+ +s.slice(0,2), +s.slice(2,4)-1, +s.slice(4,6)).getDay();
    return w===0||w===6;};

  let base=_t(), days=4, gubun='all', cust='', line='', wo='', doban='', jado='';
  let open=new Set();          // ★집계에서 클릭해 펼친 자도번(그 위로 제번이 뜬다)
  let dets=[];                 // ★서버가 준 제번 상세 원본(구분 전환의 기준)
  let rows=[], cal=[], loading=false, msg='';
  let cnt=0, detCnt=0, totQty=0, totLot=0, totDay={};
  let opts={lines:[],custs:[]};

  const loadOpts=async()=>{try{
    const r=await fetch(`${API}/api/matinput/opts`);opts=await r.json();
  }catch(e){opts={lines:[],custs:[]};}};

  // 코드 ↔ 거래처명 상호 변환 (두 칸이 서로를 채운다)
  const custNm=()=>{const v=(cust||'').trim();if(!v)return '';
    const f=(opts.custs||[]).find(x=>x.cc===v);return f?f.nm:'';};
  const nm2cc=(nm)=>{const v=(nm||'').trim();if(!v)return '';
    const L=(opts.custs||[]);
    const ex=L.find(x=>x.nm===v);if(ex)return ex.cc;          // 정확일치 우선
    const hit=L.filter(x=>x.nm.indexOf(v)>=0);                 // 부분일치는 유일할 때만
    return hit.length===1?hit[0].cc:'';};

  const load=async()=>{loading=true;msg='';draw();
    try{
      const u=`${API}/api/matinput/list?base_ymd=${y6(base)}&days=${days}&gubun=${gubun}`
        +`&cust=${encodeURIComponent(cust.trim())}&line=${encodeURIComponent(line.trim())}`
        +`&wo=${encodeURIComponent(wo.trim())}&doban=${encodeURIComponent(doban.trim())}`
        +`&jadoban=${encodeURIComponent(jado.trim())}`;
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();
      dets=j.rows||[];cal=j.cal||[];detCnt=j.det_cnt||0;
      totQty=j.tot_qty||0;totLot=j.tot_lot||0;totDay=j.tot_day||{};
      rows=viewRows();cnt=rows.length;msg='';
    }catch(e){msg='조회 실패 — '+e.message;dets=[];rows=[];cal=[];cnt=detCnt=0;}
    loading=false;draw();};

  // 구분 라디오 = 재조회 없이 즉시 전환(스크롤 유지)
  const reView=()=>{const w=c.querySelector('.mi-wrap');const sc=w?w.scrollTop:0;
    rows=viewRows();cnt=rows.length;draw();
    const w2=c.querySelector('.mi-wrap');if(w2)w2.scrollTop=sc;};

  const NC=()=>14+cal.length+17;   // 앞 14 + 일자 + 뒤 17(출하실적 포함)

  // 일자 칸 — 값 없으면 빈칸(레거시 동일)
  /* ★구분 전환 = 재조회 없이 프론트 집계(레거시 동일).
     서버는 제번 상세(dets)만 주고, 여기서 4가지 뷰를 만든다.
       전체   : 자도번 집계행 + 클릭 시 제번 펼침
       집계   : 자도번 집계행만
       제번   : 제번 상세만
       도번별 : (도번,자도번) 행 + 도번 소계 */
  /* ★레거시 정렬 — PBD(dw_t1 setsort) 원문 그대로.
       전체·집계·제번 : mat_code, plan_ymd, line_no, output_hm, split_work_order,
                        c_item_code, excel_seq
       도번별         : c_item_code, mat_code, part_plan_ymd, part_output_hm,
                        plan_ymd, output_hm, …
     ★plan_ymd = '생산계획일'(pymd) 이다. 소요일(part_plan_ymd)이 아니다 — 이걸 혼동하면
       순서가 어긋난다. 실측(자도번 6141A20050Y):
         pymd 260831 → SVC 7건(21:00)      = 레거시 1~7행
         pymd 260901 → CA 10:37            = 8행
         pymd 260902 → CA 15:28, 15:36     = 9~10행
         pymd 260904 → CA 09:26, 19:13     = 11~12행 */
  const cmp=(a,b)=>a===b?0:(a<b?-1:1);
  const firstYmd=(x)=>{const k=Object.keys(x.byday||{}).filter(d=>x.byday[d]);
    return k.length?k.sort()[0]:'999999';};
  /* 전체/집계/제번 정렬 — ★소요일(part_plan_ymd) 먼저, 그 다음 생산계획일·라인·시각.
     레거시 실측(EBE61083212 · 28금): 0942 0945 0955 1003 1010 1034 1053 1058 …
     이 줄들은 전부 소요일 260828 · 생산계획일 260901 이고,
     그 사이 시각(0950·1037·1050)은 생산계획일이 달라 뒤로 빠진다. */
  const sortDet=(a,b)=>
      cmp(firstYmd(a),firstYmd(b))
   || cmp(a.pymd||'',b.pymd||'')
   || cmp(a.line||'',b.line||'')
   || cmp(a.lg_hm||'',b.lg_hm||'')
   || cmp(a.swo||a.wo||'',b.swo||b.wo||'')
   || cmp(a.doban||'',b.doban||'');
  // 도번별 — c_item_code, mat_code, part_plan_ymd, part_output_hm, plan_ymd, output_hm
  const sortDob=(a,b)=>
      cmp(a.doban||'',b.doban||'')
   || cmp(a.jadoban||'',b.jadoban||'')
   || cmp(a.pymd||'',b.pymd||'')
   || cmp(a.lg_hm||'',b.lg_hm||'');
  /* ★충당 계산 — 일자칸 a/b 의 a 와 색상 기준.
     ★충당 순서 = 출하 → ASSY → 도번고정(서브재고) → 생산 → 자재 (사용자 확인).
       출하실적(sale)·ASSY재고(st_a)·도번고정재고(st_d)·생산재고(st_p)는 도번 단위,
       자재(자도번재고 st_j)는 자도번 단위로 잡아 표시 순서대로 차감한다.
     전량 충당 → 노랑 / 일부만 → 진회색 / 하나도 못 하면 → 회색 */
  const calcFill=(list)=>{
    const P={sale:{},assy:{},fix:{},prod:{},mat:{}};
    list.forEach(x=>{
      // ★출하는 제번(LOT)+도번 단위 — 그 LOT 의 그 도번이 나간 수량만.
      if(P.sale[x.wo+'|'+x.doban]===undefined)P.sale[x.wo+'|'+x.doban]=(+x.sale||0);
      if(P.assy[x.doban]===undefined)P.assy[x.doban]=(+x.st_a||0);
      if(P.fix[x.doban]===undefined)P.fix[x.doban]=(+x.st_d||0);
      if(P.prod[x.doban]===undefined)P.prod[x.doban]=(+x.st_p||0);
      if(P.mat[x.jadoban]===undefined)P.mat[x.jadoban]=(+x.st_j||0);
    });
    list.forEach(x=>{
      x.fill={}; x.fsrc={}; x.filled=0;
      Object.keys(x.byday||{}).sort().forEach(d=>{
        let need=+x.byday[d]||0; if(!need)return;
        /* ★색 그룹(사용자 확인)
             살색 = 출하실적            ┐ ASSY(도번) 계열 재고
             노랑 = ASSY재고·도번고정   ┘
             회색 = 자도번(자기품번) 재고 — 생산재고·자재재고
           먼저 잡힌 그룹의 색을 쓴다(출하 → ASSY → 자도번 순으로 충당). */
        let use=0, g1=0, g2=0, g3=0;
        [['sale',x.wo+'|'+x.doban,1],['assy',x.doban,2],['fix',x.doban,2],
         ['prod',x.doban,3],['mat',x.jadoban,3]]
          .forEach(([k,key,g])=>{
            if(need<=0)return;
            const have=P[k][key]||0; if(have<=0)return;
            const t=Math.min(need,have);
            P[k][key]=have-t; need-=t; use+=t;
            if(g===1)g1+=t; else if(g===2)g2+=t; else g3+=t;
          });
        x.fill[d]=use;
        x.fsrc[d]=(g1>0?'sale':(g2>0?'fin':(g3>0?'mat':'')));
        x.filled+=use;
      });
    });
    return list;
  };

  const viewRows=()=>{
    const D=dets;
    if(gubun==='wo')
      return calcFill(D.slice().sort((a,b)=>cmp(a.jadoban||'',b.jadoban||'')||sortDet(a,b))
        .map(x=>Object.assign({},x,{kind:'wo'})));
    const roll=(list,keyf,base)=>{
      const m=new Map();
      list.forEach(x=>{const k=keyf(x);
        let it=m.get(k);
        if(!it){it=Object.assign(base(x),{byday:{},qty:0,lot_qty:0,wo_cnt:0});m.set(k,it);}
        Object.keys(x.byday||{}).forEach(d=>{it.byday[d]=(it.byday[d]||0)+x.byday[d];});
        it.qty+=(+x.qty||0);it.lot_qty+=(+x.lot_qty||0);it.wo_cnt++;});
      return m;
    };
    if(gubun==='all'||gubun==='sum'){
      // 충당은 '표시 순서'대로 도번재고를 깎는다 → 정렬 후 한 번에 계산
      const flat=calcFill([...new Set(D.map(x=>x.jadoban))].sort()
        .flatMap(k=>D.filter(d=>d.jadoban===k).sort(sortDet)
                     .map(x=>Object.assign({},x,{kind:'wo'}))));
      const m=roll(flat,x=>x.jadoban,x=>({jadoban:x.jadoban,jnm:x.jnm,cc:x.cc,cnm:x.cnm,
                                          st_j:x.st_j,st_p:x.st_p,st_d:0,st_a:x.st_a,
                                          sale:x.sale,model:x.model,dia:x.dia,thk:x.thk,
                                          len:x.len,wgt:x.wgt,cost:x.cost}));
      /* 소계행 충당량 = 자식 fill 합.
         ★색 규칙(사용자 확인): 자식이 **전부 색을 가졌을 때만** 소계에 색.
           하나라도 무색(미충당·일부충당)이면 소계도 무색.
           섞였으면 **가장 낮은 등급**(살색 > 노랑 > 회색 중 회색)을 쓴다.
           예: 노랑6 + 회색14 → 회색 (레거시 96/96) */
      const fsum={}, ssum={}, smix={}, RK={sale:1,fin:2,mat:3}, RV=['','sale','fin','mat'];
      flat.forEach(x=>{
        const t=fsum[x.jadoban]||(fsum[x.jadoban]={});
        const mx=smix[x.jadoban]||(smix[x.jadoban]={});
        Object.keys(x.byday||{}).forEach(d=>{
          if(!x.byday[d])return;
          const b=+x.byday[d]||0, f=(x.fill||{})[d]||0;
          const c=(f>=b&&b>0)?((x.fsrc||{})[d]||''):'';   // 자식 색(전량 충당일 때만)
          const cur=mx[d];
          if(cur===undefined)mx[d]=c;
          else if(cur===''||c==='')mx[d]='';              // 하나라도 무색 → 무색
          else mx[d]=RV[Math.max(RK[cur],RK[c])];         // 섞이면 낮은 등급
        });
        Object.keys(x.fill||{}).forEach(d=>{t[d]=(t[d]||0)+x.fill[d];});});
      Object.keys(smix).forEach(k=>{
        const s=ssum[k]||(ssum[k]={});
        Object.keys(smix[k]).forEach(d=>{if(smix[k][d])s[d]=smix[k][d];});});
      const out=[];
      [...m.keys()].sort().forEach(k=>{
        // ★전체 = 제번 상세를 쭉 깔고 자도번이 바뀌는 지점에 소계행(99:99).
        //   집계 = 소계행만, 단 **클릭한 자도번은 그 위로 제번이 펼쳐진다**(사용자 요청).
        if(gubun==='all'||open.has(k))
          flat.filter(d=>d.jadoban===k).forEach(d=>out.push(d));
        out.push(Object.assign({},m.get(k),{kind:'sum',key:k,fill:fsum[k]||{},
                                            fsrc:ssum[k]||{},open:open.has(k)}));
      });
      return out;
    }
    // 도번별
    const m=roll(D,x=>x.doban+''+x.jadoban,
                 x=>({doban:x.doban,dnm:x.dnm,jadoban:x.jadoban,jnm:x.jnm,
                      cc:x.cc,cnm:x.cnm,line:x.line,st_j:x.st_j,st_p:x.st_p,st_d:x.st_d,
                      st_a:x.st_a,sale:x.sale,model:x.model,dia:x.dia,thk:x.thk,
                      len:x.len,wgt:x.wgt,cost:x.cost}));
    const bydb=new Map();
    [...m.values()].forEach(v=>{const a=bydb.get(v.doban)||[];a.push(v);bydb.set(v.doban,a);});
    const out=[];
    [...bydb.keys()].sort().forEach(db=>{
      const kids=calcFill(bydb.get(db).sort(sortDob));
      kids.forEach(v=>out.push(Object.assign({},v,{kind:'doban'})));
      // ★도번계도 소계와 같은 규칙 — 자식이 전부 같은 색일 때만 그 색
      const t={kind:'dtot',doban:db,dnm:kids[0].dnm,jadoban:'',cc:'',cnm:'',line:'',
               byday:{},fill:{},fsrc:{},qty:0,lot_qty:0,
               st_j:kids[0].st_j,st_p:kids[0].st_p,st_d:kids[0].st_d,st_a:kids[0].st_a};
      const mixD={}, RK2={sale:1,fin:2,mat:3}, RV2=['','sale','fin','mat'];
      kids.forEach(v=>{
        Object.keys(v.byday||{}).forEach(d=>{
          if(!v.byday[d])return;
          t.byday[d]=(t.byday[d]||0)+v.byday[d];
          const bb=+v.byday[d]||0, ff=(v.fill||{})[d]||0;
          const c=(ff>=bb&&bb>0)?((v.fsrc||{})[d]||''):'';
          const cur=mixD[d];
          if(cur===undefined)mixD[d]=c;
          else if(cur===''||c==='')mixD[d]='';
          else mixD[d]=RV2[Math.max(RK2[cur],RK2[c])];
        });
        Object.keys(v.fill||{}).forEach(d=>{t.fill[d]=(t.fill[d]||0)+v.fill[d];});
        t.qty+=v.qty;t.lot_qty+=v.lot_qty;});
      Object.keys(mixD).forEach(d=>{if(mixD[d])t.fsrc[d]=mixD[d];});
      out.push(t);
    });
    return out;
  };

  const n0=v=>(+v||0)?num(v):'';
  // ★일자 뒤 컬럼(레거시 순서) — 자재/완료/요청/준비/생산 → 재고4종 → 모델·치수·금액
  const xcell=(r)=>`
    <td class="num">${n0(r.qty)}</td><td class="num">${n0(r.done)}</td>
    <td class="num">${n0(r.req)}</td><td class="num">${n0(r.ready)}</td>
    <td class="num">${n0(r.prod)}</td>
    <td class="num mi-st">${n0(r.st_j)}</td>
    <td class="num">${n0(r.sale)}</td>
    <td class="num mi-st">${n0(r.st_p)}</td>
    <td class="num mi-st">${n0(r.st_d)}</td>
    <td class="num mi-st">${n0(r.st_a)}</td>
    <td class="bcap" title="${esc(r.model||'')}">${esc(r.model||'')}</td>
    <td class="num">${n0(r.dia)}</td><td class="num">${n0(r.thk)}</td>
    <td class="num">${n0(r.len)}</td><td class="num">${n0(r.wgt)}</td>
    <td class="num mi-am">${n0(r.cost)}</td>
    <td class="num mi-am">${n0((+r.cost||0)*(+r.st_j||0))}</td>`;
  // ★일자 앞 고정 컬럼(레거시 순서)
  const hcell=(r,seq,tag)=>`
    <td class="mid mut">${seq||''}</td><td class="mid">${esc(r.line||'')}</td>
    <td class="mid">${esc(hm4(r.lg_hm))}</td><td>${esc(r.wo||'')}</td>
    <td></td><td></td><td></td><td></td><td></td>
    <td class="mid">${tag||''}</td>
    <td class="mi-cc" title="${esc(r.dnm||'')}">${esc(r.doban||'')}</td>
    <td class="mi-cw" title="${esc(r.cc||'')}">${esc(r.cnm||r.cc||'')}</td>
    <td class="mi-cc" title="${esc(r.jnm||'')}">${esc(r.jadoban||'')}</td>
    <td class="num">${n0(r.lot_qty)}</td>`;

  // 일자 셀 — 레거시 색상: 값있음=회색 / 기준일(당일)=노랑 / 휴무=연회색 / 빈칸=기본
  /* 일자 셀 — ★레거시 표기는 'a/b'.
       실측(7일 화면): 회색 칸도 20/20 · 10/10 처럼 **양쪽이 같은 숫자**다.
       즉 a 는 충당량이 아니라 소요수량 그대로이고(소계행만 30/85 처럼 갈린다),
       **색상만** ASSY재고 충당 여부로 노랑/회색이 나뉜다.
       소계행은 자식 충당합/소요합이라 a<b 가 될 수 있다. */
  const dcell=(r)=>cal.map(d=>{
    const b=(r.byday||{})[d.ymd]||0;
    const f=(r.fill||{})[d.ymd]||0;
    /* ★표기(레거시 실측)
         충당분이 있으면  a/b   (a=충당량, b=소요)   예: 96/130 · 155/189 · 2/2
         충당이 전혀 없으면 **정수만** — 슬래시를 쓰지 않는다  예: 5 · 12 · 88
       ★색상 = **전량 충당됐을 때만** 칠한다(사용자 확인).
         살색 = 출하실적 / 노랑 = ASSY·도번고정(서브) / 회색 = 생산·자재
         일부만 충당(a<b) 도, 전혀 못 채워도 → 무색 */
    const src=(r.fsrc||{})[d.ymd]||'';
    const isSum=(r.kind==='sum'||r.kind==='dtot');
    let cls='';
    if(b){
      // 상세 = 전량 충당일 때만 색 / 소계 = 자식이 전부 같은 색일 때만(fsrc 에 이미 반영)
      const ok=isSum?!!src:(f>=b&&!!src);
      if(ok)cls=(src==='sale')?'mi-sl':(src==='fin'?'mi-d0':'mi-v');
    }else if(dowOff(d.ymd))cls='mi-off';
    const txt=b?(f>0?(num(f)+'/'+num(b)):num(b)):'';
    return `<td class="num mid ${cls}">${txt}</td>`;}).join('');

  const draw=()=>{
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%;min-height:0">
     <div class="page-title">📥 자재입고진행현황 <span style="font-size:12px;color:var(--muted);font-weight:400">자재(자도번)별 소요계획·진행 · nx</span></div>
     <div class="page-sub">기준일부터 근무일 ${days}일. 일자칸=소요수량(휴무일은 회색). 레거시 <code>w_pr_input_010_part</code> · IN/OUT = <b>INPUT</b></div>
     <!-- ★레거시 w_pr_input_010_part 조건부 레이아웃 — 라벨=파란 블록, 2행 배치,
          구분은 드롭다운이 아니라 라디오(레거시 동일). 2026-08-28 사용자요청 -->
     <div class="mi-cond">
       <div class="mi-row">
         <span class="mi-lb">기준일자</span>
         <input type="date" class="inp mi-in mi-dt" id="mi-base" value="${esc(base)}">
         <span class="mi-lb">기간</span>
         <select class="inp mi-in" id="mi-days" style="width:70px">
           ${[3,4,5,7,10,15,30].map(n=>`<option value="${n}" ${days===n?'selected':''}>${n}일</option>`).join('')}
         </select>
         <span class="mi-lb">구분</span>
         <span class="mi-rg">
           ${[['all','전체'],['sum','집계'],['wo','제번'],['doban','도번별']].map(([v,t])=>
             `<label class="mi-rd"><input type="radio" name="mi-gb" value="${v}" ${gubun===v?'checked':''}> ${t}</label>`).join('')}
         </span>
         <span class="mi-lb">IN/OUT</span>
         <span class="mi-rg">
           <label class="mi-rd"><input type="radio" name="mi-io" value="I" checked> INPUT</label>
           <label class="mi-rd mi-dis" title="계획DB 차이 — 2차 구현"><input type="radio" name="mi-io" value="O" disabled> OUTPUT</label>
         </span>
       </div>
       <div class="mi-row">
         <span class="mi-lb">라인</span>
         <select class="inp mi-in" id="mi-line" style="width:96px">
           <option value="">% 전체</option>
           ${(opts.lines||[]).map(x=>`<option value="${esc(x)}" ${line===x?'selected':''}>${esc(x)}</option>`).join('')}
         </select>
         <span class="mi-lb">제번</span>
         <input class="inp mi-in" id="mi-wo" value="${esc(wo)}" style="width:104px">
         <span class="mi-lb">도번</span>
         <input class="inp mi-in" id="mi-do" list="mi-dol" value="${esc(doban)}" style="width:122px">
         <datalist id="mi-dol">${(opts.dobans||[]).map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('')}</datalist>
         <span class="mi-lb">자도번</span>
         <input class="inp mi-in" id="mi-ja" list="mi-jal" value="${esc(jado)}" style="width:122px">
         <datalist id="mi-jal">${(opts.jados||[]).map(x=>`<option value="${esc(x.code)}">${esc(x.nm||'')}</option>`).join('')}</datalist>
       </div>
       <div class="mi-row">
         <!-- ★자도번작업처 = 코드칸 + 거래처명칸(둘 다 입력·선택 가능).
              어느 쪽에 넣어도 나머지가 자동으로 채워지고, 조회는 항상 '코드'로 나간다.
              (이름 부분일치로 조회하면 다른 업체가 섞이는 문제 — 사용자 지적) -->
         <span class="mi-lb">자도번작업처</span>
         <input class="inp mi-in mi-cud" id="mi-cu" list="mi-cul" value="${esc(cust)}"
                placeholder="코드" style="width:96px">
         <datalist id="mi-cul">${(opts.custs||[]).map(x=>`<option value="${esc(x.cc)}">${esc(x.nm)}</option>`).join('')}</datalist>
         <input class="inp mi-in mi-cnm" id="mi-cnm" list="mi-cnl" value="${esc(custNm())}"
                placeholder="거래처명" style="width:210px">
         <datalist id="mi-cnl">${(opts.custs||[]).map(x=>`<option value="${esc(x.nm)}">${esc(x.cc)}</option>`).join('')}</datalist>
         <button class="btn" id="mi-go">🔍 조회</button>
         <button class="btn xls" id="mi-xls">📥 엑셀</button>
         <span class="spacer"></span>
         <span class="rowcount">${cnt}행 · 제번 ${detCnt} · LOT <b>${num(totLot)}</b> · 소요 <b>${num(totQty)}</b></span>
       </div>
     </div>
     ${msg?`<div class="page-sub" style="color:${/실패|오류/.test(msg)?'#c0392b':'#2f6db3'}">${/실패|오류/.test(msg)?'⚠':'ℹ'} ${esc(msg)}</div>`:''}
     <div class="grid-wrap mi-wrap"><table class="tbl mi-tbl">
      <!-- ★레거시 w_pr_input_010_part 컬럼 순서 그대로:
           SEQ·라인·LG INPUT·제번·비고1·당김,변경·Work Code·Work Center·작업처·투입
           ·도번·자도번작업처·자도번·LOT수량·[일자…]
           ·자재수량·완료수량·요청수량·준비실적·생산실적
           ·자도번재고·생산재고·도번고정재고·ASSY재고·모델·지름·두께·길이·중량·단가·재고금액 -->
      <thead><tr>
        <th style="width:34px">SEQ</th><th style="width:52px">라인</th>
        <th style="width:60px">LG INPUT</th><th style="width:84px">제번</th>
        <th style="width:52px">비고1</th><th style="width:62px">당김,변경</th>
        <th style="width:64px">Work Code</th><th style="width:68px">Work Center</th>
        <th style="width:56px">작업처</th><th style="width:46px">투입</th>
        <th class="mi-hc" style="width:120px">도번</th>
        <th class="mi-hw" style="width:110px">자도번작업처</th>
        <th class="mi-hc" style="width:130px">자도번</th>
        <th style="width:56px">LOT수량</th>
        ${cal.map(d=>`<th class="num ${dowOff(d.ymd)?'mi-offh':''}" style="width:62px">${esc(dlab(d.ymd))}</th>`).join('')}
        <th style="width:60px">자재수량</th><th style="width:60px">완료수량</th>
        <th style="width:58px">요청수량</th><th style="width:58px">준비실적</th>
        <th style="width:58px">생산실적</th>
        <th class="mi-hs" style="width:64px">자도번재고</th>
        <th style="width:58px">출하실적</th>
        <th class="mi-hs" style="width:60px">생산재고</th>
        <th class="mi-hs" style="width:74px">도번고정재고</th>
        <th class="mi-hs" style="width:62px">ASSY재고</th>
        <th class="mi-hc" style="width:150px">모델</th>
        <th class="num" style="width:52px">지름</th><th class="num" style="width:52px">두께</th>
        <th class="num" style="width:56px">길이</th><th class="num" style="width:56px">중량</th>
        <th class="num mi-ha" style="width:64px">단가</th>
        <th class="num mi-ha" style="width:78px">재고금액</th>
      </tr></thead>
      <tbody>${loading?spinRow(NC()):(rows.length?(()=>{let seq=0;return rows.map((r,i)=>{
        const k=r.kind;
        if(k==='wo'||k==='doban')seq++;   // SEQ = 상세행에만(소계행은 비움) — 레거시 동일
        // ★소계행(99:99) — 자도번이 바뀌는 지점에 들어가는 파란 줄(레거시 동일)
        if(k==='sum')
          return `<tr class="mi-sum${gubun==='sum'?' mi-clk':''}" data-k="${esc(r.key||'')}">`
               + `${hcell(r,gubun==='sum'?(r.open?'▼':'▶'):'','99:99')}${dcell(r)}${xcell(r)}</tr>`;
        if(k==='wo')
          return `<tr>${hcell(r,seq,'')}${dcell(r)}${xcell(r)}</tr>`;
        const tot=k==='dtot';
        return `<tr class="${tot?'mi-dtot':''}">${hcell(r,tot?'':seq,tot?'99:99':'')}`
             + `${dcell(r)}${xcell(r)}</tr>`;
      }).join('');})()+`<tr class="grandtot">
        <td colspan="13" class="right">총계 (제번 ${detCnt})</td>
        <td class="num">${num(totLot)}</td>
        ${cal.map(d=>`<td class="num">${num(totDay[d.ymd]||0)}</td>`).join('')}
        <td class="num">${num(totQty)}</td><td colspan="16"></td></tr>`
        :`<tr><td colspan="${NC()}" class="empty">조회 결과 없음</td></tr>`)}</tbody>
     </table></div>
     </div>
     <style>
       .mi-wrap{flex:0 1 auto;min-height:0;max-height:100%;overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px;box-shadow:0 3px 12px rgba(30,45,70,.08)}
       .mi-tbl{font-size:11.5px;white-space:nowrap;width:100%}
       .mi-tbl th,.mi-tbl td{padding:2px 5px;border-bottom:1px solid #eef2f8}
       .mi-tbl thead th{position:sticky;top:0;background:#dbe6f5;z-index:2;border-bottom:1px solid #9db4d4;text-align:center}
       /* ★주말 헤더 = 주황(레거시 29토·30일) */
       .mi-tbl th.mi-offh{background:#f5b878;color:#5a3a12}
       /* ★식별 컬럼(도번·자도번) = 연파랑 블록 */
       .mi-tbl th.mi-hc{background:#cfe0f3}
       .mi-tbl td.mi-cc{background:#eef5fc}
       /* ★자도번작업처(거래처) = 살구색 강조 — 눈에 띄게(사용자 요청) */
       .mi-tbl th.mi-hw{background:#f6d3a8;color:#6b3f10}
       .mi-tbl td.mi-cw{background:#fdf0dd;color:#7a4a12;font-weight:600}
       /* ★재고 3종 = 연초록 블록 */
       .mi-tbl th.mi-hs{background:#d6ebd9;color:#255c30}
       .mi-tbl td.mi-st{background:#f1f9f2}
       /* 금액(단가·재고금액) = 연노랑 */
       .mi-tbl th.mi-ha{background:#fdf2d6;color:#6b4e12}
       .mi-tbl td.mi-am{background:#fffdf3}
       .mi-tbl td.bcap{max-width:150px;overflow:hidden;text-overflow:ellipsis}
       /* ★전 셀 가운데 정렬(레거시 동일) — 숫자도 가운데.
          app.css 의 .tbl td.num{text-align:right} 를 이기려면 선택자를 더 구체적으로. */
       .mi-tbl tbody td,.mi-tbl thead th,.mi-tbl tfoot td{text-align:center}
       .mi-tbl tbody td.num,.mi-tbl tbody td.mid{text-align:center;font-variant-numeric:tabular-nums}
       .mi-tbl tbody td.bcap{text-align:left}
       .mi-tbl td.mut{color:#8aa0bd}
       .mi-tbl td.mi-off{background:#f0f2f5}                 /* 주말 칸 */
       /* ★일자칸 색 = 충당 재고 종류
          살색=출하 · 노랑=완제품/도번고정(서브) · 회색=생산/자재 · 무색=부족 */
       .mi-tbl td.mi-sl{background:#ffd9b3;font-weight:700}   /* 출하 */
       .mi-tbl td.mi-d0{background:#fff35c;font-weight:700}   /* 완제품·서브 */
       .mi-tbl td.mi-v{background:#d9dce1;font-weight:600}    /* 생산·자재 */
       /* ★마우스 올려도 색이 바뀌지 않게 — 호버 효과 없음(사용자 요청) */
       /* ★소계행 = 청록 전체 강조(레거시 99:99 행) */
       /* 소계행(99:99) — 레거시는 연한 파랑 줄 */
       .mi-tbl tr.mi-sum td{background:#bcd7f0;font-weight:600;border-top:1px solid #8fb4dc;
                            border-bottom:1px solid #8fb4dc;color:#123a63}
       .mi-tbl tr.mi-clk{cursor:pointer}
       /* ★소계·도번계행에도 일자칸 색상 유지 — 파란 줄 배경이 덮지 않게 3종 모두 지정 */
       .mi-tbl tbody tr.mi-sum td.mi-d0,.mi-tbl tbody tr.mi-dtot td.mi-d0
         {background:#fff35c;color:#4a3c00}
       .mi-tbl tbody tr.mi-sum td.mi-v,.mi-tbl tbody tr.mi-dtot td.mi-v
         {background:#d9dce1;color:#23303c}
       .mi-tbl tbody tr.mi-sum td.mi-sl,.mi-tbl tbody tr.mi-dtot td.mi-sl
         {background:#ffd9b3;color:#5a3a12}
       .mi-tbl tr.mi-dtot td{background:#5fe3ee;font-weight:700;border-top:1px solid #2fb9c6;color:#06303a}
       .mi-tbl tr.grandtot td{position:sticky;bottom:0;background:#c7d8ef;font-weight:800;border-top:2px solid #7f9dc4;z-index:2}
       .mi-tw{color:#2f6db3;font-size:10px}
       /* ★조건부 = 레거시 레이아웃(라벨 파란블록 + 2행) */
       .mi-cond{flex:0 0 auto;border:1px solid #9db4d4;border-radius:6px;background:#f4f8fd;padding:4px 6px;margin-bottom:6px}
       .mi-row{display:flex;align-items:center;gap:5px;flex-wrap:wrap;padding:2px 0}
       .mi-lb{display:inline-block;min-width:56px;text-align:center;padding:3px 7px;
              background:#cfe0f3;border:1px solid #9db4d4;border-radius:3px;
              font-size:12px;font-weight:600;color:#1c3f6e;white-space:nowrap}
       /* ★app.css 의 .inp{min-width:200px} 때문에 width 만 줘선 안 줄어든다 */
       .mi-cond .mi-in{height:24px;font-size:12px;min-width:0;padding:2px 6px}
       .mi-cond .mi-dt{width:124px}                     /* 날짜칸 — 길이 축소 */
       .mi-cond input[type=date].mi-dt::-webkit-calendar-picker-indicator{margin-left:0;padding:0}
       .mi-rg{display:inline-flex;align-items:center;gap:10px;padding:2px 8px;
              border:1px solid #b9cbe4;border-radius:3px;background:#fff}
       .mi-rd{display:inline-flex;align-items:center;gap:3px;font-size:12px;color:#334;cursor:pointer}
       .mi-rd input{margin:0;cursor:pointer}
       .mi-rd.mi-dis{color:#a8b0bb;cursor:not-allowed}
       .mi-rd.mi-dis input{cursor:not-allowed}
       .mi-cond .spacer{flex:1}
       /* 코드 입력칸 = 파란글씨 가운데(레거시) + 옆에 이름 표시 */
       .mi-cond .mi-cud{text-align:center;color:#1c47a0;font-weight:600}
       .mi-fx{display:inline-block;min-width:130px;padding:3px 8px;font-size:12px;
              background:#eef2f7;border:1px solid #d3dbe6;border-radius:3px;color:#333}
     </style>`;
    const g=(id)=>c.querySelector(id);
    g('#mi-base').onchange=e=>{base=e.target.value;};
    // ★조건 변경은 상태만 바꾼다 — 조회는 [조회] 버튼(또는 Enter)으로만. 2026-08-28 요청
    g('#mi-days').onchange=e=>{days=+e.target.value;};
    // ★구분 = 라디오(레거시 동일)
    c.querySelectorAll('input[name="mi-gb"]').forEach(x=>x.onchange=e=>{
      // ★구분 = 조회한 데이터로 즉시 전환(재조회 없음 — 레거시 동일)
      if(!e.target.checked)return;gubun=e.target.value;reView();});
    g('#mi-line').onchange=e=>{line=e.target.value;};
    // ★작업처 코드칸 ↔ 거래처명칸 상호 채움(부분갱신, 포커스 유지). 조회는 코드로.
    const cu=g('#mi-cu'), cn2=g('#mi-cnm');
    const syncNm=()=>{if(cn2)cn2.value=custNm();};
    cu.oninput=e=>{cust=e.target.value.trim();syncNm();};
    cu.onchange=e=>{cust=e.target.value.trim();syncNm();};
    cu.onkeyup=e=>{if(e.key==='Enter')load();};
    if(cn2){
      const fromNm=(v)=>{const cc=nm2cc(v);
        if(cc){cust=cc;if(cu)cu.value=cc;}
        else if(!v.trim()){cust='';if(cu)cu.value='';}};
      cn2.oninput=e=>fromNm(e.target.value);
      cn2.onchange=e=>{fromNm(e.target.value);syncNm();};
      cn2.onkeyup=e=>{if(e.key==='Enter')load();};
    }
    ['#mi-wo','#mi-do','#mi-ja'].forEach((id,n)=>{const el=g(id);
      el.oninput=e=>{const v=e.target.value;if(n===0)wo=v;else if(n===1)doban=v;else jado=v;};
      el.onkeyup=e=>{if(e.key==='Enter')load();};});
    g('#mi-go').onclick=()=>load();
    g('#mi-xls').onclick=()=>xls();
    // ★집계행 클릭 = 그 자도번의 제번을 소계 위로 펼침/접힘(스크롤 유지)
    c.querySelectorAll('.mi-clk').forEach(tr=>tr.onclick=()=>{
      const k=tr.dataset.k;if(!k)return;
      if(open.has(k))open.delete(k);else open.add(k);
      reView();});
  };

  const xls=()=>{
    if(!rows.length){alert('내보낼 자료가 없습니다.');return;}
    // 화면과 동일 순서 — 재고 3종이 일자 앞
    // 화면과 동일 순서
    const H=['구분','라인','LG INPUT','제번','투입','도번','자도번작업처','자도번','LOT수량']
      .concat(cal.map(d=>dlab(d.ymd)))
      .concat(['자재수량','완료수량','요청수량','준비실적','생산실적',
               '자도번재고','출하실적','생산재고','도번고정재고','ASSY재고',
               '모델','지름','두께','길이','중량','단가','재고금액']);
    const KN={sum:'집계',wo:'제번',doban:'도번',dtot:'도번계'};
    const out=rows.map(r=>[KN[r.kind]||'',r.line||'',r.lg_hm||'',r.wo||'',
        (r.kind==='sum'||r.kind==='dtot')?'99:99':'',
        r.doban||'',r.cnm||r.cc||'',r.jadoban||'',r.lot_qty||0]
      .concat(cal.map(d=>(r.byday||{})[d.ymd]||0))
      .concat([r.qty||0,r.done||0,r.req||0,r.ready||0,r.prod||0,
               r.st_j||0,r.sale||0,r.st_p||0,r.st_d||0,r.st_a||0,
               r.model||'',r.dia||0,r.thk||0,r.len||0,r.wgt||0,
               r.cost||0,Math.round((+r.cost||0)*(+r.st_j||0))]));
    out.push(['총계','','','','','','','',totLot]
      .concat(cal.map(d=>totDay[d.ymd]||0))
      .concat([totQty,'','','','','','','','','','','','','','','','']));
    downloadCSV(`자재입고진행현황_${y6(base)}_${days}일.csv`,H,out);
  };

  // ★화면 진입 시 자동조회 안 함 — 조건 확인 후 [조회] 를 누른다(사용자 요청).
  //   드롭다운 후보만 미리 받아 둔다.
  msg='조건을 지정하고 [🔍 조회]를 누르세요.';
  draw();
  loadOpts().then(()=>draw());
};
