import streamlit as st
import pandas as pd
import requests
import time
import random
from datetime import datetime
import json

# ---------- 页面配置 ----------
st.set_page_config(page_title="AI选股·全能版", page_icon="📈", layout="wide")

# ---------- 初始化会话状态 ----------
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'holdings' not in st.session_state:
    st.session_state.holdings = {}
if 'page' not in st.session_state:
    st.session_state.page = 'home'

# ---------- 数据获取（新浪行情） ----------
@st.cache_data(ttl=600, show_spinner="正在获取实时行情...")
def load_market_data():
    stocks = []
    for page in range(1, 4):
        try:
            url = f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=5000&sort=symbol&asc=1&node=hs_a"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data:
                    stocks.extend(data)
                else:
                    break
            time.sleep(random.uniform(0.3, 0.8))
        except:
            continue
    return stocks

def process_market(raw):
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

# ---------- 财务数据（尝试用 akshare，失败则跳过） ----------
def get_financial_data():
    try:
        import akshare as ak
        df = ak.stock_financial_abstract_ths(symbol="全部", indicator="按年度")
        col_map = {
            "code": "code",
            "净资产收益率": "roe",
            "净利润增长率": "profit_growth",
            "营业收入增长率": "revenue_growth",
            "经营现金流/营业收入": "ocf_to_rev",
            "商誉/净资产": "goodwill_to_equity"
        }
        existing = {k: v for k, v in col_map.items() if k in df.columns}
        df = df[list(existing.keys())].rename(columns=existing)
        for c in ["roe", "profit_growth", "revenue_growth", "ocf_to_rev", "goodwill_to_equity"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except:
        return pd.DataFrame()

# ---------- 辅助函数：GARP筛选 ----------
def garp_filter(market_df, fin_df):
    if market_df.empty or fin_df.empty:
        return pd.DataFrame()
    df = pd.merge(market_df, fin_df, on="代码", how="left")
    for col in ["roe", "profit_growth", "ocf_to_rev", "goodwill_to_equity"]:
        if col not in df.columns:
            df[col] = pd.NA
    df["peg"] = df["市盈率"] / df["profit_growth"].replace(0, pd.NA)
    mask = (
        df["peg"].notna() & (df["peg"] < 1.0) &
        df["profit_growth"].notna() & (df["profit_growth"] > 15) &
        df["市盈率"].notna() & (df["市盈率"] < 20) &
        df["roe"].notna() & (df["roe"] > 10) &
        df["ocf_to_rev"].notna() & (df["ocf_to_rev"] > 0.08) &
        df["goodwill_to_equity"].notna() & (df["goodwill_to_equity"] < 0.30)
    )
    return df[mask].sort_values("profit_growth", ascending=False)

# ---------- 妖股识别 ----------
def monster_stocks(df):
    return df[(df["涨跌幅"] > 9) & (df["换手率"] > 15) & (df["市盈率"] < 100)].sort_values("换手率", ascending=False)

# ---------- 侧边栏导航 ----------
st.sidebar.title("📈 AI选股导航")
page = st.sidebar.radio("选择功能", ["市场概览", "AI对话诊断", "妖股雷达", "自选股（实验）"])

# ---------- 加载数据 ----------
raw = load_market_data()
if raw:
    market = process_market(raw)
else:
    market = pd.DataFrame()

# ---------- 页面：市场概览 ----------
if page == "市场概览":
    st.title("📊 市场概览")
    if market.empty:
        st.error("行情数据获取失败，请稍后刷新。")
    else:
        col1, col2 = st.columns(2)
        up = (market["涨跌幅"] > 0).sum()
        down = (market["涨跌幅"] < 0).sum()
        col1.metric("上涨家数", up)
        col2.metric("下跌家数", down)

        st.subheader("📋 低市盈率股票池（PE<20）")
        low_pe = market[market["市盈率"] < 20].sort_values("市盈率").head(100)
        st.dataframe(low_pe, use_container_width=True)

        # 尝试GARP
        fin = get_financial_data()
        if not fin.empty:
            st.subheader("🔍 GARP严格筛选结果（PEG<1, ROE>10%等）")
            garp_result = garp_filter(market, fin)
            if not garp_result.empty:
                st.success(f"共筛选出 {len(garp_result)} 只")
                st.dataframe(garp_result, use_container_width=True)
            else:
                st.info("暂无满足条件的股票")
        else:
            st.info("财务数据暂不可用（akshare接口波动），仅展示行情数据。")

# ---------- 页面：AI对话诊断 ----------
elif page == "AI对话诊断":
    st.title("🤖 AI诊断助手")
    st.caption("输入6位股票代码或股票名称，获取即时分析")
    
    # 显示历史对话
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    
    # 输入框
    prompt = st.chat_input("请输入股票代码或名称")
    if prompt:
        # 添加到历史
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        # 查找股票
        if market.empty:
            reply = "行情数据暂未加载，请先回到“市场概览”等待数据加载完成。"
        else:
            match = market[market["代码"].str.contains(prompt) | market["名称"].str.contains(prompt)]
            if match.empty:
                reply = f"未找到与“{prompt}”相关的股票。"
            else:
                s = match.iloc[0]
                reply = f"**{s['名称']} ({s['代码']})**\n"
                reply += f"- 最新价：{s['最新价']} 元\n"
                reply += f"- 涨跌幅：{s['涨跌幅']}%\n"
                reply += f"- 市盈率：{s['市盈率']}\n"
                reply += f"- 市净率：{s['市净率']}\n"
                reply += f"- 换手率：{s['换手率']}%\n\n"
                # 简单评价
                if s['市盈率'] < 20:
                    reply += "✅ 市盈率较低，估值相对合理。"
                else:
                    reply += "⚠️ 市盈率偏高，需关注成长性。"
                if s['涨跌幅'] > 9:
                    reply += "\n🔥 今日涨幅较大，短线注意回调风险。"
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()

# ---------- 页面：妖股雷达 ----------
elif page == "妖股雷达":
    st.title("🦅 妖股雷达")
    st.caption("实时监控涨幅>9%、换手率>15%的潜在妖股")
    if market.empty:
        st.error("行情数据不可用")
    else:
        monsters = monster_stocks(market)
        if not monsters.empty:
            st.warning(f"当前发现 {len(monsters)} 只妖股候选（高风险！）")
            st.dataframe(monsters, use_container_width=True)
        else:
            st.info("当前无妖股候选")

# ---------- 页面：自选股（实验） ----------
elif page == "自选股（实验）":
    st.title("⭐ 我的自选股")
    st.caption("在此输入代码添加自选，可查看实时行情")
    code = st.text_input("输入股票代码")
    if st.button("添加") and code:
        if code not in st.session_state.holdings:
            st.session_state.holdings[code] = {"name": code}
    st.write("当前自选：")
    if st.session_state.holdings:
        for c in st.session_state.holdings:
            if not market.empty:
                match = market[market["代码"] == c]
                if not match.empty:
                    s = match.iloc[0]
                    st.write(f"{s['名称']} {s['最新价']} 元  {s['涨跌幅']}%")
                else:
                    st.write(f"{c} 未找到行情")
            else:
                st.write(c)
    else:
        st.write("暂无自选股")

# ---------- 页脚 ----------
st.markdown("---")
st.caption(f"更新时间：{datetime.now().strftime('%H:%M:%S')} | 数据源：新浪财经 + akshare财务")
st.error("⚠️ 风险声明：本系统仅基于公开数据客观筛选，不构成投资建议。")
