const FB_DEFAULT_PROJECT = {
    id: '',
    title: '',
    cycle: '',
    description: '',
    status: '',
    workflow: {
        scale_min: 1,
        scale_max: 5,
        anonymous: false,
        deadline_days: 0,
        statuses: [],
        screens: [],
        transitions: []
    },
    participants: { subjects: [], reviewers: [], matrix: {} },
    questions: [],
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

// Jira-style UX Globals
let fbActiveTicketId = null;
let fbSelectedBoardProjectId = '';
let fbBoardFilter = 'all'; // 'all' | 'mine' | 'approvals'

// Visual Canvas Dragging
let fbCanvasDraggingNode = null;
let fbCanvasDragOffset = { x: 0, y: 0 };

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
    fbCurrent.workflow.statuses = Array.isArray(fbCurrent.workflow.statuses) ? fbCurrent.workflow.statuses : [];
    fbCurrent.workflow.screens = Array.isArray(fbCurrent.workflow.screens) ? fbCurrent.workflow.screens : [];
    fbCurrent.workflow.transitions = Array.isArray(fbCurrent.workflow.transitions) ? fbCurrent.workflow.transitions : [];
}

function fbCollectProject() {
    fbNormalizeWorkflow();
    const scale = (document.getElementById('fb-scale')?.value || '1-5').split('-').map(Number);
    if (fbPermissions.can_manage_workflow) {
        fbCurrent.title = document.getElementById('fb-title')?.value.trim() || 'Untitled form';
        fbCurrent.cycle = document.getElementById('fb-cycle')?.value.trim() || '';
        fbCurrent.description = document.getElementById('fb-description')?.value.trim() || '';
        fbCurrent.workflow.scale_min = scale[0] || 1;
        fbCurrent.workflow.scale_max = scale[1] || 5;
        fbCurrent.workflow.deadline_days = Number(document.getElementById('fb-deadline')?.value || 0);
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
        from_status: row.querySelector('[data-transition-from]')?.value || '',
        to_status: row.querySelector('[data-transition-to]')?.value || '',
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
    const adminHeadings = ['Application setup', 'Workflow builder', 'Participants', 'Assessment fields', 'Ticket form builder', 'Approvals and transitions'];
    document.querySelectorAll('.feedback-card').forEach(card => {
        const heading = card.querySelector('h2')?.textContent.trim();
        if (adminHeadings.includes(heading)) card.style.display = isAdmin ? '' : 'none';
    });
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
    fbRenderPerformanceOverview();
    fbRenderPublishedState();
    fbRenderProjectSelector();
}

function fbRenderPublishedState() {
    const hasProject = Boolean(fbCurrent.id);
    const hasAssessment = hasProject && (fbCurrent.questions || []).length > 0;
    const hasTicketForm = hasProject && (fbCurrent.form_fields || []).length > 0;
    const assessmentForm = document.getElementById('fb-assessment-form');
    const assessmentEmpty = document.getElementById('fb-assessment-empty');
    const ticketForm = document.getElementById('fb-ticket-create-form');
    const ticketEmpty = document.getElementById('fb-ticket-empty');
    if (assessmentForm) assessmentForm.style.display = hasAssessment ? '' : 'none';
    if (assessmentEmpty) assessmentEmpty.style.display = hasAssessment ? 'none' : 'block';
    if (ticketForm) ticketForm.style.display = hasTicketForm ? '' : 'none';
    if (ticketEmpty) ticketEmpty.style.display = hasTicketForm ? 'none' : 'block';
}

function fbShowView(view, updateUrl = true) {
    const isAdmin = fbPermissions.can_manage_workflow;
    const selected = ['assessments', 'performance', 'tickets', 'designer'].includes(view) ? view : 'assessments';
    document.querySelectorAll('[data-fb-view]').forEach(section => {
        section.style.display = section.dataset.fbView === selected ? '' : 'none';
    });
    const adminHeadings = ['Application setup', 'Workflow builder', 'Participants', 'Assessment fields', 'Ticket form builder', 'Approvals and transitions'];
    document.querySelectorAll('.feedback-card').forEach(card => {
        const heading = card.querySelector('h2')?.textContent.trim();
        if (adminHeadings.includes(heading)) card.style.display = isAdmin && selected === 'designer' ? '' : 'none';
    });
    document.querySelector('.feedback-sidebar').style.display = isAdmin && selected === 'designer' ? '' : 'none';
    document.querySelector('.feedback-shell').classList.toggle('single-view', !(isAdmin && selected === 'designer'));
    document.querySelectorAll('.feedback-view-nav button').forEach(button => {
        button.classList.toggle('active', button.getAttribute('onclick')?.includes(`'${selected}'`));
    });
    if (selected === 'tickets') {
        if (!fbSelectedBoardProjectId && fbCurrent.id) {
            fbSelectedBoardProjectId = fbCurrent.id;
        }
        fbRenderTickets();
    }
    if (updateUrl) {
        history.replaceState(null, '', `/feedback?view=${encodeURIComponent(selected)}`);
    }
    window.scrollTo({ top: 0, behavior: 'auto' });
}

function fbRenderPerformanceOverview() {
    const target = document.getElementById('fb-performance-overview');
    if (!target) return;
    target.innerHTML = (fbProjects || []).map(project => {
        const status = (project.workflow?.statuses || []).find(item => item.id === project.status)?.name || project.status || 'Draft';
        return `<button type="button" class="performance-card" onclick="fbOpenProject('${fbEscape(project.id)}'); fbShowView('assessments')"><span class="performance-status">${fbEscape(status)}</span><strong>${fbEscape(project.title || 'Performance cycle')}</strong><small>${(project.responses || []).length} response(s) · ${(project.questions || []).length} question(s)</small></button>`;
    }).join('') || '<div class="feedback-empty">No 180 performance cycle is assigned to you yet.</div>';
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

function fbAddFormField() { fbCollectProject(); fbCurrent.form_fields.push({ id: `field_${Date.now()}`, key: '', label: '', type: 'single_line', required: false, options: [], user_source: 'database' }); fbRenderFormFields(); fbRenderTicketForm(); }
function fbRemoveFormField(index) { fbCollectProject(); fbCurrent.form_fields.splice(index, 1); fbRenderFormFields(); fbRenderTicketForm(); }

async function fbImportSharedFields() {
    try {
        fbCollectProject();
        const response = await fetch('/api/processes/fields?module=feedback_180', { credentials: 'include' });
        const data = await response.json();
        if (!data.success) throw new Error(data.detail || 'Could not load shared fields');
        const existing = new Set((fbCurrent.form_fields || []).map(field => field.key));
        (data.fields || []).forEach(field => {
            if (existing.has(field.key)) return;
            fbCurrent.form_fields.push({
                id: field.id,
                key: field.key,
                label: field.label,
                type: field.type,
                required: Boolean(field.config?.required),
                placeholder: field.config?.placeholder || '',
                help_text: field.config?.help_text || '',
                options: field.config?.options || [],
                user_source: field.config?.user_source || 'database',
                condition_field: field.visibility?.condition?.field || '',
                condition_operator: field.visibility?.condition?.operator || 'equals',
                condition_value: field.visibility?.condition?.value || '',
                shared_definition_id: field.id
            });
        });
        fbRenderFormFields();
        fbRenderTicketForm();
        fbSetStatus(`${data.fields.length} shared field definition(s) loaded. Save the cycle to apply them.`, 'success');
    } catch (error) {
        fbSetStatus(error.message || 'Shared field import failed.', 'error');
    }
}

function fbRenderTransitions() {
    const target = document.getElementById('fb-transitions');
    if (!target) return;
    const disabled = fbPermissions.can_manage_workflow ? '' : 'disabled';
    const statuses = fbCurrent.workflow.statuses || [];
    const statusOptions = (selected) => statuses.map(status => `<option value="${fbEscape(status.id)}" ${status.id === selected ? 'selected' : ''}>${fbEscape(status.name)}</option>`).join('');
    target.innerHTML = (fbCurrent.workflow.transitions || []).map((item, index) => `<div class="process-builder-row" data-fb-transition data-transition-id="${fbEscape(item.id)}"><div class="feedback-grid three"><label>Name<input ${disabled} data-transition-name class="form-control" value="${fbEscape(item.name)}"></label><label>From<select ${disabled} data-transition-from class="form-control">${statusOptions(item.from_status)}</select></label><label>To<select ${disabled} data-transition-to class="form-control">${statusOptions(item.to_status)}</select></label></div><div class="feedback-grid three"><label>Approver<select ${disabled} data-transition-approver class="form-control"><option value="any_user">Any permitted user</option><option value="manager" ${item.approver_type === 'manager' ? 'selected' : ''}>Ticket manager</option><option value="user" ${item.approver_type === 'user' ? 'selected' : ''}>Specific user</option><option value="role" ${item.approver_type === 'role' ? 'selected' : ''}>Role</option><option value="feedback_admin" ${item.approver_type === 'feedback_admin' ? 'selected' : ''}>180 admin</option></select></label><label>User / role<input ${disabled} data-transition-value class="form-control" value="${fbEscape(item.approver_value || '')}"></label><label>Condition field<input ${disabled} data-transition-condition-key class="form-control" value="${fbEscape(item.condition_field || '')}"></label></div><div class="feedback-grid two"><label>Operator<select ${disabled} data-transition-condition-operator class="form-control"><option value="equals">equals</option><option value="not_equals" ${item.condition_operator === 'not_equals' ? 'selected' : ''}>not equals</option><option value="contains" ${item.condition_operator === 'contains' ? 'selected' : ''}>contains</option><option value="is_set" ${item.condition_operator === 'is_set' ? 'selected' : ''}>is set</option></select></label><label>Value<input ${disabled} data-transition-condition-value class="form-control" value="${fbEscape(item.condition_value || '')}"></label></div><button class="btn danger-soft" data-admin-only type="button" onclick="fbRemoveTransition(${index})">Remove</button></div>`).join('') || '<div class="feedback-empty">No transitions configured.</div>';
    fbSetAdminMode();
}

function fbAddTransition() {
    fbCollectProject();
    const statuses = fbCurrent.workflow.statuses || [];
    if (statuses.length < 2) return fbSetStatus('Create at least two statuses before adding a transition.', 'error');
    fbCurrent.workflow.transitions = fbCurrent.workflow.transitions || [];
    fbCurrent.workflow.transitions.push({ id: `transition_${Date.now()}`, name: 'New transition', from_status: statuses[0].id, to_status: statuses[1].id, approver_type: 'any_user' });
    fbRenderTransitions();
}
function fbRemoveTransition(index) { fbCollectProject(); fbCurrent.workflow.transitions.splice(index, 1); fbRenderTransitions(); }

function fbRenderTicketForm() {
    const target = document.getElementById('fb-ticket-fields');
    if (!target) return;
    
    // Find fields to show on the initial status screen
    let fieldsToShow = fbCurrent.form_fields || [];
    const initialStatus = fbCurrent.workflow?.statuses?.[0];
    if (initialStatus && initialStatus.screen_id) {
        const screen = fbCurrent.workflow.screens.find(s => s.id === initialStatus.screen_id);
        if (screen && screen.fields && screen.fields.length) {
            fieldsToShow = fbCurrent.form_fields.filter(field => 
                screen.fields.includes(field.key) || screen.fields.includes(field.id)
            );
        }
    }
    
    target.innerHTML = fieldsToShow.map(field => {
        const options = (field.options || []).map(option => `<option value="${fbEscape(option)}">${fbEscape(option)}</option>`).join('');
        let input = `<input class="form-control" data-ticket-field="${fbEscape(field.key)}" type="${field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'}" placeholder="${fbEscape(field.placeholder || '')}">`;
        if (field.type === 'multi_line') input = `<textarea class="form-control" data-ticket-field="${fbEscape(field.key)}" rows="3"></textarea>`;
        if (field.type === 'single_select') input = `<select class="form-control" data-ticket-field="${fbEscape(field.key)}"><option value="">Select...</option>${options}</select>`;
        if (field.type === 'multi_select') input = `<select multiple class="form-control" data-ticket-field="${fbEscape(field.key)}">${options}</select>`;
        if (field.type === 'checkbox') input = `<input type="checkbox" data-ticket-field="${fbEscape(field.key)}">`;
        if (field.type === 'single_user_picker' || field.type === 'user_picker' || field.type === 'multi_user_picker') {
            input = `<div id="fb-picker-field-${fbEscape(field.key)}" class="user-picker-wrapper"></div>`;
        }
        return `<label data-ticket-field-wrap="${fbEscape(field.key)}" style="display: block; margin-bottom: 12px; font-weight: 700;">${fbEscape(field.label)}${field.required ? ' *' : ''}${input}<small style="display: block; margin-top: 4px; font-weight: 400; color: var(--text-secondary);">${fbEscape(field.help_text || '')}</small></label>`;
    }).join('');
    
    // Now instantiate user pickers for fields that require them
    fieldsToShow.forEach(field => {
        if (field.type === 'single_user_picker' || field.type === 'user_picker' || field.type === 'multi_user_picker') {
            const container = document.getElementById(`fb-picker-field-${field.key}`);
            if (container) {
                fbRenderUserPicker(container, field, field.type === 'multi_user_picker' ? [] : '', true);
            }
        }
    });

    // Instantiate assignee & manager pickers in create form
    const source = document.getElementById('fb-user-source')?.value || 'database';
    const assigneeContainer = document.getElementById('fb-ticket-assignee-picker-container');
    if (assigneeContainer) {
        fbRenderUserPicker(assigneeContainer, { key: 'assigned_to', type: 'single_user_picker', user_source: source }, '', true);
    }
    const managerContainer = document.getElementById('fb-ticket-manager-picker-container');
    if (managerContainer) {
        fbRenderUserPicker(managerContainer, { key: 'manager_username', type: 'single_user_picker', user_source: source }, '', true);
    }
}

async function fbSearchUsers(query, forcedSource = '') {
    const source = forcedSource || document.getElementById('fb-user-source')?.value || 'database';
    const res = await fetch(`/api/feedback/users?source=${encodeURIComponent(source)}&query=${encodeURIComponent(query || '')}`, { credentials: 'include' });
    const data = await res.json();
    document.getElementById('fb-user-options').innerHTML = (data.users || []).map(user => `<option value="${fbEscape(user.username)}">${fbEscape(user.label)} - ${fbEscape(user.email || '')}</option>`).join('');
}

// Autocomplete user picker rendering
function fbRenderUserPicker(container, field, selectedValues, isEditable, onUpdate = null) {
    container.innerHTML = '';
    container.fbSelectedValues = selectedValues;
    container.dataset.fieldKey = field.key;
    
    const isMulti = field.type === 'multi_user_picker';
    
    const pillsWrap = document.createElement('div');
    pillsWrap.className = 'user-picker-pills';
    container.appendChild(pillsWrap);
    
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control user-picker-input';
    input.placeholder = isEditable ? 'Search user...' : '';
    input.disabled = !isEditable;
    
    const dropdown = document.createElement('div');
    dropdown.className = 'user-autocomplete-list d-none';
    
    const updatePills = () => {
        pillsWrap.innerHTML = '';
        const vals = Array.isArray(container.fbSelectedValues) 
            ? container.fbSelectedValues 
            : (container.fbSelectedValues ? [container.fbSelectedValues] : []);
            
        vals.forEach(val => {
            if (!val) return;
            const pill = document.createElement('span');
            pill.className = 'user-pill';
            pill.textContent = val;
            
            if (isEditable) {
                const removeBtn = document.createElement('span');
                removeBtn.className = 'user-pill-remove';
                removeBtn.innerHTML = '&times;';
                removeBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (isMulti) {
                        container.fbSelectedValues = container.fbSelectedValues.filter(v => v !== val);
                    } else {
                        container.fbSelectedValues = '';
                        input.style.display = '';
                    }
                    updatePills();
                    if (onUpdate) onUpdate(container.fbSelectedValues);
                };
                pill.appendChild(removeBtn);
            }
            pillsWrap.appendChild(pill);
        });
        
        if (!isMulti && vals.length > 0) {
            input.style.display = 'none';
        } else {
            input.style.display = '';
        }
    };
    
    if (isEditable) {
        const inputWrap = document.createElement('div');
        inputWrap.style.position = 'relative';
        inputWrap.style.width = '100%';
        inputWrap.className = 'user-picker-box';
        
        inputWrap.appendChild(pillsWrap);
        inputWrap.appendChild(input);
        inputWrap.appendChild(dropdown);
        container.appendChild(inputWrap);
        
        let searchTimeout;
        input.oninput = () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                fbSearchUsersForPicker(input, dropdown, field.user_source || 'database', (selectedUser) => {
                    if (isMulti) {
                        if (!Array.isArray(container.fbSelectedValues)) container.fbSelectedValues = [];
                        if (!container.fbSelectedValues.includes(selectedUser)) {
                            container.fbSelectedValues.push(selectedUser);
                        }
                    } else {
                        container.fbSelectedValues = selectedUser;
                    }
                    input.value = '';
                    dropdown.classList.add('d-none');
                    updatePills();
                    if (onUpdate) onUpdate(container.fbSelectedValues);
                });
            }, 200);
        };
        
        // Hide dropdown on blur
        const hideHandler = (e) => {
            if (!container.contains(e.target)) {
                dropdown.classList.add('d-none');
            }
        };
        document.addEventListener('click', hideHandler);
        container._blurHandler = hideHandler; // Store reference to clean up if re-rendered
    } else {
        container.appendChild(pillsWrap);
        if (pillsWrap.children.length === 0) {
            pillsWrap.innerHTML = '<span class="text-muted" style="font-size:0.85rem; font-weight:400;">Unassigned</span>';
        }
    }
    
    updatePills();
}

