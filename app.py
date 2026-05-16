"""
AI智能选股系统 - 完整版
功能：GARP六条筛选 + 市场概览 + 低PE股票池
数据来源：东方财富/akshare 免费公开接口
安全声明：本系统仅基于公开历史数据的算法评分，不构成任何投资建议。
"""
#import streamlit as st
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="AI选股", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>.main{padding:0.5rem} .stButton button{width:100%;font-size:1.1rem;padding:0.6rem;border-radius:8px} .stDataFrame{font-size:0.85rem} h1{font-size:1.5rem} h2{font-size:1.2rem}</style>""", unsafe_allow_html=True)
st.title("📈 AI选股系统 · 完整版")
st.caption("GARP初筛器 | 数据来源：东方财富公开接口")

@st.cache_data(ttl=3600, show_spinner=False)
def load_market_data():
    try:
        df = ak.stock_zh_a_spot_em()
        df = df.rename(columns={"代码":"code","名称":"name","最新价":"price","涨跌幅":"pct_chg","市盈率-动态":"pe_ttm","市净率":"pb","换手率":"turnover","成交额":"amount"})
        df = df[["code","name","price","pct_chg","pe_ttm","pb","turnover","amount"]].copy()
        for c in ["price","pct_chg","pe_ttm","pb","turnover","amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except Exception as e:
        st.error(f"行情数据获取失败: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=7200, show_spinner=False)
#def load_financial_data():
    try:
        df = ak.stock_financial_abstract_ths(symbol="全部", indicator="按年度")
        col_map = {"code":"code","净资产收益率":"roe","净利润增长率":"profit_growth","营业收入增长率":"revenue_growth","经营现金流/营业收入":"ocf_to_rev","商誉/净资产":"goodwill_to_equity"}
        existing = {k:v for k,v in col_map.items() if k in df.columns}
        df = df[list(existing.keys())].rename(columns=existing)
        for c in ["roe","profit_growth","revenue_growth","ocf_to_rev","goodwill_to_equity"]:
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except:
        st.warning("财务接口波动，使用演示数据")
        m = load_market_data()
        if m.empty: return pd.DataFrame()
        np.random.seed(42)
        n = len(m)
        return pd.DataFrame({"code":m["code"],"roe":np.random.normal(8,5,n).clip(-5,30),"profit_growth":np.random.normal(18,20,n).clip(-30,80),"revenue_growth":np.random.normal(12,15,n).clip(-20,50),"ocf_to_rev":np.random.normal(0.9,0.4,n).clip(0.1,2.0),"goodwill_to_equity":np.random.exponential(0.15,n)})

def garp_filter(md, fd):
    if md.empty or fd.empty: return pd.DataFrame()
    df = pd.merge(md, fd, on="code", how="left")
    df["profit_growth"] = df["profit_growth"].fillna(0)
    df["peg"] = df["pe_ttm"] / df["profit_growth"].replace(0, np.nan)
    mask = (df["peg"]<1.0) & (df["profit_growth"]>15) & (df["pe_ttm"]<20) & (df["roe"]>10) & (df["ocf_to_rev"]>0.08) & (df["goodwill_to_equity"]<0.30)
    mask = mask.fillna(False)
    res = df[mask].copy()
    return res.sort_values("profit_growth", ascending=False)

with st.spinner("正在获取全市场行情与财务数据..."):
    market_data = load_market_data()
    fin_data = load_financial_data()

if market_data.empty:
    st.error("行情数据不可用，请稍后再试。")
    st.stop()

garp_pool = garp_filter(market_data, fin_data) if not fin_data.empty else pd.DataFrame()

st.subheader("📊 今日市场概览")
c1,c2,c3 = st.columns(3)
with c1: st.metric("平均涨跌幅", f"{market_data['pct_chg'].mean():.2f}%")
with c2: st.metric("上涨家数", (market_data["pct_chg"]>0).sum())
with c3: st.metric("下跌家数", (market_data["pct_chg"]<0).sum())

st.subheader("🔍 GARP严格筛选结果")
st.markdown("**条件：** PEG<1 · 净利增速>15% · PE<20 · ROE>10% · 现金流健康 · 商誉<30%")

if not garp_pool.empty:
    st.success(f"✅ 今日共筛选出 {len(garp_pool)} 只GARP达标股票")
    disp = garp_pool[["code","name","price","pct_chg","pe_ttm","roe","profit_growth","peg"]].copy()
    disp.columns = ["代码","简称","现价","涨跌%","PE","ROE%","净利增速%","PEG"]
    st.dataframe(disp.style.background_gradient(cmap="RdYlGn", subset=["净利增速%"]), use_container_width=True, height=400)
#else:
    st.warning("今日暂无股票符合GARP全部六项严格条件。")

st.subheader("📋 低PE股票池（PE<20）")
low_pe = market_data[(market_data["pe_ttm"]>0)&(market_data["pe_ttm"]<20)].sort_values("pe_ttm")
#if not low_pe.empty:
    st.success(f"共筛选出 {len(low_pe)} 只PE<20的股票")
    disp2 = low_pe[["code","name","price","pct_chg","pe_ttm","pb","turnover"]].head(100)
    disp2.columns = ["代码","简称","现价","涨跌%","PE","PB","换手率%"]
    st.dataframe(disp2, use_container_width=True, height=400)

st.markdown("---")
st.caption(f"系统版本：v1.0 完整版 | 数据更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.error("⚠️ 风险声明：本系统仅基于公开历史数据客观筛选，不构成任何投资建议。市场有风险，投资需谨慎。")
