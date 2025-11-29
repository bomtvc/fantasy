#!/bin/bash

# FPL League Analyzer - Flask App Manager
# Script quản lý deploy và vận hành trên Ubuntu VPS
# Sử dụng: ./fpl-manager.sh [command]

SERVICE_NAME="fpl-app"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLASK_APP="flask_app.py"
REQUIREMENTS="flask_requirements.txt"

# Màu sắc - dùng printf thay vì echo -e
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
CYAN=$'\033[0;36m'
NC=$'\033[0m'

# Print function để thay thế echo -e
print_color() {
    printf "%b\n" "$1"
}

# Banner
show_banner() {
    print_color "${BLUE}╔════════════════════════════════════════╗${NC}"
    print_color "${BLUE}║   ⚽ FPL League Analyzer Manager v1.0  ║${NC}"
    print_color "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
}

# Menu
show_menu() {
    show_banner
    print_color "${YELLOW}Chọn một lệnh:${NC}"
    echo ""
    printf "  ${GREEN}%-16s${NC} - %s\n" "deploy" "Deploy/cài đặt ứng dụng lần đầu"
    printf "  ${GREEN}%-16s${NC} - %s\n" "start" "Khởi động service"
    printf "  ${GREEN}%-16s${NC} - %s\n" "stop" "Dừng service"
    printf "  ${GREEN}%-16s${NC} - %s\n" "restart" "Restart service"
    printf "  ${GREEN}%-16s${NC} - %s\n" "status" "Xem trạng thái service"
    printf "  ${GREEN}%-16s${NC} - %s\n" "logs" "Xem logs realtime"
    printf "  ${GREEN}%-16s${NC} - %s\n" "logs-error" "Xem chỉ errors"
    printf "  ${GREEN}%-16s${NC} - %s\n" "nginx" "Cấu hình Nginx reverse proxy"
    printf "  ${GREEN}%-16s${NC} - %s\n" "nginx-reload" "Reload Nginx"
    printf "  ${GREEN}%-16s${NC} - %s\n" "nginx-check" "Kiểm tra Nginx và static files"
    printf "  ${GREEN}%-16s${NC} - %s\n" "ssl" "Cài đặt SSL với Let's Encrypt"
    printf "  ${GREEN}%-16s${NC} - %s\n" "firewall" "Mở ports UFW + tắt iptables (Oracle Cloud)"
    printf "  ${GREEN}%-16s${NC} - %s\n" "fix-permissions" "Sửa lỗi Permission Denied"
    printf "  ${GREEN}%-16s${NC} - %s\n" "uninstall" "Gỡ bỏ hoàn toàn service"
    printf "  ${GREEN}%-16s${NC} - %s\n" "uninstall-nginx" "Gỡ bỏ cấu hình Nginx"
    printf "  ${GREEN}%-16s${NC} - %s\n" "help" "Hiển thị help"
    echo ""
    print_color "${YELLOW}Sử dụng:${NC} ./fpl-manager.sh [command]"
    echo ""
}

# Deploy
deploy() {
    show_banner
    print_color "${BLUE}[DEPLOY] Đang deploy FPL League Analyzer...${NC}"
    echo ""

    cd "$APP_DIR"

    # Kiểm tra quyền root
    if [ "$EUID" -ne 0 ]; then
        print_color "${YELLOW}Một số bước cần quyền root. Script sẽ dùng sudo.${NC}"
        echo ""
    fi

    # 1. Cài đặt dependencies hệ thống
    print_color "${CYAN}[1/7]${NC} Cài đặt build tools..."
    sudo apt update -qq
    sudo apt install -y build-essential python3-dev python3-pip python3-venv >/dev/null 2>&1
    print_color "${GREEN}  ✓ Done${NC}"

    # 2. Tạo virtual environment
    print_color "${CYAN}[2/7]${NC} Tạo virtual environment..."
    if [ -d "venv" ]; then
        print_color "${YELLOW}  Xóa venv cũ...${NC}"
        rm -rf venv
    fi
    python3 -m venv venv
    print_color "${GREEN}  ✓ Done${NC}"

    # 3. Cài đặt Python packages
    print_color "${CYAN}[3/7]${NC} Cài đặt Python packages..."
    source venv/bin/activate
    pip install -q --upgrade pip setuptools wheel
    pip install -q -r "$REQUIREMENTS"
    pip install -q gunicorn
    deactivate
    print_color "${GREEN}  ✓ Done${NC}"

    # 4. Tạo thư mục cần thiết
    print_color "${CYAN}[4/7]${NC} Tạo thư mục..."
    mkdir -p cache logs
    chmod 755 cache logs
    print_color "${GREEN}  ✓ Done${NC}"

    # 5. Tạo start script
    print_color "${CYAN}[5/7]${NC} Tạo start script..."
    cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
exec gunicorn --workers 2 --bind 0.0.0.0:5000 --timeout 120 --access-logfile logs/access.log --error-logfile logs/error.log "flask_app:create_app()"
EOF
    chmod +x start.sh
    print_color "${GREEN}  ✓ Done${NC}"

    # 6. Cấu hình systemd service
    print_color "${CYAN}[6/7]${NC} Cấu hình systemd service..."
    CURRENT_USER=$(whoami)
    cat > $SERVICE_NAME.service << EOF
[Unit]
Description=FPL League Analyzer Flask Application
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=/bin/bash $APP_DIR/start.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    sudo cp $SERVICE_NAME.service /etc/systemd/system/
    print_color "${GREEN}  ✓ Done${NC}"

    # 7. Enable và start service
    print_color "${CYAN}[7/7]${NC} Enable và start service..."
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME >/dev/null 2>&1
    sudo systemctl stop $SERVICE_NAME >/dev/null 2>&1
    sudo systemctl start $SERVICE_NAME
    sleep 2

    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        print_color "${GREEN}  ✓ Service đang chạy${NC}"
    else
        print_color "${RED}  ✗ Service failed - Xem logs: ./fpl-manager.sh logs${NC}"
    fi

    echo ""
    print_color "${GREEN}╔════════════════════════════════════════╗${NC}"
    print_color "${GREEN}║        ⚽ Deploy Hoàn Thành!           ║${NC}"
    print_color "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    IP=$(hostname -I | awk '{print $1}')
    print_color "${CYAN}Truy cập:${NC} http://$IP:5000"
    echo ""
}

# Start Service
start_service() {
    print_color "${BLUE}[START]${NC} Đang khởi động service..."
    sudo systemctl start $SERVICE_NAME
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        print_color "${GREEN}✓ Service đã khởi động${NC}"
        show_status
    else
        print_color "${RED}✗ Không thể khởi động - Xem logs: ./fpl-manager.sh logs${NC}"
    fi
}

# Stop Service
stop_service() {
    print_color "${BLUE}[STOP]${NC} Đang dừng service..."
    sudo systemctl stop $SERVICE_NAME
    print_color "${GREEN}✓ Service đã dừng${NC}"
}

# Restart Service
restart_service() {
    print_color "${BLUE}[RESTART]${NC} Đang restart service..."
    sudo systemctl restart $SERVICE_NAME
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        print_color "${GREEN}✓ Service đã restart${NC}"
        show_status
    else
        print_color "${RED}✗ Service failed - Xem logs: ./fpl-manager.sh logs${NC}"
    fi
}

# Status
show_status() {
    print_color "${BLUE}════════════════════════════════════════${NC}"
    print_color "${BLUE}  Service Status${NC}"
    print_color "${BLUE}════════════════════════════════════════${NC}"
    sudo systemctl status $SERVICE_NAME --no-pager -l | head -20
    echo ""
    print_color "${BLUE}════════════════════════════════════════${NC}"
    print_color "${BLUE}  Port Status${NC}"
    print_color "${BLUE}════════════════════════════════════════${NC}"
    if sudo lsof -i :5000 >/dev/null 2>&1; then
        print_color "${GREEN}✓ Port 5000 đang listen${NC}"
        sudo lsof -i :5000
    else
        print_color "${RED}✗ Port 5000 không có process${NC}"
    fi
}

