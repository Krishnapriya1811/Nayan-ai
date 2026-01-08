// History Page JavaScript
// Load and display screening results

// Use same-origin API when served by the backend.
// NOTE: use `var` so it can be safely re-declared across multiple script files.
var API_BASE = `${window.location.origin}/api`;

let cataractResults = [];
let dryeyeResults = [];
let glaucomaResults = [];

document.addEventListener('DOMContentLoaded', function() {
    const userId = sessionStorage.getItem('userId');
    if (!userId) {
        alert('Please login first');
        window.location.href = 'login.html';
        return;
    }

    const patientId = sessionStorage.getItem('patientId');
    if (!patientId) {
        alert('Please complete patient information first');
        window.location.href = 'index.html';
        return;
    }

    // Load results when page loads
    loadResults();

    // Search handlers (optional)
    const cataractSearch = document.getElementById('cataractSearch');
    if (cataractSearch) {
        cataractSearch.addEventListener('input', () => renderCataractTable());
    }
    const dryeyeSearch = document.getElementById('dryeyeSearch');
    if (dryeyeSearch) {
        dryeyeSearch.addEventListener('input', () => renderDryeyeTable());
    }
    const glaucomaSearch = document.getElementById('glaucomaSearch');
    if (glaucomaSearch) {
        glaucomaSearch.addEventListener('input', () => renderGlaucomaTable());
    }

    // Tab switching (reload on tab click to stay fresh)
    const tabs = document.querySelectorAll('[role="tab"]');
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            setTimeout(loadResults, 100);
        });
    });
});

function loadResults() {
    loadCataractRecords();
    loadDryeyeRecords();
    loadGlaucomaRecords();
}

