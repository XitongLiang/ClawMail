
## ToDo List 核心架构

### 数据来源双轨制

| 来源类型 | 产生方式 | 特点 |
|---------|---------|------|
| **AI提取** | 自动扫描邮件内容识别行动项 | 绑定邮件，可追溯上下文 |
| **用户创建** | 手动输入或语音/快捷方式添加 | 独立存在，可关联任意邮件或悬空 |

---

### 任务实体结构

```
Task
├── 基础身份
│   ├── id: UUID                    # 全局唯一
│   ├── source_type: enum           # extracted | manual | template | recurring
│   └── source_ref: object          # 来源引用（根据source_type变化）
│
├── 来源引用（source_ref 多态结构）
│   ├── 当 extracted: {email_id, quote, confidence, ai_rationale}
│   ├── 当 manual: {created_via: ui/shortcut/voice, original_input}
│   ├── 当 template: {template_id, auto_fill_params}
│   └── 当 recurring: {parent_task_id, recurrence_rule, next_instance}
│
├── 内容层
│   ├── title: string               # 必填，动词开头
│   ├── description: string         # 详细描述，支持Markdown
│   ├── rich_content: object         # 结构化内容（清单项/子任务/笔记）
│   │   ├── checklist: [ ]          # 可勾选子项
│   │   ├── notes: string           # 用户随时追加的备忘
│   │   └── attachments: [ ]       # 关联文件/图片/链接
│   │
│   └── context_links: [ ]           # 关联上下文
│       ├── 邮件引用（email_id + 段落高亮）
│       ├── 外部链接（URL + 标题快照）
│       └── 本地文件（路径 + 预览）
│
├── 时间属性
│   ├── created_at: timestamp
│   ├── updated_at: timestamp
│   ├── due_date: timestamp|null    # 截止日期
│   ├── due_time: time|null         # 具体时刻（可选）
│   ├── duration_estimate: minutes  # 预计耗时
│   ├── reminders: [ ]              # 多级提醒设置
│   └── completion: object
│       ├── completed_at
│       ├── actual_duration
│       └── outcome_notes           # 完成后复盘
│
├── 状态流转
│   ├── status: enum
│   │   ├── pending（默认）
│   │   ├── in_progress（已开始）
│   │   ├── snoozed（暂缓）
│   │   ├── completed（完成）
│   │   ├── cancelled（取消）
│   │   └── archived（归档，不再显示但可搜索）
│   │
│   └── status_history: [ ]         # 状态变更日志
│       └── [{from, to, at, by: user/ai/system, reason}]
│
├── 优先级与分类
│   ├── priority: enum              # high | medium | low | none
│   ├── priority_source: enum       # ai_suggested | user_set | inherited
│   ├── tags: [string]              # 用户自定义标签
│   ├── category: string            # 继承邮件分类或用户指定
│   └── project: string|null        # 所属项目（跨邮件聚合）
│
├── 执行属性
│   ├── assignee: enum              # me | delegate | waiting
│   │                               # （AI输出的 me/sender/other 映射：me→me，sender→waiting，other→delegate）
│   ├── delegate_info: object        # 委派时填写
│   │   ├── person_name/email
│   │   ├── sent_request_at         # 何时发出请求
│   │   ├── follow_up_reminder      # 跟进提醒
│   │   └── response_received       # 是否收到回复
│   │
│   ├── effort_level: enum           # quick(<5min) | medium | deep
│   ├── energy_required: enum       # high | normal | low | any
│   └── location_context: enum      # any | desk | mobile | deep_focus
│
└── 视图与呈现
    ├── display_config: object
    │   ├── color_override          # 自定义颜色
    │   ├── icon_emoji              # 自定义图标
    │   ├── list_view_expanded      # 默认展开详情
    │   └── hide_until              # 延迟显示（未来任务不打扰）
    │
    └── ui_state: object            # 运行时临时状态
        ├── is_selected
        ├── is_editing
        └── scroll_into_view
```

---

### 创建入口矩阵

