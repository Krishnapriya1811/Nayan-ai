// History Page JavaScript
// Compact patient history list (name, age, last screening) with actions

// Use same-origin API when served by the backend.
// If the frontend is opened via Live Server (e.g. :5500) or file://, fall back to Flask backend.
// NOTE: use `var` so it can be safely re-declared across multiple script files.
function resolveApiBase() {
    const override = (localStorage.getItem('NAYAN_API_BASE') || '').trim();
    if (override) return override.replace(/\/+$/, '');

    const proto = String(window.location.protocol || '').toLowerCase();
    const origin = String(window.location.origin || '');
    const port = String(window.location.port || '');

    if (proto === 'file:' || origin === 'null' || !origin) {
        return 'http://localhost:5000/api';
    }

    // Common dev servers (VS Code Live Server / Vite / React). Backend is typically on 5000.
    if (port === '5500' || port === '5173' || port === '3000') {
        return 'http://localhost:5000/api';
    }

    return `${origin}/api`;
}

var API_BASE = resolveApiBase();

let patients = [];

document.addEventListener('DOMContentLoaded', function() {
    const userId = sessionStorage.getItem('userId');
    if (!userId) {
        alert('Please login first');
        window.location.href = 'login.html';
        return;
    }

    loadPatients();

    const patientSearch = document.getElementById('patientSearch');
    if (patientSearch) {
        patientSearch.addEventListener('input', renderPatientsTable);
    }

    const refreshBtn = document.getElementById('refreshPatientsBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadPatients);
    }

    // Delegate click handlers for dynamic rows
    document.addEventListener('click', function(e) {
        const viewBtn = e.target.closest && e.target.closest('[data-action="view-report"]');
        if (viewBtn) {
            e.preventDefault();
            const pid = viewBtn.getAttribute('data-patient-id');
            const name = viewBtn.getAttribute('data-patient-name') || '';
            const age = viewBtn.getAttribute('data-patient-age') || '';
            const gender = viewBtn.getAttribute('data-patient-gender') || '';

            if (pid) {
                sessionStorage.setItem('patientId', String(pid));
                sessionStorage.setItem('patientData', JSON.stringify({ name, age, gender }));
            }
            window.location.href = 'report.html';
            return;
        }

        const dlBtn = e.target.closest && e.target.closest('[data-action="download-report"]');
        if (dlBtn) {
            e.preventDefault();
            const pid = dlBtn.getAttribute('data-patient-id');
            const name = dlBtn.getAttribute('data-patient-name') || 'Patient';
            if (pid) {
                downloadComprehensivePdf(pid, name);
            }
        }
    });
});

function loadPatients() {
    const container = document.getElementById('patientsTable');
    if (!container) return;

    container.innerHTML = `
        <div class="alert alert-info text-center">
            <span class="spinner-border spinner-border-sm me-2"></span>Loading patients...
        </div>
    `;

    const userId = sessionStorage.getItem('userId');
    const url = `${API_BASE}/patients?user_id=${encodeURIComponent(userId || '')}`;

    fetch(url)
        .then(async r => {
            const contentType = String(r.headers.get('content-type') || '').toLowerCase();
            const text = await r.text();
            if (!contentType.includes('application/json')) {
                throw new Error(
                    `API did not return JSON. Make sure backend is running at ${API_BASE}. ` +
                    `If you're using Live Server, open http://localhost:5000/history.html instead.`
                );
            }
            return JSON.parse(text);
        })
        .then(data => {
            patients = (data && data.success && Array.isArray(data.patients)) ? data.patients : [];
            renderPatientsTable();
        })
        .catch(err => {
            console.error(err);
            container.innerHTML = `
                <div class="alert alert-danger">Error loading patient history. Backend may not be available.</div>
            `;
        });
}

function renderPatientsTable() {
    const container = document.getElementById('patientsTable');
    if (!container) return;

    const q = String(document.getElementById('patientSearch')?.value || '').trim().toLowerCase();
    const filtered = patients.filter(p => {
        const name = String(p.name || '').toLowerCase();
        const age = String(p.age || '').toLowerCase();
        const gender = String(p.gender || '').toLowerCase();
        const ts = String(p.last_screening || '').toLowerCase();
        return !q || name.includes(q) || age.includes(q) || gender.includes(q) || ts.includes(q);
    });

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info text-center">
                <i class="bi bi-info-circle me-2"></i>No patient history found.
            </div>
        `;
        return;
    }

    let html = `
        <div class="table-responsive">
            <table class="table table-hover align-middle">
                <thead class="table-light">
                    <tr>
                        <th>Patient</th>
                        <th style="width: 90px;">Age</th>
                        <th>Last Screening</th>
                        <th class="text-end" style="width: 120px;">Actions</th>
                    </tr>
                </thead>
                <tbody>
    `;

    filtered.forEach(p => {
        const pid = p.id;
        const name = String(p.name || '--');
        const age = (p.age !== null && p.age !== undefined && p.age !== '') ? String(p.age) : '--';
        const gender = String(p.gender || '--');
        const last = p.last_screening ? new Date(p.last_screening).toLocaleString() : '—';

        html += `
            <tr>
                <td>
                    <div class="fw-semibold">${escapeHtml(name)}</div>
                    <div class="small text-muted">${escapeHtml(gender)}</div>
                </td>
                <td>${escapeHtml(age)}</td>
                <td>${escapeHtml(last)}</td>
                <td class="text-end">
                    <a href="#" class="btn btn-sm btn-outline-primary" title="View full report" data-action="view-report" data-patient-id="${escapeAttr(String(pid))}" data-patient-name="${escapeAttr(name)}" data-patient-age="${escapeAttr(age)}" data-patient-gender="${escapeAttr(gender)}">
                        <i class="bi bi-eye"></i>
                    </a>
                    <a href="#" class="btn btn-sm btn-outline-success ms-2" title="Download PDF" data-action="download-report" data-patient-id="${escapeAttr(String(pid))}" data-patient-name="${escapeAttr(name)}">
                        <i class="bi bi-download"></i>
                    </a>
                </td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    container.innerHTML = html;
}

function downloadComprehensivePdf(patientId, patientName) {
    const safeName = String(patientName || 'Patient').replace(/[^a-z0-9_-]+/gi, '_');
    const filename = `NAYAN_AI_Report_${safeName}_${new Date().toISOString().split('T')[0]}.pdf`;

    fetch(`${API_BASE}/report/pdf/${encodeURIComponent(patientId)}`)
        .then(resp => {
            if (!resp.ok) {
                throw new Error('Failed to generate PDF');
            }
            return resp.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        })
        .catch(err => {
            console.error(err);
            alert('PDF download failed. Please try again.');
        });
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeAttr(value) {
    return escapeHtml(value).replace(/\n/g, ' ');
}
