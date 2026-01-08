// Comprehensive Patient Report JavaScript
// Loads and displays all screening results in one unified report

var API_BASE = `${window.location.origin}/api`;

let patientInfo = null;
let cataractResults = [];
let dryeyeResults = [];
let glaucomaResults = [];

document.addEventListener('DOMContentLoaded', function() {
    // Prefer sessionStorage, but allow fallback restoration (e.g. CAMP/report navigation)
    const restoredUserId = sessionStorage.getItem('userId') || localStorage.getItem('userId');
    if (restoredUserId && !sessionStorage.getItem('userId')) {
        sessionStorage.setItem('userId', restoredUserId);
    }

    const restoredUserName = sessionStorage.getItem('userName') || localStorage.getItem('userName');
    if (restoredUserName && !sessionStorage.getItem('userName')) {
        sessionStorage.setItem('userName', restoredUserName);
    }

    let patientId = sessionStorage.getItem('patientId');
    if (!patientId) {
        patientId = localStorage.getItem('campLastPatientId') || localStorage.getItem('patientId');
        if (patientId) {
            sessionStorage.setItem('patientId', patientId);
        }
    }

    if (!sessionStorage.getItem('patientData')) {
        const fallbackPatientData = localStorage.getItem('campLastPatientData');
        if (fallbackPatientData) {
            sessionStorage.setItem('patientData', fallbackPatientData);
        }
    }

    const userId = sessionStorage.getItem('userId');

    if (!userId) {
        alert('Please login first');
        window.location.href = 'login.html';
        return;
    }

    if (!patientId) {
        alert('Please complete patient information first');
        window.location.href = 'index.html';
        return;
    }

    // Load all data
    loadPatientInfo(patientId);
    loadAllResults(patientId);

    // Event handlers
    document.getElementById('refreshBtn')?.addEventListener('click', () => {
        loadPatientInfo(patientId);
        loadAllResults(patientId);
    });

    document.getElementById('downloadPdfBtn')?.addEventListener('click', downloadPDF);
    document.getElementById('exportExcelBtn')?.addEventListener('click', exportToExcel);
});

