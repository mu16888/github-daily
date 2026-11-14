# nxnative 解决什么问题？功能、安装与上手

nxnative 在 GitHub 上给自己的简介是「Switch games running natively on iPhone, iPad and Mac: an NS」，15367 Star 的开源项目。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

仓库说明没专门写「为什么要做这个」，能看的只有作者自己那几句话。

说明开头是这么写的。

> Play your own Nintendo Switch and Switch 2 games natively on Apple silicon Macs, iPhone and iPad. One script packs your game into a Mac app or an unsigned IPA that you sideload.
> It is not an emulator: the game's own code runs directly on the Apple chip, with Switch graphics rebuilt on Metal. Nothing from any game is in this repository, and the project is not affiliated with Nintendo or any game publisher.
> [Games](#games) · [Community front ends](#community-front-ends) · [Requirements](#requirements) · [How to play](#how-to-play) · [Discussions](#discussions) · [For developers](#for-developers)

仓库简介就一句。

> Switch games running natively on iPhone, iPad and Mac: an NSP folder becomes an unsigned IPA (NSO rewriter, Horizon HLE host, NVN→Metal)

挂的标签是 没标，能看出它大概跟什么沾边。

## 这是个什么项目

> Switch games running natively on iPhone, iPad and Mac: an NSP folder becomes an unsigned IPA (NSO rewriter, Horizon HLE host, NVN→Metal)

主要用 **Python** 写，GitHub 上攒了 **15367** 颗星（就是收藏数），用的是 MIT 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[seedds/nxnative](https://github.com/seedds/nxnative)。

## 能做什么

说明里没单列功能清单，能确认的只有仓库简介和这几项。

- 作者原话，Switch games running natively on iPhone, iPad and Mac: an NSP folder becomes an unsigned IPA (NSO rewriter, Horizon HLE host, NVN→Metal)
- 主要用 Python 写
- 标签有 没标


## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 MIT 协议，用起来有规矩
- 不用自己把源码做成软件
- 不用另外配数据库、账号或者付费服务
- 15367 颗星，不算冷门

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
xcodebuild -downloadComponent MetalToolchain
git clone https://github.com/seedds/nxnative.git && cd nxnative
brew install xcodegen zstd glslang
python3 -m pip install lz4 "capstone>=5,<6" fonttools nsz zbic "backports.zstd; python_version < '3.14'"
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

Install the IPA on your iPhone or iPad with a sideloading tool such as AltStore, Sideloadly or LiveContainer. If your tool offers **Increased Memory Limit**, turn it on: the bigger games need it.

Game too big to install? Build again with `--romfs separate`, and run the command the script prints once to copy the game files to your phone ([Quick reinstalls](docs/development.md#quick-reinstalls)). With AltServer, also add `--shader-files`: it cannot install a file of 2 GiB or more.

Controls, saves and settings: [Playing](docs/playing.md).

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [seedds/nxnative](https://github.com/seedds/nxnative) |
| 收藏数 | 15367 |
| 主要用什么写 | Python |
| 开源协议 | MIT |
| 标签 | 没标 |
| 创建时间 | 2026-10-13 |
| 最近更新 | 2026-11-14 |
| 数据记于 | 2026-11-14T08:10:08+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- MIT 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**nxnative 解决什么问题？**

nxnative 在仓库简介里写的是「Switch games running natively on iPhone, iPad and Mac: an NS」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**nxnative 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**nxnative 免费吗？**

仓库标的是 MIT 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**nxnative 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

nxnative 还在改，装之前记得翻一眼仓库说明。
