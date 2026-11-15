# xerj 与同类做法的差别，不在「离线可用」在边界

> xerj 怎么用，先看能查到的事实。

收藏比点赞多的那类内容，通常不是讲道理，是给了一份能带走的做法。怎么用、从哪一步开始，看仓库里能查到的东西。

## 它是什么

> AI search engine and MCP server for bots and agents. One Rust binary indexes code, docs, logs, JSONL/CSV and PDFs for BM25 full-text, vector and hybrid search, code search without grep, agent memory and RAG. Elasticsearch-compatible API; Corpus Hub serves hundreds of reference memory corpora.

主要用 **Rust** 写，GitHub 上攒了 **19092** 颗星（就是收藏数），用的是 Apache-2.0 协议。仓库地址：[xerj-org/xerj](https://github.com/xerj-org/xerj)。

| 能查到的 | 值 |
| --- | --- |
| 仓库 | [xerj-org/xerj](https://github.com/xerj-org/xerj) |
| 收藏数 | 19092 |
| 主要语言 | Rust |
| 协议 | Apache-2.0 |
| 建库 / 最近更新 | 2026-06-30 / 2026-11-15 |

## 安装与第一步

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

命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。

## 能带走的三条

- 不用 match 的实现
- html / txt / md 格式支持
- 离线可用

## 边界在哪

- Apache-2.0 协议，拿去商用或者改了再发，先看条款让不让。
- 建库 2026-06-30，最近更新 2026-11-15，项目还在改。
- 命令隔段时间可能不一样，用之前翻一眼仓库说明。

话题：#开发工具# #开源# #效率工具#
标签：agent-memory,ai-agents,bm25,命令行工具,开发工具

工具还在改，真要长期用，记得回头看一眼仓库。
