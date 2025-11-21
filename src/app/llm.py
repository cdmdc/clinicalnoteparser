"""LLM wrapper for Ollama integration with retry logic and JSON parsing."""

import json
import logging
import os
import platform
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from langchain_ollama import ChatOllama
except ImportError:
    # Fallback to deprecated import for backward compatibility
    from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Config, get_config

logger = logging.getLogger(__name__)


def _detect_apple_silicon() -> bool:
    """Detect if running on Apple Silicon (M1/M2/M3/etc.).
    
    This function checks the actual hardware, not just what Python reports,
    since Python may run under Rosetta 2 (x86_64 emulation) on Apple Silicon.
    
    Returns:
        bool: True if running on Apple Silicon, False otherwise
    """
    try:
        # Check if we're on macOS
        if platform.system() != "Darwin":
            return False
        
        # First check: processor architecture (works if Python is native arm64)
        machine = platform.machine()
        if machine == "arm64":
            return True
        
        # Second check: Check actual CPU brand string via sysctl
        # This works even if Python is running under Rosetta 2
        try:
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                cpu_brand = result.stdout.strip().lower()
                # Apple Silicon CPUs contain "Apple" in the brand string
                if "apple" in cpu_brand:
                    return True
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        
        # Third check: Check processor name (fallback)
        processor = platform.processor()
        if processor and ("arm" in processor.lower() or "apple" in processor.lower()):
            return True
        
        return False
    except Exception:
        return False


def _configure_mps_for_ollama() -> bool:
    """Configure MPS (Metal Performance Shaders) for Ollama on Apple Silicon.
    
    Sets environment variables that Ollama will use for GPU acceleration.
    Note: These need to be set before Ollama service starts, but we set them
    here anyway in case Ollama is started from this process or restarted.
    
    Returns:
        bool: True if MPS is available and configured, False otherwise
    """
    if not _detect_apple_silicon():
        return False
    
    # Set environment variables for Ollama to use MPS
    # OLLAMA_GPU_LAYERS=-1 tells Ollama to use all available GPU layers
    os.environ.setdefault("OLLAMA_GPU_LAYERS", "-1")
    
    # PYTORCH_ENABLE_MPS_FALLBACK=1 enables MPS fallback (if PyTorch is used)
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    
    # Check if MPS is actually available (requires PyTorch)
    try:
        import torch
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            logger.info("✓ MPS (Metal Performance Shaders) detected and configured for Ollama GPU acceleration")
            return True
        else:
            logger.debug("Apple Silicon detected but MPS not available (PyTorch MPS not available)")
            return False
    except ImportError:
        # PyTorch not installed, but we can still set the env vars
        # Ollama will use its own MPS detection
        logger.info("✓ Apple Silicon detected - MPS environment variables set for Ollama")
        logger.debug("Note: Install PyTorch for MPS availability verification")
        return True


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class OllamaNotAvailableError(LLMError):
    """Raised when Ollama is not available or model doesn't exist."""

    pass


