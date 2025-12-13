/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */
// TODO  MC80OmFIVnBZMlhuZzV2bmtJWTZhbkZ0V0E9PTozOTc3ZWFlOQ==

import type { Base64ContentBlock } from "@langchain/core/messages";
import { toast } from "sonner";

// 定义期望的图片格式类型
export interface ImageUrlContentBlock {
  type: "image_url";
  image_url: {
    url: string;
    metadata?: {
      name: string;
    };
  };
}
// @ts-expect-error  MS80OmFIVnBZMlhuZzV2bmtJWTZhbkZ0V0E9PTozOTc3ZWFlOQ==

// 定义文件内容块类型
export interface FileContentBlock {
  type: "file";
  source_type: "base64";
  mime_type: string;
  data: string;
  metadata: { filename: string };
}

// 联合类型
export type OptimizedContentBlock = ImageUrlContentBlock | FileContentBlock;
// FIXME  Mi80OmFIVnBZMlhuZzV2bmtJWTZhbkZ0V0E9PTozOTc3ZWFlOQ==

// Returns a Promise of a typed multimodal block for images or PDFs
export async function fileToContentBlock(
  file: File,
): Promise<OptimizedContentBlock> {
  const supportedImageTypes = [
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
  ];
  const supportedFileTypes = [...supportedImageTypes, "application/pdf"];

  if (!supportedFileTypes.includes(file.type)) {
    toast.error(
      `Unsupported file type: ${file.type}. Supported types are: ${supportedFileTypes.join(", ")}`,
    );
    return Promise.reject(new Error(`Unsupported file type: ${file.type}`));
  }

  const data = await fileToBase64(file);

  if (supportedImageTypes.includes(file.type)) {
    // 返回期望的 image_url 格式
    return {
      type: "image_url",
      image_url: {
        url: `data:${file.type};base64,${data}`,
        metadata: {
          name: file.name,
        },
      },
    };
  }

  // PDF - 保持原有格式
  return {
    type: "file",
    source_type: "base64",
    mime_type: "application/pdf",
    data,
    metadata: { filename: file.name },
  };
}

// Helper to convert File to base64 string
export async function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // Remove the data:...;base64, prefix
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// Type guard for OptimizedContentBlock
export function isOptimizedContentBlock(
  block: unknown,
): block is OptimizedContentBlock {
  if (typeof block !== "object" || block === null || !("type" in block))
    return false;

  // 检查 image_url 类型
  if (
    (block as { type: unknown }).type === "image_url" &&
    "image_url" in block &&
    typeof (block as { image_url?: unknown }).image_url === "object" &&
    (block as { image_url: any }).image_url !== null &&
    "url" in (block as { image_url: any }).image_url &&
    typeof (block as { image_url: { url?: unknown } }).image_url.url === "string"
  ) {
    return true;
  }

  // 检查 file 类型
  if (
    (block as { type: unknown }).type === "file" &&
    "source_type" in block &&
    (block as { source_type: unknown }).source_type === "base64" &&
    "mime_type" in block &&
    typeof (block as { mime_type?: unknown }).mime_type === "string" &&
    (block as { mime_type: string }).mime_type === "application/pdf"
  ) {
    return true;
  }

  return false;
}

// 保留原有的类型守卫以兼容性
export function isBase64ContentBlock(
  block: unknown,
): block is Base64ContentBlock {
  if (typeof block !== "object" || block === null || !("type" in block))
    return false;
  // file type (legacy)
  if (
    (block as { type: unknown }).type === "file" &&
    "source_type" in block &&
    (block as { source_type: unknown }).source_type === "base64" &&
    "mime_type" in block &&
    typeof (block as { mime_type?: unknown }).mime_type === "string" &&
    ((block as { mime_type: string }).mime_type.startsWith("image/") ||
      (block as { mime_type: string }).mime_type === "application/pdf")
  ) {
    return true;
  }
  // image type (new)
  if (
    (block as { type: unknown }).type === "image" &&
    "source_type" in block &&
    (block as { source_type: unknown }).source_type === "base64" &&
    "mime_type" in block &&
    typeof (block as { mime_type?: unknown }).mime_type === "string" &&
    (block as { mime_type: string }).mime_type.startsWith("image/")
  ) {
    return true;
  }
  return false;
}
// TODO  My80OmFIVnBZMlhuZzV2bmtJWTZhbkZ0V0E9PTozOTc3ZWFlOQ==
