# laoyuan-code

一个基于 Python 标准库 + SQLite 的轻量后台管理系统示例，包含：

- 登录鉴权（默认账号 `admin` / `123456`）
- 仪表盘统计卡片
- 管理员用户管理（新增、列表、删除）
- 商品管理（新增、列表、删除）
- 基础输入校验（重复用户名、无效 JSON、负库存/价格拦截）

## 快速启动

```bash
python3 app.py
```

打开：<http://127.0.0.1:8000>

## API 列表

- `GET /api/stats` 统计数据
- `GET /api/users` 用户列表
- `POST /api/users` 新增用户
- `DELETE /api/users/<id>` 删除用户
- `GET /api/products` 商品列表
- `POST /api/products` 新增商品
- `DELETE /api/products/<id>` 删除商品
