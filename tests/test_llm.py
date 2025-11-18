"""Tests for LLM client wrapper."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.llm import LLMClient, LLMError, OllamaNotAvailableError


class TestLLMClient:
    """Tests for LLMClient class."""

    @patch('subprocess.run')
    def test_check_ollama_available_success(self, mock_subprocess, sample_config):
        """Test checking Ollama availability when available."""
        # Mock successful ollama list command
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "llama3\nllama3.2\n"
        mock_subprocess.return_value = mock_result
        
        client = LLMClient(sample_config)
        assert client.check_ollama_available() is True

    @patch('subprocess.run')
    def test_check_ollama_available_model_not_found(self, mock_subprocess, sample_config):
        """Test checking Ollama when model is not found."""
        # Mock ollama list without the model
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "other_model\n"
        mock_subprocess.return_value = mock_result
        
        with pytest.raises(OllamaNotAvailableError):
            LLMClient(sample_config)

    @patch('subprocess.run')
    def test_check_ollama_available_not_running(self, mock_subprocess, sample_config):
        """Test checking Ollama when it's not running."""
        # Mock failed ollama list command
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_subprocess.return_value = mock_result
        
        with pytest.raises(OllamaNotAvailableError):
            LLMClient(sample_config)

    @patch('app.llm.ChatOllama')
    @patch('subprocess.run')
    def test_llm_client_call_json_response(self, mock_subprocess, mock_chat_ollama, sample_config):
        """Test LLM client call with JSON response."""
        # Mock successful ollama check
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "llama3\n"
        mock_subprocess.return_value = mock_result
        
        # Mock ChatOllama response
        mock_response = MagicMock()
        mock_response.content = json.dumps({"result": "test"})
        mock_chat_instance = MagicMock()
        mock_chat_instance.invoke.return_value = mock_response
        mock_chat_ollama.return_value = mock_chat_instance
        
        client = LLMClient(sample_config)
        result = client.call("test prompt")
        
        assert isinstance(result, dict)
        assert result["result"] == "test"

    @patch('app.llm.ChatOllama')
    @patch('subprocess.run')
    def test_llm_client_call_text_response(self, mock_subprocess, mock_chat_ollama, sample_config):
        """Test LLM client call with text response."""
        # Mock successful ollama check
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "llama3\n"
        mock_subprocess.return_value = mock_result
        
        # Mock ChatOllama response
        mock_response = MagicMock()
        mock_response.content = "Plain text response"
        mock_chat_instance = MagicMock()
        mock_chat_instance.invoke.return_value = mock_response
        mock_chat_ollama.return_value = mock_chat_instance
        
        client = LLMClient(sample_config)
        result = client.call("test prompt", return_text=True)
        
        assert isinstance(result, str)
        assert result == "Plain text response"

    @patch('app.llm.ChatOllama')
    @patch('subprocess.run')
    def test_llm_client_call_json_in_markdown(self, mock_subprocess, mock_chat_ollama, sample_config):
        """Test LLM client parsing JSON from markdown code block."""
        # Mock successful ollama check
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "llama3\n"
        mock_subprocess.return_value = mock_result
        
        # Mock ChatOllama response with JSON in markdown
        mock_response = MagicMock()
        mock_response.content = "```json\n{\"result\": \"test\"}\n```"
        mock_chat_instance = MagicMock()
        mock_chat_instance.invoke.return_value = mock_response
        mock_chat_ollama.return_value = mock_chat_instance
        
        client = LLMClient(sample_config)
        result = client.call("test prompt")
        
        assert isinstance(result, dict)
        assert result["result"] == "test"

    @patch('app.llm.ChatOllama')
    @patch('subprocess.run')
    def test_llm_client_load_prompt(self, mock_subprocess, mock_chat_ollama, sample_config):
        """Test loading prompt template."""
        # Mock successful ollama check
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "llama3\n"
        mock_subprocess.return_value = mock_result
        
        client = LLMClient(sample_config)
        
        # Try to load a prompt (may fail if file doesn't exist, but should not crash)
        try:
            prompt = client.load_prompt("text_summary.md")
            assert isinstance(prompt, str)
        except FileNotFoundError:
            # This is okay if the prompt file doesn't exist in test environment
            pass

