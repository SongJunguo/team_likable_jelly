# Claude Context MCP 服务器故障排查报告

## 文档信息

- **创建日期**: 2025-10-30
- **问题类型**: MCP服务器连接失败
- **影响范围**: `claude-context` MCP服务器
- **状态**: 已诊断，提供多种解决方案

---

## 问题描述

### 错误现象

执行 `/mcp` 命令时，系统报告以下错误：

```
Failed to reconnect to claude-context.
```

通过 `claude mcp list` 检查发现：

```
context7: https://mcp.context7.com/mcp (HTTP) - ✓ Connected
claude-context: ... - ✗ Failed to connect
```

---

## 诊断过程

### 1. 初步检查

通过查看Claude Code调试日志（`~/.claude/debug/*.txt`），发现以下关键错误：

```
[DEBUG] MCP server "claude-context": Connection failed after 53ms:
spawn OPENAI_API_KEY=sk-proj-0anH2I... ENOENT

[ERROR] MCP server "claude-context" Connection failed:
spawn OPENAI_API_KEY=sk-proj-0anH2I... ENOENT
```

**问题1识别**: `ENOENT` 错误表示系统尝试将 `OPENAI_API_KEY=...` 作为可执行命令运行，说明MCP配置格式错误。

### 2. 配置检查

检查 `~/.claude.json` 中的MCP配置，发现原始配置将环境变量混入命令字符串中：

```bash
# 错误的配置方式
command: "OPENAI_API_KEY=xxx MILVUS_TOKEN=xxx npx @zilliz/claude-context-mcp@latest"
```

### 3. 修复配置后的新错误

使用正确的配置格式后：

```bash
claude mcp add claude-context \
  -e OPENAI_API_KEY=xxx \
  -e MILVUS_TOKEN=xxx \
  -- npx @zilliz/claude-context-mcp@latest
```

手动测试启动，发现新的错误：

```
Error: Cannot find module '@langchain/core/documents'
Require stack:
- .../node_modules/@langchain/textsplitters/dist/text_splitter.cjs
- .../node_modules/@zilliz/claude-context-core/node_modules/langchain/dist/text_splitter.cjs
```

**问题2识别**: 这是上游包的依赖解析问题。

---

## 根本原因分析

### 问题1: MCP配置格式错误（已修复）

**错误原因**:
- Claude Code MCP 配置要求环境变量通过 `-e` 选项传递
- 直接在命令中使用 `KEY=value` 格式会被解析为可执行文件名
- 这导致系统尝试执行名为 `OPENAI_API_KEY=...` 的程序

**正确格式对比**:

```bash
# ❌ 错误：环境变量混在命令中
claude mcp add claude-context -- OPENAI_API_KEY=xxx npx ...

# ✅ 正确：使用 -e 选项
claude mcp add claude-context -e OPENAI_API_KEY=xxx -- npx ...
```

### 问题2: NPM Peer Dependency 解析失败（未解决）

**依赖链结构**:

```
@zilliz/claude-context-mcp@0.1.3
└── @zilliz/claude-context-core@0.1.3
    ├── langchain@0.3.36 (dependencies)
    │   └── peerDependencies: @langchain/core >=0.3.58 <0.4.0
    └── @langchain/textsplitters (dependencies)
        └── peerDependencies: @langchain/core >=0.2.21 <0.4.0
```

**问题分析**:

1. **Peer Dependencies 未被安装**
   - `@langchain/textsplitters` 和 `langchain` 都声明 `@langchain/core` 为 peerDependency
   - npx 在临时缓存环境中未正确解析和安装这些 peer dependencies
   - 导致运行时 `require('@langchain/core/documents')` 失败

2. **NPX 临时缓存特性**
   - npx 使用随机hash的缓存目录: `~/.npm/_npx/<hash>/`
   - 每次可能使用不同的缓存位置
   - peer dependencies 的安装行为在 npx 环境中不稳定

3. **上游包的依赖配置缺陷**
   - `@zilliz/claude-context-core` 应该将 `@langchain/core` 列为直接依赖
   - 或者正确配置 peerDependenciesMeta
   - 当前版本(0.1.3)缺少这些配置

**技术细节**:

检查实际安装情况：

