# NOC Monitoring Toolkit – Bộ công cụ giám sát hạ tầng và phát hiện bất thường

**Môn học:** Python cho An toàn thông tin  
**Chủ đề:** Topic 09  
**Nhóm:** Nhóm 1  
**Repository:** https://github.com/anvohoang/topic09-noc-monitoring-nhom1  
**Trạng thái:** Đã tích hợp các thành phần chính; tiếp tục kiểm thử và hoàn thiện hệ thống.

---

## 1. Giới thiệu dự án

NOC Monitoring Toolkit là bộ công cụ giám sát hạ tầng máy tính, máy chủ và dịch vụ mạng được xây dựng bằng ngôn ngữ Python.

Hệ thống được thiết kế theo mô hình Central Server – Collector Agent. Các máy tính cần giám sát (Node) chạy chương trình Collector Agent để thu thập thông tin tài nguyên hệ thống và kiểm tra dịch vụ HTTP. Dữ liệu sau đó được gửi qua mạng đến máy chủ trung tâm (Central Server) để lưu trữ, phân tích, phát hiện dấu hiệu bất thường và quản lý cảnh báo.

Kết quả giám sát được hiển thị trên giao diện web được xây dựng bằng Streamlit, giúp người vận hành theo dõi tình trạng hoạt động của các Node, tài nguyên hệ thống, dịch vụ HTTP và những cảnh báo phát sinh.

Dự án được triển khai bằng các tiến trình Python độc lập trên Windows, không bắt buộc sử dụng Docker. Mô hình này giúp nhóm giảm độ phức tạp trong quá trình cài đặt, cấu hình và thử nghiệm trên môi trường máy tính cá nhân và mạng LAN.

Dự án phục vụ mục đích học tập, thực hành lập trình Python và nghiên cứu các kỹ thuật giám sát hạ tầng trong môi trường do nhóm quản lý hoặc được cấp phép.

## 2. Mục tiêu dự án

Các mục tiêu chính của dự án:

- Thu thập các chỉ số hoạt động của hệ thống gồm CPU, RAM, ổ đĩa và lưu lượng mạng.
- Giám sát trạng thái hoạt động và thời gian phản hồi của các dịch vụ HTTP.
- Xây dựng cơ chế truyền dữ liệu từ các Collector Agent đến máy chủ trung tâm thông qua REST API.
- Xác thực các yêu cầu gửi dữ liệu bằng API Key.
- Lưu trữ dữ liệu giám sát và lịch sử cảnh báo bằng SQLite.
- Phân tích dữ liệu bằng ngưỡng tĩnh và Rolling Z-Score để phát hiện các dấu hiệu bất thường.
- Xây dựng cơ chế quản lý vòng đời cảnh báo, hạn chế cảnh báo trùng lặp và hỗ trợ tự động giải quyết cảnh báo.
- Xây dựng giao diện Dashboard trực quan để theo dõi tình trạng hệ thống.
- Mô phỏng các tình huống bất thường nhằm kiểm tra hoạt động của hệ thống.
- Tạo nền tảng để mở rộng khả năng giám sát nhiều máy tính và dịch vụ trong mạng nội bộ.

## 3. Các chức năng chính

Bảng dưới đây thể hiện tình trạng triển khai của các thành phần dựa trên mã nguồn hiện tại.

