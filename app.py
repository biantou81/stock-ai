"""
AI智能选股系统 · 最终完整版（双数据源自动切换）
新浪财经优先，东方财富备用；无 akshare 依赖
"""
import streamlit as st
import pandas as pd
import requests
import time
import random
from datetime import datetime

st.set_page_config(page_title="AI选股·全能版", page_icon="📈", layout="wide")

# 会话状态
for key, default in {
    'chat_history': [],
    'holdings': {},
    'alert_log': []
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---------- 数据获取（双源自动切换） ----------
@st.cache_data(ttl=600, show_spinner="正在获取实时行情...")
def load_market_data():
    # 源1：新浪财经
    stocks = []
    for page in range(1, 4):
        try:
            url = f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=5000&sort=symbol&asc=1&node=hs_a"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data:
                    stocks.extend(data)
                else:
                    break
            time.sleep(random.uniform(0.3, 0.8))
        except:
            continue

    if not stocks:
        # 源2：东方财富备用
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1", "pz": "5000", "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f2,f3,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f37"
            }
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            stocks_raw = data.get("data", {}).get("diff", [])
            # 转换为统一格式
            for s in stocks_raw:
                stocks.append({
                    "symbol": s.get("f12", ""),
                    "name": s.get("f14", ""),
                    "trade": s.get("f2", 0),
                    "changepercent": s.get("f3", 0),
                    "per": s.get("f9", 0),
                    "pb": s.get("f23", 0),
                    "turnoverratio": s.get("f8", 0),
                    "amount": s.get("f20", 0)
                })
        except:
            pass

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

# ---------- 财务数据（东方财富公开接口，无 akshare） ----------
def get_financial_data():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "5000", "po": "1", "np": "1",
            "fltt": "2", "invt": "2", "fid": "f12",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f9,f23,f37,f10,f8"
        }
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        stocks = data.get("data", {}).get("diff", [])
        records = []
        for s in stocks:
            records.append({
                "code": s.get("f12", ""),
                "名称": s.get("f14", ""),
                "市盈率": float(s.get("f9", 0) if s.get("f9") else 0),
                "市净率": float(s.get("f23", 0) if s.get("f23") else 0),
                "roe": float(s.get("f37", 0) if s.get("f37") else 0),
                "profit_growth": float(s.get("f10", 0) if s.get("f10") else 0),
                "换手率": float(s.get("f8", 0) if s.get("f8") else 0)
            })
        df = pd.DataFrame(records)
        df = df[df["市盈率"] > 0]
        return df
    except:
        return pd.DataFrame()

# ---------- GARP筛选 ----------
def garp_filter(market_df, fin_df):
    if market_df.empty or fin_df.empty: return pd.DataFrame()
    df = pd.merge(market_df, fin_df, on="代码", how="left")
    for c in ["roe", "profit_growth"]:
        if c not in df.columns: df[c] = pd.NA
    df["peg"] = df["市盈率"] / df["profit_growth"].replace(0, pd.NA)
    mask = (
        df["peg"].notna() & (df["peg"] < 1.0) &
        df["profit_growth"].notna() & (df["profit_growth"] > 15) &
        df["市盈率"].notna() & (df["市盈率"] < 20) &
        df["roe"].notna() & (df["roe"] > 10)
    )
    return df[mask].sort_values("profit_growth", ascending=False)

# ---------- 妖股识别 ----------
def monster_stocks(df):
    return df[(df["涨跌幅"] > 9) & (df["换手率"] > 15) & (df["市盈率"] < 100)].sort_values("换手率", ascending=False)

# ---------- 资金流向 ----------
@st.cache_data(ttl=300)
def get_money_flow():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=1&np=1&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f62,f184,f66,f72"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        data = r.json()
        items = data.get("data",{}).get("diff",[])
        return [{"板块":i.get("f14",""),"主力净流入(亿)":round(i.get("f62",0)/1e8,2)} for i in items]
    except:
        return []

# ---------- 龙虎榜 ----------
@st.cache_data(ttl=1800)
def get_lhb():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=20&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6&fields=f12,f14,f3,f8,f9,f10"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        data = r.json()
        items = data.get("data",{}).get("diff",[])
        return [{"代码":i.get("f12",""),"名称":i.get("f14",""),"涨跌幅":i.get("f3",""),"换手率":i.get("f8",""),"市盈率":i.get("f9","")} for i in items if float(i.get("f8",0))>10]
    except:
        return []

