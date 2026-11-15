# xerj 适用边界：什么时候能用，什么时候别碰

xerj 在 GitHub 上给自己的简介是「AI search engine and MCP server for bots and agents. One Rus」，19092 Star 的开源项目。仓库标签里有 命令行工具、MCP、Rust。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

作者在仓库说明里写了做这个东西的缘由。

Agents burn their context window reading files. The PHP in WordPress core is about 5.2
million tokens, or 26 full context windows, so an agent cannot simply read it. Grep does not
solve this either, because a grep hit is a line, and judging that line means opening the
whole file.

Querying an index with passages and a projected _source costs kilobytes per question (a default _search returns whole documents) instead. In
[an AI security audit of WordPress core](https://xerj.org/use-cases/code-security-audit.html),
an agent worked across 1,492 PHP files on roughly 26,000 tokens, which is what it takes to
load about half a percent of the tree.

## 这是个什么项目

> AI search engine and MCP server for bots and agents. One Rust binary indexes code, docs, logs, JSONL/CSV and PDFs for BM25 full-text, vector and hybrid search, code search without grep, agent memory and RAG. Elasticsearch-compatible API; Corpus Hub serves hundreds of reference memory corpora.

主要用 **Rust** 写，GitHub 上攒了 **19092** 颗星（就是收藏数），用的是 Apache-2.0 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[xerj-org/xerj](https://github.com/xerj-org/xerj)。

## 能做什么

说明里没单列功能清单，能确认的只有仓库简介和这几项。

- 作者原话，AI search engine and MCP server for bots and agents. One Rust binary indexes code, docs, logs, JSONL/CSV and PDFs for BM25 full-text, vector and hybrid search, code search without grep, agent memory and RAG. Elasticsearch-compatible API; Corpus Hub serves hundreds of reference memory corpora.
- 主要用 Rust 写
- 标签有 agent-memory、ai-agents、bm25、claude-code、cli、code-search、cursor、database


## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 Apache-2.0 协议，用起来有规矩
- 19092 颗星，不算冷门
- 写明了限制或不适用场景
- 有对比或基准测试
- 有版本变动或迁移说明
- 讲了设计取舍或为什么做

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
curl -fsSL https://xerj.org/get | sh -s -- --with-model
```
```
curl -fsSL https://xerj.org/get | sh
xerj --insecure --data-dir ~/xerj-data &
xerj init                                        # wire XERJ into Claude Code/Cursor (MCP + skill), one command
xerj autoindex ~/my-project
xerj search "how do we rotate the WAL segment"   # ranked passages, file:line
xerj def "euler_to_rotationmatrix"               # go-to-definition: file:line + signature
xerj gain                                        # what it did for you — counted, not estimated
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

```sh
curl -fsSL https://xerj.org/get | sh
```

Windows PowerShell:

```powershell
irm https://xerj.org/get.ps1 | iex
```

Nix (builds from source; `nix develop` opens a shell with the Rust toolchain):

```sh
nix run github:xerj-org/xerj -- --version
```

One static binary, no JVM, no dependencies. Prebuilt for Linux, macOS and Windows on x86-64
and arm64. The x86-64 builds target x86-64-v2 (SSE4.2: Intel Nehalem 2008 and later, AMD
Bulldozer and later) and use AVX2 and FMA at runtime when the CPU has them, so a pre-Haswell
machine runs the same binary. It speaks the Elasticsearch API, so existing
clients, dashboards and tooling work against it unchanged.

First commands after install (the installer prints where `xerj` landed; add it to your PATH
if needed): `xerj --insecure --data-dir ~/xerj-data &`, wait until `http://localhost:9200`
responds, then `xerj autoindex ~/my-project`. See [Index a folder](#index-a-folder).

For a host with no runtime internet access, follow the
[air-gapped deployment recipe](./docs/recipes/air-gapped-deployment.md). The default lexical
embedder is offline; neural mode needs the three model files staged locally before the first
semantic operation.

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [xerj-org/xerj](https://github.com/xerj-org/xerj) |
| 收藏数 | 19092 |
| 主要用什么写 | Rust |
| 开源协议 | Apache-2.0 |
| 标签 | agent-memory、ai-agents、bm25、claude-code、cli、code-search、cursor、database |
| 创建时间 | 2026-06-30 |
| 最近更新 | 2026-11-15 |
| 数据记于 | 2026-11-15T07:12:11+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- Apache-2.0 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**xerj 解决什么问题？**

xerj 在仓库简介里写的是「AI search engine and MCP server for bots and agents. One Rus」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**xerj 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**xerj 免费吗？**

仓库标的是 Apache-2.0 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**xerj 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

xerj 还在改，装之前记得翻一眼仓库说明。
