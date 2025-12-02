import asyncio
import subprocess
import shutil
import threading
import signal
import sys
from pathlib import Path
from typing import Optional
from kokoro.common.utils.logging import setup_logger
from kokoro.common.utils.thread_pool import get_thread_pool
from kokoro.common.utils.retry import retry_with_backoff
import httpx

logger = setup_logger(__name__)


class AutoUpdateService:
    def __init__(
        self,
        github_repo: str,
        branch: str = "main",
        check_interval: int = 300,
        restart_delay: int = 10
    ):
        self.github_repo = github_repo
        self.branch = branch
        self.check_interval = check_interval
        self.restart_delay = restart_delay
        self.current_commit: Optional[str] = None
        self.is_running = False
        self._check_task = None
        self.thread_pool = get_thread_pool()
        self._restart_pending = False
    
    async def start(self):
        if self.is_running:
            logger.warning("Auto-update service is already running")
            return
        
        self.is_running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("Auto-update service started")
    
    async def stop(self):
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Auto-update service stopped")
    
    async def _check_loop(self):
        while self.is_running:
            try:
                await self._check_for_updates()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("Check loop cancelled")
                break
            except Exception as e:
                logger.error(f"Auto-update check failed: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)
    
    @retry_with_backoff(max_retries=3, initial_delay=2.0, max_delay=30.0)
    async def _get_latest_commit(self) -> str:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"https://api.github.com/repos/{self.github_repo}/commits/{self.branch}"
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                return data["sha"]
        except Exception as e:
            logger.error(f"Failed to get latest commit: {e}", exc_info=True)
            raise
    
    async def _check_for_updates(self):
        try:
            latest_commit = await self._get_latest_commit()
            
            if self.current_commit is None:
                self.current_commit = latest_commit
                logger.info(f"Initial commit: {latest_commit}")
                return
            
            if latest_commit != self.current_commit:
                logger.info(f"New commit detected: {latest_commit}")
                await self._update_code()
                self.current_commit = latest_commit
        except Exception as e:
            logger.error(f"Failed to check for updates: {e}", exc_info=True)
    
    async def _update_code(self):
        if self._restart_pending:
            logger.warning("Update already in progress, skipping")
            return
        
        logger.info("Starting code update...")
        self._restart_pending = True
        
        try:
            await self._backup_current_version()
            await self._pull_latest_code()
            await self._run_tests()
            
            logger.info(f"Scheduling service restart in {self.restart_delay} seconds...")
            await asyncio.sleep(self.restart_delay)
            
            await self._restart_service()
            logger.info("Code update completed successfully")
        except Exception as e:
            logger.error(f"Code update failed: {e}", exc_info=True)
            await self._rollback()
        finally:
            self._restart_pending = False
    
    async def _backup_current_version(self):
        try:
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)
            
            import time
            timestamp = int(time.time())
            backup_path = backup_dir / f"backup_{timestamp}"
            
            def do_backup():
                shutil.copytree(".", backup_path, ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", "*.pyc", ".venv", "venv", "backups"
                ))
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.thread_pool.executor, do_backup)
            
            logger.info(f"Backup created: {backup_path}")
        except Exception as e:
            logger.error(f"Backup failed: {e}", exc_info=True)
            raise
    
    async def _pull_latest_code(self):
        try:
            def do_pull():
                process = subprocess.run(
                    ["git", "pull", "origin", self.branch],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if process.returncode != 0:
                    raise Exception(f"Git pull failed: {process.stderr}")
                return process.stdout
            
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(self.thread_pool.executor, do_pull)
            logger.info(f"Code pulled successfully: {output}")
        except Exception as e:
            logger.error(f"Git pull failed: {e}", exc_info=True)
            raise
    
    async def _run_tests(self):
        try:
            def do_tests():
                process = subprocess.run(
                    ["python", "-m", "pytest", "tests/"],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return process.returncode == 0, process.stdout, process.stderr
            
            loop = asyncio.get_event_loop()
            success, stdout, stderr = await loop.run_in_executor(
                self.thread_pool.executor, do_tests
            )
            
            if not success:
                logger.warning(f"Tests failed: {stderr}")
        except Exception as e:
            logger.warning(f"Test execution failed: {e}")
    
    async def _restart_service(self):
        logger.info("Initiating graceful service restart...")
        
        def restart_in_thread():
            import time
            import os
            time.sleep(2)
            logger.info("Restarting service...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        
        import os
        restart_thread = threading.Thread(
            target=restart_in_thread,
            daemon=True,
            name="restart-thread"
        )
        restart_thread.start()
        
        await asyncio.sleep(1)
    
    async def _rollback(self):
        try:
            logger.info("Rolling back to previous version...")
            backup_dir = Path("backups")
            backups = sorted(backup_dir.glob("backup_*"), reverse=True)
            
            if backups:
                latest_backup = backups[0]
                
                def do_rollback():
                    shutil.copytree(latest_backup, ".", dirs_exist_ok=True)
                
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(self.thread_pool.executor, do_rollback)
                logger.info("Rollback completed")
            else:
                logger.warning("No backups found for rollback")
        except Exception as e:
            logger.error(f"Rollback failed: {e}", exc_info=True)
