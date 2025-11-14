# plugins/Plugin_manager/plugin.py
import os
import json
import aiohttp
import asyncio
import shutil
import tempfile
import ssl
import time
import base64
from typing import List, Tuple, Type, Optional, Dict, Any
from pathlib import Path

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseCommand,
    ComponentInfo,
    ConfigField
)
from src.plugin_system.apis import chat_api, person_api

# 插件管理器版本
PLUGIN_MANAGER_VERSION = "1.1.2"

class PluginManagerCommand(BaseCommand):
    """插件管理器命令 - 管理所有插件的更新和状态"""
    
    command_name = "PluginManagerCommand"
    command_description = "插件管理器，用于管理插件的更新和状态检查"
    command_pattern = r"^/pm\s+(?P<action>\S+)(?:\s+(?P<plugin_name>.+))?$"
    command_help = (
        "📦 **插件管理器帮助**\n\n"
        "🔧 **可用命令**\n"
        "🔸 `/pm list` - 列出所有已安装插件\n"
        "🔸 `/pm check` - 检查所有插件更新\n"
        "🔸 `/pm update <插件名>` - 更新指定插件\n"
        "🔸 `/pm update ALL` - 更新所有需要更新的插件\n"
        "🔸 `/pm info <插件名>` - 查看插件详细信息\n"
        "🔸 `/pm settings` - 管理插件自动更新设置\n"
        "🔸 `/pm github` - 查看GitHub配置状态\n"
        "🔸 `/pm help` - 显示此帮助信息\n\n"
        "💡 **提示**\n"
        "• 默认忽略 'Hello World 示例插件'\n"
        "• 只有管理员可以使用插件管理器\n"
        "• 如需更好的GitHub API体验，请在配置中添加GitHub Token\n"
        "• 尽管此插件带有自动更新功能，但我们仍然强烈建议您在更新或检查插件更新后手动检查插件文件!!!"
    )
    intercept_message = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_api_call = 0
        self._min_api_interval = 2.0  # 最少2秒间隔避免频率限制

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行插件管理器命令"""
        try:
            # 首先检查管理员权限
            if not await self._check_admin_permission():
                try:
                    await self.send_text("❌ 权限不足，只有管理员可以使用插件管理器。")
                except Exception as e:
                    print(f"发送权限错误消息失败: {e}")
                return False, "权限不足", True

            # 安全获取匹配的参数
            matched_groups = self.matched_groups or {}
            action = str(matched_groups.get("action", "")).strip().lower() if matched_groups.get("action") else ""
            plugin_name = str(matched_groups.get("plugin_name", "")).strip() if matched_groups.get("plugin_name") else ""

            # 如果没有action，显示帮助
            if not action:
                try:
                    await self.send_text(self.command_help)
                except Exception as e:
                    print(f"发送帮助信息失败: {e}")
                return True, "已发送帮助信息", True

            # 处理不同动作
            if action == "list":
                return await self._list_plugins()
            elif action == "check":
                return await self._check_updates()
            elif action == "update":
                return await self._update_plugin(plugin_name)
            elif action == "info":
                return await self._plugin_info(plugin_name)
            elif action == "settings":
                return await self._manage_settings(plugin_name)
            elif action == "github":
                return await self._show_github_status()
            elif action == "help":
                try:
                    await self.send_text(self.command_help)
                except Exception as e:
                    print(f"发送帮助信息失败: {e}")
                return True, "已发送帮助信息", True
            else:
                try:
                    await self.send_text(f"❌ 未知命令: {action}\n请使用 `/pm help` 查看可用命令。")
                except Exception as e:
                    print(f"发送未知命令错误失败: {e}")
                return False, f"未知命令: {action}", True

        except Exception as e:
            error_msg = f"❌ 命令执行出错: {str(e)}"
            try:
                await self.send_text(error_msg)
            except Exception as send_e:
                print(f"发送错误消息也失败了: {send_e}")
            return False, error_msg, True

    async def _show_github_status(self) -> Tuple[bool, Optional[str], bool]:
        """显示GitHub配置状态"""
        try:
            github_config = self._get_github_config()
            has_token = bool(github_config.get('token'))
            has_username = bool(github_config.get('username'))
            
            status_message = "🔗 **GitHub配置状态**\n\n"
            
            if has_token and has_username:
                status_message += "✅ **认证状态**: 已配置GitHub账号\n"
                status_message += f"👤 **用户名**: {github_config['username']}\n"
                status_message += "🔑 **Token状态**: 已配置\n"
                status_message += "🚀 **API限制**: 大幅提升 (5000次/小时)\n"
            elif has_token:
                status_message += "⚠️ **认证状态**: 部分配置\n"
                status_message += "🔑 **Token状态**: 已配置\n"
                status_message += "👤 **用户名**: 未配置\n"
                status_message += "🚀 **API限制**: 提升 (5000次/小时)\n"
            else:
                status_message += "❌ **认证状态**: 未配置GitHub账号\n"
                status_message += "🔑 **Token状态**: 未配置\n"
                status_message += "👤 **用户名**: 未配置\n"
                status_message += "🐌 **API限制**: 严格 (60次/小时)\n"
            
            status_message += "\n💡 **配置说明**\n"
            status_message += "• 在 `config.toml` 的 `[github]` 节中配置\n"
            status_message += "• `username`: 你的GitHub用户名\n"
            status_message += "• `token`: GitHub Personal Access Token\n"
            status_message += "• 获取Token: https://github.com/settings/tokens\n"
            status_message += "• Token权限: 只需要 `public_repo` 权限\n"
            
            await self.send_text(status_message)
            return True, "已显示GitHub状态", True
            
        except Exception as e:
            error_msg = f"❌ 获取GitHub状态时出错: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, True

    def _get_github_config(self) -> Dict[str, str]:
        """获取GitHub配置"""
        return {
            'username': self.get_config("github.username", "").strip(),
            'token': self.get_config("github.token", "").strip()
        }

    def _get_github_headers(self) -> Dict[str, str]:
        """获取GitHub API请求头"""
        github_config = self._get_github_config()
        headers = {
            'User-Agent': 'MaiBot-Plugin-Manager/1.1.2',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # 如果有token，使用token认证
        if github_config.get('token'):
            headers['Authorization'] = f"token {github_config['token']}"
            
        return headers

    async def _check_admin_permission(self) -> bool:
        """检查用户是否为管理员 - 使用聊天API正确获取用户信息"""
        try:
            # 获取配置的管理员QQ号列表
            admin_qq_list = self.get_config("admin.qq_list", [])
            if not admin_qq_list:
                print("管理员QQ列表为空，拒绝访问")
                return False

            # 获取当前聊天流信息
            message_obj = getattr(self, 'message', None)
            if not message_obj:
                print("无法获取message对象")
                return False

            # 获取聊天流
            chat_stream = getattr(message_obj, 'chat_stream', None)
            if not chat_stream:
                print("无法获取chat_stream")
                return False

            # 使用聊天API获取流信息
            stream_info = chat_api.get_stream_info(chat_stream)
            print(f"聊天流信息: {stream_info}")

            # 根据聊天流类型获取用户ID
            user_id = None
            stream_type = chat_api.get_stream_type(chat_stream)
            
            if stream_type == "private":
                # 私聊：直接从流信息获取用户ID
                user_id = stream_info.get('user_id')
                print(f"私聊用户ID: {user_id}")
            elif stream_type == "group":
                # 群聊：需要从消息发送者获取用户ID
                sender_info = getattr(message_obj, 'sender_info', None)
                if sender_info:
                    user_id = getattr(sender_info, 'user_id', None)
                    print(f"群聊发送者用户ID: {user_id}")
            else:
                print(f"未知聊天流类型: {stream_type}")
                return False

            if not user_id:
                print("无法获取用户ID")
                return False

            # 转换为字符串比较
            user_id_str = str(user_id).strip()
            admin_qq_str_list = [str(qq).strip() for qq in admin_qq_list]
            
            print(f"权限检查 - 用户ID: '{user_id_str}', 管理员列表: {admin_qq_str_list}")
            
            # 精确匹配检查
            is_admin = user_id_str in admin_qq_str_list
            print(f"权限检查结果: {is_admin}")
            
            return is_admin

        except Exception as e:
            print(f"检查管理员权限时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _list_plugins(self) -> Tuple[bool, Optional[str], bool]:
        """列出所有已安装插件"""
        try:
            plugins_dir = self._get_plugins_directory()
            plugins = self._scan_plugins(plugins_dir)
            
            if not plugins:
                await self.send_text("📦 未找到任何有效插件。")
                return True, "未找到插件", True

            # 构建插件列表消息
            message = "📦 **已安装插件列表**\n\n"
            for plugin in plugins:
                status = "🟢 最新" if not plugin.get("needs_update", False) else "🟡 可更新"
                auto_update_status = "✅" if self._get_plugin_auto_update_setting(plugin['name']) else "❌"
                message += f"• {plugin['name']} v{plugin['local_version']} {status} {auto_update_status}\n"

            message += f"\n💡 共找到 {len(plugins)} 个插件"
            message += "\n🔧 使用 `/pm check` 检查更新，`/pm update <插件名>` 更新插件"
            message += "\n⚙️  ✅ = 自动更新开启，❌ = 自动更新关闭"

            await self.send_text(message)
            return True, f"已列出 {len(plugins)} 个插件", True

        except Exception as e:
            error_msg = f"❌ 列出插件时出错: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, True

    async def _check_updates(self) -> Tuple[bool, Optional[str], bool]:
        """检查所有插件更新 - 统一发送结果"""
        try:
            plugins_dir = self._get_plugins_directory()
            plugins = self._scan_plugins(plugins_dir)
            
            if not plugins:
                await self.send_text("📦 未找到任何有效插件。")
                return True, "未找到插件", True

            # 发送检查开始消息
            checking_message = f"🔄 **正在检查 {len(plugins)} 个插件的更新...**\n请稍候..."
            await self.send_text(checking_message)

            # 串行检查所有插件的更新（避免GitHub API限制）
            update_available = []
            check_results = []
            
            # 创建 SSL 上下文以禁用证书验证
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            github_config = self._get_github_config()
            auth_status = "🔑 使用认证" if github_config.get('token') else "⚠️ 未认证"
            
            # 串行检查所有插件，避免GitHub API限制
            for plugin in plugins:
                try:
                    # 添加延迟避免API限制
                    await self._rate_limit_delay()
                    
                    # 只使用 repository_url 字段
                    repository_url = plugin.get('repository_url', '')
                    if not repository_url:
                        check_results.append(f"🔴 {plugin['name']}: v{plugin['local_version']} (无仓库地址)")
                        continue
                    
                    remote_version = await self._get_remote_version(repository_url, ssl_context)
                    if remote_version and remote_version != plugin['local_version']:
                        plugin['remote_version'] = remote_version
                        plugin['needs_update'] = True
                        update_available.append(plugin)
                        check_results.append(f"🟡 {plugin['name']}: v{plugin['local_version']} → v{remote_version}")
                    else:
                        check_results.append(f"🟢 {plugin['name']}: v{plugin['local_version']} (最新)")
                except Exception as e:
                    check_results.append(f"🔴 {plugin['name']}: v{plugin['local_version']} (检查失败)")
                    print(f"检查插件 {plugin['name']} 更新失败: {e}")

            # 构建统一的结果消息
            result_message = "📊 **插件更新检查结果**\n\n"
            
            # 添加有更新的插件
            if update_available:
                result_message += "🟡 **可更新插件**\n"
                for plugin in update_available:
                    result_message += f"• {plugin['name']}: v{plugin['local_version']} → v{plugin['remote_version']}\n"
                result_message += "\n"
            
            # 添加所有插件状态
            result_message += "📋 **所有插件状态**\n"
            for result in check_results:
                result_message += f"{result}\n"
            
            # 添加操作提示
            result_message += f"\n🎯 **检查完成**\n"
            if update_available:
                result_message += f"发现 {len(update_available)} 个可更新插件\n\n"
                result_message += f"💡 使用 `/pm update ALL` 更新所有插件\n"
                result_message += f"🔧 或使用 `/pm update <插件名>` 更新指定插件"
            else:
                result_message += "🟢 所有插件均为最新版本"

            await self.send_text(result_message)
            return True, f"检查完成，发现 {len(update_available)} 个可更新插件", True

        except Exception as e:
            error_msg = f"❌ 检查更新时出错: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, True

    async def _rate_limit_delay(self):
        """API调用频率限制"""
        current_time = time.time()
        time_since_last_call = current_time - self._last_api_call
        if time_since_last_call < self._min_api_interval:
            await asyncio.sleep(self._min_api_interval - time_since_last_call)
        self._last_api_call = time.time()

    async def _update_plugin(self, plugin_name: str) -> Tuple[bool, Optional[str], bool]:
        """更新指定插件或所有插件"""
        try:
            if not plugin_name:
                await self.send_text("❌ 请指定要更新的插件名或使用 ALL 更新所有插件。")
                return False, "未指定插件名", True

            plugins_dir = self._get_plugins_directory()
            plugins = self._scan_plugins(plugins_dir)
            
            if plugin_name.upper() == "ALL":
                # 先检查所有需要更新的插件
                plugins_to_update = []
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                checking_message = "🔄 **正在检查所有插件的更新状态...**"
                await self.send_text(checking_message)
                
                for plugin in plugins:
                    # 添加延迟避免API限制
                    await self._rate_limit_delay()
                    
                    # 只使用 repository_url 字段
                    repository_url = plugin.get('repository_url', '')
                    if not repository_url:
                        continue
                    
                    remote_version = await self._get_remote_version(repository_url, ssl_context)
                    if remote_version and remote_version != plugin['local_version']:
                        plugin['remote_version'] = remote_version
                        plugin['needs_update'] = True
                        plugins_to_update.append(plugin)

                if not plugins_to_update:
                    await self.send_text("🟢 所有插件均为最新版本，无需更新。")
                    return True, "无需更新", True

                update_message = f"🔄 **开始更新 {len(plugins_to_update)} 个插件**\n\n"
                await self.send_text(update_message)

                success_count = 0
                update_results = []
                for plugin in plugins_to_update:
                    try:
                        if await self._perform_plugin_update(plugin):
                            success_count += 1
                            update_results.append(f"✅ {plugin['name']} → v{plugin['remote_version']}")
                        else:
                            update_results.append(f"❌ {plugin['name']} 更新失败")
                    except Exception as e:
                        update_results.append(f"❌ {plugin['name']} 更新出错: {str(e)}")

                # 统一发送更新结果
                result_message = f"🎉 **批量更新完成**\n成功: {success_count}/{len(plugins_to_update)}\n\n"
                for result in update_results:
                    result_message += f"{result}\n"
                
                await self.send_text(result_message)
                return True, f"批量更新完成: {success_count}/{len(plugins_to_update)}", True

            else:
                # 更新指定插件
                target_plugin = None
                for plugin in plugins:
                    if plugin['name'].lower() == plugin_name.lower():
                        target_plugin = plugin
                        break

                if not target_plugin:
                    await self.send_text(f"❌ 未找到插件: {plugin_name}")
                    return False, f"插件未找到: {plugin_name}", True

                # 检查是否需要更新
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # 添加延迟避免API限制
                await self._rate_limit_delay()
                
                # 只使用 repository_url 字段
                repository_url = target_plugin.get('repository_url', '')
                if not repository_url:
                    await self.send_text(f"❌ 插件 {plugin_name} 没有配置仓库地址")
                    return False, "无仓库地址", True
                
                remote_version = await self._get_remote_version(repository_url, ssl_context)
                if not remote_version:
                    await self.send_text(f"❌ 无法获取 {plugin_name} 的远程版本信息")
                    return False, "无法获取远程版本", True

                if remote_version == target_plugin['local_version']:
                    await self.send_text(f"🟢 {plugin_name} 已是最新版本 (v{remote_version})")
                    return True, "插件已是最新", True

                target_plugin['remote_version'] = remote_version
                await self.send_text(f"🔄 开始更新插件: {plugin_name} (v{target_plugin['local_version']} → v{remote_version})")
                
                if await self._perform_plugin_update(target_plugin):
                    success_msg = f"✅ **更新成功**\n{plugin_name} 已更新到 v{remote_version}"
                    await self.send_text(success_msg)
                    return True, f"插件更新成功: {plugin_name}", True
                else:
                    error_msg = f"❌ 更新插件失败: {plugin_name}"
                    await self.send_text(error_msg)
                    return False, error_msg, True

        except Exception as e:
            error_msg = f"❌ 更新插件时出错: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, True

    async def _plugin_info(self, plugin_name: str) -> Tuple[bool, Optional[str], bool]:
        """查看插件详细信息"""
        try:
            if not plugin_name:
                await self.send_text("❌ 请指定要查看的插件名。")
                return False, "未指定插件名", True

            plugins_dir = self._get_plugins_directory()
            plugins = self._scan_plugins(plugins_dir)
            
            target_plugin = None
            for plugin in plugins:
                if plugin['name'].lower() == plugin_name.lower():
                    target_plugin = plugin
                    break

            if not target_plugin:
                await self.send_text(f"❌ 未找到插件: {plugin_name}")
                return False, f"插件未找到: {plugin_name}", True

            # 构建详细信息消息
            info_message = f"📋 **插件信息 - {target_plugin['name']}**\n\n"
            info_message += f"🔸 **版本**: v{target_plugin['local_version']}\n"
            info_message += f"🔸 **目录**: {target_plugin['directory_name']}\n"
            info_message += f"🔸 **仓库**: {target_plugin['repository_url']}\n"
            
            # 检查远程版本
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # 添加延迟避免API限制
            await self._rate_limit_delay()
            
            # 只使用 repository_url 字段
            repository_url = target_plugin.get('repository_url', '')
            if repository_url:
                remote_version = await self._get_remote_version(repository_url, ssl_context)
                if remote_version:
                    status = "🟢 最新" if remote_version == target_plugin['local_version'] else "🟡 可更新"
                    info_message += f"🔸 **远程版本**: v{remote_version}\n"
                    info_message += f"🔸 **状态**: {status}\n"
                else:
                    info_message += "🔸 **状态**: 🔴 无法检查更新\n"
            else:
                info_message += "🔸 **状态**: 🔴 无仓库地址\n"

            # 自动更新设置
            auto_update = self._get_plugin_auto_update_setting(target_plugin['name'])
            info_message += f"🔸 **自动更新**: {'✅ 开启' if auto_update else '❌ 关闭'}\n"

            await self.send_text(info_message)
            return True, f"已显示插件信息: {plugin_name}", True

        except Exception as e:
            error_msg = f"❌ 获取插件信息时出错: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, True

    async def _manage_settings(self, setting_args: str) -> Tuple[bool, Optional[str], bool]:
        """管理插件自动更新设置"""
        try:
            if not setting_args:
                # 显示当前设置
                settings = self._load_settings()
                message = "⚙️ **插件自动更新设置**\n\n"
                
                plugins_dir = self._get_plugins_directory()
                plugins = self._scan_plugins(plugins_dir)
                
                for plugin in plugins:
                    auto_update = settings.get('auto_update', {}).get(plugin['name'], False)
                    status = "✅ 开启" if auto_update else "❌ 关闭"
                    message += f"• {plugin['name']}: {status}\n"
                
                message += "\n💡 使用 `/pm settings <插件名> on/off` 修改设置"
                message += "\n💡 例如: `/pm settings 海龟汤 on`"
                
                await self.send_text(message)
                return True, "已显示设置", True
            else:
                # 修改设置
                parts = setting_args.split()
                if len(parts) < 2:
                    await self.send_text("❌ 参数格式错误。使用: `/pm settings <插件名> on/off`")
                    return False, "参数格式错误", True
                
                plugin_name = ' '.join(parts[:-1])
                action = parts[-1].lower()
                
                if action not in ['on', 'off']:
                    await self.send_text("❌ 操作参数错误，请使用 'on' 或 'off'")
                    return False, "操作参数错误", True
                
                # 验证插件是否存在
                plugins_dir = self._get_plugins_directory()
                plugins = self._scan_plugins(plugins_dir)
                plugin_exists = any(p['name'].lower() == plugin_name.lower() for p in plugins)
                
                if not plugin_exists:
                    await self.send_text(f"❌ 未找到插件: {plugin_name}")
                    return False, "插件未找到", True
                
                # 更新设置
                settings = self._load_settings()
                if 'auto_update' not in settings:
                    settings['auto_update'] = {}
                
                # 找到准确的插件名（保持大小写）
                actual_plugin_name = next(p['name'] for p in plugins if p['name'].lower() == plugin_name.lower())
                settings['auto_update'][actual_plugin_name] = (action == 'on')
                self._save_settings(settings)
                
                status = "开启" if action == 'on' else "关闭"
                await self.send_text(f"✅ 已{status} {actual_plugin_name} 的自动更新")
                return True, f"已更新设置: {actual_plugin_name} = {action}", True

        except Exception as e:
            error_msg = f"❌ 管理设置时出错: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, True

    def _get_plugins_directory(self) -> Path:
        """获取plugins目录路径"""
        current_file = Path(__file__).resolve()
        # 当前插件目录: plugins/Plugin_manager
        plugins_dir = current_file.parent.parent
        return plugins_dir

    def _scan_plugins(self, plugins_dir: Path) -> List[Dict[str, Any]]:
        """扫描plugins目录下的所有插件"""
        plugins = []
        ignored_plugin = "Hello World 示例插件 (Hello World Plugin)"
        
        for item in plugins_dir.iterdir():
            if item.is_dir() and item.name != "Plugin_manager":
                manifest_file = item / "_manifest.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, 'r', encoding='utf-8') as f:
                            manifest_data = json.load(f)
                        
                        plugin_name = manifest_data.get('name', '')
                        if plugin_name == ignored_plugin:
                            continue
                            
                        plugins.append({
                            'name': plugin_name,
                            'local_version': manifest_data.get('version', '未知'),
                            'repository_url': manifest_data.get('repository_url', ''),
                            'directory_name': item.name,
                            'directory_path': item,
                            'needs_update': False
                        })
                    except Exception as e:
                        print(f"读取插件 {item.name} 的manifest文件失败: {e}")
                        continue
        
        return plugins

    async def _get_remote_version(self, repository_url: str, ssl_context: ssl.SSLContext = None) -> Optional[str]:
        """从GitHub仓库获取最新版本号 - 支持GitHub认证"""
        try:
            if not repository_url or "github.com" not in repository_url:
                print(f"无效的仓库URL: {repository_url}")
                return None

            # 清理和验证仓库URL
            repo_path = repository_url.replace("https://github.com/", "").strip("/")
            if not repo_path or '/' not in repo_path:
                print(f"无效的仓库路径: {repo_path}")
                return None

            # 构建GitHub API URL
            api_url = f"https://api.github.com/repos/{repo_path}/contents/_manifest.json"
            print(f"请求GitHub API: {api_url}")

            # 创建连接器，禁用SSL验证
            connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context else None
            
            # 获取GitHub认证头
            headers = self._get_github_headers()
            github_config = self._get_github_config()
            
            timeout = aiohttp.ClientTimeout(total=15)  # 15秒超时
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(api_url, headers=headers) as response:
                    print(f"GitHub API响应状态: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        if 'content' in data:
                            # 解码base64内容
                            content = base64.b64decode(data['content']).decode('utf-8')
                            manifest_data = json.loads(content)
                            version = manifest_data.get('version')
                            print(f"获取到远程版本: {version}")
                            return version
                        else:
                            print(f"响应中缺少content字段: {data}")
                    elif response.status == 403:
                        # 检查速率限制头
                        remaining = response.headers.get('X-RateLimit-Remaining', '未知')
                        limit = response.headers.get('X-RateLimit-Limit', '未知')
                        reset_time = response.headers.get('X-RateLimit-Reset', '未知')
                        print(f"GitHub API限制 - 剩余: {remaining}/{limit}, 重置: {reset_time}")
                        
                        if github_config.get('token'):
                            print("即使使用Token也遇到限制，可能需要等待")
                        else:
                            print("未使用GitHub Token，API限制严格")
                            
                    elif response.status == 404:
                        print("仓库或manifest文件不存在")
                    elif response.status == 401:
                        print("GitHub Token无效或过期")
                    else:
                        print(f"GitHub API错误: {response.status}")
                        error_text = await response.text()
                        print(f"错误详情: {error_text}")
            
            return None
        except asyncio.TimeoutError:
            print(f"获取远程版本超时: {repository_url}")
            return None
        except Exception as e:
            print(f"获取远程版本失败 {repository_url}: {e}")
            return None

    async def _perform_plugin_update(self, plugin: Dict[str, Any]) -> bool:
        """执行插件更新：从GitHub仓库下载并覆盖文件 - 改进的网络稳定性"""
        try:
            repository_url = plugin['repository_url']
            if not repository_url or "github.com" not in repository_url:
                print(f"无效的仓库URL: {repository_url}")
                return False

            repo_path = repository_url.replace("https://github.com/", "").strip("/")
            if not repo_path or '/' not in repo_path:
                print(f"无效的仓库路径: {repo_path}")
                return False

            api_url = f"https://api.github.com/repos/{repo_path}/contents/"
            print(f"开始更新插件 {plugin['name']}，仓库: {repo_path}")

            # 创建 SSL 上下文以禁用证书验证
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            # 获取GitHub认证头
            headers = self._get_github_headers()

            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 获取仓库文件列表
                async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                    async with session.get(api_url) as response:
                        if response.status != 200:
                            print(f"获取仓库文件列表失败: {response.status}")
                            return False
                        
                        files_data = await response.json()
                        print(f"找到 {len(files_data)} 个文件")
                        
                        # 只下载必要的文件，跳过LICENSE等非必要文件
                        essential_files = ['plugin.py', '_manifest.json', 'config.toml', 'requirements.txt']
                        download_tasks = []
                        for file_info in files_data:
                            if file_info['type'] == 'file' and file_info.get('download_url'):
                                file_name = file_info['name']
                                # 优先下载必要文件，其他文件可选
                                if file_name in essential_files or file_name.endswith('.py') or file_name.endswith('.json'):
                                    download_tasks.append(self._download_file_with_retry(session, file_info, temp_path))
                        
                        # 并行下载文件，但限制并发数
                        if download_tasks:
                            # 限制并发数为3，避免网络压力过大
                            semaphore = asyncio.Semaphore(3)
                            async def limited_download(task):
                                async with semaphore:
                                    return await task
                            
                            limited_tasks = [limited_download(task) for task in download_tasks]
                            await asyncio.gather(*limited_tasks, return_exceptions=True)

                # 检查是否下载了必要文件
                downloaded_files = list(temp_path.iterdir())
                essential_downloaded = any(file.name in essential_files for file in downloaded_files)
                
                if not essential_downloaded:
                    print("没有成功下载必要文件")
                    return False

                print(f"成功下载 {len(downloaded_files)} 个文件")

                # 备份原插件目录
                plugin_dir = plugin['directory_path']
                backup_dir = plugin_dir.with_suffix('.backup')
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                shutil.copytree(plugin_dir, backup_dir)
                print(f"已创建备份: {backup_dir}")

                try:
                    # 清空原目录
                    for item in plugin_dir.iterdir():
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)

                    # 复制新文件
                    for item in temp_path.iterdir():
                        if item.is_file():
                            shutil.copy2(item, plugin_dir / item.name)
                        elif item.is_dir():
                            shutil.copytree(item, plugin_dir / item.name)

                    print(f"成功更新插件 {plugin['name']}")

                    # 更新成功后删除备份
                    if backup_dir.exists():
                        shutil.rmtree(backup_dir)
                    
                    return True

                except Exception as e:
                    # 恢复备份
                    print(f"更新失败，恢复备份: {e}")
                    if backup_dir.exists():
                        # 清空失败的文件
                        for item in plugin_dir.iterdir():
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item)
                        # 恢复备份
                        for item in backup_dir.iterdir():
                            if item.is_file():
                                shutil.copy2(item, plugin_dir / item.name)
                            elif item.is_dir():
                                shutil.copytree(item, plugin_dir / item.name)
                        print("已从备份恢复插件")
                    return False

        except Exception as e:
            print(f"执行插件更新失败 {plugin['name']}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _download_file_with_retry(self, session: aiohttp.ClientSession, file_info: Dict, temp_path: Path, max_retries: int = 3) -> None:
        """下载单个文件，带重试机制"""
        for attempt in range(max_retries):
            try:
                file_url = file_info['download_url']
                file_path = temp_path / file_info['name']
                
                # 设置较短的超时时间，避免长时间等待
                timeout = aiohttp.ClientTimeout(total=10)
                
                async with session.get(file_url, timeout=timeout) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        print(f"下载成功: {file_info['name']} (尝试 {attempt + 1})")
                        return
                    else:
                        print(f"下载失败 {file_info['name']}: {response.status} (尝试 {attempt + 1})")
            except asyncio.TimeoutError:
                print(f"下载超时 {file_info['name']} (尝试 {attempt + 1})")
            except Exception as e:
                print(f"下载文件 {file_info['name']} 时出错 (尝试 {attempt + 1}): {e}")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # 等待1秒后重试
        
        print(f"下载失败 {file_info['name']}，已重试 {max_retries} 次")

    def _get_settings_file_path(self) -> Path:
        """获取设置文件路径"""
        plugin_dir = Path(__file__).parent
        return plugin_dir / "plugin_settings.json"

    def _load_settings(self) -> Dict[str, Any]:
        """加载设置文件"""
        settings_file = self._get_settings_file_path()
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取设置文件失败: {e}")
        return {}

    def _save_settings(self, settings: Dict[str, Any]) -> None:
        """保存设置文件"""
        try:
            settings_file = self._get_settings_file_path()
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存设置文件失败: {e}")

    def _get_plugin_auto_update_setting(self, plugin_name: str) -> bool:
        """获取插件的自动更新设置"""
        settings = self._load_settings()
        return settings.get('auto_update', {}).get(plugin_name, False)


@register_plugin
class PluginManagerPlugin(BasePlugin):
    """插件管理器插件 - 管理所有插件的更新和状态"""
    
    plugin_name = "plugin_manager"
    plugin_description = "插件管理器，用于管理插件的更新和状态检查"
    plugin_version = PLUGIN_MANAGER_VERSION
    plugin_author = "Plugin Manager Team"
    enable_plugin = True

    dependencies = []
    python_dependencies = ["aiohttp"]

    config_file_name = "config.toml"
    config_section_descriptions = {
        "plugin": "插件启用配置",
        "admin": "管理员配置",
        "github": "GitHub API配置"
    }

    config_schema = {
        "plugin": {
            "enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用插件管理器"
            ),
            "config_version": ConfigField(
                type=str,
                default="1.1.2",
                description="配置文件版本"
            ),
        },
        "admin": {
            "qq_list": ConfigField(
                type=list,
                default=[],
                description="管理员QQ号列表（所有命令都需要管理员权限）"
            )
        },
        "github": {
            "username": ConfigField(
                type=str,
                default="",
                description="GitHub用户名（用于显示和调试）"
            ),
            "token": ConfigField(
                type=str,
                default="",
                description="GitHub Personal Access Token（获取地址：https://github.com/settings/tokens，只需要public_repo权限）"
            )
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """注册插件组件"""
        return [
            (PluginManagerCommand.get_command_info(), PluginManagerCommand),
        ]