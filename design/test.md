# ClawMail Skill 场景化测试框架

## 1. 背景与目标

ClawMail 的 skill（analyzer、executor、reply、task-handler）全部通过 subprocess 调用 Python 脚本，脚本内部通过 HTTP 与两个外部服务通信：

| 服务 | 地址 | 用途 |
|------|------|------|
| ClawMail REST API | `http://127.0.0.1:9999` | 读写邮件、记忆、待提取事实等 |
| LLM API | `http://127.0.0.1:18789/v1/chat/completions` | 调用大模型（OpenAI 兼容格式） |

**问题**：测试一个 skill 的完整流程需要同时启动 ClawMail 服务器、数据库、LLM 网关，难以做到：
- 固定输入 → 固定输出（LLM 每次结果不同）
- 快速迭代（启动全栈太慢）
- 覆盖边界场景（需要构造特定邮件数据）

**目标**：构建一个场景化测试框架——用 Mock HTTP 服务器替代真实服务，用 JSON 场景文件定义固定剧本（输入 + 预期响应 + 验证规则），让每个 skill 在完全可控的环境下端到端运行。

## 2. 核心思路

所有 skill 脚本已有 `--clawmail-api` 和 `--llm-api` CLI 参数可覆盖 URL（analyzer、executor、reply 均支持），因此：

```
场景 JSON ──→ 加载路由表 ──→ 启动 Mock 服务器 (port=0 自动分配)
                                   ↓
                          skill subprocess 运行
                          --clawmail-api http://127.0.0.1:{port}
                          --llm-api http://127.0.0.1:{port}/v1/chat/completions
                                   ↓
                          捕获 stdout / stderr / exit_code
                          + Mock 服务器录制的所有 POST 请求
                                   ↓
                          断言验证 ──→ 测试结果
```

ClawMail API 路径（`/emails/*`、`/memories/*`）与 LLM API 路径（`/v1/chat/completions`）不冲突，因此**单个 Mock 服务器同时模拟两个服务**。

## 3. 目录结构

```
tests/scenarios/
├── __init__.py
├── mock_server.py            # Mock HTTP 服务器
├── test_runner.py            # 场景执行器 + 断言引擎
├── conftest.py               # pytest 自动发现与参数化
├── fixtures/                 # 可复用的 mock 数据片段
│   ├── emails/
│   │   ├── meeting_confirmation.json
│   │   └── urgent_task.json
│   ├── memories/
│   │   └── empty.json        # {"memories": []}
│   └── llm_responses/
│       ├── analyzer_normal.json
│       ├── executor_insert.json
│       └── reply_text.json
└── scenarios/                # 场景定义（每个 JSON = 一个测试用例）
    ├── analyzer/
    │   └── test_normal_email.json
    ├── executor/
    │   └── test_importance_correction.json
    └── reply/
        └── test_generate_reply.json
```

## 4. 组件设计

### 4.1 Mock HTTP 服务器 (`mock_server.py`)

基于 Python 标准库 `http.server`，无第三方依赖。

**核心数据结构：**

```python
class RequestRecord:
    """一条录制的 HTTP 请求"""
    method: str          # GET / POST
    path: str            # /emails/email-001
    query: dict          # URL query params
    headers: dict
    body: Any            # JSON parsed body (POST)

class MockServer(HTTPServer):
    route_table: List[Dict]       # 路由 → 固定响应映射
    request_log: List[RequestRecord]  # 录制所有收到的请求
```

**路由匹配规则：**
- 精确匹配：`/emails/email-001` 匹配 `/emails/email-001`
- 通配符：`/emails/{id}` 匹配 `/emails/任意值`
- 按序响应：同一路径有多条路由时，按 FIFO 顺序返回（支持 analyzer 的多次 LLM 调用），用完后循环最后一条
- 未匹配路由返回 404 + 错误信息（方便调试）

**关键方法：**

```python
def load_routes(self, routes: List[Dict]) -> None:
    """从场景 JSON 加载路由表"""

def find_response(self, method: str, path: str) -> Optional[Dict]:
    """根据 method + path 查找匹配的路由，返回 {status, body}"""

def get_posts_to(self, path_prefix: str) -> List[RequestRecord]:
    """返回所有发送到指定路径前缀的 POST 请求（用于断言验证）"""

def reset(self) -> None:
    """清空路由表和请求日志"""
```

