# dsh-Go 解决什么问题？功能、安装与上手

dsh-Go 在 GitHub 上给自己的简介是「dsh-go — DeepSeek Harness 装进口袋：手机本机运行，也能遥控你的电脑」，18445 Star 的开源项目。仓库标签里有 大模型。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

仓库说明没专门写「为什么要做这个」，能看的只有作者自己那几句话。

说明开头是这么写的。

> DSH Go 提供聊天界面、本机运行环境和远程连接，是基于 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的第三方项目。运行在手机上的是 DSH 引擎；模型请求仍由你配置的模型提供方处理。
> - **本机运行**：在 App 内安装 Ubuntu、Node.js 与 DSH 运行环境，无需 Root 或另装 Termux。
> - **远程连接**：通过 SSH 或李国宝老师开发的 [DSHarness Remote](https://github.com/liguobao/ds-harness-remote) 使用电脑、服务器上的 DSH。
> - **聊天与工具**：切换模型，发送图片、使用语音输入，处理工具审批和提问；支持聊天界面与网页模式。
> - **插件界面**：使用适配 DSH Go 的原生工具卡、表单和面板；仓库提供 SDK、教程和示例。
> - **手机操控**：在你开启权限后，让本机引擎读取屏幕、点按和输入，并可随时停止。
> - **分享与外观**：分享、导出和回放对话，调整主题、图标和桌宠。
> 功能随主机和连接方式不同。DSHarness Remote 当前只支持图片附件，不能在 App 内打开网页版，插件管理限于开关，且不支持 DS Bot 和对话日志导出。详见[本机引擎与远程主机](docs/guide/zh/03-engine-hosts.md)。

仓库简介就一句。

> dsh-go — DeepSeek Harness 装进口袋：手机本机运行，也能遥控你的电脑。

挂的标签是 ai-agent、android、android-app、coding-agent、deepseek、deepseek-harness、dsh、dsh-plugin，能看出它大概跟什么沾边。

## 这是个什么项目

> dsh-go — DeepSeek Harness 装进口袋：手机本机运行，也能遥控你的电脑。

主要用 **Dart** 写，GitHub 上攒了 **18445** 颗星（就是收藏数），用的是 AGPL-3.0 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[ccch1mneyyy/dsh-Go](https://github.com/ccch1mneyyy/dsh-Go)。

## 能做什么

说明里没单列功能清单，能确认的只有仓库简介和这几项。

- 作者原话，dsh-go — DeepSeek Harness 装进口袋：手机本机运行，也能遥控你的电脑。
- 主要用 Dart 写
- 标签有 ai-agent、android、android-app、coding-agent、deepseek、deepseek-harness、dsh、dsh-plugin


## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 AGPL-3.0 协议，用起来有规矩
- 不用自己把源码做成软件
- 不用另外配数据库、账号或者付费服务
- 18445 颗星，不算冷门

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
git clone https://github.com/ccch1mneyyy/dsh-go.git
cd dsh-go

bash tooling/setup-toolchain.sh
source tooling/env.sh
flutter --version
java -version

bash runtime/build-runtime.sh arm64-v8a
DSH_BETA_TOKEN_FILE= bash tooling/build-apk.sh -f arm64 --keep-daemon
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

安装要求为 Android 8.0（API 26）及以上。Release 页面上的 **arm64** 安装包适用于常见的 64 位 Android 手机；x86_64 设备和模拟器用的 x64 包在发布说明末尾的「其他版本下载」里。仓库没有 32 位 ARM 构建。

1. 从 [GitHub Releases](https://github.com/ccch1mneyyy/dsh-go/releases/latest) 或[官网下载页](https://go.dshtui.com/download)下载对应架构的 APK，并按系统提示允许该安装来源。
2. 首次启动时，选择在本机安装运行环境，或连接远程主机。
3. 为所选主机配置模型和所需凭据，再开始对话；部分远程渠道需要在主机侧配置。

仅连接远程主机时，不必在手机上安装本机运行环境。手机操控只对正常模式下的本机引擎开放，需要按界面说明开启无障碍等权限；不打扰模式另外要求 Android 14 及以上，以及 Shizuku 或自连 ADB。首次使用可按[使用指南](docs/guide/README.md)逐项配置。

本地引擎默认使用 PRoot 兼容启动。开发者选项中的直接启动默认关闭，开启后的兼容性和回退方式见[常见问题](docs/guide/zh/11-faq.md)。当前 Android 构建以 APK 侧载为目标，不是 Google Play 发布配置。

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [ccch1mneyyy/dsh-Go](https://github.com/ccch1mneyyy/dsh-Go) |
| 收藏数 | 18445 |
| 主要用什么写 | Dart |
| 开源协议 | AGPL-3.0 |
| 标签 | ai-agent、android、android-app、coding-agent、deepseek、deepseek-harness、dsh、dsh-plugin |
| 创建时间 | 2026-10-25 |
| 最近更新 | 2026-11-10 |
| 数据记于 | 2026-11-10T14:45:31+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- AGPL-3.0 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**dsh-Go 解决什么问题？**

dsh-Go 在仓库简介里写的是「dsh-go — DeepSeek Harness 装进口袋：手机本机运行，也能遥控你的电脑」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**dsh-Go 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**dsh-Go 免费吗？**

仓库标的是 AGPL-3.0 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**dsh-Go 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

dsh-Go 还在改，装之前记得翻一眼仓库说明。
