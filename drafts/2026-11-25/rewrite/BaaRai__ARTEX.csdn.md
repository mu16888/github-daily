# ARTEX 的 Go 实现，决定了哪些场景用不上

> ARTEX 怎么用，先看能查到的事实。

很多工具不是不好用，是一开始就被用错了地方。怎么用、从哪一步开始，看仓库里能查到的东西。

## 它是什么

> Actively maintained ARTEX: AI autonomous penetration testing system. Self-hosted, model-agnostic, evidence-backed findings. Community continuation of Autumn-27/ARTEX, AGPL-3.0.

主要用 **Go** 写，GitHub 上攒了 **19844** 颗星（就是收藏数），用的是 AGPL-3.0 协议。仓库地址：[BaaRai/ARTEX](https://github.com/BaaRai/ARTEX)。

| 能查到的 | 值 |
| --- | --- |
| 仓库 | [BaaRai/ARTEX](https://github.com/BaaRai/ARTEX) |
| 收藏数 | 19844 |
| 主要语言 | Go |
| 协议 | AGPL-3.0 |
| 建库 / 最近更新 | 2026-10-08 / 2026-11-24 |

## 安装与第一步

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

命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。

## 先记这几点

- 不用 manual 的实现
- 19844 Star

## 边界在哪

- AGPL-3.0 协议，拿去商用或者改了再发，先看条款让不让。
- 建库 2026-10-08，最近更新 2026-11-24，项目还在改。
- 命令隔段时间可能不一样，用之前翻一眼仓库说明。

话题：#开源项目# #开发工具# #上手#
标签：ai,ai-agents,autonomous-agents,AI,Docker

项目还在更新，命令和版本以仓库说明为准。
