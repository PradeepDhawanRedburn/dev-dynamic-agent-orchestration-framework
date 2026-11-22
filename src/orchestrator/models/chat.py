"""Build a chat model from a catalogue entry.

Everything about the call comes from the entry: the deployment, which API to use, the API version
and the reasoning effort. The endpoint and key are read from the environment when the model is
built and are never stored in a settings object, a state or a log line.

Verified against langchain-azure-ai 1.2.3 and langchain-openai 1.8.5 (WP-03, 2026-11):
`AzureAIOpenAIApiChatModel` subclasses `ChatOpenAI`; `reasoning_effort` becomes `reasoning.effort`
on the Responses API; `max_tokens` becomes the output cap on both APIs. Retries are off here
(`max_retries=0`): retry is the job of `ModelRetryMiddleware`, in one place, so a call is not
retried twice."""

import os

from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from langchain_core.language_models import BaseChatModel

from orchestrator.models.catalogue import ModelEntry

ENDPOINT_VARIABLE = "AZURE_OPENAI_ENDPOINT"
KEY_VARIABLE = "AZURE_OPENAI_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 120.0


class FoundryNotConfigured(RuntimeError):
    """The endpoint or key is not in the environment."""


def foundry_is_configured() -> bool:
    return bool(os.environ.get(ENDPOINT_VARIABLE) and os.environ.get(KEY_VARIABLE))


def build_chat_model(
    entry: ModelEntry,
    *,
    max_output_tokens: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> BaseChatModel:
    endpoint = os.environ.get(ENDPOINT_VARIABLE)
    key = os.environ.get(KEY_VARIABLE)
    if not endpoint or not key:
        raise FoundryNotConfigured(f"{ENDPOINT_VARIABLE} and {KEY_VARIABLE} must be set")
    chat: BaseChatModel = AzureAIOpenAIApiChatModel(
        endpoint=endpoint.rstrip("/") + "/openai/v1",
        credential=key,
        model=entry.deployment,
        api_version=entry.api_version,
        use_responses_api=entry.api == "responses",
        reasoning_effort=entry.reasoning_effort,
        max_tokens=max_output_tokens,
        max_retries=0,
    )
    return chat
