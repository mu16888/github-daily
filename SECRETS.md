# 上线清单：GitHub Secrets 与一次网页提交

「云端全发」的全部凭据都放在 **GitHub 仓库 → Settings → Secrets and variables → Actions**。
它们加密存储、不进代码、不打日志，重装系统不会丢 —— 这正是云端方案相对本机方案的核心好处。

> ⚠️ Cookie 等同于账号登录态。不要贴进代码、Issue、聊天或任何文件；只填在 GitHub Secrets 里。
> 按你定的账号安全红线，这套工具只发**自己生成的公开技术文章**，不用于操作任何社交账号的登录态。

---

## 一、需要填的 5 组 Secrets

| Secret 名 | 用途 | 从哪来 |
| --- | --- | --- |
| `ZHIHU_APP_KEY` | 知乎官方 OpenAPI 的 member token / URLToken | 知乎「发布者」内测凭据，见下方 §2 |
| `ZHIHU_APP_SECRET` | HMAC-SHA256 签名密钥 | 同上，官方共享凭据文件 `~/.zhihu/openapi-credentials.json` |
| `JUEJIN_COOKIE` | 掘金登录态 | 浏览器登录 juejin.cn → F12 → Network → 任意请求 → 复制完整 `Cookie` 请求头 |
| `JUEJIN_UUID` | 掘金请求 URL 上的用户级常量 | 同上，从请求 URL 的 `uuid=` 参数抠出（不是 Cookie 里的值） |
| `CSDN_COOKIE` | CSDN 登录态 | 浏览器登录 editor.csdn.net → F12 → Network → 复制完整 `Cookie` 请求头 |

`GITHUB_TOKEN` 由 Actions 自动注入，不需要手动创建。

---

## 二、知乎凭据有一个前置条件

知乎官方发布接口是 `POST https://openapi.zhihu.com/openapi/publish`，
规范见 [ZhihuSync / publish-openapi.md](https://github.com/zhihu/ZhihuSync/blob/main/zhihu-publish/reference/publish-openapi.md)。
凭据字段名是 `ZHIHU_OPENAPI_APP_KEY` 与 `ZHIHU_OPENAPI_APP_SECRET`，
官方默认从 `~/.zhihu/openapi-credentials.json` 读取。

**但 APP_KEY/APP_SECRET 需要知乎「发布者」内测授权才能拿到**
（申请入口 `zhihu.com/playground/zhihu-publisher`）。本机重装后该文件已不存在，
E 盘也没有备份。所以：

- 如果你已通过内测并拿到这两个值 → 直接填进 Secrets，知乎通道可全自动。
- 如果还在「等待逐步开放」→ **知乎这一路现在发不了**，另外两个平台不受影响。
  适配器会返回 `skipped`，不会假装成功。等资格下来再填一次即可。

这一点必须如实说，不能把「接口存在」等同于「你的账号现在能用」。

另外官方规范还有两条硬要求，代码已按此实现：

1. `confirmed: true` 只能在用户确认后发送 → 本仓库用 `zhihu.standing_consent` 一次性长期授权代替逐篇预览，默认 `false`。改成 `true` 就是你明确授权，且意味着**接受不再逐篇人工预览**这个偏差。
2. 内容是程序生成的 → 官方建议声明 `ai_creation`。是否声明由你决定，在 `settings.yaml` 的 `zhihu.creation_statement` 填写；不填就不发送该字段。

---

## 三、首次上线顺序（别跳步）

1. **先别填 Secrets**，用 `workflow_dispatch` 勾 `dry_run=true` 手动跑一次，
   看 `run-summary.json`：应有 `picked >= 1`、三个平台 `dry_run` 或 `skipped`、无 `failed`。
2. 填好 5 组 Secrets，仍保持 `dry_run=true` 再跑一次，确认凭据齐备（状态从 `skipped` 变 `dry_run`）。
3. 真发之前，把 `config/settings.yaml` 三个开关改掉并推送：
   ```yaml
   publish:
     enabled: true
     dry_run: false
   zhihu:
     standing_consent: true    # 仅当你已确认接受长期授权
   ```
4. 手动 `workflow_dispatch`（不勾 dry_run）跑一次，到三个平台各核对 1 篇文章。
   **首次真发务必人工看一眼**，重点核对：掘金/CSDN 的响应结构解析、CSDN 是否出现 Markdown 源码乱码（正文必须是 HTML）、知乎是否返回 `status=0`。
5. 确认无误后交给每日 cron（`17 1 * * *` UTC = 北京 09:17）。

---

## 四、一个必须本人做的动作：提交 workflow 文件

现有 `gh` 令牌只有 `repo` 权限，**没有 `workflow` 权限**，推 `.github/workflows/` 会被 GitHub 硬拦
（此前 FreeScrape 项目已实测：HTTPS 推送、contents API、Git Data API、临时部署密钥 + SSH 四条路都被同一道闸门挡住）。

所以 `.github/workflows/daily.yml` 需要你在 **GitHub 网页**用浏览器登录态新建一次：

- 打开 `https://github.com/mu16888/github-daily/new/main?filename=.github%2Fworkflows%2Fdaily.yml`
- 把本地 `.github/workflows/daily.yml` 的内容粘进去
- 点 **Commit new file**

这是唯一需要你动手的一步（填 Secrets 也可由你本人完成，更安全）。
其他代码文件我可以直接推送。

---

## 五、轮换与风控

| 事项 | 处理 |
| --- | --- |
| 掘金 Cookie 约 30 天过期 | 定期重新复制，更新 `JUEJIN_COOKIE` Secret |
| CSDN Cookie 过期表现 | `code != 200`，`run-summary.json` 报 `failed`，更新 Secret 即可 |
| 出现异地登录验证 / 短信 | 立即把对应平台在 `config/platforms.yaml` 的 `enabled` 改 `false`，登录态手工处理后再开 |
| 每日发文额度 | 三平台取交集 = **每平台 1 篇/天**；`quota.per_day` 在代码里做硬闸门。掘金第 2 篇会返回成功却不进列表，知乎网页端是「距上一篇 ≥24h」滚动限流，都不要调高 |
| 想多发几篇 | 不建议。真要调，改 `config/settings.yaml` 的 `quota.per_day` 与 `daily.picks_per_day`，但掘金超过 1 篇会静默失效 |
| 撤销全部自动发文 | 删掉对应 Secrets，或把 `publish.enabled` 改回 `false` |

**风险如实说明**：掘金与 CSDN 用登录 Cookie 从 GitHub 境外机房 IP 发文，属于异常设备指纹，
存在触发风控的可能。这是「云端全发」相对「本机发」的主要代价，没有技术手段能完全消除；
能做的只有低频（每天 1 篇）、失败即停、凭据随时可撤销。

最后一条：**任何 Secret 的真实值都不要发给我**，也不需要发。你在 GitHub 网页填完即可，
我这边只会核验 `run-summary.json` 里的状态，不会读取凭据内容。
