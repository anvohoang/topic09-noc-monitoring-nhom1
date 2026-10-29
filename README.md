# Bộ công cụ giám sát hạ tầng NOC và phát hiện bất thường

**Môn học:** Python cho An toàn thông tin  
**Chủ đề:** Topic 09  
**Nhóm:** Nhóm 1  
**Trạng thái dự án:** Đang phát triển

---

## 1. Tổng quan dự án

Dự án xây dựng bộ công cụ giám sát hạ tầng NOC (Trung tâm vận hành mạng) bằng ngôn ngữ Python, nhằm theo dõi tình trạng hoạt động, khả năng sẵn sàng và hiệu suất của hệ thống máy tính, máy chủ và dịch vụ mạng.

Hệ thống có nhiệm vụ thu thập các chỉ số hoạt động, lưu trữ dữ liệu theo thời gian, phát hiện những dấu hiệu bất thường, quản lý cảnh báo và hiển thị thông tin giám sát thông qua giao diện web trực quan.

Dự án được triển khai và thử nghiệm trong môi trường cục bộ, môi trường mô phỏng hoặc môi trường được cấp phép rõ ràng.

## 2. Mục tiêu dự án

Các mục tiêu chính của dự án bao gồm:

- Thu thập thông tin về mức sử dụng CPU, RAM, ổ đĩa và lưu lượng mạng.
- Giám sát trạng thái hoạt động và thời gian phản hồi của các dịch vụ HTTP.
- Lưu trữ dữ liệu theo chuỗi thời gian với dấu thời gian chuẩn UTC.
- Phát hiện bất thường bằng phương pháp ngưỡng tĩnh và Rolling Z-Score.
- Quản lý vòng đời cảnh báo, hạn chế cảnh báo trùng lặp và áp dụng thời gian chờ cảnh báo.
- Xây dựng giao diện trực quan để theo dõi tình trạng hệ thống và các cảnh báo đang hoạt động.
- Mô phỏng các tình huống sự cố để kiểm thử khả năng phát hiện của hệ thống.
- Đánh giá hiệu quả phát hiện thông qua độ chính xác, số lượng cảnh báo sai và thời gian trung bình phát hiện sự cố (MTTD).
- Hỗ trợ xuất báo cáo về thời gian hoạt động và kết quả đánh giá.

## 3. Các chức năng chính

Bảng dưới đây mô tả các chức năng dự kiến của hệ thống. Trạng thái sẽ được cập nhật theo tiến độ triển khai và kết quả kiểm thử thực tế.

| Chức năng | Trạng thái |
|---|---|
| Thu thập chỉ số hoạt động của hệ thống | Dự kiến |
| Giám sát trạng thái và độ trễ dịch vụ HTTP | Dự kiến |
| Lưu trữ dữ liệu theo thời gian bằng SQLite | Dự kiến |
| Phát hiện bất thường bằng ngưỡng tĩnh | Dự kiến |
| Phát hiện bất thường bằng Rolling Z-Score | Dự kiến |
| Quản lý vòng đời cảnh báo | Dự kiến |
| Hạn chế cảnh báo trùng lặp và áp dụng thời gian chờ | Dự kiến |
| Xây dựng giao diện giám sát bằng Streamlit | Dự kiến |
| Mô phỏng bốn tình huống sự cố | Dự kiến |
| Kiểm thử tự động | Dự kiến |
| Đánh giá hiệu quả phát hiện bất thường | Dự kiến |
| Xuất báo cáo CSV/PDF | Dự kiến |

**Ý nghĩa trạng thái:**

- **Dự kiến:** Chức năng chưa được triển khai.
- **Đang thực hiện:** Chức năng đang được phát triển.
- **Hoàn thành:** Chức năng đã được triển khai và kiểm thử.

Nhóm sẽ cập nhật trạng thái của từng chức năng trong quá trình thực hiện dự án.

## 4. Công nghệ sử dụng

