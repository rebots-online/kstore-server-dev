/**
 * Clean-room ZIM (Zeno IMproved) file format reader/writer library for TypeScript/Node.js
 *
 * Based on ZIM file format specification from openZIM
 * Supports reading and writing ZIM archives for offline content storage
 *
 * Copyright (C) 2025 Robin L. M. Cheung, MBA. All rights reserved.
 *
 * =====================================================================
 * BACKPORT AUDIT — 2026-05-06 — from EnZIMErgent backend/zim_parser.py
 * =====================================================================
 * This TS module mirrors zimlib.py and inherits the SAME structural
 * bugs (magic number 0x4D495A5A is wrong; header schema lacks the
 * 16-byte UUID; DirectoryEntry uses 4-byte mimetype where spec says
 * 2 + 1 + 1; cluster compression byte is not nibble-masked; blob
 * offsets use a non-existent zero-sentinel; cluster_count vs +1
 * off-by-one; missing zstd; missing HTTP-Range; missing storage
 * planner). See zimlib.py top banner for the BACKPORT-EN001..EN020
 * task list — every item there applies here too.
 *
 * AnZimmermanLib has never been officially deployed; no consumers
 * exist. Corrections are invisible. Recommended: rewrite reader+writer
 * cores in one commit and tag a clean v1.0.
 *
 * EnZIMErgent's mobile app will consume THIS TypeScript file (via the
 * `ZIMReaderBrowser` ArrayBuffer path) running in Hermes. So this file
 * is the load-bearing one of the family. Get this right first; Go and
 * PHP can lag.
 *
 * Additional TS-specific notes:
 *  - BACKPORT-EN008-TS: zstd needs a JS-side library. Candidates:
 *      `fzstd` (smaller, decode-only, browser-friendly) or
 *      `@oneidentity/zstd-js`. Verify it works in Hermes runtime —
 *      some pure-JS zstd libs assume Node `Buffer` / `Worker`.
 *  - BACKPORT-EN009-TS: For the HTTP-Range remote reader, use
 *      `fetch(url, { headers: { Range: 'bytes=N-M' }})`. Hermes 0.74+
 *      supports fetch natively; otherwise polyfill via `expo/fetch`.
 *  - BACKPORT-EN021-TS: `ZIMReaderBrowser` (ArrayBuffer-based) is the
 *      class EnZIMErgent will consume. Make sure post-rewrite it stays
 *      browser/Hermes-safe (no Node fs imports in its dependency tree).
 *
 * grep -n BACKPORT-EN zimlib.ts zimlib.py examples/  to find all sites.
 * =====================================================================
 */

import { readFileSync, writeFileSync, openSync, closeSync, readSync, writeSync, fstatSync } from 'fs';
import { createGunzip, createInflate, gunzipSync, inflateSync } from 'zlib';
import { promisify } from 'util';

export enum CompressionType {
    DEFAULT = 0,
    NONE = 1,
    ZLIB = 2,
    BZIP2 = 3,
    LZMA = 4,
    ZSTD = 5
}

export enum Namespace {
    MAIN_ARTICLE = 'A'.charCodeAt(0),
    IMAGE = 'I'.charCodeAt(0),
    METADATA = 'M'.charCodeAt(0),
    RAW_DATA = '-'.charCodeAt(0),
    STYLE = 'S'.charCodeAt(0),
    SCRIPT = 'J'.charCodeAt(0),
    FONT = 'T'.charCodeAt(0),
    TRANSLATION = 'U'.charCodeAt(0),
    VIDEO = 'V'.charCodeAt(0),
    AUDIO = 'W'.charCodeAt(0)
}

export interface ZIMHeader {
    magicNumber: number;
    majorVersion: number;
    minorVersion: number;
    entryCount: number;
    articleCount: number;
    clusterCount: number;
    redirectCount: number;
    mimeTypeListPos: bigint;
    titleIndexPos: bigint;
    clusterPtrPos: bigint;
    clusterCountPos: bigint;
    mainPageIndex: number;
    layoutPageIndex: number;
    checksumPos: bigint;
}

