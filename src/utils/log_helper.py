"""Logging configuration and helper utilities.

This module provides a centralized logging configuration that:
- Uses UTC timestamps with 'Z' suffix
- Respects LOG_LEVEL environment variable (default: INFO)
- Is idempotent (safe to call setup_logging() multiple times)
- Provides consistent formatting across all modules
- Includes decorators for method entry/exit logging

Usage:
    from jira.utils.log_helper import setup_logging, log_method_calls, log_async_method_calls
    import logging
    
    # Setup logging (usually done once at application startup)
    setup_logging()
    
    # Get logger for your module
    logger = logging.getLogger(__name__)
    
    # Use the logger
    logger.info("This will be logged with UTC timestamp")
    logger.info("This will only appear if LOG_LEVEL=info")
    
    # Decorate functions to log entry/exit
    @log_method_calls
    def my_function(arg1, arg2):
        return "result"
    
    @log_async_method_calls
    async def my_async_function(arg1, arg2):
        return "result"

Environment Variables:
    LOG_LEVEL: Controls logging verbosity (info, INFO, WARNING, ERROR)
               Defaults to INFO if not set
               Set to info to see method entry/exit logs
"""

import logging
import os
import time
from functools import wraps

_DEFAULT_FMT = "%(levelname)s %(asctime)sZ [%(name)s] %(message)s"


class _UTCFormatter(logging.Formatter):
    """Force UTC timestamps with trailing 'Z'."""

    converter = time.gmtime


def setup_logging():
    """Idempotent root logger setup.

    Respects LOG_LEVEL environment variable (default: INFO).

    Returns:
        Configured root logger.
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_UTCFormatter(_DEFAULT_FMT))
        root.addHandler(handler)

    root.setLevel(level)
    return root


def log_method_calls(func):
    """Decorator to log method entry and exit with arguments.
    
    Usage:
        @log_method_calls
        def my_function(arg1, arg2):
            return "result"
    
    This will log:
        - Method entry with arguments
        - Method exit with result (or exception)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        func_name = func.__qualname__ if hasattr(func, '__qualname__') else func.__name__
        
        # Log entry
        logger.info(f"Entry :  {func_name}")
        # if args and len(args) > 1:  # Skip 'self' or 'cls'
        #     logger.info(f"  Args: {args[1:]}")
        # if kwargs:
        #     logger.info(f"  Kwargs: {kwargs}")
        
        try:
            result = func(*args, **kwargs)
            logger.info(f"Exit : {func_name}")
            return result
        except Exception as e:
            logger.error(f"Exception : {func_name}: {e}")
            raise
    
    return wrapper


def log_async_method_calls(func):
    """Decorator to log async method entry and exit with arguments.
    
    Usage:
        @log_async_method_calls
        async def my_async_function(arg1, arg2):
            return "result"
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        func_name = func.__qualname__ if hasattr(func, '__qualname__') else func.__name__
        
        # Log entry
        logger.info(f"Entry :  {func_name} (async)")
        # if args and len(args) > 1:  # Skip 'self' or 'cls'
        #     logger.info(f"  Args: {args[1:]}")
        # if kwargs:
        #     logger.info(f"  Kwargs: {kwargs}")
        
        try:
            result = await func(*args, **kwargs)
            logger.info(f"Exit : {func_name} (async)")
            return result
        except Exception as e:
            logger.error(f"Exception : {func_name} (async): {e}")
            raise
    
    return wrapper
