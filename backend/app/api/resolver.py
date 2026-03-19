import os
from typing import Annotated

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services import csv_loader
from app.services.csv_loader import FIELDS

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── Request / Response models ─────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    """Benefit option values to resolve to a plancode.
    All field values should be the code values (e.g. '1a', 'NMORI') not labels."""

    underwriting:    str = Field(..., examples=["NMORI"])
    corecover:       str = Field(..., examples=["Y"])
    psych:           str = Field(..., examples=["1a"])
    gpreferred:      str = Field(..., examples=["2a"])
    hospital_list:   str = Field(..., examples=["3a"])
    opticaldental:   str = Field(..., examples=["4a"])
    sixweek:         str = Field(..., examples=["5a"])
    excess:          str = Field(..., examples=["6a"])
    benefitreduction:str = Field(..., examples=["7a"])
    oplimit:         str = Field(..., examples=["8a"])
    islands:         str = Field(..., examples=["9a"])


class ResolveResponse(BaseModel):
    plancode: str
    dalecode:  str
    inputs:   dict


class DalecodeLookupRequest(BaseModel):
    """A dalecode string to deconstruct back into field values and resolve to a plancode."""
    dalecode: str = Field(..., examples=["NMORIY1a2a3a4a5a6a7a8a9a"])


class DecodedField(BaseModel):
    field: str
    value: str
    label: str


class DalecodeLookupResponse(BaseModel):
    dalecode: str
    plancode: str
    fields:   list[DecodedField]


# ── Resolver ──────────────────────────────────────────────────────────────────

@router.post(
    "/api/resolve",
    response_model=ResolveResponse,
    tags=["Resolver"],
    summary="Resolve benefit options to a plancode",
)
def resolve_plancode(req: ResolveRequest):
    """
    Submit all 11 benefit option **code values** to receive the matching plancode
    and its derived dalecode.

    Values must exactly match the codes in the `/api/field-values` response
    (e.g. `"1a"`, `"NMORI"`) — not the human-readable labels.
    """
    # model_dump with by_alias=True gives us the "6week" key the lookup expects
    inputs = req.model_dump()

    # Validate each value against the allowed set for its field
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
                    errors.append({"field": field, "input": value, "allowed": allowed_vals})
        if errors:
            raise HTTPException(status_code=422, detail=errors)

    plancode = csv_loader.resolve(inputs)
    if not plancode:
        raise HTTPException(status_code=404, detail="No matching plancode found for the given inputs.")

    dalecode = "".join(str(inputs.get(f, "")) for f in FIELDS)
    return {"plancode": plancode, "dalecode": dalecode, "inputs": inputs}


# ── Dalecode lookup ───────────────────────────────────────────────────────────

@router.post(
    "/api/dalecode-lookup",
    response_model=DalecodeLookupResponse,
    tags=["Resolver"],
    summary="Decode a dalecode back to field values and plancode",
)
def dalecode_lookup(req: DalecodeLookupRequest):
    """
    Submit a **dalecode** string to deconstruct it into its constituent field
    values (with human-readable labels) and resolve it back to a plancode.

    The dalecode is the concatenation of all field code values with no separators,
    e.g. `NMORIY1a2a3a4a5a6a7a8a9a`.
    """
    dalecode = req.dalecode.strip()

    decoded = csv_loader.decode_dalecode(dalecode)
    if decoded is None:
        raise HTTPException(
            status_code=404,
            detail="Unable to decode — dalecode does not match any known field value sequence.",
        )

    inputs = {item["field"]: item["value"] for item in decoded}
    plancode = csv_loader.resolve(inputs)

    return {"dalecode": dalecode, "plancode": plancode or "", "fields": decoded}


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get(
    "/api/field-values",
    tags=["Resolver"],
    summary="Get valid options per field",
)
def get_field_values():
    """
    Returns all valid option values for each field, including human-readable labels.

    Response shape: `{field: [{value, label}, ...]}`

    Use `value` when submitting to `/api/resolve`; display `label` in UI dropdowns.
    """
    return csv_loader.get_field_values()


@router.get("/api/mappings", tags=["Admin"])
def get_mappings():
    """Return all loaded plancode mappings (plancode, dalecode, and all field values)."""
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
