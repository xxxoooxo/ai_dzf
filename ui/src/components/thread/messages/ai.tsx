/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */
// NOTE  MC80OmFIVnBZMlhuZzV2bmtJWTZNVWxYY2c9PTo5ZTdmN2ZkZA==

import { parsePartialJson } from "@langchain/core/output_parsers";
import { useStreamContext } from "@/providers/Stream";
import { AIMessage, Checkpoint, Message } from "@langchain/langgraph-sdk";
import { getContentString } from "../utils";
import { BranchSwitcher, CommandBar } from "./shared";
import { MarkdownText } from "../markdown-text";
import { LoadExternalComponent } from "@langchain/langgraph-sdk/react-ui";
import { cn } from "@/lib/utils";
import { ToolCalls } from "./tool-calls-new";
import { MessageContentComplex } from "@langchain/core/messages";
import { Fragment } from "react/jsx-runtime";
import { isAgentInboxInterruptSchema } from "@/lib/agent-inbox-interrupt";
import { ThreadView } from "../agent-inbox";
import { useQueryState, parseAsBoolean } from "nuqs";
import { GenericInterruptView } from "./generic-interrupt";
import { useArtifact } from "../artifact";
import { useRafThrottledValue } from "@/hooks/useRafThrottledValue";

function CustomComponent({
  message,
  thread,
}: {
  message: Message;
  thread: ReturnType<typeof useStreamContext>;
}) {
  const artifact = useArtifact();
  const { values } = useStreamContext();
  const customComponents = values.ui?.filter(
    (ui) => ui.metadata?.message_id === message.id,
  );

  if (!customComponents?.length) return null;
  return (
    <Fragment key={message.id}>
      {customComponents.map((customComponent) => (
        <LoadExternalComponent
          key={customComponent.id}
          stream={thread}
          message={customComponent}
          meta={{ ui: customComponent, artifact }}
        />
      ))}
    </Fragment>
  );
}
// NOTE  MS80OmFIVnBZMlhuZzV2bmtJWTZNVWxYY2c9PTo5ZTdmN2ZkZA==

function parseAnthropicStreamedToolCalls(
  content: MessageContentComplex[],
): AIMessage["tool_calls"] {
  const toolCallContents = content.filter((c) => c.type === "tool_use" && c.id);

  return toolCallContents
    .map((tc) => {
      const toolCall = tc as Record<string, any>;
      let json: Record<string, any> = {};
      if (toolCall?.input) {
        try {
          json = parsePartialJson(toolCall.input) ?? {};
        } catch {
          // Pass
        }
      }
      return {
        name: toolCall.name ?? "",
        id: toolCall.id ?? "",
        args: json,
        type: "tool_call" as const,
      };
    })
    .filter((tc) => tc.name && tc.name.trim() !== ""); // Filter out empty names
}

interface InterruptProps {
  interruptValue?: unknown;
  isLastMessage: boolean;
  hasNoAIOrToolMessages: boolean;
}

function Interrupt({
  interruptValue,
  isLastMessage,
  hasNoAIOrToolMessages,
}: InterruptProps) {
  return (
    <>
      {isAgentInboxInterruptSchema(interruptValue) &&
        (isLastMessage || hasNoAIOrToolMessages) && (
          <ThreadView interrupt={interruptValue} />
        )}
      {interruptValue &&
      !isAgentInboxInterruptSchema(interruptValue) &&
      (isLastMessage || hasNoAIOrToolMessages) ? (
        <GenericInterruptView interrupt={interruptValue} />
      ) : null}
    </>
  );
}
// eslint-disable  Mi80OmFIVnBZMlhuZzV2bmtJWTZNVWxYY2c9PTo5ZTdmN2ZkZA==

