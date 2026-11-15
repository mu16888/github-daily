# 「html / txt / md 格式支持」不是免费午餐：xerj 的依赖项先看

> xerj 能用的几条，都从说明里挑出来了。

一个工具值不值得装，先看它能不能给你留下点能直接用的东西。说明里给了几条能直接用的。

## 它是什么

> AI search engine and MCP server for bots and agents. One Rust binary indexes code, docs, logs, JSONL/CSV and PDFs for BM25 full-text, vector and hybrid search, code search without grep, agent memory and RAG. Elasticsearch-compatible API; Corpus Hub serves hundreds of reference memory corpora.

主要用 **Rust** 写，GitHub 上攒了 **19092** 颗星（就是收藏数），用的是 Apache-2.0 协议。仓库地址：[xerj-org/xerj](https://github.com/xerj-org/xerj)。

## 能带走的三条

- 不用 match 的实现
- html / txt / md 格式支持
- 离线可用

## 先跑这条

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

话题：#开发工具# #开源# #效率工具#
标签：agent-memory,ai-agents,bm25,命令行工具,开发工具

能不能用上，试过第一步就知道，不用先把说明从头读完。
