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
