from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path
from pydantic import BaseModel
import asyncio
import json

from fastapi.responses import FileResponse

from database import get_db
from auth import get_current_user
from models import User

router = APIRouter()

RCLONE_REMOTE = "GCS:media_mover_test"

class FileItem(BaseModel):
    id: str
    name: str
    type: str
    size: int
    modified: str
    path: str

@router.get("/files", response_model=List[FileItem])
async def list_files(
    path: str = Query("/", description="Path to list files from"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List files and folders at the specified path
    """
    try:
        # Sanitize and validate path
        clean_path = Path(path).resolve()
        if ".." in str(clean_path):
            raise HTTPException(status_code=400, detail="Invalid path")

        # List files using rclone
        process = await asyncio.create_subprocess_exec(
            "rclone",
            "lsjson",
            str(f"{RCLONE_REMOTE}/{path}").replace("//", "/"),
            "--gcs-bucket-policy-only",
            "--no-traverse", 
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list files: {stderr.decode()}"
            )

        # Parse the JSON output
        items = json.loads(stdout.decode())
        
        # Convert to FileItem objects
        file_items = []
        for item in items:
            file_items.append(FileItem(
                id=f"{path}/{item['Path']}".replace("//", "/"),
                name=item['Name'],
                type="folder" if item['IsDir'] else "file",
                size=item['Size'],
                modified=item['ModTime'],
                path=f"{path}/{item['Path']}".replace("//", "/")
            ))

        return file_items

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download")
async def download_file(
    path: str = Query(..., description="Path of file to download"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download a file from storage
    """
    try:
        # Sanitize and validate path
        clean_path = Path(path).resolve()
        if ".." in str(clean_path):
            raise HTTPException(status_code=400, detail="Invalid path")

        # Create a temporary directory for the download
        temp_dir = Path("temp_downloads")
        temp_dir.mkdir(exist_ok=True)
        
        local_path = temp_dir / Path(path).name

        try:
            # Download file using rclone
            process = await asyncio.create_subprocess_exec(
                "rclone",
                "copy",
                f"{RCLONE_REMOTE}/{path}",
                str(local_path.parent),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to download file: {stderr.decode()}"
                )

            # Return file as streaming response
            return FileResponse(
                path=local_path,
                filename=Path(path).name,
                media_type="application/octet-stream"
            )

        finally:
            # Clean up temporary files
            if local_path.exists():
                local_path.unlink()
            if not any(temp_dir.iterdir()):
                temp_dir.rmdir()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/files")
async def delete_file(
    path: str = Query(..., description="Path of file or folder to delete"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a file or folder from storage
    """
    try:
        # Sanitize and validate path
        clean_path = Path(path).resolve()
        if ".." in str(clean_path):
            raise HTTPException(status_code=400, detail="Invalid path")

        # Check if it's a file or folder
        process_check = await asyncio.create_subprocess_exec(
            "rclone",
            "lsf",  # List files and folders
            "--dirs-only",
            f"{RCLONE_REMOTE}/{path}".replace("//", "/"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process_check.communicate()

        # Determine deletion method
        if stdout.strip():  # If output exists, it's a folder
            command = "purge"
        else:  # If no output, assume it's a file
            command = "delete"

        # Execute the correct delete command
        process_delete = await asyncio.create_subprocess_exec(
            "rclone",
            command,
            f"{RCLONE_REMOTE}/{path}".replace("//", "/"),
            "--gcs-bucket-policy-only",
            "--no-traverse",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process_delete.communicate()

        if process_delete.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete {command}: {stderr.decode()}"
            )

        return {"message": f"{'Folder' if command == 'purge' else 'File'} deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mkdir")
async def create_directory(
    path: str = Query(..., description="Path of directory to create"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new directory
    """
    try:
        # Sanitize and validate path
        clean_path = Path(path).resolve()
        if ".." in str(clean_path):
            raise HTTPException(status_code=400, detail="Invalid path")

        # Create a temporary empty file
        temp_file = "/tmp/.keep"
        open(temp_file, "w").close()  # Create an empty file

        # Create directory using rclone
        process = await asyncio.create_subprocess_exec(
            "rclone",
            "copyto",
            temp_file,
            f"{RCLONE_REMOTE}/{path}/.keep".replace("//", "/"),
            "--gcs-bucket-policy-only",
            "--no-traverse",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create directory: {stderr.decode()}"
            )

        # process_delete = await asyncio.create_subprocess_exec(
        #     "rclone",
        #     "delete",
        #     f"{RCLONE_REMOTE}/{path}/.keep".replace("//", "/"),
        #     "--gcs-bucket-policy-only",
        #     "--no-traverse",
        #     stdout=asyncio.subprocess.PIPE,
        #     stderr=asyncio.subprocess.PIPE
        # )
        # _out, _err = await process_delete.communicate()

        return {"message": "Directory created successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/move")
async def move_file(
    source: str = Query(..., description="Source path"),
    destination: str = Query(..., description="Destination path"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Move/rename a file or directory
    """
    try:
        # Sanitize and validate paths
        clean_source = Path(source).resolve()
        clean_dest = Path(destination).resolve()
        if ".." in str(clean_source) or ".." in str(clean_dest):
            raise HTTPException(status_code=400, detail="Invalid path")

        # Move using rclone
        process = await asyncio.create_subprocess_exec(
            "rclone",
            "moveto",
            f"{RCLONE_REMOTE}/{source}",
            f"{RCLONE_REMOTE}/{destination}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to move file: {stderr.decode()}"
            )

        return {"message": "File moved successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))