export interface DirectoryEntry {
    mimetypeIndex: number;
    namespace: number;
    revision: number;
    clusterNumber: number;
    blobNumber: number;
    url: string;
    title: string;
}

export interface RedirectEntry {
    mimetypeIndex: number;
    namespace: number;
    revision: number;
    redirectIndex: number;
    url: string;
    title: string;
}

export type Entry = DirectoryEntry | RedirectEntry;

/**
 * Binary reader utility for ZIM files
 */
class BinaryReader {
    private buffer: Buffer;
    private position: number = 0;

    constructor(buffer: Buffer) {
        this.buffer = buffer;
    }

    readUInt32LE(): number {
        const value = this.buffer.readUInt32LE(this.position);
        this.position += 4;
        return value;
    }

    readUInt16LE(): number {
        const value = this.buffer.readUInt16LE(this.position);
        this.position += 2;
        return value;
    }

    readUInt8(): number {
        const value = this.buffer.readUInt8(this.position);
        this.position += 1;
        return value;
    }

    readUInt64LE(): bigint {
        const value = this.buffer.readBigUInt64LE(this.position);
        this.position += 8;
        return value;
    }

    readNullTerminatedString(): string {
        const start = this.position;
        while (this.position < this.buffer.length && this.buffer[this.position] !== 0) {
            this.position++;
        }
        const str = this.buffer.toString('utf8', start, this.position);
        this.position++; // Skip null terminator
        return str;
    }

    seek(position: number): void {
        this.position = position;
    }

    getPosition(): number {
        return this.position;
    }

    readBytes(length: number): Buffer {
        const bytes = this.buffer.subarray(this.position, this.position + length);
        this.position += length;
        return bytes;
    }
}

/**
 * Binary writer utility for ZIM files
 */
class BinaryWriter {
    private buffer: Buffer;
    private position: number = 0;

    constructor(initialSize: number = 1024) {
        this.buffer = Buffer.alloc(initialSize);
    }

    private ensureCapacity(additionalBytes: number): void {
        if (this.position + additionalBytes > this.buffer.length) {
            const newSize = Math.max(this.buffer.length * 2, this.position + additionalBytes);
            const newBuffer = Buffer.alloc(newSize);
            this.buffer.copy(newBuffer);
            this.buffer = newBuffer;
        }
    }

    writeUInt32LE(value: number): void {
        this.ensureCapacity(4);
        this.buffer.writeUInt32LE(value, this.position);
        this.position += 4;
    }

    writeUInt16LE(value: number): void {
        this.ensureCapacity(2);
        this.buffer.writeUInt16LE(value, this.position);
        this.position += 2;
    }

    writeUInt8(value: number): void {
        this.ensureCapacity(1);
        this.buffer.writeUInt8(value, this.position);
        this.position += 1;
    }

    writeUInt64LE(value: bigint): void {
        this.ensureCapacity(8);
        this.buffer.writeBigUInt64LE(value, this.position);
        this.position += 8;
    }

    writeNullTerminatedString(str: string): void {
        const strBytes = Buffer.from(str, 'utf8');
        this.ensureCapacity(strBytes.length + 1);
        strBytes.copy(this.buffer, this.position);
        this.position += strBytes.length;
        this.buffer[this.position] = 0; // Null terminator
        this.position += 1;
    }

    writeBytes(bytes: Buffer): void {
        this.ensureCapacity(bytes.length);
        bytes.copy(this.buffer, this.position);
        this.position += bytes.length;
    }

    seek(position: number): void {
        this.position = position;
    }

    getPosition(): number {
        return this.position;
    }

    getBuffer(): Buffer {
        return this.buffer.subarray(0, this.position);
    }
}

