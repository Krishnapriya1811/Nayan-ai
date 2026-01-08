// Cataract Detection Page JavaScript
// Complete integration with backend API

// Use same-origin API when served by the backend.
// NOTE: use `var` so it can be safely re-declared across multiple script files.
var API_BASE = `${window.location.origin}/api`;

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
