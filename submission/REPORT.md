# Báo cáo Day 09 — Chu Thien Phu, 2A202603114

> Mọi số liệu lấy từ `submission/reports/` (lần chạy `make run` với `phash_dist=10`, `second_opinion.conf=0.75`) và `submission/calibration/`.

## 1. Kết luận trước
Pipeline kết luận **Release** (mã thoát 0). **224 ảnh vào → 202 ảnh ra** dataset `submission/export/clean_v1` (loại 22 ảnh ở cửa vào).
Sau máy sửa và người duyệt (80/80 ảnh ngân sách) không còn lỗi bắt buộc nào; còn **19/202 ảnh (9.4%)** có cảnh báo chưa duyệt, dưới ngưỡng Hold 10%.
Biên độ rất mỏng: chỉ thêm 2 ảnh cảnh báo là thành Hold, và 9/19 ảnh còn lại là `POSSIBLE_FALSE_POS` — loại cảnh báo có precision thấp nhất (0.31 trên calib).

## 2. Lỗi và phân việc
Từ `02_error_list_v1` (trước khi sửa), `01_intake` và `03_fixes.csv`:

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT | 8 ảnh | máy (loại ở cửa vào) | trùng md5, chắc chắn trùng — giữ lại làm lệch phân bố |
| DUP_IMAGE_NEAR | 4 ảnh | máy (loại ở cửa vào) | phash ≤ 10, đã kiểm bằng mắt (mục 3) |
| LEAK_TEST | 5 ảnh | máy (loại ở cửa vào) | trùng ảnh tập test/val: giữ lại sẽ làm số đo test bị thổi phồng |
| BAD_SIZE / CORRUPT_IMAGE | 3 / 2 ảnh | máy (loại) | ảnh quá nhỏ / không mở được, không có gì để sửa |
| BOX_OUT_OF_IMAGE | 8 dòng | máy (`clip_box`, 8 fix) | cắt về [0,1] là an toàn, giữ nguyên lớp |
| DUP_BOX | 7 dòng | máy (`drop_line`) | cùng lớp, IoU > 0.9: dòng sau là thừa |
| BAD_CLASS_ID | 6 dòng | máy (`drop_line`) | id ngoài 0..3 (vd `img_0020` dòng 3: id 93), không đoán được lớp đúng |
| BOX_ZERO | 4 dòng | máy (`drop_line`) | box không có diện tích |
| BAD_FORMAT | 3 dòng | máy (`drop_line`) | dòng không đủ 5 cột số |
| BAD_CLASS_NAME | 1 (data.yaml) | máy (`rename_classes`) | ghi lại `names` theo `classes` của dự án |
| MISSING_LABEL_FILE | 6 ảnh | **người** (`needs_label`) | máy không được bịa nhãn; file rỗng = "ảnh nền", khác "chưa gán" |
| POSSIBLE_MISSING | 39 dòng / 38 ảnh | **người** | model lớn thấy vật mà nhãn không có — model cũng có thể sai |
| POSSIBLE_WRONG_CLASS | 16 ảnh | **người** | nhầm lớp hợp lệ, không phát hiện được bằng quy tắc |
| POSSIBLE_LOOSE_BOX | 14 ảnh | **người** | box lỏng/lệch: cần mắt người đánh giá |
| POSSIBLE_FALSE_POS | 29 dòng / 27 ảnh | **người** | box nhãn không khớp vật nào model thấy |
| EMPTY_LABEL | 12 ảnh | **người** | có thể là ảnh nền thật hoặc quên gán |
| BOX_TINY / BOX_HUGE / CLASS_RARE | 6 dòng / 3 / 4 | **người** | cảnh báo, có thể hợp lệ (người ở xa, vật chiếm cả ảnh) |

Máy ghi **35 thay đổi** (`drop_line` 20, `clip_box` 8, `needs_label` 6, `rename_classes` 1). Sau sửa (`04_error_list_v2`) chỉ còn 6 lỗi bắt buộc, đều là `MISSING_LABEL_FILE`.

**Thứ tự hàng đợi** (`05_review_queue.csv`, 108 ảnh): điểm ưu tiên = tổng trọng số cảnh báo × (1 + conf của model) + trọng số các dòng máy đã sửa. Đầu hàng là `img_0020` (11.5 điểm: máy đã xoá 1 dòng id 93 + model thấy `bus` ở chỗ nhãn ghi `truck` với conf 0.95 + 1 người bị thiếu nhãn với conf 0.84), tiếp theo là 6 ảnh `NEEDS_LABEL` (10 điểm: chỉ người mới gán được). Ảnh nhiều tín hiệu, model càng chắc thì càng lên trước.
**Ngân sách 80 ảnh:** người duyệt được 80/108 ảnh, trong đó **72 ảnh có cảnh báo ngữ nghĩa** (`POSSIBLE_*`) trên tổng 81 ảnh ngữ nghĩa trong hàng đợi: toàn bộ 38 MISSING, 16 WRONG_CLASS, 14 LOOSE_BOX đã được xem; còn sót 9 ảnh `POSSIBLE_FALSE_POS` chưa ai xem.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **10** | NEAR: 1.00 / 0.50 → 1.00 / 0.67 | Giá trị nhỏ nhất bắt được cặp trùng thật `img_0186`/`img_0061` (khoảng cách 10) trên lô raw; 12–14 không bắt thêm gì; 16 vứt nhầm 8 ảnh (xem dưới) |
| `second_opinion.conf` | 0.25 | **0.75** | WRONG_CLASS: 0.56 / 0.83 → 1.00 / 0.83; MISSING: 0.50 / 1.00 → 0.64 / 0.88 | F1 của MISSING cao nhất (0.74) và WRONG_CLASS không còn báo giả; đổi lại bỏ sót 1/8 lỗi MISSING trên calib. 0.8 giữ precision nhưng recall MISSING tụt xuống 0.75 |

