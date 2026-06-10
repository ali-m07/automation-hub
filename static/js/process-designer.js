let pdMeta = { modules: [], field_types: [] };

function pdEscape(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
}

function pdStatus(message, type = 'info') {
    const box = document.getElementById('pd-status');
    box.style.display = 'block';
    box.className = `status-box ${type}`;
    box.textContent = message;
}

function pdSelected(id) {
    return Array.from(document.getElementById(id).selectedOptions).map(option => option.value);
}

function pdJson(id, fallback) {
    const raw = document.getElementById(id).value.trim();
    if (!raw) return fallback;
    return JSON.parse(raw);
}

async function pdRequest(url, options = {}) {
    const response = await fetch(url, { credentials: 'include', ...options });
    const data = await response.json();
    if (!data.success) throw new Error(data.detail || data.error || 'Request failed');
    return data;
}

function pdRenderModuleOptions() {
    const options = pdMeta.modules.map(module => `<option value="${pdEscape(module.key)}">${pdEscape(module.label)}</option>`).join('');
    document.getElementById('pd-field-modules').innerHTML = options;
    document.getElementById('pd-workflow-modules').innerHTML = options;
    document.getElementById('pd-field-type').innerHTML = pdMeta.field_types.map(type => `<option value="${type}">${type.replaceAll('_', ' ')}</option>`).join('');
}

async function pdLoad() {
    try {
        pdMeta = await pdRequest('/api/processes/meta');
        pdRenderModuleOptions();
        const [fields, workflows] = await Promise.all([pdRequest('/api/processes/fields'), pdRequest('/api/processes/workflows')]);
        document.getElementById('pd-fields').innerHTML = fields.fields.map(field => `<article class="ticket-card"><strong>${pdEscape(field.label)}</strong><span>${pdEscape(field.key)} · ${pdEscape(field.type)} · ${field.scope_type === 'global' ? 'all modules' : pdEscape(field.scope_modules.join(', '))}</span></article>`).join('') || '<div class="feedback-empty">No shared fields yet.</div>';
        document.getElementById('pd-workflows').innerHTML = workflows.workflows.map(item => `<article class="ticket-card"><strong>${pdEscape(item.name)}</strong><span>${pdEscape(item.key)} · ${item.statuses.length} statuses · ${item.transitions.length} transitions</span></article>`).join('') || '<div class="feedback-empty">No shared workflows yet.</div>';
    } catch (error) { pdStatus(error.message, 'error'); }
}

async function pdSaveField() {
    try {
        const payload = {
            label: document.getElementById('pd-field-label').value,
            key: document.getElementById('pd-field-key').value,
            type: document.getElementById('pd-field-type').value,
            scope_type: document.getElementById('pd-field-scope').value,
            scope_modules: pdSelected('pd-field-modules'),
            config: { options: document.getElementById('pd-field-options').value.split('\n').map(v => v.trim()).filter(Boolean) },
            visibility: pdJson('pd-field-visibility', {})
        };
        await pdRequest('/api/processes/fields', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        pdStatus('Shared custom field saved.', 'success'); await pdLoad();
    } catch (error) { pdStatus(error.message, 'error'); }
}

async function pdSaveWorkflow() {
    try {
        const payload = {
            name: document.getElementById('pd-workflow-name').value,
            key: document.getElementById('pd-workflow-key').value,
            description: document.getElementById('pd-workflow-description').value,
            scope_type: document.getElementById('pd-workflow-scope').value,
            scope_modules: pdSelected('pd-workflow-modules'),
            statuses: pdJson('pd-statuses', []),
            transitions: pdJson('pd-transitions', []),
            manage_policy: pdJson('pd-policy', {})
        };
        await pdRequest('/api/processes/workflows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        pdStatus('Reusable workflow saved.', 'success'); await pdLoad();
    } catch (error) { pdStatus(error.message, 'error'); }
}

document.addEventListener('DOMContentLoaded', pdLoad);