# Logs realtime
show_logs() {
    print_color "${BLUE}[LOGS]${NC} Theo dõi logs realtime (Ctrl+C để thoát)..."
    echo ""
    sudo journalctl -u $SERVICE_NAME -f
}

# Logs errors only
show_logs_error() {
    print_color "${BLUE}[LOGS]${NC} Chỉ errors:"
    echo ""
    sudo journalctl -u $SERVICE_NAME -p err --no-pager
}

# Configure Nginx
configure_nginx() {
    show_banner
    print_color "${BLUE}[NGINX SETUP]${NC} Cấu hình Nginx reverse proxy..."
    echo ""

    # Kiểm tra Nginx
    if ! command -v nginx &> /dev/null; then
        print_color "${YELLOW}Nginx chưa cài. Đang cài đặt...${NC}"
        sudo apt update -qq
        sudo apt install -y nginx
    fi
    print_color "${GREEN}✓ Nginx đã sẵn sàng${NC}"

    # Lấy domain/IP
    echo ""
    read -p "Nhập domain (để trống dùng IP): " DOMAIN
    if [ -z "$DOMAIN" ]; then
        DOMAIN=$(hostname -I | awk '{print $1}')
        print_color "${YELLOW}Sử dụng IP: $DOMAIN${NC}"
    fi

    # Cấp quyền static
    echo ""
    print_color "${CYAN}[1/4]${NC} Cấp quyền static files..."
    sudo chmod -R 755 "$APP_DIR/static/" 2>/dev/null
    print_color "${GREEN}  ✓ Done${NC}"

    # Tạo cấu hình Nginx
    print_color "${CYAN}[2/4]${NC} Tạo cấu hình Nginx..."
    NGINX_CONF="/etc/nginx/sites-available/$SERVICE_NAME"

    sudo tee "$NGINX_CONF" > /dev/null << EOF
# FPL League Analyzer - Nginx Configuration
# Created: $(date)

server {
    listen 80;
    server_name $DOMAIN;

    access_log /var/log/nginx/fpl-access.log;
    error_log /var/log/nginx/fpl-error.log;

    client_max_body_size 10M;

    # Static files
    location /static/ {
        alias $APP_DIR/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Flask app
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
}
EOF
    print_color "${GREEN}  ✓ Done${NC}"

    # Enable site
    print_color "${CYAN}[3/4]${NC} Enable site..."
    sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/$SERVICE_NAME
    sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null
    print_color "${GREEN}  ✓ Done${NC}"

    # Test và reload
    print_color "${CYAN}[4/4]${NC} Test và reload Nginx..."
    if sudo nginx -t 2>&1 | grep -q "successful"; then
        sudo systemctl reload nginx
        sudo systemctl enable nginx >/dev/null 2>&1
        print_color "${GREEN}  ✓ Nginx đã được reload${NC}"

        echo ""
        print_color "${GREEN}╔════════════════════════════════════════╗${NC}"
        print_color "${GREEN}║     Nginx Configured Successfully!     ║${NC}"
        print_color "${GREEN}╚════════════════════════════════════════╝${NC}"
        echo ""
        print_color "${CYAN}Truy cập:${NC} http://$DOMAIN"
        print_color "${CYAN}Static:${NC}  http://$DOMAIN/static/"
        echo ""
    else
        print_color "${RED}  ✗ Cấu hình lỗi${NC}"
        sudo nginx -t
    fi
}

# Reload Nginx
reload_nginx() {
    print_color "${BLUE}[NGINX RELOAD]${NC} Đang reload Nginx..."
    if sudo nginx -t; then
        sudo systemctl reload nginx
        print_color "${GREEN}✓ Nginx đã được reload${NC}"
    else
        print_color "${RED}✗ Cấu hình có lỗi${NC}"
    fi
}

# Check Nginx và Static Files
check_nginx() {
    show_banner
    print_color "${BLUE}[NGINX CHECK]${NC} Kiểm tra Nginx và Static Files..."
    echo ""

    PASS=0
    FAIL=0

    # 1. Nginx installed
    print_color "${CYAN}[1/6]${NC} Kiểm tra Nginx..."
    if command -v nginx &> /dev/null; then
        print_color "${GREEN}  ✓ Nginx đã cài${NC}"
        ((PASS++))
    else
        print_color "${RED}  ✗ Nginx chưa cài${NC}"
        ((FAIL++))
    fi

    # 2. Nginx running
    print_color "${CYAN}[2/6]${NC} Nginx đang chạy..."
    if sudo systemctl is-active --quiet nginx; then
        print_color "${GREEN}  ✓ Nginx đang chạy${NC}"
        ((PASS++))
    else
        print_color "${RED}  ✗ Nginx không chạy${NC}"
        ((FAIL++))
    fi

    # 3. Config exists
    print_color "${CYAN}[3/6]${NC} File config..."
    if [ -f "/etc/nginx/sites-available/$SERVICE_NAME" ]; then
        print_color "${GREEN}  ✓ Config tồn tại${NC}"
        ((PASS++))
    else
        print_color "${RED}  ✗ Config không tồn tại${NC}"
        ((FAIL++))
    fi

    # 4. Static folder
    print_color "${CYAN}[4/6]${NC} Thư mục static..."
    if [ -d "$APP_DIR/static" ]; then
        print_color "${GREEN}  ✓ Thư mục static tồn tại${NC}"
        ((PASS++))
    else
        print_color "${RED}  ✗ Không có thư mục static${NC}"
        ((FAIL++))
    fi

    # 5. Test homepage
    print_color "${CYAN}[5/6]${NC} Test homepage..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        print_color "${GREEN}  ✓ Homepage OK (HTTP $HTTP_CODE)${NC}"
        ((PASS++))
    else
        print_color "${RED}  ✗ Homepage fail (HTTP $HTTP_CODE)${NC}"
        ((FAIL++))
    fi

    # 6. Test static
    print_color "${CYAN}[6/6]${NC} Test static files..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/base.css 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        print_color "${GREEN}  ✓ Static files OK (HTTP $HTTP_CODE)${NC}"
        ((PASS++))
    else
        print_color "${RED}  ✗ Static files fail (HTTP $HTTP_CODE)${NC}"
        ((FAIL++))
    fi

    # Result
    echo ""
    print_color "${BLUE}════════════════════════════════════════${NC}"
    printf "  ${GREEN}✓ PASS: $PASS${NC}  ${RED}✗ FAIL: $FAIL${NC}\n"
    print_color "${BLUE}════════════════════════════════════════${NC}"
}

# Fix Permissions
fix_permissions() {
    show_banner
    print_color "${BLUE}[FIX PERMISSIONS]${NC} Sửa lỗi Permission Denied..."
    echo ""

    print_color "${CYAN}[1/3]${NC} Cấp quyền thư mục static..."
    sudo chmod -R 755 "$APP_DIR/static/"
    print_color "${GREEN}  ✓ Done${NC}"

    print_color "${CYAN}[2/3]${NC} Cấp quyền thư mục cha..."
    sudo chmod 755 "$APP_DIR"
    sudo chmod 755 "$(dirname "$APP_DIR")"
    print_color "${GREEN}  ✓ Done${NC}"

    print_color "${CYAN}[3/3]${NC} Reload Nginx..."
    sudo systemctl reload nginx 2>/dev/null
    print_color "${GREEN}  ✓ Done${NC}"

    echo ""
    print_color "${CYAN}Kiểm tra lại:${NC}"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/base.css 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        print_color "${GREEN}✓ Static files load OK!${NC}"
    else
        print_color "${RED}✗ Vẫn lỗi (HTTP $HTTP_CODE) - Xem: sudo tail /var/log/nginx/fpl-error.log${NC}"
    fi
}

# Uninstall Service
uninstall_service() {
    show_banner
    print_color "${RED}[UNINSTALL SERVICE]${NC} Gỡ bỏ hoàn toàn service..."
    echo ""

    print_color "${RED}⚠️  CẢNH BÁO:${NC}"
    echo "  • Sẽ xóa systemd service"
    echo "  • Mã nguồn và cache vẫn được giữ lại"
    echo ""

    read -p "Bạn có chắc chắn? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        print_color "${YELLOW}❌ Đã hủy.${NC}"
        exit 0
    fi

    echo ""
    print_color "${CYAN}[1/3]${NC} Dừng service..."
    sudo systemctl stop $SERVICE_NAME 2>/dev/null
    print_color "${GREEN}  ✓ Done${NC}"

    print_color "${CYAN}[2/3]${NC} Disable và xóa service..."
    sudo systemctl disable $SERVICE_NAME 2>/dev/null
    sudo rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    print_color "${GREEN}  ✓ Done${NC}"

    print_color "${CYAN}[3/3]${NC} Reload daemon..."
    sudo systemctl daemon-reload
    print_color "${GREEN}  ✓ Done${NC}"

    echo ""
    print_color "${GREEN}✓ Service đã được gỡ bỏ${NC}"
    print_color "${CYAN}Deploy lại:${NC} ./fpl-manager.sh deploy"
}

# Uninstall Nginx config
uninstall_nginx() {
    show_banner
    print_color "${RED}[UNINSTALL NGINX]${NC} Gỡ bỏ cấu hình Nginx..."
    echo ""

    read -p "Bạn có chắc chắn? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        print_color "${YELLOW}❌ Đã hủy.${NC}"
        exit 0
    fi

    echo ""
    print_color "${CYAN}[1/3]${NC} Xóa config..."
    sudo rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
    sudo rm -f "/etc/nginx/sites-available/$SERVICE_NAME"
    print_color "${GREEN}  ✓ Done${NC}"

    print_color "${CYAN}[2/3]${NC} Test config..."
    sudo nginx -t 2>/dev/null
    print_color "${GREEN}  ✓ Done${NC}"

    print_color "${CYAN}[3/3]${NC} Reload Nginx..."
    sudo systemctl reload nginx
    print_color "${GREEN}  ✓ Done${NC}"

    echo ""
    print_color "${GREEN}✓ Cấu hình Nginx đã được gỡ bỏ${NC}"
    IP=$(hostname -I | awk '{print $1}')
    print_color "${CYAN}Truy cập trực tiếp:${NC} http://$IP:5000"
}

# Firewall - Mở ports UFW + tắt iptables
configure_firewall() {
    show_banner
    print_color "${BLUE}[FIREWALL SETUP]${NC} Cấu hình Firewall cho Oracle Cloud / VPS..."
    echo ""

    # 1. Cấu hình UFW
    print_color "${CYAN}[1/3]${NC} Cấu hình UFW..."

    # Cài UFW nếu chưa có
    if ! command -v ufw &> /dev/null; then
        print_color "${YELLOW}  Đang cài đặt UFW...${NC}"
        sudo apt update -qq
        sudo apt install -y ufw >/dev/null 2>&1
    fi

    # Mở các ports cần thiết
    sudo ufw allow 22/tcp >/dev/null 2>&1    # SSH
    sudo ufw allow 80/tcp >/dev/null 2>&1    # HTTP
    sudo ufw allow 443/tcp >/dev/null 2>&1   # HTTPS
    sudo ufw allow 5000/tcp >/dev/null 2>&1  # Flask

    # Enable UFW
    echo "y" | sudo ufw enable >/dev/null 2>&1
    print_color "${GREEN}  ✓ UFW đã mở ports: 22, 80, 443, 5000${NC}"

    # 2. Tắt iptables (Oracle Cloud issue)
    print_color "${CYAN}[2/3]${NC} Tắt iptables firewall (Oracle Cloud fix)..."

    # Flush all rules
    sudo iptables -F
    sudo iptables -X
    sudo iptables -t nat -F
    sudo iptables -t nat -X
    sudo iptables -t mangle -F
    sudo iptables -t mangle -X

    # Set default policy to ACCEPT
    sudo iptables -P INPUT ACCEPT
    sudo iptables -P FORWARD ACCEPT
    sudo iptables -P OUTPUT ACCEPT

    print_color "${GREEN}  ✓ iptables đã được tắt${NC}"

    # 3. Lưu cấu hình iptables
    print_color "${CYAN}[3/3]${NC} Lưu cấu hình (persistent)..."

    # Cài iptables-persistent
    echo iptables-persistent iptables-persistent/autosave_v4 boolean true | sudo debconf-set-selections
    echo iptables-persistent iptables-persistent/autosave_v6 boolean true | sudo debconf-set-selections
    sudo apt install -y iptables-persistent >/dev/null 2>&1

    # Lưu rules
    sudo netfilter-persistent save >/dev/null 2>&1
    print_color "${GREEN}  ✓ Cấu hình đã được lưu${NC}"

    # Hiển thị kết quả
    echo ""
    print_color "${GREEN}╔════════════════════════════════════════╗${NC}"
    print_color "${GREEN}║     🔥 Firewall Configured!            ║${NC}"
    print_color "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""

    print_color "${CYAN}UFW Status:${NC}"
    sudo ufw status | grep -E "22|80|443|5000"
    echo ""

    IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    print_color "${CYAN}Truy cập:${NC} http://$IP"
    echo ""

    print_color "${YELLOW}Lưu ý:${NC} Nếu dùng Oracle Cloud, đảm bảo đã mở ports trong Security List"
}

# SSL với Let's Encrypt
configure_ssl() {
    show_banner
    print_color "${BLUE}[SSL SETUP]${NC} Cài đặt SSL với Let's Encrypt..."
    echo ""

    # Kiểm tra Nginx config
    if [ ! -f "/etc/nginx/sites-available/$SERVICE_NAME" ]; then
        print_color "${RED}✗ Chưa cấu hình Nginx. Chạy: ./fpl-manager.sh nginx${NC}"
        exit 1
    fi

    # Lấy domain từ Nginx config
    DOMAIN=$(grep -m1 "server_name" /etc/nginx/sites-available/$SERVICE_NAME | awk '{print $2}' | tr -d ';')
    print_color "${CYAN}Domain:${NC} $DOMAIN"
    echo ""

    # Kiểm tra domain hợp lệ (không phải IP)
    if [[ $DOMAIN =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        print_color "${RED}✗ SSL cần domain name, không thể dùng IP address${NC}"
        print_color "${YELLOW}Hãy cấu hình lại Nginx với domain: ./fpl-manager.sh nginx${NC}"
        exit 1
    fi

    # Cài đặt Certbot
    print_color "${CYAN}[1/3]${NC} Cài đặt Certbot..."
    sudo apt update -qq
    sudo apt install -y certbot python3-certbot-nginx >/dev/null 2>&1
    print_color "${GREEN}  ✓ Done${NC}"

    # Xin certificate
    print_color "${CYAN}[2/3]${NC} Xin SSL certificate..."
    echo ""
    print_color "${YELLOW}Certbot sẽ yêu cầu email và đồng ý điều khoản.${NC}"
    echo ""

    sudo certbot --nginx -d "$DOMAIN"

    # Kiểm tra kết quả
    if [ $? -eq 0 ]; then
        print_color "${CYAN}[3/3]${NC} Thiết lập auto-renew..."
        sudo systemctl enable certbot.timer >/dev/null 2>&1
        sudo systemctl start certbot.timer
        print_color "${GREEN}  ✓ Done${NC}"

        echo ""
        print_color "${GREEN}╔════════════════════════════════════════╗${NC}"
        print_color "${GREEN}║      🔒 SSL Configured Successfully!   ║${NC}"
        print_color "${GREEN}╚════════════════════════════════════════╝${NC}"
        echo ""
        print_color "${CYAN}Truy cập:${NC} https://$DOMAIN"
        print_color "${CYAN}Auto-renew:${NC} Đã bật (kiểm tra: sudo certbot renew --dry-run)"
        echo ""
    else
        print_color "${RED}✗ Xin certificate thất bại${NC}"
        print_color "${YELLOW}Kiểm tra:${NC}"
        echo "  • Domain đã trỏ về IP server chưa?"
        echo "  • Port 80 đã mở chưa?"
        echo "  • Nginx đang chạy chưa?"
    fi
}

# Help
show_help() {
    show_banner
    print_color "${CYAN}FPL League Analyzer - Flask App Manager${NC}"
    echo ""
    echo "Script quản lý deploy và vận hành ứng dụng trên Ubuntu VPS"
    echo ""
    print_color "${YELLOW}Các lệnh:${NC}"
    echo ""
    printf "  ${GREEN}deploy${NC}\n"
    echo "    Deploy ứng dụng lần đầu (tạo venv, cài packages, tạo service)"
    echo ""
    printf "  ${GREEN}start${NC}, ${GREEN}stop${NC}, ${GREEN}restart${NC}\n"
    echo "    Quản lý service (khởi động, dừng, restart)"
    echo ""
    printf "  ${GREEN}status${NC}\n"
    echo "    Xem trạng thái service và port"
    echo ""
    printf "  ${GREEN}logs${NC}, ${GREEN}logs-error${NC}\n"
    echo "    Xem logs realtime hoặc chỉ errors"
    echo ""
    printf "  ${GREEN}nginx${NC}\n"
    echo "    Cấu hình Nginx reverse proxy (auto setup static files)"
    echo ""
    printf "  ${GREEN}ssl${NC}\n"
    echo "    Cài đặt SSL certificate với Let's Encrypt"
    echo ""
    printf "  ${GREEN}firewall${NC}\n"
    echo "    Mở ports UFW + tắt iptables (fix Oracle Cloud)"
    echo ""
    printf "  ${GREEN}nginx-reload${NC}, ${GREEN}nginx-check${NC}\n"
    echo "    Reload Nginx hoặc kiểm tra trạng thái"
    echo ""
    printf "  ${GREEN}fix-permissions${NC}\n"
    echo "    Sửa lỗi 403 Permission Denied cho static files"
    echo ""
    printf "  ${GREEN}uninstall${NC}, ${GREEN}uninstall-nginx${NC}\n"
    echo "    Gỡ bỏ service hoặc cấu hình Nginx"
    echo ""
    print_color "${CYAN}Ví dụ:${NC}"
    echo "  ./fpl-manager.sh deploy      # Deploy lần đầu"
    echo "  ./fpl-manager.sh nginx       # Cấu hình Nginx"
    echo "  ./fpl-manager.sh ssl         # Cài SSL"
    echo "  ./fpl-manager.sh firewall    # Mở firewall (Oracle Cloud)"
    echo "  ./fpl-manager.sh restart     # Restart sau khi update code"
    echo ""
}

# Main
case "$1" in
    deploy)
        deploy
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    logs-error)
        show_logs_error
        ;;
    nginx)
        configure_nginx
        ;;
    ssl)
        configure_ssl
        ;;
    firewall)
        configure_firewall
        ;;
    nginx-reload)
        reload_nginx
        ;;
    nginx-check)
        check_nginx
        ;;
    fix-permissions)
        fix_permissions
        ;;
    uninstall)
        uninstall_service
        ;;
    uninstall-nginx)
        uninstall_nginx
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_menu
        ;;
esac

