#!/bin/bash

# FPL League Analyzer - Flask App Manager
# Script quản lý deploy và vận hành trên Ubuntu VPS
# Sử dụng: ./fpl-manager.sh [command]

SERVICE_NAME="fpl-app"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLASK_APP="flask_app.py"
REQUIREMENTS="flask_requirements.txt"

# Màu sắc
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Banner
show_banner() {
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   ⚽ FPL League Analyzer Manager v1.0  ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
}

# Menu
show_menu() {
    show_banner
    echo -e "${YELLOW}Chọn một lệnh:${NC}"
    echo ""
    echo "  ${GREEN}deploy${NC}          - Deploy/cài đặt ứng dụng lần đầu"
    echo "  ${GREEN}start${NC}           - Khởi động service"
    echo "  ${GREEN}stop${NC}            - Dừng service"
    echo "  ${GREEN}restart${NC}         - Restart service"
    echo "  ${GREEN}status${NC}          - Xem trạng thái service"
    echo "  ${GREEN}logs${NC}            - Xem logs realtime"
    echo "  ${GREEN}logs-error${NC}      - Xem chỉ errors"
    echo "  ${GREEN}nginx${NC}           - Cấu hình Nginx reverse proxy"
    echo "  ${GREEN}nginx-reload${NC}    - Reload Nginx"
    echo "  ${GREEN}nginx-check${NC}     - Kiểm tra Nginx và static files"
    echo "  ${GREEN}fix-permissions${NC} - Sửa lỗi Permission Denied"
    echo "  ${GREEN}uninstall${NC}       - Gỡ bỏ hoàn toàn service"
    echo "  ${GREEN}uninstall-nginx${NC} - Gỡ bỏ cấu hình Nginx"
    echo "  ${GREEN}help${NC}            - Hiển thị help"
    echo ""
    echo -e "${YELLOW}Sử dụng:${NC} ./fpl-manager.sh [command]"
    echo ""
}

# Deploy
deploy() {
    show_banner
    echo -e "${BLUE}[DEPLOY] Đang deploy FPL League Analyzer...${NC}"
    echo ""
    
    cd "$APP_DIR"
    
    # Kiểm tra quyền root
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${YELLOW}Một số bước cần quyền root. Script sẽ dùng sudo.${NC}"
        echo ""
    fi
    
    # 1. Cài đặt dependencies hệ thống
    echo -e "${CYAN}[1/7]${NC} Cài đặt build tools..."
    sudo apt update -qq
    sudo apt install -y build-essential python3-dev python3-pip python3-venv >/dev/null 2>&1
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 2. Tạo virtual environment
    echo -e "${CYAN}[2/7]${NC} Tạo virtual environment..."
    if [ -d "venv" ]; then
        echo -e "${YELLOW}  Xóa venv cũ...${NC}"
        rm -rf venv
    fi
    python3 -m venv venv
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 3. Cài đặt Python packages
    echo -e "${CYAN}[3/7]${NC} Cài đặt Python packages..."
    source venv/bin/activate
    pip install -q --upgrade pip setuptools wheel
    pip install -q -r "$REQUIREMENTS"
    pip install -q gunicorn
    deactivate
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 4. Tạo thư mục cần thiết
    echo -e "${CYAN}[4/7]${NC} Tạo thư mục..."
    mkdir -p cache logs
    chmod 755 cache logs
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 5. Tạo start script
    echo -e "${CYAN}[5/7]${NC} Tạo start script..."
    cat > start.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
exec gunicorn --workers 2 --bind 0.0.0.0:5000 --timeout 120 --access-logfile logs/access.log --error-logfile logs/error.log "flask_app:create_app()"
EOF
    chmod +x start.sh
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 6. Cấu hình systemd service
    echo -e "${CYAN}[6/7]${NC} Cấu hình systemd service..."
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
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 7. Enable và start service
    echo -e "${CYAN}[7/7]${NC} Enable và start service..."
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME >/dev/null 2>&1
    sudo systemctl stop $SERVICE_NAME >/dev/null 2>&1
    sudo systemctl start $SERVICE_NAME
    sleep 2
    
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}  ✓ Service đang chạy${NC}"
    else
        echo -e "${RED}  ✗ Service failed - Xem logs: ./fpl-manager.sh logs${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        ⚽ Deploy Hoàn Thành!           ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    IP=$(hostname -I | awk '{print $1}')
    echo -e "${CYAN}Truy cập:${NC} http://$IP:5000"
    echo ""
}

