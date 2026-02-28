# ClawMail Testing Guide - Synthetic Email Account

## Overview

This guide shows you how to test ClawMail features using synthetic test emails without needing a real email account or IMAP sync.

**Benefits:**
- ✅ No need for real email account
- ✅ Instant email creation
- ✅ Full control over test scenarios
- ✅ Test personalization, AI features, UI
- ✅ Reproducible test cases

---

## Setup

### 1. Ensure ClawMail is installed

```bash
cd ~/Desktop/projectA
# Make sure ClawMail database exists
ls ~/clawmail_data/clawmail.db
```

### 2. Test scripts are ready

```bash
cd tests
ls -la
# Should see:
# - synthetic_email_injector.py
# - create_test_email.py
```

---

## Usage Methods

### **Method 1: Quick Interactive Email Creator (Easiest)**

```bash
cd ~/Desktop/projectA/tests
python create_test_email.py
```

**Interactive prompts:**
```
Select email type:
1. 会议确认 (Meeting confirmation)
2. 紧急任务 (Urgent task)
3. 信息请求 (Information request)
4. Newsletter (低优先级)
5. 感谢信 (Thank you note)
6. 投诉/问题 (Complaint/Issue)
7. 自定义 (Custom)

Choice (1-7): 1

--- 模板内容 ---
发件人: 张三 <colleague@company.com>
主题: 明天的会议确认
正文: 明天下午2点的会议你能参加吗？
标签: 工作, 会议

是否编辑? (y/n): n

✅ 测试邮件创建成功!
```

---

### **Method 2: Batch Inject Predefined Scenarios**

Inject 10 diverse test emails at once:

```bash
python synthetic_email_injector.py --batch 10
```

**Output:**
```
[Injector] Connected to database: ~/clawmail_data
[Injector] Created test account: uuid-xxx
[Injector] Email: test@synthetic.clawmail

[Injector] Injecting 10 test emails...

[Injector] ✅ Injected email: xxx
           From: colleague@company.com
           Subject: 明天下午2点的会议确认

[Injector] ✅ Injected email: yyy
           From: boss@company.com
           Subject: 【紧急】客户报告需要在周五前完成

... (8 more emails)

[Injector] ✅ Successfully injected 10 emails
```

**Predefined scenarios included:**
1. Meeting confirmation request
2. Urgent task assignment
3. Newsletter (low priority)
4. Information request
5. Thank you note
6. Automated notification
7. Complaint/Issue report
8. Collaboration invitation
9. Document request with deadline
10. Follow-up email

---

### **Method 3: Custom Email via Command Line**

Create custom email interactively:

```bash
python synthetic_email_injector.py --custom
```

**Prompts:**
```
=== Custom Email Creator ===
From address: client@test.com
From name (optional): 测试客户
Subject: 关于合作的咨询
Body (end with Ctrl+D on Unix or Ctrl+Z on Windows):
您好，我们对贵公司的产品很感兴趣。
能否安排时间详细沟通一下？
谢谢！
^D  (or ^Z on Windows)

Labels (comma-separated, optional): 客户,咨询

✅ Injected custom email: xxx
```

---

### **Method 4: Programmatic Injection (For Scripts)**

```python
from synthetic_email_injector import SyntheticEmailInjector

# Initialize
injector = SyntheticEmailInjector()
account_id = injector.get_or_create_test_account()

# Inject custom email
email_id = injector.inject_custom_email(
    account_id=account_id,
    from_addr="test@example.com",
    subject="测试邮件",
    body="这是一封测试邮件",
    from_name="测试用户",
    labels=["测试"]
)

print(f"Created email: {email_id}")
```

---

## Test Scenarios Reference

### **Scenario 1: Meeting Confirmation**
```
From: colleague@company.com (张三)
Subject: 明天下午2点的会议确认
Body: 明天下午2点的季度总结会议你能参加吗？
      我们需要讨论Q1的预算和下季度计划...
Labels: 工作, 会议
```

**Test focus:** Reply generation with confirmation stance

---

### **Scenario 2: Urgent Task**
```
From: boss@company.com (李经理)
Subject: 【紧急】客户报告需要在周五前完成
Body: 刚接到通知，ABC客户需要在本周五下午5点前收到季度分析报告...
Labels: 工作, 紧急
```

