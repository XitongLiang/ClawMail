#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Synthetic Email Injector for ClawMail Testing

Injects test emails directly into ClawMail database without IMAP sync.
Useful for testing AI features, personalization, and UI.

Usage:
    python synthetic_email_injector.py --account-id <account_id>
    python synthetic_email_injector.py --scenario meeting_confirmation
    python synthetic_email_injector.py --batch 10
"""

import sys
import os
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.domain.models.email import Email


class SyntheticEmailInjector:
    """Generate and inject synthetic test emails into ClawMail database."""

    def __init__(self, data_dir: str = None):
        """Initialize injector with ClawMail database."""
        if data_dir is None:
            data_dir = os.path.expanduser("~/clawmail_data")

        self.db = ClawDB(data_dir)
        print(f"[Injector] Connected to database: {data_dir}")

    def get_or_create_test_account(self):
        """Get or create synthetic test account."""
        # Check if test account exists
        accounts = self.db.list_accounts()
        for acc in accounts:
            if acc.email_address == "test@synthetic.clawmail":
                print(f"[Injector] Using existing test account: {acc.id}")
                return acc.id

        # Create new test account
        account_id = str(uuid.uuid4())

        # Create minimal credentials (won't be used for sync)
        fake_credentials = json.dumps({
            "type": "synthetic",
            "email": "test@synthetic.clawmail",
            "note": "Synthetic test account - not a real email account"
        }).encode('utf-8')

        self.db.save_account(
            account_id=account_id,
            email_address="test@synthetic.clawmail",
            display_name="Synthetic Test Account",
            credentials_encrypted=fake_credentials,
            is_enabled=True
        )

        print(f"[Injector] Created test account: {account_id}")
        print(f"[Injector] Email: test@synthetic.clawmail")
        return account_id

    def inject_email(self, email_data: dict, account_id: str) -> str:
        """Inject a single synthetic email into database."""

        email_id = str(uuid.uuid4())

        # Create Email object
        email = Email(
            id=email_id,
            account_id=account_id,
            message_id=email_data.get('message_id', f"<{uuid.uuid4()}@synthetic.clawmail>"),
            thread_id=email_data.get('thread_id', f"thread_{uuid.uuid4()}"),
            from_address=email_data['from_address'],
            from_name=email_data.get('from_name', ''),
            to_addresses=email_data.get('to_addresses', ['test@synthetic.clawmail']),
            cc_addresses=email_data.get('cc_addresses', []),
            bcc_addresses=email_data.get('bcc_addresses', []),
            subject=email_data['subject'],
            body_text=email_data['body_text'],
            body_html=email_data.get('body_html', f"<p>{email_data['body_text']}</p>"),
            snippet=email_data['body_text'][:150],
            date_received=email_data.get('date_received', datetime.utcnow()),
            folder=email_data.get('folder', 'INBOX'),
            labels=email_data.get('labels', []),
            read_status=email_data.get('read_status', 'unread'),
            flag_status=email_data.get('flag_status', 'none'),
            has_attachments=email_data.get('has_attachments', False),
            attachment_count=email_data.get('attachment_count', 0),
            importance_score=email_data.get('importance_score'),
            pinned=email_data.get('pinned', False)
        )

        # Save to database
        self.db.save_email(email)

        print(f"[Injector] ✅ Injected email: {email_id}")
        print(f"           From: {email_data['from_address']}")
        print(f"           Subject: {email_data['subject']}")

        return email_id

    def generate_test_scenarios(self) -> list:
        """Generate predefined test email scenarios."""

        now = datetime.utcnow()

        scenarios = [
            # Scenario 1: Meeting confirmation request
            {
                "from_address": "colleague@company.com",
                "from_name": "张三",
                "subject": "明天下午2点的会议确认",
                "body_text": """Hi，

明天下午2点的季度总结会议你能参加吗？我们需要讨论Q1的预算和下季度计划。

地点：会议室A
时长：预计1小时

请确认一下，谢谢！

张三""",
                "date_received": now - timedelta(hours=2),
                "labels": ["工作", "会议"],
            },

            # Scenario 2: Urgent task assignment
            {
                "from_address": "boss@company.com",
                "from_name": "李经理",
                "subject": "【紧急】客户报告需要在周五前完成",
                "body_text": """你好，

