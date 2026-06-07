
// Global state
let state = {
    psdFileId: null,
    dataFileId: null,
    layers: [],
    columns: [],
    layerMapping: [],
    filenameFields: [],
    emailDataFileId: null,
    singleImageId: null,
    folderImageId: null,
    emailConfig: null,
    dataGridInitialized: false,
    dataGrid: null,
    currentTableId: 'default',
    tables: [],
    selectedColumnField: null,
    dataGridAutoSaveTimer: null,
    users: [],
    currentPermission: "edit",
    dbConnectors: [],
    dbSyncFilename: null,
    dbSyncSheets: [],
    creativeFonts: [],
    layerOverrides: {}
};

// Dark mode
function initDarkMode() {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    updateDarkModeIcon(saved);
}

function toggleDarkMode() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateDarkModeIcon(newTheme);
}

function updateDarkModeIcon(theme) {
    const icon = document.getElementById('dark-mode-icon');
    if (icon) {
        icon.textContent = theme === 'dark' ? '☀️' : '🌙';
    }
}

// Initialize on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDarkMode);
} else {
    initDarkMode();
}

// Keyboard shortcuts
const shortcuts = {
    'Ctrl+K': () => {
        const search = document.getElementById('platform-search');
        if (search) search.focus();
    },
    'g c': () => { window.location.href = '/creative'; },
    'g d': () => { window.location.href = '/data'; },
    'g m': () => { window.location.href = '/messaging'; },
    'g s': () => { window.location.href = '/summary'; },
    'g a': () => { window.location.href = '/admin'; },
    '?': () => { alert('Shortcuts:\nCtrl+K: Search\nG+C: Creative\nG+D: Data\nG+M: Messaging\nG+S: Summary\nG+A: Admin'); }
};

let shortcutBuffer = '';
let shortcutTimer = null;

document.addEventListener('keydown', (e) => {
    // Ctrl+K
    if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        shortcuts['Ctrl+K']();
        return;
    }
    // G-based shortcuts (g+c, g+d, etc)
    if (e.key === 'g' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        shortcutBuffer = 'g';
        shortcutTimer = setTimeout(() => { shortcutBuffer = ''; }, 1000);
        return;
    }
    if (shortcutBuffer === 'g' && ['c', 'd', 'm', 's', 'a'].includes(e.key.toLowerCase())) {
        e.preventDefault();
        clearTimeout(shortcutTimer);
        const key = `g ${e.key.toLowerCase()}`;
        if (shortcuts[key]) shortcuts[key]();
        shortcutBuffer = '';
    }
    // ? for help
    if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
        shortcuts['?']();
    }
});

// Onboarding tour
let onboardingStep = 0;
const onboardingSteps = [
    { element: '#app-sidebar', title: 'Welcome!', text: 'This is the main navigation menu. Use it to access different modules.' },
    { element: '.top-nav', title: 'Search & Notifications', text: 'Use Ctrl+K to search, and check notifications here.' },
    { element: '#platform-search', title: 'Quick Search', text: 'Search across tables, templates, gallery, and tickets.' },
];

function startOnboarding() {
    if (localStorage.getItem('onboarding_completed') === 'true') {
        return;
    }
    onboardingStep = 0;
    showOnboardingStep();
}

function showOnboardingStep() {
    if (onboardingStep >= onboardingSteps.length) {
        endOnboarding();
        return;
    }
    const step = onboardingSteps[onboardingStep];
    const el = document.querySelector(step.element);
    if (!el) {
        onboardingStep++;
        setTimeout(showOnboardingStep, 100);
        return;
    }
    const rect = el.getBoundingClientRect();
    const overlay = document.createElement('div');
    overlay.id = 'onboarding-overlay';
    overlay.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:9999;';
    overlay.onclick = () => { endOnboarding(); };
    const tooltip = document.createElement('div');
    tooltip.style.cssText = `position:fixed; top:${rect.top + rect.height + 10}px; left:${rect.left}px; background:#fff; padding:16px; border-radius:8px; box-shadow:0 4px 12px rgba(0,0,0,0.15); z-index:10000; max-width:300px;`;
    tooltip.innerHTML = `
        <h3 style="margin:0 0 8px 0; font-size:1.1rem;">${step.title}</h3>
        <p style="margin:0 0 12px 0; color:#6b7280;">${step.text}</p>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#6b7280; font-size:0.9rem;">${onboardingStep + 1} / ${onboardingSteps.length}</span>
            <div>
                ${onboardingStep > 0 ? '<button onclick="onboardingStep--; showOnboardingStep();" style="margin-right:8px; padding:6px 12px; border:1px solid #e5e7eb; background:#fff; border-radius:6px; cursor:pointer;">Previous</button>' : ''}
                <button onclick="onboardingStep++; showOnboardingStep();" style="padding:6px 12px; background:#111827; color:#fff; border:none; border-radius:6px; cursor:pointer;">${onboardingStep === onboardingSteps.length - 1 ? 'Finish' : 'Next'}</button>
            </div>
        </div>
    `;
    overlay.appendChild(tooltip);
    document.body.appendChild(overlay);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function endOnboarding() {
    const overlay = document.getElementById('onboarding-overlay');
    if (overlay) overlay.remove();
    localStorage.setItem('onboarding_completed', 'true');
    // Save to backend
    fetch('/api/me/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ has_seen_onboarding: true })
    }).catch(() => {});
}

// i18n support
const translations = {
    en: {
        'welcome': 'Welcome',
        'search': 'Search',
        'notifications': 'Notifications',
        'profile': 'Profile',
        'logout': 'Logout',
    },
    fa: {
        'welcome': 'خوش آمدید',
        'search': 'جستجو',
        'notifications': 'اعلان‌ها',
        'profile': 'پروفایل',
        'logout': 'خروج',
    }
};

let currentLang = localStorage.getItem('language') || 'en';

function setLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('language', lang);
    document.documentElement.setAttribute('lang', lang);
    document.documentElement.setAttribute('dir', lang === 'fa' ? 'rtl' : 'ltr');
    // Update text elements (simplified - would need more comprehensive implementation)
    const t = translations[lang] || translations.en;
    const searchInput = document.getElementById('platform-search');
    if (searchInput) searchInput.placeholder = t.search + '...';
    const selector = document.getElementById('language-selector');
    if (selector) selector.value = lang;
    // Save to backend
    fetch('/api/me/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ language: lang })
    }).catch(() => {});
}

function t(key) {
    return (translations[currentLang] || translations.en)[key] || key;
}

// Initialize language and onboarding
(async () => {
    try {
        const res = await fetch('/api/me/preferences', { credentials: 'include' });
        const data = await res.json();
        if (data.language) setLanguage(data.language);
        if (!data.has_seen_onboarding) {
            setTimeout(() => startOnboarding(), 1000);
        }
    } catch (e) {
        setLanguage(currentLang);
    }
})();

// Default grid shape for new tables
const DATA_DEFAULT_COLUMNS = 5;
const DATA_DEFAULT_ROWS = 5;

function buildDefaultColumns() {
    const cols = [];
    for (let i = 1; i <= DATA_DEFAULT_COLUMNS; i++) {
        cols.push({
            title: `Col ${i}`,
            field: `c${i}`,
            editor: 'input'
        });
    }
    return cols;
}

function buildBlankRows(count) {
    const rows = [];
    for (let i = 0; i < count; i++) {
        rows.push({});
    }
    return rows;
}

function ensureColumnsForData() {
    if (!state.dataGridInitialized || !state.dataGrid) return;
    
    const data = state.dataGrid.getData();
    if (!data || data.length === 0) return;
    
    // Find the maximum number of fields (columns) in any row
    // Check both c1, c2, ... fields and any other fields that might exist
    let maxFieldIndex = 0;
    data.forEach(row => {
        Object.keys(row).forEach(key => {
            if (key.startsWith('c')) {
                const match = key.match(/^c(\d+)$/);
                if (match) {
                    const idx = parseInt(match[1], 10);
                    if (idx > maxFieldIndex) {
                        maxFieldIndex = idx;
                    }
                }
            }
        });
    });
    
    // Get current column definitions
    const cols = state.dataGrid.getColumnDefinitions() || [];
    const currentColCount = cols.length;
    
    // If we need more columns, add them
    if (maxFieldIndex > currentColCount) {
        for (let i = currentColCount + 1; i <= maxFieldIndex; i++) {
            const field = `c${i}`;
            // Check if column already exists
            const exists = cols.some(c => c.field === field);
            if (!exists) {
                const colDef = {
                    title: `Col ${i}`,
                    field,
                    editor: 'input'
                };
                try {
                    state.dataGrid.addColumn(colDef, false);
                } catch (err) {
                    console.warn(`Could not add column ${i}:`, err);
                }
            }
        }
        // Redraw after adding columns to ensure layout is correct
        if (maxFieldIndex > currentColCount) {
            state.dataGrid.redraw(true);
        }
    }
}

// Tabulator script loader (only when needed)
function ensureTabulatorLoaded(callback) {
    if (window.Tabulator) {
        callback();
        return;
    }
    const script = document.createElement('script');
    script.src = '/static/js/tabulator.min.js';
    script.onload = () => callback();
    document.head.appendChild(script);
}

// Tab switching
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    
    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = (event && event.target && event.target.classList && event.target.classList.contains('tab-button')) ? event.target : document.querySelector(`.tab-button[onclick*="switchTab('${tabName}')"]`);
    if (activeBtn) activeBtn.classList.add('active');

    // Lazy-init data grid when entering Data & Connectors
    if (tabName === 'data-connectors' && !state.dataGridInitialized) {
        ensureTabulatorLoaded(() => initDataGrid());
    }
    if (tabName === 'data-connectors') {
        loadDbConnectors();
    }

    // Load tickets when entering Support tab
    if (tabName === 'support') {
        loadMyTickets();
    }

    // Load gallery when entering File Repository tab
    if (tabName === 'gallery') {
        loadGallery();
    }
    // Load PSD templates and job history when entering Creative tab
    if (tabName === 'creative') {
        loadCreativeTemplates();
        loadCreativeJobs();
    }
    // Load summary when entering Summary tab
    if (tabName === 'summary') {
        loadSummary();
    }
}

async function loadSummary() {
    const cardsEl = document.getElementById('summary-cards');
    const jobsEl = document.getElementById('summary-last-jobs');
    const ticketEl = document.getElementById('summary-last-ticket');
    if (!cardsEl || !jobsEl || !ticketEl) return;
    try {
        const res = await fetch('/api/summary', { credentials: 'include' });
        const data = await res.json();
        if (!data.success) {
            cardsEl.innerHTML = '<p class="status-box error">Failed to load summary.</p>';
            return;
        }
        cardsEl.innerHTML = `
            <div class="card" style="padding:16px; border:1px solid #e5e7eb; border-radius:12px;">
                <div style="font-size:0.9rem; color:#6b7280;">Tables</div>
                <div style="font-size:1.75rem; font-weight:800; color:#111827;">${data.tables_count ?? 0}</div>
            </div>
            <div class="card" style="padding:16px; border:1px solid #e5e7eb; border-radius:12px;">
                <div style="font-size:0.9rem; color:#6b7280;">Creative jobs (last 5)</div>
                <div style="font-size:1.75rem; font-weight:800; color:#111827;">${(data.last_jobs || []).length}</div>
            </div>
            <div class="card" style="padding:16px; border:1px solid #e5e7eb; border-radius:12px;">
                <div style="font-size:0.9rem; color:#6b7280;">Files in gallery</div>
                <div style="font-size:1.75rem; font-weight:800; color:#111827;">${data.gallery_count ?? 0}</div>
            </div>
        `;
        const jobs = data.last_jobs || [];
        if (jobs.length === 0) {
            jobsEl.innerHTML = '<p style="color:#6b7280;">No Creative jobs yet.</p>';
        } else {
            jobsEl.innerHTML = '<h3 style="margin-bottom:8px;">Last Creative jobs</h3><ul style="list-style:none; padding:0;">' +
                jobs.map(j => `
                    <li style="padding:10px 0; border-bottom:1px solid #e5e7eb;">
                        Job #${j.job_id} — ${j.status} — ${j.row_count || 0} rows
                        ${j.zip_link ? ` <a href="${j.zip_link}" class="btn" style="padding:4px 8px;">Download ZIP</a>` : ''}
                    </li>
                `).join('') + '</ul>';
        }
        const t = data.last_ticket;
        if (!t) {
            ticketEl.innerHTML = '<p style="color:#6b7280;">No tickets yet.</p>';
        } else {
            ticketEl.innerHTML = `
                <h3 style="margin-bottom:8px;">Latest ticket</h3>
                <div style="padding:12px; border:1px solid #e5e7eb; border-radius:8px;">
                    <strong>#${t.id}</strong> ${escapeHtml(t.subject || '')} — ${t.status || 'open'}
                    <br><small>Created: ${t.created_at || ''}${t.admin_replied_at ? ' · Replied: ' + t.admin_replied_at : ''}</small>
                </div>
            `;
        }
    } catch (e) {
        cardsEl.innerHTML = '<p class="status-box error">Failed to load summary.</p>';
    }
}

function showTablesHub() {
    const hub = document.getElementById("tables-hub");
    const panel = document.getElementById("grid-panel");
    if (hub) hub.style.display = "block";
    if (panel) panel.style.display = "none";
    const vPanel = document.getElementById('table-versions-panel');
    if (vPanel) vPanel.style.display = 'none';
}

function toggleTableVersionsPanel() {
    const panel = document.getElementById('table-versions-panel');
    if (!panel) return;
    if (panel.style.display === 'block') {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'block';
    loadTableVersions();
}

async function loadTableVersions() {
    const listEl = document.getElementById('table-versions-list');
    const tableId = state.currentTableId || 'default';
    if (!listEl) return;
    try {
        const res = await fetch(`/api/data/tables/${encodeURIComponent(tableId)}/versions`, { credentials: 'include' });
        const data = await res.json();
        if (!data.success) {
            listEl.innerHTML = '<p style="color:#6b7280;">' + (data.error || 'Failed to load versions.') + '</p>';
            return;
        }
        const versions = data.versions || [];
        if (versions.length === 0) {
            listEl.innerHTML = '<p style="color:#6b7280;">No backup versions yet. Save the table to create versions.</p>';
            return;
        }
        listEl.innerHTML = versions.map(v => `
            <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 0; border-bottom:1px solid #e5e7eb;">
                <span>Version #${v.version_number} — ${escapeHtml(v.created_at || '')}</span>
                <button class="btn" style="padding:4px 10px;" onclick="restoreTableVersion(${v.id})">Restore</button>
            </div>
        `).join('');
    } catch (e) {
        listEl.innerHTML = '<p style="color:#ef4444;">Error loading versions.</p>';
    }
}

async function restoreTableVersion(versionId) {
    const tableId = state.currentTableId || 'default';
    try {
        const res = await fetch(`/api/data/tables/${encodeURIComponent(tableId)}/restore`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version_id: versionId })
        });
        const data = await res.json();
        if (data.success) {
            if (typeof showToast === 'function') showToast('Restored. Reloading grid.', 'success');
            loadDataGrid();
            loadTableVersions();
        } else {
            if (typeof showToast === 'function') showToast(data.error || 'Restore failed', 'error');
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast('Restore failed', 'error');
    }
}

function showGridPanel() {
    const hub = document.getElementById("tables-hub");
    const panel = document.getElementById("grid-panel");
    if (hub) hub.style.display = "none";
    if (panel) panel.style.display = "block";
}

// Database connectors (Excel sync to SQL Server)
async function loadDbConnectors() {
    const noAccess = document.getElementById('db-connectors-no-access');
    const form = document.getElementById('db-connectors-form');
    const select = document.getElementById('db-connector-select');
    if (!noAccess || !form || !select) return;
    try {
        const res = await fetch('/api/db-connectors', { credentials: 'include' });
        if (res.status === 403) {
            noAccess.style.display = 'block';
            form.style.display = 'none';
            return;
        }
        noAccess.style.display = 'none';
        form.style.display = 'block';
        const data = await res.json();
        if (!data.success || !data.connectors) {
            state.dbConnectors = [];
        } else {
            state.dbConnectors = data.connectors;
        }
        // In user UI فقط اسم کانکتور را نشان بده، نه نام جدول/اسکیمای فنی
        select.innerHTML = '<option value="">— Select connector —</option>' +
            state.dbConnectors.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
        state.dbSyncFilename = null;
        state.dbSyncSheets = [];
        document.getElementById('db-sync-file-name').textContent = '';
        document.getElementById('db-sync-sheet-row').style.display = 'none';
        document.getElementById('db-sync-run-btn').disabled = true;
        document.getElementById('db-sync-status').textContent = '';
        // Reset preview panel until a connector is selected
        const previewPanel = document.getElementById('db-preview-panel');
        const previewGrid = document.getElementById('db-preview-grid');
        const previewStatus = document.getElementById('db-preview-status');
        if (previewPanel && previewGrid && previewStatus) {
            previewPanel.style.display = 'none';
            previewGrid.innerHTML = '';
            previewStatus.textContent = '';
        }
    } catch (e) {
        noAccess.style.display = 'block';
        form.style.display = 'none';
    }
}

