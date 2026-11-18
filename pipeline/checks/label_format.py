"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    c = cfg["label_format"]
    n_cls = len(ds.classes)
    issues = []

    def add(sev, code, stem, msg, line, extra=None):
        issues.append(Issue("label_format", sev, code, stem, msg, line, extra or {}))

    for lp in ds.label_files():
        stem = lp.stem
        # read_label_lines giữ số dòng GỐC (dòng trống bị bỏ nhưng vẫn được đếm)
        lines = ds.read_label_lines(stem) or []
        size = ds.image_size(stem)              # (W, H) px; None nếu ảnh mất/hỏng -> bỏ qua BOX_TINY
        seen = []                               # các box hợp lệ ở dòng TRƯỚC, để tìm DUP_BOX

        for no, text in lines:
            # 1) Cú pháp: đúng 5 cột số, không nan/inf. Dòng hỏng thì không kiểm tiếp.
            try:
                cid, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", stem, f"dòng không đúng 5 cột số: {e}", no, {"text": text})
                continue
            # 2) ID lớp phải nằm trong 0..n_cls-1
            if not 0 <= cid < n_cls:
                add(ERROR, "BAD_CLASS_ID", stem, f"id lớp {cid} ngoài 0..{n_cls - 1}", no)
                continue
            # 3) Box rỗng
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", stem, f"box rỗng w={w} h={h}", no)
                continue
            # 4) Tràn ảnh: mức tràn lớn nhất trong 4 mép, chỉ báo khi vượt quá dung sai
            overflow = max(0.0, -(x - w / 2), (x + w / 2) - 1, -(y - h / 2), (y + h / 2) - 1)
            if overflow > c["overflow_tol"]:
                add(ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f}", no, {"overflow": round(overflow, 6)})
            # 5) Box lặp: cùng lớp với một dòng trước và IoU cao -> báo ở dòng SAU
            box = (x, y, w, h)
            for prev_no, prev_cid, prev_box in seen:
                iou = iou_xywh(box, prev_box)
                if prev_cid == cid and iou > c["dup_box_iou"]:
                    add(ERROR, "DUP_BOX", stem, f"trùng box dòng {prev_no} (IoU={iou:.3f})", no, {"iou": round(iou, 4), "dup_of": prev_no})
                    break
            seen.append((no, cid, box))
            # 6) Cảnh báo (người xem): box quá nhỏ theo px, box gần phủ cả ảnh
            if size:
                short_px = min(w * size[0], h * size[1])
                if short_px < c["min_box_px"]:
                    add(WARN, "BOX_TINY", stem, f"cạnh ngắn {short_px:.1f}px < {c['min_box_px']}px", no, {"short_px": round(short_px, 2)})
            if w * h > c["max_box_frac"]:
                add(WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.2%} ảnh", no, {"area_frac": round(w * h, 4)})
    return issues
