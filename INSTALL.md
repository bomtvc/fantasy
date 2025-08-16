# Hướng dẫn cài đặt FPL League Analyzer

## 📋 Yêu cầu hệ thống

- **Python 3.10 trở lên**
- **Kết nối Internet** (để gọi FPL API)
- **Web browser** để xem ứng dụng Streamlit

## 🛠️ Cài đặt từng bước

### Bước 1: Kiểm tra Python

Mở terminal/command prompt và chạy:

```bash
python --version
```

Hoặc:

```bash
python3 --version
```

Nếu chưa có Python, tải về từ: https://www.python.org/downloads/

### Bước 2: Clone/Download project

```bash
# Nếu có git
git clone <repository-url>
cd fantasy

# Hoặc download và giải nén vào thư mục fantasy/
```

### Bước 3: Tạo virtual environment (khuyến nghị)

```bash
# Tạo virtual environment
python -m venv fpl_env

# Kích hoạt virtual environment
# Trên Windows:
fpl_env\Scripts\activate

# Trên macOS/Linux:
source fpl_env/bin/activate
```

### Bước 4: Cài đặt dependencies

```bash
pip install -r requirements.txt
```

Nếu gặp lỗi, thử cài từng package:

```bash
pip install streamlit>=1.28.0
pip install pandas>=2.0.0
pip install requests>=2.31.0
pip install plotly>=5.15.0
pip install numpy>=1.24.0
```

### Bước 5: Test API (tùy chọn)

Chạy demo để kiểm tra API:

```bash
python demo.py
```

Nếu thành công, bạn sẽ thấy:
```
✅ All API tests passed! The FPL APIs are working correctly.
```

### Bước 6: Chạy ứng dụng

```bash
streamlit run app.py
```

Ứng dụng sẽ mở tại: http://localhost:8501

## 🚨 Xử lý lỗi thường gặp

### Lỗi: "streamlit: command not found"

**Nguyên nhân**: Streamlit chưa được cài đặt hoặc không trong PATH

**Giải pháp**:
```bash
pip install streamlit
# Hoặc
python -m pip install streamlit
```

### Lỗi: "ModuleNotFoundError: No module named 'xxx'"

**Nguyên nhân**: Thiếu dependencies

**Giải pháp**:
```bash
pip install -r requirements.txt
# Hoặc cài từng package bị thiếu
pip install <package-name>
```

### Lỗi: "Permission denied" hoặc "Access denied"

**Nguyên nhân**: Quyền truy cập file/thư mục

**Giải pháp**:
- Chạy terminal với quyền Administrator (Windows)
- Sử dụng `sudo` (macOS/Linux)
- Kiểm tra quyền truy cập thư mục

### Lỗi: "SSL Certificate" hoặc "Connection Error"

**Nguyên nhân**: Vấn đề kết nối mạng hoặc firewall

**Giải pháp**:
- Kiểm tra kết nối Internet
- Tắt VPN/Proxy tạm thời
- Kiểm tra firewall settings

### Lỗi: "Rate limit" từ FPL API

**Nguyên nhân**: Gọi API quá nhiều/nhanh

**Giải pháp**:
- Đợi vài phút rồi thử lại
- Giảm số entries trong settings
- Tăng REQUEST_DELAY trong config.py

## 🔧 Cấu hình nâng cao

### Tùy chỉnh settings

Chỉnh sửa file `config.py`:

```python
# Tăng delay để tránh rate limit
REQUEST_DELAY = 0.5  # Từ 0.3 lên 0.5

# Giảm số thread
MAX_WORKERS = 4  # Từ 6 xuống 4

# Tăng timeout
REQUEST_TIMEOUT = 15  # Từ 10 lên 15
```

### Chạy trên port khác

```bash
streamlit run app.py --server.port 8502
```

### Chạy trên network

```bash
streamlit run app.py --server.address 0.0.0.0
```

## 📱 Sử dụng trên mobile

Ứng dụng responsive, có thể sử dụng trên mobile browser:

1. Chạy app với `--server.address 0.0.0.0`
2. Tìm IP của máy tính: `ipconfig` (Windows) hoặc `ifconfig` (macOS/Linux)
3. Truy cập từ mobile: `http://<IP>:8501`

## 🐳 Docker (tùy chọn)

Tạo file `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
```

Chạy:
```bash
docker build -t fpl-analyzer .
docker run -p 8501:8501 fpl-analyzer
```

## 📞 Hỗ trợ

Nếu gặp vấn đề:

1. Kiểm tra file `demo.py` chạy được không
2. Xem log lỗi chi tiết
3. Kiểm tra requirements.txt
4. Thử tạo virtual environment mới

## 📝 Ghi chú

- Ứng dụng cần Internet để gọi FPL API
- Dữ liệu được cache để tăng tốc độ
- Không cần đăng nhập FPL account
- Hỗ trợ export CSV cho tất cả bảng dữ liệu