| Chức năng | Trạng thái | Mô tả |
|---|---|---|
| Thu thập chỉ số CPU, RAM, Disk | Hoàn thành | Thu thập mức sử dụng tài nguyên hệ thống trên từng Node. |
| Thu thập chỉ số Network | Hoàn thành | Ghi nhận lượng dữ liệu mạng gửi và nhận theo chu kỳ. |
| Giám sát dịch vụ HTTP | Hoàn thành | Kiểm tra trạng thái phản hồi và thời gian phản hồi của endpoint. |
| Collector Agent | Hoàn thành | Gửi dữ liệu giám sát đến Central Server thông qua API. |
| Central API | Hoàn thành | Tiếp nhận dữ liệu, xác thực API Key và cung cấp các API truy vấn. |
| SQLite Storage | Hoàn thành | Lưu trữ dữ liệu metrics, service checks và alerts. |
| Analyzer | Hoàn thành | Phân tích dữ liệu bằng ngưỡng tĩnh và Rolling Z-Score. |
| Alert Engine | Hoàn thành | Quản lý cảnh báo, cooldown, chống trùng lặp và auto-resolve. |
| Analyzer – Alert Integration | Hoàn thành | Tích hợp kết quả phân tích với hệ thống quản lý cảnh báo. |
| Streamlit Dashboard | Đã tích hợp | Hiển thị Node, CPU/RAM/Disk, dịch vụ HTTP, độ trễ và cảnh báo. |
| Xuất dữ liệu CSV | Đã tích hợp | Hỗ trợ tải dữ liệu giám sát và cảnh báo dưới dạng CSV. |
| Mô phỏng sự cố | Hoàn thành | Có các kịch bản mô phỏng phục vụ kiểm tra Alert Engine. |
| Unit Tests và Integration Tests | Đã có | Kiểm thử các chức năng Alert Engine và luồng tích hợp. |
| Kiểm thử trên nhiều máy vật lý | Cần kiểm thử thực tế | Cần xác nhận hoạt động đồng thời của các Agent trên các máy độc lập. |
| Đánh giá định lượng hiệu quả phát hiện | Chưa hoàn thiện | Cần xây dựng bộ dữ liệu và kịch bản có nhãn để đánh giá. |

### 3.1. Phạm vi Dashboard hiện tại

Dashboard được xây dựng bằng Streamlit, cung cấp các chức năng:

- Hiển thị thông tin tổng quan về các Node đang được giám sát.
- Theo dõi trạng thái Node UP/DOWN dựa trên thời điểm nhận dữ liệu gần nhất.
- Hiển thị biểu đồ CPU, RAM và Disk theo thời gian.
- Hiển thị các kết quả kiểm tra dịch vụ HTTP.
- Theo dõi mã trạng thái HTTP và thời gian phản hồi.
- Hiển thị danh sách cảnh báo và trạng thái xử lý.
- Hỗ trợ lọc dữ liệu giám sát và tải dữ liệu CSV.

**Một số giới hạn hiện tại:**

- Dashboard chưa có biểu đồ trực quan riêng cho Network.
- Dashboard hiện đọc dữ liệu trực tiếp từ SQLite thay vì gọi các API đọc dữ liệu của Central API.
- Vì sử dụng SQLite cục bộ, Dashboard cần chạy trên máy Central Server và sử dụng cùng cơ sở dữ liệu với Central API và Alert Runner.
- Khi cơ sở dữ liệu chưa có dữ liệu metrics, giao diện có thể hiển thị dữ liệu mẫu để minh họa.

## 4. Kiến trúc hệ thống

### 4.1. Mô hình tổng thể

Hệ thống gồm các thành phần chính:

1. **Collector Agent:** Chạy trên các máy Node, thu thập chỉ số tài nguyên hệ thống và kiểm tra dịch vụ HTTP.
2. **Central API:** Tiếp nhận dữ liệu từ Agent thông qua REST API và xác thực API Key.
3. **Storage:** Lưu trữ dữ liệu giám sát bằng SQLite.
4. **Analyzer:** Phân tích dữ liệu để xác định các dấu hiệu bất thường.
5. **Alert Adapter:** Chuyển đổi và chuẩn hóa kết quả phân tích sang định dạng của Alert Engine.
6. **Alert Engine:** Quản lý vòng đời cảnh báo, mức độ nghiêm trọng và trạng thái xử lý.
7. **Alert Runner:** Điều phối quá trình phân tích và xử lý cảnh báo theo chu kỳ.
8. **Dashboard:** Hiển thị kết quả giám sát thông qua giao diện web.

### 4.2. Sơ đồ luồng dữ liệu

