## ClawMail - AI智能邮箱功能实现说明

### 基础架构
ClawMail基于Python开发，采用**模块化插件架构**。核心流程：通过IMAP协议连接163邮箱（`aioimaplib`，原生 async），每2分钟（可配置）拉取新邮件到本地数据库，经AI处理后展示。AI能力通过标准OpenAI接口对接本地部署的OpenClaw服务（`openai` Python SDK）。UI层使用 **PyQt6**，异步集成使用 **qasync**。Python 运行时锁定：**CPython 3.11.13**。OpenClaw 作为本地 AI 网关，负责对接 **Moonshot Kimi K2.5** 大语言模型，为邮件智能分类、摘要生成、回复建议等场景提供底层能力支撑。

---

### 核心功能实现

**1. 智能邮件撰写**
用户在AI对话框输入写作需求（如"给客户写封延期道歉信"），系统调用OpenClaw生成邮件草稿，支持语气调整（正式/友好/简洁）。生成内容可直接插入编辑器或一键发送。

**2. 邮件辅导**
用户撰写邮件时，选中文字点击"润色"，AI实时提供语法修正、语气优化、措辞建议。支持中英双语辅导，在发送前进行最后检查。

**3. 邮件摘要**
新邮件下载后自动触发，AI提取核心要点生成3-5行摘要，显示在邮件列表预览中。长线程邮件自动合并历史上下文，生成对话脉络总结。

**4. 邮件关键词与分类**
AI分析邮件内容自动提取关键词，并按预设规则（紧急/待回复/项目/通知/订阅）或动态学习模式分类。分类标签显示在邮件列表，支持点击筛选。

**5. 智能任务流 & ToDo清单**
系统自动扫描邮件中的行动项（如"请周五前回复"），提取为待办任务加入右侧面板。支持手动添加任务，关联原始邮件，标记完成状态自动同步回邮件标签。

**6. AI Assistance聊天框**
右侧面板常驻对话窗口，支持上下文感知查询。可针对当前选中邮件提问（"这封邮件需要什么行动"），或执行跨邮件操作（"总结本周所有项目A的邮件"）。对话历史本地保存，支持连续会话。

---

### 技术亮点
- **流水线处理**：邮件下载→AI分析→状态更新→UI展示，全程异步非阻塞
- **插件化设计**：各AI功能独立为Claw插件，可单独开关、热更新
- **本地优先**：邮件数据本地存储，AI通过OpenClaw本地接口调用，保障隐私
- **渐进式增强**：基础功能离线可用，AI功能按需加载

---





ClawMail 核心架构
┌─────────────────────────────────────────────────────────────────┐
│                         表现层 (Presentation)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │
│  │ 邮件列表视图 │  │ 邮件详情页  │  │    AI Assistant 聊天窗   │   │
│  │ (懒加载AI)  │  │ (显示AI标签) │  │                        │   │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      应用协调层 (Orchestrator)                     │
│                    ┌─────────────────────┐                       │
│                    │    ClawMailCore     │                       │
│                    │  (事件调度/模块组装)  │                       │
│                    └─────────────────────┘                       │
│                              │                                   │
│           ┌──────────────────┼──────────────────┐                │
│           ▼                  ▼                  ▼                │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐        │
│  │  SyncManager   │ │ PluginPipeline │ │  ChatSession   │        │
│  │   同步管理器    │ │   插件流水线    │ │   AI对话管理    │        │
│  └────────────────┘ └────────────────┘ └────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      领域服务层 (Domain Services)                  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ EmailEngine  │  │ TaskManager  │  │   OpenClawBridge     │   │
│  │ (IMAP/SMTP)  │  │  (ToDo List) │  │ (AI服务统一接口)      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │         Skill-Driven AI Pipeline (新架构)                   │ │
│  │                                                            │ │
│  │   ┌──────────────┐    ┌────────────────────────────────┐  │ │
│  │   │ ai_processor │───►│ subprocess → skill 脚本         │  │ │
│  │   │  (dispatcher)│    │ (analyze_email.py 等)           │  │ │
│  │   └──────────────┘    └────────────┬───────────────────┘  │ │
│  │        │ fallback                  │ skill 通过 REST API  │ │
│  │        ▼                           │ 读写 DB 数据         │ │
│  │   ┌──────────────┐                 ▼                      │ │
│  │   │ Legacy Path  │        ┌────────────────┐              │ │
│  │   │ (旧 prompt   │        │ pending_facts  │              │ │
│  │   │  LLM 调用)   │        │ 事实累积→提升   │              │ │
│  │   └──────────────┘        └────────────────┘              │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      数据层 (Data Layer)                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │ EmailRepository│  │  TaskRepository│  │  ConversationStore │  │
│  │  (邮件存储)     │  │   (任务存储)    │  │    (对话历史)       │  │
│  └────────────────┘  └────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘


