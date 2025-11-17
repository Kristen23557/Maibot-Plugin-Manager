# plugins/Plugin_manager/plugin.py  # 注: 原文件路径说明 / EN: original file path / JP: 元ファイルパス
import os  # 注: 操作系统交互模块 / EN: OS interaction module / JP: OS操作モジュール
import json  # 注: JSON 编码/解码 / EN: JSON encode/decode / JP: JSON エンコード/デコード
import aiohttp  # 注: 异步 HTTP 客户端 / EN: async HTTP client / JP: 非同期HTTPクライアント
import asyncio  # 注: 异步 IO 支持 / EN: async IO support / JP: 非同期IOサポート
import shutil  # 注: 高级文件操作（复制/删除） / EN: high-level file operations / JP: ファイル操作
import tempfile  # 注: 临时文件/目录支持 / EN: temporary files/dirs support / JP: 一時ファイルサポート
import ssl  # 注: SSL/TLS 支持 / EN: SSL/TLS support / JP: SSL/TLS サポート
import time  # 注: 时间相关功能 / EN: time utilities / JP: 時間ユーティリティ
import base64  # 注: Base64 编码/解码 / EN: Base64 encode/decode / JP: Base64 エンコード/デコード
from typing import List, Tuple, Type, Optional, Dict, Any  # 注: 类型注解 / EN: typing annotations / JP: 型注釈
from pathlib import Path  # 注: Path 对象用于路径操作 / EN: Path object for path ops / JP: Path オブジェクト

from src.plugin_system import (  # 注: 从宿主插件系统导入接口 / EN: import plugin system interfaces / JP: プラグインシステムをインポート
    BasePlugin,  # 注: 插件基类 / EN: base plugin class / JP: プラグイン基底クラス
    register_plugin,  # 注: 注册插件装饰器 / EN: plugin registration decorator / JP: プラグイン登録デコレータ
    BaseCommand,  # 注: 命令基类 / EN: base command class / JP: コマンド基底クラス
    ComponentInfo,  # 注: 组件信息类型 / EN: component info type / JP: コンポーネント情報型
    ConfigField  # 注: 配置字段描述 / EN: configuration field descriptor / JP: 設定フィールド
)
from src.plugin_system.apis import chat_api, person_api  # 注: 导入对外 API（聊天/人） / EN: import external apis (chat/person) / JP: APIをインポート

# 插件管理器版本 / EN: plugin manager version / JP: プラグインマネージャーのバージョン
PLUGIN_MANAGER_VERSION = "1.1.2"  # 注: 版本号常量 / EN: version constant / JP: バージョン定数

