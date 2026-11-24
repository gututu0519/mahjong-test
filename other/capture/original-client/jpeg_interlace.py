"""将原始 JPEG 解码像素无损保存为 Adam7 PNG。Pillow 仅在出现 JPEG 时需要。"""
import hashlib
import io
import struct

from png_interlace import convert_png


def convert_jpeg(raw):
    try:
        from PIL import Image
    except ImportError:
        raise ValueError("当前 Python 缺少 JPEG 解码依赖 Pillow") from None
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format != "JPEG" or getattr(source, "n_frames", 1) != 1:
                raise ValueError("原件不是单幅 JPEG")
            width, height = source.size
            if width * height > 12_000_000 or max(width, height) > 32_768:
                raise ValueError("JPEG 像素规模超过转换上限")
            if source.mode not in {"L", "RGB"}:
                raise ValueError("JPEG 色彩模式需要单独校准")
            if source.info.get("icc_profile") or any(name == "APP2" and value.startswith(b"ICC_PROFILE") for name, value in source.applist):
                raise ValueError("JPEG 含 ICC 色彩配置，需要核验浏览器颜色表现")
            exif = source.getexif()
            if exif.get(274, 1) != 1:
                raise ValueError("JPEG 含 EXIF 旋转或镜像方向，需要核验显示方向")
            if exif.get(40961, 1) != 1 or exif.get_ifd(34665).get(40961, 1) != 1:
                raise ValueError("JPEG 声明的 EXIF 色彩空间需要单独校准")
            if any(name in {"APP1", "APP2"} and not
                   (name == "APP1" and value.startswith(b"Exif\0\0")) for name, value in source.applist):
                raise ValueError("JPEG 含额外图像或 XMP 显示元数据，需要确认用途")
            for name, value in source.applist:
                if name == "COM" or (name == "APP0" and value.startswith(b"JFIF\0")):
                    continue
                if name == "APP1" and value.startswith(b"Exif\0\0"):
                    continue
                if name == "APP14" and value.startswith(b"Adobe") and source.info.get("adobe_transform") in (0, 1):
                    continue
                raise ValueError("JPEG 含未识别的应用标记，需要核验显示元数据")
            if getattr(source, "bits", 8) != 8:
                raise ValueError("JPEG 原始位深需要单独处理")
            source.load()
            mode = source.mode
            rgba = source.convert("RGBA").tobytes()
            digest = hashlib.sha256(rgba).hexdigest()
            # 单独创建像素对象，仅保留尺寸与源像素模式，避免把账户或定位元数据带入图片。
            pixels = Image.frombytes(mode, source.size, source.tobytes())
            buffer = io.BytesIO()
            options = {"dpi": source.info["dpi"]} if "dpi" in source.info else {}
            pixels.save(buffer, format="PNG", **options)
        result = convert_png(buffer.getvalue())
        with Image.open(io.BytesIO(result)) as check:
            if (check.format != "PNG" or result[28] != 1 or check.mode != mode or
                    check.size != (width, height) or check.convert("RGBA").tobytes() != rgba):
                raise ValueError("JPEG 转为 Adam7 PNG 后像素或尺寸存在差异")
        return result, {"size_px": [width, height], "source_mode":mode,
                        "rgba_sha256":digest, "interlace":1}
    except (OSError, SyntaxError, TypeError, struct.error, Image.DecompressionBombError):
        raise ValueError("JPEG 正文、元数据或解码结果不完整") from None