/**
 * ZIM file reader class
 */
export class ZIMReader {
    private filePath: string;
    private fileHandle?: number;
    private fileBuffer?: Buffer;
    private header?: ZIMHeader;
    private mimeTypes: string[] = [];
    private directoryEntries: Entry[] = [];
    private clusterOffsets: bigint[] = [];

    constructor(filePath: string) {
        this.filePath = filePath;
    }

    open(): void {
        this.fileBuffer = readFileSync(this.filePath);
        this.readHeader();
        this.readMimeTypes();
        this.readDirectory();
        this.readClusterPointers();
    }

    close(): void {
        if (this.fileHandle !== undefined) {
            closeSync(this.fileHandle);
            this.fileHandle = undefined;
        }
        this.fileBuffer = undefined;
    }

    private readHeader(): void {
        if (!this.fileBuffer) throw new Error('File not opened');

        const reader = new BinaryReader(this.fileBuffer);
        this.header = {
            magicNumber: reader.readUInt32LE(),
            majorVersion: reader.readUInt16LE(),
            minorVersion: reader.readUInt16LE(),
            entryCount: reader.readUInt32LE(),
            articleCount: reader.readUInt32LE(),
            clusterCount: reader.readUInt32LE(),
            redirectCount: reader.readUInt32LE(),
            mimeTypeListPos: reader.readUInt64LE(),
            titleIndexPos: reader.readUInt64LE(),
            clusterPtrPos: reader.readUInt64LE(),
            clusterCountPos: reader.readUInt64LE(),
            mainPageIndex: reader.readUInt32LE(),
            layoutPageIndex: reader.readUInt32LE(),
            checksumPos: reader.readUInt64LE()
        };

        // TODO(BACKPORT-EN001): Magic number is WRONG. The openZIM v5
        // magic is 0x044D495A (bytes Z I M \x04 little-endian). The value
        // 0x4D495A5A here is "ZZIM" which never appears in a real archive.
        // Replace with `0x044D495A`. Same fix needed at line ~727 below
        // (ZIMReaderBrowser) and in the writer.
        // Verify magic number
        if (this.header.magicNumber !== 0x4D495A5A) { // "ZZIM" in little endian
            throw new Error('Invalid ZIM file format');
        }
    }

    private readMimeTypes(): void {
        if (!this.header || !this.fileBuffer) throw new Error('Header not parsed or file not opened');

        const startPos = Number(this.header.mimeTypeListPos);
        const reader = new BinaryReader(this.fileBuffer.subarray(startPos));

        const mimeTypesData: Buffer[] = [];
        let currentChunk = Buffer.alloc(0);

        // Read until double null terminator
        while (true) {
            const chunk = reader.readBytes(1024);
            if (chunk.length === 0) break;

            currentChunk = Buffer.concat([currentChunk, chunk]);

            // Check for double null terminator
            const nullNullPos = currentChunk.indexOf(Buffer.from([0, 0]));
            if (nullNullPos !== -1) {
                mimeTypesData.push(currentChunk.subarray(0, nullNullPos));
                break;
            }
        }

        // Split by null terminator and filter empty strings
        const mimeTypesString = mimeTypesData[0]?.toString('utf8') || '';
        this.mimeTypes = mimeTypesString.split('\x00').filter(mt => mt.length > 0);
    }

    private readDirectory(): void {
        if (!this.header || !this.fileBuffer) throw new Error('Header not parsed or file not opened');

        // Read index pointer list (starts after header at offset 80)
        const indexPtrStart = 80;
        const reader = new BinaryReader(this.fileBuffer.subarray(indexPtrStart));

        const indexPointers: bigint[] = [];
        for (let i = 0; i < this.header.entryCount; i++) {
            indexPointers.push(reader.readUInt64LE());
        }

        // Read directory entries
        for (const ptr of indexPointers) {
            const entryReader = new BinaryReader(this.fileBuffer!.subarray(Number(ptr)));

            // Read mimetype to determine entry type
            const mimetype = entryReader.readUInt32LE();
            entryReader.seek(0); // Reset position

            if (mimetype === 0xFFFF) { // Redirect entry
                const entry = this.readRedirectEntry(entryReader);
                this.directoryEntries.push(entry);
            } else { // Article entry
                const entry = this.readDirectoryEntry(entryReader);
                this.directoryEntries.push(entry);
            }
        }
    }