| 入口 | 触发方式 | 默认source_type | 特殊行为 |
|-----|---------|----------------|---------|
| AI自动提取 | 邮件处理流程 | extracted | 自动填充关联邮件，用户可编辑后确认 |
| 邮件右键菜单 | 选中文字→"添加为任务" | manual | 自动带入引用上下文 |
| 顶部工具栏 | "新建任务"按钮 | manual | 空白模板，自由填写 |
| 快捷键 | Ctrl+Shift+T | manual | 弹出快速输入浮层 |
| AI对话 | "@Claw 提醒我..." | manual | 自然语言解析为结构化任务 |
| 语音输入 | 按住麦克风图标 | manual | 语音转文字后解析 |
| 模板库 | 选择预设模板 | template | 自动填充重复性任务结构 |
| 任务复制 | 右键现有任务→"复制" | manual | 继承除时间外的所有属性 |
| 周期性生成 | 父任务触发 | recurring | 自动按规则生成子实例 |

---

### 列表视图架构

```
ToDo Panel（右一上半区）
├── 智能分组（可折叠）
│   ├── 🔥 今日焦点（算法排序）
│   │   └── 综合due_date/priority/effort/energy的最优执行序列
│   │
│   ├── 📥 待确认（AI提取未人工复核）
│   │   └── 用户需点击"确认"或"编辑"后进入正式列表
│   │
│   ├── ⏰ 已到期/今日到期（按时间排序）
│   ├── 📅 未来7天（按日期分组）
│   ├── 📂 无截止日期（按项目/标签分组）
│   └── ⏳ 暂缓中（snoozed_until到期后自动回归）
│
├── 用户自定义视图
│   ├── 按项目分组
│   ├── 按标签筛选
│   ├── 按能量状态匹配（"现在只有15分钟"→quick任务）
│   └── 按地点匹配（"在路上"→mobile可处理）
│
├── 快速操作栏
│   ├── [+ 新建] [🔍 搜索] [⚡ 智能排序] [📥 归档已完成]
│   └── 批量选择模式：多选后批量修改日期/标签/状态
│
└── 任务卡片交互
    ├── 悬停：显示完整描述和快捷操作
    ├── 点击：展开详情编辑面板
    ├── 拖拽：调整优先级或移动到其他分组
    └── 右滑：快速完成/删除
```

---

### 关键交互流程

**AI提取任务确认流程**
```
邮件处理完成
   ↓
AI识别出3个潜在任务 → 显示在"待确认"分组
   ↓
用户操作：
   ├─► 点击✓ 确认 → 进入正式列表，保留AI元数据
   ├─► 点击✎ 编辑 → 修改标题/日期后确认
   ├─► 点击✕ 忽略 → 标记为rejected，不再提示
   └─► 忽略超过24小时 → 自动归档（可找回）
```

**手动创建任务流程**
```
用户点击[+ 新建]
   ↓
弹出快速输入框（单行，智能解析）
   ↓
输入："明天下午3点给张总打电话谈合同"
   ↓
NLP解析：
   ├── due_date: 2024-01-16
   ├── due_time: 15:00
   ├── title: "与张总电话沟通合同事宜"
   └── 建议标签：["电话", "商务", "合同"]
   ↓
用户确认或调整 → 创建完成
```

---

### 与邮件系统的双向关联

| 方向 | 机制 | 场景 |
|-----|------|------|
| 邮件→任务 | 自动提取 + 手动创建 | 从邮件产生行动 |
| 任务→邮件 | 任务卡片显示"来自邮件"入口 | 回溯上下文 |
| 任务完成→邮件 | 可选：标记邮件为"已处理" | 清理收件箱 |
| 邮件归档→任务 | 邮件移动时询问"相关任务如何处理" | 防止 orphaned task |
| 任务延期→邮件 | 可选：发送跟进邮件给对方 | 外部协调 |

---

### 数据存储要点

- **来源可追溯**：无论手动自动，保留创建上下文
- **用户编辑不丢AI信息**：AI建议保存为suggestion层，用户修改为override层，并存diff
- **悬空任务友好**：允许暂不关联邮件，后续可随时绑定
- **模板可扩展**：用户高频任务保存为个人模板





