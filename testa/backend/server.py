from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import aiofiles
import shutil
import asyncio
import ffmpeg
import numpy as np
from PIL import Image, ImageDraw
import cv2
import tempfile
import trimesh
import json


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Create uploads directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Create videos directory for generated content
VIDEO_DIR = ROOT_DIR / "videos"
VIDEO_DIR.mkdir(exist_ok=True)

# Define Models

class VideoJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model_id: str
    status: str = "pending"  # pending, processing, completed, failed
    progress: int = 0  # 0-100
    video_path: Optional[str] = None
    error_message: Optional[str] = None
    settings: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

class VideoJobCreate(BaseModel):
    model_id: str
    settings: Optional[dict] = None

# Serve uploaded files through API route (must be after router inclusion)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/api/videos", StaticFiles(directory=str(VIDEO_DIR)), name="videos")
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class ModelUpload(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    file_path: str
    file_size: int
    upload_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    file_type: str
    processing_status: str = "uploaded"

class HologramSettings(BaseModel):
    glow_intensity: float = Field(default=0.8, ge=0.0, le=2.0)
    scan_speed: float = Field(default=1.0, ge=0.1, le=5.0)
    flicker_rate: float = Field(default=2.0, ge=0.5, le=10.0)

# Helper functions
def validate_3d_geometry(file_path: str, file_extension: str) -> dict:
    """Validate that uploaded file contains actual 3D geometry data"""
    validation_result = {
        "is_valid": False,
        "vertex_count": 0,
        "face_count": 0,
        "has_geometry": False,
        "error_message": None,
        "file_info": {}
    }
    
    try:
        logger.info(f"🔍 Starting 3D geometry validation for: {file_path}")
        
        # Try to load the 3D model using trimesh
        if file_extension.lower() == '.obj':
            logger.info("📄 Loading OBJ file...")
            mesh = trimesh.load_mesh(file_path)
        elif file_extension.lower() in ['.gltf', '.glb']:
            logger.info("📄 Loading GLTF/GLB file...")
            mesh = trimesh.load(file_path)
        elif file_extension.lower() == '.ply':
            logger.info("📄 Loading PLY file...")
            mesh = trimesh.load_mesh(file_path)
        else:
            # For other formats, try generic loading
            logger.info(f"📄 Loading {file_extension} file...")
            mesh = trimesh.load(file_path)
        
        logger.info(f"🔍 Mesh loaded successfully. Type: {type(mesh)}")
        
        # Handle different mesh types
        if isinstance(mesh, trimesh.Scene):
            logger.info("🎭 Loaded as Scene, extracting geometry...")
            # For scenes, get all geometries
            total_vertices = 0
            total_faces = 0
            geometries = []
            
            for name, geometry in mesh.geometry.items():
                if hasattr(geometry, 'vertices') and hasattr(geometry, 'faces'):
                    v_count = len(geometry.vertices)
                    f_count = len(geometry.faces)
                    total_vertices += v_count
                    total_faces += f_count
                    geometries.append({
                        "name": name,
                        "vertices": v_count,
                        "faces": f_count
                    })
                    logger.info(f"  └─ Geometry '{name}': {v_count} vertices, {f_count} faces")
            
            validation_result.update({
                "vertex_count": total_vertices,
                "face_count": total_faces,
                "has_geometry": total_vertices > 0 and total_faces > 0,
                "file_info": {
                    "type": "scene",
                    "geometries": geometries,
                    "geometry_count": len(geometries)
                }
            })
            
        elif isinstance(mesh, trimesh.Trimesh):
            logger.info("🔺 Loaded as single Trimesh...")
            vertex_count = len(mesh.vertices)
            face_count = len(mesh.faces)
            
            logger.info(f"  └─ Single mesh: {vertex_count} vertices, {face_count} faces")
            
            validation_result.update({
                "vertex_count": vertex_count,
                "face_count": face_count,
                "has_geometry": vertex_count > 0 and face_count > 0,
                "file_info": {
                    "type": "single_mesh",
                    "bounds": mesh.bounds.tolist() if hasattr(mesh, 'bounds') else None,
                    "is_watertight": bool(mesh.is_watertight) if hasattr(mesh, 'is_watertight') else False
                }
            })
        else:
            logger.warning(f"⚠️ Unexpected mesh type: {type(mesh)}")
            validation_result["error_message"] = f"Unsupported mesh type: {type(mesh)}"
            return validation_result
        
        # Final validation
        validation_result["is_valid"] = validation_result["has_geometry"]
        
        if validation_result["is_valid"]:
            logger.info(f"✅ 3D geometry validation PASSED: {validation_result['vertex_count']} vertices, {validation_result['face_count']} faces")
        else:
            logger.error(f"❌ 3D geometry validation FAILED: No geometry found")
            validation_result["error_message"] = "No 3D geometry found in file"
            
    except Exception as e:
        logger.error(f"❌ 3D geometry validation ERROR: {str(e)}")
        validation_result["error_message"] = f"Failed to parse 3D file: {str(e)}"
        validation_result["is_valid"] = False
    
    return validation_result

def prepare_for_mongo(data):
    """Convert datetime objects to ISO strings for MongoDB storage"""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
    return data

def parse_from_mongo(item):
    """Parse datetime strings from MongoDB back to datetime objects"""
    if isinstance(item, dict):
        for key, value in item.items():
            if key.endswith('timestamp') or key.endswith('_at') and isinstance(value, str):
                try:
                    item[key] = datetime.fromisoformat(value)
                except ValueError:
                    pass
    return item

# Video processing functions
async def generate_hologram_frames(model_path: str, settings: dict, num_frames: int = 120) -> List[str]:
    """Generate hologram effect frames for video creation"""
    logger.info(f"🎬 Generating {num_frames} hologram frames for {model_path}")
    
    # Create temporary directory for frames
    temp_dir = tempfile.mkdtemp(prefix="hologram_frames_")
    frame_paths = []
    
    try:
        # For MVP, we'll create simple hologram-style frames
        # In production, this would integrate with actual 3D rendering
        for frame_num in range(num_frames):
            # Create hologram-style frame
            frame_path = Path(temp_dir) / f"frame_{frame_num:04d}.png"
            
            # Create a simple hologram visualization
            create_hologram_frame(frame_path, frame_num, settings)
            frame_paths.append(str(frame_path))
            
        logger.info(f"✅ Generated {len(frame_paths)} frames")
        return frame_paths
        
    except Exception as e:
        logger.error(f"❌ Frame generation failed: {e}")
        # Clean up on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

def create_hologram_frame(output_path: Path, frame_num: int, settings: dict):
    """Create a single hologram effect frame"""
    width, height = 800, 600
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Get hologram settings
    glow_intensity = settings.get('glowIntensity', 0.8)
    scan_speed = settings.get('scanSpeed', 1.0)
    flicker_rate = settings.get('flickerRate', 2.0)
    
    # Calculate animation values
    time = frame_num / 30.0  # Assuming 30 FPS
    rotation = (frame_num * 3) % 360
    
    # Create hologram effect
    cx, cy = width // 2, height // 2
    
    # Draw rotating cube wireframe
    cube_size = 100
    
    # Simple cube wireframe simulation
    for i in range(8):
        angle = (rotation + i * 45) * np.pi / 180
        x = cx + cube_size * np.cos(angle)
        y = cy + cube_size * np.sin(angle)
        
        # Hologram colors (cyan/blue)
        intensity = int(255 * glow_intensity)
        color = (0, intensity, intensity, 200)
        
        # Draw glowing points
        draw.ellipse([x-5, y-5, x+5, y+5], fill=color)
    
    # Add scan lines effect
    scan_pos = int((time * scan_speed * 50) % height)
    for y in range(0, height, 4):
        if abs(y - scan_pos) < 20:
            alpha = int(100 * glow_intensity)
            draw.line([(0, y), (width, y)], fill=(0, 255, 255, alpha), width=1)
    
    # Add flicker effect
    if int(time * flicker_rate) % 2:
        # Reduce opacity for flicker
        alpha_channel = img.split()[-1]
        reduced_alpha = alpha_channel.point(lambda x: int(x * 0.7))
        img.putalpha(reduced_alpha)
    
    img.save(output_path, 'PNG')

async def create_video_from_frames(frame_paths: List[str], output_path: str, fps: int = 30):
    """Create MP4 video from frame sequence using FFmpeg"""
    logger.info(f"🎬 Creating video from {len(frame_paths)} frames at {fps} FPS")
    
    try:
        # Create temporary input pattern file for FFmpeg
        temp_dir = Path(frame_paths[0]).parent
        
        # Use ffmpeg-python to create video with transparent background support
        (
            ffmpeg
            .input(str(temp_dir / 'frame_%04d.png'), framerate=fps)
            .output(
                output_path,
                vcodec='libx264',
                pix_fmt='yuv420p',
                crf=18,  # High quality
                preset='fast'
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        
        logger.info(f"✅ Video created successfully: {output_path}")
        
        # Clean up frame files
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    except ffmpeg.Error as e:
        logger.error(f"❌ FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
        raise HTTPException(status_code=500, detail=f"Video creation failed: {str(e)}")

async def process_video_job(job_id: str):
    """Background task to process video generation"""
    logger.info(f"🎬 Starting video processing for job {job_id}")
    
    try:
        # Get job from database
        job = await db.video_jobs.find_one({"id": job_id})
        if not job:
            logger.error(f"❌ Job {job_id} not found")
            return
        
        # Update status to processing
        await db.video_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "processing", "progress": 10}}
        )
        
        # Get model info
        model = await db.model_uploads.find_one({"id": job["model_id"]})
        if not model:
            await db.video_jobs.update_one(
                {"id": job_id},
                {"$set": {"status": "failed", "error_message": "Model not found"}}
            )
            return
        
        model_path = ROOT_DIR / model["file_path"]
        
        # Update progress
        await db.video_jobs.update_one(
            {"id": job_id},
            {"$set": {"progress": 25}}
        )
        
        # Generate hologram frames
        settings = job.get("settings", {})
        frame_paths = await generate_hologram_frames(str(model_path), settings)
        
        # Update progress
        await db.video_jobs.update_one(
            {"id": job_id},
            {"$set": {"progress": 75}}
        )
        
        # Create video
        video_filename = f"hologram_{job_id}.mp4"
        video_path = VIDEO_DIR / video_filename
        
        await create_video_from_frames(frame_paths, str(video_path))
        
        # Update job as completed
        await db.video_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "completed",
                "progress": 100,
                "video_path": f"videos/{video_filename}",
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"✅ Video processing completed for job {job_id}")
        
    except Exception as e:
        logger.error(f"❌ Video processing failed for job {job_id}: {str(e)}")
        await db.video_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )

# Routes
@api_router.get("/")
async def root():
    return {"message": "HoloForge API - 3D to Hologram Converter"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    model_dict = prepare_for_mongo(status_obj.dict())
    _ = await db.status_checks.insert_one(model_dict)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**parse_from_mongo(status_check)) for status_check in status_checks]

@api_router.post("/upload-model", response_model=ModelUpload)
async def upload_3d_model(file: UploadFile = File(...)):
    # Validate file type
    allowed_extensions = {'.obj', '.fbx', '.gltf', '.glb', '.ply'}
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Check file size (50MB limit)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    content = await file.read()
    file_size = len(content)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024):.0f}MB"
        )
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename
    
    # Save file
    try:
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # CRITICAL: Validate 3D geometry content
    logger.info(f"🔍 Validating 3D geometry for uploaded file: {file.filename}")
    
    geometry_validation = validate_3d_geometry(str(file_path), file_extension)
    
    if not geometry_validation["is_valid"]:
        # Delete the invalid file
        file_path.unlink(missing_ok=True)
        error_msg = geometry_validation.get("error_message", "No 3D geometry found")
        logger.error(f"❌ 3D validation failed for {file.filename}: {error_msg}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid 3D file: {error_msg}"
        )
    
    logger.info(f"✅ 3D validation passed for {file.filename}: {geometry_validation['vertex_count']} vertices, {geometry_validation['face_count']} faces")
    
    # Create model record
    model_upload = ModelUpload(
        id=file_id,
        filename=file.filename,
        file_path=str(file_path.relative_to(ROOT_DIR)),
        file_size=file_size,
        file_type=file_extension,
        processing_status="validated"  # Changed from "uploaded" to show validation passed
    )
    
    # Save to database
    model_dict = prepare_for_mongo(model_upload.dict())
    await db.model_uploads.insert_one(model_dict)
    
    return model_upload