    private readDirectoryEntry(reader: BinaryReader): DirectoryEntry {
        const mimetypeIndex = reader.readUInt32LE();
        const namespace = reader.readUInt8();
        const revision = reader.readUInt32LE();
        const clusterNumber = reader.readUInt32LE();
        const blobNumber = reader.readUInt32LE();
        const url = reader.readNullTerminatedString();
        const title = reader.readNullTerminatedString();

        return {
            mimetypeIndex,
            namespace,
            revision,
            clusterNumber,
            blobNumber,
            url,
            title
        };
    }

    private readRedirectEntry(reader: BinaryReader): RedirectEntry {
        const mimetypeIndex = reader.readUInt32LE();
        const namespace = reader.readUInt8();
        const revision = reader.readUInt32LE();
        const redirectIndex = reader.readUInt32LE();
        const url = reader.readNullTerminatedString();
        const title = reader.readNullTerminatedString();

        return {
            mimetypeIndex,
            namespace,
            revision,
            redirectIndex,
            url,
            title
        };
    }

    private readClusterPointers(): void {
        if (!this.header || !this.fileBuffer) throw new Error('Header not parsed or file not opened');

        const startPos = Number(this.header.clusterPtrPos);
        const reader = new BinaryReader(this.fileBuffer.subarray(startPos));

        for (let i = 0; i < this.header.clusterCount; i++) {
            this.clusterOffsets.push(reader.readUInt64LE());
        }
    }

    getEntryByPath(path: string): Entry | undefined {
        const namespace = path.charCodeAt(0);
        const url = path.length > 2 ? path.substring(2) : '';

        return this.directoryEntries.find(entry =>
            entry.namespace === namespace && entry.url === url
        );
    }

    getArticleContent(entry: DirectoryEntry): Buffer {
        if (!this.fileBuffer || !this.header) {
            throw new Error('File not opened or header not parsed');
        }

        // Get cluster offset
        const clusterOffset = Number(this.clusterOffsets[entry.clusterNumber]);
        const clusterReader = new BinaryReader(this.fileBuffer.subarray(clusterOffset));

        // Read cluster header (compression type)
        const compressionByte = clusterReader.readUInt8();

        // Read blob offsets
        const blobOffsets: number[] = [];
        while (true) {
            const offset = clusterReader.readUInt32LE();
            blobOffsets.push(offset);
            if (offset === 0) break; // Last offset
        }

        // Calculate blob size and position
        if (entry.blobNumber >= blobOffsets.length - 1) {
            throw new Error('Invalid blob number');
        }

        const blobStart = blobOffsets[entry.blobNumber];
        const blobEnd = blobOffsets[entry.blobNumber + 1];
        const blobSize = blobEnd - blobStart;

        // Read blob data
        const currentPos = clusterReader.getPosition();
        clusterReader.seek(currentPos + blobStart);

        let blobData = clusterReader.readBytes(blobSize);

        // Decompress if needed
        if (compressionByte === CompressionType.ZLIB) {
            blobData = inflateSync(blobData);
        } else if (compressionByte === CompressionType.LZMA) {
            throw new Error('LZMA compression not implemented in this clean-room version');
        }

        return blobData;
    }

    getMainPage(): Entry | undefined {
        if (!this.header) return undefined;

        if (this.header.mainPageIndex < this.directoryEntries.length) {
            return this.directoryEntries[this.header.mainPageIndex];
        }

        return undefined;
    }

