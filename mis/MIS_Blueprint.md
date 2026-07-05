# MIS Blueprint

---

## Design Philosophy

MIS exists to help the trader understand the market, focus on the highest-quality opportunities, execute consistently, and continuously improve through feedback.

MIS不预测市场，不寻找最低点，也不猜测未来。MIS 只识别已经被市场确认的机会，帮助交易者在最早的可执行阶段理解市场、聚焦机会、跟随趋势、稳定执行，并通过持续反馈不断优化整个交易系统。

Focus is the reduction of decision space.

聚焦的本质，不是推荐股票，而是不断缩小交易者需要做出的决策空间。

Every layer must reduce uncertainty. Never increase complexity.

每一层都必须降低交易的不确定性，而不是增加信息复杂度。

MIS increases analytical depth internally so it can decrease decision complexity externally. The richness of Layer 1 and Layer 2's inputs, and the complexity of how raw data becomes a final result, do not violate this principle — it governs what the trader absorbs from MIS each day to face the market with, not how the system arrives at its conclusions internally.

MIS 对内追求分析的深度，对外追求决策的简单。Layer 1、Layer 2 输入维度的丰富，以及原始数据得出结论的处理过程，并不违反这一原则——这一原则约束的是交易者每天从 MIS 中吸收、并据此面对市场的内容，而不是系统内部得出结论的过程。

MIS 的存在目的不是分析更多信息。

MIS 的存在目的，是帮助交易者：

理解市场；

聚焦机会；

稳定执行；

持续改善。

## Core Principles

1.

The market is always smarter than any model.

市场永远比任何模型更聪明。

2.

Information is not value. Focus is value.

不是信息越多越好，真正的价值来自于聚焦后的正反馈。

3.

Every recommendation must be executable.

所有建议最终都必须能够落实到实际交易，而不是停留在分析层面。

4.

Every recommendation must be explainable.

每一个建议都必须能够解释原因，而不是黑箱评分。

5.

Every recommendation must be reviewable.

所有建议最终都必须能够复盘，并不断修正。

6.

What MIS does not surface is not merely unseen — it is excluded.

未被MIS呈现的机会，不是"尚未被看见"，而是"已经被排除"。临时起意、不在系统内的交易，不属于MIS，也不应该被执行。

## System Architecture

MIS is designed as a multi-layer decision system. Each layer has only one responsibility. Information flows from market data to trading execution, and finally back into learning. No layer should duplicate the responsibility of another layer.

MIS 是一个多层决策系统。每一层都只有一个明确职责。信息始终沿着同一个方向流动：市场 → 理解 → 机会 → 计划 → 执行 → 反馈 → 学习。每一层都不能重复另一层的工作。

Market → Layer 1 (Market Intelligence) → Layer 2 (Opportunity Intelligence) → Layer 3 (Focus Intelligence) → Layer 4 (Execution Intelligence) → Layer 5 (Feedback & Behaviour) → Layer 6 (Knowledge Base)

One deliberate exception exists inside this flow: Layer 1 and Layer 2 are mutual inputs rather than a one-way gate. Sector-level breadth observed in Layer 2 feeds back into Layer 1's market judgment (see Layer 2, Breadth Feedback).

这条流向中存在一个刻意设计的例外：Layer 1 与 Layer 2 互为输入，而不是单向门控。Layer 2 观察到的板块广度信息会反向输入 Layer 1 的市场判断（详见 Layer 2 的"广度反馈"）。

### Layer 1 — Market Intelligence

#### Objective

Layer 1 exists to understand the current market environment before evaluating any trading opportunity.

The market always comes before the stock.

No individual opportunity should be evaluated without first understanding the overall market.

#### Core Question

What is the market trying to do today?

#### Inputs

- Market breadth（市场涨跌家数）

- Index performance（指数表现）

- Sector rotation（板块轮动）

- Capital flow（资金流向）

- Sector capital-flow breadth from Layer 2（来自 Layer 2 的板块资金广度，作为反向证据）

- Leading sectors（领涨板块）

- Market Leaders（市场龙头）

- Opening auction data（集合竞价：竞价量 / 竞价额 / 竞价涨幅）

- News（新闻资讯）

- Social sentiment（论坛 / 社交媒体情绪）

- Search trends（搜索热度）

- Intraday price action（盘中分时走势）

- Historical market behaviour（历史市场行为）

- Theme Memory from Knowledge Base（主题记忆）

#### Core Components

##### Market Context

Market Context represents the overall trading environment rather than any individual stock.

It is evaluated as a trend rather than a snapshot.

Its objective is to determine whether the current market rewards aggressive execution, selective execution, or defensive behaviour.

Market Context is evaluated using multiple dimensions, including:

- Limit-up height and ladder distribution（连板高度与连板梯队分布）

- Sealed limit-up count（封板家数：收盘仍封住）

- Touched limit-up count（触板家数：盘中触及涨停，含此后炸板）

- Broken board rate, derived from the pair（炸板率：由触板与封板推导）

- Sealed and touched limit-down counts（跌停封板与触及家数）

- Yesterday's Limit-up Premium（昨日涨停溢价率）

- Market breadth（市场涨跌家数）

- Capital concentration（资金集中度）

- Sector rotation（板块轮动）

- Cross-market Confirmation（沪深主板 / 创业板 / 科创板共振）

- Intraday participation（盘中承接强度）

- Risk appetite（市场风险偏好）

Paired indicators are never collapsed into a single number. Sealed and touched counts are stored as a pair and the failure rate is derived from them; the divergence between the pair is itself a sentiment signal, and collapsing it into one number loses that information. Only the pair is stored; the ratios are derived: the seal rate equals sealed divided by touched, and the broken board rate equals one minus the seal rate.

成对指标绝不压缩成一个数字。封板与触板家数成对存储，炸板率由两者推导；两个数字之间的分歧本身就是情绪信号，压缩成一个数就丢失了这层信息。系统只存储这对原始家数，比率全部推导得出：封板率 = 封板 ÷ 触板，炸板率 = 1 − 封板率。

Market Context operates in two modes. The end-of-day mode performs deep analysis after the close to prepare tomorrow's decisions. The intraday mode performs lightweight, real-time confirmation of whether the executability environment assumed by today's plan still holds. The intraday mode never generates new decisions; it only verifies conditions that were defined in advance.

市场环境有两种工作模式。盘后模式在收盘后做深度分析，为明天的决策做准备。盘中模式做轻量的实时确认：今天计划所依赖的可执行环境是否仍然成立。盘中模式绝不产生新的决策，只验证事先定义好的条件。

##### Attention Score

Attention Score measures where the market is currently focusing.

It measures attention rather than opportunity.

Measures:

- News frequency（新闻数量）

- Search trends（搜索热度）

- Social discussion（论坛讨论热度）

- Sector discussion（板块讨论热度）

- Capital inflow（资金流入）

- Intraday activity（盘中活跃度）

A high Attention Score only means the market is paying attention.

It does not imply a trading opportunity.

##### Impact Score

Impact Score estimates how likely current attention will translate into sustained price movement.

Impact Score is continuously adjusted by market feedback.

The same news can produce very different Impact Scores under different Market Context.

Impact Score measures market reaction rather than news importance.

The market decides the impact, not the news itself.

Impact Score is influenced by:

- Market Context

- Theme Memory

- Historical follow-through（历史持续性）

- Capital confirmation（资金确认）

- Intraday confirmation（盘中确认）

- Leadership confirmation（龙头确认）

Impact Score exists to answer one question:

Will the market actually reward this idea?

##### Theme Memory

Markets have memory.

Theme Memory continuously learns from historical market behaviour instead of predicting the future.

Themes that repeatedly fail after positive news gradually lose confidence.

Themes that consistently generate follow-through gradually gain confidence.

Theme Memory provides long-term learning rather than short-term prediction.

Theme Memory is stored inside the Knowledge Base and updated after every trading day.

##### Decision Bias Warning

Decision Bias Warning identifies situations where historical market behaviour suggests elevated execution risk despite attractive scores.

It does not reduce any score directly.

Instead, it reminds the trader that similar opportunities have historically produced weak follow-through, false breakouts, or short-lived momentum.

Typical warning sources include:

- Historical one-day themes（一日游题材）

- Weak historical follow-through（历史持续性较弱）

- Frequent false breakouts（假突破频繁）

- High failure patterns（高失败率模式）

- Low persistence themes（持续性较弱题材）

Warnings never override the system.

They exist to prevent repeated historical mistakes.

Decision Bias Warning in Layer 1 is scoped to market and theme-level history. Bias arising from the trader's own execution behaviour is intentionally out of scope here and belongs to Layer 5.

Layer 1 的决策偏差警示仅针对市场与题材层面的历史行为。由交易者自身执行习惯产生的偏差，不在本层范围内，属于 Layer 5 的职责。

#### Outputs

Layer 1 produces:

- Market Context Score

- Attention Score

- Impact Score

- Theme Confidence

- Theme Ranking

- Market Confidence

- Executability Environment（可执行环境）

- Decision Bias Warnings（决策偏差警示）

#### Responsibilities

Layer 1 never recommends buying a stock.

Its responsibility is only to understand:

- Where money is flowing

- Which themes are strengthening

- Which themes are weakening

- Whether momentum is being rewarded

- Whether aggressive execution is appropriate

- Whether historical behaviour suggests additional caution

Layer 1 provides the market environment in which every later decision will be made.

#### Success Criteria

At the end of Layer 1, the trader should clearly understand:

- What kind of market this is.

- What kind of opportunities deserve attention.

- What kind of opportunities should be ignored.

- Whether tomorrow should be aggressive, selective, or defensive.

- Which opportunities require additional caution despite attractive scores.

Layer 1 reduces uncertainty about the market.

It does not generate trading decisions.

### Layer 2 — Opportunity Intelligence

#### Objective

Layer 2 exists to identify every market opportunity and transform the market into a structured Opportunity Universe.

MIS does not predict opportunities.

MIS attempts to recognise opportunities at the earliest executable stage while avoiding unsupported speculation.

Every opportunity develops through time.

The objective of Layer 2 is to understand where each opportunity currently sits within its lifecycle.

#### Core Question

What opportunities is the market actually offering today?

#### Inputs

- Market Context from Layer 1

- Attention Score

- Impact Score

- Theme Memory from Knowledge Base（主题记忆）

- News and Catalysts（新闻与催化）

- Sector Rotation（板块轮动）

- Capital Flow（资金流向）

- Leadership Structure（龙头结构）

- Intraday Behaviour（盘中行为）

- Technical Confirmation（技术确认）

- Historical Opportunity Records（历史机会记录）

#### Core Components

##### Opportunity Universe

Opportunity Universe represents every meaningful opportunity currently existing in the market.

It is intentionally broad.

Completeness is more important than selectivity.

No opportunity should be filtered before entering the Opportunity Universe.

Focus belongs to Layer 3.

##### Opportunity Object

Every opportunity is represented by a standardized Opportunity Object.

Opportunity Object is the fundamental decision unit throughout MIS.

Each Opportunity Object contains:

- Theme（主题）

- Catalyst（催化）

- Leadership Structure（龙头结构）

- Representative Stocks（代表个股）

- Capital Flow（资金流）

- Technical Status（技术状态）

- Opportunity Score

- Opportunity Maturity

- Executability

- Confidence

- Risk

- Historical Behaviour（历史表现）

Every later layer operates on Opportunity Objects instead of individual stocks.

##### Opportunity Maturity

Opportunities evolve continuously.

They should never be treated as simply "confirmed" or "not confirmed".

Typical maturity stages include:

- Potential（潜在）

- Emerging（开始形成）

- Pre-confirmed（初步确认）

- Confirmed（市场确认）

- Expanding（持续加强）

- Exhausting（开始衰竭）

- Resolved（兑现结束）

MIS attempts to recognise opportunities as they approach the earliest executable stage.

The objective is not to be earliest.

The objective is to be earliest while remaining executable.

##### Opportunity Evaluation

Every Opportunity Object is evaluated using multiple dimensions rather than a single score.

Evaluation includes:

- Opportunity Score

- Confidence

- Risk

- Expected Persistence（持续性）

- Market Context Compatibility（市场环境适配）

- Historical Behaviour（历史表现）

No opportunity should rely on only one source of confirmation.

##### Leadership Intelligence

Every opportunity possesses a leadership structure.

Leadership is evaluated as:

- Absolute Leader（绝对龙头）

- Market Leader（市场龙头）

- Core Leader（中军）

- Secondary Leader（龙二）

- Catch-up（补涨）

- Follower（跟风）

- Replacement Leader（卡位龙头）

- Noise（杂毛）

Leadership quality directly influences opportunity sustainability.

Crowding is not scored separately — it is read from Leadership Intelligence: when Followers and Noise increasingly outnumber a clear Leader, the opportunity is becoming crowded.

拥挤度不单独打分，而是通过龙头结构判断：当跟风和杂毛相对龙头的占比持续上升，说明该机会正在变得拥挤。

Sector-level judgments are never expressed at the sector-name level alone. Every sector judgment names the specific stocks involved and their roles — for example, "semiconductor (equipment): Core Leader X −x%, Catch-up Y −y%" — never just "semiconductors are fading". Sector membership definitions differ across data sources, and one stock can belong to several concepts at once; only named stocks with roles are verifiable and unambiguous.

