from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

# Import both systems
from tiles_endpoint import router as tiles_router
from agents.agent_chat import handle_chat_request

app = FastAPI(title="NLDAS-3 All-in-One Backend")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Tile endpoints
app.include_router(tiles_router, prefix="/api", tags=["tiles"])

# Chat endpoint (replaces Azure Functions)
@app.post("/api/chat")
async def chat_endpoint(data: dict):
    """Same as your Azure Functions multi_agent_function"""
    try:
        result = handle_chat_request(data)
        return JSONResponse(content={"response": result})  # Match Azure Functions format
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# Health checks
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "nldas3-all-in-one"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