async function handleDbSyncUpload(evt) {
    const file = evt.target.files && evt.target.files[0];
    const fileNameEl = document.getElementById('db-sync-file-name');
    const sheetRow = document.getElementById('db-sync-sheet-row');
    const sheetSelect = document.getElementById('db-sync-sheet');
    const runBtn = document.getElementById('db-sync-run-btn');
    const statusEl = document.getElementById('db-sync-status');
    if (!file) {
        fileNameEl.textContent = '';
        sheetRow.style.display = 'none';
        runBtn.disabled = true;
        state.dbSyncFilename = null;
        state.dbSyncSheets = [];
        return;
    }
    statusEl.textContent = 'Uploading…';
    statusEl.className = 'status-box info';
    try {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch('/api/db-connectors/upload', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });
        const data = await res.json();
        if (!data.success) {
            statusEl.textContent = data.error || 'Upload failed';
            statusEl.className = 'status-box error';
            return;
        }
        state.dbSyncFilename = data.filename;
        state.dbSyncSheets = data.sheets || [];
        fileNameEl.textContent = file.name;
        sheetSelect.innerHTML = state.dbSyncSheets.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
        sheetRow.style.display = 'block';
        updateDbSyncRunButton();
        statusEl.textContent = 'File uploaded. Select sheet and click Sync.';
        statusEl.className = 'status-box success';
    } catch (e) {
        statusEl.textContent = e.message || 'Upload failed';
        statusEl.className = 'status-box error';
    }
}

function updateDbSyncRunButton() {
    const runBtn = document.getElementById('db-sync-run-btn');
    const connectorSelect = document.getElementById('db-connector-select');
    const sheetSelect = document.getElementById('db-sync-sheet');
    if (!runBtn) return;
    const hasConnector = connectorSelect && connectorSelect.value;
    const hasFile = !!state.dbSyncFilename;
    const hasSheet = sheetSelect && sheetSelect.value;
    runBtn.disabled = !hasConnector || !hasFile || !hasSheet;
}

function switchDbTab(tab) {
    const syncTab = document.getElementById('db-sync-tab');
    const browsePanel = document.getElementById('db-preview-panel');
    const syncBtn = document.getElementById('db-tab-sync-btn');
    const browseBtn = document.getElementById('db-tab-browse-btn');
    if (!syncTab || !browsePanel || !syncBtn || !browseBtn) return;

    if (tab === 'browse') {
        syncTab.style.display = 'none';
        browsePanel.style.display = 'block';
        syncBtn.classList.remove('active');
        browseBtn.classList.add('active');
        // When switching to browse, ensure grid is loaded for current connector
        loadDbConnectorPreview();
    } else {
        syncTab.style.display = 'block';
        browsePanel.style.display = 'none';
        syncBtn.classList.add('active');
        browseBtn.classList.remove('active');
    }
}

async function loadDbConnectorPreview() {
    const select = document.getElementById('db-connector-select');
    const previewPanel = document.getElementById('db-preview-panel');
    const previewGrid = document.getElementById('db-preview-grid');
    const previewStatus = document.getElementById('db-preview-status');
    if (!select || !previewPanel || !previewGrid || !previewStatus) return;

    const connectorId = select.value;
    if (!connectorId) {
        previewPanel.style.display = 'none';
        previewGrid.innerHTML = '';
        previewStatus.textContent = '';
        return;
    }

    previewPanel.style.display = 'block';
    previewStatus.textContent = 'Loading preview (read-only)…';
    previewStatus.className = 'status-box info';
    previewGrid.innerHTML = '';

    try {
        // limit=0 => load all rows; Tabulator paginates locally in the browser.
        const res = await fetch(`/api/db-connectors/${encodeURIComponent(connectorId)}/preview?limit=0`, {
            credentials: 'include'
        });
        const data = await res.json();
        if (!data.success) {
            previewStatus.textContent = data.error || 'Failed to load preview.';
            previewStatus.className = 'status-box error';
            previewGrid.innerHTML = '';
            return;
        }
        const rows = data.rows || [];
        const cols = data.columns || [];
        previewStatus.textContent = `Showing ${rows.length} row(s) (read-only).`;
        previewStatus.className = 'status-box info';

        const render = () => {
            const columns = cols.map(name => ({
                title: name,
                field: name,
                headerSort: true,
                editor: false,
            }));
            if (!window.dbPreviewGrid) {
                window.dbPreviewGrid = new Tabulator('#db-preview-grid', {
                    height: '320px',
                    layout: 'fitDataStretch',
                    selectable: false,
                    movableColumns: false,
                    pagination: 'local',
                    paginationSize: 50,
                    paginationSizeSelector: [25, 50, 100, 200],
                    columns,
                    data: rows,
                });
            } else {
                window.dbPreviewGrid.setColumns(columns);
                window.dbPreviewGrid.setData(rows);
            }
        };

        if (window.Tabulator) {
            render();
        } else if (typeof ensureTabulatorLoaded === 'function') {
            ensureTabulatorLoaded(render);
        }
    } catch (e) {
        previewStatus.textContent = e.message || 'Failed to load preview.';
        previewStatus.className = 'status-box error';
        previewGrid.innerHTML = '';
    }
}

function filterDbBrowseGrid(query) {
    if (!window.dbPreviewGrid) return;
    const value = (query || '').trim();
    if (!value) {
        window.dbPreviewGrid.clearFilter(true);
        return;
    }
    // Global search across all columns
    window.dbPreviewGrid.setFilter((data, row) => {
        const q = value.toLowerCase();
        for (const key in data) {
            if (!Object.prototype.hasOwnProperty.call(data, key)) continue;
            const v = data[key];
            if (v != null && String(v).toLowerCase().includes(q)) {
                return true;
            }
        }
        return false;
    });
}

function downloadDbConnectorData() {
    const select = document.getElementById('db-connector-select');
    if (!select || !select.value) {
        if (typeof showToast === 'function') {
            showToast('Select a connector first.', 'error');
        }
        return;
    }
    const connectorId = select.value;
    // Trigger browser download
    window.location.href = `/api/db-connectors/${encodeURIComponent(connectorId)}/export`;
}

async function runDbSync() {
    const connectorId = document.getElementById('db-connector-select').value;
    const sheetSelect = document.getElementById('db-sync-sheet');
    const statusEl = document.getElementById('db-sync-status');
    if (!connectorId || !state.dbSyncFilename) {
        statusEl.textContent = 'Select connector and upload a file.';
        statusEl.className = 'status-box error';
        return;
    }
    const sheetName = sheetSelect ? sheetSelect.value : '';
    if (!sheetName) {
        statusEl.textContent = 'Select a sheet.';
        statusEl.className = 'status-box error';
        return;
    }
    statusEl.textContent = 'Syncing…';
    statusEl.className = 'status-box info';
    try {
        const res = await fetch('/api/db-connectors/sync', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                connector_id: parseInt(connectorId, 10),
                filename: state.dbSyncFilename,
                sheet_name: sheetName
            })
        });
        const data = await res.json();
        if (data.success) {
            statusEl.textContent = data.message || 'Sync completed.';
            statusEl.className = 'status-box success';
        } else {
            statusEl.textContent = data.error || 'Sync failed.';
            statusEl.className = 'status-box error';
        }
    } catch (e) {
        statusEl.textContent = e.message || 'Sync failed.';
        statusEl.className = 'status-box error';
    }
}

// Data grid (Data & Connectors) using Tabulator
function initDataGrid() {
    const gridElement = document.getElementById('data-grid');
    if (!gridElement) return;

    // Default generic columns so the user can immediately type or paste like Excel
    const defaultColumns = buildDefaultColumns();

    state.dataGrid = new Tabulator('#data-grid', {
        height: '70vh',
        layout: 'fitColumns', // Only show existing columns, no empty space
        placeholder: 'Click and start typing, or paste from Excel/Sheets.',
        // Virtual DOM required for range selection (works well with large datasets)
        virtualDom: true,
        virtualDomBuffer: 300, // Render extra rows for smooth scrolling
        // Selection
        selectable: true,
        selectableRows: true, // Enable row selection
        selectableRowsRangeMode: 'click', // Click to select rows
        // Cell range selection (for multi-cell select / copy like Excel)
        selectableRange: true,
        selectableRangeColumns: true,
        selectableRangeRows: true,
        selectableRangeClearCells: false, // Don't clear cells when selecting range
        // Clipboard / paste
        clipboard: true,
        clipboardPasteParser: 'range',
        clipboardPasteAction: 'replace',
        clipboardCopySelector: 'active', // Copy selected range
        // History (for undo / redo)
        history: true,
        historySize: 50, // Keep last 50 actions for undo
        reactiveData: true,
        columns: defaultColumns,
        // Allow dynamic column/row expansion on paste
        autoColumns: false,
        autoColumnsDefinitions: false,
        // Prevent empty column space
        columnMinWidth: 100,
        resizableColumns: true,
        // Better keyboard navigation
        tabEndNewRow: true, // Tab at end of row creates new row
        tabEndNewRowEdit: true // Start editing new row immediately
    });

    // Pre-create a few empty rows so you can type immediately
    state.dataGrid.setData(buildBlankRows(DATA_DEFAULT_ROWS));

    // Auto-save on edits / paste / row add
    state.dataGrid.on('cellEdited', handleDataGridChanged);
    state.dataGrid.on('rowAdded', handleDataGridChanged);
    state.dataGrid.on('dataChanged', function() {
        // After data changes (including paste), ensure we have enough columns
        ensureColumnsForData();
        handleDataGridChanged();
    });
    
    // Handle paste to auto-expand columns/rows if needed
    state.dataGrid.on('dataLoaded', function() {
        ensureColumnsForData();
    });
    
    // Intercept paste to auto-add columns/rows before paste
    document.addEventListener('paste', function(e) {
        // Only handle if focus is on the grid
        const activeEl = document.activeElement;
        if (!activeEl || !activeEl.closest('#data-grid')) return;
        
        const clipboardData = e.clipboardData || window.clipboardData;
        if (!clipboardData) return;
        
        const pastedText = clipboardData.getData('text/plain');
        if (!pastedText) return;
        
        // Parse the pasted data to see dimensions
        const lines = pastedText.split('\n').filter(line => line.trim());
        if (lines.length === 0) return;
        
        const firstLine = lines[0];
        const columnCount = firstLine.split('\t').length;
        const rowCount = lines.length;
        
        // Get current grid dimensions
        const cols = state.dataGrid.getColumnDefinitions() || [];
        const currentColCount = cols.length;
        const currentData = state.dataGrid.getData();
        const currentRowCount = currentData.length;
        
        // Add columns if needed
        if (columnCount > currentColCount) {
            for (let i = currentColCount + 1; i <= columnCount; i++) {
                const field = `c${i}`;
                const colDef = {
                    title: `Col ${i}`,
                    field,
                    editor: 'input'
                };
                try {
                    state.dataGrid.addColumn(colDef, false);
                } catch (err) {
                    console.warn(`Could not add column ${i}:`, err);
                }
            }
        }
        
        // Add rows if needed (we'll let Tabulator handle this, but ensure we have enough)
        if (rowCount > currentRowCount) {
            const neededRows = rowCount - currentRowCount;
            for (let i = 0; i < neededRows; i++) {
                try {
                    state.dataGrid.addRow({});
                } catch (err) {
                    console.warn(`Could not add row:`, err);
                }
            }
        }
    }, true); // Use capture phase to intercept before Tabulator

    // Track which column user clicked last for rename / delete actions
    // Use headerClick instead of columnClick for better compatibility
    state.dataGrid.on('headerClick', function (e, column) {
        const field = column.getField();
        if (!field) return;
        state.selectedColumnField = field;
        const def = column.getDefinition();
        const title = def.title || field || '(untitled)';
        const label = document.getElementById('data-grid-column-label');
        if (label) {
            label.textContent = title;
            label.style.color = '#0f766e';
            label.style.fontWeight = '600';
        }
        // Clear any error status
        showStatus('data-grid-status', '', 'info');
    });

    // Function to update selection status display - checks DOM directly
    function updateSelectionStatus() {
        try {
            const statusEl = document.getElementById('data-grid-status');
            if (!statusEl) return;
            
            // Check DOM directly for selected cells (most reliable method)
            const gridEl = document.getElementById('data-grid');
            if (!gridEl) {
                statusEl.textContent = '';
                statusEl.className = 'status-box info';
                return;
            }
            
            // Find all selected cells in DOM
            const selectedCells = gridEl.querySelectorAll('.tabulator-cell.tabulator-range-selected, .tabulator-cell.tabulator-selected');
            const count = selectedCells.length;
            
            if (count > 0) {
                statusEl.textContent = `✓ Selected: ${count} cell${count !== 1 ? 's' : ''}`;
                statusEl.className = 'status-box success';
            } else {
                statusEl.textContent = '';
                statusEl.className = 'status-box info';
            }
        } catch (err) {
            console.log('Selection status error:', err);
        }
    }
    
    // Poll for selection changes (simple and reliable)
    let selectionCheckInterval = setInterval(updateSelectionStatus, 200);
    
    // Also update on mouse/keyboard events
    const gridContainer = document.getElementById('data-grid');
    if (gridContainer) {
        // Update on any mouse activity in grid
        gridContainer.addEventListener('mousedown', function() {
            setTimeout(updateSelectionStatus, 100);
        });
        gridContainer.addEventListener('mouseup', function() {
            setTimeout(updateSelectionStatus, 150);
        });
        gridContainer.addEventListener('click', function() {
            setTimeout(updateSelectionStatus, 100);
        });
    }
    
    // Update on keyboard events
    document.addEventListener('keydown', function() {
        setTimeout(updateSelectionStatus, 100);
    });
    
    // Make updateSelectionStatus available globally
    window.updateSelectionStatus = updateSelectionStatus;

    // Track mouse drag for multi-cell selection
    state.dataGridInitialized = true;
    state.selectedColumnField = null; // Reset on init

    // Reset column label
    const label = document.getElementById('data-grid-column-label');
    if (label) {
        label.textContent = 'None';
        label.style.color = '#374151';
        label.style.fontWeight = 'normal';
    }

    // Try to load any previously saved grid from backend
    loadDataGrid();
}

function handleDataGridChanged() {
    // Debounced auto-save so pasting 20k rows does not spam the server
    if (state.dataGridAutoSaveTimer) {
        clearTimeout(state.dataGridAutoSaveTimer);
    }
    showStatus('data-grid-status', 'Saving changes…', 'info');
    state.dataGridAutoSaveTimer = setTimeout(() => {
        saveDataGrid(true);
    }, 1000);
}

async function loadDataGrid() {
    if (!state.dataGridInitialized || !state.dataGrid) return;
    try {
        const res = await fetch(`/api/data/grid?table=${encodeURIComponent(state.currentTableId)}`, {
            credentials: 'include'
        });
        const data = await res.json();
        state.currentPermission = data.permission || "edit";

        // Only update if backend has actual data (not empty arrays)
        if (Array.isArray(data.columns) && data.columns.length > 0) {
            state.dataGrid.setColumns(data.columns);
        }
        if (Array.isArray(data.rows) && data.rows.length > 0) {
            state.dataGrid.setData(data.rows);
        } else if (Array.isArray(data.rows) && data.rows.length === 0 && Array.isArray(data.columns) && data.columns.length === 0) {
            // Backend explicitly returned empty - keep current empty state, don't override
            showStatus('data-grid-status', 'New table ready. Start typing or paste data.', 'info');
            applyGridPermission();
            return;
        }

        if (data.columns && data.columns.length > 0) {
            showStatus('data-grid-status', 'Grid loaded.', 'info');
        }
        applyGridPermission();
    } catch (err) {
        showStatus('data-grid-status', `Error: ${err.message}`, 'error');
    }
}

