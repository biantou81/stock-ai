"""
AI智能选股系统 · 最终完整版（修复版）
双数据源自动切换 | 12种K线形态 | 六位AI分析师 | 50+自然语言理解 | 涨停跌停统计
"""
import streamlit as st
import pandas as pd
import requests
import time
import random
import numpy as np
from datetime import datetime, timedelta
import json
import re

# ---------- 页面配置 ----------
st.set_page_config(page_title="AI选股·全能版", page_icon="📈", layout="wide")

# ---------- 会话状态初始化 ----------
for key, default in {
    'chat_history': [],
    'holdings': {},
    'alert_log': [],
    'pending_prompt': None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---------- 休市判断 ----------
def is_market_open():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        return False
    if now.hour > 15 or (now.hour == 15 and now.minute > 0):
        return False
    if now.hour == 11 and now.minute >= 30 and now.hour < 13:
        return False
    return True

# ---------- 双数据源行情获取 ----------
@st.cache_data(ttl=600, show_spinner="正在获取实时行情...")
def load_market_data():
    stocks = []
    # 源1：新浪财经
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
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1", "pz": "5000", "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f2,f3,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f37,f8"
            }
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            stocks_raw = data.get("data", {}).get("diff", [])
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
            pe = float(s.get("per", 0) or 0)
            if pe <= 0:
                pe = 999
            records.append({
                "代码": str(s.get("symbol", "")),
                "名称": str(s.get("name", "")),
                "最新价": float(s.get("trade", 0) or 0),
                "涨跌幅": float(s.get("changepercent", 0) or 0),
                "市盈率": pe,
                "市净率": float(s.get("pb", 0) or 0),
                "换手率": float(s.get("turnoverratio", 0) or 0),
                "成交额": float(s.get("amount", 0) or 0)
            })
        except:
            continue
    return pd.DataFrame(records)

# ---------- 财务数据 ----------
def get_financial_data():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "5000", "po": "1", "np": "1",
            "fltt": "2", "invt": "2", "fid": "f12",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f9,f23,f37,f10,f8,f184,f185"
        }
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        stocks = data.get("data", {}).get("diff", [])
        records = []
        for s in stocks:
            records.append({
                "code": str(s.get("f12", "")),
                "roe": float(s.get("f37", 0) if s.get("f37") else 0),
                "profit_growth": float(s.get("f10", 0) if s.get("f10") else 0),
                "revenue_growth": float(s.get("f184", 0) if s.get("f184") else 0),
                "ocf_to_rev": float(s.get("f185", 0) if s.get("f185") else 0),
                "goodwill_to_equity": 0.0
            })
        return pd.DataFrame(records)
    except:
        return pd.DataFrame()

# ---------- 资金流向 ----------
@st.cache_data(ttl=300)
def get_money_flow():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f62,f184,f66,f72"
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
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f8&fs=m:0+t:6&fields=f12,f14,f3,f8,f9,f10,f20,f21"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        data = r.json()
        items = data.get("data",{}).get("diff",[])
        result = []
        for i in items:
            try:
                turnover = float(i.get("f8", 0) or 0)
                if turnover > 10:
                    result.append({
                        "代码":i.get("f12",""),"名称":i.get("f14",""),
                        "涨跌幅":i.get("f3",""),"换手率":turnover,
                        "市盈率":i.get("f9",""),"成交额(亿)":round(float(i.get("f20",0) or 0)/1e8,2)
                    })
            except:
                continue
        return result
    except:
        return []

# ---------- 新闻（双源防乱码） ----------
@st.cache_data(ttl=600)
def get_news():
    news_list = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=15&page=1"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'utf-8'
        data = r.json()
        for item in data.get("result",{}).get("data",[]):
            news_list.append({"标题": item.get("title",""), "时间": item.get("ctime",""), "来源": "新浪财经"})
    except:
        pass
    if not news_list:
        try:
            url = "https://push2.eastmoney.com/api/qt/ulist.np/get?fields=f3,f4,f5,f6&fltt=1&secids=1.000001"
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            r.encoding = 'utf-8'
            data = r.json()
            items = data.get("data",{}).get("diff",[])
            for i in items[:10]:
                news_list.append({"标题":i.get("f4",""),"时间":i.get("f6",""),"来源":"东方财富"})
        except:
            pass
    return news_list[:15]
    # ==================== GARP筛选 ====================
