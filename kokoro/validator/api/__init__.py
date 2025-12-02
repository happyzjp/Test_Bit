from fastapi import APIRouter
from kokoro.validator.api import audit, scores, weights, consensus

router = APIRouter()

router.include_router(audit.router, prefix="/audit", tags=["audit"])
router.include_router(scores.router, prefix="/scores", tags=["scores"])
router.include_router(weights.router, prefix="/weights", tags=["weights"])
router.include_router(consensus.router, prefix="/consensus", tags=["consensus"])