板块层面的判断绝不停留在板块名称这个抽象层级。每一个板块判断都必须列出具体涉及的个股并标注角色——例如"半导体（设备子方向）：中军XX −x%、补涨XX −y%"——绝不能只说"半导体退潮"。不同数据源对板块成分股的定义本身就不统一，同一只股票也可能同时属于多个概念；只有落到具体个股与角色，判断才是可验证、不模糊的。

##### Catalyst Intelligence

Catalysts explain why opportunities exist.

Catalysts include:

- Policy（政策）

- Earnings（业绩）

- Industry Events（产业事件）

- Supply and Demand（供需变化）

- Technology Breakthrough（技术突破）

- Capital Behaviour（资金行为）

- Market Narrative（市场叙事）

Catalyst quality is evaluated by both strength and persistence.

Short-term attention and long-term impact should be distinguished.

##### Capital Flow State

Sector capital flow, read against sector price action, is classified into two states.

板块资金流相对于价格走势，分为两种状态。

Divergence（背离）: capital is flowing out of or into a sector at a clearly abnormal scale, but price has not yet followed — for example, heavy outflow while the sector barely falls. This is the earliest signal, and possibly a false one; it has not been verified by price.

背离：板块资金流出或流入的幅度已经明显异常，但价格还没有跟上（例如资金大幅流出但当天板块跌幅很小）。这是最早期的信号，但也可能是假信号，尚未被价格验证。

Resonance（共振）: capital direction and price direction confirm each other — inflow with a rising sector, or outflow with a falling one. The structure is already being realised, and part of the move may already be over.

共振：资金流向和价格方向已经互相确认（资金流入且板块上涨，或资金流出且板块下跌）。这代表结构已经在兑现，甚至可能已经走完一部分。

These states bind to the existing anticipate–probe–confirm–add rhythm; they are not a new, independent position rule. Divergence corresponds to the anticipate/probe stage: observation or a minimal probe only, never a heavy position, because divergence may be noise that price has not yet validated. Resonance corresponds to the confirm/add stage: only after capital and price confirm each other does an opportunity enter the stage where normal or increased size becomes possible.

这组状态与既有的"预判–试错–确认–加仓"节奏绑定，不是一套新增的独立仓位规则。背离对应预判/试错阶段：只允许观察或极轻仓试错，绝不允许重仓，因为背离本身可能只是尚未被价格验证的噪音。共振对应确认/加仓阶段：资金与价格互相确认之后，机会才进入可以正常甚至加大仓位的阶段。

Mandatory warning: whenever the system or any report judges a sector to be in Divergence, it must state in the same output: "this state permits anticipation or probing only — never a heavy position." Early signals must never be misused as grounds for heavy positioning.

强制提示：系统或任何报告在判断某板块处于"背离"状态时，必须同时输出一句提醒——"当前只能预判或试错，不能重仓"。早期信号绝不允许被误用为重仓（抢跑）的依据。

##### Breadth Feedback

Layer 1 and Layer 2 are mutual inputs, not a one-way gate.

Layer 1 与 Layer 2 互为输入，不是单向门控关系。

Layer 1 measures the water level of the overall capital pool — market turnover, margin balances, market breadth — whether new money is entering or leaving the market as a whole. Layer 2 measures the distribution inside the pool — which sectors capital currently favours. Layer 2's analysis assumes the pool is roughly constant in the short term, and that assumption breaks precisely when the water level itself is changing sharply.

Layer 1 衡量的是整体资金池的水位——大盘成交额、两融余额、涨跌家数——反映新钱是否在净流入或净流出整个市场。Layer 2 衡量的是资金池内部的分布——资金当前更青睐哪个板块。Layer 2 的分析假设短期内资金总量大致不变，而这个假设恰恰在水位剧烈变化时失真。

When Layer 2 observes breadth information — for example, most sectors losing capital simultaneously while only a few defensive sectors receive inflows — that breadth itself becomes evidence fed back into Layer 1, helping to judge whether the market has entered a decline or freezing stage. Layer 1 does not first decide the stage and then gate whether Layer 2 runs; the two inform each other.

当 Layer 2 观察到广度信息——例如多数板块同时资金流出、只有少数避险类板块资金流入——这个广度本身就应该反过来作为证据输入给 Layer 1，帮助判断市场是否已进入衰退或冰点阶段。不是 Layer 1 先判断完阶段、Layer 2 再被动跟随做或不做分析，两者互相提供输入。

##### Executability Assessment

A good opportunity is not necessarily executable.

Executability evaluates whether the current opportunity should enter tomorrow's Focus List.

Executability considers:

- Timing（天时）

- Market Environment（地利）

- Strategy Compatibility（策略匹配）

- Trader Compatibility（人和）

High Opportunity Score does not imply high Executability.

#### Outputs

Layer 2 produces:

- Opportunity Universe

- Opportunity Objects

- Opportunity Ranking

- Opportunity Score

- Opportunity Maturity

- Leadership Assessment

- Catalyst Assessment

- Capital Flow State per sector（板块资金流状态：背离 / 共振）

- Breadth evidence, fed back to Layer 1（广度证据，反馈给 Layer 1）

- Executability Assessment

#### Responsibilities

Layer 2 never recommends buying a stock.

Its responsibility is to understand:

- What opportunities currently exist.

- Which opportunities are strengthening.

- Which opportunities are weakening.

- Which opportunities are approaching the earliest executable stage.

- Which opportunities require continued observation.

Layer 2 transforms the market into a structured Opportunity Universe.

Layer 3 determines where attention should be focused.

#### Success Criteria

At the end of Layer 2, the trader should clearly understand:

- What opportunities currently exist.

- Which opportunities deserve continued observation.

- Which opportunities are approaching execution.

- Which opportunities are already becoming crowded.

- Which opportunities should receive Focus tomorrow.

Layer 2 reduces thousands of stocks into a manageable Opportunity Universe.

It does not determine tomorrow's trading decisions.

### Layer 3 — Focus Intelligence

#### Objective

Layer 3 exists to transform the Opportunity Universe into a small, executable Focus List for tomorrow.

Layer 3 的存在目的，是把机会全集转化为一份小而可执行的明日聚焦清单。

Layer 1 and Layer 2 expand understanding. Layer 3 contracts decision space. Layer 3 is where Focus actually happens.

Layer 1 和 Layer 2 负责扩展理解。Layer 3 负责收缩决策空间。Layer 3 是"聚焦"真正发生的地方。

Elimination is the primary work of Layer 3. Selection is only its result. The trader's confidence to ignore an opportunity is as valuable as the confidence to act on one.

排除是 Layer 3 的主要工作，入选只是排除之后的结果。交易者"敢于忽略一个机会"的信心，与"敢于执行一个机会"的信心同样有价值。

#### Core Question

What deserves my attention tomorrow — and what must I confidently ignore?

