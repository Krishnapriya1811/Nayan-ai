// Cataract Detection Page JavaScript
// Complete integration with backend API

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
    // Get patient data from session
    const patientData = JSON.parse(sessionStorage.getItem('patientData') || '{}');
    const patientId = sessionStorage.getItem('patientId');
    
    if (!patientId) {
        alert('Please complete patient information first');
        window.location.href = 'index.html';
        return;
    }

    const imageInput = document.getElementById('imageInput');
    const previewContainer = document.getElementById('previewContainer');
    const imagePreview = document.getElementById('imagePreview');
    const fileInfo = document.getElementById('fileInfo');
    const uploadBtn = document.getElementById('uploadBtn');
    const loadingCard = document.getElementById('loadingCard');
    const resultCard = document.getElementById('resultCard');
    const initialCard = document.getElementById('initialCard');
    const errorAlert = document.getElementById('errorAlert');
    const errorMessage = document.getElementById('errorMessage');

    const esp32PreviewBtn = document.getElementById('esp32PreviewBtn');
    const esp32AnalyzeBtn = document.getElementById('esp32AnalyzeBtn');
    const esp32DeviceId = document.getElementById('esp32DeviceId');
    const esp32Status = document.getElementById('esp32Status');

    const esp32AnalyzeCapturedBtn = document.getElementById('esp32AnalyzeCapturedBtn');
    const esp32LiveStartBtn = document.getElementById('esp32LiveStartBtn');
    const esp32LiveStopBtn = document.getElementById('esp32LiveStopBtn');
    const esp32LiveContainer = document.getElementById('esp32LiveContainer');
    const esp32LiveImg = document.getElementById('esp32LiveImg');
    const esp32CaptureBtn = document.getElementById('esp32CaptureBtn');
    const esp32CaptureStatus = document.getElementById('esp32CaptureStatus');

    let esp32LastPreview = null;
    let esp32CapturedSnapshotUrl = null;
    let hwSinceId = 0;
    let hwInProgress = false;

    let autoNextTimer = null;

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

    function getEsp32DeviceIdOrDefault() {
        return (((esp32DeviceId && esp32DeviceId.value) || 'esp32cam1').trim() || 'esp32cam1');
    }

    function setCaptureStatus(message, type = 'info') {
        if (!esp32CaptureStatus) return;
        esp32CaptureStatus.style.display = 'block';
        const cls = type === 'error' ? 'text-danger' : (type === 'success' ? 'text-success' : 'text-muted');
        esp32CaptureStatus.className = `small mt-2 ${cls}`;
        esp32CaptureStatus.textContent = message;
    }

    function startEsp32Live() {
        const deviceId = getEsp32DeviceIdOrDefault();
        if (esp32LiveContainer) esp32LiveContainer.style.display = 'block';
        if (esp32LiveImg) {
            const cb = `cb=${Date.now()}`;
            esp32LiveImg.src = `${API_BASE}/camera/esp32/mjpeg?device_id=${encodeURIComponent(deviceId)}&${cb}`;
        }
        if (esp32LiveStartBtn) esp32LiveStartBtn.disabled = true;
        if (esp32LiveStopBtn) esp32LiveStopBtn.disabled = false;
        setCaptureStatus('Live stream started', 'success');
    }

    function stopEsp32Live() {
        if (esp32LiveImg) esp32LiveImg.src = '';
        if (esp32LiveContainer) esp32LiveContainer.style.display = 'none';
        if (esp32LiveStartBtn) esp32LiveStartBtn.disabled = false;
        if (esp32LiveStopBtn) esp32LiveStopBtn.disabled = true;
        setCaptureStatus('Live stream stopped');
    }

    function captureEsp32Snapshot() {
        const deviceId = getEsp32DeviceIdOrDefault();
        if (esp32CaptureBtn) esp32CaptureBtn.disabled = true;
        if (esp32AnalyzeCapturedBtn) esp32AnalyzeCapturedBtn.disabled = true;
        setCaptureStatus('Capturing snapshot...');

        return fetch(`${API_BASE}/camera/esp32/capture`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId })
        })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                throw new Error(data.message || 'Capture failed');
            }
            esp32CapturedSnapshotUrl = data.snapshot_url;

            // Show captured snapshot in the normal preview area
            const cb = `cb=${Date.now()}`;
            imagePreview.src = `${esp32CapturedSnapshotUrl}${esp32CapturedSnapshotUrl.includes('?') ? '&' : '?'}${cb}`;
            fileInfo.textContent = `ESP32 (${deviceId}) captured snapshot`;
            previewContainer.style.display = 'block';

            setCaptureStatus('Snapshot captured. Ready to analyze.', 'success');
            if (esp32AnalyzeCapturedBtn) esp32AnalyzeCapturedBtn.disabled = false;
        })
        .catch(err => {
            console.error('ESP32 capture error:', err);
            setCaptureStatus(err.message || 'Capture failed', 'error');
            showError('ESP32 capture error:\n' + (err.message || 'Capture failed'));
            throw err;
        })
        .finally(() => {
            if (esp32CaptureBtn) esp32CaptureBtn.disabled = false;
        });
    }

    function analyzeCapturedSnapshot() {
        if (!esp32CapturedSnapshotUrl) {
            showError('Capture a snapshot first.');
            return;
        }

        const deviceId = getEsp32DeviceIdOrDefault();

        // Show loading
        loadingCard.style.display = 'block';
        resultCard.style.display = 'none';
        initialCard.style.display = 'none';
        if (esp32AnalyzeCapturedBtn) esp32AnalyzeCapturedBtn.disabled = true;
        if (esp32AnalyzeBtn) esp32AnalyzeBtn.disabled = true;
        if (esp32PreviewBtn) esp32PreviewBtn.disabled = true;

        setEsp32Status('Fetching captured snapshot bytes...');

        fetch(esp32CapturedSnapshotUrl)
            .then(r => r.blob())
            .then(blob => {
                setEsp32Status('Analyzing captured snapshot...');
                return fetch(`${API_BASE}/camera/esp32/cataract?patient_id=${encodeURIComponent(patientId)}&device_id=${encodeURIComponent(deviceId)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'image/jpeg' },
                    body: blob
                });
            })
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => {
                        throw new Error(`HTTP ${response.status}: ${text}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    setEsp32Status('Captured snapshot analyzed successfully.', 'success');
                    displayResults(data.analysis, data.image_url);
                } else {
                    setEsp32Status(data.message || 'Failed to analyze snapshot', 'error');
                    showError(data.message || 'Failed to analyze snapshot');
                }
            })
            .catch(err => {
                console.error('ESP32 analyze snapshot error:', err);
                setEsp32Status(err.message || 'Failed to analyze snapshot', 'error');
                showError('ESP32 camera error:\n' + (err.message || 'Failed to analyze snapshot'));
            })
            .finally(() => {
                loadingCard.style.display = 'none';
                if (esp32AnalyzeCapturedBtn) esp32AnalyzeCapturedBtn.disabled = false;
                if (esp32AnalyzeBtn) esp32AnalyzeBtn.disabled = false;
                if (esp32PreviewBtn) esp32PreviewBtn.disabled = false;
            });
    }

    function pollHardwareEvents() {
        const deviceId = getEsp32DeviceIdOrDefault();
        const url = `${API_BASE}/hardware/poll?device_id=${encodeURIComponent(deviceId)}&since_id=${encodeURIComponent(hwSinceId)}`;
        fetch(url)
            .then(r => r.json())
            .then(async data => {
                if (!data || !data.success || !data.event) return;
                if (typeof data.id === 'number') {
                    hwSinceId = data.id;
                } else if (data.id) {
                    hwSinceId = Number(data.id) || hwSinceId;
                }

                if (String(data.event).toUpperCase() !== 'CATARACT') return;
                if (hwInProgress) return;
                hwInProgress = true;

                try {
                    setCaptureStatus('Hardware CATARACT button detected. Capturing...', 'info');
                    await captureEsp32Snapshot();
                    // Auto-analyze immediately for the currently selected patient.
                    analyzeCapturedSnapshot();
                } catch (e) {
                    // errors already surfaced by existing handlers
                } finally {
                    // allow next event after a short cooldown
                    setTimeout(() => { hwInProgress = false; }, 1500);
                }
            })
            .catch(() => {
                // silent: polling is best-effort
            });
    }

    // Poll hardware events so ESP32-WROOM can trigger actions over Wi-Fi
    setInterval(pollHardwareEvents, 1000);

    // Image input change handler
    imageInput.addEventListener('change', function(e) {
        // Reset UI state for a new selection
        if (errorAlert) errorAlert.style.display = 'none';
        uploadBtn.disabled = true;

        const file = e.target.files && e.target.files[0];
        if (!file) return;

        // Validate file type.
        // Some mobile browsers provide an empty MIME type for captured photos,
        // so only enforce the check when a type is present.
        if (file.type && !file.type.startsWith('image/')) {
            showError('Please select a valid image file');
            imageInput.value = '';
            return;
        }

        // Validate file size (max 10MB)
        const maxSize = 10 * 1024 * 1024;
        if (file.size > maxSize) {
            showError('File size exceeds 10MB limit');
            imageInput.value = '';
            return;
        }

        // Enable upload immediately after validation.
        // Some mobile browsers fail to fire FileReader onload reliably.
        uploadBtn.disabled = false;

        // Show preview
        const reader = new FileReader();
        reader.onload = function(event) {
            imagePreview.src = event.target.result;
            fileInfo.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
            previewContainer.style.display = 'block';
        };
        reader.onerror = function() {
            // Preview is optional; keep upload enabled.
            fileInfo.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
            previewContainer.style.display = 'block';
        };
        reader.readAsDataURL(file);
    });

    // Upload and analyze
    uploadBtn.addEventListener('click', function() {
        const file = imageInput.files[0];
        if (!file) {
            showError('Please select an image');
            return;
        }

        uploadImage(file);
    });

    // ESP32-CAM: preview first
    if (esp32PreviewBtn) {
        esp32PreviewBtn.addEventListener('click', function() {
            const deviceId = getEsp32DeviceIdOrDefault();
            previewLatestEsp32Frame(deviceId);
        });
    }

    // ESP32-CAM: analyze the preview
    if (esp32AnalyzeBtn) {
        esp32AnalyzeBtn.addEventListener('click', function() {
            if (!patientId) {
                showError('Patient ID missing. Please complete patient information first.');
                return;
            }
            const deviceId = getEsp32DeviceIdOrDefault();
            analyzeLatestEsp32Frame(deviceId);
        });
    }

    if (esp32LiveStartBtn) {
        esp32LiveStartBtn.addEventListener('click', startEsp32Live);
    }

    if (esp32LiveStopBtn) {
        esp32LiveStopBtn.addEventListener('click', stopEsp32Live);
    }

    if (esp32CaptureBtn) {
        esp32CaptureBtn.addEventListener('click', captureEsp32Snapshot);
    }

    if (esp32AnalyzeCapturedBtn) {
        esp32AnalyzeCapturedBtn.addEventListener('click', analyzeCapturedSnapshot);
    }

    // Auto-start live preview when entering the page (if the UI exists)
    try {
        if (esp32LiveStartBtn && esp32LiveImg) {
            startEsp32Live();
        }
    } catch (e) {
        // non-fatal
    }

    function uploadImage(file) {
        // Show loading
        loadingCard.style.display = 'block';
        resultCard.style.display = 'none';
        initialCard.style.display = 'none';
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Uploading...';

        // Create form data
        const formData = new FormData();
        formData.append('image', file);
        formData.append('patient_id', patientId);

        console.log('Uploading file:', file.name, file.size, 'bytes');
        console.log('Patient ID:', patientId);
        console.log('Upload URL:', `${API_BASE}/cataract/upload`);

        // Send to backend
        fetch(`${API_BASE}/cataract/upload`, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            console.log('Response status:', response.status);
            if (!response.ok) {
                return response.text().then(text => {
                    throw new Error(`HTTP ${response.status}: ${text}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Response data:', data);
            if (data.success) {
                displayResults(data.analysis, data.image_url);
            } else {
                showError(data.message || 'Analysis failed');
            }
        })
        .catch(error => {
            console.error('Upload error:', error);
            showError('Failed to upload image:\n' + error.message);
        })
        .finally(() => {
            loadingCard.style.display = 'none';
            uploadBtn.disabled = false;
            uploadBtn.innerHTML = '<i class="bi bi-cloud-upload me-1"></i>Upload & Predict';
        });
    }

    function setEsp32Status(message, type = 'info') {
        if (!esp32Status) return;
        esp32Status.style.display = 'block';
        const cls = type === 'error' ? 'text-danger' : (type === 'success' ? 'text-success' : 'text-muted');
        esp32Status.className = `small mt-2 ${cls}`;
        esp32Status.textContent = message;
    }

    function previewLatestEsp32Frame(deviceId) {
        if (errorAlert) errorAlert.style.display = 'none';
        if (esp32AnalyzeBtn) esp32AnalyzeBtn.disabled = true;
        setEsp32Status(`Fetching latest frame from ${deviceId}...`);

        fetch(`${API_BASE}/camera/esp32/latest?device_id=${encodeURIComponent(deviceId)}`)
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => {
                        throw new Error(`HTTP ${response.status}: ${text}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (!data.success) {
                    throw new Error(data.message || 'No ESP32 frame received yet');
                }

                // Reuse the existing preview UI
                const ts = data.timestamp_ms || Date.now();
                const url = `${data.latest_url}?t=${encodeURIComponent(ts)}`;
                imagePreview.src = url;
                fileInfo.textContent = `ESP32 (${deviceId}) latest frame`;
                previewContainer.style.display = 'block';

                // Remember that we have a valid preview
                esp32LastPreview = { deviceId, ts };
                setEsp32Status('Preview ready. Click Analyze to run prediction.', 'success');
                if (esp32AnalyzeBtn) esp32AnalyzeBtn.disabled = false;
            })
            .catch(err => {
                console.error('ESP32 preview error:', err);
                setEsp32Status(err.message || 'Failed to fetch ESP32 preview', 'error');
                showError('ESP32 preview error:\n' + err.message);
            });
    }

    function analyzeLatestEsp32Frame(deviceId) {
        if (errorAlert) errorAlert.style.display = 'none';

        // Show loading
        loadingCard.style.display = 'block';
        resultCard.style.display = 'none';
        initialCard.style.display = 'none';
        if (esp32AnalyzeBtn) esp32AnalyzeBtn.disabled = true;
        if (esp32PreviewBtn) esp32PreviewBtn.disabled = true;
        setEsp32Status(`Requesting latest frame from ${deviceId}...`);

        fetch(`${API_BASE}/camera/esp32/cataract/latest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                patient_id: patientId,
                device_id: deviceId
            })
        })
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    throw new Error(`HTTP ${response.status}: ${text}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                setEsp32Status('Frame analyzed successfully.', 'success');
                displayResults(data.analysis, data.image_url);
            } else {
                setEsp32Status(data.message || 'Failed to analyze ESP32 frame', 'error');
                showError(data.message || 'Failed to analyze ESP32 frame');
            }
        })
        .catch(err => {
            console.error('ESP32 analyze error:', err);
            setEsp32Status(err.message || 'Failed to analyze ESP32 frame', 'error');
            showError('ESP32 camera error:\n' + err.message);
        })
        .finally(() => {
            loadingCard.style.display = 'none';
            if (esp32AnalyzeBtn) esp32AnalyzeBtn.disabled = false;
            if (esp32PreviewBtn) esp32PreviewBtn.disabled = false;
        });
    }

    function displayResults(analysis, imageUrl) {
        // Update result badge and color
        const resultBadge = document.getElementById('resultBadge');
        const resultCard_elem = document.getElementById('resultCard');
        
        if (analysis.label.includes('Risk')) {
            resultBadge.className = 'badge fs-3 px-4 py-3 bg-warning text-dark';
            resultCard_elem.style.borderTop = '4px solid #ffc107';
        } else {
            resultBadge.className = 'badge fs-3 px-4 py-3 bg-success';
            resultCard_elem.style.borderTop = '4px solid #28a745';
        }
        resultBadge.textContent = analysis.label;

        // Update confidence
        const confidenceValue = document.getElementById('confidenceValue');
        const confidenceBar = document.getElementById('confidenceBar');
        const confidence = Math.round(analysis.confidence);
        
        confidenceValue.textContent = `${confidence}%`;
        confidenceBar.style.width = confidence + '%';
        confidenceBar.className = confidence > 70 ? 'progress-bar bg-success' : 'progress-bar bg-warning';

        // Update probability table
        const probNormal = document.getElementById('probNormal');
        const probCataract = document.getElementById('probCataract');
        
        const cataractProb = analysis.label.includes('Risk') ? confidence : (100 - confidence);
        const normalProb = 100 - cataractProb;
        
        probNormal.innerHTML = `<strong>${normalProb.toFixed(1)}%</strong>`;
        probCataract.innerHTML = `<strong>${cataractProb.toFixed(1)}%</strong>`;

        // Update uploaded image
        document.getElementById('uploadedImage').src = imageUrl;

        // Update timestamp
        document.getElementById('resultTimestamp').textContent = new Date().toLocaleString();

        // Update interpretation
        const interpretationText = document.getElementById('interpretationText');
        if (analysis.label.includes('Risk')) {
            interpretationText.innerHTML = `
                <strong>Cataract Risk Detected:</strong><br>
                Based on image quality metrics (Contrast: ${analysis.contrast.toFixed(2)}, 
                Sharpness: ${analysis.sharpness.toFixed(2)}), there are indicators suggesting possible cataract formation.<br>
                <strong style="color: #ff6b6b;">⚠️ Recommendation:</strong> Please consult an ophthalmologist for clinical examination and proper diagnosis.
            `;
        } else {
            interpretationText.innerHTML = `
                <strong>Normal Result:</strong><br>
                Image quality metrics (Contrast: ${analysis.contrast.toFixed(2)}, 
                Sharpness: ${analysis.sharpness.toFixed(2)}) indicate no visible signs of cataract at this time.<br>
                <strong style="color: #28a745;">✓ Continue:</strong> You can proceed to next screening or consult for regular checkups.
            `;
        }

        // Show result card
        initialCard.style.display = 'none';
        resultCard.style.display = 'block';
        resultCard.scrollIntoView({ behavior: 'smooth' });

        // Save to session
        sessionStorage.setItem('cataractResults', JSON.stringify(analysis));

        // Update print template
        updatePrintTemplate(analysis);

        // Auto-advance to next screening after 10 seconds
        startAutoNextCountdown('dryeye.html', 'Dry Eye', 10);
    }

    function updatePrintTemplate(analysis) {
        const patientData = JSON.parse(sessionStorage.getItem('patientData') || '{}');

        // Patient information
        if (document.getElementById('printPatientName')) {
            document.getElementById('printPatientName').textContent = patientData.name || '--';
            document.getElementById('printPatientAge').textContent = patientData.age || '--';
            document.getElementById('printPatientGender').textContent = patientData.gender || '--';
            document.getElementById('printDate').textContent = new Date().toLocaleDateString();

            // Test results
            document.getElementById('printRiskLabel').textContent = analysis.label;
            const printRiskLabel = document.getElementById('printRiskLabel').parentElement;
            if (analysis.label.includes('Risk')) {
                printRiskLabel.style.backgroundColor = '#fff3cd';
                printRiskLabel.style.borderLeftColor = '#ff9800';
            } else {
                printRiskLabel.style.backgroundColor = '#d4edda';
                printRiskLabel.style.borderLeftColor = '#28a745';
            }

            // Metrics
            document.getElementById('printContrast').textContent = analysis.contrast.toFixed(2);
            document.getElementById('printSharpness').textContent = analysis.sharpness.toFixed(2);
            document.getElementById('printEdge').textContent = analysis.edge.toFixed(2);
            document.getElementById('printConfidence').textContent = analysis.confidence.toFixed(1) + '%';

            // Generated date
            document.getElementById('printGeneratedDate').textContent = new Date().toLocaleString();
        }
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
                    <title>Cataract Analysis Report - NAYAN-AI</title>
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
            fetch(`${API_BASE}/report/cataract/pdf/${patientId}`)
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
                    a.download = `Cataract_Report_${patientData.name || 'Patient'}_${new Date().toISOString().split('T')[0]}.pdf`;
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

    function showError(message) {
        errorMessage.textContent = message;
        errorAlert.style.display = 'block';
        errorAlert.scrollIntoView({ behavior: 'smooth' });
        
        setTimeout(() => {
            errorAlert.style.display = 'none';
        }, 5000);
    }
});
