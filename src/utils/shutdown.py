"""
Global shutdown flag for graceful interrupt handling in worker threads.
"""
import threading
import signal
import sys

# Global shutdown event
_shutdown_event = threading.Event()


def setup_shutdown_handler():
    """
    Set up signal handlers for graceful shutdown.
    Call this at the start of the main process.
    """
    def signal_handler(signum, frame):
        _shutdown_event.set()
        # Print a message but don't exit immediately - let workers finish current task
        if signum == signal.SIGINT:
            print("\nShutdown requested (Ctrl+C). Waiting for workers to finish current task...")
            # Allow one more Ctrl+C to force exit
            def force_exit():
                import time
                time.sleep(0.5)
                if not _shutdown_event.is_set():
                    print("Force exiting...")
                    sys.exit(130)
            threading.Thread(target=force_exit, daemon=True).start()
    
    signal.signal(signal.SIGINT, signal_handler)


def is_shutdown_requested() -> bool:
    """
    Check if shutdown has been requested.
    Workers should check this periodically and exit gracefully.
    
    Returns:
        True if shutdown is requested
    """
    return _shutdown_event.is_set()


def wait_for_shutdown(timeout: float = None) -> bool:
    """
    Wait for shutdown signal with optional timeout.
    
    Args:
        timeout: Maximum time to wait in seconds (None = wait forever)
        
    Returns:
        True if shutdown was requested, False if timeout expired
    """
    return _shutdown_event.wait(timeout=timeout)


def request_shutdown():
    """
    Programmatically request shutdown.
    """
    _shutdown_event.set()


def clear_shutdown():
    """
    Clear the shutdown flag (for testing or recovery).
    """
    _shutdown_event.clear()