# Start Service
start_service() {
    echo -e "${BLUE}[START]${NC} Đang khởi động service..."
    sudo systemctl start $SERVICE_NAME
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✓ Service đã khởi động${NC}"
        show_status
    else
        echo -e "${RED}✗ Không thể khởi động - Xem logs: ./fpl-manager.sh logs${NC}"
    fi
}

# Stop Service
stop_service() {
    echo -e "${BLUE}[STOP]${NC} Đang dừng service..."
    sudo systemctl stop $SERVICE_NAME
    echo -e "${GREEN}✓ Service đã dừng${NC}"
}

# Restart Service
restart_service() {
    echo -e "${BLUE}[RESTART]${NC} Đang restart service..."
    sudo systemctl restart $SERVICE_NAME
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✓ Service đã restart${NC}"
        show_status
    else
        echo -e "${RED}✗ Service failed - Xem logs: ./fpl-manager.sh logs${NC}"
    fi
}

# Status
show_status() {
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Service Status${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    sudo systemctl status $SERVICE_NAME --no-pager -l | head -20
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Port Status${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    if sudo lsof -i :5000 >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Port 5000 đang listen${NC}"
        sudo lsof -i :5000
    else
        echo -e "${RED}✗ Port 5000 không có process${NC}"
    fi
}

# Logs realtime
show_logs() {
    echo -e "${BLUE}[LOGS]${NC} Theo dõi logs realtime (Ctrl+C để thoát)..."
    echo ""
    sudo journalctl -u $SERVICE_NAME -f
}

# Logs errors only
show_logs_error() {
    echo -e "${BLUE}[LOGS]${NC} Chỉ errors:"
    echo ""
    sudo journalctl -u $SERVICE_NAME -p err --no-pager
}

# Configure Nginx
configure_nginx() {
    show_banner
    echo -e "${BLUE}[NGINX SETUP]${NC} Cấu hình Nginx reverse proxy..."
    echo ""

    # Kiểm tra Nginx
    if ! command -v nginx &> /dev/null; then
        echo -e "${YELLOW}Nginx chưa cài. Đang cài đặt...${NC}"
        sudo apt update -qq
        sudo apt install -y nginx
    fi
    echo -e "${GREEN}✓ Nginx đã sẵn sàng${NC}"

    # Lấy domain/IP
    echo ""
    read -p "Nhập domain (để trống dùng IP): " DOMAIN
    if [ -z "$DOMAIN" ]; then
        DOMAIN=$(hostname -I | awk '{print $1}')
        echo -e "${YELLOW}Sử dụng IP: $DOMAIN${NC}"
    fi

    # Cấp quyền static
    echo ""
    echo -e "${CYAN}[1/4]${NC} Cấp quyền static files..."
    sudo chmod -R 755 "$APP_DIR/static/" 2>/dev/null
    echo -e "${GREEN}  ✓ Done${NC}"

    # Tạo cấu hình Nginx
    echo -e "${CYAN}[2/4]${NC} Tạo cấu hình Nginx..."
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
    echo -e "${GREEN}  ✓ Done${NC}"

    # Enable site
    echo -e "${CYAN}[3/4]${NC} Enable site..."
    sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/$SERVICE_NAME
    sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null
    echo -e "${GREEN}  ✓ Done${NC}"

    # Test và reload
    echo -e "${CYAN}[4/4]${NC} Test và reload Nginx..."
    if sudo nginx -t 2>&1 | grep -q "successful"; then
        sudo systemctl reload nginx
        sudo systemctl enable nginx >/dev/null 2>&1
        echo -e "${GREEN}  ✓ Nginx đã được reload${NC}"

        echo ""
        echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║     Nginx Configured Successfully!     ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}Truy cập:${NC} http://$DOMAIN"
        echo -e "${CYAN}Static:${NC}  http://$DOMAIN/static/"
        echo ""
    else
        echo -e "${RED}  ✗ Cấu hình lỗi${NC}"
        sudo nginx -t
    fi
}

# Reload Nginx
reload_nginx() {
    echo -e "${BLUE}[NGINX RELOAD]${NC} Đang reload Nginx..."
    if sudo nginx -t; then
        sudo systemctl reload nginx
        echo -e "${GREEN}✓ Nginx đã được reload${NC}"
    else
        echo -e "${RED}✗ Cấu hình có lỗi${NC}"
    fi
}

# Check Nginx và Static Files
check_nginx() {
    show_banner
    echo -e "${BLUE}[NGINX CHECK]${NC} Kiểm tra Nginx và Static Files..."
    echo ""

    PASS=0
    FAIL=0

    # 1. Nginx installed
    echo -e "${CYAN}[1/6]${NC} Kiểm tra Nginx..."
    if command -v nginx &> /dev/null; then
        echo -e "${GREEN}  ✓ Nginx đã cài${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Nginx chưa cài${NC}"
        ((FAIL++))
    fi

    # 2. Nginx running
    echo -e "${CYAN}[2/6]${NC} Nginx đang chạy..."
    if sudo systemctl is-active --quiet nginx; then
        echo -e "${GREEN}  ✓ Nginx đang chạy${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Nginx không chạy${NC}"
        ((FAIL++))
    fi

    # 3. Config exists
    echo -e "${CYAN}[3/6]${NC} File config..."
    if [ -f "/etc/nginx/sites-available/$SERVICE_NAME" ]; then
        echo -e "${GREEN}  ✓ Config tồn tại${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Config không tồn tại${NC}"
        ((FAIL++))
    fi

    # 4. Static folder
    echo -e "${CYAN}[4/6]${NC} Thư mục static..."
    if [ -d "$APP_DIR/static" ]; then
        echo -e "${GREEN}  ✓ Thư mục static tồn tại${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Không có thư mục static${NC}"
        ((FAIL++))
    fi

    # 5. Test homepage
    echo -e "${CYAN}[5/6]${NC} Test homepage..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        echo -e "${GREEN}  ✓ Homepage OK (HTTP $HTTP_CODE)${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Homepage fail (HTTP $HTTP_CODE)${NC}"
        ((FAIL++))
    fi

    # 6. Test static
    echo -e "${CYAN}[6/6]${NC} Test static files..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/base.css 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}  ✓ Static files OK (HTTP $HTTP_CODE)${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Static files fail (HTTP $HTTP_CODE)${NC}"
        ((FAIL++))
    fi

    # Result
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}✓ PASS: $PASS${NC}  ${RED}✗ FAIL: $FAIL${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
}

# Fix Permissions
fix_permissions() {
    show_banner
    echo -e "${BLUE}[FIX PERMISSIONS]${NC} Sửa lỗi Permission Denied..."
    echo ""

    echo -e "${CYAN}[1/3]${NC} Cấp quyền thư mục static..."
    sudo chmod -R 755 "$APP_DIR/static/"
    echo -e "${GREEN}  ✓ Done${NC}"

    echo -e "${CYAN}[2/3]${NC} Cấp quyền thư mục cha..."
    sudo chmod 755 "$APP_DIR"
    sudo chmod 755 "$(dirname "$APP_DIR")"
    echo -e "${GREEN}  ✓ Done${NC}"

    echo -e "${CYAN}[3/3]${NC} Reload Nginx..."
    sudo systemctl reload nginx 2>/dev/null
    echo -e "${GREEN}  ✓ Done${NC}"

    echo ""
    echo -e "${CYAN}Kiểm tra lại:${NC}"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/base.css 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ Static files load OK!${NC}"
    else
        echo -e "${RED}✗ Vẫn lỗi (HTTP $HTTP_CODE) - Xem: sudo tail /var/log/nginx/fpl-error.log${NC}"
    fi
}

# Uninstall Service
uninstall_service() {
    show_banner
    echo -e "${RED}[UNINSTALL SERVICE]${NC} Gỡ bỏ hoàn toàn service..."
    echo ""

    echo -e "${RED}⚠️  CẢNH BÁO:${NC}"
    echo "  • Sẽ xóa systemd service"
    echo "  • Mã nguồn và cache vẫn được giữ lại"
    echo ""

    read -p "Bạn có chắc chắn? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo -e "${YELLOW}❌ Đã hủy.${NC}"
        exit 0
    fi

    echo ""
    echo -e "${CYAN}[1/3]${NC} Dừng service..."
    sudo systemctl stop $SERVICE_NAME 2>/dev/null
    echo -e "${GREEN}  ✓ Done${NC}"

    echo -e "${CYAN}[2/3]${NC} Disable và xóa service..."
    sudo systemctl disable $SERVICE_NAME 2>/dev/null
    sudo rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    echo -e "${GREEN}  ✓ Done${NC}"

    echo -e "${CYAN}[3/3]${NC} Reload daemon..."
    sudo systemctl daemon-reload
    echo -e "${GREEN}  ✓ Done${NC}"

    echo ""
    echo -e "${GREEN}✓ Service đã được gỡ bỏ${NC}"
    echo -e "${CYAN}Deploy lại:${NC} ./fpl-manager.sh deploy"
}

# Uninstall Nginx config
uninstall_nginx() {
    show_banner
    echo -e "${RED}[UNINSTALL NGINX]${NC} Gỡ bỏ cấu hình Nginx..."
    echo ""

    read -p "Bạn có chắc chắn? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo -e "${YELLOW}❌ Đã hủy.${NC}"
        exit 0
    fi

    echo ""
    echo -e "${CYAN}[1/3]${NC} Xóa config..."
    sudo rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
    sudo rm -f "/etc/nginx/sites-available/$SERVICE_NAME"
    echo -e "${GREEN}  ✓ Done${NC}"

    echo -e "${CYAN}[2/3]${NC} Test config..."
    sudo nginx -t 2>/dev/null
    echo -e "${GREEN}  ✓ Done${NC}"

    echo -e "${CYAN}[3/3]${NC} Reload Nginx..."
    sudo systemctl reload nginx
    echo -e "${GREEN}  ✓ Done${NC}"

    echo ""
    echo -e "${GREEN}✓ Cấu hình Nginx đã được gỡ bỏ${NC}"
    IP=$(hostname -I | awk '{print $1}')
    echo -e "${CYAN}Truy cập trực tiếp:${NC} http://$IP:5000"
}

# Help
show_help() {
    show_banner
    echo -e "${CYAN}FPL League Analyzer - Flask App Manager${NC}"
    echo ""
    echo "Script quản lý deploy và vận hành ứng dụng trên Ubuntu VPS"
    echo ""
    echo -e "${YELLOW}Các lệnh:${NC}"
    echo ""
    echo "  ${GREEN}deploy${NC}"
    echo "    Deploy ứng dụng lần đầu (tạo venv, cài packages, tạo service)"
    echo ""
    echo "  ${GREEN}start${NC}, ${GREEN}stop${NC}, ${GREEN}restart${NC}"
    echo "    Quản lý service (khởi động, dừng, restart)"
    echo ""
    echo "  ${GREEN}status${NC}"
    echo "    Xem trạng thái service và port"
    echo ""
    echo "  ${GREEN}logs${NC}, ${GREEN}logs-error${NC}"
    echo "    Xem logs realtime hoặc chỉ errors"
    echo ""
    echo "  ${GREEN}nginx${NC}"
    echo "    Cấu hình Nginx reverse proxy (auto setup static files)"
    echo ""
    echo "  ${GREEN}nginx-reload${NC}, ${GREEN}nginx-check${NC}"
    echo "    Reload Nginx hoặc kiểm tra trạng thái"
    echo ""
    echo "  ${GREEN}fix-permissions${NC}"
    echo "    Sửa lỗi 403 Permission Denied cho static files"
    echo ""
    echo "  ${GREEN}uninstall${NC}, ${GREEN}uninstall-nginx${NC}"
    echo "    Gỡ bỏ service hoặc cấu hình Nginx"
    echo ""
    echo -e "${CYAN}Ví dụ:${NC}"
    echo "  ./fpl-manager.sh deploy      # Deploy lần đầu"
    echo "  ./fpl-manager.sh nginx       # Cấu hình Nginx"
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

