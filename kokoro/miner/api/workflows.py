from fastapi import APIRouter, HTTPException
from kokoro.miner.services.queue_manager import QueueManager
from kokoro.miner.schemas.workflow import WorkflowReceive, WorkflowReceiveResponse, WorkflowSubmit, WorkflowSubmitResponse
from kokoro.common.utils.logging import setup_logger
import httpx
from kokoro.common.config import settings

router = APIRouter()
logger = setup_logger(__name__)
queue_manager = QueueManager()


@router.post("/receive", response_model=WorkflowReceiveResponse)
async def receive_workflow(request: WorkflowReceive):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.TASK_CENTER_URL}/v1/miners/receive",
                json=request.dict()
            )
            response.raise_for_status()
            task_data = response.json()
            
            await queue_manager.enqueue_task(task_data)
            
            return WorkflowReceiveResponse(**task_data)
    except httpx.HTTPError as e:
        logger.error(f"Failed to receive workflow: {e}")
        raise HTTPException(status_code=500, detail="Failed to receive workflow")


@router.post("/submit", response_model=WorkflowSubmitResponse)
async def submit_workflow(request: WorkflowSubmit):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.TASK_CENTER_URL}/v1/miners/submit",
                json=request.dict()
            )
            response.raise_for_status()
            result = response.json()
            
            return WorkflowSubmitResponse(**result)
    except httpx.HTTPError as e:
        logger.error(f"Failed to submit workflow: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit workflow")