function applyGridPermission() {
    const perm = state.currentPermission || "edit";
    const isReadOnly = perm === "view" || perm === "view_nocopy";

    // Disable editing by stripping editors
    if (state.dataGrid) {
        const cols = state.dataGrid.getColumnDefinitions() || [];
        const patched = cols.map((c) => {
            const copy = { ...c };
            if (isReadOnly) {
                delete copy.editor;
                copy.editable = false;
            } else {
                if (!copy.editor) copy.editor = "input";
                delete copy.editable;
            }
            return copy;
        });
        try {
            state.dataGrid.setColumns(patched);
        } catch (e) {}
    }

    // Disable save/delete controls
    const btnSave = document.querySelector('button[onclick="saveDataGrid()"]');
    const btnDel = document.querySelector('button[onclick="deleteSelectedRows()"]');
    if (btnSave) btnSave.disabled = isReadOnly;
    if (btnDel) btnDel.disabled = isReadOnly;

    // "no copy" block
    const gridEl = document.getElementById("data-grid");
    if (gridEl) {
        gridEl.oncopy = null;
        gridEl.oncut = null;
        if (perm === "view_nocopy") {
            gridEl.oncopy = (e) => {
                e.preventDefault();
                showStatus("data-grid-status", "Copy is disabled for this table.", "error");
            };
            gridEl.oncut = (e) => e.preventDefault();
        }
    }
}

async function exportTableToExcel() {
    if (!state.currentTableId) {
        showStatus('data-grid-status', 'No table selected.', 'error');
        return;
    }
    try {
        const url = `/api/data/tables/${encodeURIComponent(state.currentTableId)}/export-excel`;
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showStatus('data-grid-status', err.error || 'Export failed.', 'error');
            return;
        }
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = (state.currentTableId || 'table') + '.xlsx';
        a.click();
        URL.revokeObjectURL(a.href);
        showStatus('data-grid-status', 'Excel downloaded.', 'success');
        showToast('Excel downloaded.', 'success');
    } catch (e) {
        showStatus('data-grid-status', e.message || 'Export failed.', 'error');
    }
}

async function exportTableToJson() {
    if (!state.currentTableId) {
        showStatus('data-grid-status', 'No table selected.', 'error');
        return;
    }
    try {
        const url = `/api/data/tables/${encodeURIComponent(state.currentTableId)}/export-json`;
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showStatus('data-grid-status', err.error || 'Export failed.', 'error');
            return;
        }
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = (state.currentTableId || 'table') + '.json';
        a.click();
        URL.revokeObjectURL(a.href);
        showStatus('data-grid-status', 'JSON downloaded.', 'success');
        showToast('JSON downloaded.', 'success');
    } catch (e) {
        showStatus('data-grid-status', e.message || 'Export failed.', 'error');
    }
}

async function importTableFromJsonFile(event) {
    const file = event.target && event.target.files[0];
    if (!file || !state.currentTableId) return;
    event.target.value = '';
    if (state.currentPermission === 'view' || state.currentPermission === 'view_nocopy') {
        showStatus('data-grid-status', 'Read-only: cannot import.', 'error');
        return;
    }
    try {
        const text = await file.text();
        const payload = JSON.parse(text);
        const columns = payload.columns || [];
        const rows = payload.rows || [];
        const res = await fetch(`/api/data/tables/${encodeURIComponent(state.currentTableId)}/import-json`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ columns, rows })
        });
        const data = await res.json();
        if (!data.success) {
            showStatus('data-grid-status', data.error || 'Import failed.', 'error');
            return;
        }
        showStatus('data-grid-status', 'Imported. Reloading grid.', 'success');
        showToast('Imported. Reloading grid.', 'success');
        loadDataGrid();
    } catch (e) {
        showStatus('data-grid-status', 'Invalid JSON or error: ' + (e.message || ''), 'error');
    }
}

async function saveDataGrid(isAuto = false) {
    if (!state.dataGridInitialized || !state.dataGrid) return;
    if (state.currentPermission === "view" || state.currentPermission === "view_nocopy") {
        showStatus('data-grid-status', 'Read-only access: cannot save.', 'error');
        return;
    }
    try {
        const columns = state.dataGrid.getColumnDefinitions();
        const rows = state.dataGrid.getData();

        const res = await fetch(`/api/data/grid?table=${encodeURIComponent(state.currentTableId)}`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ columns, rows })
        });
        const result = await res.json();
        if (result.success) {
            if (isAuto) {
                showStatus('data-grid-status', 'All changes saved.', 'success');
                showToast('All changes saved.', 'success');
            } else {
                showStatus('data-grid-status', 'Data saved.', 'success');
            showToast('Data saved.', 'success');
            }
        } else {
            showStatus('data-grid-status', result.error || 'Failed to save data.', 'error');
        }
    } catch (err) {
        showStatus('data-grid-status', `Error: ${err.message}`, 'error');
    }
}

// Data Tables: submit for admin review / promotion
async function submitCurrentTableForReview() {
    const tableId = state.currentTableId || '';
    if (!tableId || tableId === 'default') {
        showStatus('data-grid-status', 'Select a table to submit.', 'error');
        return;
    }
    try {
        showStatus('data-grid-status', 'Submitting for review…', 'info');
        const res = await fetch(`/api/data/tables/${encodeURIComponent(tableId)}/submit-review`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        const out = await res.json();
        if (!out.success) {
            showStatus('data-grid-status', out.error || 'Submit failed.', 'error');
            return;
        }
        showStatus('data-grid-status', 'Submitted for review. Admin can promote it.', 'success');
        showToast('Submitted for review.', 'success');
        await refreshTables();
    } catch (e) {
        showStatus('data-grid-status', e.message || 'Submit failed.', 'error');
    }
}

function deleteSelectedRows() {
    if (!state.dataGridInitialized || !state.dataGrid) return;
    
    // Try multiple methods to get selected rows
    let rowsToDelete = [];
    
    // Method 1: getSelectedRows() - returns row components
    const selectedRows = state.dataGrid.getSelectedRows();
    if (selectedRows && selectedRows.length > 0) {
        rowsToDelete = selectedRows;
    } else {
        // Method 2: getSelectedData() - returns row data, need to find components
        const selectedData = state.dataGrid.getSelectedData();
        if (selectedData && selectedData.length > 0) {
            const allRows = state.dataGrid.getRows();
            rowsToDelete = allRows.filter(row => {
                const rowData = row.getData();
                return selectedData.some(sel => {
                    // Compare by all fields to find matching row
                    return Object.keys(sel).every(key => rowData[key] === sel[key]);
                });
            });
        }
    }
    
    if (!rowsToDelete || rowsToDelete.length === 0) {
        showStatus('data-grid-status', 'No rows selected. Click on row numbers to select rows, then click Delete selected.', 'error');
        return;
    }
    
    // Delete rows
    rowsToDelete.forEach(row => {
        try {
            if (typeof row.delete === 'function') {
                row.delete();
            } else if (typeof row.deselect === 'function') {
                // Fallback: remove row by index
                const rowIndex = row.getPosition();
                state.dataGrid.deleteRow(rowIndex);
            }
        } catch (err) {
            console.warn('Error deleting row:', err);
        }
    });
    
    handleDataGridChanged();
    showStatus('data-grid-status', `${rowsToDelete.length} row(s) deleted.`, 'success');
}

function searchDataGrid(query) {
    if (!state.dataGridInitialized || !state.dataGrid) return;

    const value = (query || '').toString().trim().toLowerCase();

    if (!value) {
        state.dataGrid.clearFilter(true);
        return;
    }

    // Global search across all fields
    state.dataGrid.setFilter((data) => {
        for (const key in data) {
            if (Object.prototype.hasOwnProperty.call(data, key)) {
                const cellValue = data[key];
                if (cellValue !== null && cellValue !== undefined) {
                    if (String(cellValue).toLowerCase().includes(value)) {
                        return true;
                    }
                }
            }
        }
        return false;
    });
}

// Column management helpers
function renameSelectedColumn() {
    if (!state.dataGridInitialized || !state.dataGrid) return;
    if (!state.selectedColumnField) {
        showStatus('data-grid-status', 'Please click on a column header first.', 'error');
        return;
    }
    const col = state.dataGrid.getColumn(state.selectedColumnField);
    if (!col) {
        showStatus('data-grid-status', 'Column not found.', 'error');
        return;
    }
    const currentTitle = col.getDefinition().title || state.selectedColumnField;
    
    // Inline editing: replace label with input
    const label = document.getElementById('data-grid-column-label');
    if (!label) return;
    
    // Remove any existing input first
    const existingInput = label.parentNode.querySelector('input[data-column-rename]');
    if (existingInput) {
        existingInput.remove();
        label.style.display = '';
    }
    
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentTitle;
    input.setAttribute('data-column-rename', 'true');
    input.style.cssText = 'padding:4px 8px; border:2px solid #0f766e; border-radius:4px; font-size:0.95em; min-width:120px; outline:none;';
    input.onblur = function() {
        const nextTitle = input.value.trim();
        if (nextTitle && nextTitle !== currentTitle) {
            try {
                col.updateDefinition({ title: nextTitle });
                handleDataGridChanged();
                showStatus('data-grid-status', `Column renamed to "${nextTitle}".`, 'success');
            } catch (err) {
                showStatus('data-grid-status', `Error: ${err.message}`, 'error');
            }
        }
        label.textContent = nextTitle || currentTitle;
        label.style.display = '';
        input.remove();
    };
    input.onkeydown = function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            label.textContent = currentTitle;
            label.style.display = '';
            input.remove();
        }
    };
    
    label.style.display = 'none';
    label.parentNode.insertBefore(input, label);
    input.focus();
    input.select();
}

function deleteSelectedColumn() {
    if (!state.dataGridInitialized || !state.dataGrid) return;
    if (!state.selectedColumnField) {
        showStatus('data-grid-status', 'Please click on a column header first.', 'error');
        return;
    }
    
    const col = state.dataGrid.getColumn(state.selectedColumnField);
    if (!col) {
        showStatus('data-grid-status', 'Column not found.', 'error');
        return;
    }
    
    const def = col.getDefinition();
    const title = def.title || state.selectedColumnField;
    
    // No confirm popup - direct delete
    try {
        // Try deleteColumn first (Tabulator v5+)
        if (typeof state.dataGrid.deleteColumn === 'function') {
            state.dataGrid.deleteColumn(state.selectedColumnField);
        } else {
            // Fallback: remove column by updating column definitions
            const cols = state.dataGrid.getColumnDefinitions();
            const filtered = cols.filter(c => c.field !== state.selectedColumnField);
            state.dataGrid.setColumns(filtered);
        }
        
        // Redraw to ensure layout is correct
        state.dataGrid.redraw(true);
        
        state.selectedColumnField = null;
        const label = document.getElementById('data-grid-column-label');
        if (label) {
            label.textContent = 'None';
            label.style.color = '#374151';
            label.style.fontWeight = 'normal';
        }
        handleDataGridChanged();
        showStatus('data-grid-status', `Column "${title}" deleted.`, 'success');
    } catch (err) {
        showStatus('data-grid-status', `Error: ${err.message}`, 'error');
    }
}

function addDataColumn() {
    if (!state.dataGridInitialized || !state.dataGrid) return;

    const cols = state.dataGrid.getColumnDefinitions() || [];
    const nextIndex = cols.length + 1;
    const field = `c${nextIndex}`;
    const colDef = {
        title: `Col ${nextIndex}`,
        field,
        editor: 'input'
    };

    try {
        state.dataGrid.addColumn(colDef, false, cols.length ? cols[cols.length - 1].field : undefined);
        // Redraw to ensure layout is correct
        state.dataGrid.redraw(true);
        state.selectedColumnField = field;
        const label = document.getElementById('data-grid-column-label');
        if (label) {
            label.textContent = colDef.title;
            label.style.color = '#0f766e';
            label.style.fontWeight = '600';
        }
        handleDataGridChanged();
        
        // Automatically trigger rename so user can immediately type the column name
        setTimeout(() => {
            renameSelectedColumn();
        }, 100);
    } catch (err) {
        showStatus('data-grid-status', `Error adding column: ${err.message}`, 'error');
    }
}

function addDataRow() {
    if (!state.dataGridInitialized || !state.dataGrid) return;
    try {
        state.dataGrid.addRow({});
        handleDataGridChanged();
    } catch (err) {
        showStatus('data-grid-status', `Error adding row: ${err.message}`, 'error');
    }
}

// Multiple logical tables support
function changeDataTable(tableId) {
    const id = (tableId || '').trim() || 'default';
    state.currentTableId = id;
    state.selectedColumnField = null; // Reset selected column

    if (state.dataGridInitialized && state.dataGrid) {
        // Clear both data and columns to start fresh
        state.dataGrid.clearData();
        // Reset to default columns and a few empty rows
        state.dataGrid.setColumns(buildDefaultColumns());
        state.dataGrid.setData(buildBlankRows(DATA_DEFAULT_ROWS));
        
        // Reset column label
        const label = document.getElementById('data-grid-column-label');
        if (label) {
            label.textContent = 'None';
            label.style.color = '#374151';
            label.style.fontWeight = 'normal';
        }
        
        // Now load from backend (will override if data exists, otherwise stays empty)
        loadDataGrid();
    }
}

function createNewDataTable() {
    // Create inline input in the "Start a new table" row
    const startRow = document.getElementById('tables-start-row');
    if (!startRow) return;

    // Avoid duplicates
    if (document.getElementById('new-table-inline')) return;

    const card = document.createElement('div');
    card.id = 'new-table-inline';
    card.style.cssText = 'width: 220px; border: 1px dashed #93c5fd; border-radius: 14px; padding: 14px; background: #f8fafc;';

    const title = document.createElement('div');
    title.textContent = 'New table';
    title.style.cssText = 'font-weight:800; color:#111827; margin-bottom:8px;';

    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'employees_2026';
    input.className = 'form-control';
    input.style.cssText = 'padding:10px 12px; border-radius:10px;';

    const help = document.createElement('div');
    help.textContent = 'Press Enter to create • Esc to cancel';
    help.style.cssText = 'margin-top:8px; color:#6b7280; font-size:0.85rem;';

    card.appendChild(title);
    card.appendChild(input);
    card.appendChild(help);
    startRow.prepend(card);
    input.focus();

    input.onkeydown = async (e) => {
        if (e.key === 'Escape') {
            card.remove();
            return;
        }
        if (e.key !== 'Enter') return;
        e.preventDefault();
        const name = (input.value || '').trim();
        if (!/^[A-Za-z0-9_-]+$/.test(name)) {
            showStatus('data-grid-status', 'Table id must contain only letters, numbers, dash or underscore.', 'error');
            return;
        }

        try {
            const res = await fetch('/api/data/tables', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ table_id: name, title: name })
            });
            const result = await res.json();
            if (!result.success) {
                showStatus('data-grid-status', result.error || 'Failed to create table.', 'error');
                return;
            }
            await refreshTables();
            card.remove();
            selectDataTable(result.table.id);
        } catch (err) {
            showStatus('data-grid-status', `Error: ${err.message}`, 'error');
        }
    };
}

function selectDataTable(tableId) {
    state.currentTableId = tableId;
    state.selectedColumnField = null; // Reset selected column
    showGridPanel();
    
    if (state.dataGridInitialized && state.dataGrid) {
        // Clear both data and columns to start fresh
        state.dataGrid.clearData();
        // Reset to default columns and a few empty rows
        state.dataGrid.setColumns(buildDefaultColumns());
        state.dataGrid.setData(buildBlankRows(DATA_DEFAULT_ROWS));
        
        // Reset column label
        const label = document.getElementById('data-grid-column-label');
        if (label) {
            label.textContent = 'None';
            label.style.color = '#374151';
            label.style.fontWeight = 'normal';
        }
        
        // Now load from backend (will override if data exists, otherwise stays empty)
        loadDataGrid();
    }
    // Update tables hub active states
    renderTablesHub();
}

// PSD File Upload
async function loadCreativeFonts(selectedId = null) {
    const select = document.getElementById('creative-font-select');
    const status = document.getElementById('creative-font-status');
    if (!select) return;
    try {
        const response = await fetch('/api/creative/fonts', { credentials: 'include' });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.detail || data.error || 'Could not load fonts');
        }
        state.creativeFonts = data.fonts || [];
        const current = selectedId !== null ? selectedId : select.value;
        select.innerHTML = '<option value="">Automatic fallback font</option>' +
            state.creativeFonts.map(font => {
                const label = `${font.family} - ${font.style} (${font.filename})`;
                return `<option value="${escapeHtml(font.id)}">${escapeHtml(label)}</option>`;
            }).join('');
        if (current && state.creativeFonts.some(font => font.id === current)) {
            select.value = current;
        }
        if (status) {
            status.textContent = `${state.creativeFonts.length} readable font(s) available.`;
            status.className = 'status-box info';
        }
        renderPsdLayerEditor();
    } catch (error) {
        if (status) {
            status.textContent = error.message;
            status.className = 'status-box error';
        }
    }
}