明天什么值得我关注——什么必须被我有信心地忽略？

#### Inputs

- Market Context and Executability Environment from Layer 1（来自 Layer 1 的市场环境与可执行环境）

- Decision Bias Warnings from Layer 1（来自 Layer 1 的决策偏差警示）

- Opportunity Universe and Opportunity Objects from Layer 2（来自 Layer 2 的机会全集与机会对象）

- Opportunity Ranking, Maturity, and Executability Assessment from Layer 2（来自 Layer 2 的机会排序、成熟度与可执行性评估）

- Strategy Profile, current version from Knowledge Base（策略画像，当前版本，来自知识库）

- Personal Bias Warnings from Knowledge Base（来自知识库的个人偏差警示）

- Current Positions（当前持仓）

- Focus History from Knowledge Base（来自知识库的历史聚焦记录）

#### Core Components

##### Strategy Profile

Strategy Profile is the formal definition of the trader's own system. It describes what kinds of opportunities belong to this trader, independent of what the market is offering today.

策略画像是交易者自身交易系统的正式定义。它描述什么类型的机会属于这位交易者，与市场今天提供什么无关。

The current Strategy Profile is centred on structural accumulation: long consolidation, first volume expansion, first breakout, early sector, supportive sentiment, persistent capital.

当前的策略画像以结构低吸为核心：长期横盘、首次放量、首次突破、板块初起、情绪允许、资金持续。

Signals are weighted rather than treated equally. The current weighting is approximately seven parts mechanical breakout structure and three parts leadership and sentiment. This weighting is an explicit, versioned, tunable parameter — never an unwritten habit.

信号是有权重的，而不是被同等对待的。当前的权重大约是：七分机械突破结构，三分龙头与情绪。这个权重是一个明确的、有版本记录的、可调节的参数——绝不允许停留在不成文的习惯里。

Strategy Profile changes only through deliberate revision, never through intraday emotion.

策略画像只能通过审慎的修订而改变，绝不允许被盘中情绪改变。

##### Elimination Engine

The Elimination Engine removes opportunities from consideration, in explicit stages, each with a recorded reason.

排除引擎分阶段将机会移出考虑范围，每一次排除都记录原因。

Typical elimination gates include:

典型的排除关卡包括：

- Market Context Gate: the environment does not reward this type of opportunity（市场环境关卡：当前环境不奖励这类机会）

- Maturity Gate: the opportunity is too early to execute or already exhausting（成熟度关卡：机会尚未到可执行阶段，或已开始衰竭）

- Strategy Gate: the opportunity does not match the Strategy Profile（策略关卡：机会不符合策略画像）

- Crowding Gate: Followers and Noise dominate the leadership structure（拥挤度关卡：跟风与杂毛在龙头结构中占比过高）

- Bias Gate: Decision Bias Warnings indicate historically weak follow-through（偏差关卡：决策偏差警示显示历史持续性弱）

An opportunity may be excellent in general and still be eliminated because it does not belong to this trader.

一个机会可能整体上非常优秀，但依然会因为"不属于这位交易者"而被排除。

##### Focus List

The Focus List contains the small number of opportunities that survive elimination. Focus capacity is deliberately limited and never expands because the market looks exciting. A typical Focus List contains no more than three to five opportunities.

聚焦清单包含通过所有排除关卡后剩下的少数机会。聚焦容量是刻意受限的，绝不因为市场看起来热闹而扩大。典型的聚焦清单不超过三到五个机会。

An empty Focus List is a legitimate output. "Nothing qualifies today" is a complete and successful answer.

空的聚焦清单是一个完全合法的输出。"今天没有合格的机会"是一个完整且成功的答案。

##### Ignore List

The Ignore List makes exclusion explicit instead of silent. Every meaningful opportunity that was eliminated appears on the Ignore List together with its elimination reason. The Ignore List exists to build the trader's confidence to not trade.

忽略清单让"排除"成为显式的记录，而不是无声的缺席。每一个被排除的重要机会，都会出现在忽略清单上，并附带排除原因。忽略清单的存在，是为了建立交易者"不交易"的信心。

What is not on the Focus List is not merely unseen — it is excluded. Any intraday impulse toward an opportunity on the Ignore List is, by definition, an out-of-system trade.

不在聚焦清单上的机会，不是"尚未被看见"，而是"已经被排除"。盘中对忽略清单上机会的任何临时冲动，从定义上讲，就是系统外交易。

##### Tomorrow Plan

The Tomorrow Plan converts each Focus List item into concrete, pre-committed conditions.

明日计划将聚焦清单上的每一项转化为具体的、事先承诺的条件。

For each focus item, the Tomorrow Plan specifies:

对每一个聚焦项，明日计划明确规定：

- Trigger Conditions: what must happen before any action is considered（触发条件：在考虑任何行动之前必须发生什么）

- Invalidation Conditions: what would remove this item from focus immediately（失效条件：什么情况会使该项立即失去聚焦资格）

- Observation Points: what to watch to judge whether the opportunity is strengthening or weakening（观察要点：通过什么判断机会在加强还是减弱）

- Priority: the order of attention if multiple items trigger together（优先级：多个项目同时触发时的注意力顺序）

Trigger and Invalidation Conditions are defined at three levels: market, sector, and stock. A stock-level trigger alone is never sufficient; the plan states what the market and the sector must be doing for the trigger to count.

触发条件与失效条件在三个层面上定义：大盘、板块、个股。仅有个股层面的触发永远不够；计划必须写明大盘和板块需要处于什么状态，触发才算数。

The Tomorrow Plan describes conditions, never predictions. The Tomorrow Plan never specifies position size or entry price; those belong to Layer 4.

明日计划描述的是条件，绝不是预测。明日计划绝不规定仓位大小或买入价格；那些属于 Layer 4 的职责。

##### Focus Discipline

Decisions about what to focus on are made after the close, never during the trading session. During the session, the Focus List is read-only.

关于聚焦什么的决策在收盘后做出，绝不在盘中做出。盘中，聚焦清单是只读的。

Opportunities discovered intraday enter tomorrow's Opportunity Universe. They never enter today's Focus List.

盘中发现的机会进入明天的机会全集，绝不进入今天的聚焦清单。

This single rule directly targets the trader's most repeated historical mistake: execution running ahead of the system.

这一条规则直接针对交易者历史上最常重复的错误：执行跑到系统前面。

#### Outputs

Layer 3 produces:

Layer 3 产出：

- Focus List（聚焦清单）

- Ignore List with elimination reasons（附排除原因的忽略清单）

- Tomorrow Plan（明日计划）

- Priority Ranking（优先级排序）

- Focus Rationale（聚焦理由：每一项为何获得聚焦）

#### Responsibilities

Layer 3 never executes a trade and never sizes a position.

