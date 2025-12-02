from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from kokoro.common.database import get_db
from kokoro.task_center.services.task_dispatcher import TaskDispatcher
from kokoro.task_center.shared import miner_cache
from kokoro.task_center.schemas.miner import MinerTaskReceive, MinerTaskResponse, MinerSubmitRequest, MinerSubmitResponse
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


@router.post("/receive", response_model=MinerTaskResponse)
async def receive_task(
    request: MinerTaskReceive,
    db: Session = Depends(get_db)
):
    dispatcher = TaskDispatcher(db, miner_cache)
    task = dispatcher.assign_task_to_miner(request.workflow_id, request.miner_key)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or already assigned")
    
    return MinerTaskResponse.from_task(task)


@router.post("/submit", response_model=MinerSubmitResponse)
async def submit_result(
    request: MinerSubmitRequest,
    db: Session = Depends(get_db)
):
    dispatcher = TaskDispatcher(db, miner_cache)
    submission = dispatcher.receive_miner_submission(request)
    
    return MinerSubmitResponse(
        submission_id=submission["submission_id"],
        workflow_id=submission["workflow_id"],
        status=submission["status"],
        estimated_reward=submission.get("estimated_reward", 0.0)
    )

