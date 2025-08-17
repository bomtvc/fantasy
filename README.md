# FPL League Analyzer

Web application for analyzing Fantasy Premier League (FPL) League data using Streamlit.

## 🚀 Features

- **League Analysis**: Fetch data from FPL public APIs
- **Points by Gameweek**: Display detailed points for each GW with interactive charts
- **Points by Month**: Group GWs into months and calculate total points
- **Top Picks**: Top 5 most picked players
- **Rankings**: Weekly and monthly rankings with medals for top 3
- **Awards Statistics**: Track weekly and monthly wins for each manager
- **Chip History**: Track chip usage (Wildcard, Free Hit, Bench Boost, Triple Captain) for each manager by gameweek
- **CSV Export**: Export data to CSV files
- **Charts**: Interactive visualization with Plotly
- **Caching**: Tối ưu hiệu năng với cache
- **Clean UI**: Ẩn các thông báo không cần thiết để giao diện gọn gàng

## 📋 Yêu cầu

- Python 3.10+
- Các package trong `requirements.txt`

## 🛠️ Cài đặt

1. Clone hoặc download project
2. Cài đặt dependencies:
```bash
pip install -r requirements.txt
```

3. Chạy ứng dụng:
```bash
streamlit run app.py
```

4. Mở browser tại `http://localhost:8501`

## 📖 Hướng dẫn sử dụng

### 1. Cấu hình cơ bản
- **League ID**: ID của league muốn phân tích (mặc định: 1042917)
- **Phase**: Phase của league (thường là 1)
- **Phân trang**: Nếu league có nhiều thành viên

### 2. Chọn Gameweek Range
- **GW bắt đầu**: Gameweek đầu tiên (1-38)
- **GW kết thúc**: Gameweek cuối cùng (1-38)

### 3. Month Mapping
Định nghĩa cách gom các GW thành tháng:
```
1-4,5-9,10-13,14-17,18-21,22-26,27-30,31-34,35-38
```
Có nghĩa là:
- Month 1: GW 1-4
- Month 2: GW 5-9
- Month 3: GW 10-13
- ...

### 4. Tối ưu hiệu năng
- **Giới hạn entries**: Để test nhanh với ít dữ liệu
- Dữ liệu được cache để tăng tốc độ

## 📊 Các Tab chính

### 👥 League Members
- Danh sách tất cả thành viên trong league
- Thông tin: Entry ID, Player Name, Team Name, Rank

### 📊 GW Points
- Điểm chi tiết theo từng Gameweek
- Bao gồm: Points, Transfers, Transfer Costs, Total Points
- Hiển thị dạng bảng pivot

### 📅 Month Points
- Điểm gom theo tháng dựa trên Month Mapping
- Biểu đồ line chart cho top 10 entries
- Tổng điểm theo tháng

### ⭐ Top Picks
- Top 5 cầu thủ được pick nhiều nhất
- Có thể chọn 1 GW cụ thể hoặc gom nhiều GW
- Biểu đồ bar chart với phần trăm

### 🏆 Rankings
- Bảng xếp hạng theo tuần và theo tháng
- Huy chương vàng, bạc, đồng cho top 3
- Lọc theo GW và Month (mặc định là hiện tại)
- Thống kê tổng quan và biểu đồ phân phối điểm

### 🏅 Awards Statistics
- Thống kê số lần nhất tuần và nhất tháng của từng Manager
- Bảng xếp hạng theo tổng số giải thưởng
- Biểu đồ phân tích: Stacked Bar, Pie Chart, Scatter Plot
- Metrics tổng quan về giải thưởng

### 🎯 Chip History
- Lịch sử sử dụng chip của từng manager theo từng gameweek
- Bảng hiển thị: Manager, Team, và các cột GW (không có cột Rank)
- Hiển thị trực quan với icon từ file `statics/` và màu sắc cho từng loại chip:
  - Wildcard (màu cam #ff9800) - icon từ `statics/wildcard.png`
  - Free Hit (màu xanh dương #2196f3) - icon từ `statics/freehit.png`
  - Bench Boost (màu xanh lá #4caf50) - icon từ `statics/bboost.png`
  - Triple Captain (màu tím #9c27b0) - icon từ `statics/3xc.png`
- Template hiển thị: icon ở trên, text ở dưới (theo thiết kế được cung cấp)
- Icon được chuyển đổi thành base64 để embed trực tiếp vào HTML
- Sắp xếp theo tên Manager (alphabetical order)
- Thống kê tổng quan về việc sử dụng chip
- Biểu đồ phân tích chip usage theo GW và loại chip
- Hover effects và animation cho chip containers

## 🔧 API Endpoints sử dụng

1. **League Standings**:
   ```
   https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/
   ```

2. **Entry Picks**:
   ```
   https://fantasy.premierleague.com/api/entry/{entry_id}/event/{gw}/picks/
   ```

3. **Bootstrap Static**:
   ```
   https://fantasy.premierleague.com/api/bootstrap-static/
   ```

## ⚡ Tối ưu hiệu năng

- **Caching**: Bootstrap data cache 10 phút, API calls cache 5 phút
- **Threading**: Sử dụng ThreadPoolExecutor để gọi API song song
- **Rate Limiting**: Delay 0.3s giữa các request
- **Progress Bar**: Hiển thị tiến trình khi load dữ liệu

## 🚨 Xử lý lỗi

- **Rate Limit**: Tự động retry với exponential backoff
- **Missing Data**: Điền giá trị mặc định cho dữ liệu thiếu
- **API Errors**: Thông báo lỗi rõ ràng cho user

## 📁 Cấu trúc file

```
fantasy/
├── app.py              # Ứng dụng Streamlit chính
├── requirements.txt    # Dependencies
└── README.md          # Hướng dẫn này
```

## 🔍 Troubleshooting

### Lỗi thường gặp:

1. **"Không thể lấy dữ liệu"**:
   - Kiểm tra kết nối internet
   - League ID có đúng không
   - Thử giảm số GW hoặc entries

2. **"Rate limit"**:
   - Đợi vài phút rồi thử lại
   - Giảm số entries để test

3. **"Month mapping không hợp lệ"**:
   - Kiểm tra format: "1-4,5-9,10-13"
   - Không có khoảng trắng thừa

## 📝 Ghi chú

- Ứng dụng chỉ sử dụng API công khai, không cần đăng nhập
- Dữ liệu được cache để tránh gọi API quá nhiều
- Hỗ trợ export CSV cho tất cả bảng dữ liệu
- Responsive design, hoạt động tốt trên mobile

## 🤝 Đóng góp

Mọi đóng góp và feedback đều được chào đón!
