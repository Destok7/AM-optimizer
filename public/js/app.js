// Shared utilities for AM-Optimizer v2

const API = '';

function getToken() {
    return localStorage.getItem('token');
}

function authHeaders() {
    return { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' };
}

function logout() {
    localStorage.removeItem('token');
    window.location.href = '/';
}

function checkAuth() {
    if (!getToken()) window.location.href = '/';
}

// Toast notifications
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// Active nav
function setActiveNav(page) {
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.page === page);
    });
}

// Format currency
function formatEur(val) {
    if (val == null) return '—';
    return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(val);
}

// Format number
function formatNum(val, decimals = 1) {
    if (val == null) return '—';
    return Number(val).toFixed(decimals).replace('.', ',');
}

// Platform bar color
function platformBarClass(pct) {
    if (pct >= 90) return 'danger';
    if (pct >= 70) return 'warn';
    return '';
}

// Machine materials map
const MACHINE_MATERIALS = {
    'Xline':  ['AlSi10Mg'],
    'EOS':    ['AlSi10Mg', 'IN718', 'IN625'],
    'M2_alt': ['IN718', 'IN625', '1.4404'],
    'M2_neu': ['AlSi10Mg', 'IN718', 'IN625', '1.4404'],
};

const MACHINE_PLATFORM = {
    'Xline':  320000,
    'EOS':    62500,
    'M2_alt': 62500,
    'M2_neu': 48400,
};

const MATERIAL_GROUPS = {
    'AlSi10Mg': 'AlSi10Mg',
    'IN718':    'IN718_IN625',
    'IN625':    'IN718_IN625',
    '1.4404':   '1.4404',
};

function getMaterialGroup(material) {
    return MATERIAL_GROUPS[material] || material;
}

// Populate machine select
function populateMachineSelect(selectEl, onChange) {
    selectEl.innerHTML = '<option value="">-- Maschine wählen --</option>';
    Object.keys(MACHINE_MATERIALS).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        selectEl.appendChild(opt);
    });
    if (onChange) selectEl.addEventListener('change', onChange);
}

// Populate material select based on machine
function populateMaterialSelect(selectEl, machine, includeGroups = false) {
    selectEl.innerHTML = '<option value="">-- Material wählen --</option>';
    const mats = MACHINE_MATERIALS[machine] || [];
    if (includeGroups) {
        // Show unique groups
        const groups = [...new Set(mats.map(m => MATERIAL_GROUPS[m]))];
        groups.forEach(g => {
            const opt = document.createElement('option');
            opt.value = g;
            opt.textContent = g === 'IN718_IN625' ? 'IN718 / IN625' : g;
            selectEl.appendChild(opt);
        });
    } else {
        mats.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            selectEl.appendChild(opt);
        });
    }
}

// Generic fetch wrapper
async function apiFetch(url, options = {}) {
    const res = await fetch(API + url, {
        headers: authHeaders(),
        ...options,
    });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Fehler');
    return data;
}

// Sidebar HTML
function renderSidebar(activePage) {
    return `
    <div class="sidebar">
        <div class="sidebar-logo">
            <h2>AM<span>-</span>Optimizer</h2>
            <div style="color:rgba(255,255,255,0.4);font-size:11px;margin-top:2px;">Produktionsplanung v2</div>
        </div>
        <nav class="sidebar-nav">
            <a href="/dashboard.html" class="nav-item ${activePage==='dashboard'?'active':''}" data-page="dashboard">
                <span class="icon">📊</span> Dashboard
            </a>
            <a href="/datenbank.html" class="nav-item ${activePage==='datenbank'?'active':''}" data-page="datenbank">
                <span class="icon">🗄️</span> Datenbank
            </a>
            <a href="/kalkulation.html" class="nav-item ${activePage==='kalkulation'?'active':''}" data-page="kalkulation">
                <span class="icon">🔲</span> Komb. Kalkulation
            </a>
            <a href="/emails.html" class="nav-item ${activePage==='emails'?'active':''}" data-page="emails">
                <span class="icon">✉️</span> E-Mail-Entwürfe
            </a>
        </nav>
        <div class="sidebar-footer">
            <button class="logout-btn" onclick="logout()">🚪 Abmelden</button>
        </div>
    </div>`;
}
