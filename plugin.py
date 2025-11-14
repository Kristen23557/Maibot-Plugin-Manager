# plugins/Plugin_manager/plugin.py
import os
import json
import aiohttp
import asyncio
import shutil
import tempfile
from typing import List, Tuple, Type, Optional, Dict, Any
from pathlib import Path

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseCommand,
    ComponentInfo,
    ConfigField
)

# 插件管理器版本
PLUGIN_MANAGER_VERSION = "1.0.0"

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
        "🔸 `/pm help` - 显示此帮助信息\n\n"
        "💡 **提示**\n"
        "• 默认忽略 'Hello World 示例插件'\n"
        "• 只有管理员可以使用更新功能\n"
        "• 插件更新从 GitHub 仓库获取最新版本"
    )
    intercept_message = True

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行插件管理器命令"""
        # 获取匹配的参数
        matched_groups = self.matched_groups if self.matched_groups is not None else {}
        action = matched_groups.get("action", "").strip().lower()
        plugin_name = matched_groups.get("plugin_name", "").strip()

        # 检查管理员权限（对于需要权限的操作）
        if action in ["update", "settings"] and not await self._check_admin_permission():
            try:
                await self.send_text("❌ 权限不足，只有管理员可以使用此功能。")
            except Exception as e:
                print(f"发送权限错误消息失败: {e}")
            return False, "权限不足", True

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
        elif action == "help" or not action:
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

    async def _check_admin_permission(self) -> bool:
        """检查用户是否为管理员"""
        try:
            # 获取配置的管理员QQ号列表
            admin_qq_list = self.get_config("admin.qq_list", [])
            if not admin_qq_list:
                return False

            # 获取当前用户QQ号
            chat_stream = getattr(self, 'chat_stream', None)
            if not chat_stream:
                return False

            user_info = getattr(chat_stream, 'user_info', None)
            if not user_info:
                return False

            user_qq = getattr(user_info, 'user_id', None)
            if not user_qq:
                return False

            return str(user_qq) in [str(qq) for qq in admin_qq_list]

        except Exception as e:
            print(f"检查管理员权限时出错: {e}")
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
        """检查所有插件更新"""
        try:
            plugins_dir = self._get_plugins_directory()
            plugins = self._scan_plugins(plugins_dir)
            
            if not plugins:
                await self.send_text("📦 未找到任何有效插件。")
                return True, "未找到插件", True

            # 检查每个插件的更新
            update_available = []
            checking_message = "🔄 **正在检查插件更新...**\n\n"
            await self.send_text(checking_message)

            for plugin in plugins:
                remote_version = await self._get_remote_version(plugin['repository_url'])
                if remote_version and remote_version != plugin['local_version']:
                    plugin['remote_version'] = remote_version
                    plugin['needs_update'] = True
                    update_available.append(plugin)
                    
                    progress_msg = f"🟡 {plugin['name']}: v{plugin['local_version']} → v{remote_version}"
                    await self.send_text(progress_msg)
                else:
                    progress_msg = f"🟢 {plugin['name']}: v{plugin['local_version']} (最新)"
                    await self.send_text(progress_msg)

            # 发送检查结果摘要
            if update_available:
                result_message = f"\n🎯 **检查完成**\n发现 {len(update_available)} 个可更新插件\n\n"
                result_message += f"💡 使用 `/pm update ALL` 更新所有插件\n"
                result_message += f"🔧 或使用 `/pm update <插件名>` 更新指定插件"
            else:
                result_message = "\n🎯 **检查完成**\n🟢 所有插件均为最新版本"

            await self.send_text(result_message)
            return True, f"检查完成，发现 {len(update_available)} 个可更新插件", True

        except Exception as e:
            error_msg = f"❌ 检查更新时出错: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, True

    async def _update_plugin(self, plugin_name: str) -> Tuple[bool, Optional[str], bool]:
        """更新指定插件或所有插件"""
        try:
            if not plugin_name:
                await self.send_text("❌ 请指定要更新的插件名或使用 ALL 更新所有插件。")
                return False, "未指定插件名", True

            plugins_dir = self._get_plugins_directory()
            plugins = self._scan_plugins(plugins_dir)
            
            if plugin_name.upper() == "ALL":
                # 更新所有需要更新的插件
                plugins_to_update = []
                for plugin in plugins:
                    remote_version = await self._get_remote_version(plugin['repository_url'])
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
                for plugin in plugins_to_update:
                    try:
                        if await self._perform_plugin_update(plugin):
                            success_count += 1
                            progress_msg = f"✅ 已更新: {plugin['name']} → v{plugin['remote_version']}"
                            await self.send_text(progress_msg)
                        else:
                            error_msg = f"❌ 更新失败: {plugin['name']}"
                            await self.send_text(error_msg)
                    except Exception as e:
                        error_msg = f"❌ 更新 {plugin['name']} 时出错: {str(e)}"
                        await self.send_text(error_msg)

                final_msg = f"🎉 **更新完成**\n成功更新 {success_count}/{len(plugins_to_update)} 个插件"
                await self.send_text(final_msg)
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
                remote_version = await self._get_remote_version(target_plugin['repository_url'])
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
            remote_version = await self._get_remote_version(target_plugin['repository_url'])
            if remote_version:
                status = "🟢 最新" if remote_version == target_plugin['local_version'] else "🟡 可更新"
                info_message += f"🔸 **远程版本**: v{remote_version}\n"
                info_message += f"🔸 **状态**: {status}\n"
            else:
                info_message += "🔸 **状态**: 🔴 无法检查更新\n"

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

    async def _get_remote_version(self, repository_url: str) -> Optional[str]:
        """从GitHub仓库获取最新版本号"""
        try:
            if not repository_url or "github.com" not in repository_url:
                return None

            # 构建GitHub API URL
            repo_path = repository_url.replace("https://github.com/", "").strip("/")
            api_url = f"https://api.github.com/repos/{repo_path}/contents/_manifest.json"

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'content' in data:
                            # 解码base64内容
                            import base64
                            content = base64.b64decode(data['content']).decode('utf-8')
                            manifest_data = json.loads(content)
                            return manifest_data.get('version', None)
            
            return None
        except Exception as e:
            print(f"获取远程版本失败 {repository_url}: {e}")
            return None

    async def _perform_plugin_update(self, plugin: Dict[str, Any]) -> bool:
        """执行插件更新：从GitHub仓库下载并覆盖文件"""
        try:
            repository_url = plugin['repository_url']
            if not repository_url or "github.com" not in repository_url:
                return False

            repo_path = repository_url.replace("https://github.com/", "").strip("/")
            api_url = f"https://api.github.com/repos/{repo_path}/contents/"

            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 获取仓库文件列表
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url) as response:
                        if response.status != 200:
                            return False
                        
                        files_data = await response.json()
                        
                        # 下载所有文件
                        for file_info in files_data:
                            if file_info['type'] == 'file':
                                file_url = file_info['download_url']
                                file_path = temp_path / file_info['name']
                                
                                async with session.get(file_url) as file_response:
                                    if file_response.status == 200:
                                        content = await file_response.read()
                                        with open(file_path, 'wb') as f:
                                            f.write(content)

                # 备份原插件目录
                plugin_dir = plugin['directory_path']
                backup_dir = plugin_dir.with_suffix('.backup')
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                shutil.copytree(plugin_dir, backup_dir)

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
                    return False

        except Exception as e:
            print(f"执行插件更新失败 {plugin['name']}: {e}")
            return False

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
        "admin": "管理员配置"
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
                default="1.0.0",
                description="配置文件版本"
            ),
        },
        "admin": {
            "qq_list": ConfigField(
                type=list,
                default=[],
                description="管理员QQ号列表"
            )
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """注册插件组件"""
        return [
            (PluginManagerCommand.get_command_info(), PluginManagerCommand),
        ]