import type { AvailabilitySlot } from "@/api/rehearsal";

function splitDelimitedLine(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (quoted && line[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === delimiter && !quoted) {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
  }

  if (quoted) throw new Error("CSV 中存在未闭合的引号");
  cells.push(cell.trim());
  return cells;
}

function detectDelimiter(line: string): string {
  if (line.includes("\t")) return "\t";
  if (line.includes("|") || line.includes("｜")) return "|";
  return ",";
}

function isHeaderRow(parts: string[]): boolean {
  const normalized = parts.map((part) => part.replace(/\s/g, "").toLowerCase());
  return ["演员", "演员姓名", "姓名", "actor", "actorname", "name"].includes(normalized[0]);
}

function isMarkdownDivider(parts: string[]): boolean {
  return parts.length === 4 && parts.every((part) => /^:?-{3,}:?$/.test(part));
}

function normalizeParts(parts: string[]): string[] {
  const normalized = parts.map((part) => part.replaceAll("｜", "|").replaceAll("：", ":").trim());
  if (normalized[0] === "") normalized.shift();
  if (normalized[normalized.length - 1] === "") normalized.pop();
  return normalized;
}

function normalizeDate(value: string): string | null {
  const match = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth) return null;
  return `${match[1]}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function normalizeTime(value: string): string | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return null;
  return `${String(hour).padStart(2, "0")}:${match[2]}`;
}

export function parseAvailabilityImport(value: string): AvailabilitySlot[] {
  const slots: AvailabilitySlot[] = [];
  const lines = value.replace(/^\uFEFF/, "").split(/\r?\n/);
  let firstDataLineRead = false;

  lines.forEach((line, index) => {
    const text = line.trim();
    if (!text) return;
    const normalizedLine = text.replaceAll("｜", "|").replaceAll("，", ",");
    const parts = normalizeParts(splitDelimitedLine(normalizedLine, detectDelimiter(normalizedLine)));
    if (!firstDataLineRead) {
      firstDataLineRead = true;
      if (isHeaderRow(parts)) return;
    }
    if (isMarkdownDivider(parts)) return;
    if (parts.length !== 4 || parts.some((part) => !part)) {
      throw new Error(`第 ${index + 1} 行格式错误，应为：演员, 日期, 开始时间, 结束时间`);
    }
    const date = normalizeDate(parts[1]);
    const start = normalizeTime(parts[2]);
    const end = normalizeTime(parts[3]);
    if (!date) throw new Error(`第 ${index + 1} 行日期格式错误，应为 YYYY-MM-DD`);
    if (!start || !end) throw new Error(`第 ${index + 1} 行时间格式错误，应为 HH:MM`);
    if (start >= end) {
      throw new Error(`第 ${index + 1} 行结束时间必须晚于开始时间`);
    }
    slots.push({ actor: parts[0], date, start, end });
  });
  if (slots.length === 0) throw new Error("请先填写至少一条演员可用时间");

  return slots.filter((slot, index, items) => (
    items.findIndex((item) => (
      item.actor === slot.actor
      && item.date === slot.date
      && item.start === slot.start
      && item.end === slot.end
    )) === index
  ));
}

export function parseAvailabilityText(value: string): AvailabilitySlot[] {
  return parseAvailabilityImport(value);
}

export function formatAvailabilityText(slots: AvailabilitySlot[]): string {
  return slots.map((slot) => `${slot.actor} | ${slot.date} | ${slot.start} | ${slot.end}`).join("\n");
}

function escapeCsvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

export function formatAvailabilityCsv(slots: AvailabilitySlot[]): string {
  const header = ["演员", "日期", "开始时间", "结束时间"].join(",");
  const rows = slots.map((slot) => [slot.actor, slot.date, slot.start, slot.end].map(escapeCsvCell).join(","));
  return [header, ...rows].join("\n");
}
