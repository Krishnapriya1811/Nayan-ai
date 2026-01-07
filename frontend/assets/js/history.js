// History Page JavaScript
// Load and display screening results

const API_BASE = 'http://localhost:5000/api';

document.addEventListener('DOMContentLoaded', function() {
    const patientId = sessionStorage.getItem('patientId');
    
    if (!patientId) {
        alert('Please login first');
        window.location.href = 'login.html';
        return;
    }

    // Load results when page loads
    loadResults();

    // Tab switching
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

    fetch(`${API_BASE}/results/cataract/${patientId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.results.length > 0) {
                let html = `
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
                
                data.results.forEach(result => {
                    const timestamp = new Date(result[7]).toLocaleString();
                    const resultClass = result[6].includes('Risk') ? 'bg-warning' : 'bg-success';
                    
                    html += `
                        <tr>
                            <td>${timestamp}</td>
                            <td>${result[3].toFixed(2)}</td>
                            <td>${result[4].toFixed(2)}</td>
                            <td><span class="badge ${resultClass}">${result[6]}</span></td>
                            <td>${result[7]}</td>
                            <td>
                                <a href="/uploads/cataract/${result[2]}" target="_blank" class="btn btn-sm btn-primary">
                                    <i class="bi bi-download"></i>
                                </a>
                            </td>
                        </tr>
                    `;
                });
                
                html += `</tbody></table>`;
                container.innerHTML = html;
            } else {
                container.innerHTML = `
                    <div class="alert alert-info text-center">
                        <i class="bi bi-info-circle me-2"></i>No cataract screening records found.
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    Error loading records. Backend may not be available.
                </div>
            `;
        });
}

        let html = '<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>Patient</th><th>Result</th><th>Confidence</th><th>Date</th></tr></thead><tbody>';
        
        records.forEach(record => {
            const badgeClass = record.result === 'Normal' ? 'bg-success' : 'bg-warning';
            html += `<tr>
                <td>${record.patient}</td>
                <td><span class="badge ${badgeClass}">${record.result}</span></td>
                <td>${record.confidence}%</td>
                <td>${record.date}</td>
            </tr>`;
        });
        
        html += '</tbody></table></div>';
        container.innerHTML = html;
    }

    function loadDryeyeRecords() {
        const container = document.getElementById('dryeyeTable');
        const records = sampleRecords.dryeye;
        
        if (records.length === 0) {
            container.innerHTML = '<div class="alert alert-info text-center"><i class="bi bi-info-circle me-2"></i>No dry eye screening records found.</div>';
            return;
        }

        let html = '<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>Patient</th><th>Blink Rate (BPM)</th><th>Result</th><th>Date</th></tr></thead><tbody>';
        
        records.forEach(record => {
            const badgeClass = record.result === 'Normal' ? 'bg-success' : 'bg-warning';
            html += `<tr>
                <td>${record.patient}</td>
                <td>${record.blinkRate}</td>
                <td><span class="badge ${badgeClass}">${record.result}</span></td>
                <td>${record.date}</td>
            </tr>`;
        });
        
        html += '</tbody></table></div>';
        container.innerHTML = html;
    }

    function loadGlaucomaRecords() {
        const container = document.getElementById('glaucomaTable');
        const records = sampleRecords.glaucoma;
        
        if (records.length === 0) {
            container.innerHTML = '<div class="alert alert-info text-center"><i class="bi bi-info-circle me-2"></i>No glaucoma screening records found.</div>';
            return;
        }

        let html = '<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>Patient</th><th>IOP (mmHg)</th><th>Result</th><th>Date</th></tr></thead><tbody>';
        
        records.forEach(record => {
            const badgeClass = record.result === 'Normal' ? 'bg-success' : 'bg-danger';
            html += `<tr>
                <td>${record.patient}</td>
                <td>${record.iop}</td>
                <td><span class="badge ${badgeClass}">${record.result}</span></td>
                <td>${record.date}</td>
            </tr>`;
        });
        
        html += '</tbody></table></div>';
        container.innerHTML = html;
    }

    function searchRecords(type, query) {
        const records = sampleRecords[type];
        const filteredRecords = records.filter(record => 
            record.patient.toLowerCase().includes(query.toLowerCase()) ||
            record.result.toLowerCase().includes(query.toLowerCase())
        );

        let container;
        if (type === 'cataract') {
            container = document.getElementById('cataractTable');
        } else if (type === 'dryeye') {
            container = document.getElementById('dryeyeTable');
        } else {
            container = document.getElementById('glaucomaTable');
        }

        if (filteredRecords.length === 0) {
            container.innerHTML = '<div class="alert alert-warning text-center"><i class="bi bi-search me-2"></i>No matching records found.</div>';
            return;
        }

        if (type === 'cataract') {
            let html = '<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>Patient</th><th>Result</th><th>Confidence</th><th>Date</th></tr></thead><tbody>';
            filteredRecords.forEach(record => {
                const badgeClass = record.result === 'Normal' ? 'bg-success' : 'bg-warning';
                html += `<tr><td>${record.patient}</td><td><span class="badge ${badgeClass}">${record.result}</span></td><td>${record.confidence}%</td><td>${record.date}</td></tr>`;
            });
            html += '</tbody></table></div>';
            container.innerHTML = html;
        } else if (type === 'dryeye') {
            let html = '<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>Patient</th><th>Blink Rate (BPM)</th><th>Result</th><th>Date</th></tr></thead><tbody>';
            filteredRecords.forEach(record => {
                const badgeClass = record.result === 'Normal' ? 'bg-success' : 'bg-warning';
                html += `<tr><td>${record.patient}</td><td>${record.blinkRate}</td><td><span class="badge ${badgeClass}">${record.result}</span></td><td>${record.date}</td></tr>`;
            });
            html += '</tbody></table></div>';
            container.innerHTML = html;
        } else {
            let html = '<div class="table-responsive"><table class="table table-hover"><thead class="table-light"><tr><th>Patient</th><th>IOP (mmHg)</th><th>Result</th><th>Date</th></tr></thead><tbody>';
            filteredRecords.forEach(record => {
                const badgeClass = record.result === 'Normal' ? 'bg-success' : 'bg-danger';
                html += `<tr><td>${record.patient}</td><td>${record.iop}</td><td><span class="badge ${badgeClass}">${record.result}</span></td><td>${record.date}</td></tr>`;
            });
            html += '</tbody></table></div>';
            container.innerHTML = html;
        }
    }
});