```bash
# @langchain/core 目录存在但不完整
$ ls /root/.npm/_npx/.../node_modules/@langchain/core/
LICENSE  agents.cjs  callbacks  dist  utils
# 缺少 package.json 和 documents 相关文件

# textsplitters 的依赖声明
$ cat .../node_modules/@langchain/textsplitters/package.json
{
  "peerDependencies": {
    "@langchain/core": ">=0.2.21 <0.4.0"
  }
}
```

---

## 解决方案对比

### 方案1: 禁用 claude-context MCP 服务器 ✅ 推荐

**操作步骤**:

```bash
claude mcp remove claude-context
```

**优点**:
- ✅ 零风险，立即生效
- ✅ context7 MCP 已经提供文档查询功能
- ✅ 保持环境整洁，避免维护负担

**缺点**:
- ❌ 失去语义代码搜索功能（对当前项目影响较小）

**适用场景**: 不需要语义代码搜索的情况

---

### 方案2: 手动修复 npx 缓存依赖 ❌ 不推荐

**操作步骤**:

```bash
# 进入 npx 缓存目录
cd /root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@zilliz/claude-context-core/

# 手动安装缺失的依赖
npm install @langchain/core@latest
```

**风险评估**:

| 风险类型 | 风险等级 | 说明 |
|---------|---------|------|
| 临时性失效 | 🔴 高 | npx 缓存清理后手动安装失效 |
| 版本不匹配 | 🟡 中 | 需手动选择满足所有peerDeps的版本 |
| 依赖链不完整 | 🟡 中 | 可能遗漏传递依赖 |
| 破坏模块结构 | 🔴 高 | 可能影响其他包的解析 |
| 不可复现 | 🔴 高 | 无法通过配置文件管理 |
| 维护成本 | 🟡 中 | 每次更新需重新手动操作 |

**技术问题**:

1. **npx 缓存路径是动态的**:
   ```bash
   # 当前: /root/.npm/_npx/3aea99e9ad4d1a82/
   # 清理后可能变成: /root/.npm/_npx/<new-hash>/
   ```

2. **版本兼容性需手动验证**:
   ```bash
   # textsplitters 要求: >=0.2.21 <0.4.0
   # langchain 要求: >=0.3.58 <0.4.0
   # 必须选择: 0.3.58 ~ 0.3.x
   ```

3. **可能引入新的错误**:
   ```bash
   # @langchain/core 可能还有自己的依赖
   npm install @langchain/core
   # 可能出现: Error: Cannot find module 'zod'
   ```

**结论**: 此方案仅适合临时测试，不适合生产环境。

---

### 方案3: 本地持久化安装 🔧 可选

**操作步骤**:

```bash
# 1. 创建本地MCP服务器目录
mkdir -p ~/mcp-servers/claude-context
cd ~/mcp-servers/claude-context

# 2. 完整安装（包括所有依赖）
npm init -y
npm install @zilliz/claude-context-mcp@latest

# 3. 手动安装缺失的 peer dependencies
npm install @langchain/core@latest

# 4. 修改 Claude MCP 配置
claude mcp remove claude-context
claude mcp add claude-context \
  -e OPENAI_API_KEY=your-key \
  -e MILVUS_TOKEN=your-token \
  -- node ~/mcp-servers/claude-context/node_modules/@zilliz/claude-context-mcp/dist/index.js
```

**优点**:
- ✅ 持久化安装，不受 npx 缓存影响
- ✅ 完整的依赖解析
- ✅ 可维护和可复现
- ✅ 可以通过 git 管理配置

**缺点**:
- ⚠️ 占用磁盘空间（约 200MB）
- ⚠️ 需要手动管理版本更新
- ⚠️ 仍需手动解决 peer dependency 问题

**适用场景**: 确实需要语义代码搜索功能的情况

---

### 方案4: 等待上游修复 ⏳

**操作步骤**:

1. 在 GitHub 提交 Issue:
   ```
   Repository: https://github.com/zilliztech/claude-context
   Issue Title: Missing peer dependency @langchain/core in @zilliz/claude-context-mcp
   ```

2. 定期检查新版本:
   ```bash
   npm view @zilliz/claude-context-mcp version
   ```

3. 等待版本 > 0.1.3 发布后重新安装

**优点**:
- ✅ 从根本上解决问题
- ✅ 所有用户受益

