import streamlit as st
import pandas as pd
import requests
import time
import random
from datetime import datetime

st.set_page_config(page_title="AI选股·稳定版", page_icon="📈", layout="wide")
st.title("📈 AI选股 · 完整版")
st.caption("数据源：新浪财经 | 自动更新 | 反爬已优化")

# 新浪实时行情（沪深A股，每页5000只）
SINA_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={}&num=5000&sort=symbol&asc=1&node=hs_a"

@st.cache_data(ttl=600, show_spinner="正在获取实时行情...")
def fetch_all_stocks():
    stocks = []
    for page in range(1, 4):   # 总共约4900只，3页足够
        try:
            url = SINA_URL.format(page)
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data:
                    stocks.extend(data)
                else:
                    break
            # 随机延时，避免反爬
            time.sleep(random.uniform(0.3, 0.8))
        except:
            continue
    return stocks

def process_stocks(raw):
    records = []
    for s in raw:
        try:
            pe = float(s.get("per", 0))
            if pe <= 0:
                continue
            records.append({
                "代码": s.get("symbol", ""),
                "名称": s.get("name", ""),
                "最新价": float(s.get("trade", 0)),
                "涨跌幅": float(s.get("changepercent", 0)),
                "市盈率": pe,
                "市净率": float(s.get("pb", 0)),
                "换手率": float(s.get("turnoverratio", 0)),
                "成交额": float(s.get("amount", 0))
            })
        except:
            continue
    return pd.DataFrame(records)

raw = fetch_all_stocks()
if raw:
    df = process_stocks(raw)
    if not df.empty:
        # 市场概览
        st.subheader("📊 今日市场概览")
        c1, c2 = st.columns(2)
        up = (df["涨跌幅"] > 0).sum()
        down = (df["涨跌幅"] < 0).sum()
        c1.metric("上涨家数", up)
        c2.metric("下跌家数", down)

        # 低PE股票池
        st.subheader("📋 低PE股票池（市盈率<20）")
        low_pe = df[df["市盈率"] < 20].sort_values("市盈率")
        st.dataframe(low_pe[["代码","名称","最新价","涨跌幅","市盈率","市净率","换手率"]].head(100),
                     use_container_width=True)
    else:
        st.error("数据解析失败，请刷新重试。")
else:
    st.error("无法获取行情数据，请稍后刷新重试。")

st.markdown("---")
st.caption(f"更新时间：{datetime.now().strftime('%H:%M:%S')} | 数据源：新浪财经")
st.error("⚠️ 风险声明：不构成投资建议，仅客观筛选。")
