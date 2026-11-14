# nxnative 使用笔记：15367 Star，附现成安装步骤

> nxnative 能用的几条，都从说明里挑出来了。

改一遍和每次都改，是两回事。说明里给了几条能直接用的。

## 它是什么

> Switch games running natively on iPhone, iPad and Mac: an NSP folder becomes an unsigned IPA (NSO rewriter, Horizon HLE host, NVN→Metal)

主要用 **Python** 写，GitHub 上攒了 **15367** 颗星（就是收藏数），用的是 MIT 协议。仓库地址：[seedds/nxnative](https://github.com/seedds/nxnative)。

## 前后差在哪

- 15367 Star

## 先跑这条

```
xcodebuild -downloadComponent MetalToolchain
git clone https://github.com/seedds/nxnative.git && cd nxnative
brew install xcodegen zstd glslang
python3 -m pip install lz4 "capstone>=5,<6" fonttools nsz zbic "backports.zstd; python_version < '3.14'"
```

命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。

话题：#开发工具# #编码规范# #开源#
标签：开发工具,编码规范,开源

说明会改，动手前去仓库页面扫一眼。