核心数据流：新邮件处理（Skill-Driven 架构）
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌──────────────────────┐
│ IMAP拉取 │────►│ 原始存储 │────►│ 状态标记 │────►│  ai_processor.py     │
│ 新邮件   │     │ (Raw)   │     │pending  │     │  (Skill dispatcher)  │
└─────────┘     └─────────┘     └─────────┘     └────────┬─────────────┘
                                                          │
                                           ┌──────────────┴──────────────┐
                                           ▼                             ▼
                                   ┌───────────────┐           ┌─────────────────┐
                                   │  Skill Path   │           │  Fallback Path  │
                                   │  (subprocess) │           │  (旧 prompt LLM) │
                                   └───────┬───────┘           └─────────────────┘
                                           │
                              ┌────────────┼────────────┐
                              ▼            ▼            ▼
                       ┌──────────┐ ┌──────────┐ ┌──────────────┐
                       │ 邮件分析  │ │ 事实提取  │ │ pending facts│
                       │摘要+分类  │ │联系人/项目│ │ 累积→提升     │
                       │+评分+任务 │ │+职业信息  │ │ →USER.md     │
                       └──────────┘ └──────────┘ └──────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │ Skill → REST API    │
                    │ 写入 EmailAIMetadata│
                    │ ai_status=processed │
                    └────────┬────────────┘
                             │
                             ▼
                    ┌─────────────────────┐
                    │  通知UI更新          │
                    │ (Qt Signals → 主线程) │
                    └─────────────────────┘


### 个性化反馈闭环（OpenClaw skill 触发）

用户修改邮件重要性评分后，ClawMail 记录到 `~/clawmail_data/feedback/feedback_importance_score.jsonl`。当记录数达到 5 条时，自动向 OpenClaw 发送消息触发 `clawmail-personalization` skill，该 skill 读取反馈 + 当前 prompt + 用户侧写，由大模型生成个性化评分标准，更新 `prompts/importance_score.txt` 并归档旧数据。详见 `PersonalizationPlan.md`。

### Skill-Driven 架构（新）

ClawMail 已迁移至 Skill-Driven 架构。AI 逻辑不再由 ClawMail 内部拼 prompt 调 LLM，而是通过 `subprocess` 直接调用外部 OpenClaw skill 脚本：

- **clawmail-analyzer**: 邮件分析（摘要、分类、评分、垃圾邮件检测、行动项、事实提取）
- **clawmail-reply**: 回复生成、新邮件生成、润色
- **clawmail-executor**: 用户偏好提取（用户修正 AI 预测后触发）

ClawMail 变为纯数据层 + UI 层，通过 REST API（`127.0.0.1:9999`）向 skill 脚本暴露邮件数据、记忆和 pending facts。Skill 脚本不存在时自动 fallback 到旧的 prompt-based 路径。

