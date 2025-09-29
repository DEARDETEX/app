import requests
import sys
import os
import time
import json
from datetime import datetime
from pathlib import Path

class HoloForgeAPITester:
    def __init__(self, base_url="https://amazing-matsumoto.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        # Use localhost for video endpoints due to routing issues
        self.local_api_url = "http://localhost:8001/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.uploaded_model_id = None
        self.video_job_id = None
        self.video_path = None

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if not endpoint.startswith('http') else endpoint
        headers = {}
        if data and not files:
            headers['Content-Type'] = 'application/json'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, data=data)
                else:
                    response = requests.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {response_data}")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test the root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_status_create(self):
        """Test creating a status check"""
        test_data = {"client_name": f"test_client_{datetime.now().strftime('%H%M%S')}"}
        return self.run_test("Create Status Check", "POST", "status", 200, data=test_data)

    def test_status_get(self):
        """Test getting status checks"""
        return self.run_test("Get Status Checks", "GET", "status", 200)

    def test_upload_valid_model(self):
        """Test uploading a valid 3D model"""
        test_file_path = "/app/test_cube.obj"
        
        if not os.path.exists(test_file_path):
            print(f"❌ Test file not found: {test_file_path}")
            return False, {}
        
        with open(test_file_path, 'rb') as f:
            files = {'file': ('test_cube.obj', f, 'application/octet-stream')}
            success, response = self.run_test(
                "Upload Valid OBJ Model", 
                "POST", 
                "upload-model", 
                200, 
                files=files
            )
            
            if success and 'id' in response:
                self.uploaded_model_id = response['id']
                print(f"   Model ID: {self.uploaded_model_id}")
            
            return success, response

    def test_upload_invalid_file_type(self):
        """Test uploading an invalid file type"""
        # Create a temporary text file to test invalid upload
        test_content = b"This is not a 3D model file"
        files = {'file': ('test.txt', test_content, 'text/plain')}
        
        return self.run_test(
            "Upload Invalid File Type", 
            "POST", 
            "upload-model", 
            400, 
            files=files
        )

    def test_upload_large_file(self):
        """Test uploading a file that exceeds size limit"""
        # Create a large dummy file (simulate 51MB)
        large_content = b"x" * (51 * 1024 * 1024)  # 51MB
        files = {'file': ('large_model.obj', large_content, 'application/octet-stream')}
        
        return self.run_test(
            "Upload Large File (>50MB)", 
            "POST", 
            "upload-model", 
            400, 
            files=files
        )

    def test_get_models(self):
        """Test getting all uploaded models"""
        return self.run_test("Get All Models", "GET", "models", 200)

    def test_get_specific_model(self):
        """Test getting a specific model by ID"""
        if not self.uploaded_model_id:
            print("⚠️  Skipping - No uploaded model ID available")
            return True, {}
        
        return self.run_test(
            "Get Specific Model", 
            "GET", 
            f"model/{self.uploaded_model_id}", 
            200
        )

    def test_get_nonexistent_model(self):
        """Test getting a model that doesn't exist"""
        fake_id = "nonexistent-model-id"
        return self.run_test(
            "Get Nonexistent Model", 
            "GET", 
            f"model/{fake_id}", 
            404
        )

    def test_static_file_serving(self):
        """Test if uploaded files can be served statically"""
        if not self.uploaded_model_id:
            print("⚠️  Skipping - No uploaded model ID available")
            return True, {}
        
        # Try to access the uploaded file via static file serving
        file_url = f"{self.base_url}/uploads/{self.uploaded_model_id}_test_cube.obj"
        
        try:
            response = requests.get(file_url)
            success = response.status_code == 200
            
            if success:
                self.tests_passed += 1
                print(f"✅ Static File Serving - Status: {response.status_code}")
                print(f"   File URL: {file_url}")
                print(f"   Content Length: {len(response.content)} bytes")
            else:
                print(f"❌ Static File Serving Failed - Status: {response.status_code}")
            
            self.tests_run += 1
            return success, {}
            
        except Exception as e:
            print(f"❌ Static File Serving Failed - Error: {str(e)}")
            self.tests_run += 1
            return False, {}

    def test_delete_model(self):
        """Test deleting a model (cleanup)"""
        if not self.uploaded_model_id:
            print("⚠️  Skipping - No uploaded model ID available")
            return True, {}
        
        return self.run_test(
            "Delete Model", 
            "DELETE", 
            f"model/{self.uploaded_model_id}", 
            200
        )

    def run_video_test(self, name, method, endpoint, expected_status, data=None):
        """Run a video API test using localhost"""
        url = f"{self.local_api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'} if data else {}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {response_data}")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}
        """Test video generation with existing model ID"""
        model_id = "85d4deab-cf8c-4e6c-aa72-f0f0d86acfa6"  # Test cube model
        hologram_settings = {
            "glowIntensity": 0.8,
            "scanSpeed": 1.0,
            "flickerRate": 2.0
        }
        
        test_data = {
            "model_id": model_id,
            "settings": hologram_settings
        }
        
    # Video Processing Tests
    def test_generate_video_with_existing_model(self):
        """Test video generation with existing model ID"""
        model_id = "85d4deab-cf8c-4e6c-aa72-f0f0d86acfa6"  # Test cube model
        hologram_settings = {
            "glowIntensity": 0.8,
            "scanSpeed": 1.0,
            "flickerRate": 2.0
        }
        
        test_data = {
            "model_id": model_id,
            "settings": hologram_settings
        }
        
        success, response = self.run_video_test(
            "Generate Video with Existing Model",
            "POST",
            "generate-video",
            200,
            data=test_data
        )
        
        if success and 'id' in response:
            self.video_job_id = response['id']
            print(f"   Video Job ID: {self.video_job_id}")
            print(f"   Initial Status: {response.get('status', 'unknown')}")
            print(f"   Initial Progress: {response.get('progress', 0)}%")
        
        return success, response

    def test_generate_video_invalid_model(self):
        """Test video generation with invalid model ID"""
        test_data = {
            "model_id": "invalid-model-id-12345",
            "settings": {"glowIntensity": 0.5}
        }
        
        return self.run_video_test(
            "Generate Video with Invalid Model",
            "POST",
            "generate-video",
            404,
            data=test_data
        )

    def test_video_job_status_tracking(self):
        """Test video job status tracking and progress updates"""
        if not hasattr(self, 'video_job_id') or not self.video_job_id:
            print("⚠️  Skipping - No video job ID available")
            return True, {}
        
        print(f"\n🔍 Tracking video job status for {self.video_job_id}...")
        
        max_attempts = 30  # Maximum 30 attempts (about 5 minutes)
        attempt = 0
        last_progress = -1
        
        while attempt < max_attempts:
            attempt += 1
            
            success, response = self.run_video_test(
                f"Get Video Job Status (Attempt {attempt})",
                "GET",
                f"video-job/{self.video_job_id}",
                200
            )
            
            if not success:
                return False, {}
            
            status = response.get('status', 'unknown')
            progress = response.get('progress', 0)
            
            print(f"   Status: {status}, Progress: {progress}%")
            
            # Check for progress updates
            if progress > last_progress:
                print(f"   ✅ Progress updated: {last_progress}% → {progress}%")
                last_progress = progress
            
            # Check completion
            if status == 'completed':
                print(f"   🎉 Video generation completed!")
                self.video_path = response.get('video_path')
                print(f"   Video Path: {self.video_path}")
                return True, response
            elif status == 'failed':
                print(f"   ❌ Video generation failed!")
                error_msg = response.get('error_message', 'Unknown error')
                print(f"   Error: {error_msg}")
                return False, response
            
            # Wait before next check
            time.sleep(10)  # Wait 10 seconds between checks
        
        print(f"   ⚠️  Timeout after {max_attempts} attempts")
        return False, {"error": "Timeout waiting for video completion"}

    def test_get_video_jobs_list(self):
        """Test getting all video jobs"""
        success, response = self.run_video_test(
            "Get All Video Jobs",
            "GET",
            "video-jobs",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   Found {len(response)} video jobs")
            for i, job in enumerate(response[:3]):  # Show first 3 jobs
                print(f"   Job {i+1}: {job.get('id', 'unknown')} - {job.get('status', 'unknown')}")
        
        return success, response

    def test_get_specific_video_job(self):
        """Test getting a specific video job"""
        if not hasattr(self, 'video_job_id') or not self.video_job_id:
            print("⚠️  Skipping - No video job ID available")
            return True, {}
        
        return self.run_video_test(
            "Get Specific Video Job",
            "GET",
            f"video-job/{self.video_job_id}",
            200
        )

    def test_get_nonexistent_video_job(self):
        """Test getting a video job that doesn't exist"""
        fake_job_id = "nonexistent-job-id-12345"
        return self.run_video_test(
            "Get Nonexistent Video Job",
            "GET",
            f"video-job/{fake_job_id}",
            404
        )

    def test_download_video(self):
        """Test downloading generated video"""
        if not hasattr(self, 'video_job_id') or not self.video_job_id:
            print("⚠️  Skipping - No video job ID available")
            return True, {}
        
        # First check if job is completed
        success, job_response = self.run_video_test(
            "Check Job Status Before Download",
            "GET",
            f"video-job/{self.video_job_id}",
            200
        )
        
        if not success:
            return False, {}
        
        if job_response.get('status') != 'completed':
            print(f"⚠️  Skipping download - Job status: {job_response.get('status')}")
            return True, {}
        
        # Test download
        url = f"{self.local_api_url}/download-video/{self.video_job_id}"
        print(f"\n🔍 Testing Download Generated Video...")
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url)
            success = response.status_code == 200
            
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                print(f"   Content-Type: {response.headers.get('content-type', 'unknown')}")
                print(f"   Content-Length: {len(response.content)} bytes")
                
                # Check if it's actually a video file
                if response.headers.get('content-type') == 'video/mp4':
                    print(f"   ✅ Correct MIME type: video/mp4")
                else:
                    print(f"   ⚠️  Unexpected MIME type: {response.headers.get('content-type')}")
                
                # Verify file size is reasonable (should be > 1KB for a real video)
                if len(response.content) > 1024:
                    print(f"   ✅ File size looks reasonable: {len(response.content)} bytes")
                else:
                    print(f"   ⚠️  File size seems small: {len(response.content)} bytes")
                
            else:
                print(f"❌ Failed - Status: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
            
            self.tests_run += 1
            return success, {}
            
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.tests_run += 1
            return False, {}

    def test_download_video_not_ready(self):
        """Test downloading video when job is not completed"""
        # Use a different model to create a job we won't wait for
        model_id = "85d4deab-cf8c-4e6c-aa72-f0f0d86acfa6"
        test_data = {
            "model_id": model_id,
            "settings": {"glowIntensity": 0.3}
        }
        
        # Create a new job
        success, response = self.run_video_test(
            "Create Job for Download Test",
            "POST",
            "generate-video",
            200,
            data=test_data
        )
        
        if not success or 'id' not in response:
            print("⚠️  Could not create test job")
            return True, {}
        
        temp_job_id = response['id']
        
        # Immediately try to download (should fail)
        return self.run_test(
            "Download Video Not Ready",
            "GET",
            f"download-video/{temp_job_id}",
            400
        )

    def test_file_system_verification(self):
        """Test file system verification for video generation"""
        print(f"\n🔍 Testing File System Verification...")
        
        # Check if videos directory exists
        videos_dir = Path("/app/backend/videos")
        
        if videos_dir.exists():
            print(f"✅ Videos directory exists: {videos_dir}")
            
            # List video files
            video_files = list(videos_dir.glob("*.mp4"))
            print(f"   Found {len(video_files)} MP4 files")
            
            for video_file in video_files[:3]:  # Show first 3 files
                file_size = video_file.stat().st_size
                print(f"   - {video_file.name}: {file_size} bytes")
            
            self.tests_passed += 1
        else:
            print(f"❌ Videos directory not found: {videos_dir}")
        
        self.tests_run += 1
        
        # Check if our specific video file exists (if we have a job ID)
        if hasattr(self, 'video_job_id') and self.video_job_id:
            expected_video = videos_dir / f"hologram_{self.video_job_id}.mp4"
            if expected_video.exists():
                file_size = expected_video.stat().st_size
                print(f"✅ Our generated video exists: {expected_video.name} ({file_size} bytes)")
            else:
                print(f"⚠️  Our generated video not found: {expected_video.name}")
        
        return True, {}

    def test_ffmpeg_integration(self):
        """Test FFmpeg integration availability"""
        print(f"\n🔍 Testing FFmpeg Integration...")
        
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"✅ FFmpeg is available")
                # Extract version info
                version_line = result.stdout.split('\n')[0]
                print(f"   {version_line}")
                self.tests_passed += 1
            else:
                print(f"❌ FFmpeg command failed")
                
        except FileNotFoundError:
            print(f"❌ FFmpeg not found in system PATH")
        except Exception as e:
            print(f"❌ FFmpeg test error: {str(e)}")
        
        self.tests_run += 1
        return True, {}

