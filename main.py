from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os

# Import your existing routers
from tiles_endpoint import router as tiles_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NLDAS-3 Hydrology Backend",
    description="Weather and climate data API with interactive mapping",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register tile endpoint
app.include_router(tiles_router, prefix="/api", tags=["tiles"])

# Import your existing chat functionality
from agents.agent_chat import handle_chat_request

@app.post("/api/chat")
async def chat_endpoint(data: dict):
    """Main chat endpoint - same as your Azure Functions endpoint"""
    try:
        result = handle_chat_request(data)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "content": str(e)}
        )

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "nldas3-backend"}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "NLDAS-3 Hydrology Backend",
        "endpoints": {
            "chat": "/api/chat",
            "tiles": "/api/tiles/{variable}/{date}/{z}/{x}/{y}.png",
            "health": "/api/health"
        },
        "examples": {
            "chat_request": {
                "method": "POST",
                "url": "/api/chat",
                "body": {"input": "Show me temperature in Florida on January 15, 2023"}
            },
            "tile_request": {
                "method": "GET", 
                "url": "/api/tiles/Tair/2023-01-15/5/15/12.png"
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