```text
       NODE 01                  NODE 02                  NODE 03
  +----------------+       +----------------+       +----------------+
  | Collector      |       | Collector      |       | Collector      |
  | Agent          |       | Agent          |       | Agent          |
  +-------+--------+       +-------+--------+       +-------+--------+
          |                        |                        |
          +------------------------+------------------------+
                                   |
                             HTTP REST API
                                   |
                                   v
                     +--------------------------+
                     |       CENTRAL SERVER     |
                     |                          |
                     |       Central API        |
                     |            |             |
                     |            v             |
                     |      SQLite Storage      |
                     |            |             |
                     |            v             |
                     |         Analyzer         |
                     |            |             |
                     |            v             |
                     |       Alert Adapter      |
                     |            |             |
                     |            v             |
                     |       Alert Engine       |
                     |            |             |
                     |            v             |
                     |       Alert Runner       |
                     |                          |
                     |            |             |
                     |            v             |
                     |    Streamlit Dashboard   |
                     +--------------------------+
```

Dashboard hiện truy cập trực tiếp cơ sở dữ liệu SQLite trên Central Server. Sơ đồ thể hiện kiến trúc tổng quát của hệ thống, không có nghĩa Dashboard hiện truy vấn dữ liệu thông qua Central API.

### 4.3. Cơ chế hoạt động

Quy trình xử lý dữ liệu:

1. Collector Agent thu thập các chỉ số CPU, RAM, Disk và Network tại máy Node.
2. Agent kiểm tra trạng thái và thời gian phản hồi của dịch vụ HTTP.
3. Agent đóng gói dữ liệu thành payload và gửi về Central API.
4. Central API xác thực API Key và kiểm tra dữ liệu đầu vào.
5. Dữ liệu hợp lệ được lưu vào cơ sở dữ liệu SQLite.
6. Alert Runner định kỳ lấy danh sách Node và yêu cầu Analyzer thực hiện phân tích.
7. Kết quả phân tích được chuyển qua Alert Adapter.
8. Alert Engine xử lý kết quả, tạo mới, cập nhật hoặc tự động giải quyết cảnh báo.
9. Dashboard hiển thị các dữ liệu giám sát và cảnh báo để người vận hành theo dõi.

### 4.4. Các API chính

| Phương thức | Endpoint | Chức năng |
|---|---|---|
| GET | `/health` | Kiểm tra trạng thái hoạt động của Central API. |
| POST | `/api/v1/collector/payload` | Tiếp nhận dữ liệu từ Collector Agent. |
| GET | `/api/v1/nodes` | Lấy danh sách Node. |
| GET | `/api/v1/metrics/latest` | Truy vấn metrics mới nhất. |
| GET | `/api/v1/metrics` | Truy vấn lịch sử metrics. |
| GET | `/api/v1/service-checks` | Truy vấn lịch sử kiểm tra dịch vụ. |
| GET | `/api/v1/alerts` | Truy vấn danh sách cảnh báo. |
| GET | `/api/v1/analyzer/{node_id}` | Lấy kết quả phân tích của một Node. |

Các API nghiệp vụ yêu cầu xác thực thông qua HTTP header `X-API-Key`. Endpoint `/health` được sử dụng để kiểm tra tình trạng hoạt động của API.

Có thể truy cập tài liệu API tại:

```text
http://127.0.0.1:8000/docs
```

## 5. Công nghệ sử dụng

| Công nghệ / Thư viện | Mục đích |
|---|---|
| Python 3.14.x | Ngôn ngữ lập trình chính. |
| psutil | Thu thập thông tin CPU, RAM, Disk và Network. |
| httpx | Gửi HTTP request và kiểm tra các dịch vụ HTTP. |
| FastAPI | Xây dựng Central REST API. |
| Uvicorn | Chạy ứng dụng FastAPI. |
| SQLite | Lưu trữ dữ liệu giám sát và cảnh báo. |
| NumPy | Hỗ trợ tính toán và xử lý dữ liệu. |
| Streamlit | Xây dựng giao diện giám sát web. |
| Plotly | Trực quan hóa dữ liệu và biểu đồ. |
| pandas | Xử lý, lọc và hiển thị dữ liệu trên Dashboard. |
| unittest | Thực hiện kiểm thử tự động. |
| Git | Quản lý phiên bản mã nguồn. |
| GitHub | Lưu trữ mã nguồn và phối hợp làm việc nhóm. |
| ChatGPT (OpenAI) | Hỗ trợ tham khảo, giải thích kỹ thuật, đề xuất mã nguồn và gỡ lỗi trong quá trình phát triển. |