def main():
    print("🚀 Starting HoloForge API Tests...")
    print("=" * 50)
    
    tester = HoloForgeAPITester()
    
    # Run all tests in sequence
    test_methods = [
        # Basic API tests
        tester.test_root_endpoint,
        tester.test_status_create,
        tester.test_status_get,
        
        # Model upload tests
        tester.test_upload_valid_model,
        tester.test_upload_invalid_file_type,
        tester.test_upload_large_file,
        tester.test_get_models,
        tester.test_get_specific_model,
        tester.test_get_nonexistent_model,
        tester.test_static_file_serving,
        
        # Video processing tests (CRITICAL - NEW FUNCTIONALITY)
        tester.test_generate_video_with_existing_model,
        tester.test_generate_video_invalid_model,
        tester.test_video_job_status_tracking,
        tester.test_get_video_jobs_list,
        tester.test_get_specific_video_job,
        tester.test_get_nonexistent_video_job,
        tester.test_download_video,
        tester.test_download_video_not_ready,
        
        # System verification tests
        tester.test_file_system_verification,
        tester.test_ffmpeg_integration,
        
        # Cleanup
        tester.test_delete_model
    ]
    
    for test_method in test_methods:
        try:
            test_method()
        except Exception as e:
            print(f"❌ Test failed with exception: {str(e)}")
            tester.tests_run += 1
    
    # Print final results
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} tests passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  {tester.tests_run - tester.tests_passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())