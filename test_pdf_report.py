"""
Test PDF Report Generation
Quick test to verify the PDF endpoint works
"""

import requests
import json

# Configuration
BASE_URL = "http://127.0.0.1:5000"
API_BASE = f"{BASE_URL}/api"

def test_pdf_generation():
    """Test PDF report generation for a patient"""
    
    print("=" * 60)
    print("TESTING PDF REPORT GENERATION")
    print("=" * 60)
    
    # Test with patient ID 1 (adjust if needed)
    patient_id = 1
    
    print(f"\n1. Requesting PDF report for patient ID: {patient_id}")
    print(f"   Endpoint: {API_BASE}/report/pdf/{patient_id}")
    
    try:
        response = requests.get(f"{API_BASE}/report/pdf/{patient_id}")
        
        print(f"\n2. Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS - PDF generated successfully!")
            
            # Save the PDF to test file
            filename = f"test_report_patient_{patient_id}.pdf"
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            print(f"\n3. PDF saved as: {filename}")
            print(f"   File size: {len(response.content)} bytes")
            print("\n✅ TEST PASSED - PDF report generation working!")
            
            return True
            
        elif response.status_code == 404:
            print("   ❌ ERROR - Patient not found")
            print("   Make sure patient ID 1 exists in database")
            
            # Try to get patient info
            print("\n   Checking patient data...")
            patient_response = requests.get(f"{API_BASE}/patient/{patient_id}")
            if patient_response.status_code == 200:
                data = patient_response.json()
                print(f"   Patient data: {json.dumps(data, indent=2)}")
            else:
                print(f"   Cannot fetch patient data: {patient_response.status_code}")
                
            return False
            
        else:
            print(f"   ❌ ERROR - Unexpected status code")
            print(f"   Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("   ❌ ERROR - Cannot connect to backend server")
        print("   Make sure the backend is running on http://127.0.0.1:5000")
        print("\n   Start backend with:")
        print("   cd backend")
        print("   python app.py")
        return False
        
    except Exception as e:
        print(f"   ❌ ERROR - {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_patient_exists():
    """Check if a patient exists to test with"""
    
    print("\n" + "=" * 60)
    print("CHECKING FOR TEST PATIENT")
    print("=" * 60)
    
    try:
        # Try to get patient list or create a test patient
        response = requests.get(f"{API_BASE}/patient/1")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                patient = data.get('patient', {})
                print(f"\n✅ Found test patient:")
                print(f"   ID: {patient.get('id')}")
                print(f"   Name: {patient.get('name')}")
                print(f"   Age: {patient.get('age')}")
                return True
        
        print("\n⚠️  No test patient found (ID: 1)")
        print("   You can create one through the web interface")
        print("   Or use a different patient ID in the test")
        return False
        
    except Exception as e:
        print(f"\n❌ Error checking patient: {str(e)}")
        return False

if __name__ == "__main__":
    print("\nNAYAN-AI PDF Report Generation Test")
    print("Make sure backend server is running first!\n")
    
    # Check if patient exists
    patient_exists = test_patient_exists()
    
    # Test PDF generation
    if patient_exists:
        success = test_pdf_generation()
        
        if success:
            print("\n" + "=" * 60)
            print("🎉 ALL TESTS PASSED!")
            print("=" * 60)
            print("\nYou can now:")
            print("1. Open the generated PDF file to verify content")
            print("2. Test from web interface: Full Report → Download PDF")
            print("3. The PDF includes all three screening types:")
            print("   - Cataract Screening")
            print("   - Dry Eye Screening")
            print("   - Glaucoma Screening")
        else:
            print("\n" + "=" * 60)
            print("❌ TEST FAILED")
            print("=" * 60)
            print("\nTroubleshooting:")
            print("1. Make sure backend is running")
            print("2. Check if reportlab is installed: pip install reportlab")
            print("3. Verify patient exists in database")
            print("4. Check backend logs for errors")
    else:
        print("\n⚠️  Cannot test PDF generation without a patient")
        print("   Create a patient first through the web interface")
