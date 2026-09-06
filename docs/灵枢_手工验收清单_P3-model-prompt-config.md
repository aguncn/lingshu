# 灵枢 P3 model-prompt-config 手工验收清单

> 范围：模型供应商（MD-04）、任务绑模型（MD-01）、提示词库（MD-03）三组 REST 契约。
> 对应 OpenSpec change：`model-prompt-config`（已 verify 通过，本文用于开发机手工复验）。
> 命令面向 **Windows cmd**，用 `curl.exe`（避开 PowerShell 的 `curl`→`Invoke-WebRequest` 别名）。
> JSON 里的内层双引号统一写成 `\"`（cmd/curl.exe 的转义，已实测可行）；若嫌转义烦，可改为先落 `body.json` 再 `-d @body.json`。

## 0. 前置条件

```cmd
:: 后端已在跑，健康检查应返回 200
curl.exe http://127.0.0.1:5000/api/health
:: {"ok":true,"ts":"..."}
```

绑模型组需要一个「任务」，先建测试空间与任务（P2 接口），记下返回的 space id / task id，下文用 `<sid>`/`<tid>` 代指：

```cmd
curl.exe -s -X POST http://127.0.0.1:5000/api/spaces -H "Content-Type: application/json" -d "{\"name\":\"验收空间\"}"
curl.exe -s -X POST http://127.0.0.1:5000/api/spaces/1/tasks -H "Content-Type: application/json" -d "{\"title\":\"验收任务\",\"task_type\":\"fault\"}"
```

---

## A 组 · 模型供应商（MD-04）

### A1 正常创建并加密落库 → 201
```cmd
curl.exe -s -X POST http://127.0.0.1:5000/api/model-providers -H "Content-Type: application/json" -d "{\"name\":\"deepseek\",\"type\":\"deepseek\",\"base_url\":\"https://api.deepseek.com/v1\",\"default_model\":\"deepseek-v4-flash\",\"api_key\":\"sk-abc12345\"}"
```
期望：HTTP 201；返回 `api_key` 为掩码 `****2345`，响应体**不含明文** `sk-abc12345`。

明文不下库校验（`api_key_enc` 应为 `gAAAAA...` 密文、且可解回）：

```cmd
uv run python -c "from backend import crypto; import sqlite3; c=sqlite3.connect('backend/data/app.db'); r=c.execute('select api_key_enc from model_providers order by id desc limit 1').fetchone(); print('cipher:',r[0]); print('decrypt==plain:', crypto.decrypt(r[0])=='sk-abc12345')"
```
期望：`cipher:` 非明文；`decrypt==plain: True`。

### A2 缺必填 / type 非法 → 400（且不产生记录）
```cmd
curl.exe -i -X POST http://127.0.0.1:5000/api/model-providers -H "Content-Type: application/json" -d "{\"type\":\"openai\",\"base_url\":\"https://x/v1\"}"            :: 缺 name
curl.exe -i -X POST http://127.0.0.1:5000/api/model-providers -H "Content-Type: application/json" -d "{\"name\":\"x\",\"type\":\"nope\",\"base_url\":\"https://x/v1\"}"      :: type 非法
curl.exe -i -X POST http://127.0.0.1:5000/api/model-providers -H "Content-Type: application/json" -d "{\"name\":\"deepseek\",\"type\":\"deepseek\",\"base_url\":\"https://api.deepseek.com/v1\"}"   :: 重名
```
期望：全部 HTTP 400，`{"message":"..."}`；`GET /api/model-providers` 里无多余记录。

### A3 本地类型可不带密钥 → 201
```cmd
curl.exe -s -X POST http://127.0.0.1:5000/api/model-providers -H "Content-Type: application/json" -d "{\"name\":\"localbox\",\"type\":\"local\",\"base_url\":\"http://127.0.0.1:11434/v1\"}"
```
期望：HTTP 201；返回对象 `api_key` 为 `null`（空掩码占位），可正常创建。

### A4 列表掩码 + 单查 404
```cmd
curl.exe http://127.0.0.1:5000/api/model-providers                  :: 200，数组内每个 api_key 都是掩码，无明文
curl.exe -i http://127.0.0.1:5000/api/model-providers/99999         :: 404 {"message":"模型供应商不存在"}
```

