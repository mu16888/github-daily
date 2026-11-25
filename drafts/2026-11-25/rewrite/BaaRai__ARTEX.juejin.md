# 把 ARTEX 换掉的成本，比装它的成本高多少

> ARTEX 能用的几条，都从说明里挑出来了。

同样的活儿换个做法，省下来的往往不是时间，是反复确认的功夫。说明里给了几条能直接用的。

## 它是什么

> Actively maintained ARTEX: AI autonomous penetration testing system. Self-hosted, model-agnostic, evidence-backed findings. Community continuation of Autumn-27/ARTEX, AGPL-3.0.

主要用 **Go** 写，GitHub 上攒了 **19844** 颗星（就是收藏数），用的是 AGPL-3.0 协议。仓库地址：[BaaRai/ARTEX](https://github.com/BaaRai/ARTEX)。

## 先记这几点

- 不用 manual 的实现
- 19844 Star

## 先跑这条

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

话题：#开源项目# #开发工具# #上手#
标签：ai,ai-agents,autonomous-agents,AI,Docker

合不合用，拿一条真实命令试一下比看十行介绍快。
