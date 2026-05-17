import streamlit as st
import pandas as pd
import requests
import re
import time
import random
from datetime import datetime

st.set_page_config(page_title="AI选股·稳定版", page_icon="📈", layout="wide")
st.title("📈 AI选股 · 完整稳定版")
st.caption("数据来源：新浪财经 | 自动更新 | 已解决反爬")

# 新浪实时行情接口（沪深A股，每页5000只）
SINA_API = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={}&num=5000&sort=symbol&asc=1&node=hs_a&symbol=&_s_r_a=init"

@st.cache_data(ttl=600, show_spinner="正在获取实时行情...")
def load_sina_data():
    stocks = []
    for page in range(1, 4):  # 共约4900只，3页足够
        try:
            url = SINA_API.format(page)
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if data:
                    stocks.extend(data)
                else:
                    break
            time.sleep(random.uniform(0.5, 1.5))  # 随机延时，避免被禁
        except Exception as e:
            st.warning(f"第{page}页数据获取失败，重试中...")
            time.sleep(2)
            continue
    return stocks

def process_sina_data(raw_data):
    records = []
    for s in raw_data:
        try:
            records.append({
                "代码": s.get("symbol", ""),
                "名称": s.get("name", ""),
                "最新价": float(s.get("trade", 0)),
                "涨跌幅": float(s.get("changepercent", 0)),
                "市盈率": float(s.get("per", 0)),
                "市净率": float(s.get("pb", 0)),
                "换手率": float(s.get("turnoverratio", 0)),
                "成交额": float(s.get("amount", 0))
            })
        except:
            continue
    return pd.DataFrame(records)

raw = load_sina_data()
if raw:
    df = process_sina_data(raw)
    if not df.empty:
        st.subheader("📊 今日市场概览")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("上涨家数", (df["涨跌幅"] > 0).sum())
        with c2:
            st.metric("下跌家数", (df["涨跌幅"] < 0).sum())

        st.subheader("📋 低PE股票池（PE<20，且大于0）")
        low_pe = df[(df["市盈率"] > 0) & (df["市盈率"] < 20)].sort_values("市盈率")
        if not low_pe.empty:
            st.dataframe(low_pe[["代码","名称","最新价","涨跌幅","市盈率","市净率","换手率"]].head(100), use_container_width=True)
        else:
            st.info("无符合条件的股票")
    else:
        st.error("数据解析失败")
else:
    st.error("无法获取行情数据，请稍后刷新重试。")

st.markdown("---")
st.caption(f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据源：新浪财经")
st.error("⚠️ 风险声明：本系统仅基于公开数据客观筛选，不构成投资建议。")