function loadPatientInfo(patientId) {
    fetch(`${API_BASE}/patient/${patientId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.patient) {
                patientInfo = data.patient;
                displayPatientInfo(data.patient);
            }
        })
        .catch(error => {
            console.error('Error loading patient info:', error);
        });
}

function displayPatientInfo(patient) {
    document.getElementById('patientName').textContent = patient.name || '--';
    document.getElementById('patientAge').textContent = patient.age || '--';
    document.getElementById('patientGender').textContent = patient.gender || '--';
    document.getElementById('patientPhone').textContent = patient.phone || '--';
    document.getElementById('patientEmail').textContent = patient.email || '--';
    document.getElementById('patientIdDisplay').textContent = patient.id || '--';
    
    document.getElementById('medicalHistory').textContent = patient.medical_history || 'None reported';
    document.getElementById('familyHistory').textContent = patient.family_history || 'None reported';
    
    document.getElementById('reportDate').textContent = new Date().toLocaleString();
    document.getElementById('operatorName').textContent = sessionStorage.getItem('userName') || 'Medical Staff';
}

function loadAllResults(patientId) {
    // Load all screening results in parallel
    Promise.all([
        fetch(`${API_BASE}/results/cataract/${patientId}`).then(r => r.json()),
        fetch(`${API_BASE}/results/dryeye/${patientId}`).then(r => r.json()),
        fetch(`${API_BASE}/results/glaucoma/${patientId}`).then(r => r.json())
    ])
    .then(([cataractData, dryeyeData, glaucomaData]) => {
        cataractResults = (cataractData.success && Array.isArray(cataractData.results)) ? cataractData.results : [];
        dryeyeResults = (dryeyeData.success && Array.isArray(dryeyeData.results)) ? dryeyeData.results : [];
        glaucomaResults = (glaucomaData.success && Array.isArray(glaucomaData.results)) ? glaucomaData.results : [];

        displayAllResults();
        generateRecommendations();
    })
    .catch(error => {
        console.error('Error loading results:', error);
    });
}

function displayAllResults() {
    displayCataractSummary();
    displayDryeyeSummary();
    displayGlaucomaSummary();
    
    displayCataractDetails();
    displayDryeyeDetails();
    displayGlaucomaDetails();
}

function displayCataractSummary() {
    const badge = document.getElementById('cataractSummaryBadge');
    const text = document.getElementById('cataractSummaryText');
    
    if (cataractResults.length === 0) {
        badge.className = 'risk-badge badge bg-success';
        badge.textContent = 'Normal';
        text.textContent = 'No screening performed yet (Assumed Normal)';
        return;
    }

    const latest = cataractResults[0];
    const label = String(latest.label || latest[6] || 'Normal');
    const confidence = Number(latest.confidence || latest[7] || 0);
    
    if (label.toLowerCase().includes('risk') || label.toLowerCase().includes('cataract')) {
        badge.className = 'risk-badge badge bg-warning text-dark';
        badge.textContent = 'Risk Detected';
    } else {
        badge.className = 'risk-badge badge bg-success';
        badge.textContent = 'Normal';
    }
    
    text.textContent = `${cataractResults.length} screening(s) | Latest: ${label} (${confidence.toFixed(1)}%)`;
    
    const timestamp = latest.timestamp || latest[8];
    const date = timestamp ? new Date(timestamp).toLocaleDateString() : '--';
    document.getElementById('screeningDate').textContent = date;
}

function displayDryeyeSummary() {
    const badge = document.getElementById('dryeyeSummaryBadge');
    const text = document.getElementById('dryeyeSummaryText');
    
    if (dryeyeResults.length === 0) {
        badge.className = 'risk-badge badge bg-success';
        badge.textContent = 'Normal';
        text.textContent = 'No screening performed yet (Assumed Normal)';
        return;
    }

    const latest = dryeyeResults[0];
    const label = String(latest.label || latest[9] || 'Normal');
    const blinkRate = Number(
        latest.blink_rate_bpm ??
        latest.blink_rate ??
        latest[5] ??
        0
    );
    
    if (label.toLowerCase().includes('risk') || label.toLowerCase().includes('dry')) {
        badge.className = 'risk-badge badge bg-warning text-dark';
        badge.textContent = 'Risk Detected';
    } else {
        badge.className = 'risk-badge badge bg-success';
        badge.textContent = 'Normal';
    }
    
    text.textContent = `${dryeyeResults.length} screening(s) | Blink Rate: ${blinkRate.toFixed(1)} BPM`;
}

function displayGlaucomaSummary() {
    const badge = document.getElementById('glaucomaSummaryBadge');
    const text = document.getElementById('glaucomaSummaryText');
    
    if (glaucomaResults.length === 0) {
        badge.className = 'risk-badge badge bg-success';
        badge.textContent = 'Normal';
        text.textContent = 'No screening performed yet (Assumed Normal)';
        return;
    }

    const latest = glaucomaResults[0];
    const riskLevel = String(latest.risk_level || latest[3] || 'Normal');
    const iop = Number(latest.iop_proxy || latest[2] || 0);
    
    if (riskLevel.toLowerCase().includes('high')) {
        badge.className = 'risk-badge badge bg-danger';
        badge.textContent = 'High Risk';
    } else if (riskLevel.toLowerCase().includes('low')) {
        badge.className = 'risk-badge badge bg-info';
        badge.textContent = 'Low Risk';
    } else {
        badge.className = 'risk-badge badge bg-success';
        badge.textContent = 'Normal';
    }
    
    text.textContent = `${glaucomaResults.length} measurement(s) | IOP: ${iop.toFixed(1)} mmHg`;
}

function displayCataractDetails() {
    const container = document.getElementById('cataractDetails');
    
    if (cataractResults.length === 0) {
        container.innerHTML = '<div class="alert alert-info"><i class="bi bi-info-circle me-2"></i>No cataract screening performed yet. Status: <strong>Normal (Assumed)</strong></div>';
        return;
    }

    let html = '<div class="table-responsive"><table class="table table-bordered table-hover">';
    html += '<thead class="table-light"><tr>';
    html += '<th>Date & Time</th><th>Contrast</th><th>Sharpness</th><th>Edge</th><th>Result</th><th>Confidence</th><th>Image</th>';
    html += '</tr></thead><tbody>';

    cataractResults.forEach(result => {
        const timestamp = result.timestamp || result[8];
        const timestampStr = timestamp ? new Date(timestamp).toLocaleString() : '--';
        const contrast = Number(result.contrast || result[3] || 0).toFixed(2);
        const sharpness = Number(result.sharpness || result[4] || 0).toFixed(2);
        const edge = Number(result.edge_density || result[5] || 0).toFixed(2);
        const label = String(result.label || result[6] || 'Normal');
        const confidence = Number(result.confidence || result[7] || 0).toFixed(1);
        const imageFile = result.image_file || result[2];
        const badgeClass = label.toLowerCase().includes('risk') || label.toLowerCase().includes('cataract') ? 'bg-warning text-dark' : 'bg-success';

        html += `<tr>`;
        html += `<td>${timestampStr}</td>`;
        html += `<td>${contrast}</td>`;
        html += `<td>${sharpness}</td>`;
        html += `<td>${edge}</td>`;
        html += `<td><span class="badge ${badgeClass}">${label}</span></td>`;
        html += `<td>${confidence}%</td>`;
        html += `<td>${imageFile ? `<a href="/uploads/cataract/${imageFile}" target="_blank" class="btn btn-sm btn-outline-primary"><i class="bi bi-image"></i> View</a>` : '--'}</td>`;
        html += `</tr>`;
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function displayDryeyeDetails() {
    const container = document.getElementById('dryeyeDetails');
    
    if (dryeyeResults.length === 0) {
        container.innerHTML = '<div class="alert alert-info"><i class="bi bi-info-circle me-2"></i>No dry eye screening performed yet. Status: <strong>Normal (Assumed)</strong></div>';
        return;
    }

    let html = '<div class="table-responsive"><table class="table table-bordered table-hover">';
    html += '<thead class="table-light"><tr>';
    html += '<th>Date & Time</th><th>Duration</th><th>Blinks</th><th>Blink Rate</th><th>Mean IBI</th><th>Max Eye Open</th><th>Result</th><th>Video</th>';
    html += '</tr></thead><tbody>';

    dryeyeResults.forEach(result => {
        const timestamp = result.timestamp || result[10];
        const timestampStr = timestamp ? new Date(timestamp).toLocaleString() : '--';
        const duration = Number(result.duration_sec ?? result.duration ?? result[3] ?? 0).toFixed(1);
        const blinks = Number(result.blink_count ?? result.blinks ?? result[4] ?? 0);
        const blinkRate = Number(
            result.blink_rate_bpm ??
            result.blink_rate ??
            result[5] ??
            0
        ).toFixed(1);
        const meanIbi = Number(result.mean_ibi_sec ?? result.mean_ibi ?? result[6] ?? 0).toFixed(2);
        const maxEyeOpen = Number(result.max_eye_open_sec ?? result.max_eye_open_time ?? result[8] ?? 0).toFixed(2);
        const label = String(result.label || result[9] || 'Normal');
        const videoFile = result.video_file || result[2];
        const badgeClass = label.toLowerCase().includes('risk') || label.toLowerCase().includes('dry') ? 'bg-warning text-dark' : 'bg-success';

        html += `<tr>`;
        html += `<td>${timestampStr}</td>`;
        html += `<td>${duration}s</td>`;
        html += `<td>${blinks}</td>`;
        html += `<td>${blinkRate} BPM</td>`;
        html += `<td>${meanIbi}s</td>`;
        html += `<td>${maxEyeOpen}s</td>`;
        html += `<td><span class="badge ${badgeClass}">${label}</span></td>`;
        html += `<td>${videoFile ? `<a href="/uploads/dryeye/${videoFile}" target="_blank" class="btn btn-sm btn-outline-primary"><i class="bi bi-film"></i> View</a>` : '--'}</td>`;
        html += `</tr>`;
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function displayGlaucomaDetails() {
    const container = document.getElementById('glaucomaDetails');
    
    if (glaucomaResults.length === 0) {
        container.innerHTML = '<div class="alert alert-info"><i class="bi bi-info-circle me-2"></i>No glaucoma screening performed yet. Status: <strong>Normal (Assumed)</strong></div>';
        return;
    }

    let html = '<div class="table-responsive"><table class="table table-bordered table-hover">';
    html += '<thead class="table-light"><tr>';
    html += '<th>Date & Time</th><th>IOP Measurement</th><th>Risk Level</th><th>Notes</th>';
    html += '</tr></thead><tbody>';

    glaucomaResults.forEach(result => {
        const timestamp = result.timestamp || result[4];
        const timestampStr = timestamp ? new Date(timestamp).toLocaleString() : '--';
        const iop = Number(result.iop_proxy || result[2] || 0).toFixed(1);
        const riskLevel = String(result.risk_level || result[3] || 'Normal');
        let badgeClass = 'bg-success';
        if (riskLevel.toLowerCase().includes('high')) badgeClass = 'bg-danger';
        else if (riskLevel.toLowerCase().includes('low')) badgeClass = 'bg-info';

        html += `<tr>`;
        html += `<td>${timestampStr}</td>`;
        html += `<td>${iop} mmHg</td>`;
        html += `<td><span class="badge ${badgeClass}">${riskLevel}</span></td>`;
        html += `<td>IOP proxy measurement from tonometer</td>`;
        html += `</tr>`;
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function generateRecommendations() {
    const container = document.getElementById('specificRecommendations');
    let recommendations = [];
    let hasAnyRisk = false;

    // Check cataract results
    if (cataractResults.length > 0) {
        const latest = cataractResults[0];
        const label = String(latest.label || latest[6] || 'Normal');
        if (label.toLowerCase().includes('risk') || label.toLowerCase().includes('cataract')) {
            hasAnyRisk = true;
            recommendations.push({
                icon: 'camera',
                color: 'warning',
                title: 'Cataract Risk Detected',
                text: 'Schedule an appointment with an ophthalmologist for comprehensive eye examination and cataract assessment. Early detection can help preserve vision.'
            });
        }
    }

    // Check dry eye results
    if (dryeyeResults.length > 0) {
        const latest = dryeyeResults[0];
        const label = String(latest.label || latest[9] || 'Normal');
        if (label.toLowerCase().includes('risk') || label.toLowerCase().includes('dry')) {
            hasAnyRisk = true;
            recommendations.push({
                icon: 'droplet',
                color: 'info',
                title: 'Dry Eye Risk Detected',
                text: 'Consider using artificial tears, take regular breaks from screen time, and consult an eye care specialist for proper dry eye management.'
            });
        }
    }

    // Check glaucoma results
    if (glaucomaResults.length > 0) {
        const latest = glaucomaResults[0];
        const riskLevel = String(latest.risk_level || latest[3] || 'Normal');
        if (riskLevel.toLowerCase().includes('high')) {
            hasAnyRisk = true;
            recommendations.push({
                icon: 'eye',
                color: 'danger',
                title: 'High Glaucoma Risk Detected',
                text: 'URGENT: Schedule immediate consultation with an ophthalmologist for comprehensive glaucoma evaluation. High IOP requires prompt medical attention.'
            });
        }
    }

    if (!hasAnyRisk) {
        container.innerHTML = '<div class="alert alert-success"><i class="bi bi-check-circle me-2"></i><strong>Good News!</strong> All screenings appear normal. Continue regular eye check-ups as recommended by your healthcare provider for optimal eye health maintenance.</div>';
    } else {
        let html = '';
        recommendations.forEach(rec => {
            html += `
                <div class="alert alert-${rec.color}">
                    <h5><i class="bi bi-${rec.icon} me-2"></i>${rec.title}</h5>
                    <p class="mb-0">${rec.text}</p>
                </div>
            `;
        });
        container.innerHTML = html;
    }
}

function downloadPDF() {
    const patientId = sessionStorage.getItem('patientId');
    
    if (!patientId) {
        alert('Patient ID not found. Please complete patient information first.');
        return;
    }
    
    // Show loading message
    const btn = document.getElementById('downloadPdfBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Generating PDF...';
    btn.disabled = true;
    
    // Call backend API to generate PDF
    fetch(`${API_BASE}/report/pdf/${patientId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to generate PDF report');
            }
            return response.blob();
        })
        .then(blob => {
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `NAYAN-AI_Report_${patientInfo?.name || 'Patient'}_${new Date().toISOString().split('T')[0]}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            // Reset button
            btn.innerHTML = originalText;
            btn.disabled = false;
        })
        .catch(error => {
            console.error('Error downloading PDF:', error);
            alert('Failed to generate PDF report. Please try again or use the Print button as an alternative.');
            
            // Reset button
            btn.innerHTML = originalText;
            btn.disabled = false;
        });
}

function exportToExcel() {
    // Simple CSV export
    let csv = 'NAYAN-AI Eye Screening Report\n\n';
    
    if (patientInfo) {
        csv += 'Patient Information\n';
        csv += `Name,${patientInfo.name}\n`;
        csv += `Age,${patientInfo.age}\n`;
        csv += `Gender,${patientInfo.gender}\n`;
        csv += `Phone,${patientInfo.phone}\n`;
        csv += `Email,${patientInfo.email}\n\n`;
    }
    
    if (cataractResults.length > 0) {
        csv += '\nCataract Screening Results\n';
        csv += 'Date,Contrast,Sharpness,Edge,Result,Confidence\n';
        cataractResults.forEach(r => {
            csv += `${r[8] || ''},${r[3]},${r[4]},${r[5]},${r[6]},${r[7]}\n`;
        });
    }
    
    if (dryeyeResults.length > 0) {
        csv += '\nDry Eye Screening Results\n';
        csv += 'Date,Duration,Blinks,Blink Rate,Mean IBI,Max Eye Open,Result\n';
        dryeyeResults.forEach(r => {
            csv += `${r[10] || ''},${r[3]},${r[4]},${r[5]},${r[6]},${r[8]},${r[9]}\n`;
        });
    }
    
    if (glaucomaResults.length > 0) {
        csv += '\nGlaucoma Screening Results\n';
        csv += 'Date,IOP,Risk Level\n';
        glaucomaResults.forEach(r => {
            csv += `${r[4] || ''},${r[2]},${r[3]}\n`;
        });
    }
    
    // Download CSV
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nayan-ai-report-${Date.now()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
}