Khảo sát `conf` trên lô raw (cùng `phash_dist=10`) cho thấy kết luận rất nhạy với ngưỡng: **0.70 → Hold (14.4%)**, **0.75 → Release (9.4%)**, **0.80 → Release (7.9%)**. Tôi giữ 0.75 vì lý do chất lượng phát hiện trên calib, không chọn theo kết luận của cổng.

**Chỗ calibration đánh lừa:** trên calib, `phash_dist=16` có recall NEAR tốt nhất (0.83). Nhưng trên lô raw, 16 loại **31 ảnh thay vì 22** (thêm 3 DUP_IMAGE_NEAR + 6 LEAK_TEST, trong đó chỉ 1 ảnh là trùng thật). Tôi mở xem 10 cặp ảnh chỉ bị bắt ở mức cao (ghép cạnh nhau trong `work/pairs/`): chỉ **2 cặp trùng thật** (`img_0084`/`img_0074` ở khoảng cách 16, `img_0186`/`img_0061` ở 10); **8 cặp còn lại là cảnh hoàn toàn khác nhau**, gồm 6 ảnh bị gán nhầm là rò rỉ tập test. Bộ calib chỉ 39 ảnh nên điểm đẹp trên calib không đảm bảo đúng trên dữ liệu thật — phải nhìn tận mắt các ảnh bị loại.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt): kết luận **Rework**, **mã thoát 20**, log in "KHÔNG xuất: còn lỗi bắt buộc (Rework)", và thư mục `work/exp_nb` **không được tạo**. Lý do: 6 ảnh `MISSING_LABEL_FILE` (`img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`) vẫn chưa có nhãn — máy không bịa nhãn, nên lỗi bắt buộc còn nguyên và cổng chặn xuất.

**(b) Điểm mù có bằng chứng:**
1. **Ảnh trùng biến đổi mạnh:** cặp `img_0084`/`img_0074` là cùng một ảnh nhưng khoảng cách phash 16. Ở ngưỡng 10 nó **lọt qua**; muốn bắt phải lên 16 và chịu vứt nhầm 8 ảnh tốt. Trên calib cũng còn sót 2/6 ảnh NEAR (recall 0.67).
2. **Box lỏng nhẹ:** `POSSIBLE_LOOSE_BOX` chỉ bắt được **1/5** lỗi chèn trên calib (recall 0.20) ở `conf=0.75`. Box lệch ít (IoU với dự đoán vẫn ≥ 0.5) không bị cờ; chỉ người hoặc kiểm tra tay mới thấy.
3. **Nhầm lớp mà model cũng nhầm / thiếu nhãn model không thấy:** WRONG_CLASS bỏ sót 1/6 và MISSING bỏ sót 1/8 trên calib. Second opinion chỉ mạnh bằng model yolo26l: chỗ model cũng sai hoặc không tự tin (< 0.75) thì pipeline im lặng.
4. **Báo động giả nhiều:** `POSSIBLE_FALSE_POS` có precision 0.31 (11 báo giả / 16 cờ trên calib) và không calibrate được vì `fp_conf` cố định; 9/19 ảnh còn cảnh báo khi Release thuộc loại này.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy: phần train (Colab) là tùy chọn, chưa thực hiện trong buổi làm bài; ưu tiên hoàn thành phần lõi (pipeline, calibration, báo cáo). Bài được kiểm bằng `make check-core`.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối: Release** `clean_v1` (202 ảnh), kèm ghi chú rủi ro: tỉ lệ cảnh báo 9.4% sát ngưỡng 10%, 9 ảnh `POSSIBLE_FALSE_POS` chưa được người xem, và cặp trùng `img_0084`/`img_0074` vẫn còn trong dataset. Để Release chắc chắn hơn: tăng ngân sách duyệt cho các ảnh FALSE_POS còn lại, và loại tay cặp trùng đã phát hiện.

**(b) Ghi chú AI:** có dùng AI (Claude Code) để viết cả 4 module.
- *Prompt chính:* giao từng module kèm docstring của stub, file test tương ứng, ràng buộc trong RULES.md (chỉ sửa 1 file, không viết cứng ngưỡng/tên ảnh, không đọc đáp án) và yêu cầu tự viết 3 ca biên trong `work/`.
- *Cách kiểm:* chạy `pytest` từng module rồi toàn bộ (79 passed); chạy script ca biên (`work/thu_3_ca.py`, `thu_gate.py`, `thu_autofix.py`, `thu_second_opinion.py`); chạy pipeline thật và mở xem ảnh bị loại/cờ (viz, CVAT, `work/pairs/`).
- *Một lần AI sai:* khi thử ca biên của `autofix` ("một dòng vừa tràn vừa trùng"), AI viết sai kết quả mong đợi — quên rằng dòng 1 cũng tràn ảnh nên cũng bị `clip_box`. Code chạy đúng; phần "mong đợi" phải sửa lại. Ngoài ra AI từng khẳng định tăng `conf` "gần như vô ích" để giảm tỉ lệ cảnh báo, nhưng chạy thử cho thấy 0.8 vẫn giảm từ 9.4% xuống 7.9% (do hàng đợi ngắn hơn) — phải đo chứ không tin lời giải thích.