class PluginManagerCommand(BaseCommand):  # 注: 定义插件管理命令类 / EN: plugin manager command class / JP: プラグイン管理コマンドクラス
    """插件管理器命令 - 管理所有插件的更新和状态"""  # 注: 类说明 / EN: class docstring / JP: クラス説明
    
    command_name = "PluginManagerCommand"  # 注: 命令名 / EN: command name / JP: コマンド名
    command_description = "插件管理器，用于管理插件的更新和状态检查"  # 注: 命令描述 / EN: command description / JP: コマンド説明
    command_pattern = r"^/pm\s+(?P<action>\S+)(?:\s+(?P<plugin_name>.+))?$"  # 注: 命令匹配正则 / EN: regex for command pattern / JP: コマンド正規表現
    command_help = (  # 注: 帮助文本 / EN: help text / JP: ヘルプテキスト
        "📦 **插件管理器帮助**\n\n"  # 注: 多语言帮助内容片段 / EN: help content piece / JP: ヘルプ内容
        "🔧 **可用命令**\n"  # 注: 帮助行 / EN: help line / JP: ヘルプ行
        "🔸 `/pm list` - 列出所有已安装插件\n"  # 注: 列表命令说明 / EN: list command / JP: リストコマンド
        "🔸 `/pm check` - 检查所有插件更新\n"  # 注: 检查命令 / EN: check updates / JP: 更新チェック
        "🔸 `/pm update <插件名>` - 更新指定插件\n"  # 注: 更新单个插件 / EN: update a plugin / JP: プラグイン更新
        "🔸 `/pm update ALL` - 更新所有需要更新的插件\n"  # 注: 更新全部 / EN: update all / JP: すべて更新
        "🔸 `/pm info <插件名>` - 查看插件详细信息\n"  # 注: 查看信息 / EN: show plugin info / JP: 情報表示
        "🔸 `/pm settings` - 管理插件自动更新设置\n"  # 注: 设置命令 / EN: manage settings / JP: 設定管理
        "🔸 `/pm github` - 查看GitHub配置状态\n"  # 注: GitHub 状态 / EN: github status / JP: GitHub 状態
        "🔸 `/pm help` - 显示此帮助信息\n\n"  # 注: 帮助命令 / EN: help command / JP: ヘルプコマンド
        "💡 **提示**\n"  # 注: 提示区 / EN: tips section / JP: ヒント
        "• 默认忽略 'Hello World 示例插件'\n"  # 注: 忽略示例插件 / EN: ignore example plugin / JP: サンプル無視
        "• 只有管理员可以使用插件管理器\n"  # 注: 权限提示 / EN: admin only / JP: 管理者のみ
        "• 如需更好的GitHub API体验，请在配置中添加GitHub Token\n"  # 注: Token 提示 / EN: token recommended / JP: トークン推奨
        "• 尽管此插件带有自动更新功能，但我们仍然强烈建议您在更新或检查插件更新后手动检查插件文件!!!"  # 注: 警告建议 / EN: manual check advised / JP: 手動チェック推奨
    )
    intercept_message = True  # 注: 拦截消息标志 / EN: intercept messages flag / JP: メッセージインターセプト

    def __init__(self, *args, **kwargs):  # 注: 初始化方法 / EN: initializer / JP: 初期化
        super().__init__(*args, **kwargs)  # 注: 调用父类构造 / EN: call parent ctor / JP: 親クラス初期化
        self._last_api_call = 0  # 注: 上次 API 调用时间 / EN: last API call timestamp / JP: 最終API呼び出し時刻
        self._min_api_interval = 2.0  # 最少2秒间隔避免频率限制 / EN: min interval seconds / JP: 最小間隔(秒)

    async def execute(self) -> Tuple[bool, Optional[str], bool]:  # 注: 命令执行入口 / EN: command entrypoint / JP: コマンド実行入口
        """执行插件管理器命令"""  # 注: 方法说明 / EN: method docstring / JP: メソッド説明
        try:  # 注: 主 try 块 / EN: main try block / JP: メインtryブロック
            # 首先检查管理员权限 / EN: check admin permission first / JP: まず管理者権限を確認
            if not await self._check_admin_permission():  # 注: 异步权限检查 / EN: async permission check / JP: 非同期権限チェック
                try:  # 注: 发送权限不足消息 / EN: send permission denied message / JP: 権限不足メッセージ送信
                    await self.send_text("❌ 权限不足，只有管理员可以使用插件管理器。")  # 注: 发送文本 / EN: send text / JP: テキスト送信
                except Exception as e:  # 注: 捕获发送异常 / EN: catch send exception / JP: 送信例外捕捉
                    print(f"发送权限错误消息失败: {e}")  # 注: 打印错误 / EN: print error / JP: エラー出力
                return False, "权限不足", True  # 注: 返回权限错误 / EN: return permission error / JP: 権限エラー返却

            # 安全获取匹配的参数 / EN: safely get matched params / JP: マッチパラメータ取得
            matched_groups = self.matched_groups or {}  # 注: 从匹配获取组 / EN: get matched groups / JP: マッチグループ
            action = str(matched_groups.get("action", "")).strip().lower() if matched_groups.get("action") else ""  # 注: 规范化动作 / EN: normalize action / JP: アクション正規化
            plugin_name = str(matched_groups.get("plugin_name", "")).strip() if matched_groups.get("plugin_name") else ""  # 注: 规范化插件名 / EN: normalize plugin name / JP: プラグイン名正規化

            # 如果没有action，显示帮助 / EN: show help if no action / JP: アクション無ければヘルプ表示
            if not action:  # 注: 无动作分支 / EN: no-action branch / JP: アクションなし
                try:  # 注: 发送帮助文本 / EN: send help text / JP: ヘルプ送信
                    await self.send_text(self.command_help)  # 注: 调用发送 / EN: call send / JP: 送信呼び出し
                except Exception as e:  # 注: 捕获发送异常 / EN: catch send exception / JP: 送信例外
                    print(f"发送帮助信息失败: {e}")  # 注: 打印异常 / EN: print exception / JP: 例外出力
                return True, "已发送帮助信息", True  # 注: 返回成功 / EN: return success / JP: 成功返却

            # 处理不同动作 / EN: handle different actions / JP: アクション処理
            if action == "list":  # 注: 列表动作 / EN: list action / JP: リストアクション
                return await self._list_plugins()  # 注: 列出插件 / EN: list plugins / JP: プラグイン一覧
            elif action == "check":  # 注: 检查动作 / EN: check action / JP: チェックアクション
                return await self._check_updates()  # 注: 检查更新 / EN: check updates / JP: 更新チェック
            elif action == "update":  # 注: 更新动作 / EN: update action / JP: 更新アクション
                return await self._update_plugin(plugin_name)  # 注: 更新插件 / EN: update plugin / JP: プラグイン更新
            elif action == "info":  # 注: 信息动作 / EN: info action / JP: 情報アクション
                return await self._plugin_info(plugin_name)  # 注: 显示信息 / EN: show info / JP: 情報表示
            elif action == "settings":  # 注: 设置动作 / EN: settings action / JP: 設定アクション
                return await self._manage_settings(plugin_name)  # 注: 管理设置 / EN: manage settings / JP: 設定管理
            elif action == "github":  # 注: GitHub 状态动作 / EN: github action / JP: GitHubアクション
                return await self._show_github_status()  # 注: 显示 GitHub 状态 / EN: show github status / JP: GitHub状態表示
            elif action == "help":  # 注: 帮助动作 / EN: help action / JP: ヘルプアクション
                try:  # 注: 发送帮助 / EN: send help / JP: ヘルプ送信
                    await self.send_text(self.command_help)  # 注: 发送帮助文本 / EN: send help text / JP: ヘルプテキスト送信
                except Exception as e:  # 注: 捕获异常 / EN: catch exception / JP: 例外捕捉
                    print(f"发送帮助信息失败: {e}")  # 注: 打印异常 / EN: print exception / JP: 例外出力
                return True, "已发送帮助信息", True  # 注: 返回成功 / EN: return success / JP: 成功返却
            else:  # 注: 未知命令 / EN: unknown command / JP: 不明コマンド
                try:  # 注: 发送未知命令提示 / EN: send unknown command message / JP: 不明コマンドメッセージ
                    await self.send_text(f"❌ 未知命令: {action}\n请使用 `/pm help` 查看可用命令。")  # 注: 发送文本 / EN: send text / JP: テキスト送信
                except Exception as e:  # 注: 捕获发送异常 / EN: catch send exception / JP: 送信例外
                    print(f"发送未知命令错误失败: {e}")  # 注: 打印错误 / EN: print error / JP: エラー出力
                return False, f"未知命令: {action}", True  # 注: 返回错误 / EN: return error / JP: エラー返却

        except Exception as e:  # 注: 总体异常捕获 / EN: catch-all exception / JP: 全体例外捕捉
            error_msg = f"❌ 命令执行出错: {str(e)}"  # 注: 构建错误消息 / EN: build error msg / JP: エラーメッセージ作成
            try:  # 注: 尝试发送错误消息 / EN: try to send error msg / JP: エラーメッセージ送信試行
                await self.send_text(error_msg)  # 注: 发送错误 / EN: send error / JP: エラー送信
            except Exception as send_e:  # 注: 发送失败处理 / EN: handle send failure / JP: 送信失敗処理
                print(f"发送错误消息也失败了: {send_e}")  # 注: 打印发送失败 / EN: print send failure / JP: 送信失敗出力
            return False, error_msg, True  # 注: 返回错误 / EN: return error / JP: エラー返却

    async def _show_github_status(self) -> Tuple[bool, Optional[str], bool]:  # 注: 显示 GitHub 配置状态 / EN: show github config status / JP: GitHub設定表示
        """显示GitHub配置状态"""  # 注: 方法说明 / EN: docstring / JP: メソッド説明
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            github_config = self._get_github_config()  # 注: 获取配置 / EN: get config / JP: 設定取得
            has_token = bool(github_config.get('token'))  # 注: 是否有 token / EN: has token / JP: トークン有無
            has_username = bool(github_config.get('username'))  # 注: 是否有用户名 / EN: has username / JP: ユーザー名有無
            
            status_message = "🔗 **GitHub配置状态**\n\n"  # 注: 状态消息初始 / EN: status message start / JP: 状態メッセージ
            
            if has_token and has_username:  # 注: 两者都存在 / EN: both present / JP: 両方存在
                status_message += "✅ **认证状态**: 已配置GitHub账号\n"  # 注: 已配置 / EN: configured / JP: 設定済み
                status_message += f"👤 **用户名**: {github_config['username']}\n"  # 注: 显示用户名 / EN: show username / JP: ユーザー名表示
                status_message += "🔑 **Token状态**: 已配置\n"  # 注: Token 已配置 / EN: token set / JP: トークン設定済み
                status_message += "🚀 **API限制**: 大幅提升 (5000次/小时)\n"  # 注: 速率提示 / EN: rate limit boost / JP: レート制限
            elif has_token:  # 注: 只有 token / EN: only token / JP: トークンのみ
                status_message += "⚠️ **认证状态**: 部分配置\n"  # 注: 部分配置 / EN: partial configured / JP: 部分設定
                status_message += "🔑 **Token状态**: 已配置\n"  # 注: token 已配置 / EN: token set / JP: トークン設定済み
                status_message += "👤 **用户名**: 未配置\n"  # 注: 用户名未配置 / EN: username not set / JP: ユーザー名未設定
                status_message += "🚀 **API限制**: 提升 (5000次/小时)\n"  # 注: 速率提升 / EN: rate boost / JP: レート上昇
            else:  # 注: 未配置 / EN: not configured / JP: 未設定
                status_message += "❌ **认证状态**: 未配置GitHub账号\n"  # 注: 未配置 / EN: not configured / JP: 未設定
                status_message += "🔑 **Token状态**: 未配置\n"  # 注: token 未配置 / EN: token not set / JP: トークン未設定
                status_message += "👤 **用户名**: 未配置\n"  # 注: 用户名未配置 / EN: username not set / JP: ユーザー名未設定
                status_message += "🐌 **API限制**: 严格 (60次/小时)\n"  # 注: 限制提示 / EN: strict rate limit / JP: レート制限厳しい
            
            status_message += "\n💡 **配置说明**\n"  # 注: 配置说明标题 / EN: config notes / JP: 設定説明
            status_message += "• 在 `config.toml` 的 `[github]` 节中配置\n"  # 注: 指示配置位置 / EN: where to configure / JP: 設定場所
            status_message += "• `username`: 你的GitHub用户名\n"  # 注: 字段说明 / EN: field说明 / JP: フィールド説明
            status_message += "• `token`: GitHub Personal Access Token\n"  # 注: token 说明 / EN: token说明 / JP: トークン説明
            status_message += "• 获取Token: https://github.com/settings/tokens\n"  # 注: 获取 token 链接 / EN: token link / JP: トークン取得リンク
            status_message += "• Token权限: 只需要 `public_repo` 权限\n"  # 注: 权限说明 / EN: scope recommendation / JP: 権限説明
            
            await self.send_text(status_message)  # 注: 发送状态消息 / EN: send status / JP: 状態送信
            return True, "已显示GitHub状态", True  # 注: 返回成功 / EN: return success / JP: 成功返却
            
        except Exception as e:  # 注: 捕获异常 / EN: catch exception / JP: 例外捕捉
            error_msg = f"❌ 获取GitHub状态时出错: {str(e)}"  # 注: 构建错误消息 / EN: build error msg / JP: エラーメッセージ
            await self.send_text(error_msg)  # 注: 发送错误消息 / EN: send error msg / JP: エラー送信
            return False, error_msg, True  # 注: 返回错误 / EN: return error / JP: エラー返却

    def _get_github_config(self) -> Dict[str, str]:  # 注: 获取 GitHub 配置 / EN: get github config / JP: GitHub設定取得
        """获取GitHub配置"""  # 注: docstring / EN: docstring / JP: ドックストリング
        return {  # 注: 返回配置字典 / EN: return config dict / JP: 設定辞書返却
            'username': self.get_config("github.username", "").strip(),  # 注: 获取用户名 / EN: get username / JP: ユーザー名取得
            'token': self.get_config("github.token", "").strip()  # 注: 获取 token / EN: get token / JP: トークン取得
        }

    def _get_github_headers(self) -> Dict[str, str]:  # 注: 构建 GitHub HTTP 头 / EN: build headers / JP: ヘッダ構築
        """获取GitHub API请求头"""  # 注: docstring / EN: docstring / JP: ドックストリング
        github_config = self._get_github_config()  # 注: 读取配置 / EN: read config / JP: 設定読み取り
        headers = {  # 注: 默认头部 / EN: default headers / JP: デフォルトヘッダ
            'User-Agent': 'MaiBot-Plugin-Manager/1.1.2',  # 注: UA 标识 / EN: user agent / JP: ユーザーエージェント
            'Accept': 'application/vnd.github.v3+json'  # 注: 接受类型 / EN: accept header / JP: Acceptヘッダ
        }
        
        # 如果有token，使用token认证 / EN: use token if available / JP: トークンがあれば使用
        if github_config.get('token'):  # 注: 检查 token / EN: check token / JP: トークンチェック
            headers['Authorization'] = f"token {github_config['token']}"  # 注: Authorization 头 / EN: auth header / JP: 認証ヘッダ
            
        return headers  # 注: 返回头部 / EN: return headers / JP: ヘッダ返却

    async def _check_admin_permission(self) -> bool:  # 注: 检查管理员权限 / EN: check admin permission / JP: 管理者権限チェック
        """检查用户是否为管理员 - 使用聊天API正确获取用户信息"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            # 获取配置的管理员QQ号列表 / EN: get admin QQ list / JP: 管理者QQリスト取得
            admin_qq_list = self.get_config("admin.qq_list", [])  # 注: 读取配置 / EN: read config / JP: 設定読み取り
            if not admin_qq_list:  # 注: 列表为空处理 / EN: empty list handling / JP: 空リスト処理
                print("管理员QQ列表为空，拒绝访问")  # 注: 打印警告 / EN: print warning / JP: 警告出力
                return False  # 注: 拒绝访问 / EN: deny access / JP: アクセス拒否

            # 获取当前聊天流信息 / EN: get current chat stream / JP: 現在のチャットストリーム取得
            message_obj = getattr(self, 'message', None)  # 注: 获取 message 对象 / EN: get message object / JP: message オブジェクト取得
            if not message_obj:  # 注: 无 message 时处理 / EN: handle missing message / JP: message無い場合
                print("无法获取message对象")  # 注: 打印 / EN: print / JP: 出力
                return False  # 注: 返回 False / EN: return False / JP: False返却

            # 获取聊天流 / EN: get chat stream / JP: チャットストリーム取得
            chat_stream = getattr(message_obj, 'chat_stream', None)  # 注: 读取 chat_stream / EN: read chat_stream / JP: chat_stream読み取り
            if not chat_stream:  # 注: 处理缺失 / EN: handle missing / JP: 欠如処理
                print("无法获取chat_stream")  # 注: 打印 / EN: print / JP: 出力
                return False  # 注: 返回 False / EN: return False / JP: False返却

            # 使用聊天API获取流信息 / EN: get stream info via chat API / JP: chat APIでストリーム情報取得
            stream_info = chat_api.get_stream_info(chat_stream)  # 注: 获取流信息 / EN: get stream info / JP: ストリーム情報取得
            print(f"聊天流信息: {stream_info}")  # 注: 打印流信息 / EN: print stream info / JP: ストリーム情報出力

            # 根据聊天流类型获取用户ID / EN: determine user id by stream type / JP: ストリーム種別でユーザーID取得
            user_id = None  # 注: 初始化 user_id / EN: init user_id / JP: user_id初期化
            stream_type = chat_api.get_stream_type(chat_stream)  # 注: 获取流类型 / EN: get stream type / JP: ストリーム種別取得
            
            if stream_type == "private":  # 注: 私聊情况 / EN: private chat / JP: プライベートチャット
                # 私聊：直接从流信息获取用户ID / EN: private chat get user id / JP: プライベートでID取得
                user_id = stream_info.get('user_id')  # 注: 从流信息获取 / EN: get from stream info / JP: ストリーム情報から取得
                print(f"私聊用户ID: {user_id}")  # 注: 打印用户ID / EN: print user id / JP: ユーザーID出力
            elif stream_type == "group":  # 注: 群聊情况 / EN: group chat / JP: グループチャット
                # 群聊：需要从消息发送者获取用户ID / EN: group chat get sender id / JP: 送信者からID取得
                sender_info = getattr(message_obj, 'sender_info', None)  # 注: 获取发送者信息 / EN: get sender info / JP: 送信者情報取得
                if sender_info:  # 注: 存在发送者信息 / EN: if sender info present / JP: 送信者情報あり
                    user_id = getattr(sender_info, 'user_id', None)  # 注: 读取 user_id / EN: read user_id / JP: user_id読み取り
                    print(f"群聊发送者用户ID: {user_id}")  # 注: 打印 / EN: print / JP: 出力
            else:  # 注: 未知流类型 / EN: unknown stream type / JP: 未知ストリーム種別
                print(f"未知聊天流类型: {stream_type}")  # 注: 打印 / EN: print / JP: 出力
                return False  # 注: 返回 False / EN: return False / JP: False返却

            if not user_id:  # 注: 无 user_id 处理 / EN: handle missing user id / JP: user_id無い場合
                print("无法获取用户ID")  # 注: 打印 / EN: print / JP: 出力
                return False  # 注: 返回 False / EN: return False / JP: False返却

            # 转换为字符串比较 / EN: normalize to string for comparison / JP: 文字列に変換して比較
            user_id_str = str(user_id).strip()  # 注: 去空白 / EN: strip whitespace / JP: 空白削除
            admin_qq_str_list = [str(qq).strip() for qq in admin_qq_list]  # 注: 规范化管理员列表 / EN: normalize admin list / JP: 管理者リスト正規化
            
            print(f"权限检查 - 用户ID: '{user_id_str}', 管理员列表: {admin_qq_str_list}")  # 注: 打印检查详情 / EN: print check details / JP: チェック詳細出力
            
            # 精确匹配检查 / EN: exact match check / JP: 厳密一致チェック
            is_admin = user_id_str in admin_qq_str_list  # 注: 是否在管理员列表中 / EN: check membership / JP: メンバー判定
            print(f"权限检查结果: {is_admin}")  # 注: 打印结果 / EN: print result / JP: 結果出力
            
            return is_admin  # 注: 返回布尔值 / EN: return boolean / JP: ブール返却

        except Exception as e:  # 注: 异常处理 / EN: exception handling / JP: 例外処理
            print(f"检查管理员权限时出错: {e}")  # 注: 打印异常 / EN: print exception / JP: 例外出力
            import traceback  # 注: 导入 traceback / EN: import traceback / JP: tracebackインポート
            traceback.print_exc()  # 注: 打印堆栈 / EN: print stack / JP: スタック出力
            return False  # 注: 返回 False / EN: return False / JP: False返却

    async def _list_plugins(self) -> Tuple[bool, Optional[str], bool]:  # 注: 列出所有插件 / EN: list all plugins / JP: すべてのプラグインを列挙
        """列出所有已安装插件"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            plugins_dir = self._get_plugins_directory()  # 注: 获取插件目录 / EN: get plugins dir / JP: プラグインディレクトリ取得
            plugins = self._scan_plugins(plugins_dir)  # 注: 扫描插件 / EN: scan plugins / JP: プラグインスキャン
            
            if not plugins:  # 注: 无插件时 / EN: no plugins / JP: プラグインなし
                await self.send_text("📦 未找到任何有效插件。")  # 注: 发送提示 / EN: send notice / JP: メッセージ送信
                return True, "未找到插件", True  # 注: 返回结果 / EN: return result / JP: 結果返却

            # 构建插件列表消息 / EN: build list message / JP: リストメッセージ構築
            message = "📦 **已安装插件列表**\n\n"  # 注: 消息起始 / EN: message start / JP: メッセージ開始
            for plugin in plugins:  # 注: 遍历插件 / EN: iterate plugins / JP: プラグイン反復
                status = "🟢 最新" if not plugin.get("needs_update", False) else "🟡 可更新"  # 注: 状态文字 / EN: status text / JP: ステータステキスト
                auto_update_status = "✅" if self._get_plugin_auto_update_setting(plugin['name']) else "❌"  # 注: 自动更新状态 / EN: auto-update status / JP: 自動更新ステータス
                message += f"• {plugin['name']} v{plugin['local_version']} {status} {auto_update_status}\n"  # 注: 拼接行 / EN: append line / JP: 行追加

            message += f"\n💡 共找到 {len(plugins)} 个插件"  # 注: 插件计数 / EN: count plugins / JP: プラグイン数
            message += "\n🔧 使用 `/pm check` 检查更新，`/pm update <插件名>` 更新插件"  # 注: 操作提示 / EN: usage hint / JP: 操作ヒント
            message += "\n⚙️  ✅ = 自动更新开启，❌ = 自动更新关闭"  # 注: 图例 / EN: legend / JP: 凡例

            await self.send_text(message)  # 注: 发送消息 / EN: send message / JP: 送信
            return True, f"已列出 {len(plugins)} 个插件", True  # 注: 返回成功 / EN: return success / JP: 成功返却

        except Exception as e:  # 注: 异常捕获 / EN: exception catch / JP: 例外捕捉
            error_msg = f"❌ 列出插件时出错: {str(e)}"  # 注: 构建错误消息 / EN: build error msg / JP: エラーメッセージ作成
            await self.send_text(error_msg)  # 注: 发送错误 / EN: send error / JP: エラー送信
            return False, error_msg, True  # 注: 返回错误 / EN: return error / JP: エラー返却

    async def _check_updates(self) -> Tuple[bool, Optional[str], bool]:  # 注: 检查所有插件更新 / EN: check all plugins updates / JP: すべての更新チェック
        """检查所有插件更新 - 统一发送结果"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            plugins_dir = self._get_plugins_directory()  # 注: 获取插件目录 / EN: get plugins dir / JP: ディレクトリ取得
            plugins = self._scan_plugins(plugins_dir)  # 注: 扫描插件 / EN: scan plugins / JP: スキャン
            
            if not plugins:  # 注: 无插件处理 / EN: no plugins / JP: プラグインなし
                await self.send_text("📦 未找到任何有效插件。")  # 注: 发送消息 / EN: send message / JP: 送信
                return True, "未找到插件", True  # 注: 返回 / EN: return / JP: 返却

            # 发送检查开始消息 / EN: send start message / JP: 開始メッセージ送信
            checking_message = f"🔄 **正在检查 {len(plugins)} 个插件的更新...**\n请稍候..."  # 注: 检查消息 / EN: checking msg / JP: チェックメッセージ
            await self.send_text(checking_message)  # 注: 发送 / EN: send / JP: 送信

            # 串行检查所有插件的更新（避免GitHub API限制） / EN: serial check to avoid rate limits / JP: 逐次チェック
            update_available = []  # 注: 可更新列表 / EN: update available list / JP: 更新可能リスト
            check_results = []  # 注: 检查结果列表 / EN: check results list / JP: チェック結果リスト
            
            # 创建 SSL 上下文以禁用证书验证 / EN: create SSL context (no-verify) / JP: SSLコンテキスト作成(検証無効)
            ssl_context = ssl.create_default_context()  # 注: 默认 context / EN: default context / JP: デフォルト
            ssl_context.check_hostname = False  # 注: 关闭主机名检查 / EN: disable hostname check / JP: ホスト名検証無効
            ssl_context.verify_mode = ssl.CERT_NONE  # 注: 不验证证书 / EN: do not verify certs / JP: 証明書検証無効
            
            github_config = self._get_github_config()  # 注: 读取 GitHub 配置 / EN: read github config / JP: GitHub設定読み取り
            auth_status = "🔑 使用认证" if github_config.get('token') else "⚠️ 未认证"  # 注: 认证状态文字 / EN: auth status text / JP: 認証状態
            
            # 串行检查所有插件，避免GitHub API限制 / EN: serial check to avoid API limits / JP: 逐次チェック
            for plugin in plugins:  # 注: 遍历插件 / EN: iterate plugins / JP: プラグイン繰り返し
                try:  # 注: 内部 try / EN: inner try / JP: 内部try
                    # 添加延迟避免API限制 / EN: rate limit delay / JP: レート制限遅延
                    await self._rate_limit_delay()  # 注: 延迟调用 / EN: wait to respect rate limit / JP: 待機
                    
                    # 只使用 repository_url 字段 / EN: only use repository_url / JP: repository_urlのみ使用
                    repository_url = plugin.get('repository_url', '')  # 注: 获取仓库地址 / EN: get repo url / JP: リポジトリURL取得
                    if not repository_url:  # 注: 无仓库地址处理 / EN: handle missing repo url / JP: URL欠如処理
                        check_results.append(f"🔴 {plugin['name']}: v{plugin['local_version']} (无仓库地址)")  # 注: 添加结果 / EN: append result / JP: 結果追加
                        continue  # 注: 跳过 / EN: skip / JP: スキップ
                    
                    remote_version = await self._get_remote_version(repository_url, ssl_context)  # 注: 获取远程版本 / EN: get remote version / JP: リモートバージョン取得
                    if remote_version and remote_version != plugin['local_version']:  # 注: 版本比较 / EN: compare versions / JP: バージョン比較
                        plugin['remote_version'] = remote_version  # 注: 记录远程版本 / EN: store remote version / JP: リモート版記録
                        plugin['needs_update'] = True  # 注: 标记需要更新 / EN: mark needs update / JP: 更新必要フラグ
                        update_available.append(plugin)  # 注: 添加到更新列表 / EN: add to update list / JP: 更新リスト追加
                        check_results.append(f"🟡 {plugin['name']}: v{plugin['local_version']} → v{remote_version}")  # 注: 结果行 / EN: result line / JP: 結果行
                    else:  # 注: 否则为最新 / EN: else up-to-date / JP: 最新
                        check_results.append(f"🟢 {plugin['name']}: v{plugin['local_version']} (最新)")  # 注: 结果行 / EN: result line / JP: 結果行
                except Exception as e:  # 注: 单个插件检查异常 / EN: per-plugin check exception / JP: プラグインチェック例外
                    check_results.append(f"🔴 {plugin['name']}: v{plugin['local_version']} (检查失败)")  # 注: 记录失败 / EN: record failure / JP: 失敗記録
                    print(f"检查插件 {plugin['name']} 更新失败: {e}")  # 注: 打印错误 / EN: print error / JP: エラー出力

            # 构建统一的结果消息 / EN: build summary message / JP: 結果メッセージ構築
            result_message = "📊 **插件更新检查结果**\n\n"  # 注: 消息头 / EN: header / JP: ヘッダ
            
            # 添加有更新的插件 / EN: add update-available list / JP: 更新可能プラグイン追加
            if update_available:  # 注: 如果有更新 / EN: if updates exist / JP: 更新あり
                result_message += "🟡 **可更新插件**\n"  # 注: 小节标题 / EN: subsection title / JP: 小見出し
                for plugin in update_available:  # 注: 遍历可更新插件 / EN: iterate update list / JP: 更新リスト反復
                    result_message += f"• {plugin['name']}: v{plugin['local_version']} → v{plugin['remote_version']}\n"  # 注: 列表行 / EN: list line / JP: 行
                result_message += "\n"  # 注: 换行 / EN: newline / JP: 改行
            
            # 添加所有插件状态 / EN: add all plugin statuses / JP: 全プラグイン状態追加
            result_message += "📋 **所有插件状态**\n"  # 注: 小节标题 / EN: section title / JP: セクション
            for result in check_results:  # 注: 遍历结果 / EN: iterate results / JP: 結果反復
                result_message += f"{result}\n"  # 注: 添加每行 / EN: append each line / JP: 行追加
            
            # 添加操作提示 / EN: add action hints / JP: 操作ヒント追加
            result_message += f"\n🎯 **检查完成**\n"  # 注: 完成消息 / EN: completion msg / JP: 完了メッセージ
            if update_available:  # 注: 如果有更新 / EN: if updates exist / JP: 更新あり
                result_message += f"发现 {len(update_available)} 个可更新插件\n\n"  # 注: 发现数量 / EN: found count / JP: 発見数

                result_message += f"💡 使用 `/pm update ALL` 更新所有插件\n"  # 注: 提示命令 / EN: hint command / JP: コマンドヒント
                result_message += f"🔧 或使用 `/pm update <插件名>` 更新指定插件"  # 注: 另一个提示 / EN: another hint / JP: 追加ヒント
            else:  # 注: 无更新 / EN: no updates / JP: 更新無し
                result_message += "🟢 所有插件均为最新版本"  # 注: 最新提示 / EN: up-to-date msg / JP: 最新メッセージ

            await self.send_text(result_message)  # 注: 发送总结 / EN: send summary / JP: まとめ送信
            return True, f"检查完成，发现 {len(update_available)} 个可更新插件", True  # 注: 返回结果 / EN: return result / JP: 結果返却

        except Exception as e:  # 注: 异常处理 / EN: exception handling / JP: 例外処理
            error_msg = f"❌ 检查更新时出错: {str(e)}"  # 注: 构建错误消息 / EN: build error msg / JP: エラーメッセージ
            await self.send_text(error_msg)  # 注: 发送错误 / EN: send error / JP: 送信
            return False, error_msg, True  # 注: 返回错误 / EN: return error / JP: エラー返却

    async def _rate_limit_delay(self):  # 注: API 调用节流延迟 / EN: rate limit delay / JP: レート制限遅延
        """API调用频率限制"""  # 注: docstring / EN: docstring / JP: ドックストリング
        current_time = time.time()  # 注: 当前时间 / EN: current time / JP: 現在時刻
        time_since_last_call = current_time - self._last_api_call  # 注: 距离上次调用 / EN: since last call / JP: 前回からの時間
        if time_since_last_call < self._min_api_interval:  # 注: 如果太快则等待 / EN: wait if too soon / JP: 速すぎる場合待機
            await asyncio.sleep(self._min_api_interval - time_since_last_call)  # 注: 睡眠 / EN: sleep / JP: スリープ
        self._last_api_call = time.time()  # 注: 更新最后调用时间 / EN: update timestamp / JP: 最終時刻更新

    async def _update_plugin(self, plugin_name: str) -> Tuple[bool, Optional[str], bool]:  # 注: 更新插件 / EN: update plugin / JP: プラグイン更新
        """更新指定插件或所有插件"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            if not plugin_name:  # 注: 未指定插件名错误 / EN: missing plugin name / JP: プラグイン名無し
                await self.send_text("❌ 请指定要更新的插件名或使用 ALL 更新所有插件。")  # 注: 发送提示 / EN: send prompt / JP: メッセージ送信
                return False, "未指定插件名", True  # 注: 返回错误 / EN: return error / JP: エラー返却

            plugins_dir = self._get_plugins_directory()  # 注: 插件目录 / EN: plugins dir / JP: ディレクトリ
            plugins = self._scan_plugins(plugins_dir)  # 注: 扫描插件 / EN: scan plugins / JP: スキャン
            
            if plugin_name.upper() == "ALL":  # 注: 批量更新 / EN: update all / JP: すべて更新
                # 先检查所有需要更新的插件 / EN: first gather updates / JP: 先に更新必要リスト作成
                plugins_to_update = []  # 注: 待更新列表 / EN: to-update list / JP: 更新対象リスト
                ssl_context = ssl.create_default_context()  # 注: SSL context / EN: SSL context / JP: SSLコンテキスト
                ssl_context.check_hostname = False  # 注: 关闭主机名检查 / EN: disable hostname check / JP: ホスト名検証無効
                ssl_context.verify_mode = ssl.CERT_NONE  # 注: 不验证证书 / EN: no cert verification / JP: 証明書検証無効
                
                checking_message = "🔄 **正在检查所有插件的更新状态...**"  # 注: 检查提示 / EN: checking prompt / JP: チェックプロンプト
                await self.send_text(checking_message)  # 注: 发送 / EN: send / JP: 送信
                
                for plugin in plugins:  # 注: 遍历插件 / EN: iterate plugins / JP: 反復
                    # 添加延迟避免API限制 / EN: rate limit delay / JP: レート制限遅延
                    await self._rate_limit_delay()  # 注: 延迟 / EN: delay / JP: 待機
                    
                    # 只使用 repository_url 字段 / EN: only repository_url / JP: repository_urlのみ
                    repository_url = plugin.get('repository_url', '')  # 注: 仓库地址 / EN: repo url / JP: URL
                    if not repository_url:  # 注: 无仓库跳过 / EN: skip if no repo / JP: スキップ
                        continue  # 注: continue / EN: continue / JP: 続行
                    
                    remote_version = await self._get_remote_version(repository_url, ssl_context)  # 注: 获取远程版本 / EN: get remote version / JP: リモート版取得
                    if remote_version and remote_version != plugin['local_version']:  # 注: 需要更新则加入列表 / EN: add if needs update / JP: 更新必要なら追加
                        plugin['remote_version'] = remote_version  # 注: 记录 / EN: store / JP: 記録
                        plugin['needs_update'] = True  # 注: 标记 / EN: mark / JP: マーク
                        plugins_to_update.append(plugin)  # 注: 添加到列表 / EN: append / JP: 追加

                if not plugins_to_update:  # 注: 无需更新 / EN: nothing to update / JP: 更新不要
                    await self.send_text("🟢 所有插件均为最新版本，无需更新。")  # 注: 发送消息 / EN: send message / JP: 送信
                    return True, "无需更新", True  # 注: 返回 / EN: return / JP: 返却

                update_message = f"🔄 **开始更新 {len(plugins_to_update)} 个插件**\n\n"  # 注: 开始更新消息 / EN: start update msg / JP: 開始メッセージ
                await self.send_text(update_message)  # 注: 发送 / EN: send / JP: 送信

                success_count = 0  # 注: 成功计数 / EN: success counter / JP: 成功カウンタ
                update_results = []  # 注: 结果列表 / EN: results list / JP: 結果リスト
                for plugin in plugins_to_update:  # 注: 遍历待更新 / EN: iterate to-update / JP: 反復
                    try:  # 注: 单个更新 try / EN: per-update try / JP: 更新ごとtry
                        if await self._perform_plugin_update(plugin):  # 注: 执行更新 / EN: perform update / JP: 更新実行
                            success_count += 1  # 注: 成功计数加一 / EN: increment success / JP: 成功インクリメント
                            update_results.append(f"✅ {plugin['name']} → v{plugin['remote_version']}")  # 注: 追加成功信息 / EN: append success info / JP: 成功情報追加
                        else:  # 注: 更新失败 / EN: update failed / JP: 更新失敗
                            update_results.append(f"❌ {plugin['name']} 更新失败")  # 注: 追加失败信息 / EN: append fail info / JP: 失敗情報
                    except Exception as e:  # 注: 更新异常 / EN: update exception / JP: 更新例外
                        update_results.append(f"❌ {plugin['name']} 更新出错: {str(e)}")  # 注: 记录异常 / EN: record exception / JP: 例外記録

                # 统一发送更新结果 / EN: send combined results / JP: 結果一括送信
                result_message = f"🎉 **批量更新完成**\n成功: {success_count}/{len(plugins_to_update)}\n\n"  # 注: 结果摘要 / EN: summary / JP: サマリ
                for result in update_results:  # 注: 添加结果行 / EN: add result lines / JP: 行追加
                    result_message += f"{result}\n"  # 注: 追加行 / EN: append line / JP: 行追加
                
                await self.send_text(result_message)  # 注: 发送最终结果 / EN: send final result / JP: 送信
                return True, f"批量更新完成: {success_count}/{len(plugins_to_update)}", True  # 注: 返回 / EN: return / JP: 返却

            else:  # 注: 更新单个插件分支 / EN: single plugin update / JP: 単一プラグイン更新
                # 更新指定插件 / EN: update specific plugin / JP: 指定プラグイン更新
                target_plugin = None  # 注: 初始化 / EN: init / JP: 初期化
                for plugin in plugins:  # 注: 查找插件 / EN: find plugin / JP: プラグイン検索
                    if plugin['name'].lower() == plugin_name.lower():  # 注: 忽略大小写比较 / EN: case-insensitive compare / JP: 大文字小文字無視
                        target_plugin = plugin  # 注: 找到目标 / EN: assign target / JP: ターゲット設定
                        break  # 注: 退出循环 / EN: break loop / JP: ループ抜け

                if not target_plugin:  # 注: 未找到目标 / EN: not found / JP: 見つからない
                    await self.send_text(f"❌ 未找到插件: {plugin_name}")  # 注: 发送未找到消息 / EN: send not found / JP: 見つからない送信
                    return False, f"插件未找到: {plugin_name}", True  # 注: 返回错误 / EN: return error / JP: エラー返却

                # 检查是否需要更新 / EN: check need-update / JP: 更新要否確認
                ssl_context = ssl.create_default_context()  # 注: SSL context / EN: SSL context / JP: SSLコンテキスト
                ssl_context.check_hostname = False  # 注: 关闭主机名检查 / EN: disable hostname check / JP: ホスト名検証無効
                ssl_context.verify_mode = ssl.CERT_NONE  # 注: 不验证证书 / EN: no-cert-verify / JP: 証明書検証無効
                
                # 添加延迟避免API限制 / EN: rate delay / JP: レート遅延
                await self._rate_limit_delay()  # 注: 延迟 / EN: delay / JP: 待機
                
                # 只使用 repository_url 字段 / EN: only repo url / JP: repository_urlのみ
                repository_url = target_plugin.get('repository_url', '')  # 注: 获取仓库 URL / EN: get repo url / JP: URL取得
                if not repository_url:  # 注: 无仓库地址错误 / EN: missing repo error / JP: URL欠如エラー
                    await self.send_text(f"❌ 插件 {plugin_name} 没有配置仓库地址")  # 注: 发送 / EN: send / JP: 送信
                    return False, "无仓库地址", True  # 注: 返回 / EN: return / JP: 返却
                
                remote_version = await self._get_remote_version(repository_url, ssl_context)  # 注: 获取远程版本 / EN: get remote version / JP: リモート版取得
                if not remote_version:  # 注: 无法获取远程版本 / EN: cannot get remote version / JP: 取得不可
                    await self.send_text(f"❌ 无法获取 {plugin_name} 的远程版本信息")  # 注: 发送错误 / EN: send error / JP: エラー送信
                    return False, "无法获取远程版本", True  # 注: 返回 / EN: return / JP: 返却

                if remote_version == target_plugin['local_version']:  # 注: 已是最新 / EN: already latest / JP: 既に最新
                    await self.send_text(f"🟢 {plugin_name} 已是最新版本 (v{remote_version})")  # 注: 发送提示 / EN: send notice / JP: 通知
                    return True, "插件已是最新", True  # 注: 返回 / EN: return / JP: 返却

                target_plugin['remote_version'] = remote_version  # 注: 记录远程版本 / EN: store remote version / JP: リモート版記録
                await self.send_text(f"🔄 开始更新插件: {plugin_name} (v{target_plugin['local_version']} → v{remote_version})")  # 注: 发送开始更新 / EN: send start update / JP: 更新開始送信
                
                if await self._perform_plugin_update(target_plugin):  # 注: 执行更新 / EN: perform update / JP: 更新実行
                    success_msg = f"✅ **更新成功**\n{plugin_name} 已更新到 v{remote_version}"  # 注: 成功消息 / EN: success message / JP: 成功メッセージ
                    await self.send_text(success_msg)  # 注: 发送成功消息 / EN: send success / JP: 送信
                    return True, f"插件更新成功: {plugin_name}", True  # 注: 返回成功 / EN: return success / JP: 成功返却
                else:  # 注: 更新失败 / EN: update failed / JP: 更新失敗
                    error_msg = f"❌ 更新插件失败: {plugin_name}"  # 注: 错误消息 / EN: error message / JP: エラーメッセージ
                    await self.send_text(error_msg)  # 注: 发送错误 / EN: send error / JP: 送信
                    return False, error_msg, True  # 注: 返回失败 / EN: return failure / JP: 失敗返却

        except Exception as e:  # 注: 外层异常 / EN: outer exception / JP: 外部例外
            error_msg = f"❌ 更新插件时出错: {str(e)}"  # 注: 构建错误 / EN: build error / JP: エラーメッセージ
            await self.send_text(error_msg)  # 注: 发送错误 / EN: send error / JP: 送信
            return False, error_msg, True  # 注: 返回错误 / EN: return error / JP: エラー返却

    async def _plugin_info(self, plugin_name: str) -> Tuple[bool, Optional[str], bool]:  # 注: 查看插件信息 / EN: plugin info / JP: プラグイン情報
        """查看插件详细信息"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try / EN: try / JP: try
            if not plugin_name:  # 注: 未指定插件名 / EN: missing plugin name / JP: プラグイン名無し
                await self.send_text("❌ 请指定要查看的插件名。")  # 注: 发送提示 / EN: send prompt / JP: 送信
                return False, "未指定插件名", True  # 注: 返回 / EN: return / JP: 返却

            plugins_dir = self._get_plugins_directory()  # 注: 插件目录 / EN: plugins dir / JP: ディレクトリ
            plugins = self._scan_plugins(plugins_dir)  # 注: 扫描插件 / EN: scan plugins / JP: スキャン
            
            target_plugin = None  # 注: 初始化目标 / EN: init target / JP: ターゲット初期化
            for plugin in plugins:  # 注: 查找目标插件 / EN: find target plugin / JP: ターゲット検索
                if plugin['name'].lower() == plugin_name.lower():  # 注: 忽略大小写 / EN: case-insensitive / JP: 大文字小文字無視
                    target_plugin = plugin  # 注: 设置目标 / EN: set target / JP: ターゲット設定
                    break  # 注: 退出循环 / EN: break loop / JP: ループ抜け

            if not target_plugin:  # 注: 未找到插件 / EN: not found / JP: 見つからない
                await self.send_text(f"❌ 未找到插件: {plugin_name}")  # 注: 发送 / EN: send / JP: 送信
                return False, f"插件未找到: {plugin_name}", True  # 注: 返回 / EN: return / JP: 返却

            # 构建详细信息消息 / EN: build info message / JP: 情報メッセージ構築
            info_message = f"📋 **插件信息 - {target_plugin['name']}**\n\n"  # 注: 标题 / EN: header / JP: ヘッダ
            info_message += f"🔸 **版本**: v{target_plugin['local_version']}\n"  # 注: 版本 / EN: version / JP: バージョン
            info_message += f"🔸 **目录**: {target_plugin['directory_name']}\n"  # 注: 目录 / EN: directory / JP: ディレクトリ
            info_message += f"🔸 **仓库**: {target_plugin['repository_url']}\n"  # 注: 仓库 / EN: repository / JP: リポジトリ
            
            # 检查远程版本 / EN: check remote version / JP: リモート版確認
            ssl_context = ssl.create_default_context()  # 注: SSL context / EN: SSL context / JP: SSLコンテキスト
            ssl_context.check_hostname = False  # 注: 关闭主机名检查 / EN: disable hostname check / JP: ホスト名検証無効
            ssl_context.verify_mode = ssl.CERT_NONE  # 注: 不验证证书 / EN: no cert verify / JP: 証明書検証無効
            
            # 添加延迟避免API限制 / EN: rate delay / JP: レート遅延
            await self._rate_limit_delay()  # 注: 延迟 / EN: delay / JP: 待機
            
            # 只使用 repository_url 字段 / EN: only repo url / JP: repository_urlのみ
            repository_url = target_plugin.get('repository_url', '')  # 注: 获取仓库地址 / EN: get repo url / JP: URL取得
            if repository_url:  # 注: 有仓库则检查 / EN: if has repo / JP: リポジトリあり
                remote_version = await self._get_remote_version(repository_url, ssl_context)  # 注: 获取远程版本 / EN: get remote version / JP: 取得
                if remote_version:  # 注: 如果获取到 / EN: if obtained / JP: 取得できた場合
                    status = "🟢 最新" if remote_version == target_plugin['local_version'] else "🟡 可更新"  # 注: 状态 / EN: status / JP: ステータス
                    info_message += f"🔸 **远程版本**: v{remote_version}\n"  # 注: 远程版本 / EN: remote version / JP: リモート版
                    info_message += f"🔸 **状态**: {status}\n"  # 注: 状态行 / EN: status line / JP: ステータス行
                else:  # 注: 无法检查 / EN: cannot check / JP: チェック不可
                    info_message += "🔸 **状态**: 🔴 无法检查更新\n"  # 注: 状态提示 / EN: status hint / JP: 状態
            else:  # 注: 无仓库地址 / EN: no repo / JP: リポジトリ無し
                info_message += "🔸 **状态**: 🔴 无仓库地址\n"  # 注: 提示 / EN: hint / JP: ヒント

            # 自动更新设置 / EN: auto-update setting / JP: 自動更新設定
            auto_update = self._get_plugin_auto_update_setting(target_plugin['name'])  # 注: 读取设置 / EN: read setting / JP: 設定取得
            info_message += f"🔸 **自动更新**: {'✅ 开启' if auto_update else '❌ 关闭'}\n"  # 注: 显示设置 / EN: show setting / JP: 設定表示

            await self.send_text(info_message)  # 注: 发送信息 / EN: send info / JP: 送信
            return True, f"已显示插件信息: {plugin_name}", True  # 注: 返回成功 / EN: return success / JP: 成功返却

        except Exception as e:  # 注: 异常处理 / EN: exception handle / JP: 例外処理
            error_msg = f"❌ 获取插件信息时出错: {str(e)}"  # 注: 构建错误 / EN: build error / JP: エラーメッセージ
            await self.send_text(error_msg)  # 注: 发送错误 / EN: send error / JP: 送信
            return False, error_msg, True  # 注: 返回错误 / EN: return error / JP: エラー返却

    async def _manage_settings(self, setting_args: str) -> Tuple[bool, Optional[str], bool]:  # 注: 管理设置 / EN: manage settings / JP: 設定管理
        """管理插件自动更新设置"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            if not setting_args:  # 注: 无参数则显示当前设置 / EN: no args -> show settings / JP: 引数無ければ表示
                # 显示当前设置 / EN: show current settings / JP: 現在の設定表示
                settings = self._load_settings()  # 注: 载入设置文件 / EN: load settings / JP: 設定読み込み
                message = "⚙️ **插件自动更新设置**\n\n"  # 注: 消息头 / EN: message header / JP: メッセージヘッダ
                
                plugins_dir = self._get_plugins_directory()  # 注: 获取插件目录 / EN: get plugins dir / JP: プラグインディレクトリ取得
                plugins = self._scan_plugins(plugins_dir)  # 注: 扫描插件 / EN: scan plugins / JP: スキャン
                
                for plugin in plugins:  # 注: 列出每个插件的自动更新开关 / EN: list auto-update for each / JP: 各プラグインの自動更新表示
                    auto_update = settings.get('auto_update', {}).get(plugin['name'], False)  # 注: 获取状态 / EN: get status / JP: ステータス取得
                    status = "✅ 开启" if auto_update else "❌ 关闭"  # 注: 可读状态 / EN: readable status / JP: ステータス文字列
                    message += f"• {plugin['name']}: {status}\n"  # 注: 添加行 / EN: append line / JP: 行追加
                
                message += "\n💡 使用 `/pm settings <插件名> on/off` 修改设置"  # 注: 操作说明 / EN: usage / JP: 使用法
                message += "\n💡 例如: `/pm settings 海龟汤 on`"  # 注: 示例 / EN: example / JP: 例
                
                await self.send_text(message)  # 注: 发送消息 / EN: send message / JP: 送信
                return True, "已显示设置", True  # 注: 返回成功 / EN: return success / JP: 成功返却
            else:  # 注: 有参数则修改设置 / EN: modify settings / JP: 設定変更
                # 修改设置 / EN: change setting / JP: 設定変更
                parts = setting_args.split()  # 注: 拆分参数 / EN: split args / JP: 引数分割
                if len(parts) < 2:  # 注: 参数数不足 / EN: not enough args / JP: 引数不足
                    await self.send_text("❌ 参数格式错误。使用: `/pm settings <插件名> on/off`")  # 注: 发送错误提示 / EN: send error / JP: エラー送信
                    return False, "参数格式错误", True  # 注: 返回错误 / EN: return error / JP: エラー返却
                
                plugin_name = ' '.join(parts[:-1])  # 注: 插件名可能包含空格 / EN: plugin name may include spaces / JP: プラグイン名に空白含む場合
                action = parts[-1].lower()  # 注: 最后一个参数为 on/off / EN: last param is on/off / JP: 最後の引数はon/off
                
                if action not in ['on', 'off']:  # 注: 参数校验 / EN: validate action / JP: アクション検証
                    await self.send_text("❌ 操作参数错误，请使用 'on' 或 'off'")  # 注: 发送错误 / EN: send error / JP: エラー送信
                    return False, "操作参数错误", True  # 注: 返回错误 / EN: return error / JP: エラー返却
                
                # 验证插件是否存在 / EN: verify plugin exists / JP: プラグイン存在確認
                plugins_dir = self._get_plugins_directory()  # 注: 获取目录 / EN: get dir / JP: ディレクトリ取得
                plugins = self._scan_plugins(plugins_dir)  # 注: 扫描 / EN: scan / JP: スキャン
                plugin_exists = any(p['name'].lower() == plugin_name.lower() for p in plugins)  # 注: 判断存在 / EN: check existence / JP: 存在判定
                
                if not plugin_exists:  # 注: 未找到插件 / EN: not found / JP: 見つからない
                    await self.send_text(f"❌ 未找到插件: {plugin_name}")  # 注: 发送 / EN: send / JP: 送信
                    return False, "插件未找到", True  # 注: 返回 / EN: return / JP: 返却
                
                # 更新设置 / EN: update settings / JP: 設定更新
                settings = self._load_settings()  # 注: 载入当前设置 / EN: load current / JP: 現在設定読み込み
                if 'auto_update' not in settings:  # 注: 确保键存在 / EN: ensure key exists / JP: キー存在確認
                    settings['auto_update'] = {}  # 注: 初始化 / EN: init / JP: 初期化
                
                # 找到准确的插件名（保持大小写） / EN: find exact plugin name (case preserved) / JP: 大文字小文字保持で正確な名前取得
                actual_plugin_name = next(p['name'] for p in plugins if p['name'].lower() == plugin_name.lower())  # 注: 获取正确名称 / EN: get actual name / JP: 実名取得
                settings['auto_update'][actual_plugin_name] = (action == 'on')  # 注: 设置布尔值 / EN: set boolean / JP: ブール設定
                self._save_settings(settings)  # 注: 保存设置 / EN: save settings / JP: 設定保存
                
                status = "开启" if action == 'on' else "关闭"  # 注: 可读状态 / EN: readable status / JP: 表示
                await self.send_text(f"✅ 已{status} {actual_plugin_name} 的自动更新")  # 注: 发送确认 / EN: send confirmation / JP: 確認送信
                return True, f"已更新设置: {actual_plugin_name} = {action}", True  # 注: 返回成功 / EN: return success / JP: 成功返却

        except Exception as e:  # 注: 异常处理 / EN: exception handling / JP: 例外処理
            error_msg = f"❌ 管理设置时出错: {str(e)}"  # 注: 构建错误消息 / EN: build error msg / JP: エラーメッセージ
            await self.send_text(error_msg)  # 注: 发送错误 / EN: send error / JP: 送信
            return False, error_msg, True  # 注: 返回错误 / EN: return error / JP: エラー返却

    def _get_plugins_directory(self) -> Path:  # 注: 获取plugins目录路径 / EN: get plugins directory / JP: プラグインディレクトリ取得
        """获取plugins目录路径"""  # 注: docstring / EN: docstring / JP: ドックストリング
        current_file = Path(__file__).resolve()  # 注: 当前文件路径 / EN: current file path / JP: 現在ファイルパス
        # 当前插件目录: plugins/Plugin_manager / EN: expected plugin dir / JP: 期待プラグインディレクトリ
        plugins_dir = current_file.parent.parent  # 注: 往上两级以到 plugins 目录 / EN: go up two levels / JP: 2階層上がる
        return plugins_dir  # 注: 返回路径 / EN: return path / JP: パス返却

    def _scan_plugins(self, plugins_dir: Path) -> List[Dict[str, Any]]:  # 注: 扫描插件目录 / EN: scan plugins dir / JP: プラグインスキャン
        """扫描plugins目录下的所有插件"""  # 注: docstring / EN: docstring / JP: ドックストリング
        plugins = []  # 注: 插件列表容器 / EN: plugins list / JP: プラグインリスト
        ignored_plugin = "Hello World 示例插件 (Hello World Plugin)"  # 注: 要忽略的示例插件名 / EN: ignored sample / JP: 無視するサンプル名
        
        for item in plugins_dir.iterdir():  # 注: 遍历目录项 / EN: iterate dir items / JP: ディレクトリ反復
            if item.is_dir() and item.name != "Plugin_manager":  # 注: 排除本插件目录 / EN: exclude manager dir / JP: 管理ディレクトリ除外
                manifest_file = item / "_manifest.json"  # 注: manifest 路径 / EN: manifest path / JP: マニフェストパス
                if manifest_file.exists():  # 注: 如果 manifest 存在 / EN: if manifest exists / JP: マニフェスト存在確認
                    try:  # 注: 读 manifest / EN: read manifest / JP: マニフェスト読み取り
                        with open(manifest_file, 'r', encoding='utf-8') as f:  # 注: 打开文件 / EN: open file / JP: ファイルオープン
                            manifest_data = json.load(f)  # 注: 解析 JSON / EN: parse JSON / JP: JSON解析
                        
                        plugin_name = manifest_data.get('name', '')  # 注: 读取名称 / EN: get name / JP: 名前取得
                        if plugin_name == ignored_plugin:  # 注: 忽略示例插件 / EN: skip sample / JP: サンプルをスキップ
                            continue  # 注: 跳过 / EN: continue / JP: 続行
                            
                        plugins.append({  # 注: 加入插件信息字典 / EN: append plugin info / JP: 情報追加
                            'name': plugin_name,  # 注: 名称 / EN: name / JP: 名前
                            'local_version': manifest_data.get('version', '未知'),  # 注: 本地版本 / EN: local version / JP: ローカル版
                            'repository_url': manifest_data.get('repository_url', ''),  # 注: 仓库地址 / EN: repo url / JP: リポジトリURL
                            'directory_name': item.name,  # 注: 目录名 / EN: dir name / JP: ディレクトリ名
                            'directory_path': item,  # 注: Path 对象 / EN: Path object / JP: Pathオブジェクト
                            'needs_update': False  # 注: 默认不需要更新 / EN: default needs_update / JP: 更新不要デフォルト
                        })
                    except Exception as e:  # 注: 读取/解析 manifest 失败 / EN: manifest read/parse failed / JP: マニフェスト読み取り失敗
                        print(f"读取插件 {item.name} 的manifest文件失败: {e}")  # 注: 打印错误 / EN: print error / JP: エラー出力
                        continue  # 注: 跳过此插件 / EN: skip plugin / JP: スキップ
        
        return plugins  # 注: 返回列表 / EN: return list / JP: リスト返却

    async def _get_remote_version(self, repository_url: str, ssl_context: ssl.SSLContext = None) -> Optional[str]:  # 注: 获取远程版本 / EN: get remote version / JP: リモート版取得
        """从GitHub仓库获取最新版本号 - 支持GitHub认证"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            if not repository_url or "github.com" not in repository_url:  # 注: 简单校验 URL / EN: basic URL check / JP: URLチェック
                print(f"无效的仓库URL: {repository_url}")  # 注: 打印并返回 / EN: print and return / JP: 出力して返却
                return None  # 注: 返回 None / EN: return None / JP: None返却

            # 清理和验证仓库URL / EN: clean repo URL / JP: リポジトリURL整形
            repo_path = repository_url.replace("https://github.com/", "").strip("/")  # 注: 提取 owner/repo / EN: extract owner/repo / JP: 所有者/リポジトリ抽出
            if not repo_path or '/' not in repo_path:  # 注: 格式不对 / EN: invalid format / JP: 形式不正
                print(f"无效的仓库路径: {repo_path}")  # 注: 打印 / EN: print / JP: 出力
                return None  # 注: 返回 / EN: return / JP: 返却

            # 构建GitHub API URL / EN: build API url / JP: API URL構築
            api_url = f"https://api.github.com/repos/{repo_path}/contents/_manifest.json"  # 注: 指向仓库根的 manifest / EN: point to manifest / JP: マニフェスト参照
            print(f"请求GitHub API: {api_url}")  # 注: 打印调试 / EN: debug print / JP: デバッグ出力

            # 创建连接器，禁用SSL验证 / EN: create connector (ssl_context) / JP: コネクタ作成
            connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context else None  # 注: 可选 connector / EN: optional connector / JP: オプショナル
            
            # 获取GitHub认证头 / EN: get headers / JP: ヘッダ取得
            headers = self._get_github_headers()  # 注: headers from config / EN: headers / JP: ヘッダ
            github_config = self._get_github_config()  # 注: read config / EN: read config / JP: 設定読み取り
            
            timeout = aiohttp.ClientTimeout(total=15)  # 15秒超时 / EN: 15s timeout / JP: タイムアウト
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:  # 注: 建立会话 / EN: create session / JP: セッション作成
                async with session.get(api_url, headers=headers) as response:  # 注: GET 请求 / EN: GET request / JP: GETリクエスト
                    print(f"GitHub API响应状态: {response.status}")  # 注: 打印状态 / EN: print status / JP: ステータス出力
                    
                    if response.status == 200:  # 注: 成功 / EN: success / JP: 成功
                        data = await response.json()  # 注: 解析 JSON / EN: parse json / JP: JSON解析
                        if 'content' in data:  # 注: GitHub 返回 base64 内容 / EN: content in response / JP: content有無
                            # 解码base64内容 / EN: decode base64 / JP: base64デコード
                            content = base64.b64decode(data['content']).decode('utf-8')  # 注: 解码 / EN: decode / JP: デコード
                            manifest_data = json.loads(content)  # 注: 解析 manifest / EN: parse manifest / JP: マニフェスト解析
                            version = manifest_data.get('version')  # 注: 读取 version / EN: get version / JP: バージョン取得
                            print(f"获取到远程版本: {version}")  # 注: 打印 / EN: print / JP: 出力
                            return version  # 注: 返回版本 / EN: return version / JP: 返却
                        else:  # 注: 未包含 content / EN: missing content / JP: content無し
                            print(f"响应中缺少content字段: {data}")  # 注: 打印 / EN: print / JP: 出力
                    elif response.status == 403:  # 注: 速率限制或权限问题 / EN: rate limit or forbidden / JP: レート制限
                        # 检查速率限制头 / EN: check rate-limit headers / JP: レート制限ヘッダ
                        remaining = response.headers.get('X-RateLimit-Remaining', '未知')  # 注: 剩余次数 / EN: remaining / JP: 残り
                        limit = response.headers.get('X-RateLimit-Limit', '未知')  # 注: 限制 / EN: limit / JP: 制限
                        reset_time = response.headers.get('X-RateLimit-Reset', '未知')  # 注: 重置时间 / EN: reset / JP: リセット
                        print(f"GitHub API限制 - 剩余: {remaining}/{limit}, 重置: {reset_time}")  # 注: 打印 / EN: print / JP: 出力
                        
                        if github_config.get('token'):  # 注: 如果用 token 仍被限流 / EN: token but still limited / JP: トークン使っても制限
                            print("即使使用Token也遇到限制，可能需要等待")  # 注: 打印 / EN: print / JP: 出力
                        else:  # 注: 未认证 / EN: unauthenticated / JP: 未認証
                            print("未使用GitHub Token，API限制严格")  # 注: 打印 / EN: print / JP: 出力
                    elif response.status == 404:  # 注: 未找到 / EN: not found / JP: 見つからない
                        print("仓库或manifest文件不存在")  # 注: 打印 / EN: print / JP: 出力
                    elif response.status == 401:  # 注: 未授权 / EN: unauthorized / JP: 認証失敗
                        print("GitHub Token无效或过期")  # 注: 打印 / EN: print / JP: 出力
                    else:  # 注: 其他错误 / EN: other errors / JP: その他エラー
                        print(f"GitHub API错误: {response.status}")  # 注: 打印 / EN: print / JP: 出力
                        error_text = await response.text()  # 注: 读取错误正文 / EN: read error text / JP: エラーテキスト取得
                        print(f"错误详情: {error_text}")  # 注: 打印 / EN: print / JP: 出力
            
            return None  # 注: 未获取到版本则返回 None / EN: return None / JP: None返却
        except asyncio.TimeoutError:  # 注: 超时单独处理 / EN: timeout handling / JP: タイムアウト処理
            print(f"获取远程版本超时: {repository_url}")  # 注: 打印 / EN: print / JP: 出力
            return None  # 注: 返回 None / EN: return None / JP: None返却
        except Exception as e:  # 注: 其他异常 / EN: other exceptions / JP: その他例外
            print(f"获取远程版本失败 {repository_url}: {e}")  # 注: 打印 / EN: print / JP: 出力
            return None  # 注: 返回 None / EN: return None / JP: None返却

    async def _perform_plugin_update(self, plugin: Dict[str, Any]) -> bool:  # 注: 执行插件更新 / EN: perform plugin update / JP: プラグイン更新実行
        """执行插件更新：从GitHub仓库下载并覆盖文件 - 改进的网络稳定性"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: try 块 / EN: try block / JP: tryブロック
            repository_url = plugin['repository_url']  # 注: 仓库 URL / EN: repo url / JP: リポジトリURL
            if not repository_url or "github.com" not in repository_url:  # 注: 验证 URL / EN: validate URL / JP: URL検証
                print(f"无效的仓库URL: {repository_url}")  # 注: 打印 / EN: print / JP: 出力
                return False  # 注: 返回失败 / EN: return False / JP: False返却

            repo_path = repository_url.replace("https://github.com/", "").strip("/")  # 注: 提取 owner/repo / EN: extract owner/repo / JP: 所有者/リポジトリ抽出
            if not repo_path or '/' not in repo_path:  # 注: 格式检查 / EN: format check / JP: 形式チェック
                print(f"无效的仓库路径: {repo_path}")  # 注: 打印 / EN: print / JP: 出力
                return False  # 注: 返回失败 / EN: return False / JP: False返却

            api_url = f"https://api.github.com/repos/{repo_path}/contents/"  # 注: API 列表 URL / EN: api contents url / JP: contents API URL
            print(f"开始更新插件 {plugin['name']}，仓库: {repo_path}")  # 注: 打印开始更新 / EN: start update log / JP: 更新開始ログ

            # 创建 SSL 上下文以禁用证书验证 / EN: create ssl context / JP: SSLコンテキスト作成
            ssl_context = ssl.create_default_context()  # 注: 默认 context / EN: default context / JP: デフォルト
            ssl_context.check_hostname = False  # 注: 禁用主机名检查 / EN: disable hostname check / JP: ホスト名検証無効
            ssl_context.verify_mode = ssl.CERT_NONE  # 注: 不验证证书 / EN: no cert verify / JP: 証明書検証無効
            connector = aiohttp.TCPConnector(ssl=ssl_context)  # 注: 连接器 / EN: connector / JP: コネクタ

            # 获取GitHub认证头 / EN: get headers / JP: ヘッダ取得
            headers = self._get_github_headers()  # 注: headers / EN: headers / JP: ヘッダ

            # 创建临时目录 / EN: create temp dir / JP: 一時ディレクトリ作成
            with tempfile.TemporaryDirectory() as temp_dir:  # 注: 自动清理 / EN: auto cleanup / JP: 自動クリーン
                temp_path = Path(temp_dir)  # 注: Path 对象 / EN: Path object / JP: Pathオブジェクト
                
                # 获取仓库文件列表 / EN: get repo file list / JP: ファイル一覧取得
                async with aiohttp.ClientSession(connector=connector, headers=headers) as session:  # 注: session with headers / EN: session / JP: セッション
                    async with session.get(api_url) as response:  # 注: 请求根目录文件列表 / EN: request root contents / JP: ルート取得
                        if response.status != 200:  # 注: 非 200 则失败 / EN: non-200 fail / JP: 200以外は失敗
                            print(f"获取仓库文件列表失败: {response.status}")  # 注: 打印 / EN: print / JP: 出力
                            return False  # 注: 返回失败 / EN: return False / JP: False返却
                        
                        files_data = await response.json()  # 注: 解析 JSON / EN: parse json / JP: JSON解析
                        print(f"找到 {len(files_data)} 个文件")  # 注: 打印数量 / EN: print count / JP: 件数出力
                        
                        # 只下载必要的文件，跳过LICENSE等非必要文件 / EN: prioritize essential files / JP: 必要ファイル優先
                        essential_files = ['plugin.py', '_manifest.json', 'config.toml', 'requirements.txt']  # 注: 必需列表 / EN: essential list / JP: 必要リスト
                        download_tasks = []  # 注: 下载任务列表 / EN: download tasks / JP: ダウンロードタスク
                        for file_info in files_data:  # 注: 遍历文件信息 / EN: iterate files_data / JP: ファイル情報反復
                            if file_info['type'] == 'file' and file_info.get('download_url'):  # 注: 仅文件且有下载地址 / EN: file with download_url / JP: ダウンロードURLあり
                                file_name = file_info['name']  # 注: 文件名 / EN: file name / JP: ファイル名
                                # 优先下载必要文件，其他文件可选 / EN: prioritize essential / JP: 優先ダウンロード
                                if file_name in essential_files or file_name.endswith('.py') or file_name.endswith('.json'):  # 注: 筛选规则 / EN: filter rules / JP: フィルタ
                                    download_tasks.append(self._download_file_with_retry(session, file_info, temp_path))  # 注: 添加协程 / EN: add coroutine / JP: コルーチン追加
                        
                        # 并行下载文件，但限制并发数 / EN: parallel download with concurrency limit / JP: 並列ダウンロード
                        if download_tasks:  # 注: 如果有任务 / EN: if tasks exist / JP: タスクあり
                            # 限制并发数为3，避免网络压力过大 / EN: semaphore limit 3 / JP: セマフォ制限
                            semaphore = asyncio.Semaphore(3)  # 注: 并发信号量 / EN: semaphore / JP: セマフォ
                            async def limited_download(task):  # 注: 限制封装 / EN: wrapper / JP: ラッパー
                                async with semaphore:  # 注: 获取信号量 / EN: acquire sem / JP: セマフォ取得
                                    return await task  # 注: 执行下载协程 / EN: await task / JP: タスク実行
                            
                            limited_tasks = [limited_download(task) for task in download_tasks]  # 注: 包装任务 / EN: wrap tasks / JP: タスク包装
                            await asyncio.gather(*limited_tasks, return_exceptions=True)  # 注: 并发执行 / EN: run tasks / JP: 実行

                # 检查是否下载了必要文件 / EN: check essential files downloaded / JP: 必要ファイル確認
                downloaded_files = list(temp_path.iterdir())  # 注: 列出临时目录项 / EN: list temp files / JP: 一時ディレクトリ列挙
                essential_downloaded = any(file.name in essential_files for file in downloaded_files)  # 注: 任意必要文件存在 / EN: any essential present / JP: いずれか存在確認
                
                if not essential_downloaded:  # 注: 未下载到必要文件 / EN: no essential files / JP: 必要ファイル無し
                    print("没有成功下载必要文件")  # 注: 打印 / EN: print / JP: 出力
                    return False  # 注: 返回失败 / EN: return False / JP: False返却

                print(f"成功下载 {len(downloaded_files)} 个文件")  # 注: 打印下载数量 / EN: print count / JP: 件数出力

                # 备份原插件目录 / EN: backup original plugin dir / JP: 元ディレクトリバックアップ
                plugin_dir = plugin['directory_path']  # 注: 原目录 Path / EN: original dir / JP: 元ディレクトリ
                backup_dir = plugin_dir.with_suffix('.backup')  # 注: 简单后缀备份 / EN: backup with suffix / JP: サフィックスバックアップ
                if backup_dir.exists():  # 注: 若存在则删除 / EN: if exists remove / JP: 存在なら削除
                    shutil.rmtree(backup_dir)  # 注: 删除旧备份 / EN: remove old backup / JP: 古いバックアップ削除
                shutil.copytree(plugin_dir, backup_dir)  # 注: 复制备份 / EN: copy backup / JP: バックアップコピー
                print(f"已创建备份: {backup_dir}")  # 注: 打印备份路径 / EN: print backup path / JP: バックアップ出力

                try:  # 注: 尝试替换原目录 / EN: try replace original / JP: 元ディレクトリ置換試行
                    # 清空原目录 / EN: clear original dir / JP: 元ディレクトリクリア
                    for item in plugin_dir.iterdir():  # 注: 遍历原目录 / EN: iterate original / JP: 元ディレクトリ反復
                        if item.is_file():  # 注: 文件则删除 / EN: remove file / JP: ファイル削除
                            item.unlink()  # 注: 删除 / EN: unlink / JP: 削除
                        elif item.is_dir():  # 注: 目录则删除树 / EN: remove dir tree / JP: ディレクトリ削除
                            shutil.rmtree(item)  # 注: 删除目录树 / EN: rmtree / JP: ディレクトリ削除

                    # 复制新文件 / EN: copy new files / JP: 新ファイルコピー
                    for item in temp_path.iterdir():  # 注: 遍历临时下载目录 / EN: iterate temp / JP: 一時ディレクトリ反復
                        if item.is_file():  # 注: 文件复制 / EN: copy file / JP: ファイルコピー
                            shutil.copy2(item, plugin_dir / item.name)  # 注: 保留元数据复制 / EN: copy2 / JP: コピー
                        elif item.is_dir():  # 注: 目录复制 / EN: copy dir / JP: ディレクトリコピー
                            shutil.copytree(item, plugin_dir / item.name)  # 注: 复制目录树 / EN: copytree / JP: コピー

                    print(f"成功更新插件 {plugin['name']}")  # 注: 打印成功 / EN: print success / JP: 成功出力

                    # 更新成功后删除备份 / EN: remove backup on success / JP: 成功後バックアップ削除
                    if backup_dir.exists():  # 注: 若备份存在则删除 / EN: remove backup / JP: バックアップ削除
                        shutil.rmtree(backup_dir)  # 注: 删除 / EN: remove / JP: 削除
                    
                    return True  # 注: 返回成功 / EN: return True / JP: True返却

                except Exception as e:  # 注: 更新过程中出现异常则恢复备份 / EN: on exception restore backup / JP: 例外時に復元
                    # 恢复备份 / EN: restore backup / JP: バックアップ復元
                    print(f"更新失败，恢复备份: {e}")  # 注: 打印 / EN: print / JP: 出力
                    if backup_dir.exists():  # 注: 如果有备份则恢复 / EN: if backup exists restore / JP: バックアップあれば復元
                        # 清空失败的文件 / EN: clear failed files / JP: 失敗ファイル削除
                        for item in plugin_dir.iterdir():  # 注: 遍历当前失败目录 / EN: iterate failed dir / JP: 反復
                            if item.is_file():  # 注: 删除文件 / EN: remove file / JP: ファイル削除
                                item.unlink()  # 注: 删除 / EN: unlink / JP: 削除
                            elif item.is_dir():  # 注: 删除目录 / EN: remove dir / JP: ディレクトリ削除
                                shutil.rmtree(item)  # 注: rmtree / EN: rmtree / JP: 削除
                        # 恢复备份到原目录 / EN: restore backup / JP: バックアップ復元
                        for item in backup_dir.iterdir():  # 注: 遍历备份 / EN: iterate backup / JP: バックアップ反復
                            if item.is_file():  # 注: 复制回文件 / EN: copy back file / JP: ファイル復元
                                shutil.copy2(item, plugin_dir / item.name)  # 注: copy2 / EN: copy2 / JP: コピー
                            elif item.is_dir():  # 注: 复制回目录 / EN: copy back dir / JP: ディレクトリ復元
                                shutil.copytree(item, plugin_dir / item.name)  # 注: copytree / EN: copytree / JP: コピー
                        print("已从备份恢复插件")  # 注: 打印恢复完成 / EN: restored / JP: 復元完了
                    return False  # 注: 返回失败 / EN: return False / JP: False返却

        except Exception as e:  # 注: 外层异常处理 / EN: outer exception / JP: 外部例外
            print(f"执行插件更新失败 {plugin['name']}: {e}")  # 注: 打印异常 / EN: print exception / JP: 例外出力
            import traceback  # 注: 导入 traceback / EN: import traceback / JP: tracebackインポート
            traceback.print_exc()  # 注: 打印堆栈 / EN: print stack / JP: スタック出力
            return False  # 注: 返回失败 / EN: return False / JP: False返却

    async def _download_file_with_retry(self, session: aiohttp.ClientSession, file_info: Dict, temp_path: Path, max_retries: int = 3) -> None:  # 注: 下载单文件带重试 / EN: download with retry / JP: 再試行ダウンロード
        """下载单个文件，带重试机制"""  # 注: docstring / EN: docstring / JP: ドックストリング
        for attempt in range(max_retries):  # 注: 重试循环 / EN: retry loop / JP: 再試行ループ
            try:  # 注: 尝试下载 / EN: try download / JP: ダウンロード試行
                file_url = file_info['download_url']  # 注: 下载 URL / EN: download url / JP: ダウンロードURL
                file_path = temp_path / file_info['name']  # 注: 临时文件路径 / EN: temp file path / JP: 一時ファイルパス
                
                # 设置较短的超时时间，避免长时间等待 / EN: short timeout / JP: タイムアウト設定
                timeout = aiohttp.ClientTimeout(total=10)  # 注: 10 秒超时 / EN: 10s timeout / JP: 10秒
                
                async with session.get(file_url, timeout=timeout) as response:  # 注: 请求文件 / EN: request file / JP: ファイル取得
                    if response.status == 200:  # 注: 成功则写入 / EN: success write / JP: 成功
                        content = await response.read()  # 注: 读取内容 / EN: read content / JP: 読み取り
                        with open(file_path, 'wb') as f:  # 注: 写二进制文件 / EN: write binary / JP: バイナリ書込
                            f.write(content)  # 注: 写入 / EN: write / JP: 書込
                        print(f"下载成功: {file_info['name']} (尝试 {attempt + 1})")  # 注: 打印成功 / EN: print success / JP: 成功出力
                        return  # 注: 返回成功 / EN: return / JP: 返却
                    else:  # 注: 非200错误 / EN: non-200 / JP: 200以外
                        print(f"下载失败 {file_info['name']}: {response.status} (尝试 {attempt + 1})")  # 注: 打印 / EN: print / JP: 出力
            except asyncio.TimeoutError:  # 注: 超时 / EN: timeout / JP: タイムアウト
                print(f"下载超时 {file_info['name']} (尝试 {attempt + 1})")  # 注: 打印 / EN: print / JP: 出力
            except Exception as e:  # 注: 其他异常 / EN: other exception / JP: その他例外
                print(f"下载文件 {file_info['name']} 时出错 (尝试 {attempt + 1}): {e}")  # 注: 打印 / EN: print / JP: 出力
            
            # 如果不是最后一次尝试，等待后重试 / EN: wait before retry / JP: リトライ前待機
            if attempt < max_retries - 1:  # 注: 若将重试 / EN: if will retry / JP: リトライがある場合
                await asyncio.sleep(1)  # 注: 等待 1 秒 / EN: sleep 1s / JP: 1秒待機
        
        print(f"下载失败 {file_info['name']}，已重试 {max_retries} 次")  # 注: 最终失败 / EN: failed after retries / JP: 最終失敗

    def _get_settings_file_path(self) -> Path:  # 注: 获取设置文件路径 / EN: get settings path / JP: 設定ファイルパス取得
        """获取设置文件路径"""  # 注: docstring / EN: docstring / JP: ドックストリング
        plugin_dir = Path(__file__).parent  # 注: 当前插件目录 / EN: plugin dir / JP: プラグインディレクトリ
        return plugin_dir / "plugin_settings.json"  # 注: 返回文件路径 / EN: settings file path / JP: 設定ファイルパス

    def _load_settings(self) -> Dict[str, Any]:  # 注: 加载设置 / EN: load settings / JP: 設定読み込み
        """加载设置文件"""  # 注: docstring / EN: docstring / JP: ドックストリング
        settings_file = self._get_settings_file_path()  # 注: 获取路径 / EN: get path / JP: パス取得
        if settings_file.exists():  # 注: 若存在则读取 / EN: if exists read / JP: 存在すれば読み取り
            try:  # 注: 尝试解析 / EN: try parse / JP: 解析試行
                with open(settings_file, 'r', encoding='utf-8') as f:  # 注: 打开文件 / EN: open file / JP: ファイルオープン
                    return json.load(f)  # 注: 解析 JSON 返回 / EN: parse json / JP: JSON解析
            except Exception as e:  # 注: 解析失败 / EN: parse failed / JP: 解析失敗
                print(f"读取设置文件失败: {e}")  # 注: 打印错误 / EN: print error / JP: エラー出力
        return {}  # 注: 默认空字典 / EN: default empty / JP: 空辞書返却

    def _save_settings(self, settings: Dict[str, Any]) -> None:  # 注: 保存设置 / EN: save settings / JP: 設定保存
        """保存设置文件"""  # 注: docstring / EN: docstring / JP: ドックストリング
        try:  # 注: 写文件尝试 / EN: try write / JP: 書込試行
            settings_file = self._get_settings_file_path()  # 注: 路径 / EN: path / JP: パス
            with open(settings_file, 'w', encoding='utf-8') as f:  # 注: 打开写入 / EN: open write / JP: 書込オープン
                json.dump(settings, f, ensure_ascii=False, indent=2)  # 注: 写 JSON / EN: dump json / JP: JSON書込
        except Exception as e:  # 注: 写入异常 / EN: write exception / JP: 書込例外
            print(f"保存设置文件失败: {e}")  # 注: 打印 / EN: print / JP: 出力

    def _get_plugin_auto_update_setting(self, plugin_name: str) -> bool:  # 注: 获取插件自动更新设置 / EN: get auto-update setting / JP: 自動更新設定取得
        """获取插件的自动更新设置"""  # 注: docstring / EN: docstring / JP: ドックストリング
        settings = self._load_settings()  # 注: 载入设置 / EN: load settings / JP: 設定読み込み
        return settings.get('auto_update', {}).get(plugin_name, False)  # 注: 返回布尔状态 / EN: return bool / JP: ブール返却