## 数据库表结构

### 主表：tasks

```sql
CREATE TABLE tasks (
    -- 主键与身份
    id TEXT PRIMARY KEY,                          -- UUID v4，全局唯一
    created_at INTEGER NOT NULL,                  -- Unix时间戳毫秒，统一时区处理
    updated_at INTEGER NOT NULL,
    
    -- 来源类型 (核心区分字段)
    source_type TEXT NOT NULL CHECK(source_type IN (
        'extracted',      -- AI从邮件自动提取
        'manual',         -- 用户手动创建
        'template',       -- 从模板生成
        'recurring'       -- 周期性任务实例
    )),
    
    -- 来源详情 (JSON多态结构，根据source_type解析)
    source_ref TEXT NOT NULL,
    /*
    extracted 格式: {
        "email_id": "email_uuid",
        "quote": "原文引用片段",
        "confidence": 0.92,
        "ai_rationale": "AI判断理由",
        "extraction_version": "v2.1"
    }
    
    manual 格式: {
        "created_via": "ui|shortcut|voice|chat",
        "original_input": "用户原始输入（未解析）",
        "nlp_parsed": true,
        "device_id": "创建设备标识"
    }
    
    template 格式: {
        "template_id": "template_uuid",
        "template_name": "每日站会",
        "auto_fill_params": {"project": "项目A"}
    }
    
    recurring 格式: {
        "parent_task_id": "parent_uuid",
        "instance_number": 3,
        "recurrence_rule": "RRULE:FREQ=WEEKLY;BYDAY=MO",
        "generated_at": 1705312800000
    }
    */
    
    -- 内容层
    title TEXT NOT NULL,                          -- 纯文本，限制200字符
    description TEXT,                           -- Markdown格式，限制2000字符
    
    -- 富内容 (JSON结构化)
    rich_content TEXT,
    /*
    {
        "checklist": [
            {"id": "chk_1", "text": "准备材料", "checked": true, "checked_at": 1705312800000},
            {"id": "chk_2", "text": "预约会议室", "checked": false}
        ],
        "notes": "用户追加的备忘笔记",
        "attachments": [
            {"type": "file", "path": "attachments/...", "name": "参考.pdf"},
            {"type": "link", "url": "...", "title": "快照标题", "favicon": "..."}
        ]
    }
    */
    
    -- 上下文链接 (JSON数组)
    context_links TEXT,
    /*
    [
        {"type": "email", "email_id": "...", "highlight_range": [120, 350], "preview": "..."},
        {"type": "url", "url": "...", "title": "...", "snapshot": "..."},
        {"type": "file", "path": "...", "mime_type": "..."}
    ]
    */
    
    -- 时间属性
    due_date INTEGER,                             -- 截止日期 00:00:00
    due_time INTEGER,                             -- 具体时刻分钟数 (如900=15:00)
    duration_estimate INTEGER,                    -- 预计耗时分钟数
    timezone TEXT DEFAULT 'Asia/Shanghai',        -- 时区标识
    
    -- 提醒设置 (JSON)
    reminders TEXT,
    /*
    [
        {"type": "desktop", "advance_minutes": 30},
        {"type": "email", "advance_minutes": 1440},
        {"type": "mobile_push", "advance_minutes": 10}
    ]
    */
    
    -- 完成记录 (JSON)
    completion TEXT,
    /*
    {
        "completed_at": 1705312800000,
        "completed_by": "user|ai_suggestion|system_auto",
        "actual_duration": 45,
        "outcome_notes": "完成后复盘笔记"
    }
    */
    
    -- 状态机（完整枚举见 tech_spec.md 2.6节）
    -- rejected：仅适用于 source_type='extracted' 的 AI 提取任务，用户点击"忽略"触发
    --           rejected 任务不出现在任何主视图，不参与统计，但可通过搜索找到
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
        'pending', 'in_progress', 'snoozed', 'completed', 'cancelled', 'rejected', 'archived'
    )),
    
    -- 状态历史 (JSON数组，自动追加)
    status_history TEXT DEFAULT '[]',
    /*
    [
        {"from": null, "to": "pending", "at": 1705312800000, "by": "system", "reason": "created"},
        {"from": "pending", "to": "in_progress", "at": 1705312900000, "by": "user", "reason": "开始处理"}
    ]
    */
    
    snoozed_until INTEGER,                        -- 暂缓至何时
    
    -- 优先级
    priority TEXT DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low', 'none')),
    priority_source TEXT DEFAULT 'user_set' CHECK(priority_source IN (
        'ai_suggested', 'user_set', 'inherited', 'calculated'
    )),
    
    -- 分类体系
    tags TEXT,                                    -- JSON数组: ["电话", "合同", "紧急"]
    category TEXT,                                -- 继承邮件分类或用户指定
    project_id TEXT,                              -- 关联项目表 (可选扩展)
    
    -- 执行属性
    assignee_type TEXT DEFAULT 'me' CHECK(assignee_type IN ('me', 'delegate', 'waiting')),
    delegate_info TEXT,                           -- JSON，assignee为delegate时必填
    /*
    {
        "person_name": "李四",
        "email": "li@company.com",
        "request_sent_at": 1705312800000,
        "follow_up_reminder": 1705399200000,
        "response_received": false
    }
    */
    
    effort_level TEXT CHECK(effort_level IN ('quick', 'medium', 'deep')),
    energy_required TEXT CHECK(energy_required IN ('high', 'normal', 'low', 'any')),
    location_context TEXT CHECK(location_context IN ('any', 'desk', 'mobile', 'deep_focus')),
    
    -- 视图配置 (JSON)
    display_config TEXT,
    /*
    {
        "color_override": "#FF6B6B",
        "icon_emoji": "📞",
        "list_view_expanded": false,
        "hide_until": null
    }
    */
    
    -- 软删除与归档
    is_deleted INTEGER DEFAULT 0,                 -- 软删除标记
    deleted_at INTEGER,
    archived_at INTEGER,                          -- 归档时间 (非删除，仅移出主列表)
    
    -- 搜索优化
    search_text TEXT,                             -- 全文搜索合成字段 (title+description+notes)
    
    -- 同步标记 (多设备场景)
    sync_version INTEGER DEFAULT 1,               -- 乐观锁版本号
    last_sync_at INTEGER,
    device_origin TEXT                            -- 创建设备标识
);

-- 核心索引
CREATE INDEX idx_tasks_status ON tasks(status, is_deleted, archived_at) 
    WHERE is_deleted = 0;                         -- 主列表查询

CREATE INDEX idx_tasks_due ON tasks(due_date, due_time, priority, status) 
    WHERE status IN ('pending', 'in_progress', 'snoozed');

CREATE INDEX idx_tasks_email ON tasks(
    json_extract(source_ref, '$.email_id')
) WHERE source_type = 'extracted';              -- 邮件关联查询

CREATE INDEX idx_tasks_project ON tasks(project_id, status) 
    WHERE project_id IS NOT NULL;

CREATE INDEX idx_tasks_tags ON tasks(tags);       -- JSON虚拟表索引需额外配置

CREATE INDEX idx_tasks_snoozed ON tasks(snoozed_until, status) 
    WHERE status = 'snoozed';                     -- 暂缓到期自动唤醒

-- 全文搜索索引 (SQLite FTS5扩展)
CREATE VIRTUAL TABLE tasks_fts USING fts5(
    title, description, 
    content='tasks', 
    content_rowid='rowid'
);

-- 触发器：自动同步搜索字段
CREATE TRIGGER tasks_ai AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, title, description) 
    VALUES (new.rowid, new.title, new.description);
END;

CREATE TRIGGER tasks_ad AFTER DELETE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, description) 
    VALUES ('delete', old.rowid, old.title, old.description);
END;

CREATE TRIGGER tasks_au AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, description) 
    VALUES ('delete', old.rowid, old.title, old.description);
    INSERT INTO tasks_fts(rowid, title, description) 
    VALUES (new.rowid, new.title, new.description);
END;
```