### 4.2 场景执行器 (`test_runner.py`)

```python
class ScenarioRunner:
    def __init__(self, scenario_path: str):
        """加载场景 JSON 文件"""

    def run(self) -> dict:
        """
        完整执行一个场景：
        1. 启动 MockServer（port=0，OS 自动分配端口，避免冲突）
        2. 加载场景中的 mock_routes
        3. 解析 $ref 引用（指向 fixtures/ 下的共享数据文件）
        4. 构建 subprocess 命令，注入 --clawmail-api 和 --llm-api
        5. 运行 skill 脚本，捕获 stdout / stderr / exit_code
        6. 从 MockServer.request_log 提取所有 POST 记录
        7. 执行 assertions 中定义的全部断言
        8. 返回 {passed, errors, stdout, stderr, request_log}
        """
```

**$ref 引用机制：** 场景 JSON 中的 mock response body 可以引用 fixtures 文件：

```json
{
  "method": "GET",
  "path": "/emails/email-001",
  "response": {"status": 200, "body": {"$ref": "emails/meeting_confirmation.json"}}
}
```

执行器在加载路由时自动读取 `fixtures/emails/meeting_confirmation.json` 的内容替换 `$ref`。

### 4.3 pytest 集成 (`conftest.py`)

自动发现 `scenarios/` 下所有 `.json` 文件，每个文件参数化为一个独立的 pytest 用例：

```python
@pytest.mark.parametrize("scenario_file", discover_scenarios(), ids=lambda p: p.stem)
def test_scenario(scenario_file):
    runner = ScenarioRunner(str(scenario_file))
    result = runner.run()
    if not result["passed"]:
        error_msg = "\n".join(f"  - {e}" for e in result["errors"])
        pytest.fail(f"Scenario failed:\n{error_msg}\n\nstderr:\n{result['stderr']}")
```

运行方式：

```bash
# 全部场景
pytest tests/scenarios/ -v

# 只跑 analyzer
pytest tests/scenarios/ -v -k "analyzer"

# 单个场景
pytest tests/scenarios/ -v -k "test_normal_email"
```

## 5. 场景 JSON 格式规范

### 5.1 完整结构

```json
{
  "name": "场景唯一标识名",
  "description": "场景描述",

  "skill": {
    "script": "skills/clawmail-analyzer/scripts/analyze_email.py",
    "args": ["--email-id", "email-001", "--account-id", "acct-001"],
    "timeout_seconds": 10,
    "env": {}
  },

  "mock_routes": [
    {
      "method": "GET|POST",
      "path": "/路径（支持 {param} 通配）",
      "response": {
        "status": 200,
        "body": {}
      }
    }
  ],

  "assertions": {
    "exit_code": 0,
    "stdout_not_empty": true,
    "stdout_contains": ["子串"],
    "stdout_json": {
      "required_keys": ["key1", "key2"],
      "field_checks": {"path.to.field": "expected_value"},
      "field_type_checks": {"path.to.field": "int|str|list|dict|bool|float"}
    },
    "posted_requests": [
      {
        "comment": "描述",
        "method": "POST",
        "path_prefix": "/memories/acct-001",
        "count": 1,
        "min_count": 1,
        "max_count": 3,
        "body_checks": {
          "field.path": {
            "equals": "value",
            "not_empty": true,
            "starts_with": "prefix",
            "type": "int",
            "range": [0, 100]
          }
        }
      }
    ]
  }
}
```

### 5.2 断言类型一览

| 断言 | 适用场景 | 说明 |
|------|---------|------|
| `exit_code` | 所有 skill | 进程退出码（0 = 成功） |
| `stdout_not_empty` | reply 类 skill | stdout 非空（输出了回复文本） |
| `stdout_contains` | reply 类 skill | stdout 包含指定子串 |
| `stdout_json.required_keys` | analyzer / executor | stdout JSON 必须包含的 key |
| `stdout_json.field_checks` | analyzer / executor | 字段精确匹配（支持 dot path） |
| `stdout_json.field_type_checks` | analyzer / executor | 字段类型检查 |
| `posted_requests[].count` | 所有 skill | 指定端点被 POST 的次数 |
| `posted_requests[].body_checks` | 所有 skill | POST body 中字段的断言 |

