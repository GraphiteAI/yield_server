from yield_server.backend.database.models import UserRole

from yield_server.backend.crud.leader_crud import LeaderCRUD
from yield_server.backend.schema.leader_schema import LeaderGet
from yield_server.backend.crud.leadermetrics_crud import LeaderMetricsCRUD
from yield_server.backend.schema.leadermetrics_schema import (
    LeaderMetricsCreate,
    LeaderMetricsUpdate,
    LeaderMetricsRemove,
    LeaderMetricsOut,
    LeaderMetricsGet,
    LeaderMetricsSnapshotCreate,
    LeaderMetricsSnapshotUpdate,
    LeaderMetricsSnapshotOut,
    LeaderMetricsSnapshotGet,   
    LeaderMetricsHistoryGet,
    # LeaderMetricsSnapshotDelete,
    LeaderMetricsSnapshotGet
)

from yield_server.middleware.jwt_middleware import get_user_id_from_jwt, enforce_user_id_from_jwt
from yield_server.middleware.admin_middleware import validate_admin_key
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.types import UUID4
from typing import Union, Optional, List

router = APIRouter(prefix="/api/v1/leader_metrics", tags=["leader_metrics"])
leader_metrics_crud = LeaderMetricsCRUD()
leader_crud = LeaderCRUD()

@router.post("/create_metrics", response_model=LeaderMetricsOut, summary="[Admin] Create leader metrics", description="Create leader metrics for a leader")
async def create_metrics(
    metrics: LeaderMetricsCreate,
    is_admin: UUID4 = Depends(validate_admin_key)
) -> LeaderMetricsOut:
    try:
        if not is_admin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        # check if the user is a copytrader
        leader_create = LeaderGet(
            id = metrics.leader_id
        )
        leader = await leader_crud.get_leader_by_id_public(leader_create)
        leader_metrics = await leader_metrics_crud.create_metrics(metrics)
        return leader_metrics
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_metrics_history", response_model=List[LeaderMetricsSnapshotOut])
async def get_metrics_history(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> List[LeaderMetricsSnapshotOut]:
    leader_get = LeaderMetricsHistoryGet(
        leader_id = current_user
    )
    try:
        return await leader_metrics_crud.get_metrics_history(leader_get)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/update_metrics", response_model=LeaderMetricsOut, summary="[Admin] Update leader metrics", description="Update leader metrics for a leader")
async def update_metrics(
    metrics: LeaderMetricsUpdate,
    is_admin: UUID4 = Depends(validate_admin_key)
) -> LeaderMetricsOut:
    try:
        if not is_admin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return await leader_metrics_crud.update_metrics(metrics)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/take_snapshot", response_model=bool, summary="[Admin] Take snapshot of all leader metrics", description="Take a snapshot of all leader metrics")
async def take_snapshot(
    is_admin: UUID4 = Depends(validate_admin_key)
) -> bool:
    try:
        all_leader_get: List[LeaderMetricsGet] = await leader_metrics_crud.get_all_leader_uuids()
        for leader_get in all_leader_get:
            await leader_metrics_crud.take_snapshot(leader_get)
        return True
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create_snapshot", response_model=LeaderMetricsSnapshotOut, summary="[Admin] Create a snapshot of a leader metrics", description="Create a snapshot of a leader metrics")
async def create_snapshot(
    snapshot_create: LeaderMetricsSnapshotCreate,
    is_admin: UUID4 = Depends(validate_admin_key)
) -> LeaderMetricsSnapshotOut:
    try:
        if not is_admin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return await leader_metrics_crud.create_snapshot(snapshot_create)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Yield Leader Metrics API",
    description="API for managing leader metrics",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://taotrader.xyz"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
