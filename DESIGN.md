# 设计定稿：每日 GitHub 小白项目介绍 → 知乎 / 掘金 / CSDN

选定方案：**云端全发**。凭据全部放 GitHub Secrets，GitHub Actions 完成
「抓取 → 筛选 → 核查 → 成稿 → 归档 → 发布 → 记台账」全流程，本机不需要开机。

---

## 1. 数据流

```
GitHub Actions (公开仓库 / ubuntu-latest / 免费)
   │  cron 每 15 分钟唤醒（UTC 00:08~03:53）+ 手动 workflow_dispatch
   ▼
[0] gate       用 HMAC(日期+盐) 确定性算出当天唯一发布时刻；未到点空跑退出，
               该棒轮到才 sleep 对齐到精确分钟/秒；发完记 last_dispatched → §5.2
   ▼
[1] discover    GitHub Search API 取候选（近 45 天创建/活跃，star 150..20000）
                → 抓 README 原文
   ▼
[2] score       小白友好打分：单命令安装 / Quick Start / 有 License /
                不需编译 / 不依赖额外服务；WIP、README 过短、要 API key 扣分
                → 低于门槛直接丢弃，不凑数
   ▼
[3] facts       所有写进文章的数字与命令，只来自 API 字段与 README 原文
                （不调用 LLM，不生成、不补全任何安装命令）
   ▼
[4] compose     结构化模板拼中文长文 → Markdown + HTML 两份
                （知乎/CSDN 要 HTML，掘金要 Markdown）
   ▼
[5] archive     drafts/YYYY-MM-DD/{owner__repo}.md / .html
   ▼
[6] publish     先过每日配额闸门（每平台 1 篇），再走三个独立适配器：
                知乎  官方 OpenAPI（HMAC 签名，confirmed:true）
                掘金  建草稿 → 发布（Cookie，两步）
                CSDN  saveArticle（Cookie + x-ca 签名）
                各平台用各自的 SEO 标题 / 摘要 / 标签
   ▼
[7] ledger      state/published.json 去重台账（只记真正发布成功的）
   ▼
[8] commit      git commit & push 归档 + 保活（防 60 天禁用定时任务）
```

**失败隔离**：任一平台挂掉不影响其他平台，也不影响出稿归档。
抓取/成稿阶段失败则让 CI 变红（不静默吞异常）。

---

## 2. 目录与职责

| 路径 | 职责 |
| --- | --- |
| `.github/workflows/daily.yml` | 定时触发、装依赖、跑单测、跑流水线、归档推送 |
| `src/discover.py` | 候选搜索、README 抓取、事实抽取、可解释打分 |
| `src/compose.py` | 中文文章模板 + 自带 Markdown→HTML（少一个依赖） |
| `src/seo.py` | 按平台生成标题 / 摘要 / 标签 / FAQ，钩子只认真实信号 |
| `src/publish.py` | 三个发布适配器 + 统一结果模型 + 成功判定 |
| `src/schedule.py` | 仿人工发布时间：每日目标时刻、到点闸门、三平台错峰、派发台账 |
| `src/main.py` | 编排、每日配额闸门、去重台账、运行摘要、退出码 |
| `config/settings.yaml` | 打分权重、每日篇数、配额、发布窗口、平台开关、长期授权开关 |
| `config/platforms.yaml` | 端点、字段、长度限制、来源与验证状态（可改，不硬编码） |
| `config/seo.yaml` | 标题模板、标题长度、钩子词表、topics 中文映射、FAQ 模板 |
| `state/published.json` | 跨天去重台账 |
| `drafts/` | 每日成稿归档（Markdown + HTML） |
| `tests/test_pipeline.py` | 离线单测（unittest 原生，CI 真的会执行） |
| `SECRETS.md` | 5 组 Secrets 的获取步骤与轮换提醒 |

依赖只有 `requests` + `PyYAML`，无浏览器、无数据库、无模型服务。

---

## 3. 决定这套架构的硬约束（2026-11-09 核查）

