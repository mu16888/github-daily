# unslop 上手：15277 Star，附安装步骤

> unslop 能用的几条，都从说明里挑出来了。

同样的活儿换个做法，省下来的往往不是时间，是反复确认的功夫。说明里给了几条能直接用的。

## 它是什么

> A Claude skill that turns vibecoded, AI-looking UI into a designed interface

主要用 **JavaScript** 写，GitHub 上攒了 **15277** 颗星（就是收藏数），用的是 CC-BY-4.0 协议。仓库地址：[heydamir/unslop](https://github.com/heydamir/unslop)。

## 先记这几点

- MCP server 接口
- 15277 Star

## 先跑这条

```
npm install -D playwright
npx playwright install chromium
```

```
git clone https://github.com/heydamir/unslop
mkdir -p ~/.claude/skills && cp -r unslop/skills/unslop ~/.claude/skills/
```

命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。

话题：#开源项目# #开发工具# #上手#
标签：开源项目,开发工具,上手

合不合用，拿一条真实命令试一下比看十行介绍快。