class LLMClient:
    """Wrapper for ChatOllama with retry logic, JSON parsing, and logging."""

    def __init__(self, config: Optional[Config] = None):
        """Initialize LLM client.

        Args:
            config: Configuration instance (uses global config if None)

        Raises:
            OllamaNotAvailableError: If Ollama is not available or model doesn't exist
        """
        if config is None:
            config = get_config()

        self.config = config
        self.model_name = config.model_name
        self.temperature = config.temperature
        self.max_retries = config.max_retries

        # Check Ollama availability and model existence
        self._check_ollama_availability()

        # Configure MPS for Apple Silicon if available
        mps_configured = _configure_mps_for_ollama()
        
        # Initialize ChatOllama
        # Ollama automatically detects and uses MPS/GPU if available and configured
        self.client = ChatOllama(
            model=self.model_name,
            temperature=self.temperature,
            base_url=config.ollama_base_url,
        )
        
        if mps_configured:
            logger.info("LLM client configured for GPU acceleration (MPS)")

        logger.info(f"Initialized LLM client with model: {self.model_name}, temperature: {self.temperature}")

    def _check_ollama_availability(self) -> None:
        """Check if Ollama is available and model exists.

        Raises:
            OllamaNotAvailableError: If Ollama is not available or model doesn't exist
        """
        try:
            # Try to import and check Ollama
            import subprocess

            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise OllamaNotAvailableError(
                    "Ollama is not available. Please ensure Ollama is installed and running. "
                    "Visit https://ollama.ai for installation instructions."
                )

            # Check if model exists
            if self.model_name not in result.stdout:
                raise OllamaNotAvailableError(
                    f"Model '{self.model_name}' not found. Available models: {result.stdout}. "
                    f"Install it with: ollama pull {self.model_name}"
                )

        except FileNotFoundError:
            raise OllamaNotAvailableError(
                "Ollama command not found. Please install Ollama from https://ollama.ai"
            )
        except subprocess.TimeoutExpired:
            raise OllamaNotAvailableError("Ollama is not responding. Please ensure Ollama is running.")
        except Exception as e:
            if isinstance(e, OllamaNotAvailableError):
                raise
            raise OllamaNotAvailableError(f"Error checking Ollama availability: {e}") from e
    
    def check_ollama_available(self) -> bool:
        """Check if Ollama is available and model exists (non-raising version).
        
        Returns:
            bool: True if Ollama is available and model exists, False otherwise
        """
        try:
            self._check_ollama_availability()
            return True
        except OllamaNotAvailableError:
            return False

    def load_prompt(self, prompt_name: str) -> str:
        """Load a prompt template from the prompts directory.

        Args:
            prompt_name: Name of the prompt file (e.g., "summary_extraction.md")

        Returns:
            str: Prompt template content

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        prompts_dir = Path(__file__).parent.parent.parent / "prompts"
        prompt_path = prompts_dir / prompt_name

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        return prompt_path.read_text(encoding="utf-8")

    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from text, handling markdown code blocks.

        Args:
            text: Text that may contain JSON

        Returns:
            Optional[Dict[str, Any]]: Parsed JSON dict, or None if extraction fails
        """
        # Try to find JSON in markdown code blocks
        json_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(json_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object directly
        json_pattern = r"\{.*\}"
        match = re.search(json_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Try parsing entire text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def call(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        logger_instance: Optional[logging.Logger] = None,
        return_text: bool = False,
    ) -> Dict[str, Any] | str:
        """Call LLM with retry logic and JSON parsing.

        Args:
            prompt: User prompt text
            system_message: Optional system message
            logger_instance: Optional logger instance for detailed logging
            return_text: If True, return plain text instead of parsing JSON

        Returns:
            Dict[str, Any] | str: Parsed JSON response or plain text

        Raises:
            LLMError: If all retries fail or JSON parsing fails (when return_text=False)
        """
        log = logger_instance if logger_instance else logger

        # Log before call
        log.info(f"Calling LLM (model: {self.model_name}, temperature: {self.temperature})")
        log.debug(f"Prompt preview: {prompt[:200]}...")
        if system_message:
            log.debug(f"System message preview: {system_message[:200]}...")

        messages = []
        if system_message:
            messages.append(SystemMessage(content=system_message))
        messages.append(HumanMessage(content=prompt))

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                start_time = time.time()

                # Call LLM
                response = self.client.invoke(messages)
                response_text = response.content if hasattr(response, "content") else str(response)

                elapsed_time = time.time() - start_time

                log.debug(f"LLM response (attempt {attempt}): {response_text[:500]}...")

                # If return_text is True, return plain text
                if return_text:
                    log.info(f"LLM call succeeded (attempt {attempt}, {elapsed_time:.2f}s)")
                    log.debug(f"Response text preview: {response_text[:500]}...")
                    return response_text

                # Try to parse JSON
                parsed_json = self._extract_json_from_text(response_text)

                if parsed_json is None:
                    raise ValueError(f"Failed to parse JSON from response: {response_text[:500]}")

                # Log success
                log.info(f"LLM call succeeded (attempt {attempt}, {elapsed_time:.2f}s)")
                log.debug(f"Parsed JSON: {json.dumps(parsed_json, indent=2)[:500]}...")

                return parsed_json

            except Exception as e:
                last_error = e
                log.warning(f"LLM call failed (attempt {attempt}/{self.max_retries}): {e}")

                if attempt < self.max_retries:
                    # Exponential backoff
                    wait_time = 2 ** (attempt - 1)
                    log.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    log.error(f"All {self.max_retries} attempts failed")

        # All retries failed
        raise LLMError(f"LLM call failed after {self.max_retries} attempts: {last_error}") from last_error

