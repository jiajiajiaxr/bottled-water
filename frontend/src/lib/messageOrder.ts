import type { ChatMessage } from "@/types";

type TimelineRecord = {
  message: ChatMessage;
  source: "history" | "stream";
  time: number;
  fallbackOrder: number;
  rank: number;
};

export function mergeVisibleMessagesForDisplay(
  historyMessages: ChatMessage[],
  streamingMessages: Map<string, ChatMessage>,
  displayOrder: string[],
): ChatMessage[] {
  const records: TimelineRecord[] = [];
  const historyKeys = new Set<string>();
  const historyKeyRanks = new Map<string, number>();

  const historyRecords = historyMessages
    .map((message, index) => ({
      message,
      source: "history" as const,
      time: messageTime(message),
      fallbackOrder: index,
      rank: index,
    }))
    .sort((left, right) => {
      if (left.time !== right.time) return left.time - right.time;
      return left.fallbackOrder - right.fallbackOrder;
    })
    .map((record, index) => ({ ...record, rank: index }));

  historyRecords.forEach((record) => {
    const { message, rank } = record;
    for (const key of messageIdentityKeys(message)) {
      historyKeys.add(key);
      historyKeyRanks.set(key, rank);
    }
    records.push(record);
  });

  displayOrder.forEach((streamKey, index) => {
    const message = streamingMessages.get(streamKey);
    if (!message) return;
    if (messageIdentityKeys(message).some((key) => historyKeys.has(key))) {
      return;
    }
    const anchorRank = streamAnchorRank(message, historyKeyRanks);
    if (anchorRank === undefined && streamBoundaryKeys(message).length > 0) {
      return;
    }
    records.push({
      message,
      source: "stream",
      time: messageTime(message),
      fallbackOrder: historyMessages.length + index,
      rank:
        anchorRank === undefined
          ? streamTimeRank(message, historyRecords) + index / 1000000
          : anchorRank + 0.5 + index / 1000000,
    });
  });

  return records
    .sort((left, right) => {
      if (left.rank !== right.rank) return left.rank - right.rank;
      if (left.time !== right.time) return left.time - right.time;
      if (left.source !== right.source) {
        return left.source === "history" ? -1 : 1;
      }
      return left.fallbackOrder - right.fallbackOrder;
    })
    .map((record) => record.message);
}

function messageTime(message: ChatMessage): number {
  const time = Date.parse(message.createdAt);
  return Number.isFinite(time) ? time : Number.MAX_SAFE_INTEGER;
}

function messageIdentityKeys(message: ChatMessage): string[] {
  const raw = message.rawContent ?? {};
  return [
    message.id,
    message.clientMessageId,
    message.client_message_id,
    raw.agent_message_id,
    raw.message_id,
    raw.clientMessageId,
    raw.client_message_id,
  ]
    .map((value) => (typeof value === "string" ? value.trim() : ""))
    .filter(Boolean);
}

function streamAnchorRank(
  message: ChatMessage,
  historyKeyRanks: Map<string, number>,
): number | undefined {
  let rank: number | undefined;
  for (const value of streamBoundaryKeys(message)) {
    const itemRank = historyKeyRanks.get(String(value));
    if (itemRank === undefined) continue;
    rank = rank === undefined ? itemRank : Math.max(rank, itemRank);
  }
  return rank;
}

function streamBoundaryKeys(message: ChatMessage): string[] {
  const raw = message.rawContent ?? {};
  return Array.isArray(raw._streamHistoryBoundaryIds)
    ? raw._streamHistoryBoundaryIds
        .map((value) => (typeof value === "string" ? value.trim() : ""))
        .filter(Boolean)
    : [];
}

function streamTimeRank(
  message: ChatMessage,
  historyRecords: TimelineRecord[],
): number {
  const time = messageTime(message);
  if (!Number.isFinite(time)) {
    return historyRecords.length + 0.5;
  }
  let rank = -0.5;
  for (const record of historyRecords) {
    if (record.time <= time) {
      rank = record.rank + 0.5;
    }
  }
  return rank;
}
