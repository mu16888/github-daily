# wordcraft 解决什么问题？功能、安装与上手

wordcraft 在 GitHub 上给自己的简介是「WordCraft: an open-source, clean-room word processor in pure」，17741 Star 的开源项目。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

作者在仓库说明里写了做这个东西的缘由。

- **Familiar.** Ribbon tabs, groups, shortcuts and behaviour: Enter continues a list,
  Tab demotes it, Ctrl/⌘+B bolds the word under the caret, the Styles gallery previews styles live,
  F4 repeats, F7 checks spelling, F8 extends the selection.
- **Your files.** Opens and saves .docx (OOXML), and also .odt, .rtf, .html, .md, .tex (LaTeX), .txt; opens legacy 97-2003 .doc; exports PDF
  with real, selectable text, links and bookmarks.
- **Fast.** Paragraph layout is cached, so typing in a 188-page document re-lays it out in about
  1.4 ms; pages render on demand.
- **Everywhere.** One Rust codebase for macOS, Windows, Linux, BSD and the web. No Electron, no
  Tauri: native [egui](https://github.com/emilk/egui) on the GPU.
- **Built for agents.** Every action is a command with an id. The same 422 commands drive the
  ribbon, keyboard shortcuts, the command search, a command-line tool, a JSON control channel and
  an MCP server.
- **Private.** Spelling, grammar and everything else work offline.
- **Open.** MIT OR Apache-2.0. Clean-room: built from public specifications and observation, with
  every asset original or openly licensed.

## 这是个什么项目

> WordCraft: an open-source, clean-room word processor in pure Rust

主要用 **Rust** 写，GitHub 上攒了 **17741** 颗星（就是收藏数），用的是 Apache-2.0 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[storytold/wordcraft](https://github.com/storytold/wordcraft)。

## 能做什么

说明里没单列功能清单，能确认的只有仓库简介和这几项。

- 作者原话，WordCraft: an open-source, clean-room word processor in pure Rust
- 主要用 Rust 写
- 标签有 没标


## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 Apache-2.0 协议，用起来有规矩
- 不用自己把源码做成软件
- 不用另外配数据库、账号或者付费服务
- 17741 颗星，不算冷门

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
git clone https://github.com/storytold/wordcraft
cd wordcraft
cargo run --release -p wordcraft -- --sample        # the desktop app with the sample document
cargo run --release -p wordcraft -- report.docx     # open a document
```
```
git clone https://github.com/storytold/craft-i18n ../craft-i18n
git -C ../craft-i18n checkout "$(cat craft-i18n.rev)"
CRAFT_I18N_DIR="$PWD/../craft-i18n" cargo run --release -p wordcraft -- --sample
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

The interface translations and the spelling and hyphenation data come from
[craft-i18n](https://github.com/storytold/craft-i18n), an optional build input. To build with them,
check it out at the commit in `craft-i18n.rev` and point `CRAFT_I18N_DIR` at it (an absolute
path); without it WordCraft builds with an English interface, English spelling falls back to an
installed Hunspell English or craft-proof's built-in word list, and only Bulgarian, Turkish and
Russian hyphenate (by rule):



Command line:

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [storytold/wordcraft](https://github.com/storytold/wordcraft) |
| 收藏数 | 17741 |
| 主要用什么写 | Rust |
| 开源协议 | Apache-2.0 |
| 标签 | 没标 |
| 创建时间 | 2026-10-07 |
| 最近更新 | 2026-11-10 |
| 数据记于 | 2026-11-10T15:08:11+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- Apache-2.0 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**wordcraft 解决什么问题？**

wordcraft 在仓库简介里写的是「WordCraft: an open-source, clean-room word processor in pure」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**wordcraft 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**wordcraft 免费吗？**

仓库标的是 Apache-2.0 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**wordcraft 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

wordcraft 还在改，装之前记得翻一眼仓库说明。
