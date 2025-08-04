# SSL证书Webhook自动同步服务

简洁高效的SSL证书自动同步服务，遵循DRY和KISS原则设计。

## 功能特性

- 🚀 **简单高效**: 基于FastAPI的轻量级webhook服务
- 🔒 **安全可靠**: 使用Ansible进行证书同步，支持SSH密钥认证
- 🛡️ **安全机制**: 可配置的webhook路径
- 📊 **灵活配置**: YAML配置文件，支持多服务器组和域名映射
- 🔄 **自动部署**: Supervisor进程管理，自动重启和监控
- 📝 **详细日志**: 基于loguru的结构化日志记录，supervisor处理轮转
- 🏃 **异步处理**: 后台任务处理，不阻塞webhook响应
- 🌐 **通用兼容**: 支持Nginx、Apache、HAProxy等多种Web服务器

## 技术栈

- **Python 3.13** - 现代Python版本
- **uv** - 快速Python包管理器
- **FastAPI** - 高性能Web框架
- **Ansible Runner** - Python Ansible API集成
- **Loguru** - 优雅的日志库
- **Supervisor** - 进程管理器
- **Ruff** - 代码格式化和检查

## 快速开始

### 1. 环境准备

```bash
# 安装uv包管理器
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装supervisor
sudo apt-get update
sudo apt-get install supervisor
```

### 2. 项目设置

```bash
# 克隆或进入项目目录
cd certimate_webhook

# 安装依赖
uv sync

# 复制配置文件
cp config.yml.sample config.yml

# 编辑配置文件
vim config.yml
```

### 3. 部署服务

```bash
# 复制supervisor配置
sudo cp supervisor.conf /etc/supervisor/conf.d/certimate_webhook.conf

# 更新supervisor配置（根据实际项目路径修改）
sudo sed -i 's|/home/ubuntu/projects/certimate_webhook|'$(pwd)'|g' /etc/supervisor/conf.d/certimate_webhook.conf

# 重新加载supervisor配置
sudo supervisorctl reread
sudo supervisorctl update

# 启动服务
sudo supervisorctl start certimate_webhook
```

### 4. 测试webhook

```bash
# 健康检查
curl http://localhost:8080/health

# 测试SSL更新
curl -X POST 'http://localhost:8080/cert-sync/your-path' \
  -H "Content-Type: application/json" \
  -d '{"name": "example.com"}'
```

### 配置文件结构

```yaml
# 服务器配置
server:
  host: "0.0.0.0"
  port: 8080
  log_level: "INFO"
  webhook_path: "cert-sync/your-secure-path"
  playbook_file: "ssl_sync.yml"  # 可自定义playbook文件名

# 服务器组配置
server_groups:
  - name: "服务器组名称"
    hosts: ["服务器IP列表"]
    ssh_user: "SSH用户名"
    ssh_key_path: "SSH私钥路径"

# 域名映射配置
domain_mappings:
  - domain: "域名"
    server_groups: ["服务器组列表"]
    ssl_source_path: "SSL证书源路径"
    ssl_target_path: "目标服务器SSL路径"
    reload_cmd: "服务重载命令（支持Nginx、Apache、HAProxy等）"
```

## API接口

### 健康检查

```bash
GET /health
```

### SSL证书更新

```bash
POST /{webhook_path}
Content-Type: application/json

{
  "name": "域名"
}
```

## 服务管理

```bash
# 查看状态
sudo supervisorctl status certimate_webhook

# 启动服务
sudo supervisorctl start certimate_webhook

# 停止服务
sudo supervisorctl stop certimate_webhook

# 重启服务
sudo supervisorctl restart certimate_webhook

# 查看日志
sudo tail -f /var/log/supervisor/certimate_webhook.log

# 手动运行（调试用）
uv run main.py
```

## 目录结构

```
certimate_webhook/
├── main.py              # 主程序
├── config.py            # 配置管理
├── sync.py              # SSL同步模块  
├── config.yml           # 配置文件（从sample复制）
├── config.yml.sample    # 配置文件模板
├── pyproject.toml       # 项目配置和依赖
├── supervisor.conf      # Supervisor配置
├── playbooks/           # Ansible playbook文件
│   └── ssl_sync.yml     # SSL证书同步playbook
├── CLAUDE.md           # Claude Code工作指南
└── README.md           # 说明文档
```

## 注意事项

1. **SSH密钥**: 确保webhook服务器能够SSH免密登录到目标服务器
2. **证书路径**: 确保SSL证书源路径存在且可读
3. **权限配置**: 目标服务器需要适当的文件权限和Web服务重载权限
4. **网络连通**: 确保webhook服务器与目标服务器网络连通
5. **防火墙**: 开放webhook监听端口(默认8080)
6. **依赖管理**: 使用uv管理Python依赖，ansible-runner会自动处理Ansible集成

## 自定义Playbook

你可以创建自己的Ansible playbook来定制SSL证书同步过程：

1. **创建自定义playbook**：
   ```bash
   # 在playbooks目录下创建自定义playbook
   cp playbooks/ssl_sync.yml playbooks/my_ssl_sync.yml
   vim playbooks/my_ssl_sync.yml
   ```

2. **修改配置文件**：
   ```yaml
   server:
     playbook_file: "my_ssl_sync.yml"  # 使用自定义playbook
   ```

3. **可用变量**：
   - `{{ ssl_source_path }}`: SSL证书源路径
   - `{{ ssl_target_path }}`: SSL证书目标路径  
   - `{{ ssl_target_parent_dir }}`: 目标路径的父目录
   - `{{ reload_cmd }}`: 服务重载命令

4. **自定义示例**：
   ```yaml
   ---
   - name: 自定义SSL证书同步
     hosts: ssl_servers
     become: yes
     tasks:
       - name: 停止服务
         service:
           name: nginx
           state: stopped
           
       - name: 备份旧证书
         archive:
           path: "{{ ssl_target_path }}"
           dest: "{{ ssl_target_path }}.backup.{{ ansible_date_time.epoch }}.tar.gz"
           
       - name: 复制新证书
         copy:
           src: "{{ ssl_source_path }}/"
           dest: "{{ ssl_target_path }}/"
           
       - name: 启动服务
         service:
           name: nginx
           state: started
   ```

## 故障排查

1. **查看supervisor日志**: `sudo tail -f /var/log/supervisor/certimate_webhook.log`
2. **检查服务状态**: `sudo supervisorctl status certimate_webhook`
3. **测试SSH连接**: `ssh -i ~/.ssh/id_rsa user@target-server`
4. **手动测试服务**: `uv run main.py`
5. **检查配置文件**: `uv run python -c "from config import app_config; print('配置加载成功')"`
6. **测试依赖安装**: `uv run python -c "import ansible_runner; print('ansible-runner已安装')"`