#!/usr/bin/env bash
# AI 报销审核台 · 一键部署（Ubuntu 22.04，全新机器）
#
# 用法：
#   1) 把代码包传上去：scp -r ai-invoice.tar.gz root@<IP>:/root/
#   2) 解包并执行：
#        mkdir -p /opt/ai-invoice && tar -xzf /root/ai-invoice.tar.gz -C /opt/ai-invoice --strip-components=1
#        bash /opt/ai-invoice/deploy/bootstrap.sh
#
# 脚本是幂等的：重复执行不会把已有的数据库和上传文件冲掉。

set -euo pipefail

APP_DIR=/opt/ai-invoice
APP_USER=aiinvoice
LOG_DIR=/var/log/ai-audit
NODE_VERSION=v20.18.0

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[注意] %s\033[0m\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "请用 root 执行（或 sudo bash $0）"; exit 1; }
[[ -d "$APP_DIR/backend" ]] || { echo "找不到 $APP_DIR/backend，先解包代码"; exit 1; }

# ---------------------------------------------------------------- 1. 系统依赖
say "安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip nginx curl xz-utils >/dev/null
python3 --version

# ---------------------------------------------------------------- 2. Node 20
# 用官方二进制包，不引第三方 apt 源：香港节点拉 nodejs.org 很稳，
# 而且少一个源就少一处以后会失效的东西。
if ! command -v node >/dev/null || [[ "$(node -v)" != "$NODE_VERSION" ]]; then
  say "安装 Node $NODE_VERSION"
  curl -fsSL "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz
  tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
  rm -f /tmp/node.tar.xz
fi
node -v && npm -v

# ---------------------------------------------------------------- 3. 运行用户
if ! id "$APP_USER" >/dev/null 2>&1; then
  say "创建运行用户 $APP_USER（不用 root 跑服务）"
  useradd -m -s /bin/bash "$APP_USER"
fi
mkdir -p "$LOG_DIR" "$APP_DIR/backend/data"
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$LOG_DIR"

# ---------------------------------------------------------------- 4. 后端
say "安装后端依赖（venv）"
cd "$APP_DIR"
if [[ ! -d .venv ]]; then
  sudo -u "$APP_USER" python3 -m venv .venv
fi
# 国内/香港都用阿里云 PyPI 镜像，快很多
sudo -u "$APP_USER" .venv/bin/pip install -q --upgrade pip
sudo -u "$APP_USER" .venv/bin/pip install -q -r backend/requirements.txt \
  -i https://mirrors.aliyun.com/pypi/simple/
sudo -u "$APP_USER" .venv/bin/python -c "import fastapi, PIL; print('后端依赖 OK')"

# ---------------------------------------------------------------- 5. 前端
say "构建前端（这一步 1-2 分钟，4GB 内存够）"
cd "$APP_DIR/frontend"
sudo -u "$APP_USER" npm ci --no-audit --no-fund
# 关键：构建时把 API 基址设成**空字符串**，页面就会用相对路径 /api/*，
# 由 nginx 转给后端。默认值 127.0.0.1 会让评委的浏览器去连他自己的电脑。
sudo -u "$APP_USER" env NEXT_PUBLIC_API_BASE="" npm run build

# ---------------------------------------------------------------- 6. systemd
say "安装 systemd 服务"
install -m 644 "$APP_DIR/deploy/ai-audit-backend.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/ai-audit-frontend.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ai-audit-backend
systemctl enable --now ai-audit-frontend

# ---------------------------------------------------------------- 7. nginx
say "配置 nginx（80 → 前端，/api → 后端）"
install -m 644 "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/ai-audit
ln -sf /etc/nginx/sites-available/ai-audit /etc/nginx/sites-enabled/ai-audit
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ---------------------------------------------------------------- 8. 自检
say "自检"
sleep 2
echo -n "后端 8000 : "; curl -fsS http://127.0.0.1:8000/api/health || echo "失败"
echo; echo -n "前端 3100 : "; curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3100/
echo -n "nginx 80  : "; curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1/
echo -n "接口经 80 : "; curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1/api/health

say "完成"
cat <<TIPS
对外访问：http://$(curl -fsS --max-time 3 https://api.ipify.org 2>/dev/null || echo '<公网IP>')

还要去阿里云控制台做一件事（脚本改不了）：
  安全组 → 入方向 → 放行 TCP 80（0.0.0.0/0）
  22 端口建议限制来源 IP，别全网开放。

常用命令：
  systemctl status ai-audit-backend ai-audit-frontend
  tail -f /var/log/ai-audit/backend.log
  tail -f /var/log/ai-audit/frontend.log
TIPS