**Pending Facts 机制**：skill 从邮件中提取事实性信息（联系人关系、项目上下文、职业信息等）写入 `pending_facts` 表，同一事实被多封邮件佐证后置信度累加，达标后自动提升到 `~/.openclaw/workspace/USER.md`。



 好的，我来为你设计ClawMail的代码文件分层结构。基于我们讨论的架构原则（模块化、可组装、接口清晰），以下是完整的目录结构和文件组织方案。

---

## 整体目录结构

```
clawmail/
├── 📁 config/                    # 配置管理
├── 📁 core/                      # 核心框架（最小依赖）
├── 📁 domain/                    # 领域模型（纯数据，无业务逻辑）
├── 📁 infrastructure/            # 基础设施实现（具体技术）
├── 📁 plugins/                   # 智能插件（Claws）
├── 📁 services/                  # 应用服务层（协调器）
├── 📁 ui/                        # 用户界面（PyQt6 widgets；无直接业务逻辑）
├── 📁 tests/                     # 测试套件
├── 📁 scripts/                   # 工具脚本
├── 📄 main.py                    # 应用入口
├── 📄 requirements.txt           # 依赖清单
└── 📄 README.md                  # 项目文档
```

---

## 详细分层设计

### 1. Core 层（核心框架）

```
core/
├── __init__.py
├── interfaces/                   # 抽象接口定义（最稳定）
│   ├── __init__.py
│   ├── plugin.py                 # IClawPlugin, ClawContext, ClawResult
│   ├── email_sync.py             # IEmailSyncEngine, RawEmail
│   ├── repository.py             # IEmailRepository, ITaskRepository
│   ├── ai_provider.py            # IAIProvider, AIResponse
│   ├── event_bus.py              # IEventBus, Event
│   └── config.py                 # IConfigManager
├── events/                       # 事件定义
│   ├── __init__.py
│   ├── email_events.py           # EmailDownloaded, EmailProcessed
│   ├── plugin_events.py          # PluginExecuted, PluginFailed
│   └── system_events.py          # SyncStarted, ConfigChanged
├── exceptions/                   # 自定义异常
│   ├── __init__.py
│   ├── plugin_errors.py          # PluginExecutionError
│   ├── sync_errors.py            # SyncConnectionError
│   └── ai_errors.py              # AIProviderError
└── types/                        # 共享类型定义
    ├── __init__.py
    ├── primitives.py             # EmailId, Timestamp, etc.
    └── enums.py                  # PluginPriority, EmailStatus, etc.
```

**设计原则**：
- `core/` 不依赖任何外部库（除Python标准库）
- 所有接口使用 `abc.ABC` 定义
- 事件总线是模块间唯一通信方式

---

### 2. Domain 层（领域模型）

```
domain/
├── __init__.py
├── models/                       # 实体模型
│   ├── __init__.py
│   ├── email.py                  # Email 实体
│   ├── attachment.py             # Attachment 实体
│   ├── task.py                   # Task 实体（ToDo）
│   ├── conversation.py           # AI对话会话
│   └── user.py                   # 用户配置实体
├── value_objects/                # 值对象（不可变）
│   ├── __init__.py
│   ├── address.py                # EmailAddress（含验证）
│   ├── content.py                # EmailContent (text/html)
│   └── classification.py         # ClassificationLabel
└── aggregates/                   # 聚合根
    ├── __init__.py
    └── email_thread.py           # 邮件会话线程
```

**关键文件示例**：

```python
# domain/models/email.py
@dataclass
class Email:
    id: EmailId
    subject: str
    from_addr: EmailAddress
    to_addrs: List[EmailAddress]
    content: EmailContent
    received_at: datetime
    status: EmailStatus          # UNPROCESSED, PROCESSING, PROCESSED, FAILED
    ai_metadata: Dict[str, Any]  # AI处理结果存储
    tags: List[ClassificationLabel]
    
    def mark_processing(self):
        self.status = EmailStatus.PROCESSING
        
    def update_ai_result(self, plugin_name: str, result: Any):
        self.ai_metadata[plugin_name] = result
```

---

