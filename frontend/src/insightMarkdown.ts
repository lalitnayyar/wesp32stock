// Markdown export of an AI insight (Analytics page). Lalit Stock Application - not financial advice.

export interface InsightExport {
  portfolio: string;
  taskLabel: string;
  question?: string;
  provider: string;
  model: string;
  text: string;
  disclaimer: string;
  generatedAt: Date;
}

export function insightMarkdown(i: InsightExport): string {
  const lines = [
    `# ${i.taskLabel}: ${i.portfolio}`,
    "",
    `- **Generated:** ${i.generatedAt.toLocaleString()}`,
    `- **AI provider:** ${i.provider} (${i.model})`,
  ];
  if (i.question?.trim()) lines.push(`- **Question:** ${i.question.trim()}`);
  lines.push("", "---", "", i.text.trim(), "", "---", "", `> ${i.disclaimer}`, "",
    "_Lalit Stock Application. Informational only, not financial advice._", "");
  return lines.join("\n");
}

export function insightFilename(portfolio: string, task: string, at: Date): string {
  const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "portfolio";
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${at.getFullYear()}${p(at.getMonth() + 1)}${p(at.getDate())}-${p(at.getHours())}${p(at.getMinutes())}`;
  return `insight-${slug(portfolio)}-${slug(task)}-${stamp}.md`;
}

export function downloadText(filename: string, text: string, type = "text/markdown;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
