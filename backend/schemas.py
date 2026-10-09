"""schemas.py — request bodies for endpoints that take more than one or
two simple fields (kept as real Pydantic models instead of loose query
params so a JSON body works cleanly, which matters once a Flutter client
is sending these instead of Swagger UI's form)."""

from pydantic import BaseModel


class VerifyBody(BaseModel):
    approve: bool
    verified_by: str = "Officer"


class BulkVerifyBody(BaseModel):
    report_ids: list[str]
    approve: bool
    verified_by: str = "Officer"


class AssignResponderBody(BaseModel):
    responder_name: str
    eta_minutes: int


class DeviceRegisterBody(BaseModel):
    fcm_token: str
    platform: str  # "android" | "ios"
    lat: float | None = None
    lon: float | None = None
