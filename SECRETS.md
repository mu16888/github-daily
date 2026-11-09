# 上线清单：GitHub Secrets、知乎三条通道与当前状态

「云端全发」的全部凭据放在 **GitHub 仓库 → Settings → Secrets and variables → Actions**。
加密存储、不进代码、不打日志，重装系统不会丢。

> ⚠️ Cookie 等同于账号登录态。不要贴进代码、Issue、聊天或任何文件；只填在 GitHub Secrets 里。
> 这套工具只发**自己生成的公开技术文章**，不用于操作社交账号的登录态。

---

## 〇、2026-11-09 当前状态（先看这个）

| 项 | 状态 |
| --- | --- |
| 定时 / 时间闸门 / 出稿 / 归档 | ✅ 已打通，Actions `daily-github-picks / active` |
| 发布总开关 `publish.enabled` | ✅ `true`（适配器会实例化） |
| **`publish.dry_run`** | ⚠️ **`true` —— 已暂停对外发文**，定时跑只出稿归档 |
| 已填 Secrets | `JUEJIN_COOKIE`、`JUEJIN_UUID`、`CSDN_COOKIE` |
| 待补 Secrets | `ZHIHU_COOKIE`（B）、`ZHIHU_APP_KEY` + `ZHIHU_APP_SECRET`（C） |
| workflow | ⚠️ 需再网页覆盖一次，注入 `ZHIHU_COOKIE` 环境变量 |
| 首次真发 | ❌ run `42616075753`：`published=0 / failed=2`，原因与修复见 §四 |

**一句话**：现在怎么跑都不会对外发文。要恢复自动发，按 §五 的五步走。

---

## 一、6 组 Secrets

| Secret 名 | 通道 | 从哪来 | 当前 |
| --- | --- | --- | --- |
| `JUEJIN_COOKIE` | 掘金 | 登录 juejin.cn → F12 → 网络 → 主文档 →「标头」→ `Cookie:` 右键「复制值」 | ✅ 已填，**但已泄露，需作废重抓** |
| `JUEJIN_UUID` | 掘金 | 同一批请求 URL 里的 `uuid=` 参数（不是 Cookie 字段） | ✅ 已填 |
| `CSDN_COOKIE` | CSDN | 登录 www.csdn.net → F12 → 网络 → 主文档 →「标头」→ `Cookie:` 复制值 | ✅ 已填 |
| `ZHIHU_COOKIE` | 知乎 B | 登录 zhihu.com → F12 → 网络 → 任意请求 → `Cookie:` 复制值，须含 `z_c0` 与 `_xsrf` | ⬜ 待填 |
| `ZHIHU_APP_KEY` | 知乎 C | 知乎主页 URL 里的用户名（免申请），或官方凭据文件 | ⬜ 需内测 |
| `ZHIHU_APP_SECRET` | 知乎 C | 官方共享凭据文件 `~/.zhihu/openapi-credentials.json`（字段 `ZHIHU_OPENAPI_APP_SECRET`） | ⬜ 需内测 |

`GITHUB_TOKEN` 由 Actions 自动注入，不需要手动创建。

**填 Cookie 的两个坑（已经踩过）**：
1. 别把 `cookie:` / `Cookie:` / `cookie\n` 这个**请求头标签名**一起复制进去。代码现在会
   `clean_cookie()` 自动去掉标签名、换行与多余空格；但如果复制的只有标签名，会判为缺失并 `skipped`。
2. 别在控制台敲 `document.cookie`：登录态 Cookie 多为 `HttpOnly`，JS 读不到，粘出来是残缺的。
   必须走网络面板的**完整请求头**。

---

## 二、知乎 A / B / C 三条通道

「官方 OpenAPI 需要内测」只针对 **C 通道**，不等于知乎不能自动发。三条路都已在代码里，
由 `config/settings.yaml` 的 `zhihu.mode` 选择：

