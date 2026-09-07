# O2 PromQL 指标查询速查（资料库参考件 03）

指标用 OTLP gauge 写入，**metric 名即 O2 流名**（都带 `ec_`）。PromQL 里直接写 family 名即可；
按 label 过滤定位到具体服务/组件/节点。值多为“瞬时/比例/延迟”，不是累计计数，直接读原值最直观。

## 三个“先知道”
1. **灌完数据等 1~3 分钟**索引追上再查最稳；窄窗口偶发空 → 放大时间窗刷新。
2. 时间单位：PromQL 查询的起止时间**用秒**（O2 日志 SQL 是微秒，别混）。
3. 指标按“服务 HTTP / 中间件 / 节点 / 业务 / RUM”五组，见下表。

## Metric 族 + 标签字典（全部 `ec_` 前缀）

### 服务 HTTP（跳过网关；label: service / host / region）
| family | 含义 | 例 |
|---|---|---|
| `ec_http_request_rate` | 每秒请求数 | `{service="ec-order"}` |
| `ec_http_error_rate` | 错误率 % | `{service="ec-order"}` |
| `ec_http_p99_ms` | P99 延迟 ms | `{service="ec-product"}` |

> 服务名只能是：ec-order / ec-payment / ec-product / ec-search / ec-cart / ec-inventory / ec-user / ec-web（网关不出这三支）。

### 中间件（label: component / host）
| family | component 可取 | 含义 |
|---|---|---|
| `ec_db_conn_pool_active` | `ec-order-db` `ec-shop-db` | 当前活动连接（对比 pool_max） |
| `ec_db_conn_pool_waiting` | 同上 | 等待连接的请求数（**故障直读**） |
| `ec_db_conn_pool_max` | 同上 | 池上限 |
| `ec_mysql_qps` | 同上 | 库 QPS（击穿时冲高） |
| `ec_mysql_slow_ratio` | 同上 | 慢查询占比 |
| `ec_redis_hit_ratio` | redis=`ec-redis-cache` | 命中率 0..1（乘 100 = %） |
| `ec_redis_memory_bytes` | redis=`ec-redis-cache` | 占用字节 |
| `ec_kafka_consumer_lag` | consumer=`payment-callback` | 消费积压（**F3 直读**） |

### 节点（label: node）
`ec_node_cpu_pct` · `ec_node_mem_pct` · `ec_node_disk_pct` — node 可取 `ec-node-1/2/3`（**F5 看 disk**）。

### 业务
`ec_order_placed_rate`{service="ec-order"} 下单速率 · `ec_payment_confirm_pct`{channel="callback"} 支付回调确认占比。

### 前端体验（RUM，label: page）
`ec_rum_pv_rate` · `ec_rum_lcp_ms` · `ec_rum_js_error_rate` — page 目前 `/`。

## 按故障看哪支指标（诊断地图）
| 故障 | 直接看 | 佐证 |
|---|---|---|
| F1 | `ec_db_conn_pool_active{component="ec-order-db"}` 顶到 max、`ec_db_conn_pool_waiting`>0 | `ec_http_p99_ms{service="ec-order"}` 飚、`ec_http_error_rate` 升 |
| F2 | `ec_redis_hit_ratio` 从 ~95% 跌到 ~45% | `ec_mysql_qps{component="ec-shop-db"}` 冲高、`ec_http_p99_ms{service="ec-product"}` 升 |
| F3 | `ec_kafka_consumer_lag` 单调爬升 | `ec_payment_confirm_pct` 下滑、`ec_http_request_rate{service="ec-payment"}` |
| F4 | `ec_http_error_rate{service="ec-product"}` 抬（后端被打满的那个服务） | `ec_http_p99_ms{service="ec-product"}` 升；429/502 明细去 `ec_access_logs`（网关本身不出 HTTP 指标） |
| F5 | `ec_node_disk_pct{node="ec-node-2"}` 逼近 100 | `ec_node_cpu_pct`/`ec_node_mem_pct` 佐证 |
| F6 | `ec_rum_js_error_rate` 突升 | `ec_rum_lcp_ms` 抬、配合 `ec_rum_error` 日志流看 error_type/route |

## 常用查询模板
```promql
ec_db_conn_pool_active{component="ec-order-db"}         # 连接池活动连接
ec_db_conn_pool_waiting{component="ec-order-db"}        # 等待数
ec_redis_hit_ratio * 100                                # 命中率(%)
ec_mysql_qps{component="ec-shop-db"}                    # 击穿时库 QPS
ec_kafka_consumer_lag                                   # 消费积压
ec_node_disk_pct{node="ec-node-2"}                      # 磁盘占用
ec_http_error_rate{service="ec-order"}                  # 某服务错误率
ec_http_p99_ms{service="ec-product"}                    # 某服务 P99
ec_rum_js_error_rate                                    # 前端 JS 报错率
```

## 结论
**故障→指标**：连接池/等待看 F1、命中率+库QPS 看 F2、Kafka lag 看 F3、错误率/P99 看 F4、节点磁盘看 F5、RUM 报错率看 F6。
**名没把握就先 StreamSchema/读 `ec_` 指标流再写 PromQL**，别硬猜 label。