async function fbSearchUsersForPicker(input, dropdown, source, onSelect) {
    const query = input.value.trim();
    if (!query) {
        dropdown.innerHTML = '';
        dropdown.classList.add('d-none');
        return;
    }
    const res = await fetch(`/api/feedback/users?source=${encodeURIComponent(source)}&query=${encodeURIComponent(query)}`, { credentials: 'include' });
    const data = await res.json();
    if (!data.success || !data.users || data.users.length === 0) {
        dropdown.innerHTML = '<div class="user-autocomplete-item text-muted">No users found</div>';
        dropdown.classList.remove('d-none');
        return;
    }
    
    dropdown.innerHTML = data.users.map(user => `
        <div class="user-autocomplete-item" data-username="${fbEscape(user.username)}">
            <strong>${fbEscape(user.label)}</strong> <span style="font-size:0.75rem; color:var(--text-secondary);">(${fbEscape(user.username)})</span>
        </div>
    `).join('');
    
    dropdown.querySelectorAll('.user-autocomplete-item').forEach(item => {
        item.onclick = () => {
            const username = item.dataset.username;
            onSelect(username);
        };
    });
    dropdown.classList.remove('d-none');
}

// Create and Close Modal controls
function fbOpenCreateTicketModal() {
    const modal = document.getElementById('fb-create-ticket-modal');
    if (modal) modal.style.display = 'flex';
    fbRenderTicketForm();
}