| 模式 | 含义 | 凭据 | 前提 | 成功判定 |
| --- | --- | --- | --- | --- |
| **A `off`** | 整条知乎跳过，如实 `skipped` | 无 | 无 | 不发文 |
| **B `web`** | 登录态网页会话：建草稿 → 写正文 → 尝试公开 | `ZHIHU_COOKIE` | 本人登录并填 Cookie | HTTP 200 + `code==0` + 解析出 `publish.id` |
| **C `openapi`** | 官方 `POST https://openapi.zhihu.com/openapi/publish` | `ZHIHU_APP_KEY` + `ZHIHU_APP_SECRET` | 「发布者」内测资格 + `standing_consent: true` | HTTP 200 + `status==0` |
| **`auto`（默认）** | 有官方凭据且已授权走 C；否则有 `ZHIHU_COOKIE` 走 B；都没有按 A 跳过 | — | — | — |

### B 通道：不需要内测，但有两处如实说明

抓包契约来源：[bifrost-proxy/bifrost / traffic-contract.md](https://github.com/bifrost-proxy/bifrost/blob/main/.agents/skills/zhihu-publish/references/traffic-contract.md)
—— `POST /api/articles/drafts` → `PATCH /api/articles/{id}/draft` → `POST /api/v4/content/publish`。

1. **第三步「公开发布」可能需要前端动态签名 `x-zse-96`**，纯静态 Cookie 不保证成功。
   代码对此严格判定：拿不到 `publish.id` 就报 `failed`，**草稿仍在**，可到创作中心手动发。
   若不想每天看到失败，把 `zhihu.web_auto_publish` 改 `false`，则只自动建草稿 + 写正文，
   返回 `drafted` 状态（也占当天名额，不会堆草稿）。
2. **同样有风控代价**：登录态 Cookie 从 GitHub 境外机房发文属异常设备指纹。
   每天 1 篇、失败即停、随时删 Secret。

### C 通道：内测门槛不是我编的

申请入口 `https://www.zhihu.com/playground/zhihu-publisher`，页面至今为「等待逐步开放」的内测。
知乎官方仓库 `zhihu/ZhihuSync` 的 `references/auth-info.md` 明确写了 APP_SECRET 需该内测开通。
本机 `zhihu-cli` v0.7.0（公开开放平台 + Access Secret）的能力表只有搜索 / 热榜 / 本人内容 /
知识库 / 额度，**没有任何发布命令**——公开开放平台确实没有发文接口。

> 关于「重装前推送过」：本机已查不到对应的知乎发文脚本或凭据残留；9 月日志里 `zhihu-cli`
> 是纯读取，10 月真正打通自动发文的是公众号与博客。这条我标**待核实**，不冒充已确认。
> C 通道能重新申请下来就直接填两组 Secrets，代码会优先走它。

---

## 三、workflow 需要再网页覆盖一次

`gh` 令牌只有 `repo` 权限、**没有 `workflow`**，推 `.github/workflows/` 会被硬拦
（FreeScrape 项目实测：HTTPS 推送、contents API、Git Data API、部署密钥 + SSH 四条路都被挡）。

新版只比远程多一行：

```yaml
ZHIHU_COOKIE: ${{ secrets.ZHIHU_COOKIE }}
```

不注入它，B 通道拿不到登录态，永远只会 `skipped`。**必须由账号本人**打开
`https://github.com/mu16888/github-daily/edit/main/.github/workflows/daily.yml`
→ 用 `E:\workbuddy工作台\网站建设\github-daily_webcommit.html` 里的「复制 YAML 全文」
整份覆盖 → 点 **Commit changes**（选 Commit directly to the main branch）。
工具页同时提供编辑链接与备用新建链接；`github-daily_ci_link.txt` 是纯文本版。

---

## 四、首次真发复盘与安全事件

run `42616075753`，11 分钟（含错峰等待），CI 结论 `success` **只代表流水线没崩**：

| 平台 | 结果 | 根因 | 已修 |
| --- | --- | --- | --- |
| 掘金 | `failed` | `JUEJIN_COOKIE` 值以 `cookie\n` 开头 → `InvalidHeader` | `clean_cookie()` 统一清洗 |
| CSDN | `failed` | `401 HMAC signature does not match`：签名串第二行误写成 `/`，Content-Type 与请求头不一致 | 签名串第二行改为 Accept 实际值；Accept / Content-Type 由同一配置生成、逐字一致 |
| 知乎 | `skipped` | 三种凭据都没有 | 已实现 A/B/C 三通道 |

`published=0`，配额未消耗，台账 `platforms={}`，一篇都没对外发。

### 🔴 安全事件：请本人处理

`InvalidHeader` 的异常消息把**完整掘金登录态 Cookie**（1716 字符，含 `sessionid` /
`sid_guard` / `passport_csrf_token`）原样带出，写进了公开仓库的 `run-summary.json`。

- ✅ 已做：当前 `run-summary.json` 覆盖为脱敏版（提交 `4165f04`）；代码侧 `Result.__post_init__`
  对所有 `detail` / `url` 统一脱敏，`main.py` 的 FATAL 分支同样脱敏，不会再复发。
- ⚠️ **覆盖文件抹不掉 git 历史**：提交 `0671311` 里仍有明文，且公开仓库可能被 fork / clone。
  **最有效的一步是账号本人退出掘金并重新登录**，让旧 Cookie 立即失效，然后重抓一份填回
  `JUEJIN_COOKIE`。这比删文件管用。
- 若要清理历史，需要 `git filter-repo` + force push 或删库重建，属破坏性操作，
  **我不会擅自做，需你明确拍板**；且无法保证第三方已克隆的副本被清除。

---

## 五、恢复自动发文的顺序（别跳步）

1. **作废旧 Cookie**：退出掘金重新登录 → 重新抓 `Cookie:` 整串 → 更新 `JUEJIN_COOKIE` Secret。
2. **知乎三选一**：
   - A：什么都不做，`zhihu.mode: off`（或留 auto 但不填凭据），知乎如实 `skipped`；
   - B：填 `ZHIHU_COOKIE` + 按 §三 网页覆盖 workflow；
   - C：去 playground 申请内测，拿到后填 `ZHIHU_APP_KEY` / `ZHIHU_APP_SECRET`，
     并把 `zhihu.standing_consent` 改 `true`（即你的一次性长期授权）。
3. **演练**：手动 `workflow_dispatch` 勾 `dry_run=true` + `force=true`，看 `run-summary.json`：
   掘金 / CSDN 应为 `dry_run`，知乎按所选模式为 `dry_run` 或 `skipped`，`failed=0`。
   这一步不发任何文章。
4. **开真发**：把 `config/settings.yaml` 的 `publish.dry_run` 改回 `false` 并推送。
5. **手动真发一次并人工核稿**：`workflow_dispatch` 显式传 `dry_run=false` + `force=true`
   （`dry_run` 输入默认是 `true`，不显式传就又是演练），到各平台核对正文是否为 HTML、
   标题是否正常、有无重复。确认无误再交给每日自动。

> 暂停对外发文：把 `publish.dry_run` 改回 `true` 即可，无需改代码或删 Secrets。

---

## 六、轮换与风控

| 事项 | 处理 |
| --- | --- |
| 掘金 Cookie 约 30 天过期 | 定期重新复制，更新 `JUEJIN_COOKIE` |
| CSDN Cookie 过期 | `code != 200`，`run-summary.json` 报 `failed`，更新 Secret |
| 知乎 B 的 `z_c0` 失效 | 建草稿返回非 200 或无 `id`，报 `failed`，更新 `ZHIHU_COOKIE` |
| 出现异地登录验证 / 短信 | 立即把对应平台在 `config/platforms.yaml` 的 `enabled` 改 `false` |
| 每日发文额度 | 三平台取交集 = **每平台 1 篇/天**；`quota.per_day` 在代码里做硬闸门 |
| 撤销全部自动发文 | 删掉对应 Secrets，或把 `publish.dry_run` 改回 `true` |

**风险如实说明**：掘金、CSDN 与知乎 B 都靠登录 Cookie 从 GitHub 境外机房 IP 发文，
属异常设备指纹，存在触发风控的可能。这是「云端全发」的固有代价，没有技术手段能完全消除；
能做的只有低频（每天 1 篇）、严格判定不误报、失败即停、凭据随时可撤销。

最后一条：**任何 Secret 的真实值都不要发给我**，也不需要发。你在 GitHub 网页填完即可，
我这边只核验 `gh api .../actions/secrets` 的名字与更新时间、`run-summary.json` 的状态，读不到值。
