#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive Test Email Creator for ClawMail

Simple CLI tool to quickly create test emails.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from synthetic_email_injector import SyntheticEmailInjector


def create_quick_email():
    """Interactive quick email creator."""
    print("\n" + "="*60)
    print("  ClawMail - Quick Test Email Creator")
    print("="*60 + "\n")

    injector = SyntheticEmailInjector()
    account_id = injector.get_or_create_test_account()

    print("\nSelect email type:")
    print("1. 会议确认 (Meeting confirmation)")
    print("2. 紧急任务 (Urgent task)")
    print("3. 信息请求 (Information request)")
    print("4. Newsletter (低优先级)")
    print("5. 感谢信 (Thank you note)")
    print("6. 投诉/问题 (Complaint/Issue)")
    print("7. 自定义 (Custom)")
    print()

    choice = input("Choice (1-7): ").strip()

    templates = {
        "1": {
            "from": "colleague@company.com",
            "name": "张三",
            "subject": "明天的会议确认",
            "body": "明天下午2点的会议你能参加吗？",
            "labels": ["工作", "会议"]
        },
        "2": {
            "from": "boss@company.com",
            "name": "李经理",
            "subject": "【紧急】任务需要今天完成",
            "body": "这个任务比较紧急，请优先处理，今天下班前完成。",
            "labels": ["工作", "紧急"]
        },
        "3": {
            "from": "client@customer.com",
            "name": "王总",
            "subject": "请问项目进度",
            "body": "您好，能否提供一下项目的最新进度？谢谢。",
            "labels": ["客户"]
        },
        "4": {
            "from": "newsletter@tech.com",
            "name": "Tech Weekly",
            "subject": "本周技术资讯 Newsletter",
            "body": "本周技术动态：1. 新产品发布 2. 技术分享...",
            "labels": ["Newsletter"]
        },
        "5": {
            "from": "partner@company.com",
            "name": "赵总监",
            "subject": "感谢您的帮助",
            "body": "非常感谢您上次的技术支持，问题已经解决了。",
            "labels": ["合作伙伴"]
        },
        "6": {
            "from": "support@customer.com",
            "name": "客服部",
            "subject": "客户投诉反馈",
            "body": "收到客户投诉，反映服务响应时间过长，请协助处理。",
            "labels": ["客户服务", "待处理"]
        },
    }

    if choice == "7":
        # Custom email
        print("\n--- 自定义邮件 ---")
        from_addr = input("发件人邮箱: ")
        from_name = input("发件人姓名: ")
        subject = input("主题: ")
        body = input("正文: ")
        labels_str = input("标签 (逗号分隔): ")
        labels = [l.strip() for l in labels_str.split(',')] if labels_str else []

    elif choice in templates:
        template = templates[choice]
        from_addr = template["from"]
        from_name = template["name"]
        subject = template["subject"]
        body = template["body"]
        labels = template["labels"]

        # Allow editing
        print(f"\n--- 模板内容 ---")
        print(f"发件人: {from_name} <{from_addr}>")
        print(f"主题: {subject}")
        print(f"正文: {body}")
        print(f"标签: {', '.join(labels)}")
        print()

        edit = input("是否编辑? (y/n): ").lower()
        if edit == 'y':
            subject = input(f"主题 [{subject}]: ") or subject
            body = input(f"正文 [{body}]: ") or body

    else:
        print("无效选择")
        return

    # Inject email
    print("\n正在创建测试邮件...")
    email_id = injector.inject_custom_email(
        account_id,
        from_addr,
        subject,
        body,
        from_name,
        labels
    )

    print(f"\n✅ 测试邮件创建成功!")
    print(f"📧 邮件ID: {email_id}")
    print(f"📬 发件人: {from_name} <{from_addr}>")
    print(f"📝 主题: {subject}")
    print(f"\n💡 提示: 打开 ClawMail 即可查看该邮件")
    print()


if __name__ == "__main__":
    try:
        create_quick_email()
    except KeyboardInterrupt:
        print("\n\n已取消")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
