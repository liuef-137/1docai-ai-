# DocAI 部署到 Render 详细步骤

## 前置准备

1. 一个 GitHub 账号（你的项目已上传到 `liuef-137/1docai-ai`）
2. 一个 Render 账号（免费注册：https://render.com）

---

## 第一步：推送代码到 GitHub

确保项目目录结构如下（`server/` 是 Flask 后端）：

```
docai-redesign/          ← Git 仓库根目录
├── render.yaml           ← Render 配置（自动读取）
├── .gitignore            ← 忽略敏感文件
├── assets/               ← 静态图片资源
├── colors_and_type.css   ← 品牌样式
├── pages/                ← 原始设计 HTML（不需要部署）
└── server/               ← Flask 后端
    ├── app.py            ← 应用入口
    ├── config.py         ← 配置
    ├── requirements.txt  ← Python 依赖
    ├── models.py
    ├── routes.py
    ├── auth.py
    ├── i18n_translations.py
    └── templates/        ← Jinja2 模板
```

在项目根目录执行：

```bash
cd docai-redesign
git init
git add .
git commit -m "prepare for Render deployment"
git remote add origin https://github.com/liuef-137/1docai-ai.git
git push -u origin main
```

> 如果已经关联过 remote，直接 `git push` 即可。

---

## 第二步：注册/登录 Render

1. 打开 https://render.com
2. 点击 **Sign Up**，选择 **Sign up with GitHub**
3. 授权 Render 访问你的 GitHub 仓库

---

## 第三步：创建 Web Service（推荐方式）

### 方式 A：使用 render.yaml 自动配置（推荐）

1. 登录 Render 后，点击 **Dashboard** → **New** → **Blueprint**
2. 选择你的 GitHub 仓库 `liuef-137/1docai-ai`
3. Render 会自动检测到 `render.yaml` 文件
4. 点击 **Apply**，确认配置
5. Render 会自动创建 Web Service 并开始构建

### 方式 B：手动创建 Web Service

1. 登录 Render 后，点击 **Dashboard** → **New** → **Web Service**
2. 连接你的 GitHub 账号，选择仓库 `liuef-137/1docai-ai`
3. 配置以下选项：

| 配置项 | 值 |
|--------|-----|
| **Name** | `docai`（会变成 `docai.onrender.com`） |
| **Runtime** | `Python 3` |
| **Root Directory** | 留空或填 `.` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn "wsgi:application" --bind 0.0.0.0:$PORT` |
| **Instance Type** | `Free` |

4. 点击 **Advanced**，添加环境变量：

| Key | Value | 说明 |
|-----|-------|------|
| `DEEPSEEK_API_KEY` | `sk-你的key` | **必填**，否则AI分析不可用 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 默认值 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 默认值 |
| `SECRET_KEY` | 随机长字符串 | 用于登录token加密，自行生成 |
| `ADMIN_PASSWORD` | 你想设的管理员密码 | 默认 admin123 |

5. 点击 **Create Web Service**

---

## 第四步：等待部署完成

- 构建大约需要 1-2 分钟
- 看到 **Live** 状态表示部署成功
- 访问 `https://docai.onrender.com` 即可打开网站

---

## 第五步：验证功能

部署完成后，测试以下功能：

1. 打开首页，确认页面正常显示
2. 点击 **注册**，创建一个新账号
3. 尝试粘贴合同文本进行分析
4. 点击右下角 Feedback 按钮提交反馈
5. 用 admin 账号登录后访问 `/admin` 查看后台

---

## 重要注意事项

### 免费计划的限制
- **15 分钟无请求会休眠**，首次访问需要等 30-50 秒冷启动
- 每月 750 小时免费额度
- **SQLite 数据库不持久**：每次部署会重置数据库，数据丢失
  - 解决方案：在 Render 后台添加免费 PostgreSQL，然后改环境变量 `DATABASE`

### 数据持久化（可选升级）

Zeabur/Render 等容器平台的本地 SQLite 文件不应作为生产数据源。请在平台绑定持久化 Volume，或配置外部 PostgreSQL，并将连接串设置为环境变量 `DATABASE`。不要在部署脚本中删除 `docai.db`，应用启动迁移只会添加缺失字段，不会清空已有用户、分析和反馈记录。

如果需要数据不丢失，添加免费 PostgreSQL：

1. Render Dashboard → **New** → **PostgreSQL**
2. 选择 Free 计划，创建数据库
3. 创建完成后，进入数据库的 **Settings**，找到 **Internal Database URL**
4. 回到 Web Service → **Environment**，添加：
   - Key: `DATABASE`
   - Value: `postgresql://用户名:密码@主机:5432/数据库名`（即 Internal Database URL 的值）
5. Render 会自动重启服务

### 自定义域名（可选）

1. 在你的域名服务商添加 CNAME 记录指向 `docai.onrender.com`
2. Render Web Service → **Settings** → **Custom Domain** → 添加你的域名
3. Render 自动配置 SSL 证书

### 修改代码后重新部署

- Push 到 GitHub 的 `main` 分支会自动触发重新部署
- 或者在 Render 控制台手动点击 **Manual Deploy** → **Deploy latest commit**

---

## 常见问题

**Q: 部署失败 "Module not found"**
A: 检查 Root Directory 是否为项目根目录，Build Command 是否正确。

**Q: 访问网站显示 502**
A: 查看 Render 的 Logs，通常是 Start Command 配置错误。确认为 `gunicorn "wsgi:application" --bind 0.0.0.0:$PORT`

**Q: AI 分析报错**
A: 检查环境变量 `DEEPSEEK_API_KEY` 是否正确设置。

**Q: 登录后数据丢失**
A: 免费 SQLite 每次部署会重置，改用 PostgreSQL（见上文）。