async function handleCreativeFontUpload(event) {
    const file = event.target.files && event.target.files[0];
    const name = document.getElementById('creative-font-file-name');
    const status = document.getElementById('creative-font-status');
    if (!file) return;
    if (name) name.textContent = file.name;
    if (status) {
        status.textContent = 'Validating and uploading font...';
        status.className = 'status-box info';
    }
    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await fetch('/api/creative/fonts', {
            method: 'POST',
            credentials: 'include',
            body: formData
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.detail || data.error || 'Font upload failed');
        }
        await loadCreativeFonts(data.font.id);
        if (status) {
            status.textContent = data.created
                ? `${data.font.family} ${data.font.style} uploaded and selected.`
                : 'This font already exists and has been selected.';
            status.className = 'status-box success';
        }
        showToast(data.created ? 'Font uploaded.' : 'Font already exists.', 'success');
        scheduleAutoPreview();
    } catch (error) {
        if (status) {
            status.textContent = error.message;
            status.className = 'status-box error';
        }
        showToast(error.message, 'error');
    } finally {
        event.target.value = '';
    }
}

async function handlePSDUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    document.getElementById('psd-file-name').textContent = file.name;
    
    const formData = new FormData();
    formData.append('file', file);
    
    showStatus('process-status', 'Uploading PSD file...', 'info');
    
    try {
        const response = await fetch('/api/upload-psd', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            showToast(result.detail || result.error || 'Upload failed', 'error');
        }
        if (result.success) {
            state.psdFileId = result.file_id;
            state.layers = result.layers;
            state.layerOverrides = {};
            const templateSel = document.getElementById('psd-template-select');
            if (templateSel) { templateSel.value = ''; }
            const saveBtn = document.getElementById('save-as-template-btn');
            if (saveBtn) { saveBtn.style.display = 'inline-block'; }
            renderLayersInfo();
            
            showStatus('process-status', 'PSD file uploaded successfully!', 'success');
            showToast('PSD uploaded.', 'success');
            
            showMappingSection();
            syncCreativeWorkflowSections();
        } else {
            showStatus('process-status', `Error: ${result.error}`, 'error');
        }
    } catch (error) {
        showStatus('process-status', `Error: ${error.message}`, 'error');
    }
}

// Data File Upload
async function handleDataUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    document.getElementById('data-file-name').textContent = file.name;
    
    const formData = new FormData();
    formData.append('file', file);
    
    showStatus('process-status', 'Uploading data file...', 'info');
    
    try {
        const response = await fetch('/api/upload-data', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        if (!response.ok) {
            showToast(result.detail || result.error || 'Upload failed', 'error');
        }
        if (result.success) {
            state.dataFileId = result.file_id;
            state.columns = result.columns;
            
            // Display column info
            const columnsInfo = document.getElementById('data-columns-info');
            columnsInfo.innerHTML = `
                <strong>✓ Data file loaded successfully!</strong><br>
                Found ${result.columns.length} columns, ${result.row_count} rows
            `;
            columnsInfo.style.display = 'block';
            
            showStatus('process-status', 'Data file uploaded successfully!', 'success');
            showToast('Data file uploaded.', 'success');
            
            if (state.psdFileId) {
                showMappingSection();
            }
            syncCreativeWorkflowSections();
        } else {
            showStatus('process-status', `Error: ${result.error || result.detail}`, 'error');
            showToast(result.detail || result.error || 'Upload failed', 'error');
        }
    } catch (error) {
        showStatus('process-status', `Error: ${error.message}`, 'error');
        showToast(error.message, 'error');
    }
}

// Show mapping section
function showMappingSection() {
    const section = document.getElementById('mapping-section');
    if (section) {
        section.style.display = state.psdFileId ? 'block' : 'none';
    }
    renderMappingRows();
    renderCreativeLayerPicker();
}

function renderCreativeLayerPicker() {
    const pickerWrap = document.getElementById('creative-layer-picker');
    const picker = document.getElementById('creative-layer-picker-select');
    const hint = document.getElementById('creative-mapping-hint');
    if (!pickerWrap || !picker || !hint) return;

    if (!state.psdFileId) {
        pickerWrap.style.display = 'none';
        picker.innerHTML = '';
        hint.textContent = 'Upload a PSD to load layer names.';
        return;
    }

    const layers = state.layers || [];
    if (!layers.length) {
        pickerWrap.style.display = 'none';
        picker.innerHTML = '';
        hint.textContent = state.dataFileId
            ? 'Now choose Read layers or upload another PSD to load the layer names.'
            : 'Layer names will appear here after the PSD is read. Then upload your Excel/CSV file to map columns.';
        return;
    }

    pickerWrap.style.display = 'block';
    picker.innerHTML = layers.map((layer, index) => {
        const label = layer.name || `Layer ${index + 1}`;
        const suffix = layer.is_text_layer ? ' (Text)' : '';
        return `<option value="${escapeHtml(label)}">${escapeHtml(label + suffix)}</option>`;
    }).join('');
    hint.textContent = state.dataFileId
        ? 'Select a layer name below or from the detected layers list, then map it to a column.'
        : 'Layer names are loaded. Upload your Excel/CSV file next, then map the layers.';
}

function addSelectedCreativeLayer() {
    const picker = document.getElementById('creative-layer-picker-select');
    if (!picker || !picker.value) {
        showStatus('process-status', 'No layer selected', 'error');
        return;
    }
    applyLayerNameToMapping(picker.value);
}

function renderLayersInfo() {
    const datalist = document.getElementById('layer-names');
    if (datalist) {
        datalist.innerHTML = '';
        (state.layers || []).forEach(layer => {
            const option = document.createElement('option');
            option.value = layer.name;
            datalist.appendChild(option);
        });
    }

    const layersInfo = document.getElementById('psd-layers-info');
    const browser = document.getElementById('psd-layers-browser');
    const summary = document.getElementById('psd-layers-summary');
    const search = document.getElementById('psd-layer-search');
    if (!layersInfo) return;
    if (!state.layers || state.layers.length === 0) {
        layersInfo.style.display = 'none';
        layersInfo.innerHTML = '';
        if (browser) browser.style.display = 'none';
        if (summary) summary.textContent = '';
        if (search) search.value = '';
        renderCreativeLayerPicker();
        return;
    }
    const textLayerCount = state.layers.filter(layer => layer.is_text_layer).length;
    layersInfo.innerHTML = `
        <strong>✓ PSD file loaded successfully!</strong><br>
        Found ${state.layers.length} layers. Text layers: ${textLayerCount}
    `;
    layersInfo.style.display = 'block';
    if (browser) browser.style.display = 'block';
    if (summary) summary.textContent = `${state.layers.length} total layers · ${textLayerCount} text layers`;
    renderCreativeLayerList();
    renderPsdLayerEditor();
    loadPsdCanvasPreview();
    renderCreativeLayerPicker();
}

async function loadPsdCanvasPreview() {
    const image = document.getElementById('psd-editor-canvas');
    const empty = document.getElementById('psd-editor-empty');
    if (!image || !state.psdFileId) return;
    const formData = new FormData();
    formData.append('psd_file_id', state.psdFileId);
    try {
        const response = await fetch('/api/creative/canvas-preview', {
            method: 'POST', body: formData, credentials: 'include'
        });
        const data = await response.json();
        if (!response.ok || !data.preview_url) throw new Error(data.detail || 'Preview failed');
        image.src = data.preview_url;
        image.style.display = 'block';
        if (empty) empty.style.display = 'none';
    } catch (error) {
        if (empty) {
            empty.textContent = error.message;
            empty.style.display = 'block';
        }
    }
}

function getLayerOverride(layer) {
    const name = layer.name || '';
    if (!state.layerOverrides[name]) {
        state.layerOverrides[name] = {
            enabled: true,
            type: layer.is_text_layer ? 'text' : 'image',
            source: 'column',
            column: '',
            value: '',
            font_id: '',
            font_size: 0,
            image_file_id: ''
        };
    }
    return state.layerOverrides[name];
}

function updateLayerOverride(layerName, field, value, rerender = true) {
    const layer = (state.layers || []).find(item => item.name === layerName);
    if (!layer) return;
    const override = getLayerOverride(layer);
    override[field] = value;
    if (field === 'source' && value === 'constant' && !override.value) {
        override.value = layer.text || '';
    }
    if (rerender) renderPsdLayerEditor();
    scheduleAutoPreview();
}

async function uploadLayerReplacement(layerName, input) {
    const file = input.files && input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    showStatus('psd-editor-status', `Uploading ${file.name}...`, 'info');
    try {
        const response = await fetch('/api/upload-image', {
            method: 'POST', body: formData, credentials: 'include'
        });
        const data = await response.json();
        if (!response.ok || !data.file_id) throw new Error(data.detail || 'Upload failed');
        updateLayerOverride(layerName, 'image_file_id', data.file_id);
        updateLayerOverride(layerName, 'source', 'image');
        showStatus('psd-editor-status', `${file.name} is ready for preview and batch rendering.`, 'success');
    } catch (error) {
        showStatus('psd-editor-status', error.message, 'error');
    }
}

function renderPsdLayerEditor() {
    const container = document.getElementById('psd-layer-editor-list');
    const card = document.getElementById('psd-layer-editor-card');
    if (!container || !card) return;
    const layers = state.layers || [];
    card.style.display = layers.length ? 'block' : 'none';
    container.innerHTML = '';
    layers.forEach(layer => {
        const override = getLayerOverride(layer);
        const row = document.createElement('div');
        row.style.cssText = 'padding:14px; border:1px solid #e5e7eb; border-radius:10px; background:#fff; display:grid; gap:10px;';
        const fontOptions = '<option value="">Global/default font</option>' +
            (state.creativeFonts || []).map(font =>
                `<option value="${escapeHtml(font.id)}"${override.font_id === font.id ? ' selected' : ''}>${escapeHtml(font.family + ' - ' + font.style)}</option>`
            ).join('');
        const columnOptions = '<option value="">Select data column</option>' +
            (state.columns || []).map(column =>
                `<option value="${escapeHtml(column)}"${override.column === column ? ' selected' : ''}>${escapeHtml(column)}</option>`
            ).join('');
        const bbox = Array.isArray(layer.bbox) ? layer.bbox.join(', ') : 'No bounds';
        row.innerHTML = `
            <div style="display:flex; gap:10px; align-items:center; justify-content:space-between; flex-wrap:wrap;">
                <div><strong>${escapeHtml(layer.name || 'Unnamed layer')}</strong>
                    <span style="color:#6b7280; margin-left:8px;">${layer.is_text_layer ? 'Text' : 'Image'} · ${escapeHtml(bbox)}</span>
                </div>
                <label><input type="checkbox" ${override.enabled ? 'checked' : ''}
                    onchange="updateLayerOverride(${JSON.stringify(layer.name)}, 'enabled', this.checked)"> Apply override</label>
            </div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px;">
                <select class="form-control" onchange="updateLayerOverride(${JSON.stringify(layer.name)}, 'source', this.value)">
                    <option value="column"${override.source === 'column' ? ' selected' : ''}>Data column</option>
                    ${layer.is_text_layer ? `<option value="constant"${override.source === 'constant' ? ' selected' : ''}>Fixed text</option>` : ''}
                    <option value="image"${override.source === 'image' ? ' selected' : ''}>Uploaded image</option>
                </select>
                ${override.source === 'column' ? `<select class="form-control" onchange="updateLayerOverride(${JSON.stringify(layer.name)}, 'column', this.value)">${columnOptions}</select>` : ''}
                ${override.source === 'constant' ? `<input class="form-control" value="${escapeHtml(override.value || layer.text || '')}" placeholder="Replacement text" oninput="updateLayerOverride(${JSON.stringify(layer.name)}, 'value', this.value, false)">` : ''}
                ${override.source === 'image' ? `<input class="form-control" type="file" accept=".png,.jpg,.jpeg,.webp" onchange="uploadLayerReplacement(${JSON.stringify(layer.name)}, this)">` : ''}
                ${layer.is_text_layer ? `<select class="form-control" onchange="updateLayerOverride(${JSON.stringify(layer.name)}, 'font_id', this.value)">${fontOptions}</select>
                    <input class="form-control" type="number" min="8" max="300" value="${override.font_size || ''}" placeholder="Auto font size" onchange="updateLayerOverride(${JSON.stringify(layer.name)}, 'font_size', parseInt(this.value || 0))">` : ''}
            </div>
        `;
        container.appendChild(row);
    });
}

function getActiveLayerOverrides() {
    const result = {};
    Object.entries(state.layerOverrides || {}).forEach(([name, override]) => {
        if (!override.enabled) return;
        if (override.source === 'column' && !override.column) return;
        if (override.source === 'image' && !override.image_file_id) return;
        result[name] = override;
    });
    return result;
}

function getFilteredCreativeLayers() {
    const search = document.getElementById('psd-layer-search');
    const query = search ? search.value.trim().toLowerCase() : '';
    return (state.layers || []).filter(layer => {
        if (!query) return true;
        return (layer.name || '').toLowerCase().includes(query);
    });
}

function renderCreativeLayerList() {
    const list = document.getElementById('psd-layers-list');
    if (!list) return;
    const filteredLayers = getFilteredCreativeLayers();
    list.innerHTML = '';

    if (!state.layers || state.layers.length === 0) {
        return;
    }

    if (filteredLayers.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding: 12px; border: 1px dashed #d1d5db; border-radius: 10px; color: #6b7280;';
        empty.textContent = 'No layers match your search.';
        list.appendChild(empty);
        return;
    }

    filteredLayers.forEach((layer, index) => {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; gap:10px; align-items:center; justify-content:space-between; padding:10px 12px; border:1px solid #e5e7eb; border-radius:10px; background:#fff;';

        const meta = document.createElement('div');
        meta.style.cssText = 'min-width:0; flex:1;';

        const top = document.createElement('div');
        top.style.cssText = 'display:flex; align-items:center; gap:8px; flex-wrap:wrap;';

        const nameBtn = document.createElement('button');
        nameBtn.type = 'button';
        nameBtn.className = 'btn';
        nameBtn.style.cssText = 'padding:0; border:none; background:none; color:#111827; font-weight:700; cursor:pointer; text-align:left;';
        nameBtn.textContent = layer.name || `Layer ${index + 1}`;
        nameBtn.title = 'Use this layer in mapping';
        nameBtn.onclick = () => applyLayerNameToMapping(layer.name || '');

        const badge = document.createElement('span');
        badge.style.cssText = `display:inline-flex; align-items:center; padding:3px 8px; border-radius:999px; font-size:0.75rem; font-weight:700; ${layer.is_text_layer ? 'background:#dcfce7; color:#166534;' : 'background:#e5e7eb; color:#374151;'}`;
        badge.textContent = layer.is_text_layer ? 'Text layer' : 'Layer';

        top.appendChild(nameBtn);
        top.appendChild(badge);

        const sub = document.createElement('div');
        sub.style.cssText = 'margin-top:4px; color:#6b7280; font-size:0.86rem;';
        sub.textContent = 'Click name or Use to fill mapping, or Copy to clipboard.';

        meta.appendChild(top);
        meta.appendChild(sub);

        const actions = document.createElement('div');
        actions.style.cssText = 'display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end;';

        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'btn';
        copyBtn.textContent = 'Copy';
        copyBtn.onclick = () => copyCreativeLayerName(layer.name || '');

        const useBtn = document.createElement('button');
        useBtn.type = 'button';
        useBtn.className = 'btn btn-primary';
        useBtn.textContent = 'Use in mapping';
        useBtn.onclick = () => applyLayerNameToMapping(layer.name || '');

        actions.appendChild(copyBtn);
        actions.appendChild(useBtn);
        row.appendChild(meta);
        row.appendChild(actions);
        list.appendChild(row);
    });
}

function filterCreativeLayers() {
    renderCreativeLayerList();
}

async function readCreativeLayers() {
    if (!state.psdFileId) {
        showStatus('process-status', 'Upload or select a PSD first', 'error');
        return;
    }

    showStatus('process-status', 'Reading PSD layers...', 'info');
    const formData = new FormData();
    formData.append('psd_file_id', state.psdFileId);

    try {
        const res = await fetch('/api/creative/read-layers', {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            showStatus('process-status', data.detail || data.error || 'Failed to read layers', 'error');
            return;
        }
        state.layers = data.layers || [];
        renderLayersInfo();
        showMappingSection();
        syncCreativeWorkflowSections();
        showStatus('process-status', `Read ${state.layers.length} layer(s) successfully.`, 'success');
        showToast('Layers loaded.', 'success');
    } catch (e) {
        showStatus('process-status', 'Error: ' + e.message, 'error');
    }
}

async function copyCreativeLayerName(layerName) {
    if (!layerName) return;
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(layerName);
        } else {
            const temp = document.createElement('textarea');
            temp.value = layerName;
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            temp.remove();
        }
        showToast(`Copied layer name: ${layerName}`, 'success');
    } catch (e) {
        showStatus('process-status', 'Could not copy layer name', 'error');
    }
}

