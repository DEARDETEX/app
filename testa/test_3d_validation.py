#!/usr/bin/env python3
"""
Focused test script for 3D geometry validation functionality
Tests the critical 3D file parsing that was just implemented
"""

import requests
import os
import tempfile
import json
from pathlib import Path

class GeometryValidationTester:
    def __init__(self):
        self.base_url = "http://localhost:8001/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.uploaded_models = []

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
            if details:
                print(f"   {details}")
        else:
            print(f"❌ {name}")
            if details:
                print(f"   {details}")

    def test_valid_obj_upload(self):
        """Test uploading valid OBJ file with geometry validation"""
        print("\n🔍 Testing Valid OBJ Upload with Geometry Validation...")
        
        test_file = "/app/test_cube.obj"
        if not os.path.exists(test_file):
            self.log_test("Valid OBJ Upload", False, f"Test file not found: {test_file}")
            return False

        try:
            with open(test_file, 'rb') as f:
                files = {'file': ('test_cube.obj', f, 'application/octet-stream')}
                response = requests.post(f"{self.base_url}/upload-model", files=files)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ['id', 'filename', 'processing_status', 'file_size']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Valid OBJ Upload", False, f"Missing fields: {missing_fields}")
                    return False
                
                # Verify processing status is "validated" (not just "uploaded")
                if data['processing_status'] != 'validated':
                    self.log_test("Valid OBJ Upload", False, f"Expected processing_status='validated', got '{data['processing_status']}'")
                    return False
                
                # Store model ID for cleanup
                self.uploaded_models.append(data['id'])
                
                self.log_test("Valid OBJ Upload", True, 
                    f"Model ID: {data['id']}, Status: {data['processing_status']}, Size: {data['file_size']} bytes")
                return True
            else:
                self.log_test("Valid OBJ Upload", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Valid OBJ Upload", False, f"Exception: {str(e)}")
            return False

    def test_invalid_geometry_rejection(self):
        """Test that files without valid 3D geometry are rejected"""
        print("\n🔍 Testing Invalid Geometry Rejection...")
        
        # Create a fake OBJ file with no geometry
        fake_obj_content = """# Fake OBJ file with no geometry
# This should be rejected by validation
mtllib fake.mtl
usemtl Material
"""
        
        try:
            with tempfile.NamedTemporaryFile(suffix='.obj', delete=False) as tmp_file:
                tmp_file.write(fake_obj_content.encode())
                tmp_file.flush()
                
                with open(tmp_file.name, 'rb') as f:
                    files = {'file': ('fake_model.obj', f, 'application/octet-stream')}
                    response = requests.post(f"{self.base_url}/upload-model", files=files)
                
                # Clean up temp file
                os.unlink(tmp_file.name)
            
            if response.status_code == 400:
                error_data = response.json()
                if "Invalid 3D file" in error_data.get('detail', ''):
                    self.log_test("Invalid Geometry Rejection", True, 
                        f"Correctly rejected: {error_data['detail']}")
                    return True
                else:
                    self.log_test("Invalid Geometry Rejection", False, 
                        f"Wrong error message: {error_data.get('detail', 'No detail')}")
                    return False
            else:
                self.log_test("Invalid Geometry Rejection", False, 
                    f"Expected HTTP 400, got {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Invalid Geometry Rejection", False, f"Exception: {str(e)}")
            return False

    def test_unsupported_file_type(self):
        """Test that unsupported file types are rejected"""
        print("\n🔍 Testing Unsupported File Type Rejection...")
        
        try:
            # Create a text file
            text_content = b"This is not a 3D model file"
            files = {'file': ('not_a_model.txt', text_content, 'text/plain')}
            response = requests.post(f"{self.base_url}/upload-model", files=files)
            
            if response.status_code == 400:
                error_data = response.json()
                if "Unsupported file type" in error_data.get('detail', ''):
                    self.log_test("Unsupported File Type Rejection", True, 
                        f"Correctly rejected: {error_data['detail']}")
                    return True
                else:
                    self.log_test("Unsupported File Type Rejection", False, 
                        f"Wrong error message: {error_data.get('detail', 'No detail')}")
                    return False
            else:
                self.log_test("Unsupported File Type Rejection", False, 
                    f"Expected HTTP 400, got {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Unsupported File Type Rejection", False, f"Exception: {str(e)}")
            return False

    def test_file_size_limit(self):
        """Test file size limit enforcement"""
        print("\n🔍 Testing File Size Limit...")
        
        try:
            # Create a large fake OBJ file (simulate 51MB)
            large_content = b"# Large fake OBJ\n" + b"v 0 0 0\n" * (51 * 1024 * 1024 // 10)  # ~51MB
            files = {'file': ('large_model.obj', large_content, 'application/octet-stream')}
            response = requests.post(f"{self.base_url}/upload-model", files=files)
            
            if response.status_code == 400:
                error_data = response.json()
                if "File too large" in error_data.get('detail', ''):
                    self.log_test("File Size Limit", True, 
                        f"Correctly rejected: {error_data['detail']}")
                    return True
                else:
                    self.log_test("File Size Limit", False, 
                        f"Wrong error message: {error_data.get('detail', 'No detail')}")
                    return False
            else:
                self.log_test("File Size Limit", False, 
                    f"Expected HTTP 400, got {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("File Size Limit", False, f"Exception: {str(e)}")
            return False

    def test_file_cleanup_on_validation_failure(self):
        """Test that invalid files are deleted from disk after validation fails"""
        print("\n🔍 Testing File Cleanup on Validation Failure...")
        
        # Get initial file count
        uploads_dir = Path("/app/backend/uploads")
        initial_files = set(uploads_dir.glob("*fake*"))
        
        # Try to upload an invalid file
        fake_obj_content = b"# Invalid OBJ\nThis is not valid geometry\n"
        
        try:
            files = {'file': ('cleanup_test.obj', fake_obj_content, 'application/octet-stream')}
            response = requests.post(f"{self.base_url}/upload-model", files=files)
            
            # Check that no new fake files were left behind
            final_files = set(uploads_dir.glob("*cleanup_test*"))
            
            if response.status_code == 400 and len(final_files) == len(initial_files):
                self.log_test("File Cleanup on Validation Failure", True, 
                    "Invalid file was properly deleted after validation failed")
                return True
            elif response.status_code == 400:
                self.log_test("File Cleanup on Validation Failure", False, 
                    f"File not cleaned up. Found {len(final_files)} files with cleanup_test pattern")
                return False
            else:
                self.log_test("File Cleanup on Validation Failure", False, 
                    f"Expected validation failure (400), got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("File Cleanup on Validation Failure", False, f"Exception: {str(e)}")
            return False

    def test_uploads_directory_structure(self):
        """Test that files are saved to correct uploads directory"""
        print("\n🔍 Testing Uploads Directory Structure...")
        
        uploads_dir = Path("/app/backend/uploads")
        
        if not uploads_dir.exists():
            self.log_test("Uploads Directory Structure", False, "Uploads directory does not exist")
            return False
        
        # Check if our uploaded files are there
        obj_files = list(uploads_dir.glob("*.obj"))
        
        if len(obj_files) > 0:
            self.log_test("Uploads Directory Structure", True, 
                f"Found {len(obj_files)} OBJ files in uploads directory")
            return True
        else:
            self.log_test("Uploads Directory Structure", False, 
                "No OBJ files found in uploads directory")
            return False

    def cleanup_uploaded_models(self):
        """Clean up models uploaded during testing"""
        print("\n🧹 Cleaning up uploaded test models...")
        
        for model_id in self.uploaded_models:
            try:
                response = requests.delete(f"{self.base_url}/model/{model_id}")
                if response.status_code == 200:
                    print(f"   ✅ Deleted model {model_id}")
                else:
                    print(f"   ⚠️  Failed to delete model {model_id}: HTTP {response.status_code}")
            except Exception as e:
                print(f"   ❌ Error deleting model {model_id}: {str(e)}")

    def run_all_tests(self):
        """Run all 3D geometry validation tests"""
        print("🚀 Starting 3D Geometry Validation Tests")
        print("=" * 60)
        
        # Run tests in order
        test_methods = [
            self.test_valid_obj_upload,
            self.test_invalid_geometry_rejection,
            self.test_unsupported_file_type,
            self.test_file_size_limit,
            self.test_file_cleanup_on_validation_failure,
            self.test_uploads_directory_structure,
        ]
        
        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                print(f"❌ Test {test_method.__name__} failed with exception: {str(e)}")
                self.tests_run += 1
        
        # Cleanup
        self.cleanup_uploaded_models()
        
        # Print results
        print("\n" + "=" * 60)
        print(f"📊 3D Geometry Validation Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All 3D geometry validation tests passed!")
            return True
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} tests failed")
            return False

def main():
    tester = GeometryValidationTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())