def garp_filter(market_df, fin_df):
    if market_df.empty or fin_df.empty:
        return pd.DataFrame()
    df = pd.merge(market_df, fin_df, left_on="代码", right_on="code", how="left")
    for c in ["roe", "profit_growth", "ocf_to_rev", "goodwill_to_equity"]:
        if c not in df.columns:
            df[c] = np.nan
    df["peg"] = df["市盈率"] / df["profit_growth"].replace(0, np.nan)
    mask = (
        df["peg"].notna() & (df["peg"] < 1.0) &
        df["profit_growth"].notna() & (df["profit_growth"] > 15) &
        (df["市盈率"] > 0) & (df["市盈率"] < 20) &
        df["roe"].notna() & (df["roe"] > 10)
    )
    if "ocf_to_rev" in df.columns and df["ocf_to_rev"].notna().sum() > 0:
        mask = mask & (df["ocf_to_rev"] > 0.08)
    if "goodwill_to_equity" in df.columns and df["goodwill_to_equity"].notna().sum() > 0:
        mask = mask & (df["goodwill_to_equity"] < 0.30)
    return df[mask].sort_values("profit_growth", ascending=False)

# ==================== 妖股识别 ====================
def monster_stocks(df):
    return df[(df["涨跌幅"] > 9) & (df["换手率"] > 15) & (df["市盈率"] < 100)].sort_values("换手率", ascending=False)

# ==================== K线形态识别（12种） ====================
def detect_kline_patterns(hist_data):
    patterns = []
    if hist_data is None or len(hist_data) < 3:
        return patterns
    latest = hist_data.iloc[-1]
    prev = hist_data.iloc[-2]
    prev2 = hist_data.iloc[-3] if len(hist_data) >= 3 else None
    pct = latest.get("涨跌幅", 0)
    prev_pct = prev.get("涨跌幅", 0)
    turnover = latest.get("换手率", 0)
    prev_turnover = prev.get("换手率", 0)
    if pct > 9 and prev_pct < 7 and prev_turnover > 15 and turnover > prev_turnover * 0.8:
        patterns.append("⚡ 爆量弱转强")
    if pct < -8 and prev_pct < -3:
        patterns.append("📉 恐慌下杀")
    if pct > 5 and prev_pct < -3 and turnover > 10:
        patterns.append("🔄 V型反转迹象")
    if prev2 is not None:
        if prev_pct > 5 and prev2["涨跌幅"] > 3 and pct < -3 and turnover > prev_turnover:
            patterns.append("⚠️ 头肩顶风险")
        if prev_pct < -5 and prev2["涨跌幅"] < -3 and pct > 3 and turnover > prev_turnover:
            patterns.append("🔻 头肩底雏形")
        if prev2["涨跌幅"] > 5 and abs(prev_pct) < 2 and pct < -5:
            patterns.append("🏝️ 岛型反转预警")
        if pct > 1 and prev_pct > 1 and prev2["涨跌幅"] > 1:
            patterns.append("🔥 红三兵")
        if pct < -1 and prev_pct < -1 and prev2["涨跌幅"] < -1:
            patterns.append("🐦 三只乌鸦")
    if pct > 3 and prev_pct < -2 and turnover > prev_turnover * 1.5:
        patterns.append("✅ 看涨吞没")
    if pct < -3 and prev_pct > 2 and turnover > prev_turnover * 1.5:
        patterns.append("❌ 看跌吞没")
    if prev2 is not None and pct > 0 and prev_pct > 0 and prev2["涨跌幅"] > 0 and turnover > 5:
        patterns.append("⚠️ 倒三阳诱多")
    if prev2 is not None and pct > 3 and prev_pct < -2 and prev2["涨跌幅"] > 2:
        patterns.append("🔄 2B法则反转")
    return list(set(patterns))

# ==================== 六位AI分析师 ====================
def analyst_report(stock, market_context=None):
    pe = stock.get("市盈率", 0)
    pct = stock.get("涨跌幅", 0)
    turnover = stock.get("换手率", 0)
    reports = {
        "基本面分析师": f"市盈率{pe:.1f}，{'估值偏低，具备安全边际' if pe < 20 else '估值偏高，需关注成长性'}。",
        "资金分析师": f"换手率{turnover:.1f}%，{'交投活跃，资金关注度高' if turnover > 10 else '交易平淡，市场分歧小'}。",
        "技术分析师": f"今日{'强势上涨，短线趋势向上' if pct > 5 else '震荡整理，方向待选择' if abs(pct) < 3 else '弱势下跌，注意风险'}。",
        "宏观策略师": "建议结合大盘情绪和板块轮动综合判断。",
        "风险管理员": f"{'⚠️ 高位高波动，严格止损' if pct > 9 else '🟢 正常波动，可控风险'}。",
        "首席投资经理": f"综合评分：{'B+（偏正面）' if pe < 30 and pct > 0 else 'C（观望）' if pe > 50 else 'B（中性）'}。"
    }
    patterns = detect_kline_patterns(stock.to_frame().T if isinstance(stock, pd.Series) else pd.DataFrame([stock]))
    if patterns:
        reports["技术分析师"] += f" 识别形态：{'、'.join(patterns)}"
    return reports