function applyLayerNameToMapping(layerName) {
    if (!layerName) return;
    let targetIndex = state.layerMapping.findIndex(item => !item.layer);
    if (targetIndex === -1) {
        state.layerMapping.push({ layer: '', column: '' });
        targetIndex = state.layerMapping.length - 1;
    }
    state.layerMapping[targetIndex].layer = layerName;
    showMappingSection();
    syncCreativeWorkflowSections();
    showToast(`Layer "${layerName}" added to mapping.`, 'success');

    setTimeout(() => {
        const inputs = document.querySelectorAll('#layer-mapping-container input[list="layer-names"]');
        const target = inputs[targetIndex];
        if (target) {
            target.focus();
            target.select();
        }
    }, 0);
}

function refreshCreativeActionButtons() {
    const readLayersBtn = document.getElementById('read-layers-btn');
    if (readLayersBtn) {
        readLayersBtn.disabled = !state.psdFileId;
    }

    const processHint = document.getElementById('creative-process-hint');
    const validMappings = state.layerMapping.filter(m => m.layer && m.column);
    if (processHint) {
        if (!state.psdFileId) {
            processHint.textContent = 'Upload a PSD first.';
        } else if (!state.dataFileId) {
            processHint.textContent = 'PSD loaded. Upload your Excel/CSV data file to continue.';
        } else if (validMappings.length === 0) {
            processHint.textContent = 'Choose at least one layer and map it to a data column.';
        } else if (!state.filenameFields.length) {
            processHint.textContent = 'Select at least one filename field to enable generate.';
        } else {
            processHint.textContent = 'Everything is ready. You can preview or generate now.';
        }
    }

    const generateBtn = document.getElementById('creative-generate-btn');
    if (generateBtn) {
        generateBtn.disabled = !(state.psdFileId && state.dataFileId && validMappings.length > 0 && state.filenameFields.length > 0);
    }
}

function syncCreativeWorkflowSections() {
    const filenameSection = document.getElementById('filename-section');
    const processSection = document.getElementById('process-section');
    if (!filenameSection || !processSection) {
        refreshCreativeActionButtons();
        return;
    }

    const hasFiles = !!state.psdFileId && !!state.dataFileId;
    const validMappings = state.layerMapping.filter(m => m.layer && m.column);

    processSection.style.display = 'block';

    if (!state.psdFileId) {
        document.getElementById('mapping-section').style.display = 'none';
        filenameSection.style.display = 'none';
        refreshCreativeActionButtons();
        return;
    }

    showMappingSection();

    if (!hasFiles || validMappings.length === 0) {
        filenameSection.style.display = 'none';
        refreshCreativeActionButtons();
        return;
    }

    showFilenameSection();
    refreshCreativeActionButtons();
}

// Render mapping rows
function renderMappingRows() {
    const container = document.getElementById('layer-mapping-container');
    container.innerHTML = '';
    
    state.layerMapping.forEach((mapping, index) => {
        const row = createMappingRow(mapping.layer, mapping.column, index);
        container.appendChild(row);
    });
    
    // Add at least one empty row
    if (state.layerMapping.length === 0) {
        addMappingRow();
    }
}

// Create mapping row
function createMappingRow(layerName = '', columnName = '', index = null) {
    const row = document.createElement('div');
    row.className = 'mapping-row';
    
    const idx = index !== null ? index : state.layerMapping.length;
    
    // Layer name input
    const layerInput = document.createElement('input');
    layerInput.type = 'text';
    layerInput.className = 'form-control';
    layerInput.placeholder = 'Layer name';
    layerInput.value = layerName;
    layerInput.list = 'layer-names';
    layerInput.onchange = () => updateMapping(idx, 'layer', layerInput.value);
    
    // Column select
    const columnSelect = document.createElement('select');
    columnSelect.className = 'form-control';
    columnSelect.innerHTML = '<option value="">Select column...</option>';
    state.columns.forEach(col => {
        const option = document.createElement('option');
        option.value = col;
        option.textContent = col;
        if (col === columnName) option.selected = true;
        columnSelect.appendChild(option);
    });
    columnSelect.onchange = () => updateMapping(idx, 'column', columnSelect.value);
    
    // Remove button
    const removeBtn = document.createElement('button');
    removeBtn.className = 'btn';
    removeBtn.textContent = '✕';
    removeBtn.style.background = '#dc3545';
    removeBtn.style.color = 'white';
    removeBtn.onclick = () => removeMappingRow(idx);
    
    row.appendChild(layerInput);
    row.appendChild(columnSelect);
    row.appendChild(removeBtn);
    
    return row;
}

// Add mapping row
function addMappingRow() {
    state.layerMapping.push({ layer: '', column: '' });
    renderMappingRows();
}

// Update mapping
function updateMapping(index, field, value) {
    if (state.layerMapping[index]) {
        state.layerMapping[index][field] = value;
    }
    syncCreativeWorkflowSections();
    scheduleAutoPreview();
}

// Remove mapping row
function removeMappingRow(index) {
    state.layerMapping.splice(index, 1);
    renderMappingRows();
    syncCreativeWorkflowSections();
    scheduleAutoPreview();
}

// --- Creative auto preview (debounced) ---
let creativeAutoPreviewTimer = null;

function scheduleAutoPreview() {
    const autoCheckbox = document.getElementById('auto-preview');
    if (!autoCheckbox || !autoCheckbox.checked) {
        return;
    }
    if (creativeAutoPreviewTimer) {
        clearTimeout(creativeAutoPreviewTimer);
    }
    creativeAutoPreviewTimer = setTimeout(() => {
        // Ignore errors in background preview
        runPreview().catch(() => {});
    }, 800);
}

// Show filename fields section
function showFilenameSection() {
    // Validate mappings
    const validMappings = state.layerMapping.filter(m => m.layer && m.column);
    if (validMappings.length === 0) {
        showStatus('process-status', 'Please add at least one valid layer-column mapping', 'error');
        return;
    }
    
    document.getElementById('filename-section').style.display = 'block';
    document.getElementById('process-section').style.display = 'block';
    
    const selectedFields = new Set(state.filenameFields || []);
    const container = document.getElementById('filename-fields-container');
    container.innerHTML = '';
    refreshCreativeActionButtons();

    const group = document.createElement('div');
    group.className = 'checkbox-group';
    
    state.columns.forEach((col, index) => {
        const item = document.createElement('div');
        item.className = 'checkbox-item';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `filename-${index}`;
        checkbox.value = col;
        checkbox.checked = selectedFields.has(col);
        checkbox.onchange = () => updateFilenameFields();
        
        const label = document.createElement('label');
        label.htmlFor = `filename-${index}`;
        label.textContent = col;
        
        item.appendChild(checkbox);
        item.appendChild(label);
        group.appendChild(item);
    });

    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'btn btn-primary';
    confirmBtn.textContent = 'Confirm';
    confirmBtn.style.marginTop = '15px';
    confirmBtn.onclick = () => confirmFilenameFields();

    container.appendChild(group);
    container.appendChild(confirmBtn);
    updateFilenameFields();
}

// Update filename fields
function updateFilenameFields() {
    state.filenameFields = Array.from(document.querySelectorAll('#filename-fields-container input[type="checkbox"]:checked'))
        .map(cb => cb.value);
    refreshCreativeActionButtons();
    scheduleAutoPreview();
}

// Confirm filename fields
function confirmFilenameFields() {
    if (state.filenameFields.length === 0) {
        showStatus('process-status', 'Please select at least one field for filename', 'error');
        return;
    }
    showStatus('process-status', `Selected ${state.filenameFields.length} field(s) for filename`, 'success');
}

// Creative: PSD template library
async function loadCreativeTemplates() {
    const sel = document.getElementById('psd-template-select');
    const catFilter = document.getElementById('psd-template-category-filter');
    if (!sel) return;
    try {
        const res = await fetch('/api/creative/templates', { credentials: 'include' });
        const data = await res.json();
        const allTemplates = data.templates || [];
        const categories = [...new Set(allTemplates.map(t => (t.category || '').trim()).filter(Boolean))].sort();
        if (catFilter) {
            const currentCat = catFilter.value;
            catFilter.innerHTML = '<option value="">All categories</option>' + categories.map(c => `<option value="${escapeHtml(c)}"${c === currentCat ? ' selected' : ''}>${escapeHtml(c)}</option>`).join('');
        }
        const category = catFilter && catFilter.value ? catFilter.value : '';
        const templates = category ? allTemplates.filter(t => (t.category || '') === category) : allTemplates;
        sel.innerHTML = '<option value="">— Upload new or select template —</option>' +
            templates.map(t => `<option value="${t.id}" data-file-path="${escapeHtml(t.file_path)}">${escapeHtml(t.name)}${t.category ? ' (' + escapeHtml(t.category) + ')' : ''}</option>`).join('');
    } catch (e) {
        console.warn('Load templates failed', e);
    }
}

async function loadCreativeJobs() {
    const listEl = document.getElementById('creative-jobs-list');
    if (!listEl) return;
    try {
        const res = await fetch('/api/creative/jobs', { credentials: 'include' });
        const data = await res.json();
        if (!data.success) {
            listEl.innerHTML = '<p style="color:#6b7280;">Failed to load job history.</p>';
            return;
        }
        const jobs = data.jobs || [];
        if (jobs.length === 0) {
            listEl.innerHTML = '<p style="color:#6b7280;">No Creative jobs yet.</p>';
            return;
        }
        listEl.innerHTML = '<table class="form-control" style="width:100%; border-collapse:collapse;"><thead><tr style="border-bottom:1px solid #e5e7eb;"><th style="text-align:left; padding:8px;">Job</th><th style="text-align:left; padding:8px;">Status</th><th style="text-align:left; padding:8px;">Date</th><th style="text-align:left; padding:8px;">Rows</th><th></th></tr></thead><tbody>' +
            jobs.map(j => `
                <tr style="border-bottom:1px solid #e5e7eb;">
                    <td style="padding:8px;">#${j.job_id}</td>
                    <td style="padding:8px;">${escapeHtml(j.status)}</td>
                    <td style="padding:8px;">${escapeHtml(j.created_at || '')}</td>
                    <td style="padding:8px;">${j.row_count || 0}</td>
                    <td style="padding:8px;">${j.zip_link ? `<a href="${j.zip_link}" class="btn" style="padding:4px 8px;">Download ZIP</a>` : ''}</td>
                </tr>
            `).join('') + '</tbody></table>';
    } catch (e) {
        listEl.innerHTML = '<p style="color:#ef4444;">Error loading job history.</p>';
    }
}

function onPsdTemplateSelect() {
    const sel = document.getElementById('psd-template-select');
    const val = sel && sel.value;
    if (!val) {
        state.psdFileId = null;
        state.layers = [];
        state.layerOverrides = {};
        document.getElementById('psd-file-name').textContent = '';
        document.getElementById('save-as-template-btn').style.display = 'none';
        renderLayersInfo();
        syncCreativeWorkflowSections();
        return;
    }
    const opt = sel.selectedOptions[0];
    const filePath = opt && opt.getAttribute('data-file-path');
    if (!filePath) return;
    state.psdFileId = filePath;
    state.layerOverrides = {};
    document.getElementById('psd-file-name').textContent = opt.textContent;
    document.getElementById('save-as-template-btn').style.display = 'none';
    fetch('/api/creative/templates/' + val + '/layers', { credentials: 'include' })
        .then(r => r.json())
        .then(data => {
            if (data.layers) {
                state.layers = data.layers;
                renderLayersInfo();
                showMappingSection();
                syncCreativeWorkflowSections();
            }
        })
        .catch(() => showStatus('process-status', 'Failed to load template layers', 'error'));
}

async function saveCurrentPsdAsTemplate() {
    if (!state.psdFileId) {
        showStatus('process-status', 'Upload a PSD first', 'error');
        return;
    }
    const name = prompt('Template name:');
    if (!name || !name.trim()) return;
    const category = prompt('Category or tag (optional):') || '';
    try {
        const res = await fetch('/api/creative/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ name: name.trim(), file_id: state.psdFileId, category: category.trim() })
        });
        const data = await res.json();
        if (data.success) {
            showStatus('process-status', 'Template saved.', 'success');
            showToast('Template saved.', 'success');
            loadCreativeTemplates();
        } else {
            showStatus('process-status', data.error || 'Failed', 'error');
        }
    } catch (e) {
        showStatus('process-status', 'Error: ' + e.message, 'error');
    }
}

function getWatermarkConfig() {
    const enabled = document.getElementById('watermark-enabled')?.checked || false;
    if (!enabled) return null;
    
    const type = document.getElementById('watermark-type')?.value || 'text';
    const position = document.getElementById('watermark-position')?.value || 'bottom-right';
    const opacity = (document.getElementById('watermark-opacity')?.value || 50) / 100;
    
    const config = {
        enabled: true,
        type: type,
        position: position,
        opacity: opacity
    };
    
    if (type === 'text') {
        const text = document.getElementById('watermark-text')?.value || '';
        const fontSize = parseInt(document.getElementById('watermark-font-size')?.value || 24);
        if (!text) return null; // No watermark if text is empty
        config.value = text;
        config.font_size = fontSize;
    } else {
        const imageInput = document.getElementById('watermark-image');
        if (!imageInput?.files?.[0]) return null; // No watermark if no image
        // For preview, we'll need to handle this differently - for now return null
        // In production, you'd upload the watermark image first and get a file_id
        return null; // Image watermark not supported in preview yet
    }
    
    return config;
}

function toggleWatermarkSettings() {
    const enabled = document.getElementById('watermark-enabled')?.checked || false;
    const settings = document.getElementById('watermark-settings');
    if (settings) {
        settings.style.display = enabled ? 'block' : 'none';
    }
    scheduleAutoPreview();
}

function toggleWatermarkType() {
    const type = document.getElementById('watermark-type')?.value || 'text';
    const textGroup = document.getElementById('watermark-text-group');
    const imageGroup = document.getElementById('watermark-image-group');
    const textSizeGroup = document.getElementById('watermark-text-size-group');
    
    if (textGroup) textGroup.style.display = type === 'text' ? 'block' : 'none';
    if (imageGroup) imageGroup.style.display = type === 'image' ? 'block' : 'none';
    if (textSizeGroup) textSizeGroup.style.display = type === 'text' ? 'block' : 'none';
    scheduleAutoPreview();
}

function handleWatermarkImageUpload(event) {
    const file = event.target.files[0];
    const nameSpan = document.getElementById('watermark-image-name');
    if (nameSpan && file) {
        nameSpan.textContent = file.name;
    }
    scheduleAutoPreview();
}

async function runPreview() {
    if (!state.psdFileId || !state.dataFileId) {
        showStatus('process-status', 'Please upload PSD and data files', 'error');
        return;
    }
    const validMappings = state.layerMapping.filter(m => m.layer && m.column);
    if (validMappings.length === 0) {
        showStatus('process-status', 'Add at least one layer-column mapping', 'error');
        return;
    }
    const mappingObj = {};
    validMappings.forEach(m => { mappingObj[m.layer] = m.column; });
    const formData = new FormData();
    formData.append('psd_file_id', state.psdFileId);
    formData.append('data_file_id', state.dataFileId);
    formData.append('layer_mapping', JSON.stringify(mappingObj));
    formData.append('filename_fields', JSON.stringify(state.filenameFields.length ? state.filenameFields : []));
    
    // Use selected output format or default to png for preview
    const outputFormat = document.getElementById('output-format')?.value || 'png';
    formData.append('output_format', outputFormat);
    formData.append('font_id', document.getElementById('creative-font-select')?.value || '');
    formData.append('layer_overrides', JSON.stringify(getActiveLayerOverrides()));
    
    // Add watermark config
    const watermarkConfig = getWatermarkConfig();
    if (watermarkConfig) {
        formData.append('watermark_config', JSON.stringify(watermarkConfig));
    } else {
        formData.append('watermark_config', '{}');
    }
    
    showStatus('process-status', 'Generating preview...', 'info');
    document.getElementById('preview-area').style.display = 'none';
    try {
        const res = await fetch('/api/preview', { method: 'POST', body: formData, credentials: 'include' });
        const data = await res.json();
        if (data.success && data.preview_url) {
            document.getElementById('preview-image').src = data.preview_url;
            document.getElementById('preview-area').style.display = 'block';
            showStatus('process-status', 'Preview ready.', 'success');
        } else {
            showStatus('process-status', data.detail || 'Preview failed', 'error');
        }
    } catch (e) {
        showStatus('process-status', 'Error: ' + e.message, 'error');
    }
}