    listArticles(): DirectoryEntry[] {
        return this.directoryEntries.filter(entry =>
            'clusterNumber' in entry && 'blobNumber' in entry
        ) as DirectoryEntry[];
    }

    getMimeTypes(): string[] {
        return [...this.mimeTypes];
    }

    getHeader(): ZIMHeader | undefined {
        return this.header;
    }
}

/**
 * ZIM file writer class
 */
export class ZIMWriter {
    private filePath: string;
    private mimeTypes: string[] = [];
    private directoryEntries: Entry[] = [];
    private clusters: Buffer[] = [];
    private mainPageIndex: number = 0;

    constructor(filePath: string) {
        this.filePath = filePath;
    }

    create(): void {
        // Write placeholder header
        const writer = new BinaryWriter(80);
        writer.writeUInt32LE(0x4D495A5A); // Magic number
        writer.writeUInt16LE(4); // Major version
        writer.writeUInt16LE(0); // Minor version
        writer.writeUInt32LE(0); // Entry count
        writer.writeUInt32LE(0); // Article count
        writer.writeUInt32LE(0); // Cluster count
        writer.writeUInt32LE(0); // Redirect count
        writer.writeUInt64LE(BigInt(0)); // MIME type list pos
        writer.writeUInt64LE(BigInt(0)); // Title index pos
        writer.writeUInt64LE(BigInt(0)); // Cluster ptr pos
        writer.writeUInt64LE(BigInt(0)); // Cluster count pos
        writer.writeUInt32LE(0); // Main page index
        writer.writeUInt32LE(0); // Layout page index
        writer.writeUInt64LE(BigInt(0)); // Checksum pos

        writeFileSync(this.filePath, writer.getBuffer());
    }

    addMimeType(mimeType: string): number {
        if (!this.mimeTypes.includes(mimeType)) {
            this.mimeTypes.push(mimeType);
        }
        return this.mimeTypes.indexOf(mimeType);
    }

    addArticle(namespace: number, url: string, title: string, content: Buffer, mimeType: string = 'text/html'): void {
        const mimetypeIndex = this.addMimeType(mimeType);

        // Create cluster with content (for simplicity, one blob per cluster)
        const clusterData = this.createCluster([content], CompressionType.DEFAULT);
        const clusterNumber = this.clusters.length;
        this.clusters.push(clusterData);

        const entry: DirectoryEntry = {
            mimetypeIndex,
            namespace,
            revision: 0,
            clusterNumber,
            blobNumber: 0,
            url,
            title
        };

        this.directoryEntries.push(entry);
    }

    addRedirect(namespace: number, url: string, title: string, redirectIndex: number): void {
        const entry: RedirectEntry = {
            mimetypeIndex: 0xFFFF, // Redirect marker
            namespace,
            revision: 0,
            redirectIndex,
            url,
            title
        };

        this.directoryEntries.push(entry);
    }

    private createCluster(blobs: Buffer[], compression: CompressionType): Buffer {
        // Calculate blob offsets
        const offsets: number[] = [0];
        let currentOffset = 0;
        for (const blob of blobs) {
            currentOffset += blob.length;
            offsets.push(currentOffset);
        }

        const writer = new BinaryWriter();
        writer.writeUInt8(compression);

        // Add offsets
        for (const offset of offsets) {
            writer.writeUInt32LE(offset);
        }

        // Add blob data
        for (let blob of blobs) {
            if (compression === CompressionType.ZLIB) {
                blob = Buffer.from(deflateSync(blob));
            }
            writer.writeBytes(blob);
        }

        return writer.getBuffer();
    }