function loadCataractRecords() {
    const patientId = sessionStorage.getItem('patientId');
    const container = document.getElementById('cataractTable');

    if (!container) return;

    fetch(`${API_BASE}/results/cataract/${patientId}`)
        .then(response => response.json())
        .then(data => {
            cataractResults = (data && data.success && Array.isArray(data.results)) ? data.results : [];
            renderCataractTable();
        })
        .catch(error => {
            console.error('Error:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    Error loading cataract records. Backend may not be available.
                </div>
            `;
        });
}

function renderCataractTable() {
    const container = document.getElementById('cataractTable');
    if (!container) return;

    const query = (document.getElementById('cataractSearch')?.value || '').toLowerCase();
    const filtered = cataractResults.filter(row => {
        // Handle both object and array formats
        const label = String(row.label || row[6] || '').toLowerCase();
        const ts = String(row.timestamp || row[8] || '').toLowerCase();
        return !query || label.includes(query) || ts.includes(query);
    });

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info text-center">
                <i class="bi bi-info-circle me-2"></i>No cataract screening records found.
            </div>
        `;
        return;
    }

    let html = `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead class="table-light">
                    <tr>
                        <th>Date</th>
                        <th>Contrast</th>
                        <th>Sharpness</th>
                        <th>Result</th>
                        <th>Confidence</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
    `;

    filtered.forEach(result => {
        const timestamp = (result.timestamp || result[8]) ? new Date(result.timestamp || result[8]).toLocaleString() : '--';
        const contrast = Number(result.contrast || result[3] || 0);
        const sharpness = Number(result.sharpness || result[4] || 0);
        const label = String(result.label || result[6] || '');
        const confidence = Number(result.confidence || result[7] || 0);
        const imageFile = result.image_file || result[2];
        const resultClass = label.toLowerCase().includes('risk') ? 'bg-warning text-dark' : 'bg-success';

        html += `
            <tr>
                <td>${timestamp}</td>
                <td>${Number.isFinite(contrast) ? contrast.toFixed(2) : '--'}</td>
                <td>${Number.isFinite(sharpness) ? sharpness.toFixed(2) : '--'}</td>
                <td><span class="badge ${resultClass}">${label}</span></td>
                <td>${Number.isFinite(confidence) ? confidence.toFixed(1) + '%' : '--'}</td>
                <td>
                    ${imageFile ? `
                        <a href="/uploads/cataract/${imageFile}" target="_blank" class="btn btn-sm btn-primary" title="Download">
                            <i class="bi bi-download"></i>
                        </a>
                    ` : ''}
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

function loadDryeyeRecords() {
    const patientId = sessionStorage.getItem('patientId');
    const container = document.getElementById('dryeyeTable');

    if (!container) return;

    fetch(`${API_BASE}/results/dryeye/${patientId}`)
        .then(response => response.json())
        .then(data => {
            dryeyeResults = (data && data.success && Array.isArray(data.results)) ? data.results : [];
            renderDryeyeTable();
        })
        .catch(error => {
            console.error('Error:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    Error loading dry eye records. Backend may not be available.
                </div>
            `;
        });
}

function renderDryeyeTable() {
    const container = document.getElementById('dryeyeTable');
    if (!container) return;

    const query = (document.getElementById('dryeyeSearch')?.value || '').toLowerCase();
    const filtered = dryeyeResults.filter(row => {
        // Handle both object and array formats
        const label = String(row.label || row[9] || '').toLowerCase();
        const ts = String(row.timestamp || row[10] || '').toLowerCase();
        return !query || label.includes(query) || ts.includes(query);
    });

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info text-center">
                <i class="bi bi-info-circle me-2"></i>No dry eye screening records found.
            </div>
        `;
        return;
    }

    let html = `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead class="table-light">
                    <tr>
                        <th>Date</th>
                        <th>Blinks</th>
                        <th>Blink Rate (BPM)</th>
                        <th>Mean IBI (s)</th>
                        <th>Max Eye Open (s)</th>
                        <th>Result</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
    `;

    filtered.forEach(result => {
        const timestamp = (result.timestamp || result[10]) ? new Date(result.timestamp || result[10]).toLocaleString() : '--';
        const blinkCount = Number(result.blinks || result[4] || 0);
        const blinkRate = Number(result.blink_rate || result[5] || 0);
        const meanIbi = Number(result.mean_ibi || result[6] || 0);
        const maxEyeOpen = Number(result.max_eye_open_time || result[8] || 0);
        const label = String(result.label || result[9] || '');
        const videoFile = result.video_file || result[2];
        const resultClass = label.toLowerCase().includes('risk') ? 'bg-warning text-dark' : 'bg-success';

        html += `
            <tr>
                <td>${timestamp}</td>
                <td>${Number.isFinite(blinkCount) ? blinkCount : '--'}</td>
                <td>${Number.isFinite(blinkRate) ? blinkRate.toFixed(2) : '--'}</td>
                <td>${Number.isFinite(meanIbi) ? meanIbi.toFixed(2) : '--'}</td>
                <td>${Number.isFinite(maxEyeOpen) ? maxEyeOpen.toFixed(2) : '--'}</td>
                <td><span class="badge ${resultClass}">${label}</span></td>
                <td>
                    ${videoFile ? `
                        <a href="/uploads/dryeye/${videoFile}" target="_blank" class="btn btn-sm btn-primary" title="Download">
                            <i class="bi bi-download"></i>
                        </a>
                    ` : ''}
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

function loadGlaucomaRecords() {
    const patientId = sessionStorage.getItem('patientId');
    const container = document.getElementById('glaucomaTable');

    if (!container) return;

    fetch(`${API_BASE}/results/glaucoma/${patientId}`)
        .then(response => response.json())
        .then(data => {
            glaucomaResults = (data && data.success && Array.isArray(data.results)) ? data.results : [];
            renderGlaucomaTable();
        })
        .catch(error => {
            console.error('Error:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    Error loading glaucoma records. Backend may not be available.
                </div>
            `;
        });
}

function renderGlaucomaTable() {
    const container = document.getElementById('glaucomaTable');
    if (!container) return;

    const query = (document.getElementById('glaucomaSearch')?.value || '').toLowerCase();
    const filtered = glaucomaResults.filter(row => {
        // Handle both object and array formats
        const riskLevel = String(row.risk_level || row[3] || '').toLowerCase();
        const ts = String(row.timestamp || row[4] || '').toLowerCase();
        return !query || riskLevel.includes(query) || ts.includes(query);
    });

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info text-center">
                <i class="bi bi-info-circle me-2"></i>No glaucoma screening records found.
            </div>
        `;
        return;
    }

    let html = `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead class="table-light">
                    <tr>
                        <th>Date</th>
                        <th>IOP Measurement</th>
                        <th>Risk Level</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
    `;

    filtered.forEach(result => {
        const timestamp = (result.timestamp || result[4]) ? new Date(result.timestamp || result[4]).toLocaleString() : '--';
        const iop = Number(result.iop_proxy || result[2] || 0);
        const riskLevel = String(result.risk_level || result[3] || '');
        let resultClass = 'bg-success';
        if (riskLevel.toLowerCase().includes('high')) {
            resultClass = 'bg-danger';
        } else if (riskLevel.toLowerCase().includes('low')) {
            resultClass = 'bg-info';
        }

        html += `
            <tr>
                <td>${timestamp}</td>
                <td>${Number.isFinite(iop) ? iop.toFixed(1) + ' mmHg' : '--'}</td>
                <td><span class="badge ${resultClass}">${riskLevel}</span></td>
                <td>Tonometer measurement</td>
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
