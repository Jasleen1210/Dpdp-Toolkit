import mammoth from "mammoth/mammoth.browser";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

const MAX_SCAN_TEXT_LENGTH = 500_000;

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export interface ScanPayloadEntry {
  name: string;
  content: string;
}

interface ExtractInput {
  name: string;
  extension?: string;
  blob: Blob;
}

function normalizeExtractedText(text: string): string {
  const normalized = text
    .replace(/\u0000/g, "")
    .replace(/\r\n/g, "\n")
    .trim();
  if (normalized.length <= MAX_SCAN_TEXT_LENGTH) return normalized;
  return (
    normalized.slice(0, MAX_SCAN_TEXT_LENGTH) +
    "\n\n...[truncated for scan payload]"
  );
}

function extractReadableStringsFromPdfBytes(data: Uint8Array): string {
  const source = new TextDecoder("latin1").decode(data);
  const matches = source.match(/\((?:\\.|[^\\)])*\)/g) || [];

  const decoded = matches
    .map((token) => token.slice(1, -1))
    .map((token) =>
      token
        .replace(/\\\(/g, "(")
        .replace(/\\\)/g, ")")
        .replace(/\\n/g, "\n")
        .replace(/\\r/g, "\n")
        .replace(/\\t/g, "\t")
        .replace(/\\\\/g, "\\")
        .replace(/\\([0-7]{1,3})/g, (_, octal) =>
          String.fromCharCode(parseInt(octal, 8)),
        ),
    )
    .map((t) => t.replace(/\s+/g, " ").trim())
    .filter(Boolean);

  return normalizeExtractedText(decoded.join("\n"));
}

async function extractPdfText(blob: Blob): Promise<string> {
  const data = new Uint8Array(await blob.arrayBuffer());
  const loadingTask = getDocument({
    data,
    disableWorker: true,
    useWorkerFetch: false,
  });

  const pdf = await loadingTask.promise;
  const pages: string[] = [];
  const pageStats: Array<{ page: number; items: number; chars: number }> = [];

  for (let pageNo = 1; pageNo <= pdf.numPages; pageNo += 1) {
    const page = await pdf.getPage(pageNo);
    const textContent = await page.getTextContent({
      includeMarkedContent: true,
    });
    const pageText = textContent.items
      .map((item) => {
        if (typeof item === "object" && item && "str" in item) {
          const str = (item as { str?: unknown }).str;
          return typeof str === "string" ? str : "";
        }
        return "";
      })
      .join(" ")
      .trim();

    pageStats.push({
      page: pageNo,
      items: textContent.items.length,
      chars: pageText.length,
    });

    if (pageText) pages.push(pageText);
  }

  const normalized = normalizeExtractedText(pages.join("\n"));
  const rawFallback = !normalized
    ? extractReadableStringsFromPdfBytes(data)
    : "";
  const finalText = normalized || rawFallback;

  console.log("[LocalScan][PDF Parsed]", {
    pages: pdf.numPages,
    pageStats,
    chars: finalText.length,
    mode: normalized
      ? "pdfjs-text"
      : rawFallback
        ? "raw-bytes-fallback"
        : "none",
    preview: finalText.slice(0, 240),
  });

  return finalText;
}

async function extractDocxText(blob: Blob): Promise<string> {
  const arrayBuffer = await blob.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer });
  const normalized = normalizeExtractedText(result.value || "");
  console.log("[LocalScan][DOCX Parsed]", {
    chars: normalized.length,
    preview: normalized.slice(0, 240),
  });
  return normalized;
}

export async function extractTextForScan(input: ExtractInput): Promise<string> {
  const extension = (input.extension || input.name.split(".").pop() || "")
    .toLowerCase()
    .trim();

  if (extension === "pdf") {
    return extractPdfText(input.blob);
  }

  if (extension === "docx") {
    return extractDocxText(input.blob);
  }

  return normalizeExtractedText(await input.blob.text());
}

export async function buildScanPayloadEntry(
  input: ExtractInput,
): Promise<ScanPayloadEntry | null> {
  const content = await extractTextForScan(input);
  const extension = (input.extension || input.name.split(".").pop() || "")
    .toLowerCase()
    .trim();

  const fallback =
    extension === "pdf" || extension === "docx"
      ? "[No extractable text found in document]"
      : "[No text found in file]";

  return {
    name: input.name,
    content: content || fallback,
  };
}
