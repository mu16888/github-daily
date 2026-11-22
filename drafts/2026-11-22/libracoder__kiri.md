# kiri 适用边界：什么时候能用，什么时候别碰

kiri 在 GitHub 上给自己的简介是「A small, fast container runtime for macOS, Windows and Linux」，一行命令就能装好。仓库标签里有 Docker。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

作者在仓库说明里写了做这个东西的缘由。

Kiri runs containers in one small Linux VM (or straight on the kernel on
Linux) and speaks the Docker Engine API, so your tools just work. The name
comes from the Igbo word *ntakịrị*, "small".

- **Fast**: a container starts and exits in about 2.5 ms through the Docker API.

## 这是个什么项目

> A small, fast container runtime for macOS, Windows and Linux with free Ngrok alternative

主要用 **Rust** 写，GitHub 上攒了 **12136** 颗星（就是收藏数），用的是 Apache-2.0 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[libracoder/kiri](https://github.com/libracoder/kiri)。

## 能做什么

作者在说明里列了这些。

| Area | What you get |
|------|--------------|
| **Containers** | The full lifecycle: `run`, `exec`, `logs`, `attach`, `stop`, `kill`, `restart`, `pause`, `update`, `stats`, `top`, `diff`, `export`, `commit` and `cp` both ways. Records survive a daemon restart. |
| **Limits and security** | `--memory`, `--cpus`, `--pids-limit`, `--shm-size`. Docker's default capabilities and a default seccomp filter, `--cap-add`/`--cap-drop`, `--privileged`, `--read-only`, `no-new-privileges`. |
| **Networking** | A default bridge, user networks with DNS by name and alias, `-p`/`-P` for TCP and UDP, `--network host\|none\|container:<name>`, IPAM (`--subnet`, `--gateway`, `--ip`), IPv6, `host.docker.internal`. |
| **Local domains** | `http://<name>.kiri.local` for every container and `<service>.<project>.kiri.local` for Compose, with HTTPS from Kiri's own certificate authority. |
| **Storage** | Named and anonymous volumes, bind mounts of host paths, `--tmpfs`, `--mount`. |
| **Images** | `pull`, `push`, `tag`, `save`, `load`, `history`, `search`, with `docker login` credentials. amd64 images run through Rosetta on Apple silicon.

## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 Apache-2.0 协议，用起来有规矩
- 12136 颗星，不算冷门
- 写明了限制或不适用场景
- 有对比或基准测试
- 有版本变动或迁移说明
- 讲了设计取舍或为什么做

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
brew install --cask libracoder/kiri/kiri
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

```sh
docker --context kiri run --rm alpine echo hello
docker --context kiri compose up -d
kiri k8s start                      # single-node Kubernetes as the `kiri` kubectl context
kiri machine create dev --distro ubuntu && kiri machine shell dev
kiri import                         # bring images, volumes and containers over from OrbStack or Docker Desktop
```

Docker's commands also work as `kiri` commands (`kiri run`, `kiri ps`,
`kiri compose up`, and so on), and always target Kiri.

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [libracoder/kiri](https://github.com/libracoder/kiri) |
| 收藏数 | 12136 |
| 主要用什么写 | Rust |
| 开源协议 | Apache-2.0 |
| 标签 | containers、docker、kubernetes、linux、macos、oci、windows |
| 创建时间 | 2026-11-02 |
| 最近更新 | 2026-11-22 |
| 数据记于 | 2026-11-22T08:55:20+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- Apache-2.0 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**kiri 解决什么问题？**

kiri 在仓库简介里写的是「A small, fast container runtime for macOS, Windows and Linux」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**kiri 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**kiri 免费吗？**

仓库标的是 Apache-2.0 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**kiri 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

kiri 还在改，装之前记得翻一眼仓库说明。
