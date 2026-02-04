// Glaucoma Detection Page JavaScript
// VL53L1X ocular response → OMDI workflow (ESP32 device)

// Use same-origin API when served by the backend.
// If opened via Live Server (e.g. :5500) or file://, fall back to Flask backend.
// NOTE: use `var` so it can be safely re-declared across multiple script files.
window.resolveApiBase = window.resolveApiBase || function resolveApiBase() {
    const override = (localStorage.getItem('NAYAN_API_BASE') || '').trim();
    if (override) return override.replace(/\/+$/, '');

    const proto = String(window.location.protocol || '').toLowerCase();
    const origin = String(window.location.origin || '');
    const host = String(window.location.hostname || 'localhost');
    const port = String(window.location.port || '');

    if (proto === 'file:' || origin === 'null' || !origin) {
        return 'http://localhost:5000/api';
    }

    if (port === '5500' || port === '5173' || port === '3000') {
        return `${window.location.protocol}//${host}:5000/api`;
    }

    return `${origin}/api`;
};

var API_BASE = window.resolveApiBase();

document.addEventListener('DOMContentLoaded', function() {
    const patientId = sessionStorage.getItem('patientId');
    
    if (!patientId) {
        alert('Please complete patient information first');
        window.location.href = 'index.html';
        return;
    }

    const measureBtn = document.getElementById('measureBtn');
    const refreshBtn = document.getElementById('refreshBtn');
    const autoRefreshToggle = document.getElementById('autoRefreshToggle');
    const hardwareStatus = document.getElementById('hardwareStatus');
    const resultCard = document.getElementById('resultCard');
    const kProxyValue = document.getElementById('kProxyValue');
    const riskLabel = document.getElementById('riskLabel');
    const riskLabelContainer = document.getElementById('riskLabelContainer');

    const deviceIdInput = document.getElementById('glaucomaDeviceId');
    const bindDeviceBtn = document.getElementById('bindDeviceBtn');

    const peakMmEl = document.getElementById('peakMm');
    const recoveryLatencyEl = document.getElementById('recoveryLatency');
    const varianceEl = document.getElementById('variance');
    const omdiEl = document.getElementById('omdi');

    // Live scan status UI
    const scanStatusBox = document.getElementById('scanStatusBox');
    const scanStageEl = document.getElementById('scanStage');
    const scanMessageEl = document.getElementById('scanMessage');
    const scanMetaEl = document.getElementById('scanMeta');
    const scanProgressBar = document.getElementById('scanProgressBar');

    let autoRefreshInterval = null;
    let lastResultId = null;

    let statusPollInterval = null;
    let lastStatusId = null;

    let autoNextTimer = null;
    let autoNextResultId = null;

    function startAutoNextCountdown(nextUrl, nextLabel, seconds = 10) {
        if (!nextUrl) return;
        if (autoNextTimer) {
            clearInterval(autoNextTimer);
            autoNextTimer = null;
        }

        const resultCardEl = document.getElementById('resultCard');
        const body = resultCardEl ? resultCardEl.querySelector('.card-body') : null;
        if (!body) return;

        let box = document.getElementById('autoNextBox');
        if (!box) {
            box = document.createElement('div');
            box.id = 'autoNextBox';
            box.className = 'alert alert-primary mt-3 mb-0';
            body.appendChild(box);
        }

        let remaining = Number(seconds);
        const render = () => {
            box.innerHTML = `Next: <strong>${nextLabel}</strong> in <strong>${remaining}s</strong>. ` +
                `<a href="${nextUrl}" class="alert-link">Go now</a> ` +
                `<button type="button" class="btn btn-sm btn-outline-primary ms-2" id="autoNextCancelBtn">Cancel</button>`;

            const cancelBtn = document.getElementById('autoNextCancelBtn');
            if (cancelBtn) {
                cancelBtn.onclick = () => {
                    if (autoNextTimer) {
                        clearInterval(autoNextTimer);
                        autoNextTimer = null;
                    }
                    box.className = 'alert alert-secondary mt-3 mb-0';
                    box.innerHTML = `Auto-next cancelled. <a href="${nextUrl}" class="alert-link">Go to ${nextLabel}</a>`;
                };
            }
        };

        render();
        autoNextTimer = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                clearInterval(autoNextTimer);
                autoNextTimer = null;
                window.location.href = nextUrl;
                return;
            }
            render();
        }, 1000);
    }

    // Initialize hardware status
    updateHardwareStatus();

    function getDeviceId() {
        return String((deviceIdInput && deviceIdInput.value) ? deviceIdInput.value : 'esp32cam1').trim() || 'esp32cam1';
    }

    async function bindDeviceToPatient() {
        const deviceId = getDeviceId();
        const resp = await fetch(`${API_BASE}/device/bind`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, patient_id: patientId })
        });
        const data = await resp.json();
        if (!data.success) {
            throw new Error(data.message || 'Failed to bind device');
        }
        return data;
    }

    async function fetchLatestDeviceMeasurement() {
        const deviceId = getDeviceId();
        const resp = await fetch(`${API_BASE}/glaucoma/device/latest?device_id=${encodeURIComponent(deviceId)}`);
        const data = await resp.json();
        if (!data.success) {
            throw new Error(data.message || 'No device measurement yet');
        }
        return data.result;
    }

    async function fetchLatestDeviceStatus() {
        const deviceId = getDeviceId();
        const resp = await fetch(`${API_BASE}/glaucoma/device/status/latest?device_id=${encodeURIComponent(deviceId)}`);
        const data = await resp.json();
        if (!data.success) {
            throw new Error(data.message || 'No status yet');
        }
        return data.result;
    }

    function renderScanStatus(status) {
        if (!scanStatusBox || !scanStageEl || !scanMessageEl) return;

        if (!status) {
            scanStatusBox.className = 'alert alert-secondary mb-0';
            scanStageEl.textContent = 'Waiting…';
            scanMessageEl.textContent = 'Press the hardware button to start. This box will show baseline and distance guidance.';
            if (scanMetaEl) scanMetaEl.textContent = '—';
            if (scanProgressBar) {
                scanProgressBar.style.width = '0%';
                scanProgressBar.textContent = '0%';
            }
            return;
        }

        const stage = String(status.stage || 'STATUS').toUpperCase();
        const level = String(status.level || 'info').toLowerCase();
        const msg = String(status.message || '').trim();

        let bs = 'secondary';
        if (level === 'danger') bs = 'danger';
        else if (level === 'warning') bs = 'warning';
        else if (level === 'success') bs = 'success';
        else if (level === 'info') bs = 'info';

        scanStatusBox.className = `alert alert-${bs} mb-0`;

        const stageTitleMap = {
            'START': 'Starting scan…',
            'BASELINE': 'Baseline check',
            'DISTANCE_BAD': 'Adjust distance',
            'RESPONSE': 'Measuring response…',
            'DONE': 'Scan complete',
            'ERROR': 'Device error'
        };
        scanStageEl.textContent = stageTitleMap[stage] || stage;

        const baseline = status.baseline_mm;
        const baselineText = (baseline !== null && baseline !== undefined && baseline !== '')
            ? `Baseline: ${Number(baseline).toFixed(2)} mm. `
            : '';

        scanMessageEl.textContent = baselineText + (msg || '—');

        const ts = status.timestamp ? new Date(status.timestamp).toLocaleString() : null;
        const did = status.device_id ? String(status.device_id) : getDeviceId();
        if (scanMetaEl) {
            scanMetaEl.textContent = `Device: ${did}` + (ts ? ` | ${ts}` : '');
        }

        if (scanProgressBar) {
            const p = Number(status.progress);
            if (Number.isFinite(p) && p >= 0) {
                const pct = Math.max(0, Math.min(100, Math.round(p * 100)));
                scanProgressBar.style.width = `${pct}%`;
                scanProgressBar.textContent = `${pct}%`;
            }
        }
    }

    // Measure button (hardware-driven): bind + refresh
    measureBtn.addEventListener('click', async function() {
        measureBtn.disabled = true;
        refreshBtn.disabled = true;
        const originalText = measureBtn.innerHTML;
        measureBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Waiting...';
        try {
            await bindDeviceToPatient();
            // Begin live status polling immediately after bind.
            if (statusPollInterval) {
                clearInterval(statusPollInterval);
                statusPollInterval = null;
            }
            refreshStatus();
            statusPollInterval = setInterval(refreshStatus, 800);
            await refreshMeasurement();
        } catch (e) {
            showError(e.message || 'Failed to start');
        } finally {
            measureBtn.disabled = false;
            refreshBtn.disabled = false;
            measureBtn.innerHTML = originalText;
        }
    });

    // Refresh button
    refreshBtn.addEventListener('click', function() {
        refreshMeasurement();
        refreshStatus();
    });

    if (bindDeviceBtn) {
        bindDeviceBtn.addEventListener('click', async function() {
            bindDeviceBtn.disabled = true;
            const original = bindDeviceBtn.innerHTML;
            bindDeviceBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Binding...';
            try {
                await bindDeviceToPatient();
                showError('Device bound to patient successfully.', false);
            } catch (e) {
                showError(e.message || 'Bind failed');
            } finally {
                bindDeviceBtn.disabled = false;
                bindDeviceBtn.innerHTML = original;
            }
        });
    }

    // Auto-refresh toggle
    autoRefreshToggle.addEventListener('change', function() {
        if (this.checked) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });

    function updateHardwareStatus() {
        fetch(`${API_BASE}/health`)
            .then(response => response.json())
            .then(data => {
                hardwareStatus.innerHTML = `
                    <span class="badge bg-success fs-6">
                        <span class="me-2">●</span>Connected
                    </span>
                `;
            })
            .catch(error => {
                hardwareStatus.innerHTML = `
                    <span class="badge bg-danger fs-6">
                        <span class="me-2">●</span>Disconnected
                    </span>
                `;
                console.error('Backend not available:', error);
            });
    }

    async function refreshMeasurement() {
        try {
            if (loadingCard) loadingCard.style.display = 'block';
            const result = await fetchLatestDeviceMeasurement();
            if (result && result.id && String(result.id) === String(lastResultId)) {
                return;
            }
            lastResultId = result.id;
            displayMeasurement(result);
        } catch (e) {
            // Not fatal: device may not have produced a measurement yet
            console.warn('No device measurement yet:', e);
        } finally {
            if (loadingCard) loadingCard.style.display = 'none';
        }
    }

    async function refreshStatus() {
        try {
            const st = await fetchLatestDeviceStatus();
            if (st && st.id && String(st.id) === String(lastStatusId)) {
                return;
            }
            lastStatusId = st && st.id ? String(st.id) : lastStatusId;
            renderScanStatus(st);

            const stage = st && st.stage ? String(st.stage).toUpperCase() : '';
            if (stage === 'DISTANCE_BAD') {
                showError(st.message || 'Adjust distance and try again (75..105mm)', true);
            }
        } catch (e) {
            // ignore transient errors
        }
    }

    function displayMeasurement(result) {
        const omdi = Number(result.omdi ?? 0);
        const risk = String(result.risk_level || result.risk || '--').toUpperCase();
        const peak = Number(result.peak_mm ?? 0);
        const trMs = Number(result.recovery_latency_ms ?? 0);
        const variance = Number(result.variance ?? 0);
        const deviceId = String(result.device_id || getDeviceId());
        const ts = result.timestamp ? new Date(result.timestamp).toLocaleString() : new Date().toLocaleString();

        if (kProxyValue) kProxyValue.textContent = Number.isFinite(omdi) ? omdi.toFixed(3) : '--';

        riskLabel.textContent = risk;
        if (risk.includes('HIGH')) {
            riskLabel.className = 'badge fs-5 px-4 py-2 bg-danger';
        } else if (risk.includes('MODERATE') || risk.includes('MED')) {
            riskLabel.className = 'badge fs-5 px-4 py-2 bg-warning text-dark';
        } else {
            riskLabel.className = 'badge fs-5 px-4 py-2 bg-success';
        }

        if (document.getElementById('deviceId')) document.getElementById('deviceId').textContent = deviceId;
        if (peakMmEl) peakMmEl.textContent = Number.isFinite(peak) ? peak.toFixed(3) : '--';
        if (recoveryLatencyEl) recoveryLatencyEl.textContent = Number.isFinite(trMs) ? String(Math.round(trMs)) : '--';
        if (varianceEl) varianceEl.textContent = Number.isFinite(variance) ? variance.toFixed(4) : '--';
        if (omdiEl) omdiEl.textContent = Number.isFinite(omdi) ? omdi.toFixed(3) : '--';
        if (document.getElementById('timestamp')) document.getElementById('timestamp').textContent = ts;

        // Show result card
        resultCard.style.display = 'block';
        resultCard.scrollIntoView({ behavior: 'smooth' });

        // Save to session
        sessionStorage.setItem('glaucomaDeviceResults', JSON.stringify(result));

        // Auto-advance only once per unique result id
        const rid = result && result.id ? String(result.id) : null;
        if (rid && rid !== autoNextResultId) {
            autoNextResultId = rid;
            startAutoNextCountdown('cataract.html', 'Cataract', 10);
        }
    }

    function showError(message, isError = true) {
        const errorAlert = document.getElementById('errorAlert');
        const errorMessage = document.getElementById('errorMessage');
        if (!errorAlert || !errorMessage) return;
        errorAlert.style.display = 'block';
        errorAlert.className = isError ? 'alert alert-danger' : 'alert alert-success';
        errorMessage.textContent = message;
        setTimeout(() => {
            errorAlert.style.display = 'none';
        }, 4000);
    }

    // Print functionality
    const printBtn = document.getElementById('printBtn');
    if (printBtn) {
        printBtn.addEventListener('click', function() {
            const template = document.getElementById('printTemplate');
            const printContent = template ? template.innerHTML : '';
            const printWindow = window.open('', '', 'height=600,width=800');

            if (!printWindow) {
                alert('Popup blocked. Please allow popups to print.');
                return;
            }

            printWindow.document.write(`
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Glaucoma Screening Report - NAYAN-AI</title>
                    <style>
                        @media print { body { margin: 0; padding: 20px; } }
                        body { font-family: Arial, sans-serif; }
                    </style>
                </head>
                <body>
                    ${printContent}
                </body>
                </html>
            `);
            printWindow.document.close();
            printWindow.print();
        });
    }

    // Download functionality (PDF report)
    const downloadBtn = document.getElementById('downloadBtn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', function() {
            const patientId = sessionStorage.getItem('patientId');
            
            if (!patientId) {
                alert('Patient ID not found');
                return;
            }
            
            // Show loading
            const originalText = downloadBtn.innerHTML;
            downloadBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Generating PDF...';
            downloadBtn.disabled = true;
            
            // Download PDF
            fetch(`${API_BASE}/report/glaucoma/pdf/${patientId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Failed to generate PDF');
                    }
                    return response.blob();
                })
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    const patientData = JSON.parse(sessionStorage.getItem('patientData') || '{}');
                    a.download = `Glaucoma_Report_${patientData.name || 'Patient'}_${new Date().toISOString().split('T')[0]}.pdf`;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                })
                .catch(error => {
                    console.error('Error downloading PDF:', error);
                    alert('Failed to generate PDF report. Please try Print instead.');
                })
                .finally(() => {
                    downloadBtn.innerHTML = originalText;
                    downloadBtn.disabled = false;
                });
        });
    }

    function startAutoRefresh() {
        autoRefreshInterval = setInterval(() => {
            refreshMeasurement();
            refreshStatus();
        }, 3000);
        console.log('Auto-refresh started (3 seconds interval)');
    }

    function stopAutoRefresh() {
        if (autoRefreshInterval) {
            clearInterval(autoRefreshInterval);
            autoRefreshInterval = null;
            console.log('Auto-refresh stopped');
        }

        if (statusPollInterval) {
            clearInterval(statusPollInterval);
            statusPollInterval = null;
        }
    }

    // Start auto-refresh by default
    if (autoRefreshToggle.checked) {
        startAutoRefresh();
    }

    // Initial status render
    refreshStatus();

    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
        stopAutoRefresh();
    });
});