Layer 3 绝不执行交易，也绝不决定仓位。

Its responsibility is to decide:

它的职责是决定：

- What deserves attention tomorrow.（明天什么值得关注。）

- What must be ignored, and why.（什么必须被忽略，以及为什么。）

- Under what pre-committed conditions attention may become action.（在什么样的事先承诺条件下，关注才可以变成行动。）

Layer 3 transforms a broad Opportunity Universe into a narrow, disciplined attention structure. Layer 4 decides how pre-committed conditions become actual execution.

Layer 3 将广阔的机会全集转化为狭窄而有纪律的注意力结构。Layer 4 决定事先承诺的条件如何变成实际的执行。

#### Success Criteria

At the end of Layer 3, the trader should clearly understand:

Layer 3 结束时，交易者应该清楚地知道：

- Exactly what to watch tomorrow, and in what order.（明天到底看什么，按什么顺序看。）

- Exactly what has been excluded, and why.（到底什么被排除了，为什么被排除。）

- What conditions must occur before any action is even considered.（在考虑任何行动之前，必须先发生什么条件。）

- That anything outside the Focus List does not belong to tomorrow's trading.（聚焦清单之外的任何东西，都不属于明天的交易。）

The trader should be able to say, calmly and with confidence: "I don't need to trade this."

交易者应该能够平静而自信地说出："这个我不需要做。"

Layer 3 reduces the Opportunity Universe into tomorrow's attention. It does not execute trades.

Layer 3 将机会全集收缩为明天的注意力。它不执行交易。

### Layer 4 — Execution Intelligence

#### Objective

Layer 4 exists to convert the Tomorrow Plan's pre-committed conditions into disciplined, traceable execution.

Layer 4 的存在目的，是把明日计划中事先承诺的条件，转化为有纪律、可追溯的实际执行。

Layer 3 decides what deserves attention. Layer 4 decides how attention becomes action. Execution is the only layer where money actually moves, which is exactly why it must contain the least improvisation.

Layer 3 决定什么值得关注。Layer 4 决定关注如何变成行动。执行是资金真正流动的唯一一层，也正因为如此，它必须包含最少的即兴发挥。

The purpose of Layer 4 is not to trade more skilfully. Its purpose is to make every trade an execution of the system, and to make every deviation from the system immediately visible.

Layer 4 的目的不是让交易更"高明"。它的目的是让每一笔交易都成为系统的执行，并让每一次偏离系统的行为立即变得可见。

#### Core Question

The conditions have been met — now what exactly do I do, and how much?

条件已经满足——现在我到底做什么，做多少？

#### Inputs

- Tomorrow Plan from Layer 3（来自 Layer 3 的明日计划）

- Focus List and Priority Ranking from Layer 3（来自 Layer 3 的聚焦清单与优先级排序）

- Intraday Market Context from Layer 1（来自 Layer 1 的盘中市场环境）

- Current Positions and Account State（当前持仓与账户状态）

- Risk Parameters, current version from Knowledge Base（风险参数，当前版本，来自知识库）

- Execution History from Knowledge Base（来自知识库的历史执行记录）

#### Core Components

##### Execution Plan

The Execution Plan translates each triggered Tomorrow Plan item into a concrete action specification: entry method, position size, initial stop, and exit framework — all defined before the action, never during it.

执行计划把明日计划中每一个被触发的项目，转化为具体的行动规范：买入方式、仓位大小、初始止损、退出框架——全部在行动之前定义，绝不在行动过程中定义。

An opportunity without a complete Execution Plan is not executable, regardless of how attractive it looks intraday.

没有完整执行计划的机会就是不可执行的机会，无论它盘中看起来多么诱人。

##### Position Sizing

Position size is determined by pre-defined Risk Parameters, never by intraday conviction or excitement.

仓位大小由事先定义的风险参数决定，绝不由盘中的信心或兴奋程度决定。

Risk Parameters include:

风险参数包括：

- Maximum risk per trade（单笔交易最大风险）

- Maximum total exposure（总仓位上限）

- Maximum number of concurrent positions（同时持仓数量上限）

- Daily loss limit（单日亏损上限）

Like the Strategy Profile, Risk Parameters are explicit, versioned, and tunable — and they change only through deliberate revision, never intraday.

与策略画像一样，风险参数是明确的、有版本记录的、可调节的——并且只能通过审慎的修订而改变，绝不允许盘中修改。

##### Entry Discipline

An entry is permitted only when three conditions hold simultaneously: the opportunity is on today's Focus List; its stock-level Trigger Conditions from the Tomorrow Plan have actually occurred; and the market-level and sector-level conditions written in the Tomorrow Plan, confirmed intraday by Layer 1, still hold.

只有三个条件同时成立，买入才被允许：该机会在今天的聚焦清单上；明日计划中个股层面的触发条件已经真实发生；明日计划中写明的大盘与板块条件，经 Layer 1 盘中确认仍然成立。

If any of the three is missing, there is no entry. Almost triggered is not triggered. Looks strong is not a trigger condition.

三者缺一，即不买入。"差一点就触发"不等于触发。"看起来很强"不是触发条件。

##### Exit Intelligence

Every position carries pre-committed exit conditions from the moment it is opened. Exits take exactly two forms: the Stop Loss（止损）, placed where the entry logic is invalidated, and the Sell Point（卖点）, the pre-defined conditions under which the position is closed.

每一个仓位从建立的那一刻起，就带有事先承诺的退出条件。退出只有两种形式：止损——设在买入逻辑失效之处；卖点——事先定义的平仓条件。

There is no separate profit-target concept. Specific stop-loss and sell-point methods are defined in the Strategy Profile, not in this Blueprint.

不设独立的止盈概念。具体的止损与卖点方法在策略画像中定义，不写入本蓝图。

Exits are executed when their conditions occur, not when the trader feels ready. Hope is not an exit strategy, and neither is fear.

退出在条件发生时执行，而不是在交易者"感觉可以了"的时候执行。希望不是退出策略，恐惧也不是。

##### In-System Verification

Every trade, at the moment it happens, is classified as In-System or Out-of-System.

每一笔交易在发生的那一刻，就被归类为"系统内"或"系统外"。

An In-System trade maps to a Focus List item, an occurred Trigger Condition, and a compliant position size. Anything else — including a profitable trade — is Out-of-System.

系统内交易必须对应一个聚焦清单项目、一个已发生的触发条件、以及一个合规的仓位。除此之外的任何交易——包括赚钱的交易——都是系统外交易。

MIS cannot physically prevent an Out-of-System trade. Its responsibility is to make the classification undeniable at the moment of action, so that no trade can retroactively claim to have been part of the system.

MIS 无法在物理上阻止一笔系统外交易。它的职责是让这个分类在行动发生的那一刻就无可辩驳，使任何交易都无法事后声称自己"属于系统"。