@api_router.get("/models", response_model=List[ModelUpload])
async def get_uploaded_models():
    models = await db.model_uploads.find().to_list(100)
    return [ModelUpload(**parse_from_mongo(model)) for model in models]

@api_router.get("/model/{model_id}", response_model=ModelUpload)
async def get_model(model_id: str):
    model = await db.model_uploads.find_one({"id": model_id})
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelUpload(**parse_from_mongo(model))

@api_router.delete("/model/{model_id}")
async def delete_model(model_id: str):
    model = await db.model_uploads.find_one({"id": model_id})
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Delete file
    file_path = ROOT_DIR / model["file_path"]
    if file_path.exists():
        file_path.unlink()
    
    # Delete from database
    await db.model_uploads.delete_one({"id": model_id})
    
    return {"message": "Model deleted successfully"}

# Video processing endpoints
@api_router.post("/generate-video", response_model=VideoJob)
async def generate_video(job_data: VideoJobCreate, background_tasks: BackgroundTasks):
    """Start video generation process"""
    logger.info(f"🎬 Video generation requested for model {job_data.model_id}")
    
    # Check if model exists
    model = await db.model_uploads.find_one({"id": job_data.model_id})
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Create video job
    video_job = VideoJob(
        model_id=job_data.model_id,
        settings=job_data.settings or {}
    )
    
    # Save job to database
    job_dict = prepare_for_mongo(video_job.dict())
    await db.video_jobs.insert_one(job_dict)
    
    # Start background processing
    background_tasks.add_task(process_video_job, video_job.id)
    
    logger.info(f"✅ Video job {video_job.id} created and queued")
    return video_job

@api_router.get("/video-job/{job_id}", response_model=VideoJob)
async def get_video_job(job_id: str):
    """Get video generation job status"""
    job = await db.video_jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")
    return VideoJob(**parse_from_mongo(job))

@api_router.get("/video-jobs", response_model=List[VideoJob])
async def get_video_jobs():
    """Get all video generation jobs"""
    jobs = await db.video_jobs.find().sort("created_at", -1).to_list(100)
    return [VideoJob(**parse_from_mongo(job)) for job in jobs]

@api_router.get("/download-video/{job_id}")
async def download_video(job_id: str):
    """Download generated video"""
    job = await db.video_jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")
    
    if job["status"] != "completed" or not job.get("video_path"):
        raise HTTPException(status_code=400, detail="Video not ready for download")
    
    video_path = ROOT_DIR / job["video_path"]
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"hologram_video_{job_id}.mp4"
    )

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()