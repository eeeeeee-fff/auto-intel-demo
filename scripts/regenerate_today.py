"""重新生成今天的早报数据"""
from app.db import get_engine
from app.services.dashboard import build_today_digest
from datetime import date
from sqlalchemy.orm import Session

# 创建数据库会话
engine = get_engine()
session = Session(bind=engine)

try:
    # 重新生成今天的早报
    today = date.today()
    print(f"正在重新生成 {today} 的早报数据...")
    
    digest = build_today_digest(session, target_date=today)
    
    print(f"✅ 早报数据已重新生成！")
    print(f"   日期：{digest.digest_date}")
    print(f"   文章数：{digest.article_count}")
    print(f"   重大事件：{digest.major_event_count}")
    print(f"\n现在刷新网页即可看到新的 AI 标题")
finally:
    session.close()