### 3. Infrastructure 层（技术实现）

```
infrastructure/
├── __init__.py
├── email_clients/                # 邮件协议实现
│   ├── __init__.py
│   ├── base.py                   # 共享基类
│   ├── imap_client.py            # IMAP 客户端（aioimaplib，原生 async）
│   │                             # 参考根目录 emailIMAP.py 的 mailIMAP 类骨架
│   │                             # 凭据通过 CredentialManager.decrypt_credentials() 获取
│   │                             # delete_email_by_message_id(message_id):
│   │                             #   遍历服务端所有 IMAP 文件夹（LIST），对每个文件夹 SELECT，
│   │                             #   用 SEARCH HEADER Message-ID 定位 UID，标记 \Deleted 后 EXPUNGE。
│   │                             #   实现跨文件夹服务端彻底删除（UID 仅在单文件夹唯一，
│   │                             #   Message-ID 全局唯一，适合跨文件夹检索）。
│   ├── smtp_client.py            # 发送邮件实现
│   │                             # 参考根目录 emailSMTP.py 的完整 send_email() 实现
│   │                             # 使用 aiosmtplib（async）替换同步 smtplib
│   │                             # 服务器：smtp.163.com:465（SSL）
│   └── parsers/                  # 邮件解析器
│       ├── __init__.py
│       ├── mime_parser.py        # MIME解析
│       └── text_extractor.py     # 正文提取
├── database/                     # 数据持久化
│   ├── __init__.py
│   ├── connection.py             # 数据库连接管理（WAL模式）
│   ├── repositories/             # 仓库实现
│   │   ├── __init__.py
│   │   ├── email_repo.py         # SQLiteEmailRepository
│   │   ├── task_repo.py          # SQLiteTaskRepository
│   │   └── vector_repo.py        # 向量检索（可选Chroma，Phase 5）
│   └── migrations/               # 数据库迁移脚本
│       ├── __init__.py
│       └── v1_initial.py
├── ai/                           # AI服务实现
│   ├── __init__.py
│   ├── ai_processor.py           # Skill-Driven: subprocess → skill scripts (fallback: legacy prompt)
│   │                             # process_email(): 优先调 analyzer skill，失败 fallback 旧路径
│   │                             # generate_reply_draft()/generate_email()/polish_email(): 同上模式
│   │                             # 详细 skill 路径配置见 tech_spec.md 1.5b 节
│   ├── openai_bridge.py          # OpenClaw桥接（legacy fallback + 用户聊天）
│   │                             # 遵循根目录 ClawChat.py 的通信模式（不导入，独立实现）
│   │                             # process_email(): 对应 mailChat，agentId="mailAgent_{id[:8]}"
│   │                             # user_chat(): 对应 userChat，agentId="userAgent001"
│   │                             # 同步调用，Plugin层用 run_in_executor 包装为 async
│   │                             # 详细实现模式见 tech_spec.md 第1.5节
│   └── prompts/                  # 提示词模板（legacy, Phase 3 后清理）
│       ├── __init__.py
│       ├── templates/            # 按功能分类（对应 prompt.md 中各 Prompt）
│       │   ├── unified_analyze.txt  # Prompt #1：统一分析（摘要+分类+任务提取）
│       │   ├── reclassify.txt       # Prompt #3：重新分类（独立功能）
│       │   ├── compose.txt          # Prompt #5：智能撰写
│       │   ├── polish.txt           # Prompt #6：邮件润色
│       │   ├── reply_suggest.txt    # Prompt #7：回复建议
│       │   └── chat_assistant.txt   # Prompt #8：AI对话
│       └── prompt_manager.py     # 提示词加载与变量注入
├── security/                     # 安全实现（新增）
│   ├── __init__.py
│   └── credential_manager.py     # keyring + Fernet 凭据加密（见 tech_spec.md 第4节）
└── config/                       # 配置实现
    ├── __init__.py
    ├── yaml_config.py            # YAML配置管理
    └── validators.py             # 配置验证
```

