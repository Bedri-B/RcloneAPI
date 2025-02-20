from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import os
import shutil
from typing import List
import asyncio
from pathlib import Path
import uvicorn
from datetime import timedelta
import models
import schemas 
import auth
import dashboard
from database import engine, get_db
import files
from auth import get_current_user
from starlette.middleware.base import BaseHTTPMiddleware

from starlette.middleware.trustedhost import TrustedHostMiddleware

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="File Upload Dashboard", root_path="/file-manager") # Updated title


class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net;"
        )
        return response

app.add_middleware(CSPMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# Include dashboard routes
app.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["dashboard"]
)


# Include routers
app.include_router(
    files.router,
    prefix="/dashboard",
    tags=["files"],
    dependencies=[Depends(get_current_user)]
)
# Configuration
RCLONE_REMOTE = "GCS:media_mover_test"
LOCAL_UPLOAD_PATH = "uploads"

# Ensure upload directory exists
Path(LOCAL_UPLOAD_PATH).mkdir(parents=True, exist_ok=True)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a single file and transfer it to Google Cloud Storage using rclone
    """
    try:
        # Create a unique filename
        file_location = os.path.join(LOCAL_UPLOAD_PATH, file.filename)
        
        # Save uploaded file locally
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)

        # Upload to GCS using rclone
        try:
            process = await asyncio.create_subprocess_exec(
                "rclone",
                "copy",
                file_location,
                f"{RCLONE_REMOTE}",
                "--no-traverse",
                "--gcs-bucket-policy-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload to cloud storage: {stderr.decode()}"
                )

        finally:
            # Clean up local file
            if os.path.exists(file_location):
                os.remove(file_location)

        return JSONResponse(
            content={
                "filename": file.filename,
                "status": "success",
                "message": "File uploaded successfully"
            },
            status_code=200
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-multiple/")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    folder: str = Form("/"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload multiple files to a specific folder
    """
    try:
        # Sanitize and validate folder path
        clean_folder = Path(folder).resolve()
        if ".." in str(clean_folder):
            raise HTTPException(status_code=400, detail="Invalid folder path")

        uploaded_files = []
        
        # Create temporary upload directory
        temp_dir = Path(LOCAL_UPLOAD_PATH) / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Save files to temporary directory
            for file in files:
                file_location = temp_dir / file.filename
                with open(file_location, "wb+") as file_object:
                    shutil.copyfileobj(file.file, file_object)
                uploaded_files.append(file_location)

            # Create destination folder if it doesn't exist
            process = await asyncio.create_subprocess_exec(
                "rclone",
                "copy",
                str(temp_dir),
                f"{RCLONE_REMOTE}/{folder}",
                "--gcs-bucket-policy-only",  # <=== Fix: Prevents legacy ACL issues
                "--no-traverse",             # <=== Fix: Optimizes upload without unnecessary checks
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            # Upload files to the specified folder
            process = await asyncio.create_subprocess_exec(
                "rclone",
                "copy",
                str(temp_dir),
                f"{RCLONE_REMOTE}/{folder}",
                "--gcs-bucket-policy-only",  # <=== Fix: Prevents legacy ACL issues
                "--no-traverse", 
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload to cloud storage: {stderr.decode()}"
                )

            # Log uploads to database
            for file in files:
                db_upload = models.FileUpload(
                    filename=file.filename,
                    size=file.size,
                    mime_type=file.content_type,
                    upload_path=f"{folder}/{file.filename}".replace("//", "/"),
                    status="success",
                    uploaded_by=current_user.id
                )
                db.add(db_upload)
            
            db.commit()

        finally:
            # Clean up temporary files
            for file_path in uploaded_files:
                if file_path.exists():
                    file_path.unlink()
            
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

        return JSONResponse(
            content={
                "filenames": [file.filename for file in files],
                "folder": folder,
                "status": "success",
                "message": f"Files uploaded successfully to {folder}"
            },
            status_code=200
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Verify rclone configuration on startup"""
    try:
        process = await asyncio.create_subprocess_exec(
            "rclone", "lsd", RCLONE_REMOTE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"Warning: rclone configuration check failed: {stderr.decode()}")
    except Exception as e:
        print(f"Warning: Could not verify rclone configuration: {str(e)}")

    try:
        db = next(get_db())
        create_user_(db, {
        "username": "bedri-b",
        "email": "bahrubedri@gmail.com",
        "password": "12345678q",
        "is_admin": True
    })
    except Exception as e:
        print(f"Warning: Could not create system user: {str(e)}")

@app.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/token-check")
async def check(
    current_user: models.User = Depends(get_current_user),
):
    return JSONResponse(status_code=200, content={})

def create_user_(db, user):
    db_user = db.query(models.User).filter(
        models.User.username == user.get("username")
    ).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    hashed_password = auth.get_password_hash(user.get("password"))
    db_user = models.User(
        username=user.get("username"),
        email=user.get("email"),
        hashed_password=hashed_password,
        is_admin=user.get("is_admin")
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/users/", response_model=schemas.User)
async def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    return create_user_(db, {
        "username": user.get("username"),
        "email": user.get("email"),
        "password": user.get("password"),
        "is_admin": user.get("is_admin")
    })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3369)