| Công nghệ | Mục đích sử dụng |
|---|---|
| Python | Ngôn ngữ lập trình chính |
| psutil | Thu thập các chỉ số hoạt động của hệ thống |
| SQLite | Lưu trữ dữ liệu giám sát và lịch sử cảnh báo |
| Streamlit | Xây dựng giao diện giám sát trên web |
| Plotly | Trực quan hóa dữ liệu và biểu đồ theo thời gian |
| pandas | Xử lý và phân tích dữ liệu |
| scikit-learn | Hỗ trợ các thử nghiệm mở rộng về phát hiện bất thường |
| prometheus-client | Cung cấp các chỉ số tương thích với Prometheus |
| requests | Kiểm tra trạng thái và thời gian phản hồi của dịch vụ HTTP |
| pytest | Xây dựng và thực hiện kiểm thử tự động |
| Git | Quản lý phiên bản mã nguồn |
| GitHub | Lưu trữ mã nguồn và hỗ trợ làm việc nhóm |

## 5. Kiến trúc hệ thống

Hệ thống được thiết kế gồm các thành phần chính sau:

1. **Bộ thu thập dữ liệu:** Thu thập chỉ số hệ thống và kiểm tra trạng thái của các dịch vụ.
2. **Bộ lưu trữ:** Lưu các chỉ số cùng dấu thời gian vào cơ sở dữ liệu.
3. **Bộ phân tích:** Kiểm tra các ngưỡng tĩnh và tính toán Rolling Z-Score để nhận diện những giá trị bất thường.
4. **Bộ quản lý cảnh báo:** Tạo và cập nhật cảnh báo, quản lý trạng thái sự cố, hạn chế cảnh báo trùng lặp và áp dụng thời gian chờ.
5. **Giao diện giám sát:** Hiển thị các chỉ số, trạng thái của từng nút giám sát và danh sách cảnh báo.
6. **Bộ đánh giá:** Thực hiện các kịch bản mô phỏng sự cố và đo lường hiệu quả phát hiện.

Luồng xử lý tổng quát:

**Thu thập dữ liệu → Lưu trữ → Phân tích bất thường → Quản lý cảnh báo → Hiển thị trên giao diện → Đánh giá kết quả.**

## 6. Cấu trúc thư mục dự án

```text
topic09-noc-monitoring-nhom1/
├── .github/
│   └── workflows/
│       └── ci.yml
├── collector/
│   ├── __init__.py
│   ├── system_collector.py
│   ├── service_probe.py
│   └── poller.py
├── storage/
│   ├── __init__.py
│   └── database.py
├── analyzer/
│   ├── __init__.py
│   └── anomaly.py
├── alerts/
│   ├── __init__.py
│   └── engine.py
├── ui/
│   └── app.py
├── tests/
├── docs/
├── reports/
├── stress_sim.py
├── requirements.txt
├── .gitignore
└── README.md
```

**Ý nghĩa các thư mục và tệp:**

- `collector/`: Chứa các thành phần thu thập chỉ số hệ thống và giám sát dịch vụ.
- `storage/`: Chứa mã nguồn lưu trữ và truy vấn dữ liệu.
- `analyzer/`: Chứa các thuật toán phát hiện bất thường.
- `alerts/`: Chứa chức năng quản lý cảnh báo và thời gian chờ.
- `ui/`: Chứa mã nguồn giao diện giám sát.
- `tests/`: Chứa các chương trình kiểm thử tự động.
- `docs/`: Chứa tài liệu thiết kế và hướng dẫn kỹ thuật.
- `reports/`: Chứa báo cáo đánh giá và kết quả thực nghiệm.
- `stress_sim.py`: Chương trình mô phỏng các tình huống sự cố.
- `requirements.txt`: Danh sách các thư viện Python cần cài đặt.
- `.gitignore`: Danh sách tệp và thư mục không đưa lên GitHub.
- `README.md`: Tài liệu giới thiệu và hướng dẫn sử dụng dự án.

Cấu trúc trên là cấu trúc dự kiến và có thể được điều chỉnh theo quá trình triển khai thực tế.

