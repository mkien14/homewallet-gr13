import pathlib

from PIL import Image, ImageOps

SRC = pathlib.Path("data")
DST = pathlib.Path("data_small")
DST.mkdir(exist_ok=True)

MAX_SIDE = 2000          # cạnh dài tối đa (pixel)
TARGET_BYTES = 2_000_000  # mục tiêu ≤ 2 MB mỗi ảnh


def shrink(src, dst):
    im = Image.open(src)
    im = ImageOps.exif_transpose(im).convert("RGB")  # xoay đúng chiều ảnh điện thoại
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    for q in (88, 80, 72, 65):
        im.save(dst, "JPEG", quality=q, optimize=True)
        if dst.stat().st_size <= TARGET_BYTES:
            break
    return im.size, dst.stat().st_size


for f in sorted(SRC.iterdir()):
    if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
        out = DST / (f.stem + ".jpg")
        size, nbytes = shrink(f, out)
        print(f"{f.name}: {f.stat().st_size/1e6:.1f} MB -> {nbytes/1e6:.2f} MB {size}")