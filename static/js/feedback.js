const FB_DEFAULT_PROJECT = {
    id: '',
    title: '180 Feedback Cycle',
    cycle: 'Quarterly',
    description: 'A modular 180 review cycle with admin-controlled workflow, screens and response form.',
    status: 'draft',
    workflow: {
        scale_min: 1,
        scale_max: 5,
        anonymous: true,
        deadline_days: 14,
        statuses: [
            { id: 'draft', name: 'Draft', category: 'todo', screen_id: 'screen_setup', description: 'Cycle is being configured by 180 admin.' },
            { id: 'ready', name: 'Ready to launch', category: 'todo', screen_id: 'screen_setup', description: 'Participants and questions are approved.' },
            { id: 'collecting', name: 'Collecting feedback', category: 'doing', screen_id: 'screen_response', description: 'Reviewers submit feedback.' },
            { id: 'calibration', name: 'Calibration', category: 'doing', screen_id: 'screen_summary', description: '180 admin reviews response quality.' },
            { id: 'closed', name: 'Closed', category: 'done', screen_id: 'screen_summary', description: 'Cycle is complete.' }
        ],
        screens: [
            { id: 'screen_setup', name: 'Setup screen', description: 'Admin defines objective, scale and participants.', fields: ['title', 'cycle', 'deadline', 'rating_scale'] },
            { id: 'screen_response', name: 'Reviewer response screen', description: 'Reviewer answers rating and text questions.', fields: ['subject', 'questions', 'overall_comment'] },
            { id: 'screen_summary', name: 'Manager summary screen', description: 'Feedback admin reviews scores and coaching notes.', fields: ['response_count', 'average_score', 'comments'] }
        ]
    },
    participants: { subjects: ['Sara Manager', 'Omid Lead'], reviewers: ['Direct manager', 'Peer reviewer', 'Team member'], matrix: {} },
    questions: [
        { id: 'q_1', category: 'Leadership', type: 'rating', required: true, text: 'Communicates priorities clearly and consistently.' },
        { id: 'q_2', category: 'Collaboration', type: 'rating', required: true, text: 'Builds trust and follows through on commitments.' },
        { id: 'q_3', category: 'Growth', type: 'text', required: false, text: 'What is one behavior this person should continue?' },
        { id: 'q_4', category: 'Growth', type: 'text', required: false, text: 'What is one behavior this person should improve?' }
    ],
    form_fields: [],
    tickets: [],
    responses: []
};

const FB_COLUMNS = [
    { id: 'todo', title: 'To do' },
    { id: 'doing', title: 'In progress' },
    { id: 'done', title: 'Done' }
];

let fbProjects = [];
let fbCurrent = structuredCloneSafe(FB_DEFAULT_PROJECT);
let fbPermissions = { can_manage_workflow: false, can_respond: true };
let fbSaving = false;
let fbDraggedStatusId = null;

function structuredCloneSafe(value) {
    return JSON.parse(JSON.stringify(value));
}

function fbEscape(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
}

function fbLines(value) {
    return String(value || '').split('\n').map((line) => line.trim()).filter(Boolean);
}

function fbSetStatus(message, type = 'info') {
    const box = document.getElementById('fb-status');
    if (!box) return;
    box.style.display = 'block';
    box.className = `status-box ${type}`;
    box.textContent = message;
}

function fbNormalizeWorkflow() {
    fbCurrent.workflow = fbCurrent.workflow || structuredCloneSafe(FB_DEFAULT_PROJECT.workflow);
    fbCurrent.workflow.statuses = fbCurrent.workflow.statuses?.length ? fbCurrent.workflow.statuses : structuredCloneSafe(FB_DEFAULT_PROJECT.workflow.statuses);
    fbCurrent.workflow.screens = fbCurrent.workflow.screens?.length ? fbCurrent.workflow.screens : structuredCloneSafe(FB_DEFAULT_PROJECT.workflow.screens);
}

function fbCollectProject() {
    fbNormalizeWorkflow();
    const scale = (document.getElementById('fb-scale')?.value || '1-5').split('-').map(Number);
    if (fbPermissions.can_manage_workflow) {
        fbCurrent.title = document.getElementById('fb-title')?.value.trim() || '180 Feedback Cycle';
        fbCurrent.cycle = document.getElementById('fb-cycle')?.value.trim() || 'Quarterly';
        fbCurrent.description = document.getElementById('fb-description')?.value.trim() || '';
        fbCurrent.workflow.scale_min = scale[0] || 1;
        fbCurrent.workflow.scale_max = scale[1] || 5;
        fbCurrent.workflow.deadline_days = Number(document.getElementById('fb-deadline')?.value || 14);
        fbCurrent.workflow.anonymous = Boolean(document.getElementById('fb-anonymous')?.checked);
        fbCurrent.participants.subjects = fbLines(document.getElementById('fb-subjects')?.value);
        fbCurrent.participants.reviewers = fbLines(document.getElementById('fb-reviewers')?.value);
        fbCollectScreens();
        fbCollectQuestions();
        fbCollectFormFields();
        fbCollectTransitions();
    }
}