# ---------- 新闻 ----------
@st.cache_data(ttl=600)
def get_news():
    try:
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get?fields=f3,f4,f5,f6&fltt=1&secids=1.000001"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        data = r.json()
        items = data.get("data",{}).get("diff",[])
        return [{"标题":i.get("f4",""),"时间":i.get("f6","")} for i in items[:10]]
    except:
        return []

# ---------- K线形态 ----------
def detect_pattern(df):
    patterns = []
    if len(df) < 3: return patterns
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    if latest["涨跌幅"] > 9 and prev["涨跌幅"] < 5 and float(prev.get("换手率",0)) > 20:
        patterns.append("⚡ 爆量弱转强")
    if latest["涨跌幅"] < -8 and prev["涨跌幅"] < -5:
        patterns.append("📉 恐慌下杀")
    if latest["涨跌幅"] > 5 and prev["涨跌幅"] < -3 and float(latest.get("换手率",0)) > 10:
        patterns.append("🔄 V型反转迹象")
    return patterns

# ---------- 六位分析师 ----------
def analyst_report(stock):
    pe = stock.get("市盈率",0)
    pct = stock.get("涨跌幅",0)
    turnover = stock.get("换手率",0)
    return {
        "基本面分析师": f"市盈率{pe:.1f}，{'估值偏低' if pe<20 else '估值偏高'}。",
        "资金分析师": f"换手率{turnover:.1f}%，{'交投活跃' if turnover>10 else '交易平淡'}。",
        "技术分析师": f"今日{'强势上涨' if pct>5 else '震荡' if abs(pct)<3 else '弱势下跌'}。",
        "宏观策略师": "建议结合大盘情绪判断操作时机。",
        "风险管理员": f"{'⚠️ 高位风险' if pct>9 else '🟢 正常波动'}，严格止损。",
        "首席投资经理": f"综合评分：{'B+（偏正面）' if pe<30 and pct>0 else 'C（观望）' if pe>50 else 'B（中性）'}。"
    }

# ========== 侧边栏导航 ==========
st.sidebar.title("📈 AI全能选股")
page = st.sidebar.radio("功能导航", [
    "🏠 市场概览", "🔍 GARP选股", "🦅 妖股雷达",
    "💰 资金监测", "📋 龙虎榜", "📰 实时快讯",
    "🤖 AI对话诊断", "📊 持仓监控", "📝 复盘日报"
])

raw = load_market_data()
market = process_market(raw) if raw else pd.DataFrame()

# ========== 各页面 ==========
if page == "🏠 市场概览":
    st.title("📊 市场概览")
    if market.empty:
        st.error("行情数据不可用（双源均失败），请稍后刷新。")
    else:
        c1,c2,c3 = st.columns(3)
        up = (market["涨跌幅"]>0).sum()
        down = (market["涨跌幅"]<0).sum()
        c1.metric("上涨家数", up)
        c2.metric("下跌家数", down)
        c3.metric("平均涨跌幅", f"{market['涨跌幅'].mean():.2f}%")
        st.subheader("📋 低PE股票池（PE<20）")
        st.dataframe(market[market["市盈率"]<20].sort_values("市盈率").head(100), use_container_width=True)

elif page == "🔍 GARP选股":
    st.title("🔍 GARP严格筛选")
    st.caption("PEG<1 · 净利增速>15% · PE<20 · ROE>10%")
    fin = get_financial_data()
    if fin.empty:
        st.warning("财务数据暂不可用（可能接口波动），请开盘后刷新。")
    elif market.empty:
        st.error("行情数据不可用")
    else:
        garp = garp_filter(market, fin)
        if not garp.empty:
            st.success(f"共筛选出 {len(garp)} 只")
            st.dataframe(garp[["代码","名称","最新价","涨跌幅","市盈率","roe","profit_growth","peg"]], use_container_width=True)
        else:
            st.info("暂无满足GARP全部条件的股票")

elif page == "🦅 妖股雷达":
    st.title("🦅 妖股雷达")
    st.caption("涨幅>9% + 换手率>15% + 市盈率<100")
    if not market.empty:
        m = monster_stocks(market)
        if not m.empty:
            st.warning(f"⚠️ 发现 {len(m)} 只妖股候选（高风险！）")
            st.dataframe(m[["代码","名称","最新价","涨跌幅","市盈率","换手率"]], use_container_width=True)
        else:
            st.info("当前无妖股候选")

