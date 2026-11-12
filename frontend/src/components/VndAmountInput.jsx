import { useLayoutEffect, useRef, useState } from "react";
import { deleteVndGroupingDigit, formatVndInputEdit } from "../vndAmountInput.js";

export default function VndAmountInput({ value, onValueChange, ...props }) {
  const input = useRef(null);
  const [selection, setSelection] = useState(null);

  useLayoutEffect(() => {
    if (selection && document.activeElement === input.current) {
      input.current.setSelectionRange(selection.start, selection.end);
    }
  }, [value, selection]);

  function applyEdit(edit) {
    onValueChange(edit.value);
    setSelection({ start: edit.start, end: edit.end });
  }

  return <input {...props} ref={input} type="text" inputMode="numeric" value={value}
    onChange={(event) => {
      const field = event.target;
      const native = event.nativeEvent;
      applyEdit(native.isComposing
        ? { value: field.value, start: field.selectionStart, end: field.selectionEnd }
        : formatVndInputEdit(value, field.value, field.selectionStart, field.selectionEnd, native));
    }}
    onPaste={(event) => {
      const data = event.clipboardData.getData("text");
      const field = event.currentTarget;
      const raw = value.slice(0, field.selectionStart) + data + value.slice(field.selectionEnd);
      const caret = field.selectionStart + data.length;
      event.preventDefault();
      applyEdit(formatVndInputEdit(value, raw, caret, caret, { inputType: "insertFromPaste", data }));
    }}
    onKeyDown={(event) => {
      if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
      const field = event.currentTarget;
      const edit = deleteVndGroupingDigit(value, field.selectionStart, field.selectionEnd, event.key);
      if (edit) {
        event.preventDefault();
        applyEdit(edit);
      }
    }}
  />;
}
