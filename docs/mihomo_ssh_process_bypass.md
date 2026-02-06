# Mihomo SSH 进程直连配置说明

## 目的
在开启 TUN 的情况下，让 `ssh` 进程直连（绕开 TUN），避免被 fake-ip 或代理规则影响。

## 修改内容
在 `/opt/clash/mixin.yaml` 的 `rules` 开头加入：
```
PROCESS-NAME,ssh,DIRECT
PROCESS-PATH,/usr/bin/ssh,DIRECT
```

## 生效方式
`/opt/clash/runtime.yaml` 由运行时生成，实际生效取决于你当前的启动方式。
常见做法之一是重载/重启 mihomo 服务后由 mixin 生成 runtime：
```
sudo systemctl restart clash
```
如果你有自定义脚本或面板，请使用你原来的更新/重载方式。

## 验证
```
ssh -v sjg@4070.goodstar.top
```
如果仍被 fake-ip 影响，可再次确认 DNS 是否对该域名做了 fake-ip 过滤。
