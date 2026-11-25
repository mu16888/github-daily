# ARTEX 适用边界：什么时候能用，什么时候别碰

ARTEX 在 GitHub 上给自己的简介是「Actively maintained ARTEX: AI autonomous penetration testing」，19844 Star 的开源项目。仓库标签里有 AI、Docker、大模型、MCP。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

仓库说明没专门写「为什么要做这个」，能看的只有作者自己那几句话。

说明开头是这么写的。

> **Autonomous penetration testing that keeps its receipts.**
> Self-hosted multi-agent offensive security. A planner explores, workers run real tools,
> and every finding stays bound to the assets and HTTP traffic that prove it.
> [](https://github.com/BaaRai/ARTEX/releases)
> [](LICENSE)
> [](https://github.com/BaaRai/ARTEX/actions/workflows/ci.yml)
> [](go.mod)
> [](https://discord.gg/VKyvMTcgXh)

仓库简介就一句。

> Actively maintained ARTEX: AI autonomous penetration testing system. Self-hosted, model-agnostic, evidence-backed findings. Community continuation of Autumn-27/ARTEX, AGPL-3.0.

挂的标签是 ai、ai-agents、autonomous-agents、bug-bounty、docker、golang、linux、llm，能看出它大概跟什么沾边。

## 这是个什么项目

> Actively maintained ARTEX: AI autonomous penetration testing system. Self-hosted, model-agnostic, evidence-backed findings. Community continuation of Autumn-27/ARTEX, AGPL-3.0.

主要用 **Go** 写，GitHub 上攒了 **19844** 颗星（就是收藏数），用的是 AGPL-3.0 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[BaaRai/ARTEX](https://github.com/BaaRai/ARTEX)。

## 能做什么

说明里没单列功能清单，能确认的只有仓库简介和这几项。

- 作者原话，Actively maintained ARTEX: AI autonomous penetration testing system. Self-hosted, model-agnostic, evidence-backed findings. Community continuation of Autumn-27/ARTEX, AGPL-3.0.
- 主要用 Go 写
- 标签有 ai、ai-agents、autonomous-agents、bug-bounty、docker、golang、linux、llm


## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 AGPL-3.0 协议，用起来有规矩
- 19844 颗星，不算冷门
- 有版本变动或迁移说明
- 讲了设计取舍或为什么做

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
git clone https://github.com/BaaRai/ARTEX.git
cd ARTEX
cp .env.example .env            # set POSTGRES_PASSWORD (and optionally an LLM key)
docker compose up -d --build    # builds from this checkout, starts PostgreSQL
```
```
git clone https://github.com/BaaRai/ARTEX.git
cd ARTEX
./install.sh
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

Open **http://localhost:8787**. On the first visit `/setup` asks for the one-time setup token
printed at startup:

```bash
docker compose logs artex | grep "Setup token"
```

> Multi-arch release images (`linux/amd64`, `linux/arm64`) are published to GitHub Container
> Registry at `ghcr.io/baarai/artex` from the next tagged release; v0.7.0 predates the publish
> step.

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [BaaRai/ARTEX](https://github.com/BaaRai/ARTEX) |
| 收藏数 | 19844 |
| 主要用什么写 | Go |
| 开源协议 | AGPL-3.0 |
| 标签 | ai、ai-agents、autonomous-agents、bug-bounty、docker、golang、linux、llm |
| 创建时间 | 2026-10-08 |
| 最近更新 | 2026-11-24 |
| 数据记于 | 2026-11-25T10:34:28+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- AGPL-3.0 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**ARTEX 解决什么问题？**

ARTEX 在仓库简介里写的是「Actively maintained ARTEX: AI autonomous penetration testing」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**ARTEX 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**ARTEX 免费吗？**

仓库标的是 AGPL-3.0 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**ARTEX 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

ARTEX 还在改，装之前记得翻一眼仓库说明。