    finalize(): void {
        // Calculate positions
        let currentPos = 80; // After header

        // Write MIME type list
        const mimeTypePos = currentPos;
        const mimeTypeData = Buffer.concat([
            Buffer.from(this.mimeTypes.join('\x00'), 'utf8'),
            Buffer.from([0, 0]) // Double null terminator
        ]);
        currentPos += mimeTypeData.length;

        // Write directory entries
        const directoryPos = currentPos;
        const indexPointers: bigint[] = [];

        for (const entry of this.directoryEntries) {
            indexPointers.push(BigInt(currentPos));
            const entryData = this.serializeEntry(entry);
            currentPos += entryData.length;
        }

        // Write index pointer list
        const indexPtrPos = currentPos;
        currentPos += indexPointers.length * 8;

        // Write cluster pointer list
        const clusterPtrPos = currentPos;
        const clusterOffsets: bigint[] = [];

        for (const cluster of this.clusters) {
            clusterOffsets.push(BigInt(currentPos));
            currentPos += cluster.length;
        }

        // Update header with real values
        const articleCount = this.directoryEntries.filter(entry =>
            'clusterNumber' in entry && 'blobNumber' in entry
        ).length;
        const redirectCount = this.directoryEntries.filter(entry =>
            'redirectIndex' in entry
        ).length;

        const headerWriter = new BinaryWriter(80);
        headerWriter.writeUInt32LE(0x4D495A5A); // Magic number
        headerWriter.writeUInt16LE(4); // Major version
        headerWriter.writeUInt16LE(0); // Minor version
        headerWriter.writeUInt32LE(this.directoryEntries.length); // Entry count
        headerWriter.writeUInt32LE(articleCount); // Article count
        headerWriter.writeUInt32LE(this.clusters.length); // Cluster count
        headerWriter.writeUInt32LE(redirectCount); // Redirect count
        headerWriter.writeUInt64LE(BigInt(mimeTypePos)); // MIME type list pos
        headerWriter.writeUInt64LE(BigInt(0)); // Title index pos
        headerWriter.writeUInt64LE(BigInt(clusterPtrPos)); // Cluster ptr pos
        headerWriter.writeUInt64LE(BigInt(0)); // Cluster count pos
        headerWriter.writeUInt32LE(this.mainPageIndex); // Main page index
        headerWriter.writeUInt32LE(0); // Layout page index
        headerWriter.writeUInt64LE(BigInt(currentPos)); // Checksum pos

        // Write all data to file
        const finalWriter = new BinaryWriter();
        finalWriter.writeBytes(headerWriter.getBuffer());
        finalWriter.writeBytes(mimeTypeData);

        // Write directory entries
        for (const entry of this.directoryEntries) {
            finalWriter.writeBytes(this.serializeEntry(entry));
        }

        // Write index pointer list
        for (const ptr of indexPointers) {
            finalWriter.writeUInt64LE(ptr);
        }

        // Write cluster pointer list
        for (const offset of clusterOffsets) {
            finalWriter.writeUInt64LE(offset);
        }

        // Write clusters
        for (const cluster of this.clusters) {
            finalWriter.writeBytes(cluster);
        }

        // Write placeholder checksum
        finalWriter.writeBytes(Buffer.alloc(16)); // 16-byte checksum placeholder

        writeFileSync(this.filePath, finalWriter.getBuffer());
    }

    private serializeEntry(entry: Entry): Buffer {
        const writer = new BinaryWriter();

        if ('redirectIndex' in entry) {
            // Redirect entry
            const redirectEntry = entry as RedirectEntry;
            writer.writeUInt32LE(redirectEntry.mimetypeIndex);
            writer.writeUInt8(redirectEntry.namespace);
            writer.writeUInt32LE(redirectEntry.revision);
            writer.writeUInt32LE(redirectEntry.redirectIndex);
            writer.writeNullTerminatedString(redirectEntry.url);
            writer.writeNullTerminatedString(redirectEntry.title);
        } else {
            // Directory entry
            const dirEntry = entry as DirectoryEntry;
            writer.writeUInt32LE(dirEntry.mimetypeIndex);
            writer.writeUInt8(dirEntry.namespace);
            writer.writeUInt32LE(dirEntry.revision);
            writer.writeUInt32LE(dirEntry.clusterNumber);
            writer.writeUInt32LE(dirEntry.blobNumber);
            writer.writeNullTerminatedString(dirEntry.url);
            writer.writeNullTerminatedString(dirEntry.title);
        }

        return writer.getBuffer();
    }

