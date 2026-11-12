'use strict';
const $ = (q) => document.querySelector(q);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {user:null, tab:'overview', exams:[], attempts:[], candidates:[], data:null, index:0, saving:false, pending:{}, events:[], client:sessionStorage.getItem('exam-client') || crypto.randomUUID(), offset:0, busy:false};
sessionStorage.setItem('exam-client', state.client);
const active = () => state.data?.status === 'in_progress';
let toastTimer, heartbeatTimer, timerTick, lastEvent = {}, editorExam = null;
const logo = '<div class="logo"><span class="logo-mark">M</span>MeritGate<span class="sr-only"> Examination Portal</span></div>';
const date = (t) => new Date(t * 1000).toLocaleString();
const label = (s) => String(s).replaceAll('_',' ');
const badge = (s) => `<span class="tag ${['pending_review','in_progress'].includes(s)?'warn':['disqualified','not_qualified'].includes(s)?'bad':''}">${esc(label(s))}</span>`;
function toast(message) { $('#toast').textContent=message; $('#toast').style.display='block'; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').style.display='none',5000); }
async function api(path, method='GET', body) {
  const headers={'Content-Type':'application/json'};
  if (state.data) headers['X-Exam-Client']=state.client;
  const r=await fetch('/v1'+path,{method,credentials:'same-origin',headers,body:body===undefined?undefined:JSON.stringify(body)});
  let data; try { data=await r.json(); } catch { data={detail:'The service is temporarily unavailable.'}; }
  if (!r.ok) {
    const message=typeof data.detail==='string'?data.detail:(Array.isArray(data.detail)?data.detail.map(x=>x.msg).join('; '):'Request failed');
    const e=new Error(message); e.status=r.status; throw e;
  }
  return data;
}
function closeModal(){ $('#modal').innerHTML=''; editorExam=null; }
function modal(title, body, actions='') {
  $('#modal').innerHTML=`<div class="modal-backdrop"><section class="modal-box" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-head"><h2>${esc(title)}</h2><button class="small" data-action="close-modal" aria-label="Close dialog">✕</button></div>${body}${actions}</section></div>`;
  $('#modal input, #modal button')?.focus();
}
function loginView(error='') {
  $('#app').innerHTML=`<main class="login"><section class="login-brand">${logo}<div><div class="eyebrow">A fair start. A clear standard.</div><h1>Your next chapter<br>starts with merit.</h1><p>A focused examination experience for candidates, with a clear path from assessment to qualification review.</p><span class="tag">CANDIDATE EXAMINATIONS</span></div><small>MeritGate Examination Portal · Designed for accountable assessments</small></section><section class="login-area"><form class="login-box" id="login-form"><div class="eyebrow">Welcome to MeritGate</div><h2>Sign in to your portal</h2><p>Use the user ID and password provided by your examination administrator.</p><label for="username">User ID</label><input id="username" name="username" autocomplete="username" placeholder="Enter your user ID" required maxlength="80"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" placeholder="Enter your password" required maxlength="128"><div class="error" id="form-error" role="alert">${esc(error)}</div><button class="primary" type="submit">Sign in securely →</button><small>Need access or a password reset? Contact your examination administrator.</small></form></section></main>`;
}
function shell(body) {
  const isAdmin=state.user.role==='admin';
  const tabs=isAdmin?[['overview','◈','Overview'],['exams','▤','Examinations'],['candidates','♙','Candidates'],['reviews','◎','Attempts & review'],['audit','≡','Activity log']]:[['overview','◈','My examinations'],['results','◎','My results']];
  $('#app').innerHTML=`<div class="layout"><aside class="sidebar">${logo}<div><div class="eyebrow">${isAdmin?'Examination management':'Candidate workspace'}</div><nav>${tabs.map(([id,icon,name])=>`<button class="${state.tab===id?'active':''}" data-action="tab" data-id="${id}"><span>${icon}</span>${name}</button>`).join('')}</nav></div><div class="side-note"><strong>Every step, accounted for.</strong><br>Timed assessments. Saved answers.<br>Human review when it matters.</div></aside><div><header class="topbar"><span class="muted">Examination portal / <b>${esc(label(state.tab))}</b></span><div class="identity"><span class="avatar">${esc(state.user.name.charAt(0))}</span><span>${esc(state.user.name)}<small>${isAdmin?'Administrator':'Candidate'} · ${esc(state.user.username)}</small></span><button class="small ghost" data-action="logout">Sign out</button></div></header><main class="content">${body}<footer class="footer"><span>MeritGate · Examination & qualification review</span><span>Support: your examination administrator</span></footer></main></div></div>`;
}
function stats(items){ return `<div class="stats">${items.map(([name,value,icon])=>`<div class="stat"><span class="label">${esc(name)}</span><span class="stat-icon">${icon}</span><div class="value">${value}</div><span class="label">${name==='Assigned examinations'?'Your examination journey':'Current overview'}</span></div>`).join('')}</div>`; }
function examCard(e, admin=false) {
  const a=e.attempt;
  return `<article class="exam-card"><div class="eyebrow">${admin?'Examination management':'Assigned examination'} · ${e.published?'Published':'Draft'}</div><h2>${esc(e.title)}</h2><p>${esc(e.description)}</p><div class="card-meta"><div><b>${e.duration_minutes} min</b><span>Duration</span></div><div><b>${e.question_count}</b><span>Questions</span></div><div><b>${e.pass_percent}%</b><span>Pass mark</span></div><div><b>MCQ</b><span>Assessment format</span></div></div><div class="card-foot"><span>${a?badge(a.outcome):admin?badge(e.published?'published':'draft'):'● Fullscreen requested · answers autosaved'}</span><div>${admin?`${!e.published?`<button class="small" data-action="edit-exam" data-id="${e.id}">Edit draft</button> <button class="small primary" data-action="publish" data-id="${e.id}">Publish</button>`:''} <button class="small" data-action="assign" data-id="${e.id}">Assign candidate</button>`:`<button class="primary" data-action="preflight" data-id="${e.id}">${a?(a.status==='in_progress'?'Resume exam →':'View result →'):'View instructions →'}</button>`}</div></div></article>`;
}
function candidateDashboard() {
  const done=state.exams.filter(e=>e.attempt && e.attempt.status!=='in_progress');
  const result=state.tab==='results';
  const list=result?done:state.exams;
  shell(`<div class="page-heading"><div><div class="eyebrow">Candidate workspace</div><h1>${result?'Your results':`Welcome, ${esc(state.user.name.split(' ')[0])}.`}</h1><p>${result?'Assessment scores and qualification review status.':'Everything you need for your next examination, in one place.'}</p></div><span class="tag">${result?'ASSESSMENT HISTORY':'YOUR EXAMINATION JOURNEY'}</span></div>${stats([['Assigned examinations',state.exams.length,'▤'],['Completed',done.length,'✓'],['Qualified',done.filter(e=>e.attempt.outcome==='qualified').length,'◎']])}<div class="dashboard-grid"><section><div class="section-title"><h2>${result?'Completed examinations':'Your examinations'}</h2><span class="muted">${list.length} ${list.length===1?'assessment':'assessments'}</span></div>${list.length?list.map(e=>examCard(e)).join(''):'<div class="panel empty">No examinations to display. Your administrator assigns examinations to your account.</div>'}</section><aside><section class="panel"><h3>Your assessment journey</h3><ol class="steps"><li><b>Review the instructions</b>Check the duration, pass mark and examination rules.</li><li><b>Take your examination</b>Stay in the exam window. Answers save as you go.</li><li><b>View your outcome</b>See your score and any required human review.</li></ol></section><section class="panel"><div class="eyebrow">Before you begin</div><h3>Set yourself up for success</h3><p>Use a reliable connection, close other applications and allow enough time to finish.</p><div class="notice">Your timer continues if the connection drops or you leave the page.</div></section></aside></div>`);
}
function attemptTable(rows) {
  return `<div class="panel table-wrap"><table><thead><tr><th>Candidate</th><th>Examination</th><th>Score</th><th>Outcome</th><th>Signals</th><th>Actions</th></tr></thead><tbody>${rows.map(a=>`<tr><td><b>${esc(a.candidate)}</b><small>${esc(a.username)}</small></td><td>${esc(a.exam_title)}<small>${esc(label(a.status))}</small></td><td>${a.score_percent===null?'—':a.score_percent+'%'}</td><td>${badge(a.outcome)}</td><td>${a.event_count} events${a.needs_review?'<small>Review flagged</small>':''}</td><td><button class="small" data-action="events" data-id="${a.id}">Events</button>${a.status==='in_progress'?`<button class="small" data-action="recover" data-id="${a.id}">Recover</button>`:`<button class="small" data-action="review" data-id="${a.id}">Review</button>`}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">No attempts yet. Publish an exam and assign a candidate to begin.</td></tr>'}</tbody></table></div>`;
}
function adminDashboard() {
  let body='';
  if (state.tab==='overview') {
    body=`<div class="page-heading"><div><div class="eyebrow">Examination administration</div><h1>A clear view of every assessment.</h1><p>Create examinations, support candidates and review outcomes.</p></div><button class="primary" data-action="new-exam">＋ Create examination</button></div>${stats([['Candidates',state.candidates.length,'♙'],['Active attempts',state.attempts.filter(a=>a.status==='in_progress').length,'◷'],['Awaiting review',state.attempts.filter(a=>a.outcome==='pending_review').length,'◎']])}<div class="dashboard-grid"><section><div class="section-title"><h2>Recent attempts</h2><button class="small" data-action="refresh">Refresh</button></div>${attemptTable(state.attempts.slice(0,8))}</section><aside><div class="panel"><div class="eyebrow">Administration checklist</div><h3>From draft to decision</h3><ol class="steps"><li><b>Prepare questions</b>Verify wording and correct answers.</li><li><b>Publish & assign</b>Assign candidates individually.</li><li><b>Review fairly</b>Signals need context. Record your decision.</li></ol></div><div class="notice warn">Browser events are advisory. They do not prove misconduct.</div></aside></div>`;
  } else if(state.tab==='exams') {
    body=`<div class="page-heading"><div><div class="eyebrow">Assessment library</div><h1>Examinations</h1><p>Published questions and scoring rules are locked against modification.</p></div><button class="primary" data-action="new-exam">＋ Create examination</button></div>${state.exams.map(e=>examCard(e,true)).join('') || '<div class="panel empty">Create your first examination.</div>'}`;
  } else if(state.tab==='candidates') {
    body=`<div class="page-heading"><div><div class="eyebrow">Candidate access</div><h1>Candidates</h1><p>Provision individual accounts and issue credentials privately.</p></div><button class="primary" data-action="new-candidate">＋ Add candidate</button></div><div class="panel table-wrap"><table><thead><tr><th>Name</th><th>User ID</th><th>Account</th><th>Actions</th></tr></thead><tbody>${state.candidates.map(c=>`<tr><td><b>${esc(c.name)}</b></td><td>${esc(c.username)}</td><td>${badge('candidate')}</td><td><button class="small" data-action="reset-password" data-id="${c.id}">Reset password</button></td></tr>`).join('') || '<tr><td colspan="4">No candidates yet.</td></tr>'}</tbody></table></div>`;
  } else if(state.tab==='reviews') {
    body=`<div class="page-heading"><div><div class="eyebrow">Human review</div><h1>Attempts & review</h1><p>Review events in context. A heartbeat gap can also mean a network interruption.</p></div><div class="toolbar"><button data-action="refresh">Refresh</button><button class="primary" data-action="export">Export results ↓</button></div></div>${attemptTable(state.attempts)}`;
  } else {
    body=`<div class="page-heading"><div><div class="eyebrow">Accountability</div><h1>Activity log</h1><p>Latest 200 administrative and examination actions. Server timestamps.</p></div><button data-action="refresh">Refresh</button></div><div id="audit-content" class="panel">Loading activity…</div>`;
  }
  shell(body);
}
async function refresh() {
  state.exams=await api('/exams');
  if(state.user.role==='admin') {
    [state.attempts,state.candidates]=await Promise.all([api('/admin/attempts'),api('/admin/candidates')]);
    adminDashboard();
    if(state.tab==='audit') {
      const rows=await api('/admin/audit');
      $('#audit-content').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Actor</th><th>Detail</th></tr></thead><tbody>${rows.map(a=>`<tr><td>${esc(date(a.created_at))}</td><td>${esc(label(a.action))}</td><td>${esc(a.actor_id.slice(0,8))}</td><td>${esc(a.detail || a.target_id)}</td></tr>`).join('')}</tbody></table></div>`;
    }
  } else candidateDashboard();
}
function preflight(id) {
  const e=state.exams.find(x=>x.id===id);
  if(e.attempt && e.attempt.status!=='in_progress') return showResult(e.attempt,e);
  modal('Before you begin',`<div class="eyebrow">${esc(e.title)}</div><div class="card-meta"><div><b>${e.duration_minutes} minutes</b><span>Fixed server deadline</span></div><div><b>${e.question_count} questions</b><span>One answer per question</span></div><div><b>${e.pass_percent}%</b><span>Pass mark</span></div></div><ol class="steps"><li><b>Stay in this examination window</b>Fullscreen is requested. Leaving fullscreen or changing tabs is recorded.</li><li><b>Avoid copying, screenshots and sharing</b>This portal cannot block operating system screenshots or external screen sharing. Follow your examination rules.</li><li><b>Save and submit</b>Your answers save to the server. The timer continues during disconnections. Repeated signals or a heartbeat gap may require human review.</li></ol><div class="notice warn">This browser version provides monitoring signals, not device lockdown. No camera, microphone or screen recordings are collected.</div><label class="check"><input id="consent" type="checkbox">I understand the rules and consent to logging exam events, answer submissions, session activity and timestamps.</label><p class="error" id="modal-error" role="alert"></p>`,`<div class="modal-actions"><button data-action="close-modal">Cancel</button><button class="primary" data-action="start" data-id="${id}">${e.attempt?'Resume in fullscreen':'Enter fullscreen & start'} →</button></div>`);
}
async function begin(id) {
  if(!$('#consent')?.checked) throw new Error('Please acknowledge the examination rules.');
  if(!document.fullscreenEnabled) throw new Error('Fullscreen is unavailable in this browser. Use a supported desktop browser.');
  try { await document.documentElement.requestFullscreen(); }
  catch { throw new Error('Fullscreen was denied by the browser. Allow fullscreen for this site or use a supported desktop browser.'); }
  try {
    const data=await api(`/exams/${id}/start`,'POST',{client_id:state.client,consent:true});
    state.data=data;
    const detailed=await api(`/attempts/${data.id}`);
    state.data=detailed;
    state.exam=state.exams.find(e=>e.id===id);
    state.offset=detailed.server_time*1000-Date.now();
    const local=JSON.parse(sessionStorage.getItem('attempt-'+data.id)||'{}');
    state.pending=local.pending || {}; state.events=local.events || [];
    state.index=0; closeModal();
    if(!active()) return endExam();
    Object.assign(state.data.answers,state.pending);
    renderExam();
    heartbeatTimer=setInterval(pulse,10000);
    timerTick=setInterval(updateTimer,1000);
    updateTimer();
  } catch(e) {
    if(!active() && document.fullscreenElement) await document.exitFullscreen();
    throw e;
  }
}
function persist() {
  if(state.data) sessionStorage.setItem('attempt-'+state.data.id,JSON.stringify({pending:state.pending,events:state.events}));
}
function renderExam() {
  if(!active()) return;
  const d=state.data, qs=d.questions, q=qs[state.index], count=Object.keys(d.answers).filter(k=>d.answers[k]!==null).length;
  $('#app').innerHTML=`<div class="exam-shell"><header class="exam-top">${logo}<div><b>${esc(state.exam.title)}</b><br><small class="muted">${esc(state.user.name)} · ${esc(state.user.username)}</small></div><div><small>TIME REMAINING</small><div class="timer" id="timer">—</div></div></header><div class="exam-notice"><span>● Examination in progress · stay in this window</span><span id="save-state">${Object.keys(state.pending).length?'Answers awaiting sync':'All changes saved'}</span></div><main class="exam-body"><section class="panel question-panel"><span class="watermark">${esc(state.user.username)} · ${esc(d.id.slice(0,8))}</span><div class="eyebrow">Question ${state.index+1} of ${qs.length}</div><h2>${esc(q.prompt)}</h2>${q.options.map((o,i)=>`<button class="option ${d.answers[q.id]===i?'selected':''}" data-action="answer" data-index="${i}" ${state.saving?'disabled':''}><span class="letter">${'ABCD'[i]}</span>${esc(o)}</button>`).join('')}<div class="question-nav"><button data-action="previous" ${state.index===0?'disabled':''}>← Previous</button><button class="ghost small" data-action="clear-answer">Clear answer</button><button class="primary" data-action="next">${state.index===qs.length-1?'Review & submit':'Next question →'}</button></div></section><aside><section class="panel"><h3>Your progress</h3><span class="muted">${count} of ${qs.length} answered</span><div class="progress"><div id="exam-progress"></div></div><div class="palette">${qs.map((x,i)=>`<button class="${Number.isInteger(d.answers[x.id])?'done':''} ${i===state.index?'current':''}" data-action="jump" data-index="${i}" aria-label="Question ${i+1}">${i+1}</button>`).join('')}</div><p>Green = answered<br>Outlined = current question</p><button class="primary" data-action="submit-confirm">Submit examination</button></section><div class="notice warn">The server deadline continues if you leave or lose connection. Check that your answers have synced.</div><button class="small ghost" data-action="sync">Retry sync</button></aside></main></div>`;
  $('#exam-progress').style.width=(count/qs.length*100)+'%';
  updateTimer(); enforceFocus();
}
function updateTimer() {
  if(!active()) return;
  const remain=Math.max(0,Math.ceil((state.data.deadline*1000-Date.now()-state.offset)/1000));
  if($('#timer')) $('#timer').textContent=`${String(Math.floor(remain/60)).padStart(2,'0')}:${String(remain%60).padStart(2,'0')}`;
  if(remain===0) { $('#save-state').textContent='Time is up. Confirming final status…'; pulse(); }
}
async function flushAnswers() {
  if(!active() || state.saving) return;
  state.saving=true;
  try {
    for(const [id,value] of Object.entries(state.pending)) {
      await api(`/attempts/${state.data.id}/answer`,'PUT',{question_id:id,selected_index:value});
      if(state.pending[id]===value) delete state.pending[id];
      persist();
    }
    if($('#save-state')) $('#save-state').textContent=Object.keys(state.pending).length?'Answers awaiting sync':'All changes saved';
  } finally { state.saving=false; }
}
async function chooseAnswer(index) {
  if(state.saving) return;
  const q=state.data.questions[state.index];
  state.data.answers[q.id]=index;
  state.pending[q.id]=index; persist();
  try { await flushAnswers(); } catch(e){ toast('Answer kept in this tab. '+e.message); if(e.status===409) await pulse(); }
  renderExam();
}
function signal(kind) {
  if(!active()) return;
  const now=Date.now();
  if(now-(lastEvent[kind]||0)<3000) return;
  lastEvent[kind]=now;
  if(state.events.length<100) state.events.push({kind,event_id:crypto.randomUUID()});
  persist();
  if(!['window_resize','offline'].includes(kind)) toast('Exam event recorded: '+label(kind)+'. Stay in the examination window.');
}
async function flushEvents() {
  while(active() && state.events.length) {
    await api(`/attempts/${state.data.id}/events`,'POST',state.events[0]);
    state.events.shift(); persist();
  }
}
async function pulse() {
  if(!active() || state.busy) return;
  state.busy=true;
  try {
    // Heartbeat first: request-time deadline enforcement closes overdue attempts.
    const d=await api(`/attempts/${state.data.id}/heartbeat`,'POST');
    state.offset=d.server_time*1000-Date.now();
    if(d.status!=='in_progress') {state.data={...state.data,...d}; await endExam(); return;}
    await flushAnswers(); await flushEvents();
  } catch(e) {
    if($('#save-state')) $('#save-state').textContent='Sync interrupted. '+e.message;
    if(e.status===401 || e.status===409) block('Session needs recovery',e.message,true);
  } finally {state.busy=false;}
}
function block(title,text,exit=false) {
  let el=$('#exam-block');
  if(el?.dataset.fatal && !exit) return;
  if(!el){el=document.createElement('div');el.id='exam-block';document.body.appendChild(el);}
  el.className='blocked';
  if(exit) el.dataset.fatal='true';
  el.innerHTML=`<div class="inner"><div class="eyebrow">Examination paused on this screen</div><h1>${esc(title)}</h1><p>${esc(text)}</p><p>Your server timer is still running.</p><button class="primary" data-action="${exit?'session-exit':'restore-fullscreen'}">${exit?'Return to sign in':'Return to fullscreen'}</button></div>`;
}
function enforceFocus() {
  if(!active()) return;
  if(!document.fullscreenElement) block('Return to your examination','Fullscreen was exited. Your saved answers remain available.');
  else if(document.hasFocus() && $('#exam-block') && !$('#exam-block').dataset.fatal) $('#exam-block').remove();
}
function submitConfirm() {
  const count=Object.values(state.data.answers).filter(Number.isInteger).length;
  modal('Submit your examination?',`<p>You have answered <b>${count} of ${state.data.questions.length}</b> questions. You cannot change answers after submission.</p><p class="error" id="modal-error"></p>`,`<div class="modal-actions"><button data-action="close-modal">Keep working</button><button class="primary" data-action="submit">Submit final answers</button></div>`);
}
async function endExam() {
  clearInterval(heartbeatTimer); clearInterval(timerTick);
  $('#exam-block')?.remove(); closeModal();
  if(document.fullscreenElement) await document.exitFullscreen();
  sessionStorage.removeItem('attempt-'+state.data.id);
  state.pending={}; state.events=[];
  showResult(state.data,state.exam);
}
function showResult(data,exam) {
  state.data=data; state.exam=exam;
  shell(`<div class="page-heading"><div><div class="eyebrow">Assessment outcome</div><h1>Your examination result</h1><p>${esc(exam.title)}</p></div></div><section class="panel result">${badge(data.outcome)}<div class="score">${data.score_percent ?? '—'}<span class="muted">%</span></div><h2>${data.outcome==='qualified'?'Assessment passed':data.outcome==='pending_review'?'Awaiting administrator review':'Assessment completed'}</h2><p>${data.outcome==='pending_review'?'Your answers have been scored. An administrator will review the recorded signals before confirming your portal qualification status.':'Your outcome reflects the examination score and any recorded administrator decision.'}</p>${data.review_note?`<div class="notice">Review note: ${esc(data.review_note)}</div>`:''}<p>Passing this assessment records a portal result. Any official selection or eligibility decision remains with the responsible authority.</p><button class="primary" data-action="back-dashboard">Back to my examinations</button></section>`);
}
function examEditor(existing=null) {
  const example=[{prompt:'What is 10 percent of 250?',options:['10','20','25','50'],correct_index:2}];
  modal(existing?'Edit examination draft':'Create an examination',`<form id="exam-form"><label for="exam-title">Examination title</label><input id="exam-title" name="title" required minlength="3" maxlength="150" value="${esc(existing?.title||'')}"><label for="exam-desc">Description</label><textarea id="exam-desc" name="description" maxlength="3000">${esc(existing?.description||'')}</textarea><div class="field-row"><div><label for="duration">Duration (minutes)</label><input id="duration" name="duration_minutes" type="number" min="1" max="180" value="${existing?.duration_minutes||30}" required></div><div><label for="pass">Pass mark (%)</label><input id="pass" name="pass_percent" type="number" min="1" max="100" value="${existing?.pass_percent||60}" required></div></div><label for="questions-json">Questions (JSON · correct_index is 0–3)</label><textarea class="json-editor" id="questions-json" spellcheck="false" required>${esc(JSON.stringify(existing?.questions||example,null,2))}</textarea><p class="muted">Use 1–100 questions, each with four distinct options. This editor saves a draft; publishing is a separate step.</p><div class="toolbar"><input id="draft-topic" placeholder="Optional Gemma topic" aria-label="Question topic"><button type="button" data-action="gemma">Draft 3 questions with Gemma</button></div><div class="notice warn">Verify every question and correct answer. AI drafts can contain errors.</div><div class="error" id="modal-error"></div><div class="modal-actions"><button type="button" data-action="close-modal">Cancel</button><button class="primary" type="submit">Save draft</button></div></form>`);
  editorExam=existing?.id||null;
}
async function action(name, el) {
  const id=el.dataset.id;
  if(name==='close-modal') return closeModal();
  if(name==='tab'){ state.tab=id; state.data=null; return refresh(); }
  if(name==='refresh') return refresh();
  if(name==='logout'){ await api('/auth/logout','POST'); state.user=null;state.data=null;return loginView(); }
  if(name==='preflight') return preflight(id);
  if(name==='start') return begin(id);
  if(name==='answer') return chooseAnswer(Number(el.dataset.index));
  if(name==='clear-answer') return chooseAnswer(null);
  if(name==='previous'){state.index=Math.max(0,state.index-1);return renderExam();}
  if(name==='next'){if(state.index===state.data.questions.length-1)return submitConfirm();state.index++;return renderExam();}
  if(name==='jump'){state.index=Number(el.dataset.index);return renderExam();}
  if(name==='sync') return pulse();
  if(name==='restore-fullscreen'){await document.documentElement.requestFullscreen();$('#exam-block')?.remove();return;}
  if(name==='session-exit'){clearInterval(heartbeatTimer);clearInterval(timerTick);state.data=null;$('#exam-block')?.remove();if(document.fullscreenElement)await document.exitFullscreen();return loginView('Contact your administrator if the original examination session is unavailable.');}
  if(name==='submit-confirm') return submitConfirm();
  if(name==='submit') {
    if(state.saving || state.busy) throw new Error('Please wait for the current save to finish.');
    await flushAnswers(); await flushEvents();
    state.data={...state.data,...await api(`/attempts/${state.data.id}/submit`,'POST')};return endExam();
  }
  if(name==='back-dashboard'){state.data=null;state.tab='overview';return refresh();}
  if(name==='new-exam') return examEditor();
  if(name==='edit-exam') return examEditor(await api('/admin/exams/'+id));
  if(name==='publish') return modal('Publish examination',`<p>Publishing locks the question set, duration and pass mark. Confirm that a human has verified all questions and answer keys.</p><label class="check"><input id="publish-reviewed" type="checkbox">I have reviewed and approved this examination.</label><p class="error" id="modal-error"></p>`,`<div class="modal-actions"><button data-action="close-modal">Cancel</button><button class="primary" data-action="publish-confirm" data-id="${id}">Publish examination</button></div>`);
  if(name==='publish-confirm'){if(!$('#publish-reviewed').checked)throw new Error('Confirm human review before publishing.');await api(`/admin/exams/${id}/publish`,'POST',{reviewed:true});closeModal();toast('Examination published.');return refresh();}
  if(name==='assign') return modal('Assign a candidate',`<form id="assign-form" data-id="${id}"><label for="assign-user">Candidate</label><select id="assign-user" name="user_id" required>${state.candidates.map(c=>`<option value="${c.id}">${esc(c.name)} (${esc(c.username)})</option>`).join('')}</select><div class="error" id="modal-error"></div><div class="modal-actions"><button type="button" data-action="close-modal">Cancel</button><button class="primary" type="submit">Assign examination</button></div></form>`);
  if(name==='new-candidate') return modal('Add a candidate',`<form id="candidate-form"><label for="new-name">Full name</label><input id="new-name" name="name" required maxlength="120"><label for="new-user">User ID (letters, numbers, _, -, .)</label><input id="new-user" name="username" required pattern="[a-zA-Z0-9_.-]{3,80}"><label for="new-password">Initial password (at least 12 characters)</label><input id="new-password" name="password" type="password" autocomplete="new-password" required minlength="12" maxlength="128"><p class="muted">Share the credentials privately with the candidate.</p><div class="error" id="modal-error"></div><div class="modal-actions"><button type="button" data-action="close-modal">Cancel</button><button class="primary" type="submit">Create account</button></div></form>`);
  if(name==='reset-password') return modal('Reset candidate password',`<form id="password-form" data-id="${id}"><p>This signs out the candidate. For an active exam, also use session recovery if the original tab is unavailable.</p><label for="reset-pw">New password (12+ characters)</label><input id="reset-pw" name="password" type="password" minlength="12" maxlength="128" required autocomplete="new-password"><div class="error" id="modal-error"></div><div class="modal-actions"><button type="button" data-action="close-modal">Cancel</button><button class="primary" type="submit">Reset password</button></div></form>`);
  if(name==='review') return modal('Record a review decision',`<form id="review-form" data-id="${id}"><div class="notice warn">Focus loss or disconnection alone does not prove misconduct. Consider candidate explanations and examination rules.</div><label for="decision">Decision</label><select id="decision" name="decision"><option value="approve">Approve attempt (score determines pass/fail)</option><option value="reject">Disqualify attempt</option></select><label for="review-note">Reason and context (required)</label><textarea id="review-note" name="note" required minlength="10" maxlength="2000"></textarea><div class="error" id="modal-error"></div><div class="modal-actions"><button type="button" data-action="close-modal">Cancel</button><button class="primary" type="submit">Save review decision</button></div></form>`);
  if(name==='recover') return modal('Recover examination session',`<form id="recover-form" data-id="${id}"><p>This revokes the candidate's current login and releases the tab binding. The candidate can sign in again and resume. Saved answers and the original deadline are preserved; review is required.</p><label for="recover-note">Reason for recovery</label><textarea id="recover-note" name="note" minlength="10" maxlength="2000" required></textarea><div class="error" id="modal-error"></div><div class="modal-actions"><button type="button" data-action="close-modal">Cancel</button><button class="primary" type="submit">Recover session</button></div></form>`);
  if(name==='events') {
    const rows=await api(`/admin/attempts/${id}/events`);
    return modal('Recorded browser events',`<p class="muted">Server receipt times. Browser reports can be missing or manipulated. Heartbeat gaps may indicate connectivity issues.</p><div class="table-wrap"><table><thead><tr><th>Received</th><th>Signal</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(date(x.received_at))}</td><td>${esc(label(x.kind))}</td></tr>`).join('')||'<tr><td colspan="2">No browser events received.</td></tr>'}</tbody></table></div>`);
  }
  if(name==='export'){const r=await api('/admin/reports','POST');const a=document.createElement('a');a.href=r.download_url;a.download='meritgate-results.csv';a.click();toast('Report saved. Download requested.');return;}
  if(name==='gemma') {
    const topic=$('#draft-topic').value;
    toast('Drafting questions. Local Gemma may take a few minutes.');
    const r=await api('/admin/questions/draft','POST',{topic,count:3});
    $('#questions-json').value=JSON.stringify(r.questions,null,2);toast(r.notice);return;
  }
}
document.addEventListener('click',async ev=>{
  const el=ev.target.closest('[data-action]');if(!el || el.disabled)return;
  const name=el.dataset.action;
  try {
    // Fullscreen must be requested directly within the click's user activation.
    if(['start','restore-fullscreen'].includes(name)){await action(name,el);return;}
    if(!['answer','next','previous','jump','clear-answer'].includes(name))el.disabled=true;
    await action(name,el);
  } catch(e){const error=$('#modal-error');if(error)error.textContent=e.message;else toast(e.message);}
  finally{el.disabled=false;}
});
document.addEventListener('submit',async ev=>{
  ev.preventDefault();const form=ev.target,values=Object.fromEntries(new FormData(form)),button=form.querySelector('[type=submit]');
  button.disabled=true;
  try {
    if(form.id==='login-form'){state.user=await api('/auth/login','POST',values);state.tab='overview';await refresh();}
    if(form.id==='candidate-form'){await api('/admin/candidates','POST',values);closeModal();toast('Candidate account created.');await refresh();}
    if(form.id==='assign-form'){await api(`/admin/exams/${form.dataset.id}/assign`,'POST',values);closeModal();toast('Candidate assigned.');}
    if(form.id==='password-form'){await api(`/admin/candidates/${form.dataset.id}/password`,'POST',values);closeModal();toast('Password reset.');}
    if(form.id==='review-form'){await api(`/admin/attempts/${form.dataset.id}/review`,'POST',values);closeModal();toast('Review decision saved.');await refresh();}
    if(form.id==='recover-form'){await api(`/admin/attempts/${form.dataset.id}/recover`,'POST',values);closeModal();toast('Candidate can sign in again. Deadline preserved.');await refresh();}
    if(form.id==='exam-form') {
      const body={...values,duration_minutes:Number(values.duration_minutes),pass_percent:Number(values.pass_percent),questions:JSON.parse($('#questions-json').value)};
      await api(editorExam?'/admin/exams/'+editorExam:'/admin/exams',editorExam?'PUT':'POST',body);
      closeModal();toast('Examination draft saved.');await refresh();
    }
  }catch(e){const error=$('#form-error')||$('#modal-error');if(error)error.textContent=e.message;else toast(e.message);}
  finally{button.disabled=false;}
});
document.addEventListener('visibilitychange',()=>{if(active()&&document.hidden)signal('tab_hidden');else enforceFocus();});
document.addEventListener('fullscreenchange',()=>{if(active()&&!document.fullscreenElement)signal('fullscreen_exit');enforceFocus();});
window.addEventListener('blur',()=>{setTimeout(()=>{if(active()&&!document.hidden&&!document.hasFocus())signal('focus_lost');},600);});
window.addEventListener('focus',enforceFocus);
let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(active())signal('window_resize');},750);});
window.addEventListener('offline',()=>{signal('offline');if($('#save-state'))$('#save-state').textContent='Offline. Keep this tab open; pending answers retry after reconnection.';});
window.addEventListener('online',pulse);
window.addEventListener('beforeunload',e=>{if(active()){persist();e.preventDefault();e.returnValue='';}});
for(const [eventName,kind] of [['copy','copy_attempt'],['cut','copy_attempt'],['paste','paste_attempt'],['contextmenu','context_menu']]) {
  document.addEventListener(eventName,e=>{if(active()){e.preventDefault();signal(kind);}});
}
document.addEventListener('keydown',e=>{
  if(!active())return;
  if((e.ctrlKey||e.metaKey)&&['p','s','u'].includes(e.key.toLowerCase())){e.preventDefault();signal('print_shortcut');}
  if(e.key==='PrintScreen'||(e.metaKey&&e.shiftKey&&['3','4','5'].includes(e.key)))signal('screenshot_shortcut');
});
(async()=>{try{state.user=await api('/auth/me');await refresh();}catch(e){loginView(e.status===401?'':e.message);}})();
