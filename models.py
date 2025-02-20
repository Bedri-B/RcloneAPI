from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class FileUpload(Base):
    __tablename__ = "file_uploads"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    size = Column(Float)  # in bytes
    mime_type = Column(String)
    upload_path = Column(String)
    status = Column(String)  # success, failed, pending
    error_message = Column(String, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="uploads")

class SystemMetric(Base):
    __tablename__ = "system_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    storage_used = Column(Float)  # in bytes
    storage_free = Column(Float)  # in bytes
    cpu_usage = Column(Float)  # percentage
    memory_usage = Column(Float)  # percentage
    created_at = Column(DateTime, default=datetime.utcnow)

User.uploads = relationship("FileUpload", back_populates="user")

