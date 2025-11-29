#!/bin/bash

# Security App Manager - Script quản lý toàn diện
# Sử dụng: ./app-manager.sh [command]

SERVICE_NAME="security-app"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    echo -e "${BLUE}║     Security App Manager v1.0          ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
}

# Menu
show_menu() {
    show_banner
    echo -e "${YELLOW}Chọn một lệnh:${NC}"
    echo ""
    echo "  ${GREEN}deploy${NC}      - Deploy/cài đặt ứng dụng lần đầu"
    echo "  ${GREEN}start${NC}       - Khởi động service"
    echo "  ${GREEN}stop${NC}        - Dừng service"
    echo "  ${GREEN}restart${NC}     - Restart service"
    echo "  ${GREEN}status${NC}      - Xem trạng thái service"
    echo "  ${GREEN}logs${NC}        - Xem logs realtime"
    echo "  ${GREEN}logs-n${NC}      - Xem N dòng logs gần nhất"
    echo "  ${GREEN}logs-error${NC}  - Xem chỉ errors"
    echo "  ${GREEN}test${NC}        - Test ứng dụng"
    echo "  ${GREEN}update${NC}      - Update dependencies"
    echo "  ${GREEN}backup${NC}      - Backup database"
    echo "  ${GREEN}backup-users${NC} - Backup tất cả user"
    echo "  ${GREEN}restore-users${NC} - Restore user từ backup"
    echo "  ${GREEN}reset-admin${NC} - Reset mật khẩu admin"
    echo "  ${GREEN}info${NC}        - Thông tin hệ thống"
    echo "  ${GREEN}nginx${NC}       - Cấu hình Nginx reverse proxy (tự động setup UI)"
    echo "  ${GREEN}nginx-test${NC}  - Test cấu hình Nginx"
    echo "  ${GREEN}nginx-reload${NC} - Reload Nginx"
    echo "  ${GREEN}nginx-check${NC} - Kiểm tra Nginx và static files"
    echo "  ${GREEN}fix-permissions${NC} - Sửa lỗi Permission Denied cho static files"
    echo "  ${GREEN}uninstall${NC}   - Gỡ bỏ hoàn toàn service"
    echo "  ${GREEN}uninstall-nginx${NC} - Gỡ bỏ cấu hình Nginx"
    echo "  ${GREEN}help${NC}        - Hiển thị help"
    echo ""
    echo -e "${YELLOW}Sử dụng:${NC} ./app-manager.sh [command]"
    echo ""
}

# Deploy
deploy() {
    show_banner
    echo -e "${BLUE}[DEPLOY] Đang deploy ứng dụng...${NC}"
    echo ""
    
    cd "$APP_DIR"
    
    # Kiểm tra quyền root cho một số lệnh
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${YELLOW}Một số bước cần quyền root. Script sẽ dùng sudo.${NC}"
        echo ""
    fi
    
    # 1. Cài đặt dependencies hệ thống
    echo -e "${CYAN}[1/8]${NC} Cài đặt build tools..."
    sudo apt update -qq
    sudo apt install -y build-essential python3-dev python3-pip python3-venv >/dev/null 2>&1
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 2. Tạo virtual environment
    echo -e "${CYAN}[2/8]${NC} Tạo virtual environment..."
    if [ -d "venv" ]; then
        echo -e "${YELLOW}  Xóa venv cũ...${NC}"
        rm -rf venv
    fi
    python3 -m venv venv
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 3. Cài đặt Python packages
    echo -e "${CYAN}[3/8]${NC} Cài đặt Python packages..."
    source venv/bin/activate
    pip install -q --upgrade pip setuptools wheel
    pip install -q -r requirements.txt
    pip install -q gunicorn
    deactivate
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 4. Tạo thư mục cần thiết
    echo -e "${CYAN}[4/8]${NC} Tạo thư mục..."
    mkdir -p instance cache backups logs
    chmod 755 instance cache backups logs
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 5. Khởi tạo database
    echo -e "${CYAN}[5/8]${NC} Khởi tạo database..."
    if [ ! -f "instance/security_app.db" ]; then
        source venv/bin/activate
        python3 << 'EOF' >/dev/null 2>&1
from app import app, db
with app.app_context():
    db.create_all()
EOF
        deactivate
        echo -e "${GREEN}  ✓ Database initialized${NC}"
    else
        echo -e "${YELLOW}  Database đã tồn tại${NC}"
    fi
    
    # 6. Cập nhật service file
    echo -e "${CYAN}[6/8]${NC} Cấu hình systemd service..."
    CURRENT_USER=$(whoami)
    cat > security-app.service << EOF
[Unit]
Description=Security Registration Flask Application
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
Environment="FLASK_APP=app.py"
Environment="FLASK_ENV=production"
Environment="PORT=5000"
Environment="BIND_HOST=0.0.0.0"

ExecStart=/bin/bash $APP_DIR/start.sh

Restart=always
RestartSec=10
StartLimitInterval=200
StartLimitBurst=5

TimeoutStartSec=0
TimeoutStopSec=30

StandardOutput=journal
StandardError=journal
SyslogIdentifier=security-app

[Install]
WantedBy=multi-user.target
EOF
    sudo cp security-app.service /etc/systemd/system/
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 7. Enable và start service
    echo -e "${CYAN}[7/8]${NC} Enable và start service..."
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME >/dev/null 2>&1
    sudo systemctl stop $SERVICE_NAME >/dev/null 2>&1
    sudo systemctl start $SERVICE_NAME
    echo -e "${GREEN}  ✓ Done${NC}"
    
    # 8. Verify
    echo -e "${CYAN}[8/8]${NC} Kiểm tra..."
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}  ✓ Service đang chạy${NC}"
    else
        echo -e "${RED}  ✗ Service failed${NC}"
        echo -e "${YELLOW}  Xem logs: ./app-manager.sh logs${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        Deploy Hoàn Thành!              ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    show_status
}

# Start
start_service() {
    echo -e "${BLUE}[START]${NC} Đang khởi động service..."
    sudo systemctl start $SERVICE_NAME
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✓ Service đã khởi động${NC}"
        show_status
    else
        echo -e "${RED}✗ Không thể khởi động service${NC}"
        echo -e "${YELLOW}Xem logs: ./app-manager.sh logs${NC}"
    fi
}

# Stop
stop_service() {
    echo -e "${BLUE}[STOP]${NC} Đang dừng service..."
    sudo systemctl stop $SERVICE_NAME
    echo -e "${GREEN}✓ Service đã dừng${NC}"
}

# Restart
restart_service() {
    echo -e "${BLUE}[RESTART]${NC} Đang restart service..."
    sudo systemctl restart $SERVICE_NAME
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✓ Service đã restart${NC}"
        show_status
    else
        echo -e "${RED}✗ Service failed sau khi restart${NC}"
        echo -e "${YELLOW}Xem logs: ./app-manager.sh logs${NC}"
    fi
}

