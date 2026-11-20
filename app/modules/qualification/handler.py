from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.dependencies import Archive

router = APIRouter(prefix="/api/runs/{run_id}/admission")


class AdmissionRequest(BaseModel):
    wafer: str
    source: str
    note: str | None = Field(default=None, max_length=200)


def _service(request: Request):
    return request.app.state.admission


@router.get("")
def admission_overview(archive: Archive, request: Request):
    return {"reviews": _service(request).listing(request.path_params["run_id"], archive[1])}


@router.get("/review")
def admission_review(run_id: str, archive: Archive, request: Request, wafer: str, source: str):
    return _service(request).review(run_id, archive[1], wafer, source)


@router.post("/decisions", status_code=201)
def admission_decision(run_id: str, payload: AdmissionRequest, archive: Archive, request: Request):
    result = _service(request).record(run_id, archive[1], payload.wafer, payload.source, payload.note)
    return result