function fbCollectFormFields() {
    fbCurrent.form_fields = Array.from(document.querySelectorAll('[data-fb-form-field]')).map((row, index) => ({
        id: row.dataset.fieldId || `field_${Date.now()}_${index}`,
        key: row.querySelector('[data-field-key]')?.value.trim() || `field_${index + 1}`,
        label: row.querySelector('[data-field-label]')?.value.trim() || 'Field',
        type: row.querySelector('[data-field-type]')?.value || 'single_line',
        required: Boolean(row.querySelector('[data-field-required]')?.checked),
        placeholder: row.querySelector('[data-field-placeholder]')?.value.trim() || '',
        help_text: row.querySelector('[data-field-help]')?.value.trim() || '',
        options: fbLines(row.querySelector('[data-field-options]')?.value),
        user_source: row.querySelector('[data-field-source]')?.value || 'database',
        condition_field: row.querySelector('[data-field-condition-key]')?.value.trim() || '',
        condition_operator: row.querySelector('[data-field-condition-operator]')?.value || 'equals',
        condition_value: row.querySelector('[data-field-condition-value]')?.value.trim() || ''
    }));
}

function fbCollectTransitions() {
    fbCurrent.workflow.transitions = Array.from(document.querySelectorAll('[data-fb-transition]')).map((row, index) => ({
        id: row.dataset.transitionId || `transition_${Date.now()}_${index}`,
        name: row.querySelector('[data-transition-name]')?.value.trim() || 'Transition',
        from_status: row.querySelector('[data-transition-from]')?.value || 'draft',
        to_status: row.querySelector('[data-transition-to]')?.value || 'ready',
        approver_type: row.querySelector('[data-transition-approver]')?.value || 'any_user',
        approver_value: row.querySelector('[data-transition-value]')?.value.trim() || '',
        condition_field: row.querySelector('[data-transition-condition-key]')?.value.trim() || '',
        condition_operator: row.querySelector('[data-transition-condition-operator]')?.value || 'equals',
        condition_value: row.querySelector('[data-transition-condition-value]')?.value.trim() || ''
    }));
}

function fbCollectScreens() {
    const screenRows = Array.from(document.querySelectorAll('[data-fb-screen]'));
    if (!screenRows.length) return;
    fbCurrent.workflow.screens = screenRows.map((row) => ({
        id: row.dataset.screenId,
        name: row.querySelector('[data-screen-name]')?.value.trim() || 'Workflow screen',
        description: row.querySelector('[data-screen-description]')?.value.trim() || '',
        fields: fbLines(row.querySelector('[data-screen-fields]')?.value).map((field) => field.replace(/^[-*]\s*/, ''))
    }));
}

function fbCollectQuestions() {
    fbCurrent.questions = Array.from(document.querySelectorAll('[data-fb-question]')).map((row, index) => ({
        id: row.dataset.questionId || `q_${index + 1}`,
        text: row.querySelector('[data-question-text]')?.value.trim() || '',
        category: row.querySelector('[data-question-category]')?.value.trim() || 'General',
        type: row.querySelector('[data-question-type]')?.value || 'rating',
        required: Boolean(row.querySelector('[data-question-required]')?.checked)
    })).filter((question) => question.text);
}

function fbSetAdminMode() {
    const isAdmin = fbPermissions.can_manage_workflow;
    document.body.classList.toggle('fb-readonly-user', !isAdmin);
    document.querySelectorAll('[data-admin-only]').forEach((el) => { el.style.display = isAdmin ? '' : 'none'; });
    ['fb-title', 'fb-cycle', 'fb-description', 'fb-deadline', 'fb-scale', 'fb-anonymous', 'fb-subjects', 'fb-reviewers'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.disabled = !isAdmin;
    });
    const lock = document.getElementById('fb-admin-lock');
    if (lock) lock.style.display = isAdmin ? 'none' : 'block';
}

function fbRenderAll() {
    fbNormalizeWorkflow();
    fbSetAdminMode();
    fbRenderProjectList();
    fbRenderSetup();
    fbRenderWorkflowBoard();
    fbRenderScreens();
    fbRenderParticipants();
    fbRenderQuestions();
    fbRenderFormFields();
    fbRenderTransitions();
    fbRenderTicketForm();
    fbRenderTickets();
    fbRenderPreview();
    fbRenderMetrics();
}