刚接到通知，ABC客户需要在本周五下午5点前收到季度分析报告。

请优先处理这个任务，如果有问题及时沟通。报告模板我已经发到你邮箱了。

谢谢配合！

李经理""",
                "date_received": now - timedelta(hours=1),
                "labels": ["工作", "紧急"],
                "read_status": "unread",
            },

            # Scenario 3: Newsletter (low priority)
            {
                "from_address": "newsletter@techcompany.com",
                "from_name": "TechCompany Weekly",
                "subject": "TechCompany Weekly Newsletter - 本周技术动态",
                "body_text": """【本周头条】

1. 新产品发布：XYZ功能上线
2. 技术分享：如何优化数据库性能
3. 团队动态：研发部门获得年度创新奖

点击查看详情 →

---
取消订阅 | 更新偏好设置""",
                "date_received": now - timedelta(days=1),
                "labels": ["Newsletter"],
            },

            # Scenario 4: Information request
            {
                "from_address": "client@customer.com",
                "from_name": "王总",
                "subject": "Re: 项目进度咨询",
                "body_text": """您好，

上次讨论的合作项目现在进展如何？能否提供一份最新的进度报告？

我们这边的董事会下周要审核，需要相关资料。

期待您的回复。

王总
ABC公司""",
                "date_received": now - timedelta(hours=4),
                "labels": ["客户", "重要"],
            },

            # Scenario 5: Thank you note
            {
                "from_address": "partner@partner.com",
                "from_name": "赵总监",
                "subject": "感谢上周的技术支持",
                "body_text": """您好，

非常感谢您上周在技术对接会上的详细讲解和耐心解答。

您分享的方案很有启发性，我们团队已经开始按照新的思路调整架构。

期待后续继续合作！

赵总监""",
                "date_received": now - timedelta(days=2),
                "labels": ["合作伙伴"],
                "read_status": "read",
            },

            # Scenario 6: Automated notification
            {
                "from_address": "noreply@system.com",
                "from_name": "System Notification",
                "subject": "【系统通知】您的账户安全验证",
                "body_text": """尊敬的用户，

检测到您的账户在新设备上登录。

时间：2026-02-28 10:23
设备：Windows PC
地点：北京

如果这不是您本人操作，请立即修改密码。

此邮件由系统自动发送，请勿回复。""",
                "date_received": now - timedelta(hours=6),
                "labels": ["系统通知"],
            },

            # Scenario 7: Complaint/Issue report
            {
                "from_address": "support@customer.com",
                "from_name": "客户服务部",
                "subject": "关于上周服务的投诉反馈",
                "body_text": """您好，

我们收到了一位客户（订单号：#12345）关于上周服务质量的反馈。

客户反映：
1. 响应时间过长（超过2小时）
2. 问题未完全解决
3. 缺少后续跟进

请协助调查并提供处理方案。

客服部""",
                "date_received": now - timedelta(hours=3),
                "labels": ["客户服务", "待处理"],
                "read_status": "unread",
            },

            # Scenario 8: Collaboration invitation
            {
                "from_address": "hr@company.com",
                "from_name": "人力资源部",
                "subject": "邀请参与新员工培训分享",
                "body_text": """您好，

鉴于您在技术领域的丰富经验，我们诚邀您在下月的新员工培训中做一次技术分享。

主题：《高效团队协作与技术最佳实践》
时间：3月15日下午3-4点
形式：线上/线下均可

如果您愿意参与，请回复确认。我们会提前发送详细安排。

人力资源部""",
                "date_received": now - timedelta(days=1, hours=2),
                "labels": ["内部"],
            },

            # Scenario 9: Document request with deadline
            {
                "from_address": "finance@company.com",
                "from_name": "财务部",
                "subject": "【提醒】2月份报销单据截止日期",
                "body_text": """各位同事，

2月份的报销单据提交截止日期为本周五（3月1日）下午5点。

请确保：
✓ 所有发票原件已扫描
✓ 报销申请表已填写完整
✓ 审批流程已完成