### A5 PATCH 部分更新：不触碰密钥 / 提供新 key 才重加密
```cmd
:: 记下 deepseek 的 id 为 <pid>；只改 base_url —— 应不动原密钥
curl.exe -s -X PATCH http://127.0.0.1:5000/api/model-providers/<pid> -H "Content-Type: application/json" -d "{\"base_url\":\"https://api.deepseek.com/v2\"}"
:: 期望 200，base_url 已更新；再跑 A1 的 DB 校验，decrypt 仍是 sk-abc12345（未被覆盖）

:: 提供新明文 key —— 应重加密
curl.exe -s -X PATCH http://127.0.0.1:5000/api/model-providers/<pid> -H "Content-Type: application/json" -d "{\"api_key\":\"sk-newkey-888\"}"
:: 期望 200，返回掩码 ****-888；DB decrypt 应为 sk-newkey-888
curl.exe -i -X PATCH http://127.0.0.1:5000/api/model-providers/99999 -H "Content-Type: application/json" -d "{\"base_url\":\"https://x\"}"   :: 404
```

### A6 DELETE：未引用 200 / 被引用 400
```cmd
:: 先删 A3 的 localbox（未被绑定）→ 200，随后单查 404
curl.exe -s -X DELETE http://127.0.0.1:5000/api/model-providers/<localbox_id>   :: {"ok":true}
curl.exe -i http://127.0.0.1:5000/api/model-providers/<localbox_id>             :: 404

:: deepseek 已被 B2 绑定后删 → 400 拒绝（先做完 B 组再回来验这句）
curl.exe -i -X DELETE http://127.0.0.1:5000/api/model-providers/<pid>           :: 400 {"message":"该供应商已被任务绑定，无法删除"}
```

---

## B 组 · 任务绑模型（MD-01）

### B1 未绑定 GET → 404
```cmd
curl.exe -i http://127.0.0.1:5000/api/tasks/<tid>/model-config
```
期望：404 `{"message":"任务尚未绑定模型配置"}`。

### B2 首次绑定 → 201，缺省取值，指针同步
```cmd
curl.exe -s -X POST http://127.0.0.1:5000/api/tasks/<tid>/model-config -H "Content-Type: application/json" -d "{\"provider_id\":<pid>, \"temperature\":0.7}"
```
期望：HTTP 201；`model_name` 缺省取供应商 `default_model`=`deepseek-v4-flash`、`timeout` 缺省 60、`temperature`=0.7。记下 config 的 `id`。

指针同步校验（`tasks.model_config_id` 应等于该 config id）：
```cmd
uv run python -c "import sqlite3; c=sqlite3.connect('backend/data/app.db'); print(c.execute('select id,model_config_id from tasks where id=?',(<tid>,)).fetchone())"
```
随后同端点 GET 应回读一致参数（`curl.exe http://127.0.0.1:5000/api/tasks/<tid>/model-config` → 200）。

### B3 重复绑定即更新（POST 替换 200 / PATCH 调参 200）
```cmd
curl.exe -s -X POST http://127.0.0.1:5000/api/tasks/<tid>/model-config -H "Content-Type: application/json" -d "{\"provider_id\":<pid>, \"temperature\":1.2}"
:: 期望 200，id 不变、temperature=1.2（仍唯一）

curl.exe -s -X PATCH http://127.0.0.1:5000/api/tasks/<tid>/model-config -H "Content-Type: application/json" -d "{\"max_tokens\":2048}"
:: 期望 200，max_tokens=2048
```

### B4 provider 不存在 / 数值越界 → 400 且不改动既有绑定
```cmd
curl.exe -i -X POST http://127.0.0.1:5000/api/tasks/<tid>/model-config -H "Content-Type: application/json" -d "{\"provider_id\":99999}"        :: 400 provider 不存在
curl.exe -i -X POST http://127.0.0.1:5000/api/tasks/<tid>/model-config -H "Content-Type: application/json" -d "{\"provider_id\":<pid>, \"temperature\":5}"     :: 400 越界（须 0-2）
curl.exe -i -X PATCH http://127.0.0.1:5000/api/tasks/<tid>/model-config -H "Content-Type: application/json" -d "{\"timeout\":-1}"               :: 400 非正整数
:: 之后 GET 应仍是 B3 的参数（未被改动）
```

### B5 任务不存在 → 404
```cmd
curl.exe -i http://127.0.0.1:5000/api/tasks/99999/model-config                                        :: 404
curl.exe -i -X POST http://127.0.0.1:5000/api/tasks/99999/model-config -H "Content-Type: application/json" -d "{\"provider_id\":<pid>}"   :: 404
```

