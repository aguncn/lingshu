# 领域错误：service 层抛、API 层统一转 HTTP 状态码。
# 用异常让校验/资源查找逻辑不散在路由里，路由只负责参数取用与序列化。


class AppError(Exception):
    """业务错误基类，携带 HTTP 状态码与中文提示。"""

    status = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    """请求参数非法（缺必填 / 取值不在白名单）。"""

    status = 400


class NotFoundError(AppError):
    """目标资源不存在。"""

    status = 404