| 约束 | 对设计的影响 |
| --- | --- |
| GitHub Models 已于 2026-07-30 全面退役，云端无官方免费 LLM | 用结构化模板成稿，不调付费推理。副作用是文章不会编造安装命令，正合「严禁假数据」 |
| 公开仓库标准 runner 免费 | 零成本成立 |
| 公开仓库 scheduled workflow 60 天无活动会被自动禁用 | 每天把草稿 commit 回仓库，天然保活 |
| `GITHUB_TOKEN` 1,000 次/小时/仓库；搜索接口另有更严的独立限额 | 每天只搜 3 次、每次 ≤8 条，命中 403/429 按 `retry-after` 退避 |
| cron 按 UTC、只能写固定时刻，整点高负载还会排队延迟 | 每 15 分钟唤醒 + 代码层到点闸门；唤醒刻度用 08/23/38/53 分避开整点排队；实际发布时刻由 §5.2 决定 |
| 知乎官方规范要求 `confirmed:true` 且「用户确认预览后」才发 | 设计成 `standing_consent` 一次性长期授权开关，默认 false；`confirm_note` 如实写明授权方式，不冒充逐篇预览 |
| 知乎正文必须 HTML、每日上限 50 次、HTTP 200 不等于成功（`status==0` 才算） | 自带 HTML 转换；每天只发 1 篇；严格判定 JSON |
| 掘金/CSDN 是登录态内部接口，从境外 CI IP 发出有风控风险 | 失败不影响归档；凭据可随时从 Secrets 撤销；文档如实写明风险，不承诺「稳定」 |

### 3.1 三平台每日发文上限（2026-11-09 核查，决定 `picks_per_day = 1`）

