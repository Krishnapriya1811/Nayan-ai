// Dry Eye Detection Page JavaScript
// Complete API integration with backend

// Use same-origin API when served by the backend.
// NOTE: use `var` so it can be safely re-declared across multiple script files.
var API_BASE = `${window.location.origin}/api`;

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

    function displayResults(data) {
        const riskLabel = document.getElementById('riskLabel');
        const riskAlert = document.getElementById('riskAlert');
        const blinkCount = document.getElementById('blinkCount');
        const blinkRate = document.getElementById('blinkRate');
        const meanIbi = document.getElementById('meanIbi');
        const maxEyeOpen = document.getElementById('maxEyeOpen');
        const timestamp = document.getElementById('timestamp');

        // Update risk label and color
        if (riskLabel) riskLabel.textContent = data.label;
        if (riskAlert) {
            if (data.label === 'Dry Eye Risk') {
                riskAlert.className = 'alert alert-warning mb-4';
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

        // Store test results in session
        sessionStorage.setItem('dryEyeResults', JSON.stringify(data));

        // Update print template with patient and results data
        updatePrintTemplate(data);

        // Show results card and next button
        if (resultsCard) resultsCard.style.display = 'block';
        if (nextBtn) nextBtn.style.display = 'block';
        if (resultsCard) resultsCard.scrollIntoView({ behavior: 'smooth' });
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
});