**Test focus:** Importance scoring (should be high), urgency detection

---

### **Scenario 3: Newsletter (Low Priority)**
```
From: newsletter@techcompany.com (TechCompany Weekly)
Subject: TechCompany Weekly Newsletter - 本周技术动态
Body: 【本周头条】...
Labels: Newsletter
```

**Test focus:** Automated content detection, low importance scoring

---

### **Scenario 4: Information Request**
```
From: client@customer.com (王总)
Subject: Re: 项目进度咨询
Body: 上次讨论的合作项目现在进展如何？
      能否提供一份最新的进度报告？
Labels: 客户, 重要
```

**Test focus:** Reply generation with informative stance

---

### **Scenario 5: Thank You Note**
```
From: partner@partner.com (赵总监)
Subject: 感谢上周的技术支持
Body: 非常感谢您上周在技术对接会上的详细讲解...
Labels: 合作伙伴
```

**Test focus:** Low action items, acknowledgment detection

---

## Testing Workflow

### **Step 1: Inject Test Emails**

```bash
# Create test account and inject 10 emails
cd ~/Desktop/projectA/tests
python synthetic_email_injector.py --batch 10
```

### **Step 2: Open ClawMail**

```bash
cd ~/Desktop/projectA
python -m clawmail.ui.app
```

### **Step 3: Verify Emails Appear**

- Check INBOX for 10 new emails
- Verify they show as "unread"
- Account name: "Synthetic Test Account"

### **Step 4: Test AI Features**

**Test Importance Scoring:**
1. Select newsletter email → Should have low importance (20-30)
2. Select urgent task email → Should have high importance (80-90)
3. Manually adjust score → Test MemSkill Executor learning

**Test Summarization:**
1. Click on meeting confirmation email
2. Check AI-generated summary
3. Click 👎 if summary is bad → Test feedback loop

**Test Reply Generation:**
1. Click meeting confirmation email
2. Click "回复" button
3. Select stance: "同意并确认时间"
4. Select tone: "正式严肃"
5. Click "AI 生成回复"
6. Verify generated reply is appropriate

### **Step 5: Test Personalization Learning**

```bash
# Inject same sender multiple times
python create_test_email.py
# Choose: 1 (Meeting confirmation)
# From: colleague@company.com

# In ClawMail UI:
# 1. Adjust importance to 90 → High priority
# 2. Wait for Executor to learn
# 3. Inject another email from same sender
python create_test_email.py
# Choose: 1 again

# 4. Check if new email from colleague@company.com
#    automatically gets higher importance score
```

---

## Advanced Usage

### **Inject Specific Account**

If you have multiple accounts in ClawMail:

```bash
# List accounts first
python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))
from clawmail.infrastructure.database.storage_manager import ClawDB
import os

db = ClawDB(os.path.expanduser('~/clawmail_data'))
for acc in db.list_accounts():
    print(f'{acc.id}: {acc.email_address}')
"

# Inject to specific account
python synthetic_email_injector.py --account-id <uuid-from-above> --batch 5
```

---

### **Inject Multiple Batches**

```bash
# Inject 30 emails (will repeat scenarios)
python synthetic_email_injector.py --batch 30
```

---

### **Create Email Reply Chain**

```python
from synthetic_email_injector import SyntheticEmailInjector
from datetime import datetime, timedelta

injector = SyntheticEmailInjector()
account_id = injector.get_or_create_test_account()

# Original email
thread_id = "thread_meeting_12345"
email1 = {
    "from_address": "boss@company.com",
    "from_name": "李经理",
    "subject": "下周一的会议",
    "body_text": "下周一上午10点开会讨论项目，请确认。",
    "thread_id": thread_id,
    "date_received": datetime.utcnow() - timedelta(days=1)
}
injector.inject_email(email1, account_id)

# Reply
email2 = {
    "from_address": "colleague@company.com",
    "from_name": "张三",
    "subject": "Re: 下周一的会议",
    "body_text": "收到，我会准时参加。",
    "thread_id": thread_id,
    "date_received": datetime.utcnow() - timedelta(hours=20)
}
injector.inject_email(email2, account_id)

# Follow-up
email3 = {
    "from_address": "boss@company.com",
    "from_name": "李经理",
    "subject": "Re: 下周一的会议",
    "body_text": "好的，会议室已预订。请提前准备材料。",
    "thread_id": thread_id,
    "date_received": datetime.utcnow() - timedelta(hours=18)
}
injector.inject_email(email3, account_id)
```

