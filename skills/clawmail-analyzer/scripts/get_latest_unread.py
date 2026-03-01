#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取最新未读邮件
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from get_email import get_latest_unread
import json

if __name__ == "__main__":
    results = get_latest_unread()
    print(json.dumps(results, ensure_ascii=False, indent=2))