function fbRenderFormFields() {
    const target = document.getElementById('fb-form-fields');
    if (!target) return;
    const disabled = fbPermissions.can_manage_workflow ? '' : 'disabled';
    target.innerHTML = (fbCurrent.form_fields || []).map((field, index) => `<div class="process-builder-row" data-fb-form-field data-field-id="${fbEscape(field.id)}">
        <div class="feedback-grid three"><label>Label<input ${disabled} data-field-label class="form-control" value="${fbEscape(field.label)}"></label><label>Key<input ${disabled} data-field-key class="form-control" value="${fbEscape(field.key)}"></label><label>Type<select ${disabled} data-field-type class="form-control">${['single_line','multi_line','number','date','single_select','multi_select','user_picker','checkbox'].map(type => `<option value="${type}" ${field.type === type ? 'selected' : ''}>${type.replaceAll('_',' ')}</option>`).join('')}</select></label></div>
        <div class="feedback-grid three"><label>Placeholder<input ${disabled} data-field-placeholder class="form-control" value="${fbEscape(field.placeholder || '')}"></label><label>Help text<input ${disabled} data-field-help class="form-control" value="${fbEscape(field.help_text || '')}"></label><label>User source<select ${disabled} data-field-source class="form-control"><option value="database" ${field.user_source !== 'ldap' ? 'selected' : ''}>Database</option><option value="ldap" ${field.user_source === 'ldap' ? 'selected' : ''}>Active Directory</option></select></label></div>
        <div class="feedback-grid three"><label>Options (one per line)<textarea ${disabled} data-field-options class="form-control" rows="3">${fbEscape((field.options || []).join('\n'))}</textarea></label><label>Show when field<input ${disabled} data-field-condition-key class="form-control" value="${fbEscape(field.condition_field || '')}"></label><label>Condition<select ${disabled} data-field-condition-operator class="form-control"><option value="equals">equals</option><option value="not_equals" ${field.condition_operator === 'not_equals' ? 'selected' : ''}>not equals</option><option value="contains" ${field.condition_operator === 'contains' ? 'selected' : ''}>contains</option><option value="is_set" ${field.condition_operator === 'is_set' ? 'selected' : ''}>is set</option></select><input ${disabled} data-field-condition-value class="form-control" value="${fbEscape(field.condition_value || '')}" placeholder="Condition value"></label></div>
        <label class="feedback-toggle"><input ${disabled} data-field-required type="checkbox" ${field.required ? 'checked' : ''}> Required</label><button class="btn danger-soft" data-admin-only type="button" onclick="fbRemoveFormField(${index})">Remove</button>
    </div>`).join('') || '<div class="feedback-empty">No custom ticket fields yet.</div>';
    fbSetAdminMode();
}

function fbAddFormField() { fbCollectProject(); fbCurrent.form_fields.push({ id: `field_${Date.now()}`, key: `field_${fbCurrent.form_fields.length + 1}`, label: 'New field', type: 'single_line', required: false, options: [], user_source: 'database' }); fbRenderFormFields(); fbRenderTicketForm(); }
function fbRemoveFormField(index) { fbCollectProject(); fbCurrent.form_fields.splice(index, 1); fbRenderFormFields(); fbRenderTicketForm(); }

function fbRenderTransitions() {
    const target = document.getElementById('fb-transitions');
    if (!target) return;
    const disabled = fbPermissions.can_manage_workflow ? '' : 'disabled';
    const statuses = fbCurrent.workflow.statuses || [];
    const statusOptions = (selected) => statuses.map(status => `<option value="${fbEscape(status.id)}" ${status.id === selected ? 'selected' : ''}>${fbEscape(status.name)}</option>`).join('');
    target.innerHTML = (fbCurrent.workflow.transitions || []).map((item, index) => `<div class="process-builder-row" data-fb-transition data-transition-id="${fbEscape(item.id)}"><div class="feedback-grid three"><label>Name<input ${disabled} data-transition-name class="form-control" value="${fbEscape(item.name)}"></label><label>From<select ${disabled} data-transition-from class="form-control">${statusOptions(item.from_status)}</select></label><label>To<select ${disabled} data-transition-to class="form-control">${statusOptions(item.to_status)}</select></label></div><div class="feedback-grid three"><label>Approver<select ${disabled} data-transition-approver class="form-control"><option value="any_user">Any permitted user</option><option value="manager" ${item.approver_type === 'manager' ? 'selected' : ''}>Ticket manager</option><option value="user" ${item.approver_type === 'user' ? 'selected' : ''}>Specific user</option><option value="role" ${item.approver_type === 'role' ? 'selected' : ''}>Role</option><option value="feedback_admin" ${item.approver_type === 'feedback_admin' ? 'selected' : ''}>180 admin</option></select></label><label>User / role<input ${disabled} data-transition-value class="form-control" value="${fbEscape(item.approver_value || '')}"></label><label>Condition field<input ${disabled} data-transition-condition-key class="form-control" value="${fbEscape(item.condition_field || '')}"></label></div><div class="feedback-grid two"><label>Operator<select ${disabled} data-transition-condition-operator class="form-control"><option value="equals">equals</option><option value="not_equals" ${item.condition_operator === 'not_equals' ? 'selected' : ''}>not equals</option><option value="contains" ${item.condition_operator === 'contains' ? 'selected' : ''}>contains</option><option value="is_set" ${item.condition_operator === 'is_set' ? 'selected' : ''}>is set</option></select></label><label>Value<input ${disabled} data-transition-condition-value class="form-control" value="${fbEscape(item.condition_value || '')}"></label></div><button class="btn danger-soft" data-admin-only type="button" onclick="fbRemoveTransition(${index})">Remove</button></div>`).join('') || '<div class="feedback-empty">No transitions configured.</div>';
    fbSetAdminMode();
}

