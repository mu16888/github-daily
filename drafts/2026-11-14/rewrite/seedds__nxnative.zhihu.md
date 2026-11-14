# 15367 Star，nxnative 说明里写了这些

> nxnative 值不值得花时间，先看它管什么。

改一遍和每次都改，是两回事。值不值得花时间，先看它到底管什么。

## 它是什么

> Switch games running natively on iPhone, iPad and Mac: an NSP folder becomes an unsigned IPA (NSO rewriter, Horizon HLE host, NVN→Metal)

主要用 **Python** 写，GitHub 上攒了 **15367** 颗星（就是收藏数），用的是 MIT 协议。仓库地址：[seedds/nxnative](https://github.com/seedds/nxnative)。

| 能查到的 | 值 |
| --- | --- |
| 仓库 | [seedds/nxnative](https://github.com/seedds/nxnative) |
| 收藏数 | 15367 |
| 主要语言 | Python |
| 协议 | MIT |
| 建库 / 最近更新 | 2026-10-13 / 2026-11-14 |

## 前后差在哪

- 15367 Star

## 先做哪一步

```
xcodebuild -downloadComponent MetalToolchain
git clone https://github.com/seedds/nxnative.git && cd nxnative
brew install xcodegen zstd glslang
python3 -m pip install lz4 "capstone>=5,<6" fonttools nsz zbic "backports.zstd; python_version < '3.14'"
```

命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。

## 边界在哪

- MIT 协议，拿去商用或者改了再发，先看条款让不让。
- 建库 2026-10-13，最近更新 2026-11-14，项目还在改。
- 命令隔段时间可能不一样，用之前翻一眼仓库说明。

话题：#开发工具# #编码规范# #开源#
标签：开发工具,编码规范,开源

先做最小那一步，比一次写全更省事。