## 7. Yêu cầu môi trường

Trước khi cài đặt dự án, máy tính cần đáp ứng các yêu cầu sau:

- Đã cài đặt Python 3.14.x hoặc phiên bản được cả nhóm thống nhất.
- Đã cài đặt Git.
- Có Visual Studio Code hoặc trình soạn thảo mã nguồn Python tương thích.
- Có terminal để thực hiện các lệnh cài đặt và chạy chương trình.
- Có kết nối Internet để cài đặt các thư viện cần thiết.

Tất cả thành viên nên sử dụng cùng phiên bản Python để hạn chế lỗi khác biệt môi trường.

## 8. Hướng dẫn cài đặt

### 8.1. Tải mã nguồn dự án

Mở PowerShell hoặc Terminal và chạy các lệnh sau để tải mã nguồn dự án về máy tính:

```bash
git clone https://github.com/anvohoang/topic09-noc-monitoring-nhom1.git
cd topic09-noc-monitoring-nhom1
```

Sau khi tải thành công, truy cập thư mục dự án để tiếp tục cài đặt môi trường và các thư viện cần thiết.
```

### 8.2. Tạo môi trường ảo

Trên Windows PowerShell, chạy:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Môi trường ảo giúp các thư viện của dự án được cài đặt riêng, tránh ảnh hưởng đến các dự án Python khác trên máy tính.

### 8.3. Cài đặt thư viện

Sau khi kích hoạt môi trường ảo, chạy:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Các thư viện được cài đặt theo danh sách trong tệp `requirements.txt`.

## 9. Hướng dẫn chạy chương trình

### 9.1. Khởi chạy giao diện giám sát

Sau khi giao diện đã được triển khai, sử dụng lệnh:

```bash
python -m streamlit run ui/app.py
```

Sau khi chương trình khởi chạy thành công, mở địa chỉ cục bộ được hiển thị trên terminal để truy cập giao diện giám sát.

### 9.2. Chạy các thành phần giám sát và mô phỏng sự cố

Các lệnh cụ thể để khởi chạy bộ thu thập dữ liệu và mô phỏng từng tình huống sự cố sẽ được bổ sung sau khi các thành phần tương ứng được triển khai.

Nhóm sẽ cập nhật hướng dẫn sử dụng để phù hợp với mã nguồn thực tế.

## 10. Kiểm thử hệ thống

Để thực hiện kiểm thử tự động, chạy lệnh sau tại thư mục gốc của dự án:

```bash
python -m pytest -q
```

Hệ thống dự kiến được kiểm tra với bốn tình huống:

1. CPU tăng đột biến.
2. Bộ nhớ tăng dần theo thời gian.
3. Độ trễ phản hồi HTTP tăng cao.
4. Dịch vụ không còn khả dụng.

Kết quả kiểm thử sẽ được ghi nhận sau mỗi lần chạy thực tế. Các số liệu minh họa hoặc dự kiến không được trình bày như kết quả thực nghiệm đã đo.

## 11. Đánh giá hiệu quả phát hiện bất thường

Dự án sẽ so sánh hai phương pháp phát hiện bất thường là ngưỡng tĩnh và Rolling Z-Score dựa trên các chỉ tiêu:

- **Độ chính xác phát hiện:** Đánh giá khả năng phân loại đúng trạng thái bình thường và bất thường.
- **Số lượng cảnh báo sai:** Thống kê những trường hợp hệ thống phát cảnh báo khi không có sự cố tương ứng.
- **Số lượng sự cố bị bỏ sót:** Thống kê các sự cố đã xảy ra nhưng hệ thống không phát hiện.
- **Thời gian trung bình phát hiện sự cố (MTTD):** Thời gian trung bình từ khi sự cố bắt đầu đến khi hệ thống phát cảnh báo.

Kết quả sẽ được trình bày trong bảng so sánh dựa trên dữ liệu thu được từ các lần thử nghiệm có kiểm soát.

## 12. Thành viên và phân công nhiệm vụ

| Thành viên | Nhiệm vụ phụ trách |
|---|---|
| Ân | Điều phối nhóm, xây dựng phần lưu trữ, tích hợp các thành phần và hoàn thiện tài liệu |
| Tiến Anh | Thu thập chỉ số hệ thống và giám sát dịch vụ |
| Khoa | Xây dựng thuật toán phát hiện bất thường và đánh giá kết quả |
| Lộc | Xây dựng bộ quản lý cảnh báo và chương trình mô phỏng sự cố |
| Tú | Xây dựng giao diện giám sát và chức năng xuất báo cáo |

Các thành viên phối hợp kiểm thử, tích hợp mã nguồn, hoàn thiện báo cáo và chuẩn bị bảo vệ dự án.

Đóng góp cá nhân được thể hiện thông qua lịch sử commit, nhánh phát triển, yêu cầu hợp nhất mã nguồn và hoạt động review trên GitHub.

## 13. Quy trình làm việc nhóm

Nhóm sử dụng Git và GitHub để quản lý mã nguồn và phối hợp phát triển.

Quy trình làm việc gồm các bước:

1. Tạo nhánh riêng cho từng tính năng hoặc lỗi cần sửa.
2. Phát triển và kiểm thử mã nguồn trên nhánh của mình.
3. Lưu thay đổi bằng các commit có nội dung rõ ràng.
4. Tạo yêu cầu hợp nhất mã nguồn vào nhánh `main`.
5. Nhờ thành viên khác kiểm tra và đưa ra nhận xét.
6. Sửa các vấn đề được góp ý và kiểm thử lại.
7. Hợp nhất mã nguồn sau khi quá trình kiểm tra đạt yêu cầu.

Nhóm không thực hiện push trực tiếp lên nhánh `main`.

## 14. An toàn và phạm vi kiểm thử

Mọi hoạt động thử nghiệm phải được thực hiện trong môi trường cục bộ, cô lập, mô phỏng hoặc được cấp phép rõ ràng.

Nhóm không sử dụng hệ thống để kiểm tra hoặc tác động đến các hệ thống bên thứ ba khi chưa được ủy quyền.

Không đưa mật khẩu, khóa API, mã truy cập, khóa riêng tư hoặc dữ liệu nhạy cảm vào repository.

Các tình huống sự cố được tạo ra nhằm phục vụ mục đích học tập, kiểm thử và đánh giá khả năng phát hiện bất thường của hệ thống.

## 15. Tài liệu tham khảo

Các tài liệu dưới đây được sử dụng để tra cứu kỹ thuật, triển khai các thành phần và kiểm thử hệ thống. Nhóm sẽ cập nhật danh sách theo các công nghệ thực tế được sử dụng trong dự án.

1. Python Software Foundation. *Python Documentation*.  
   https://docs.python.org/3/

2. psutil Contributors. *psutil Documentation*.  
   https://psutil.readthedocs.io/

3. Prometheus Authors. *Prometheus Python Client*.  
   https://github.com/prometheus/client_python

4. scikit-learn Developers. *Novelty and Outlier Detection*.  
   https://scikit-learn.org/stable/modules/outlier_detection.html

5. Streamlit. *Streamlit Documentation*.  
   https://docs.streamlit.io/

6. pytest Developers. *pytest Documentation*.  
   https://docs.pytest.org/en/stable/

7. Python Software Foundation. *sqlite3 — DB-API 2.0 Interface for SQLite Databases*.  
   https://docs.python.org/3/library/sqlite3.html

8. Plotly. *Plotly Python Documentation*.  
   https://plotly.com/python/

9. Python Software Foundation. *Requests Documentation*.  
   https://requests.readthedocs.io/en/latest/

---

**Đồ án môn học:** Python cho An toàn thông tin  
**Chủ đề:** Topic 09 – Bộ công cụ giám sát hạ tầng NOC và phát hiện bất thường  
**Nhóm thực hiện:** Nhóm 1