function fbAddTransition() { fbCollectProject(); const statuses = fbCurrent.workflow.statuses || []; fbCurrent.workflow.transitions = fbCurrent.workflow.transitions || []; fbCurrent.workflow.transitions.push({ id: `transition_${Date.now()}`, name: 'Approve', from_status: statuses[0]?.id || 'draft', to_status: statuses[1]?.id || 'ready', approver_type: 'manager' }); fbRenderTransitions(); }
function fbRemoveTransition(index) { fbCollectProject(); fbCurrent.workflow.transitions.splice(index, 1); fbRenderTransitions(); }

function fbRenderTicketForm() {
    const target = document.getElementById('fb-ticket-fields');
    if (!target) return;
    target.innerHTML = (fbCurrent.form_fields || []).map(field => {
        const options = (field.options || []).map(option => `<option value="${fbEscape(option)}">${fbEscape(option)}</option>`).join('');
        let input = `<input class="form-control" data-ticket-field="${fbEscape(field.key)}" type="${field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'}" placeholder="${fbEscape(field.placeholder || '')}">`;
        if (field.type === 'multi_line') input = `<textarea class="form-control" data-ticket-field="${fbEscape(field.key)}" rows="3"></textarea>`;
        if (field.type === 'single_select') input = `<select class="form-control" data-ticket-field="${fbEscape(field.key)}"><option value="">Select...</option>${options}</select>`;
        if (field.type === 'multi_select') input = `<select multiple class="form-control" data-ticket-field="${fbEscape(field.key)}">${options}</select>`;
        if (field.type === 'checkbox') input = `<input type="checkbox" data-ticket-field="${fbEscape(field.key)}">`;
        if (field.type === 'user_picker') input = `<input class="form-control" list="fb-user-options" data-ticket-field="${fbEscape(field.key)}" data-user-source="${fbEscape(field.user_source || 'database')}" oninput="fbSearchUsers(this.value, '${fbEscape(field.user_source || 'database')}')">`;
        return `<label data-ticket-field-wrap="${fbEscape(field.key)}">${fbEscape(field.label)}${field.required ? ' *' : ''}${input}<small>${fbEscape(field.help_text || '')}</small></label>`;
    }).join('');
}

async function fbSearchUsers(query, forcedSource = '') {
    const source = forcedSource || document.getElementById('fb-user-source')?.value || 'database';
    const res = await fetch(`/api/feedback/users?source=${encodeURIComponent(source)}&query=${encodeURIComponent(query || '')}`, { credentials: 'include' });
    const data = await res.json();
    document.getElementById('fb-user-options').innerHTML = (data.users || []).map(user => `<option value="${fbEscape(user.username)}">${fbEscape(user.label)} - ${fbEscape(user.email || '')}</option>`).join('');
}

async function fbCreateTicket() {
    if (!fbCurrent.id) return fbSetStatus('Save the process before creating tickets.', 'error');
    const values = {};
    document.querySelectorAll('[data-ticket-field]').forEach(input => { values[input.dataset.ticketField] = input.multiple ? Array.from(input.selectedOptions).map(o => o.value) : input.type === 'checkbox' ? input.checked : input.value; });
    const ticket = { title: document.getElementById('fb-ticket-title').value, description: document.getElementById('fb-ticket-description').value, description_html: document.getElementById('fb-ticket-html').value, assigned_to: document.getElementById('fb-ticket-assignee').value, manager_username: document.getElementById('fb-ticket-manager').value, field_values: values };
    const res = await fetch(`/api/feedback/projects/${encodeURIComponent(fbCurrent.id)}/tickets`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ticket }) });
    const data = await res.json();
    if (!data.success) return fbSetStatus(data.detail || data.error || 'Ticket creation failed.', 'error');
    fbCurrent.tickets = fbCurrent.tickets || []; fbCurrent.tickets.unshift(data.ticket); fbRenderTickets(); fbSetStatus('Ticket created.', 'success');
}

