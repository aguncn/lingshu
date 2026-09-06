# 种子包：应用初始化落库的幂等数据。
# P9 十二场景域种子在 backend/seed/scenarios.py（create_app 建表后调用 run_scenario_seed）。
# 后续其他提案需要「跑一次/幂等」的数据也放这里，避免散落在迁移 SQL 或业务 service。