// Process files (sync or async queue)
async function processFiles() {
    if (!state.psdFileId || !state.dataFileId) {
        showStatus('process-status', 'Please upload both PSD and data files', 'error');
        return;
    }
    const validMappings = state.layerMapping.filter(m => m.layer && m.column);
    if (validMappings.length === 0) {
        showStatus('process-status', 'Please add at least one valid layer-column mapping', 'error');
        return;
    }
    updateFilenameFields();
    if (state.filenameFields.length === 0) {
        showStatus('process-status', 'Please select at least one field for filename', 'error');
        return;
    }
    const mappingObj = {};
    validMappings.forEach(m => { mappingObj[m.layer] = m.column; });
    const formData = new FormData();
    formData.append('psd_file_id', state.psdFileId);
    formData.append('data_file_id', state.dataFileId);
    formData.append('layer_mapping', JSON.stringify(mappingObj));
    formData.append('filename_fields', JSON.stringify(state.filenameFields));
    formData.append('output_format', document.getElementById('output-format').value);
    formData.append('font_id', document.getElementById('creative-font-select')?.value || '');
    formData.append('layer_overrides', JSON.stringify(getActiveLayerOverrides()));
    
    // Add watermark config
    const watermarkConfig = getWatermarkConfig();
    formData.append('watermark_config', JSON.stringify(watermarkConfig || {}));
    
    // Handle image watermark upload if needed
    const watermarkType = document.getElementById('watermark-type')?.value;
    if (watermarkConfig && watermarkConfig.enabled && watermarkType === 'image') {
        const imageInput = document.getElementById('watermark-image');
        if (imageInput?.files?.[0]) {
            // Upload watermark image first and get file_id
            const watermarkFormData = new FormData();
            watermarkFormData.append('file', imageInput.files[0]);
            try {
                const uploadRes = await fetch('/api/upload-image', {
                    method: 'POST',
                    body: watermarkFormData,
                    credentials: 'include'
                });
                const uploadData = await uploadRes.json();
                if (uploadData.success && uploadData.file_id) {
                    watermarkConfig.image_path = uploadData.file_path || uploadData.file_id;
                }
            } catch (e) {
                console.warn('Failed to upload watermark image:', e);
            }
        }
    }
    
    const asyncCheck = document.getElementById('process-async');
    const useAsync = asyncCheck && asyncCheck.checked;
    const url = '/api/process' + (useAsync ? '?async=1' : '');
    showStatus('process-status', useAsync ? 'Queued. Waiting for result...' : 'Processing files... This may take a while.', 'info');
    try {
        const response = await fetch(url, { method: 'POST', body: formData, credentials: 'include' });
        const result = await response.json();
        if (result.success && result.async && result.job_id) {
            const jobId = result.job_id;
            const poll = async () => {
                const r = await fetch('/api/jobs/' + jobId, { credentials: 'include' });
                const j = await r.json();
                if (j.status === 'completed' && j.result) {
                    showStatus('process-status',
                        `Done! <a href="${j.result.zip_file}" download>Download ZIP</a>`, 'success');
                    return;
                }
                if (j.status === 'cancelled') {
                    showStatus('process-status', 'Job cancelled.', 'error');
                    return;
                }
                if (j.status === 'failed' && j.result && j.result.error) {
                    showStatus('process-status', 'Job failed: ' + j.result.error, 'error');
                    return;
                }
                showStatus(
                    'process-status',
                    `${escapeHtml(j.message || 'Processing')} (${j.progress || 0}%) ` +
                    `<button class="btn" onclick="cancelCreativeJob(${jobId})">Cancel</button>`,
                    'info'
                );
                setTimeout(poll, 2000);
            };
            poll();
            return;
        }
        if (result.success && result.results) {
            const successCount = result.results.filter(r => r.success).length;
            const failCount = result.results.filter(r => !r.success).length;
            showStatus('process-status',
                `Processing complete! ${successCount} successful, ${failCount} failed. ` +
                `<a href="${result.zip_file}" download>Download ZIP</a>`, 'success');
            showToast('Processing complete. Download ready.', 'success');
        } else {
            showStatus('process-status', `Error: ${result.error || result.detail || 'Processing failed'}`, 'error');
        }
    } catch (error) {
        showStatus('process-status', `Error: ${error.message}`, 'error');
    }
}

async function cancelCreativeJob(jobId) {
    const response = await fetch(`/api/jobs/${jobId}/cancel`, {
        method: 'POST',
        credentials: 'include'
    });
    const data = await response.json();
    showStatus(
        'process-status',
        response.ok ? 'Job cancelled.' : (data.detail || 'Could not cancel job'),
        response.ok ? 'success' : 'error'
    );
}

// Email Sender Functions
async function handleEmailDataUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    document.getElementById('email-data-file-name').textContent = file.name;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload-data', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            state.emailDataFileId = result.file_id;
            state.emailDataColumns = result.columns || [];
            showStatus('email-status', `Data file uploaded successfully! Found ${result.columns?.length || 0} columns.`, 'success');
        } else {
            showStatus('email-status', `Error: ${result.error}`, 'error');
        }
    } catch (error) {
        showStatus('email-status', `Error: ${error.message}`, 'error');
    }
}

function toggleImageOptions() {
    const option = document.getElementById('image-option').value;
    if (option === '1') {
        document.getElementById('single-image-section').style.display = 'block';
        document.getElementById('folder-image-section').style.display = 'none';
    } else {
        document.getElementById('single-image-section').style.display = 'none';
        document.getElementById('folder-image-section').style.display = 'block';
    }
}

async function handleSingleImageUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    document.getElementById('single-image-name').textContent = file.name;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload-image', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            state.singleImageId = result.file_id;
        }
    } catch (error) {
        showStatus('email-status', `Error: ${error.message}`, 'error');
    }
}

async function handleFolderImagesUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    
    document.getElementById('folder-images-count').textContent = `${files.length} file(s) selected`;
    
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }
    
    try {
        const response = await fetch('/api/upload-image-folder', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            state.folderImageId = result.folder_id;
        }
    } catch (error) {
        showStatus('email-status', `Error: ${error.message}`, 'error');
    }
}

// Messaging Settings Panel Functions
function showMessagingSettings() {
    if (!state.emailDataFileId) {
        showStatus('email-status', 'Please upload Excel file first', 'error');
        return;
    }
    
    // Create datalist for column suggestions if columns are available
    const columns = state.emailDataColumns || [];
    let datalistHtml = '';
    if (columns.length > 0) {
        datalistHtml = '<datalist id="email-columns-datalist">';
        columns.forEach(col => {
            datalistHtml += `<option value="${col}">`;
        });
        datalistHtml += '</datalist>';
        
        // Add datalist to panel if not already present
        const panel = document.getElementById('messaging-settings-panel');
        let datalistEl = document.getElementById('email-columns-datalist');
        if (!datalistEl) {
            panel.insertAdjacentHTML('afterbegin', datalistHtml);
        }
        
        // Update existing datalist
        if (datalistEl) {
            datalistEl.innerHTML = columns.map(col => `<option value="${col}">`).join('');
        }
    }
    
    // Set list attribute on inputs
    const toInput = document.getElementById('email-to-column');
    const imgInput = document.getElementById('email-img-column');
    if (columns.length > 0) {
        toInput.setAttribute('list', 'email-columns-datalist');
        imgInput.setAttribute('list', 'email-columns-datalist');
    }
    
    // Load existing config if available
    if (state.emailConfig) {
        toInput.value = state.emailConfig.to_column || '';
        imgInput.value = state.emailConfig.img_column || '';
        document.getElementById('smtp-server').value = state.emailConfig.smtp_server || 'smtp.example.com';
        document.getElementById('smtp-port').value = state.emailConfig.smtp_port || '587';
        
        // Load CC columns
        const container = document.getElementById('email-cc-columns-container');
        container.innerHTML = '';
        if (state.emailConfig.cc_columns && state.emailConfig.cc_columns.length > 0) {
            state.emailConfig.cc_columns.forEach(col => {
                addCCColumnInput(col);
            });
        }
    } else {
        // Reset to defaults
        toInput.value = '';
        imgInput.value = '';
        document.getElementById('smtp-server').value = 'smtp.example.com';
        document.getElementById('smtp-port').value = '587';
        document.getElementById('email-cc-columns-container').innerHTML = '';
    }
    
    document.getElementById('messaging-settings-panel').style.display = 'block';
}

function hideMessagingSettings() {
    document.getElementById('messaging-settings-panel').style.display = 'none';
}

function addCCColumn(existingValue = '') {
    addCCColumnInput(existingValue);
}

function addCCColumnInput(existingValue = '') {
    const container = document.getElementById('email-cc-columns-container');
    const div = document.createElement('div');
    div.style.display = 'flex';
    div.style.gap = '8px';
    div.style.alignItems = 'center';
    
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control';
    input.placeholder = 'Enter CC column name';
    input.value = existingValue;
    input.style.flex = '1';
    
    // Add datalist if columns are available
    const columns = state.emailDataColumns || [];
    if (columns.length > 0) {
        input.setAttribute('list', 'email-columns-datalist');
    }
    
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn';
    removeBtn.textContent = '×';
    removeBtn.style.padding = '6px 12px';
    removeBtn.style.background = '#fee2e2';
    removeBtn.style.color = '#dc2626';
    removeBtn.onclick = () => div.remove();
    
    div.appendChild(input);
    div.appendChild(removeBtn);
    container.appendChild(div);
}

async function saveMessagingSettings() {
    const toColumn = document.getElementById('email-to-column').value.trim();
    if (!toColumn) {
        showStatus('email-status', 'Please enter the "To" column name', 'error');
        return;
    }
    
    const imgColumn = document.getElementById('email-img-column').value.trim() || null;
    const smtpServer = document.getElementById('smtp-server').value.trim() || 'smtp.example.com';
    const smtpPort = parseInt(document.getElementById('smtp-port').value) || 587;
    
    // Collect CC columns
    const ccColumns = [];
    const ccInputs = document.getElementById('email-cc-columns-container').querySelectorAll('input');
    ccInputs.forEach(input => {
        const val = input.value.trim();
        if (val) ccColumns.push(val);
    });
    
    state.emailConfig = {
        to_column: toColumn,
        img_column: imgColumn,
        cc_columns: ccColumns,
        smtp_server: smtpServer,
        smtp_port: smtpPort
    };
    
    showStatus('email-status', 'Settings saved successfully!', 'success');
    hideMessagingSettings();
}