function fbRenderTickets() {
    const target = document.getElementById('fb-ticket-list');
    if (!target) return;
    target.innerHTML = (fbCurrent.tickets || []).map(ticket => {
        const transitions = (fbCurrent.workflow.transitions || []).filter(item => item.from_status === ticket.status);
        return `<article class="ticket-card"><div class="ticket-card-head"><div><strong>${fbEscape(ticket.title)}</strong><span>${fbEscape(ticket.id)} · ${fbEscape(ticket.status)}</span></div><span>${fbEscape(ticket.assigned_to || 'Unassigned')}</span></div><p>${fbEscape(ticket.description || '')}</p><div class="ticket-html">${ticket.description_html || ''}</div><div class="ticket-actions">${transitions.map(item => `<button class="btn" type="button" onclick="fbTransitionTicket('${fbEscape(ticket.id)}','${fbEscape(item.id)}')">${fbEscape(item.name)}</button>`).join('')}</div><div class="ticket-comments">${(ticket.comments || []).map(c => `<p><strong>${fbEscape(c.author)}</strong>: ${fbEscape(c.body || '')}</p>`).join('')}</div><div class="feedback-grid two"><input id="comment-${fbEscape(ticket.id)}" class="form-control" placeholder="Add a comment"><button class="btn" type="button" onclick="fbAddTicketComment('${fbEscape(ticket.id)}')">Comment</button></div></article>`;
    }).join('') || '<div class="feedback-empty">No tickets in this process.</div>';
}

async function fbAddTicketComment(ticketId) {
    const input = document.getElementById(`comment-${ticketId}`); const body = input?.value || '';
    const res = await fetch(`/api/feedback/projects/${encodeURIComponent(fbCurrent.id)}/tickets/${encodeURIComponent(ticketId)}/comments`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) });
    const data = await res.json(); if (!data.success) return fbSetStatus(data.detail || 'Comment failed.', 'error');
    const ticket = fbCurrent.tickets.find(item => item.id === ticketId); ticket.comments = ticket.comments || []; ticket.comments.push(data.comment); fbRenderTickets();
}

async function fbTransitionTicket(ticketId, transitionId) {
    const res = await fetch(`/api/feedback/projects/${encodeURIComponent(fbCurrent.id)}/tickets/${encodeURIComponent(ticketId)}/transition`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transition_id: transitionId }) });
    const data = await res.json(); if (!data.success) return fbSetStatus(data.detail || 'Transition failed.', 'error');
    const index = fbCurrent.tickets.findIndex(item => item.id === ticketId); fbCurrent.tickets[index] = data.ticket; fbRenderTickets(); fbSetStatus('Workflow transition completed.', 'success');
}

function fbRenderSetup() {
    document.getElementById('fb-title').value = fbCurrent.title || '';
    document.getElementById('fb-cycle').value = fbCurrent.cycle || '';
    document.getElementById('fb-description').value = fbCurrent.description || '';
    document.getElementById('fb-deadline').value = fbCurrent.workflow?.deadline_days || 14;
    document.getElementById('fb-scale').value = `${fbCurrent.workflow?.scale_min || 1}-${fbCurrent.workflow?.scale_max || 5}`;
    document.getElementById('fb-anonymous').checked = Boolean(fbCurrent.workflow?.anonymous);
}

function fbRenderProjectList() {
    const list = document.getElementById('fb-project-list');
    if (!list) return;
    const newButton = document.querySelector('.feedback-sidebar .btn-primary');
    if (newButton) newButton.style.display = fbPermissions.can_manage_workflow ? '' : 'none';
    if (!fbProjects.length) {
        list.innerHTML = '<div class="feedback-empty">No visible cycles yet.</div>';
        return;
    }
    list.innerHTML = fbProjects.map((project) => `<button type="button" class="feedback-project ${project.id === fbCurrent.id ? 'active' : ''}" onclick="fbOpenProject('${project.id}')"><strong>${fbEscape(project.title || 'Untitled cycle')}</strong><span>${fbEscape(project.status || 'draft')} - ${(project.participants?.subjects || []).length} subject(s)</span></button>`).join('');
}

function fbRenderWorkflowBoard() {
    const board = document.getElementById('fb-workflow-board');
    if (!board) return;
    const screens = fbCurrent.workflow.screens || [];
    board.innerHTML = FB_COLUMNS.map((column) => {
        const cards = (fbCurrent.workflow.statuses || []).filter((status) => (status.category || 'todo') === column.id);
        return `<section class="workflow-lane" data-lane="${column.id}" ondragover="fbAllowDrop(event)" ondrop="fbDropStatus(event, '${column.id}')"><div class="workflow-lane-title">${column.title}<span>${cards.length}</span></div>${cards.map((status) => fbWorkflowCard(status, screens)).join('')}</section>`;
    }).join('');
}

