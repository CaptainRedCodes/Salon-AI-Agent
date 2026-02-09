from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.logging_config import get_logger
from app.api.routes import (
    bookings_router,
    help_requests_router,
    dashboard_router,
    knowledge_router,
)

load_dotenv()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup/shutdown."""
    logger.info("Dashboard: http://localhost:8000")
    logger.info("API Docs:  http://localhost:8000/docs")
    yield
    logger.info("Backend stopped")


app = FastAPI(
    title="Salon AI Backend",
    description="""
    Backend API for Salon AI Agent.
    
    The AI agent calls these endpoints directly:
    - POST /api/bookings - Create booking
    - POST /api/help-requests - Escalate question
    - GET /api/availability - Check slots
    - GET /api/knowledge-base/search - Search for answers
    """,
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)
app.include_router(bookings_router)
app.include_router(help_requests_router)
app.include_router(knowledge_router)


@app.get("/health")
async def health_check():
    """Health check endpoint for api_client."""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