async function testSMTPConnection() {
    const email = document.getElementById('email-address').value;
    const password = document.getElementById('email-password').value;
    const smtpServer = document.getElementById('smtp-server').value.trim() || 'smtp.example.com';
    const smtpPort = parseInt(document.getElementById('smtp-port').value) || 587;
    
    if (!email || !password) {
        showStatus('smtp-test-status', 'Please enter email and password first', 'error');
        return;
    }
    
    showStatus('smtp-test-status', 'Testing SMTP connection...', 'info');
    
    try {
        const response = await fetch('/api/test-smtp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email,
                password,
                smtp_server: smtpServer,
                smtp_port: smtpPort
            }),
            credentials: 'include'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showStatus('smtp-test-status', 'SMTP connection successful!', 'success');
        } else {
            showStatus('smtp-test-status', `SMTP test failed: ${result.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showStatus('smtp-test-status', `Error: ${error.message}`, 'error');
    }
}

async function sendEmails() {
    if (!state.emailDataFileId) {
        showStatus('email-status', 'Please upload Excel file first', 'error');
        return;
    }
    
    if (!state.emailConfig) {
        showStatus('email-status', 'Please configure email settings first', 'error');
        return;
    }
    
    const email = document.getElementById('email-address').value;
    const password = document.getElementById('email-password').value;
    const subject = document.getElementById('email-subject').value;
    const imageOption = document.getElementById('image-option').value;
    const imageLink = document.getElementById('image-link').value;
    
    if (!email || !password || !subject) {
        showStatus('email-status', 'Please fill in all required fields', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('email', email);
    formData.append('password', password);
    formData.append('data_file_id', state.emailDataFileId);
    formData.append('subject', subject);
    formData.append('image_option', imageOption);
    formData.append('smtp_server', state.emailConfig.smtp_server || 'smtp.example.com');
    formData.append('smtp_port', String(state.emailConfig.smtp_port || 587));
    if (imageOption === '1' && state.singleImageId) {
        formData.append('image_upload_id', state.singleImageId);
    }
    if (imageOption === '2' && state.folderImageId) {
        formData.append('image_folder_id', state.folderImageId);
    }
    if (imageLink) {
        formData.append('image_link', imageLink);
    }
    formData.append('to_column', state.emailConfig.to_column);
    if (state.emailConfig.img_column) {
        formData.append('img_column', state.emailConfig.img_column);
    }
    formData.append('cc_columns', JSON.stringify(state.emailConfig.cc_columns || []));
    
    showStatus('email-status', 'Sending emails in background...', 'info');
    
    try {
        const response = await fetch('/api/send-emails', {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showStatus('email-status', result.message, 'success');
            showToast(result.message || 'Emails sent.', 'success');
        } else {
            showStatus('email-status', `Error: ${result.error || 'Failed to send emails'}`, 'error');
        }
    } catch (error) {
        showStatus('email-status', `Error: ${error.message}`, 'error');
    }
}

// Utility function
function showStatus(elementId, message, type) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = message;
        element.className = `status-box ${type}`;
    }
}

// In-app toasts (top-right)
function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = typeof message === 'string' ? message : (message && message.message) || 'Done';
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        setTimeout(() => el.remove(), 300);
    }, 4000);
}

// Email Template Editor
function showTemplateEditor() {
    const modal = document.getElementById('template-editor-modal');
    if (modal) modal.style.display = 'flex';
}

function hideTemplateEditor() {
    const modal = document.getElementById('template-editor-modal');
    if (modal) modal.style.display = 'none';
}

function insertTemplateVariable(varName) {
    const textarea = document.getElementById('template-html');
    if (!textarea) return;
    const cursorPos = textarea.selectionStart;
    const textBefore = textarea.value.substring(0, cursorPos);
    const textAfter = textarea.value.substring(cursorPos);
    textarea.value = textBefore + '{{' + varName + '}}' + textAfter;
    textarea.focus();
    textarea.setSelectionRange(cursorPos + varName.length + 4, cursorPos + varName.length + 4);
}

function previewTemplate() {
    const html = document.getElementById('template-html')?.value || '';
    const preview = document.getElementById('template-preview');
    if (!preview) return;
    preview.innerHTML = html.replace(/\{\{(\w+)\}\}/g, '<span style="background:#fef3c7; padding:2px 4px; border-radius:3px;">{{$1}}</span>');
    preview.style.display = 'block';
}

async function saveTemplate() {
    const name = document.getElementById('template-name')?.value?.trim();
    const html = document.getElementById('template-html')?.value || '';
    if (!name) {
        alert('Please enter a template name');
        return;
    }
    try {
        const res = await fetch('/api/campaigns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                name: name,
                subject: 'Email Template',
                template_html: html
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Template saved!', 'success');
            hideTemplateEditor();
        } else {
            alert('Failed to save template: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Error saving template: ' + e.message);
    }
}

// Auto-show mapping section when both files are uploaded
setInterval(() => {
    if (state.psdFileId && state.dataFileId && 
        document.getElementById('mapping-section').style.display === 'none') {
        showMappingSection();
    }
}, 1000);

// Initialize default data grid and table list on first load
window.addEventListener('DOMContentLoaded', async () => {
    // Load list of existing tables and render as pills
    try {
        await refreshUsers();
        await refreshTables();
        // Notifications badge (unread count)
        const notifRes = await fetch('/api/notifications', { credentials: 'include' });
        const notifData = await notifRes.json();
        if (notifData.success && (notifData.unread_count || 0) > 0) {
            const badgeEl = document.getElementById('notifications-badge');
            if (badgeEl) {
                badgeEl.textContent = notifData.unread_count;
                badgeEl.style.display = 'inline';
            }
        }
    } catch (e) {
        // ignore and keep default
    }

    ensureTabulatorLoaded(() => {
        initDataGrid();
        showTablesHub();
        // wire search
        const search = document.getElementById('tables-search');
        if (search) {
            search.addEventListener('input', () => renderTablesHub(search.value));
        }
        renderTablesHub();

        // Global keyboard shortcuts for data grid (undo / redo / copy / paste)
        document.addEventListener('keydown', (evt) => {
            if (!state.dataGrid) return;

            const key = evt.key.toLowerCase();
            const isCtrlCmd = evt.ctrlKey || evt.metaKey;
            const target = evt.target;
            const isInGrid = target && (target.closest('#data-grid') || target.classList.contains('tabulator-cell'));

            // Only handle shortcuts when focused on grid or not in an input field
            if (!isInGrid && target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {
                return;
            }

            // Ctrl+Z / Cmd+Z -> undo
            if (isCtrlCmd && !evt.shiftKey && key === 'z') {
                evt.preventDefault();
                try {
                    const undoCount = state.dataGrid.getHistoryUndoSize();
                    if (undoCount > 0) {
                        state.dataGrid.undo();
                        showStatus('data-grid-status', `Undone (${undoCount - 1} more available)`, 'success');
                    }
                } catch (e) {
                    // Ignore if nothing to undo
                }
                return;
            }

            // Ctrl+Y or Ctrl+Shift+Z -> redo
            if (isCtrlCmd && (key === 'y' || (evt.shiftKey && key === 'z'))) {
                evt.preventDefault();
                try {
                    const redoCount = state.dataGrid.getHistoryRedoSize();
                    if (redoCount > 0) {
                        state.dataGrid.redo();
                        showStatus('data-grid-status', `Redone (${redoCount - 1} more available)`, 'success');
                    }
                } catch (e) {
                    // Ignore if nothing to redo
                }
                return;
            }

            // Ctrl+C / Cmd+C -> copy (Tabulator handles this, but show feedback)
            if (isCtrlCmd && key === 'c' && isInGrid) {
                // Let Tabulator handle copy, just show feedback
                setTimeout(() => {
                    const selectedRanges = state.dataGrid.getSelectedRanges();
                    if (selectedRanges && selectedRanges.length > 0) {
                        showStatus('data-grid-status', 'Range copied to clipboard', 'success');
                    }
                }, 50);
            }

            // Ctrl+V / Cmd+V -> paste (Tabulator handles this automatically)
            if (isCtrlCmd && key === 'v' && isInGrid) {
                // Tabulator will handle paste automatically
                setTimeout(() => {
                    showStatus('data-grid-status', 'Pasted from clipboard', 'success');
                }, 100);
            }
        });

        // Global shortcuts: Ctrl+K search, Ctrl+S save table
        document.addEventListener('keydown', (e) => {
            const isCtrlCmd = e.ctrlKey || e.metaKey;
            const k = (e.key || '').toLowerCase();
            const target = e.target;
            const inInput = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.getAttribute('contenteditable') === 'true');
            if (isCtrlCmd && k === 'k') {
                e.preventDefault();
                const searchEl = document.getElementById('platform-search');
                if (searchEl) {
                    searchEl.focus();
                    searchEl.select();
                    if (typeof onPlatformSearchFocus === 'function') onPlatformSearchFocus();
                }
                return;
            }
            if (isCtrlCmd && k === 's') {
                const panel = document.getElementById('grid-panel');
                if (panel && panel.style.display !== 'none' && state.currentTableId && !inInput) {
                    e.preventDefault();
                    if (typeof saveDataGrid === 'function') saveDataGrid();
                }
            }
        });
    });
});

function renderTablesHub(filterText = '') {
    const startRow = document.getElementById('tables-start-row');
    const list = document.getElementById('tables-list');
    if (!startRow || !list) return;

    // Start row cards
    startRow.innerHTML = '';
    const newCard = document.createElement('button');
    newCard.className = 'btn';
    newCard.style.cssText = 'width:220px; height:110px; border:1px solid #e5e7eb; border-radius:14px; background:#fff; text-align:left; padding:14px; cursor:pointer;';
    newCard.innerHTML = `<div style="font-weight:900; color:#111827; margin-bottom:6px;">+ Blank table</div><div style="color:#6b7280; font-size:0.9rem;">Create a new empty table</div>`;
    newCard.onclick = () => createNewDataTable();
    startRow.appendChild(newCard);

    // List rows
    const q = (filterText || '').toLowerCase();
    const items = (state.tables || []).filter(t => {
        const hay = `${t.title || ''} ${t.id || ''} ${t.owner || ''}`.toLowerCase();
        return !q || hay.includes(q);
    });

    list.innerHTML = '';
    if (items.length === 0) {
        list.innerHTML = `<div style="padding:16px; color:#6b7280;">No tables found.</div>`;
        return;
    }

    items.forEach((t, idx) => {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; align-items:center; justify-content:space-between; gap:10px; padding:12px 14px; border-top:1px solid #f3f4f6;';
        if (idx === 0) row.style.borderTop = 'none';

        const left = document.createElement('div');
        left.style.cssText = 'display:flex; flex-direction:column; gap:2px;';
        left.innerHTML = `<div style="font-weight:800; color:#111827;">${t.title || t.id}</div>
<div style="color:#6b7280; font-size:0.85rem;">ID: ${t.id} • Access: ${t.permission}</div>`;

        const actions = document.createElement('div');
        actions.style.cssText = 'display:flex; gap:8px; align-items:center;';

        const starBtn = document.createElement('button');
        starBtn.className = 'btn';
        starBtn.style.cssText = 'padding:6px 10px; font-size:1.1rem; background:transparent; border:none; cursor:pointer;';
        starBtn.title = t.starred ? 'Unstar' : 'Star';
        starBtn.textContent = t.starred ? '★' : '☆';
        starBtn.style.color = t.starred ? '#f59e0b' : '#9ca3af';
        starBtn.onclick = async (e) => {
            e.stopPropagation();
            try {
                const r = await fetch(`/api/data/tables/${encodeURIComponent(t.id)}/favorite`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ starred: !t.starred })
                });
                const out = await r.json();
                if (out.success) await refreshTables();
            } catch (err) {}
        };

        const openBtn = document.createElement('button');
        openBtn.className = 'btn btn-primary';
        openBtn.textContent = 'Open';
        openBtn.onclick = () => selectDataTable(t.id);

        const shareBtn = document.createElement('button');
        shareBtn.className = 'btn';
        shareBtn.textContent = 'Share';
        shareBtn.onclick = () => openSharePanel(t.id);

        const delBtn = document.createElement('button');
        delBtn.className = 'btn';
        delBtn.textContent = 'Delete';
        delBtn.style.background = '#fee2e2';
        delBtn.onclick = () => deleteDataTable(t.id);
        delBtn.disabled = t.id === 'default' || !['owner', 'admin'].includes(t.permission);

        actions.appendChild(starBtn);
        actions.appendChild(openBtn);
        actions.appendChild(shareBtn);
        actions.appendChild(delBtn);

        row.appendChild(left);
        row.appendChild(actions);
        list.appendChild(row);
    });
}

async function refreshTables() {
    const res = await fetch('/api/data/tables', { credentials: 'include' });
    const data = await res.json();
    if (!res.ok || !data.success) {
        showStatus('data-grid-status', data.error || 'Failed to load tables.', 'error');
        // Keep rendering hub so "+ Blank table" is visible
        renderTablesHub((document.getElementById('tables-search')?.value || ''));
        return;
    }

    state.tables = data.tables || [];
    renderTablesHub((document.getElementById('tables-search')?.value || ''));
}

async function refreshUsers() {
    const res = await fetch('/api/users', { credentials: 'include' });
    const data = await res.json();
    if (data.success) state.users = data.users || [];
}

function openSharePanel(tableId) {
    // inline panel inside tables list (no popups)
    const list = document.getElementById('tables-list');
    if (!list) return;

    // remove existing
    const existing = document.getElementById('share-panel');
    if (existing) existing.remove();

    const panel = document.createElement('div');
    panel.id = 'share-panel';
    panel.style.cssText = 'padding:14px; border-top:1px solid #e5e7eb; background:#f8fafc;';
    panel.innerHTML = `<div style="font-weight:900; color:#111827; margin-bottom:8px;">Share: ${escapeHtml(tableId)}</div>`;

    // Share link (expiry)
    const linkRow = document.createElement('div');
    linkRow.style.cssText = 'display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:12px;';
    const expirySel = document.createElement('select');
    expirySel.className = 'form-control';
    expirySel.style.cssText = 'max-width:160px; padding:8px 12px;';
    expirySel.innerHTML = '<option value="7d">7 days</option><option value="30d">30 days</option><option value="never">No expiry</option>';
    const getLinkBtn = document.createElement('button');
    getLinkBtn.className = 'btn';
    getLinkBtn.textContent = 'Get share link';
    const linkOut = document.createElement('span');
    linkOut.style.cssText = 'font-size:0.85rem; word-break:break-all;';
    const pbiOut = document.createElement('div');
    pbiOut.style.cssText = 'font-size:0.85rem; word-break:break-all; margin-top:8px; color:#374151;';
    getLinkBtn.onclick = async () => {
        const expiry = expirySel.value;
        try {
            const r = await fetch(`/api/data/tables/${encodeURIComponent(tableId)}/share`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ expiry })
            });
            const out = await r.json();
            if (out.success && out.share_url) {
                const full = window.location.origin + out.share_url;
                linkOut.innerHTML = `<a href="${out.share_url}" target="_blank">${escapeHtml(full)}</a>`;

                // Power BI URL: JSON rows endpoint (public)
                if (out.pbi_url) {
                    const pbiFull = window.location.origin + out.pbi_url;
                    pbiOut.innerHTML = `Power BI URL: <span style="font-family:monospace;">${escapeHtml(pbiFull)}</span>`;
                    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
                        navigator.clipboard.writeText(pbiFull);
                        if (typeof showToast === 'function') showToast('Power BI URL copied to clipboard', 'success');
                    }
                } else {
                    pbiOut.textContent = '';
                }

                if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(full);
                    if (typeof showToast === 'function') showToast('Link copied to clipboard', 'success');
                }
            } else {
                linkOut.textContent = out.error || 'Failed';
                pbiOut.textContent = '';
            }
        } catch (e) {
            linkOut.textContent = 'Error: ' + (e.message || '');
            pbiOut.textContent = '';
        }
    };
    linkRow.appendChild(expirySel);
    linkRow.appendChild(getLinkBtn);
    linkRow.appendChild(linkOut);
    panel.appendChild(linkRow);
    panel.appendChild(pbiOut);

    const row = document.createElement('div');
    row.style.cssText = 'display:flex; gap:10px; flex-wrap:wrap; align-items:center;';

    const userSel = document.createElement('select');
    userSel.className = 'form-control';
    userSel.style.cssText = 'max-width:220px; padding:10px 12px;';
    userSel.innerHTML = `<option value="">Select user…</option>` + (state.users || []).map(u => `<option value="${u.username}">${u.username}</option>`).join('');

    const permSel = document.createElement('select');
    permSel.className = 'form-control';
    permSel.style.cssText = 'max-width:220px; padding:10px 12px;';
    permSel.innerHTML = `
      <option value="edit">Editor (can edit)</option>
      <option value="view">Viewer (view only)</option>
      <option value="view_nocopy">Viewer (no copy)</option>
    `;

    const grantBtn = document.createElement('button');
    grantBtn.className = 'btn btn-success';
    grantBtn.textContent = 'Grant access';
    grantBtn.onclick = async () => {
        const u = userSel.value;
        const p = permSel.value;
        if (!u) {
            showStatus('data-grid-status', 'Pick a user to share with.', 'error');
            return;
        }
        const r = await fetch(`/api/data/tables/${encodeURIComponent(tableId)}/grants`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, permission: p })
        });
        const out = await r.json();
        if (out.success) {
            showStatus('data-grid-status', `Shared with ${u}: ${p}`, 'success');
            panel.remove();
            await refreshTables();
        } else {
            showStatus('data-grid-status', out.error || 'Share failed.', 'error');
        }
    };

    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn';
    closeBtn.textContent = 'Close';
    closeBtn.onclick = () => panel.remove();

    row.appendChild(userSel);
    row.appendChild(permSel);
    row.appendChild(grantBtn);
    row.appendChild(closeBtn);
    panel.appendChild(row);

    list.prepend(panel);
}

async function deleteDataTable(tableId) {
    if (tableId === 'default') {
        showStatus('data-grid-status', 'Cannot delete default table.', 'error');
        return;
    }
    
    // No confirm popup - direct delete
    try {
        const res = await fetch(`/api/data/tables/${encodeURIComponent(tableId)}`, {
            method: 'DELETE',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!res.ok) {
            const errorText = await res.text();
            console.error('Delete error response:', res.status, errorText);
            showStatus('data-grid-status', `Failed to delete table: ${res.status} ${errorText}`, 'error');
            return;
        }
        
        const result = await res.json();
        console.log('Delete result:', result);
        
        if (result.success) {
            await refreshTables();
            
            // If deleted table was current, switch to default
            if (state.currentTableId === tableId) {
                showTablesHub();
                state.currentTableId = 'default';
            } else {
                renderTablesHub();
            }
            
            showStatus('data-grid-status', `Table "${tableId}" deleted.`, 'success');
        } else {
            showStatus('data-grid-status', result.error || 'Failed to delete table.', 'error');
        }
    } catch (err) {
        console.error('Delete error:', err);
        showStatus('data-grid-status', `Error: ${err.message}`, 'error');
    }
}

// Support / Tickets functions
async function submitTicket() {
    const subjectEl = document.getElementById('ticket-subject');
    const bodyEl = document.getElementById('ticket-body');
    const statusEl = document.getElementById('ticket-status');
    const priorityEl = document.getElementById('ticket-priority');
    const categoryEl = document.getElementById('ticket-category');
    
    const subject = (subjectEl.value || '').trim();
    const body = (bodyEl.value || '').trim();
    const priority = (priorityEl && priorityEl.value) ? priorityEl.value : 'medium';
    const category = (categoryEl && categoryEl.value) ? categoryEl.value : 'general';
    
    if (!subject || subject.length < 3) {
        showStatus('ticket-status', 'Subject must be at least 3 characters', 'error');
        return;
    }
    
    if (!body || body.length < 10) {
        showStatus('ticket-status', 'Message must be at least 10 characters', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/tickets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ subject, body, priority, category }),
        });
        
        const data = await res.json();
        if (!data.success) {
            showStatus('ticket-status', data.error || 'Failed to submit ticket', 'error');
            return;
        }
        
        showStatus('ticket-status', 'Ticket submitted successfully! Admin will be notified.', 'success');
        showToast('Ticket submitted.', 'success');
        subjectEl.value = '';
        bodyEl.value = '';
        
        // Reload tickets list
        await loadMyTickets();
    } catch (err) {
        console.error('Submit ticket error:', err);
        showStatus('ticket-status', `Error: ${err.message}`, 'error');
    }
}

function formatBytes(n) {
    if (n == null || n === undefined) return '—';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
}

async function loadGallery() {
    const listEl = document.getElementById('gallery-list');
    const emptyEl = document.getElementById('gallery-empty');
    const loadingEl = document.getElementById('gallery-loading');
    const cardsEl = document.getElementById('gallery-cards');
    if (!listEl || !cardsEl) return;

    if (loadingEl) loadingEl.style.display = 'block';
    if (emptyEl) emptyEl.style.display = 'none';
    cardsEl.innerHTML = '';

    const q = document.getElementById('gallery-search') && document.getElementById('gallery-search').value.trim();
    const fromDate = document.getElementById('gallery-from-date') && document.getElementById('gallery-from-date').value;
    const toDate = document.getElementById('gallery-to-date') && document.getElementById('gallery-to-date').value;
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (fromDate) params.set('from_date', fromDate);
    if (toDate) params.set('to_date', toDate);
    const url = '/api/gallery/files' + (params.toString() ? '?' + params.toString() : '');
    try {
        const res = await fetch(url, { credentials: 'include' });
        if (res.status === 401) {
            if (loadingEl) loadingEl.style.display = 'none';
            cardsEl.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 24px; color: #6b7280;">Please log in to see your files.</div>';
            return;
        }
        if (!res.ok) {
            if (loadingEl) loadingEl.style.display = 'none';
            cardsEl.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 24px; color: #dc2626;">Failed to load gallery.</div>';
            return;
        }
        const payload = await res.json();
        if (loadingEl) loadingEl.style.display = 'none';
        if (!payload.success) {
            cardsEl.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 24px; color: #dc2626;">Failed to load gallery.</div>';
            return;
        }
        const files = payload.files || [];

        if (!files || files.length === 0) {
            if (emptyEl) emptyEl.style.display = 'block';
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        cardsEl.innerHTML = files.map(f => `
            <div style="border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: #fff; display: flex; flex-direction: column;">
                <div style="height: 160px; background: #f3f4f6; display: flex; align-items: center; justify-content: center;">
                    <img src="/api/gallery/thumb/${f.id}" alt="" style="max-width: 100%; max-height: 100%; object-fit: contain;" onerror="this.style.display='none'; var s=document.createElement('span'); s.style.cssText='color:#9ca3af;font-size:0.9rem'; s.textContent='ZIP'; this.parentElement.appendChild(s);">
                </div>
                <div style="padding: 12px; flex: 1;">
                    <div style="font-weight: 600; color: #111827; margin-bottom: 4px; word-break: break-all;">${escapeHtml(f.display_name || f.job_id || 'File')}</div>
                    <div style="font-size: 0.85rem; color: #6b7280;">${formatBytes(f.file_size)} · ${formatDate(f.created_at)}</div>
                    <a href="/api/gallery/download/${f.id}" download="${escapeHtml((f.display_name || f.job_id || 'file') + '.zip')}" class="btn" style="margin-top: 10px; display: inline-block; text-align: center; padding: 8px 12px; font-size: 0.9rem;">Download</a>
                </div>
            </div>
        `).join('');
    } catch (err) {
        console.error('Load gallery error:', err);
        if (loadingEl) loadingEl.style.display = 'none';
        cardsEl.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 24px; color: #dc2626;">Error loading gallery.</div>';
    }
}

async function loadMyTickets() {
    const listEl = document.getElementById('tickets-list');
    if (!listEl) return;
    
    try {
        const res = await fetch('/api/tickets', { credentials: 'include' });
        const data = await res.json();
        
        if (!data.success) {
            listEl.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 20px;">Failed to load tickets: ${escapeHtml(data.error || 'Unknown error')}</div>`;
            return;
        }
        
        const tickets = data.tickets || [];
        if (tickets.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; color: #9ca3af; padding: 20px;">No tickets yet. Create one above!</div>';
            return;
        }
        
        listEl.innerHTML = tickets.map(t => `
            <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-bottom: 16px; background: #fff;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                    <div>
                        <div style="font-weight: 600; font-size: 1.1rem; margin-bottom: 4px;">${escapeHtml(t.subject)}</div>
                        <div style="font-size: 0.9rem; color: #6b7280;">${formatDate(t.created_at)}</div>
                        <div style="font-size: 0.85rem; color:#4b5563; margin-top:4px;">Priority: <span style="font-weight:600;">${escapeHtml(t.priority || 'medium')}</span> • Category: <span style="font-weight:600;">${escapeHtml(t.category || 'general')}</span></div>
                    </div>
                    <div>
                        <span style="padding: 4px 12px; border-radius: 12px; font-size: 0.85rem; background: ${t.status === 'open' ? '#fef3c7' : '#d1fae5'}; color: ${t.status === 'open' ? '#92400e' : '#065f46'};">${t.status}</span>
                    </div>
                </div>
                <div style="background: #f9fafb; padding: 12px; border-radius: 6px; margin-bottom: 12px; white-space: pre-wrap; font-size: 0.95rem;">${escapeHtml(t.body)}</div>
                ${t.admin_reply ? `
                    <div style="background: #eff6ff; padding: 12px; border-radius: 6px; border-left: 3px solid #3b82f6;">
                        <div style="font-weight: 600; margin-bottom: 6px; color: #1e40af;">Admin Reply (${formatDate(t.admin_replied_at)})</div>
                        <div style="white-space: pre-wrap; font-size: 0.95rem;">${escapeHtml(t.admin_reply)}</div>
                    </div>
                ` : '<div style="color: #6b7280; font-size: 0.9rem;">Waiting for admin response...</div>'}
            </div>
        `).join('');
    } catch (err) {
        console.error('Load tickets error:', err);
        listEl.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 20px;">Error loading tickets: ${escapeHtml(err.message || 'Unknown error')}</div>`;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(iso) {
    if (!iso) return 'Unknown';
    try {
        const d = new Date(iso);
        return d.toLocaleString();
    } catch {
        return iso;
    }
}