function fbWorkflowCard(status, screens) {
    const screenOptions = screens.map((screen) => `<option value="${fbEscape(screen.id)}" ${screen.id === status.screen_id ? 'selected' : ''}>${fbEscape(screen.name)}</option>`).join('');
    const draggable = fbPermissions.can_manage_workflow ? 'true' : 'false';
    const disabled = fbPermissions.can_manage_workflow ? '' : 'disabled';
    return `<article class="workflow-card" draggable="${draggable}" data-status-id="${fbEscape(status.id)}" ondragstart="fbDragStatus(event, '${fbEscape(status.id)}')"><div class="workflow-card-top"><strong>${fbEscape(status.name)}</strong><span>${fbEscape(status.id)}</span></div><textarea ${disabled} class="form-control" rows="2" onchange="fbUpdateStatus('${fbEscape(status.id)}', 'description', this.value)">${fbEscape(status.description || '')}</textarea><label>Screen<select ${disabled} class="form-control" onchange="fbUpdateStatus('${fbEscape(status.id)}', 'screen_id', this.value)">${screenOptions}</select></label><div class="workflow-card-actions" data-admin-only><button class="btn" type="button" onclick="fbRenameStatus('${fbEscape(status.id)}')">Rename</button><button class="btn danger-soft" type="button" onclick="fbRemoveStatus('${fbEscape(status.id)}')">Delete</button></div></article>`;
}

function fbDragStatus(event, statusId) {
    if (!fbPermissions.can_manage_workflow) return;
    fbDraggedStatusId = statusId;
    event.dataTransfer.effectAllowed = 'move';
}

function fbAllowDrop(event) {
    if (!fbPermissions.can_manage_workflow) return;
    event.preventDefault();
}

function fbDropStatus(event, category) {
    if (!fbPermissions.can_manage_workflow || !fbDraggedStatusId) return;
    event.preventDefault();
    const status = fbCurrent.workflow.statuses.find((item) => item.id === fbDraggedStatusId);
    if (status) status.category = category;
    fbDraggedStatusId = null;
    fbRenderWorkflowBoard();
    fbSetAdminMode();
}

function fbUpdateStatus(statusId, field, value) {
    const status = fbCurrent.workflow.statuses.find((item) => item.id === statusId);
    if (status && fbPermissions.can_manage_workflow) status[field] = value;
}

function fbRenameStatus(statusId) {
    const status = fbCurrent.workflow.statuses.find((item) => item.id === statusId);
    if (!status) return;
    const nextName = prompt('Status name', status.name);
    if (!nextName) return;
    status.name = nextName.trim();
    fbRenderWorkflowBoard();
    fbSetAdminMode();
}

function fbRemoveStatus(statusId) {
    if (!confirm('Delete this workflow status?')) return;
    fbCurrent.workflow.statuses = fbCurrent.workflow.statuses.filter((item) => item.id !== statusId);
    if (fbCurrent.status === statusId) fbCurrent.status = fbCurrent.workflow.statuses[0]?.id || 'draft';
    fbRenderWorkflowBoard();
    fbSetAdminMode();
}

function fbAddWorkflowStatus() {
    fbCollectProject();
    const name = prompt('New workflow status name', 'New status');
    if (!name) return;
    const id = `status_${Date.now()}`;
    fbCurrent.workflow.statuses.push({ id, name: name.trim(), category: 'todo', screen_id: fbCurrent.workflow.screens[0]?.id || 'screen_response', description: '' });
    fbRenderWorkflowBoard();
    fbSetAdminMode();
}

function fbRenderScreens() {
    const target = document.getElementById('fb-screen-builder');
    if (!target) return;
    const disabled = fbPermissions.can_manage_workflow ? '' : 'disabled';
    target.innerHTML = `<div class="screen-builder-head"><div><h3>Workflow screens</h3><p>Each status points to a screen. This makes the flow clear like Jira: status + screen + fields.</p></div><button class="btn" type="button" data-admin-only onclick="fbAddScreen()">+ Add screen</button></div>` + (fbCurrent.workflow.screens || []).map((screen) => `<div class="screen-card" data-fb-screen data-screen-id="${fbEscape(screen.id)}"><label>Screen name<input ${disabled} data-screen-name class="form-control" value="${fbEscape(screen.name)}"></label><label>Description<textarea ${disabled} data-screen-description class="form-control" rows="2">${fbEscape(screen.description || '')}</textarea></label><label>Fields, one per line<textarea ${disabled} data-screen-fields class="form-control" rows="3">${fbEscape((screen.fields || []).join('\n'))}</textarea></label><button class="btn danger-soft" type="button" data-admin-only onclick="fbRemoveScreen('${fbEscape(screen.id)}')">Remove screen</button></div>`).join('');
    fbSetAdminMode();
}

function fbAddScreen() {
    fbCollectProject();
    fbCurrent.workflow.screens.push({ id: `screen_${Date.now()}`, name: 'New screen', description: '', fields: ['questions', 'comment'] });
    fbRenderScreens();
    fbRenderWorkflowBoard();
}