# Status
show_status() {
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Service Status${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    sudo systemctl status $SERVICE_NAME --no-pager -l | head -20
    echo ""
    
    # Port status
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

# Logs
show_logs() {
    echo -e "${BLUE}[LOGS]${NC} Theo dõi logs realtime (Ctrl+C để thoát)..."
    echo ""
    sudo journalctl -u $SERVICE_NAME -f
}

# Logs N lines
show_logs_n() {
    LINES=${1:-50}
    echo -e "${BLUE}[LOGS]${NC} $LINES dòng logs gần nhất:"
    echo ""
    sudo journalctl -u $SERVICE_NAME -n $LINES --no-pager
}

# Logs errors
show_logs_error() {
    echo -e "${BLUE}[LOGS]${NC} Chỉ errors:"
    echo ""
    sudo journalctl -u $SERVICE_NAME -p err --no-pager
}

# Test
test_app() {
    echo -e "${BLUE}[TEST]${NC} Đang test ứng dụng..."
    echo ""
    
    # Test localhost
    if curl -f http://localhost:5000 >/dev/null 2>&1; then
        echo -e "${GREEN}✓ App đang chạy OK${NC}"
    else
        echo -e "${RED}✗ App không phản hồi${NC}"
    fi
    
    # Lấy IP
    IP=$(hostname -I | awk '{print $1}')
    echo ""
    echo -e "${CYAN}URL truy cập:${NC}"
    echo -e "  • Local:      ${GREEN}http://localhost:5000${NC}"
    echo -e "  • Public IP:  ${GREEN}http://$IP:5000${NC}"
    echo ""
    echo -e "${YELLOW}Lưu ý:${NC}"
    echo -e "  • Truy cập trực tiếp qua port 5000"
    echo -e "  • Hoặc qua Nginx reverse proxy (port 80) nếu đã cấu hình"
}

# Update
update_deps() {
    echo -e "${BLUE}[UPDATE]${NC} Đang update dependencies..."
    cd "$APP_DIR"
    source venv/bin/activate
    pip install -q --upgrade pip
    pip install -q --upgrade -r requirements.txt
    deactivate
    echo -e "${GREEN}✓ Dependencies đã được update${NC}"
    echo -e "${YELLOW}Restart service để áp dụng: ./app-manager.sh restart${NC}"
}

# Backup
backup_db() {
    echo -e "${BLUE}[BACKUP]${NC} Đang backup database..."
    BACKUP_DIR="$APP_DIR/backups"
    mkdir -p "$BACKUP_DIR"
    DATE=$(date +%Y%m%d_%H%M%S)
    
    if [ -f "$APP_DIR/instance/security_app.db" ]; then
        cp "$APP_DIR/instance/security_app.db" "$BACKUP_DIR/security_app_$DATE.db"
        echo -e "${GREEN}✓ Backup thành công: security_app_$DATE.db${NC}"
        
        # Giữ 7 bản backup gần nhất
        ls -t "$BACKUP_DIR"/security_app_*.db | tail -n +8 | xargs rm -f 2>/dev/null
        echo -e "${YELLOW}Đã giữ 7 bản backup gần nhất${NC}"
    else
        echo -e "${RED}✗ Database không tồn tại${NC}"
    fi
}

# Backup Users
backup_users() {
    show_banner
    echo -e "${BLUE}[BACKUP USERS]${NC} Đang backup tất cả user..."
    echo ""

    # Kiểm tra file user_backup_restore.py
    if [ ! -f "$APP_DIR/user_backup_restore.py" ]; then
        echo -e "${RED}✗ Không tìm thấy file user_backup_restore.py${NC}"
        exit 1
    fi

    # Kiểm tra Python và venv
    if [ -d "$APP_DIR/venv" ]; then
        PYTHON="$APP_DIR/venv/bin/python"
    else
        PYTHON="python3"
    fi

    # Chạy backup
    cd "$APP_DIR"
    echo -e "${CYAN}Đang chạy backup script...${NC}"
    echo ""

    # Tạo temporary Python script để chạy backup
    cat > /tmp/run_backup.py << 'EOF'
import sys
import os
sys.path.insert(0, os.getcwd())
from user_backup_restore import backup_users
backup_users()
EOF

    $PYTHON /tmp/run_backup.py
    EXIT_CODE=$?
    rm -f /tmp/run_backup.py

    echo ""
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              🎉 BACKUP USER THÀNH CÔNG! 🎉                            ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}File backup:${NC} backups/users_backup.json"
        echo ""
        echo -e "${YELLOW}Lưu ý:${NC}"
        echo "  • File backup chứa tất cả thông tin user (username, password hash, role)"
        echo "  • Có thể commit file này vào Git để đồng bộ user giữa các môi trường"
        echo "  • Dùng lệnh 'restore-users' để khôi phục user từ backup"
    else
        echo -e "${RED}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║                    ⚠️  BACKUP THẤT BẠI! ⚠️                            ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    fi
    echo ""
}

# Restore Users
restore_users() {
    show_banner
    echo -e "${BLUE}[RESTORE USERS]${NC} Đang restore user từ backup..."
    echo ""

    # Kiểm tra file backup
    if [ ! -f "$APP_DIR/backups/users_backup.json" ]; then
        echo -e "${RED}✗ Không tìm thấy file backup!${NC}"
        echo -e "${YELLOW}Đường dẫn:${NC} $APP_DIR/backups/users_backup.json"
        echo ""
        echo -e "${CYAN}Vui lòng chạy backup trước:${NC}"
        echo "  ./app-manager.sh backup-users"
        echo ""
        exit 1
    fi

    # Kiểm tra file user_backup_restore.py
    if [ ! -f "$APP_DIR/user_backup_restore.py" ]; then
        echo -e "${RED}✗ Không tìm thấy file user_backup_restore.py${NC}"
        exit 1
    fi

    # Kiểm tra Python và venv
    if [ -d "$APP_DIR/venv" ]; then
        PYTHON="$APP_DIR/venv/bin/python"
    else
        PYTHON="python3"
    fi

    # Hiển thị thông tin backup
    echo -e "${CYAN}Thông tin file backup:${NC}"
    BACKUP_DATE=$(grep -o '"backup_date": "[^"]*"' "$APP_DIR/backups/users_backup.json" | cut -d'"' -f4)
    TOTAL_USERS=$(grep -o '"total_users": [0-9]*' "$APP_DIR/backups/users_backup.json" | grep -o '[0-9]*')
    echo "  📅 Ngày backup: $BACKUP_DATE"
    echo "  👥 Số lượng user: $TOTAL_USERS"
    echo ""

    # Cảnh báo
    echo -e "${RED}⚠️  CẢNH BÁO:${NC}"
    echo "  • Quá trình restore sẽ XÓA TẤT CẢ user hiện có"
    echo "  • Sau đó tạo lại user từ file backup"
    echo "  • Không thể hoàn tác sau khi restore!"
    echo ""

    # Xác nhận
    read -p "Bạn có chắc chắn muốn tiếp tục? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ] && [ "$CONFIRM" != "y" ]; then
        echo ""
        echo -e "${YELLOW}❌ Đã hủy quá trình restore.${NC}"
        echo ""
        exit 0
    fi

    # Chạy restore
    cd "$APP_DIR"
    echo ""
    echo -e "${CYAN}Đang chạy restore script...${NC}"
    echo ""

    # Tạo temporary Python script để chạy restore (tự động confirm)
    cat > /tmp/run_restore.py << 'EOF'
import sys
import os
sys.path.insert(0, os.getcwd())

# Mock input để tự động confirm
original_input = __builtins__.input
def mock_input(prompt):
    if "yes/no" in prompt.lower():
        print(prompt + "yes")
        return "yes"
    return original_input(prompt)
__builtins__.input = mock_input

from user_backup_restore import restore_users
restore_users()
EOF

    $PYTHON /tmp/run_restore.py
    EXIT_CODE=$?
    rm -f /tmp/run_restore.py

    echo ""
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              🎉 RESTORE USER THÀNH CÔNG! 🎉                           ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}Đã restore $TOTAL_USERS user từ backup${NC}"
        echo ""
        echo -e "${YELLOW}Bước tiếp theo:${NC}"
        echo "  • Restart ứng dụng: ./app-manager.sh restart"
        echo "  • Đăng nhập với user đã restore"
    else
        echo -e "${RED}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║                    ⚠️  RESTORE THẤT BẠI! ⚠️                           ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    fi
    echo ""
}

