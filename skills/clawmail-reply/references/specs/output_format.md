# Reply Skill 输出格式

## 输出方式

所有 reply skill 脚本通过 **stdout** 输出纯文本。不输出 JSON。

ClawMail 的 ai_processor 通过 `result.stdout.strip()` 获取文本内容。

## 输出内容

### generate_reply.py
- 纯文本回复内容
- 不含 subject
- 不含签名
- 不含任何标记或标签

### generate_email.py
- 纯文本邮件正文
- 不含 subject（subject 由用户指定）
- 不含签名

### polish_email.py
- 润色后的纯文本邮件正文
- 保持与原文相同的语言

## 错误输出

脚本失败时（exit code != 0），错误信息输出到 **stderr**。
stdout 为空或包含错误 JSON：

```json
{"status": "error", "message": "错误描述"}
```