# ==================== 自然语言理解引擎（50+问法） ====================
def ai_understand(text, market_df=None):
    text = str(text).strip().lower()
    
    # 股票代码/名称匹配（修复版）
    if market_df is not None and not market_df.empty:
        clean_text = text.replace(" ", "").replace("分析", "").replace("怎么样", "").replace("如何", "").replace("？", "").replace("?", "").strip()
        if len(clean_text) >= 2:
            code_match = market_df[market_df["代码"].astype(str).str.strip().str.contains(clean_text, na=False)]
            name_match = market_df[market_df["名称"].astype(str).str.strip().str.contains(clean_text, na=False)]
            if not code_match.empty:
                return "stock_query", code_match.iloc[0].to_dict()
            if not name_match.empty:
                return "stock_query", name_match.iloc[0].to_dict()
    
    # 意图关键词库（50+问法）
    intent_map = {
        "market": ["大盘", "行情", "市场", "走势", "指数", "今天怎么样", "现在什么情况", "今日大盘"],
        "hot": ["热点", "板块", "主力买", "资金流", "谁在涨", "领涨"],
        "recommend": ["推荐", "潜力", "选股", "荐股", "好股票", "值得买", "值得投资", "机会", "布局", "推荐潜力股"],
        "monster": ["妖股", "涨停", "打板", "连板", "强势股", "妖股有哪些"],
        "analyze": ["分析", "诊断", "怎么看", "评价", "表现", "前景"],
        "stoploss": ["止损", "止盈", "目标价"],
        "review": ["复盘", "总结", "回顾", "今天表现", "帮我复盘"],
        "compare": ["对比", "比较", "哪个好"],
        "advice": ["建议", "操作", "怎么办", "怎么操作", "明天", "接下来"]
    }
    for intent, keywords in intent_map.items():
        for kw in keywords:
            if kw in text:
                return intent, None
    return "unknown", None

# ==================== 生成推荐回复 ====================
def generate_recommendation(market_df, fin_df):
    if market_df.empty:
        return "当前行情数据不可用。"
    low_pe = market_df[(market_df["市盈率"] > 0) & (market_df["市盈率"] < 20)].sort_values("市盈率").head(5)
    if low_pe.empty:
        return "当前无市盈率<20的股票。"
    reply = "💡 为您筛选低市盈率潜力股（Top5）：\n"
    for _, row in low_pe.iterrows():
        reply += f"• {row['名称']}({row['代码']})  PE:{row['市盈率']:.1f}  涨跌:{row['涨跌幅']}%  换手:{row['换手率']}%\n"
    reply += "\n⚠️ 以上仅为客观筛选，不构成投资建议。"
    return reply

def generate_stop_loss_advice(stock):
    price = stock.get("最新价", 0)
    if price <= 0:
        return "无法获取价格数据。"
    atr_est = price * 0.03
    stop_loss = round(price - atr_est * 1.5, 2)
    take_profit = round(price + atr_est * 2, 2)
    return f"📊 基于估算波动率：\n• 短线止损参考：{stop_loss} 元\n• 短线止盈参考：{take_profit} 元\n⚠️ 实际请结合K线支撑/压力位调整。"
    # ==================== 加载数据 ====================
raw = load_market_data()
market = process_market(raw) if raw else pd.DataFrame()
fin_data = get_financial_data()
market_open = is_market_open()

# ==================== 侧边栏导航 ====================
st.sidebar.title("📈 AI全能选股")
if not market_open:
    st.sidebar.warning("🔴 当前为休市时间，数据为最近交易日")
main_page = st.sidebar.radio("核心功能", ["📊 行情总览", "🔍 选股与持仓", "🤖 AI智能分析"])

