"""
Health diagnostics and monitoring for the RAG system.

This module provides utilities to check the health and status of the RAG system,
useful for debugging and monitoring.
"""
import os
import asyncio
import logging
import psutil
import aiohttp
import aiofiles
import aiofiles.os
from datetime import datetime
from typing import Dict, Any, List
import json

from .config import (
    LLAMA_SERVER_URL, VECTOR_DB_PATH, METADATA_PATH,
    FILE_HISTORY_PATH, EMBEDDINGS_CACHE_PATH, DOCUMENT_SUMMARIES_PATH,
    DOCUMENT_TEXTS_DIR, UPLOADS_FOLDER, VECTOR_DB_FOLDER,
    INGESTION_RAPPORT_PATH
)
from .state import state

logger = logging.getLogger("rag-assistant-enhanced")


class RAGHealthChecker:
    """Health checker for the RAG system."""
    
    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = 0
        self.results = []
    
    def _log_check(self, component: str, status: str, message: str, details: Any = None):
        """Log a check result."""
        result = {
            "component": component,
            "status": status,  # "pass", "fail", "warning"
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        
        if status == "pass":
            self.checks_passed += 1
            logger.info(f"✓ {component}: {message}")
        elif status == "fail":
            self.checks_failed += 1
            logger.error(f"✗ {component}: {message}")
        elif status == "warning":
            self.warnings += 1
            logger.warning(f"⚠️  {component}: {message}")
        
        if details:
            logger.debug(f"   Details: {details}")
    
    async def check_llama_server(self) -> bool:
        """Check if llama-server is accessible."""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = LLAMA_SERVER_URL.rsplit('/', 1)[0]
                async with session.get(url) as response:
                    if response.status == 200:
                        self._log_check(
                            "Llama Server",
                            "pass",
                            f"Server is responding at {url}",
                            {"status_code": response.status}
                        )
                        return True
                    else:
                        self._log_check(
                            "Llama Server",
                            "warning",
                            f"Server responded with status {response.status}",
                            {"url": url, "status_code": response.status}
                        )
                        return False
        except Exception as e:
            self._log_check(
                "Llama Server",
                "fail",
                f"Cannot connect to server: {e}",
                {"url": LLAMA_SERVER_URL, "error": str(e)}
            )
            return False
    
    async def check_database_files(self) -> bool:
        """Check if database files exist and are valid."""
        checks = {
            "Vector DB": VECTOR_DB_PATH,
            "Vector DB Map": VECTOR_DB_PATH + ".map",
            "Metadata": METADATA_PATH,
            "File History": FILE_HISTORY_PATH,
        }
        
        all_ok = True
        for name, path in checks.items():
            exists = await aiofiles.os.path.exists(path)
            if exists:
                try:
                    stat = await aiofiles.os.stat(path)
                    size_mb = stat.st_size / (1024 * 1024)
                    self._log_check(
                        f"Database File: {name}",
                        "pass",
                        f"File exists ({size_mb:.2f} MB)",
                        {"path": path, "size_bytes": stat.st_size}
                    )
                except Exception as e:
                    self._log_check(
                        f"Database File: {name}",
                        "warning",
                        f"File exists but cannot read stats: {e}",
                        {"path": path}
                    )
                    all_ok = False
            else:
                self._log_check(
                    f"Database File: {name}",
                    "fail",
                    "File does not exist",
                    {"path": path}
                )
                all_ok = False
        
        return all_ok
    
    async def check_cache_files(self) -> bool:
        """Check cache files."""
        cache_file = EMBEDDINGS_CACHE_PATH + ".npy"
        
        if await aiofiles.os.path.exists(cache_file):
            try:
                stat = await aiofiles.os.stat(cache_file)
                size_mb = stat.st_size / (1024 * 1024)
                self._log_check(
                    "Embeddings Cache",
                    "pass",
                    f"Cache file exists ({size_mb:.2f} MB)",
                    {"path": cache_file, "size_mb": size_mb}
                )
                return True
            except Exception as e:
                self._log_check(
                    "Embeddings Cache",
                    "warning",
                    f"Cache file exists but cannot read: {e}",
                    {"path": cache_file}
                )
                return False
        else:
            self._log_check(
                "Embeddings Cache",
                "warning",
                "Cache file does not exist (will be created on first use)",
                {"path": cache_file}
            )
            return True  # Not critical
    
    async def check_uploads_folder(self) -> bool:
        """Check uploads folder and document count."""
        if not await aiofiles.os.path.exists(UPLOADS_FOLDER):
            self._log_check(
                "Uploads Folder",
                "fail",
                f"Folder does not exist: {UPLOADS_FOLDER}",
                {"path": UPLOADS_FOLDER}
            )
            return False
        
        try:
            files = await aiofiles.os.listdir(UPLOADS_FOLDER)
            doc_files = [f for f in files if not f.startswith('.') and os.path.isfile(os.path.join(UPLOADS_FOLDER, f))]
            
            self._log_check(
                "Uploads Folder",
                "pass",
                f"Found {len(doc_files)} document(s) in uploads",
                {"path": UPLOADS_FOLDER, "num_files": len(doc_files), "files": doc_files[:10]}  # Show first 10
            )
            return True
        except Exception as e:
            self._log_check(
                "Uploads Folder",
                "fail",
                f"Cannot read uploads folder: {e}",
                {"path": UPLOADS_FOLDER, "error": str(e)}
            )
            return False
    
    def check_state(self) -> bool:
        """Check in-memory state."""
        checks_ok = True
        
        # Check if RAG is enabled
        if state.rag_enabled:
            self._log_check(
                "RAG State",
                "pass",
                "RAG is enabled and operational",
                {"rag_enabled": True}
            )
        else:
            self._log_check(
                "RAG State",
                "fail",
                "RAG is disabled or not initialized",
                {"rag_enabled": False}
            )
            checks_ok = False
        
        # Check Annoy index
        if state.annoy_index:
            num_items = state.annoy_index.index.get_n_items()
            self._log_check(
                "Annoy Index",
                "pass",
                f"Index loaded with {num_items:,} vectors",
                {"num_vectors": num_items, "next_id": state.annoy_index.next_id}
            )
        else:
            self._log_check(
                "Annoy Index",
                "fail",
                "Annoy index is not loaded",
                {"annoy_index": None}
            )
            checks_ok = False
        
        # Check metadata
        num_chunks = len(state.chunks_metadata)
        if num_chunks > 0:
            self._log_check(
                "Chunks Metadata",
                "pass",
                f"Loaded {num_chunks:,} chunk(s) metadata",
                {"num_chunks": num_chunks}
            )
        else:
            self._log_check(
                "Chunks Metadata",
                "warning",
                "No chunks metadata loaded",
                {"num_chunks": 0}
            )
        
        # Check document summaries
        num_summaries = len(state.document_summaries)
        if num_summaries > 0:
            self._log_check(
                "Document Summaries",
                "pass",
                f"Loaded {num_summaries} document summarie(s)",
                {"num_summaries": num_summaries}
            )
        else:
            self._log_check(
                "Document Summaries",
                "warning",
                "No document summaries loaded",
                {"num_summaries": 0}
            )
        
        # Check embeddings cache
        num_cached = len(state.embeddings_cache)
        if num_cached > 0:
            cache_size_mb = sum(arr.nbytes for arr in state.embeddings_cache.values()) / (1024*1024)
            self._log_check(
                "Embeddings Cache (Memory)",
                "pass",
                f"Cached {num_cached:,} embedding(s) ({cache_size_mb:.2f} MB)",
                {"num_cached": num_cached, "size_mb": cache_size_mb}
            )
        else:
            self._log_check(
                "Embeddings Cache (Memory)",
                "warning",
                "No embeddings cached in memory yet",
                {"num_cached": 0}
            )
        
        return checks_ok
    
    def check_memory(self) -> bool:
        """Check memory usage."""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Warn if memory is high (>2GB)
            if memory_mb > 2048:
                self._log_check(
                    "Memory Usage",
                    "warning",
                    f"High memory usage: {memory_mb:.2f} MB",
                    {"memory_mb": memory_mb, "threshold": 2048}
                )
                return False
            else:
                self._log_check(
                    "Memory Usage",
                    "pass",
                    f"Memory usage is normal: {memory_mb:.2f} MB",
                    {"memory_mb": memory_mb}
                )
                return True
        except Exception as e:
            self._log_check(
                "Memory Usage",
                "warning",
                f"Cannot check memory: {e}",
                {"error": str(e)}
            )
            return False
    
    async def check_ingestion_rapport(self) -> bool:
        """Check the ingestion rapport for errors."""
        if not await aiofiles.os.path.exists(INGESTION_RAPPORT_PATH):
            self._log_check(
                "Ingestion Rapport",
                "warning",
                "No ingestion rapport found (no ingestion run yet?)",
                {"path": INGESTION_RAPPORT_PATH}
            )
            return True  # Not critical
        
        try:
            async with aiofiles.open(INGESTION_RAPPORT_PATH, 'r') as f:
                content = await f.read()
                rapport = json.loads(content)
            
            status = rapport.get('status', 'unknown')
            files_processed = rapport.get('files_processed', 0)
            files_failed = rapport.get('files_failed', 0)
            files_skipped = rapport.get('files_skipped', 0)
            
            if files_failed > 0:
                self._log_check(
                    "Ingestion Rapport",
                    "warning",
                    f"Last ingestion had {files_failed} failure(s)",
                    {
                        "status": status,
                        "processed": files_processed,
                        "failed": files_failed,
                        "skipped": files_skipped
                    }
                )
                return False
            else:
                self._log_check(
                    "Ingestion Rapport",
                    "pass",
                    f"Last ingestion: {files_processed} processed, {files_skipped} skipped",
                    {
                        "status": status,
                        "processed": files_processed,
                        "failed": files_failed,
                        "skipped": files_skipped
                    }
                )
                return True
        except Exception as e:
            self._log_check(
                "Ingestion Rapport",
                "warning",
                f"Cannot read ingestion rapport: {e}",
                {"path": INGESTION_RAPPORT_PATH, "error": str(e)}
            )
            return False
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks and return a summary."""
        logger.info("=" * 60)
        logger.info("🏥 RUNNING RAG HEALTH DIAGNOSTICS")
        logger.info("=" * 60)
        
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = 0
        self.results = []
        
        # Run all checks
        await self.check_llama_server()
        await self.check_database_files()
        await self.check_cache_files()
        await self.check_uploads_folder()
        self.check_state()
        self.check_memory()
        await self.check_ingestion_rapport()
        
        # Summary
        logger.info("=" * 60)
        logger.info("📊 HEALTH CHECK SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✓ Passed:   {self.checks_passed}")
        logger.info(f"✗ Failed:   {self.checks_failed}")
        logger.info(f"⚠️  Warnings: {self.warnings}")
        
        overall_status = "healthy" if self.checks_failed == 0 else "unhealthy"
        if self.warnings > 0 and self.checks_failed == 0:
            overall_status = "degraded"
        
        logger.info(f"Overall Status: {overall_status.upper()}")
        logger.info("=" * 60)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": overall_status,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "warnings": self.warnings,
            "details": self.results
        }


# Convenience function
async def run_health_check() -> Dict[str, Any]:
    """Run a complete health check of the RAG system."""
    checker = RAGHealthChecker()
    return await checker.run_all_checks()


# Quick check function for command line
async def quick_check():
    """Quick health check - just the essentials."""
    logger.info("🏥 Running quick RAG health check...")
    
    checker = RAGHealthChecker()
    
    # Essential checks only
    await checker.check_llama_server()
    checker.check_state()
    
    if checker.checks_failed == 0:
        logger.info("✓ RAG system is operational")
        return True
    else:
        logger.error(f"✗ RAG system has issues ({checker.checks_failed} critical checks failed)")
        return False


if __name__ == "__main__":
    # Run from command line
    async def main():
        result = await run_health_check()
        
        # Optionally save to file
        output_file = "rag_health_report.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n📄 Detailed report saved to: {output_file}")
    
    asyncio.run(main())