Các thư viện Python cần thiết được khai báo trong tệp `requirements.txt`.

## 6. Cấu trúc thư mục dự án

```text
topic09-noc-monitoring-nhom1/
│
├── alerts/
│   ├── __init__.py
│   └── engine.py
│
├── analyzer/
│   ├── __init__.py
│   └── anomaly.py
│
├── api/
│   ├── __init__.py
│   └── main.py
│
├── collector/
│   ├── __init__.py
│   └── collector.py
│
├── integration/
│   ├── __init__.py
│   ├── alert_adapter.py
│   └── collector_storage.py
│
├── storage/
│   ├── __init__.py
│   └── database.py
│
├── tests/
│   ├── test_alerts.py
│   └── test_alert_integration.py
│
├── ui/
│   └── app.py
│
├── run_agent.py
├── run_alerts.py
├── run_collector.py
├── stress_sim.py
│
├── requirements.txt
├── .gitignore
└── README.md
```

### 6.1. Chức năng các thư mục và tệp

| Thư mục / Tệp | Chức năng |
|---|---|
| `collector/` | Thu thập chỉ số hệ thống và kiểm tra dịch vụ HTTP. |
| `storage/` | Khởi tạo SQLite, quản lý bảng và các hàm lưu trữ, truy vấn. |
| `integration/collector_storage.py` | Chuyển payload Collector thành dữ liệu lưu trữ. |
| `integration/alert_adapter.py` | Chuẩn hóa kết quả Analyzer cho Alert Engine. |
| `analyzer/` | Chứa thuật toán và logic phát hiện bất thường. |
| `alerts/` | Quản lý cảnh báo và vòng đời xử lý cảnh báo. |
| `api/` | Xây dựng Central REST API. |
| `ui/` | Chứa mã nguồn giao diện Streamlit Dashboard. |
| `tests/` | Chứa các chương trình kiểm thử tự động. |
| `run_agent.py` | Khởi chạy Collector Agent và gửi dữ liệu lên Central API. |
| `run_alerts.py` | Khởi chạy tiến trình phân tích và quản lý cảnh báo. |
| `run_collector.py` | Chạy Collector theo chế độ ghi dữ liệu trực tiếp vào SQLite cục bộ. |
| `stress_sim.py` | Mô phỏng các tình huống bất thường để kiểm thử. |
| `requirements.txt` | Danh sách các thư viện Python cần cài đặt. |
| `.gitignore` | Các tệp và thư mục không đưa lên GitHub. |
| `README.md` | Tài liệu giới thiệu và hướng dẫn sử dụng dự án. |

## 7. Yêu cầu môi trường

Để cài đặt và chạy dự án, máy tính cần đáp ứng:

- Hệ điều hành Windows 10/11 hoặc môi trường tương thích với Python.
- Python 3.14.x.
- Git.
- Visual Studio Code hoặc trình soạn thảo mã nguồn Python tương đương.
- Kết nối mạng nội bộ giữa các máy khi triển khai mô hình nhiều Node.
- Kết nối Internet để cài đặt thư viện và kiểm tra các endpoint HTTP bên ngoài.

Nhóm đang sử dụng Python 3.14.10 trong môi trường phát triển.

Các thành viên nên sử dụng cùng phiên bản Python và cài đặt thư viện từ `requirements.txt` để hạn chế khác biệt môi trường.

## 8. Hướng dẫn cài đặt

### 8.1. Clone repository

Mở PowerShell hoặc Git Bash và thực hiện:

```bash
git clone https://github.com/anvohoang/topic09-noc-monitoring-nhom1.git
cd topic09-noc-monitoring-nhom1
```

