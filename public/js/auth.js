// Shared auth utilities used across all pages

function getToken() {
    return localStorage.getItem('token');
}

function requireAuth() {
    if (!getToken()) {
        window.location.href = '/static/index.html';
    }
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('full_name');
    window.location.href = '/static/index.html';
}

async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...(options.headers || {})
    };

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        logout();
        return null;
    }

    return res;
}

function setUserName() {
    const name = localStorage.getItem('full_name') || 'Benutzer';
    const el = document.getElementById('user-name');
    if (el) el.textContent = name;
}

function showAlert(containerId, message, type = 'info') {
    const el = document.getElementById(containerId);
    if (el) {
        el.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
        setTimeout(() => { if (el) el.innerHTML = ''; }, 5000);
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '–';
    return new Date(dateStr).toLocaleDateString('de-DE');
}

function formatCurrency(val) {
    if (val === null || val === undefined) return '–';
    return parseFloat(val).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

function formatNumber(val, decimals = 2) {
    if (val === null || val === undefined) return '–';
    return parseFloat(val).toFixed(decimals);
}

function statusBadge(status) {
    const map = {
        pending:        ['badge-pending',  'Ausstehend'],
        combined:       ['badge-combined', 'Kombiniert'],
        quoted:         ['badge-quoted',   'Angeboten'],
        accepted:       ['badge-quoted',   'Akzeptiert'],
        declined:       ['badge-danger',   'Abgelehnt'],
        open:           ['badge-open',     'Offen'],
        planned:        ['badge-planned',  'Geplant'],
        in_production:  ['badge-reviewed', 'In Produktion'],
        completed:      ['badge-combined', 'Abgeschlossen'],
        draft:          ['badge-draft',    'Entwurf'],
        reviewed:       ['badge-reviewed', 'Geprüft'],
        sent_manually:  ['badge-combined', 'Manuell gesendet'],
    };
    const [cls, label] = map[status] || ['badge-pending', status];
    return `<span class="badge ${cls}">${label}</span>`;
}
