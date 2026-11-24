# nginx-proxy 更新到 2026-11-24，旧的接入结论要重算

> nginx-proxy 能用的几条，都从说明里挑出来了。

一个工具值不值得装，先看它能不能给你留下点能直接用的东西。说明里给了几条能直接用的。

## 它是什么

> Automated Nginx Reverse Proxy for Docker

主要用 **Python** 写，GitHub 上攒了 **19949** 颗星（就是收藏数），用的是 MIT 协议。仓库地址：[nginx-proxy/nginx-proxy](https://github.com/nginx-proxy/nginx-proxy)。

## 能带走的三条

- 19949 Star

## 先跑这条

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

话题：#开发工具# #开源# #效率工具#
标签：docker,docker-gen,nginx,Docker,开发工具

工具还在改，真要长期用，记得回头看一眼仓库。