Nếu đã có mã nguồn trên máy, cập nhật nhánh `main`:

```bash
git switch main
git pull origin main
```

### 8.2. Tạo môi trường ảo

Trên Windows PowerShell:

```powershell
py -3.14 -m venv .venv
```

Kích hoạt môi trường ảo:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn thực thi script, có thể sử dụng lệnh sau trong phiên PowerShell hiện tại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Kiểm tra phiên bản Python:

```powershell
python --version
```

### 8.3. Cài đặt thư viện

Sau khi kích hoạt môi trường ảo, chạy:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Kiểm tra các thư viện:

```bash
python -m pip check
```

## 9. Cấu hình hệ thống

### 9.1. Cấu hình API Key

Central API và tất cả Collector Agent phải sử dụng cùng một API Key để xác thực.

Không ghi API Key trực tiếp vào mã nguồn hoặc đưa khóa thật lên GitHub.

Trên Windows PowerShell, có thể lưu API Key vào biến môi trường người dùng:

```powershell
[Environment]::SetEnvironmentVariable("NOC_API_KEY", "<YOUR_SHARED_API_KEY>", "User")
```

Thay `<YOUR_SHARED_API_KEY>` bằng API Key do nhóm tự tạo.

Sau khi thiết lập biến môi trường, mở terminal mới để nhận giá trị đã lưu.

Đối với Git Bash, có thể nạp lại biến môi trường từ Windows:

```bash
export NOC_API_KEY="$(powershell.exe -NoProfile -Command '[Environment]::GetEnvironmentVariable("NOC_API_KEY","User")' | tr -d '\r')"
```

Thực hiện cấu hình này trên Central Server và các máy Agent.

### 9.2. Cấu hình địa chỉ Central API

Nếu Agent chạy cùng máy với Central API, có thể sử dụng địa chỉ mặc định:

```text
http://127.0.0.1:8000
```

Nếu Agent chạy trên máy khác, cần cấu hình địa chỉ IP LAN của máy Central Server.

Ví dụ:

```bash
export NOC_API_URL="http://192.168.1.10:8000"
```

Trong đó `192.168.1.10` chỉ là địa chỉ minh họa, cần thay bằng địa chỉ IPv4 thực tế của Central Server.

### 9.3. Các biến môi trường

| Biến môi trường | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `NOC_API_KEY` | Khóa xác thực với Central API. | Không có, cần cấu hình. |
| `NOC_API_URL` | Địa chỉ Central API. | `http://127.0.0.1:8000` |
| `NOC_NODE_ID` | Định danh của máy Node. | Hostname viết thường. |
| `NOC_TARGET_URL` | Endpoint HTTP cần kiểm tra. | `https://httpbin.org/get` |
| `NOC_INTERVAL_SECONDS` | Chu kỳ gửi dữ liệu. | `5` giây. |

Mỗi máy Agent cần có `NOC_NODE_ID` riêng để Central Server phân biệt dữ liệu của từng Node.

## 10. Hướng dẫn chạy hệ thống

### 10.1. Khởi chạy Central API

Trên máy được chọn làm Central Server, mở terminal tại thư mục dự án.

Nạp API Key:

```bash
export NOC_API_KEY="$(powershell.exe -NoProfile -Command '[Environment]::GetEnvironmentVariable("NOC_API_KEY","User")' | tr -d '\r')"
```

Khởi chạy API:

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Sau khi API hoạt động, có thể kiểm tra:

```text
http://127.0.0.1:8000/health
```

Tài liệu API:

```text
http://127.0.0.1:8000/docs
```

### 10.2. Khởi chạy Collector Agent

Trên từng máy Node, mở terminal tại thư mục dự án.

Nạp API Key:

```bash
export NOC_API_KEY="$(powershell.exe -NoProfile -Command '[Environment]::GetEnvironmentVariable("NOC_API_KEY","User")' | tr -d '\r')"
```

Cấu hình địa chỉ Central API:

```bash
export NOC_API_URL="http://192.168.1.10:8000"
```

