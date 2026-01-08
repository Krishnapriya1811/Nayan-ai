// Main app-level JS - Complete authentication and patient data flow

// Use same-origin API when served by the backend.
// NOTE: use `var` so it can be safely re-declared across multiple script files.
var API_BASE = `${window.location.origin}/api`;

// Check if user is logged in, redirect to login if not
document.addEventListener('DOMContentLoaded', function() {
    const currentPage = window.location.pathname;

    // Restore login from localStorage if user opted for "Remember me".
    if (!sessionStorage.getItem('userId')) {
        const remembered = localStorage.getItem('rememberMe') === 'true';
        if (remembered) {
            const userId = localStorage.getItem('userId');
            const userName = localStorage.getItem('userName');
            const userEmail = localStorage.getItem('userEmail');
            if (userId) {
                sessionStorage.setItem('userId', userId);
                if (userName) sessionStorage.setItem('userName', userName);
                if (userEmail) sessionStorage.setItem('userEmail', userEmail);
            }
        }
    }
    
    // List of pages that require login
    // Glaucoma UI is intentionally excluded (hardware-only).
    const protectedPages = [
        '/index', '/index.html',
        '/cataract', '/cataract.html',
        '/dryeye', '/dryeye.html',
        '/history', '/history.html',
        '/patient', '/patient_input', '/patient_input.html'
    ];
    
    // Check if current page is protected
    const isProtected = protectedPages.some(page => currentPage === page || currentPage.endsWith(page));
    
    if (isProtected && !sessionStorage.getItem('userId')) {
        window.location.href = 'login.html';
        return;
    }

    // Display logged-in user info
    displayUserInfo();

    // Handle patient info form
    const patientForm = document.getElementById('patientInfoForm');
    if (patientForm) {
        patientForm.addEventListener('submit', function(e) {
            e.preventDefault();
            savePatientData();
        });
    }

    // Add logout functionality
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function() {
            sessionStorage.clear();
            localStorage.removeItem('rememberMe');
            localStorage.removeItem('userId');
            localStorage.removeItem('userName');
            localStorage.removeItem('userEmail');
            window.location.href = 'login.html';
        });
    }
});

function displayUserInfo() {
    const userName = sessionStorage.getItem('userName');
    const userEmail = sessionStorage.getItem('userEmail');
    
    const userDisplay = document.querySelector('[id*="userDisplay"]') || 
                        document.querySelector('[class*="userDisplay"]');
    
    if (userDisplay && userName) {
        userDisplay.textContent = `Welcome, ${userName}`;
    }
}

function savePatientData() {
    const patientForm = document.getElementById('patientInfoForm');
    const userId = sessionStorage.getItem('userId');
    
    // Collect form data
    const patientData = {
        user_id: userId,
        name: document.getElementById('patientName').value,
        age: document.getElementById('patientAge').value,
        gender: document.getElementById('patientGender').value,
        phone: document.getElementById('patientPhone').value,
        email: document.getElementById('patientEmail').value,
        medicalHistory: document.getElementById('medicalHistory').value,
        familyHistory: document.getElementById('familyHistory').value
    };

    // Show loading
    const submitBtn = patientForm.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';

    // Send to backend
    fetch(`${API_BASE}/patient`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(patientData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Store patient data and ID in session
            sessionStorage.setItem('patientData', JSON.stringify(patientData));
            sessionStorage.setItem('patientId', data.patient_id);
            
            // Show confirmation
            showAlert('Patient information saved successfully! You can now proceed to screening.', 'success');

            // Disable form and button
            patientForm.style.display = 'none';
            
            // Show screening modules section
            setTimeout(() => {
                const modulesSection = document.getElementById('modules') || 
                                      document.querySelector('[id*="modules"]') ||
                                      document.querySelector('section:nth-of-type(3)');
                if (modulesSection) {
                    modulesSection.scrollIntoView({ behavior: 'smooth' });
                }
            }, 1500);
        } else {
            showAlert(data.message || 'Failed to save patient information', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error: Backend is not reachable', 'danger');
    })
    .finally(() => {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    });
}

// Show alert function
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const patientForm = document.getElementById('patientInfoForm');
    const mainContent = document.querySelector('main') || document.body;
    
    if (patientForm) {
        patientForm.parentElement.insertBefore(alertDiv, patientForm);
    } else {
        mainContent.insertBefore(alertDiv, mainContent.firstChild);
    }
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}
