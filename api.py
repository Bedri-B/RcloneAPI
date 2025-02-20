from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import subprocess
import os
import shutil
from typing import List

app = FastAPI()

RCLONE_REMOTE = "GCS:media_mover_test"
LOCAL_UPLOAD_PATH = "uploads"

# Ensure upload directory exists
if not os.path.exists(LOCAL_UPLOAD_PATH):
    os.makedirs(LOCAL_UPLOAD_PATH)

def run_rclone_command(command: List[str]):
    """Run an rclone command and return the output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return JSONResponse(content={"success": True, "output": result.stdout})
    except subprocess.CalledProcessError as e:
        return JSONResponse(content={"success": False, "error": e.stderr})

@app.get("/list")
def list_files():
    """List files in the GCS bucket."""
    return run_rclone_command(["rclone", "lsf", RCLONE_REMOTE])

@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    """Upload a file to the GCS bucket."""
    file_path = os.path.join(LOCAL_UPLOAD_PATH, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return run_rclone_command(["rclone", "copy", file_path, RCLONE_REMOTE])

@app.get("/download")
def download_file(file_name: str):
    """Download a file from the GCS bucket."""
    return run_rclone_command(["rclone", "copy", f"{RCLONE_REMOTE}/{file_name}", LOCAL_UPLOAD_PATH])

@app.delete("/delete")
def delete_file(file_name: str):
    """Delete a file from the GCS bucket."""
    return run_rclone_command(["rclone", "delete", f"{RCLONE_REMOTE}/{file_name}"])

@app.post("/sync")
def sync_files(local_folder: str = Form(...)):
    """Sync a local folder with the GCS bucket."""
    return run_rclone_command(["rclone", "sync", local_folder, RCLONE_REMOTE])

@app.get("/config")
def get_rclone_config():
    """Get the rclone configuration."""
    return run_rclone_command(["rclone", "config", "show"])