---

### 4. Plugins 层（智能插件）

```
plugins/
├── __init__.py
├── base.py                       # 插件基类（继承core接口）
├── registry.py                   # 插件注册表（自动发现）
├── coordinator.py                # 插件协调器（串联执行）
├── builtin/                      # 内置插件
│   ├── __init__.py
│   ├── compose_assistant/        # 智能撰写
│   │   ├── __init__.py
│   │   ├── plugin.py             # ComposePlugin 实现
│   │   └── config.yaml           # 插件配置
│   ├── summarize/                # 邮件摘要
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   └── config.yaml
│   ├── classify/                 # 智能分类
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   └── config.yaml
│   ├── extract_tasks/            # 任务提取（ToDo）
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   └── config.yaml
└── custom/                       # 用户自定义插件（Git忽略）
    ├── __init__.py
    └── .gitkeep
```

**插件标准结构**：

```python
# plugins/builtin/summarize/plugin.py
class SummarizePlugin(IClawPlugin):
    name = "email_summarize"
    priority = PluginPriority.NORMAL
    triggers = ["new_email"]
    
    def __init__(self, ai_provider: IAIProvider):
        self.ai = ai_provider
        
    async def execute(self, context: ClawContext) -> ClawResult:
        email = context.email
        prompt = f"总结以下邮件：\n{email.content.text}"
        
        response = await self.ai.chat_completion([{
            "role": "user", 
            "content": prompt
        }])
        
        return ClawResult(
            success=True,
            data={"summary": response.content},
            ui_components=[SummaryCard(text=response.content)]
        )
```

---

### 5. Services 层（应用服务）

```
services/
├── __init__.py
├── sync_service.py               # 邮件同步协调
├── plugin_service.py             # 插件生命周期管理
├── ai_chat_service.py            # AI对话服务（右一面板）
├── task_service.py               # ToDo任务管理
├── search_service.py             # 邮件检索（关键词+向量）
└── orchestration/                # 复杂流程编排
    ├── __init__.py
    └── email_processing_flow.py  # 邮件处理流水线
```

**关键服务**：

```python
# services/orchestration/email_processing_flow.py
class EmailProcessingFlow:
    """邮件处理流水线：下载 → AI处理 → 存储 → 通知UI"""
    
    def __init__(
        self,
        sync_engine: IEmailSyncEngine,
        plugin_coordinator: PluginCoordinator,
        email_repo: IEmailRepository,
        event_bus: IEventBus
    ):
        self.sync = sync_engine
        self.plugins = plugin_coordinator
        self.repo = email_repo
        self.events = event_bus
        
    async def process_new_emails(self, since: datetime):
        # 1. 下载邮件
        raw_emails = await self.sync.sync_since(since)
        
        for raw in raw_emails:
            # 2. 转换为领域模型
            email = self._convert_to_domain(raw)
            email.mark_processing()
            await self.repo.save_email(email)
            
            # 3. 发布"开始处理"事件（UI显示进度条）
            await self.events.publish(EmailProcessingStarted(email.id))
            
            # 4. 串联执行插件
            context = ClawContext(email=email)
            results = await self.plugins.execute_chain(context)
            
            # 5. 合并结果
            for result in results:
                if result.success:
                    email.update_ai_result(result.plugin_name, result.data)
                    
            email.status = EmailStatus.PROCESSED
            await self.repo.save_email(email)
            
            # 6. 通知UI更新
            await self.events.publish(EmailProcessingCompleted(email.id, results))
```

---

### 6. UI 层（用户界面）

