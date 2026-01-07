# 🏥 NAYAN-AI - Eye Screening System
## Complete Frontend-Backend Integration Guide

---

## 📋 Table of Contents
1. [System Overview](#system-overview)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Running the System](#running-the-system)
5. [API Documentation](#api-documentation)
6. [Mobile Camera Integration](#mobile-camera-integration)
7. [Workflow Guide](#workflow-guide)
8. [Troubleshooting](#troubleshooting)

---

## 🎯 System Overview

NAYAN-AI is a comprehensive AI-powered eye screening system with:

### **Features**
- ✅ **Cataract Detection** - Image-based analysis
- ✅ **Dry Eye Analysis** - Video blink pattern analysis
- ✅ **Glaucoma Screening** - IOP measurement and tracking
- ✅ **Patient Management** - Full patient data storage
- ✅ **WebSocket Support** - Real-time mobile camera streaming
- ✅ **Database Integration** - SQLite3 for persistent storage
- ✅ **REST API** - Complete REST endpoints for all operations
- ✅ **Multi-User Support** - Authentication and user management

### **Architecture**

```
┌─────────────────────────────────────────────────────┐
│                 FRONTEND (Web Browser)               │
│  HTML5 | Bootstrap 5 | JavaScript | Session Storage │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ HTTP/REST & WebSocket
                   │
┌──────────────────▼──────────────────────────────────┐
│              BACKEND (Flask + SocketIO)              │
│  API Endpoints | Image Processing | Video Analysis  │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ SQLite3 ORM
                   │
┌──────────────────▼──────────────────────────────────┐
│           DATABASE (SQLite3 nayan_ai.db)             │
│  Users | Patients | Results | History | Analytics   │
└─────────────────────────────────────────────────────┘
```

---

## 📦 Requirements

### **System Requirements**
- Windows 10/11 or Linux/Mac
- Python 3.9 or higher
- Laptop with browser supporting HTML5
- Mobile device (optional, for camera streaming)
- 500MB+ free disk space

### **Python Dependencies**
```
Flask >= 2.3.0
Flask-CORS >= 4.0.0
Flask-SocketIO >= 5.3.0
OpenCV >= 4.5.0
NumPy >= 1.21.0
TensorFlow >= 2.12.0
SQLite3 (built-in)
```

---

## 💾 Installation

### **Step 1: Navigate to Project Directory**
```bash
cd "c:\Users\krishnapriyas\OneDrive\Desktop\NAYAN-AI\Nayan-ai"
```

### **Step 2: Install Python Dependencies**
```bash
cd backend
pip install -r requirements.txt
```

### **Step 3: Verify Installation**
```bash
python -c "import flask, cv2, numpy; print('✓ All dependencies installed')"
```

---

## ▶️ Running the System

### **Option 1: Using Batch Script (Windows)**
Double-click the `START_BACKEND.bat` file in the project root:
```
c:\Users\krishnapriyas\OneDrive\Desktop\NAYAN-AI\Nayan-ai\START_BACKEND.bat
```

### **Option 2: Manual Start**
```bash
cd "c:\Users\krishnapriyas\OneDrive\Desktop\NAYAN-AI\Nayan-ai\backend"
python app.py
```

### **Expected Output**
```
╔════════════════════════════════════════╗
║         NAYAN-AI BACKEND SERVER        ║
║     Eye Screening System v1.0          ║
╠════════════════════════════════════════╣
║ REST API:  http://0.0.0.0:5000         ║
║ WebSocket: ws://0.0.0.0:5000           ║
║ Database:  SQLite3 (nayan_ai.db)       ║
╚════════════════════════════════════════╝
```

---

## 🌐 Accessing the Frontend

### **Open in Browser**
```
http://localhost/frontend/login.html
```

Or use file path:
```
file:///c:/Users/krishnapriyas/OneDrive/Desktop/NAYAN-AI/Nayan-ai/frontend/login.html
```

### **Demo Login**
- **Email:** demo@nayan-ai.com
- **Password:** demo123
- **Click:** "Demo Login" button

---

## 📡 API Documentation

### **Base URL**
```
http://localhost:5000/api
```

### **Authentication Endpoints**

#### **1. User Registration**
```
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password",
  "name": "User Name"
}

Response:
{
  "success": true,
  "message": "Registration successful",
  "user_id": 1
}
```

#### **2. User Login**
```
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password"
}

Response:
{
  "success": true,
  "message": "Login successful",
  "user_id": 1,
  "name": "User Name",
  "email": "user@example.com"
}
```

### **Patient Management Endpoints**

#### **3. Save Patient Data**
```
POST /patient
Content-Type: application/json

{
  "user_id": 1,
  "name": "John Doe",
  "age": 45,
  "gender": "Male",
  "phone": "9876543210",
  "email": "john@example.com",
  "medicalHistory": "None",
  "familyHistory": "Cataract"
}

Response:
{
  "success": true,
  "message": "Patient saved",
  "patient_id": 1
}
```

#### **4. Get Patient Data**
```
GET /patient/{patient_id}

Response:
{
  "success": true,
  "patient": {
    "id": 1,
    "name": "John Doe",
    "age": 45,
    "gender": "Male",
    "phone": "9876543210",
    "email": "john@example.com"
  }
}
```

### **Screening Endpoints**

#### **5. Upload Cataract Image**
```
POST /cataract/upload
Content-Type: multipart/form-data

Parameters:
- image: [binary image file]
- patient_id: [integer]

Response:
{
  "success": true,
  "result_id": 1,
  "analysis": {
    "contrast": 25.4,
    "sharpness": 145.3,
    "edge": 18.2,
    "label": "Normal",
    "confidence": 92.5
  },
  "image_url": "/uploads/cataract/cataract_1234567890.jpg"
}
```

#### **6. Upload Dry Eye Video**
```
POST /dryeye/upload
Content-Type: multipart/form-data

Parameters:
- video: [binary video file]
- patient_id: [integer]

Response:
{
  "success": true,
  "result_id": 1,
  "analysis": {
    "duration_sec": 30.2,
    "blink_count": 8,
    "blink_rate_bpm": 16.5,
    "mean_ibi_sec": 3.75,
    "max_ibi_sec": 5.6,
    "max_eye_open_sec": 4.3,
    "label": "Normal"
  },
  "video_url": "/uploads/dryeye/dryeye_1234567890.mp4"
}
```

#### **7. Glaucoma Measurement**
```
POST /glaucoma/measure
Content-Type: application/json

{
  "patient_id": 1,
  "iop_proxy": 18.5
}

Response:
{
  "success": true,
  "result_id": 1,
  "analysis": {
    "iop_proxy": 18.5,
    "risk_level": "Normal"
  }
}
```

### **Results Endpoints**

#### **8. Get Screening Results**
```
GET /results/{result_type}/{patient_id}

Result Types: cataract, dryeye, glaucoma

Response:
{
  "success": true,
  "results": [...],
  "count": 5
}
```

#### **9. Health Check**
```
GET /health

Response:
{
  "status": "healthy",
  "service": "NAYAN-AI Backend",
  "timestamp": "2026-01-07T10:30:00"
}
```

---

## 📱 Mobile Camera Integration

### **Using WebSocket for Camera Streaming**

#### **1. Get Your Laptop IP Address**
```bash
# On Windows
ipconfig
# Look for "IPv4 Address" under your active network adapter
# Example: 192.168.1.100
```

#### **2. Access from Mobile**
Open mobile browser and go to:
```
http://{your-laptop-ip}:5000
```

Example:
```
http://192.168.1.100:5000
```

#### **3. WebSocket Events**

**Connect to Stream**
```javascript
const socket = io('http://192.168.1.100:5000');

socket.emit('start_stream', {
  patient_id: 1,
  stream_type: 'cataract'  // or 'dryeye', 'glaucoma'
});
```

**Send Frame**
```javascript
// Capture camera frame and send as base64
socket.emit('frame', {
  frame: 'data:image/jpeg;base64,/9j/4AAQ...',
  patient_id: 1
});
```

**Receive Acknowledgment**
```javascript
socket.on('frame_received', (data) => {
  console.log('Frame received by server:', data.status);
});
```

**Stop Stream**
```javascript
socket.emit('stop_stream');
```

---

## 🔄 Workflow Guide

### **Step-by-Step Screening Process**

```
┌──────────────────────────────────────────────────┐
│ STEP 1: USER AUTHENTICATION                      │
├──────────────────────────────────────────────────┤
│ 1. Open http://localhost/frontend/login.html     │
│ 2. Click "Demo Login" or enter credentials       │
│ 3. System saves user_id in sessionStorage         │
│ 4. Redirected to index.html (dashboard)          │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ STEP 2: PATIENT DATA COLLECTION                  │
├──────────────────────────────────────────────────┤
│ 1. Fill patient information form:                │
│    - Name, Age, Gender                           │
│    - Phone, Email                                │
│    - Medical History                             │
│    - Family History                              │
│ 2. Submit form                                   │
│ 3. System:                                       │
│    - POST /patient endpoint                      │
│    - Saves patient_id in sessionStorage           │
│    - Hides form, shows screening modules         │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ STEP 3A: GLAUCOMA SCREENING                      │
├──────────────────────────────────────────────────┤
│ 1. Navigate to Glaucoma tab                      │
│ 2. Check hardware status (auto-refresh)          │
│ 3. Click "Take Measurement"                      │
│ 4. System:                                       │
│    - POST /glaucoma/measure                      │
│    - Gets IOP proxy value                        │
│    - Stores result in database                   │
│ 5. View result badge (Normal/High Risk)          │
│ 6. Proceed to Step 4                             │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ STEP 3B: CATARACT SCREENING                      │
├──────────────────────────────────────────────────┤
│ 1. Navigate to Cataract tab                      │
│ 2. Click "Select or capture image"               │
│ 3. Choose eye image from device/camera           │
│ 4. Preview image                                 │
│ 5. Click "Upload & Predict"                      │
│ 6. System:                                       │
│    - POST /cataract/upload                       │
│    - Extracts features (Contrast, Sharpness)     │
│    - Classifies: Normal or Possible Risk         │
│    - Shows confidence score                      │
│ 7. View detailed analysis                        │
│ 8. Proceed to Step 4                             │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ STEP 3C: DRY EYE SCREENING                       │
├──────────────────────────────────────────────────┤
│ 1. Navigate to Dry Eye tab                       │
│ 2. Click "Select Video File"                     │
│ 3. Upload 30-60 second eye video                 │
│ 4. System:                                       │
│    - POST /dryeye/upload                         │
│    - Analyzes blink patterns                     │
│    - Calculates metrics:                         │
│      * Blink count & rate                        │
│      * Inter-blink interval (IBI)                │
│      * Eye opening duration                      │
│    - Classifies: Normal or Dry Eye Risk          │
│ 5. View detailed analysis                        │
│ 6. Proceed to Step 4                             │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ STEP 4: VIEW SCREENING HISTORY                   │
├──────────────────────────────────────────────────┤
│ 1. Navigate to History tab                       │
│ 2. System loads:                                 │
│    - GET /results/cataract/{patient_id}          │
│    - GET /results/dryeye/{patient_id}            │
│    - GET /results/glaucoma/{patient_id}          │
│ 3. Display results in tables                     │
│ 4. Download reports (JSON format)                │
│ 5. Print results                                 │
└──────────────────────────────────────────────────┘
```

---

## 🐛 Troubleshooting

### **Issue 1: "Cannot connect to backend"**

**Symptom:** Frontend shows "Failed to upload image" or "Connection error"

**Solution:**
1. Check if backend is running:
   ```bash
   netstat -ano | findstr ":5000"
   ```
2. If no process, start backend:
   ```bash
   python app.py
   ```
3. Test connection:
   ```bash
   python -c "import requests; print(requests.get('http://localhost:5000/api/health').json())"
   ```

### **Issue 2: Port 5000 Already in Use**

**Symptom:** "OSError: [WinError 10048] Only one usage of each socket address"

**Solution:**
```bash
# Find process using port 5000
netstat -ano | findstr ":5000"

# Kill the process (replace PID with actual number)
taskkill /PID {PID} /F

# Start server again
python app.py
```

### **Issue 3: Database Locked**

**Symptom:** "sqlite3.OperationalError: database is locked"

**Solution:**
1. Close all instances of the backend
2. Delete `nayan_ai.db`
3. Restart the backend (it will recreate the database)

### **Issue 4: Missing Dependencies**

**Symptom:** "ModuleNotFoundError: No module named 'flask_socketio'"

**Solution:**
```bash
pip install -r requirements.txt --upgrade
```

### **Issue 5: Frontend Not Accessible**

**Symptom:** "Cannot open http://localhost/frontend/login.html"

**Solution:**
Use file path instead:
```
file:///c:/Users/krishnapriyas/OneDrive/Desktop/NAYAN-AI/Nayan-ai/frontend/login.html
```

Or setup a local web server:
```bash
# Using Python
cd frontend
python -m http.server 8000

# Then access at: http://localhost:8000/login.html
```

---

## 📊 Database Schema

### **Tables**

**users**
```sql
id (INTEGER PRIMARY KEY)
email (TEXT UNIQUE)
password (TEXT)
name (TEXT)
created_at (TIMESTAMP)
```

**patients**
```sql
id (INTEGER PRIMARY KEY)
user_id (INTEGER FOREIGN KEY)
name (TEXT)
age (INTEGER)
gender (TEXT)
phone (TEXT)
email (TEXT)
medical_history (TEXT)
family_history (TEXT)
created_at (TIMESTAMP)
```

**cataract_results**
```sql
id (INTEGER PRIMARY KEY)
patient_id (INTEGER FOREIGN KEY)
image_file (TEXT)
contrast (REAL)
sharpness (REAL)
edge_strength (REAL)
label (TEXT)
confidence (REAL)
timestamp (TIMESTAMP)
```

**dryeye_results**
```sql
id (INTEGER PRIMARY KEY)
patient_id (INTEGER FOREIGN KEY)
video_file (TEXT)
duration_sec (REAL)
blink_count (INTEGER)
blink_rate_bpm (REAL)
mean_ibi_sec (REAL)
max_ibi_sec (REAL)
max_eye_open_sec (REAL)
label (TEXT)
timestamp (TIMESTAMP)
```

**glaucoma_results**
```sql
id (INTEGER PRIMARY KEY)
patient_id (INTEGER FOREIGN KEY)
iop_proxy (REAL)
risk_level (TEXT)
timestamp (TIMESTAMP)
```

---

## 🔒 Security Notes

⚠️ **Important:** This is a demonstration system. For production use:

1. **Replace hardcoded secret key** in `app.py`
2. **Use environment variables** for sensitive data
3. **Add JWT token authentication** instead of sessionStorage
4. **Implement HTTPS/SSL** encryption
5. **Add rate limiting** to prevent abuse
6. **Hash passwords** with bcrypt or similar
7. **Validate all user inputs** server-side
8. **Add CORS restrictions** to specific domains
9. **Regular database backups**
10. **HIPAA compliance** for medical data

---

## 📞 Support

For issues or questions:
1. Check the **Troubleshooting** section
2. Review API documentation
3. Check server logs for errors
4. Verify all dependencies are installed

---

## 📝 Version Information

- **NAYAN-AI Version:** 1.0
- **Backend:** Flask 2.3+
- **Frontend:** HTML5 + Bootstrap 5 + Vanilla JavaScript
- **Database:** SQLite3
- **Python:** 3.9+
- **Last Updated:** January 7, 2026

---

## 👥 Team

**Developed by:**
- Krishnapriya S (ECE)
- Madhumitha S (ECE)
- Mahalakshmi B S (ECE)

**Electronics and Communication Engineering Department**

---

**Happy Screening! 👁️ 🎉**