##### Execution Log

Every action — entry, exit, size change, and every Out-of-System trade — is recorded with its timestamp, its planned basis, and its actual result.

每一个动作——买入、卖出、仓位变化、以及每一笔系统外交易——都被记录下来，包括时间戳、计划依据和实际结果。

The Execution Log answers the question the brokerage statement never can: was this trade inside the system or outside it. It is the primary raw material for Layer 5 and the foundation of the system's data capability.

执行日志回答了交割单永远无法回答的问题：这笔交易在系统内还是系统外。它是 Layer 5 最主要的原材料，也是整个系统数据化能力的地基。

#### Outputs

Layer 4 produces:

Layer 4 产出：

- Execution Plans（执行计划）

- Executed Actions（实际执行动作）

- In-System / Out-of-System Classification（系统内/系统外分类）

- Execution Log（执行日志）

- Deviation Records（偏离记录）

#### Responsibilities

Layer 4 never selects opportunities and never modifies the Focus List. It acts only on what Layer 3 has already decided, under conditions Layer 3 has already defined.

Layer 4 绝不挑选机会，也绝不修改聚焦清单。它只在 Layer 3 已经定义的条件下，执行 Layer 3 已经决定的事情。

Its responsibility is to decide:

它的职责是决定：

- Whether trigger conditions have genuinely occurred.（触发条件是否真实发生。）

- How much to commit, according to Risk Parameters.（按照风险参数，投入多少。）

- When and how to exit, according to pre-committed conditions.（按照事先承诺的条件，何时以及如何退出。）

- Whether each trade was In-System or Out-of-System.（每一笔交易属于系统内还是系统外。）

Layer 4 turns plans into records. Layer 5 turns records into learning.

Layer 4 把计划变成记录。Layer 5 把记录变成学习。

#### Success Criteria

At the end of Layer 4, the trader should clearly understand:

Layer 4 结束时，交易者应该清楚地知道：

- Exactly what was done today, and on what planned basis.（今天到底做了什么，依据的是哪个计划。）

- Which actions were In-System and which were Out-of-System.（哪些动作在系统内，哪些在系统外。）

- Whether Risk Parameters were respected throughout.（风险参数是否全程得到遵守。）

- What every open position's exit conditions are.（每一个持仓的退出条件是什么。）

The measure of a successful trading day is not profit. It is that every action taken can be traced to a plan, and every deviation is honestly on record.

一个成功交易日的衡量标准不是盈利，而是：每一个动作都能追溯到计划，每一次偏离都被诚实地记录在案。

Layer 4 converts pre-committed conditions into disciplined action. It does not evaluate whether the system itself is working — that is the responsibility of Layer 5.

Layer 4 将事先承诺的条件转化为有纪律的行动。它不评估系统本身是否有效——那是 Layer 5 的职责。

### Layer 5 — Feedback & Behaviour

#### Objective

Layer 5 exists to turn records into learning: it reviews every trading day against the plan, evaluates both the system and the trader, and converts what happened into structured improvement.

Layer 5 的存在目的，是把记录变成学习：它对照计划复盘每一个交易日，同时评估系统与交易者，并把发生过的一切转化为结构化的改进。

Layer 5 always evaluates two different things, and never confuses them: whether the system made good decisions, and whether the trader executed the system. A losing day can be perfect execution. A winning day can be terrible execution.

Layer 5 永远评估两件不同的事，并且绝不混淆它们：系统是否做出了好的决策，以及交易者是否执行了系统。亏损的一天可能是完美的执行，盈利的一天可能是糟糕的执行。

Profit is not proof. Outcome quality and decision quality are recorded separately, because the market can reward a bad process and punish a good one on any single day.

盈利不是证明。结果质量与决策质量分开记录，因为在任何单独的一天里，市场都可能奖励坏的过程、惩罚好的过程。

#### Core Question

Did the system work today — and did I work the system?

今天系统起作用了吗——以及，我按系统做了吗？

#### Inputs

- Execution Log and In-System / Out-of-System Classification from Layer 4（来自 Layer 4 的执行日志与系统内/系统外分类）

- Focus List, Ignore List, and Tomorrow Plan from Layer 3（来自 Layer 3 的聚焦清单、忽略清单与明日计划）

- Layer 1 and Layer 2 outputs for the day（当日 Layer 1 与 Layer 2 的输出）

- Actual market outcomes of focused and ignored opportunities（被聚焦与被忽略机会的实际市场结果）

- Historical review records from Knowledge Base（来自知识库的历史复盘记录）

#### Core Components

##### Daily Review

The Daily Review compares plan against reality, item by item: what was planned, what triggered, what was done, and what happened afterwards.

每日复盘逐项对照计划与现实：计划了什么，什么被触发了，做了什么，之后发生了什么。

The Daily Review is structured, not narrative. It answers the same fixed questions every day, so that days become comparable and patterns become visible over time.

每日复盘是结构化的，不是随笔式的。它每天回答同一组固定的问题，使日与日之间可以比较，使模式随时间变得可见。

##### Decision Quality Assessment

Every executed trade is placed into one of four categories: In-System win, In-System loss, Out-of-System win, Out-of-System loss.

每一笔已执行的交易被归入四个类别之一：系统内盈利、系统内亏损、系统外盈利、系统外亏损。

The categories are not equally dangerous. An In-System loss is tuition paid to a working process. An Out-of-System win is the most dangerous outcome of all, because it rewards the exact behaviour the system exists to eliminate.

这四个类别的危险程度并不相等。系统内亏损是交给一个正常运转的过程的学费。系统外盈利是所有结果中最危险的一种，因为它奖励的恰恰是系统存在的目的所要消除的行为。

Inaction is also a decision and is reviewed with the same seriousness: a trigger that occurred but was not acted upon is a deviation, exactly as an entry without a trigger is.

不行动也是一种决策，并以同样的严肃程度被复盘：触发条件发生了却没有执行，与没有触发却买入，同样都是偏离。

##### Ignore List Review

The Ignore List is reviewed against what actually happened: did the eliminated opportunities fail as expected, or did they succeed without us?

忽略清单会与实际发生的结果对照复盘：被排除的机会是否如预期般失败了，还是在没有我们的情况下成功了？

A correctly ignored opportunity is a system success and is recorded as one. An incorrectly ignored opportunity is not a reason for regret; it is data about which elimination gate fired wrongly and why.

一个被正确忽略的机会是系统的成功，并被作为成功记录下来。一个被错误忽略的机会不是后悔的理由，而是数据——关于哪一道排除关卡误判了、为什么误判。

Over time, the Ignore List Review is what turns "I don't need to trade this" from a hope into an evidence-backed belief.

长期来看，正是忽略清单复盘让"这个我不需要做"从一种希望，变成一种有证据支撑的信念。

