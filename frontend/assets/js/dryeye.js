// Dry Eye Detection Page JavaScript
// Complete API integration with backend

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

    const dryeyeForm = document.getElementById('dryeyeForm');
    const videoInput = document.getElementById('videoInput');
    const videoPreview = document.getElementById('videoPreview');
    const fileName = document.getElementById('fileName');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const resultsCard = document.getElementById('resultsCard');
    const nextBtn = document.getElementById('nextBtn');
    const printBtn = document.getElementById('printBtn');
    const downloadBtn = document.getElementById('downloadBtn');

    // ESP32 Dry Eye
    const esp32DeviceIdDryeye = document.getElementById('esp32DeviceIdDryeye');
    const esp32SecondsDryeye = document.getElementById('esp32SecondsDryeye');
    const esp32PreviewBtnDryeye = document.getElementById('esp32PreviewBtnDryeye');
    const esp32AnalyzeBtnDryeye = document.getElementById('esp32AnalyzeBtnDryeye');
    const esp32StatusDryeye = document.getElementById('esp32StatusDryeye');
    const esp32PreviewContainerDryeye = document.getElementById('esp32PreviewContainerDryeye');
    const esp32PreviewImgDryeye = document.getElementById('esp32PreviewImgDryeye');

    const esp32LiveStartBtnDryeye = document.getElementById('esp32LiveStartBtnDryeye');
    const esp32LiveStopBtnDryeye = document.getElementById('esp32LiveStopBtnDryeye');
    const esp32LiveContainerDryeye = document.getElementById('esp32LiveContainerDryeye');
    const esp32LiveImgDryeye = document.getElementById('esp32LiveImgDryeye');
    const esp32RecordBtnDryeye = document.getElementById('esp32RecordBtnDryeye');
    const esp32CaptureStatusDryeye = document.getElementById('esp32CaptureStatusDryeye');

    const esp32ClipContainerDryeye = document.getElementById('esp32ClipContainerDryeye');
    const esp32ClipVideoDryeye = document.getElementById('esp32ClipVideoDryeye');
    const esp32ClipStatusDryeye = document.getElementById('esp32ClipStatusDryeye');

    // Analyze should use the same clip created in Step 3 (if available).
    let esp32LastRecordedClipUrl = null;
    let hwSinceId = 0;
    let hwInProgress = false;

    let autoNextTimer = null;

    function startAutoNextCountdown(nextUrl, nextLabel, seconds = 10) {
        if (!nextUrl) return;
        if (autoNextTimer) {
            clearInterval(autoNextTimer);
            autoNextTimer = null;
        }

        const resultsCardEl = document.getElementById('resultsCard');
        const body = resultsCardEl ? resultsCardEl.querySelector('.card-body') : null;
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

    // File input change handler
    if (videoInput) {
        videoInput.addEventListener('change', function(e) {
            const file = e.target.files && e.target.files[0];
            if (!file) {
                return;
            }

            // Validate file size (max 100MB)
            const maxSize = 100 * 1024 * 1024;
            if (file.size > maxSize) {
                alert('File size exceeds 100MB limit');
                videoInput.value = '';
                return;
            }

            if (fileName) {
                fileName.textContent = file.name;
            }
            if (videoPreview) {
                videoPreview.style.display = 'block';
            }
        });
    }

    // Form submission handler
    if (dryeyeForm) {
        dryeyeForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const file = videoInput && videoInput.files && videoInput.files[0];
            if (!file) {
                alert('Please select a video file');
                return;
            }

            uploadVideo(file);
        });
    }

    function uploadVideo(file) {
        // Show loading spinner
        if (loadingSpinner) loadingSpinner.style.display = 'block';
        if (resultsCard) resultsCard.style.display = 'none';
        if (nextBtn) nextBtn.style.display = 'none';
        if (dryeyeForm) dryeyeForm.style.display = 'none';

        const formData = new FormData();
        formData.append('video', file);
        formData.append('patient_id', patientId);

        fetch(`${API_BASE}/dryeye/upload`, {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayResults(data.analysis);
                } else {
                    alert('Analysis failed: ' + (data.message || 'Unknown error'));
                    if (dryeyeForm) dryeyeForm.style.display = 'block';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Failed to upload video. Backend may not be available.');
                if (dryeyeForm) dryeyeForm.style.display = 'block';
            })
            .finally(() => {
                if (loadingSpinner) loadingSpinner.style.display = 'none';
            });
    }

    function setEsp32DryeyeStatus(message, isError) {
        if (!esp32StatusDryeye) return;
        esp32StatusDryeye.textContent = `Status: ${message}`;
        esp32StatusDryeye.className = isError ? 'small text-danger' : 'small text-muted';
    }

    function setEsp32DryeyeCaptureStatus(message, isError) {
        if (!esp32CaptureStatusDryeye) return;
        esp32CaptureStatusDryeye.style.display = 'block';
        esp32CaptureStatusDryeye.textContent = message;
        esp32CaptureStatusDryeye.className = isError ? 'small text-danger mt-2' : 'small text-muted mt-2';
    }

    function setEsp32ClipStatus(message, isError) {
        if (!esp32ClipStatusDryeye) return;
        esp32ClipStatusDryeye.textContent = message;
        esp32ClipStatusDryeye.className = isError ? 'small text-danger' : 'small text-muted';
    }

    function getDeviceIdDryeye() {
        const v = (esp32DeviceIdDryeye && esp32DeviceIdDryeye.value) ? esp32DeviceIdDryeye.value.trim() : '';
        return v || 'esp32cam1';
    }

    function startEsp32LiveDryeye() {
        const deviceId = getDeviceIdDryeye();
        if (esp32LiveContainerDryeye) esp32LiveContainerDryeye.style.display = 'block';
        if (esp32LiveImgDryeye) {
            const cb = `cb=${Date.now()}`;
            esp32LiveImgDryeye.src = `${API_BASE}/camera/esp32/mjpeg?device_id=${encodeURIComponent(deviceId)}&${cb}`;
        }
        if (esp32LiveStartBtnDryeye) esp32LiveStartBtnDryeye.disabled = true;
        if (esp32LiveStopBtnDryeye) esp32LiveStopBtnDryeye.disabled = false;
        setEsp32DryeyeStatus('Live preview running', false);
    }

    function stopEsp32LiveDryeye() {
        if (esp32LiveImgDryeye) esp32LiveImgDryeye.src = '';
        if (esp32LiveContainerDryeye) esp32LiveContainerDryeye.style.display = 'none';
        if (esp32LiveStartBtnDryeye) esp32LiveStartBtnDryeye.disabled = false;
        if (esp32LiveStopBtnDryeye) esp32LiveStopBtnDryeye.disabled = true;
        setEsp32DryeyeStatus('Live preview stopped', false);
    }

    async function recordEsp32Mp4Dryeye() {
        const deviceId = getDeviceIdDryeye();
        const sec = Number(esp32SecondsDryeye && esp32SecondsDryeye.value ? esp32SecondsDryeye.value : 30);
        const secClamped = Number.isFinite(sec) ? Math.max(10, Math.min(60, sec)) : 30;

        if (esp32RecordBtnDryeye) esp32RecordBtnDryeye.disabled = true;
        if (esp32AnalyzeBtnDryeye) esp32AnalyzeBtnDryeye.disabled = true;
        // Ensure live preview is running so the user understands it's collecting frames.
        if (esp32LiveImgDryeye && !esp32LiveImgDryeye.src) {
            startEsp32LiveDryeye();
        }

        // Countdown (collect frames)
        let remaining = secClamped;
        setEsp32DryeyeCaptureStatus(`Recording... ${remaining}s remaining`, false);
        if (esp32ClipContainerDryeye) esp32ClipContainerDryeye.style.display = 'block';
        setEsp32ClipStatus('Waiting for frames...', false);

        await new Promise(resolve => {
            const t = setInterval(() => {
                remaining -= 1;
                if (remaining <= 0) {
                    clearInterval(t);
                    setEsp32DryeyeCaptureStatus('Recording finished. Building clip...', false);
                    setEsp32ClipStatus('Building...', false);
                    resolve();
                    return;
                }
                setEsp32DryeyeCaptureStatus(`Recording... ${remaining}s remaining`, false);
            }, 1000);
        });

        try {
            const resp = await fetch(`${API_BASE}/camera/esp32/record`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: deviceId, seconds: secClamped })
            });
            const data = await resp.json();
            if (!data || !data.success) {
                throw new Error(data && data.message ? data.message : 'Record failed');
            }

            const cb = `cb=${Date.now()}`;
            if (esp32ClipVideoDryeye) {
                const clipUrl = `${data.video_url}${data.video_url.includes('?') ? '&' : '?'}${cb}`; 
                esp32LastRecordedClipUrl = data.video_url; // store non-cachebusted server path
                const clipType = data.content_type || (clipUrl.toLowerCase().includes('.webm') ? 'video/webm' : 'video/mp4');

                // Use <source> for better codec/type detection.
                try {
                    esp32ClipVideoDryeye.pause();
                } catch (e) {}
                esp32ClipVideoDryeye.removeAttribute('src');
                while (esp32ClipVideoDryeye.firstChild) {
                    esp32ClipVideoDryeye.removeChild(esp32ClipVideoDryeye.firstChild);
                }
                const source = document.createElement('source');
                source.src = clipUrl;
                source.type = clipType;
                esp32ClipVideoDryeye.appendChild(source);
                esp32ClipVideoDryeye.load();
            }
            setEsp32ClipStatus('Clip ready', false);
            setEsp32DryeyeCaptureStatus(`Clip created (${data.frames_used || 'many'} frames, ${data.fps || '--'} fps). Now click Analyze.`, false);
            if (esp32AnalyzeBtnDryeye) esp32AnalyzeBtnDryeye.disabled = false;
        } catch (e) {
            console.error(e);
            setEsp32ClipStatus('Clip failed', true);
            setEsp32DryeyeCaptureStatus(e.message || 'Clip failed', true);
        } finally {
            if (esp32RecordBtnDryeye) esp32RecordBtnDryeye.disabled = false;
        }
    }

    async function handleHardwareDryeyeEvent() {
        if (hwInProgress) return;
        hwInProgress = true;
        try {
            // Record using current UI seconds value, then analyze immediately for the active patient.
            await recordEsp32Mp4Dryeye();

            const deviceId = getDeviceIdDryeye();
            const sec = Number(esp32SecondsDryeye && esp32SecondsDryeye.value ? esp32SecondsDryeye.value : 30);
            const secClamped = Number.isFinite(sec) ? Math.max(10, Math.min(60, sec)) : 30;
            await analyzeEsp32Dryeye(deviceId, secClamped);
        } catch (e) {
            // errors already surfaced in UI
        } finally {
            setTimeout(() => { hwInProgress = false; }, 1500);
        }
    }

    function pollHardwareEvents() {
        const deviceId = getDeviceIdDryeye();
        const url = `${API_BASE}/hardware/poll?device_id=${encodeURIComponent(deviceId)}&since_id=${encodeURIComponent(hwSinceId)}`;
        fetch(url)
            .then(r => r.json())
            .then(data => {
                if (!data || !data.success || !data.event) return;
                const idNum = Number(data.id);
                if (Number.isFinite(idNum) && idNum > hwSinceId) hwSinceId = idNum;

                if (String(data.event).toUpperCase() !== 'DRYEYE') return;
                handleHardwareDryeyeEvent();
            })
            .catch(() => {
                // best-effort polling
            });
    }

    // Poll hardware events so ESP32-WROOM can trigger actions over Wi-Fi
    setInterval(pollHardwareEvents, 1000);

    async function previewLatestEsp32DryeyeFrame(deviceId) {
        if (!deviceId) {
            setEsp32DryeyeStatus('Device ID required', true);
            return;
        }

        if (esp32PreviewBtnDryeye) esp32PreviewBtnDryeye.disabled = true;
        if (esp32AnalyzeBtnDryeye) esp32AnalyzeBtnDryeye.disabled = true;
        setEsp32DryeyeStatus('Fetching latest frame...', false);

        try {
            const url = `${API_BASE}/camera/esp32/latest?device_id=${encodeURIComponent(deviceId)}`;
            const resp = await fetch(url);
            const data = await resp.json();
            if (!data || !data.success) {
                throw new Error(data && data.message ? data.message : 'No latest frame');
            }

            if (esp32PreviewContainerDryeye) esp32PreviewContainerDryeye.style.display = 'block';
            if (esp32PreviewImgDryeye) {
                const cacheBust = `cb=${Date.now()}`;
                esp32PreviewImgDryeye.src = `${data.latest_url}${data.latest_url.includes('?') ? '&' : '?'}${cacheBust}`;
            }

            setEsp32DryeyeStatus(`Preview ready (ts=${data.timestamp_ms})`, false);
            if (esp32AnalyzeBtnDryeye) esp32AnalyzeBtnDryeye.disabled = false;
        } catch (e) {
            console.error(e);
            setEsp32DryeyeStatus(e.message || 'Preview failed', true);
        } finally {
            if (esp32PreviewBtnDryeye) esp32PreviewBtnDryeye.disabled = false;
        }
    }

    async function analyzeEsp32Dryeye(deviceId, seconds) {
        if (!deviceId) {
            setEsp32DryeyeStatus('Device ID required', true);
            return;
        }

        const sec = Number(seconds);
        const secClamped = Number.isFinite(sec) ? Math.max(10, Math.min(60, sec)) : 30;

        if (esp32PreviewBtnDryeye) esp32PreviewBtnDryeye.disabled = true;
        if (esp32AnalyzeBtnDryeye) esp32AnalyzeBtnDryeye.disabled = true;

        // Show loading spinner
        if (loadingSpinner) loadingSpinner.style.display = 'block';
        if (resultsCard) resultsCard.style.display = 'none';
        if (nextBtn) nextBtn.style.display = 'none';
        setEsp32DryeyeStatus(`Analyzing last ${secClamped}s...`, false);

        try {
            // If a clip was created in Step 3, analyze THAT exact clip (same as download+upload flow).
            const endpoint = esp32LastRecordedClipUrl ? `${API_BASE}/camera/esp32/dryeye/analyze_clip` : `${API_BASE}/camera/esp32/dryeye/latest`;
            const body = esp32LastRecordedClipUrl
                ? { patient_id: patientId, clip_url: esp32LastRecordedClipUrl }
                : { patient_id: patientId, device_id: deviceId, seconds: secClamped };

            const resp = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await resp.json();

            if (!data || !data.success) {
                throw new Error(data && data.message ? data.message : 'Dry-eye analysis failed');
            }

            displayResults(data.analysis);
            setEsp32DryeyeStatus('Analysis complete', false);
        } catch (e) {
            console.error(e);
            alert('Dry eye analysis failed: ' + (e.message || 'Unknown error'));
            setEsp32DryeyeStatus(e.message || 'Analysis failed', true);
        } finally {
            if (loadingSpinner) loadingSpinner.style.display = 'none';
            if (esp32PreviewBtnDryeye) esp32PreviewBtnDryeye.disabled = false;
            // Re-enable analyze after preview exists (simple approach: allow retry)
            if (esp32AnalyzeBtnDryeye) esp32AnalyzeBtnDryeye.disabled = false;
        }
    }

    function displayResults(data) {
        const riskLabel = document.getElementById('riskLabel');
        const riskAlert = document.getElementById('riskAlert');
        const blinkCount = document.getElementById('blinkCount');
        const blinkRate = document.getElementById('blinkRate');
        const meanIbi = document.getElementById('meanIbi');
        const maxEyeOpen = document.getElementById('maxEyeOpen');
        const timestamp = document.getElementById('timestamp');
        const interpretation = document.getElementById('interpretation');

        // Update risk label and color
        if (riskLabel) riskLabel.textContent = data.label;
        if (riskAlert) {
            if (data.label === 'Dry Eye Risk') {
                riskAlert.className = 'alert alert-warning mb-4';
            } else if (data.label === 'Insufficient Data') {
                riskAlert.className = 'alert alert-secondary mb-4';
            } else {
                riskAlert.className = 'alert alert-success mb-4';
            }
        }

        // Update metrics
        if (blinkCount) blinkCount.textContent = data.blink_count;
        if (blinkRate) blinkRate.textContent = data.blink_rate_bpm;
        if (meanIbi) meanIbi.textContent = data.mean_ibi_sec + 's';
        if (maxEyeOpen) maxEyeOpen.textContent = data.max_eye_open_sec + 's';
        if (timestamp) timestamp.textContent = new Date().toLocaleString();

        // Show any backend note (helps user fix capture quality)
        if (interpretation && data.note) {
            interpretation.innerHTML = `<small><strong>Note:</strong> ${data.note}</small>`;
        }

        // Store test results in session
        sessionStorage.setItem('dryEyeResults', JSON.stringify(data));

        // Update print template with patient and results data
        updatePrintTemplate(data);

        // Show results card and next button
        if (resultsCard) resultsCard.style.display = 'block';
        if (nextBtn) nextBtn.style.display = 'block';
        if (resultsCard) resultsCard.scrollIntoView({ behavior: 'smooth' });

        // Auto-advance to report after 10 seconds
        startAutoNextCountdown('report.html', 'Full Report', 10);
    }

    function updatePrintTemplate(data) {
        const patientData = JSON.parse(sessionStorage.getItem('patientData') || '{}');

        // Patient information
        if (document.getElementById('printPatientName')) {
            document.getElementById('printPatientName').textContent = patientData.name || '--';
            document.getElementById('printPatientAge').textContent = patientData.age || '--';
            document.getElementById('printPatientGender').textContent = patientData.gender || '--';
            document.getElementById('printDate').textContent = new Date().toLocaleDateString();

            // Test results
            document.getElementById('printRiskLabel').textContent = data.label;
            const printRiskLabel = document.getElementById('printRiskLabel').parentElement;
            if (data.label === 'Dry Eye Risk') {
                printRiskLabel.style.backgroundColor = '#fff3cd';
                printRiskLabel.style.borderLeftColor = '#ff9800';
            } else {
                printRiskLabel.style.backgroundColor = '#d4edda';
                printRiskLabel.style.borderLeftColor = '#28a745';
            }

            // Metrics
            document.getElementById('printBlinkCount').textContent = data.blink_count;
            document.getElementById('printBlinkRate').textContent = data.blink_rate_bpm + ' BPM';
            document.getElementById('printMeanIbi').textContent = data.mean_ibi_sec + ' s';
            document.getElementById('printMaxEyeOpen').textContent = data.max_eye_open_sec + ' s';

            // Generated date
            document.getElementById('printGeneratedDate').textContent = new Date().toLocaleString();
        }
    }

    // Print functionality
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
                    <title>Dry Eye Analysis Report - NAYAN-AI</title>
                    <style>
                        @media print { body { margin: 0; padding: 20px; } }
                        body { font-family: Arial, sans-serif; }
                        .header { text-align: center; margin-bottom: 30px; }
                        .header h1 { color: #0066cc; margin: 0; }
                        .content { margin: 20px 0; }
                        .section { margin-bottom: 20px; padding: 15px; border-left: 4px solid #0066cc; }
                        .metric { display: flex; justify-content: space-between; margin: 10px 0; }
                        .label { font-weight: bold; }
                        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 12px; }
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
            fetch(`${API_BASE}/report/dryeye/pdf/${patientId}`)
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
                    a.download = `DryEye_Report_${patientData.name || 'Patient'}_${new Date().toISOString().split('T')[0]}.pdf`;
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

    // ESP32 Dry Eye handlers
    if (esp32PreviewBtnDryeye) {
        esp32PreviewBtnDryeye.addEventListener('click', function() {
            const deviceId = (esp32DeviceIdDryeye && esp32DeviceIdDryeye.value) ? esp32DeviceIdDryeye.value.trim() : 'esp32cam1';
            previewLatestEsp32DryeyeFrame(deviceId);
        });
    }

    if (esp32AnalyzeBtnDryeye) {
        esp32AnalyzeBtnDryeye.addEventListener('click', function() {
            const deviceId = (esp32DeviceIdDryeye && esp32DeviceIdDryeye.value) ? esp32DeviceIdDryeye.value.trim() : 'esp32cam1';
            const seconds = (esp32SecondsDryeye && esp32SecondsDryeye.value) ? esp32SecondsDryeye.value : 30;
            analyzeEsp32Dryeye(deviceId, seconds);
        });
    }

    if (esp32LiveStartBtnDryeye) {
        esp32LiveStartBtnDryeye.addEventListener('click', startEsp32LiveDryeye);
    }
    if (esp32LiveStopBtnDryeye) {
        esp32LiveStopBtnDryeye.addEventListener('click', stopEsp32LiveDryeye);
    }
    if (esp32RecordBtnDryeye) {
        esp32RecordBtnDryeye.addEventListener('click', recordEsp32Mp4Dryeye);
    }

    // Auto-start live preview when entering the page
    try {
        if (esp32LiveStartBtnDryeye && esp32LiveImgDryeye) {
            startEsp32LiveDryeye();
        }
    } catch (e) {
        // non-fatal
    }
});
