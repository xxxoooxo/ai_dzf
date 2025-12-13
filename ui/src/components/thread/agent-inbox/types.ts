/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

import { BaseMessage } from "@langchain/core/messages";
import { Thread, ThreadStatus } from "@langchain/langgraph-sdk";
import { HumanInterrupt, HumanResponse } from "@langchain/langgraph/prebuilt";
// eslint-disable  MC80OmFIVnBZMlhuZzV2bmtJWTZRV0ZIYXc9PTo3YzY2NGZhZg==

export type HumanResponseWithEdits = HumanResponse &
  (
    | { acceptAllowed?: false; editsMade?: never }
    | { acceptAllowed?: true; editsMade?: boolean }
  );
// eslint-disable  MS80OmFIVnBZMlhuZzV2bmtJWTZRV0ZIYXc9PTo3YzY2NGZhZg==

export type Email = {
  id: string;
  thread_id: string;
  from_email: string;
  to_email: string;
  subject: string;
  page_content: string;
  send_time: string | undefined;
  read?: boolean;
  status?: "in-queue" | "processing" | "hitl" | "done";
};

export interface ThreadValues {
  email: Email;
  messages: BaseMessage[];
  triage: {
    logic: string;
    response: string;
  };
}

export type ThreadData<
  ThreadValues extends Record<string, any> = Record<string, any>,
> = {
  thread: Thread<ThreadValues>;
} & (
  | {
      status: "interrupted";
      interrupts: HumanInterrupt[] | undefined;
    }
  | {
      status: "idle" | "busy" | "error";
      interrupts?: never;
    }
);
// @ts-expect-error  Mi80OmFIVnBZMlhuZzV2bmtJWTZRV0ZIYXc9PTo3YzY2NGZhZg==

export type ThreadStatusWithAll = ThreadStatus | "all";

export type SubmitType = "accept" | "response" | "edit";

export interface AgentInbox {
  /**
   * A unique identifier for the inbox.
   */
  id: string;
  /**
   * The ID of the graph.
   */
  graphId: string;
  /**
   * The URL of the deployment. Either a localhost URL, or a deployment URL.
   */
  deploymentUrl: string;
  /**
   * Optional name for the inbox, used in the UI to label the inbox.
   */
  name?: string;
  /**
   * Whether or not the inbox is selected.
   */
  selected: boolean;
}
// FIXME  My80OmFIVnBZMlhuZzV2bmtJWTZRV0ZIYXc9PTo3YzY2NGZhZg==
