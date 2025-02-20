from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class UserBase(BaseModel):
    username: str
    email: str
    is_admin: bool = False

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class FileUploadBase(BaseModel):
    filename: str
    size: float
    mime_type: str
    upload_path: str
    status: str
    error_message: Optional[str] = None

class FileUpload(FileUploadBase):
    id: int
    uploaded_by: int
    created_at: datetime

    class Config:
        orm_mode = True

class SystemMetricBase(BaseModel):
    storage_used: float
    storage_free: float
    cpu_usage: float
    memory_usage: float

class SystemMetric(SystemMetricBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class DashboardStats(BaseModel):
    total_uploads: int
    total_storage_used: float
    success_rate: float
    recent_uploads: List[FileUpload]
    system_metrics: SystemMetric

