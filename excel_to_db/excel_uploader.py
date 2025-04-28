#!/usr/bin/env python3
"""
Excel数据上传与中间表管理系统
支持Excel文件上传并自动创建数据库表
"""

import os
import sys
import urllib.parse
import html
import json
import time
import uuid
import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse
import cgi
import tempfile
import shutil
import base64
from functools import wraps

# 配置
PORT = 8082
UPLOAD_FOLDER = 'uploads'
# 上传的表前缀，用于识别应用上传的表
TABLE_PREFIX = 'excel_upload_'

# 授权用户列表
AUTHORIZED_USERS = {
    'admin': 'admin123',  # 用户名: 密码
    'shizhonghui': 'password123'  # 可以添加更多用户
}

# 会话存储
sessions = {}

# 数据库配置
DB_CONFIGS = {
    'tuanyou': {
        'dbname': 'newlink',
        'user': 'dws_finance_rw',
        'password': 'e8jtA9QYNFtUnFch',
        'host': '10.61.11.179',
        'port': '8000'
    },
    'zhidian': {
        'dbname': 'newlink',
        'user': 'shizhonghui_r',
        'password': r'VQqEPa4otgjt^jB2',  # 使用原始字符串处理特殊字符
        'host': '10.65.5.206',
        'port': '8000'
    }
}

# 当前选择的数据库配置
CURRENT_DB = 'tuanyou'

# 创建上传文件夹
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 获取数据库连接
def get_db_connection():
    config = DB_CONFIGS[CURRENT_DB]
    print(f"正在连接数据库: {CURRENT_DB}")
    print(f"数据库配置: {config['host']}:{config['port']}, 用户: {config['user']}")
    try:
        conn = psycopg2.connect(**config)
        print(f"数据库连接成功: {CURRENT_DB}")
        return conn
    except Exception as e:
        print(f"数据库连接错误: {str(e)}")
        raise

