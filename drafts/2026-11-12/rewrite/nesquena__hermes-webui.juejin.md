# hermes-webui 上手：离线可用，附安装步骤

> hermes-webui 能用的几条，都从说明里挑出来了。

一个工具值不值得装，先看它能不能给你留下点能直接用的东西。说明里给了几条能直接用的。

## 它是什么

> Hermes WebUI: The best way to use Hermes Agent from the web or from your phone!

主要用 **Python** 写，GitHub 上攒了 **19488** 颗星（就是收藏数），用的是 MIT 协议。仓库地址：[nesquena/hermes-webui](https://github.com/nesquena/hermes-webui)。

## 能带走的三条

- 不用 build 的实现
- md / txt / yaml 格式支持
- 离线可用

## 先跑这条

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

话题：#开发工具# #开源# #效率工具#
标签：agent,ai-agents,hermes,开发工具,开源

工具还在改，真要长期用，记得回头看一眼仓库。