```
ui/
├── __init__.py
├── app.py                        # 应用主窗口（组装各组件）
├── components/                   # 可复用组件
│   ├── __init__.py
│   ├── base.py                   # 基础组件接口
│   ├── toolbar.py                # 工具栏
│   ├── action_bar.py             # 操作按钮栏（新邮件/同步/设置）
│   ├── compose_dialog.py         # 撰写/回复/转发/草稿编辑对话框
│   │                             # draft_id 参数：非 None 时为编辑已有草稿（保存→update_draft）
│   │                             # 60 秒 QTimer 自动静默保存；reject() 覆盖实现关闭/取消/ESC 询问
│   │                             # WebEngine 回复模式：runJavaScript 两步异步提取
│   │                             #   innerText（纯文本）→ innerHTML（html_body）后发送/保存
│   ├── email_list.py             # 邮件列表组件
│   ├── email_viewer.py           # 邮件内容展示（QWebEngineView，见下）
│   ├── progress_indicator.py     # 状态进度条
│   ├── ai_panel.py               # AI处理区域
│   ├── todo_panel.py             # ToDo列表面板
│   └── chat_panel.py             # AI对话框
├── views/                        # 页面级布局
│   ├── __init__.py
│   ├── main_layout.py            # 主四栏布局
│   ├── compose_window.py         # 写信窗口
│   └── settings_dialog.py        # 设置界面
├── controllers/                  # 视图-服务桥接
│   ├── __init__.py
│   ├── email_controller.py       # 邮件相关操作
│   ├── ai_controller.py          # AI功能操作
│   └── sync_controller.py        # 同步控制
└── assets/                       # 静态资源
    ├── icons/
    ├── styles/
    └── fonts/
```

**UI 框架（最终确定）：PyQt6 6.7.x + PyQt6-WebEngine**

| 理由 | 说明 |
|------|------|
| 纯 Python 集成最深 | 无 subprocess 桥接，无 IPC 延迟 |
| 原生桌面通知 | `QSystemTrayIcon` 直接支持 |
| 异步兼容 | `qasync` 将 asyncio 集成进 Qt 事件循环 |
| 浏览器级邮件渲染 | `QWebEngineView`（Chromium 内核），正确处理 CSS / `display:none` / 图片 |

**邮件内容渲染与操作（`app.py` 中实现）：**
- `_EmailWebPage(QWebEnginePage)` — 拦截链接点击，在系统浏览器打开
- `EmailWebView(QWebEngineView)` — JS 禁用，允许加载外链图片，注入 `_RESPONSIVE_CSS` 使图片等宽自适应
- 邮件内容栏头部含操作按钮：`[回复]` `[回复全部]` `[转发]`，选中邮件后可见
  - 回复：预填发件人地址，主题加 `Re:`，正文含纯文本引用
  - 回复全部：收件人含原发件人+所有原收件人（排除自己），抄送=原抄送
  - 转发：收件人留空，主题加 `Fwd:`，正文含原文
  - 三个方法均复用 `ComposeDialog`（支持 `initial_to/cc/subject/body` 预填充参数）
- 所有栏目标题：`font-size: 10px bold`，`padding: 4px 8px`

**邮件列表交互（`app.py` 中实现）：**
- `_on_email_context_menu()` — 右键菜单，根据当前文件夹动态显示选项
- `_ctx_delete_email()` — 软删除：folder → "已删除"（本地操作）
- `_ctx_perm_delete_email()` — 彻底删除：本地 DB delete + 异步 IMAP 服务端删除（`delete_email_by_message_id`）
- `_ctx_delete_draft()` — 草稿删除：仅本地 DB delete，不经过回收站
- `_ctx_restore_email()` — 移回收件箱：folder → "INBOX"
- `_on_email_double_clicked()` — 草稿箱双击打开 ComposeDialog（带 draft_id）
- `_make_email_item()` — 草稿箱显示"致: 收件人"；UserRole+7 存 is_draft 标志
- `EmailListDelegate.paint()` — 草稿条目灰色（#888888）斜体渲染

不选择：PySide6（许可证差异）/ Toga（组件成熟度不足）/ Tauri（破坏纯 Python 约束）

---

### 异步线程模型

**选型：qasync（让 asyncio 事件循环运行在 Qt 事件循环内部）**

