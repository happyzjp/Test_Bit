from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Union
from datetime import datetime, timezone
from kokoro.common.models.miner import Miner
from kokoro.common.models.score import Score
from kokoro.common.models.task_assignment import TaskAssignment
from kokoro.common.utils.logging import setup_logger
from kokoro.task_center.services.miner_cache import MinerCache
from kokoro.task_center import shared
import random
import httpx
from kokoro.common.config import settings

logger = setup_logger(__name__)


class MinerSelector:
    def __init__(self, db: Session, miner_cache: MinerCache):
        self.db = db
        self.bittensor_client = shared.bittensor_client
        self.miner_cache = miner_cache
    
    def select_miners(
        self,
        workflow_id: str,
        count: Optional[int] = 10,
        min_stake: float = 1000.0
    ) -> List[str]:

        online_miners = self.miner_cache.get_online_miners()
        
        eligible_miners = []
        for miner_data in online_miners:
            hotkey = miner_data["hotkey"]
            
            if miner_data.get("stake", 0.0) < min_stake:
                continue
            
            if not miner_data.get("is_active", False):
                continue
            
            miner = self.db.query(Miner).filter(
                Miner.hotkey == hotkey
            ).first()
            
            if not miner:
                miner = Miner(
                    hotkey=hotkey,
                    stake=miner_data.get("stake", 0.0),
                    reputation=miner_data.get("reputation", 0.0),
                    is_online=True
                )
                self.db.add(miner)
                self.db.commit()
            
            recent_scores = self.db.query(Score).filter(
                Score.miner_hotkey == hotkey
            ).order_by(Score.created_at.desc()).limit(10).all()
            
            avg_score = sum(s.final_score for s in recent_scores) / len(recent_scores) if recent_scores else 0.0
            
            weight = miner_data.get("stake", 0.0) * (1.0 + avg_score / 10.0)
            
            eligible_miners.append({
                "hotkey": hotkey,
                "stake": miner_data.get("stake", 0.0),
                "reputation": miner_data.get("reputation", 0.0),
                "weight": weight
            })
        
        if not eligible_miners:
            logger.warning(f"No eligible online miners found for task {workflow_id}")
            return []
        
        # If count is None, return all eligible miners
        if count is None:
            logger.info(f"Selecting all {len(eligible_miners)} eligible miners for task {workflow_id}")
            return [m["hotkey"] for m in eligible_miners]
        
        # Otherwise, use weighted random selection
        weights = [m["weight"] for m in eligible_miners]
        selected = random.choices(eligible_miners, weights=weights, k=min(count, len(eligible_miners)))
        
        return [m["hotkey"] for m in selected]
    
    async def assign_task_to_miners(
        self,
        workflow_id: str,
        task_data: Dict,
        miner_hotkeys: List[str]
    ) -> Dict[str, bool]:
        results = {}
        
        for miner_hotkey in miner_hotkeys:
            try:
                miner = self.db.query(Miner).filter(Miner.hotkey == miner_hotkey).first()
                if not miner:
                    continue
                
                from kokoro.common.models.task_assignment import TaskAssignment
                existing_assignment = self.db.query(TaskAssignment).filter(
                    TaskAssignment.workflow_id == workflow_id,
                    TaskAssignment.miner_hotkey == miner_hotkey
                ).first()
                
                if existing_assignment:
                    results[miner_hotkey] = False
                    continue
                
                import uuid
                assignment = TaskAssignment(
                    id=str(uuid.uuid4()),
                    workflow_id=workflow_id,
                    miner_hotkey=miner_hotkey,
                    assigned_at=datetime.now(timezone.utc),
                    status="assigned"
                )
                self.db.add(assignment)
                self.db.commit()
                
                miner_url = self._get_miner_url(miner_hotkey)
                
                if miner_url:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        endpoints = ["/v1/train", "/v1/workflows/receive"]
                        response = None

                        for endpoint in endpoints:
                            try:
                                response = await client.post(
                                    f"{miner_url}{endpoint}",
                                    json={
                                        "workflow_id": workflow_id,
                                        "miner_key": miner_hotkey,
                                        **task_data
                                    },
                                )
                                if response.status_code == 200:
                                    break
                            except Exception as e:
                                logger.debug(f"Failed to post to {endpoint}: {e}")
                                continue

                        if response is not None and response.status_code == 200:
                            results[miner_hotkey] = True
                            assignment.status = "delivered"
                            logger.info(f"Task assigned to miner {miner_hotkey}")
                        else:
                            results[miner_hotkey] = False
                            assignment.status = "failed"
                            status_code = response.status_code if response is not None else "no_response"
                            logger.warning(f"Failed to assign task to miner {miner_hotkey}: {status_code}")
                else:
                    results[miner_hotkey] = True
                    assignment.status = "pending"
                    logger.info(f"Task queued for miner {miner_hotkey} (URL not available)")
                
                self.db.commit()
            except Exception as e:
                logger.error(f"Error assigning task to miner {miner_hotkey}: {e}")
                results[miner_hotkey] = False
        
        return results
    
    def _get_miner_url(self, miner_hotkey: str) -> Optional[str]:
        miner_url = self.miner_cache.get_miner_url(miner_hotkey)
        if miner_url:
            return miner_url
        
        try:
            miner = self.db.query(Miner).filter(Miner.hotkey == miner_hotkey).first()
            if miner and miner.miner_url:
                return miner.miner_url
            
            miners = self.bittensor_client.get_all_miners()
            
            for miner_data in miners:
                if miner_data["hotkey"] == miner_hotkey:
                    if miner_data.get("uid") is not None:
                        uid = miner_data.get("uid")
                        if self.bittensor_client.metagraph and uid < len(self.bittensor_client.metagraph.axons):
                            axon = self.bittensor_client.metagraph.axons[uid]
                            ip = axon.ip
                            port = axon.port
                            if ip and ip != "0.0.0.0" and port:
                                url = f"http://{ip}:{port}"
                                if miner:
                                    miner.miner_url = url
                                    self.db.commit()
                                return url
        except Exception as e:
            logger.error(f"Error getting miner URL: {e}", exc_info=True)
        
        return None
