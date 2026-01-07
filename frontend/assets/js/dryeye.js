// Dry Eye Detection Page JavaScript
// Complete API integration with backend

const API_BASE = 'http://localhost:5000/api';

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
    videoInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            // Validate file size (max 100MB)
            const maxSize = 100 * 1024 * 1024;
            if (file.size > maxSize) {
                alert('File size exceeds 100MB limit');
                videoInput.value = '';
                return;
            }

            fileName.textContent = file.name;
            videoPreview.style.display = 'block';
        }
    });

    // Form submission handler
    dryeyeForm.addEventListener('submit', function(e) {
        e.preventDefault();

        const file = videoInput.files[0];
        if (!file) {
            alert('Please select a video file');
            return;
        }

        uploadVideo(file);
    });

    function uploadVideo(file) {
        // Show loading spinner
        loadingSpinner.style.display = 'block';
        resultsCard.style.display = 'none';
        nextBtn.style.display = 'none';
        dryeyeForm.style.display = 'none';

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
                alert('Analysis failed: ' + data.message);
                dryeyeForm.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to upload video. Make sure backend is running at http://localhost:5000');
            dryeyeForm.style.display = 'block';
        })
        .finally(() => {
            loadingSpinner.style.display = 'none';
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
        riskLabel.textContent = data.label;
        if (data.label === 'Dry Eye Risk') {
            riskAlert.className = 'alert alert-warning mb-4';
        } else {
            riskAlert.className = 'alert alert-success mb-4';
        }

        // Update metrics
        blinkCount.textContent = data.blink_count;
        blinkRate.textContent = data.blink_rate_bpm;
        meanIbi.textContent = data.mean_ibi_sec + 's';
        maxEyeOpen.textContent = data.max_eye_open_sec + 's';
        timestamp.textContent = new Date().toLocaleString();

        // Store test results in session
        sessionStorage.setItem('dryEyeResults', JSON.stringify(data));

        // Update print template with patient and results data
        updatePrintTemplate(data);

        // Show results card and next button
        resultsCard.style.display = 'block';
        nextBtn.style.display = 'block';
        resultsCard.scrollIntoView({ behavior: 'smooth' });
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
            const printContent = document.getElementById('printTemplate').innerHTML;
            const printWindow = window.open('', '', 'height=600,width=800');
            
            printWindow.document.write(`
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Dry Eye Analysis Report - NAYAN-AI</title>
                    <style>
                        @media print {
                            body { margin: 0; padding: 20px; }
                        }
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

    // Download functionality
    if (downloadBtn) {
        downloadBtn.addEventListener('click', function() {
            const patientData = JSON.parse(sessionStorage.getItem('patientData') || '{}');
            const dryeyeResults = JSON.parse(sessionStorage.getItem('dryEyeResults') || '{}');
            
            const reportData = {
                patient: patientData,
                test_type: 'Dry Eye Detection',
                results: dryeyeResults,
                date: new Date().toISOString()
            };
            
            const dataStr = JSON.stringify(reportData, null, 2);
            const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
            
            const exportFileDefaultName = `dry_eye_report_${Date.now()}.json`;
            
            const linkElement = document.createElement('a');
            linkElement.setAttribute('href', dataUri);
            linkElement.setAttribute('download', exportFileDefaultName);
            linkElement.click();
        });
    }
});
                    </style>
                </head>
                <body>
                    ${printContent}
                    <script>
                        window.print();
                        window.close();
                    </script>
                </body>
                </html>
            `);
            printWindow.document.close();
        });
    }

    // Download as PDF (simple version - creates downloadable HTML)
    if (downloadBtn) {
        downloadBtn.addEventListener('click', function() {
            const printContent = document.getElementById('printTemplate').innerHTML;
            const htmlContent = `
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Dry Eye Analysis Report - NAYAN-AI</title>
                    <style>
                        body { font-family: Arial, sans-serif; margin: 20px; }
                    </style>
                </head>
                <body>
                    ${printContent}
                </body>
                </html>
            `;
            
            const blob = new Blob([htmlContent], { type: 'text/html' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `NAYAN-AI_DryEye_Report_${new Date().getTime()}.html`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        });
    }
});