function fbCloseCreateTicketModal() {
    const modal = document.getElementById('fb-create-ticket-modal');
    if (modal) modal.style.display = 'none';
}

// Board controls
function fbRenderProjectSelector() {
    const select = document.getElementById('fb-board-project-select');
    if (!select) return;
    select.innerHTML = fbProjects.map(project => `
        <option value="${fbEscape(project.id)}" ${project.id === fbSelectedBoardProjectId ? 'selected' : ''}>
            ${fbEscape(project.title || 'Untitled Project')}
        </option>
    `).join('');
}

function fbSwitchTicketProject(projectId) {
    fbSelectedBoardProjectId = projectId;
    fbRenderTickets();
}

function fbSetBoardFilter(filter) {
    fbBoardFilter = filter;
    ['all', 'mine', 'approvals'].forEach(f => {
        const btn = document.getElementById(`fb-filter-${f}`);
        if (btn) btn.classList.toggle('active', f === filter);
    });
    fbRenderTickets();
}

// Drag & drop ticket board
let fbDraggedTicketId = null;
let fbDraggedTicketFromStatusId = null;

function fbTicketDragStart(event, ticketId, fromStatusId) {
    fbDraggedTicketId = ticketId;
    fbDraggedTicketFromStatusId = fromStatusId;
    event.dataTransfer.effectAllowed = 'move';
}