##### Behaviour Pattern Recognition

Layer 5 owns the trader's personal execution biases — the counterpart to Layer 1's market-level Decision Bias Warning.

Layer 5 负责交易者个人的执行偏差——它与 Layer 1 的市场层面决策偏差警示互为对应。

Single deviations are recorded; repeated deviations become patterns. Typical patterns include: intraday impulse entries, hesitation on valid triggers, premature exits before conditions occur, position sizes drifting with emotion, revenge trading after losses, and holding an underperforming overnight position past its decision window.

单次偏离被记录；重复的偏离成为模式。典型的模式包括：盘中冲动买入、有效触发前的犹豫、条件未到的提前离场、随情绪漂移的仓位、亏损后的报复性交易、以及不及预期的隔夜仓位被"再等等看"拖过决策窗口。

Recognised patterns are converted into Personal Bias Warnings and fed back into future Tomorrow Plans, so that tomorrow's plan is written with full knowledge of how this trader has historically failed.

被识别的模式会转化为个人偏差警示，反馈进未来的明日计划——使明天的计划在书写时，就已经完全了解这位交易者历史上是如何失败的。

##### System Calibration

Layer 5 is where deliberate revision lives. Proposals to change any versioned parameter — Strategy Profile weightings, Risk Parameters, screening thresholds — are generated here, supported by accumulated evidence, and adopted on a fixed cadence.

Layer 5 是"审慎修订"的所在地。任何有版本记录的参数——策略画像权重、风险参数、筛选阈值——的修改提案都在这里产生，由积累的证据支撑，并按固定的周期采纳。

Calibration follows three rules: every change is proposed with evidence, every change is versioned with its reasoning, and no change is ever made intraday or in reaction to a single day's result.

校准遵循三条规则：每一次修改都必须附带证据提出；每一次修改都带版本号并记录理由；任何修改都绝不在盘中进行，也绝不因单日结果而做出。

Feeling that the market has changed is a reason to open an investigation, never a reason to change a parameter.

"感觉市场变了"是启动一项调查的理由，永远不是修改一个参数的理由。

##### Feedback Routing

Layer 5 decides where each piece of learning belongs and routes it accordingly: theme behaviour to Theme Memory, opportunity outcomes to historical opportunity records, execution patterns to Personal Bias Warnings, and calibration evidence to parameter history — all stored in the Knowledge Base.

Layer 5 决定每一份学习成果的归属并相应地分发：题材行为进入主题记忆，机会结果进入历史机会记录，执行模式进入个人偏差警示，校准证据进入参数历史——全部存入知识库。

Nothing learned is allowed to remain only in the trader's head. Memory that is not written down is memory the system does not have.

任何学到的东西都不允许只留在交易者的脑子里。没有被写下来的记忆，就是系统不拥有的记忆。

#### Outputs

Layer 5 produces:

Layer 5 产出：

- Daily Review Report（每日复盘报告）

- Decision Quality Classification（决策质量分类：四象限）

- Ignore List Review（忽略清单复盘）

- Personal Bias Warnings（个人偏差警示）

- Calibration Proposals with evidence（附证据的校准提案）

- Knowledge Base updates（知识库更新）

#### Responsibilities

Layer 5 never changes tomorrow's plan directly and never modifies a parameter on its own. It reviews, recognises, proposes, and routes; adoption of any change remains a deliberate, versioned decision.

Layer 5 绝不直接修改明天的计划，也绝不自行修改任何参数。它复盘、识别、提案、分发；任何修改的采纳，始终是一个审慎的、有版本记录的决定。

Its responsibility is to determine:

它的职责是判断：

- Whether today's system decisions were good, independent of outcome.（今天系统的决策是否是好的，与结果无关。）

- Whether today's execution followed the system, independent of profit.（今天的执行是否遵循了系统，与盈亏无关。）

- Which deviations are becoming patterns.（哪些偏离正在成为模式。）

- What evidence has accumulated for or against current parameters.（支持或反对当前参数的证据积累到了什么程度。）

Layer 4 turns plans into records. Layer 5 turns records into learning. Layer 6 makes learning permanent.

Layer 4 把计划变成记录。Layer 5 把记录变成学习。Layer 6 让学习成为永久。

#### Success Criteria

At the end of Layer 5, the trader should clearly understand:

Layer 5 结束时，交易者应该清楚地知道：

- Whether the system worked today, and whether they worked the system.（今天系统是否起了作用，以及自己是否按系统做了。）

- The honest classification of every trade, including the profitable ones.（每一笔交易的诚实分类，包括赚钱的那些。）

- Whether the ignored opportunities confirmed or challenged the elimination logic.（被忽略的机会是印证了还是挑战了排除逻辑。）

- Which personal patterns tomorrow's plan must defend against.（明天的计划必须防范自己的哪些行为模式。）

Over time, the measure of Layer 5 is a single trend: the share of trading that happens inside the system should rise, and the same mistake should never have to be learned twice.

长期来看，Layer 5 的衡量标准是一个趋势：系统内交易的占比应该不断上升，而同一个错误永远不需要学第二次。

Layer 5 turns every trading day into evidence. It does not store that evidence permanently — that is the responsibility of Layer 6.

Layer 5 把每一个交易日变成证据。它不负责永久保存这些证据——那是 Layer 6 的职责。

### Layer 6 — Knowledge Base

#### Objective

Layer 6 exists to make learning permanent. It is the memory of MIS: the only layer that persists across every trading day, every tool, and every conversation.

Layer 6 的存在目的，是让学习成为永久。它是 MIS 的记忆：唯一跨越每一个交易日、每一个工具、每一次对话而持续存在的一层。

The Knowledge Base stores; it never decides. It performs no analysis, produces no scores, and proposes no changes. Its entire value lies in answering one kind of question, instantly and honestly: what does the system already know?

知识库只负责存储，绝不做决策。它不做任何分析，不产生任何评分，不提出任何修改。它全部的价值在于即时、诚实地回答一类问题：系统已经知道什么？

Within a single day, information flows in one direction, from market to learning. Across days, the Knowledge Base closes the loop: what was learned yesterday becomes an input to every layer today. Memory is how the system compounds.

在单个交易日内，信息沿一个方向流动，从市场到学习。而跨越日与日之间，知识库让这个环闭合：昨天学到的，成为今天每一层的输入。记忆是系统实现复利的方式。

#### Core Question

What does the system already know — and can every layer reach it when it matters?

系统已经知道什么——并且每一层都能在需要的时刻取用它吗？

#### Inputs

- Raw market data: daily quotes, volumes, adjustment events（原始市场数据：日线行情、成交量、复权事件）

- Theme Memory updates from Layer 5（来自 Layer 5 的主题记忆更新）

- Historical Opportunity Records from Layer 5（来自 Layer 5 的历史机会记录）

