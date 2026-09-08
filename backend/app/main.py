from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router
from app.api.layers import router as layers_router
from app.api.spatial import router as spatial_router
from app.api.network import router as network_router
from app.api.routing import router as routing_router
from app.core.config import settings
from app.schemas.health import RootResponse

app = FastAPI(title="CityScope API", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(layers_router)
app.include_router(spatial_router)
app.include_router(network_router)
app.include_router(routing_router)


@app.get("/", response_model=RootResponse)
def root() -> RootResponse:
    return RootResponse()