function fbTicketAllowDrop(event) {
    event.preventDefault();
}

async function fbTicketDrop(event, toStatusId) {
    event.preventDefault();
    document.querySelectorAll('.ticket-lane').forEach(lane => lane.classList.remove('dragover'));
    
    const ticketId = fbDraggedTicketId;
    const fromStatusId = fbDraggedTicketFromStatusId;
    
    fbDraggedTicketId = null;
    fbDraggedTicketFromStatusId = null;
    
    if (!ticketId || fromStatusId === toStatusId) return;
    
    const project = fbProjects.find(p => p.id === fbSelectedBoardProjectId) || fbCurrent;
    const transitions = project.workflow?.transitions || [];
    const transition = transitions.find(t => t.from_status === fromStatusId && t.to_status === toStatusId);
    
    if (!transition) {
        alert(`No valid transition defined from status "${fromStatusId}" to "${toStatusId}".`);
        return;
    }
    
    fbSetStatus(`Transitioning ticket ${ticketId}...`, 'info');
    try {
        const res = await fetch(`/api/feedback/projects/${encodeURIComponent(project.id)}/tickets/${encodeURIComponent(ticketId)}/transition`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transition_id: transition.id })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || 'Transition failed');
        
        const index = project.tickets.findIndex(t => t.id === ticketId);
        if (index >= 0) project.tickets[index] = data.ticket;
        
        fbRenderTickets();
        fbSetStatus('Workflow transition completed.', 'success');
        
        if (fbActiveTicketId === ticketId) {
            fbOpenTicketDrawer(ticketId);
        }
    } catch (error) {
        fbSetStatus(error.message || 'Transition failed.', 'error');
        alert(`Transition failed: ${error.message}`);
    }
}

async function fbCreateTicket() {
    if (!fbCurrent.id) return fbSetStatus('Save the process before creating tickets.', 'error');
    
    const values = {};
    document.querySelectorAll('[data-ticket-field]').forEach(input => {
        values[input.dataset.ticketField] = input.multiple ? Array.from(input.selectedOptions).map(o => o.value) : input.type === 'checkbox' ? input.checked : input.value;
    });
    
    document.querySelectorAll('#fb-ticket-fields .user-picker-wrapper').forEach(wrapper => {
        const key = wrapper.dataset.fieldKey;
        if (key) {
            values[key] = wrapper.fbSelectedValues;
        }
    });
    
    const assigneeContainer = document.getElementById('fb-ticket-assignee-picker-container');
    const managerContainer = document.getElementById('fb-ticket-manager-picker-container');
    const assigned_to = assigneeContainer ? (assigneeContainer.fbSelectedValues || '') : '';
    const manager_username = managerContainer ? (managerContainer.fbSelectedValues || '') : '';
    
    const titleVal = document.getElementById('fb-ticket-title').value.trim();
    if (!titleVal) {
        alert('Ticket Title is required');
        return;
    }
    
    const ticket = {
        title: titleVal,
        description: document.getElementById('fb-ticket-description').value,
        description_html: document.getElementById('fb-ticket-html').value,
        assigned_to: assigned_to,
        manager_username: manager_username,
        field_values: values
    };
    
    fbSetStatus('Creating ticket...', 'info');
    try {
        const res = await fetch(`/api/feedback/projects/${encodeURIComponent(fbCurrent.id)}/tickets`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || data.error || 'Ticket creation failed');
        
        fbCurrent.tickets = fbCurrent.tickets || [];
        fbCurrent.tickets.unshift(data.ticket);
        
        const projIdx = fbProjects.findIndex(p => p.id === fbCurrent.id);
        if (projIdx >= 0) fbProjects[projIdx] = fbCurrent;
        
        fbCloseCreateTicketModal();
        fbRenderTickets();
        fbSetStatus('Ticket created.', 'success');
    } catch (error) {
        fbSetStatus(error.message || 'Ticket creation failed.', 'error');
        alert(`Ticket creation failed: ${error.message}`);
    }
}

