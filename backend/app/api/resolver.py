import os

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.core.config import settings
from app.services import csv_loader

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class ResolveResponse(BaseModel):
    plancode: str
    dalecode: str
    inputs: dict


# ── Resolver ──────────────────────────────────────────────────────────────────

@router.post("/api/resolve", tags=["Resolver"])
async def resolve_plancode(request: Request):
    """Resolve a set of benefit option values to a plancode + dalecode."""
    inputs: dict = await request.json()

    # Validate each submitted value against the allowed values for that field
    field_values = csv_loader.get_field_values()
    if field_values:
        errors = []
        for field, value in inputs.items():
            if value == "":
                continue
            options = field_values.get(field)
            if options is not None:
                allowed_vals = [opt["value"] for opt in options]
                if value not in allowed_vals:
                    errors.append({
                        "field": field,
                        "input": value,
                        "allowed": allowed_vals,
                    })
        if errors:
            raise HTTPException(status_code=422, detail=errors)

    plancode = csv_loader.resolve(inputs)
    if not plancode:
        raise HTTPException(
            status_code=404,
            detail="No matching plancode found for the given inputs.",
        )

    # Derive the dalecode from the resolved row
    from app.services.csv_loader import FIELDS
    dalecode = "".join(str(inputs.get(f, "")) for f in FIELDS)

    return {"plancode": plancode, "dalecode": dalecode, "inputs": inputs}


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get("/api/field-values", tags=["Resolver"])
def get_field_values():
    """Return valid options per field: {field: [{value, label}, ...]}"""
    return csv_loader.get_field_values()


@router.get("/api/mappings", tags=["Admin"])
def get_mappings():
    """Return all loaded plancode mappings."""
    return {
        **csv_loader.get_load_info(),
        "version_info": csv_loader.get_version_info(),
        "rows": csv_loader.get_all_rows(),
    }


@router.get("/api/status", tags=["Admin"])
def get_status():
    """Return load status, file metadata, and current version info."""
    return {
        **csv_loader.get_load_info(),
        "version_info": csv_loader.get_version_info(),
    }


@router.get("/api/version", tags=["Admin"])
def get_version():
    """Return current version information from the version sheet."""
    info = csv_loader.get_version_info()
    if not info:
        raise HTTPException(status_code=503, detail="Version information not available.")
    return info


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/api/admin/upload", tags=["Admin"])
async def upload_file(file: UploadFile = File(...)):
    """Upload a new plancode_mappings.xlsx and reload immediately."""
    if not (file.filename or "").endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    data_path = settings.DATA_FILE
    tmp_path = data_path + ".tmp"

    try:
        with open(tmp_path, "wb") as f:
            f.write(content)
        os.replace(tmp_path, data_path)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc

    try:
        csv_loader.load()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse xlsx: {exc}") from exc

    return {
        "message": "File uploaded and reloaded successfully.",
        **csv_loader.get_load_info(),
        "version_info": csv_loader.get_version_info(),
    }


# ── Admin UI ──────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin(request: Request):
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            **csv_loader.get_load_info(),
            "version_info": csv_loader.get_version_info(),
        },
    )