function fbRemoveScreen(screenId) {
    if (!confirm('Delete this screen? Statuses using it will fall back to the first screen.')) return;
    fbCurrent.workflow.screens = fbCurrent.workflow.screens.filter((screen) => screen.id !== screenId);
    const fallback = fbCurrent.workflow.screens[0]?.id || 'screen_response';
    fbCurrent.workflow.statuses.forEach((status) => { if (status.screen_id === screenId) status.screen_id = fallback; });
    fbRenderScreens();
    fbRenderWorkflowBoard();
}

function fbRenderParticipants() {
    document.getElementById('fb-subjects').value = (fbCurrent.participants?.subjects || []).join('\n');
    document.getElementById('fb-reviewers').value = (fbCurrent.participants?.reviewers || []).join('\n');
    fbBuildMatrix(false);
}

function fbRenderQuestions() {
    const target = document.getElementById('fb-questions');
    const disabled = fbPermissions.can_manage_workflow ? '' : 'disabled';
    target.innerHTML = (fbCurrent.questions || []).map((question, index) => `<div class="question-row" data-fb-question data-question-id="${fbEscape(question.id || `q_${index + 1}`)}"><div class="question-index">Q${index + 1}</div><div class="question-fields"><div class="feedback-grid three"><label>Category<input ${disabled} data-question-category class="form-control" value="${fbEscape(question.category || 'General')}"></label><label>Type<select ${disabled} data-question-type class="form-control"><option value="rating" ${question.type === 'rating' ? 'selected' : ''}>Rating</option><option value="text" ${question.type === 'text' ? 'selected' : ''}>Text</option><option value="yes_no" ${question.type === 'yes_no' ? 'selected' : ''}>Yes / No</option></select></label><label class="feedback-toggle compact"><input ${disabled} data-question-required type="checkbox" ${question.required ? 'checked' : ''}> Required</label></div><label>Question<textarea ${disabled} data-question-text class="form-control" rows="2">${fbEscape(question.text || '')}</textarea></label></div><button class="btn danger-soft" type="button" data-admin-only onclick="fbRemoveQuestion(${index})">Remove</button></div>`).join('');
    fbSetAdminMode();
}

function fbRenderPreview() {
    const subjectSelect = document.getElementById('fb-response-subject');
    const reviewerSelect = document.getElementById('fb-response-reviewer');
    subjectSelect.innerHTML = (fbCurrent.participants.subjects || []).map((name) => `<option>${fbEscape(name)}</option>`).join('');
    reviewerSelect.innerHTML = (fbCurrent.participants.reviewers || []).map((name) => `<option>${fbEscape(name)}</option>`).join('');
    const min = fbCurrent.workflow.scale_min || 1;
    const max = fbCurrent.workflow.scale_max || 5;
    const preview = document.getElementById('fb-form-preview');
    preview.innerHTML = (fbCurrent.questions || []).map((question) => {
        if (question.type === 'text') return `<label>${fbEscape(question.text)}<textarea class="form-control" data-answer="${fbEscape(question.id)}" rows="2"></textarea></label>`;
        if (question.type === 'yes_no') return `<label>${fbEscape(question.text)}<select class="form-control" data-answer="${fbEscape(question.id)}"><option>Yes</option><option>No</option></select></label>`;
        return `<label>${fbEscape(question.text)}<input class="form-control" data-answer="${fbEscape(question.id)}" type="number" min="${min}" max="${max}" value="${max}"></label>`;
    }).join('') || '<div class="feedback-empty">No response screen is configured yet.</div>';
    fbRenderResponseSummary();
}

function fbRenderMetrics() {
    document.getElementById('fb-metric-subjects').textContent = (fbCurrent.participants.subjects || []).length;
    document.getElementById('fb-metric-reviewers').textContent = (fbCurrent.participants.reviewers || []).length;
    const currentStatus = (fbCurrent.workflow.statuses || []).find((status) => status.id === fbCurrent.status);
    document.getElementById('fb-metric-progress').textContent = currentStatus?.name || fbCurrent.status || 'Draft';
}

function fbRenderResponseSummary() {
    const target = document.getElementById('fb-response-summary');
    const responses = fbCurrent.responses || [];
    const ratings = [];
    responses.forEach((response) => Object.values(response.answers || {}).forEach((value) => { const numberValue = Number(value); if (!Number.isNaN(numberValue)) ratings.push(numberValue); }));
    const average = ratings.length ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1) : 'N/A';
    target.innerHTML = `<div class="metric"><span>${responses.length}</span><small>Responses</small></div><div class="metric"><span>${average}</span><small>Avg rating</small></div><div class="metric"><span>${fbCurrent.questions.length}</span><small>Questions</small></div>`;
}