    close(): void {
        // Nothing to do for file-based writer
    }
}

// Utility functions
export function readZIMFile(filePath: string): ZIMReader {
    return new ZIMReader(filePath);
}

export function createZIMFile(filePath: string): ZIMWriter {
    return new ZIMWriter(filePath);
}

// Browser-compatible version (for Chrome extensions)
export class ZIMReaderBrowser {
    private arrayBuffer: ArrayBuffer;
    private header?: ZIMHeader;
    private mimeTypes: string[] = [];
    private directoryEntries: Entry[] = [];
    private clusterOffsets: bigint[] = [];

    constructor(arrayBuffer: ArrayBuffer) {
        this.arrayBuffer = arrayBuffer;
    }

    async open(): Promise<void> {
        const buffer = new Uint8Array(this.arrayBuffer);
        const reader = new BinaryReader(Buffer.from(buffer));

        this.readHeader(reader);
        await this.readMimeTypes(reader);
        await this.readDirectory(reader);
        this.readClusterPointers(reader);
    }

    private readHeader(reader: BinaryReader): void {
        this.header = {
            magicNumber: reader.readUInt32LE(),
            majorVersion: reader.readUInt16LE(),
            minorVersion: reader.readUInt16LE(),
            entryCount: reader.readUInt32LE(),
            articleCount: reader.readUInt32LE(),
            clusterCount: reader.readUInt32LE(),
            redirectCount: reader.readUInt32LE(),
            mimeTypeListPos: reader.readUInt64LE(),
            titleIndexPos: reader.readUInt64LE(),
            clusterPtrPos: reader.readUInt64LE(),
            clusterCountPos: reader.readUInt64LE(),
            mainPageIndex: reader.readUInt32LE(),
            layoutPageIndex: reader.readUInt32LE(),
            checksumPos: reader.readUInt64LE()
        };

        // TODO(BACKPORT-EN001, BACKPORT-EN021-TS): Same wrong magic as
        // line ~260; replace with 0x044D495A. THIS class (ZIMReaderBrowser)
        // is the one EnZIMErgent's mobile app will consume — getting this
        // line right is highest priority across the entire library.
        if (this.header.magicNumber !== 0x4D495A5A) {
            throw new Error('Invalid ZIM file format');
        }
    }

    private async readMimeTypes(reader: BinaryReader): Promise<void> {
        if (!this.header) throw new Error('Header not parsed');

        reader.seek(Number(this.header.mimeTypeListPos));

        const mimeTypesData: number[] = [];
        let prevByte = 0;
        let nullNullCount = 0;

        while (nullNullCount < 2 && reader.getPosition() < this.arrayBuffer.byteLength) {
            const byte = reader.readUInt8();
            mimeTypesData.push(byte);

            if (byte === 0 && prevByte === 0) {
                nullNullCount++;
            }
            prevByte = byte;
        }

        const mimeTypesString = Buffer.from(mimeTypesData).toString('utf8');
        this.mimeTypes = mimeTypesString.split('\x00').filter(mt => mt.length > 0);
    }