---

## C 组 · 提示词库（MD-03）

### C1 新建提示词 → 201，version=1、parent_id 空
```cmd
curl.exe -s -X POST http://127.0.0.1:5000/api/prompts -H "Content-Type: application/json" -d "{\"name\":\"排障SOP\",\"category\":\"ops\",\"domain\":\"ts\",\"content\":\"v1 内容\"}"
```
期望：HTTP 201；`version`=1、`parent_id`=null。记下 `id` 为 `<id1>`。

### C2 同名再保存 → 新版本 parent 指向旧链头
```cmd
curl.exe -s -X POST http://127.0.0.1:5000/api/prompts -H "Content-Type: application/json" -d "{\"name\":\"排障SOP\",\"category\":\"ops\",\"content\":\"v2 内容\"}"
```
期望：HTTP 201；`version`=2、`parent_id`=`<id1>`；旧版仍可经 `GET /api/prompts/<id1>` 取回（content=v1）。

### C3 缺必填字段 → 400
```cmd
curl.exe -i -X POST http://127.0.0.1:5000/api/prompts -H "Content-Type: application/json" -d "{\"name\":\"n\",\"category\":\"c\"}"     :: 缺 content → 400
```

### C4 列表只回链头 + 过滤 + 历史 id 可读
```cmd
curl.exe "http://127.0.0.1:5000/api/prompts?name=排障SOP"                 :: 200，该 name 只出现 1 条（version=2 链头）
curl.exe "http://127.0.0.1:5000/api/prompts?category=ops"                 :: 200，只回该分类链头
curl.exe http://127.0.0.1:5000/api/prompts/<id1>                          :: 200，取回历史版 v1
curl.exe -i http://127.0.0.1:5000/api/prompts/99999                       :: 404
```

### C5 PATCH 仅链头可「再保存」；历史版 → 400
```cmd
curl.exe -s -X PATCH http://127.0.0.1:5000/api/prompts/<id2> -H "Content-Type: application/json" -d "{\"content\":\"v3 内容\"}"
:: 期望 200，生成 version=3、parent_id=<id2>，原 v2 仍在；记新 id 为 <id3>

curl.exe -i -X PATCH http://127.0.0.1:5000/api/prompts/<id1> -H "Content-Type: application/json" -d "{\"content\":\"branch\"}"   :: 对历史版再保存 → 400（防分叉）
```

### C6 删除单版本行 → 200，再单查 404
```cmd
curl.exe -s -X DELETE http://127.0.0.1:5000/api/prompts/<id3>      :: {"ok":true}
curl.exe -i http://127.0.0.1:5000/api/prompts/<id3>                 :: 404
```

### C7 预设种子（迁移自带的四类常用任务）
```cmd
curl.exe "http://127.0.0.1:5000/api/prompts?category=task-preset"
```
期望：HTTP 200，返回 **写文档 / 写代码 / 数据分析 / 排障** 四条链头，各 `version`=1、`content` 非空中文系统提示词。

---

## 收尾与常见问题

**收尾清理**（把验收造的供应商/提示词删掉；任务可选删）：
```cmd
curl.exe -s -X DELETE http://127.0.0.1:5000/api/model-providers/<pid>
curl.exe -s -X DELETE http://127.0.0.1:5000/api/prompts/<id2>
curl.exe -s -X DELETE http://127.0.0.1:5000/api/spaces/1
```

**遇到 404/500 先查这几点**（都是本仓库踩过的坑）：
1. **500 + `no such table`** → 根 `.env` 里 `LINGSHU_DATA_DIR=` 是**空值**会把库建到当前目录、ORM 却走 `instance/app.db`（两库不一致）。已修复 `backend/config.py`：空值回落默认 `backend/data`。确认 `.env` 无空的 `LINGSHU_DATA_DIR=` / 重复的 `LINGSHU_MASTER_KEY=` 占位。
2. **404 但 health 正常** → 跑着的进程是旧代码（无 P3 蓝图）；`flask run` 不热重载，**重启**后端。
3. **响应体 JSON 内引号写错** → cmd 里 JSON 内层引号必须 `\"`（见文首）；PowerShell 需 `curl.exe` + 单引号字符串或 `@file`。
4. **P3 主密钥**：根 `.env` 的 `LINGSHU_MASTER_KEY` 别删空，否则重启后旧供应商密文不可解，只能删除重建。
