from fastapi.testclient import TestClient
from main import app
import pytest
from pathlib import Path
import os

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_upload_file(tmp_path):
    # Create a test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    
    with open(test_file, "rb") as f:
        response = client.post(
            "/upload/",
            files={"file": ("test.txt", f, "text/plain")}
        )
    
    assert response.status_code == 200
    assert response.json()["filename"] == "test.txt"
    assert response.json()["status"] == "success"

def test_upload_multiple_files(tmp_path):
    # Create test files
    files = []
    for i in range(3):
        test_file = tmp_path / f"test{i}.txt"
        test_file.write_text(f"test content {i}")
        files.append(("files", open(test_file, "rb")))
    
    response = client.post("/upload-multiple/", files=files)
    
    # Clean up
    for _, f in files:
        f.close()
    
    assert response.status_code == 200
    assert len(response.json()["filenames"]) == 3
    assert response.json()["status"] == "success"

def test_upload_no_file():
    response = client.post("/upload/")
    assert response.status_code == 422  # Validation error

def test_upload_empty_file_list():
    response = client.post("/upload-multiple/")
    assert response.status_code == 422  # Validation error