# Reset Admin Password
reset_admin_password() {
    show_banner
    echo -e "${BLUE}[RESET ADMIN PASSWORD]${NC} Reset mật khẩu tài khoản admin..."
    echo ""

    # Kiểm tra Python và venv
    if [ -d "$APP_DIR/venv" ]; then
        PYTHON="$APP_DIR/venv/bin/python"
    else
        PYTHON="python3"
    fi

    # Hiển thị thông tin
    echo -e "${CYAN}Tính năng này sẽ:${NC}"
    echo "  • Reset mật khẩu cho tài khoản admin"
    echo "  • Kích hoạt lại tài khoản nếu bị khóa"
    echo "  • Reset số lần đăng nhập sai về 0"
    echo ""

    # Tùy chọn
    echo -e "${YELLOW}Chọn một tùy chọn:${NC}"
    echo "  1. Reset về mật khẩu mặc định (admin123)"
    echo "  2. Đặt mật khẩu mới"
    echo ""
    read -p "Nhập lựa chọn (1 hoặc 2): " CHOICE

    if [ "$CHOICE" = "1" ]; then
        NEW_PASSWORD="admin123"
        echo ""
        echo -e "${CYAN}Sẽ reset mật khẩu admin về: ${YELLOW}admin123${NC}"
    elif [ "$CHOICE" = "2" ]; then
        echo ""
        read -sp "Nhập mật khẩu mới (ít nhất 6 ký tự): " NEW_PASSWORD
        echo ""

        # Kiểm tra độ dài mật khẩu
        if [ ${#NEW_PASSWORD} -lt 6 ]; then
            echo ""
            echo -e "${RED}✗ Mật khẩu phải có ít nhất 6 ký tự!${NC}"
            echo ""
            exit 1
        fi

        read -sp "Xác nhận mật khẩu mới: " CONFIRM_PASSWORD
        echo ""

        if [ "$NEW_PASSWORD" != "$CONFIRM_PASSWORD" ]; then
            echo ""
            echo -e "${RED}✗ Mật khẩu xác nhận không khớp!${NC}"
            echo ""
            exit 1
        fi
    else
        echo ""
        echo -e "${RED}✗ Lựa chọn không hợp lệ!${NC}"
        echo ""
        exit 1
    fi

    # Xác nhận cuối cùng
    echo ""
    echo -e "${RED}⚠️  CẢNH BÁO:${NC}"
    echo "  • Mật khẩu admin hiện tại sẽ bị thay đổi"
    echo "  • Tài khoản sẽ được kích hoạt lại nếu bị khóa"
    echo ""
    read -p "Bạn có chắc chắn muốn tiếp tục? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ] && [ "$CONFIRM" != "y" ]; then
        echo ""
        echo -e "${YELLOW}❌ Đã hủy quá trình reset.${NC}"
        echo ""
        exit 0
    fi

    # Chạy reset
    cd "$APP_DIR"
    echo ""
    echo -e "${CYAN}Đang reset mật khẩu admin...${NC}"
    echo ""

    # Tạo temporary Python script để reset password
    cat > /tmp/reset_admin.py << EOF
import sys
import os
sys.path.insert(0, os.getcwd())

from app import app, db, User

with app.app_context():
    # Tìm user admin
    admin = User.query.filter_by(username='admin').first()

    if not admin:
        print("❌ Không tìm thấy tài khoản admin!")
        print("")
        print("Đang tạo tài khoản admin mới...")
        admin = User(
            username='admin',
            email='admin@company.com',
            role='admin'
        )
        admin.set_password('$NEW_PASSWORD')
        admin.is_active = True
        db.session.add(admin)
        db.session.commit()
        print("✅ Đã tạo tài khoản admin mới")
    else:
        # Reset password
        admin.set_password('$NEW_PASSWORD')

        # Kích hoạt lại tài khoản
        admin.is_active = True

        # Reset số lần đăng nhập sai
        admin.reset_failed_login_attempts()

        db.session.commit()
        print("✅ Đã reset mật khẩu admin thành công")
        print("")
        print("Thông tin tài khoản:")
        print(f"  • Username: {admin.username}")
        print(f"  • Email: {admin.email}")
        print(f"  • Role: {admin.role}")
        print(f"  • Trạng thái: {'Hoạt động' if admin.is_active else 'Bị khóa'}")
        print(f"  • Số lần đăng nhập sai: {admin.failed_login_attempts}")
EOF

    $PYTHON /tmp/reset_admin.py
    EXIT_CODE=$?
    rm -f /tmp/reset_admin.py

    echo ""
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              🎉 RESET MẬT KHẨU ADMIN THÀNH CÔNG! 🎉                   ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}Thông tin đăng nhập:${NC}"
        echo -e "  • Username: ${GREEN}admin${NC}"
        if [ "$CHOICE" = "1" ]; then
            echo -e "  • Password: ${GREEN}admin123${NC}"
        else
            echo -e "  • Password: ${GREEN}(mật khẩu bạn vừa đặt)${NC}"
        fi
        echo ""
        echo -e "${YELLOW}Bước tiếp theo:${NC}"
        echo "  • Đăng nhập lại với mật khẩu mới"
        echo "  • Khuyến nghị đổi mật khẩu sau khi đăng nhập"
    else
        echo -e "${RED}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║                    ⚠️  RESET THẤT BẠI! ⚠️                             ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    fi
    echo ""
}

# Info
show_info() {
    show_banner
    echo -e "${CYAN}System Information:${NC}"
    echo -e "  OS:           $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
    echo -e "  Python:       $(python3 --version)"
    echo -e "  User:         $(whoami)"
    echo -e "  App Dir:      $APP_DIR"
    echo ""
    echo -e "${CYAN}Service Information:${NC}"
    echo -e "  Service:      $SERVICE_NAME"
    echo -e "  Status:       $(sudo systemctl is-active $SERVICE_NAME)"
    echo -e "  Enabled:      $(sudo systemctl is-enabled $SERVICE_NAME)"
    echo ""
    echo -e "${CYAN}Database:${NC}"
    if [ -f "$APP_DIR/instance/security_app.db" ]; then
        SIZE=$(du -h "$APP_DIR/instance/security_app.db" | cut -f1)
        echo -e "  File:         security_app.db"
        echo -e "  Size:         $SIZE"
    else
        echo -e "  ${RED}Database chưa được khởi tạo${NC}"
    fi
}

# Configure Nginx
configure_nginx() {
    show_banner
    echo -e "${BLUE}[NGINX SETUP]${NC} Cấu hình Nginx reverse proxy với static files..."
    echo ""

    # Kiểm tra Nginx đã cài chưa
    if ! command -v nginx &> /dev/null; then
        echo -e "${YELLOW}Nginx chưa được cài đặt. Đang cài đặt...${NC}"
        sudo apt update -qq
        sudo apt install -y nginx
        echo -e "${GREEN}✓ Nginx đã được cài đặt${NC}"
    else
        echo -e "${GREEN}✓ Nginx đã được cài đặt${NC}"
    fi

    # Lấy thông tin
    echo -e "${CYAN}Cấu hình domain/IP:${NC}"
    read -p "Nhập domain/subdomain (ví dụ: security.example.com hoặc để trống dùng IP): " DOMAIN

    if [ -z "$DOMAIN" ]; then
        DOMAIN=$(hostname -I | awk '{print $1}')
        echo -e "${YELLOW}Sử dụng IP: $DOMAIN${NC}"
    fi

    # Kiểm tra thư mục static
    echo ""
    echo -e "${CYAN}[1/7]${NC} Kiểm tra thư mục static..."
    if [ -d "$APP_DIR/static" ]; then
        echo -e "${GREEN}  ✓ Thư mục static tồn tại${NC}"

        # Liệt kê nội dung
        echo -e "${CYAN}  Nội dung thư mục static:${NC}"
        ls -la "$APP_DIR/static/" | head -10 | sed 's/^/    /'

        # Cấp quyền đọc
        echo -e "${CYAN}  Đang cấp quyền đọc...${NC}"
        sudo chmod -R 755 "$APP_DIR/static/"
        echo -e "${GREEN}  ✓ Đã cấp quyền 755${NC}"
    else
        echo -e "${YELLOW}  ⚠ Thư mục static không tồn tại, đang tạo...${NC}"
        mkdir -p "$APP_DIR/static/css" "$APP_DIR/static/js" "$APP_DIR/static/logo"
        sudo chmod -R 755 "$APP_DIR/static/"
        echo -e "${GREEN}  ✓ Đã tạo thư mục static${NC}"
    fi

    # Tạo cấu hình Nginx
    NGINX_CONF="/etc/nginx/sites-available/security-app"

    echo ""
    echo -e "${CYAN}[2/7]${NC} Đang tạo cấu hình Nginx..."

    sudo tee "$NGINX_CONF" > /dev/null << EOF
# ============================================================================
# Security App - Nginx Reverse Proxy Configuration
# ============================================================================
# Created: $(date)
# App Directory: $APP_DIR
# Backend: http://127.0.0.1:5000
# Frontend: http://$DOMAIN
# ============================================================================

server {
    listen 80;
    server_name $DOMAIN;

    # Logging
    access_log /var/log/nginx/security-app-access.log;
    error_log /var/log/nginx/security-app-error.log;

    # Client settings
    client_max_body_size 10M;
    client_body_timeout 60s;

    # ========================================================================
    # STATIC FILES - Serve trực tiếp từ Nginx (hiệu suất cao)
    # ========================================================================

    # CSS files
    location /static/css/ {
        alias $APP_DIR/static/css/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;

        # MIME types
        types {
            text/css css;
        }
    }

    # JavaScript files
    location /static/js/ {
        alias $APP_DIR/static/js/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;

        # MIME types
        types {
            application/javascript js;
        }
    }

    # Logo/Images
    location /static/logo/ {
        alias $APP_DIR/static/logo/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;

        # MIME types
        types {
            image/png png;
            image/jpeg jpg jpeg;
            image/svg+xml svg;
            image/x-icon ico;
        }
    }

    # Tất cả static files khác
    location /static/ {
        alias $APP_DIR/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;

        # Auto index (tùy chọn, để debug)
        # autoindex on;
    }

    # ========================================================================
    # FLASK APPLICATION - Proxy đến Flask backend
    # ========================================================================

    location / {
        # Proxy đến Flask app
        proxy_pass http://127.0.0.1:5000;

        # Headers cần thiết
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;

        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        # Buffering
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # ========================================================================
    # SECURITY HEADERS
    # ========================================================================

    # Ngăn clickjacking
    add_header X-Frame-Options "SAMEORIGIN" always;

    # XSS Protection
    add_header X-XSS-Protection "1; mode=block" always;

    # Content Type sniffing
    add_header X-Content-Type-Options "nosniff" always;

    # Referrer Policy
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
EOF

    echo -e "${GREEN}  ✓ Đã tạo cấu hình${NC}"

    # Enable site
    echo ""
    echo -e "${CYAN}[3/7]${NC} Đang enable site..."
    sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/security-app
    echo -e "${GREEN}  ✓ Đã tạo symbolic link${NC}"

    # Remove default nếu tồn tại
    echo ""
    echo -e "${CYAN}[4/7]${NC} Kiểm tra cấu hình default..."
    if [ -f "/etc/nginx/sites-enabled/default" ]; then
        echo -e "${YELLOW}  Xóa cấu hình default...${NC}"
        sudo rm /etc/nginx/sites-enabled/default
        echo -e "${GREEN}  ✓ Đã xóa default${NC}"
    else
        echo -e "${GREEN}  ✓ Không có default config${NC}"
    fi

    # Test cấu hình
    echo ""
    echo -e "${CYAN}[5/7]${NC} Đang test cấu hình Nginx..."
    if sudo nginx -t 2>&1 | grep -q "successful"; then
        echo -e "${GREEN}  ✓ Cấu hình hợp lệ${NC}"

        # Reload Nginx
        echo ""
        echo -e "${CYAN}[6/7]${NC} Đang reload Nginx..."
        sudo systemctl reload nginx
        sudo systemctl enable nginx >/dev/null 2>&1
        echo -e "${GREEN}  ✓ Nginx đã được reload${NC}"

        # Verify static files
        echo ""
        echo -e "${CYAN}[7/7]${NC} Kiểm tra static files..."
        sleep 1

        # Test CSS file nếu tồn tại
        if [ -f "$APP_DIR/static/css/style.css" ]; then
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/style.css)
            if [ "$HTTP_CODE" = "200" ]; then
                echo -e "${GREEN}  ✓ CSS file load thành công (HTTP $HTTP_CODE)${NC}"
            else
                echo -e "${YELLOW}  ⚠ CSS file HTTP $HTTP_CODE${NC}"
            fi
        fi

        # Test homepage
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/)
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
            echo -e "${GREEN}  ✓ Homepage load thành công (HTTP $HTTP_CODE)${NC}"
        else
            echo -e "${YELLOW}  ⚠ Homepage HTTP $HTTP_CODE${NC}"
        fi

        echo ""
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║        Nginx Reverse Proxy Đã Cấu Hình Thành Công!        ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}📍 Thông tin truy cập:${NC}"
        echo -e "  • Qua Nginx (khuyến nghị): ${GREEN}http://$DOMAIN${NC}"
        echo -e "  • Trực tiếp Flask:          ${YELLOW}http://$DOMAIN:5000${NC}"
        echo ""
        echo -e "${CYAN}📁 Static files:${NC}"
        echo -e "  • CSS:  ${GREEN}http://$DOMAIN/static/css/${NC}"
        echo -e "  • JS:   ${GREEN}http://$DOMAIN/static/js/${NC}"
        echo -e "  • Logo: ${GREEN}http://$DOMAIN/static/logo/${NC}"
        echo ""
        echo -e "${CYAN}📊 Logs:${NC}"
        echo -e "  • Access: ${YELLOW}/var/log/nginx/security-app-access.log${NC}"
        echo -e "  • Error:  ${YELLOW}/var/log/nginx/security-app-error.log${NC}"
        echo ""
        echo -e "${CYAN}🔧 Lệnh hữu ích:${NC}"
        echo -e "  • Test Nginx:   ${YELLOW}./app-manager.sh nginx-test${NC}"
        echo -e "  • Reload Nginx: ${YELLOW}./app-manager.sh nginx-reload${NC}"
        echo -e "  • Kiểm tra UI:  ${YELLOW}./app-manager.sh nginx-check${NC}"
        echo -e "  • Xem logs:     ${YELLOW}tail -f /var/log/nginx/security-app-error.log${NC}"
        echo ""
        echo -e "${CYAN}🔒 SSL (tùy chọn):${NC}"
        echo -e "  • Cài SSL:      ${YELLOW}sudo certbot --nginx -d $DOMAIN${NC}"
        echo ""
    else
        echo -e "${RED}  ✗ Cấu hình có lỗi${NC}"
        echo ""
        sudo nginx -t
        echo ""
        echo -e "${YELLOW}Vui lòng kiểm tra lại cấu hình${NC}"
    fi
}

