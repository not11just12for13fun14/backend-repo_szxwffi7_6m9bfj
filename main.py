import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Compliance Gap Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeResponse(BaseModel):
    id: Optional[str]
    filename: str
    size: int
    mime_type: str
    uploaded_at: str
    summary: str
    coverage_score: float
    keyword_coverage: Dict[str, float]
    gaps: List[str]
    recommendations: List[str]


def analyze_text(text: str) -> Dict[str, Any]:
    """
    Very lightweight, demo-friendly gap analysis.
    We check for presence and coverage of common compliance concepts and produce a playful summary.
    """
    # Define simple compliance keyword clusters
    clusters = {
        "privacy": ["privacy", "personal data", "pii", "consent", "gdpr", "ccpa"],
        "security": ["encryption", "access control", "key management", "vulnerability", "patch", "incident"],
        "governance": ["risk", "policy", "procedure", "audit", "control", "evidence"],
        "retention": ["retention", "archiv", "delete", "erase", "data minimization"],
        "training": ["training", "awareness", "onboarding", "annual", "phishing"],
        "vendor": ["third party", "vendor", "processor", "subprocessor", "assessment"]
    }

    lower = text.lower() if text else ""

    keyword_coverage: Dict[str, float] = {}
    present_labels: List[str] = []
    gaps: List[str] = []

    for label, kws in clusters.items():
        hits = sum(1 for k in kws if k in lower)
        score = hits / max(len(kws), 1)
        keyword_coverage[label] = round(score, 2)
        if score > 0:
            present_labels.append(label)
        else:
            gaps.append(f"Missing any mention of {label} controls")

    coverage_score = round(sum(keyword_coverage.values()) / max(len(keyword_coverage), 1), 2)

    # Build playful summary
    if coverage_score >= 0.75:
        vibe = "rock-solid — almost party-ready for auditors!"
    elif coverage_score >= 0.5:
        vibe = "decent — with a few rhythm breaks to smooth out."
    else:
        vibe = "a work-in-progress — let's add some shiny controls."

    summary = (
        f"Your compliance groove is {vibe} "
        f"Highlights: {', '.join(present_labels) if present_labels else 'none yet'}"
    )

    # Recommendations
    recommendations: List[str] = []
    if keyword_coverage.get("privacy", 0) < 0.5:
        recommendations.append("Add a clear privacy section covering consent, PII handling and data rights.")
    if keyword_coverage.get("security", 0) < 0.5:
        recommendations.append("Document technical controls like encryption at rest/in transit and access policies.")
    if keyword_coverage.get("governance", 0) < 0.5:
        recommendations.append("Describe your risk assessment, audit cadence and evidence collection.")
    if keyword_coverage.get("retention", 0) < 0.5:
        recommendations.append("Define data retention schedules and deletion processes.")
    if keyword_coverage.get("training", 0) < 0.5:
        recommendations.append("Include security awareness and annual training details.")
    if keyword_coverage.get("vendor", 0) < 0.5:
        recommendations.append("Explain third-party risk management and vendor assessments.")

    return {
        "coverage_score": coverage_score,
        "keyword_coverage": keyword_coverage,
        "gaps": gaps,
        "summary": summary,
    }


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def upload_and_analyze(
    file: UploadFile = File(...),
    doc_title: str = Form("")
):
    try:
        content_bytes = await file.read()
        text = content_bytes.decode(errors="ignore")
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read uploaded file")

    analysis = analyze_text(text)

    # Try to store metadata + results in DB
    inserted_id = None
    try:
        from database import create_document
        payload = {
            "title": doc_title or file.filename,
            "filename": file.filename,
            "size": len(content_bytes),
            "mime_type": file.content_type or "text/plain",
            "analysis": analysis,
            "uploaded_at": datetime.utcnow(),
        }
        inserted_id = create_document("analysis", payload)
    except Exception:
        # DB not configured or failed; continue without persistence
        inserted_id = None

    return AnalyzeResponse(
        id=inserted_id,
        filename=file.filename,
        size=len(content_bytes),
        mime_type=file.content_type or "text/plain",
        uploaded_at=datetime.utcnow().isoformat() + "Z",
        summary=analysis["summary"],
        coverage_score=analysis["coverage_score"],
        keyword_coverage=analysis["keyword_coverage"],
        gaps=analysis["gaps"],
        recommendations=[
            *analysis.get("gaps", []),
            *([
                "Celebrate the wins: compliance keeps users safe and builds trust.",
                "We smooth the annoying bits with templates, checklists and automation.",
            ])
        ],
    )


@app.get("/api/analyses")
def list_analyses(limit: int = 10):
    try:
        from database import get_documents
        docs = get_documents("analysis", {}, limit)
        # Normalize for JSON
        result = []
        for d in docs:
            result.append({
                "id": str(d.get("_id")),
                "title": d.get("title"),
                "filename": d.get("filename"),
                "size": d.get("size"),
                "uploaded_at": d.get("uploaded_at").isoformat() + "Z" if d.get("uploaded_at") else None,
                "coverage_score": d.get("analysis", {}).get("coverage_score"),
            })
        return {"items": result}
    except Exception:
        # DB not configured
        return {"items": []}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
