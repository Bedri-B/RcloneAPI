from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func 
from typing import List
import psutil
from datetime import datetime, timedelta
import models
import schemas
import auth
from database import get_db

router = APIRouter()

@router.get("/stats/", response_model=schemas.DashboardStats)
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Get overall dashboard statistics"""
    
    # Get upload statistics
    total_uploads = db.query(models.FileUpload).count()
    successful_uploads = db.query(models.FileUpload).filter(
        models.FileUpload.status == "success"
    ).count()
    
    # Calculate success rate
    success_rate = (successful_uploads / total_uploads * 100) if total_uploads > 0 else 0
    
    # Get total storage used
    total_storage = db.query(models.FileUpload).filter(
        models.FileUpload.status == "success"
    ).with_entities(func.sum(models.FileUpload.size)).scalar() or 0
    
    # Get recent uploads
    recent_uploads = db.query(models.FileUpload).order_by(
        models.FileUpload.created_at.desc()
    ).limit(10).all()
    
    # Get system metrics
    disk = psutil.disk_usage('/')
    
    system_metric = models.SystemMetric(
        storage_used=disk.used,
        storage_free=disk.free,
        cpu_usage=psutil.cpu_percent(),
        memory_usage=psutil.virtual_memory().percent
    )
    db.add(system_metric)
    db.commit()
    recent_uploads_ = []
    for item in recent_uploads:
        recent_uploads_.append(schemas.FileUpload.model_validate(item, from_attributes=True))
    return schemas.DashboardStats(
        total_uploads=total_uploads,
        total_storage_used=total_storage,
        success_rate=success_rate,
        recent_uploads=recent_uploads_,
        system_metrics=schemas.SystemMetric.model_validate(system_metric, from_attributes=True)

    )

@router.get("/uploads/", response_model=List[schemas.FileUpload])
async def get_uploads(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Get paginated list of uploads"""
    uploads = db.query(models.FileUpload).offset(skip).limit(limit).all()
    return uploads

@router.get("/metrics/", response_model=List[schemas.SystemMetric])
async def get_system_metrics(
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Get system metrics for the last n hours"""
    since = datetime.utcnow() - timedelta(hours=hours)
    metrics = db.query(models.SystemMetric).filter(
        models.SystemMetric.created_at >= since
    ).all()
    return metrics

@router.get("/errors/", response_model=List[schemas.FileUpload])
async def get_failed_uploads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Get list of failed uploads"""
    failed_uploads = db.query(models.FileUpload).filter(
        models.FileUpload.status == "failed"
    ).all()
    return failed_uploads