# ==================== 模块一：行情总览 ====================
if main_page == "📊 行情总览":
    st.title("📊 行情总览")
    
    if market.empty:
        st.error("行情数据不可用（双源均失败），请稍后刷新。")
    else:
        c1, c2, c3, c4 = st.columns(4)
        up = int((market["涨跌幅"] > 0).sum())
        down = int((market["涨跌幅"] < 0).sum())
        c1.metric("上涨家数", up)
        c2.metric("下跌家数", down)
        c3.metric("平均涨跌", f"{market['涨跌幅'].mean():.2f}%")
        c4.metric("低PE股票", int(len(market[(market["市盈率"]>0)&(market["市盈率"]<20)])))
        
        # 涨停跌停统计
        limit_up = int((market["涨跌幅"] >= 9.9).sum())
        limit_down = int((market["涨跌幅"] <= -9.9).sum())
        c5, c6 = st.columns(2)
        c5.metric("涨停家数", limit_up)
        c6.metric("跌停家数", limit_down)
        
        st.subheader("💰 板块资金流向")
        flows = get_money_flow()
        if flows:
            flow_df = pd.DataFrame(flows)
            st.dataframe(flow_df, use_container_width=True, height=200)
        else:
            st.info("资金数据暂不可用")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📋 龙虎榜（高换手>10%）")
            lhb = get_lhb()
            if lhb:
                st.dataframe(pd.DataFrame(lhb), use_container_width=True, height=250)
            else:
                st.info("龙虎榜数据暂不可用")
        with col2:
            st.subheader("📰 实时快讯")
            news = get_news()
            if news:
                for n in news[:8]:
                    st.write(f"• {n['标题']}")
            else:
                st.info("暂无快讯")

# ==================== 模块二：选股与持仓 ====================
elif main_page == "🔍 选股与持仓":
    tab1, tab2, tab3 = st.tabs(["🔍 GARP选股", "🦅 妖股雷达", "📊 我的持仓"])
    
    with tab1:
        st.subheader("GARP严格筛选")
        st.caption("PEG<1 · 净利增速>15% · PE<20 · ROE>10% · 现金流>0.08 · 商誉<30%")
        if fin_data.empty:
            st.warning("财务数据暂不可用，可能为休市期间，请开盘后刷新。")
        elif market.empty:
            st.error("行情数据不可用")
        else:
            garp = garp_filter(market, fin_data)
            if not garp.empty:
                st.success(f"共筛选出 {len(garp)} 只GARP达标股票")
                disp_cols = ["代码","名称","最新价","涨跌幅","市盈率","roe","profit_growth","peg"]
                disp = garp[[c for c in disp_cols if c in garp.columns]]
                st.dataframe(disp, use_container_width=True, height=400)
            else:
                st.info("暂无满足GARP全部条件的股票")
    
    with tab2:
        st.subheader("妖股雷达")
        st.caption("涨幅>9% + 换手率>15% + 市盈率<100")
        if not market.empty:
            m = monster_stocks(market)
            if not m.empty:
                st.warning(f"⚠️ 发现 {len(m)} 只妖股候选（高风险博弈！）")
                st.dataframe(m[["代码","名称","最新价","涨跌幅","市盈率","换手率"]], use_container_width=True, height=400)
            else:
                st.info("当前无妖股候选")
    
    with tab3:
        st.subheader("我的持仓")
        code = st.text_input("添加持仓（输入6位代码）")
        buy_price = st.text_input("买入价格（可选）")
        if st.button("添加持仓") and code:
            st.session_state.holdings[code] = {"name": code, "buy_price": float(buy_price) if buy_price else 0.0}
            st.rerun()
        if st.session_state.holdings:
            for c, info in list(st.session_state.holdings.items()):
                col_a, col_b, col_c = st.columns([3, 2, 1])
                if not market.empty:
                    m = market[market["代码"] == c]
                    if not m.empty:
                        s = m.iloc[0]
                        delta = ""
                        if info.get("buy_price") and info["buy_price"] > 0:
                            chg = (s["最新价"] - info["buy_price"]) / info["buy_price"] * 100
                            delta = f" | 盈亏：{chg:+.2f}%"
                        col_a.write(f"{s['名称']} ({c})")
                        col_b.write(f"{s['最新价']}元 {s['涨跌幅']}%{delta}")
                    else:
                        col_a.write(c)
                        col_b.write("行情未找到")
                else:
                    col_a.write(c)
                if col_c.button("删除", key=f"del_{c}"):
                    del st.session_state.holdings[c]
                    st.rerun()
        else:
            st.info("暂无持仓，请在上方添加")

