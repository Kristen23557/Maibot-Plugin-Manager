# MaiBot 插件管理器 (Plugin Manager)

一个用于 MaiBot 的插件管理器，提供插件检测、版本检查、自动/批量更新、管理员权限控制与 GitHub 集成等功能。

此插件的使用存在一个重要前提：目标插件的创作者是否在更新插件后更新了manifest文件内的版本号，如果他没更新，那我也没招

## 主要功能

- 插件检测：自动扫描并识别已安装插件。
- 版本检查：检测插件是否有可用更新。
- 一键更新：支持单个插件更新或批量更新（`ALL`）[此功能暂因不可抗力原因使用不稳定，可能会导致插件文件结构损毁请注意！！！]。
- 自动更新：可为每个插件单独配置自动更新。
- 管理员权限：仅管理员可执行管理相关操作。
- GitHub 集成：支持填写 GitHub Token 以提升 API 限制并加快检查/下载速度。
- 安全备份：更新前自动备份，更新失败时自动恢复。

## 快速开始

1. 将插件文件夹放入 `plugins` 目录。
2. 重启 MaiBot 或重新加载插件以启用插件管理器。

## 配置

编辑 `plugins/Plugin_manager/config.toml`，示例：

```toml
[plugin]
enabled = true
config_version = "1.1.2"

[admin]
# 在此添加管理员 QQ 号
qq_list = [123456789, 987654321]

[github]
# 可选配置，但强烈推荐配置以提升 API 限额
# username = "你的GitHub用户名"
# token = "你的GitHub Personal Access Token"
```

### 推荐：配置 GitHub Token

配置 GitHub Personal Access Token 可将无认证的 API 限额（默认 60 次/小时）提升到 5000 次/小时。配置步骤：

1. 登录 GitHub，进入 Settings → Developer settings → Personal access tokens。
2. 点击 **Generate new token**（生成新令牌）。
3. 选择最小权限，例如 `public_repo`（仅访问公开仓库）。
4. 复制生成的 token，并将其粘贴到配置文件的 `token` 字段中。

## 命令列表

| 命令 | 描述 | 示例 |
| --- | --- | --- |
| `/pm list` | 列出已安装的插件 | `/pm list` |
| `/pm check` | 检查所有插件的更新 | `/pm check` |
| `/pm update <插件名>` | 更新指定插件 | `/pm update 海龟汤` |
| `/pm update ALL` | 更新所有有可用更新的插件 | `/pm update ALL` |
| `/pm info <插件名>` | 显示插件详细信息 | `/pm info 海龟汤` |
| `/pm settings` | 管理自动更新设置 | `/pm settings` |
| `/pm github` | 查看/配置 GitHub 设置 | `/pm github` |
| `/pm help` | 显示帮助信息 | `/pm help` |

## 安全更新机制

- 更新前自动备份到 `.backup` 目录；若更新失败，自动从备份恢复。
- 实时显示更新进度与结果，便于排查问题。

## 网络与性能优化

- 支持 GitHub Token 认证以提升 API 限额与下载速度。
- 支持重试机制、并发控制与请求频率限制，降低网络请求失败概率。

## 依赖

- `aiohttp`（用于异步网络请求）

## 故障排查

如果遇到网络超时或连接失败：

- 检查主机网络连接。
- 尝试配置 GitHub Token 以减少受限带来的失败。
- 稍后重试或查看日志获取更多错误信息。

---