- Focus and Ignore History from Layer 5（来自 Layer 5 的聚焦与忽略历史）

- Execution Log archive from Layer 5（来自 Layer 5 的执行日志档案）

- Daily Review Reports and Personal Bias Warnings from Layer 5（来自 Layer 5 的每日复盘报告与个人偏差警示）

- Parameter versions and calibration evidence from Layer 5（来自 Layer 5 的参数版本与校准证据）

#### Core Components

##### Market Data Store

The Market Data Store holds objective facts: prices, volumes, and corporate events, for the full market, across years. Facts are the ground truth that every backtest, every calibration, and every memory ultimately stands on.

市场数据库保存客观事实：全市场、跨越多年的价格、成交量与公司事件。事实是每一次回测、每一次校准、每一份记忆最终立足的地面。

Facts and interpretations are stored separately and never mixed. A price is a fact. "This was a false breakout" is an interpretation. The system may revise interpretations; it never revises facts.

事实与解读分开存储，绝不混合。价格是事实，"这是一次假突破"是解读。系统可以修正解读，但绝不修改事实。

##### Learned Knowledge Store

The Learned Knowledge Store holds everything the system has concluded from experience, organised as named registries:

学习知识库保存系统从经验中得出的一切结论，按命名的登记册组织：

- Theme Memory: how themes have historically behaved（主题记忆：题材的历史行为）

- Opportunity Records: how past opportunities evolved and resolved（机会记录：过往机会如何演化与兑现）

- Focus and Ignore History: what was focused, what was excluded, and what happened next（聚焦与忽略历史：聚焦了什么，排除了什么，之后发生了什么）

- Execution Archive: every action and its classification（执行档案：每一个动作及其分类）

- Personal Bias Registry: the trader's recognised patterns（个人偏差登记册：交易者已被识别的行为模式）

- Parameter History: every version of every tunable parameter, with its evidence and reasoning（参数历史：每一个可调参数的每一个版本，及其证据与理由）

##### Memory Integrity

The Knowledge Base is append-only in spirit: records are corrected by adding new entries, never by silently rewriting old ones. Every record carries its timestamp and its source.

知识库在精神上是"只增不改"的：修正记录的方式是新增条目，绝不悄悄改写旧条目。每一条记录都带有时间戳与来源。

Failures are stored with the same care as successes. A memory that flatters is worse than no memory at all, because every future decision will lean on it.

失败与成功被以同等的认真程度保存。一份美化过的记忆比没有记忆更糟糕，因为未来的每一个决策都会依靠它。

##### Retrieval

Memory that cannot be retrieved at decision time does not exist. Every registry is structured and queryable, so that Layer 1 can ask about a theme's history, Layer 3 can ask about past eliminations, and Layer 5 can ask about a pattern's recurrence — each in seconds, not in archaeology.

无法在决策时刻被取用的记忆等于不存在。每一个登记册都是结构化、可查询的：Layer 1 可以查一个题材的历史，Layer 3 可以查过往的排除记录，Layer 5 可以查一个模式的重复次数——都在几秒钟内完成，而不是靠考古挖掘。

##### Tool Independence

MIS knowledge lives in the Knowledge Base, never inside any AI conversation, any chat history, or any single tool. AI assistants read from the Knowledge Base and write to it through Layer 5; they are collaborators of the memory, not the memory itself.

MIS 的知识存在于知识库中，绝不存在于任何 AI 对话、任何聊天记录、任何单一工具之内。AI 助手通过 Layer 5 读取和写入知识库；它们是记忆的协作者，而不是记忆本身。

Any tool in the current workflow can be replaced tomorrow without the system forgetting anything. If losing a conversation would lose knowledge, that knowledge was never properly stored.

当前工作流中的任何工具，明天都可以被替换，而系统不会遗忘任何东西。如果丢失一段对话就会丢失知识，那说明这份知识从未被正确地保存过。

#### Outputs

Layer 6 produces:

Layer 6 产出：

- Theme Memory, served to Layer 1（主题记忆，供 Layer 1 使用）

- Historical Opportunity Records, served to Layer 2（历史机会记录，供 Layer 2 使用）

- Focus History and Personal Bias Warnings, served to Layer 3（聚焦历史与个人偏差警示，供 Layer 3 使用）

- Current versions of the Strategy Profile and Risk Parameters, served to Layer 3 and Layer 4（策略画像与风险参数的当前版本，供 Layer 3 与 Layer 4 使用）

- Execution History, served to Layer 4（执行历史，供 Layer 4 使用）

- Review archives and calibration evidence, served to Layer 5（复盘档案与校准证据，供 Layer 5 使用）

- The complete historical dataset for backtesting and parameter research（用于回测与参数研究的完整历史数据集）

#### Responsibilities

Layer 6 stores and serves. It never analyses, never scores, never filters, and never proposes. Deciding what a memory means is always the responsibility of the layer that reads it.

Layer 6 只存储、只供给。它绝不分析，绝不评分，绝不筛选，绝不提案。一份记忆意味着什么，永远由读取它的那一层来判断。

Its responsibility is to guarantee:

它的职责是保证：

- Nothing learned is ever lost.（学到的东西永不丢失。）

- Nothing stored is ever silently altered.（存下的东西永不被悄悄篡改。）

- Everything stored can be retrieved when a decision needs it.（存下的一切都能在决策需要时被取用。）

- The system's memory outlives every tool that touches it.（系统的记忆比接触它的任何工具都活得更久。）

Layer 5 turns records into learning. Layer 6 makes learning permanent — and returns it to Layer 1 tomorrow morning.

Layer 5 把记录变成学习。Layer 6 让学习成为永久——并在明天早晨把它交还给 Layer 1。

#### Success Criteria

At the end of Layer 6, the system should be able to guarantee:

对 Layer 6 而言，系统应该能够保证：

- Any layer can ask any historical question and receive an honest answer.（任何一层都可以提出任何历史问题，并得到诚实的回答。）

- Every parameter's current value can be traced back through every version to its original reasoning.（每一个参数的当前值，都能沿着每一个版本追溯到最初的理由。）

- The same mistake never has to be learned twice, because the first lesson was written down.（同一个错误永远不需要学第二次，因为第一次的教训已经被写下。）

- The trader could lose every chat history tomorrow and MIS would not forget a single thing.（交易者明天丢失所有聊天记录，MIS 也不会遗忘任何一件事。）

Layer 6 is where MIS stops being a daily routine and becomes a compounding asset.

Layer 6 是 MIS 从一套每日流程，变成一份可复利资产的地方。

---

## MIS Spirit

This sentence best summarizes the entire project:

这句话最能概括整个项目：

MIS is not built to analyse more. It is built to ignore more.

MIS 不是为了分析更多而建，而是为了忽略更多而建。