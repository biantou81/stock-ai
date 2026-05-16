import streamlit as st
import pandas as pd
from datetime import datetime
import requests

st.set_page_config(page_title="AI选股·极简版", page_icon="📈", layout="wide")
st.title("📈 AI选股 · 极简测试版")
st.caption("测试部署流程 | 数据来源：东方财富公开接口")

@st.cache_data(ttl=300, show_spinner="正在获取实时行情...")
def load_data():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "50", "po": "1", "np": "1",
            "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f9,f12,f14,f15,f16,f17,f18,f20"
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        stocks = data.get("data", {}).get("diff", [])
        records = []
        for s in stocks:
            records.append({
                "代码": s.get("f12", ""),
                "名称": s.get("f14", ""),
                "最新价": s.get("f2", ""),
                "涨跌幅": s.get("f3", ""),
                "市盈率": s.get("f9", ""),
                "换手率": s.get("f8", "")
            })
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"数据获取失败：{e}")
        return pd.DataFrame()

data = load_data()

if not data.empty:
    st.subheader("📊 今日市场概览")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("上涨家数", (pd.to_numeric(data["涨跌幅"], errors='coerce') > 0).sum())
    with c2:
        st.metric("下跌家数", (pd.to_numeric(data["涨跌幅"], errors='coerce') < 0).sum())
    st.subheader("📋 低PE股票（PE<20）")
    data["市盈率"] = pd.to_numeric(data["市盈率"], errors="coerce")
    low_pe = data[(data["市盈率"] > 0) & (data["市盈率"] < 20)]
    if not low_pe.empty:
        st.dataframe(low_pe.head(50))
    else:
        st.info("无符合条件的股票")
else:
    st.warning("暂未获取到数据")

st.markdown("---")
st.caption(f"更新于 {datetime.now().strftime('%H:%M:%S')}")
