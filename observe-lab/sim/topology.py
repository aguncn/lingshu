"""电商·在线交易模拟拓扑：服务 / 中间件 / 主机 / 命名空间。

所有名字统一 ec_ / ec- 前缀，与 legacy(fin/tel) 隔离。这里只定义静态结构，
动态数值曲线见 rng.py，故障叠加见 incidents.py。
"""
from __future__ import annotations

# 区域与节点
REGIONS = ["cn-north-1", "cn-east-2"]
K8S_NAMESPACE = "ecommerce-prod"

# K8s 工作节点（跑微服务 Pod；ec-system logs 的主机来源）
NODES = [
    "ec-node-1", "ec-node-2", "ec-node-3",
]

# 微服务实例 → 运行节点（label job 用它表达副本）
SERVICE_HOSTS = {
    "ec-gateway": ["ec-node-1"],          # Kong/nginx 入口
    "ec-order": ["ec-node-1", "ec-node-2"],
    "ec-payment": ["ec-node-2"],
    "ec-inventory": ["ec-node-2", "ec-node-3"],
    "ec-product": ["ec-node-1", "ec-node-3"],
    "ec-cart": ["ec-node-3"],
    "ec-search": ["ec-node-2"],
    "ec-user": ["ec-node-1"],
    "ec-web": ["ec-node-1"],              # 前端静态/BFF 宿主（RUM 页面对应站点）
}

# 中间件主机（system logs 也引用这些）
MYSQL_HOSTS = {
    "ec-order-db": "ec-db-mysql-1",       # 订单库主（F1 故障宿主）
    "ec-order-db-ro": "ec-db-mysql-2",    # 只读副本
    "ec-shop-db": "ec-db-mysql-1",
}
REDIS_HOSTS = {
    "ec-redis-cache": "ec-db-redis-1",    # F2 热点缓存
    "ec-redis-session": "ec-db-redis-2",
}
KAFKA_HOST = "ec-kafka-1"
OBJSTORE_HOST = "ec-minio-1"

# 供循环用的中间件宿主
INFRA_HOSTS = [
    "ec-db-mysql-1", "ec-db-mysql-2", "ec-db-redis-1", "ec-db-redis-2",
    "ec-kafka-1", "ec-minio-1", "ec-es-1",
]

# HTTP 服务列表（做 metrics 里 job=... 的维度 + 各自宿主）
SERVICES = sorted(SERVICE_HOSTS.keys())

# 网关暴露的对外路由（access log 与 trace 的入口路由映射）
# route -> (实际转发服务, 语义名)
GATEWAY_ROUTES = {
    "GET /api/v1/products/{id}": ("ec-product", "商品详情"),
    "GET /api/v1/products": ("ec-product", "商品列表"),
    "GET /api/v1/search": ("ec-search", "搜索"),
    "POST /api/v1/orders": ("ec-order", "下单"),
    "GET /api/v1/orders/{id}": ("ec-order", "查订单"),
    "POST /api/v1/payments/{id}/callback": ("ec-payment", "支付回调"),
    "GET /api/v1/cart": ("ec-cart", "购物车"),
    "GET /api/v1/cart/{id}/checkout": ("ec-cart", "结算"),
    "POST /api/v1/users/{id}/login": ("ec-user", "登录"),
    "GET /api/v1/inventory/{sku}": ("ec-inventory", "库存查询"),
    "GET /": ("ec-web", "首页"),
    "GET /static/{asset}": ("ec-web", "静态资源"),
}

# 访问日志 URL 池（非路由表结构的可解析 URL，模拟真实 path 多样性）
ACCESS_URL_POOL = [
    "GET /api/v1/products/38412", "GET /api/v1/products/90321",
    "GET /api/v1/products?category=digital&page=2", "GET /api/v1/search?q=%E7%94%B5%E8%84%91&page=1",
    "POST /api/v1/orders", "GET /api/v1/orders/20260714093821-88231",
    "POST /api/v1/payments/88231/callback", "GET /api/v1/cart",
    "POST /api/v1/users/88231/login", "GET /api/v1/inventory/SKU-778",
    "GET /", "GET /static/app.2d4f.js", "GET /static/app.1ab9.css",
    "GET /api/v1/products/12845/reviews", "GET /api/v1/users/33812/orders",
]

# 购物相关统计口径（业务 metrics 里用）——参考系
ORDER_STATUS = ["created", "paid", "confirmed", "shipped", "delivered", "refunded"]