Thiết lập Node ID:

```bash
export NOC_NODE_ID="$(hostname | tr '[:upper:]' '[:lower:]')"
```

Thiết lập endpoint kiểm tra:

```bash
export NOC_TARGET_URL="https://httpbin.org/get"
```

Khởi chạy Agent:

```bash
python run_agent.py
```

Lưu ý: Thay địa chỉ IP minh họa bằng IP LAN của Central Server.

Trên máy Central Server, nếu Agent và API chạy cùng máy, có thể sử dụng địa chỉ mặc định mà không cần cấu hình `NOC_API_URL`.

### 10.3. Khởi chạy Alert Runner

Trên Central Server, mở một terminal riêng:

```bash
python run_alerts.py
```

Alert Runner thực hiện:

- Lấy danh sách các Node đã được ghi nhận.
- Đọc dữ liệu giám sát từ SQLite.
- Gọi Analyzer để phân tích dữ liệu.
- Chuyển kết quả qua Alert Adapter.
- Gửi kết quả đến Alert Engine.
- Tạo mới, cập nhật hoặc tự động giải quyết cảnh báo.

Chỉ nên chạy một Alert Runner cho cùng một cơ sở dữ liệu tại một thời điểm.

### 10.4. Khởi chạy Streamlit Dashboard

Trên Central Server, mở terminal riêng:

```bash
python -m streamlit run ui/app.py
```

Sau khi khởi chạy, Streamlit sẽ hiển thị địa chỉ truy cập trên terminal. Thông thường:

```text
http://localhost:8501
```

Mở địa chỉ này trên trình duyệt để theo dõi hệ thống.

**Lưu ý:** Dashboard hiện đọc trực tiếp từ SQLite. Vì vậy, Dashboard cần chạy trên Central Server và sử dụng cùng cơ sở dữ liệu với Central API và Alert Runner.

### 10.5. Chạy Collector cục bộ

Ngoài chế độ Agent gửi dữ liệu qua API, dự án còn có chương trình:

```bash
python run_collector.py
```

Chương trình này thu thập dữ liệu và ghi trực tiếp vào SQLite cục bộ trên máy đang chạy.

Cần phân biệt:

- `run_agent.py`: Gửi dữ liệu từ Node đến Central API.
- `run_collector.py`: Chạy Collector theo chế độ lưu dữ liệu trực tiếp vào SQLite cục bộ.

Khi triển khai mô hình nhiều máy, nên sử dụng `run_agent.py` trên các Node để dữ liệu được tập trung tại Central Server.

## 11. Kiểm thử hệ thống

### 11.1. Kiểm tra cú pháp mã nguồn

Tại thư mục gốc của dự án, chạy:

```bash
python -m compileall -q alerts analyzer api collector integration storage tests ui run_agent.py run_alerts.py run_collector.py stress_sim.py
```

Nếu không xuất hiện lỗi cú pháp và lệnh kết thúc thành công, các module đã được biên dịch cú pháp.

### 11.2. Chạy Unit Tests và Integration Tests

Sử dụng lệnh:

```bash
python -m unittest discover -s tests -v
```

Các bài kiểm thử hiện tập trung vào:

- Chức năng quản lý cảnh báo.
- Trạng thái và vòng đời cảnh báo.
- Cơ chế cooldown và chống cảnh báo trùng lặp.
- Tích hợp Analyzer, Alert Adapter và Alert Engine.

Các bài kiểm thử này không thay thế việc kiểm thử toàn bộ Collector, API, Dashboard hoặc triển khai nhiều máy vật lý.

### 11.3. Mô phỏng sự cố

Chạy chương trình:

```bash
python stress_sim.py
```

Chương trình mô phỏng một số tình huống để kiểm tra cơ chế phát hiện và quản lý cảnh báo, bao gồm:

1. CPU tăng đột biến.
2. RAM tăng cao.
3. Độ trễ HTTP tăng.
4. Dịch vụ HTTP không khả dụng.

