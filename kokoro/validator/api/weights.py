from fastapi import APIRouter, HTTPException
from kokoro.validator.services.weight_calculator import WeightCalculator
from kokoro.validator.services.bittensor_sync import BittensorSyncService
from kokoro.common.bittensor.wallet import WalletManager
from kokoro.validator.schemas.weight import WeightCalculateRequest, WeightCalculateResponse
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)

wallet_manager = WalletManager("validator", "default")
bittensor_sync = BittensorSyncService(wallet_manager)
weight_calculator = WeightCalculator(bittensor_sync)


@router.post("/calculate", response_model=WeightCalculateResponse)
async def calculate_weights(request: WeightCalculateRequest):
    try:
        weights = weight_calculator.calculate_weights(
            request.workflow_id,
            request.miner_scores
        )
        return WeightCalculateResponse(weights=weights)
    except Exception as e:
        logger.error(f"Weight calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set")
async def set_weights(weights: dict):
    try:
        weight_calculator.set_weights_to_chain(weights)
        return {"status": "success", "message": "Weights set successfully"}
    except Exception as e:
        logger.error(f"Failed to set weights: {e}")
        raise HTTPException(status_code=500, detail=str(e))

