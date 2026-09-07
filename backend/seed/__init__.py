# 种子包：应用初始化落库的幂等数据。
# 运维专家档案种子在 backend/seed/profiles.py（create_app 建表/迁移后调用 run_profile_seed）。
# 其他提案需要「跑一次/幂等」的数据也放这里，避免散落在迁移 SQL 或业务 service。
