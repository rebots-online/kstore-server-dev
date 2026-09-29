// zimlib-web.ts — browser-safe extraction of AnZimmermanLib's
// ZIMReaderBrowser (vendored zimlib.ts kept verbatim alongside).
//
// Differences from the vendored class:
//  - DataView/Uint8Array instead of Node Buffer (no polyfill needed)
//  - BACKPORT-EN001 applied: correct ZIM magic 0x044D495A (vendored
//    code checks 0x4D495A5A — flagged highest-priority defect)
//  - BACKPORT-EN008 applied: zstd via fzstd, zlib via fflate
//  - Reader only (no writer, no fs)

import { inflateSync } from "fflate";
import { decompress as zstdDecompress } from "fzstd";

export enum CompressionType {
  DEFAULT = 0, NONE = 1, ZLIB = 2, BZIP2 = 3, LZMA = 4, ZSTD = 5,
}

export interface ZIMHeader {
  magicNumber: number; majorVersion: number; minorVersion: number;
  entryCount: number; articleCount: number; clusterCount: number;
  redirectCount: number; mimeTypeListPos: number; titleIndexPos: number;
  clusterPtrPos: number; clusterCountPos: number;
  mainPageIndex: number; layoutPageIndex: number; checksumPos: number;
}

export interface DirectoryEntry {
  mimetypeIndex: number; namespace: number; revision: number;
  clusterNumber: number; blobNumber: number; url: string; title: string;
}
export interface RedirectEntry {
  mimetypeIndex: number; namespace: number; revision: number;
  redirectIndex: number; url: string; title: string;
}
export type Entry = DirectoryEntry | RedirectEntry;

class BR {
  private v: DataView; private b: Uint8Array; pos = 0;
  constructor(buf: ArrayBuffer | Uint8Array) {
    this.b = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    this.v = new DataView(this.b.buffer, this.b.byteOffset, this.b.byteLength);
  }
  u8()  { return this.v.getUint8(this.pos++); }
  u16() { const x = this.v.getUint16(this.pos, true); this.pos += 2; return x; }
  u32() { const x = this.v.getUint32(this.pos, true); this.pos += 4; return x; }
  u64() { const x = this.v.getBigUint64(this.pos, true); this.pos += 8; return Number(x); }
  seek(p: number) { this.pos = p; }
  bytes(n: number) { const s = this.b.subarray(this.pos, this.pos + n); this.pos += n; return s; }
  cstr() {
    const start = this.pos;
    while (this.pos < this.b.length && this.b[this.pos] !== 0) this.pos++;
    const s = new TextDecoder().decode(this.b.subarray(start, this.pos));
    this.pos++;
    return s;
  }
}

export class ZimWeb {
  private buf: ArrayBuffer;
  header?: ZIMHeader;
  mimeTypes: string[] = [];
  entries: Entry[] = [];
  clusterOffsets: number[] = [];

  constructor(buf: ArrayBuffer) { this.buf = buf; }

  open(): void {
    const r = new BR(this.buf);
    this.header = {
      magicNumber: r.u32(), majorVersion: r.u16(), minorVersion: r.u16(),
      entryCount: r.u32(), articleCount: r.u32(), clusterCount: r.u32(),
      redirectCount: r.u32(), mimeTypeListPos: r.u64(), titleIndexPos: r.u64(),
      clusterPtrPos: r.u64(), clusterCountPos: r.u64(),
      mainPageIndex: r.u32(), layoutPageIndex: r.u32(), checksumPos: r.u64(),
    };
    if (this.header.magicNumber !== 0x044d495a)
      throw new Error(`not a ZIM file (magic 0x${this.header.magicNumber.toString(16)})`);
    this.readMimeTypes(r);
    this.readDirectory(r);
    this.readClusterPtrs(r);
  }

  private readMimeTypes(r: BR): void {
    r.seek(this.header!.mimeTypeListPos);
    const bytes: number[] = [];
    let prev = 0, nn = 0;
    while (nn < 2 && r.pos < this.buf.byteLength) {
      const b = r.u8(); bytes.push(b);
      nn = b === 0 && prev === 0 ? nn + 1 : 0;
      prev = b;
    }
    this.mimeTypes = new TextDecoder()
      .decode(new Uint8Array(bytes))
      .split("\x00").filter(Boolean);
  }

  private readDirectory(r: BR): void {
    r.seek(80);
    const ptrs: number[] = [];
    for (let i = 0; i < this.header!.entryCount; i++) ptrs.push(r.u64());
    for (const p of ptrs) {
      r.seek(p);
      const mime = r.u16();            // mimeTypeListIndex is u16 per spec
      const paramLen = r.u8();
      const ns = r.u8();
      const rev = r.u32();
      if (mime === 0xffff) {
        const redirectIndex = r.u32();
        const url = r.cstr(), title = r.cstr();
        r.pos += paramLen;
        this.entries.push({ mimetypeIndex: mime, namespace: ns, revision: rev, redirectIndex, url, title });
      } else {
        const clusterNumber = r.u32(), blobNumber = r.u32();
        const url = r.cstr(), title = r.cstr();
        r.pos += paramLen;
        this.entries.push({ mimetypeIndex: mime, namespace: ns, revision: rev, clusterNumber, blobNumber, url, title });
      }
    }
  }

  private readClusterPtrs(r: BR): void {
    r.seek(this.header!.clusterPtrPos);
    for (let i = 0; i < this.header!.clusterCount; i++)
      this.clusterOffsets.push(r.u64());
  }

  getEntryByPath(path: string): Entry | undefined {
    const ns = path.charCodeAt(0);
    const url = path.length > 2 ? path.substring(2) : "";
    return this.entries.find(e => e.namespace === ns && e.url === url);
  }

  getMainPage(): Entry | undefined {
    return this.entries[this.header?.mainPageIndex ?? -1];
  }

  listArticles(ns?: number): DirectoryEntry[] {
    return this.entries.filter(
      e => "clusterNumber" in e && (ns === undefined || e.namespace === ns)
    ) as DirectoryEntry[];
  }

  mimeOf(e: DirectoryEntry): string {
    return this.mimeTypes[e.mimetypeIndex] || "application/octet-stream";
  }

  async getArticleContent(entry: DirectoryEntry): Promise<Uint8Array> {
    const r = new BR(this.buf);
    const clusterStart = this.clusterOffsets[entry.clusterNumber];
    r.seek(clusterStart);
    const compByte = r.u8() & 0x0f; // low nibble = compression

    // offset list starts at clusterStart+1; first offset = (nBlobs+1)*4
    const listStart = r.pos;
    const first = r.u32();
    const nBlobs = Math.floor(first / 4) - 1;
    const offsets = [first];
    for (let i = 0; i < nBlobs; i++) offsets.push(r.u32());
    if (entry.blobNumber >= nBlobs)
      throw new Error("bad blob number");

    const blobStart = offsets[entry.blobNumber];
    const blobEnd = offsets[entry.blobNumber + 1];
    r.seek(listStart + blobStart);
    const blob = r.bytes(blobEnd - blobStart);

    switch (compByte) {
      case CompressionType.NONE: case CompressionType.DEFAULT:
        return blob;
      case CompressionType.ZLIB:
        return inflateSync(blob);
      case CompressionType.ZSTD:
        return zstdDecompress(blob);
      default:
        throw new Error(`unsupported compression ${compByte} (lzma/bzip2 not ported)`);
    }
  }
}
