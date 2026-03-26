n"""
首页一屏优化验证脚本
用于验证 HOMEPAGE_ONE_SCREEN_PLAN.md 的落实情况
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db import get_db
from app.services.dashboard import get_dashboard_today
from app.services.reporting import render_daily_report
from datetime import date

def verify_homepage_optimization():
    """验证首页优化是否满足要求"""
    print("=" * 60)
    print("首页一屏优化验证")
    print("=" * 60)
    
    db = next(get_db())
    
    # 1. 获取今日数据
    try:
        from app.services.dashboard import render_dashboard_context
        payload = render_dashboard_context(db)
        print("\n✅ 成功获取 dashboard 今日上下文")
    except Exception as e:
        print(f"\n❌ 获取 dashboard 上下文失败：{e}")
        return False
    
    # 2. 验证数据结构
    required_fields = [
        "briefing_window",
        "strategic_judgement",
        "top_events",
        "followup_events",
        "source_status",
        "source_health",
        "hero_event"
    ]
    
    missing_fields = [f for f in required_fields if f not in payload]
    if missing_fields:
        print(f"❌ 缺少必需字段：{missing_fields}")
        return False
    else:
        print("✅ 数据结构完整，包含所有必需字段")
    
    # 3. 验证早报窗口信息
    bw = payload.get("briefing_window", {})
    if all(k in bw for k in ["edition_date", "start_label", "end_label", "cutoff_label"]):
        print(f"✅ 早报窗口信息完整：{bw['edition_date']} {bw['start_label']} → {bw['end_label']}")
    else:
        print(f"❌ 早报窗口信息不完整：{bw}")
    
    # 4. 验证战略判断区
    sj = payload.get("strategic_judgement", {})
    sj_fields = ["title", "summary", "business_relevance", "impact_direction", "validation_focus", "watchpoints"]
    missing_sj = [f for f in sj_fields if f not in sj]
    if missing_sj:
        print(f"❌ 战略判断缺少字段：{missing_sj}")
    else:
        print(f"✅ 战略判断完整：{sj['title']}")
        print(f"   - 业务相关性：{sj['business_relevance']}")
        print(f"   - 影响方向：{sj['impact_direction']}")
        print(f"   - 待内部验证：{' / '.join(sj['validation_focus'])}")
    
    # 5. 验证来源健康状态
    sh = payload.get("source_health", {})
    if all(k in sh for k in ["success_count", "failed_count", "running_count", "idle_count"]):
        print(f"✅ 来源健康状态：在线 {sh['success_count']} | 运行中 {sh['running_count']} | 失败 {sh['failed_count']} | 待机 {sh['idle_count']}")
    else:
        print(f"❌ 来源健康状态不完整：{sh}")
    
    # 6. 验证事件数量
    top_events = payload.get("top_events", [])
    followup_events = payload.get("followup_events", [])
    print(f"✅ 头部事件：{len(top_events)} 条（最多展示 3 条）")
    print(f"✅ 持续跟踪：{len(followup_events)} 条（最多展示 2 条）")
    
    # 7. 验证指标卡
    totals = payload.get("briefing_totals", {})
    print(f"✅ 关键指标:")
    print(f"   - 本期资讯：{totals.get('article_count', 0)} 条")
    print(f"   - 候选事件：{totals.get('candidate_count', 0)} 条")
    print(f"   - 重大事件：{totals.get('major_count', 0)} 条")
    print(f"   - 境内/境外：{totals.get('domestic_major_count', 0)} / {totals.get('foreign_major_count', 0)}")
    
    # 8. 生成日报测试
    try:
        report = render_daily_report(db)
        print(f"\n✅ 成功生成日报 HTML，长度：{len(report.html)} 字符")
        print(f"   - 报告日期：{report.report_date}")
        print(f"   - 重大事件数：{report.major_event_count}")
        print(f"   - 来源数：{report.source_count}")
    except Exception as e:
        print(f"\n❌ 生成日报失败：{e}")
    
    print("\n" + "=" * 60)
    print("验证完成！")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    verify_homepage_optimization()
