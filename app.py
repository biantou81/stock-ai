"""
AI智能选股系统 · 最终完整版
"""
import streamlit as st
import pandas as pd
import requests
import time
import random
import numpy as np
from datetime import datetime

st.set_page_config(page_title="AI选股·全能版", page_icon="📈", layout="wide")

for key, default in {
    'chat_history': [],
    'holdings': {},
    'pending_prompt': None,
    'show_all_chat': False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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

@st.cache_data(ttl=600, show_spinner="正在获取实时行情...")
def load_market_data():
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
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {"pn":"1","pz":"5000","po":"1","np":"1","fltt":"2","invt":"2","fid":"f3","fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23","fields":"f2,f3,f9,f12,f14,f20,f23,f8"}
            headers = {"User-Agent":"Mozilla/5.0","Referer":"https://data.eastmoney.com/"}
            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            for s in data.get("data",{}).get("diff",[]):
                stocks.append({"symbol":s.get("f12",""),"name":s.get("f14",""),"trade":s.get("f2",0),"changepercent":s.get("f3",0),"per":s.get("f9",0),"pb":s.get("f23",0),"turnoverratio":s.get("f8",0),"amount":s.get("f20",0)})
        except:
            pass
    return stocks

def process_market(raw):
    records = []
    for s in raw:
        try:
            pe = float(s.get("per",0) or 0)
            if pe <= 0:
                pe = 999
            records.append({"代码":str(s.get("symbol","")),"名称":str(s.get("name","")),"最新价":float(s.get("trade",0) or 0),"涨跌幅":float(s.get("changepercent",0) or 0),"市盈率":pe,"市净率":float(s.get("pb",0) or 0),"换手率":float(s.get("turnoverratio",0) or 0),"成交额":float(s.get("amount",0) or 0)})
        except:
            continue
    return pd.DataFrame(records)

def get_financial_data():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {"pn":"1","pz":"5000","po":"1","np":"1","fltt":"2","invt":"2","fid":"f12","fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23","fields":"f12,f14,f9,f23,f37,f10,f8"}
        headers = {"User-Agent":"Mozilla/5.0","Referer":"https://data.eastmoney.com/"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()
        records = []
        for s in data.get("data",{}).get("diff",[]):
            records.append({"code":str(s.get("f12","")),"roe":float(s.get("f37",0) if s.get("f37") else 0),"profit_growth":float(s.get("f10",0) if s.get("f10") else 0)})
        return pd.DataFrame(records)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_money_flow():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f62"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        data = r.json()
        return [{"板块":i.get("f14",""),"主力净流入(亿)":round(i.get("f62",0)/1e8,2)} for i in data.get("data",{}).get("diff",[])]
    except:
        return []

@st.cache_data(ttl=1800)
def get_lhb():
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f8&fs=m:0+t:6&fields=f12,f14,f3,f8,f9,f20"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        data = r.json()
        result = []
        for i in data.get("data",{}).get("diff",[]):
            try:
                t = float(i.get("f8",0) or 0)
                if t > 10:
                    result.append({"代码":i.get("f12",""),"名称":i.get("f14",""),"涨跌幅":i.get("f3",""),"换手率":t,"市盈率":i.get("f9",""),"成交额(亿)":round(float(i.get("f20",0) or 0)/1e8,2)})
            except:
                continue
        return result
    except:
        return []

@st.cache_data(ttl=600)
def get_news():
    news_list = []
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=15&page=1"
        headers = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'utf-8'
        data = r.json()
        for item in data.get("result",{}).get("data",[]):
            news_list.append({"标题":item.get("title",""),"时间":item.get("ctime","")})
    except:
        pass
    return news_list[:15]
    def market_sentiment(market_df):
    if market_df.empty:
        return "未知"
    limit_up = int((market_df["涨跌幅"] >= 9.9).sum())
    limit_down = int((market_df["涨跌幅"] <= -9.9).sum())
    up_count = int((market_df["涨跌幅"] > 0).sum())
    ratio = limit_up / max(limit_down, 1)
    if ratio >= 3 and up_count > 2000:
        return "过热"
    elif ratio >= 2:
        return "偏热"
    elif ratio >= 1:
        return "正常"
    elif ratio >= 0.5:
        return "偏冷"
    else:
        return "冰点"

def garp_filter(market_df, fin_df):
    if market_df.empty or fin_df.empty:
        return pd.DataFrame()
    df = pd.merge(market_df, fin_df, left_on="代码", right_on="code", how="left")
    if "roe" not in df.columns:
        df["roe"] = np.nan
    if "profit_growth" not in df.columns:
        df["profit_growth"] = np.nan
    df["peg"] = df["市盈率"] / df["profit_growth"].replace(0, np.nan)
    mask = (df["peg"].notna() & (df["peg"] < 1.0) & df["profit_growth"].notna() & (df["profit_growth"] > 15) & (df["市盈率"] > 0) & (df["市盈率"] < 20) & df["roe"].notna() & (df["roe"] > 10))
    return df[mask].sort_values("profit_growth", ascending=False)

def monster_stocks(df):
    return df[(df["涨跌幅"] > 9) & (df["换手率"] > 15) & (df["市盈率"] < 100)].sort_values("换手率", ascending=False)

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
        patterns.append("爆量弱转强")
    if pct < -8 and prev_pct < -3:
        patterns.append("恐慌下杀")
    if pct > 5 and prev_pct < -3 and turnover > 10:
        patterns.append("V型反转")
    if prev2 is not None:
        if prev_pct > 5 and prev2["涨跌幅"] > 3 and pct < -3 and turnover > prev_turnover:
            patterns.append("头肩顶风险")
        if prev_pct < -5 and prev2["涨跌幅"] < -3 and pct > 3 and turnover > prev_turnover:
            patterns.append("头肩底雏形")
        if prev2["涨跌幅"] > 5 and abs(prev_pct) < 2 and pct < -5:
            patterns.append("岛型反转预警")
        if pct > 1 and prev_pct > 1 and prev2["涨跌幅"] > 1:
            patterns.append("红三兵")
        if pct < -1 and prev_pct < -1 and prev2["涨跌幅"] < -1:
            patterns.append("三只乌鸦")
    if pct > 3 and prev_pct < -2 and turnover > prev_turnover * 1.5:
        patterns.append("看涨吞没")
    if pct < -3 and prev_pct > 2 and turnover > prev_turnover * 1.5:
        patterns.append("看跌吞没")
    if prev2 is not None and pct > 0 and prev_pct > 0 and prev2["涨跌幅"] > 0 and turnover > 5:
        patterns.append("倒三阳诱多")
    if prev2 is not None and pct > 3 and prev_pct < -2 and prev2["涨跌幅"] > 2:
        patterns.append("2B法则反转")
    return list(set(patterns))

def analyst_report(stock):
    pe = stock.get("市盈率", 0)
    pct = stock.get("涨跌幅", 0)
    turnover = stock.get("换手率", 0)
    reports = {
        "基本面分析师": f"PE{pe:.1f}，{'估值偏低' if pe<20 else '估值偏高'}。",
        "资金分析师": f"换手率{turnover:.1f}%，{'交投活跃' if turnover>10 else '交易平淡'}。",
        "技术分析师": f"今日{'强势上涨' if pct>5 else '震荡整理' if abs(pct)<3 else '弱势下跌'}。",
        "宏观策略师": "建议结合大盘情绪和板块轮动判断。",
        "风险管理员": f"{'高位风险，严格止损' if pct>9 else '正常波动，可控风险'}。",
        "首席投资经理": f"综合评级：{'偏正面' if pe<30 and pct>0 else '观望' if pe>50 else '中性'}。"
    }
    patterns = detect_kline_patterns(pd.DataFrame([stock]))
    if patterns:
        reports["技术分析师"] += f" 形态：{'、'.join(patterns)}"
    return reports

def ai_understand(text, market_df=None):
    text = str(text).strip()
    if market_df is not None and not market_df.empty:
        for _, row in market_df.iterrows():
            code = str(row["代码"])
            name = str(row["名称"])
            if code in text or name in text:
                return "stock_query", row.to_dict()
    kw_map = {
        "market": ["大盘", "行情", "市场", "走势"],
        "recommend": ["推荐", "潜力", "选股", "好股票", "机会"],
        "monster": ["妖股", "涨停板", "打板"],
        "review": ["复盘", "总结", "回顾"],
        "today_rec": ["今日推荐", "今天买什么"]
    }
    for intent, kws in kw_map.items():
        for kw in kws:
            if kw in text:
                return intent, None
    return "unknown", None

def today_top_picks(market_df, flows):
    if market_df.empty:
        return pd.DataFrame()
    df = market_df.copy()
    df["score"] = 0.0
    df.loc[(df["市盈率"] > 0) & (df["市盈率"] < 25), "score"] += 25
    df.loc[df["涨跌幅"] > 0, "score"] += 15
    df.loc[df["换手率"] > 5, "score"] += 15
    if flows:
        hot = [f["板块"] for f in flows[:5]]
        for s in hot:
            df.loc[df["名称"].str.contains(s, na=False), "score"] += 20
    df.loc[df["涨跌幅"] >= 9.5, "score"] += 25
    return df.sort_values("score", ascending=False).head(5)

def generate_stock_card(stock, rank=0):
    name = stock.get("名称", "")
    code = stock.get("代码", "")
    pe = stock.get("市盈率", 0)
    pct = stock.get("涨跌幅", 0)
    turnover = stock.get("换手率", 0)
    score = stock.get("score", 0)
    reasons = []
    if pe < 20:
        reasons.append("低估值")
    if pct > 5:
        reasons.append("今日强势")
    if turnover > 10:
        reasons.append("交投活跃")
    if pct >= 9.5:
        reasons.append("涨停")
    reason_str = "、".join(reasons) if reasons else "综合评分优秀"
    medal = "1" if rank == 0 else "2" if rank == 1 else "3" if rank == 2 else str(rank+1)
    card = f"### 第{medal}名 {name}({code})\n"
    card += f"现价：{stock.get('最新价','')} | 涨跌：{pct}% | PE：{pe:.1f} | 换手：{turnover}%\n\n"
    card += f"推荐理由：{reason_str} | 综合评分：{score:.0f}分\n\n"
    patterns = detect_kline_patterns(pd.DataFrame([stock]))
    if patterns:
        card += f"技术形态：{'、'.join(patterns)}\n\n"
    reports = analyst_report(stock)
    card += "六位分析师综合诊断：\n"
    for role, rpt in reports.items():
        card += f"• {role}：{rpt}\n"
    price = stock.get("最新价", 0)
    if price > 0:
        atr = price * 0.03
        card += f"\n止盈参考：{round(price+atr*2,2)}元 | 止损参考：{round(price-atr*1.5,2)}元\n"
    card += f"\n操作建议：{'短线可关注，设好止损' if score>60 else '观望为主，等待信号'}。\n---\n"
    return card
raw = load_market_data()
market = process_market(raw) if raw else pd.DataFrame()
fin_data = get_financial_data()
flows = get_money_flow()
market_open = is_market_open()
sentiment = market_sentiment(market)

st.sidebar.title("AI全能选股")
if not market_open:
    st.sidebar.warning("休市中，数据为最近交易日")
st.sidebar.metric("市场情绪", sentiment)
main_page = st.sidebar.radio("核心功能", ["行情总览", "今日推荐", "AI智能分析"])

if main_page == "行情总览":
    st.title("行情总览")
    if market.empty:
        st.error("行情数据不可用")
    else:
        limit_up = int((market["涨跌幅"] >= 9.9).sum())
        limit_down = int((market["涨跌幅"] <= -9.9).sum())
        total_amount = market["成交额"].sum() / 1e8
        avg_turnover = market["换手率"].mean()
        avg_pct = market["涨跌幅"].mean()
        c1, c2, c3 = st.columns(3)
        c1.metric("涨停家数", limit_up)
        c2.metric("跌停家数", limit_down)
        c3.metric("总成交额(亿)", f"{total_amount:.0f}")
        c4, c5 = st.columns(2)
        c4.metric("平均换手率", f"{avg_turnover:.2f}%")
        c5.metric("平均涨跌幅", f"{avg_pct:.2f}%")
        with st.expander("涨停跌停列表"):
            t1, t2 = st.columns(2)
            with t1:
                st.write("**涨停股票**")
                up_list = market[market["涨跌幅"] >= 9.9][["代码", "名称", "涨跌幅"]].head(30)
                if not up_list.empty:
                    st.dataframe(up_list, use_container_width=True)
                else:
                    st.write("无")
            with t2:
                st.write("**跌停股票**")
                down_list = market[market["涨跌幅"] <= -9.9][["代码", "名称", "涨跌幅"]].head(30)
                if not down_list.empty:
                    st.dataframe(down_list, use_container_width=True)
                else:
                    st.write("无")
        st.subheader("板块资金流向")
        if flows:
            st.dataframe(pd.DataFrame(flows), use_container_width=True, height=200)
        else:
            st.info("资金数据暂不可用")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("龙虎榜")
            lhb = get_lhb()
            if lhb:
                st.dataframe(pd.DataFrame(lhb), use_container_width=True, height=250)
            else:
                st.info("龙虎榜数据暂不可用")
        with col2:
            st.subheader("实时快讯")
            news = get_news()
            if news:
                for n in news[:8]:
                    st.write(f"• {n['标题']}")
            else:
                st.info("暂无快讯")

elif main_page == "今日推荐":
    st.title("今日推荐")
    st.caption("综合估值、资金、形态、板块热度筛选")
    picks = today_top_picks(market, flows)
    if picks.empty:
        st.info("当前无符合综合评分条件的股票，请开盘后刷新。")
    else:
        if flows:
            st.subheader("今日热门板块")
            hot_str = "、".join([f"{f['板块']}({f['主力净流入(亿)']}亿)" for f in flows[:5]])
            st.write(f"**{hot_str}**")
        st.subheader("推荐标的")
        for i, (_, row) in enumerate(picks.iterrows()):
            st.write(generate_stock_card(row, i))
        st.warning("以上基于多维度综合评分，不构成投资建议。")

elif main_page == "AI智能分析":
    st.title("AI智能诊断助手")
    quick_asks = ["今日推荐", "今日大盘如何？", "推荐潜力股", "妖股有哪些？", "帮我复盘"]
    cols = st.columns(len(quick_asks))
    for i, ask in enumerate(quick_asks):
        if cols[i].button(ask, key=f"qbtn_{i}"):
            st.session_state.chat_history.append({"role": "user", "content": ask})
            st.session_state.pending_prompt = ask
            st.rerun()
    if st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
    else:
        prompt = st.chat_input("输入问题（如：分析大唐发电 / 今日推荐）")
    if st.button("清除聊天记录"):
        st.session_state.chat_history = []
        st.rerun()
    display_count = 5 if not st.session_state.get('show_all_chat', False) else len(st.session_state.chat_history)
    for msg in st.session_state.chat_history[-display_count:]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    if len(st.session_state.chat_history) > 5 and not st.session_state.get('show_all_chat', False):
        if st.button("展开全部对话"):
            st.session_state.show_all_chat = True
            st.rerun()
    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        if market.empty:
            reply = "行情数据暂不可用，请稍后刷新。"
        else:
            intent, stock = ai_understand(prompt, market)
            if intent == "stock_query" and stock:
                s = stock
                reply = f"## {s.get('名称','')}({s.get('代码','')}) 深度分析\n\n"
                reply += f"最新价：{s.get('最新价','')} | 涨跌：{s.get('涨跌幅','')}% | PE：{s.get('市盈率','')} | 换手：{s.get('换手率','')}%\n\n"
                reply += "### 六位AI分析师综合诊断\n"
                reports = analyst_report(s)
                for role, rpt in reports.items():
                    reply += f"**{role}**：{rpt}\n\n"
                patterns = detect_kline_patterns(pd.DataFrame([s]))
                if patterns:
                    reply += f"### 技术形态识别\n{'、'.join(patterns)}\n\n"
                reply += "### 操作建议\n"
                price = s.get("最新价", 0)
                if price > 0:
                    atr = price * 0.03
                    reply += f"• 短线止损参考：{round(price-atr*1.5,2)}元\n• 短线止盈参考：{round(price+atr*2,2)}元\n"
                reply += "• 建议结合大盘情绪和板块轮动综合判断\n\n不构成投资建议。"
            elif intent in ["today_rec", "recommend"]:
                picks = today_top_picks(market, flows)
                if not picks.empty:
                    reply = "## 今日最优推荐（综合评分Top5）\n\n"
                    if flows:
                        reply += "**今日热门板块**：" + "、".join([f["板块"] for f in flows[:3]]) + "\n\n"
                    for i, (_, row) in enumerate(picks.iterrows()):
                        reply += generate_stock_card(row, i)
                    reply += "以上基于多维度综合评分，不构成投资建议。"
                else:
                    reply = "当前无符合综合评分条件的股票。"
            elif intent == "market":
                up = int((market["涨跌幅"] > 0).sum())
                down = int((market["涨跌幅"] < 0).sum())
                reply = f"## 今日市场概览\n\n上涨{up}家，下跌{down}家 | 平均涨跌{market['涨跌幅'].mean():.2f}%\n\n市场情绪：{sentiment}\n\n"
                if flows:
                    reply += "### 主力净流入前三板块\n"
                    for f in flows[:3]:
                        reply += f"• {f['板块']}：{f['主力净流入(亿)']}亿\n"
            elif intent == "monster":
                m = monster_stocks(market)
                if not m.empty:
                    reply = f"## 妖股雷达（{len(m)}只候选）\n\n"
                    for _, row in m.head(5).iterrows():
                        reply += f"• **{row['名称']}({row['代码']})** 涨幅{row['涨跌幅']}% 换手{row['换手率']}%\n"
                    reply += "\n妖股高风险高波动，严格止损。"
                else:
                    reply = "当前无妖股候选。"
            elif intent == "review":
                up = int((market["涨跌幅"] > 0).sum())
                down = int((market["涨跌幅"] < 0).sum())
                reply = f"## 今日复盘\n\n上涨{up}家，下跌{down}家 | 情绪：{sentiment}\n"
                if st.session_state.holdings:
                    reply += "\n### 持仓表现\n"
                    for c, info in st.session_state.holdings.items():
                        mh = market[market["代码"] == c]
                        if not mh.empty:
                            reply += f"• {mh.iloc[0]['名称']}：{mh.iloc[0]['涨跌幅']}%\n"
            else:
                reply = "我是您的AI选股助手。您可以说：\n• 今日推荐\n• 分析大唐发电\n• 推荐潜力股\n• 有什么妖股"
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption(f"更新时间：{datetime.now().strftime('%H:%M:%S')}")
st.sidebar.caption("数据源：新浪/东方财富双备")
st.sidebar.error("风险声明：仅基于公开数据客观筛选，不构成投资建议。")
