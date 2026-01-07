#!/usr/bin/env python
"""Test cataract upload endpoint"""
import requests
import cv2
import numpy as np
import time

# Create a test image
test_img_path = 'test_eye_image.png'
test_img = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
cv2.imwrite(test_img_path, test_img)
print(f"[TEST] Created test image: {test_img_path}")

# Test upload
api_url = 'http://localhost:5000/api/cataract/upload'
patient_id = '1'

try:
    with open(test_img_path, 'rb') as f:
        files = {'image': f}
        data = {'patient_id': patient_id}
        
        print(f"\n[TEST] Uploading to {api_url}")
        print(f"[TEST] Patient ID: {patient_id}")
        
        response = requests.post(api_url, files=files, data=data, timeout=10)
        
        print(f"[TEST] Response Status: {response.status_code}")
        print(f"[TEST] Response Headers: {dict(response.headers)}")
        print(f"[TEST] Response Body: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n[SUCCESS] Upload successful!")
            print(f"Result ID: {result.get('result_id')}")
            print(f"Analysis: {result.get('analysis')}")
        else:
            print(f"\n[ERROR] Upload failed with status {response.status_code}")
            
except Exception as e:
    print(f"[ERROR] Exception occurred: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
import os
if os.path.exists(test_img_path):
    os.remove(test_img_path)
    print(f"\n[TEST] Cleaned up test image")