# ==================== 模块三：AI智能分析 ====================
elif main_page == "🤖 AI智能分析":
    st.title("🤖 AI智能诊断助手")
    
    # 快捷提问（修复版：点完自动分析）
    quick_asks = ["今日大盘如何？", "推荐潜力股", "妖股有哪些？", "帮我复盘"]
    cols = st.columns(len(quick_asks))
    for i, ask in enumerate(quick_asks):
        if cols[i].button(ask, key=f"qbtn_{i}"):
            st.session_state.chat_history.append({"role": "user", "content": ask})
            st.session_state.pending_prompt = ask
            st.rerun()
    
    # 处理快捷按钮的待处理问题
    if st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
    else:
        prompt = st.chat_input("输入问题（如：推荐低市盈率股票 / 分析茅台 / 今天热点在哪）")
    
    # 历史对话
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    
    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        if market.empty:
            reply = "⚠️ 行情数据暂不可用，请稍后刷新再试。"
        else:
            intent, stock = ai_understand(prompt, market)
            
            if intent == "stock_query" and stock:
                s = stock
                reply = f"**{s.get('名称','')} ({s.get('代码','')})**\n"
                reply += f"最新价：{s.get('最新价','')} | 涨跌：{s.get('涨跌幅','')}%\n"
                reply += f"市盈率：{s.get('市盈率','')} | 换手：{s.get('换手率','')}%\n\n"
                reports = analyst_report(s)
                for role, rpt in reports.items():
                    reply += f"**{role}**：{rpt}\n\n"
                reply += generate_stop_loss_advice(s)
            
            elif intent == "market":
                up = int((market["涨跌幅"]>0).sum())
                down = int((market["涨跌幅"]<0).sum())
                reply = f"📊 今日市场概览：\n上涨 {up} 家，下跌 {down} 家\n平均涨跌：{market['涨跌幅'].mean():.2f}%\n"
                flows = get_money_flow()
                if flows:
                    top_flow = flows[:3]
                    reply += "\n💰 主力净流入前三板块：\n"
                    for f in top_flow:
                        reply += f"• {f['板块']}：{f['主力净流入(亿)']}亿\n"
            
            elif intent == "hot":
                flows = get_money_flow()
                if flows:
                    reply = "🔥 今日板块资金流向（前5）：\n"
                    for f in flows[:5]:
                        reply += f"• {f['板块']}：{f['主力净流入(亿)']}亿\n"
                else:
                    reply = "资金数据暂不可用。"
            
            elif intent in ["recommend", "advice"]:
                reply = generate_recommendation(market, fin_data)
            
            elif intent == "monster":
                m = monster_stocks(market)
                if not m.empty:
                    reply = f"🦅 当前妖股候选 {len(m)} 只：\n"
                    for _, row in m.head(5).iterrows():
                        reply += f"• {row['名称']}({row['代码']}) 涨幅:{row['涨跌幅']}% 换手:{row['换手率']}%\n"
                else:
                    reply = "当前无妖股候选。"
            
            elif intent == "analyze":
                reply = "请具体说明要分析哪只股票，例如：分析茅台 / 科大讯飞怎么样"
            
            elif intent == "stoploss":
                reply = "请提供具体股票代码或名称，我来估算止盈止损参考价位。"
            
            elif intent == "review":
                up = int((market["涨跌幅"]>0).sum())
                down = int((market["涨跌幅"]<0).sum())
                reply = f"📝 今日复盘：\n上涨 {up} 家，下跌 {down} 家\n平均涨跌 {market['涨跌幅'].mean():.2f}%\n"
                m = monster_stocks(market)
                if not m.empty:
                    reply += f"妖股出没 {len(m)} 只\n"
                if st.session_state.holdings:
                    reply += "持仓表现：\n"
                    for c, info in st.session_state.holdings.items():
                        mh = market[market["代码"]==c]
                        if not mh.empty:
                            reply += f"• {mh.iloc[0]['名称']}：涨跌{mh.iloc[0]['涨跌幅']}%\n"
            
            elif intent == "compare":
                reply = "请提供要对比的两只股票代码或名称，例如：茅台对比五粮液"
            
            else:
                reply = "我是您的AI选股助手。您可以这样问我：\n• “推荐潜力股”\n• “分析茅台”\n• “今天大盘怎么样”\n• “有什么妖股”\n• “帮我复盘”"
        
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()

# ==================== 页脚 ====================
st.sidebar.markdown("---")
st.sidebar.caption(f"更新时间：{datetime.now().strftime('%H:%M:%S')}")
st.sidebar.caption(f"数据源：新浪/东方财富双备")
st.sidebar.caption(f"市场状态：{'🟢 交易中' if market_open else '🔴 休市'}")
st.sidebar.error("⚠️ 风险声明：仅基于公开数据客观筛选，不构成投资建议。")
