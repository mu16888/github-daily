# 开源项目 nginx-proxy，主要解决哪类麻烦

> nginx-proxy 值不值得花时间，先看它管什么。

一个工具值不值得装，先看它能不能给你留下点能直接用的东西。值不值得花时间，先看它到底管什么。

## 它是什么

> Automated Nginx Reverse Proxy for Docker

主要用 **Python** 写，GitHub 上攒了 **19949** 颗星（就是收藏数），用的是 MIT 协议。仓库地址：[nginx-proxy/nginx-proxy](https://github.com/nginx-proxy/nginx-proxy)。

| 能查到的 | 值 |
| --- | --- |
| 仓库 | [nginx-proxy/nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) |
| 收藏数 | 19949 |
| 主要语言 | Python |
| 协议 | MIT |
| 建库 / 最近更新 | 2014-05-05 / 2026-11-24 |

## 能带走的三条

- 19949 Star

## 先做哪一步

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

命令是仓库说明里现成的，动手前扫一眼项目页面，作者可能改过版本。

## 边界在哪

- MIT 协议，拿去商用或者改了再发，先看条款让不让。
- 建库 2014-05-05，最近更新 2026-11-24，项目还在改。
- 命令隔段时间可能不一样，用之前翻一眼仓库说明。

话题：#开发工具# #开源# #效率工具#
标签：docker,docker-gen,nginx,Docker,开发工具

能不能用上，试过第一步就知道，不用先把说明从头读完。
