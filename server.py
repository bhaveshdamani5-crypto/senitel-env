"""
Sentinel-Log-Shield: FastAPI server with SST-compliant endpoints.
Provides POST /reset, POST /step, GET /state endpoints.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from env import LogSanitizerEnvironment
from models import RedactionAction, ResetResponse, StepResponse, EnvironmentState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Sentinel-Log-Shield",
    description="SST-compliant OpenEnv for PII redaction in system logs",
    version="1.0.0"
)

# CORS middleware for Hugging Face compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global environment instance
env = LogSanitizerEnvironment()
logger.info("Environment initialized: Sentinel-Log-Shield")


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "name": "Sentinel-Log-Shield",
        "description": "OpenEnv-compliant log sanitizer for PII redaction",
        "version": "1.0.0",
        "endpoints": [
            {"method": "POST", "path": "/reset", "description": "Reset environment"},
            {"method": "POST", "path": "/step", "description": "Execute one step"},
            {"method": "GET", "path": "/state", "description": "Get current state"},
        ]
    }


@app.post("/reset", response_model=ResetResponse)
async def reset():
    """
    Reset the environment and start a new episode.
    
    Returns:
        ResetResponse with initial observation and info.
    """
    logger.info("[START] Reset called - new episode beginning")
    try:
        response = env.reset()
        logger.info(f"[RESET] Task: {response.observation.task}, Log ID: {response.observation.log_id}")
        return response
    except Exception as e:
        logger.error(f"Error in reset: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@app.post("/step", response_model=StepResponse)
async def step(action: RedactionAction):
    """
    Execute one step: process redaction action and return reward.
    
    Args:
        action: RedactionAction with redactions and redacted log.
    
    Returns:
        StepResponse with observation, reward, done flag.
    """
    logger.info(f"[STEP] Processing action for log: {action.log_id}")
    try:
        response = env.step(action)
        logger.info(
            f"[STEP] Reward: {response.reward.total_reward:.2f}, "
            f"Done: {response.done}, F1: {response.reward.metrics.get('f1_score', 0):.2f}"
        )
        return response
    except ValueError as e:
        logger.error(f"Validation error in step: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in step: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Step failed: {str(e)}")


@app.get("/state", response_model=EnvironmentState)
async def get_state():
    """
    Get current environment state.
    
    Returns:
        EnvironmentState with current observation, metrics, and history.
    """
    logger.info("[END] State query")
    try:
        return env.state()
    except Exception as e:
        logger.error(f"Error in state: {str(e)}")
        raise HTTPException(status_code=500, detail=f"State query failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Sentinel-Log-Shield",
        "is_running": env.is_running,
        "cumulative_reward": env.cumulative_reward
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860,
        log_level="info"
    )