**缺点**:
- ⏰ 时间不确定（可能需要数周）

---

## 技术背景知识

### NPM Peer Dependencies 机制

**什么是 Peer Dependency?**

Peer dependency 是一种特殊的依赖声明，表示：
> "我需要这个包，但不由我安装，应该由使用我的项目来安装"

**为什么使用 Peer Dependency?**

1. **避免版本冲突**:
   ```
   项目
   ├── plugin-a (需要 core@1.0)
   └── plugin-b (需要 core@1.0)

   如果都作为 dependencies:
   ├── node_modules/
       ├── plugin-a/node_modules/core@1.0/
       └── plugin-b/node_modules/core@1.0/  # 重复！

   使用 peerDependencies:
   ├── node_modules/
       ├── core@1.0/                         # 共享
       ├── plugin-a/
       └── plugin-b/
   ```

2. **确保单例模式**:
   - 某些库（如 React、Vue）必须是单例
   - peer dependency 确保整个项目只有一个版本

**NPM 不同版本的行为**:

- **npm v3-v6**: 不自动安装 peer dependencies，只警告
- **npm v7+**: 自动安装 peer dependencies
- **npx**: 行为不稳定，特别是在嵌套依赖场景

### NPNX 临时缓存机制

**npx 工作流程**:

```bash
$ npx @zilliz/claude-context-mcp@latest

1. 计算缓存路径: ~/.npm/_npx/<package-hash>/
2. 检查缓存是否存在
3. 如果不存在，执行 npm install 到缓存目录
4. 执行包的 bin 脚本
5. 保留缓存（可能被清理）
```

**缓存目录结构**:

```
~/.npm/_npx/
├── 3aea99e9ad4d1a82/  # 某次 npx 运行
│   └── node_modules/
│       └── @zilliz/claude-context-mcp@0.1.3/
└── 7b5f3c2e1a934d89/  # 另一次 npx 运行（不同参数）
    └── node_modules/
        └── @zilliz/claude-context-mcp@0.1.3/
```

**问题**:
- 每次运行可能使用不同的缓存目录
- peer dependencies 在某些情况下不被安装
- 手动修改缓存目录是不可持续的

---

## 最佳实践建议

### 1. MCP 服务器配置

**环境变量传递**:

```bash
# ✅ 推荐：使用 -e 选项
claude mcp add server-name \
  -e VAR1=value1 \
  -e VAR2=value2 \
  -- npx package-name

# ❌ 错误：环境变量在命令中
claude mcp add server-name \
  -- VAR1=value1 npx package-name
```

**调试方法**:

```bash
# 1. 查看所有 MCP 服务器状态
claude mcp list

# 2. 查看详细配置
cat ~/.claude.json | jq '.mcpServers'

# 3. 查看调试日志
ls -lt ~/.claude/debug/*.txt | head -1 | awk '{print $NF}' | xargs cat
```

### 2. 依赖问题排查

**检查依赖完整性**:

```bash
# 进入 npx 缓存目录
cd ~/.npm/_npx/*/node_modules/package-name/

# 查看依赖声明
cat package.json | jq '{name, version, peerDependencies, dependencies}'

# 检查实际安装的依赖
ls node_modules/
```

**验证模块可用性**:

```bash
# 在 Node.js 中测试
node -e "require('@langchain/core/documents')"
# 如果报错，说明模块缺失或不完整
```

### 3. 生产环境建议

**对于关键服务**:
- ✅ 使用本地持久化安装（方案3）
- ✅ 通过 package.json 管理版本
- ✅ 使用 package-lock.json 锁定依赖树
- ❌ 避免依赖 npx 的临时缓存

**对于非关键服务**:
- ✅ 使用 npx（简单快速）
- ⚠️ 准备回退方案
- ⚠️ 定期检查服务健康状态

---

## 相关命令速查

### MCP 管理

```bash
# 列出所有 MCP 服务器
claude mcp list

# 添加 MCP 服务器
claude mcp add <name> -e KEY=value -- command args

# 移除 MCP 服务器
claude mcp remove <name>

# 查看配置文件
cat ~/.claude.json | jq '.mcpServers'
```

### NPM/NPX 诊断

