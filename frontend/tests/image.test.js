import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { compressReceiptImage, formatBytes, validateReceiptFile } from '../src/image.js';

describe('receipt image validation and compression', () => {
  let bitmap;
  let context;
  let canvas;
  let file;
  beforeEach(() => {
    bitmap = { width: 4000, height: 3000, close: vi.fn() };
    context = { fillRect: vi.fn(), drawImage: vi.fn() };
    canvas = {
      width: 0, height: 0,
      getContext: vi.fn(() => context),
      toBlob: vi.fn((callback) => callback(new Blob(['compressed'], { type: 'image/jpeg' }))),
    };
    vi.stubGlobal('createImageBitmap', vi.fn(async () => bitmap));
    vi.spyOn(document, 'createElement').mockImplementation((tag) => {
      if (tag === 'canvas') return canvas;
      throw new Error(`Unexpected element: ${tag}`);
    });
    file = new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]), 'original'], 'hoa-don.png', { type: 'image/png' });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('re-encodes even small originals, applies EXIF orientation, scales to 2000 and closes bitmap', async () => {
    const result = await compressReceiptImage(file);
    expect(createImageBitmap).toHaveBeenCalledWith(file, { imageOrientation: 'from-image' });
    expect(canvas).toMatchObject({ width: 2000, height: 1500 });
    expect(context.fillRect).toHaveBeenCalledWith(0, 0, 2000, 1500);
    expect(context.drawImage).toHaveBeenCalledWith(bitmap, 0, 0, 2000, 1500);
    expect(result).toBeInstanceOf(File);
    expect(result).toMatchObject({ name: 'hoa-don.jpg', type: 'image/jpeg', size: 10 });
    expect(bitmap.close).toHaveBeenCalledOnce();
  });

  it('does not enlarge images below the dimension limit', async () => {
    bitmap.width = 900;
    bitmap.height = 1200;
    await compressReceiptImage(file);
    expect(canvas).toMatchObject({ width: 900, height: 1200 });
  });

  it('lowers JPEG quality until a blob is within the hard byte limit', async () => {
    canvas.toBlob.mockImplementationOnce((callback) => callback(new Blob([new Uint8Array(2049)], { type: 'image/jpeg' })))
      .mockImplementationOnce((callback) => callback(new Blob([new Uint8Array(2048)], { type: 'image/jpeg' })));
    const result = await compressReceiptImage(file, { maxBytes: 2048 });
    expect(result.size).toBe(2048);
    expect(canvas.toBlob.mock.calls.map(([, , quality]) => quality)).toEqual([0.88, 0.76]);
  });

  it('reduces dimensions after quality adjustments and never returns an oversized image', async () => {
    canvas.toBlob.mockImplementation((callback) => callback(new Blob([new Uint8Array(canvas.width > 1500 ? 2049 : 2048)], { type: 'image/jpeg' })));
    const result = await compressReceiptImage(file, { maxBytes: 2048 });
    expect(result.size).toBeLessThanOrEqual(2048);
    expect(canvas.width).toBe(1500);
    expect(canvas.toBlob).toHaveBeenCalledTimes(5);
  });

  it('rejects rather than silently uploading an image that cannot meet its size limit', async () => {
    canvas.toBlob.mockImplementation((callback) => callback(new Blob([new Uint8Array(2049)], { type: 'image/jpeg' })));
    await expect(compressReceiptImage(file, { maxBytes: 2048 })).rejects.toThrow('Không thể nén');
    expect(canvas.toBlob).toHaveBeenCalledTimes(32);
    expect(bitmap.close).toHaveBeenCalledOnce();
  });

  it('rejects huge decoded images before allocating a canvas', async () => {
    bitmap.width = 10000;
    bitmap.height = 10000;
    await expect(compressReceiptImage(file)).rejects.toThrow('40 megapixel');
    expect(document.createElement).not.toHaveBeenCalled();
    expect(bitmap.close).toHaveBeenCalledOnce();
  });

  it('rejects corrupt image data without returning the original unvalidated file', async () => {
    createImageBitmap.mockRejectedValue(new Error('decode failure'));
    await expect(compressReceiptImage(file)).rejects.toThrow('Tệp có thể bị hỏng');
  });

  it('rejects SVG or other content renamed to a supported image extension before decoding', async () => {
    const disguised = new File(['<svg xmlns="http://www.w3.org/2000/svg"></svg>'], 'hoa-don.jpg', { type: 'image/jpeg' });
    await expect(compressReceiptImage(disguised)).rejects.toThrow('Nội dung tệp không khớp');
    expect(createImageBitmap).not.toHaveBeenCalled();
  });

  it('cleans up the decoded image when browser encoding fails', async () => {
    canvas.toBlob.mockImplementation((callback) => callback(null));
    await expect(compressReceiptImage(file)).rejects.toThrow('không thể nén');
    expect(bitmap.close).toHaveBeenCalledOnce();
  });

  it.each(['image/svg+xml', 'image/heic', 'application/pdf', ''])('rejects unsupported MIME type %s', (type) => {
    expect(() => validateReceiptFile(new File(['content'], 'file', { type }))).toThrow('Chỉ hỗ trợ');
  });

  it('rejects empty and over-15-MiB originals before decoding', async () => {
    expect(() => validateReceiptFile(new File([], 'empty.jpg', { type: 'image/jpeg' }))).toThrow('trống');
    const huge = new File([new Uint8Array(15 * 1024 * 1024 + 1)], 'huge.jpg', { type: 'image/jpeg' });
    await expect(compressReceiptImage(huge)).rejects.toThrow('15 MiB');
    expect(createImageBitmap).not.toHaveBeenCalled();
  });

  it('cannot configure compression above the upload or dimension hard limits', async () => {
    await expect(compressReceiptImage(file, { maxBytes: 3 * 1024 * 1024 })).rejects.toThrow('Giới hạn');
    await expect(compressReceiptImage(file, { maxDimension: 3000 })).rejects.toThrow('Giới hạn');
  });

  it('formats file sizes with binary units', () => {
    expect(formatBytes(100)).toBe('100 B');
    expect(formatBytes(2048)).toBe('2.0 KiB');
    expect(formatBytes(2097152)).toBe('2.00 MiB');
  });
});
