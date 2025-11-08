# screen 配置记录

- 2025-11-08：新增 `~/.screenrc`，启用 UTF-8、扩大滚动缓冲区并关闭启动提示，方便检查日志和中文输出。

## 生效方式
- 对新的 screen 会话立即生效；已有会话需先 `Ctrl-A` `:` 输入 `source ~/.screenrc`，或直接退出并重新进入 `screen -U`.

## 当前全局配置摘要
```text
defutf8 on
defencoding UTF-8
encoding UTF-8 UTF-8
defscrollback 5000
startup_message off
```