### 5.3 `body_checks` 支持的检查器

| 检查器 | 示例 | 说明 |
|--------|------|------|
| `equals` | `{"equals": "success"}` | 精确匹配 |
| `not_empty` | `{"not_empty": true}` | 非空（非 null/空字符串/空列表） |
| `starts_with` | `{"starts_with": "contact."}` | 字符串前缀 |
| `type` | `{"type": "int"}` | 类型检查 |
| `range` | `{"range": [0, 100]}` | 数值范围 |

## 6. 各 Skill 的 HTTP 调用清单

编写场景时需要为 skill 的每个 HTTP 调用提供 mock 响应。以下是各 skill 的调用清单：

### 6.1 clawmail-analyzer (`analyze_email.py`)

| 顺序 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 1 | GET | `/emails/{id}` | 获取邮件数据 |
| 2 | GET | `/memories/{account_id}` | 获取用户记忆 |
| 3 | GET | `/pending-facts/{account_id}` | 获取已有待审事实 |
| 4 | GET | `/emails/thread/{thread_id}` | 获取线程上下文（仅当邮件有 thread_id） |
| 5 | POST | `/v1/chat/completions` | LLM 调用（分析 + 事实提取） |
| 6 | POST | `/emails/{id}/ai-metadata` | 写入分析结果 |
| 7 | POST | `/memories/{account_id}` | 直写 contact.* 事实（0~N 次） |
| 8 | POST | `/pending-facts/{account_id}` | 提交待审事实 |
| 9 | POST | `/pending-facts/{account_id}/promote` | 自动晋升高置信事实 |

### 6.2 clawmail-executor (`extract_preference.py`)

| 顺序 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 1 | GET | `/emails/{id}` | 获取邮件上下文 |
| 2 | GET | `/memories/{account_id}` | 获取已有记忆 |
| 3 | POST | `/v1/chat/completions` | LLM 调用（偏好推断） |
| 4 | POST | `/memories/{account_id}` | 写入记忆（insert/update/delete，0~N 次） |

### 6.3 clawmail-reply (`generate_reply.py`)

| 顺序 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 1 | GET | `/emails/{id}` | 获取原始邮件 |
| 2 | GET | `/emails/{id}/ai-metadata` | 获取 AI 分析结果 |
| 3 | GET | `/memories/{account_id}` | 获取用户记忆 |
| 4 | GET | `/emails/thread/{thread_id}` | 获取线程上下文（可选） |
| 5 | POST | `/v1/chat/completions` | LLM 调用（生成回复） |

输出：纯文本到 stdout（不 POST 回服务器）。

### 6.4 clawmail-reply (`generate_email.py` / `polish_email.py`)

| 顺序 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 1 | GET | `/memories/{account_id}` | 获取用户记忆 |
| 2 | POST | `/v1/chat/completions` | LLM 调用 |

输出：纯文本到 stdout。

## 7. 示例场景

### 7.1 Analyzer — 正常邮件分析