function fbRenderTickets() {
    const target = document.getElementById('fb-ticket-list');
    if (!target) return;
    
    const project = fbProjects.find(p => p.id === fbSelectedBoardProjectId) || fbCurrent;
    if (!project || !project.id) {
        target.innerHTML = '<div class="feedback-empty">No active project selected.</div>';
        return;
    }
    
    const statuses = (project.workflow && project.workflow.statuses && project.workflow.statuses.length)
        ? project.workflow.statuses
        : [
            { id: 'todo', name: 'To do', category: 'todo' },
            { id: 'doing', name: 'In progress', category: 'doing' },
            { id: 'done', name: 'Done', category: 'done' }
          ];
          
    const currentUsername = document.querySelector('.sidebar-user div')?.textContent.trim() || '';
    
    let tickets = project.tickets || [];
    if (fbBoardFilter === 'mine') {
        tickets = tickets.filter(t => t.assigned_to === currentUsername || t.created_by === currentUsername);
    } else if (fbBoardFilter === 'approvals') {
        tickets = tickets.filter(t => t.manager_username === currentUsername);
    }
    
    target.innerHTML = statuses.map(status => {
        const statusTickets = tickets.filter(t => t.status === status.id || (status.id === 'todo' && !t.status));
        const cardsHtml = statusTickets.map(ticket => `
            <div class="ticket-card" draggable="true" 
                 ondragstart="fbTicketDragStart(event, '${fbEscape(ticket.id)}', '${fbEscape(status.id)}')" 
                 onclick="fbOpenTicketDrawer('${fbEscape(ticket.id)}')">
                <div class="ticket-card-title">${fbEscape(ticket.title)}</div>
                <div class="ticket-card-footer">
                    <span class="ticket-card-key">${fbEscape(ticket.id)}</span>
                    <span class="ticket-card-assignee">${fbEscape(ticket.assigned_to || 'Unassigned')}</span>
                </div>
            </div>
        `).join('');
        
        return `
            <div class="ticket-lane" 
                 ondragover="fbTicketAllowDrop(event)" 
                 ondragenter="this.classList.add('dragover')"
                 ondragleave="this.classList.remove('dragover')"
                 ondrop="fbTicketDrop(event, '${fbEscape(status.id)}')">
                <div class="ticket-lane-header">
                    <span>${fbEscape(status.name)}</span>
                    <span class="ticket-lane-count">${statusTickets.length}</span>
                </div>
                <div class="ticket-cards-container">
                    ${cardsHtml || '<div class="text-muted text-center" style="font-size:0.82rem; padding:24px 0; color:var(--text-secondary);">No tickets</div>'}
                </div>
            </div>
        `;
    }).join('');
}

// Drawer comment, transitions and update operations
async function fbSubmitDrawerComment() {
    const textarea = document.getElementById('fb-drawer-new-comment');
    const body = textarea ? textarea.value.trim() : '';
    if (!body) return;
    
    const project = fbProjects.find(p => p.id === fbSelectedBoardProjectId) || fbCurrent;
    const ticketId = fbActiveTicketId;
    if (!project || !ticketId) return;
    
    fbSetStatus('Adding comment...', 'info');
    try {
        const res = await fetch(`/api/feedback/projects/${encodeURIComponent(project.id)}/tickets/${encodeURIComponent(ticketId)}/comments`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ body })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || 'Comment failed');
        
        const ticket = project.tickets.find(t => t.id === ticketId);
        ticket.comments = ticket.comments || [];
        ticket.comments.push(data.comment);
        
        if (textarea) textarea.value = '';
        fbRenderTickets();
        fbOpenTicketDrawer(ticketId);
        fbSetStatus('Comment added.', 'success');
    } catch (e) {
        fbSetStatus(e.message || 'Comment failed', 'error');
    }
}

async function fbRunDrawerTransition(transitionId) {
    const project = fbProjects.find(p => p.id === fbSelectedBoardProjectId) || fbCurrent;
    const ticketId = fbActiveTicketId;
    if (!project || !ticketId) return;
    
    fbSetStatus('Executing transition...', 'info');
    try {
        const res = await fetch(`/api/feedback/projects/${encodeURIComponent(project.id)}/tickets/${encodeURIComponent(ticketId)}/transition`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transition_id: transitionId })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || 'Transition failed');
        
        const idx = project.tickets.findIndex(t => t.id === ticketId);
        if (idx >= 0) project.tickets[idx] = data.ticket;
        
        fbRenderTickets();
        fbOpenTicketDrawer(ticketId);
        fbSetStatus('Workflow transition completed.', 'success');
    } catch (e) {
        fbSetStatus(e.message || 'Transition failed.', 'error');
        alert(`Transition failed: ${e.message}`);
    }
}

async function fbUpdateTicketField(key, value) {
    const project = fbProjects.find(p => p.id === fbSelectedBoardProjectId) || fbCurrent;
    const ticketId = fbActiveTicketId;
    if (!project || !ticketId) return;
    
    const ticket = project.tickets.find(t => t.id === ticketId);
    if (!ticket) return;
    
    ticket.field_values = ticket.field_values || {};
    ticket.field_values[key] = value;
    
    const payload = {
        ticket: {
            field_values: {
                [key]: value
            }
        }
    };
    
    try {
        const res = await fetch(`/api/feedback/projects/${encodeURIComponent(project.id)}/tickets/${encodeURIComponent(ticketId)}/update`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || 'Update failed');
        
        const idx = project.tickets.findIndex(t => t.id === ticketId);
        if (idx >= 0) project.tickets[idx] = data.ticket;
        fbRenderTickets();
    } catch (e) {
        fbSetStatus(`Field update failed: ${e.message}`, 'error');
    }
}

async function fbUpdateDrawerProperty(property, value) {
    const project = fbProjects.find(p => p.id === fbSelectedBoardProjectId) || fbCurrent;
    const ticketId = fbActiveTicketId;
    if (!project || !ticketId) return;
    
    const ticket = project.tickets.find(t => t.id === ticketId);
    if (!ticket) return;
    
    ticket[property] = value;
    const payload = {
        ticket: {
            [property]: value
        }
    };
    
    try {
        const res = await fetch(`/api/feedback/projects/${encodeURIComponent(project.id)}/tickets/${encodeURIComponent(ticketId)}/update`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || 'Update failed');
        
        const idx = project.tickets.findIndex(t => t.id === ticketId);
        if (idx >= 0) project.tickets[idx] = data.ticket;
        fbRenderTickets();
    } catch (e) {
        fbSetStatus(`Property update failed: ${e.message}`, 'error');
    }
}

