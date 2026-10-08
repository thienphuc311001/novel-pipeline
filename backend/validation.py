"""Validate HTTP mutations before they reach the single workspace worker."""
from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

from config.settings import Settings


class ValidationError(ValueError):
    pass


def _matches(value, annotation):
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list:
        return isinstance(value, list) and all(_matches(item, args[0]) for item in value)
    if origin is dict:
        return isinstance(value, dict) and all(
            _matches(key, args[0]) and _matches(item, args[1]) for key, item in value.items()
        )
    if annotation is bool:
        return type(value) is bool
    if annotation is int:
        return type(value) is int
    if annotation is str:
        return isinstance(value, str)
    if annotation is dict:
        return isinstance(value, dict)
    if annotation is list:
        return isinstance(value, list)
    return True  # Any-valued preprocessing and custom rules are validated by the service.


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValidationError("Cài đặt phải là một đối tượng JSON.")
    fields = get_type_hints(Settings)
    for name, value in data.items():
        if name not in fields:
            raise ValidationError(f"Cài đặt không được hỗ trợ: {name}")
        if not _matches(value, fields[name]):
            raise ValidationError(f"Kiểu dữ liệu cài đặt không hợp lệ: {name}")
    if "max_log_lines" in data and data["max_log_lines"] < 1:
        raise ValidationError("Số dòng nhật ký phải lớn hơn 0.")
    return data


# Required fields and optional fields follow the public service contract.
_ACTIONS = {
    "import": ({"paths": list[str]}, {"sort_mode": str}),
    "normalize": ({}, {}),
    "edit": ({"text": str}, {}),
    "group": ({"title": str}, {"size": int, "method": str, "confirmation_fingerprint": str}),
    "prepare": ({"group_ids": list[str]}, {}),
    "thumbnail": ({"group_ids": list[str], "image_path": str}, {}),
    "tts": ({"group_ids": list[str]}, {}),
    "merge_partial": ({"group_ids": list[str], "allow_partial": bool}, {}),
    "edit_chunk": ({"group_id": str, "order": int, "text": str}, {}),
    "delete_group": ({"group_id": str}, {}),
    "video": ({"group_ids": list[str]}, {"cover_image": str, "qr_image": str}),
    "preview": ({"group_id": str}, {"cover_image": str, "qr_image": str}),
    "export": ({"format": str}, {}),
    "youtube_connect": ({}, {}),
    "youtube_disconnect": ({}, {}),
    "upload": ({"group_ids": list[str]}, {"metadata": dict, "group_metadata": dict[str, dict], "titles": dict[str, str]}),
    "youtube_metadata": ({"group_id": str, "metadata": dict}, {}),
    "youtube_retry_thumbnail": ({"group_id": str}, {}),
    "youtube_retry_playlist": ({"group_id": str, "playlist_id": str}, {}),
}


def validate_action(action, options):
    if not isinstance(action, str) or action not in _ACTIONS:
        raise ValidationError("Thao tác không được hỗ trợ.")
    if not isinstance(options, dict):
        raise ValidationError("Tùy chọn phải là một đối tượng JSON.")
    required, optional = _ACTIONS[action]
    fields = {**required, **optional}
    for name in required:
        if name not in options:
            raise ValidationError(f"Thiếu tùy chọn: {name}")
    for name, value in options.items():
        if name not in fields:
            raise ValidationError(f"Tùy chọn không được hỗ trợ: {name}")
        annotation = fields[name]
        if annotation is dict:
            valid = isinstance(value, dict)
        else:
            valid = _matches(value, annotation)
        if not valid:
            raise ValidationError(f"Kiểu dữ liệu tùy chọn không hợp lệ: {name}")
    for name in ("paths", "group_ids"):
        if name in options and (not options[name] or any(not value.strip() for value in options[name])):
            raise ValidationError(f"Danh sách {name} không được để trống.")
    if "group_id" in options and not options["group_id"].strip():
        raise ValidationError("Phải chọn nhóm chương.")
    if action == "import" and options.get("sort_mode", "natural") not in {"natural", "selection", "name"}:
        raise ValidationError("Thứ tự nhập không hợp lệ.")
    if action == "group":
        if options.get("size", 20) < 1:
            raise ValidationError("Số chương mỗi nhóm phải lớn hơn 0.")
        if options.get("method", "detected_chapters") not in {"detected_chapters", "numeric_boundaries"}:
            raise ValidationError("Phương pháp chia nhóm không hợp lệ.")
    if action == "export" and options["format"] not in {"txt", "json", "zip"}:
        raise ValidationError("Định dạng xuất không hợp lệ.")
    if action == "merge_partial" and options["allow_partial"] is not True:
        raise ValidationError("Phải xác nhận ghép âm thanh chưa đầy đủ.")
    if action == "edit_chunk" and options["order"] < 1:
        raise ValidationError("Thứ tự đoạn phải lớn hơn 0.")
    return action, options


def validate_ui(ui):
    if not isinstance(ui, dict):
        raise ValidationError("Trạng thái giao diện phải là một đối tượng JSON.")
    for name in ("tab", "group_size", "custom_size", "web_group_size"):
        if name in ui and type(ui[name]) is not int:
            raise ValidationError(f"Trạng thái giao diện không hợp lệ: {name}")
    for name in ("panels", "upload_titles", "upload_metadata", "group_upload_metadata", "web_panels", "web_upload_metadata", "web_group_metadata", "web_titles"):
        if name in ui and not isinstance(ui[name], dict):
            raise ValidationError(f"Trạng thái giao diện không hợp lệ: {name}")
    for name in ("cover_image", "qr_image", "web_cover_image", "web_qr_image"):
        if name in ui and not isinstance(ui[name], str):
            raise ValidationError(f"Trạng thái giao diện không hợp lệ: {name}")
    if ui.get("web_group_size", 1) < 1:
        raise ValidationError("Số chương mỗi nhóm phải lớn hơn 0.")
    for name in ("panels", "web_panels"):
        for panel in ui.get(name, {}).values():
            if not isinstance(panel, dict) or not _matches(panel.get("checked", []), list[str]):
                raise ValidationError("Danh sách nhóm được chọn không hợp lệ.")
    for name in ("upload_titles", "web_titles"):
        if not _matches(ui.get(name, {}), dict[str, str]):
            raise ValidationError("Tiêu đề tải lên phải là văn bản.")
    for name in ("upload_metadata", "group_upload_metadata", "web_upload_metadata"):
        _validate_metadata_draft(ui.get(name, {}))
    for metadata in ui.get("web_group_metadata", {}).values():
        _validate_metadata_draft(metadata)
    return ui


def _validate_metadata_draft(data):
    if not isinstance(data, dict):
        raise ValidationError("Thông tin tải lên không hợp lệ.")
    for name in ("title", "description", "category_id", "privacy"):
        if name in data and not isinstance(data[name], str):
            raise ValidationError(f"Thông tin tải lên không hợp lệ: {name}")
    for name in ("playlist_id", "publish_at"):
        if data.get(name) is not None and not isinstance(data[name], str):
            raise ValidationError(f"Thông tin tải lên không hợp lệ: {name}")
    for name in ("made_for_kids", "contains_synthetic_media"):
        if name in data and type(data[name]) is not bool:
            raise ValidationError(f"Thông tin tải lên không hợp lệ: {name}")
    if not _matches(data.get("tags", []), list[str]):
        raise ValidationError("Thẻ tải lên phải là danh sách văn bản.")
