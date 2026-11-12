import { parseVnd } from "./format.js";

function groupedInteger(value) {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function caretAfterDigits(value, count) {
  if (!count) return 0;
  for (let index = 0; index < value.length; index += 1) {
    if (/\d/.test(value[index])) count -= 1;
    if (!count) return index + 1;
  }
  return value.length;
}

// Only discard grouping dots already owned by the input when a digit-only edit
// makes their old positions obsolete. Pasted signs/decimals must reach validation.
export function formatVndInputEdit(previous, raw, start = raw.length, end = start, { inputType = "", data = null } = {}) {
  let amount = parseVnd(raw);
  const previousAmount = parseVnd(previous);
  const wasGrouped = previousAmount !== null && previous === groupedInteger(previousAmount);
  const digitEdit = typeof data === "string" && /^\d+$/.test(data);
  const deletion = inputType.startsWith("delete");
  if (amount === null && wasGrouped && (digitEdit || deletion) && /^[\d.]+$/.test(raw)) {
    amount = parseVnd(raw.replaceAll(".", ""));
  }
  if (amount === null) return { value: raw, start, end };

  const value = groupedInteger(amount);
  return {
    value,
    start: caretAfterDigits(value, (raw.slice(0, start).match(/\d/g) || []).length),
    end: caretAfterDigits(value, (raw.slice(0, end).match(/\d/g) || []).length),
  };
}

// A grouping separator should not make Backspace/Delete appear to do nothing.
export function deleteVndGroupingDigit(value, start, end, key) {
  const amount = parseVnd(value);
  if (start !== end || amount === null || value !== groupedInteger(amount)) return null;
  let removed;
  if (key === "Backspace" && value[start - 1] === ".") removed = start - 2;
  else if (key === "Delete" && value[start] === ".") removed = start + 1;
  else return null;
  const raw = value.slice(0, removed) + value.slice(removed + 1);
  const caret = key === "Backspace" ? removed : start;
  return formatVndInputEdit(value, raw, caret, caret, { inputType: "deleteContent" });
}