Dữ liệu mô phỏng phục vụ kiểm thử, không phải dữ liệu giám sát thực tế của các Node đang hoạt động.

## 12. Kiểm thử triển khai nhiều Node

Để đánh giá khả năng hoạt động trong mô hình Central Server – Collector Agent, nhóm cần thực hiện:

1. Chọn một máy tính làm Central Server.
2. Xác định địa chỉ IPv4 LAN của Central Server.
3. Khởi chạy Central API, Alert Runner và Dashboard.
4. Cài đặt môi trường Python và dependency trên các máy Node.
5. Cấu hình API Key và địa chỉ Central API trên từng Node.
6. Thiết lập `NOC_NODE_ID` khác nhau cho từng máy.
7. Khởi chạy Collector Agent trên từng Node.
8. Kiểm tra dữ liệu gửi về Central Server.
9. Theo dõi trạng thái Node, metrics, HTTP service checks và cảnh báo trên Dashboard.
10. Thực hiện ngắt kết nối hoặc dừng Agent có kiểm soát để kiểm tra khả năng cập nhật trạng thái Node.
11. Ghi nhận kết quả, hình ảnh và các vấn đề phát sinh.

Để đáp ứng yêu cầu giám sát tối thiểu ba Node độc lập, nhóm cần kiểm tra trên các máy tính riêng biệt. Việc chạy nhiều tiến trình Agent trên cùng một máy chỉ phục vụ kiểm tra sơ bộ, không thay thế kiểm thử trên các máy vật lý độc lập.

## 13. An toàn và phạm vi sử dụng

- Chỉ giám sát máy tính, dịch vụ và hệ thống thuộc quyền quản lý hoặc được cho phép kiểm thử.
- Không đưa API Key, mật khẩu, token hoặc khóa riêng tư vào repository.
- Không mở Central API trực tiếp ra Internet.
- API hiện sử dụng HTTP và API Key, do đó chỉ nên triển khai trong mạng LAN riêng hoặc VPN được kiểm soát.
- Không sử dụng hệ thống để kiểm tra hoặc tác động đến các hệ thống bên thứ ba khi chưa được ủy quyền.
- Sử dụng Node ID riêng cho từng máy để tránh nhầm lẫn dữ liệu.
- Chỉ chạy một Alert Runner trên cùng một cơ sở dữ liệu tại một thời điểm.

## 14. Thành viên và phân công nhiệm vụ

| STT | Họ và tên | Nhiệm vụ phụ trách |
|---|---|---|
| 1 | **Võ Hoàng Ân** | Điều phối nhóm; xây dựng Storage/SQLite và Central API; tích hợp các thành phần hệ thống; hỗ trợ kiểm thử, quản lý mã nguồn và hoàn thiện tài liệu. |
| 2 | **Ngô Tiến Anh** | Phát triển Collector: thu thập chỉ số CPU, RAM, Disk, Network; kiểm tra dịch vụ HTTP và xây dựng Collector Agent. |
| 3 | **Đoàn Anh Khoa** | Phát triển Analyzer: xử lý dữ liệu, xây dựng thuật toán phát hiện bất thường bằng ngưỡng tĩnh và Rolling Z-Score. |
| 4 | **Nguyễn Văn Lộc** | Phát triển Alert Engine: quản lý vòng đời cảnh báo, mức độ nghiêm trọng, cooldown, chống trùng lặp, acknowledge, auto-resolve và mô phỏng kiểm thử. |
| 5 | **Vương Tiến Tú** | Phát triển Streamlit Dashboard: hiển thị trạng thái Node, các chỉ số hệ thống, dịch vụ HTTP, cảnh báo và chức năng xuất CSV. |

Các thành viên phối hợp trong quá trình tích hợp, kiểm thử, review mã nguồn, hoàn thiện báo cáo và chuẩn bị thuyết trình.

Đóng góp của từng thành viên được theo dõi thông qua lịch sử commit, nhánh phát triển, Pull Request và hoạt động review trên GitHub.

## 15. Quy trình làm việc nhóm trên GitHub

