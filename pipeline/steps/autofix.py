"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # cộng mọi mã DUP_IMAGE_*


def clip(text):
    """Cắt box về [0,1]; trả dòng mới, hoặc None nếu box không còn diện tích."""
    c, x, y, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    # làm tròn TRƯỚC khi kiểm: w=1e-7 in ra "0.000000" sẽ thành BOX_ZERO ở lần chạy sau
    w, h = round(x2 - x1, 6), round(y2 - y1, 6)
    if w <= 0 or h <= 0:
        return None
    return f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {w:.6f} {h:.6f}"


def fix(ds, issues, cfg):
    errs = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1) Xoá ảnh trước, để issue dòng của ảnh đó tự rơi (file nhãn đã mất).
    removed = set()
    for i in errs:
        if (i.code in REMOVE or i.code.startswith("DUP_IMAGE_")) and i.image not in removed:
            removed.add(i.image)
            img = ds.image_path(i.image)
            if img is None:                                    # đã xoá ở lần chạy trước
                continue
            img.unlink()
            ds.label_path(i.image).unlink(missing_ok=True)
            fixes.append(dict(image=i.image, line="", action="remove_image", before=img.name, after=f"(đã xoá: {i.code})"))

    # 2) Gom lỗi dòng theo file: {stem: {số dòng gốc: {mã lỗi}}}
    marks = defaultdict(lambda: defaultdict(set))
    for i in errs:
        if i.line and (i.code in DROP or i.code == "BOX_OUT_OF_IMAGE"):
            marks[i.image][i.line].add(i.code)
    for stem, by_line in marks.items():
        p = ds.label_path(stem)
        if stem in removed or not p.exists():
            continue
        out = []
        # enumerate trên MỌI dòng (cả dòng trống) để khớp số dòng gốc trong issue
        for no, text in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            codes = by_line.get(no)
            if not codes:
                out.append(text)
                continue
            new = None if codes & DROP else clip(text)         # xoá thắng cắt
            action = "drop_line" if new is None else "clip_box"
            fixes.append(dict(image=stem, line=no, action=action, before=text, after=new or ""))
            if new is not None:
                out.append(new)
        p.write_text("".join(ln + "\n" for ln in out), encoding="utf-8")   # ghi lại MỘT lần

    # 3) Thiếu file nhãn: không bịa nhãn, chuyển người gán
    for i in errs:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed:
            fixes.append(dict(image=i.image, line="", action="needs_label", before="(không có file)", after="chuyển người gán"))

    # 4) Tên lớp sai: ghi lại names một lần (class_names có thể báo nhiều dòng)
    if any(i.code == "BAD_CLASS_NAME" for i in errs):
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else None
        d = d or {}
        before = d.get("names")
        d["names"] = dict(enumerate(cfg["classes"]))
        ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        fixes.append(dict(image="data.yaml", line="", action="rename_classes", before=str(before), after=str(cfg["classes"])))
    return fixes
