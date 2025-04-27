from fastapi.middleware.cors import CORSMiddleware
import time
from fastapi import Request, FastAPI, BackgroundTasks
import setup
import asyncio
from concurrent.futures import ThreadPoolExecutor
import functools
import globals
import os  # Required for Cloud Run PORT

app = FastAPI()

# Create a thread pool executor (reduced workers for Cloud Run limits)
thread_pool = ThreadPoolExecutor(max_workers=2)  # Reduced from 10 for free tier

# CORS Configuration - Updated for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.ea.com",
        "https://ea.com",
        "http://localhost:8000"  # For local testing
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

def run_in_threadpool(func):
    """Decorator to run blocking functions in threadpool"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            thread_pool, 
            functools.partial(func, *args, **kwargs)
        )
    return wrapper

# Health check endpoint (required for Cloud Run)
@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "EAFC SBC Solver"}

@app.get('/solver-logs')
async def get_solver_logs():
    return await run_in_threadpool(lambda: {"logs": globals.solver_logs})()

@app.post('/solve')
async def solve_sbc(request: Request):
    try:
        request_data = await request.json()
        result = await run_in_threadpool(process_solve_request)(request_data)
        return result
    except Exception as e:
        globals.add_log(f"API Error: {str(e)}")
        return {"error": str(e)}, 500

def process_solve_request(request_data):
    """Synchronous processing function"""
    globals.clear_logs()
    globals.add_log("Solver started")
    
    try:
        result = setup.runAutoSBC(
            request_data['sbcData'],
            request_data['clubPlayers'],
            request_data['maxSolveTime']
        )
        globals.add_log("Solver completed")
        return result
    except Exception as e:
        globals.add_log(f"Solver error: {str(e)}")
        raise

@app.post('/clear-logs')
async def clear_logs():
    return await run_in_threadpool(globals.clear_logs)()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup during shutdown"""
    thread_pool.shutdown(wait=False)
    globals.add_log("Service shutting down")

# Cloud Run entry point
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, workers=1)
