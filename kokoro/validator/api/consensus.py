from fastapi import APIRouter, HTTPException
from kokoro.validator.services.consensus_manager import ConsensusManager
from kokoro.validator.services.weight_calculator import WeightCalculator
from kokoro.validator.services.bittensor_sync import BittensorSyncService
from kokoro.common.bittensor.wallet import WalletManager
from kokoro.validator.schemas.consensus import ConsensusWeightRequest, ConsensusWeightResponse, ConsensusSyncRequest
from kokoro.common.utils.logging import setup_logger
from pydantic import BaseModel
from typing import Dict

router = APIRouter()
logger = setup_logger(__name__)
consensus_manager = ConsensusManager()

wallet_manager = WalletManager("validator", "default")
bittensor_sync = BittensorSyncService(wallet_manager)
weight_calculator = WeightCalculator(bittensor_sync)


@router.post("/weights", response_model=ConsensusWeightResponse)
async def submit_consensus_weights(request: ConsensusWeightRequest):
    try:
        result = consensus_manager.submit_consensus_weights(
            request.workflow_id,
            request.validator_key,
            request.weights
        )
        return ConsensusWeightResponse(**result)
    except Exception as e:
        logger.error(f"Consensus weight submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def receive_consensus_sync(request: ConsensusSyncRequest):
    try:
        workflow_id = request.workflow_id
        consensus_data = request.consensus_data
        miner_scores = consensus_data.get("miner_scores", {})
        
        logger.info(f"Received consensus sync for workflow {workflow_id}, {len(miner_scores)} miners")
        
        weights = weight_calculator.calculate_weights(
            workflow_id=workflow_id,
            miner_scores=miner_scores
        )
        
        weight_calculator.set_weights_to_chain(weights)
        
        logger.info(f"Consensus sync processed, weights set for {len(weights)} miners")
        
        return {
            "status": "success",
            "message": "Consensus data received and processed",
            "workflow_id": workflow_id,
            "miners_count": len(miner_scores)
        }
    except Exception as e:
        logger.error(f"Consensus sync processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

