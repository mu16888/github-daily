# unslop 解决什么问题？功能、安装与上手

unslop 在 GitHub 上给自己的简介是「A Claude skill that turns vibecoded, AI-looking UI into a de」，15277 Star 的开源项目。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

仓库说明没专门写「为什么要做这个」，能看的只有作者自己那几句话。

说明开头是这么写的。

> Created by Damir Sokolovsky ([@heydamir](https://x.com/heydamir)), who started the [Unslopping series](https://x.com/heydamir/status/2115063463063998736) on X.
> unslop is a skill for Claude Code, Codex and Google Antigravity that turns vibecoded, AI-looking UI into a designed interface with its own character. It finds the slop first, the purple gradients, glows, emoji labels, shouty copy and uneven spacing, then sets a direction from your product and fixes the screen pass by pass like a designer doing a redline review. It works in whatever your screen is built with, like Next.js, React, Vue, Svelte, Tailwind or plain HTML and CSS, on dashboards, apps and landing pages, and even on a live site when all you have is a link.

仓库简介就一句。

> A Claude skill that turns vibecoded, AI-looking UI into a designed interface

挂的标签是 没标，能看出它大概跟什么沾边。

## 这是个什么项目

> A Claude skill that turns vibecoded, AI-looking UI into a designed interface

主要用 **JavaScript** 写，GitHub 上攒了 **15277** 颗星（就是收藏数），用的是 CC-BY-4.0 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[heydamir/unslop](https://github.com/heydamir/unslop)。

## 能做什么

作者在说明里列了这些。

- **Audit.** Lists every sign of slop with where it lives.
- **Direction.** Character, world, the one or two moments that carry the color, and a signature detail, all taken from your product.
- **Passes.** Spacing, color, icons, copy, type, layout, details, visuals and motion, in that order.
- **Visuals.** Shows your product instead of a glossy blob. When a hero needs a scene or an object, it can generate one through an image service like fal, Replicate, OpenAI images or Higgsfield. If none is connected, it offers to connect one as an MCP server, and it shows the prompt and asks before every paid generation. Dashboards and apps rarely need one.
- **Story video.** A square video under 10 seconds of your screen unslopping itself, ready to post. It needs Playwright and ffmpeg.

Try it on the two vibecoded screens in [examples](examples).

## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 CC-BY-4.0 协议，用起来有规矩
- 不用自己把源码做成软件
- 不用另外配数据库、账号或者付费服务
- 15277 颗星，不算冷门

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
npm install -D playwright
npx playwright install chromium
```
```
git clone https://github.com/heydamir/unslop
mkdir -p ~/.claude/skills && cp -r unslop/skills/unslop ~/.claude/skills/
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

For Claude Code, copy the skill into your skills folder.



For a single project, copy it into `.claude/skills/` inside that project instead.

For Codex, ask it to install the skill straight from this repo.

```
$skill-installer install https://github.com/heydamir/unslop/tree/main/skills/unslop
```

Or copy it by hand into `~/.agents/skills/`, or into `.agents/skills/` inside a single project.

```bash
git clone https://github.com/heydamir/unslop
mkdir -p ~/.agents/skills && cp -r unslop/skills/unslop ~/.agents/skills/
```

For Google Antigravity, copy the skill into your skills folder.

```bash
git clone https://github.com/heydamir/unslop
mkdir -p ~/.gemini/antigravity/skills && cp -r unslop/skills/unslop ~/.gemini/antigravity/skills/
```

For a single project, copy it into `.agents/skills/` inside that project instead.

To snapshot a live site or create a story video, install Playwright and its Chromium browser from the project directory where you run the skill:

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [heydamir/unslop](https://github.com/heydamir/unslop) |
| 收藏数 | 15277 |
| 主要用什么写 | JavaScript |
| 开源协议 | CC-BY-4.0 |
| 标签 | 没标 |
| 创建时间 | 2026-10-29 |
| 最近更新 | 2026-11-08 |
| 数据记于 | 2026-11-13T07:08:24+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- CC-BY-4.0 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**unslop 解决什么问题？**

unslop 在仓库简介里写的是「A Claude skill that turns vibecoded, AI-looking UI into a de」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**unslop 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**unslop 免费吗？**

仓库标的是 CC-BY-4.0 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**unslop 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

unslop 还在改，装之前记得翻一眼仓库说明。