# Test Nginx
test_nginx() {
    echo -e "${BLUE}[NGINX TEST]${NC} Đang test cấu hình Nginx..."
    echo ""
    sudo nginx -t
}

# Reload Nginx
reload_nginx() {
    echo -e "${BLUE}[NGINX RELOAD]${NC} Đang reload Nginx..."
    if sudo nginx -t; then
        sudo systemctl reload nginx
        echo -e "${GREEN}✓ Nginx đã được reload${NC}"
    else
        echo -e "${RED}✗ Cấu hình có lỗi, không reload${NC}"
    fi
}

# Fix Permissions cho Static Files
fix_permissions() {
    show_banner
    echo -e "${BLUE}[FIX PERMISSIONS]${NC} Sửa lỗi Permission Denied cho Static Files..."
    echo ""

    # Kiểm tra thư mục static
    echo -e "${CYAN}[1/5]${NC} Kiểm tra thư mục static..."
    if [ -d "$APP_DIR/static" ]; then
        echo -e "${GREEN}  ✓ Thư mục static tồn tại: $APP_DIR/static${NC}"
    else
        echo -e "${RED}  ✗ Thư mục static không tồn tại!${NC}"
        exit 1
    fi

    # Cấp quyền cho static
    echo ""
    echo -e "${CYAN}[2/5]${NC} Cấp quyền 755 cho thư mục static và tất cả file bên trong..."
    sudo chmod -R 755 "$APP_DIR/static/"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  ✓ Đã cấp quyền 755 cho static/${NC}"
    else
        echo -e "${RED}  ✗ Lỗi khi cấp quyền!${NC}"
        exit 1
    fi

    # Cấp quyền cho thư mục cha
    echo ""
    echo -e "${CYAN}[3/5]${NC} Cấp quyền execute cho thư mục cha..."
    sudo chmod 755 "$APP_DIR"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  ✓ Đã cấp quyền 755 cho $APP_DIR${NC}"
    else
        echo -e "${YELLOW}  ⚠ Không thể cấp quyền cho $APP_DIR${NC}"
    fi

    PARENT_DIR="$(dirname "$APP_DIR")"
    sudo chmod 755 "$PARENT_DIR"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  ✓ Đã cấp quyền 755 cho $PARENT_DIR${NC}"
    else
        echo -e "${YELLOW}  ⚠ Không thể cấp quyền cho $PARENT_DIR${NC}"
    fi

    # Kiểm tra quyền
    echo ""
    echo -e "${CYAN}[4/5]${NC} Kiểm tra quyền..."
    echo ""
    echo -e "${YELLOW}Quyền thư mục static:${NC}"
    ls -ld "$APP_DIR/static/"
    echo ""
    echo -e "${YELLOW}Quyền các file trong static/css:${NC}"
    ls -la "$APP_DIR/static/css/" 2>/dev/null | head -5
    echo ""
    echo -e "${YELLOW}Quyền các file trong static/js:${NC}"
    ls -la "$APP_DIR/static/js/" 2>/dev/null | head -5
    echo ""
    echo -e "${YELLOW}Quyền các file trong static/logo:${NC}"
    ls -la "$APP_DIR/static/logo/" 2>/dev/null | head -5

    # Test truy cập
    echo ""
    echo -e "${CYAN}[5/5]${NC} Test truy cập file..."
    echo ""

    # Reload Nginx
    echo -e "${YELLOW}Reload Nginx...${NC}"
    sudo systemctl reload nginx 2>/dev/null
    sleep 1

    # Test CSS
    echo -e "${YELLOW}Test CSS file:${NC}"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/style.css 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}  ✓ CSS file load thành công (HTTP $HTTP_CODE)${NC}"
        CSS_OK=1
    elif [ "$HTTP_CODE" = "404" ]; then
        echo -e "${RED}  ✗ CSS file không tìm thấy (HTTP $HTTP_CODE)${NC}"
        CSS_OK=0
    elif [ "$HTTP_CODE" = "403" ]; then
        echo -e "${RED}  ✗ Vẫn còn lỗi permission (HTTP $HTTP_CODE)${NC}"
        CSS_OK=0
    else
        echo -e "${YELLOW}  ⚠ HTTP code: $HTTP_CODE${NC}"
        CSS_OK=0
    fi

    # Test Logo
    echo ""
    echo -e "${YELLOW}Test Logo file:${NC}"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/logo/logo.png 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}  ✓ Logo file load thành công (HTTP $HTTP_CODE)${NC}"
        LOGO_OK=1
    elif [ "$HTTP_CODE" = "404" ]; then
        echo -e "${RED}  ✗ Logo file không tìm thấy (HTTP $HTTP_CODE)${NC}"
        LOGO_OK=0
    elif [ "$HTTP_CODE" = "403" ]; then
        echo -e "${RED}  ✗ Vẫn còn lỗi permission (HTTP $HTTP_CODE)${NC}"
        LOGO_OK=0
    else
        echo -e "${YELLOW}  ⚠ HTTP code: $HTTP_CODE${NC}"
        LOGO_OK=0
    fi

    # Kết quả
    echo ""
    echo "════════════════════════════════════════════════════════════════════════════"
    echo ""

    if [ "$CSS_OK" = "1" ] && [ "$LOGO_OK" = "1" ]; then
        echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║              🎉 ĐÃ SỬA XONG LỖI PERMISSION! 🎉                         ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}Static files giờ đã load được!${NC}"
        echo ""
        echo -e "${YELLOW}Bước tiếp theo:${NC}"
        echo "  1. Mở browser: http://your-ip"
        echo "  2. Nhấn F12 → Network"
        echo "  3. Kiểm tra CSS/JS load (status 200)"
    else
        echo -e "${YELLOW}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}║                    ⚠️  VẪN CÒN VẤN ĐỀ! ⚠️                             ║${NC}"
        echo -e "${YELLOW}╚════════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}Các bước debug tiếp theo:${NC}"
        echo ""
        echo "1. Kiểm tra Nginx error log:"
        echo "   ${YELLOW}sudo tail -20 /var/log/nginx/security-app-error.log${NC}"
        echo ""
        echo "2. Test với Nginx user:"
        echo "   ${YELLOW}sudo -u www-data cat $APP_DIR/static/css/style.css${NC}"
        echo ""
        echo "3. Kiểm tra quyền từng cấp:"
        echo "   ${YELLOW}namei -l $APP_DIR/static/css/style.css${NC}"
        echo ""
        echo "4. Xem hướng dẫn chi tiết:"
        echo "   ${YELLOW}cat FIX_PERMISSION_DENIED.txt${NC}"
    fi

    echo ""
    echo "════════════════════════════════════════════════════════════════════════════"
    echo ""
}

