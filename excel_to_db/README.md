# Excel导入工具

一个简单的Web应用程序，用于将Excel文件导入到PostgreSQL数据库中，并管理中间表。

## 功能特点

- 上传Excel文件并导入到PostgreSQL数据库
- 支持团油和智电两个主体的数据库连接
- 查看和删除已导入的中间表
- 用户认证，限制特定用户访问

## 安装与运行

### 本地运行

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 运行应用：

```bash
python excel_uploader.py
```

3. 在浏览器中访问：`http://localhost:8082`

### 服务器部署

#### 方法一：直接运行

1. 将代码上传到服务器：

```bash
# 使用scp或其他方式上传
scp -r excel_to_db/ user@your-server-ip:/path/to/destination/
```

2. 在服务器上安装依赖：

```bash
cd /path/to/destination/excel_to_db/
pip install -r requirements.txt
```

3. 使用nohup或screen在后台运行：

```bash
# 使用nohup
nohup python excel_uploader.py > app.log 2>&1 &

# 或使用screen
screen -S excel-app
python excel_uploader.py
# 按Ctrl+A然后按D来分离screen会话
```

#### 方法二：使用Systemd（推荐）

1. 创建systemd服务文件：

```bash
sudo nano /etc/systemd/system/excel-uploader.service
```

2. 添加以下内容：

```
[Unit]
Description=Excel Uploader Web Application
After=network.target

[Service]
User=your-username
WorkingDirectory=/path/to/destination/excel_to_db
ExecStart=/usr/bin/python3 excel_uploader.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. 启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable excel-uploader
sudo systemctl start excel-uploader
```

4. 查看服务状态：

```bash
sudo systemctl status excel-uploader
```

#### 方法三：使用Docker（可选）

1. 创建Dockerfile：

```
FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8082

CMD ["python", "excel_uploader.py"]
```

2. 构建并运行Docker镜像：

```bash
docker build -t excel-uploader .
docker run -d -p 8082:8082 --name excel-app excel-uploader
```

### 配置反向代理（可选）

如果您想通过域名访问应用，可以配置Nginx反向代理：

1. 安装Nginx：

```bash
sudo apt update
sudo apt install nginx
```

2. 创建Nginx配置文件：

```bash
sudo nano /etc/nginx/sites-available/excel-uploader
```

3. 添加以下内容：

```
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8082;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

4. 启用站点并重启Nginx：

```bash
sudo ln -s /etc/nginx/sites-available/excel-uploader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 用户管理

应用内置了用户认证功能，默认用户：

- 用户名: admin, 密码: admin123
- 用户名: shizhonghui, 密码: password123

要添加或修改用户，请编辑`excel_uploader.py`文件中的`AUTHORIZED_USERS`字典：

```python
AUTHORIZED_USERS = {
    'admin': 'admin123',  # 用户名: 密码
    'shizhonghui': 'password123',  # 可以添加更多用户
    'newuser': 'newpassword'  # 添加新用户
}
```

## 故障排除

1. 如果端口被占用，应用会自动尝试下一个端口
2. 如果数据库连接失败，请检查数据库配置
3. 如果上传失败，请确保Excel文件格式正确

## 联系方式

如有问题，请联系开发者。
