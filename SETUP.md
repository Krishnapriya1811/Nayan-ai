# ⚡ QUICK START GUIDE - NAYAN-AI

## 🚀 Get Started in 5 Minutes

### **Step 1: Start Backend Server**

**Option A - Double-click (Windows)**
```
START_BACKEND.bat
```

**Option B - Command Line**
```bash
cd backend
python app.py
```

**Expected Output:**
```
╔════════════════════════════════════════╗
║    NAYAN-AI BACKEND SERVER RUNNING     ║
║    http://0.0.0.0:5000                 ║
╚════════════════════════════════════════╝
```

---

### **Step 2: Open Frontend in Browser**

**Copy-paste one of these URLs:**

```
file:///c:/Users/krishnapriyas/OneDrive/Desktop/NAYAN-AI/Nayan-ai/frontend/login.html
```

Or use local server:
```bash
cd frontend
python -m http.server 8000
# Then open: http://localhost:8000/login.html
```

---

### **Step 3: Login**

**Demo Credentials:**
- Email: `demo@nayan-ai.com`
- Password: `demo123`
- Click: **Demo Login** button

---

### **Step 4: Use the System**

**Complete Flow:**

1. **Dashboard (index.html)**
   - Fill patient information form
   - Click "Proceed to Screening"

2. **Step 1: Glaucoma**
   - Click "Take Measurement"
   - View IOP Proxy result
   - Check Risk Level badge

3. **Step 2: Cataract**
   - Click "Select or capture image"
   - Upload eye image
   - View analysis & confidence score

4. **Step 3: Dry Eye**
   - Click "Select Video File"
   - Upload 30-60 second eye video
   - View blink metrics

5. **History**
   - View all screening results
   - Download reports
   - Print records

---

## 🔌 API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/register` | User registration |
| POST | `/api/patient` | Save patient data |
| GET | `/api/patient/{id}` | Get patient info |
| POST | `/api/cataract/upload` | Upload cataract image |
| POST | `/api/dryeye/upload` | Upload dry eye video |
| POST | `/api/glaucoma/measure` | Record glaucoma measurement |
| GET | `/api/results/{type}/{id}` | Get screening results |
| GET | `/api/health` | Health check |

---

## 📱 Mobile Camera Access

Get your laptop IP:
```bash
ipconfig
# Look for IPv4 Address, e.g., 192.168.1.100
```

Open on mobile:
```
http://192.168.1.100:5000
```

---

## 🆘 Quick Troubleshoot

**Issue:** "Cannot connect to localhost:5000"
```bash
# Check if port is free
netstat -ano | findstr ":5000"

# If occupied, kill process
taskkill /PID {PID} /F
```

**Issue:** Module not found
```bash
pip install -r backend/requirements.txt
```

**Issue:** Browser shows blank/loading
```bash
# Clear browser cache: Ctrl+Shift+Delete
# Or use Ctrl+Shift+R to hard refresh
```

---

## 📊 File Structure

```
Nayan-ai/
├── backend/
│   ├── app.py                 ← Main server
│   ├── requirements.txt        ← Dependencies
│   ├── uploads/               ← Uploaded images/videos
│   └── nayan_ai.db            ← SQLite database
├── frontend/
│   ├── login.html             ← Login page
│   ├── index.html             ← Dashboard
│   ├── cataract.html          ← Cataract screening
│   ├── dryeye.html            ← Dry eye screening
│   ├── glaucoma.html          ← Glaucoma screening
│   ├── history.html           ← Results history
│   ├── assets/
│   │   ├── css/style.css
│   │   └── js/
│   │       ├── app.js
│   │       ├── cataract.js
│   │       ├── dryeye.js
│   │       ├── glaucoma.js
│   │       └── history.js
├── START_BACKEND.bat
├── README.md
└── test_integration.py
```

---

## ✅ System Status Check

Run this to verify everything works:

```bash
python test_integration.py
```

Expected output:
```
╔═══════════════════════════════════════════════════════════════╗
║                    TEST SUMMARY                               ║
╠═══════════════════════════════════════════════════════════════╣
║ ✓ Backend Server: RUNNING                                     ║
║ ✓ Database: SQLite3 initialized                               ║
║ ✓ Authentication: Working (Login/Register)                    ║
║ ✓ Patient Management: Working                                 ║
║ ✓ Glaucoma Module: Working                                    ║
║ ✓ Results Storage: Working                                    ║
║ ✓ API Endpoints: All accessible                               ║
║                                                               ║
║            🎉 ALL SYSTEMS GO! 🎉                             ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 🎯 Key Features

✅ **Complete Integration**
- Frontend ↔ Backend fully connected
- Real-time data sync via API
- Database persistence

✅ **Three Screening Modules**
- Cataract detection with image analysis
- Dry eye detection with blink pattern analysis
- Glaucoma screening with IOP measurement

✅ **Multi-User Support**
- User authentication & registration
- Patient management
- Screening history tracking

✅ **Mobile Ready**
- Responsive Bootstrap UI
- Mobile camera streaming (WebSocket)
- Portrait/landscape support

✅ **Data Management**
- SQLite3 database
- Automatic result logging
- Report export (JSON)
- Print functionality

---

## 📞 Need Help?

1. **Check README.md** - Full documentation
2. **Review API docs** - Detailed endpoint guide
3. **Check logs** - See console output for errors
4. **Verify setup** - Run test_integration.py

---

## 🎉 You're All Set!

Enjoy using NAYAN-AI! 👁️

**Start the backend, open the frontend, and begin screening!**
