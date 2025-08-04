"""配置管理模块 - 遵循KISS原则的简单配置"""

from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field


class ServerGroup(BaseModel):
    """服务器组配置"""

    name: str
    hosts: List[str] = Field(description="服务器IP或主机名列表")
    ssh_user: str = Field(default="", description="SSH用户名（可选，使用系统SSH配置）")
    ssh_key_path: str = Field(default="", description="SSH私钥路径（可选，使用系统SSH配置）")
    ssh_pass: str = Field(default="", description="SSH密码（可选，不建议在生产环境使用）")
    ssh_port: int = Field(default=22, description="SSH端口号")


class PlaybookMapping(BaseModel):
    """Playbook映射配置"""

    key: str = Field(description="证书标识符（可以是域名、服务名等）")
    server_groups: List[str] = Field(description="对应的服务器组名称")
    playbook_file: str = Field(description="使用的playbook文件名")
    
    # 支持任意var_开头的动态变量
    model_config = {"extra": "allow"}
    
    def get_ansible_vars(self) -> dict:
        """提取所有var_开头的变量作为ansible变量"""
        ansible_vars = {}
        for field_name, field_value in self.model_dump().items():
            if field_name.startswith("var_"):
                # 去掉var_前缀作为ansible变量名
                var_name = field_name[4:]  # 去掉"var_"前缀
                ansible_vars[var_name] = field_value
        return ansible_vars


class ServerConfig(BaseModel):
    """服务器配置"""

    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=8080, description="监听端口")
    log_level: str = Field(default="INFO", description="日志级别")
    webhook_path: str = Field(description="Webhook路径")
    playbook_file: str = Field(default="ssl_sync.yml", description="Ansible playbook文件名")


class AppConfig:
    """应用配置管理器 - 简单直接"""

    def __init__(self, config_file: str = "config.yml"):
        self.config_file = Path(config_file)
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if not self.config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_file}")

        with open(self.config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 加载服务器配置（包括webhook配置）
        server_data = data.get("server", {})
        # 合并webhook配置到server配置中
        webhook_data = data.get("webhook", {})
        if webhook_data.get("path"):
            server_data["webhook_path"] = webhook_data["path"]
        self.server = ServerConfig(**server_data)

        # 加载服务器组配置
        self.server_groups = {
            sg["name"]: ServerGroup(**sg) for sg in data.get("server_groups", [])
        }

        # 加载playbook映射配置
        self.playbook_mappings = [
            PlaybookMapping(**pm) for pm in data.get("playbook_mappings", [])
        ]

    def find_playbook_config(self, key: str) -> PlaybookMapping | None:
        """根据key查找playbook配置"""
        return next((pm for pm in self.playbook_mappings if pm.key == key), None)

    def get_servers_for_key(self, key: str) -> Dict[str, ServerGroup]:
        """获取key对应的服务器组"""
        playbook_config = self.find_playbook_config(key)
        if not playbook_config:
            return {}

        return {
            group_name: self.server_groups[group_name]
            for group_name in playbook_config.server_groups
            if group_name in self.server_groups
        }


# 全局配置实例
app_config = AppConfig()