---

### 辅助表

```sql
-- 用户任务模板库
CREATE TABLE task_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    
    -- 模板默认值
    default_title TEXT,                           -- 可含变量如"{项目}周会"
    default_description TEXT,
    default_duration INTEGER,
    default_effort_level TEXT,
    default_energy_required TEXT,
    default_tags TEXT,                            -- JSON数组
    
    -- 模板结构
    structure TEXT,                               -- JSON定义必填/可选字段
    
    -- 快捷触发
    shortcut_key TEXT,                            -- 如"Ctrl+Shift+1"
    icon_emoji TEXT,
    color TEXT,
    
    usage_count INTEGER DEFAULT 0,
    last_used_at INTEGER,
    created_at INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1
);

-- 周期性任务父表（生成器）
CREATE TABLE recurring_tasks (
    id TEXT PRIMARY KEY,
    template_task_id TEXT,                        -- 基于哪个任务生成
    
    -- 周期规则 (标准RRULE + 自定义)
    recurrence_rule TEXT,                           -- "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"
    recurrence_json TEXT,                           -- 解析后的结构化规则
    
    -- 生成控制
    start_date INTEGER,                             -- 开始日期
    end_date INTEGER,                               -- 结束日期或null无限
    max_instances INTEGER,                          -- 最大生成数
    
    -- 生成记录
    last_generated_at INTEGER,
    last_instance_date INTEGER,
    generated_count INTEGER DEFAULT 0,
    
    -- 异常处理
    exceptions TEXT,                                -- JSON: 跳过特定日期
    
    is_active INTEGER DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 任务依赖关系（可选扩展）
CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    dependency_type TEXT DEFAULT 'finish_to_start', -- finish_to_start|start_to_start|finish_to_finish|start_to_finish
    created_at INTEGER NOT NULL,
    
    PRIMARY KEY (task_id, depends_on_task_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- 用户视图配置（保存自定义筛选）
CREATE TABLE task_views (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,                             -- "今日重点"|"深度工作时段"
    
    -- 筛选条件 (JSON)
    filter_config TEXT,
    /*
    {
        "status": ["pending", "in_progress"],
        "priority": ["high", "medium"],
        "due_within_days": 7,
        "effort_level": ["quick", "medium"],
        "energy_required": ["normal", "low"],
        "tags_include": ["合同"],
        "tags_exclude": ["等待他人"]
    }
    */
    
    -- 排序规则
    sort_config TEXT,
    /*
    {
        "primary": "smart_score",  // 智能排序算法
        "secondary": "due_date",
        "tertiary": "priority"
    }
    */
    
    -- 分组方式
    group_by TEXT,                                  -- date|project|priority|effort|none
    
    is_default INTEGER DEFAULT 0,                   -- 默认打开此视图
    shortcut_key TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
```

