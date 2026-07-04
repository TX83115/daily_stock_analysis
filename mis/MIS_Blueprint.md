
# MIS Blueprint
---
## Design Philosophy

MIS exists to help the trader understand the market, focus on the highest-quality opportunities， execute consistently, and continuously improve through feedback. 
MIS不预测市场，不寻找最低点，也不猜测未来。MIS 只识别已经被市场确认的机会，帮助交易者在最早的可执行阶段理解市场、聚焦机会、跟随趋势、稳定执行，并通过持续反馈不断优化整个交易系统。
Focus is the reduction of decision space. 
聚焦的本质，不是推荐股票，而是不断缩小交易者需要做出的决策空间。
Every layer must reduce uncertainty. Never increase complexity. 
每一层都必须降低交易的不确定性，而不是增加信息复杂度。
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

## System Architecture

MIS is designed as a multi-layer decision system. Each layer has only one responsibility. Information flows from market data to trading execution, and finally back into learning. No layer should duplicate the responsibility of another layer.
MIS 是一个多层决策系统。每一层都只有一个明确职责。信息始终沿着同一个方向流动：市场 → 理解 → 机会 → 计划 → 执行 → 反馈 → 学习。每一层都不能重复另一层的工作。

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
- Leading sectors（领涨板块）
- Market Leaders（市场龙头）
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

- Limit-up height（连板高度）
- Limit-up success rate（涨停封板成功率）
- Yesterday's Limit-up Premium（昨日涨停溢价率）
- Limit-up Failure Rate（封板失败率）
- Broken board rate（炸板率）
- Market breadth（市场涨跌家数）
- Capital concentration（资金集中度）
- Sector rotation（板块轮动）
- Cross-market Confirmation（沪深主板 / 创业板 / 科创板共振）
- Intraday participation（盘中承接强度）
- Risk appetite（市场风险偏好）

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
- Historical Memory（历史表现）

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
- Follower（跟风）
- Replacement Leader（卡位龙头）
- Noise（杂毛）

Leadership quality directly influences opportunity sustainability.

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