"""Synthetic route metadata for offline runtime tests; never provider evidence."""


def deepinfra_metadata():
    return {"data": {"id": "deepseek/deepseek-v3.2", "endpoints": [{
        "tag": "deepinfra/fp4", "provider_name": "DeepInfra",
        "model_id": "deepseek/deepseek-v3.2", "name": "DeepInfra | deepseek/deepseek-v3.2-20251201",
        "quantization": "fp4", "status": 0, "context_length": 163840,
        "max_completion_tokens": 14000,
        "supported_parameters": ["reasoning", "max_tokens", "temperature", "top_p", "top_k", "min_p",
                                 "seed", "presence_penalty", "repetition_penalty", "tools", "tool_choice"],
        "supports_tool_choice": {"auto": True},
        "pricing": {"prompt": "0.00000026", "completion": "0.00000038"},
    }]}}
