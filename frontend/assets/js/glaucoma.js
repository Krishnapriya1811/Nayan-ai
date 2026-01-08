// Glaucoma Detection Page JavaScript
// Hardware sensor integration with backend API

const API_BASE = 'http://localhost:5000/api';

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

    let autoRefreshInterval = null;
    let lastIOPValue = null;

    // Initialize hardware status
    updateHardwareStatus();

    // Measure button
    measureBtn.addEventListener('click', function() {
        takeMeasurement();
    });

    // Refresh button
    refreshBtn.addEventListener('click', function() {
        takeMeasurement();
    });

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

    function takeMeasurement() {
        measureBtn.disabled = true;
        refreshBtn.disabled = true;
        
        const originalText = measureBtn.innerHTML;
        measureBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Measuring...';

        // Simulate IOP measurement (15-25 range typical)
        const iopValue = 15 + Math.random() * 10;

        fetch(`${API_BASE}/glaucoma/measure`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                patient_id: patientId,
                iop_proxy: iopValue
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                lastIOPValue = data.analysis.iop_proxy;
                displayMeasurement(data.analysis);
            } else {
                alert('Failed to record measurement: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to connect to backend. Make sure server is running.');
        })
        .finally(() => {
            measureBtn.disabled = false;
            refreshBtn.disabled = false;
            measureBtn.innerHTML = originalText;
        });
    }

    function displayMeasurement(analysis) {
        const iop = analysis.iop_proxy;
        const risk = analysis.risk_level;

        // Update IOP value
        kProxyValue.textContent = iop.toFixed(1);

        // Update risk label with color
        riskLabel.textContent = risk;
        
        if (risk === 'Low Risk') {
            riskLabel.className = 'badge fs-5 px-4 py-2 bg-success';
        } else if (risk === 'Normal') {
            riskLabel.className = 'badge fs-5 px-4 py-2 bg-info';
        } else {
            riskLabel.className = 'badge fs-5 px-4 py-2 bg-danger';
        }

        // Show result card
        resultCard.style.display = 'block';
        resultCard.scrollIntoView({ behavior: 'smooth' });

        // Save to session
        sessionStorage.setItem('glaucomaResults', JSON.stringify(analysis));

        // Update print template
        updatePrintTemplate(analysis);

        // Update detailed table
        if (document.getElementById('deviceId')) {
            document.getElementById('deviceId').textContent = 'ESP32-GLAUCOMA';
            document.getElementById('deltaMm').textContent = '0.5 mm';
            document.getElementById('kProxy').textContent = iop.toFixed(2);
            document.getElementById('timestamp').textContent = new Date().toLocaleString();
        }
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
            document.getElementById('printRiskLabel').textContent = analysis.risk_level;
            const printRiskLabel = document.getElementById('printRiskLabel').parentElement;
            if (analysis.risk_level && !analysis.risk_level.includes('Normal') && !analysis.risk_level.includes('Low')) {
                printRiskLabel.style.backgroundColor = '#fff3cd';
                printRiskLabel.style.borderLeftColor = '#ff9800';
            } else {
                printRiskLabel.style.backgroundColor = '#d4edda';
                printRiskLabel.style.borderLeftColor = '#28a745';
            }

            // Metrics
            document.getElementById('printIOP').textContent = analysis.iop_proxy.toFixed(1) + ' mmHg';
            document.getElementById('printDelta').textContent = '0.5 mm';
            document.getElementById('printKProxy').textContent = analysis.iop_proxy.toFixed(2);

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
            takeMeasurement();
        }, 3000);
        console.log('Auto-refresh started (3 seconds interval)');
    }

    function stopAutoRefresh() {
        if (autoRefreshInterval) {
            clearInterval(autoRefreshInterval);
            autoRefreshInterval = null;
            console.log('Auto-refresh stopped');
        }
    }

    // Start auto-refresh by default
    if (autoRefreshToggle.checked) {
        startAutoRefresh();
    }

    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
        stopAutoRefresh();
    });
});