```json
{
  "name": "analyzer_normal_email",
  "description": "分析一封会议确认邮件，验证 metadata 写入和 fact 提取",

  "skill": {
    "script": "skills/clawmail-analyzer/scripts/analyze_email.py",
    "args": ["--email-id", "email-001", "--account-id", "acct-001"],
    "timeout_seconds": 15
  },

  "mock_routes": [
    {
      "method": "GET",
      "path": "/emails/email-001",
      "response": {
        "status": 200,
        "body": {
          "id": "email-001",
          "account_id": "acct-001",
          "subject": "明天下午2点的会议确认",
          "from_address": {"name": "张三", "email": "colleague@company.com"},
          "to_addresses": [{"name": "Test", "email": "test@example.com"}],
          "cc_addresses": [],
          "body_text": "Hi，\n\n明天下午2点的季度总结会议你能参加吗？\n地点：会议室A\n\n张三",
          "received_at": "2026-03-01T10:00:00Z",
          "thread_id": null,
          "in_reply_to": null
        }
      }
    },
    {
      "method": "GET",
      "path": "/memories/acct-001",
      "response": {"status": 200, "body": {"memories": []}}
    },
    {
      "method": "GET",
      "path": "/pending-facts/acct-001",
      "response": {"status": 200, "body": {"facts": []}}
    },
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "response": {
        "status": 200,
        "body": {
          "choices": [{
            "message": {
              "content": "{\"summary\":{\"keywords\":[\"会议\",\"季度总结\"],\"one_line\":\"张三邀请确认明天下午2点季度总结会议\",\"brief\":\"张三邀请参加明天下午2点的季度总结会议，讨论Q1预算。地点会议室A。\"},\"action_items\":[{\"text\":\"确认参加会议\",\"deadline\":\"2026-03-02\",\"deadline_source\":\"inferred\",\"priority\":\"high\",\"category\":\"工作\",\"assignee\":\"me\",\"quote\":\"你能参加吗\"}],\"metadata\":{\"category\":[\"meeting\",\"pending_reply\"],\"sentiment\":\"neutral\",\"language\":\"zh\",\"confidence\":0.9,\"is_spam\":false,\"importance_scores\":{\"sender_score\":60,\"urgency_score\":70,\"deadline_score\":75,\"complexity_score\":30},\"suggested_reply\":\"好的，我会准时参加。\",\"reply_stances\":[\"确认参加\",\"需要改时间\",\"无法参加\"]},\"pending_facts\":[{\"fact_key\":\"contact.colleague@company.com.relationship\",\"fact_category\":\"contact\",\"fact_content\":\"同事\",\"confidence\":0.6}]}"
            },
            "finish_reason": "stop"
          }]
        }
      }
    },
    {
      "method": "POST",
      "path": "/emails/email-001/ai-metadata",
      "response": {"status": 200, "body": {"status": "ok"}}
    },
    {
      "method": "POST",
      "path": "/memories/acct-001",
      "response": {"status": 200, "body": {"status": "ok"}}
    },
    {
      "method": "POST",
      "path": "/pending-facts/acct-001",
      "response": {"status": 200, "body": {"status": "ok", "created": 0, "updated": 0}}
    },
    {
      "method": "POST",
      "path": "/pending-facts/acct-001/promote",
      "response": {"status": 200, "body": {"promoted_count": 0, "promoted": []}}
    }
  ],

  "assertions": {
    "exit_code": 0,
    "stdout_json": {
      "required_keys": ["status", "email_id"],
      "field_checks": {
        "status": "success",
        "email_id": "email-001"
      }
    },
    "posted_requests": [
      {
        "comment": "AI metadata 已写入",
        "method": "POST",
        "path_prefix": "/emails/email-001/ai-metadata",
        "count": 1
      },
      {
        "comment": "LLM 被调用 1 次",
        "method": "POST",
        "path_prefix": "/v1/chat/completions",
        "count": 1
      }
    ]
  }
}
```

### 7.2 Executor — 重要性评分修正

```json
{
  "name": "executor_importance_correction",
  "description": "用户将重要性从 30 修正为 85，验证记忆写入",

  "skill": {
    "script": "skills/clawmail-executor/scripts/extract_preference.py",
    "args": [
      "--feedback-type", "importance_score",
      "--feedback-data", "{\"original_score\": 30, \"user_score\": 85}",
      "--email-id", "email-002",
      "--account-id", "acct-001"
    ],
    "timeout_seconds": 10
  },

  "mock_routes": [
    {
      "method": "GET",
      "path": "/emails/email-002",
      "response": {
        "status": 200,
        "body": {
          "id": "email-002",
          "subject": "【紧急】客户报告需要在周五前完成",
          "from_address": {"name": "李经理", "email": "boss@company.com"},
          "to_addresses": [{"name": "Test", "email": "test@example.com"}],
          "cc_addresses": [],
          "body_text": "刚接到通知，ABC客户需要在本周五下午5点前收到季度分析报告。请优先处理。",
          "received_at": "2026-03-01T09:00:00Z"
        }
      }
    },
    {
      "method": "GET",
      "path": "/memories/acct-001",
      "response": {"status": 200, "body": {"memories": []}}
    },
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "response": {
        "status": 200,
        "body": {
          "choices": [{
            "message": {
              "content": "[{\"op\": \"insert\", \"memory_type\": \"sender_importance\", \"memory_key\": \"contact.boss@company.com.importance_bias\", \"content\": {\"direction\": \"undervalued\", \"typical_importance\": \"high\", \"note\": \"用户认为老板邮件应为高重要性\"}, \"confidence\": 0.8}]"
            }
          }]
        }
      }
    },
    {
      "method": "POST",
      "path": "/memories/acct-001",
      "response": {"status": 200, "body": {"status": "ok"}}
    }
  ],

  "assertions": {
    "exit_code": 0,
    "stdout_json": {
      "required_keys": ["status", "operations_total", "operations_applied", "feedback_type"],
      "field_checks": {
        "status": "success",
        "feedback_type": "importance_score",
        "operations_total": 1,
        "operations_applied": 1
      }
    },
    "posted_requests": [
      {
        "comment": "记忆 insert 操作",
        "method": "POST",
        "path_prefix": "/memories/acct-001",
        "min_count": 1,
        "body_checks": {
          "memory_type": {"equals": "sender_importance"}
        }
      }
    ]
  }
}
```

