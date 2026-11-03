const VIETNAMESE_TEXT = /[À-ỹĐđ]/u;

export function localizeJsxText() {
  return {
    name: "homewallet-localize-jsx-text",
    enforce: "pre",
    transform(source, id) {
      const filename = id.split("?")[0].replaceAll("\\", "/");
      if (!filename.endsWith(".jsx") || !filename.includes("/src/pages/") || filename.endsWith("/ReactAuth.jsx")) return null;
      let changed = false;
      let output = source.replace(/>([^<>]+)</gu, (whole, text, offset) => {
        const previousTagStart = source.lastIndexOf("<", offset);
        const openTag = source.slice(previousTagStart, offset);
        if (!/^<\/?[A-Za-z][\w.:-]*(?:\s|$)/u.test(openTag) && openTag !== "<>") return whole;
        // Regex-based JSX text handling must skip expression-bearing children;
        // otherwise a `>` in a nested expression can make us wrap executable JS.
        if (text.includes("{") || text.includes("}")) return whole;
        if (!VIETNAMESE_TEXT.test(text)) return whole;
        changed = true;
        return `>{t(${JSON.stringify(text)})}<`;
      });
      output = output.replace(/\b(placeholder|title|alt|aria-label)="([^"]*[À-ỹĐđ][^"]*)"/gu, (_whole, attribute, value) => {
        changed = true;
        return `${attribute}={t(${JSON.stringify(value)})}`;
      });
      if (!changed) return null;
      const alreadyImportsTranslator = /import\s*\{[^}]*\bt\b[^}]*\}\s*from\s*["']\.\.\/preferences["']/u.test(output);
      return { code: `${alreadyImportsTranslator ? "" : 'import { t } from "../preferences";\n'}${output}`, map: null };
    },
  };
}