@register_plugin  # 注: 注册插件装饰器 / EN: register plugin / JP: プラグイン登録
class PluginManagerPlugin(BasePlugin):  # 注: 插件注册类 / EN: plugin class / JP: プラグインクラス
    """插件管理器插件 - 管理所有插件的更新和状态"""  # 注: 类说明 / EN: class doc / JP: クラス説明
    
    plugin_name = "plugin_manager"  # 注: 插件标识 / EN: plugin id / JP: プラグインID
    plugin_description = "插件管理器，用于管理插件的更新和状态检查"  # 注: 描述 / EN: description / JP: 説明
    plugin_version = PLUGIN_MANAGER_VERSION  # 注: 版本号 / EN: version / JP: バージョン
    plugin_author = "KArabella"  # 注: 作者 / EN: author / JP: 作者
    enable_plugin = True  # 注: 默认开启 / EN: enabled by default / JP: デフォルト有効

    dependencies = []  # 注: 依赖列表 / EN: dependencies / JP: 依存
    python_dependencies = ["aiohttp"]  # 注: Python 依赖 / EN: python deps / JP: Python依存

    config_file_name = "config.toml"  # 注: 配置文件名 / EN: config file name / JP: 設定ファイル名
    config_section_descriptions = {  # 注: 配置节说明 / EN: config section descriptions / JP: セクション説明
        "plugin": "插件启用配置",  # 注: 插件节 / EN: plugin section / JP: プラグイン節
        "admin": "管理员配置",  # 注: 管理节 / EN: admin section / JP: 管理者節
        "github": "GitHub API配置"  # 注: GitHub 节 / EN: github section / JP: GitHub節
    }

    config_schema = {  # 注: 配置模式 / EN: config schema / JP: 設定スキーマ
        "plugin": {
            "enabled": ConfigField(  # 注: 是否启用插件管理器 / EN: enable plugin manager / JP: 有効化フラグ
                type=bool,  # 注: 类型 / EN: type / JP: 型
                default=True,  # 注: 默认值 / EN: default / JP: デフォルト
                description="是否启用插件管理器"  # 注: 描述 / EN: description / JP: 説明
            ),
            "config_version": ConfigField(  # 注: 配置版本字段 / EN: config version / JP: 設定バージョン
                type=str,  # 注: 类型 / EN: type / JP: 型
                default="1.1.2",  # 注: 默认版本 / EN: default version / JP: デフォルト
                description="配置文件版本"  # 注: 描述 / EN: description / JP: 説明
            ),
        },
        "admin": {
            "qq_list": ConfigField(  # 注: 管理员 QQ 列表 / EN: admin qq list / JP: 管理者QQリスト
                type=list,  # 注: 类型 / EN: type / JP: 型
                default=[],  # 注: 默认空列表 / EN: default empty / JP: デフォルト
                description="管理员QQ号列表（所有命令都需要管理员权限）"  # 注: 描述 / EN: description / JP: 説明
            )
        },
        "github": {
            "username": ConfigField(  # 注: GitHub 用户名 / EN: github username / JP: GitHubユーザー名
                type=str,  # 注: 类型 / EN: type / JP: 型
                default="",  # 注: 默认空 / EN: default empty / JP: デフォルト
                description="GitHub用户名（用于显示和调试）"  # 注: 描述 / EN: description / JP: 説明
            ),
            "token": ConfigField(  # 注: GitHub Token / EN: github token / JP: GitHubトークン
                type=str,  # 注: 类型 / EN: type / JP: 型
                default="",  # 注: 默认空 / EN: default empty / JP: デフォルト
                description="GitHub Personal Access Token（获取地址：https://github.com/settings/tokens，只需要public_repo权限）"  # 注: 描述 / EN: description / JP: 説明
            )
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:  # 注: 注册插件组件 / EN: register components / JP: コンポーネント登録
        """注册插件组件"""  # 注: docstring / EN: docstring / JP: ドックストリング
        return [  # 注: 返回组件列表 / EN: return components / JP: コンポーネント返却
            (PluginManagerCommand.get_command_info(), PluginManagerCommand),  # 注: 命令组件 / EN: command component / JP: コマンドコンポーネント
        ]