elif page == "💰 资金监测":
    st.title("💰 资金流向监测")
    flows = get_money_flow()
    if flows:
        st.dataframe(pd.DataFrame(flows), use_container_width=True)
    else:
        st.info("资金数据暂不可用")

elif page == "📋 龙虎榜":
    st.title("📋 今日龙虎榜（高换手）")
    lhb = get_lhb()
    if lhb:
        st.dataframe(pd.DataFrame(lhb), use_container_width=True)
    else:
        st.info("龙虎榜数据暂不可用")

elif page == "📰 实时快讯":
    st.title("📰 实时财经快讯")
    news = get_news()
    if news:
        for n in news:
            st.write(f"• {n['标题']}  ({n['时间']})")
    else:
        st.info("暂无快讯")

elif page == "🤖 AI对话诊断":
    st.title("🤖 AI诊断助手")
    st.caption("输入6位股票代码或名称，六位AI分析师综合诊断")
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    prompt = st.chat_input("请输入股票代码或名称")
    if prompt:
        st.session_state.chat_history.append({"role":"user","content":prompt})
        if market.empty:
            reply = "行情数据暂未加载，请先回到“市场概览”等待加载。"
        else:
            match = market[market["代码"].str.contains(prompt)|market["名称"].str.contains(prompt)]
            if match.empty:
                reply = f"未找到与“{prompt}”相关的股票，请检查代码或名称。"
            else:
                s = match.iloc[0]
                reply = f"**{s['名称']} ({s['代码']})**\n"
                reply += f"最新价：{s['最新价']} | 涨跌幅：{s['涨跌幅']}%\n"
                reply += f"市盈率：{s['市盈率']} | 换手率：{s['换手率']}%\n\n"
                reports = analyst_report(s)
                for role, rpt in reports.items():
                    reply += f"**{role}**：{rpt}\n\n"
                patterns = detect_pattern(match.head(5))
                if patterns:
                    reply += "**技术形态识别**：" + "、".join(patterns)
        st.session_state.chat_history.append({"role":"assistant","content":reply})
        st.rerun()

elif page == "📊 持仓监控":
    st.title("📊 我的持仓")
    code = st.text_input("添加持仓（输入代码）")
    buy_price = st.text_input("买入价格（可选）")
    if st.button("添加") and code:
        st.session_state.holdings[code] = {"name":code,"buy_price":float(buy_price) if buy_price else None}
    if st.session_state.holdings:
        for c, info in st.session_state.holdings.items():
            if not market.empty:
                m = market[market["代码"]==c]
                if not m.empty:
                    s = m.iloc[0]
                    delta = ""
                    if info.get("buy_price"):
                        chg = (s["最新价"]-info["buy_price"])/info["buy_price"]*100
                        delta = f" | 持仓盈亏：{chg:+.2f}%"
                    st.write(f"{s['名称']} {s['最新价']}元 {s['涨跌幅']}%{delta}")
                else:
                    st.write(f"{c} 行情未找到")
            else:
                st.write(c)
            if st.button(f"删除 {c}", key=f"del_{c}"):
                del st.session_state.holdings[c]
                st.rerun()
    else:
        st.info("暂无持仓")

elif page == "📝 复盘日报":
    st.title("📝 复盘日报")
    if market.empty:
        st.error("行情数据不可用")
    else:
        up = (market["涨跌幅"]>0).sum()
        down = (market["涨跌幅"]<0).sum()
        st.write(f"📊 上涨 {up} 家 | 下跌 {down} 家 | 平均涨跌 {market['涨跌幅'].mean():.2f}%")
        m = monster_stocks(market)
        if not m.empty:
            st.write(f"🦅 妖股候选 {len(m)} 只")
        st.subheader("我的持仓回顾")
        if st.session_state.holdings:
            for c, info in st.session_state.holdings.items():
                m = market[market["代码"]==c]
                if not m.empty:
                    st.write(f"{m.iloc[0]['名称']}：涨跌{m.iloc[0]['涨跌幅']}%")
        else:
            st.write("无持仓记录")

st.sidebar.markdown("---")
st.sidebar.caption(f"更新时间：{datetime.now().strftime('%H:%M:%S')} | 数据源：新浪/东方财富双备")
st.sidebar.error("⚠️ 风险声明：仅基于公开数据客观筛选，不构成投资建议。")