function fbRenderDrawerCustomField(field, value, isEditable) {
    const wrapper = document.createElement('div');
    wrapper.style.display = 'flex';
    wrapper.style.flexDirection = 'column';
    wrapper.style.gap = '4px';
    wrapper.style.marginBottom = '12px';
    
    const label = document.createElement('span');
    label.style.fontSize = '0.78rem';
    label.style.color = 'var(--text-secondary)';
    label.style.fontWeight = '700';
    label.style.textTransform = 'uppercase';
    label.style.letterSpacing = '0.05em';
    label.textContent = field.label;
    wrapper.appendChild(label);
    
    if (field.type === 'single_user_picker' || field.type === 'user_picker' || field.type === 'multi_user_picker') {
        const container = document.createElement('div');
        container.className = 'user-picker-wrapper';
        wrapper.appendChild(container);
        fbRenderUserPicker(container, field, value, isEditable, (newVal) => {
            fbUpdateTicketField(field.key, newVal);
        });
    } else {
        if (isEditable) {
            let input;
            if (field.type === 'multi_line') {
                input = document.createElement('textarea');
                input.className = 'form-control';
                input.rows = 2;
                input.value = value || '';
                input.onchange = () => fbUpdateTicketField(field.key, input.value);
            } else if (field.type === 'single_select') {
                input = document.createElement('select');
                input.className = 'form-control';
                input.innerHTML = `<option value="">Select...</option>` + (field.options || []).map(o => `
                    <option value="${fbEscape(o)}" ${o === value ? 'selected' : ''}>${fbEscape(o)}</option>
                `).join('');
                input.onchange = () => fbUpdateTicketField(field.key, input.value);
            } else if (field.type === 'checkbox') {
                input = document.createElement('input');
                input.type = 'checkbox';
                input.checked = Boolean(value);
                input.onchange = () => fbUpdateTicketField(field.key, input.checked);
            } else {
                input = document.createElement('input');
                input.type = field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text';
                input.className = 'form-control';
                input.value = value || '';
                input.onchange = () => fbUpdateTicketField(field.key, input.value);
            }
            wrapper.appendChild(input);
        } else {
            const display = document.createElement('div');
            display.style.fontSize = '0.95rem';
            display.style.color = 'var(--text-primary)';
            display.style.padding = '4px 0';
            display.textContent = value !== undefined && value !== null ? String(value) : 'None';
            wrapper.appendChild(display);
        }
    }
    
    return wrapper;
}

function fbOpenTicketDrawer(ticketId) {
    fbActiveTicketId = ticketId;
    const project = fbProjects.find(p => p.id === fbSelectedBoardProjectId) || fbCurrent;
    const ticket = project.tickets.find(t => t.id === ticketId);
    if (!ticket) return;
    
    document.getElementById('fb-drawer-ticket-id').textContent = ticket.id;
    document.getElementById('fb-drawer-title').textContent = ticket.title;
    document.getElementById('fb-drawer-description').textContent = ticket.description || 'No description';
    
    const htmlWrap = document.getElementById('fb-drawer-html-wrap');
    const htmlContent = document.getElementById('fb-drawer-html');
    if (ticket.description_html) {
        htmlWrap.style.display = 'flex';
        htmlContent.innerHTML = ticket.description_html;
    } else {
        htmlWrap.style.display = 'none';
    }
    
    document.getElementById('fb-drawer-reporter').textContent = ticket.created_by;
    document.getElementById('fb-drawer-created').textContent = new Date(ticket.created_at).toLocaleString();
    
    const statusObj = (project.workflow?.statuses || []).find(s => s.id === ticket.status);
    const statusName = statusObj ? statusObj.name : ticket.status;
    const badge = document.getElementById('fb-drawer-status-badge');
    badge.textContent = statusName;
    
    const currentUsername = document.querySelector('.sidebar-user div')?.textContent.trim() || '';
    const isEditable = fbPermissions.can_manage_workflow ||
                       ticket.created_by === currentUsername ||
                       ticket.assigned_to === currentUsername ||
                       ticket.manager_username === currentUsername;
                       
    const assigneeContainer = document.getElementById('fb-drawer-assignee-container');
    fbRenderUserPicker(assigneeContainer, { key: 'assigned_to', type: 'single_user_picker', user_source: 'database' }, ticket.assigned_to, isEditable, (val) => {
        fbUpdateDrawerProperty('assigned_to', val);
    });
    
    const managerContainer = document.getElementById('fb-drawer-manager-container');
    fbRenderUserPicker(managerContainer, { key: 'manager_username', type: 'single_user_picker', user_source: 'database' }, ticket.manager_username, isEditable, (val) => {
        fbUpdateDrawerProperty('manager_username', val);
    });
    
    const transContainer = document.getElementById('fb-drawer-transitions-container');
    const transitions = (project.workflow?.transitions || []).filter(t => t.from_status === ticket.status);
    transContainer.innerHTML = transitions.map(t => `
        <button class="btn btn-sm" type="button" style="width: 100%; text-align: left;" onclick="fbRunDrawerTransition('${fbEscape(t.id)}')">
            &rarr; ${fbEscape(t.name)}
        </button>
    `).join('') || '<span class="text-muted" style="font-size: 0.8rem;">No transitions available</span>';
    
    const commentsContainer = document.getElementById('fb-drawer-comments');
    commentsContainer.innerHTML = (ticket.comments || []).map(c => `
        <div class="comment-card" style="background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:8px; padding:10px; margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-secondary); margin-bottom:4px; font-weight:700;">
                <span>${fbEscape(c.author)}</span>
                <span>${new Date(c.created_at).toLocaleString()}</span>
            </div>
            <div style="font-size:0.9rem; color:var(--text-primary); white-space:pre-wrap;">${fbEscape(c.body)}</div>
        </div>
    `).join('') || '<div class="text-muted" style="font-size:0.85rem;">No comments yet.</div>';
    
    const fieldsContainer = document.getElementById('fb-drawer-fields-container');
    fieldsContainer.innerHTML = '';
    
    let fieldsToShow = project.form_fields || [];
    if (statusObj && statusObj.screen_id) {
        const screen = project.workflow?.screens?.find(s => s.id === statusObj.screen_id);
        if (screen && screen.fields && screen.fields.length) {
            fieldsToShow = project.form_fields.filter(field => 
                screen.fields.includes(field.key) || screen.fields.includes(field.id)
            );
        }
    }
    
    if (fieldsToShow.length === 0) {
        fieldsContainer.innerHTML = '<span class="text-muted" style="font-size: 0.85rem;">No custom fields shown in this status.</span>';
    } else {
        fieldsToShow.forEach(field => {
            const val = ticket.field_values ? ticket.field_values[field.key] : undefined;
            const fieldEl = fbRenderDrawerCustomField(field, val, isEditable);
            fieldsContainer.appendChild(fieldEl);
        });
    }
    
    const drawer = document.getElementById('fb-ticket-drawer');
    drawer.style.display = 'flex';
}