// Profile / Settings panel
function toggleNotificationsPanel() {
    const panel = document.getElementById('notifications-panel');
    if (!panel) return;
    if (panel.style.display === 'block') {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'block';
    loadNotifications();
}

async function loadNotifications() {
    const listEl = document.getElementById('notifications-list');
    const badgeEl = document.getElementById('notifications-badge');
    if (!listEl) return;
    try {
        const res = await fetch('/api/notifications', { credentials: 'include' });
        const data = await res.json();
        if (!data.success) {
            listEl.innerHTML = '<p style="padding:12px; color:#6b7280;">Failed to load notifications.</p>';
            return;
        }
        const items = data.notifications || [];
        if (badgeEl) {
            const c = data.unread_count || 0;
            badgeEl.textContent = c;
            badgeEl.style.display = c > 0 ? 'inline' : 'none';
        }
        if (items.length === 0) {
            listEl.innerHTML = '<p style="padding:12px; color:#6b7280;">No notifications.</p>';
            return;
        }
        listEl.innerHTML = items.map(n => `
            <div class="notification-item" data-id="${n.id}" style="padding:10px 12px; border-bottom:1px solid #e5e7eb; ${n.read_at ? '' : 'background:#f0f9ff;'} cursor:pointer;" onclick="markNotificationRead(${n.id})">
                <div style="font-weight:600; font-size:0.9rem;">${escapeHtml(n.title)}</div>
                ${n.body ? `<div style="font-size:0.85rem; color:#6b7280; margin-top:4px;">${escapeHtml(n.body)}</div>` : ''}
                <div style="font-size:0.75rem; color:#9ca3af; margin-top:4px;">${escapeHtml(n.created_at || '')}</div>
            </div>
        `).join('');
    } catch (e) {
        listEl.innerHTML = '<p style="padding:12px; color:#ef4444;">Error loading notifications.</p>';
    }
}

async function markNotificationRead(id) {
    try {
        await fetch(`/api/notifications/${id}/read`, { method: 'POST', credentials: 'include' });
        loadNotifications();
    } catch (e) {
        if (typeof showToast === 'function') showToast('Failed to mark as read', 'error');
    }
}

let platformSearchTimer = null;
function onPlatformSearchInput(value) {
    const panel = document.getElementById('platform-search-results');
    if (!panel) return;
    const q = (value || '').trim();
    if (q.length < 1) {
        panel.style.display = 'none';
        panel.innerHTML = '';
        return;
    }
    if (platformSearchTimer) clearTimeout(platformSearchTimer);
    platformSearchTimer = setTimeout(() => fetchPlatformSearch(q), 200);
}

function onPlatformSearchFocus() {
    const input = document.getElementById('platform-search');
    const panel = document.getElementById('platform-search-results');
    if (input && input.value.trim().length >= 1 && panel && panel.innerHTML) panel.style.display = 'block';
}

async function fetchPlatformSearch(q) {
    const panel = document.getElementById('platform-search-results');
    if (!panel) return;
    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`, { credentials: 'include' });
        const data = await res.json();
        if (!data.success) {
            panel.innerHTML = '<p style="padding:12px; color:#6b7280;">Search failed.</p>';
            panel.style.display = 'block';
            return;
        }
        const results = data.results || [];
        if (results.length === 0) {
            panel.innerHTML = '<p style="padding:12px; color:#6b7280;">No results.</p>';
            panel.style.display = 'block';
            return;
        }
        const typeLabel = { table: 'Table', template: 'Template', gallery: 'Gallery', ticket: 'Ticket' };
        panel.innerHTML = results.map(r => `
            <div class="platform-search-item" style="padding:10px 12px; border-bottom:1px solid #e5e7eb; cursor:pointer;" data-type="${escapeHtml(r.type)}" data-extra="${escapeHtml(r.extra || '')}" data-link="${escapeHtml(r.link || '')}">
                <div style="font-size:0.75rem; color:#6b7280;">${escapeHtml(typeLabel[r.type] || r.type)}</div>
                <div style="font-weight:600;">${escapeHtml(r.title)}</div>
            </div>
        `).join('');
        panel.style.display = 'block';
        panel.querySelectorAll('.platform-search-item').forEach(el => {
            el.addEventListener('click', () => {
                const type = el.getAttribute('data-type');
                const extra = el.getAttribute('data-extra');
                const link = el.getAttribute('data-link');
                panel.style.display = 'none';
                if (type === 'table' && extra) {
                    switchTab('data-connectors');
                    setTimeout(() => selectDataTable(extra), 100);
                } else if (link) {
                    const tab = (link.replace(/^#/, '') || 'data-connectors');
                    const tabMap = { 'data-connectors': 'data-connectors', 'creative': 'creative', 'gallery': 'gallery', 'support': 'support' };
                    const tabName = tabMap[tab] || tab;
                    const btn = document.querySelector(`.tab-button[onclick*="switchTab('${tabName}')"]`);
                    if (btn) btn.click();
                    else switchTab(tabName);
                }
            });
        });
    } catch (e) {
        panel.innerHTML = '<p style="padding:12px; color:#ef4444;">Error.</p>';
        panel.style.display = 'block';
    }
}

document.addEventListener('click', (e) => {
    const searchWrap = document.getElementById('platform-search');
    const resultsPanel = document.getElementById('platform-search-results');
    if (resultsPanel && searchWrap && !searchWrap.contains(e.target) && !resultsPanel.contains(e.target)) resultsPanel.style.display = 'none';
});

function toggleNavMenu() {
    // Backward compat: older templates call toggleNavMenu()
    toggleSidebar();
}

function openSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!sidebar || !overlay) return;
    sidebar.classList.add('open');
    overlay.style.display = 'block';
}

function closeSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!sidebar || !overlay) return;
    sidebar.classList.remove('open');
    overlay.style.display = 'none';
}

function toggleSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!sidebar || !overlay) return;
    const isOpen = sidebar.classList.contains('open');
    if (isOpen) closeSidebar();
    else openSidebar();
}

// Close sidebar on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const sidebar = document.getElementById('app-sidebar');
        if (sidebar && sidebar.classList.contains('open')) closeSidebar();
    }
});

function toggleProfilePanel() {
    const panel = document.getElementById('profile-panel');
    if (!panel) return;
    if (panel.style.display === 'flex') {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'flex';
    loadProfile();
}

async function loadProfile() {
    const usernameEl = document.getElementById('profile-username');
    const firstNameEl = document.getElementById('profile-first-name');
    const lastNameEl = document.getElementById('profile-last-name');
    const emailEl = document.getElementById('profile-email');
    const msgEl = document.getElementById('profile-message');
    if (!usernameEl) return;
    msgEl.style.display = 'none';
    try {
        const res = await fetch('/api/me', { credentials: 'include' });
        const data = await res.json();
        if (data.authenticated && data.user) {
            const u = data.user;
            usernameEl.value = u.username || '';
            firstNameEl.value = u.first_name || '';
            lastNameEl.value = u.last_name || '';
            emailEl.value = u.email || u.username || '';
        }
    } catch (e) {
        if (msgEl) { msgEl.textContent = 'Failed to load profile'; msgEl.className = 'status-box error'; msgEl.style.display = 'block'; }
    }
}

async function saveProfile() {
    const firstName = document.getElementById('profile-first-name').value.trim();
    const lastName = document.getElementById('profile-last-name').value.trim();
    const email = document.getElementById('profile-email').value.trim();
    const msgEl = document.getElementById('profile-message');
    msgEl.style.display = 'block';
    msgEl.textContent = 'Saving...';
    msgEl.className = 'status-box info';
    try {
        const res = await fetch('/api/me/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ first_name: firstName, last_name: lastName, email })
        });
        const data = await res.json();
        if (data.success) {
            msgEl.textContent = 'Profile saved.';
            msgEl.className = 'status-box success';
            showToast('Profile saved.', 'success');
        } else {
            msgEl.textContent = data.detail || 'Failed';
            msgEl.className = 'status-box error';
        }
    } catch (e) {
        msgEl.textContent = 'Error: ' + e.message;
        msgEl.className = 'status-box error';
    }
}

async function changePassword() {
    const current = document.getElementById('profile-current-password').value;
    const newPass = document.getElementById('profile-new-password').value;
    const msgEl = document.getElementById('profile-message');
    msgEl.style.display = 'block';
    if (!current || !newPass) {
        msgEl.textContent = 'Enter current and new password.';
        msgEl.className = 'status-box error';
        return;
    }
    if (newPass.length < 12) {
        msgEl.textContent = 'New password must be at least 12 characters.';
        msgEl.className = 'status-box error';
        return;
    }
    msgEl.textContent = 'Updating...';
    msgEl.className = 'status-box info';
    try {
        const res = await fetch('/api/me/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ current_password: current, new_password: newPass })
        });
        const data = await res.json();
        if (data.success) {
            msgEl.textContent = 'Password changed.';
            msgEl.className = 'status-box success';
            document.getElementById('profile-current-password').value = '';
            document.getElementById('profile-new-password').value = '';
            showToast('Password changed.', 'success');
        } else {
            msgEl.textContent = data.detail || 'Failed';
            msgEl.className = 'status-box error';
        }
    } catch (e) {
        msgEl.textContent = 'Error: ' + e.message;
        msgEl.className = 'status-box error';
    }
}

// Security / 2FA panel
function toggleSecurityPanel() {
    const panel = document.getElementById('security-panel');
    if (!panel) return;
    if (panel.style.display === 'flex') {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'flex';
    load2FAStatus();
}

async function load2FAStatus() {
    const statusEl = document.getElementById('2fa-status');
    const setupEl = document.getElementById('2fa-setup');
    const disableEl = document.getElementById('2fa-disable');
    const msgEl = document.getElementById('2fa-message');
    if (!statusEl) return;
    statusEl.textContent = 'Loading…';
    setupEl.style.display = 'none';
    disableEl.style.display = 'none';
    msgEl.style.display = 'none';
    try {
        const res = await fetch('/api/me/2fa/status', { credentials: 'include' });
        const data = await res.json();
        if (data.enabled) {
            statusEl.textContent = 'Two-factor authentication is enabled.';
            disableEl.style.display = 'block';
        } else {
            statusEl.textContent = 'Two-factor authentication is not enabled.';
            setupEl.style.display = 'block';
        }
    } catch (e) {
        statusEl.textContent = 'Failed to load status.';
    }
}

async function enable2FA() {
    const codeEl = document.getElementById('2fa-verify-code');
    const msgEl = document.getElementById('2fa-message');
    const code = (codeEl && codeEl.value || '').trim().replace(/\s/g, '');
    if (!code || code.length < 6) {
        msgEl.textContent = 'Enter the 6-digit code from your app.';
        msgEl.className = 'status-box error';
        msgEl.style.display = 'block';
        return;
    }
    try {
        const res = await fetch('/api/me/2fa/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        msgEl.style.display = 'block';
        if (data.success) {
            msgEl.textContent = '2FA enabled.';
            msgEl.className = 'status-box success';
            load2FAStatus();
        } else {
            msgEl.textContent = data.detail || 'Invalid code.';
            msgEl.className = 'status-box error';
        }
    } catch (e) {
        msgEl.textContent = 'Error: ' + e.message;
        msgEl.className = 'status-box error';
        msgEl.style.display = 'block';
    }
}

async function setup2FA() {
    const msgEl = document.getElementById('2fa-message');
    const qrEl = document.getElementById('2fa-qr');
    try {
        const res = await fetch('/api/me/2fa/setup', { method: 'POST', credentials: 'include' });
        const data = await res.json();
        if (data.provisioning_uri) {
            qrEl.innerHTML = '<img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(data.provisioning_uri) + '" alt="QR code">';
            document.getElementById('2fa-setup').style.display = 'block';
            document.getElementById('2fa-verify-code').value = '';
        } else {
            msgEl.textContent = data.detail || 'Setup failed.';
            msgEl.className = 'status-box error';
            msgEl.style.display = 'block';
        }
    } catch (e) {
        msgEl.textContent = 'Error: ' + e.message;
        msgEl.className = 'status-box error';
        msgEl.style.display = 'block';
    }
}

async function disable2FA() {
    const codeEl = document.getElementById('2fa-disable-code');
    const msgEl = document.getElementById('2fa-message');
    const code = (codeEl && codeEl.value || '').trim().replace(/\s/g, '');
    if (!code || code.length < 6) {
        msgEl.textContent = 'Enter your current 6-digit code.';
        msgEl.className = 'status-box error';
        msgEl.style.display = 'block';
        return;
    }
    try {
        const res = await fetch('/api/me/2fa/disable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        msgEl.style.display = 'block';
        if (data.success) {
            msgEl.textContent = '2FA disabled.';
            msgEl.className = 'status-box success';
            load2FAStatus();
        } else {
            msgEl.textContent = data.detail || 'Invalid code.';
            msgEl.className = 'status-box error';
        }
    } catch (e) {
        msgEl.textContent = 'Error: ' + e.message;
        msgEl.className = 'status-box error';
        msgEl.style.display = 'block';
    }
}
