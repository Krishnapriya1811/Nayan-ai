# 🏥 NAYAN-AI Camp Workflow - User Guide for Rural Nurses

## Overview
The Camp Workflow is specifically designed for rural camp nurses who need to screen 100+ patients efficiently in a single day. It provides a streamlined, step-by-step process with automatic data storage and printable reports.

---

## 🚀 Quick Start for Camp Nurses

### Access Camp Mode
**Option 1: Direct Link**
- Open browser: `http://127.0.0.1:5000/camp_workflow.html`

**Option 2: From Login Page**
- Click green **"Camp Mode (Quick Access)"** button
- Automatically logs in as "Camp Nurse" user

**Option 3: From Dashboard**
- Login → Click **"Camp Mode"** button in hero section

---

## 📋 Complete Workflow (5 Steps)

### **Step 1: Patient Information** ✅
**What to collect:**
- Full Name (Required)
- Age (Required)
- Gender (Required)
- Phone Number (Required)
- Email (Optional)
- Medical History (Any existing eye conditions, medications)
- Family History (Family history of eye diseases)

**Time: ~2 minutes**

**Action:** Click **"Save & Continue to Glaucoma"**

---

### **Step 2: Glaucoma Screening** 🔴
**Required:** IOP (Intraocular Pressure) measurement

**How to perform:**
1. Use tonometer device (or manual measurement)
2. Enter IOP reading in mmHg (typical range: 10-21)
3. Select which eye(s) tested
4. System automatically shows risk level:
   - **Normal:** 12-21 mmHg (Green)
   - **High Risk:** >21 mmHg (Red - Refer immediately!)
   - **Low Risk:** <12 mmHg (Blue - Monitor)

**Time: ~1 minute**

**Action:** Click **"Save & Continue to Cataract"**

---

### **Step 3: Cataract Screening** 🟡
**Required:** Clear eye photograph

**How to perform:**
1. Click "Upload Eye Image"
2. Use mobile camera or upload photo
3. Ensure:
   - Good lighting
   - Eye centered in frame
   - No strong reflections
4. AI analyzes image automatically
5. Results show:
   - "Normal" (Green) or "Possible Cataract Risk" (Yellow)
   - Confidence score (0-100%)

**Time: ~1 minute**

**Action:** Click **"Save & Continue to Dry Eye"**

---

### **Step 4: Dry Eye Screening** 🟢
**Required:** 15-30 second video of natural blinking

