import os

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.core.config import settings
from app.services import csv_loader

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class ResolveRequest(BaseModel):
    underwriting: str
    reduced_op: str
    gp_referal: str
    optden: str
    psych: str
    excess: str
    sixweek: str
    reduced_bens: str
    hospital_list: str
    non_mainland: str


class ResolveResponse(BaseModel):
    plancode: str
    inputs: dict


# ── Resolver ──────────────────────────────────────────────────────────────────

@router.post("/api/resolve", response_model=ResolveResponse, tags=["Resolver"])
def resolve_plancode(req: ResolveRequest):
    """Resolve a set of benefit configuration values to a plancode."""
    inputs = req.model_dump()

    # Validate inputs against allowed field values (skip fields not in values sheet)
    field_values = csv_loader.get_field_values()
    if field_values:
        errors = []
        for field, value in inputs.items():
            if value == "":  # unselected / null — always valid, matches empty cells in lookup
                continue
            allowed = field_values.get(field)
            if allowed is not None and value not in allowed:
                errors.append({
                    "field": field,
                    "input": value,
                    "allowed": allowed,
                })
        if errors:
            raise HTTPException(status_code=422, detail=errors)

    plancode = csv_loader.resolve(inputs)
    if not plancode:
        raise HTTPException(
            status_code=404,
            detail="No matching plancode found for the given inputs.",
        )
    return {"plancode": plancode, "inputs": inputs}


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get("/api/field-values", tags=["Resolver"])
def get_field_values():
    """Return valid options per field for use in dropdowns."""
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
        os.replace(tmp_path, data_path)  # atomic on same filesystem
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