export function AssistantMessage({
  message,
  isLoading,
  handleRegenerate,
}: {
  message: Message | undefined;
  isLoading: boolean;
  handleRegenerate: (parentCheckpoint: Checkpoint | null | undefined) => void;
}) {
  const content = message?.content ?? [];
  const contentString = getContentString(content);
  const [hideToolCalls] = useQueryState(
    "hideToolCalls",
    parseAsBoolean.withDefault(false),
  );

  const thread = useStreamContext();
  const lastMessageId = thread.messages[thread.messages.length - 1]?.id;
  const isLastMessage = !!lastMessageId && lastMessageId === message?.id;
  const hasNoAIOrToolMessages = !thread.messages.find(
    (m) => m.type === "ai" || m.type === "tool",
  );
  const meta = message ? thread.getMessagesMetadata(message) : undefined;
  const threadInterrupt = thread.interrupt;
  const isStreamingMessage = isLoading && isLastMessage;

  // Rendering very large markdown synchronously (plus code highlighting/math) can block the main thread
  // long enough to trigger Chrome's "Page unresponsive" prompt. Degrade to plain text for streaming/large payloads.
  const MAX_MARKDOWN_RENDER_CHARS = 80_000;
  const MAX_STREAMING_RENDER_CHARS = 30_000;
  const MAX_PLAINTEXT_RENDER_CHARS = 200_000;
  const shouldRenderMarkdown =
    !isStreamingMessage && contentString.length <= MAX_MARKDOWN_RENDER_CHARS;
  const plainText =
    isStreamingMessage && contentString.length > MAX_STREAMING_RENDER_CHARS
      ? contentString.slice(-MAX_STREAMING_RENDER_CHARS)
      : contentString.length > MAX_PLAINTEXT_RENDER_CHARS
        ? contentString.slice(-MAX_PLAINTEXT_RENDER_CHARS)
        : contentString;
  const throttledPlainText = useRafThrottledValue(plainText);
  const isTruncated =
    (isStreamingMessage && contentString.length > MAX_STREAMING_RENDER_CHARS) ||
    (!isStreamingMessage && contentString.length > MAX_PLAINTEXT_RENDER_CHARS);

  const parentCheckpoint = meta?.firstSeenState?.parent_checkpoint;
  const anthropicStreamedToolCalls = Array.isArray(content)
    ? parseAnthropicStreamedToolCalls(content)
    : undefined;

  const hasToolCalls =
    message &&
    "tool_calls" in message &&
    message.tool_calls &&
    message.tool_calls.length > 0;
  const toolCallsHaveContents =
    hasToolCalls &&
    message.tool_calls?.some(
      (tc) => tc.args && Object.keys(tc.args).length > 0,
    );
  const hasAnthropicToolCalls = !!anthropicStreamedToolCalls?.length;
  const isToolResult = message?.type === "tool";

  if (isToolResult) {
    return null; // Hide individual tool results since they're now combined with tool calls
  }

  return (
    <div className="group mr-auto w-full">
      <div className="flex flex-col gap-2">
        {!isToolResult && (
          <>
            {contentString.length > 0 && (
              <div className="py-1">
                {shouldRenderMarkdown ? (
                  <MarkdownText>{contentString}</MarkdownText>
                ) : (
                  <div className="bg-muted/30 rounded-xl px-4 py-3">
                    <pre className="m-0 whitespace-pre-wrap break-words text-sm leading-6">
                      {throttledPlainText}
                    </pre>
                    {isTruncated && (
                      <p className="text-muted-foreground mt-2 text-xs">
                        {isStreamingMessage
                          ? `为保证流畅输出，仅显示最后 ${MAX_STREAMING_RENDER_CHARS.toLocaleString()} 个字符（总计 ${contentString.length.toLocaleString()}）。`
                          : `内容过大，已切换为纯文本并仅显示最后 ${MAX_PLAINTEXT_RENDER_CHARS.toLocaleString()} 个字符（总计 ${contentString.length.toLocaleString()}）。`}
                      </p>
                    )}
                    {!isStreamingMessage &&
                      !isTruncated &&
                      contentString.length > MAX_MARKDOWN_RENDER_CHARS && (
                        <p className="text-muted-foreground mt-2 text-xs">
                          内容较大，已切换为纯文本渲染以避免卡顿。
                        </p>
                      )}
                  </div>
                )}
              </div>
            )}

            {!hideToolCalls && (
              <>
                {(hasToolCalls && toolCallsHaveContents && (
                  <ToolCalls
                    toolCalls={message.tool_calls}
                    toolResults={thread.messages.filter(
                      (m): m is import("@langchain/langgraph-sdk").ToolMessage =>
                        m.type === "tool" &&
                        !!message.tool_calls?.some(tc => tc.id === (m as any).tool_call_id)
                    )}
                  />
                )) ||
                  (hasAnthropicToolCalls && (
                    <ToolCalls
                      toolCalls={anthropicStreamedToolCalls}
                      toolResults={thread.messages.filter(
                        (m): m is import("@langchain/langgraph-sdk").ToolMessage =>
                          m.type === "tool" &&
                          anthropicStreamedToolCalls?.some(tc => tc.id === (m as any).tool_call_id)
                      )}
                    />
                  )) ||
                  (hasToolCalls && (
                    <ToolCalls
                      toolCalls={message.tool_calls}
                      toolResults={thread.messages.filter(
                        (m): m is import("@langchain/langgraph-sdk").ToolMessage =>
                          m.type === "tool" &&
                          !!message.tool_calls?.some(tc => tc.id === (m as any).tool_call_id)
                      )}
                    />
                  ))}
              </>
            )}

            {message && (
              <CustomComponent
                message={message}
                thread={thread}
              />
            )}
            <Interrupt
              interruptValue={threadInterrupt?.value}
              isLastMessage={isLastMessage}
              hasNoAIOrToolMessages={hasNoAIOrToolMessages}
            />
            <div
              className={cn(
                "mr-auto flex items-center gap-2 transition-opacity",
                "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
              )}
            >
              <BranchSwitcher
                branch={meta?.branch}
                branchOptions={meta?.branchOptions}
                onSelect={(branch) => thread.setBranch(branch)}
                isLoading={isLoading}
              />
              <CommandBar
                content={contentString}
                isLoading={isLoading}
                isAiMessage={true}
                handleRegenerate={() => handleRegenerate(parentCheckpoint)}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
// NOTE  My80OmFIVnBZMlhuZzV2bmtJWTZNVWxYY2c9PTo5ZTdmN2ZkZA==

export function AssistantMessageLoading() {
  return (
    <div className="mr-auto flex items-start gap-2">
      <div className="bg-muted flex h-8 items-center gap-1 rounded-2xl px-4 py-2">
        <div className="bg-foreground/50 h-1.5 w-1.5 animate-[pulse_1.5s_ease-in-out_infinite] rounded-full"></div>
        <div className="bg-foreground/50 h-1.5 w-1.5 animate-[pulse_1.5s_ease-in-out_0.5s_infinite] rounded-full"></div>
        <div className="bg-foreground/50 h-1.5 w-1.5 animate-[pulse_1.5s_ease-in-out_1s_infinite] rounded-full"></div>
      </div>
    </div>
  );
}