### 7.3 Reply — 生成回复

```json
{
  "name": "reply_generate_reply",
  "description": "为会议邮件生成确认参加的回复",

  "skill": {
    "script": "skills/clawmail-reply/scripts/generate_reply.py",
    "args": [
      "--email-id", "email-001",
      "--account-id", "acct-001",
      "--stance", "确认参加",
      "--tone", "professional"
    ],
    "timeout_seconds": 10
  },

  "mock_routes": [
    {
      "method": "GET",
      "path": "/emails/email-001",
      "response": {
        "status": 200,
        "body": {
          "id": "email-001",
          "subject": "明天下午2点的会议确认",
          "from_address": {"name": "张三", "email": "colleague@company.com"},
          "to_addresses": [{"name": "Test", "email": "test@example.com"}],
          "cc_addresses": [],
          "body_text": "明天下午2点的季度总结会议你能参加吗？\n张三",
          "received_at": "2026-03-01T10:00:00Z",
          "thread_id": null
        }
      }
    },
    {
      "method": "GET",
      "path": "/emails/email-001/ai-metadata",
      "response": {
        "status": 200,
        "body": {
          "summary": {"one_line": "张三邀请确认明天下午2点会议"},
          "categories": ["meeting"],
          "sentiment": "neutral"
        }
      }
    },
    {
      "method": "GET",
      "path": "/memories/acct-001",
      "response": {"status": 200, "body": {"memories": []}}
    },
    {
      "method": "POST",
      "path": "/v1/chat/completions",
      "response": {
        "status": 200,
        "body": {
          "choices": [{
            "message": {
              "content": "张三，\n\n收到，我会准时参加明天下午2点的季度总结会议。\n\n如需我提前准备材料，请告知。\n\n谢谢！"
            }
          }]
        }
      }
    }
  ],

  "assertions": {
    "exit_code": 0,
    "stdout_not_empty": true,
    "stdout_contains": ["张三"],
    "posted_requests": [
      {
        "comment": "LLM 调用 1 次",
        "method": "POST",
        "path_prefix": "/v1/chat/completions",
        "count": 1
      }
    ]
  }
}
```

## 8. 注意事项

| 问题 | 说明 |
|------|------|
| **USER.md** | analyzer/reply 会读 `~/.openclaw/workspace/USER.md`，文件不存在时函数返回空字符串，不影响测试 |
| **references/ 目录** | skill 从自身 `references/` 目录加载 prompt 模板，这些文件在 repo 中存在，无需 mock |
| **端口冲突** | MockServer 使用 `port=0`（OS 自动分配临时端口），不会与运行中的服务冲突 |
| **task_handler** | 目前 hardcode `CLAWMAIL_API`，缺少 `--clawmail-api` 参数，暂不纳入初始场景。后续可增加该参数使其可测 |
| **LLM 响应内容** | mock 中的 LLM 响应内容需要是 skill 能正确解析的格式（JSON 字符串或纯文本），参考各 skill 的 parse 逻辑 |

## 9. 扩展方向

- **更多场景**：spam 邮件、线程邮件、摘要差评、回复编辑、新邮件撰写、邮件润色
- **错误场景**：LLM 返回 500、返回非法 JSON、ClawMail API 超时、邮件不存在（404）
- **回归测试**：修改 skill 代码后运行全部场景，确保输出不变
- **task_handler 支持**：为 `task_handler.py` 添加 `--clawmail-api` 参数后纳入测试
