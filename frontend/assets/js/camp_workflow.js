// Camp Workflow JavaScript - Streamlined for Rural Camp Nurses
// Sequential testing: Patient Info → Glaucoma → Cataract → Dry Eye → Report

var API_BASE = `${window.location.origin}/api`;

let currentStep = 0;
let patientCount = parseInt(localStorage.getItem('campPatientCount') || '0');
let currentPatientId = null;
let screeningResults = {
    glaucoma: null,
    cataract: null,
    dryeye: null
};

document.addEventListener('DOMContentLoaded', function() {
    const userId = sessionStorage.getItem('userId');
    if (!userId) {
        alert('Please login first');
        window.location.href = 'login.html';
        return;
    }

    updatePatientCounter();
    setupEventListeners();
});

function setupEventListeners() {
    // Step 1: Patient Form
    document.getElementById('patientForm')?.addEventListener('submit', handlePatientSubmit);
    
    // Step 2: Glaucoma
    document.getElementById('glaucomaSubmit')?.addEventListener('click', handleGlaucomaSubmit);
    document.getElementById('iopValue')?.addEventListener('input', calculateGlaucomaRisk);
    
    // Step 3: Cataract
    document.getElementById('cataractImage')?.addEventListener('change', handleCataractImageSelect);
    document.getElementById('cataractSubmit')?.addEventListener('click', handleCataractSubmit);
    
    // Step 4: Dry Eye
    document.getElementById('dryeyeVideo')?.addEventListener('change', handleDryeyeVideoSelect);
    document.getElementById('dryeyeSubmit')?.addEventListener('click', handleDryeyeSubmit);
}

function updatePatientCounter() {
    document.getElementById('patientCounter').textContent = `Patient: ${patientCount}`;
}

function startNewPatient() {
    document.getElementById('welcomeCard').style.display = 'none';
    goToStep(1);
}

function startNextPatient() {
    // Quick restart for next patient
    currentPatientId = null;
    screeningResults = { glaucoma: null, cataract: null, dryeye: null };
    
    // Clear forms
    document.getElementById('patientForm').reset();
    document.getElementById('cataractImage').value = '';
    document.getElementById('dryeyeVideo').value = '';
    document.getElementById('iopValue').value = '';
    
    // Clear results
    document.getElementById('cataractPreview').style.display = 'none';
    
    goToStep(1);
}