---

## Troubleshooting

### **Problem: Emails don't appear in ClawMail**

**Solution:**
1. Restart ClawMail UI
2. Check if test account is enabled:
   - Settings → Account Management
   - "Synthetic Test Account" should be listed
3. Check database:
   ```bash
   sqlite3 ~/clawmail_data/clawmail.db "SELECT COUNT(*) FROM emails;"
   ```

---

### **Problem: "test@synthetic.clawmail" account exists but emails go to wrong account**

**Solution:**
```bash
# List all accounts
python -c "
from clawmail.infrastructure.database.storage_manager import ClawDB
import os
db = ClawDB(os.path.expanduser('~/clawmail_data'))
for acc in db.list_accounts():
    print(f'{acc.id}: {acc.email_address}')
"

# Use specific account ID
python synthetic_email_injector.py --account-id <correct-uuid> --batch 5
```

---

### **Problem: Want to delete all test emails**

**Solution:**
```bash
# Delete all emails from synthetic account
python -c "
from clawmail.infrastructure.database.storage_manager import ClawDB
import os

db = ClawDB(os.path.expanduser('~/clawmail_data'))

# Find synthetic account
accounts = db.list_accounts()
for acc in accounts:
    if acc.email_address == 'test@synthetic.clawmail':
        count = db.delete_all_emails(account_id=acc.id)
        print(f'Deleted {count} test emails')
        break
"
```

---

## Testing Checklist

### **Basic Features:**
- [ ] Emails appear in INBOX
- [ ] Read/unread status works
- [ ] Email details view shows correctly
- [ ] Folder operations work (move to trash, etc.)

### **AI Features:**
- [ ] Importance scoring works
- [ ] Summary generation works
- [ ] Action items extraction works
- [ ] Categories assigned correctly

### **Personalization (MemSkill):**
- [ ] Can adjust importance score
- [ ] Executor runs after correction (check logs)
- [ ] Memories stored in database:
  ```bash
  sqlite3 ~/clawmail_data/clawmail.db \
    "SELECT COUNT(*) FROM user_preference_memory;"
  ```
- [ ] Next email from same sender uses learned preference
- [ ] Summary feedback improves future summaries

### **Reply Generation:**
- [ ] AI generates appropriate reply
- [ ] Stance selection works (agree/decline/etc.)
- [ ] Tone selection works (formal/casual)
- [ ] User notes incorporated into draft
- [ ] Personalization improves replies over time

---

## Next Steps

### **Create Custom Test Suite**

1. **Define your specific test scenarios:**
   ```python
   # my_test_scenarios.py
   scenarios = [
       {"from": "client1@test.com", "subject": "...", ...},
       {"from": "client2@test.com", "subject": "...", ...},
   ]
   ```

2. **Inject all scenarios:**
   ```python
   for scenario in scenarios:
       injector.inject_email(scenario, account_id)
   ```

3. **Test systematically:**
   - Document expected vs actual behavior
   - Track correction frequency
   - Measure personalization improvement

---

## Tips

1. **Use consistent sender addresses** for personalization testing
   - `colleague@company.com` for work emails
   - `newsletter@company.com` for low-priority
   - `boss@company.com` for urgent tasks

2. **Add realistic variety:**
   - Different times of day
   - Different email lengths
   - Various tones (urgent, casual, formal)

3. **Test edge cases:**
   - Very long emails (>1000 words)
   - Very short emails (1 sentence)
   - Emails with special characters
   - Emails in mixed Chinese/English

4. **Monitor database growth:**
   ```bash
   du -sh ~/clawmail_data/
   sqlite3 ~/clawmail_data/clawmail.db \
     "SELECT COUNT(*) FROM emails;"
   ```

---

## Summary

You now have a complete synthetic testing environment:

✅ **No real email account needed**
✅ **10+ predefined scenarios**
✅ **Custom email creator**
✅ **Batch injection tool**
✅ **Full ClawMail feature testing**

Start testing:
```bash
cd ~/Desktop/projectA/tests
python create_test_email.py
```

Happy testing! 🎉
