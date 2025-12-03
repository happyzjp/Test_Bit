from fastapi import APIRouter, Depends, HTTPException, Security, Request
from sqlalchemy.orm import Session
from kokoro.common.database import get_db
from kokoro.common.auth.api_key import verify_api_key
from kokoro.task_center.services.score_archive import ScoreArchive
from kokoro.task_center.services.consensus_sync import ConsensusSync
from kokoro.task_center.schemas.score import ScoreSubmit, ScoreQueryResponse
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


@router.post("/submit")
async def submit_score(
    score_data: ScoreSubmit,
    db: Session = Depends(get_db)
):
    archive = ScoreArchive(db)
    archive.submit_score(score_data)
    return {"status": "success", "message": "Score submitted successfully"}


@router.get("/query/{miner_hotkey}", response_model=ScoreQueryResponse)
async def query_score(
    miner_hotkey: str,
    workflow_id: str = None,
    request: Request = None,
    api_key: str = Security(verify_api_key),
    db: Session = Depends(get_db)
):
    archive = ScoreArchive(db)
    scores = archive.get_miner_scores(miner_hotkey, workflow_id)
    
    if not scores:
        raise HTTPException(status_code=404, detail="No scores found")
    
    return ScoreQueryResponse(
        miner_hotkey=miner_hotkey,
        scores=scores,
        ema_score=archive.calculate_ema_score(miner_hotkey, workflow_id)
    )


@router.get("/all")
async def get_all_scores(
    workflow_id: str,
    request: Request,
    api_key: str = Security(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Get all miner scores for a workflow with consensus data.
    According to architecture doc section 6.4: GET /v1/scores/query (for all miners)
    """
    archive = ScoreArchive(db)
    consensus_sync = ConsensusSync(db)
    
    scores = archive.get_all_scores_for_workflow(workflow_id)
    consensus_data = consensus_sync.sync_consensus_data(workflow_id)
    
    return {
        "workflow_id": workflow_id,
        "scores": scores,
        "consensus_data": consensus_data
    }


@router.get("/query")
async def query_all_scores(
    workflow_id: str = None,
    request: Request = None,
    api_key: str = Security(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Query all miner scores for weight calculation.
    According to architecture doc section 6.4: GET /v1/scores/query
    Returns all miners' cumulative scores and EMA scores (aggregated by task center)
    """
    archive = ScoreArchive(db)
    consensus_sync = ConsensusSync(db)
    
    if workflow_id:
        # Get scores for specific workflow
        scores = archive.get_all_scores_for_workflow(workflow_id)
        consensus_data = consensus_sync.sync_consensus_data(workflow_id)
        
        return {
            "workflow_id": workflow_id,
            "miner_scores": {
                item["miner_hotkey"]: {
                    "average_score": item["average_score"],
                    "ema_score": item["ema_score"],
                    "validator_count": item["validator_count"]
                }
                for item in scores
            },
            "consensus_data": consensus_data
        }
    else:
        # Get all miners' historical scores (for overall weight calculation)
        from kokoro.common.models.score import Score
        from sqlalchemy import func
        
        # Get all unique miners
        miners = db.query(Score.miner_hotkey).distinct().all()
        
        all_miner_scores = {}
        for (miner_hotkey,) in miners:
            ema_score = archive.calculate_ema_score(miner_hotkey)
            history = archive.get_miner_history_scores(miner_hotkey, limit=100)
            
            all_miner_scores[miner_hotkey] = {
                "ema_score": ema_score,
                "history_count": len(history),
                "latest_score": history[0]["final_score"] if history else 0.0
            }
        
        return {
            "all_miners": all_miner_scores,
            "total_miners": len(all_miner_scores)
        }

