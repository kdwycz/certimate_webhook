"""SSL证书同步模块 - 使用Ansible Runner和静态playbook文件"""

from pathlib import Path
from typing import Dict

import ansible_runner
from loguru import logger

from config import AppConfig, PlaybookMapping, ServerGroup


class SSLSyncer:
    """SSL证书同步器 - 使用静态playbook文件，无临时文件"""

    def __init__(self, app_config: AppConfig):
        # 保存配置引用
        self.app_config = app_config
        
        # 获取playbook目录路径
        self.playbook_dir = Path(__file__).parent / "playbooks"

    def sync_ssl_certificate(
        self,
        key: str,
        playbook_config: PlaybookMapping,
        server_groups: Dict[str, ServerGroup],
    ) -> bool:
        """同步SSL证书到服务器组"""
        try:
            logger.info(f"开始同步key {key} 的SSL证书")

            # 验证playbook文件存在
            playbook_path = self.playbook_dir / playbook_config.playbook_file
            if not playbook_path.exists():
                raise FileNotFoundError(f"Playbook文件不存在: {playbook_path}")

            # 为每个服务器组执行同步
            for group_name, server_group in server_groups.items():
                if not self._sync_to_server_group(
                    playbook_config, server_group, group_name, playbook_path
                ):
                    return False

            logger.info(f"key {key} SSL证书同步完成")
            return True

        except Exception as e:
            logger.error(f"同步SSL证书失败: {e}")
            return False

    def _sync_to_server_group(
        self, playbook_config: PlaybookMapping, server_group: ServerGroup, group_name: str, playbook_path: Path
    ) -> bool:
        """同步证书到指定服务器组 - 使用配置化playbook"""
        try:
            # 创建inventory字典
            inventory_content = self._create_inventory_dict(server_group)
            
            # 从PlaybookMapping中提取所有var_开头的变量
            extra_vars = playbook_config.get_ansible_vars()

            # 使用ansible-runner执行指定的playbook
            result = ansible_runner.run(
                playbook=str(playbook_path),
                inventory=inventory_content,
                extravars=extra_vars,
                ssh_key=server_group.ssh_key_path,
                quiet=False,
                verbosity=1,
            )

            if result.status == "successful":
                logger.info(f"服务器组 {group_name} SSL证书同步成功")
                return True
            else:
                logger.error(f"服务器组 {group_name} SSL证书同步失败")
                logger.error(f"返回码: {getattr(result, 'rc', 'unknown')}")
                
                # 安全地获取输出信息
                try:
                    stdout_attr = getattr(result, "stdout", None)
                    if stdout_attr and hasattr(stdout_attr, "read"):
                        stdout_content = stdout_attr.read()
                        if stdout_content:
                            logger.error(f"输出信息: {stdout_content}")
                except Exception:
                    pass
                
                # 安全地遍历事件
                try:
                    events = getattr(result, "events", [])
                    for event in events:
                        if (
                            isinstance(event, dict)
                            and event.get("event") == "runner_on_failed"
                        ):
                            logger.error(f"任务失败详情: {event.get('event_data', {})}")
                except Exception:
                    pass
                return False

        except Exception as e:
            logger.error(f"服务器组 {group_name} SSL证书同步异常: {e}")
            return False

    def _create_inventory_dict(self, server_group: ServerGroup) -> dict:
        """创建Ansible inventory字典"""
        inventory = {"ssl_servers": {"hosts": {}}}

        for host in server_group.hosts:
            host_config = {}
            
            # 只有配置了非默认端口才添加端口配置
            if server_group.ssh_port != 22:
                host_config["ansible_port"] = server_group.ssh_port
            
            # 只有明确配置了用户名才添加用户配置
            if server_group.ssh_user:
                host_config["ansible_user"] = server_group.ssh_user
            
            # 只有明确配置了密钥路径才添加密钥配置
            if server_group.ssh_key_path:
                host_config["ansible_ssh_private_key_file"] = server_group.ssh_key_path
            
            # 只有明确配置了密码才添加密码配置
            if server_group.ssh_pass:
                host_config["ansible_ssh_pass"] = server_group.ssh_pass
            
            inventory["ssl_servers"]["hosts"][host] = host_config

        return inventory


    def cleanup_temp_files(self):
        """清理临时文件 - 无需操作"""
        # 使用静态playbook文件，无需清理
        logger.debug("使用静态playbook文件，无需清理临时文件")