```bash
# 查看包信息
npm view <package-name> version dependencies peerDependencies

# 查看 npx 缓存
ls -la ~/.npm/_npx/

# 清理 npx 缓存
rm -rf ~/.npm/_npx/*

# 手动安装到临时目录（测试用）
mkdir /tmp/test-mcp && cd /tmp/test-mcp
npm install <package-name>
node node_modules/.bin/<bin-name>
```

### 调试

```bash
# 查看最新的调试日志
ls -lt ~/.claude/debug/*.txt | head -1 | awk '{print $NF}' | xargs tail -100

# 搜索特定错误
grep -r "ENOENT\|MODULE_NOT_FOUND" ~/.claude/debug/*.txt

# 监控 MCP 服务器进程
ps aux | grep -i mcp
```

---

## 参考资料

### 官方文档

- [Claude Code MCP Documentation](https://docs.anthropic.com/en/docs/claude-code/mcp)
- [Claude Context GitHub](https://github.com/zilliztech/claude-context)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [NPM Peer Dependencies Documentation](https://docs.npmjs.com/cli/v10/configuring-npm/package-json#peerdependencies)

### 相关Issue

- [NPM Issue: peer dependencies not installed in npx](https://github.com/npm/cli/issues/3119)
- [LangChain Issue: Module resolution in different environments](https://github.com/langchain-ai/langchainjs/issues)

---

## 结论与建议

### 当前状态

- ✅ **问题1（配置错误）**: 已修复
- ⏸️ **问题2（依赖缺失）**: 待上游修复

### 推荐行动

**立即执行**:
```bash
# 禁用有问题的 MCP 服务器
claude mcp remove claude-context
```

**如需语义代码搜索**:
- 考虑使用方案3（本地持久化安装）
- 或等待 `@zilliz/claude-context-mcp` 版本 > 0.1.3

**长期监控**:
```bash
# 每周检查一次新版本
npm view @zilliz/claude-context-mcp version

# 版本更新后重新测试
claude mcp add claude-context \
  -e OPENAI_API_KEY=xxx \
  -e MILVUS_TOKEN=xxx \
  -- npx @zilliz/claude-context-mcp@latest
```

---

## 附录：完整错误日志

### 错误日志1: ENOENT (配置错误)

```
[DEBUG] MCP server "claude-context": Starting connection with timeout of 30000ms
[DEBUG] MCP server "claude-context": Connection failed after 53ms:
spawn OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx ENOENT

[ERROR] MCP server "claude-context" Connection failed:
spawn OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx ENOENT
```

### 错误日志2: MODULE_NOT_FOUND (依赖缺失)

```
node:internal/modules/cjs/loader:1383
  const err = new Error(message);
              ^

Error: Cannot find module '@langchain/core/documents'
Require stack:
- /root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@langchain/textsplitters/dist/text_splitter.cjs
- /root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@langchain/textsplitters/dist/index.cjs
- /root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@langchain/textsplitters/index.cjs
- /root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@zilliz/claude-context-core/node_modules/langchain/dist/text_splitter.cjs
- /root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@zilliz/claude-context-core/node_modules/langchain/text_splitter.cjs
- /root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@zilliz/claude-context-core/dist/splitter/langchain-splitter.js
    at Function._resolveFilename (node:internal/modules/cjs/loader:1383:15)
    at defaultResolveImpl (node:internal/modules/cjs/loader:1025:19)
    at resolveForCJSWithHooks (node:internal/modules/cjs/loader:1030:22)
    at Function._load (node:internal/modules/cjs/loader:1192:37)
    at TracingChannel.traceSync (node:diagnostics_channel:322:14)
    at wrapModuleLoad (node:internal/modules/cjs/loader:237:24)
    at Module.require (node:internal/modules/cjs/loader:1463:12)
    at require (node:internal/modules/helpers:147:16)
    at Object.<anonymous> (/root/.npm/_npx/3aea99e9ad4d1a82/node_modules/@langchain/textsplitters/dist/text_splitter.cjs:4:21)
    at Module._compile (node:internal/modules/cjs/loader:1706:14) {
  code: 'MODULE_NOT_FOUND',
  requireStack: [...]
}

Node.js v22.19.0
```

---

**文档版本**: 1.0
**最后更新**: 2025-10-30
**维护者**: Team Likable Jelly