逾期将顺延至下月处理。

财务部""",
                "date_received": now - timedelta(hours=8),
                "labels": ["财务", "截止日期"],
            },

            # Scenario 10: Follow-up email
            {
                "from_address": "colleague@company.com",
                "from_name": "张三",
                "subject": "Re: 上次会议讨论的API文档",
                "body_text": """Hi，

上周五会议上你提到的API文档能否发我一份？

我们这边开发需要参考接口定义，目前进度有点卡住了。

如果方便的话今天能给到最好，谢谢！

张三""",
                "date_received": now - timedelta(minutes=30),
                "labels": ["工作", "待处理"],
                "read_status": "unread",
            },
        ]

        return scenarios

    def inject_batch(self, account_id: str, count: int = 10):
        """Inject a batch of test emails."""
        scenarios = self.generate_test_scenarios()

        if count > len(scenarios):
            # Repeat scenarios if needed
            scenarios = scenarios * (count // len(scenarios) + 1)

        scenarios = scenarios[:count]

        print(f"\n[Injector] Injecting {count} test emails...")
        print(f"[Injector] Account: {account_id}\n")

        injected_ids = []
        for scenario in scenarios:
            email_id = self.inject_email(scenario, account_id)
            injected_ids.append(email_id)

        print(f"\n[Injector] ✅ Successfully injected {len(injected_ids)} emails")
        print(f"[Injector] You can now view them in ClawMail UI")

        return injected_ids

    def inject_custom_email(self, account_id: str,
                           from_addr: str, subject: str, body: str,
                           from_name: str = "", labels: list = None):
        """Inject a single custom email."""
        email_data = {
            "from_address": from_addr,
            "from_name": from_name or from_addr.split('@')[0],
            "subject": subject,
            "body_text": body,
            "date_received": datetime.utcnow(),
            "labels": labels or [],
        }

        return self.inject_email(email_data, account_id)


def main():
    parser = argparse.ArgumentParser(
        description="Inject synthetic test emails into ClawMail"
    )
    parser.add_argument(
        '--account-id',
        help='Specific account ID to use (if not provided, uses/creates test account)'
    )
    parser.add_argument(
        '--batch',
        type=int,
        default=10,
        help='Number of emails to inject (default: 10)'
    )
    parser.add_argument(
        '--scenario',
        help='Inject specific scenario only (e.g., meeting_confirmation)'
    )
    parser.add_argument(
        '--custom',
        action='store_true',
        help='Interactive mode to create custom email'
    )

    args = parser.parse_args()

    injector = SyntheticEmailInjector()

    # Get or create account
    if args.account_id:
        account_id = args.account_id
        print(f"[Injector] Using account: {account_id}")
    else:
        account_id = injector.get_or_create_test_account()

    # Inject emails
    if args.custom:
        # Interactive mode
        print("\n=== Custom Email Creator ===")
        from_addr = input("From address: ")
        from_name = input("From name (optional): ")
        subject = input("Subject: ")
        print("Body (end with Ctrl+D on Unix or Ctrl+Z on Windows):")
        body_lines = []
        try:
            while True:
                line = input()
                body_lines.append(line)
        except EOFError:
            pass
        body = '\n'.join(body_lines)

        labels_input = input("Labels (comma-separated, optional): ")
        labels = [l.strip() for l in labels_input.split(',')] if labels_input else []

        email_id = injector.inject_custom_email(
            account_id, from_addr, subject, body, from_name, labels
        )
        print(f"\n✅ Injected custom email: {email_id}")

    elif args.scenario:
        # Inject specific scenario
        scenarios = injector.generate_test_scenarios()
        # Find matching scenario (simplified, matches subject keyword)
        matching = [s for s in scenarios if args.scenario.lower() in s['subject'].lower()]
        if matching:
            email_id = injector.inject_email(matching[0], account_id)
            print(f"\n✅ Injected scenario email: {email_id}")
        else:
            print(f"❌ No scenario matching '{args.scenario}' found")

    else:
        # Batch inject
        injector.inject_batch(account_id, args.batch)


if __name__ == "__main__":
    main()
