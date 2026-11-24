# nginx-proxy 适用边界：什么时候能用，什么时候别碰

nginx-proxy 在 GitHub 上给自己的简介是「Automated Nginx Reverse Proxy for Docker」，19949 Star 的开源项目。仓库标签里有 Docker。要不要装，先看它解决什么问题跟你对不对得上。

## 它解决什么问题

仓库说明没专门写「为什么要做这个」，能看的只有作者自己那几句话。

说明开头是这么写的。

> [](https://github.com/nginx-proxy/nginx-proxy/actions/workflows/test.yml)
> [](https://github.com/nginx-proxy/nginx-proxy/releases)
> [](https://nginx.org/en/CHANGES)
> [](https://hub.docker.com/r/nginxproxy/nginx-proxy "Click to view the image on Docker Hub")
> [](https://hub.docker.com/r/nginxproxy/nginx-proxy "DockerHub")
> [](https://hub.docker.com/r/nginxproxy/nginx-proxy "DockerHub")
> nginx-proxy sets up a container running nginx and [docker-gen](https://github.com/nginx-proxy/docker-gen). docker-gen generates reverse proxy configs for nginx and reloads nginx when containers are started and stopped.
> See [Automated Nginx Reverse Proxy for Docker](http://jasonwilder.com/blog/2014/03/25/automated-nginx-reverse-proxy-for-docker/) for why you might want to use this.

仓库简介就一句。

> Automated Nginx Reverse Proxy for Docker

挂的标签是 docker、docker-gen、nginx、reverse-proxy，能看出它大概跟什么沾边。

## 这是个什么项目

> Automated Nginx Reverse Proxy for Docker

主要用 **Python** 写，GitHub 上攒了 **19949** 颗星（就是收藏数），用的是 MIT 协议。
协议管的是你能不能拿去商用、改了要不要公开，用之前扫一眼。仓库地址：[nginx-proxy/nginx-proxy](https://github.com/nginx-proxy/nginx-proxy)。

## 能做什么

作者在说明里列了这些。

> [!NOTE]
> This repository is officially maintained by <strong>ZeroSSL</strong> as part of our commitment to secure and reliable SSL/TLS solutions.  
> We welcome contributions and feedback from the community!  
> For more information about our services, including free and paid SSL/TLS certificates, visit https://zerossl.com.

## 新手装起来麻烦吗

第一次上手最容易卡在两件事。要不要自己把源码做成能跑的软件，说明里有没有现成命令。这个仓库查到的是这些。

- 写了说明文档
- 说明写得够长，不是三两句就完事
- 写了 Quick Start（快速上手）和怎么装
- 有能直接复制的安装命令
- 标了 MIT 协议，用起来有规矩
- 19949 颗星，不算冷门
- 有版本变动或迁移说明
- 讲了设计取舍或为什么做

## 安装教程

下面这些命令是仓库说明里现成的，复制下来就能跑。动手前顺手去仓库页面扫一眼，作者可能改过版本。

```
docker run --detach \
    --name nginx-proxy \
    --publish 80:80 \
    --volume /var/run/docker.sock:/tmp/docker.sock:ro \
    nginxproxy/nginx-proxy:1.11
```
```
docker run --detach \
    --name your-proxied-app \
    --env VIRTUAL_HOST=foo.bar.com \
    nginx
```

装不上先别急着重试。看看说明是不是改过命令，再看电脑上装没装它要的环境、版本对不对。

## 装完怎么上手

仓库说明里 Quick Start（快速上手）那部分写了这些。

To run it:



Then start any containers (here an nginx container) you want proxied with an env var `VIRTUAL_HOST=subdomain.yourdomain.com`



Provided your DNS is setup to resolve `foo.bar.com` to the host running nginx-proxy, a request to `http://foo.bar.com` will then be routed to a container with the `VIRTUAL_HOST` env var set to `foo.bar.com` (in this case, the **your-proxied-app** container).

The containers being proxied must :

- [expose](https://docs.docker.com/engine/reference/run/#expose-incoming-ports) the port to be proxied, either by using the `EXPOSE` directive in their `Dockerfile` or by using the `--expose` flag to `docker run` or `docker create`.
- share at least one Docker network with the nginx-proxy container: by default, if you don't pass the `--net` flag when your nginx-proxy container is created, it will only be attached to the default bridge network.

## 项目档案

| 项目 | 内容 |
| --- | --- |
| 仓库 | [nginx-proxy/nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) |
| 收藏数 | 19949 |
| 主要用什么写 | Python |
| 开源协议 | MIT |
| 标签 | docker、docker-gen、nginx、reverse-proxy |
| 创建时间 | 2014-05-05 |
| 最近更新 | 2026-11-24 |
| 数据记于 | 2026-11-24T11:41:54+00:00 |

## 动手前留意

- 项目还在改，命令隔段时间可能就不一样了。
- MIT 协议。拿去商用或者改了再发，先看条款让不让。

## 常见问题

**nginx-proxy 解决什么问题？**

nginx-proxy 在仓库简介里写的是「Automated Nginx Reverse Proxy for Docker」。说明里写了缘由的，开头那段就是作者原话；没写的，就看这句简介和标签，别自己脑补。

**nginx-proxy 怎么安装？**

把说明里 Install 那段的命令复制下来跑一遍就行。装不上先看说明是不是改过，再看电脑上装没装它要的环境。

**nginx-proxy 免费吗？**

仓库标的是 MIT 协议，代码可以免费用。拿去做生意或者改了再发，先看条款让不让。

**nginx-proxy 适合新手吗？**

看两件事就够了。说明里有没有现成安装命令，要不要自己把源码做成软件。星星多不多跟这个没关系。


---

nginx-proxy 还在改，装之前记得翻一眼仓库说明。