function goToStep(step) {
    // Hide all steps
    for (let i = 1; i <= 5; i++) {
        document.getElementById(`step${i}`).style.display = 'none';
        document.getElementById(`step${i}Badge`).classList.remove('bg-primary', 'bg-success');
        document.getElementById(`step${i}Badge`).classList.add('bg-secondary');
    }
    
    // Show current step
    document.getElementById(`step${step}`).style.display = 'block';
    document.getElementById(`step${step}Badge`).classList.remove('bg-secondary');
    document.getElementById(`step${step}Badge`).classList.add('bg-primary');
    
    // Mark completed steps
    for (let i = 1; i < step; i++) {
        document.getElementById(`step${i}Badge`).classList.remove('bg-secondary', 'bg-primary');
        document.getElementById(`step${i}Badge`).classList.add('bg-success');
    }
    
    // Update progress bar
    const progress = ((step - 1) / 4) * 100;
    document.getElementById('overallProgress').style.width = progress + '%';
    
    currentStep = step;
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// STEP 1: Patient Information
async function handlePatientSubmit(e) {
    e.preventDefault();
    
    const submitBtn = e.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';
    
    const patientData = {
        user_id: sessionStorage.getItem('userId'),
        name: document.getElementById('patientName').value,
        age: document.getElementById('patientAge').value,
        gender: document.getElementById('patientGender').value,
        phone: document.getElementById('patientPhone').value,
        email: document.getElementById('patientEmail').value || '',
        medicalHistory: document.getElementById('medicalHistory').value,
        familyHistory: document.getElementById('familyHistory').value
    };
    
    try {
        const response = await fetch(`${API_BASE}/patient`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patientData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentPatientId = data.patient_id;
            sessionStorage.setItem('patientId', currentPatientId);
            sessionStorage.setItem('patientData', JSON.stringify(patientData));
            
            patientCount++;
            localStorage.setItem('campPatientCount', patientCount);
            updatePatientCounter();
            
            goToStep(2);
        } else {
            alert('Failed to save patient info: ' + data.message);
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Connection error. Please check backend.');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// STEP 2: Glaucoma Screening
function calculateGlaucomaRisk() {
    const iop = parseFloat(document.getElementById('iopValue').value);
    const resultDiv = document.getElementById('glaucomaResult');
    
    if (!iop || iop < 5 || iop > 40) {
        resultDiv.classList.add('d-none');
        return;
    }
    
    let riskLevel, riskClass, message;
    
    if (iop < 12) {
        riskLevel = "Low Risk";
        riskClass = "alert-info";
        message = "IOP is below normal range. Monitor for hypotony.";
    } else if (iop <= 21) {
        riskLevel = "Normal";
        riskClass = "alert-success";
        message = "IOP is within normal range.";
    } else {
        riskLevel = "High Risk";
        riskClass = "alert-danger";
        message = "⚠️ ELEVATED IOP! Refer to ophthalmologist immediately.";
    }
    
    resultDiv.className = `alert ${riskClass}`;
    resultDiv.innerHTML = `<strong>${riskLevel}:</strong> IOP ${iop} mmHg - ${message}`;
    resultDiv.classList.remove('d-none');
}

async function handleGlaucomaSubmit() {
    const iopValue = parseFloat(document.getElementById('iopValue').value);
    const eye = document.getElementById('glaucomaEye').value;
    
    if (!iopValue) {
        alert('Please enter IOP value');
        return;
    }
    
    const submitBtn = document.getElementById('glaucomaSubmit');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';
    
    try {
        const response = await fetch(`${API_BASE}/glaucoma/measure`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: currentPatientId,
                iop_proxy: iopValue,
                eye: eye
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            screeningResults.glaucoma = data.analysis;
            goToStep(3);
        } else {
            alert('Failed to save glaucoma results: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Connection error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// STEP 3: Cataract Screening
function handleCataractImageSelect(e) {
    const file = e.target.files[0];
    const submitBtn = document.getElementById('cataractSubmit');
    
    if (!file) {
        submitBtn.disabled = true;
        return;
    }
    
    // Show preview
    const reader = new FileReader();
    reader.onload = function(event) {
        document.getElementById('cataractImg').src = event.target.result;
        document.getElementById('cataractPreview').style.display = 'block';
    };
    reader.readAsDataURL(file);
    
    submitBtn.disabled = false;
}

async function handleCataractSubmit() {
    const fileInput = document.getElementById('cataractImage');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select an image');
        return;
    }
    
    const submitBtn = document.getElementById('cataractSubmit');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Analyzing...';
    
    const resultDiv = document.getElementById('cataractResult');
    resultDiv.classList.add('d-none');
    
    const formData = new FormData();
    formData.append('image', file);
    formData.append('patient_id', currentPatientId);
    
    try {
        const response = await fetch(`${API_BASE}/cataract/upload`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            screeningResults.cataract = data.analysis;
            
            // Show result
            const isRisk = data.analysis.label.includes('Risk');
            resultDiv.className = `alert ${isRisk ? 'alert-warning' : 'alert-success'}`;
            resultDiv.innerHTML = `<strong>${data.analysis.label}</strong> - Confidence: ${data.analysis.confidence.toFixed(1)}%`;
            resultDiv.classList.remove('d-none');
            
            setTimeout(() => goToStep(4), 1500);
        } else {
            alert('Failed to analyze image: ' + data.message);
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Connection error');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// STEP 4: Dry Eye Screening
function handleDryeyeVideoSelect(e) {
    const file = e.target.files[0];
    const submitBtn = document.getElementById('dryeyeSubmit');
    
    if (!file) {
        submitBtn.disabled = true;
        return;
    }
    
    submitBtn.disabled = false;
}

async function handleDryeyeSubmit() {
    const fileInput = document.getElementById('dryeyeVideo');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a video');
        return;
    }
    
    const submitBtn = document.getElementById('dryeyeSubmit');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Analyzing...';
    
    const resultDiv = document.getElementById('dryeyeResult');
    resultDiv.classList.add('d-none');
    
    const formData = new FormData();
    formData.append('video', file);
    formData.append('patient_id', currentPatientId);
    
    try {
        const response = await fetch(`${API_BASE}/dryeye/upload`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            screeningResults.dryeye = data.analysis;
            
            // Show result
            const isRisk = data.analysis.label.includes('Risk');
            resultDiv.className = `alert ${isRisk ? 'alert-warning' : 'alert-success'}`;
            resultDiv.innerHTML = `<strong>${data.analysis.label}</strong> - Blink Rate: ${data.analysis.blink_rate_bpm.toFixed(1)} BPM`;
            resultDiv.classList.remove('d-none');
            
            setTimeout(() => goToStep(5), 1500);
        } else {
            alert('Failed to analyze video: ' + data.message);
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Connection error');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}