# Check Nginx và Static Files
check_nginx() {
    show_banner
    echo -e "${BLUE}[NGINX CHECK]${NC} Kiểm tra Nginx và Static Files..."
    echo ""

    PASS=0
    FAIL=0

    # 1. Kiểm tra Nginx đã cài
    echo -e "${CYAN}[1/10]${NC} Kiểm tra Nginx đã cài..."
    if command -v nginx &> /dev/null; then
        echo -e "${GREEN}  ✓ Nginx đã cài đặt${NC}"
        nginx -v 2>&1 | sed 's/^/    /'
        ((PASS++))
    else
        echo -e "${RED}  ✗ Nginx chưa được cài đặt${NC}"
        ((FAIL++))
    fi

    # 2. Kiểm tra Nginx đang chạy
    echo ""
    echo -e "${CYAN}[2/10]${NC} Kiểm tra Nginx đang chạy..."
    if sudo systemctl is-active --quiet nginx; then
        echo -e "${GREEN}  ✓ Nginx đang chạy${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Nginx không chạy${NC}"
        echo -e "${YELLOW}  Khởi động: sudo systemctl start nginx${NC}"
        ((FAIL++))
    fi

    # 3. Kiểm tra cấu hình Nginx
    echo ""
    echo -e "${CYAN}[3/10]${NC} Kiểm tra cấu hình Nginx..."
    if sudo nginx -t 2>&1 | grep -q "successful"; then
        echo -e "${GREEN}  ✓ Cấu hình hợp lệ${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Cấu hình có lỗi${NC}"
        sudo nginx -t 2>&1 | sed 's/^/    /'
        ((FAIL++))
    fi

    # 4. Kiểm tra file config tồn tại
    echo ""
    echo -e "${CYAN}[4/10]${NC} Kiểm tra file config security-app..."
    if [ -f "/etc/nginx/sites-available/security-app" ]; then
        echo -e "${GREEN}  ✓ File config tồn tại${NC}"
        ((PASS++))

        # Kiểm tra symbolic link
        if [ -L "/etc/nginx/sites-enabled/security-app" ]; then
            echo -e "${GREEN}  ✓ Symbolic link đã được tạo${NC}"
            ((PASS++))
        else
            echo -e "${RED}  ✗ Chưa có symbolic link${NC}"
            echo -e "${YELLOW}  Tạo link: sudo ln -s /etc/nginx/sites-available/security-app /etc/nginx/sites-enabled/${NC}"
            ((FAIL++))
        fi
    else
        echo -e "${RED}  ✗ File config không tồn tại${NC}"
        echo -e "${YELLOW}  Chạy: ./app-manager.sh nginx${NC}"
        ((FAIL++))
    fi

    # 5. Kiểm tra thư mục static
    echo ""
    echo -e "${CYAN}[5/10]${NC} Kiểm tra thư mục static..."
    if [ -d "$APP_DIR/static" ]; then
        echo -e "${GREEN}  ✓ Thư mục static tồn tại${NC}"
        ((PASS++))

        # Liệt kê nội dung
        echo -e "${CYAN}  Nội dung:${NC}"
        ls -la "$APP_DIR/static/" | head -8 | sed 's/^/    /'
    else
        echo -e "${RED}  ✗ Thư mục static không tồn tại${NC}"
        ((FAIL++))
    fi

    # 6. Kiểm tra quyền thư mục static
    echo ""
    echo -e "${CYAN}[6/10]${NC} Kiểm tra quyền thư mục static..."
    if [ -r "$APP_DIR/static" ]; then
        echo -e "${GREEN}  ✓ Có quyền đọc thư mục static${NC}"
        ((PASS++))

        # Hiển thị quyền
        PERMS=$(stat -c "%a" "$APP_DIR/static" 2>/dev/null || stat -f "%Lp" "$APP_DIR/static" 2>/dev/null)
        echo -e "${CYAN}  Quyền hiện tại: ${YELLOW}$PERMS${NC}"
    else
        echo -e "${RED}  ✗ Không có quyền đọc thư mục static${NC}"
        echo -e "${YELLOW}  Cấp quyền: sudo chmod -R 755 $APP_DIR/static/${NC}"
        ((FAIL++))
    fi

    # 7. Kiểm tra Flask app đang chạy
    echo ""
    echo -e "${CYAN}[7/10]${NC} Kiểm tra Flask app..."
    if pgrep -f "python.*app.py" > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ Flask app đang chạy${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Flask app không chạy${NC}"
        echo -e "${YELLOW}  Khởi động: ./app-manager.sh start${NC}"
        ((FAIL++))
    fi

    # 8. Test truy cập homepage qua Nginx
    echo ""
    echo -e "${CYAN}[8/10]${NC} Test truy cập homepage qua Nginx..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        echo -e "${GREEN}  ✓ Homepage load thành công (HTTP $HTTP_CODE)${NC}"
        ((PASS++))
    else
        echo -e "${RED}  ✗ Homepage không load (HTTP $HTTP_CODE)${NC}"
        ((FAIL++))
    fi

    # 9. Test static CSS file
    echo ""
    echo -e "${CYAN}[9/10]${NC} Test static CSS file..."
    if [ -f "$APP_DIR/static/css/style.css" ]; then
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/style.css 2>/dev/null)
        if [ "$HTTP_CODE" = "200" ]; then
            echo -e "${GREEN}  ✓ CSS file load thành công (HTTP $HTTP_CODE)${NC}"
            ((PASS++))

            # Kiểm tra MIME type
            MIME=$(curl -s -I http://localhost/static/css/style.css 2>/dev/null | grep -i "content-type" | awk '{print $2}')
            echo -e "${CYAN}  MIME type: ${YELLOW}$MIME${NC}"
        else
            echo -e "${RED}  ✗ CSS file không load (HTTP $HTTP_CODE)${NC}"
            ((FAIL++))
        fi
    else
        echo -e "${YELLOW}  ⚠ File style.css không tồn tại${NC}"
    fi

    # 10. Kiểm tra logs
    echo ""
    echo -e "${CYAN}[10/10]${NC} Kiểm tra Nginx logs..."
    if [ -f "/var/log/nginx/security-app-error.log" ]; then
        echo -e "${GREEN}  ✓ Error log tồn tại${NC}"
        ((PASS++))

        # Hiển thị 3 dòng cuối
        echo -e "${CYAN}  3 dòng cuối error log:${NC}"
        sudo tail -3 /var/log/nginx/security-app-error.log 2>/dev/null | sed 's/^/    /' || echo "    (trống)"
    else
        echo -e "${YELLOW}  ⚠ Error log chưa tồn tại${NC}"
    fi

    # Tổng kết
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}  KẾT QUẢ KIỂM TRA${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    TOTAL=$((PASS + FAIL))
    if [ $TOTAL -gt 0 ]; then
        PERCENT=$((PASS * 100 / TOTAL))
    else
        PERCENT=0
    fi

    echo -e "  ${GREEN}✓ PASS: $PASS${NC}"
    echo -e "  ${RED}✗ FAIL: $FAIL${NC}"
    echo -e "  📊 Tổng:  $TOTAL"
    echo -e "  📈 Tỷ lệ: ${PERCENT}%"
    echo ""

    if [ $FAIL -eq 0 ]; then
        echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║     🎉 TẤT CẢ KIỂM TRA ĐỀU PASS! 🎉    ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${CYAN}Giao diện web đang hoạt động bình thường!${NC}"
        echo -e "${CYAN}Truy cập: ${GREEN}http://$(hostname -I | awk '{print $1}')${NC}"
    else
        echo -e "${RED}╔════════════════════════════════════════╗${NC}"
        echo -e "${RED}║        ⚠️  CÓ LỖI CẦN SỬA! ⚠️          ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${YELLOW}Hướng dẫn sửa lỗi:${NC}"

        if ! command -v nginx &> /dev/null; then
            echo -e "  1. Cài Nginx: ${CYAN}sudo apt install nginx${NC}"
        fi

        if ! sudo systemctl is-active --quiet nginx; then
            echo -e "  2. Start Nginx: ${CYAN}sudo systemctl start nginx${NC}"
        fi

        if [ ! -f "/etc/nginx/sites-available/security-app" ]; then
            echo -e "  3. Cấu hình Nginx: ${CYAN}./app-manager.sh nginx${NC}"
        fi

        if ! pgrep -f "python.*app.py" > /dev/null 2>&1; then
            echo -e "  4. Start Flask: ${CYAN}./app-manager.sh start${NC}"
        fi

        echo ""
        echo -e "${YELLOW}Hoặc xem hướng dẫn chi tiết: ${CYAN}HUONG_DAN_NGINX.md${NC}"
    fi
    echo ""
}

# Uninstall Service
uninstall_service() {
    show_banner
    echo -e "${RED}[UNINSTALL SERVICE]${NC} Gỡ bỏ hoàn toàn service..."
    echo ""

    # Cảnh báo
    echo -e "${RED}⚠️  CẢNH BÁO - THAO TÁC NGUY HIỂM! ⚠️${NC}"
    echo ""
    echo -e "${YELLOW}Thao tác này sẽ:${NC}"
    echo "  1. Dừng và xóa systemd service"
    echo "  2. Xóa file service khỏi hệ thống"
    echo "  3. KHÔNG xóa mã nguồn và database"
    echo "  4. KHÔNG xóa virtual environment"
    echo ""
    echo -e "${CYAN}Lưu ý:${NC}"
    echo "  • Mã nguồn vẫn được giữ lại tại: $APP_DIR"
    echo "  • Database vẫn được giữ lại tại: $APP_DIR/instance/"
    echo "  • Có thể deploy lại bằng: ./app-manager.sh deploy"
    echo ""

    # Xác nhận lần 1
    read -p "Bạn có chắc chắn muốn gỡ bỏ service? (yes/no): " CONFIRM1
    if [ "$CONFIRM1" != "yes" ] && [ "$CONFIRM1" != "y" ]; then
        echo ""
        echo -e "${YELLOW}❌ Đã hủy thao tác gỡ bỏ.${NC}"
        echo ""
        exit 0
    fi

    # Xác nhận lần 2
    echo ""
    echo -e "${RED}Xác nhận lần cuối!${NC}"
    read -p "Gõ 'UNINSTALL' để xác nhận gỡ bỏ service: " CONFIRM2
    if [ "$CONFIRM2" != "UNINSTALL" ]; then
        echo ""
        echo -e "${YELLOW}❌ Đã hủy thao tác gỡ bỏ.${NC}"
        echo ""
        exit 0
    fi

    echo ""
    echo -e "${CYAN}Bắt đầu gỡ bỏ service...${NC}"
    echo ""

    # 1. Dừng service
    echo -e "${CYAN}[1/4]${NC} Dừng service..."
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        sudo systemctl stop $SERVICE_NAME
        echo -e "${GREEN}  ✓ Đã dừng service${NC}"
    else
        echo -e "${YELLOW}  ⚠ Service không chạy${NC}"
    fi

    # 2. Disable service
    echo ""
    echo -e "${CYAN}[2/4]${NC} Disable service..."
    if sudo systemctl is-enabled --quiet $SERVICE_NAME 2>/dev/null; then
        sudo systemctl disable $SERVICE_NAME
        echo -e "${GREEN}  ✓ Đã disable service${NC}"
    else
        echo -e "${YELLOW}  ⚠ Service chưa được enable${NC}"
    fi

    # 3. Xóa file service
    echo ""
    echo -e "${CYAN}[3/4]${NC} Xóa file service..."
    if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        sudo rm -f "/etc/systemd/system/$SERVICE_NAME.service"
        echo -e "${GREEN}  ✓ Đã xóa /etc/systemd/system/$SERVICE_NAME.service${NC}"
    else
        echo -e "${YELLOW}  ⚠ File service không tồn tại${NC}"
    fi

    # 4. Reload systemd daemon
    echo ""
    echo -e "${CYAN}[4/4]${NC} Reload systemd daemon..."
    sudo systemctl daemon-reload
    sudo systemctl reset-failed 2>/dev/null
    echo -e "${GREEN}  ✓ Đã reload daemon${NC}"

    # Kết quả
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              🎉 GỠ BỎ SERVICE THÀNH CÔNG! 🎉                          ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Trạng thái:${NC}"
    echo "  • Service đã được gỡ bỏ khỏi systemd"
    echo "  • Ứng dụng không còn tự động khởi động"
    echo ""
    echo -e "${YELLOW}Dữ liệu được giữ lại:${NC}"
    echo "  • Mã nguồn: $APP_DIR"
    echo "  • Database: $APP_DIR/instance/"
    echo "  • Backups: $APP_DIR/backups/"
    echo "  • Virtual env: $APP_DIR/venv/"
    echo ""
    echo -e "${CYAN}Để deploy lại:${NC}"
    echo "  ./app-manager.sh deploy"
    echo ""
}

# Uninstall Nginx
uninstall_nginx() {
    show_banner
    echo -e "${RED}[UNINSTALL NGINX]${NC} Gỡ bỏ cấu hình Nginx..."
    echo ""

    # Cảnh báo
    echo -e "${RED}⚠️  CẢNH BÁO! ⚠️${NC}"
    echo ""
    echo -e "${YELLOW}Thao tác này sẽ:${NC}"
    echo "  1. Xóa cấu hình Nginx cho ứng dụng này"
    echo "  2. Xóa symbolic link trong sites-enabled"
    echo "  3. Reload Nginx"
    echo "  4. KHÔNG gỡ cài đặt Nginx (Nginx vẫn chạy)"
    echo ""
    echo -e "${CYAN}Lưu ý:${NC}"
    echo "  • Nginx vẫn được giữ lại cho các ứng dụng khác"
    echo "  • Chỉ xóa cấu hình của ứng dụng Security App"
    echo "  • Có thể cấu hình lại bằng: ./app-manager.sh nginx"
    echo ""

    # Xác nhận
    read -p "Bạn có chắc chắn muốn gỡ bỏ cấu hình Nginx? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ] && [ "$CONFIRM" != "y" ]; then
        echo ""
        echo -e "${YELLOW}❌ Đã hủy thao tác gỡ bỏ.${NC}"
        echo ""
        exit 0
    fi

    echo ""
    echo -e "${CYAN}Bắt đầu gỡ bỏ cấu hình Nginx...${NC}"
    echo ""

    # 1. Xóa symbolic link
    echo -e "${CYAN}[1/4]${NC} Xóa symbolic link..."
    if [ -L "/etc/nginx/sites-enabled/security-app" ]; then
        sudo rm -f /etc/nginx/sites-enabled/security-app
        echo -e "${GREEN}  ✓ Đã xóa /etc/nginx/sites-enabled/security-app${NC}"
    else
        echo -e "${YELLOW}  ⚠ Symbolic link không tồn tại${NC}"
    fi

    # 2. Xóa file cấu hình
    echo ""
    echo -e "${CYAN}[2/4]${NC} Xóa file cấu hình..."
    if [ -f "/etc/nginx/sites-available/security-app" ]; then
        sudo rm -f /etc/nginx/sites-available/security-app
        echo -e "${GREEN}  ✓ Đã xóa /etc/nginx/sites-available/security-app${NC}"
    else
        echo -e "${YELLOW}  ⚠ File cấu hình không tồn tại${NC}"
    fi

    # 3. Test cấu hình Nginx
    echo ""
    echo -e "${CYAN}[3/4]${NC} Test cấu hình Nginx..."
    if sudo nginx -t 2>&1 | grep -q "successful"; then
        echo -e "${GREEN}  ✓ Cấu hình Nginx hợp lệ${NC}"
    else
        echo -e "${RED}  ✗ Cấu hình Nginx có lỗi${NC}"
        echo ""
        sudo nginx -t
        echo ""
        echo -e "${YELLOW}Vui lòng kiểm tra lại cấu hình Nginx${NC}"
        exit 1
    fi

    # 4. Reload Nginx
    echo ""
    echo -e "${CYAN}[4/4]${NC} Reload Nginx..."
    sudo systemctl reload nginx
    echo -e "${GREEN}  ✓ Đã reload Nginx${NC}"

    # Kết quả
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              🎉 GỠ BỎ CẤU HÌNH NGINX THÀNH CÔNG! 🎉                   ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Trạng thái:${NC}"
    echo "  • Cấu hình Nginx cho Security App đã được gỡ bỏ"
    echo "  • Nginx vẫn đang chạy bình thường"
    echo "  • Ứng dụng vẫn có thể truy cập qua port 5000"
    echo ""
    echo -e "${YELLOW}Truy cập ứng dụng:${NC}"
    IP=$(hostname -I | awk '{print $1}')
    echo "  • Trực tiếp Flask: http://$IP:5000"
    echo ""
    echo -e "${CYAN}Để cấu hình lại Nginx:${NC}"
    echo "  ./app-manager.sh nginx"
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
    logs-n)
        show_logs_n "$2"
        ;;
    logs-error)
        show_logs_error
        ;;
    test)
        test_app
        ;;
    update)
        update_deps
        ;;
    backup)
        backup_db
        ;;
    backup-users)
        backup_users
        ;;
    restore-users)
        restore_users
        ;;
    reset-admin)
        reset_admin_password
        ;;
    info)
        show_info
        ;;
    nginx)
        configure_nginx
        ;;
    nginx-test)
        test_nginx
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
        show_menu
        ;;
    "")
        show_menu
        ;;
    *)
        echo -e "${RED}Lệnh không hợp lệ: $1${NC}"
        echo ""
        show_menu
        exit 1
        ;;
esac

