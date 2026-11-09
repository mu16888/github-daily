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
                知乎  按 zhihu.mode 路由：off 跳过 / openapi 官方内测接口 /
                      web 登录态网页会话（建草稿 → 写正文 → 尝试公开）/ auto 自动择优
                掘金  建草稿 → 发布（Cookie，两步）
                CSDN  saveArticle（Cookie + x-ca 签名）
                所有 Cookie 先规范化（去标签名/换行），所有 Result 统一脱敏
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
| `src/publish.py` | 三平台适配器 + 知乎 A/B/C 通道路由 + Cookie 规范化 + 统一脱敏 + 严格成功判定 |
| `src/schedule.py` | 仿人工发布时间：每日目标时刻、到点闸门、三平台错峰、派发台账 |
| `src/main.py` | 编排、每日配额闸门、去重台账、运行摘要、退出码 |
| `config/settings.yaml` | 打分权重、每日篇数、配额、发布窗口、平台开关、长期授权开关 |
| `config/platforms.yaml` | 端点、字段、长度限制、来源与验证状态（可改，不硬编码） |
| `config/seo.yaml` | 标题模板、标题长度、钩子词表、topics 中文映射、FAQ 模板 |
| `state/published.json` | 跨天去重台账 |
| `drafts/` | 每日成稿归档（Markdown + HTML） |
| `tests/test_pipeline.py` | 离线单测（unittest 原生，CI 真的会执行） |
| `SECRETS.md` | 6 组 Secrets、知乎 A/B/C 三通道、轮换与泄露处置 |

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
| 知乎官方规范要求 `confirmed:true` 且「用户确认预览后」才发（仅 C 通道） | 设计成 `standing_consent` 一次性长期授权开关，默认 false；`confirm_note` 如实写明授权方式，不冒充逐篇预览。B 通道走网页登录态，由本人填 `ZHIHU_COOKIE` 授权 |
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
| 知乎 C | **官方 OpenAPI**（[ZhihuSync](https://github.com/zhihu/ZhihuSync)） | `X-App-Key` + HMAC-SHA256 签名 | `content.html` = HTML | HTTP 200 且 JSON `status == 0` |
| 知乎 B | **登录态网页会话**（[抓包契约](https://github.com/bifrost-proxy/bifrost/blob/main/.agents/skills/zhihu-publish/references/traffic-contract.md)） | Cookie 含 `z_c0` + `_xsrf` → `x-xsrftoken` | 草稿 PATCH 的 `content` = HTML | 建草稿 → 写正文 → `POST /api/v4/content/publish`，必须 HTTP 200 + `code==0` + 解析出 `publish.id` |
| 掘金 | 社区抓包内部接口（[适配器实测 2026-05-11](https://github.com/PsChina/web-publish/blob/main/adapters/juejin.yaml)） | Cookie `sessionid` + 用户级 `uuid` | `mark_content` = Markdown，`edit_type:10` | 建草稿拿 `draft_id` → publish 两步，均需明确成功信号 |
| CSDN | 社区实测内部接口，**官方从未发布公开 REST API** | Cookie + `x-ca-*` 阿里云网关签名 | `content` = HTML，`markdowncontent` = Markdown | HTTP 200 且 JSON `code == 200` |

> 除知乎官方 OpenAPI 外，端点与字段都来自公开社区资料，**多来源对细节存在分歧**，
> 且尚未用你的账号跑通。因此 `config/platforms.yaml` 保留来源与 `note`，
> 成功判定一律收紧（空响应 / WAF 拦截页 / HTTP 非 200 都不算 published）。
> 知乎 B 的第三步「公开发布」可能需要前端动态签名 `x-zse-96`，纯 Cookie 无法保证成功；
> 失败时如实 `failed` 并保留草稿，`web_auto_publish: false` 可退回「只自动建草稿」（状态 `drafted`）。

**凭据现状**：本机重装后 `~/.zhihu/` 不存在，E 盘无掘金/CSDN 的 Cookie 或历史发布脚本残留，
全局 npm 包里也没有发布工具。「以前推得动、现在不行」的根因是凭据随重装丢失，
不是接口关闭。GitHub Secrets 里已有 `JUEJIN_COOKIE` / `JUEJIN_UUID` / `CSDN_COOKIE` 三项，
知乎三项（C 的 APP_KEY/APP_SECRET、B 的 ZHIHU_COOKIE）待补。

### 4.1 首次真发复盘（2026-11-09，如实记录）

run `42616075753`，CI 结论 `success` 只代表流水线没崩，**发布层 `published=0 / failed=2`**：

| 平台 | 根因 | 修复 |
| --- | --- | --- |
| 掘金 | Secret 值把 `cookie\n` 标签名连换行一起复制进去，requests 抛 `InvalidHeader` | `clean_cookie()` 去标签名 / 换行 / 多余空格；清洗后为空判 `skipped` |
| CSDN | `401 HMAC signature does not match`：签名串第二行误写成 `/`，Content-Type 也与请求头不一致 | 签名串第二行改为 Accept 的实际值，Accept / Content-Type 由同一配置生成并逐字一致 |

另有一处**安全事件**：`InvalidHeader` 的异常消息把完整掘金登录态 Cookie 原样带出，
写进公开仓库的 `run-summary.json`。当前文件已覆盖脱敏，但 git 历史里仍有明文，
最可靠的处置是账号本人退出掘金重新登录作废旧 Cookie（详见 `SECRETS.md`）。
代码侧已在 `Result.__post_init__` 对 `detail`/`url` 统一脱敏，`main.py` 的 FATAL 分支同样走脱敏。

---

## 5. 幂等与节流

- 去重键 = `owner/repo`，台账保留 120 天窗口；窗口外的项目允许重新入选。
- **演练（dry_run）不写台账**，可以反复调试而不消耗候选；正式运行出稿即写「已推荐」，保证一个项目只推荐一次。
- 只有 `published`（真发出去了）与 `drafted`（知乎草稿模式，已建草稿）才写平台记录；
  `skipped` / `failed` 不写。`drafted` 也占当天名额，避免每天重复堆草稿。
  发布失败不会自动重发同一篇（避免重复刷屏），需要补发就删掉台账里那一条。
- 没有达标的新项目时**不发文、不凑数**，只记录 `picked: 0`。
- 每天每平台 1 篇，由 `quota.per_day` 硬闸门保证；这是三平台限额的交集，不是随意取的值。
- 每天最多派发一次，由 `schedule.last_dispatched` + 时间闸门保证（详见 §5.2）；手动触发要勾 `force` 才能绕过闸门。
- 搜索接口语法坑（实测）：GitHub 搜索**不支持 `>=` / `<=`**，写错不报错、只是静默忽略条件。
  必须用 `created:>日期` 与 `stars:150..20000`。早期版本用了 `>=`，结果 star 上限失效，选出了 19 万 star 的老项目。

### 5.1 文章结构：先讲解决的问题，再讲功能与用法

顺序固定，标题用口语，不编号：

1. **它解决什么问题** —— 引用 README 里作者自己写的 Why / Motivation / Problem / 背景 章节原文；没有这类章节就如实说「没专门写」，只复述仓库简介与标签
2. 这是个什么项目（description 原文 + 可查证事实，顺手解释 star、协议这些词）
3. 能做什么（README 的 Features 原文；没有就只列语言、标签等能查到的）
4. 新手装起来麻烦吗（可解释的打分信号，用大白话说）
5. 安装教程（README 代码块逐字摘录）
6. 装完怎么上手（Quick Start 原文）
7. 项目档案（表格）
8. 动手前留意（项目会改、协议条款）
9. 常见问题（含「xxx 解决什么问题？」等长尾问题）

痛点只引用作者原文，绝不代为编造「用户很痛 / 效率提升 N 倍 / 某岗位必备」这类话术。
这是「严禁假数据」红线在文案层面的延伸：吸引人可以靠结构、真实数字和搜索词，不能靠编故事。
没有 Why 章节时，改引 README 开头原文（去掉徽章与相对路径图片，避免发出去变死链），
并在截断时回退到句子边界，不把「It ships as a」这种半句话当成原文引用出去。

#### 文案去 AI 味（2026-11-09 按 text-polisher 规范重写）

锋哥反馈「最下面这句不好」「必须去 AI 味」「机器腔小白看不懂」。原来那版是典型模板腔：
中文编号体、开场「本文先讲…再介绍…」、满篇「逐字摘自 / 未检出 / 不编造 / 请以仓库为准」自证、
把内部打分（综合得分 X 分、门槛 Y 分）暴露给读者、页脚自曝「由 GitHub Actions 自动生成并发布」，
还列了 `/search/repositories` 和采集脚本链接 —— 等于自己举报自己批量发文。

现在按 `text-polisher` 的五维规范（直接性 / 节奏 / 信任度 / 活人感 / 精炼度）处理：
- 删自曝、免责、元叙述、金句式收尾、破折号、三段式排比、加粗说明
- 术语换白话：元数据→仓库信息、二次分发→改了再发、运行时→电脑上装的环境、star→收藏数（首次出现给解释）
- 不编造第一手体验。技能建议加「我当时就拍了桌子」这类细节，与本项目的「严禁假数据」红线冲突，明确不采用
- `tests/test_pipeline.py` 加了 `test_no_machine_tone_in_article` 和 `test_plain_language_for_beginners` 两条护栏，
  把禁用词和术语解释写成机器可检查的断言，防止以后改回模板腔

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

1. ✅ 本地 `python -m src.main --dry-run` 跑通出稿；代码已推送（HEAD `4d6a23d`）。
2. ✅ `.github/workflows/daily.yml` 因 `workflow` scope 限制，已由账号本人于 2026-11-09
   在 GitHub 网页新建提交（`bcb95eb`），远程内容与本地逐字一致，Actions 识别为 `active`。
3. ✅ 手动 `workflow_dispatch`（`dry_run=true` + `force=true`）演练跑通：
   run `42601483641`，12 个步骤全 success，闸门输出 `should_run=true`，49 单测通过，
   入选 1 个项目并归档，`published=0 / failed=0`。
4. ✅ 已填 3 组 Secrets（掘金 2 + CSDN 1），`publish.enabled=true` 的凭据探活演练跑通
   （run `42613425797`：掘金 / CSDN `dry_run`、知乎 `skipped`）。
5. ⚠️ 2026-11-09 首次真发失败（详见 §4.1），已把 `publish.dry_run` 改回 `true` **暂停对外发文**，
   并修好 Cookie 规范化、CSDN 签名、统一脱敏三处，单测 55 → 77 全绿。
6. **待做**：① 账号本人退出掘金重新登录并更新 `JUEJIN_COOKIE`；② 补 `ZHIHU_COOKIE`（B 通道）
   或申请内测拿 `ZHIHU_APP_KEY`/`ZHIHU_APP_SECRET`（C 通道），或维持 A 跳过；
   ③ 在 GitHub 网页**整份覆盖** `.github/workflows/daily.yml`，注入 `ZHIHU_COOKIE` 环境变量；
   ④ 再跑一次 `dry_run` 演练确认三平台状态；⑤ 把 `dry_run` 改回 `false`，手动 `force` 真发并人工核稿。
7. 以后每次改 `.github/workflows/daily.yml` 都仍需本人在 GitHub 网页整份覆盖提交，
   否则云端还是旧版本（推不上去，也不会报错提醒）。

---

## 7. 已知风险（不隐藏）

- **知乎 B 通道未经实测**：公开抓包契约显示公开发布可能需要 `x-zse-96` 动态签名，
  纯 Cookie 不保证成功；失败时草稿仍在，可改 `web_auto_publish: false` 只自动建草稿人工发。
  该通道同样是登录态发文，风控代价与掘金 / CSDN 同级。
- **账号风控**：掘金/CSDN（以及知乎 B）靠登录 Cookie，从 GitHub 境外机房 IP 发文属于异常设备指纹，
  有触发风控的可能。这是「云端全发」相对「本机发」的主要代价；缓解手段只有低频（每天 1 篇）、
  失败即停、以及凭据可随时撤销。若出现验证短信/异常登录提示，把对应平台 `enabled` 改 false 即可。
- **Cookie 会过期**（掘金约 30 天、CSDN 依登录态），需按 `SECRETS.md` 定期更新 Secrets。
- **接口随时可能变**：非官方接口没有兼容性承诺，响应结构变化会在 `run-summary.json` 里如实报 `failed`。
- **文章靠模板拼接，不调大模型**：云端没有免费推理，所以不编造事实。可读性靠 5.1 节的文风规范和测试护栏保证，不再用「偏说明书」当借口。