| 平台 | 每天能发几篇 | 依据 | 可信度 |
| --- | --- | --- | --- |
| 知乎 | 官方 OpenAPI 文档写 **50 次/天**；但网页端实测是「距上一篇 ≥24 小时」的**滚动限流**，实际约 1 篇/天 | [官方 publish-openapi.md](https://github.com/zhihu/ZhihuSync/blob/main/zhihu-publish/reference/publish-openapi.md) + 社区实测 | 官方 + 社区 |
| 掘金 | **1 篇/天**。坑：第 2 篇会返回 `err_no: 0`、看似成功，但**不会出现在文章列表里**（静默失效） | 社区多来源实测一致 | 社区实测 |
| CSDN | 官方 2025-11-03 [公告](https://blog.csdn.net/blogdevteam/article/details/154347814) 确认「下调每日发文上限」，但正文未列数字；官方 VIP 页写基础版 5 篇/日、专业版 15 篇/日；免费用户社区实测约 1~2 篇/天 | 官方公告 + 官方 VIP 页 + 社区实测 | 部分官方 |

**结论：取三者交集 = 每天每平台 1 篇，不能调高。** 尤其掘金的静默失效最危险——多发不会报错，只会白写。
所以 `quota.per_day` 写进配置并在发布前做硬闸门：先读台账统计当天该平台已成功篇数，
达上限直接 `skipped`，手动重复触发 workflow 也不会刷屏。

CSDN 那个"付费提高发文额度"是平台商业策略，与本项目无关；我们按免费账号最保守的 1 篇设计。

### 3.2 标题与 SEO（要能被搜到，但不能编造）

标题由 `src/seo.py` + `config/seo.yaml` 按平台分别生成，不是一句通稿发三家：

| 平台 | 风格 | 标题长度上限（保守值） | 例子 |
| --- | --- | --- | --- |
| 知乎 | 问题式 / 观点式 | 50 字 | `xxx 怎么用？一行命令就能装好，MIT 开源协议｜安装到上手全流程` |
| 掘金 | 技术 + 实操 | 80 字（适配器实测） | `xxx 上手实录：一行命令就能装好，附完整安装命令` |
| CSDN | 教程向、关键词前置、吃百度收录 | 50 字 | `xxx 安装使用教程：一行命令就能装好（附完整命令）` |

搜索落点：**项目名**（核心词）+「怎么用 / 安装 / 上手 / 教程」（长尾意图词）+ 真实钩子。
钩子只允许由检测到的信号触发：单行安装命令、SPDX 许可证、star 数、创建时间 ≤90 天、仓库 topics；
检测不到就用兜底事实「README 里有现成安装命令」。**不写「神器 / 必看 / 全网最全 / 5 分钟搞定」**这类无法证实的词。

正文侧的 SEO：开头一段面向搜索引擎的摘要、H2 里带项目名与「安装教程 / 怎么上手」、
文末 FAQ 三个长尾问题（`xxx 怎么安装？` / `xxx 免费吗？` / `xxx 适合新手吗？`），
答案全部由真实字段支撑；CSDN 标签里带项目名，便于站内搜索命中。标题长度按各平台限制自动裁剪，
优先按分隔符丢尾部短语，不截出半句话。

---

## 4. 三平台通道事实（不美化）

| 平台 | 性质 | 鉴权 | 正文 | 成功判定 |
| --- | --- | --- | --- | --- |
| 知乎 | **官方 OpenAPI**（[ZhihuSync](https://github.com/zhihu/ZhihuSync)） | `X-App-Key` + HMAC-SHA256 签名 | `content.html` = HTML | JSON `status == 0` |
| 掘金 | 社区抓包内部接口（[适配器实测 2026-05-11](https://github.com/PsChina/web-publish/blob/main/adapters/juejin.yaml)） | Cookie `sessionid` + 用户级 `uuid` | `mark_content` = Markdown，`edit_type:10` | 建草稿拿 `draft_id` → publish 两步 |
| CSDN | 社区实测内部接口，**官方从未发布公开 REST API** | Cookie + `x-ca-*` 阿里云网关签名 | `content` = HTML，`markdowncontent` = Markdown | JSON `code == 200` |

> 后两者的端点、字段有多来源一致的公开依据，但**尚未用你的账号实测**。
> 因此 `config/platforms.yaml` 里保留了来源与 `note`，并且默认 `dry_run=true`。
> 首次接入请先用 `--dry-run` 观察请求组装，再单独发一篇验证响应结构。

**凭据现状**：本机重装后 `~/.zhihu/` 不存在，E 盘无掘金/CSDN 的 Cookie 或历史发布脚本残留，
全局 npm 包里也没有发布工具。所以「以前推得动、现在不行」的根因是凭据随重装丢失，
不是接口关闭——把凭据搬到 GitHub Secrets 正是这套方案要解决的问题。

---

## 5. 幂等与节流

- 去重键 = `owner/repo`，台账保留 120 天窗口；窗口外的项目允许重新入选。
- **演练（dry_run）不写台账**，可以反复调试而不消耗候选；正式运行出稿即写「已推荐」，保证一个项目只推荐一次。
- 只有 `status == published` 才写平台发布记录与 URL；`skipped` / `failed` 不写。发布失败不会自动重发同一篇（避免重复刷屏），需要补发就删掉台账里那一条。
- 没有达标的新项目时**不发文、不凑数**，只记录 `picked: 0`。
- 每天每平台 1 篇，由 `quota.per_day` 硬闸门保证；这是三平台限额的交集，不是随意取的值。
- 每天最多派发一次，由 `schedule.last_dispatched` + 时间闸门保证（详见 §5.2）；手动触发要勾 `force` 才能绕过闸门。
- 搜索接口语法坑（实测）：GitHub 搜索**不支持 `>=` / `<=`**，写错不报错、只是静默忽略条件。
  必须用 `created:>日期` 与 `stars:150..20000`。早期版本用了 `>=`，结果 star 上限失效，选出了 19 万 star 的老项目。

### 5.1 文章结构：先讲解决的问题，再讲功能与用法

十节固定顺序：

1. **{项目名} 解决什么问题（先看痛点）** —— 引用 README 里作者自己写的 Why / Motivation / Problem / 背景 章节原文；**没有这类章节就如实写「未检出，不编造痛点」**，只复述仓库自述与 topics
2. 项目是什么（description 原文 + 结构化事实）
3. 核心功能（README 的 Features 原文；没有就只列语言、topics 等可查证字段）
4. 为什么适合新手（可解释打分信号）
5. 安装教程（README 代码块逐字摘录）
6. 怎么上手（Quick Start 原文）
7. 项目档案（表格）
8. 需要注意
9. FAQ（含「xxx 解决什么问题？」等长尾问题）
10. 信息来源

痛点只引用作者原文，绝不代为编造「用户很痛 / 效率提升 N 倍 / 某岗位必备」这类话术。
这是「严禁假数据」红线在文案层面的延伸：吸引人可以靠结构、真实数字和搜索词，不能靠编故事。
没有 Why 章节时，改引 README 开头原文（去掉徽章与相对路径图片，避免发出去变死链），
并在截断时回退到句子边界——不把「It ships as a」这种半句话当成原文引用出去。

### 5.2 发布时间：每天错位，不卡同一个点

每天固定 09:17 发、三个平台同一秒三连发，是很明显的自动化特征。GitHub Actions 的
cron 只能写固定时刻，写不出「每天随机」，所以改成**高频唤醒 + 确定性随机目标时刻 + 到点闸门**：

| 环节 | 做法 |
| --- | --- |
| 唤醒 | `cron: '8,23,38,53 0-3 * * *'`（UTC 00:08~03:53 = 北京 08:08~11:53），每 15 分钟一次，非整点刻度避开排队。一天 16 次唤醒，只有 1 次真正跑流水线 |
| 定时刻 | `src/schedule.py` 用 `HMAC-SHA256(salt, 日期)` 算出当天**唯一**目标时刻，落在北京 08:30–10:45（周末整体顺延 45 分钟）。分钟避开 5 的倍数、秒避开 0 |
| 闸门 | 未到点 → 立即空跑退出（不抓 GitHub、不发文）；目标落在「本棒~下一棒」之间 → sleep 到精确时刻再放行；已过目标（GitHub 排队延迟 / 上一棒被取消）→ 立即补发 |
| 错峰 | 知乎 / 掘金 / CSDN 按发布顺序累加 90–420 秒，三篇不在同一分钟发出；dry_run 与配额跳过时不等待 |
| 防重 | `state/published.json` 里记 `schedule.last_dispatched`；当天后续唤醒直接 `done` 退出，与 `quota.per_day=1` 形成双保险 |

**确定性而非真随机**是刻意选择：某次唤醒失败时，下一棒算出的还是同一个目标时刻，
会补发而不是重新随机，因此不会漏发，也不会重复发。想换一整套时间序列，改
`config/settings.yaml` 里的 `schedule.salt` 即可。

`python -m src.schedule --preview 14` 可以本地预览未来两周每天的实际发出时刻（含三平台错峰），
不需要联网、不碰任何账号。

幂等细节：只有闸门放行的那一棒（CI 传 `--dispatched`）在**成功抓到候选**后立刻把
`last_dispatched` 落盘，即使后面成稿或发布抛异常，当天也不会再发第二次；
抓候选本身失败（如 API 403）则不写，留给后续唤醒重试。演练这一棒同样写调度标记
（否则当天会重复跑 16 遍流水线），但**不写 `seen` 去重台账**，候选与发布记录依然不会被
演练消耗。本地直接跑 `python -m src.main --dry-run` 不传 `--dispatched`，
既不经过闸门也不写任何台账，可以一天内反复调试，更不会误把「今天已派发」推上去挡住云端。

---

## 6. 上线顺序

1. 本地 `python -m src.main --dry-run` 跑通出稿（已完成）。
2. 建公开仓库、推送代码；`.github/workflows/` 受 `workflow` scope 限制，需账号本人在 GitHub 网页提交那一个文件。
3. 按 `SECRETS.md` 填 5 组 Secrets。
4. 先手动 `workflow_dispatch` 且勾 `dry_run=true`，看 `run-summary.json`。
5. 把 `config/settings.yaml` 的 `publish.enabled` 改 `true`、`dry_run` 改 `false`，
   并按知乎官方要求把 `zhihu.standing_consent` 改 `true`（这一步即你的一次性授权）。
6. 手动触发一次真发（勾上 `force` 绕过时间闸门），核验三个平台各出现 1 篇，再交给每日 cron。
   注意：`.github/workflows/daily.yml` 因 `workflow` scope 限制仍需本人在 GitHub 网页提交，
   改了发布窗口后要用新版本覆盖旧文件，否则云端还是旧的固定时间。

---

## 7. 已知风险（不隐藏）

- **账号风控**：掘金/CSDN 靠登录 Cookie，从 GitHub 境外机房 IP 发文属于异常设备指纹，
  有触发风控的可能。这是「云端全发」相对「本机发」的主要代价；缓解手段只有低频（每天 1 篇）、
  失败即停、以及凭据可随时撤销。若出现验证短信/异常登录提示，把对应平台 `enabled` 改 false 即可。
- **Cookie 会过期**（掘金约 30 天、CSDN 依登录态），需按 `SECRETS.md` 定期更新 Secrets。
- **接口随时可能变**：非官方接口没有兼容性承诺，响应结构变化会在 `run-summary.json` 里如实报 `failed`。
- **文章风格偏说明书**：无 LLM 润色，这是为了不编造事实而主动接受的可读性代价。
