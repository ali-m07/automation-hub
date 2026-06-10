let pdMeta = { modules: [], field_types: [] };
let pdAccess = { roles: [], groups: [] };
let pdStep = 1;
let pdType = 'single_line';

const PD_TYPES = [
    ['single_line', 'Single line', 'Short text such as title, code or department'],
    ['multi_line', 'Multi line', 'Long descriptions and notes'],
    ['single_select', 'Single select', 'Choose exactly one configured option'],
    ['multi_select', 'Multi choice', 'Choose multiple configured options'],
    ['single_user_picker', 'Single user picker', 'Choose one user from database or Active Directory'],
    ['multi_user_picker', 'Multi user picker', 'Choose multiple users or approvers'],
    ['number', 'Number', 'Numeric value with optional limits'],
    ['date', 'Date', 'Calendar date selection'],
    ['checkbox', 'Checkbox', 'Boolean yes or no value'],
    ['html', 'HTML content', 'Rich formatted content']
];

function pdEscape(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
function pdLines(id) { return document.getElementById(id)?.value.split('\n').map(v => v.trim()).filter(Boolean) || []; }
function pdSelected(id) { return Array.from(document.getElementById(id)?.selectedOptions || []).map(o => o.value); }
function pdJson(id, fallback) { const raw = document.getElementById(id).value.trim(); return raw ? JSON.parse(raw) : fallback; }
function pdStatus(message, type='info') { const box=document.getElementById('pd-status'); box.style.display='block'; box.className=`status-box ${type}`; box.textContent=message; }
async function pdRequest(url, options={}) { const response=await fetch(url,{credentials:'include',...options}); const data=await response.json(); if(!data.success) throw new Error(data.detail||data.error||'Request failed'); return data; }

function pdRenderTypes() {
    document.getElementById('pd-field-types').innerHTML = PD_TYPES.map(([type,title,description]) => `<button type="button" class="field-type-card ${type===pdType?'active':''}" onclick="pdChooseType('${type}')"><strong>${title}</strong><span>${description}</span></button>`).join('');
}

function pdChooseType(type) { pdType=type; pdRenderTypes(); pdRenderTypeSettings(); pdGoStep(2); }

function pdRenderTypeSettings() {
    const target=document.getElementById('pd-type-settings');
    if (['single_select','multi_select'].includes(pdType)) {
        target.innerHTML='<label>Options, one per line<textarea id="pd-field-options" class="form-control" rows="6" oninput="pdRenderPreview()" placeholder="Option A&#10;Option B"></textarea></label>';
    } else if (['single_user_picker','multi_user_picker'].includes(pdType)) {
        target.innerHTML='<div class="feedback-grid two"><label>User source<select id="pd-user-source" class="form-control" onchange="pdRenderPreview()"><option value="database">Servexa users</option><option value="ldap">Active Directory</option></select></label><label>Search minimum characters<input id="pd-user-min" type="number" min="0" max="10" value="2" class="form-control"></label></div>';
    } else if (pdType==='number') {
        target.innerHTML='<div class="feedback-grid two"><label>Minimum<input id="pd-number-min" type="number" class="form-control"></label><label>Maximum<input id="pd-number-max" type="number" class="form-control"></label></div>';
    } else if (pdType==='single_line' || pdType==='multi_line') {
        target.innerHTML='<div class="feedback-grid two"><label>Minimum length<input id="pd-text-min" type="number" min="0" class="form-control"></label><label>Maximum length<input id="pd-text-max" type="number" min="1" class="form-control"></label></div>';
    } else {
        target.innerHTML='<div class="feedback-empty">This field type needs no additional type-specific settings.</div>';
    }
    pdRenderPreview();
}

function pdRenderPreview() {
    const target=document.getElementById('pd-field-preview'); if(!target) return;
    const label=document.getElementById('pd-field-label')?.value||'Field label';
    const options=pdLines('pd-field-options').map(v=>`<option>${pdEscape(v)}</option>`).join('');
    let input=`<input class="form-control" placeholder="${pdEscape(document.getElementById('pd-field-placeholder')?.value||'Enter value')}">`;
    if(pdType==='multi_line') input='<textarea class="form-control" rows="3"></textarea>';
    if(pdType==='single_select') input=`<select class="form-control"><option>Select one...</option>${options}</select>`;
    if(pdType==='multi_select') input=`<select class="form-control" multiple size="4">${options}</select>`;
    if(pdType==='single_user_picker') input='<input class="form-control" placeholder="Search one user...">';
    if(pdType==='multi_user_picker') input='<select class="form-control" multiple size="3"><option>Selected users appear here</option></select>';
    if(pdType==='number') input='<input type="number" class="form-control">';
    if(pdType==='date') input='<input type="date" class="form-control">';
    if(pdType==='checkbox') input='<label class="feedback-toggle"><input type="checkbox"> Enabled</label>';
    if(pdType==='html') input='<div class="ticket-html"><strong>Formatted content preview</strong><p>HTML is sanitized before display.</p></div>';
    target.innerHTML=`<label>${pdEscape(label)}${input}</label>`;
}

function pdGoStep(step) {
    pdStep=Math.max(1,Math.min(3,step));
    document.querySelectorAll('[data-step-panel]').forEach(p=>p.hidden=Number(p.dataset.stepPanel)!==pdStep);
    document.querySelectorAll('[data-step-button]').forEach(b=>b.classList.toggle('active',Number(b.dataset.stepButton)===pdStep));
    document.getElementById('pd-prev').disabled=pdStep===1;
    document.getElementById('pd-next').hidden=pdStep===3;
    document.getElementById('pd-save-field').hidden=pdStep!==3;
    if(pdStep===2) pdRenderPreview();
}
function pdNext(){ pdGoStep(pdStep+1); } function pdPrevious(){ pdGoStep(pdStep-1); }
function pdToggleScope(){ document.getElementById('pd-field-modules-wrap').style.display=document.getElementById('pd-field-scope').value==='modules'?'grid':'none'; }

function pdTypeConfig() {
    const config={required:document.getElementById('pd-field-required').checked,placeholder:document.getElementById('pd-field-placeholder').value,help_text:document.getElementById('pd-field-help').value};
    if(['single_select','multi_select'].includes(pdType)) config.options=pdLines('pd-field-options');
    if(['single_user_picker','multi_user_picker'].includes(pdType)){config.user_source=document.getElementById('pd-user-source').value;config.min_search=Number(document.getElementById('pd-user-min').value||0);}
    if(pdType==='number'){config.min=document.getElementById('pd-number-min').value;config.max=document.getElementById('pd-number-max').value;}
    if(['single_line','multi_line'].includes(pdType)){config.min_length=document.getElementById('pd-text-min').value;config.max_length=document.getElementById('pd-text-max').value;}
    return config;
}

async function pdSaveField() {
    try {
        const label=document.getElementById('pd-field-label').value.trim(); if(!label) throw new Error('Field label is required.');
        if(['single_select','multi_select'].includes(pdType) && !pdLines('pd-field-options').length) throw new Error('Add at least one option.');
        const payload={label,key:document.getElementById('pd-field-key').value,type:pdType,scope_type:document.getElementById('pd-field-scope').value,scope_modules:pdSelected('pd-field-modules'),config:pdTypeConfig(),visibility:{roles:pdSelected('pd-field-roles'),groups:pdSelected('pd-field-groups')}};
        await pdRequest('/api/processes/fields',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        pdStatus('Custom field saved.','success'); pdGoStep(1); await pdLoad();
    } catch(error){pdStatus(error.message,'error');}
}

async function pdSaveRole(){try{await pdRequest('/api/processes/roles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('pd-role-name').value,key:document.getElementById('pd-role-key').value,description:document.getElementById('pd-role-description').value,permissions:pdLines('pd-role-permissions')})});pdStatus('Role saved.','success');await pdLoadAccess();}catch(e){pdStatus(e.message,'error');}}
async function pdSaveGroup(){try{await pdRequest('/api/processes/groups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('pd-group-name').value,key:document.getElementById('pd-group-key').value,members:pdLines('pd-group-members'),role_ids:pdSelected('pd-group-roles')})});pdStatus('Group saved.','success');await pdLoadAccess();}catch(e){pdStatus(e.message,'error');}}

async function pdLoadAccess(){
    pdAccess=await pdRequest('/api/processes/roles-groups');
    const roleOptions=pdAccess.roles.map(r=>`<option value="${pdEscape(r.id)}">${pdEscape(r.name)}</option>`).join('');
    const groupOptions=pdAccess.groups.map(g=>`<option value="${pdEscape(g.id)}">${pdEscape(g.name)}</option>`).join('');
    document.getElementById('pd-group-roles').innerHTML=roleOptions; document.getElementById('pd-field-roles').innerHTML=roleOptions; document.getElementById('pd-field-groups').innerHTML=groupOptions;
    document.getElementById('pd-roles').innerHTML=pdAccess.roles.map(r=>`<article class="ticket-card"><strong>${pdEscape(r.name)}</strong><span>${pdEscape(r.permissions.join(', ')||'No permissions')}</span></article>`).join('')||'<div class="feedback-empty">No roles yet.</div>';
    document.getElementById('pd-groups').innerHTML=pdAccess.groups.map(g=>`<article class="ticket-card"><strong>${pdEscape(g.name)}</strong><span>${g.members.length} member(s) · ${g.role_ids.length} role(s)</span></article>`).join('')||'<div class="feedback-empty">No groups yet.</div>';
}

async function pdSaveWorkflow(){try{const payload={name:document.getElementById('pd-workflow-name').value,key:document.getElementById('pd-workflow-key').value,description:document.getElementById('pd-workflow-description').value,scope_type:document.getElementById('pd-workflow-scope').value,scope_modules:pdSelected('pd-workflow-modules'),statuses:pdJson('pd-statuses',[]),transitions:pdJson('pd-transitions',[]),manage_policy:pdJson('pd-policy',{})};await pdRequest('/api/processes/workflows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});pdStatus('Workflow saved.','success');await pdLoad();}catch(e){pdStatus(e.message,'error');}}

async function pdLoad(){
    try{
        pdMeta=await pdRequest('/api/processes/meta');
        const options=pdMeta.modules.map(m=>`<option value="${pdEscape(m.key)}">${pdEscape(m.label)}</option>`).join('');
        document.getElementById('pd-field-modules').innerHTML=options; document.getElementById('pd-workflow-modules').innerHTML=options;
        await pdLoadAccess();
        const [fields,workflows]=await Promise.all([pdRequest('/api/processes/fields'),pdRequest('/api/processes/workflows')]);
        document.getElementById('pd-fields').innerHTML=fields.fields.map(f=>`<article class="ticket-card"><strong>${pdEscape(f.label)}</strong><span>${pdEscape(f.type.replaceAll('_',' '))} · ${f.scope_type==='global'?'all modules':pdEscape(f.scope_modules.join(', '))}</span></article>`).join('')||'<div class="feedback-empty">No shared fields yet.</div>';
        document.getElementById('pd-workflows').innerHTML=workflows.workflows.map(w=>`<article class="ticket-card"><strong>${pdEscape(w.name)}</strong><span>${w.statuses.length} statuses · ${w.transitions.length} transitions</span></article>`).join('')||'<div class="feedback-empty">No workflows yet.</div>';
        pdRenderTypes();pdRenderTypeSettings();pdToggleScope();
    }catch(e){pdStatus(e.message,'error');}
}
document.addEventListener('input',event=>{if(event.target.closest('[data-step-panel="2"]'))pdRenderPreview();});
document.addEventListener('DOMContentLoaded',pdLoad);