Nhóm sử dụng Git và GitHub để quản lý mã nguồn và phối hợp phát triển.

Quy trình làm việc:

1. Cập nhật nhánh `main` trước khi bắt đầu công việc.
2. Tạo nhánh riêng cho từng tính năng hoặc lỗi cần xử lý.
3. Phát triển và kiểm thử mã nguồn trên nhánh cá nhân.
4. Commit các thay đổi với nội dung rõ ràng.
5. Push nhánh lên GitHub.
6. Tạo Pull Request để đề xuất hợp nhất mã nguồn vào `main`.
7. Thành viên khác review và kiểm tra thay đổi.
8. Chỉnh sửa nếu phát hiện lỗi hoặc vấn đề cần cải thiện.
9. Merge Pull Request sau khi đáp ứng các yêu cầu của nhóm.

Nhóm hạn chế push trực tiếp lên `main` nhằm đảm bảo khả năng theo dõi lịch sử phát triển, kiểm tra thay đổi và phân biệt đóng góp của từng thành viên.

## 16. Việc sử dụng công cụ AI trong quá trình phát triển

Trong quá trình thực hiện dự án, nhóm có sử dụng ChatGPT của OpenAI như một công cụ hỗ trợ học tập và phát triển phần mềm.

ChatGPT được sử dụng để:

- Tham khảo cách thiết kế cấu trúc chương trình và tổ chức các module.
- Hỗ trợ giải thích cú pháp Python và các thư viện được sử dụng.
- Gợi ý và tham khảo một số đoạn mã phục vụ triển khai chức năng.
- Hỗ trợ phân tích lỗi, đề xuất hướng khắc phục và cải thiện mã nguồn.
- Hỗ trợ xây dựng các trường hợp kiểm thử và rà soát tài liệu kỹ thuật.

Các nội dung mã nguồn có sự hỗ trợ từ ChatGPT được nhóm xem xét, điều chỉnh, tích hợp và kiểm tra trước khi đưa vào dự án.

ChatGPT là công cụ hỗ trợ tham khảo, không thay thế quá trình học tập, phân tích, kiểm thử và trách nhiệm của các thành viên đối với sản phẩm cuối cùng.

## 17. Tài liệu tham khảo

### 17.1. Tài liệu kỹ thuật và thư viện

1. Python Software Foundation. *Python Documentation*.  
   https://docs.python.org/3/

2. psutil Contributors. *psutil Documentation*.  
   https://psutil.readthedocs.io/

3. HTTPX. *HTTPX Documentation*.  
   https://www.python-httpx.org/

4. FastAPI. *FastAPI Documentation*.  
   https://fastapi.tiangolo.com/

5. Uvicorn. *Uvicorn Documentation*.  
   https://www.uvicorn.org/

6. SQLite. *SQLite Documentation*.  
   https://www.sqlite.org/docs.html

7. Streamlit. *Streamlit Documentation*.  
   https://docs.streamlit.io/

8. Plotly. *Plotly Python Documentation*.  
   https://plotly.com/python/

9. NumPy Developers. *NumPy Documentation*.  
   https://numpy.org/doc/

10. pandas Development Team. *pandas Documentation*.  
    https://pandas.pydata.org/docs/

11. GitHub. *GitHub Documentation*.  
    https://docs.github.com/

### 17.2. Công cụ AI hỗ trợ phát triển mã nguồn

12. OpenAI. *ChatGPT*.  
    https://chatgpt.com/

    Công cụ AI được sử dụng để hỗ trợ tham khảo ý tưởng triển khai, giải thích kỹ thuật, đề xuất một số đoạn mã, phân tích lỗi và hỗ trợ hoàn thiện tài liệu trong quá trình thực hiện dự án. Các thành viên trong nhóm chịu trách nhiệm xem xét, chỉnh sửa, tích hợp và kiểm thử mã nguồn trước khi sử dụng.

---

**Đồ án môn học:** Python cho An toàn thông tin  
**Chủ đề:** Topic 09 – NOC Monitoring Toolkit  
**Nhóm thực hiện:** Nhóm 1
