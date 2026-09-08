from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "CityScope API"


class RootResponse(BaseModel):
    name: str = "CityScope"
    status: str = "running"


class DatabaseHealthResponse(BaseModel):
    status: str
    database: str
    postgis: bool
    detail: str | None = None
