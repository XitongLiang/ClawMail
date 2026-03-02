#!/usr/bin/env python3
"""一次性迁移：修复 key=None 的 urgency_signal/summary_preference 记录 + 清除精确重复。

用法:
    python scripts/migrate_memory_keys.py                # 预览（dry-run）
    python scripts/migrate_memory_keys.py --apply        # 实际执行
"""
import json
import sqlite3
import sys
from collections import defaultdict

DB_PATH = r"C:\Users\a\clawmail_data\clawmail.db"


def main():
    apply = "--apply" in sys.argv

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, user_account_id, memory_type, memory_key, memory_content, "
        "confidence_score, evidence_count FROM user_preference_memory "
        "ORDER BY memory_type, memory_key"
    )
    rows = cur.fetchall()
    print(f"当前记忆总数: {len(rows)}")

    # ── Phase 1: 修复 key=None 的记忆 ──
    key_fixes = 0
    for r in rows:
        mid, account_id, mtype, mkey, mcontent_raw, conf, ev = r
        if mkey is not None:
            continue
        content = json.loads(mcontent_raw) if mcontent_raw else {}

        new_key = None
        if mtype == "urgency_signal" and isinstance(content, dict):
            new_key = content.get("signal")
        elif mtype == "summary_preference" and isinstance(content, dict):
            new_key = content.get("preference_type")
        elif mtype == "response_pattern" and isinstance(content, dict):
            ctx = content.get("context", "")
            pref = content.get("preference", "")
            new_key = f"通用:{ctx}" if ctx else f"通用:{pref[:20]}" if pref else None

        if new_key:
            print(f"  KEY FIX: [{mtype}] id={mid[:12]}  None → '{new_key}'")
            if apply:
                cur.execute(
                    "UPDATE user_preference_memory SET memory_key=? WHERE id=?",
                    (new_key, mid),
                )
            key_fixes += 1

    print(f"\nPhase 1: {key_fixes} 条 key 修复")

    # ── Phase 2: 清除精确重复（同 type+key+content）──
    # 重新读取（key 可能已更新）
    if apply:
        conn.commit()
    cur.execute(
        "SELECT id, user_account_id, memory_type, memory_key, memory_content, "
        "confidence_score, evidence_count FROM user_preference_memory "
        "ORDER BY memory_type, memory_key, confidence_score DESC"
    )
    rows = cur.fetchall()

    META_KEYS = {"_source", "extracted_date", "last_updated"}
    groups = defaultdict(list)
    for r in rows:
        mid, account_id, mtype, mkey, mcontent_raw, conf, ev = r
        content = json.loads(mcontent_raw) if mcontent_raw else {}
        # 去掉元字段后的核心内容作为签名
        if isinstance(content, dict):
            core = {k: v for k, v in content.items() if k not in META_KEYS}
            sig = json.dumps(core, sort_keys=True, ensure_ascii=False)
        else:
            sig = str(content).strip()
        groups[(mtype, mkey, sig)].append((mid, conf, ev))

    delete_ids = []
    merge_targets = []
    for (mtype, mkey, sig), entries in groups.items():
        if len(entries) <= 1:
            continue
        # 保留 confidence 最高的（已按 DESC 排序），其余删除
        keep = entries[0]
        dups = entries[1:]
        total_ev = sum(e[2] for e in entries)
        max_conf = max(e[1] for e in entries)
        print(f"  DEDUP: [{mtype}] key={mkey}  {len(entries)} 条 → 保留 {keep[0][:12]}  "
              f"删除 {len(dups)} 条  evidence={total_ev}")
        for d in dups:
            delete_ids.append(d[0])
        merge_targets.append((keep[0], total_ev, max_conf))

    if apply:
        for did in delete_ids:
            cur.execute("DELETE FROM user_preference_memory WHERE id=?", (did,))
        for mid, ev, conf in merge_targets:
            cur.execute(
                "UPDATE user_preference_memory SET evidence_count=?, confidence_score=? WHERE id=?",
                (ev, conf, mid),
            )
        conn.commit()

    print(f"\nPhase 2: 删除 {len(delete_ids)} 条精确重复")

    # ── 汇总 ──
    cur.execute("SELECT COUNT(*) FROM user_preference_memory")
    final = cur.fetchone()[0]
    print(f"\n{'执行' if apply else '预览'}完成: {len(rows)} → {final if apply else len(rows) - len(delete_ids)} 条")
    if not apply:
        print("\n使用 --apply 参数实际执行迁移")

    conn.close()


if __name__ == "__main__":
    main()