function fbCloseTicketDrawer() {
    fbActiveTicketId = null;
    document.getElementById('fb-ticket-drawer').style.display = 'none';
}

function fbRenderSetup() {
    document.getElementById('fb-title').value = fbCurrent.title || '';
    document.getElementById('fb-cycle').value = fbCurrent.cycle || '';
    document.getElementById('fb-description').value = fbCurrent.description || '';
    document.getElementById('fb-deadline').value = fbCurrent.workflow?.deadline_days || '';
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
    list.innerHTML = fbProjects.map((project) => `<button type="button" class="feedback-project ${project.id === fbCurrent.id ? 'active' : ''}" onclick="fbOpenProject('${project.id}')"><strong>${fbEscape(project.title || 'Untitled application')}</strong><span>${fbEscape(project.status || 'No status')} · ${(project.form_fields || []).length} ticket field(s) · ${(project.questions || []).length} assessment field(s)</span></button>`).join('');
}

function fbInitCanvasDragging() {
    const nodesContainer = document.getElementById('fb-workflow-nodes');
    if (!nodesContainer) return;
    
    nodesContainer.addEventListener('mousemove', (e) => {
        if (!fbCanvasDraggingNode) return;
        const container = document.getElementById('fb-workflow-canvas-container');
        const containerRect = container.getBoundingClientRect();
        
        let newX = e.clientX - containerRect.left - fbCanvasDragOffset.x;
        let newY = e.clientY - containerRect.top - fbCanvasDragOffset.y;
        
        // Boundaries
        newX = Math.max(10, Math.min(newX, containerRect.width - 200));
        newY = Math.max(10, Math.min(newY, containerRect.height - 100));
        
        fbCanvasDraggingNode.style.left = `${newX}px`;
        fbCanvasDraggingNode.style.top = `${newY}px`;
        
        fbDrawWorkflowConnections();
    });
    
    document.addEventListener('mouseup', () => {
        if (fbCanvasDraggingNode) {
            const statusId = fbCanvasDraggingNode.dataset.statusId;
            const status = fbCurrent.workflow.statuses.find(s => s.id === statusId);
            if (status) {
                status.x = parseInt(fbCanvasDraggingNode.style.left);
                status.y = parseInt(fbCanvasDraggingNode.style.top);
            }
            fbCanvasDraggingNode = null;
            fbCollectProject();
        }
    });
}

function fbStartNodeDrag(e, statusId) {
    if (!fbPermissions.can_manage_workflow) return;
    const node = document.getElementById(`node-${statusId}`);
    if (!node) return;
    
    fbCanvasDraggingNode = node;
    const rect = node.getBoundingClientRect();
    fbCanvasDragOffset.x = e.clientX - rect.left;
    fbCanvasDragOffset.y = e.clientY - rect.top;
    
    e.preventDefault();
}

function fbDrawWorkflowConnections() {
    const svg = document.getElementById('fb-workflow-svg');
    const nodesContainer = document.getElementById('fb-workflow-nodes');
    if (!svg || !nodesContainer) return;
    
    // Clear old links & labels
    svg.querySelectorAll('.workflow-svg-path').forEach(p => p.remove());
    nodesContainer.querySelectorAll('.workflow-link-label').forEach(l => l.remove());
    
    const transitions = fbCurrent.workflow.transitions || [];
    transitions.forEach(trans => {
        const fromNode = document.getElementById(`node-${trans.from_status}`);
        const toNode = document.getElementById(`node-${trans.to_status}`);
        if (!fromNode || !toNode) return;
        
        const x1 = parseInt(fromNode.style.left);
        const y1 = parseInt(fromNode.style.top);
        const w1 = fromNode.offsetWidth || 190;
        const h1 = fromNode.offsetHeight || 80;
        
        const x2 = parseInt(toNode.style.left);
        const y2 = parseInt(toNode.style.top);
        const w2 = toNode.offsetWidth || 190;
        const h2 = toNode.offsetHeight || 80;
        
        const cx1 = x1 + w1 / 2;
        const cy1 = y1 + h1 / 2;
        const cx2 = x2 + w2 / 2;
        const cy2 = y2 + h2 / 2;
        
        const dx = cx2 - cx1;
        const dy = cy2 - cy1;
        const angle = Math.atan2(dy, dx);
        
        const startX = cx1 + Math.cos(angle) * (w1 / 2);
        const startY = cy1 + Math.sin(angle) * (h1 / 2);
        const endX = cx2 - Math.cos(angle) * (w2 / 2 + 10);
        const endY = cy2 - Math.sin(angle) * (h2 / 2 + 10);
        
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', `M ${startX} ${startY} L ${endX} ${endY}`);
        path.setAttribute('class', 'workflow-svg-path');
        path.setAttribute('marker-end', 'url(#arrow)');
        svg.appendChild(path);
        
        const mx = (startX + endX) / 2;
        const my = (startY + endY) / 2;
        
        const label = document.createElement('div');
        label.className = 'workflow-link-label';
        label.style.left = `${mx}px`;
        label.style.top = `${my}px`;
        label.textContent = trans.name;
        label.onclick = () => fbEditTransitionProperties(trans.id);
        nodesContainer.appendChild(label);
    });
}