# 获取所有表
def get_all_tables():
    tables = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 只获取带有特定前缀的表
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'finance' 
            AND table_name LIKE %s
            ORDER BY table_name
        """, (f'{TABLE_PREFIX}%',))
        
        tables = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"获取表列表错误: {e}")
    
    return tables

# 获取表结构
def get_table_schema(table_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 确保表名包含前缀
    if not table_name.startswith(TABLE_PREFIX):
        table_name = f"{TABLE_PREFIX}{table_name}"
    
    cursor.execute(f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'finance' AND table_name = '{table_name}'
        ORDER BY ordinal_position
    """)
    
    schema = [{"name": row[0], "type": row[1]} for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    return schema

# 获取表数据
def get_table_data(table_name, limit=100):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # 确保表名包含前缀
    if not table_name.startswith(TABLE_PREFIX):
        table_name = f"{TABLE_PREFIX}{table_name}"
    
    cursor.execute(f"SELECT * FROM finance.{table_name} LIMIT {limit}")
    data = [dict(row) for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    return data

# 删除表
def delete_table(table_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    success = False
    
    try:
        # 如果表名不包含前缀，添加前缀
        if not table_name.startswith(TABLE_PREFIX):
            table_name = f"{TABLE_PREFIX}{table_name}"
            
        cursor.execute(f"DROP TABLE IF EXISTS finance.{table_name}")
        conn.commit()
        success = True
    except Exception as e:
        print(f"删除表错误: {e}")
        conn.rollback()
        success = False
    
    cursor.close()
    conn.close()
    return success

# 从Excel导入数据
def import_from_excel(file_path, table_name, entity='tuanyou'):
    try:
        # 设置当前数据库配置
        global CURRENT_DB
        CURRENT_DB = entity
        
        # 读取Excel文件
        df = pd.read_excel(file_path)
        
        # 连接数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 添加表前缀
        prefixed_table_name = f"{TABLE_PREFIX}{table_name}"
        
        # 检查表是否已存在，如果存在则先删除
        cursor.execute(f"DROP TABLE IF EXISTS finance.{prefixed_table_name}")
        
        # 创建表
        columns = []
        for col in df.columns:
            # 清理列名，移除或替换不合法字符
            clean_col = str(col).strip().replace(' ', '_').replace('-', '_')
            
            # 确定数据类型
            sample_data = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
            
            if pd.api.types.is_integer_dtype(df[col].dtype):
                pg_type = "INTEGER"
            elif pd.api.types.is_float_dtype(df[col].dtype):
                pg_type = "NUMERIC"
            elif pd.api.types.is_datetime64_dtype(df[col].dtype):
                pg_type = "TIMESTAMP"
            else:
                pg_type = "TEXT"
            
            columns.append(f'"{clean_col}" {pg_type}')
        
        # 创建表SQL
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS finance.{prefixed_table_name} (
            {', '.join(columns)}
        )
        """
        
        cursor.execute(create_table_sql)
        
        # 准备插入数据
        # 清理列名
        clean_columns = [str(col).strip().replace(' ', '_').replace('-', '_') for col in df.columns]
        
        # 重命名DataFrame列以匹配清理后的列名
        df.columns = clean_columns
        
        placeholders = ', '.join(['%s'] * len(df.columns))
        column_names = ', '.join([f'"{col}"' for col in clean_columns])
        
        # 插入SQL
        insert_sql = f"""
        INSERT INTO finance.{prefixed_table_name} ({column_names})
        VALUES ({placeholders})
        """
        
        # 批量插入数据
        for _, row in df.iterrows():
            # 处理NaN值，将其转换为None
            values = []
            for val in row:
                if pd.isna(val):
                    values.append(None)
                else:
                    values.append(val)
            
            cursor.execute(insert_sql, tuple(values))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True, "数据导入成功"
    except Exception as e:
        print(f"导入Excel错误: {e}")
        # 尝试关闭连接
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass
        return False, f"导入Excel错误: {str(e)}"

# 主页HTML
def get_index_html(message=None):
    tables = get_all_tables()
    tables_html = ""
    
    if tables:
        for table in tables:
            # 显示时去掉前缀
            display_name = table[len(TABLE_PREFIX):] if table.startswith(TABLE_PREFIX) else table
            tables_html += f'''
            <tr>
                <td>{html.escape(display_name)}</td>
                <td>
                    <a href="/view_table?name={urllib.parse.quote(table)}" class="btn btn-sm btn-info">查看</a>
                    <form method="post" action="/delete_table" style="display:inline;">
                        <input type="hidden" name="table_name" value="{html.escape(table)}">
                        <button type="submit" class="btn btn-sm btn-danger" onclick="return confirm('确定要删除表 {html.escape(display_name)} 吗?');">删除</button>
                    </form>
                </td>
            </tr>
            '''
    else:
        tables_html = '<tr><td colspan="2" class="text-center">暂无中间表，请上传 Excel 文件创建表</td></tr>'
    
    return f'''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Excel导入工具</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ background-color: #f8f9fa; }}
            .card {{ box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-radius: 8px; overflow: hidden; margin-bottom: 20px; }}
            .form-card {{ background-color: white; }}
            .table-card {{ background-color: white; }}
            .navbar {{ background-color: #0d6efd; }}
            .navbar-brand {{ color: white; }}
            .logout-link {{ color: rgba(255,255,255,0.8); text-decoration: none; float: right; margin-top: 8px; }}
            .logout-link:hover {{ color: white; }}
        </style>
    </head>
    <body>
        <div class="container mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2>Excel导入工具</h2>
                <a href="/logout" class="btn btn-outline-primary">退出登录</a>
            </div>
            
            {f'<div class="alert alert-info">{message}</div>' if message else ''}
            
            <div class="row">
                <div class="col-md-5">
                    <div class="card form-card">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0">上传Excel文件</h5>
                        </div>
                        <div class="card-body">
                            <form action="/upload" method="post" enctype="multipart/form-data">
                                <div class="mb-3">
                                    <label for="file" class="form-label">选择Excel文件</label>
                                    <input type="file" class="form-control" id="file" name="file" accept=".xls,.xlsx" required>
                                </div>
                                <div class="mb-3">
                                    <label for="table_name" class="form-label">表名（可选）</label>
                                    <input type="text" class="form-control" id="table_name" name="table_name" placeholder="留空将使用文件名">
                                </div>
                                <div class="mb-3">
                                    <label for="entity" class="form-label">主体</label>
                                    <select class="form-select" id="entity" name="entity">
                                        <option value="tuanyou">团油</option>
                                        <option value="zhidian">智电</option>
                                    </select>
                                </div>
                                <button type="submit" class="btn btn-primary">上传并导入</button>
                            </form>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-7">
                    <div class="card table-card">
                        <div class="card-header bg-info text-white">
                            <h5 class="mb-0">中间表列表</h5>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-striped">
                                    <thead>
                                        <tr>
                                            <th>表名</th>
                                            <th>操作</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {tables_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    '''

# 查看表HTML
def get_view_table_html(table_name):
    # 确保表名包含前缀
    if not table_name.startswith(TABLE_PREFIX):
        table_name = f"{TABLE_PREFIX}{table_name}"
        
    schema = get_table_schema(table_name)
    data = get_table_data(table_name)
    
    # 显示时去掉前缀
    display_name = table_name[len(TABLE_PREFIX):] if table_name.startswith(TABLE_PREFIX) else table_name
    
    columns_html = ""
    for col in schema:
        columns_html += f'<th>{html.escape(col["name"])}</th>'
    
    rows_html = ""
    for row in data:
        rows_html += "<tr>"
        for col in schema:
            col_name = col["name"]
            cell_value = row.get(col_name, "")
            rows_html += f'<td>{html.escape(str(cell_value))}</td>'
        rows_html += "</tr>"
    
    return f'''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>查看表 - {html.escape(display_name)}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ background-color: #f8f9fa; }}
            .card {{ box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); border-radius: 8px; overflow: hidden; margin-bottom: 20px; }}
            .table-responsive {{ max-height: 600px; overflow-y: auto; }}
            .btn-back {{ margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="container mt-5">
            <a href="/" class="btn btn-primary btn-back">返回首页</a>
            
            <div class="card">
                <div class="card-header bg-info text-white">
                    <h5 class="mb-0">表 {html.escape(display_name)} 数据</h5>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-striped table-bordered">
                            <thead>
                                <tr>
                                    {columns_html}
                                </tr>
                            </thead>
                            <tbody>
                                {rows_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''

# 错误HTML
def get_error_html(message):
    return f'''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>出错了!</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ background-color: #f8f9fa; }}
            .error-card {{ 
                max-width: 600px; 
                margin: 100px auto; 
                padding: 20px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            .error-header {{ 
                background-color: #dc3545; 
                color: white; 
                padding: 20px;
                font-size: 24px;
            }}
            .error-body {{ padding: 30px; }}
            .btn-home {{ margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error-card">
                <div class="error-header">
                    出错了!
                </div>
                <div class="error-body">
                    <p class="lead">{html.escape(message)}</p>
                    <a href="/" class="btn btn-primary btn-home">返回首页</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(self, *args, **kwargs):
        if 'username' not in self.session:
            self._set_headers(HTTPStatus.FOUND)
            self.send_header('Location', '/login')
            self.end_headers()
            return
        return f(self, *args, **kwargs)
    return decorated_function

# HTTP请求处理器
class RequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status_code=HTTPStatus.OK, content_type='text/html'):
        self.send_response(status_code)
        self.send_header('Content-type', f'{content_type}; charset=utf-8')
        # 如果有Cookie需要设置，在这里设置
        if hasattr(self, 'cookie_to_set'):
            self.send_header('Set-Cookie', self.cookie_to_set)
            delattr(self, 'cookie_to_set')
        self.end_headers()
    
    def _get_session(self):
        # 从Cookie中获取会话ID
        cookies = {}
        if 'Cookie' in self.headers:
            raw_cookies = self.headers['Cookie']
            for cookie in raw_cookies.split(';'):
                if '=' in cookie:
                    name, value = cookie.strip().split('=', 1)
                    cookies[name] = value
        
        session_id = cookies.get('session_id')
        if session_id and session_id in sessions:
            return sessions[session_id]
        
        # 创建新会话
        session_id = str(uuid.uuid4())
        sessions[session_id] = {'id': session_id}
        # 注意：这里不设置Cookie头，而是在响应发送前设置
        self.cookie_to_set = f'session_id={session_id}; Path=/'
        return sessions[session_id]
    
    def _check_auth(self):
        session = self._get_session()
        return session.get('authenticated', False)
    
    def _redirect(self, location):
        self.send_response(HTTPStatus.FOUND)
        self.send_header('Location', location)
        # 确保在重定向之前完成所有头部设置
        self.end_headers()
        # 添加一些HTML内容，以防浏览器不自动重定向
        self.wfile.write(f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="refresh" content="0;url={location}">
            <title>重定向</title>
        </head>
        <body>
            <p>正在重定向到 <a href="{location}">{location}</a>...</p>
        </body>
        </html>
        '''.encode())
    
    def do_GET(self):
        try:
            # 解析URL
            parsed_url = urllib.parse.urlparse(self.path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)
            
            # 静态文件请求
            if path.startswith('/static/'):
                file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path[1:])
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    with open(file_path, 'rb') as file:
                        content = file.read()
                    
                    # 设置内容类型
                    if path.endswith('.css'):
                        self._set_headers(content_type='text/css')
                    elif path.endswith('.js'):
                        self._set_headers(content_type='application/javascript')
                    elif path.endswith('.png'):
                        self._set_headers(content_type='image/png')
                    elif path.endswith('.jpg') or path.endswith('.jpeg'):
                        self._set_headers(content_type='image/jpeg')
                    else:
                        self._set_headers()
                    
                    self.wfile.write(content)
                    return
            
            # 登录页面
            if path == '/login':
                self._set_headers()
                self.wfile.write(get_login_html().encode())
                return
            
            # 检查认证（除了登录页面和静态资源外）
            if not self._check_auth():
                self.send_response(HTTPStatus.FOUND)
                self.send_header('Location', '/login')
                # 如果有Cookie需要设置，在这里设置
                if hasattr(self, 'cookie_to_set'):
                    self.send_header('Set-Cookie', self.cookie_to_set)
                    delattr(self, 'cookie_to_set')
                self.end_headers()
                
                # 添加HTML内容以确保重定向
                self.wfile.write(f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta http-equiv="refresh" content="0;url=/login">
                    <title>重定向到登录</title>
                </head>
                <body>
                    <p>请先登录，正在重定向到 <a href="/login">登录页面</a>...</p>
                </body>
                </html>
                '''.encode())
                return
            
            # 处理其他请求
            if path == '/':
                self._set_headers()
                self.wfile.write(get_index_html().encode())
            
            elif path == '/view_table':
                table_name = query.get('name', [''])[0]
                if not table_name:
                    self._set_headers(HTTPStatus.BAD_REQUEST)
                    self.wfile.write(get_error_html('缺少表名参数').encode())
                    return
                
                self._set_headers()
                self.wfile.write(get_view_table_html(table_name).encode())
            
            elif path == '/logout':
                # 获取当前会话
                session = self._get_session()
                session_id = session.get('id')
                
                # 清除会话数据
                if session_id in sessions:
                    del sessions[session_id]
                
                # 发送响应，设置过期的Cookie
                self.send_response(HTTPStatus.FOUND)
                self.send_header('Location', '/login')
                self.send_header('Set-Cookie', 'session_id=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT')
                self.end_headers()
                
                # 添加HTML内容以确保重定向
                self.wfile.write(f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta http-equiv="refresh" content="0;url=/login">
                    <title>登出成功</title>
                </head>
                <body>
                    <p>登出成功，正在重定向到 <a href="/login">登录页面</a>...</p>
                </body>
                </html>
                '''.encode())
                return
            
            else:
                self._set_headers(HTTPStatus.NOT_FOUND)
                self.wfile.write(get_error_html('页面不存在').encode())
        
        except Exception as e:
            self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.wfile.write(get_error_html(f'服务器错误: {str(e)}').encode())
    
    def do_POST(self):
        try:
            # 解析URL
            parsed_url = urllib.parse.urlparse(self.path)
            path = parsed_url.path
            
            # 处理登录请求
            if path == '/login':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode('utf-8')
                form_data = urllib.parse.parse_qs(post_data)
                
                username = form_data.get('username', [''])[0]
                password = form_data.get('password', [''])[0]
                
                if username in AUTHORIZED_USERS and AUTHORIZED_USERS[username] == password:
                    # 登录成功，设置会话
                    session = self._get_session()
                    session['authenticated'] = True
                    session['username'] = username
                    
                    # 发送响应前设置Cookie
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header('Location', '/')
                    self.send_header('Set-Cookie', f'session_id={session["id"]}; Path=/')
                    self.end_headers()
                    
                    # 添加HTML内容以确保重定向
                    self.wfile.write(f'''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta http-equiv="refresh" content="0;url=/">
                        <title>登录成功</title>
                    </head>
                    <body>
                        <p>登录成功，正在重定向到 <a href="/">首页</a>...</p>
                    </body>
                    </html>
                    '''.encode())
                else:
                    # 登录失败
                    self._send_html(get_login_html("用户名或密码错误"))
                return
            
            # 检查认证（除了登录请求外）
            if not self._check_auth():
                self._redirect('/login')
                return
            
            # 处理其他POST请求
            if path == '/upload':
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST'}
                )
                
                # 检查是否有文件上传
                if 'file' not in form:
                    self._set_headers()
                    self.wfile.write(get_index_html("请选择文件").encode())
                    return
                
                fileitem = form['file']
                
                # 检查是否有文件名
                if not fileitem.filename:
                    self._set_headers()
                    self.wfile.write(get_index_html("请选择文件").encode())
                    return
                
                # 检查文件类型
                if not fileitem.filename.endswith(('.xls', '.xlsx')):
                    self._set_headers()
                    self.wfile.write(get_index_html("请上传Excel文件 (.xls 或 .xlsx)").encode())
                    return
                
                # 获取表名
                table_name = form.getvalue('table_name', '').strip()
                if not table_name:
                    # 如果没有提供表名，使用文件名（不包括扩展名）
                    table_name = os.path.splitext(fileitem.filename)[0]
                
                # 获取主体
                entity = form.getvalue('entity', 'tuanyou')
                
                # 确保上传目录存在
                if not os.path.exists(UPLOAD_FOLDER):
                    os.makedirs(UPLOAD_FOLDER)
                
                # 保存文件
                file_path = os.path.join(UPLOAD_FOLDER, fileitem.filename)
                with open(file_path, 'wb') as f:
                    f.write(fileitem.file.read())
                
                # 导入数据
                success, message = import_from_excel(file_path, table_name, entity)
                
                self._set_headers()
                self.wfile.write(get_index_html(message).encode())
            
            elif path == '/delete_table':
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={'REQUEST_METHOD': 'POST'}
                )
                
                table_name = form.getvalue('table_name', '')
                
                if not table_name:
                    self._set_headers(HTTPStatus.BAD_REQUEST)
                    self.wfile.write(get_error_html('缺少表名参数').encode())
                    return
                
                try:
                    success = delete_table(table_name)
                    
                    if success:
                        self._set_headers()
                        self.wfile.write(get_index_html(f"表 {table_name} 已删除").encode())
                    else:
                        self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
                        self.wfile.write(get_error_html(f'删除表 {table_name} 失败').encode())
                except Exception as e:
                    self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
                    self.wfile.write(get_error_html(f'删除表错误: {str(e)}').encode())
            
            elif path == '/logout':
                session = self._get_session()
                if 'username' in session:
                    del session['username']
                self._redirect('/login')
            
            else:
                self._set_headers(HTTPStatus.NOT_FOUND)
                self.wfile.write(get_error_html('页面不存在').encode())
        
        except Exception as e:
            self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.wfile.write(get_error_html(f'服务器错误: {str(e)}').encode())

# 登录页面
def get_login_html(error=None):
    return f'''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>登录 - Excel导入工具</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ background-color: #f8f9fa; }}
            .login-container {{ 
                max-width: 400px; 
                margin: 100px auto; 
                padding: 20px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            .login-header {{ 
                text-align: center; 
                margin-bottom: 20px;
                color: #0d6efd;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="login-container">
                <div class="login-header">
                    <h2>Excel导入工具</h2>
                    <p class="text-muted">请登录以继续</p>
                </div>
                
                <form method="post" action="/login">
                    <div class="mb-3">
                        <label for="username" class="form-label">用户名</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">密码</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary">登录</button>
                    </div>
                    {f'<p class="text-danger">{error}</p>' if error else ''}
                </form>
            </div>
        </div>
    </body>
    </html>
    '''

# 运行服务器
def run_server():
    PORT = 8082
    MAX_PORT_ATTEMPTS = 10
    
    for port_attempt in range(PORT, PORT + MAX_PORT_ATTEMPTS):
        try:
            server_address = ('0.0.0.0', port_attempt)  # 绑定到所有网络接口，允许外部访问
            httpd = HTTPServer(server_address, RequestHandler)
            print(f'服务器已启动，访问 http://localhost:{port_attempt}')
            print(f'要从其他设备访问，请使用 http://你的IP地址:{port_attempt}')
            httpd.serve_forever()
            break
        except OSError as e:
            if e.errno == 48:  # Address already in use
                print(f"端口 {port_attempt} 已被占用，尝试下一个端口...")
                if port_attempt == PORT + MAX_PORT_ATTEMPTS - 1:
                    print("无法找到可用端口，请手动关闭占用端口的程序后重试。")
                    sys.exit(1)
            else:
                print(f"启动服务器时出错: {e}")
                sys.exit(1)

if __name__ == '__main__':
    # 确保上传目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    run_server()
