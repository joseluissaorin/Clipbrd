import asyncio
import threading
import logging
from typing import Optional, Any
from concurrent.futures import Future
import atexit
import weakref

logger = logging.getLogger(__name__)

class AsyncEventLoopManager:
    """
    Singleton manager for handling async operations in a dedicated thread.
    Ensures proper lifecycle management of the event loop and provides
    thread-safe methods to schedule coroutines.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        # Skip initialization if already initialized
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._shutdown = threading.Event()
        
        # Start the event loop in a dedicated thread
        self._start_loop()
        
        # Register cleanup on interpreter shutdown
        atexit.register(self.shutdown)
        
        # Keep track of pending tasks
        self._pending_tasks = weakref.WeakSet()
        
        logger.debug("AsyncEventLoopManager initialized")
    
    def _run_event_loop(self):
        """
        Thread target that sets up and runs the event loop.
        """
        try:
            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Signal that the loop is ready
            self._running.set()
            
            logger.debug("Event loop started in dedicated thread")
            
            # Run until shutdown is requested
            while not self._shutdown.is_set():
                try:
                    self.loop.run_forever()
                except Exception as e:
                    logger.error(f"Error in event loop: {e}")
                    if not self._shutdown.is_set():
                        logger.info("Attempting to restart event loop")
                        continue
                    break
                    
        finally:
            try:
                # Cancel all pending tasks
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                    
                # Wait for tasks to complete with timeout
                if pending:
                    self.loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                    
                # Close the event loop
                self.loop.close()
                logger.debug("Event loop closed")
                
            except Exception as e:
                logger.error(f"Error during event loop cleanup: {e}")
            
            finally:
                self.loop = None
                self._running.clear()
    
    def _start_loop(self):
        """
        Starts the event loop in a dedicated thread if not already running.
        """
        if self._running.is_set():
            return
            
        self.thread = threading.Thread(
            target=self._run_event_loop,
            name="AsyncEventLoop",
            daemon=True
        )
        self.thread.start()
        
        # Wait for loop to be ready
        self._running.wait()
    
    def run_coroutine(self, coro: Any) -> Future:
        """
        Schedules a coroutine to run in the event loop thread.
        Returns a Future that will contain the result.
        
        Args:
            coro: The coroutine to run
            
        Returns:
            Future object that will contain the result
            
        Raises:
            RuntimeError: If the event loop is not running
        """
        if not self._running.is_set() or not self.loop:
            raise RuntimeError("Event loop is not running")
            
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        self._pending_tasks.add(future)
        return future
    
    def shutdown(self):
        """
        Initiates a clean shutdown of the event loop.
        Cancels all pending tasks and stops the event loop.
        """
        if not self._running.is_set():
            return
            
        logger.debug("Initiating AsyncEventLoopManager shutdown")
        
        # Signal shutdown
        self._shutdown.set()
        
        if self.loop:
            # Wake up the event loop
            self.loop.call_soon_threadsafe(self.loop.stop)
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
            if self.thread.is_alive():
                logger.warning("Event loop thread did not terminate in time")
                
        logger.debug("AsyncEventLoopManager shutdown complete")
    
    @classmethod
    def get_instance(cls) -> 'AsyncEventLoopManager':
        """
        Returns the singleton instance of the AsyncEventLoopManager.
        Creates it if it doesn't exist.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance 