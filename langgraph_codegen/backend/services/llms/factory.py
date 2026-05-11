from services.llms.providers.anthropic import AnthropicAPILLM
from services.llms.providers.openai import OpenAIAPILLM
from services.llms.local.llama_cpp import LlamaCppLLM
from services.llms.local.lm_studio import LMStudioLLM
from services.llms.providers.hugging_face import HuggingFaceAPILLM
from typing import Callable, Dict
from crud.llms import get_api_key_by_alias, get_remote_llm_by_alias, get_local_llm_by_alias
from sqlalchemy.orm import Session


REMOTE_PROVIDERS: Dict[str, Callable[[str, str | None], object]] = {
    "anthropic": lambda key, base_url=None: AnthropicAPILLM(api_key=key, base_url=base_url),
    "openai": lambda key, base_url=None: OpenAIAPILLM(api_key=key, base_url=base_url),
    "huggingface": lambda key, base_url=None: HuggingFaceAPILLM(api_key=key, base_url=base_url),
}

LOCAL_PROVIDERS: Dict[str, Callable[[str], object]] = {
    "llama-cpp": lambda path: LlamaCppLLM(path),
    "lm-studio": lambda path: LMStudioLLM(),
}


def get_llm_client_by_alias(alias: str, db: Session, is_remote: bool):

    try:
        if is_remote:
            llm = get_remote_llm_by_alias(db, alias=alias)
            api_key = get_api_key_by_alias(db, alias=alias)
            if llm.provider not in REMOTE_PROVIDERS:
                raise ValueError(f"Unknown Remote LLM provider: {llm.provider}")

            return REMOTE_PROVIDERS[llm.provider](api_key, llm.base_url)

        else:
            llm = get_local_llm_by_alias(db, alias=alias)

            if llm.provider not in LOCAL_PROVIDERS:
                raise ValueError(f"Unknown Local LLM provider: {llm.provider}")

            return LOCAL_PROVIDERS[llm.provider](llm.path)
    except Exception as e:
        print(f"LLM client instantiation error: {e}")
        raise



def get_llm_client_by_provider(provider: str, **kwargs):
    api_key = kwargs.get("api_key")
    base_url = kwargs.get("base_url")

    if provider == "anthropic":
        return AnthropicAPILLM(api_key=api_key, base_url=base_url)
    elif provider == "openai":
        return OpenAIAPILLM(api_key=api_key, base_url=base_url)
    elif provider == "huggingface":
        return HuggingFaceAPILLM(api_key=api_key, base_url=base_url)
    elif provider == "llama-cpp":
        return LlamaCppLLM()
    elif provider == "lm-studio":
        return LMStudioLLM()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
