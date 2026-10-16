const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_INPUT_BYTES = 15 * 1024 * 1024;
const MAX_PIXELS = 40_000_000;

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

export function validateReceiptFile(file) {
  if (!file || !ALLOWED_TYPES.has(file.type)) {
    throw new Error('Chỉ hỗ trợ ảnh JPEG, PNG hoặc WebP. Vui lòng chuyển ảnh HEIC hoặc định dạng khác sang JPEG.');
  }
  if (!Number.isSafeInteger(file.size) || file.size <= 0) throw new Error('Tệp ảnh trống hoặc không hợp lệ.');
  if (file.size > MAX_INPUT_BYTES) throw new Error('Ảnh gốc vượt quá 15 MiB. Vui lòng chọn ảnh nhỏ hơn.');
  return file;
}

async function validateImageSignature(file) {
  const head = file.slice(0, 12);
  const buffer = typeof head.arrayBuffer === 'function'
    ? await head.arrayBuffer()
    : await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('Không đọc được tệp ảnh.'));
      reader.readAsArrayBuffer(head);
    });
  const bytes = new Uint8Array(buffer);
  const jpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  const png = [137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => bytes[i] === byte);
  const webp = bytes[0] === 82 && bytes[1] === 73 && bytes[2] === 70 && bytes[3] === 70
    && bytes[8] === 87 && bytes[9] === 69 && bytes[10] === 66 && bytes[11] === 80;
  if (!({ 'image/jpeg': jpeg, 'image/png': png, 'image/webp': webp })[file.type]) {
    throw new Error('Nội dung tệp không khớp định dạng JPEG, PNG hoặc WebP. Vui lòng chọn ảnh hợp lệ.');
  }
}

function decodeImage(file) {
  // ImageBitmap applies EXIF orientation before canvas strips metadata.
  if (typeof globalThis.createImageBitmap === 'function') {
    return globalThis.createImageBitmap(file, { imageOrientation: 'from-image' });
  }
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error('Không đọc được ảnh.'));
    };
    image.src = objectUrl;
  });
}

function encodeJpeg(canvas, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob || blob.type !== 'image/jpeg' || blob.size === 0) {
        reject(new Error('Trình duyệt không thể nén ảnh thành JPEG.'));
      } else resolve(blob);
    }, 'image/jpeg', quality);
  });
}

/** Always re-encode (including small input files) to remove EXIF/GPS metadata. */
export async function compressReceiptImage(file, { maxDimension = 2000, maxBytes = 2 * 1024 * 1024 } = {}) {
  validateReceiptFile(file);
  if (!Number.isInteger(maxDimension) || maxDimension < 1 || maxDimension > 2000
    || !Number.isInteger(maxBytes) || maxBytes < 1024 || maxBytes > 2 * 1024 * 1024) {
    throw new Error('Giới hạn nén ảnh không hợp lệ.');
  }
  await validateImageSignature(file);
  let image;
  try { image = await decodeImage(file); } catch {
    throw new Error('Không đọc được ảnh. Tệp có thể bị hỏng hoặc không đúng định dạng JPEG, PNG, WebP.');
  }
  try {
    const originalWidth = image.width || image.naturalWidth;
    const originalHeight = image.height || image.naturalHeight;
    if (!Number.isFinite(originalWidth) || !Number.isFinite(originalHeight) || originalWidth <= 0 || originalHeight <= 0
      || originalWidth * originalHeight > MAX_PIXELS) {
      throw new Error('Ảnh quá lớn để xử lý an toàn (tối đa 40 megapixel) hoặc có kích thước không hợp lệ.');
    }
    const scale = Math.min(1, maxDimension / Math.max(originalWidth, originalHeight));
    let width = Math.max(1, Math.round(originalWidth * scale));
    let height = Math.max(1, Math.round(originalHeight * scale));
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Trình duyệt không hỗ trợ xử lý ảnh.');

    // Lower quality first, then dimensions; never return an oversized file.
    for (let attempt = 0; attempt < 8; attempt += 1) {
      canvas.width = width;
      canvas.height = height;
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);
      for (const quality of [0.88, 0.76, 0.64, 0.5]) {
        const blob = await encodeJpeg(canvas, quality);
        if (blob.size <= maxBytes) {
          const stem = typeof file.name === 'string' ? file.name.replace(/\.[^.]*$/, '') : 'hoa-don';
          return new File([blob], `${stem || 'hoa-don'}.jpg`, { type: 'image/jpeg', lastModified: Date.now() });
        }
      }
      width = Math.max(1, Math.floor(width * 0.75));
      height = Math.max(1, Math.floor(height * 0.75));
    }
    throw new Error('Không thể nén ảnh xuống giới hạn dung lượng. Vui lòng chọn ảnh nhỏ hơn.');
  } finally {
    image.close?.();
  }
}