---

## 内存缓存结构（运行时）

```python
# 热数据缓存策略
TaskCache {
    # 主索引
    by_id: Dict[str, Task]                    # 全量任务，LRU淘汰
    
    # 列表视图缓存（按查询条件分片）
    list_views: {
        "status:pending|priority:high": CachedList(
            task_ids: List[str],               # 有序ID列表
            total_count: int,
            last_updated: timestamp,
            query_hash: str                     # 用于失效判断
        )
    }
    
    # 今日焦点算法结果（每小时刷新）
    today_focus: {
        generated_at: timestamp,
        sequence: List[str],                   # 推荐执行顺序
        reasoning: Dict[str, str]              # 每个任务的排序理由
    }
    
    # 统计快照（分钟级刷新）
    stats: {
        total_pending: int,
        due_today: int,
        overdue: int,
        by_project: Dict[str, int],
        by_effort: Dict[str, int]
    }
}
```

---

## 文件存储补充

```
clawmail_data/
├── clawmail.db                    # 主数据库（上述所有表）
├── tasks/
│   └── attachments/               # 任务专属附件（与邮件附件隔离）
│       └── {task_id}/
│           ├── {hash}_合同草稿.pdf
│           └── {hash}_会议录音.m4a
├── templates/                     # 模板预览图（可选）
│   └── {template_id}.png
└── exports/                       # 任务导出
    └── tasks_2024-01-15.json
```

