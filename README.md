# github-daily

每天从 GitHub 挑一个**简单好用、适合小白**的开源项目，生成一篇含真实安装步骤的中文介绍文章，
自动发布到 **知乎 / 掘金 / CSDN**，并把草稿与去重台账归档回仓库。

运行在 GitHub Actions 上，公开仓库标准 runner 免费，本机不需要开机。
凭据存 GitHub Secrets —— 重装系统不会再丢。

- 框架与设计依据：[DESIGN.md](DESIGN.md)
- 凭据获取与上线步骤：[SECRETS.md](SECRETS.md)

## 它不会做的事（先说清楚）

- **不编造事实**：所有安装命令、star 数、许可证、创建时间只来自 GitHub API 与 README 原文，安装代码块逐字摘录。没有检出靠谱项目时当天不发文，不凑数。
- **痛点也不编**：文章第一节讲「解决什么问题」，只引用 README 里作者自己写的 Why / Motivation / Problem 原文；没写就如实标注「未检出」，不代为编造使用场景或效果。结构是先痛点 → 再功能 → 再安装用法。
- **不用大模型**：GitHub Models 已于 2026-07-30 退役，云端没有官方免费 LLM。文章按结构化模板生成，读起来偏说明书，但数字和命令不会被"润色"改错。
- **不破解反爬**：知乎走官方 OpenAPI；掘金与 CSDN 是登录态内部接口，靠你自己的 Cookie，接口变更或风控时会如实报失败，不伪装成成功。
- 三个平台里**只有知乎有官方发布 API**。掘金和 CSDN 的接口由社区实测整理，官方从未发布公开 REST API。
- **每天每平台只发 1 篇**：这是三平台限额的交集（掘金硬性 1 篇/天且第 2 篇会静默失效），代码里有硬闸门，手动重复触发也不会刷屏。详见 [DESIGN.md §3.1](DESIGN.md)。
- **不卡点发布**：不会每天固定同一分钟发，也不会三家平台同一秒三连发。见下一节。

## 发布时间：每天错位

GitHub Actions 的 cron 只能写固定时刻，所以改成「每 15 分钟唤醒一次 + 到点闸门」：
用 `HMAC(日期 + 盐)` 确定性算出当天唯一目标时刻（北京 08:30–10:45，周末顺延 45 分钟，
分钟避开整 5 分、秒避开 0），没到点空跑退出，到点才发；知乎 / 掘金 / CSDN 再依次错开
90–420 秒。一天 16 次唤醒只有 1 次真正跑流水线，发完记 `last_dispatched`，当天不再重复。

```
$ python -m src.schedule --preview 5
日期           星期    目标时刻     知乎 / 掘金 / CSDN 实际发出时刻
2026-11-09   周一    09:28:20     09:28:20 / 09:31:51 / 09:35:32
2026-11-10   周二    08:43:12     08:43:12 / 08:49:37 / 08:54:09
2026-11-11   周三    09:49:38     09:49:38 / 09:55:28 / 10:00:05
```

确定性而非真随机是刻意的：某一棒被 GitHub 排队延迟或取消时，下一棒算出的还是同一个
时刻，会补发而不是重新随机，不会漏发也不会重复发。窗口、盐、错峰幅度都在
`config/settings.yaml` 的 `schedule` 段，改 `salt` 就换一整套时间序列。
手动触发 `workflow_dispatch` 时勾 `force` 可立即跑，不受闸门限制。详见 [DESIGN.md §5.2](DESIGN.md)。

## 标题与 SEO

三个平台用**不同的标题**，不是一句通稿发三家：知乎偏问题式、掘金偏实操、CSDN 关键词前置吃百度收录。
标题 = 项目名（核心搜索词）+「怎么用 / 安装 / 上手 / 教程」（长尾词）+ 真实钩子。
钩子只由检测到的信号触发（单行安装、许可证、star 数、新建时间、topics），**不用「神器 / 必看 / 全网最全」这类无法证实的词**。
正文另有搜索摘要段、H2 关键词、FAQ 长尾问题，CSDN 标签带项目名。全部规则在 `config/seo.yaml`，可改。

