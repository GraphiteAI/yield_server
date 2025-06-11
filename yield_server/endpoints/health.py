from fastapi import FastAPI, APIRouter
from datetime import datetime
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
router = APIRouter()

@router.get("/status/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

app = FastAPI()
app.include_router(router)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://taotrader.xyz"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