---

## 关键查询模式

| 场景 | SQL模式 |
|-----|---------|
| 主列表（待处理） | `SELECT * FROM tasks WHERE status IN ('pending','in_progress') AND is_deleted=0 AND archived_at IS NULL ORDER BY due_date NULLS LAST, priority` |
| 今日到期 | `SELECT * FROM tasks WHERE date(due_date/1000, 'unixepoch') = date('now') AND status='pending'` |
| 邮件关联任务 | `SELECT * FROM tasks WHERE json_extract(source_ref, '$.email_id') = 'xxx'` |
| 智能排序（今日焦点） | 内存计算：综合评分 = 紧急度×0.4 + 时效性×0.3 + 能量匹配×0.2 + 快速 wins×0.1 |
| 全文搜索 | `SELECT t.* FROM tasks t JOIN tasks_fts f ON t.rowid = f.rowid WHERE tasks_fts MATCH '关键词'` |
| 暂缓到期唤醒 | `SELECT * FROM tasks WHERE status='snoozed' AND snoozed_until <= ?` |

---

## 数据流图示

```
创建任务
  │
  ├─► AI提取 ──► 写入tasks表(status=pending, source_type=extracted)
  │                └─► 触发FTS索引更新
  │                └─► 写入"待确认"分组缓存
  │
  ├─► 用户手动 ──► 解析NLP ──► 写入tasks表(source_type=manual)
  │                └─► 直接进入主列表缓存
  │
  └─► 模板/周期 ──► 复制结构 ──► 写入tasks表
                   └─► 关联模板使用计数

状态变更
  │
  ├─► 用户操作 ──► UPDATE tasks SET status=?, status_history=json_append(...)
  │                └─► 触发器更新search_text
  │                └─► 失效相关列表缓存
  │
  └─► 系统唤醒 ──► 暂缓到期 ──► UPDATE status='pending' WHERE snoozed_until<=now
                   └─► 推送桌面通知

查询优化
  │
  ├─► 首次加载 ──► 从DB读取 ──► 写入内存缓存 ──► 返回
  │
  └─► 后续查询 ──► 检查缓存有效性 ──► 命中则返回
                   └─► 未命中/失效 ──► 回源DB ──► 更新缓存
```

---

## 时间字段规范

> **本文档是 tasks 表时间字段类型的权威来源。`userDataStorageDesign.md` 中的 tasks 简化版以本文档为准。**

所有时间字段均使用 **INTEGER（Unix 毫秒时间戳）**：

```sql
due_date INTEGER,          -- Unix 毫秒时间戳，如 1705312800000
due_time INTEGER,          -- Unix 毫秒时间戳（精确到分钟）
snoozed_until INTEGER,     -- Unix 毫秒时间戳
created_at INTEGER,        -- Unix 毫秒时间戳
updated_at INTEGER,        -- Unix 毫秒时间戳
completed_at INTEGER,      -- Unix 毫秒时间戳
```

Python 中的转换：
```python
import time
now_ms = int(time.time() * 1000)                    # 当前时间的毫秒时间戳
from datetime import datetime
dt = datetime.fromtimestamp(timestamp_ms / 1000)    # 毫秒时间戳 → datetime
```

---

## 桌面通知实现（PyQt6）

任务提醒通过 `QSystemTrayIcon` 实现，完整实现见 `tech_spec.md` 第8节。

**触发条件：**

| 事件 | 通知内容 | 条件 |
|------|---------|------|
| 任务即将到期 | "任务提醒: {title}" | `due_date` 在 30 分钟内 且 `status='pending'` |
| 暂缓任务到期 | 状态自动改回 `pending` | `snoozed_until <= now` |

**检查机制：** 在 qasync 事件循环中用 `asyncio.create_task` 每分钟运行一次检查协程，发现到期任务后通过 Qt Signal 触发通知弹窗。

---



