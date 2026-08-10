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
  let sel=null, curL=[], curFrom='', curTo='', source='live';   // ★Phase5 데이터원(기본 라이브 무변경)
  const load=async()=>{loading=true;msg='';sel=null;
    const st=c.querySelector('#lbody');if(st)st.innerHTML=spinRow(5);
    const sc=(c.querySelector('#whcust')?c.querySelector('#whcust').value:'Z99990')||'Z99990';
    const pw=(c.querySelector('#partwh')?c.querySelector('#partwh').value:'IS0001')||'IS0001';
    const f6=iso2ymd(c.querySelector('#dfrom')?c.querySelector('#dfrom').value:'')||iso2ymd(m1Iso());
    const t6=iso2ymd(c.querySelector('#dto')?c.querySelector('#dto').value:'')||iso2ymd(todayIso());
    const qv=(c.querySelector('#q')?c.querySelector('#q').value:'').trim();   // ★품번(자도번/품명): 입력 시 서버 스코프
    curFrom=f6;curTo=t6;   // ★요청 기간을 먼저 반영 → 조회 실패(타임아웃)해도 날짜 안 되돌아감
    if(source==='nx'){loading=false;return nxDerivedView(c,`${API}/api/live/matinout?from_ymd=${f6}&to_ymd=${t6}&source=nx`,{title:'자재입출고현황',onBack:()=>{source='live';load();}});}
    try{const r=await fetch(`${API}/api/live/matinout?from_ymd=${f6}&to_ymd=${t6}&stock_cust=${encodeURIComponent(sc)}&part_wh=${encodeURIComponent(pw)}`+(qv?`&q=${encodeURIComponent(qv)}`:''));if(!r.ok)throw new Error('HTTP '+r.status);
      const j=await r.json();curFrom=j.from_ymd||f6;curTo=j.to_ymd||t6;stockAll=j.stock||[];moves=j.moves||[];
      stock=stockAll.filter(s=>Math.abs(+s.stock||0)>0.0001);
      bfMap={};stockAll.forEach(s=>bfMap[s.mat]=+s.bf||0);
      byMat={};moves.forEach(x=>{(byMat[x.mat]=byMat[x.mat]||[]).push(x);});}
    catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';stockAll=[];stock=[];moves=[];}
    loading=false;
    const df=c.querySelector('#dfrom');if(df)df.value=ymd2iso(curFrom);
    const dt=c.querySelector('#dto');if(dt)dt.value=ymd2iso(curTo);
    const sub=c.querySelector('#mio-sub');if(sub)sub.innerHTML=`${esc(WHN[sc]||sc)} · ${esc(pwName(pw))} 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PU_T_STOCK_MAINT</code> 외 · 🔴 라이브 ${esc(fmtYmd(curFrom))}~${esc(fmtYmd(curTo))} · 0재고 숨김`;
    renderLeft();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측에서 자도번을 클릭하세요</div>';};
  c.innerHTML=`
   <div class="page-title">🔁 자재 입출고현황</div>
   <div class="page-sub" id="mio-sub">재고창고·파트창고 재고 + 선택품목 입출고이력(누적재고) · 원본 <code>PU_T_STOCK_MAINT</code> 외 · 🔴 라이브 · 0재고 숨김</div>
   <div class="toolbar">
     <label class="tl">조회기간</label><input type="date" class="inp" id="dfrom" value="${m1Iso()}" style="min-width:130px"> ~ <input type="date" class="inp" id="dto" value="${todayIso()}" style="min-width:130px">
     <label class="tl">재고창고</label><select class="sel" id="whcust"><option value="Z99990">피앤씨창고</option></select>
     <label class="tl">파트창고</label><select class="sel" id="partwh"><option value="IS0001">자재창고</option><option value="IS0002">부자재창고(미키팅)</option></select>
     <input class="inp" id="q" placeholder="자도번/품명 (Enter=서버조회)"><input class="inp" id="qcust" placeholder="거래처 입력"><select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
     <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
     <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
     <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
   </div>
   <div style="display:flex;gap:10px;align-items:flex-start">
     <div style="flex:0 0 42%;min-width:0">
       <div class="summary-bar" id="lsum"></div>
       <div class="grid-wrap" style="max-height:520px;overflow:auto"><table class="tbl fit"><thead><tr><th>자도번</th><th>품명</th><th>파트창고</th><th class="num">재고</th><th class="center">최종입고일</th></tr></thead><tbody id="lbody"></tbody></table></div>
       <div class="rowcount" id="lcnt"></div>
     </div>
     <div style="flex:1;min-width:0">
       <div class="summary-bar" id="rhead"><div class="s-item">← 좌측에서 자도번을 클릭하세요</div></div>
       <div class="grid-wrap" style="max-height:548px;overflow:auto"><table class="tbl fit"><thead><tr><th class="center">일자</th><th class="num">전일재고</th><th class="num">입고</th><th class="num">출고</th><th class="num">재고조정</th><th class="num">재고이동</th><th class="num">재고수량</th><th>구분</th><th>사용이력</th></tr></thead><tbody id="rbody"></tbody></table></div>
     </div>
   </div>`;
  const renderRight=mat=>{
    const s=stockAll.find(x=>x.mat===mat)||{}; const bf=bfMap[mat]||0;
    const lines=(byMat[mat]||[]).slice().sort((a,b)=>(''+a.ymd).localeCompare(''+b.ymd,'ko'));
    let bal=bf, html=`<tr><td class="center">00/00/00</td><td class="num">${won(bf)}</td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num"></td><td class="num qty"><b>${won(bf)}</b></td><td>전월이월</td><td></td></tr>`;
    let si=0,so=0,se=0,sm=0;
    lines.forEach(r=>{const prev=bal; const i=+r.i||0,o=+r.o||0,e=+r.e||0,mv=+r.mv||0; bal=prev+i-o+e+mv; si+=i;so+=o;se+=e;sm+=mv;
      html+=`<tr><td class="center">${fmtYmd(r.ymd)}</td><td class="num">${won(prev)}</td><td class="num">${i?won(i):''}</td><td class="num">${o?won(o):''}</td><td class="num">${e?won(e):''}</td><td class="num">${mv?won(mv):''}</td><td class="num qty"><b>${won(bal)}</b></td><td>${esc(r.div)||''}</td><td class="cap" title="${esc(r.cust||r.wo||'')}">${esc(r.cust||r.wo||'')}</td></tr>`;});
    html+=`<tr class="grandtot"><td class="center">총계</td><td class="num">${won(bf)}</td><td class="num">${won(si)}</td><td class="num">${won(so)}</td><td class="num">${won(se)}</td><td class="num">${won(sm)}</td><td class="num">${won(bal)}</td><td colspan="2"></td></tr>`;
    c.querySelector('#rbody').innerHTML=html;
    c.querySelector('#rhead').innerHTML=`<div class="s-item">자도번 <b>${esc(mat)}</b></div><div class="s-item">${esc(s.nm||'')}</div><div class="s-item">현재고 <b>${won(bal)}</b></div>`;
    attachResizers(c);
  };
  const renderLeft=()=>{
    const q=c.querySelector('#q').value.trim().toLowerCase(), gb=c.querySelector('#gubun').value;
    const qc=c.querySelector('#qcust').value.trim().toLowerCase();
    const custMats=qc?new Set(moves.filter(x=>(''+(x.cust||'')).toLowerCase().includes(qc)||(''+(x.wo||'')).toLowerCase().includes(qc)).map(x=>x.mat)):null;
    curL=stock.filter(s=>(gb==='all'||(gb==='plus'?s.stock>0:s.stock<0))&&(!q||(''+s.mat).toLowerCase().includes(q)||(''+s.nm).toLowerCase().includes(q))&&(!custMats||custMats.has(s.mat)))
      .sort((a,b)=>(''+a.mat).localeCompare(''+b.mat,'ko'));
    const tot=curL.reduce((a,b)=>a+(+b.stock||0),0);
    let lb=curL.map(s=>`<tr data-mat="${esc(s.mat)}" class="${sel===s.mat?'sel':''}"><td><b>${esc(s.mat)}</b></td><td class="cap" title="${esc(s.nm)}">${esc(s.nm)}</td><td>${esc(pwName(s.part))}</td><td class="num qty">${won(s.stock)}</td><td class="center">${fmtYmd(s.lastin)!=='00/00/00'?fmtYmd(s.lastin):'-'}</td></tr>`).join('');
    if(curL.length)lb+=`<tr class="grandtot"><td colspan="3" class="right">총계 (${won(curL.length)} 품목)</td><td class="num">${won(tot)}</td><td></td></tr>`;
    c.querySelector('#lbody').innerHTML=curL.length?lb:`<tr><td colspan="5" class="empty">결과 없음</td></tr>`;
    c.querySelector('#lbody').querySelectorAll('tr[data-mat]').forEach(tr=>tr.onclick=()=>{sel=tr.dataset.mat;c.querySelectorAll('#lbody tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');renderRight(sel);});
    c.querySelector('#lsum').innerHTML=`<div class="s-item">품목 <b>${won(curL.length)}</b></div><div class="s-item">재고 합계 <b>${won(tot)}</b></div>`;
    c.querySelector('#lcnt').textContent=`${curL.length}품목 (0재고 제외)`;
    attachResizers(c);
  };
  c.querySelector('#go').onclick=()=>load();
  c.querySelector('#nxsrc').onclick=()=>{source='nx';load();};   // ★Phase5 nx 파생 보기
  c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')load();else renderLeft();};   // ★Enter=서버 스코프 조회(기간 무관 빠름), 그외=로드된 데이터 클라 필터
  c.querySelector('#qcust').onkeyup=()=>renderLeft();
  c.querySelector('#gubun').onchange=renderLeft;
  c.querySelector('#dfrom').onchange=()=>load();
  c.querySelector('#dto').onchange=()=>load();
  c.querySelector('#whcust').onchange=()=>load();
  c.querySelector('#partwh').onchange=()=>load();
  c.querySelector('#reset').onclick=()=>{c.querySelector('#q').value='';c.querySelector('#qcust').value='';c.querySelector('#gubun').value='all';c.querySelector('#partwh').value='IS0001';c.querySelector('#whcust').value='Z99990';c.querySelector('#dfrom').value=m1Iso();c.querySelector('#dto').value=todayIso();sel=null;load();};
  c.querySelector('#xls').onclick=()=>downloadCSV('자재입출고현황.csv',['자도번','품명','파트창고','재고','최종입고일'],curL.map(s=>[s.mat,s.nm,pwName(s.part),s.stock,fmtYmd(s.lastin)!=='00/00/00'?fmtYmd(s.lastin):'']));
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
     <div class="page-sub">확정입고(검사통과)+수입 · 원본 <code>PU_T_STOCK_MAINT</code>(9/S/C/G/H)+<code>PU_T_STOCK_MAINT_C</code>(P) · 🔴 라이브 ${gijun==='close'?`마감기준 ${esc(ymToInput(curYm)||'-')}`:`입고기준 ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="close" class="${gijun==='close'?'on':''}">마감기준</button><button data-g="issue" class="${gijun==='issue'?'on':''}">입고기준</button></div>
       <label class="tl">${gijun==='close'?'마감년월':'입고일자'}</label>
       ${gijun==='close'?`<input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||'2026-07')}" style="min-width:120px">`:`<input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:130px">`}
       <label class="tl">출력방식</label>
       <select class="sel" id="mode"><option value="cust" ${mode==='cust'?'selected':''}>거래처별</option><option value="item" ${mode==='item'?'selected':''}>품목별</option><option value="agg" ${mode==='agg'?'selected':''}>업체별</option></select>
       <button class="btn ${vat?'':'ghost'}" id="vat">부가세조정</button>
     </div>
     <div class="toolbar">
       <select class="sel" id="lg"><option value="">전체 대분류</option>${lgs.map(x=>`<option value="${esc(x)}" ${F.lg===x?'selected':''}>${esc(lgN(x))}</option>`).join('')}</select>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgs.map(x=>`<option value="${esc(x)}" ${F.sg===x?'selected':''}>${esc(sgN(x))}</option>`).join('')}</select>
       <select class="sel" id="ct"><option value="">전체 거래처분류</option>${cts.map(x=>`<option value="${esc(x)}" ${F.ct===x?'selected':''}>${esc(ctN(x))}</option>`).join('')}</select>
       <input class="inp" id="cq" value="${esc(F.cq)}" placeholder="거래처코드/명">
       <input class="inp" id="mq" value="${esc(F.mq)}" placeholder="품번/품명/PART NO">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
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
    const amtHdr=`<th class="num">금액</th>`+(vat?`<th class="num">금액(KRW)</th><th class="num">부가세</th><th class="num">부가세(KRW)</th><th class="num">합계</th><th class="num">합계(KRW)</th>`:'');
    const amtCells=r=>`<td class="num gstock">${wonI(r.amt)}</td>`+(vat?`${money(r.kamt)}${money(fVat(r.amt))}${money(fVat(r.kamt))}${money(r.amt+fVat(r.amt))}${money(r.kamt+fVat(r.kamt))}`:'');
    const amtSub=g=>`<td class="num gstock">${wonI(g.amt)}</td>`+(vat?`${money(g.kamt)}${money(fVat(g.amt))}${money(fVat(g.kamt))}${money(g.amt+fVat(g.amt))}${money(g.kamt+fVat(g.kamt))}`:'');
    const VC=vat?5:0;
    let lines=filt(), tbody='', thead='', ncols=0;
    // 아이템 라인 셀 (거래처별/품목별 공통 우측)
    const itemMid=r=>`<td>${esc(lgN(r.lg))}</td><td>${esc(sgN(r.sg))}</td><td class="center">${esc(r.unit)||''}</td><td class="num">${won(r.qty)}</td><td class="num">${won(r.wt)}</td><td class="center">${esc(curN(r.cur))}</td><td class="num">${rateD(r)}</td><td class="num">${won(r.cost)}</td><td class="num">${won(r.kcost)}</td>${amtCells(r)}`;
    const midHdr=`<th>대분류</th><th>소분류</th><th class="center">단위</th><th class="num">수량</th><th class="num">중량</th><th class="center">화폐</th><th class="num">환율</th><th class="num">단가</th><th class="num">단가(KRW)</th>${amtHdr}`;
    if(mode==='cust'){
      cur=lines.slice().sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko')||(''+a.mat).localeCompare(''+b.mat,'ko'));
      thead=`<tr><th>거래처코드</th><th>거래처명</th><th>거래처분류</th><th>ASY PART NO</th><th>PART NO</th><th>품명</th><th>PART SPEC</th>${midHdr}</tr>`;
      ncols=17+VC;
      const groups=[]; let ck=null;
      cur.forEach(r=>{if(r.cc!==ck){groups.push({cc:r.cc,cnm:r.cnm,rows:[]});ck=r.cc;}groups[groups.length-1].rows.push(r);});
      groups.forEach(g=>{g.rows.forEach(r=>{tbody+=`<tr><td><b>${esc(r.cc)}</b></td><td class="cap" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap" title="${esc(ctN(r.ct))}">${esc(ctN(r.ct))}</td><td>${esc(r.ic)||''}</td><td>${esc(r.mat)}</td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td>${itemMid(r)}</tr>`;});
        const gs={qty:S(g.rows,'qty'),amt:S(g.rows,'amt'),kamt:S(g.rows,'kamt')};
        tbody+=`<tr class="subtot"><td colspan="10" class="right">(업체계) ${esc(g.cnm)}</td><td class="num">${won(gs.qty)}</td><td colspan="5"></td>${amtSub(gs)}</tr>`;});
    } else if(mode==='item'){
      const map=new Map();
      lines.forEach(r=>{const k=r.ic+'|'+r.mat; if(!map.has(k))map.set(k,{...r,qty:0,amt:0,kamt:0,vat:0,kvat:0}); const o=map.get(k);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.kamt+=+r.kamt||0;o.vat+=+r.vat||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.mat).localeCompare(''+b.mat,'ko'));
      thead=`<tr><th>ASY PART NO</th><th>PART NO</th><th>품명</th><th>PART SPEC</th><th>거래처명</th><th>거래처분류</th>${midHdr}</tr>`;
      ncols=16+VC;
      cur.forEach(r=>{tbody+=`<tr><td>${esc(r.ic)||''}</td><td><b>${esc(r.mat)}</b></td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td><td class="cap" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap">${esc(ctN(r.ct))}</td>${itemMid(r)}</tr>`;});
    } else { // 업체별
      const map=new Map();
      lines.forEach(r=>{if(!map.has(r.cc))map.set(r.cc,{cc:r.cc,cnm:r.cnm,ct:r.ct,qty:0,amt:0,kamt:0,vat:0,kvat:0}); const o=map.get(r.cc);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.kamt+=+r.kamt||0;o.vat+=+r.vat||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko'));
      thead=`<tr><th>거래처코드</th><th>거래처명</th><th>담당자</th><th>거래처분류</th><th class="num">수량</th><th class="num">금액</th><th class="num">금액(KRW)</th><th class="num">부가세</th><th class="num">부가세(KRW)</th><th class="num">합계</th><th class="num">합계(KRW)</th></tr>`;
      ncols=11;
      cur.forEach(r=>{const v6=(''+r.ct).trim()==='6'?'vat6':'';tbody+=`<tr><td><b>${esc(r.cc)}</b></td><td class="cap" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td>${esc(chg(r.cc))||'-'}</td><td class="cap">${esc(ctN(r.ct))}</td><td class="num">${won(r.qty)}</td><td class="num gstock">${wonI(r.amt)}</td><td class="num">${wonI(r.kamt)}</td><td class="num ${v6}">${wonI(r.vat)}</td><td class="num ${v6}">${wonI(r.kvat)}</td><td class="num">${wonI(r.amt+r.vat)}</td><td class="num">${wonI(r.kamt+r.kvat)}</td></tr>`;});
    }
    const gq=S(cur,'qty'),ga=S(cur,'amt'),gk=S(cur,'kamt');
    if(mode==='agg'){const gv=S(cur,'vat'),gkv=S(cur,'kvat');
      tbody+=`<tr class="grandtot"><td colspan="4" class="right">총계 (${won(cur.length)} 업체)</td><td class="num">${won(gq)}</td><td class="num">${wonI(ga)}</td><td class="num">${wonI(gk)}</td><td class="num">${wonI(gv)}</td><td class="num">${wonI(gkv)}</td><td class="num">${wonI(ga+gv)}</td><td class="num">${wonI(gk+gkv)}</td></tr>`;
    } else {
      const lead=mode==='cust'?10:9;
      tbody+=`<tr class="grandtot"><td colspan="${lead}" class="right">총계</td><td class="num">${won(gq)}</td><td colspan="5"></td>${amtSub({amt:ga,kamt:gk})}</tr>`;
    }
    c.querySelector('#th').innerHTML=thead;
    c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${ncols}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
      :(msg?`<tr><td colspan="${ncols}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
      :(cur.length?tbody:`<tr><td colspan="${ncols}" class="empty">결과 없음</td></tr>`));
    c.querySelector('#sum').innerHTML=`<div class="s-item">${mode==='agg'?'업체':'라인'} <b>${won(cur.length)}</b></div><div class="s-item">수량 합계 <b>${won(gq)}</b></div><div class="s-item ${ga<0?'neg':''}">금액 합계 <b>${wonI(ga)} 원</b></div>`;
    c.querySelector('#cnt').textContent=`${cur.length}${mode==='agg'?'업체':'라인'} / 대상 ${lines.length}라인`;
    attachResizers(c);
    const go=()=>{if(gijun==='close'){curYm=inYm(c.querySelector('#dto').value);}
      else{curFrom=inD(c.querySelector('#dfrom').value);curTo=inD(c.querySelector('#dto').value);}load();};
    const syncF=()=>{F.lg=c.querySelector('#lg').value;F.sg=c.querySelector('#sg').value;F.ct=c.querySelector('#ct').value;F.cq=c.querySelector('#cq').value;F.mq=c.querySelector('#mq').value;};
    c.querySelector('#go').onclick=()=>{syncF();draw();};   // ★검색=필터적용(검색어 유지)
    const _dto=c.querySelector('#dto');if(_dto)_dto.onchange=go;   // 날짜 변경 시만 재조회
    const _dfr=c.querySelector('#dfrom');if(_dfr)_dfr.onchange=go;
    ['#lg','#sg','#ct'].forEach(s=>c.querySelector(s).onchange=()=>{syncF();draw();});
    c.querySelector('#cq').onkeyup=e=>{if(e.key==='Enter'){syncF();draw();}};c.querySelector('#mq').onkeyup=e=>{if(e.key==='Enter'){syncF();draw();}};
    c.querySelector('#reset').onclick=()=>{gijun='close';mode='cust';vat=false;curYm='';F={lg:'',sg:'',ct:'',cq:'',mq:''};load();};
    c.querySelector('#xls').onclick=()=>{let hd,rows;
      if(mode==='agg'){hd=['거래처코드','거래처명','담당자','거래처분류','수량','금액','금액(KRW)','부가세','부가세(KRW)','합계','합계(KRW)'];
        rows=cur.map(r=>[r.cc,r.cnm,chg(r.cc),ctN(r.ct),r.qty,Math.round(r.amt),Math.round(r.kamt),Math.round(r.vat),Math.round(r.kvat),Math.round(r.amt+r.vat),Math.round(r.kamt+r.kvat)]);}
      else{const base=['ASY PART NO','PART NO','품명','PART SPEC','거래처코드','거래처명','거래처분류','대분류','소분류','단위','수량','중량','화폐','환율','단가','단가(KRW)','금액'].concat(vat?['금액(KRW)','부가세','부가세(KRW)','합계','합계(KRW)']:[]);hd=base;
        rows=cur.map(r=>[r.ic,r.mat,r.nm,r.spec,r.cc,r.cnm,ctN(r.ct),lgN(r.lg),sgN(r.sg),r.unit,r.qty,r.wt,curN(r.cur),(''+r.cur).trim()==='KRW'?'':r.rate,r.cost,r.kcost,Math.round(r.amt)].concat(vat?[Math.round(r.kamt),fVat(r.amt),fVat(r.kamt),Math.round(r.amt+fVat(r.amt)),Math.round(r.kamt+fVat(r.kamt))]:[]));}
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
    ct:{h:'거래처분류',cls:'cap',get:r=>esc(ctN(r.ct))},
    chg:{h:'담당자',cls:'',get:r=>esc(chg(r.cc))||'-'},
    mat:{h:'PART_NO',cls:'',get:r=>`<b>${esc(r.mat)}</b>`},
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
    amt:{h:'금액',cls:'num gstock',get:r=>wonI(r.amt)},
  };
  const TAIL=['unit','qty','wt','cur','rate','cost','amt'];
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
     <div class="page-sub">확정입고(검사통과)+수입 라인 명세 · 원본 <code>PU_T_STOCK_MAINT</code>+<code>PU_T_STOCK_MAINT_C</code> · 🔴 라이브 ${gijun==='close'?`마감기준 ${esc(ymToInput(curYm)||'-')}`:`입고기준 ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="close" class="${gijun==='close'?'on':''}">마감기준</button><button data-g="issue" class="${gijun==='issue'?'on':''}">입고기준</button></div>
       <label class="tl">${gijun==='close'?'마감년월':'입고일자'}</label>
       ${gijun==='close'?`<input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||'2026-07')}" style="min-width:120px">`:`<input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:130px">`}
       <label class="tl">출력방식</label>
       <select class="sel" id="mode">${Object.entries(MODES).map(([k,v])=>`<option value="${k}" ${mode===k?'selected':''}>${v.label}</option>`).join('')}</select>
     </div>
     <div class="toolbar">
       <select class="sel" id="lg"><option value="">전체 대분류</option>${lgs.map(x=>`<option value="${esc(x)}">${esc(lgN(x))}</option>`).join('')}</select>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgs.map(x=>`<option value="${esc(x)}">${esc(sgN(x))}</option>`).join('')}</select>
       <select class="sel" id="ct"><option value="">전체 거래처분류</option>${cts.map(x=>`<option value="${esc(x)}">${esc(ctN(x))}</option>`).join('')}</select>
       <input class="inp" id="cq" placeholder="거래처코드/명">
       <input class="inp" id="mq" placeholder="품번/품명/PART NO (Enter=서버조회)" value="${esc(curMq)}">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
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
    const subRow=(label,q,a,g)=>`<tr class="${g||'subtot'}"><td colspan="${qi}" class="right">${esc(label)}</td><td class="num">${won(q)}</td><td colspan="4"></td><td class="num">${wonI(a)}</td></tr>`;
    const render=()=>{
      let lines=filt();
      lines.sort((a,b)=>{for(const k of cfg.sort){const c2=(''+(a[k]??'')).localeCompare(''+(b[k]??''),'ko',{numeric:true});if(c2)return c2;}return 0;});
      cur=lines; let html='';
      if(!cfg.g1){ lines.forEach(r=>html+=rowHtml(r)); }
      else { let g1v=null,g2v=null,s1q=0,s1a=0,s2q=0,s2a=0;
        lines.forEach(r=>{const v1=r[cfg.g1], v2=cfg.g2?r[cfg.g2]:null;
          if(g1v!==null && v1!==g1v){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a); html+=subRow(cfg.l1,s1q,s1a); s1q=s1a=s2q=s2a=0; g2v=null; }
          else if(cfg.g2 && g2v!==null && v2!==g2v){ html+=subRow(cfg.l2,s2q,s2a); s2q=s2a=0; }
          html+=rowHtml(r); s1q+=+r.qty||0; s1a+=+r.amt||0; s2q+=+r.qty||0; s2a+=+r.amt||0; g1v=v1; g2v=v2; });
        if(g1v!==null){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a); html+=subRow(cfg.l1,s1q,s1a); }
      }
      const tq=lines.reduce((a,b)=>a+(+b.qty||0),0), ta=lines.reduce((a,b)=>a+(+b.amt||0),0);
      html+=subRow('총계',tq,ta,'grandtot');
      c.querySelector('#th').innerHTML=`<tr>${order.map(k=>`<th class="${CD[k].cls}">${CD[k].h}</th>`).join('')}</tr>`;
      c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${order.length}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
        :(msg?`<tr><td colspan="${order.length}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
        :(lines.length?html:`<tr><td colspan="${order.length}" class="empty">결과 없음</td></tr>`));
      c.querySelector('#sum').innerHTML=`<div class="s-item">라인 <b>${won(lines.length)}</b></div><div class="s-item">입고수량 합계 <b>${won(tq)}</b></div><div class="s-item ${ta<0?'neg':''}">금액 합계 <b>${wonI(ta)} 원</b></div>`;
      c.querySelector('#cnt').textContent=`${lines.length}라인 / 대상 ${pool.length}라인`;
      attachResizers(c);
    };
    const go=()=>{if(gijun==='close'){curYm=inYm(c.querySelector('#dto').value);}
      else{curFrom=inD(c.querySelector('#dfrom').value);curTo=inD(c.querySelector('#dto').value);}load();};
    c.querySelector('#go').onclick=render;   // ★검색=클라이언트 필터(재조회 아님) → 검색어 유지·필터적용
    c.querySelector('#nxsrc').onclick=()=>{source='nx';load();};   // ★Phase5 nx 파생 보기
    const _dto=c.querySelector('#dto');if(_dto)_dto.onchange=go;   // 날짜 변경 시에만 재조회
    const _dfr=c.querySelector('#dfrom');if(_dfr)_dfr.onchange=go;
    ['#lg','#sg','#ct'].forEach(s=>c.querySelector(s).onchange=render);
    c.querySelector('#cq').onkeyup=e=>{if(e.key==='Enter')render();};
    c.querySelector('#mq').onkeyup=e=>{curMq=e.target.value.trim();if(e.key==='Enter')load();else render();};   // ★품번: 유지(curMq)·Enter=서버 스코프 재조회(기간 무관 빠름)·그외=로드된 데이터 클라 필터
    c.querySelector('#reset').onclick=()=>{mode='day';gijun='close';curYm='';curMq='';load();};
    c.querySelector('#xls').onclick=()=>{
      const hd=order.map(k=>CD[k].h);
      const raw={ymd:r=>fmtYmd(r.ymd),seq:r=>r.seq,ym:r=>fmtYm(r.ym),cnm:r=>r.cnm,ct:r=>ctN(r.ct),chg:r=>chg(r.cc),mat:r=>r.mat,nm:r=>r.nm,spec:r=>r.spec,diam:r=>r.diam,thick:r=>r.thick,length:r=>r.length,lg:r=>lgN(r.lg),sg:r=>sgN(r.sg),unit:r=>r.unit,qty:r=>r.qty,wt:r=>r.wt,cur:r=>curN(r.cur),rate:r=>(''+r.cur).trim()==='KRW'?'':r.rate,cost:r=>r.cost,amt:r=>Math.round(r.amt)};
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
    cc:{h:'불출처',cls:'cap',get:r=>esc(r.cnm)},
    ct:{h:'거래처분류',cls:'cap',get:r=>esc(ctN(r.ct))},
    chg:{h:'담당자',cls:'',get:r=>esc(chg(r.cc))||'-'},
    ic:{h:'ASY PART NO',cls:'',get:r=>esc(r.ic)||''},
    mat:{h:'PART_NO',cls:'',get:r=>`<b>${esc(r.mat)}</b>`},
    nm:{h:'품명',cls:'cap',get:r=>esc(r.nm)},
    spec:{h:'PART SPEC',cls:'cap',get:r=>esc(r.spec)||''},
    lg:{h:'대분류',cls:'',get:r=>esc(lgN(r.lg))},
    sg:{h:'소분류',cls:'',get:r=>esc(sgN(r.sg))},
    incust:{h:'입고처',cls:'cap',get:r=>esc(r.incust)||''},
    unit:{h:'단위',cls:'center',get:r=>esc(r.unit)||''},
    qty:{h:'수량',cls:'num',get:r=>won(r.qty)},
    wt:{h:'중량',cls:'num',get:r=>won(r.wt)},
    cur:{h:'화폐',cls:'center',get:r=>esc(curN(r.cur))},
    rate:{h:'환율',cls:'num',get:r=>rateD(r)},
    cost:{h:'단가',cls:'num',get:r=>won(r.cost)},
    amt:{h:'금액',cls:'num gstock',get:r=>wonI(r.amt)},
  };
  const TAIL=['unit','qty','wt','cur','rate','cost','amt'];
  const MODES={
    day:      {label:'일자별',       lead:['ymd','seq','cc','ct','chg','ic','mat','nm','spec','lg','sg','incust'], sort:['ymd','seq']},
    cust:     {label:'불출처별',      lead:['cc','ct','chg','ymd','seq','ic','mat','nm','spec','lg','sg','incust'], sort:['cc','ymd','seq'], g1:'cc',g2:'ymd',l1:'불출처소계',l2:'일계'},
    item:     {label:'품목별',        lead:['ic','mat','nm','spec','lg','sg','incust','ymd','seq','cc','ct','chg'], sort:['mat','ymd','seq'], g1:'mat',g2:'ymd',l1:'품목계',l2:'일계'},
    custitem: {label:'불출처/품목별',  lead:['cc','ct','chg','ic','mat','nm','spec','lg','sg','incust','ymd','seq'], sort:['cc','mat','ymd','seq'], g1:'cc',g2:'mat',l1:'불출처소계',l2:'품목계'},
    itemcust: {label:'품목/불출처별',  lead:['ic','mat','nm','spec','lg','sg','incust','cc','ct','chg','ymd','seq'], sort:['mat','cc','ymd','seq'], g1:'mat',g2:'cc',l1:'품목계',l2:'불출처소계'},
  };
  const API=API_BASE;
  let gijun='close', mode='day', cur=[], pool=[], loading=false, msg='', curYm='', curFrom='', curTo='', source='live';   // ★Phase5 데이터원(기본 라이브 무변경)
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
     <div class="page-sub">LG外 전 매출(유상사급 포함) 라인 명세 · 원본 <code>PU/SA_T_STOCK_MAINT</code>+<code>PU_T_STOCK_MAINT_C</code> · 🔴 라이브 ${gijun==='close'?`마감기준 ${esc(ymToInput(curYm)||'-')}`:`불출기준 ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
     <div class="toolbar">
       <label class="tl">조회기준</label>
       <div class="toggle-group"><button data-g="close" class="${gijun==='close'?'on':''}">마감기준</button><button data-g="issue" class="${gijun==='issue'?'on':''}">불출기준</button></div>
       <label class="tl">${gijun==='close'?'마감년월':'불출일자'}</label>
       ${gijun==='close'?`<input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||'2026-07')}" style="min-width:120px">`:`<input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom))}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo))}" style="min-width:130px">`}
       <label class="tl">출력방식</label>
       <select class="sel" id="mode">${Object.entries(MODES).map(([k,v])=>`<option value="${k}" ${mode===k?'selected':''}>${v.label}</option>`).join('')}</select>
     </div>
     <div class="toolbar">
       <select class="sel" id="lg"><option value="">전체 대분류</option>${lgs.map(x=>`<option value="${esc(x)}">${esc(lgN(x))}</option>`).join('')}</select>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgs.map(x=>`<option value="${esc(x)}">${esc(sgN(x))}</option>`).join('')}</select>
       <select class="sel" id="ct"><option value="">전체 거래처분류</option>${cts.map(x=>`<option value="${esc(x)}">${esc(ctN(x))}</option>`).join('')}</select>
       <input class="inp" id="cq" placeholder="불출처코드/명">
       <input class="inp" id="mq" placeholder="품번/품명/PART NO">
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
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
    const subRow=(label,q,a,g)=>`<tr class="${g||'subtot'}"><td colspan="${qi}" class="right">${esc(label)}</td><td class="num">${won(q)}</td><td colspan="4"></td><td class="num">${wonI(a)}</td></tr>`;
    const render=()=>{
      let lines=filt();
      lines.sort((a,b)=>{for(const k of cfg.sort){const c2=(''+(a[k]??'')).localeCompare(''+(b[k]??''),'ko',{numeric:true});if(c2)return c2;}return 0;});
      cur=lines;
      let html='';
      if(!cfg.g1){ lines.forEach(r=>html+=rowHtml(r)); }
      else {
        let g1v=null,g2v=null,s1q=0,s1a=0,s2q=0,s2a=0;
        lines.forEach(r=>{const v1=r[cfg.g1], v2=cfg.g2?r[cfg.g2]:null;
          if(g1v!==null && v1!==g1v){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a); html+=subRow(cfg.l1,s1q,s1a); s1q=s1a=s2q=s2a=0; g2v=null; }
          else if(cfg.g2 && g2v!==null && v2!==g2v){ html+=subRow(cfg.l2,s2q,s2a); s2q=s2a=0; }
          html+=rowHtml(r);
          s1q+=+r.qty||0; s1a+=+r.amt||0; s2q+=+r.qty||0; s2a+=+r.amt||0; g1v=v1; g2v=v2; });
        if(g1v!==null){ if(cfg.g2)html+=subRow(cfg.l2,s2q,s2a); html+=subRow(cfg.l1,s1q,s1a); }
      }
      const tq=lines.reduce((a,b)=>a+(+b.qty||0),0), ta=lines.reduce((a,b)=>a+(+b.amt||0),0);
      html+=subRow('총계',tq,ta,'grandtot');
      c.querySelector('#th').innerHTML=`<tr>${order.map(k=>`<th class="${CD[k].cls}">${CD[k].h}</th>`).join('')}</tr>`;
      c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${order.length}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
        :(msg?`<tr><td colspan="${order.length}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
        :(lines.length?html:`<tr><td colspan="${order.length}" class="empty">결과 없음</td></tr>`));
      c.querySelector('#sum').innerHTML=`<div class="s-item">라인 <b>${won(lines.length)}</b></div><div class="s-item">수량 합계 <b>${won(tq)}</b></div><div class="s-item ${ta<0?'neg':''}">금액 합계 <b>${wonI(ta)} 원</b></div>`;
      c.querySelector('#cnt').textContent=`${lines.length}라인 / 대상 ${pool.length}라인`;
      attachResizers(c);
    };
    const go=()=>{if(gijun==='close'){curYm=inYm(c.querySelector('#dto').value);}
      else{curFrom=inD(c.querySelector('#dfrom').value);curTo=inD(c.querySelector('#dto').value);}load();};
    c.querySelector('#go').onclick=render;   // ★검색=클라이언트 필터(검색어 유지)
    const _dto=c.querySelector('#dto');if(_dto)_dto.onchange=go;
    const _dfr=c.querySelector('#dfrom');if(_dfr)_dfr.onchange=go;
    ['#lg','#sg','#ct'].forEach(s=>c.querySelector(s).onchange=render);
    c.querySelector('#cq').onkeyup=e=>{if(e.key==='Enter')render();};
    c.querySelector('#mq').onkeyup=e=>{if(e.key==='Enter')render();};
    c.querySelector('#reset').onclick=()=>{mode='day';gijun='close';curYm='';load();};
    c.querySelector('#xls').onclick=()=>{
      const hd=order.map(k=>CD[k].h.replace(/<[^>]+>/g,''));
      const raw={ymd:r=>fmtYmd(r.ymd),seq:r=>r.seq,cc:r=>r.cnm,ct:r=>ctN(r.ct),chg:r=>chg(r.cc),ic:r=>r.ic,mat:r=>r.mat,nm:r=>r.nm,spec:r=>r.spec,lg:r=>lgN(r.lg),sg:r=>sgN(r.sg),incust:r=>r.incust,unit:r=>r.unit,qty:r=>r.qty,wt:r=>r.wt,cur:r=>curN(r.cur),rate:r=>(''+r.cur).trim()==='KRW'?'':r.rate,cost:r=>r.cost,amt:r=>Math.round(r.amt)};
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
      ? `<label class="tl">마감년월</label><input type="month" class="inp" id="dto" value="${esc(ymToInput(curYm)||'2026-07')}" style="min-width:120px">`
      : `<label class="tl">불출일자</label><input type="date" class="inp" id="dfrom" value="${esc(dToInput(curFrom)||'2026-07-01')}" style="min-width:130px"><span style="color:var(--muted)">~</span><input type="date" class="inp" id="dto" value="${esc(dToInput(curTo)||'2026-07-18')}" style="min-width:130px">`;
    c.innerHTML=`
     <div class="page-title">📤 자재불출집계표</div>
     <div class="page-sub">LG外 전 매출(유상사급 포함) · 원본 <code>PU/SA_T_STOCK_MAINT</code>+<code>PU_T_STOCK_MAINT_C</code> · 🔴 라이브 ${gijun==='close'?`마감기준(업체별 마감일) ${esc(ymToInput(curYm)||'-')}`:`불출기준(실제 이동일) ${esc(dToInput(curFrom))}~${esc(dToInput(curTo))}`}</div>
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
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
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
    const amtCells=r=>`<td class="num gstock">${wonI(r.amt)}</td>`+(vat?`${money(r.kamt)}${money(fVat(r.amt))}${money(fVat(r.kamt))}${money(r.amt+fVat(r.amt))}${money(r.kamt+fVat(r.kamt))}`:'');
    const amtSub=g=>`<td class="num gstock">${wonI(g.amt)}</td>`+(vat?`${money(g.kamt)}${money(fVat(g.amt))}${money(fVat(g.kamt))}${money(g.amt+fVat(g.amt))}${money(g.kamt+fVat(g.kamt))}`:'');
    const amtHdr=`<th class="num">금액</th>`+(vat?`<th class="num">금액(KRW)</th><th class="num">부가세</th><th class="num">부가세(KRW)</th><th class="num">합계</th><th class="num">합계(KRW)</th>`:'');
    const VC=vat?5:0;  // 추가 컬럼 수

    let lines=filt(), tbody='', thead='', grand={qty:0,amt:0,kamt:0}, ncols=0;
    if(mode==='wh'){
      // 창고별: item_code 무시하고 (cc,mat,cost,cur,lg,sg) 재집계
      const map=new Map();
      lines.forEach(r=>{const k=[r.cc,r.mat,r.cost,r.cur,r.lg,r.sg].join('|');
        if(!map.has(k))map.set(k,{...r,qty:0,amt:0,vat:0,kamt:0,kvat:0});
        const o=map.get(k);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.vat+=+r.vat||0;o.kamt+=+r.kamt||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko')||(''+a.mat).localeCompare(''+b.mat,'ko'));
      thead=`<tr><th>창고</th><th>창고명</th><th>매입유형</th><th>품명</th><th>PART NO</th><th>PART SPEC</th><th>대분류</th><th>소분류</th><th>입고처</th><th class="center">단위</th><th class="num">수량</th><th class="num">중량</th><th class="center">화폐</th><th class="num">환율</th><th class="num">단가</th><th class="num">단가(KRW)</th>${amtHdr}</tr>`;
      ncols=16+1+VC;
      const groups=[]; let ck=null;
      cur.forEach(r=>{if(r.cc!==ck){groups.push({cc:r.cc,cnm:r.cnm,ct:r.ct,rows:[]});ck=r.cc;}groups[groups.length-1].rows.push(r);});
      groups.forEach(g=>{
        g.rows.forEach(r=>{tbody+=`<tr><td><b>${esc(r.cc)}</b></td><td class="cap" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap" title="${esc(ctN(r.ct))}">${esc(ctN(r.ct))}</td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td>${esc(r.mat)}</td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td><td>${esc(lgN(r.lg))}</td><td>${esc(sgN(r.sg))}</td><td class="cap" title="${esc(r.incust)||''}">${esc(r.incust)||''}</td><td class="center">${esc(r.unit)||''}</td><td class="num">${won(r.qty)}</td><td class="num">${won(r.wt)}</td><td class="center">${esc(curN(r.cur))}</td><td class="num">${rateD(r)}</td><td class="num">${won(r.cost)}</td><td class="num">${won(r.kcost)}</td>${amtCells(r)}</tr>`;});
        const gs={qty:S(g.rows,'qty'),amt:S(g.rows,'amt'),kamt:S(g.rows,'kamt')};
        tbody+=`<tr class="subtot"><td colspan="10" class="right">(창고계) ${esc(g.cnm)}</td><td class="num">${won(gs.qty)}</td><td colspan="5"></td>${amtSub(gs)}</tr>`;
      });
    } else if(mode==='item'){
      cur=lines.slice().sort((a,b)=>(''+a.mat).localeCompare(''+b.mat,'ko')||(''+a.cc).localeCompare(''+b.cc,'ko'));
      thead=`<tr><th>품명</th><th>PART NO</th><th>PART SPEC</th><th>대분류</th><th>소분류</th><th>입고처</th><th>창고</th><th>창고명</th><th>매입유형</th><th class="center">단위</th><th class="num">수량</th><th class="num">중량</th><th class="center">화폐</th><th class="num">환율</th><th class="num">단가</th><th class="num">단가(KRW)</th>${amtHdr}</tr>`;
      ncols=16+1+VC;
      const groups=[]; let mk=null;
      cur.forEach(r=>{if(r.mat!==mk){groups.push({mat:r.mat,nm:r.nm,rows:[]});mk=r.mat;}groups[groups.length-1].rows.push(r);});
      groups.forEach(g=>{
        g.rows.forEach(r=>{tbody+=`<tr><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td><td><b>${esc(r.mat)}</b></td><td class="cap" title="${esc(r.spec)||''}">${esc(r.spec)||''}</td><td>${esc(lgN(r.lg))}</td><td>${esc(sgN(r.sg))}</td><td class="cap" title="${esc(r.incust)||''}">${esc(r.incust)||''}</td><td>${esc(r.cc)}</td><td class="cap" title="${esc(r.cnm)}">${esc(r.cnm)}</td><td class="cap">${esc(ctN(r.ct))}</td><td class="center">${esc(r.unit)||''}</td><td class="num">${won(r.qty)}</td><td class="num">${won(r.wt)}</td><td class="center">${esc(curN(r.cur))}</td><td class="num">${rateD(r)}</td><td class="num">${won(r.cost)}</td><td class="num">${won(r.kcost)}</td>${amtCells(r)}</tr>`;});
        const gs={qty:S(g.rows,'qty'),amt:S(g.rows,'amt'),kamt:S(g.rows,'kamt')};
        tbody+=`<tr class="subtot"><td colspan="10" class="right">(품목계) ${esc(g.nm)}</td><td class="num">${won(gs.qty)}</td><td colspan="5"></td>${amtSub(gs)}</tr>`;
      });
    } else { // 업체별 집계
      const map=new Map();
      lines.forEach(r=>{if(!map.has(r.cc))map.set(r.cc,{cc:r.cc,cnm:r.cnm,ct:r.ct,qty:0,amt:0,vat:0,kamt:0,kvat:0});
        const o=map.get(r.cc);o.qty+=+r.qty||0;o.amt+=+r.amt||0;o.vat+=+r.vat||0;o.kamt+=+r.kamt||0;o.kvat+=+r.kvat||0;});
      cur=[...map.values()].sort((a,b)=>(''+a.cc).localeCompare(''+b.cc,'ko'));
      thead=`<tr><th>거래처코드</th><th>거래처명</th><th>담당자</th><th>매입유형</th><th>사업자번호</th><th>전화번호</th><th>팩스번호</th><th class="num">수량</th><th class="num">금액</th><th class="num">금액(KRW)</th><th class="num">부가세</th><th class="num">부가세(KRW)</th><th class="num">합계</th><th class="num">합계(KRW)</th></tr>`;
      ncols=14;
      cur.forEach(r=>{const info=ci(r.cc), v6=(''+r.ct).trim()==='6'?'vat6':'';
        tbody+=`<tr><td><b>${esc(r.cc)}</b></td><td>${esc(r.cnm)}</td><td>${esc(chg(r.cc))||'-'}</td><td>${esc(ctN(r.ct))}</td><td>${esc(info.biz)}</td><td>${esc(info.tel)}</td><td>${esc(info.fax)}</td><td class="num">${won(r.qty)}</td><td class="num gstock">${wonI(r.amt)}</td><td class="num">${wonI(r.kamt)}</td><td class="num ${v6}">${wonI(r.vat)}</td><td class="num ${v6}">${wonI(r.kvat)}</td><td class="num">${wonI(r.amt+r.vat)}</td><td class="num">${wonI(r.kamt+r.kvat)}</td></tr>`;});
    }
    // 총계
    grand.qty=S(cur,'qty'); grand.amt=S(cur,'amt'); grand.kamt=S(cur,'kamt');
    if(mode==='cust'){const gv=S(cur,'vat'),gkv=S(cur,'kvat');
      tbody+=`<tr class="grandtot"><td colspan="7" class="right">총계 (${won(cur.length)} 업체)</td><td class="num">${won(grand.qty)}</td><td class="num">${wonI(grand.amt)}</td><td class="num">${wonI(grand.kamt)}</td><td class="num">${wonI(gv)}</td><td class="num">${wonI(gkv)}</td><td class="num">${wonI(grand.amt+gv)}</td><td class="num">${wonI(grand.kamt+gkv)}</td></tr>`;
    } else {
      tbody+=`<tr class="grandtot"><td colspan="10" class="right">총계</td><td class="num">${won(grand.qty)}</td><td colspan="5"></td>${amtSub({amt:grand.amt,kamt:grand.kamt})}</tr>`;
    }
    c.querySelector('#th').innerHTML=thead;
    c.querySelector('#body').innerHTML=loading?`<tr><td colspan="${ncols}" class="empty">${SPIN}라이브 조회 중…</td></tr>`
      :(msg?`<tr><td colspan="${ncols}" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`
      :(cur.length?tbody:`<tr><td colspan="${ncols}" class="empty">결과 없음</td></tr>`));
    sumbar(cur.length, grand.qty, grand.amt);
    c.querySelector('#cnt').textContent=`${cur.length}${mode==='cust'?'업체':'라인'} / 대상 ${lines.length}라인`;
    attachResizers(c);
    // 이벤트
    // 조회 = 선택 기간으로 라이브 재조회
    const go=()=>{if(gijun==='close'){curYm=inYm(c.querySelector('#dto').value);}
      else{curFrom=inD(c.querySelector('#dfrom').value);curTo=inD(c.querySelector('#dto').value);}load();};
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
      if(mode==='cust'){hd=['거래처코드','거래처명','담당자','매입유형','사업자번호','전화번호','팩스번호','수량','금액','금액(KRW)','부가세','부가세(KRW)','합계','합계(KRW)'];
        rows=cur.map(r=>{const i=ci(r.cc);return [r.cc,r.cnm,chg(r.cc),ctN(r.ct),i.biz,i.tel,i.fax,r.qty,Math.round(r.amt),Math.round(r.kamt),Math.round(r.vat),Math.round(r.kvat),Math.round(r.amt+r.vat),Math.round(r.kamt+r.kvat)];});}
      else{const base=['품명','PART NO','PART SPEC','대분류','소분류','입고처','창고','창고명','매입유형','단위','수량','중량','화폐','환율','단가','단가(KRW)','금액'].concat(vat?['금액(KRW)','부가세','부가세(KRW)','합계','합계(KRW)']:[]);
        hd=base;
        rows=cur.map(r=>[r.nm,r.mat,r.spec,lgN(r.lg),sgN(r.sg),r.incust,r.cc,r.cnm,ctN(r.ct),r.unit,r.qty,r.wt,curN(r.cur),(''+r.cur).trim()==='KRW'?'':r.rate,r.cost,r.kcost,Math.round(r.amt)].concat(vat?[Math.round(r.kamt),fVat(r.amt),fVat(r.kamt),Math.round(r.amt+fVat(r.amt)),Math.round(r.kamt+fVat(r.kamt))]:[]));}
      downloadCSV('자재불출집계표_'+gijun+'_'+mode+'.csv',hd,rows);
    };
  };
  load();
};

/* 자재 수불장 (구매/자재, 일=dw_pu_stock_260 / 월=dw_pu_stock_160) — 기초/입고/출고/기타/재고 × 수량·단가·금액 */
SCREEN.matledger=(c)=>{
  const API=API_BASE;
  let period='day';   // day=일수불장(PU_T_MONTH_STOCK_WH_DAILY) / month=월수불장(PU_T_MONTH_STOCK_WH)
  let pool=[], loading=false, curKey='', msg='', bounds=null;   // pool=라이브 조회결과, curKey=조회 일자/월(YYMMDD|YYMM), bounds=선택가능 범위
  const SG=DB.sgroupNames||{}, CT=DB.custTypeNames||{}, CHG=DB.chargeMap||{};
  const sgName=s=>{const k=(''+s).trim();return SG[k]||k||'';};      // 코드 숫자 없이 이름만
  const ctName=t=>{const k=(''+t).trim();return CT[k]||k||'';};      // 거래처분류(조달구분) 이름만
  const chg=cc=>CHG[(''+cc).trim()]||'';                             // 담당자(별도 매핑 룩업)
  const fmtYmd=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'';};
  const upr=(a,q)=>q?Math.round(a/q):0;   // 단가 = 금액/수량
  // 조회 키 ↔ input 변환
  const keyToInput=(p,k)=>{k=(''+(k||'')).trim();return p==='month'
      ?(k.length>=4?`20${k.slice(0,2)}-${k.slice(2,4)}`:'')
      :(k.length>=6?`20${k.slice(0,2)}-${k.slice(2,4)}-${k.slice(4,6)}`:'');};
  const inputToKey=(p,v)=>{v=(''+(v||'')).trim();return p==='month'?v.slice(2).replace('-',''):v.slice(2).replace(/-/g,'');};
  let cur=[], source='live';   // ★Phase5: 데이터원 라이브|nx(파생). 기본 라이브 무변경.
  const load=async(key)=>{
    if(source==='nx'){return nxDerivedView(c,`${API}/api/live/matledger?period=${period}`+(key?`&ymd=${encodeURIComponent(key)}`:'')+`&source=nx`,{title:'자재수불장',onBack:()=>{source='live';load(key);}});}
    loading=true;msg='';draw();
    try{const u=`${API}/api/live/matledger?period=${period}`+(key?`&ymd=${encodeURIComponent(key)}`:'');
      const r=await fetch(u);if(!r.ok)throw new Error('HTTP '+r.status);const j=await r.json();
      pool=j.rows||[];curKey=j.key||key||'';}
    catch(e){pool=[];msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';curKey=key||'';}
    loading=false;draw();};
  const draw=()=>{
    const isMonth=period==='month';
    const snap=keyToInput(period,curKey)||(isMonth?'':'');
    const src=isMonth?'PU_T_MONTH_STOCK_WH':'PU_T_MONTH_STOCK_WH_DAILY';
    const sub=isMonth?`월 마감 자재 수불(기초+입고−출고+기타=재고) · 단가=금액/수량 · 원본 <code>${src}</code> · 🔴 라이브 마감월 ${esc(snap||'-')}`
                     :`일자별 자재 수불(기초+입고−출고+기타=재고) · 단가=금액/수량 · 원본 <code>${src}</code> · 🔴 라이브 ${esc(snap||'-')}`;
    const sgroups=[...new Set(pool.map(r=>(''+r.sg).trim()).filter(Boolean))].sort();
    const custs=[...new Set(pool.map(r=>r.cust).filter(Boolean))].sort();
    // 선택 범위 제한(일=라이브 최신1일만, 월=마감월 범위) — 데이터 없는 날짜 조회로 빈화면 되는 것 방지
    const bDay=bounds&&bounds.day||{}, bMon=bounds&&bounds.month||{};
    const mmDay=bDay.max?`min="${keyToInput('day',bDay.min)}" max="${keyToInput('day',bDay.max)}"`:'';
    const mmMon=bMon.max?`min="${keyToInput('month',bMon.min)}" max="${keyToInput('month',bMon.max)}"`:'';
    const dateInput=isMonth
      ? `<label style="font-size:12px;color:var(--muted);font-weight:600;margin-left:4px">마감년월</label><input type="month" class="inp" id="dto" value="${esc(snap)}" ${mmMon} style="min-width:120px">`
      : `<label style="font-size:12px;color:var(--muted);font-weight:600;margin-left:4px">수불일자</label><input type="date" class="inp" id="dto" value="${esc(snap)}" ${mmDay} title="라이브 일수불은 최신 1일만 제공 · 과거는 월 수불장 이용" style="min-width:135px"><span style="font-size:11px;color:var(--muted)">＊일수불=라이브 최신 1일만 · 과거는 월 수불장</span>`;
    c.innerHTML=`
     <div class="page-title">📒 자재 수불장</div>
     <div class="page-sub">${sub}</div>
     <div class="toolbar">
       <div class="toggle-group"><button data-p="day" class="${isMonth?'':'on'}">일 수불장</button><button data-p="month" class="${isMonth?'on':''}">월 수불장</button></div>
       ${dateInput}
       <input class="inp" id="q" placeholder="품목코드/품명">
       <input class="inp" id="cust" list="ml-custl" placeholder="전체 매입처 (입력)" autocomplete="off" style="width:150px"><datalist id="ml-custl">${custs.map(w=>`<option value="${esc(w)}"></option>`).join('')}</datalist>
       <select class="sel" id="sg"><option value="">전체 소분류</option>${sgroups.map(s=>`<option value="${esc(s)}">${esc(sgName(s))}</option>`).join('')}</select>
       <select class="sel" id="gubun"><option value="all">전체</option><option value="plus">(+)재고</option><option value="minus">(-)재고</option></select>
       ${!isMonth?`<label style="display:inline-flex;align-items:center;gap:4px;font-size:12px;color:#c0392b;font-weight:700"><input type="checkbox" id="longstk"> 장기재고(3개월↑)</label>`:''}
       <button class="btn" id="go">검색</button><button class="btn ghost" id="reset">초기화</button>
       <button class="btn ghost" id="nxsrc" title="nx 단일원장 파생(대조용)">🔀 nx원장 파생</button>
       <div class="spacer"></div><button class="btn xls" id="xls">📥 엑셀 다운로드</button>
     </div>
     <div class="summary-bar" id="sum"></div>
     <div class="grid-wrap" style="max-height:510px;overflow:auto"><table class="tbl fit"><thead id="th"></thead><tbody id="body"></tbody></table></div>
     <div class="rowcount" id="cnt"></div>`;
    c.querySelectorAll('[data-p]').forEach(b=>b.onclick=()=>{period=b.dataset.p;curKey='';load('');});
    // 파생/정렬용 필드 사전계산 (단가=금액/수량, 소분류·조달구분·담당자·최종입고 룩업)
    pool.forEach(r=>{r._su=upr(r.sa,r.sq);r._bu=upr(r.ba,r.bq);r._iu=upr(r.ia,r.iq);r._ou=upr(r.oa,r.oq);r._tu=upr(r.ta,r.tq);
      r._sgn=sgName(r.sg);r._ctn=ctName(r.ctype);r._chg=chg(r.custcd);r._lin=fmtYmd(r.lastin);});
    c.querySelector('#th').innerHTML=`<tr>
      <th>품목코드</th><th class="cap">품명</th>
      <th class="num gstock">재고수량</th><th class="num gstock">재고단가</th><th class="num gstock">재고금액</th>
      <th>소분류</th><th>매입유형</th><th class="center">단위</th>
      <th class="num">기초재고</th><th class="num">기초단가</th><th class="num">기초금액</th>
      <th class="num">입고수량</th><th class="num">입고단가</th><th class="num">입고금액</th>
      <th class="num">출고수량</th><th class="num">출고단가</th><th class="num">출고금액</th>
      <th class="num">기타수량</th><th class="num">기타단가</th><th class="num">기타금액</th>
      <th>담당자</th><th class="cap">매입처명</th><th class="center">최종입고일</th></tr>`;
    const sumbar=rows=>{const bq=rows.reduce((a,b)=>a+(+b.bq||0),0),ba=rows.reduce((a,b)=>a+(+b.ba||0),0),
        sq=rows.reduce((a,b)=>a+(+b.sq||0),0),sa=rows.reduce((a,b)=>a+(+b.sa||0),0);
      c.querySelector('#sum').innerHTML=`<div class="s-item">건수 <b>${won(rows.length)}</b></div>
        <div class="s-item">기초금액 <b>${wonI(ba)}</b></div>
        <div class="s-item">재고수량 <b>${won(sq)}</b></div>
        <div class="s-item ${sa<0?'neg':''}">재고금액 <b>${wonI(sa)} 원</b></div>`;};
    const gbf=r=>{const gb=c.querySelector('#gubun').value;return gb==='all'||(gb==='plus'?r.sq>0:r.sq<0);};
    const T=(rs,k)=>rs.reduce((a,b)=>a+(+b[k]||0),0);
    const gtRow=rows=>rows.length?`<tr class="grandtot">
      <td colspan="2" class="right">총계 (${won(rows.length)}건)</td>
      <td class="num">${won(T(rows,'sq'))}</td><td></td><td class="num">${wonI(T(rows,'sa'))}</td>
      <td></td><td></td><td></td>
      <td class="num">${won(T(rows,'bq'))}</td><td></td><td class="num">${wonI(T(rows,'ba'))}</td>
      <td class="num">${won(T(rows,'iq'))}</td><td></td><td class="num">${wonI(T(rows,'ia'))}</td>
      <td class="num">${won(T(rows,'oq'))}</td><td></td><td class="num">${wonI(T(rows,'oa'))}</td>
      <td class="num">${won(T(rows,'tq'))}</td><td></td><td class="num">${wonI(T(rows,'ta'))}</td>
      <td></td><td></td><td></td></tr>`:'';
    const render=rows=>{cur=rows;c.querySelector('#body').innerHTML=rows.length?rows.map(r=>`<tr>
      <td><b>${esc(r.cd)}</b></td><td class="cap" title="${esc(r.nm)}">${esc(r.nm)}</td>
      <td class="num gstock qty"><b>${won(r.sq)}</b></td><td class="num gstock">${won(r._su)}</td><td class="num gstock amt"><b>${wonI(r.sa)}</b></td>
      <td>${esc(r._sgn)}</td><td>${esc(r._ctn)}</td><td class="center">${esc(r.unit)||''}</td>
      <td class="num">${won(r.bq)}</td><td class="num">${won(r._bu)}</td><td class="num">${wonI(r.ba)}</td>
      <td class="num">${won(r.iq)}</td><td class="num">${won(r._iu)}</td><td class="num">${wonI(r.ia)}</td>
      <td class="num">${won(r.oq)}</td><td class="num">${won(r._ou)}</td><td class="num">${wonI(r.oa)}</td>
      <td class="num">${won(r.tq)}</td><td class="num">${won(r._tu)}</td><td class="num">${wonI(r.ta)}</td>
      <td>${esc(r._chg)||'-'}</td><td class="cap" title="${esc(r.cust)||''}">${esc(r.cust)||'-'}</td><td class="center">${esc(r._lin)||'-'}</td></tr>`).join('')+gtRow(rows)
      :`<tr><td colspan="23" class="empty">${pool.length===0?(period==='day'?'해당 일자의 라이브 일수불 데이터가 없습니다 — 일수불은 최신 1일만 제공됩니다. 과거 조회는 <b>월 수불장</b>을 이용하세요.':'해당 마감월 데이터가 없습니다.'):'검색 결과 없음(필터 조건 확인)'}</td></tr>`;
      sumbar(rows);c.querySelector('#cnt').textContent=`${rows.length}건 / 대상 ${pool.length}건`;};
    // 장기재고 기준: 조회일(#dto)로부터 3개월 이전 → 최종입고일이 그보다 오래된 재고
    const cutoffYmd=()=>{const v=c.querySelector('#dto').value; if(!v)return null;
      const d=new Date(v); if(isNaN(d))return null; d.setMonth(d.getMonth()-3);
      const p=n=>('0'+n).slice(-2); return p(d.getFullYear()%100)+p(d.getMonth()+1)+p(d.getDate());};
    const apply=()=>{const q=c.querySelector('#q').value.trim().toLowerCase(),sg=c.querySelector('#sg').value,cu=c.querySelector('#cust').value;
      const lng=c.querySelector('#longstk')&&c.querySelector('#longstk').checked, cut=cutoffYmd();
      render(pool.filter(r=>gbf(r)&&(!sg||(''+r.sg).trim()===sg)&&(!cu||r.cust===cu)
        &&(!lng||(r.sq>0 && (''+(r.lastin||'')).trim()!=='' && (''+r.lastin).trim()<cut))
        &&(!q||(r.cd||'').toLowerCase().includes(q)||(r.nm||'').toLowerCase().includes(q))));};
    // 조회=선택 일자/월로 라이브 재조회. 일자 그대로면 필터만 적용.
    const go=()=>{const k=inputToKey(period,c.querySelector('#dto').value);if(k&&k!==curKey)load(k);else apply();};
    c.querySelector('#go').onclick=go;c.querySelector('#q').onkeyup=e=>{if(e.key==='Enter')apply();};
    c.querySelector('#nxsrc').onclick=()=>{source='nx';load(curKey);};   // ★Phase5: nx 파생 보기(라이브로 복귀 버튼 제공)
    c.querySelector('#dto').onchange=go;
    c.querySelector('#sg').onchange=apply;c.querySelector('#cust').onchange=apply;c.querySelector('#gubun').onchange=apply;
    if(c.querySelector('#longstk'))c.querySelector('#longstk').onchange=apply;
    c.querySelector('#reset').onclick=()=>{c.querySelector('#dto').value=snap;c.querySelector('#q').value='';c.querySelector('#sg').value='';c.querySelector('#cust').value='';c.querySelector('#gubun').value='all';if(c.querySelector('#longstk'))c.querySelector('#longstk').checked=false;apply();};
    c.querySelector('#xls').onclick=()=>downloadCSV((isMonth?'자재월수불장_':'자재일수불장_')+snap+'.csv',
      ['품목코드','품명','재고수량','재고단가','재고금액','소분류','매입유형','단위','기초재고','기초단가','기초금액','입고수량','입고단가','입고금액','출고수량','출고단가','출고금액','기타수량','기타단가','기타금액','담당자','매입처명','최종입고일'],
      cur.map(r=>[r.cd,r.nm,r.sq,r._su,Math.round(r.sa),r._sgn,r._ctn,r.unit,r.bq,r._bu,Math.round(r.ba),r.iq,r._iu,Math.round(r.ia),r.oq,r._ou,Math.round(r.oa),r.tq,r._tu,Math.round(r.ta),r._chg,r.cust,r._lin]));
    if(loading){c.querySelector('#body').innerHTML=spinRow(23);c.querySelector('#cnt').textContent='';}
    else if(msg){c.querySelector('#body').innerHTML=`<tr><td colspan="23" class="empty" style="color:#c0392b">⚠ ${esc(msg)}</td></tr>`;c.querySelector('#cnt').textContent='';}
    else{render(pool);
      enableSort(c,['cd','nm','sq','_su','sa','_sgn','_ctn','unit','bq','_bu','ba','iq','_iu','ia','oq','_ou','oa','tq','_tu','ta','_chg','cust','lastin'],()=>cur,render);}
  };
  // 초기: 선택가능 범위(일=라이브 최신1일 / 월=마감월 범위) 먼저 로드 → 최신 조회
  (async()=>{try{const r=await fetch(`${API}/api/live/matledger/dates`);if(r.ok)bounds=await r.json();}catch(e){}load('');})();
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
    c.innerHTML=`
     <div class="page-title">📤 자재출고관리 <span style="font-size:12px;color:var(--muted);font-weight:400">자재개별출고 (레거시 w_pu_stock_150)</span></div>
     <div class="page-sub">자재창고 → 생산/영업창고 개별출고(파트출고) 조회. 🔴 라이브 <code>PU_T_STOCK_MAINT</code> (MAINT_TAG='B') · 건수·수량합은 전체 집계.</div>
     <div class="toolbar">
       <label class="tl">출고기간</label><input type="date" class="inp" id="si-from" value="${esc(ymd2iso(tot._f)||m1Iso())}" style="min-width:130px"> ~ <input type="date" class="inp" id="si-to" value="${esc(ymd2iso(tot._t)||todayIso())}" style="min-width:130px">
       <label class="tl">FROM파트창고</label><select class="sel" id="si-fw">${opt(fw,F.fromwh)}</select>
       <input class="inp" id="si-pn" value="${esc(F._pn||'')}" placeholder="P/N 입력" style="width:130px">
       <input class="inp" id="si-mat" value="${esc(F._mat||'')}" placeholder="자도번 입력" style="width:130px">
       <label class="tl">TO창고구분</label><select class="sel" id="si-out"><option value="">전체</option><option value="1" ${F.out==='1'?'selected':''}>생산창고</option><option value="2" ${F.out==='2'?'selected':''}>영업창고</option></select>
       <label class="tl">TO작업장</label><select class="sel" id="si-tw">${opt(tw,F.towh)}</select>
       <button class="btn" id="si-go">🔍 조회</button>
       <div class="spacer"></div><button class="btn xls" id="si-xls">📥 엑셀</button>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="toolbar" style="margin-top:0"><span class="rowcount">총 <b>${nfq(tot.cnt)}</b>건 · 출고수량합 <b>${nf(tot.qty)}</b>${tot.pages>1?` · ${page}/${tot.pages}페이지(2000건씩)`:''}</span>
       ${tot.pages>1?`<div class="spacer"></div><button class="btn ghost" id="si-prev" ${page<=1?'disabled':''}>◀ 이전</button><button class="btn ghost" id="si-next" ${page>=tot.pages?'disabled':''}>다음 ▶</button>`:''}</div>
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
     <table class="tbl fit" style="font-size:12px"><thead><tr>
       <th class="center">출고일자</th><th class="num">출고SEQ</th><th>FROM파트창고</th><th>P/N</th><th>TO창고구분</th><th>TO파트창고</th><th>자도번</th>
       <th class="num">출고수량</th><th class="num">출고단가</th><th class="num">출고금액</th><th>비고</th><th>작업자</th><th class="center">작업일시</th></tr></thead>
     <tbody>${loading?spinRow(13):(rows.length?rows.map(r=>`<tr>
       <td class="center">${esc(fmtY(r.ymd))}</td><td class="num">${esc(r.seq)}</td><td>${esc(r.from_wh||'')}</td>
       <td class="cap" title="${esc(r.pn_nm||'')}"><b>${esc(r.pn||'')}</b></td><td>${esc(r.out_wh_nm||'')}</td><td>${esc(r.to_wh||'')}</td><td><b>${esc(r.mat||'')}</b></td>
       <td class="num qty">${nf(r.qty)}</td><td class="num">${nf(r.cost)}</td><td class="num">${nfq(r.amt)}</td><td class="cap" title="${esc(r.remarks||'')}">${esc(r.remarks||'')}</td><td>${esc(r.usr||'')}</td><td class="center">${esc(fmtDt(r.dt))}</td></tr>`).join('')
       :`<tr><td colspan="13" class="empty">${loading?'':'결과 없음'}</td></tr>`)}
       ${rows.length?`<tr class="grandtot"><td colspan="7" class="right">총계 (전체 ${nfq(tot.cnt)}건, 현재페이지 ${rows.length}건)</td><td class="num">${nf(tot.qty)}</td><td colspan="5"></td></tr>`:''}</tbody></table></div>`;
    const gv=id=>{const e=c.querySelector(id);return e?e.value.trim():'';};
    const doGo=()=>{F.out=gv('#si-out');F.fromwh=gv('#si-fw');F.towh=gv('#si-tw');F._pn=gv('#si-pn');F._mat=gv('#si-mat');tot._f=iso2ymd(gv('#si-from'));tot._t=iso2ymd(gv('#si-to'));page=1;load();};
    c.querySelector('#si-go').onclick=doGo;
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
SCREEN.salemagam=_mkMagam({base:'salemagam',weight:true,title:'🧾 매출마감처리',sub:'협력사 매출(tag5)',src:'PU_T_STOCK_MAINT(5)',verb:'매출',amtlbl:'매출금액'});
SCREEN.purmagam=_mkMagam({base:'purmagam',weight:false,title:'📥 매입마감처리',sub:'확정입고 매입(9/S/C/G/H)',src:'PU_T_STOCK_MAINT 확정입고',verb:'매입',amtlbl:'매입금액'});

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
     <div class="page-sub">좌: 생산계획(월) 대비 현재고·기발주 반영 추가발주(직접 조정 가능) · 우: 그 매입처 협력사 일자별 계획(한달). 조달 프로파일 배분(<code>nx.sourcing_profile</code>)·발주업체지정(<code>nx.order_vendor</code>)이 설정된 품목은 <b>이 매입처 몫</b>만 계상(미설정=현행 100%). 🔴 라이브 (계획 <code>PR_T_PLAN_ITEM_DTL</code>·재고 <code>PU_T_MONTH_STOCK_WH</code>)</div>
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
    c.querySelector('#mp-ym').onchange=e=>load(inYm(e.target.value));
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
  let showUnappr=false, routes=[], allocErrs=[];   // 조달경로 후보(단일 소스 nx.sourcing_route) + 저장된 route 단위 배분(nx.route_alloc)
  const loadAlloc=async()=>{try{const r=await fetch(`${API}/api/sourcing/route/alloc?item=${encodeURIComponent(sel)}&show_unapproved=${showUnappr?1:0}`);const j=await r.json();routes=j.routes||[];allocErrs=j.alloc_errs||[];}catch(e){routes=[];allocErrs=[];}};
  const search=async(auto)=>{searching=true;draw();
    try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(q)}`);slist=(await r.json()).rows||[];}
    catch(e){slist=[];msg='검색 실패';}
    searching=false;draw();if(auto&&slist.length&&!sel)open(slist[0].item);};
  const fillDL=()=>{const dl=c.querySelector('#sp-dl');if(dl)dl.innerHTML=slist.slice(0,60).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');};
  const ac=t=>{clearTimeout(acT);acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);slist=(await r.json()).rows||[];fillDL();}catch(e){}},180);};
  const open=async(item)=>{sel=item;selNm='';tree=null;tload=true;edit={};draw();
    try{const r=await fetch(`${API}/api/bom/tree?item=${encodeURIComponent(item)}`);const j=await r.json();tree=j.rows||[];selNm=j.name||'';}catch(e){tree=[];}
    await loadAlloc();
    tload=false;draw();};
  const curE=(rid,f,dflt)=>{const k=rid+'|'+f;return edit[k]!==undefined?edit[k]:dflt;};
  const setE=(rid,f,v)=>{edit[rid+'|'+f]=v;};
  const rfrom=r=>curE(r.route_id,'apply_from',r.apply_from||'');
  const rto=r=>curE(r.route_id,'apply_to',r.apply_to||'');
  const ract=r=>!!curE(r.route_id,'is_active',!!r.is_active);
  const ralloc=r=>curE(r.route_id,'alloc_ratio',(r.alloc_ratio!=null?r.alloc_ratio:''));
  const validOn=(r,d)=>{const f=rfrom(r),t=rto(r);return ract(r)&&(!f||f<=d)&&(!t||d<=t);};
  const aStat=()=>{const active=routes.filter(r=>ract(r)&&validOn(r,ref));const withAl=active.filter(r=>ralloc(r)!==''&&ralloc(r)!=null);const sum=Math.round(withAl.reduce((a,r)=>a+(parseFloat(ralloc(r))||0),0)*100)/100;return {n:active.length,sum,single:active.length<=1,withAl:withAl.length};};
  const autoset=()=>{routes.forEach(r=>{const isCur=r.current_flag||r.route_no===1;if(isCur){setE(r.route_id,'is_active',true);if(!rfrom(r))setE(r.route_id,'apply_from',FROM0);setE(r.route_id,'apply_to',OPEN);setE(r.route_id,'alloc_ratio',100);}else{setE(r.route_id,'is_active',false);setE(r.route_id,'apply_to',CLOSE);setE(r.route_id,'alloc_ratio','');}});msg='현행(R01) 활성·100% + 나머지 후보 비활성 마감('+CLOSE+'). [저장]으로 확정.';draw();};
  const save=async()=>{const rows=routes.filter(r=>!r.readonly).map(r=>{const al=ralloc(r);
      return {route_id:r.route_id,apply_from:rfrom(r)||null,apply_to:rto(r)||null,is_active:ract(r)?1:0,alloc_ratio:(ract(r)&&al!==''&&al!=null)?parseFloat(al):null};});
    try{const r=await fetch(`${API}/api/sourcing/route/alloc/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item:sel,rows})});
      const j=await r.json();if(j.ok){alert(`저장 완료 (${j.count}건)`);open(sel);return;}
      const hint=j.gate==='ALLOC'?'유효기간 겹치는 활성 후보 배분합=100% 확인':(j.gate==='APPROVE'?'미승인 후보는 활성 배정 불가(개발 승인 필요)':'저장 거부');
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
  // ===== R01(현행) 발주업체·단가 모달 (자동발주 근거) — 현행 매입처 자동시드 + 마스터 매입단가(읽기전용) =====
  let om=null, omAcT=null;   // om={item,asof,rows[],msg,loading,saving}
  const omOpen=async(it)=>{om={item:it,asof:'',rows:[],msg:'',loading:true,saving:false};draw();
    try{const r=await fetch(`${API}/api/sourcing/current_order?item=${encodeURIComponent(it)}`);const j=await r.json();
      om.asof=j.asof||'';om.rows=(j.rows||[]).map(x=>({item_code:x.item_code,item_name:x.item_name||'',spec:x.spec||'',qty:x.qty,
        make_label:x.make_label||'',cur_vendor_code:x.cur_vendor_code||'',cur_vendor_name:x.cur_vendor_name||'',
        ovr_vendor_code:x.ovr_vendor_code||'',master_price:x.master_price,price_apply:x.price_apply||'',
        sel_code:x.eff_vendor_code||'',sel_name:x.eff_vendor_name||''}));
    }catch(e){om.msg='발주 근거 로드 실패: '+e;}
    om.loading=false;draw();};
  const omClose=()=>{om=null;draw();};
  const omVendorAC=(t)=>{clearTimeout(omAcT);omAcT=setTimeout(async()=>{
    try{const r=await fetch(`${API}/api/sourcing/vendors?q=${encodeURIComponent(t)}`);const vs=(await r.json()).rows||[];
      om._vlist=vs;const dl=c.querySelector('#om-vdl');if(dl)dl.innerHTML=vs.map(v=>`<option value="${esc(v.name)}">${esc(v.name)} (${esc(v.code)})${v.role?' · '+esc(v.role):''}</option>`).join('');}catch(e){}},180);};
  const omResolve=(i,val)=>{const v=val.trim();const list=om._vlist||[];const hit=list.find(x=>x.name===v)||list.find(x=>x.code===v)||list.find(x=>(x.name||'').indexOf(v)>=0);
    if(hit){om.rows[i].sel_code=hit.code;om.rows[i].sel_name=hit.name;}else if(!v){om.rows[i].sel_code=om.rows[i].cur_vendor_code;om.rows[i].sel_name=om.rows[i].cur_vendor_name;}else{om.rows[i].sel_name=v;om.rows[i].sel_code='';}draw();};
  const omSave=async()=>{om.saving=true;om.msg='';draw();let cnt=0;
    try{for(const r of om.rows){const target=(r.sel_code===r.cur_vendor_code)?'':r.sel_code;   // 현행 매입처와 같으면 override 해제
        if(target===(r.ovr_vendor_code||''))continue;   // 변경 없음
        const res=await fetch(`${API}/api/sourcing/current_order/vendor`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_code:r.item_code,vendor_code:target})});
        if((await res.json()).ok)cnt++;}
      await omOpen(om.item);om.msg=`✅ 발주업체 저장 (${cnt}건 변경)`;draw();
    }catch(e){om.saving=false;om.msg='❌ 저장 실패: '+e;draw();}};
  const orderModal=()=>{if(!om)return '';
    const rowsHtml=om.loading?`<tr><td colspan="6">${spinRow(1)}</td></tr>`:(om.rows.length?om.rows.map((r,i)=>{
      const changed=(r.sel_code||'')!==(r.cur_vendor_code||'');
      return `<tr>
        <td style="white-space:nowrap"><b>${esc(r.item_code)}</b> <span style="font-size:10px;color:#8aa0bd">${esc(r.make_label||'')}</span></td>
        <td class="bcap" style="max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.item_name)}">${esc(r.item_name)}</td>
        <td class="num">${nfq(r.qty)}</td>
        <td><input class="inp om-e" list="om-vdl" autocomplete="off" data-i="${i}" value="${esc(r.sel_name||r.sel_code||'')}" placeholder="발주업체" style="width:180px;min-width:150px" ${canW?'':'disabled'}>${changed?`<div style="font-size:10px;color:#b8860b">변경(현행 ${esc(r.cur_vendor_name||r.cur_vendor_code)})</div>`:`<div style="font-size:10px;color:#8aa0bd">현행 매입처</div>`}</td>
        <td class="num" style="background:#f4f6fb" title="마스터 매입단가(PR_M_ITEM_COST·읽기전용)">${r.master_price==null?'<span style="color:#c9d1dc">-</span>':nfq(r.master_price)}${r.price_apply?` <span style="font-size:9px;color:#8aa0bd">${esc(r.price_apply)}</span>`:''}</td>
        <td class="center" style="font-size:11px;color:#778">${esc(r.sel_code||'')}</td>
      </tr>`;}).join(''):`<tr><td colspan="6" class="empty">현행 발주 대상 품목 없음(매입처 지정 품목 없음)</td></tr>`);
    return `<div class="wr-modal" style="position:fixed;inset:0;z-index:120;background:rgba(20,30,50,.42);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
      <div style="background:#fff;border-radius:10px;min-width:760px;max-width:96vw;box-shadow:0 8px 40px rgba(0,0,0,.25)">
       <div style="padding:12px 16px;border-bottom:1px solid #e2e8f2;display:flex;align-items:center;gap:10px">
         <span style="font-weight:700;font-size:15px;color:#1c7c3a">📦 발주업체·단가 <span style="font-size:11px;font-weight:400;color:#8aa0bd">(현행 R01 · 자동발주 근거)</span></span>
         <b style="color:#1c3a6e">${esc(om.item)}</b><span style="color:var(--muted);font-size:12px">${esc(selNm)} · 기준일 ${esc(om.asof||'')}</span>
         <div class="spacer" style="flex:1"></div>
         <button class="btn ghost" id="om-x" style="font-size:16px">✖</button></div>
       <div style="padding:8px 16px 4px;font-size:12px;color:#1c5b2e;background:#eefaf0;border-bottom:1px solid #cfe9d5">
         ✅ <b>자동발주 근거(품목→발주업체→단가)</b> — 현행 <b>매입처 자동시드</b>(레거시 실사용) + <b>마스터 매입단가</b>(PR_M_ITEM_COST as-of·<b>읽기전용·불변</b>). 발주업체를 바꾸면 nx에 저장(단가는 마감때만 수정, 여기선 변경 안 함).</div>
       <div style="padding:0 16px 12px;overflow:auto;max-height:66vh">
         <table class="tbl" style="font-size:12px;margin-top:8px"><thead><tr><th>품번</th><th>품명</th><th class="num">소요량</th><th>발주업체(현행 매입처)</th><th class="num">마스터 매입단가<br><span style="font-weight:400;font-size:10px">(읽기전용)</span></th><th class="center">코드</th></tr></thead>
         <tbody>${rowsHtml}</tbody></table>
         <datalist id="om-vdl"></datalist>
         <div style="font-size:11px;color:#8aa0bd;margin-top:4px">※ 발주업체 안 바꾸면 현행 매입처 그대로. 단가는 마스터(PR_M_ITEM_COST) 자동조회·읽기전용. R02(외주 SUB 후보)는 [🏭 업체·단가]에서.</div>
       </div>
       <div style="padding:10px 16px;border-top:1px solid #e2e8f2;display:flex;align-items:center;gap:8px">
         ${om.msg?`<span style="font-size:12px;font-weight:600;color:${om.msg.startsWith('✅')?'#1c7c3a':'#c0392b'}">${esc(om.msg)}</span>`:''}
         <div class="spacer" style="flex:1"></div>
         <button class="btn ghost" id="om-cancel">닫기</button>
         ${canW?`<button class="btn" id="om-save" style="background:#1c7c3a;color:#fff" ${om.saving?'disabled':''}>💾 발주업체 저장</button>`:''}</div>
      </div></div>`;};
  const wireOrder=()=>{if(!om)return;const g=id=>c.querySelector(id);
    const x=g('#om-x'),cn=g('#om-cancel');if(x)x.onclick=omClose;if(cn)cn.onclick=omClose;
    const sv=g('#om-save');if(sv)sv.onclick=omSave;
    c.querySelectorAll('.om-e').forEach(el=>{el.oninput=e=>omVendorAC(e.target.value);el.onchange=e=>omResolve(+el.dataset.i,e.target.value);});};
  const kindOf=n=>{if((n.nm||'').indexOf('용접봉')>=0)return{t:'용접봉',c:'#8e44ad'};if(n.haskids)return{t:'제작(SUB)',c:'#1c7c3a'};if(String(n.sag)==='1')return{t:'사급',c:'#b8860b'};return{t:'매입/구매',c:'#1c47a0'};};
  const treeTbl=()=>{if(!tree)return '';if(!tree.length)return `<div class="empty" style="margin-top:16px">설정된 BOM 구성 없음</div>`;
    return `<table class="tbl" style="font-size:12px"><thead><tr><th style="min-width:280px">레벨·품번</th><th>품명</th><th class="num">수량</th><th>구분</th><th>매입처</th></tr></thead><tbody>${tree.map(n=>{const k=kindOf(n),root=n.level===0;return `<tr style="${root?'background:#eef5ff;font-weight:700':''}"><td style="white-space:nowrap"><span style="display:inline-block;width:${n.level*18}px"></span>${n.level?'└ ':''}<b>${esc(n.code)}</b></td><td class="bcap" style="max-width:210px;overflow:hidden;text-overflow:ellipsis" title="${esc(n.nm)}">${esc(n.nm)}</td><td class="num">${root?'':nfq(n.qty)}</td><td>${root?'':`<span style="color:${k.c};font-weight:600">${k.t}</span>`}</td><td>${esc(n.custnm||'')}</td></tr>`;}).join('')}</tbody></table>`;};
  const badge=r=>{const on=r.current_flag;return `<span style="background:${on?'#1c7c3a':'#1c47a0'};color:#fff;border-radius:8px;padding:1px 8px;font-size:11px;font-weight:700">R${String(r.route_no).padStart(2,'0')}${on?' · 현행':''}</span>`;};
  const routeRow=r=>{const ro=r.readonly,valid=validOn(r,ref),al=ralloc(r);
    const canVend=r.approve_flag&&r.route_id>0;   // 승인 + 실저장 후보만 후보 업체·계획단가 지정(R02…)
    const isCur=r.current_flag||r.route_no===1;   // R01(현행) → 발주업체·단가(현행 매입처·마스터단가)
    return `<tr style="${r.current_flag?'background:#f0f7f0;':''}${ro?'background:#f4f4f4;opacity:.6;':((!valid)?'opacity:.6;':'')}">
      <td style="white-space:nowrap">${badge(r)} <b style="color:#1c3a6e">${esc(r.route_name||'')}</b>${canVend?` <button class="btn ghost sp-vend" data-ri="${r.route_id}" title="후보 업체·계획단가 지정" style="padding:1px 7px;font-size:11px">🏭 업체·단가</button>`:''}${isCur?` <button class="btn ghost sp-order" title="현행 발주업체·단가(자동발주 근거)" style="padding:1px 7px;font-size:11px;color:#1c7c3a;border-color:#9fd0ac">📦 발주업체·단가</button>`:''}</td>
      <td>${esc(r.gubun||'-')}</td>
      <td style="font-weight:600">${r.vendor_code?esc(r.vendor_name||r.vendor_code):'<span style="color:#aab">-</span>'}</td>
      <td class="center">${r.approve_flag?'<span style="background:#1c7c3a;color:#fff;border-radius:8px;padding:0 7px;font-size:10px">승인</span>':'<span style="background:#999;color:#fff;border-radius:8px;padding:0 7px;font-size:10px" title="개발 승인 전 — 배정 불가">미승인</span>'}</td>
      <td>${(canW&&!ro)?`<input class="inp sp-e" type="date" data-ri="${r.route_id}" data-f="apply_from" value="${esc(rfrom(r))}" style="width:120px;min-width:0">`:esc(rfrom(r)||'-')}</td>
      <td>${(canW&&!ro)?`<input class="inp sp-e" type="date" data-ri="${r.route_id}" data-f="apply_to" value="${esc(rto(r))}" style="width:120px;min-width:0" title="비우면 무기한">`:esc(rto(r)||'무기한')}</td>
      <td class="center">${(canW&&!ro)?`<input type="checkbox" class="sp-e" data-ri="${r.route_id}" data-f="is_active"${ract(r)?' checked':''}>`:(ro?'<span style="color:#c0392b;font-size:10px">배정불가</span>':(ract(r)?'✔':''))}</td>
      <td class="num">${(canW&&!ro)?`<input class="inp sp-e" type="number" step="0.1" data-ri="${r.route_id}" data-f="alloc_ratio" value="${al==null?'':al}" ${valid?'':'disabled'} style="width:60px;min-width:0;${valid?'':'background:#eee;color:#aab'}" placeholder="—">`:(al==null?'':al)}</td>
    </tr>`;};
  const routePanel=()=>{const appr=routes.filter(r=>r.approve_flag).length,un=routes.length-appr,A=aStat(),ok=A.single||Math.abs(A.sum-100)<0.01;
    return `<div style="font-weight:700;color:#334;margin:2px 0 4px">🧬 조달경로 후보 배정 <span style="font-size:11px;color:#8aa0bd;font-weight:400">(단일 소스 <code>nx.sourcing_route</code> · 승인 후보만 배정 · 저장 <code>nx.route_alloc</code>)</span>
      <label style="float:right;font-size:12px;font-weight:400;color:#5a6b82"><input type="checkbox" id="sp-unappr" ${showUnappr?'checked':''}> 미승인 보기</label></div>
      <div style="margin:0 0 6px;font-size:12px;color:${ok?'#1c7c3a':'#c0392b'};font-weight:600">${A.single?`활성 ${A.n}개(단일 → 100% 자동)`:`유효기간(${esc(ref)}) 겹치는 활성 ${A.n}개 배분합 ${A.sum}% ${ok?'✓':'(=100 필요)'}`}${allocErrs.length?` · 저장값 검증: ${esc(allocErrs.join(' / '))}`:''}</div>
      <table class="tbl" style="font-size:12px;margin:0"><thead><tr><th>경로</th><th>구분</th><th>공급처</th><th class="center">승인</th><th>유효시작</th><th>유효종료</th><th class="center">활성</th><th class="num">배분%</th></tr></thead>
      <tbody>${routes.length?routes.map(routeRow).join(''):`<tr><td colspan="8" class="empty">조달경로 후보 없음${!showUnappr?' — [미승인 보기]로 개발 진행중 후보 확인':' (개발 › 조달경로 통합검토에서 생성·승인)'}</td></tr>`}</tbody></table>
      <div class="page-sub" style="color:#8aa0bd;margin-top:3px">승인 ${appr}건${un?` · 미승인 ${un}건(회색·배정불가)`:''}. R01=현행(실사용 BOM 기준선·자동승인). 미승인 후보는 [개발 › 조달경로 통합검토]에서 승인해야 배정 가능.</div>`;};
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">🧭 조달 프로파일 <span style="font-size:12px;color:var(--muted);font-weight:400">승인 조달경로 후보(R01 현행·R02…)에 유효기간·배분% 배정</span></div>
     <div class="page-sub">품번 검색 → <b>실제 설정된 BOM</b>(참고) + <b>조달경로 후보 배정</b>. 후보(R01 vs R02…)마다 <b>유효기간·활성·배분%</b>(활성 겹치는 후보 합 100%) 지정. 저장 <code>nx.route_alloc</code></div>
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
          ${canW?`<button class="btn" id="sp-auto" title="현행 유지·비활성 마감">🪄 현행유지·비활성마감</button><button class="btn" id="sp-save" style="background:#1c47a0;color:#fff">💾 저장</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음</span>`}</div>
        ${tload?`<div class="grid-wrap" style="padding:20px">${spinRow(1)}</div>`:`<div style="overflow:auto;max-height:calc(100vh - 205px)">
          <div style="font-weight:700;color:#334;margin:2px 0 4px">📦 실제 설정된 BOM 구성</div>
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
    const au=g('#sp-auto');if(au)au.onclick=autoset;
    const rf=g('#sp-ref');if(rf)rf.onchange=()=>{ref=rf.value;draw();};
    const un=g('#sp-unappr');if(un)un.onchange=async()=>{showUnappr=un.checked;await loadAlloc();draw();};
    c.querySelectorAll('.sp-e').forEach(el=>{el.onchange=()=>{setE(el.dataset.ri,el.dataset.f,el.type==='checkbox'?el.checked:el.value);draw();};});
    c.querySelectorAll('.sp-vend').forEach(el=>el.onclick=()=>{const r=routes.find(x=>x.route_id==el.dataset.ri);if(r)pmOpen(r);});
    c.querySelectorAll('.sp-order').forEach(el=>el.onclick=()=>{if(sel)omOpen(sel);});
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
               <td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tmat-root">${nf(totMat)}</td><td class="num" style="color:#5a6a80;font-weight:700" id="be-tratio-root">${totSale>0?Math.round(totMat/totSale*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" id="be-tgag-root" title="총가공비 = 현재입고가 − 재료비">${nf(totGag)}</td><td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tsale-root" title="판가(현재입고가)">${nf(totSale)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>
             ${d.rows.map(r=>{const isTube=r.role==='제작동관';const isWeld=r.role==='용접봉';const isPipe=(r.role!=='반제품'&&!isWeld&&(r.coop_diam||r.unit_weight||isTube));const e=be.edits[r.code]||{};
             const dd=(e.diam!=null&&e.diam!=='')?e.diam:(r.coop_diam||'');const tt=(e.thick!=null&&e.thick!=='')?e.thick:(r.coop_thick||'');const ll=(e.length!=null&&e.length!=='')?e.length:(r.coop_length||'');
             const uw=beUw(r);const need=isTube&&!(dd&&tt&&ll);const ind=6+r.level*12;const pr=r.procs||{};
             const rq=beRowQty(r);const rmat=beRowMat(r);const rgag=beRowGag(r);const rtot=rmat+rgag;const rratio=rtot>0?Math.round(rmat/rtot*100):(rmat?100:0);
             const grey=r.in_quote===false;const matEd=be.matEdits&&be.matEdits[r.code];const qtyEd=be.qtyEdits&&be.qtyEdits[r.code];
             return `<tr style="${need?'background:#fdf0f0':''}">
               <td style="font-family:monospace;font-size:12px;padding-left:${ind}px">${r.haskids?'▸':''}${esc(r.code)}</td>
               <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td>
               <td>${(be.viewMode||r.haskids||r.role==='반제품')?beBadge(r.role_disp||r.role):(()=>{const cur=(r.role_v3==='동관고강도')?'동관고강도':(r.role==='제작동관'?'제작동관':(r.role==='용접봉'?'용접봉':'사급'));return `<select class="be-role" data-code="${esc(r.code)}" style="font-size:10px;padding:1px 2px;border:1px solid #cbd5e6;border-radius:6px;background:#fffbe8">${['제작동관','동관고강도','사급','용접봉'].map(o=>`<option${cur===o?' selected':''}>${o}</option>`).join('')}</select>`;})()}</td>
               <td class="num"><input class="be-qty inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(qtyEd!=null&&qtyEd!==''?qtyEd:(r.cum_qty||''))}" style="width:46px;min-width:0;text-align:right;padding:1px 2px"></td>
               <td class="num" style="color:#8aa0bd;font-size:11px">${r.lg_diam?('Φ'+r.lg_diam+'×'+r.lg_thick+'×'+r.lg_length):'-'}</td>
               ${isPipe?`<td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="diam" value="${esc(dd)}" style="width:38px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_diam||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="thick" value="${esc(tt)}" style="width:32px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_thick||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="length" value="${esc(ll)}" style="width:40px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_length||''}"></td>`
                 :`<td class="num" style="font-size:9px">${dd||'-'}</td><td class="num" style="font-size:9px">${tt||'-'}</td><td class="num" style="font-size:9px">${ll||'-'}</td>`}
               <td class="num be-uw" data-code="${esc(r.code)}">${(uw||r.unit_weight)?nf4(uw||r.unit_weight):(isWeld?'<span style="color:#b8791f;font-size:9px">공정</span>':'-')}</td>
               <td class="num be-sw" data-code="${esc(r.code)}" style="color:#1c6ec2">${(uw||r.unit_weight)?nf4((uw||r.unit_weight)*rq):'-'}</td>
               <td class="num">${isTube?`<input class="be-sg inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc((be.sagubEdits&&be.sagubEdits[r.code]!=null&&be.sagubEdits[r.code]!=='')?be.sagubEdits[r.code]:(r.coop_sagub>0?r.coop_sagub:''))}" style="width:60px;min-width:0;text-align:right;padding:1px 2px;color:#b8791f;font-weight:600" title="사급가(원/kg)">`:(isWeld&&r.coop_sagub>0?`<span style="color:#b8791f;font-size:11px" title="용접봉 사급가">${nf(r.coop_sagub)}</span>`:'<span style="color:#c9d1dc">-</span>')}</td>
               <td class="num" style="${grey?'color:#c9d1dc':'color:#c0392b;font-weight:700'}" title="현재(인상후) 재료비 (사급=판매단가·동관=소요중량×사급가·용접봉=소요×단가)">${grey?('('+nf(rmat)+')'):(isTube?`<span class="be-rm" data-code="${esc(r.code)}">${nf(rmat)}</span>`:`<input class="be-mat inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(matEd!=null&&matEd!==''?matEd:(r.mat_now||0))}" style="width:64px;min-width:0;text-align:right;padding:1px 2px;color:#c0392b;font-weight:700">`)}</td>
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
               <td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px">${nf(totMatB)}</td><td class="num" style="color:#5a6a80;font-weight:700">${totSaleB>0?Math.round(totMatB/totSaleB*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" title="종전 총가공비 = 종전입고가 − 종전재료비">${totGagB!=null?nf(totGagB):'-'}</td><td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px" title="종전 판가(종전입고가)">${totSaleB!=null?nf(totSaleB):'-'}</td>
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
                 <td class="num" style="color:#b8791f;font-weight:600">${sagubPrev!=null?nf(sagubPrev):'-'}</td>
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
     <div class="page-title">💱 협력사견적관리2 <span style="font-size:12px;color:var(--muted);font-weight:400">하위부품 bottom-up 견적 vs 실입고가 · nx.coop_quote</span></div>
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
               <td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tmat-root">${nf(totMat)}</td><td class="num" style="color:#5a6a80;font-weight:700" id="be-tratio-root">${totSale>0?Math.round(totMat/totSale*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" id="be-tgag-root" title="총가공비 = 현재입고가 − 재료비">${nf(totGag)}</td><td class="num" style="color:#c0392b;font-weight:800;font-size:14px" id="be-tsale-root" title="판가(현재입고가)">${nf(totSale)}</td>
               ${(d.proc_ops||[]).map(()=>'<td></td>').join('')}<td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>
             ${d.rows.map(r=>{const isTube=r.role==='제작동관';const isWeld=r.role==='용접봉';const isPipe=(r.role!=='반제품'&&!isWeld&&(r.coop_diam||r.unit_weight||isTube));const e=be.edits[r.code]||{};
             const dd=(e.diam!=null&&e.diam!=='')?e.diam:(r.coop_diam||'');const tt=(e.thick!=null&&e.thick!=='')?e.thick:(r.coop_thick||'');const ll=(e.length!=null&&e.length!=='')?e.length:(r.coop_length||'');
             const uw=beUw(r);const need=isTube&&!(dd&&tt&&ll);const ind=6+r.level*12;const pr=r.procs||{};
             const rq=beRowQty(r);const rmat=beRowMat(r);const rgag=beRowGag(r);const rtot=rmat+rgag;const rratio=rtot>0?Math.round(rmat/rtot*100):(rmat?100:0);
             const grey=r.in_quote===false;const matEd=be.matEdits&&be.matEdits[r.code];const qtyEd=be.qtyEdits&&be.qtyEdits[r.code];
             return `<tr style="${need?'background:#fdf0f0':''}">
               <td style="font-family:monospace;font-size:12px;padding-left:${ind}px">${r.haskids?'▸':''}${esc(r.code)}</td>
               <td class="cap" style="max-width:140px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td>
               <td>${(be.viewMode||r.haskids||r.role==='반제품')?beBadge(r.role_disp||r.role):(()=>{const cur=(r.role_v3==='동관고강도')?'동관고강도':(r.role==='제작동관'?'제작동관':(r.role==='용접봉'?'용접봉':'사급'));return `<select class="be-role" data-code="${esc(r.code)}" style="font-size:10px;padding:1px 2px;border:1px solid #cbd5e6;border-radius:6px;background:#fffbe8">${['제작동관','동관고강도','사급','용접봉'].map(o=>`<option${cur===o?' selected':''}>${o}</option>`).join('')}</select>`;})()}</td>
               <td class="num"><input class="be-qty inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(qtyEd!=null&&qtyEd!==''?qtyEd:(r.cum_qty||''))}" style="width:46px;min-width:0;text-align:right;padding:1px 2px"></td>
               <td class="num" style="color:#8aa0bd;font-size:11px">${r.lg_diam?('Φ'+r.lg_diam+'×'+r.lg_thick+'×'+r.lg_length):'-'}</td>
               ${isPipe?`<td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="diam" value="${esc(dd)}" style="width:38px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_diam||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="thick" value="${esc(tt)}" style="width:32px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_thick||''}"></td>
                 <td class="num"><input class="be-sp inp" data-code="${esc(r.code)}" data-f="length" value="${esc(ll)}" style="width:40px;min-width:0;text-align:right;padding:1px 2px;${need?'border-color:#c0392b':''}" placeholder="${r.lg_length||''}"></td>`
                 :`<td class="num" style="font-size:9px">${dd||'-'}</td><td class="num" style="font-size:9px">${tt||'-'}</td><td class="num" style="font-size:9px">${ll||'-'}</td>`}
               <td class="num be-uw" data-code="${esc(r.code)}">${(uw||r.unit_weight)?nf4(uw||r.unit_weight):(isWeld?'<span style="color:#b8791f;font-size:9px">공정</span>':'-')}</td>
               <td class="num be-sw" data-code="${esc(r.code)}" style="color:#1c6ec2">${(uw||r.unit_weight)?nf4((uw||r.unit_weight)*rq):'-'}</td>
               <td class="num">${isTube?`<input class="be-sg inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc((be.sagubEdits&&be.sagubEdits[r.code]!=null&&be.sagubEdits[r.code]!=='')?be.sagubEdits[r.code]:(r.coop_sagub>0?r.coop_sagub:''))}" style="width:60px;min-width:0;text-align:right;padding:1px 2px;color:#b8791f;font-weight:600" title="사급가(원/kg)">`:(isWeld&&r.coop_sagub>0?`<span style="color:#b8791f;font-size:11px" title="용접봉 사급가">${nf(r.coop_sagub)}</span>`:'<span style="color:#c9d1dc">-</span>')}</td>
               <td class="num" style="${grey?'color:#c9d1dc':'color:#c0392b;font-weight:700'}" title="현재(인상후) 재료비 (사급=판매단가·동관=소요중량×사급가·용접봉=소요×단가)">${grey?('('+nf(rmat)+')'):(isTube?`<span class="be-rm" data-code="${esc(r.code)}">${nf(rmat)}</span>`:`<input class="be-mat inp" data-code="${esc(r.code)}" type="number" step="any" value="${esc(matEd!=null&&matEd!==''?matEd:(r.mat_now||0))}" style="width:64px;min-width:0;text-align:right;padding:1px 2px;color:#c0392b;font-weight:700">`)}</td>
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
               <td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px">${nf(totMatB)}</td><td class="num" style="color:#5a6a80;font-weight:700">${totSaleB>0?Math.round(totMatB/totSaleB*100):0}%</td><td class="num" style="color:#1c7c3a;font-weight:800" title="종전 총가공비 = 종전입고가 − 종전재료비">${totGagB!=null?nf(totGagB):'-'}</td><td class="num" style="color:#8a6d3b;font-weight:800;font-size:14px" title="종전 판가(종전입고가)">${totSaleB!=null?nf(totSaleB):'-'}</td>
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
                 <td class="num" style="color:#b8791f;font-weight:600">${sagubPrev!=null?nf(sagubPrev):'-'}</td>
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
        try{await fetch(`${API}/api/coopquote2/set-role`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assy:be.assy,part:code,role})});}catch(e){}
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