```python
# main.py
import sys, asyncio, qasync
from PyQt6.QtWidgets import QApplication
from ui.app import ClawMailApp

def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = ClawMailApp()
    window.show()
    with loop:
        loop.run_forever()
```

**四条线程安全规则：**

1. **Qt widget 操作只在主线程**：禁止在协程中直接调用 `widget.setText()`
2. **纯 I/O 用 asyncio 协程**：`aioimaplib`、`httpx` 均原生 async，不需要 QThread
3. **CPU 密集用 run_in_executor**：`await loop.run_in_executor(None, blocking_func)`
4. **跨线程 UI 更新只走 Qt Signal**：emit 从任意线程安全，slot 在主线程执行

```python
# services/sync_service.py 示例
from PyQt6.QtCore import QObject, pyqtSignal

class SyncService(QObject):
    email_downloaded = pyqtSignal(str)          # email_id
    ai_progress_updated = pyqtSignal(str, int)  # email_id, progress%
    sync_completed = pyqtSignal(int)            # new_count
    sync_failed = pyqtSignal(str)               # error_msg

    async def run_sync_cycle(self):
        emails = await self._imap_client.fetch_new()
        for email in emails:
            await self._repo.save(email)
            self.email_downloaded.emit(email.id)  # 安全触发 UI 刷新
```

> 完整异步模型见 `tech_spec.md` 第 5 节。

---

### 7. Config 层（配置管理）

```
config/
├── __init__.py
├── default.yaml                  # 默认配置
├── schema.py                     # 配置项验证模式
└── manager.py                    # 配置管理器
```

**配置结构**：

```yaml
# config/default.yaml
app:
  name: "ClawMail"
  version: "0.1.0"
  
sync:
  interval_minutes: 2
  batch_size: 50
  retry:
    max_attempts: 3
    backoff_base_seconds: 2      # 2s → 4s → 8s
    backoff_max_seconds: 60
    no_retry_on: ["AuthenticationError"]
  
email:
  imap_server: "imap.163.com"
  imap_port: 993
  smtp_server: "smtp.163.com"
  smtp_port: 465
  
ai:
  provider: "openclaw"
  base_url: "http://127.0.0.1:18789/v1"  # 见 ClawChat.py；可覆盖
  model: "default"                         # OpenClaw 固定值，不可更改
  timeout: 30
  
plugins:
  enabled:
    - "email_summarize"
    - "smart_classify"
    - "extract_tasks"
  settings:
    smart_classify:
      categories: [由AI定义和设计]
```

---

## 依赖关系图

```
┌─────────────────────────────────────────┐
│              UI Layer                   │
│   (components → views → controllers)    │
├─────────────────────────────────────────┤
│           Services Layer                │
│   (sync_service, plugin_service, ...)   │
├─────────────────────────────────────────┤
│           Plugins Layer                 │
│   (builtin/ + custom/)                  │
├─────────────────────────────────────────┤
│   Core Layer  ←────  Domain Layer       │
│  (interfaces)       (models)            │
├─────────────────────────────────────────┤
│        Infrastructure Layer             │
│  (email_clients, database, ai, config)  │
└─────────────────────────────────────────┘

依赖规则：
- 上层可依赖下层
- 同层之间尽量不依赖（通过core/interfaces解耦）
- infrastructure 实现 core 的接口
- plugins 实现 core 的 IClawPlugin
```

---

## 关键流程的数据流向

```
1. 同步邮件流程：
main.py → SyncService → IMAPEngine (infra)
              ↓
         EmailRepository (infra) → SQLite
              ↓
         EventBus → PluginCoordinator
              ↓
         [串联执行各Plugin] → AIProvider (infra)
              ↓
         更新Email状态 → UI更新

2. 用户AI对话流程：
ChatPanel → AIChatService → AIProvider
                ↓
         可访问EmailRepository获取历史邮件
                ↓
         流式响应 → ChatPanel更新
```

---






