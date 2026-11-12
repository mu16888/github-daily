# hermes-webui 上手教程，先看这一点：md / txt / yaml 格式支持

> hermes-webui 怎么用，先看能查到的事实。

收藏比点赞多的那类内容，通常不是讲道理，是给了一份能带走的做法。怎么用、从哪一步开始，看仓库里能查到的东西。

## 它是什么

> Hermes WebUI: The best way to use Hermes Agent from the web or from your phone!

主要用 **Python** 写，GitHub 上攒了 **19488** 颗星（就是收藏数），用的是 MIT 协议。仓库地址：[nesquena/hermes-webui](https://github.com/nesquena/hermes-webui)。

| 能查到的 | 值 |
| --- | --- |
| 仓库 | [nesquena/hermes-webui](https://github.com/nesquena/hermes-webui) |
| 收藏数 | 19488 |
| 主要语言 | Python |
| 协议 | MIT |
| 建库 / 最近更新 | 2026-03-30 / 2026-11-12 |

## 安装与第一步

```
git clone https://github.com/nesquena/hermes-webui.git hermes-webui
cd hermes-webui
python3 bootstrap.py
```

```
git clone https://github.com/nesquena/hermes-webui
cd hermes-webui
cp .env.docker.example .env
# Edit .env if your host UID isn't 1000 (e.g. macOS where UIDs start at 501)
docker compose up -d
# Open http://localhost:8787
```

命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。

## 能带走的三条

- 不用 build 的实现
- md / txt / yaml 格式支持
- 离线可用

## 边界在哪

- MIT 协议，拿去商用或者改了再发，先看条款让不让。
- 建库 2026-03-30，最近更新 2026-11-12，项目还在改。
- 命令隔段时间可能不一样，用之前翻一眼仓库说明。

话题：#开发工具# #开源# #效率工具#
标签：agent,ai-agents,hermes,开发工具,开源

能不能用上，试过第一步就知道，不用先把说明从头读完。
