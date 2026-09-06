# 模型装配服务（P8 agentscope-runtime，design D2）：ModelProvider+ModelConfig → 可运行 OpenAI 兼容模型。
# 职责只做「把绑定/密钥/参数解析成 AgentScope OpenAIChatModel」，不碰 Agent/驱动——
#   模型解析失败（未绑定/供应商缺失/无可用密钥/模型名缺失）抛可读 AppError，由端点在 SSE 首事件转为 error。
# 密钥解析顺序（spec「会话发起与任务模型解析」）：环境变量 LINGSHU_<供应商名大写>_API_KEY 优先，
#   否则 Fernet 解库内密文；皆无 → 可读错。任何出口/日志不含密钥明文（SecretStr 自带脱敏）。
import os
import re

from agentscope.model import OpenAIChatModel
from agentscope.credential import OpenAICredential
from pydantic import SecretStr

from .. import crypto
from . import model_service
from .errors import NotFoundError, ValidationError

_ENV_PREFIX = "LINGSHU_"
_ENV_SUFFIX = "_API_KEY"


def _provider_env_var(provider_name: str) -> str:
    """供应商名 → 覆盖其密钥的环境变量名：非字母数字全部压成 _ 再大写。

    例：provider.name='deepseek' → LINGSHU_DEEPSEEK_API_KEY；'ccswitch-v2' → LINGSHU_CCSWITCH_V2_API_KEY。
    """
    norm = re.sub(r"[^A-Z0-9]+", "_", (provider_name or "").upper()).strip("_")
    return f"{_ENV_PREFIX}{norm}{_ENV_SUFFIX}"


def resolve_api_key(provider) -> str:
    """解析供应商可用密钥：env 覆盖优先，其次解密库内密文；皆无 → 可读 ValidationError。

    为什么 env 优先：单人本地开发常以环境变量提供临时 key，避免每供应商都去 UI 存一份 Fernet 密文。
    """
    env_key = os.getenv(_provider_env_var(provider.name), "").strip()
    if env_key:
        return env_key
    if not provider.api_key_enc:
        raise ValidationError(
            f"供应商「{provider.name}」未配置 API 密钥——请在供应商设置中保存，"
            f"或设置环境变量 {_provider_env_var(provider.name)}"
        )
    try:
        return crypto.decrypt(provider.api_key_enc)
    except ValueError as e:
        raise ValidationError(f"供应商「{provider.name}」密钥解密失败：{e}") from None


def _resolve_config(task_id: int):
    """取绑定配置与供应商；缺任一 → 404（可读，由端点转 SSE error）。"""
    config = model_service.get_task_config(task_id)  # 无绑定/任务不存在 → NotFoundError
    provider = model_service.get_provider_or_raise(config["provider_id"])
    return config, provider


def resolve_model(task_id: int) -> tuple[OpenAIChatModel, dict]:
    """把任务的模型绑定解析成一个可调用的 OpenAI 兼容模型 + 展示标签（不含密钥）。

    返回 (model, label)：label 供 Message.model / 审计 target / build 描述使用，
    形如 {"provider_id", "provider", "model", "base_url"}——永不带 api_key 字段。
    模型名：config.model_name 优先，否则 provider.default_model；仍缺 → 可读错。
    温度/长度等生成参数在 config 有值时注入 Parameters（无值则不传，走模型默认）。
    """
    config, provider = _resolve_config(task_id)

    model_name = (config.get("model_name") or "").strip() or (provider.default_model or "").strip()
    if not model_name:
        raise ValidationError(
            f"任务绑定的模型未指明具体模型名——请为供应商「{provider.name}」配置默认模型或绑定指定 model_name"
        )

    api_key = resolve_api_key(provider)
    credential = OpenAICredential(api_key=SecretStr(api_key), base_url=provider.base_url or None)

    # Parameters 全字段可选；只注入有值的生成参数，避免覆盖模型侧默认
    params_kwargs: dict = {}
    if config.get("temperature") is not None:
        params_kwargs["temperature"] = config["temperature"]
    if config.get("max_tokens") is not None:
        params_kwargs["max_tokens"] = config["max_tokens"]

    parameters = OpenAIChatModel.Parameters(**params_kwargs) if params_kwargs else None
    model = OpenAIChatModel(
        credential=credential,
        model=model_name,
        parameters=parameters,
    )
    label = {
        "provider_id": provider.id,
        "provider": provider.name,
        "model": model_name,
        "base_url": provider.base_url,
    }
    return model, label