function fbRenderWorkflowBoard() {
    const container = document.getElementById('fb-workflow-canvas-container');
    const nodesContainer = document.getElementById('fb-workflow-nodes');
    if (!container || !nodesContainer) return;
    
    // Check if currently viewing the designer
    const navBtn = document.querySelector('.feedback-view-nav button.active');
    const isDesigner = navBtn && navBtn.getAttribute('onclick')?.includes('designer');
    
    if (!isDesigner || !fbPermissions.can_manage_workflow) {
        container.style.display = 'none';
        return;
    }
    container.style.display = 'block';
    nodesContainer.innerHTML = '';
    
    const statuses = fbCurrent.workflow.statuses || [];
    statuses.forEach((status, index) => {
        if (!status.x) status.x = 50 + (index % 4) * 210;
        if (!status.y) status.y = 50 + Math.floor(index / 4) * 140;
        
        const node = document.createElement('div');
        node.className = `workflow-node ${status.id === fbCurrent.status ? 'active-node' : ''}`;
        node.id = `node-${status.id}`;
        node.dataset.statusId = status.id;
        node.style.left = `${status.x}px`;
        node.style.top = `${status.y}px`;
        node.onmousedown = (e) => fbStartNodeDrag(e, status.id);
        
        node.innerHTML = `
            <div class="workflow-node-title" title="${fbEscape(status.name)}">${fbEscape(status.name)}</div>
            <div class="workflow-node-meta">
                <span class="badge badge-medium" style="font-size:0.75rem;">${fbEscape(status.category)}</span>
                <span style="font-family:monospace; font-size:0.7rem;">${fbEscape(status.id.substring(0, 8))}</span>
            </div>
            <div class="workflow-node-actions" onmousedown="event.stopPropagation()">
                <button class="btn" type="button" onclick="fbEditStatusProperties('${status.id}')">Edit</button>
                <button class="btn danger-soft" type="button" onclick="fbRemoveStatus('${status.id}')">Delete</button>
            </div>
        `;
        nodesContainer.appendChild(node);
    });
    
    fbDrawWorkflowConnections();
}

function fbEditStatusProperties(statusId) {
    const status = fbCurrent.workflow.statuses.find(s => s.id === statusId);
    if (!status) return;
    
    const name = prompt('Status name:', status.name);
    if (name === null) return;
    status.name = name.trim() || status.name;
    
    const cat = prompt('Category (todo, doing, done):', status.category);
    if (cat !== null) {
        status.category = ['todo', 'doing', 'done'].includes(cat.trim()) ? cat.trim() : status.category;
    }
    
    const screensList = (fbCurrent.workflow.screens || []).map(s => `${s.id}: ${s.name}`).join('\n');
    const screenId = prompt(`Available screens:\n${screensList}\nEnter Screen ID:`, status.screen_id);
    if (screenId !== null) {
        status.screen_id = screenId.trim();
    }
    
    fbRenderWorkflowBoard();
    fbSetAdminMode();
}

function fbEditTransitionProperties(transitionId) {
    const transition = fbCurrent.workflow.transitions.find(t => t.id === transitionId);
    if (!transition) return;
    
    const name = prompt('Transition name:', transition.name);
    if (name === null) return;
    transition.name = name.trim() || transition.name;
    
    const approverType = prompt('Approver type (any_user, manager, user, role, feedback_admin):', transition.approver_type);
    if (approverType !== null) {
        transition.approver_type = approverType.trim() || 'any_user';
    }
    
    const approverVal = prompt('Approver value (username or role):', transition.approver_value);
    if (approverVal !== null) {
        transition.approver_value = approverVal.trim();
    }
    
    const condKey = prompt('Condition field key (optional):', transition.condition_field);
    if (condKey !== null) {
        transition.condition_field = condKey.trim();
    }
    
    fbRenderWorkflowBoard();
    fbSetAdminMode();
}

function fbRemoveStatus(statusId) {
    if (!confirm('Delete this workflow status? Transitions involving this status will be deleted.')) return;
    
    fbCurrent.workflow.statuses = fbCurrent.workflow.statuses.filter((item) => item.id !== statusId);
    fbCurrent.workflow.transitions = fbCurrent.workflow.transitions.filter(t => t.from_status !== statusId && t.to_status !== statusId);
    
    if (fbCurrent.status === statusId) {
        fbCurrent.status = fbCurrent.workflow.statuses[0]?.id || '';
    }
    
    fbRenderWorkflowBoard();
    fbSetAdminMode();
}

function fbAddWorkflowStatus() {
    fbCollectProject();
    const name = prompt('Workflow status name:');
    if (!name) return;
    
    const id = `status_${Date.now()}`;
    const x = 100 + (fbCurrent.workflow.statuses.length % 3) * 230;
    const y = 100 + Math.floor(fbCurrent.workflow.statuses.length / 3) * 150;
    
    fbCurrent.workflow.statuses.push({
        id,
        name: name.trim(),
        category: 'todo',
        screen_id: fbCurrent.workflow.screens[0]?.id || '',
        description: '',
        x,
        y
    });
    
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
    fbCurrent.workflow.screens.push({ id: `screen_${Date.now()}`, name: '', description: '', fields: [] });
    fbRenderScreens();
    fbRenderWorkflowBoard();
}

function fbRemoveScreen(screenId) {
    if (!confirm('Delete this screen? Statuses using it will fall back to the first screen.')) return;
    fbCurrent.workflow.screens = fbCurrent.workflow.screens.filter((screen) => screen.id !== screenId);
    const fallback = fbCurrent.workflow.screens[0]?.id || '';
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
    fbCurrent.questions.push({ id: `q_${Date.now()}`, category: '', type: 'text', required: false, text: '' });
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
    fbSetStatus('Blank builder ready. Add only the components you need.', 'info');
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

        const res = await fetch('/api/feedback/projects', { credentials: 'include' });
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || data.error || 'Could not load projects');
        fbPermissions = data.permissions || fbPermissions;
        fbProjects = data.projects || [];
        fbCurrent = fbProjects[0] ? structuredCloneSafe(fbProjects[0]) : structuredCloneSafe(FB_DEFAULT_PROJECT);
        
        if (fbProjects.length > 0) {
            fbSelectedBoardProjectId = fbCurrent.id;
        }
        
        fbRenderAll();
        fbInitCanvasDragging();
        
        const requestedView = new URLSearchParams(location.search).get('view');
        fbShowView(requestedView || (fbPermissions.can_manage_workflow ? 'designer' : 'assessments'), false);
    } catch (error) {
        fbSetStatus(error.message || 'Could not load feedback cycles.', 'error');
        fbRenderAll();
    }
}

async function fbSaveProject() {
    if (!fbPermissions.can_manage_workflow) return fbSetStatus('Only a 180 admin can configure workflow, screens, participants and questions.', 'error');
    if (fbSaving) return;
    fbCollectProject();
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
