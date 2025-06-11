from yield_server.backend.database.models import UserRole

from yield_server.backend.crud.copytrader_crud import CopyTraderCRUD
from yield_server.backend.schema.copytrader_schema import CopyTraderGet
from yield_server.backend.crud.copytradermetrics_crud import CopyTraderMetricsCRUD
from yield_server.backend.schema.copytradermetrics_schema import (
    CopyTraderMetricsCreate,
    CopyTraderMetricsUpdate,
    CopyTraderMetricsRemove,
    CopyTraderMetricsOut,
    CopyTraderMetricsGet,
    CopyTraderMetricsSnapshotCreate,
    CopyTraderMetricsSnapshotUpdate,
    CopyTraderMetricsSnapshotOut,
    CopyTraderMetricsSnapshotGet,
    # CopyTraderMetricsSnapshotDelete,
    CopyTraderMetricsSnapshotGet
)

from yield_server.middleware.jwt_middleware import get_user_id_from_jwt, enforce_user_id_from_jwt
from yield_server.middleware.admin_middleware import validate_admin_key
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.types import UUID4
from typing import Union, Optional, List

router = APIRouter(prefix="/api/v1/copytrader_metrics", tags=["copytrader_metrics"])
copytrader_metrics_crud = CopyTraderMetricsCRUD()
copytrader_crud = CopyTraderCRUD()

@router.post("/create_metrics", response_model=CopyTraderMetricsOut, summary="[Admin] Create copytrader metrics", description="Create copytrader metrics for a copytrader")
async def create_metrics(
    metrics: CopyTraderMetricsCreate,
    is_admin: UUID4 = Depends(validate_admin_key)
) -> CopyTraderMetricsOut:
    try:
        if not is_admin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        # check if the user is a copytrader
        copytrader_create = CopyTraderGet(
            id = metrics.copytrader_id
        )
        copytrader = await copytrader_crud.get_copytrader(copytrader_create)
        copytrader_metrics = await copytrader_metrics_crud.create_metrics(metrics)
        return copytrader_metrics
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_metrics_history", response_model=List[CopyTraderMetricsSnapshotOut])
async def get_metrics_history(
    current_user: UUID4 = Depends(enforce_user_id_from_jwt)
) -> List[CopyTraderMetricsSnapshotOut]:
    copytrader_get = CopyTraderMetricsGet(
        copytrader_id = current_user
    )
    try:
        return await copytrader_metrics_crud.get_metrics_history(copytrader_get)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/update_metrics", response_model=CopyTraderMetricsOut, summary="[Admin] Update copytrader metrics", description="Update copytrader metrics for a copytrader")
async def update_metrics(
    metrics: CopyTraderMetricsUpdate,
    is_admin: UUID4 = Depends(validate_admin_key)
) -> CopyTraderMetricsOut:
    try:
        if not is_admin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return await copytrader_metrics_crud.update_metrics(metrics)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/take_snapshot", response_model=bool, summary="[Admin] Take snapshot of all copytrader metrics", description="Take a snapshot of all copytrader metrics")
async def take_snapshot(
    is_admin: UUID4 = Depends(validate_admin_key)
) -> bool:
    try:
        all_copytrader_get: List[CopyTraderMetricsGet] = await copytrader_metrics_crud.get_all_copytrader_uuids()
        for copytrader_get in all_copytrader_get:
            await copytrader_metrics_crud.take_snapshot(copytrader_get)
        return True
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create_snapshot", response_model=CopyTraderMetricsSnapshotOut, summary="[Admin] Create a snapshot of a copytrader metrics", description="Create a snapshot of a copytrader metrics")
async def create_snapshot(
    snapshot_create: CopyTraderMetricsSnapshotCreate,
    is_admin: UUID4 = Depends(validate_admin_key)
) -> CopyTraderMetricsSnapshotOut:
    try:
        if not is_admin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return await copytrader_metrics_crud.create_snapshot(snapshot_create)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="Yield CopyTrader Metrics API",
    description="API for managing copytrader metrics",
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