    private async readDirectory(reader: BinaryReader): Promise<void> {
        if (!this.header) throw new Error('Header not parsed');

        // Read index pointer list (starts after header at offset 80)
        reader.seek(80);

        const indexPointers: bigint[] = [];
        for (let i = 0; i < this.header.entryCount; i++) {
            indexPointers.push(reader.readUInt64LE());
        }

        // Read directory entries
        for (const ptr of indexPointers) {
            reader.seek(Number(ptr));

            const mimetype = reader.readUInt32LE();
            reader.seek(Number(ptr)); // Reset

            if (mimetype === 0xFFFF) {
                const entry = this.readRedirectEntry(reader);
                this.directoryEntries.push(entry);
            } else {
                const entry = this.readDirectoryEntry(reader);
                this.directoryEntries.push(entry);
            }
        }
    }

    private readDirectoryEntry(reader: BinaryReader): DirectoryEntry {
        const mimetypeIndex = reader.readUInt32LE();
        const namespace = reader.readUInt8();
        const revision = reader.readUInt32LE();
        const clusterNumber = reader.readUInt32LE();
        const blobNumber = reader.readUInt32LE();
        const url = reader.readNullTerminatedString();
        const title = reader.readNullTerminatedString();

        return {
            mimetypeIndex,
            namespace,
            revision,
            clusterNumber,
            blobNumber,
            url,
            title
        };
    }

    private readRedirectEntry(reader: BinaryReader): RedirectEntry {
        const mimetypeIndex = reader.readUInt32LE();
        const namespace = reader.readUInt8();
        const revision = reader.readUInt32LE();
        const redirectIndex = reader.readUInt32LE();
        const url = reader.readNullTerminatedString();
        const title = reader.readNullTerminatedString();

        return {
            mimetypeIndex,
            namespace,
            revision,
            redirectIndex,
            url,
            title
        };
    }

    private readClusterPointers(reader: BinaryReader): void {
        if (!this.header) throw new Error('Header not parsed');

        reader.seek(Number(this.header.clusterPtrPos));

        for (let i = 0; i < this.header.clusterCount; i++) {
            this.clusterOffsets.push(reader.readUInt64LE());
        }
    }

    getEntryByPath(path: string): Entry | undefined {
        const namespace = path.charCodeAt(0);
        const url = path.length > 2 ? path.substring(2) : '';

        return this.directoryEntries.find(entry =>
            entry.namespace === namespace && entry.url === url
        );
    }

    async getArticleContent(entry: DirectoryEntry): Promise<Uint8Array> {
        if (!this.header) throw new Error('Header not parsed');

        const buffer = new Uint8Array(this.arrayBuffer);
        const reader = new BinaryReader(Buffer.from(buffer));

        // Get cluster offset
        const clusterOffset = Number(this.clusterOffsets[entry.clusterNumber]);
        reader.seek(clusterOffset);

        // Read cluster header (compression type)
        const compressionByte = reader.readUInt8();

        // Read blob offsets
        const blobOffsets: number[] = [];
        while (true) {
            const offset = reader.readUInt32LE();
            blobOffsets.push(offset);
            if (offset === 0) break;
        }

        // Calculate blob size and position
        if (entry.blobNumber >= blobOffsets.length - 1) {
            throw new Error('Invalid blob number');
        }

        const blobStart = blobOffsets[entry.blobNumber];
        const blobEnd = blobOffsets[entry.blobNumber + 1];
        const blobSize = blobEnd - blobStart;

        // Read blob data
        const currentPos = reader.getPosition();
        reader.seek(currentPos + blobStart);

        let blobData = reader.readBytes(blobSize);

        // Decompress if needed
        if (compressionByte === CompressionType.ZLIB) {
            blobData = Buffer.from(inflateSync(blobData));
        }

        return new Uint8Array(blobData);
    }

    getMainPage(): Entry | undefined {
        if (!this.header) return undefined;

        if (this.header.mainPageIndex < this.directoryEntries.length) {
            return this.directoryEntries[this.header.mainPageIndex];
        }

        return undefined;
    }

    listArticles(): DirectoryEntry[] {
        return this.directoryEntries.filter(entry =>
            'clusterNumber' in entry && 'blobNumber' in entry
        ) as DirectoryEntry[];
    }
}