## 本地跑

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v     # 离线单测，不联网
python -m src.schedule --preview 14         # 预览未来 14 天发布时刻，不联网
python -m src.main --dry-run                # 真实抓一次 GitHub，出稿但不发文
```

`--dry-run` 会生成：

```
drafts/YYYY-MM-DD/owner__repo.md      # Markdown 成稿
drafts/YYYY-MM-DD/owner__repo.html    # HTML 成稿（知乎 / CSDN 用）
run-summary.json                      # 本次运行摘要，含每个平台的状态
```

常用参数：`--date 2026-11-09`、`--limit 2`、`--no-publish`（完全跳过发布层）。

## 目录

```
.github/workflows/daily.yml   定时 + 单测 + 跑流水线 + 归档推送
src/discover.py               候选搜索 / README 事实抽取 / 可解释打分
src/compose.py                中文成稿 + 自带 Markdown→HTML
src/seo.py                    平台化标题 / 摘要 / 标签 / FAQ
src/schedule.py               仿人工发布时间 / 到点闸门 / 三平台错峰
src/publish.py                知乎 / 掘金 / CSDN 三个发布适配器
src/main.py                   编排、每日配额闸门、去重台账、运行摘要
config/settings.yaml          打分权重、每日篇数、配额、发布窗口、发布开关、长期授权
config/platforms.yaml         端点 / 字段 / 长度限制 / 来源标注
config/seo.yaml               标题模板 / 钩子词表 / 标签与 FAQ
state/published.json          跨天去重台账
drafts/                       每日成稿归档
tests/                        离线单测
```

## 三个开关决定行为

`config/settings.yaml`：

| 开关 | 默认 | 含义 |
| --- | --- | --- |
| `publish.enabled` | `false` | 总开关；false 时只出稿归档 |
| `publish.dry_run` | `true` | true 时只组装请求，不向发布端点发请求 |
| `zhihu.standing_consent` | `false` | 知乎官方要求用户确认后才能 `confirmed:true`；改成 true 代表你一次性长期授权，且不会再逐篇人工预览 |

三者都要显式打开，才会真正自动发文。这是刻意设计：默认状态下这个仓库怎么跑都不会对外发东西。

## 发布结果判定

| 状态 | 含义 | 台账行为 |
| --- | --- | --- |
| `published` | 平台明确返回成功 | 记录发布 URL 与时间 |
| `skipped` | 缺 Secrets / 未开长期授权 | 不写发布记录 |
| `dry_run` | 只组装请求 | 演练无副作用，台账完全不动 |
| `failed` | 接口返回失败或网络异常 | 不写发布记录 |

正式运行（非演练）出稿后，该项目即进入去重台账，保证同一个项目不会被重复推荐。
发布失败**不会自动重发同一篇**（避免重复刷屏）；确需补发，删掉 `state/published.json`
里对应条目再跑一次即可。演练模式**不写 `seen` 去重台账**，候选与发布记录都不会被消耗，
所以可以放心反复调试；只有 CI 里闸门放行的那一棒（含演练）会另写
`schedule.last_dispatched` 这个调度标记，避免当天 15 分钟一次的唤醒把流水线重复跑 16 遍。
本地直接跑 `python -m src.main --dry-run` 不传 `--dispatched`，完全不碰台账。

知乎**必须**看响应 JSON 的 `status == 0`，HTTP 200 也可能是失败；CSDN 看 `code == 200`；
掘金是「建草稿 → 发布」两步。这些判定都在 `src/publish.py` 里，不靠猜。

## 许可证

MIT。本项目与所介绍的任何项目、以及知乎 / 掘金 / CSDN 均无官方关联。
