from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from pydantic import BaseModel
import tomllib
import re
import json
from datetime import datetime

app = FastAPI()

CONFIG_FILE = Path("config.json")
DOCS_FILE = Path("documents.json")
WORK_DIR = Path("./work")
WORK_DIR.mkdir(exist_ok=True)

# ===== Configuration =====

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"repo_path": None}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_documents():
    if DOCS_FILE.exists():
        with open(DOCS_FILE) as f:
            return json.load(f)
    return {"documents": []}

def get_repo_path():
    config = load_config()
    repo_path = config.get("repo_path")
    if not repo_path:
        return None
    return Path(repo_path)

# ===== Data Models =====

@dataclass
class Page:
    metadata: dict
    content: str
    line_start: int

class DocumentMetadata(BaseModel):
    pages: List[dict]
    total_lines: int

class ConfigUpdate(BaseModel):
    repo_path: str

# ===== Parsing Functions =====

def parse_transcript(text: str) -> list[Page]:
    """Parse TOML-delimited transcript into pages."""
    pages = []
    chunks = re.split(r'<<<>>>\s*', text)
    
    for chunk in chunks:
        if not chunk.strip():
            continue
            
        if chunk.startswith('+++'):
            try:
                toml_end = chunk.index('+++', 3) + 3
                toml_str = chunk[3:toml_end-3]
                metadata = tomllib.loads(toml_str)
                content = chunk[toml_end:].lstrip('\n')
            except (ValueError, tomllib.TOMLDecodeError):
                metadata = {}
                content = chunk
        else:
            metadata = {}
            content = chunk
        
        pages.append(Page(
            metadata=metadata,
            content=content,
            line_start=sum(p.content.count('|') for p in pages)
        ))
    
    return pages

def parseDocument(text: str) -> dict:
    """Split header from content."""
    headerMatch = re.match(r'^===HEADER===([\s\S]*?)===END HEADER===', text)
    if headerMatch:
        return {
            "header": headerMatch.group(1).strip(),
            "content": text[headerMatch.end():].strip()
        }
    return {"header": "", "content": text}

# ===== Routes =====

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("transcribe.html")

@app.get("/api/config")
async def get_config():
    return load_config()

@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    current = load_config()
    current["repo_path"] = config.repo_path
    save_config(current)
    return {"status": "ok", "repo_path": config.repo_path}

@app.get("/api/documents")
async def list_documents():
    """Return list of all documents with status."""
    docs = load_documents()
    repo = get_repo_path()
    
    # Add status for each document
    for doc in docs["documents"]:
        if repo:
            source_path = repo / doc["source"] if doc.get("source") else None
            transcript_path = repo / doc["transcript"] if doc.get("transcript") else None
            
            doc["source_exists"] = source_path.exists() if source_path else False
            doc["transcript_exists"] = transcript_path.exists() if transcript_path else False
        else:
            doc["source_exists"] = False
            doc["transcript_exists"] = False
    
    return docs

@app.get("/api/images/{doc_id}")
async def get_images(doc_id: str):
    """Get list of image files for a document."""
    docs = load_documents()
    doc = next((d for d in docs["documents"] if d["id"] == doc_id), None)
    
    if not doc:
        return {"images": [], "error": "Document not found"}
    
    repo = get_repo_path()
    if not repo:
        return {"images": [], "error": "Repository not configured"}
    
    source = doc.get("source")
    if not source:
        return {"images": []}
    
    source_path = repo / source
    
    # Handle PDF
    if source_path.suffix == '.pdf':
        if source_path.exists():
            return {
                "type": "pdf",
                "path": f"/repo/{source}"
            }
        return {"images": [], "error": "PDF not found"}
    
    # Handle image directory
    if source_path.is_dir():
        images = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff"]:
            images.extend(sorted(source_path.glob(ext)))
        
        return {
            "type": "images",
            "images": [f"/repo/{source}/{img.name}" for img in images]
        }
    
    return {"images": [], "error": "Source not found or invalid type"}

@app.get("/metadata/{doc_id}")
async def get_metadata(doc_id: str) -> DocumentMetadata:
    """Get transcript metadata."""
    docs = load_documents()
    doc = next((d for d in docs["documents"] if d["id"] == doc_id), None)
    
    if not doc or not doc.get("transcript"):
        return DocumentMetadata(pages=[], total_lines=0)
    
    repo = get_repo_path()
    if not repo:
        return DocumentMetadata(pages=[], total_lines=0)
        
    transcript_path = repo / doc["transcript"]
    
    if not transcript_path.exists():
        return DocumentMetadata(pages=[], total_lines=0)
    
    content = transcript_path.read_text()
    pages = parse_transcript(content)
    
    return DocumentMetadata(
        pages=[p.metadata for p in pages],
        total_lines=sum(p.content.count('|') for p in pages)
    )

@app.websocket("/ws/{doc_id}")
async def websocket_endpoint(websocket: WebSocket, doc_id: str):
    await websocket.accept()
    
    docs = load_documents()
    doc = next((d for d in docs["documents"] if d["id"] == doc_id), None)
    repo = get_repo_path()
    
    if doc and doc.get("transcript") and repo:
        filepath = repo / doc["transcript"]
    else:
        filepath = WORK_DIR / f"{doc_id}.txt"
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        while True:
            data = await websocket.receive_json()
            if data["action"] == "save":
                filepath.write_text(data["content"])
                await websocket.send_json({
                    "status": "saved",
                    "timestamp": datetime.now().isoformat(),
                    "path": str(filepath)
                })
            elif data["action"] == "load":
                content = filepath.read_text() if filepath.exists() else ""
                await websocket.send_json({
                    "status": "loaded",
                    "content": content
                })
    except Exception as e:
        print(f"Error: {e}")

# Mount repo as static files on startup
@app.on_event("startup")
async def startup():
    repo = get_repo_path()
    if repo and repo.exists():
        # Unmount if already exists
        try:
            app.mount("/repo", StaticFiles(directory=str(repo), follow_symlink=True), name="repo")
            print(f"Mounted repo: {repo}")
        except Exception as e:
            print(f"Could not mount repo: {e}")

@app.get("/select", response_class=HTMLResponse)
async def selector():
    return FileResponse("selector.html")

app.mount("/static", StaticFiles(directory="static", follow_symlink=True), name="static")