**How to perform:**
1. Click "Upload Blink Video"
2. Record video of patient's eye(s)
3. Patient should blink naturally (don't force)
4. AI analyzes:
   - Blink count
   - Blink rate (blinks per minute)
   - Eye open duration
5. Results show:
   - "Normal" (Green) or "Dry Eye Risk" (Yellow)
   - Blink rate (normal: >10 BPM)

**Time: ~1-2 minutes**

**Action:** Click **"Save & Generate Report"**

---

### **Step 5: Complete & Report** ✅
**All screenings done!**

**Available actions:**
1. **"View & Print Comprehensive Report"** (Opens in new tab)
   - Complete patient information
   - All 3 screening results
   - AI recommendations
   - Print-ready format
   
2. **"Start Next Patient (Quick)"** ⭐ RECOMMENDED
   - Immediately begins next patient
   - Patient counter increments
   - All forms cleared
   - Fastest way to continue
   
3. **"Back to Start"**
   - Returns to welcome screen
   - Use for breaks

**Time: ~30 seconds**

---

## ⏱️ Total Time Per Patient
**Average: 5-7 minutes**
- Patient Info: 2 min
- Glaucoma: 1 min
- Cataract: 1 min
- Dry Eye: 1-2 min
- Report: 30 sec

**Capacity:**
- **100 patients:** ~10-12 hours (with breaks)
- **50 patients:** ~5-6 hours

---

## 📊 What Gets Stored in Database

### For Each Patient:
✅ **Patient Information:**
- Name, Age, Gender, Phone, Email
- Medical history, Family history
- Registration timestamp

✅ **Glaucoma Results:**
- IOP measurement
- Risk level classification
- Test timestamp

✅ **Cataract Results:**
- Eye image (saved to uploads/cataract/)
- AI prediction (Normal/Risk)
- Confidence score
- Contrast, sharpness metrics
- Test timestamp

✅ **Dry Eye Results:**
- Blink video (saved to uploads/dryeye/)
- Blink count and rate
- Inter-blink intervals
- Risk classification
- Test timestamp

---

## 🖨️ Printing Reports

### Comprehensive Report Features:
- **Patient demographics** with photo
- **Summary dashboard** with color-coded results
- **Detailed results** for all 3 screenings
- **Medical recommendations** based on findings
- **Disclaimers** (screening only, not diagnosis)

### How to Print:
1. Click "View & Print Comprehensive Report"
2. Report opens in new tab
3. Click browser "Print" or use Ctrl+P
4. Select printer
5. Print or save as PDF

### Print Options:
- **Single page:** Quick summary
- **Full report:** All details (2-3 pages)
- **Save as PDF:** For digital records

---

## 🔄 Best Practices for Camps

### Before Starting Camp:
1. ✅ Test system with 1-2 dummy patients
2. ✅ Ensure good internet/network connection
3. ✅ Have backup power (laptop battery)
4. ✅ Test printer connectivity
5. ✅ Prepare tonometer and camera

### During Camp:
1. ⚡ Use "Start Next Patient (Quick)" for speed
2. 📱 Keep phone/camera charged
3. 💾 Backend auto-saves everything
4. 🔍 Double-check patient names
5. ✍️ Mark urgent cases (High IOP) immediately

### After Camp:
1. 📊 View all results in History page
2. 📥 Export data to Excel/CSV
3. 🖨️ Print batch reports if needed
4. 🔒 Logout when done

---

## 🎯 Progress Tracking

### Visual Indicators:
- **Progress bar:** Shows overall completion (0-100%)
- **Step badges:** Color-coded (Gray → Blue → Green)
- **Patient counter:** Total patients screened today

### Example Progress:
```
Patient Counter: 23
[✓][✓][✓][⚫][ ] - Currently on Step 4 (Dry Eye)
████████████░░░░ 75%
```

---

## ⚠️ Important Medical Notes

### When to Refer Immediately:
1. **High IOP** (>21 mmHg) → Glaucoma risk
2. **Multiple "Risk" results** → Comprehensive exam needed
3. **Patient complaints** of pain, vision loss, flashing lights

### Disclaimers:
- ⚠️ This is a **SCREENING TOOL** only
- ⚠️ NOT a medical diagnosis
- ⚠️ All high-risk patients MUST see ophthalmologist
- ⚠️ System assists, nurse makes final call

---

## 🛠️ Troubleshooting

### Problem: Can't upload image/video
**Solution:**
- Check file size (max 500MB)
- Use supported formats (JPG, PNG, MP4, WEBM)
- Try different browser (Chrome recommended)

### Problem: Backend not responding
**Solution:**
- Check if `START_BACKEND.bat` is running
- Restart backend server
- Check network connection

### Problem: Results not saving
**Solution:**
- Ensure patient ID was created in Step 1
- Check browser console (F12) for errors
- Verify database write permissions

### Problem: Can't print report
**Solution:**
- Check printer connectivity
- Try "Save as PDF" instead
- Use print preview to adjust settings

---

## 📞 Quick Reference

| Task | Time | Action |
|------|------|--------|
| Start Day | 1 min | Click "Camp Mode" → Login |
| New Patient | 2 min | Fill patient form |
| Glaucoma Test | 1 min | Enter IOP reading |
| Cataract Test | 1 min | Upload eye photo |
| Dry Eye Test | 1-2 min | Upload blink video |
| Generate Report | 30 sec | Print/Save |
| **Next Patient** | **0 sec** | **Click "Start Next Patient"** |

---

## 🎓 Training Checklist for Nurses

Before camp day, ensure nurses can:
- [ ] Login to camp mode
- [ ] Enter patient information completely
- [ ] Use tonometer and record IOP
- [ ] Take clear eye photographs
- [ ] Record blink videos properly
- [ ] Read and interpret results
- [ ] Print comprehensive reports
- [ ] Start next patient quickly
- [ ] Identify high-risk cases
- [ ] Export data for records

---

## 📈 Expected Results

### After 100 Patients:
- ✅ 100 complete patient records in database
- ✅ ~300 screening results (100×3 tests)
- ✅ All data timestamped and searchable
- ✅ Printable reports for each patient
- ✅ Exportable CSV for camp summary
- ✅ High-risk cases identified

### Data Retention:
- Stored in: `nayan_ai.db` (SQLite database)
- Images/Videos: `uploads/` folders
- Accessible via: History page or Report page
- Export format: CSV/Excel compatible

---

## ✅ Camp Mode Advantages

1. **⚡ Speed**: Optimized for 100+ patients/day
2. **📱 Mobile-Friendly**: Works on tablets/phones
3. **🔄 Quick Restart**: "Next Patient" in 1 click
4. **💾 Auto-Save**: No data loss
5. **📊 Tracking**: Patient counter shows progress
6. **🖨️ Print-Ready**: Professional reports
7. **🎯 Guided**: Step-by-step, can't skip
8. **📈 Sequential**: Glaucoma → Cataract → Dry Eye

---

**Ready to start? Click "Camp Mode (Quick Access)" and begin screening!**

*NAYAN-AI v1.0 - Optimized for Rural Eye Screening Camps*