function fbBuildMatrix(collect = true) {
    if (collect) fbCollectProject();
    const matrix = document.getElementById('fb-matrix');
    const subjects = fbCurrent.participants.subjects || [];
    const reviewers = fbCurrent.participants.reviewers || [];
    if (!subjects.length || !reviewers.length) {
        matrix.innerHTML = '<div class="feedback-empty">Add subjects and reviewers to build the assignment matrix.</div>';
        fbRenderMetrics();
        return;
    }
    matrix.innerHTML = subjects.map((subject) => `<div class="matrix-row"><strong>${fbEscape(subject)}</strong><span>${reviewers.map((reviewer) => `<em>${fbEscape(reviewer)}</em>`).join('')}</span></div>`).join('');
    fbRenderMetrics();
}

function fbAddQuestion() {
    fbCollectProject();
    fbCurrent.questions.push({ id: `q_${Date.now()}`, category: 'General', type: 'rating', required: true, text: 'New feedback question' });
    fbRenderQuestions();
    fbRenderPreview();
}

function fbRemoveQuestion(index) {
    fbCollectProject();
    fbCurrent.questions.splice(index, 1);
    fbRenderQuestions();
    fbRenderPreview();
}

function fbNewProject() {
    if (!fbPermissions.can_manage_workflow) return;
    fbCurrent = structuredCloneSafe(FB_DEFAULT_PROJECT);
    fbCurrent.id = '';
    fbRenderAll();
    fbSetStatus('New draft ready. Only 180 admins can save workflow changes.', 'info');
}

function fbOpenProject(id) {
    const project = fbProjects.find((item) => item.id === id);
    if (!project) return;
    fbCurrent = structuredCloneSafe(project);
    fbRenderAll();
}

async function fbLoadProjects() {
    try {
        const metaRes = await fetch('/api/feedback/meta', { credentials: 'include' });
        const meta = await metaRes.json();
        if (!meta.success) throw new Error(meta.detail || meta.error || 'Could not load module metadata');
        fbPermissions = meta.permissions || fbPermissions;
        if (meta.default_workflow) FB_DEFAULT_PROJECT.workflow = meta.default_workflow;

        const res = await fetch('/api/feedback/projects', { credentials: 'include' });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || data.error || 'Could not load projects');
        fbPermissions = data.permissions || fbPermissions;
        fbProjects = data.projects || [];
        fbCurrent = fbProjects[0] ? structuredCloneSafe(fbProjects[0]) : structuredCloneSafe(FB_DEFAULT_PROJECT);
        fbRenderAll();
    } catch (error) {
        fbSetStatus(error.message || 'Could not load feedback cycles.', 'error');
        fbRenderAll();
    }
}

async function fbSaveProject() {
    if (!fbPermissions.can_manage_workflow) return fbSetStatus('Only a 180 admin can configure workflow, screens, participants and questions.', 'error');
    if (fbSaving) return;
    fbCollectProject();
    if (!fbCurrent.questions.length) return fbSetStatus('Add at least one question before saving.', 'error');
    fbSaving = true;
    fbSetStatus('Saving 180 admin configuration...', 'info');
    try {
        const res = await fetch('/api/feedback/projects', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project: fbCurrent }) });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || data.error || 'Save failed');
        fbCurrent = data.project;
        const index = fbProjects.findIndex((item) => item.id === fbCurrent.id);
        if (index >= 0) fbProjects[index] = fbCurrent; else fbProjects.unshift(fbCurrent);
        fbRenderAll();
        fbSetStatus('Saved. Workflow board, screens and response form are now stored.', 'success');
    } catch (error) {
        fbSetStatus(error.message || 'Save failed.', 'error');
    } finally {
        fbSaving = false;
    }
}

async function fbSubmitDemoResponse() {
    const answers = {};
    document.querySelectorAll('[data-answer]').forEach((input) => { answers[input.dataset.answer] = input.value; });
    if (!fbCurrent.id) return fbSetStatus('Ask a 180 admin to save and launch a cycle before responses are submitted.', 'error');
    const response = { subject: document.getElementById('fb-response-subject')?.value || '', reviewer: document.getElementById('fb-response-reviewer')?.value || '', answers, comment: document.getElementById('fb-response-comment')?.value || '' };
    try {
        const res = await fetch(`/api/feedback/projects/${encodeURIComponent(fbCurrent.id)}/responses`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ response }) });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || data.error || 'Response failed');
        fbCurrent.responses = fbCurrent.responses || [];
        fbCurrent.responses.push({ ...response, submitted_at: new Date().toISOString() });
        fbRenderResponseSummary();
        fbSetStatus('Response submitted.', 'success');
    } catch (error) {
        fbSetStatus(error.message || 'Response failed.', 'error');
    }
}

function fbExportProject() {
    fbCollectProject();
    const blob = new Blob([JSON.stringify(fbCurrent, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${(fbCurrent.title || 'feedback-cycle').replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
}

['input', 'change'].forEach((eventName) => document.addEventListener(eventName, (event) => {
    if (event.target.closest('.feedback-main')) {
        fbCollectProject();
        fbRenderMetrics();
    }
}));

document.addEventListener('DOMContentLoaded', fbLoadProjects);
